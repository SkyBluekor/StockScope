"""S16: read-only local maturity and observation coverage, never Q7 approval.

A frozen Scanner record is evaluated only when S7 verifies its snapshot
integrity (including LEGACY_LIMITED). Observation is signal-day EOD close
change, not entry/exit profit, trading advice, model uplift or an independent
approval sample. Missing / future-dated price data do not become zeros.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import math
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app.prospective.evaluation import ProspectiveEvaluator, ProspectiveEvaluationError
from app.market.session_calendar_s21 import CALENDAR_VERSION, unresolved_weekdays
from app.strategy.models import StrategyName

from .decision_reviewer_offline import DecisionReviewContractError
# Only literal, reviewed S3 projection codes from decision_reviewer_offline.py
# may pass into aggregate reports. No dynamic addition of raw exception text,
# policy IDs or candidate/source details.
KNOWN_S3_PROJECTION_CODES = frozenset({
    "CAPTURE_OR_PROTOCOL_NOT_READY",
    "SNAPSHOT_MISSING",
    "SNAPSHOT_HASH_MISMATCH",
    "CAPTURE_IDENTITY_MISMATCH",
    "ACTION_OUT_OF_SCOPE",
    "CANDIDATE_IDENTITY_MISMATCH",
    "BASELINE_EVIDENCE_INCOMPLETE",
    "BASELINE_RANK_MISMATCH",
    "BASELINE_RISK_MISSING",
    "RISK_BLOCKED_OUT_OF_SCOPE",
    "POLICY_PROVENANCE_UNVERIFIED",
    "POLICY_PIN_MISMATCH",
    "SEMANTIC_SOURCE_INVALID",
    "ENGINE_EVIDENCE_INCOMPLETE",
    "ENGINE_PASS_PROOF_MISMATCH",
    "STRATEGY_IDENTITY_MISMATCH",
    "SIGNAL_DATE_INVALID",
    "FUTURE_OR_MISMATCHED_EVIDENCE_DATE",
    "HORIZON_OUT_OF_SCOPE",
    "SEMANTIC_SOURCE_V2_MISSING",
    "SEMANTIC_SOURCE_V2_VERSION_UNSUPPORTED",
    "SEMANTIC_SOURCE_V2_CONTRACT_HASH_MISMATCH",
    "SEMANTIC_SOURCE_V2_HASH_MISMATCH",
    "SEMANTIC_SOURCE_V2_BASE_MISSING",
    "SEMANTIC_SOURCE_V2_BASE_IDENTITY_MISMATCH",
    "SEMANTIC_SOURCE_V2_RELATIONS_MISSING",
    "SEMANTIC_SOURCE_V2_RELATION_HASH_MISMATCH",
    "SEMANTIC_SOURCE_V2_CONDITIONS_MISSING",
    "SEMANTIC_SOURCE_V2_ASSERTION_MAPPING_MISMATCH",
})
SAFE_INTEGRITY_REASON_CODES = frozenset(EXPLAIN) | KNOWN_S3_PROJECTION_CODES

from .q7_diagnosis_s18 import classify_capture_timing
from .scanner_integrity_s7_1 import EXPLAIN, assess_frozen_candidate
from .scanner_shadow_s7 import EVALUATION_SPEC, WINDOWS, load_frozen_candidates


VERSION = "Q7_S16_READONLY_COHORT_MATURITY_V1"
_MAX_CAPTURES = 260  # about one year of weekday sessions; bounded SQL work
_MAX_TOTAL_SAMPLES = 6000  # stop before a large market-history read
_MAX_SAMPLES = 499  # 500 rows from S7 loader might be a truncated capture.
_STRATEGIES = frozenset(s.value for s in StrategyName if s is not StrategyName.NO_TRADE)
_KST = ZoneInfo("Asia/Seoul")


def _base(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "source_scope": "LOCAL_FROZEN_CAPTURE_AND_MARKET_STORE_READ_ONLY",
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
        "model_uplift_verified": False,
        "real_trade_profit_measured": False,
        "external_provider_calls": 0,
        "runtime_db_writes": 0,
        **extra,
    }


def _code(value: Any) -> str:
    if (type(value) is str and 1 <= len(value) <= 80
            and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in value)):
        return value
    return "UNAVAILABLE"


def _as_of(value: date | None) -> date:
    today = datetime.now(_KST).date()
    if value is None:
        return today
    if type(value) is not date or value > today:
        raise ValueError("Q7_S16_AS_OF_FUTURE_OR_INVALID")
    return value


def _strategy(sample: dict[str, Any]) -> str:
    key = sample.get("strategy")
    return key if type(key) is str and key in _STRATEGIES else "UNKNOWN"


def _empty_window(denominator: int) -> dict[str, Any]:
    return {
        "readiness_denominator": denominator,
        "observed": 0,
        "awaiting_future_trading_days": 0,
        "price_missing": 0,
        "market_evidence_unavailable": 0,
        "post_as_of_data_rejected": 0,
        "unverified_calendar_or_market_gap": 0,
        "gap_with_insufficient_confirmed_sessions": 0,
        "gap_with_sufficient_confirmed_sessions": 0,
        "average_signal_close_change_pct": None,
        "positive_observations": 0,
        "negative_observations": 0,
        "unchanged_observations": 0,
    }


def _record_windows(
    observation: dict[str, Any], as_of: date, *, signal_date: str | None = None,
) -> tuple[dict[int, tuple[str, float | None]], str | None]:
    """Check each window independently; never skip unknown in-between sessions.

    When evaluator supplies individual horizon end dates, a future 20d result
    may not invalidate an independently matured 5d result.
    """
    through = observation.get("evaluated_through")
    try:
        observed_through = date.fromisoformat(str(through)) if through else None
    except ValueError:
        return {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}, "DATE_INVALID"
    details = observation.get("details")
    details = details if isinstance(details, dict) else {}
    windows_end = details.get("observation_window_end_dates")
    windows_end = windows_end if isinstance(windows_end, dict) else {}
    known_days = details.get("observed_market_days")
    gap_check_enabled = (
        signal_date is not None and isinstance(known_days, list)
        and all(isinstance(day, str) for day in known_days)
    )
    try:
        signal = date.fromisoformat(signal_date) if gap_check_enabled else None
        market_days = [date.fromisoformat(day) for day in known_days] if gap_check_enabled else []
    except (ValueError, TypeError):
        return {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}, "MARKET_DAYS_INVALID"

    available = observation.get("available_trading_days")
    if type(available) is not int or available < 0:
        return {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}, "DAYS_INVALID"
    if gap_check_enabled and (len(market_days) != available or market_days != sorted(set(market_days))):
        return {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}, "MARKET_DAYS_MISMATCH"
    reference = details.get("reference_price")
    out: dict[int, tuple[str, float | None]] = {}
    issues: set[str] = set()
    for window in WINDOWS:
        window_end_raw = windows_end.get(f"{window}d")
        try:
            window_end = (
                date.fromisoformat(str(window_end_raw))
                if window_end_raw else observed_through
            )
        except ValueError:
            out[window] = ("MARKET_EVIDENCE_UNAVAILABLE", None)
            issues.add("DATE_INVALID")
            continue
        if window_end is not None and window_end > as_of:
            out[window] = ("POST_AS_OF_DATA_REJECTED", None)
            issues.add("FUTURE_DATED_MARKET_EVIDENCE")
            continue
        # Missing weekdays in a complete window's span invalidate that window
        # even when later EOD rows exist. For immature windows only classify
        # unresolved dates through the permitted as-of cutoff.
        until = window_end if available >= window and window_end else as_of
        if signal is not None and until >= signal and unresolved_weekdays(
            signal, until, market_days,
        ):
            out[window] = ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None)
            continue
        candidate = observation.get(f"return_{window}d")
        if available < window:
            out[window] = ("AWAITING_FUTURE_DAYS", None)
        elif (
            type(reference) not in (int, float) or not math.isfinite(reference)
            or reference <= 0 or type(candidate) not in (int, float)
            or not math.isfinite(candidate)
        ):
            out[window] = ("PRICE_MISSING", None)
        else:
            out[window] = ("OBSERVED", float(candidate))
    return out, (sorted(issues)[0] if issues else None)


def _capture_rows(simulation_db: Path) -> tuple[int, list[dict[str, Any]]]:
    with sqlite3.connect(simulation_db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        tables = {str(row["name"]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"prospective_capture_run", "prospective_recommendation_sample"} <= tables:
            raise DecisionReviewContractError("Q7_S16_SCHEMA_NOT_READY")
        total = int(conn.execute(
            "SELECT COUNT(*) FROM prospective_capture_run WHERE status='COMPLETE'"
        ).fetchone()[0])
        rows = conn.execute(
            "SELECT r.id,COUNT(s.sample_index) AS sample_count FROM prospective_capture_run r "
            "LEFT JOIN prospective_recommendation_sample s ON s.capture_run_id=r.id "
            "WHERE r.status='COMPLETE' GROUP BY r.id "
            "ORDER BY r.completed_at DESC,r.id DESC LIMIT ?",
            (_MAX_CAPTURES,),
        ).fetchall()
        return total, [dict(row) for row in rows]


def measure(
    simulation_db: Path, market_db: Path, *, as_of: date | None = None,
) -> dict[str, Any]:
    """Observe available *existing* local future bars with complete denominators.

    Never writes to either SQLite database, downloads remote prices, or
    starts a Prospective evaluation run. A missing bar or stale capture
    remains absent, never an inferred economic outcome.
    """
    cutoff = _as_of(as_of)
    # Day-of-run EOD may not have been published or fully verified yet.
    # Only yesterday or earlier is eligible for S16 local outcome proof.
    market_cutoff = min(cutoff, datetime.now(_KST).date() - timedelta(days=1))
    simulation_db, market_db = Path(simulation_db), Path(market_db)
    if not simulation_db.is_file():
        return _base("NO_SIMULATION_DB")
    if not market_db.is_file():
        return _base("NO_MARKET_DB")
    try:
        total, rows = _capture_rows(simulation_db)
    except (DecisionReviewContractError, sqlite3.Error):
        return _base("SCHEMA_OR_DB_READ_UNAVAILABLE")
    if not rows:
        return _base("NO_COMPLETE_CAPTURES", total_complete_captures=0)
    if (len(rows) != total or any(int(x["sample_count"]) > _MAX_SAMPLES for x in rows)
            or sum(int(x["sample_count"]) for x in rows) > _MAX_TOTAL_SAMPLES):
        return _base(
            "COHORT_TOO_LARGE_FOR_COMPLETE_AUDIT",
            total_complete_captures=total,
            auditable_captures=len(rows),
            sample_cap_per_capture=_MAX_SAMPLES,
            total_sample_cap=_MAX_TOTAL_SAMPLES,
            counts_complete=False,
        )

    evaluator = ProspectiveEvaluator(market_db)
    integrity_counts: Counter[str] = Counter()
    invalid_check_failures: Counter[str] = Counter()
    invalid_reason_codes: Counter[str] = Counter()
    invalid_without_failed_checks = 0
    invalid_rank_source_missing: Counter[str] = Counter()
    skipped_reasons: Counter[str] = Counter()
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    strategy_counts: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    entries = references = duplicates = inspected = 0
    retro = forward_unverified = 0
    completion_timing_counts: Counter[str] = Counter()

    try:
        for row in rows:
            pairs = load_frozen_candidates(
                simulation_db, capture_id=str(row["id"]), limit=500,
            )
            if len(pairs) != int(row["sample_count"]):
                return _base("CAPTURE_CHANGED_DURING_READ", counts_complete=False)
            inspected += len(pairs)
            for capture, sample in pairs:
                if sample.get("action") != "ENTRY_CANDIDATE":
                    references += 1
                    continue
                entries += 1
                name = _strategy(sample)
                if name not in strategy_counts:
                    strategy_counts[name] = {
                        "entries": 0, "integrity_valid": 0, "invalid": 0,
                        "distinct_keys": 0, "duplicate_keys": 0,
                        "observations": {
                            f"{w}d": _empty_window(0) for w in WINDOWS
                        },
                    }
                group = strategy_counts[name]
                group["entries"] += 1
                key = (
                    str(sample.get("signal_date")), str(sample.get("market")),
                    str(sample.get("ticker")), name,
                )
                if key in seen:
                    duplicates += 1
                    group["duplicate_keys"] += 1
                else:
                    seen.add(key)
                    group["distinct_keys"] += 1
                timing_class = classify_capture_timing(
                    capture.get("completed_at"), sample.get("signal_date"),
                )
                completion_timing_counts[timing_class] += 1
                # Preserve the historical counter for existing clients, but
                # expose its actual meaning. A later local completion date
                # does NOT prove retrospective selection or use of future bars.
                if timing_class in {
                    "NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED",
                    "LATER_THAN_SIGNAL_CALENDAR_DAY_OTHER",
                }:
                    retro += 1
                else:
                    forward_unverified += 1

                integrity = assess_frozen_candidate(capture, sample)
                category = integrity.get("category")
                if category not in ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID"):
                    return _base("INTEGRITY_CONTRACT_INVALID", counts_complete=False)
                integrity_counts[category] += 1
                if category == "INVALID":
                    group["invalid"] += 1
                    skipped_reasons["FROZEN_INTEGRITY_INVALID"] += 1
                    failed = 0
                    # Counts overlap: one INVALID candidate can have several
                    # failing checks and reasons. Never reinterpret as distinct
                    # candidates or expose any policy/source identifiers.
                    for field in ("rank", "strategy", "policy", "engine",
                                  "dates", "risk", "strict_s3"):
                        check = integrity.get(field)
                        if isinstance(check, dict) and check.get("status") == "FAIL":
                            invalid_check_failures[field] += 1
                            failed += 1
                    if not failed:
                        invalid_without_failed_checks += 1
                    rank_check = integrity.get("rank")
                    if isinstance(rank_check, dict) and rank_check.get("status") == "FAIL":
                        # Only booleans about where the public Scanner rank
                        # disappeared. Never export rank values or candidate IDs.
                        snapshot_missing = rank_check.get("snapshot_priority") is None
                        stored_missing = rank_check.get("stored") is None
                        if snapshot_missing:
                            invalid_rank_source_missing["snapshot_priority_rank_missing"] += 1
                        if stored_missing:
                            invalid_rank_source_missing["stored_sample_rank_missing"] += 1
                        if snapshot_missing and stored_missing:
                            invalid_rank_source_missing["both_rank_sources_missing"] += 1
                    codes = integrity.get("codes")
                    if isinstance(codes, list):
                        # Deduplicate *after* normalization. Several distinct
                        # unrecognized S7 strings from one INVALID candidate
                        # collapse into the same privacy-safe OTHER_S7_CODE.
                        # Counting before normalization can exceed the number
                        # of INVALID candidates and makes the G0c contract
                        # falsely fail on an otherwise readable local cohort.
                        normalized = {
                            code if type(code) is str and code in SAFE_INTEGRITY_REASON_CODES
                            else "OTHER_S7_CODE"
                            for code in codes
                        }
                        for key in normalized:
                            invalid_reason_codes[key] += 1
                    continue
                group["integrity_valid"] += 1
                try:
                    obs = evaluator.evaluate_sample(
                        sample=sample,
                        spec={**EVALUATION_SPEC, "as_of_date": market_cutoff.isoformat(),
                              "require_complete_market_eod": True},
                    )
                    windows, issue = _record_windows(
                        obs, market_cutoff, signal_date=str(sample.get("signal_date")),
                    )
                    available_sessions = obs.get("available_trading_days")
                    if issue:
                        skipped_reasons[_code(issue)] += 1
                except (ProspectiveEvaluationError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                    reason = _code(getattr(exc, "code", "MARKET_EVIDENCE_UNAVAILABLE"))
                    skipped_reasons[reason] += 1
                    windows = {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}
                    available_sessions = None

                for window in WINDOWS:
                    label = f"{window}d"
                    win = group["observations"][label]
                    win["readiness_denominator"] += 1
                    state, value = windows[window]
                    if state == "OBSERVED":
                        if value is None:
                            return _base("OBSERVATION_CONTRACT_INVALID", counts_complete=False)
                        win["observed"] += 1
                        win["positive_observations"] += int(value > 0)
                        win["negative_observations"] += int(value < 0)
                        win["unchanged_observations"] += int(value == 0)
                        values[name][label].append(value)
                    elif state == "AWAITING_FUTURE_DAYS":
                        win["awaiting_future_trading_days"] += 1
                    elif state == "PRICE_MISSING":
                        win["price_missing"] += 1
                    elif state == "POST_AS_OF_DATA_REJECTED":
                        win["post_as_of_data_rejected"] += 1
                    elif state == "UNVERIFIED_CALENDAR_OR_DATA_GAP":
                        win["unverified_calendar_or_market_gap"] += 1
                        # Orthogonal subtype, not a relaxation of S16's
                        # conservative calendar gate. In particular, fewer
                        # confirmed sessions is NOT proof that the horizon is
                        # truly immature: an unknown weekday could be a market
                        # session or an unverified closure.
                        if type(available_sessions) is not int or available_sessions < 0:
                            return _base("OBSERVATION_CONTRACT_INVALID", counts_complete=False)
                        subgroup = (
                            "gap_with_insufficient_confirmed_sessions"
                            if available_sessions < window
                            else "gap_with_sufficient_confirmed_sessions"
                        )
                        win[subgroup] += 1
                    else:
                        win["market_evidence_unavailable"] += 1
    except (DecisionReviewContractError, sqlite3.Error, KeyError, ValueError, TypeError):
        return _base("COHORT_AUDIT_FAILED", counts_complete=False)

    summary = {f"{w}d": _empty_window(0) for w in WINDOWS}
    for name in sorted(strategy_counts):
        for window in WINDOWS:
            label = f"{window}d"
            item = strategy_counts[name]["observations"][label]
            measured = values[name][label]
            item["average_signal_close_change_pct"] = (
                round(sum(measured) / len(measured), 4) if measured else None
            )
            root = summary[label]
            for key in (
                "readiness_denominator", "observed", "awaiting_future_trading_days",
                "price_missing", "market_evidence_unavailable",
                "post_as_of_data_rejected", "unverified_calendar_or_market_gap",
                "gap_with_insufficient_confirmed_sessions",
                "gap_with_sufficient_confirmed_sessions",
                "positive_observations",
                "negative_observations", "unchanged_observations",
            ):
                root[key] += item[key]
    for window in WINDOWS:
        label = f"{window}d"
        all_values = [v for strat in values.values() for v in strat[label]]
        summary[label]["average_signal_close_change_pct"] = (
            round(sum(all_values) / len(all_values), 4) if all_values else None
        )

    return _base(
        "DESCRIPTIVE_OBSERVATIONS_ONLY",
        as_of_date=cutoff.isoformat(),
        market_eod_cutoff_date=market_cutoff.isoformat(),
        calendar_evidence_version=CALENDAR_VERSION,
        total_complete_captures=total,
        audited_captures=len(rows),
        counts_complete=True,
        sample_count=inspected,
        entry_candidates=entries,
        reference_only=references,
        duplicated_signal_keys=duplicates,
        distinct_signal_keys=len(seen),
        independent_samples_verified=None,
        retrospective_or_later_capture_count=retro,
        retrospective_or_later_capture_count_deprecated=True,
        later_calendar_day_capture_count=retro,
        completion_timing_counts=dict(sorted(completion_timing_counts.items())),
        independently_proven_retroactive_count=None,
        timing_not_proven_count=forward_unverified,
        integrity_counts={
            k: integrity_counts[k] for k in ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID")
        },
        invalid_check_failure_counts={
            k: invalid_check_failures[k] for k in (
                "rank", "strategy", "policy", "engine", "dates", "risk", "strict_s3"
            )
        },
        invalid_reason_code_counts=dict(sorted(invalid_reason_codes.items())),
        invalid_rank_source_missing_counts={
            key: invalid_rank_source_missing[key] for key in (
                "snapshot_priority_rank_missing",
                "stored_sample_rank_missing",
                "both_rank_sources_missing",
            )
        },
        invalid_without_failed_checks=invalid_without_failed_checks,
        invalid_reason_counts_can_overlap=True,
        gap_subtypes_are_not_independent_calendar_proof=True,
        excluded_reason_counts=dict(sorted(skipped_reasons.items())),
        windows=summary,
        strategy_counts={k: strategy_counts[k] for k in sorted(strategy_counts)},
        notes=[
            "SIGNAL_CLOSE_CHANGE_NOT_EXECUTABLE_ENTRY_RETURN",
            "SAME_COEFFICIENT_ACROSS_CORRELATED_STOCKS_NOT_INDEPENDENT",
            "LEGACY_DERIVED_IS_NOT_ORIGINAL_STRATEGY_IDENTITY",
            "NO_UNBIASED_PRECOMMITTED_HOLDOUT_OR_COMPARABLE_JEV",
            "LATER_LOCAL_COMPLETION_DATE_DOES_NOT_PROVE_RETROSPECTIVE_SELECTION",
            "UNVERIFIED_WEEKDAY_GAP_WITHHOLDS_HORIZON_NOT_EVIDENCE_OF_TRADING_DAY",
            "EOD_OBSERVATION_CUTOFF_IS_NO_LATER_THAN_PREVIOUS_CALENDAR_DAY",
        ],
    )
