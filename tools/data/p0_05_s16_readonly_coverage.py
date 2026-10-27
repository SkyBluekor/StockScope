"""P0-05/G0b: existing S16 *on-demand* observational coverage, strictly read-only.

This does NOT create Prospective evaluation runs, capture samples, refresh
prices, activate S17, approve Q7, or persist observed returns. No private
instrument IDs, prices, percentages, snapshot notes or raw error strings in
stdout. Existing G0 inventory must first pass on the *same* inputs.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from tools.data.p0_05_prospective_readonly_audit import inspect as inspect_g0

VERSION = "STOCKSCOPE_P0_05_G0C_S16_READONLY_COVERAGE_V2"
WINDOWS = ("5d", "10d", "20d")
STATES = (
    "readiness_denominator", "observed", "awaiting_future_trading_days",
    "price_missing", "market_evidence_unavailable", "post_as_of_data_rejected",
    "unverified_calendar_or_market_gap",
)
INTEGRITY = ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID")
FAILED_CHECKS = ("rank", "strategy", "policy", "engine", "dates", "risk", "strict_s3")
GAP_SUBTYPES = (
    "gap_with_insufficient_confirmed_sessions",
    "gap_with_sufficient_confirmed_sessions",
)
S16_GOOD = "DESCRIPTIVE_OBSERVATIONS_ONLY"


def _base(code: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": code,
        "source_scope": "G0_INVENTORY_PLUS_EXISTING_S16_LOCAL_EOD",
        "on_demand_calculation_only": True,
        "stored_evaluation_created": False,
        "operational_db_read_only": True,
        "db_write_calls": 0,
        "external_requests": 0,
        "scheduler_triggered": False,
        "scanner_job_started": False,
        "new_capture_created": False,
        "independent_performance_verified": False,
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
        "official_latest_eod_verified": False,
    }


def _counts(value: Any, names: tuple[str, ...]) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for key in names:
        item = value.get(key)
        if type(item) is not int or item < 0:
            return None
        out[key] = item
    return out


def _reason_counts(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict) or len(value) > 60:
        return None
    safe = {}
    for key, n in value.items():
        if (type(key) is not str or not 1 <= len(key) <= 80
                or any(x not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for x in key)
                or type(n) is not int or n < 0):
            return None
        safe[key] = n
    return dict(sorted(safe.items()))


def _summarize(g0: dict[str, Any], s16: dict[str, Any]) -> dict[str, Any]:
    base = _base("HOLD_S16_INCOMPLETE_OR_UNAVAILABLE")
    status = s16.get("status")
    if status != S16_GOOD or s16.get("counts_complete") is not True:
        # Only a static allowlisted reason; never echo unknown exception text.
        code = status if status in {
            "NO_SIMULATION_DB", "NO_MARKET_DB", "SCHEMA_OR_DB_READ_UNAVAILABLE",
            "NO_COMPLETE_CAPTURES", "COHORT_TOO_LARGE_FOR_COMPLETE_AUDIT",
            "CAPTURE_CHANGED_DURING_READ", "INTEGRITY_CONTRACT_INVALID",
            "OBSERVATION_CONTRACT_INVALID", "COHORT_AUDIT_FAILED",
        } else "S16_UNEXPECTED_STATUS"
        return {**base, "status": "HOLD_" + code}
    n_entry = g0.get("entry_candidate_rows")
    n_complete = g0.get("complete_capture_count")
    if (s16.get("entry_candidates") != n_entry
            or s16.get("total_complete_captures") != n_complete
            or s16.get("sample_count") != g0.get("complete_capture_samples")
            or type(s16.get("reference_only")) is not int
            or s16["reference_only"] + n_entry != s16["sample_count"]):
        return {**base, "status": "HOLD_G0_S16_DENOMINATOR_MISMATCH"}

    integrity = _counts(s16.get("integrity_counts"), INTEGRITY)
    if integrity is None or sum(integrity.values()) != n_entry:
        return {**base, "status": "HOLD_S16_INTEGRITY_DENOMINATOR_MISMATCH"}
    observed_eligible = integrity["LOCAL_VALIDATED"] + integrity["LEGACY_LIMITED"]
    failed_checks = _counts(s16.get("invalid_check_failure_counts"), FAILED_CHECKS)
    invalid_codes = _reason_counts(s16.get("invalid_reason_code_counts"))
    unexplained = s16.get("invalid_without_failed_checks")
    # These are fixed, privacy-safe contract failure categories; never echo
    # the underlying S7 code/string or the original frozen sample.
    diagnostic_issue = None
    if failed_checks is None:
        diagnostic_issue = "CHECK_BUCKET_SHAPE_INVALID"
    elif invalid_codes is None:
        diagnostic_issue = "REASON_BUCKET_SHAPE_INVALID"
    elif type(unexplained) is not int or not 0 <= unexplained <= integrity["INVALID"]:
        diagnostic_issue = "UNEXPLAINED_COUNT_INVALID"
    elif s16.get("invalid_reason_counts_can_overlap") is not True:
        diagnostic_issue = "OVERLAP_CONTRACT_MISSING"
    elif any(n > integrity["INVALID"] for n in failed_checks.values()):
        diagnostic_issue = "CHECK_BUCKET_EXCEEDS_INVALID_CANDIDATES"
    elif any(n > integrity["INVALID"] for n in invalid_codes.values()):
        diagnostic_issue = "REASON_BUCKET_EXCEEDS_INVALID_CANDIDATES"
    if diagnostic_issue is not None:
        return {
            **base,
            "status": "HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT",
            "diagnostic_failure_class": diagnostic_issue,
        }

    windows = s16.get("windows")
    if not isinstance(windows, dict):
        return {**base, "status": "HOLD_S16_WINDOW_CONTRACT_INVALID"}
    output: dict[str, dict[str, int]] = {}
    for key in WINDOWS:
        row = _counts(windows.get(key), STATES)
        if row is None:
            return {**base, "status": "HOLD_S16_WINDOW_CONTRACT_INVALID"}
        groups = sum(row[x] for x in STATES if x != "readiness_denominator")
        if (row["readiness_denominator"] != observed_eligible
                or groups != row["readiness_denominator"]):
            return {**base, "status": "HOLD_S16_WINDOW_DENOMINATOR_MISMATCH"}
        split = _counts(windows[key], GAP_SUBTYPES)
        if (split is None
                or sum(split.values()) != row["unverified_calendar_or_market_gap"]
                or s16.get("gap_subtypes_are_not_independent_calendar_proof") is not True):
            return {**base, "status": "HOLD_S16_GAP_SUBTYPE_CONTRACT"}
        output[key] = {**row, **split}

    reasons = _reason_counts(s16.get("excluded_reason_counts"))
    timing = _reason_counts(s16.get("completion_timing_counts"))
    if reasons is None or timing is None:
        return {**base, "status": "HOLD_S16_REASON_CONTRACT_INVALID"}

    return {
        **_base("READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"),
        "s16_version": "Q7_S16_READONLY_COHORT_MATURITY_V1",
        "as_of_market_cutoff": s16.get("market_eod_cutoff_date")
            if type(s16.get("market_eod_cutoff_date")) is str else None,
        "counts_complete": True,
        "complete_captures": n_complete,
        "captured_entry_rows": n_entry,
        "distinct_signal_keys_g0": g0["distinct_entry_signal_keys"],
        "frozen_integrity_categories": integrity,
        "integrity_eligible_for_readonly_observation": observed_eligible,
        "invalid_check_failure_counts": failed_checks,
        "invalid_reason_code_counts": invalid_codes,
        "invalid_without_failed_checks": unexplained,
        "invalid_reason_counts_can_overlap": True,
        "gap_with_insufficient_sessions_is_not_proven_immature": True,
        "on_demand_window_status_counts": output,
        "excluded_reason_counts": reasons,
        "capture_timing_class_counts": timing,
        "stored_evaluation_run_rows": g0["stored_evaluation_inventory"]["evaluation_run_rows"],
        "stored_evaluation_unit_rows": g0["stored_evaluation_inventory"]["evaluation_unit_rows"],
        "source_missing_field_counts": {
            "scanner_baseline": g0["missing_capture_source_field_counts"].get("scanner_baseline", 0),
            "horizon_policy_version": g0["missing_capture_source_field_counts"].get("horizon_policy_version", 0),
        },
        "s16_observed_means_local_signal_close_change_not_realized_trade_return": True,
        "zero_stored_evaluation_runs_does_not_imply_zero_on_demand_observations": True,
    }


def inspect(simulation_db: Path, market_db: Path, *, as_of: date | None = None) -> dict[str, Any]:
    g0 = inspect_g0(simulation_db, market_db, as_of=as_of)
    if g0["status"] != "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED":
        return {**_base("HOLD_G0_INVENTORY_NOT_READY"),
                "g0_status": str(g0["status"]) if str(g0["status"]).startswith("HOLD_")
                else "G0_UNEXPECTED_STATUS"}

    # Import lazily: missing timezone data (on some Windows machines) must
    # yield a bounded HOLD rather than a traceback containing private paths.
    try:
        from zoneinfo import ZoneInfoNotFoundError
        from app.jev.q7_observation_s16 import measure
    except (ImportError, ModuleNotFoundError, ZoneInfoNotFoundError):
        return _base("HOLD_S16_RUNTIME_NOT_READY")

    from tools.data.p0_02_offline_scanner_replay import prohibit_external_connections
    try:
        with prohibit_external_connections() as blocked:
            s16 = measure(simulation_db, market_db, as_of=as_of)
            attempts = len(blocked)
    except Exception:
        # Do not print source path, stock/ticker, private snapshots or notes.
        return _base("HOLD_S16_RUNTIME_EXCEPTION")
    if attempts:
        return _base("HOLD_S16_NETWORK_ATTEMPT_BLOCKED")
    if not isinstance(s16, dict):
        return _base("HOLD_S16_RESPONSE_INVALID")
    return _summarize(g0, s16)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    result = inspect(args.simulation_db, args.market_db, as_of=args.as_of)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
