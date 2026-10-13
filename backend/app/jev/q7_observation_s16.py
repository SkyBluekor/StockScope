"""S16: read-only local maturity and observation coverage, never Q7 approval.

A frozen Scanner record is evaluated only when S7 verifies its snapshot
integrity (including LEGACY_LIMITED). Observation is signal-day EOD close
change, not entry/exit profit, trading advice, model uplift or an independent
approval sample. Missing / future-dated price data do not become zeros.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import math
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app.prospective.evaluation import ProspectiveEvaluator, ProspectiveEvaluationError
from app.strategy.models import StrategyName

from .decision_reviewer_offline import DecisionReviewContractError
from .scanner_integrity_s7_1 import assess_frozen_candidate
from .scanner_shadow_s7 import EVALUATION_SPEC, WINDOWS, load_frozen_candidates


VERSION = "Q7_S16_READONLY_COHORT_MATURITY_V1"
_MAX_CAPTURES = 20
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
        "average_signal_close_change_pct": None,
        "positive_observations": 0,
        "negative_observations": 0,
        "unchanged_observations": 0,
    }


def _record_windows(observation: dict[str, Any], as_of: date) -> tuple[dict[int, tuple[str, float | None]], str | None]:
    """Never count an EOD return without the bounded future observation."""
    through = observation.get("evaluated_through")
    if through:
        try:
            observed_through = date.fromisoformat(str(through))
        except ValueError:
            return {window: ("MARKET_EVIDENCE_UNAVAILABLE", None) for window in WINDOWS}, "DATE_INVALID"
        if observed_through > as_of:
            return {window: ("POST_AS_OF_DATA_REJECTED", None) for window in WINDOWS}, "FUTURE_DATED_MARKET_EVIDENCE"

    available = observation.get("available_trading_days")
    if type(available) is not int or available < 0:
        return {window: ("MARKET_EVIDENCE_UNAVAILABLE", None) for window in WINDOWS}, "DAYS_INVALID"
    reference = observation.get("details", {}).get("reference_price") if isinstance(observation.get("details"), dict) else None
    out: dict[int, tuple[str, float | None]] = {}
    for window in WINDOWS:
        candidate = observation.get(f"return_{window}d")
        if available < window:
            # No known complete trading window: even a supplied value is suspect.
            out[window] = ("AWAITING_FUTURE_DAYS", None)
        elif (
            type(reference) not in (int, float) or not math.isfinite(reference)
            or reference <= 0 or type(candidate) not in (int, float)
            or not math.isfinite(candidate)
        ):
            out[window] = ("PRICE_MISSING", None)
        else:
            out[window] = ("OBSERVED", float(candidate))
    return out, None


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
    if len(rows) != total or any(int(x["sample_count"]) > _MAX_SAMPLES for x in rows):
        return _base(
            "COHORT_TOO_LARGE_FOR_COMPLETE_AUDIT",
            total_complete_captures=total,
            auditable_captures=len(rows),
            sample_cap_per_capture=_MAX_SAMPLES,
            counts_complete=False,
        )

    evaluator = ProspectiveEvaluator(market_db)
    integrity_counts: Counter[str] = Counter()
    skipped_reasons: Counter[str] = Counter()
    category_windows: dict[str, dict[str, dict[str, Any]]] = {}
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    strategy_counts: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    entries = references = duplicates = inspected = 0
    retro = forward_unverified = 0

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
                completed = capture.get("completed_at")
                signal = sample.get("signal_date")
                try:
                    completed_date = datetime.fromisoformat(completed).astimezone(_KST).date()
                    signal_date = date.fromisoformat(signal)
                except (ValueError, TypeError, AttributeError):
                    completed_date, signal_date = None, None
                # If the completed timestamp is later than the signal date,
                # this sample cannot count as an actual precommitted prediction.
                if completed_date and signal_date and completed_date > signal_date:
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
                    continue
                group["integrity_valid"] += 1
                try:
                    obs = evaluator.evaluate_sample(sample=sample, spec=EVALUATION_SPEC)
                    windows, issue = _record_windows(obs, cutoff)
                    if issue:
                        skipped_reasons[_code(issue)] += 1
                except (ProspectiveEvaluationError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                    reason = _code(getattr(exc, "code", "MARKET_EVIDENCE_UNAVAILABLE"))
                    skipped_reasons[reason] += 1
                    windows = {w: ("MARKET_EVIDENCE_UNAVAILABLE", None) for w in WINDOWS}

                for window in WINDOWS:
                    label = f"{window}d"
                    win = group["observations"][label]
                    win["readiness_denominator"] += 1
                    state, value = windows[window]
                    if state == "OBSERVED":
                        assert value is not None
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
                "post_as_of_data_rejected", "positive_observations",
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
        timing_not_proven_count=forward_unverified,
        integrity_counts={
            k: integrity_counts[k] for k in ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID")
        },
        excluded_reason_counts=dict(sorted(skipped_reasons.items())),
        windows=summary,
        strategy_counts={k: strategy_counts[k] for k in sorted(strategy_counts)},
        notes=[
            "SIGNAL_CLOSE_CHANGE_NOT_EXECUTABLE_ENTRY_RETURN",
            "SAME_COEFFICIENT_ACROSS_CORRELATED_STOCKS_NOT_INDEPENDENT",
            "LEGACY_DERIVED_IS_NOT_ORIGINAL_STRATEGY_IDENTITY",
            "NO_UNBIASED_PRECOMMITTED_HOLDOUT_OR_COMPARABLE_JEV",
        ],
    )
