"""P0-05/G1 read-only, single-capture immutable snapshot and S7 diagnosis.

No re-capture, no API, no SQLite migrations/writes, no recommendations,
no Q7 promotion. Reports storage/hash evidence separately from S7 quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.jev.scanner_integrity_s7_1 import assess_frozen_candidate, EXPLAIN
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.prospective.models import digest_json

VERSION = "STOCKSCOPE_P0_05_G1_CAPTURE_S7_PROOF_V1"
KST = timezone(timedelta(hours=9), name="KST")
MAX_SAMPLES = 500
CAPTURE_FIELDS = frozenset({
    "id", "status", "canonical_capture_id", "source_job_id",
    "source_execution_key", "source_snapshot_hash", "result_hash",
    "scanner_version", "market_scope", "actual_data_date",
    "request_json", "returned_candidate_count", "created_at", "completed_at",
    "scanner_baseline", "input_fingerprint",
    "horizon_intent", "horizon_policy_version",
})
SAMPLE_FIELDS = frozenset({
    "capture_run_id", "sample_index", "market", "ticker", "name",
    "strategy", "action", "rank", "decision_status", "candidate_state",
    "signal_date", "snapshot_json", "snapshot_hash",
})
SHA256 = re.compile(r"^[0-9a-f]{64}$")
S7_CODES = frozenset(EXPLAIN)


def _base(status: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status,
        "operational_db_read_only": True, "db_writes": 0,
        "external_requests": 0, "scanner_job_started": False,
        "new_capture_created": False, "scheduler_registered": False,
        "real_orders": 0, "q7_approval_eligible": False,
        "independent_source_release_time_verified": False,
        "independent_market_provider_verified": False,
        "investment_performance_verified": False,
        **details,
    }


def _utc_kst(raw: Any) -> tuple[str | None, date | None]:
    if not isinstance(raw, str):
        return None, None
    try:
        stamp = datetime.fromisoformat(raw)
        if stamp.utcoffset() is None:
            return None, None
        converted = stamp.astimezone(KST)
        return converted.isoformat(), converted.date()
    except (ValueError, OverflowError):
        return None, None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _inspect_rows(capture: dict[str, Any], rows: list[sqlite3.Row]) -> dict[str, Any]:
    expected = capture["returned_candidate_count"]
    metadata_ok = (
        capture["status"] == "COMPLETE"
        and capture["canonical_capture_id"] is None
        and type(expected) is int and 0 <= expected <= MAX_SAMPLES
        and len(rows) == expected
        and all(type(capture.get(k)) is str and bool(capture[k]) for k in (
            "id", "source_job_id", "scanner_version",
        ))
        and all(type(capture.get(k)) is str and SHA256.fullmatch(capture[k]) for k in (
            "source_execution_key", "source_snapshot_hash", "result_hash",
        ))
        and capture.get("market_scope") in ("ALL", "KOSPI", "KOSDAQ")
        and isinstance(capture.get("actual_data_date"), str)
    )
    try:
        signal = date.fromisoformat(capture["actual_data_date"])
        request = json.loads(capture["request_json"])
        metadata_ok = metadata_ok and isinstance(request, dict)
        if metadata_ok:
            metadata_ok = request.get("market_scope") == capture["market_scope"]
    except (KeyError, TypeError, ValueError):
        signal = None
        metadata_ok = False
        request = None
    completed_kst, completed_day = _utc_kst(capture.get("completed_at"))
    created_kst, created_day = _utc_kst(capture.get("created_at"))
    metadata_ok = metadata_ok and completed_day is not None and created_day is not None
    if completed_kst and created_kst:
        metadata_ok = metadata_ok and created_kst <= completed_kst
    if signal and completed_day:
        metadata_ok = metadata_ok and completed_day >= signal

    snapshot_pass = 0
    snapshot_failed = 0
    structural_failed = 0
    categories: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    entry_count = 0
    reference_count = 0
    expected_indices = set(range(len(rows)))
    actual_indices: set[int] = set()
    for row in rows:
        idx = row["sample_index"]
        if type(idx) is int:
            actual_indices.add(idx)
        consistent = (
            type(idx) is int
            and idx in expected_indices
            and row["capture_run_id"] == capture["id"]
            and row["signal_date"] == capture.get("actual_data_date")
            and row["market"] in ("KOSPI", "KOSDAQ")
            and (capture.get("market_scope") == "ALL"
                 or row["market"] == capture.get("market_scope"))
            and isinstance(row["ticker"], str) and bool(row["ticker"])
        )
        if not consistent:
            structural_failed += 1
        try:
            snapshot = json.loads(row["snapshot_json"])
            valid = (
                isinstance(snapshot, dict)
                and type(row["snapshot_hash"]) is str
                and SHA256.fullmatch(row["snapshot_hash"]) is not None
                and digest_json(snapshot) == row["snapshot_hash"]
            )
        except (ValueError, TypeError, UnicodeError):
            valid = False
            snapshot = None
        if not valid:
            snapshot_failed += 1
            continue
        snapshot_pass += 1
        if not consistent:
            continue
        # S7 judges original immutable evidence, not just SHA256.
        sample = {k: row[k] for k in SAMPLE_FIELDS if k != "snapshot_json"}
        sample["snapshot"] = snapshot
        if sample["action"] == "ENTRY_CANDIDATE":
            entry_count += 1
        else:
            reference_count += 1
        try:
            judgement = assess_frozen_candidate(capture, sample)
            category = judgement.get("category")
            if category not in {"REFERENCE_ONLY", "LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID"}:
                raise DecisionReviewContractError("S7_INVALID_CATEGORY")
            categories[category] += 1
            for code in judgement.get("codes", []):
                # Never emit raw error contents or candidate/private data.
                codes[code if code in S7_CODES else "S7_UNCLASSIFIED"] += 1
        except (DecisionReviewContractError, KeyError, TypeError, ValueError):
            categories["INVALID"] += 1
            codes["S7_DIAGNOSTIC_UNAVAILABLE"] += 1

    if actual_indices != expected_indices:
        metadata_ok = False
    if not metadata_ok or structural_failed or snapshot_failed:
        status = "HOLD_CAPTURE_STORAGE_INTEGRITY_FAILED"
    else:
        status = "CAPTURE_STORAGE_VERIFIED_S7_REVIEWED"
    return _base(
        status,
        capture_id=capture["id"],
        capture_status=capture["status"],
        scope=capture.get("market_scope"),
        signal_data_date=capture.get("actual_data_date"),
        capture_created_at_kst=created_kst,
        capture_completed_at_kst=completed_kst,
        was_created_after_signal_day=(
            created_day > signal if created_day is not None and signal is not None else None
        ),
        premarket_recommendation_eligible=False,
        premarket_eligibility_not_proven=True,
        expected_samples=expected,
        actual_samples=len(rows),
        snapshot_hash_verified=snapshot_pass,
        snapshot_hash_failed=snapshot_failed,
        row_identity_failed=structural_failed,
        metadata_verified=bool(metadata_ok),
        source_execution_key_present=bool(capture.get("source_execution_key")),
        source_snapshot_hash_present=bool(capture.get("source_snapshot_hash")),
        result_hash_present=bool(capture.get("result_hash")),
        # The root hashes are not recomputable from samples alone because
        # the original Scanner summary and source result are not stored here.
        root_source_hashes_independently_recomputed=False,
        s7_entry_rows_inspected=entry_count,
        s7_reference_rows_inspected=reference_count,
        s7_category_counts=dict(sorted(categories.items())),
        s7_reason_code_counts=dict(sorted(codes.items())),
        local_validated_entry_count=categories["LOCAL_VALIDATED"],
        s7_invalid_count=categories["INVALID"],
        s7_invalid_does_not_imply_snapshot_corruption=True,
    )


def inspect(db: Path, *, capture_id: str) -> dict[str, Any]:
    if not isinstance(capture_id, str) or not capture_id.strip() or len(capture_id) > 128:
        return _base("HOLD_CAPTURE_ID_INVALID")
    path = Path(db).expanduser()
    if not path.is_file():
        return _base("HOLD_OPERATIONAL_SIMULATION_DB_MISSING")
    try:
        with closing(sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10,
        )) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")  # Consistent WAL snapshot for metadata + samples.
            tables = {
                str(r["name"]) for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"prospective_capture_run", "prospective_recommendation_sample"} <= tables:
                return _base("HOLD_PROSPECTIVE_SCHEMA_MISSING")
            if not CAPTURE_FIELDS <= _columns(conn, "prospective_capture_run"):
                return _base("HOLD_CAPTURE_SCHEMA_INCOMPLETE")
            if not SAMPLE_FIELDS <= _columns(conn, "prospective_recommendation_sample"):
                return _base("HOLD_SAMPLE_SCHEMA_INCOMPLETE")
            row = conn.execute("SELECT * FROM prospective_capture_run WHERE id=?", (capture_id,)).fetchone()
            if row is None:
                return _base("HOLD_CAPTURE_NOT_FOUND")
            if row["status"] != "COMPLETE":
                # DUPLICATE is a pointer to its canonical COMPLETE, not another
                # independently stored set of 15 sample rows.
                return _base("HOLD_CAPTURE_NOT_COMPLETE",
                             capture_status=str(row["status"]),
                             canonical_capture_present=bool(row["canonical_capture_id"]))
            expected = row["returned_candidate_count"]
            if type(expected) is not int or not 0 <= expected <= MAX_SAMPLES:
                return _base("HOLD_CAPTURE_SAMPLE_COUNT_UNSUPPORTED")
            found = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_recommendation_sample WHERE capture_run_id=?",
                (capture_id,),
            ).fetchone()[0])
            if found > MAX_SAMPLES:
                return _base("HOLD_CAPTURE_SAMPLE_COUNT_UNSUPPORTED")
            samples = conn.execute(
                "SELECT * FROM prospective_recommendation_sample WHERE capture_run_id=? ORDER BY sample_index",
                (capture_id,),
            ).fetchall()
            return _inspect_rows(dict(row), samples)
    except (sqlite3.Error, OSError):
        return _base("HOLD_CAPTURE_DB_READ_UNAVAILABLE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation-db", type=Path, required=True)
    parser.add_argument("--capture-id", required=True)
    args = parser.parse_args(argv)
    result = inspect(args.simulation_db, capture_id=args.capture_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "CAPTURE_STORAGE_VERIFIED_S7_REVIEWED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
