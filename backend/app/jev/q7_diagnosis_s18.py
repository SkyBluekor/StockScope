"""S18: read-only diagnosis of existing immutable Scanner captures.

This intentionally does not judge economic returns, restore old identities, or
approve JEV. A local S7 INVALID means a strict reviewer failed, not necessarily
that the frozen JSON or market price is corrupted.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app.prospective.models import digest_json
from .scanner_integrity_s7_1 import assess_frozen_candidate

VERSION = "Q7_S18_READONLY_CAPTURE_DIAGNOSIS_V1"
_KST = ZoneInfo("Asia/Seoul")
_CHECKS = ("rank", "strategy", "policy", "engine", "dates", "risk", "strict_s3")
_REQUIRED_CAPTURE = frozenset({
    "id", "status", "completed_at", "actual_data_date", "request_json",
    "source_execution_key", "scanner_version", "scanner_baseline",
    "input_fingerprint", "horizon_intent", "horizon_policy_version",
})
_REQUIRED_SAMPLE = frozenset({
    "capture_run_id", "sample_index", "action", "strategy", "signal_date",
    "market", "ticker", "rank", "snapshot_json", "snapshot_hash",
})


def _report(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "source_scope": "LOCAL_SIMULATION_DB_READ_ONLY",
        "runtime_db_writes": 0,
        "external_provider_calls": 0,
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
        "price_observation_eligibility_proven": False,
        "independent_timestamp_attestation": False,
        **extra,
    }


def _timing(completed_at: Any, signal_date: Any) -> str:
    """Descriptive clock grouping only, NOT evidence of data availability."""
    try:
        if type(completed_at) is not str or type(signal_date) is not str:
            return "TIME_OR_SIGNAL_UNKNOWN"
        stamp = datetime.fromisoformat(completed_at)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return "TIME_OR_SIGNAL_UNKNOWN"
        signal = date.fromisoformat(signal_date)
        local = stamp.astimezone(_KST)
    except (TypeError, ValueError, OverflowError):
        return "TIME_OR_SIGNAL_UNKNOWN"
    if local.date() < signal:
        return "COMPLETED_BEFORE_SIGNAL_CALENDAR_DAY"
    if local.date() == signal:
        return "COMPLETED_ON_SIGNAL_CALENDAR_DAY"
    if local.date() == signal + timedelta(days=1) and local.time() < time(9, 0):
        return "NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED"
    return "LATER_THAN_SIGNAL_CALENDAR_DAY_OTHER"


def _missing_columns(conn: sqlite3.Connection, table: str, required: frozenset[str]) -> list[str]:
    actual = {
        str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")
    }
    return sorted(required - actual)


def diagnose(
    simulation_db: Path, *, detail_limit: int = 40, max_samples: int = 100_000,
) -> dict[str, Any]:
    """Read immutable source rows without writing, changing, or classifying JEV policy.

    Preflight checks that complete captures and all their samples are present.
    Results have complete denominators or explicitly fail closed; details can be
    truncated without truncating aggregates. DB is kept in a single RO snapshot.
    """
    if type(detail_limit) is not int or not 0 <= detail_limit <= 1000:
        raise ValueError("Q7_S18_DETAIL_LIMIT_INVALID")
    if type(max_samples) is not int or not 1 <= max_samples <= 1_000_000:
        raise ValueError("Q7_S18_MAX_SAMPLES_INVALID")
    db = Path(simulation_db).expanduser()
    if not db.is_file():
        return _report("NO_SIMULATION_DB", database_path=str(db.resolve()))
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            tables = {
                str(r["name"]) for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"prospective_capture_run", "prospective_recommendation_sample"} <= tables:
                return _report("SCHEMA_MISSING", database_path=str(db.resolve()), counts_complete=False)
            missing = {
                "prospective_capture_run": _missing_columns(conn, "prospective_capture_run", _REQUIRED_CAPTURE),
                "prospective_recommendation_sample": _missing_columns(conn, "prospective_recommendation_sample", _REQUIRED_SAMPLE),
            }
            if any(missing.values()):
                return _report("SCHEMA_COLUMNS_MISSING", database_path=str(db.resolve()),
                               missing_columns=missing, counts_complete=False)
            status_counts = {
                str(r["status"]): int(r["n"])
                for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM prospective_capture_run GROUP BY status"
                )
            }
            expected = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample s "
                "JOIN prospective_capture_run r ON r.id=s.capture_run_id "
                "WHERE r.status='COMPLETE'"
            ).fetchone()[0])
            if expected > max_samples:
                return _report(
                    "COHORT_TOO_LARGE_FOR_DIAGNOSIS", database_path=str(db.resolve()),
                    counts_complete=False, samples_found=expected,
                    max_samples=max_samples, capture_status_counts=status_counts,
                )

            entry_categories: Counter[str] = Counter()
            invalid_codes: Counter[str] = Counter()
            invalid_code_combinations: Counter[str] = Counter()
            check_failures: Counter[str] = Counter()
            snapshot_failures: Counter[str] = Counter()
            reference_snapshot_failures: Counter[str] = Counter()
            timing: Counter[str] = Counter()
            strategy_categories: dict[str, Counter[str]] = {}
            scanner_version_categories: dict[str, Counter[str]] = {}
            details: list[dict[str, Any]] = []
            captures = entries = references = snapshot_pass = strict_only = 0
            reference_snapshot_pass = 0
            inspected = 0
            for capture_row in conn.execute(
                "SELECT * FROM prospective_capture_run WHERE status='COMPLETE' "
                "ORDER BY completed_at, id"
            ):
                captures += 1
                capture = dict(capture_row)
                # No copy of the full snapshot is ever emitted as diagnostic output.
                for sample_row in conn.execute(
                    "SELECT * FROM prospective_recommendation_sample "
                    "WHERE capture_run_id=? ORDER BY sample_index",
                    (capture["id"],),
                ):
                    inspected += 1
                    sample = dict(sample_row)
                    if sample["action"] != "ENTRY_CANDIDATE":
                        references += 1
                        # S7 validates hashes even for reference-only samples
                        # before loading any candidate. Do not hide this failure.
                        try:
                            reference_snapshot = json.loads(str(sample["snapshot_json"]))
                            if not isinstance(reference_snapshot, dict):
                                raise ValueError("S7_SNAPSHOT_INVALID")
                            if (not sample["snapshot_hash"]
                                    or digest_json(reference_snapshot) != sample["snapshot_hash"]):
                                raise ValueError("S7_SNAPSHOT_HASH_MISMATCH")
                        except (ValueError, TypeError, UnicodeError) as exc:
                            reason = (
                                str(exc) if isinstance(exc, ValueError)
                                and str(exc).startswith("S7_")
                                else "S7_SNAPSHOT_JSON_INVALID"
                            )
                            reference_snapshot_failures[reason] += 1
                        else:
                            reference_snapshot_pass += 1
                        continue
                    entries += 1
                    date_group = _timing(capture["completed_at"], sample["signal_date"])
                    timing[date_group] += 1
                    strategy = str(sample.get("strategy") or "UNKNOWN")
                    scanner_version = str(capture.get("scanner_version") or "UNKNOWN")
                    category = "NOT_ASSESSED"
                    codes: list[str] = []
                    failed_checks: list[str] = []
                    try:
                        snapshot = json.loads(str(sample["snapshot_json"]))
                        if not isinstance(snapshot, dict):
                            raise ValueError("S7_SNAPSHOT_INVALID")
                        if not sample["snapshot_hash"] or digest_json(snapshot) != sample["snapshot_hash"]:
                            raise ValueError("S7_SNAPSHOT_HASH_MISMATCH")
                    except (ValueError, TypeError, UnicodeError) as exc:
                        code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("S7_") else "S7_SNAPSHOT_JSON_INVALID"
                        snapshot_failures[code] += 1
                        category, codes = "SNAPSHOT_UNREADABLE_OR_MISMATCH", [code]
                    else:
                        snapshot_pass += 1
                        sample["snapshot"] = snapshot
                        try:
                            outcome = assess_frozen_candidate(capture, sample)
                            category = str(outcome["category"])
                            codes = sorted(set(str(code) for code in outcome.get("codes", [])))
                            failed_checks = [
                                field for field in _CHECKS
                                if isinstance(outcome.get(field), dict)
                                and outcome[field].get("status") == "FAIL"
                            ]
                            if category not in ("INVALID", "LEGACY_LIMITED", "LOCAL_VALIDATED"):
                                raise ValueError("Q7_S18_S7_CATEGORY_INVALID")
                        except (Exception) as exc:
                            # Individual failures must be counted, not dropped.
                            category = "ASSESSMENT_ERROR"
                            codes = [str(getattr(exc, "code", "Q7_S18_S7_ASSESSMENT_ERROR"))]
                            snapshot_failures["S7_ASSESSMENT_ERROR"] += 1

                    entry_categories[category] += 1
                    strategy_categories.setdefault(strategy, Counter())[category] += 1
                    scanner_version_categories.setdefault(scanner_version, Counter())[category] += 1
                    if category == "INVALID":
                        invalid_codes.update(codes)
                        invalid_code_combinations[" | ".join(codes) or "NO_CODES"] += 1
                        check_failures.update(failed_checks)
                        if failed_checks == ["strict_s3"]:
                            strict_only += 1
                    if len(details) < detail_limit and category in (
                        "INVALID", "ASSESSMENT_ERROR", "SNAPSHOT_UNREADABLE_OR_MISMATCH",
                    ):
                        details.append({
                            "capture_id": str(capture["id"]),
                            "sample_index": int(sample["sample_index"]),
                            "strategy": strategy,
                            "scanner_version": scanner_version,
                            "signal_date": sample["signal_date"],
                            "timing_class": date_group,
                            "category": category,
                            "codes": codes,
                            "failed_checks": failed_checks,
                        })
            if inspected != expected:
                return _report("COHORT_CHANGED_DURING_AUDIT",
                               database_path=str(db.resolve()), counts_complete=False)
            total_problematic = sum(entry_categories.get(k, 0) for k in (
                "INVALID", "ASSESSMENT_ERROR", "SNAPSHOT_UNREADABLE_OR_MISMATCH",
            ))
            return _report(
                "DIAGNOSIS_ONLY", database_path=str(db.resolve()), counts_complete=True,
                capture_status_counts=dict(sorted(status_counts.items())),
                completed_captures_audited=captures,
                all_samples_in_completed_captures=inspected,
                entry_candidates=entries, reference_only=references,
                snapshot_hash_verified_entry_count=snapshot_pass,
                snapshot_hash_verified_reference_count=reference_snapshot_pass,
                reference_snapshot_error_counts=dict(sorted(reference_snapshot_failures.items())),
                entry_categories=dict(sorted(entry_categories.items())),
                invalid_code_counts=dict(sorted(invalid_codes.items())),
                invalid_code_combinations=dict(sorted(invalid_code_combinations.items())),
                failing_check_counts=dict(sorted(check_failures.items())),
                strict_s3_only_invalid_count=strict_only,
                snapshot_or_assessment_error_counts=dict(sorted(snapshot_failures.items())),
                completion_timing_counts=dict(sorted(timing.items())),
                strategy_categories={
                    k: dict(sorted(v.items())) for k, v in sorted(strategy_categories.items())
                },
                scanner_version_categories={
                    k: dict(sorted(v.items())) for k, v in sorted(scanner_version_categories.items())
                },
                problematic_entries=total_problematic,
                problematic_details=details,
                problematic_details_truncated=total_problematic > len(details),
                cautions=[
                    "S7_INVALID_IS_NOT_PROOF_OF_CORRUPTED_PRICES",
                    "STRICT_JEV_CONTRACT_AND_PRICE_OBSERVATION_MUST_BE_SEPARATED",
                    "NEXT_DAY_PREMARKET_IS_NOT_INDEPENDENT_TIMESTAMP_PROOF",
                    "NO_MUTATION_OR_LEGACY_IDENTITY_RECONSTRUCTION",
                ],
            )
    except sqlite3.Error:
        return _report("SIMULATION_DB_READ_FAILED", database_path=str(db.resolve()),
                       counts_complete=False)
