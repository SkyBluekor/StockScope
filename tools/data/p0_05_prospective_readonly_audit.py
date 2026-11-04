"""StockScope P0-05/G0 operational Prospective inventory (strictly read-only).

Never starts S17, S16 evaluation, jobs, providers, migrations or a scheduler.
No ticker, stock, source job, capture ID, price, return, note, JSON payload,
file path or token is emitted. Windows Python does not need a timezone database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

VERSION = "STOCKSCOPE_P0_05_G0_PROSPECTIVE_READONLY_AUDIT_V1"
KST = timezone(timedelta(hours=9), name="KST")
MAX_CAPTURES = 260
MAX_SAMPLES = 6000
WINDOWS = (5, 10, 20)
CAPTURE_STATES = frozenset({
    "PENDING", "COMPLETE", "PARTIAL", "DUPLICATE",
    "FAILED", "CANCELLED", "INTERRUPTED",
})
CAPTURE_FIELDS = {
    "id", "status", "market_scope", "requested_as_of", "actual_data_date",
    "source_execution_key", "source_job_id", "canonical_capture_id",
    "scanner_version", "scanner_baseline", "input_fingerprint",
    "horizon_policy_version", "created_at", "completed_at",
    "returned_candidate_count",
}
SAMPLE_FIELDS = {
    "capture_run_id", "sample_index", "market", "ticker",
    "strategy", "action", "signal_date", "snapshot_hash",
}
MARKET_FIELDS = {"market", "bas_dd", "kind", "status"}
INDEX_FIELDS = {"market", "bas_dd"}


def _base(status: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "operational_db_read_only": True,
        "db_write_calls": 0,
        "external_requests": 0,
        "scheduler_registered_or_triggered": False,
        "scanner_job_started": False,
        "new_capture_created": False,
        "official_latest_eod_verified": False,
        "observed_profit_or_strategy_approval": False,
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
    }


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError()
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")
    }


def _valid_date(raw: Any) -> date | None:
    if type(raw) is not str:
        return None
    try:
        out = date.fromisoformat(raw)
        return out if out.isoformat() == raw else None
    except ValueError:
        return None


def _empty_window() -> dict[str, int]:
    return {
        "entry_candidate_rows": 0,
        "market_sessions_reached": 0,
        "awaiting_market_sessions": 0,
        "market_evidence_unknown": 0,
    }


def _market_days(market_db: sqlite3.Connection, cutoff: date) -> dict[str, list[date]]:
    """Only stored stock-data markers with matching actual index rows.

    This is market session *evidence*, not independently verified holidays,
    stock price coverage, observation or tradeable returns.
    """
    rows = market_db.execute(
        "SELECT DISTINCT d.market,d.bas_dd FROM day_status d "
        "JOIN main_index_daily i ON i.market=d.market AND i.bas_dd=d.bas_dd "
        "WHERE d.kind='stock' AND d.status='data' AND d.bas_dd<=? "
        "ORDER BY d.market,d.bas_dd",
        (cutoff.strftime("%Y%m%d"),),
    )
    result: dict[str, list[date]] = {"KOSPI": [], "KOSDAQ": []}
    for row in rows:
        market = row["market"]
        raw = row["bas_dd"]
        if market not in result or type(raw) is not str or len(raw) != 8 or not raw.isdigit():
            continue
        try:
            day = datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            continue
        result[market].append(day)
    return result


def inspect(simulation_db: Path, market_db: Path, *, as_of: date | None = None) -> dict[str, Any]:
    today = datetime.now(KST).date()
    if as_of is not None and (type(as_of) is not date or as_of > today):
        return _base("HOLD_INVALID_OR_FUTURE_AS_OF")
    # Today's EOD is never assumed to be published.
    cutoff = min(as_of or today, today - timedelta(days=1))
    base = _base("HOLD_NOT_READY")
    if not simulation_db.is_file():
        return {**base, "status": "HOLD_SIMULATION_DB_MISSING"}
    if not market_db.is_file():
        return {**base, "status": "HOLD_MARKET_DB_MISSING"}
    try:
        with closing(_connect(simulation_db)) as sim, closing(_connect(market_db)) as market:
            sim.execute("BEGIN")
            market.execute("BEGIN")
            st, mt = _tables(sim), _tables(market)
            if not {"prospective_capture_run", "prospective_recommendation_sample"} <= st:
                return {**base, "status": "HOLD_PROSPECTIVE_SCHEMA_NOT_READY"}
            if not {"day_status", "main_index_daily"} <= mt:
                return {**base, "status": "HOLD_MARKET_SCHEMA_NOT_READY"}
            if (not CAPTURE_FIELDS <= _columns(sim, "prospective_capture_run")
                    or not SAMPLE_FIELDS <= _columns(sim, "prospective_recommendation_sample")
                    or not MARKET_FIELDS <= _columns(market, "day_status")
                    or not INDEX_FIELDS <= _columns(market, "main_index_daily")):
                return {**base, "status": "HOLD_SCHEMA_INCOMPATIBLE"}

            capture_count = int(sim.execute(
                "SELECT COUNT(*) FROM prospective_capture_run"
            ).fetchone()[0])
            sample_count = int(sim.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample"
            ).fetchone()[0])
            if capture_count > MAX_CAPTURES or sample_count > MAX_SAMPLES:
                return {
                    **base, "status": "HOLD_EXCEEDS_AUDIT_LIMIT",
                    "counts_complete": False,
                    "capture_count": capture_count,
                    "sample_count": sample_count,
                    "limits": {"captures": MAX_CAPTURES, "samples": MAX_SAMPLES},
                }

            captures = [
                dict(x) for x in sim.execute(
                    "SELECT id,status,market_scope,requested_as_of,actual_data_date,"
                    "source_execution_key,source_job_id,canonical_capture_id,"
                    "scanner_version,scanner_baseline,input_fingerprint,"
                    "horizon_policy_version,created_at,completed_at,"
                    "returned_candidate_count FROM prospective_capture_run"
                )
            ]
            samples = [
                dict(x) for x in sim.execute(
                    "SELECT capture_run_id,sample_index,market,ticker,strategy,"
                    "action,signal_date,snapshot_hash "
                    "FROM prospective_recommendation_sample"
                )
            ]
            status_counts: Counter[str] = Counter()
            key_counts: Counter[tuple[str, str]] = Counter()
            id_to_capture: dict[str, dict[str, Any]] = {}
            missing = Counter()
            complete = 0
            for row in captures:
                cid = str(row["id"])
                id_to_capture[cid] = row
                state = row["status"]
                state = state if state in CAPTURE_STATES else "UNRECOGNIZED"
                status_counts[state] += 1
                if state == "COMPLETE":
                    complete += 1
                for field in ("source_job_id", "source_execution_key", "scanner_version",
                              "scanner_baseline", "input_fingerprint", "horizon_policy_version",
                              "actual_data_date", "completed_at"):
                    if row[field] is None or row[field] == "":
                        missing[field] += 1
                key = (str(row["market_scope"]), str(row["actual_data_date"]))
                if state in {"PENDING", "COMPLETE", "PARTIAL", "DUPLICATE"}:
                    key_counts[key] += 1

            bad_canonical = 0
            for row in captures:
                target = row["canonical_capture_id"]
                if target is not None and (
                    str(target) not in id_to_capture
                    or id_to_capture[str(target)]["status"] != "COMPLETE"
                    or row["status"] != "DUPLICATE"
                ):
                    bad_canonical += 1

            complete_samples = [s for s in samples
                                if id_to_capture.get(str(s["capture_run_id"]), {}).get("status") == "COMPLETE"]
            orphan_samples = len(samples) - sum(
                str(s["capture_run_id"]) in id_to_capture for s in samples
            )
            entry_rows = [s for s in complete_samples if s["action"] == "ENTRY_CANDIDATE"]
            invalid_signal_dates = 0
            invalid_market_names = 0
            unique_signal: set[tuple[str, str, str, str]] = set()
            duplicate_signals = 0
            no_sample_captures = sum(
                1 for r in captures if r["status"] == "COMPLETE"
                and not any(s["capture_run_id"] == r["id"] for s in complete_samples)
            )
            for sample in entry_rows:
                key = (str(sample["signal_date"]), str(sample["market"]),
                       str(sample["ticker"]), str(sample["strategy"]))
                if key in unique_signal:
                    duplicate_signals += 1
                else:
                    unique_signal.add(key)
            # Evidence of known market sessions, not proof of a candidate's
            # individual stock quotes or an observed/independent return.
            market_days = _market_days(market, cutoff)
            windows = {f"{n}d": _empty_window() for n in WINDOWS}
            for sample in entry_rows:
                d = _valid_date(sample["signal_date"])
                days = market_days.get(sample["market"])
                if d is None:
                    invalid_signal_dates += 1
                if sample["market"] not in market_days:
                    invalid_market_names += 1
                for n in WINDOWS:
                    cell = windows[f"{n}d"]
                    cell["entry_candidate_rows"] += 1
                    if d is None or days is None or not days or d > cutoff or d not in days:
                        cell["market_evidence_unknown"] += 1
                    else:
                        sessions = sum(1 for day in days if d < day <= cutoff)
                        cell[
                            "market_sessions_reached" if sessions >= n
                            else "awaiting_market_sessions"
                        ] += 1

            # Only existing persisted evaluator rows; do not recalculate
            # observations, combine different runs or claim independent samples.
            stored = {
                "evaluation_run_rows": None,
                "evaluation_unit_rows": None,
                "distinct_evaluated_samples": None,
                "windows_with_nonnull_stored_return_rows": {
                    f"{n}d": None for n in WINDOWS
                },
            }
            if {"prospective_evaluation_run", "prospective_evaluation_unit"} <= st:
                cols = _columns(sim, "prospective_evaluation_unit")
                if {"capture_run_id","sample_index","return_5d","return_10d","return_20d"} <= cols:
                    stored["evaluation_run_rows"] = int(sim.execute(
                        "SELECT COUNT(*) FROM prospective_evaluation_run"
                    ).fetchone()[0])
                    stored["evaluation_unit_rows"] = int(sim.execute(
                        "SELECT COUNT(*) FROM prospective_evaluation_unit"
                    ).fetchone()[0])
                    stored["distinct_evaluated_samples"] = int(sim.execute(
                        "SELECT COUNT(*) FROM (SELECT DISTINCT capture_run_id,sample_index "
                        "FROM prospective_evaluation_unit)"
                    ).fetchone()[0])
                    for n in WINDOWS:
                        stored["windows_with_nonnull_stored_return_rows"][f"{n}d"] = int(
                            sim.execute(
                                f"SELECT COUNT(*) FROM prospective_evaluation_unit "
                                f"WHERE return_{n}d IS NOT NULL"
                            ).fetchone()[0]
                        )

            inconsistencies = {
                "sample_without_capture": orphan_samples,
                "duplicate_capture_scope_and_date_rows": sum(v - 1 for v in key_counts.values() if v > 1),
                "duplicate_entry_signal_keys": duplicate_signals,
                "complete_captures_without_samples": no_sample_captures,
                "invalid_canonical_capture_links": bad_canonical,
                "entry_rows_with_invalid_signal_date": invalid_signal_dates,
                "entry_rows_with_unknown_market": invalid_market_names,
            }
            state = ("HOLD_NO_CAPTURES" if capture_count == 0 else
                     "HOLD_INCONSISTENT_CAPTURE_EVIDENCE" if any((
                         orphan_samples, no_sample_captures, bad_canonical,
                         invalid_signal_dates, invalid_market_names,
                     )) else "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED")
            return {
                **base,
                "status": state,
                "as_of": cutoff.isoformat(),
                "counts_complete": True,
                "capture_count": capture_count,
                "sample_count": sample_count,
                "capture_status_counts": {s: status_counts[s] for s in sorted(status_counts)},
                "complete_capture_count": complete,
                "complete_capture_samples": len(complete_samples),
                "entry_candidate_rows": len(entry_rows),
                "reference_or_other_samples": len(complete_samples) - len(entry_rows),
                "distinct_entry_signal_keys": len(unique_signal),
                "missing_capture_source_field_counts": dict(sorted(missing.items())),
                "evidence_anomaly_counts": inconsistencies,
                "market_session_window_eligibility": windows,
                "stored_evaluation_inventory": stored,
                "market_sessions_are_not_verified_calendar_or_individual_stock_prices": True,
                "stored_returns_are_not_independent_or_executable_performance": True,
                "next_gate": "P0_05_G1_CAPTURE_ONLY_AFTER_EXPLICIT_APPROVAL",
            }
    except (OSError, sqlite3.Error, ValueError):
        return {**base, "status": "HOLD_DB_READ_ERROR"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    report = inspect(args.simulation_db, args.market_db, as_of=args.as_of)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "READ_ONLY_PROSPECTIVE_INVENTORY_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
