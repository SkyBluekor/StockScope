"""S31-S: read *actual-provider* synthetic S6 receipts without any model call.

This is NOT a real-market Scanner review, nor a signed provider attestation.
Rows are local research journal claims; forged origin strings cannot be
cryptographically proven. Never show MOCK_TEST as model evidence.
No initialization, schema migration, journal modifications or network use.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT
from app.jev.decision_reviewer_micro_canary import CASES, synthetic_projection
from app.jev.synthetic_incremental_benchmark_s31t import compare_synthetic_cases

DEFAULT_JOURNAL = PROJECT_ROOT / "data" / "jev_research" / "s6_micro_canary.sqlite3"
VERSION = "JEV_ACT2_S31S_SYNTHETIC_ACTUAL_RECEIPT_VIEW_V1"
_CHOICES = frozenset({"PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"})
_LABELS = {c["id"]: c["gold"] for c in CASES}
_TITLES = {
    "s5-consistent": "정상 전략",
    "s5-condition-contradiction": "전략 조건 충돌",
    "s5-risk-contradiction": "위험 판단 충돌",
    "s5-insufficient-evidence": "근거 부족",
    "s5-unresolved-ambiguity": "해결되지 않는 모순",
}
_COLUMNS = frozenset({
    "review_id", "protocol_hash", "case_id", "input_hash", "request_hash",
    "expected_gold", "provider_id", "model_id", "state", "decision",
    "typed_response_json", "reason_code", "cost_status", "computed_cost_usd",
    "execution_origin", "completed_at",
})


def _base(status: str) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status, "scope": "SYNTHETIC_ONLY",
        "paired_baseline": compare_synthetic_cases(
            [], total_actual_attempts=0, malformed_rows=0, read_limit=50,
        ),
        "actual_provider_attempts_recorded": 0,
        "actual_valid_receipts": 0, "correct_against_synthetic_gold": 0,
        "incorrect_against_synthetic_gold": 0,
        "unverified_receipt_rows": 0, "mock_rows_excluded": 0,
        "results": [], "model_calls_on_request": 0,
        "external_requests_on_request": 0, "db_writes_on_request": 0,
        "real_stock_models_reviewed": 0, "scanner_uplift_proven": False,
        "provider_provenance": "LOCAL_JOURNAL_ORIGIN_CLAIM_NOT_CRYPTOGRAPHICALLY_ATTESTED",
        "cost_basis": "PUBLIC_STANDARD_ESTIMATE_NOT_ACCOUNT_BILLING",
    }


def _safe_row(row: sqlite3.Row) -> dict[str, Any] | None:
    try:
        case = row["case_id"]
        if case not in _LABELS or row["provider_id"] != "TYPESAFE_SYSTEM_ONE":
            return None
        if row["input_hash"] != synthetic_projection(case)["input_hash"]:
            return None
        state = row["state"]
        if state not in {"VALID", "ERROR", "INTERRUPTED", "PENDING"}:
            return None
        result: dict[str, Any] = {
            "case_id": case, "case_title": _TITLES[case],
            "state": state, "expected": _LABELS[case],
            "observed": None, "model": None,
            "matches_expected": None, "cost_estimate_usd": None,
            "completed_at": row["completed_at"],
            "receipt_status": "ATTEMPT_RECORDED_NOT_VALIDATED",
        }
        if state != "VALID":
            return result
        typed = json.loads(row["typed_response_json"] or "null")
        decision = row["decision"]
        if not isinstance(typed, dict) or decision not in _CHOICES:
            return None
        if typed.get("decision") != decision:
            return None
        model = typed.get("model")
        requested = typed.get("requested_model")
        if not isinstance(model, str) or not model.strip() or not isinstance(requested, str) or not requested.strip():
            return None
        if row["model_id"] != requested:
            return None
        if row["expected_gold"] != _LABELS[case]:
            return None
        if row["cost_status"] not in {
            "ESTIMATED_FROM_PUBLIC_STANDARD_RATE",
            "ESTIMATED_FROM_VERIFIED_ACCOUNT_RATE",
        }:
            return None
        result.update({
            "observed": decision,
            "model": model,
            "matches_expected": decision == _LABELS[case],
            "cost_estimate_usd": str(row["computed_cost_usd"])
                if row["computed_cost_usd"] is not None else None,
            "receipt_status": "JOURNAL_CONSISTENCY_CHECK_PASSED",
        })
        return result
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, IndexError):
        return None


def inspect_synthetic_actual_provider_receipts(
    journal: Path = DEFAULT_JOURNAL,
) -> dict[str, Any]:
    """Read-only SQL on a fixed research journal path (tests may inject path)."""
    path = Path(journal)
    if not path.is_file():
        return _base("NO_JOURNAL")
    try:
        # mode=ro avoids accidentally creating SQLite files or journaling changes.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                             timeout=0.5) as conn:
            conn.row_factory = sqlite3.Row
            found = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='jev_s5_synthetic'"
            ).fetchone()
            if found is None:
                return _base("JOURNAL_SCHEMA_UNAVAILABLE")
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(jev_s5_synthetic)")
            }
            if not _COLUMNS <= columns:
                return _base("JOURNAL_SCHEMA_UNAVAILABLE")
            mock_count = conn.execute(
                "SELECT COUNT(*) FROM jev_s5_synthetic "
                "WHERE execution_origin='MOCK_TEST'"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT case_id,provider_id,input_hash,expected_gold,model_id,"
                "state,decision,typed_response_json,cost_status,"
                "computed_cost_usd,completed_at FROM jev_s5_synthetic "
                "WHERE execution_origin='ACTUAL_PROVIDER' "
                "ORDER BY created_at,review_id LIMIT 50"
            ).fetchall()
            # Count total actual rows separately so our UI never silently
            # implies the displayed 50 comprise every experiment ever.
            actual_count = conn.execute(
                "SELECT COUNT(*) FROM jev_s5_synthetic "
                "WHERE execution_origin='ACTUAL_PROVIDER'"
            ).fetchone()[0]
    except (sqlite3.DatabaseError, OSError, ValueError):
        return _base("JOURNAL_READ_FAILED")
    result = _base("ACTUAL_RECEIPTS_FOUND" if actual_count else "NO_ACTUAL_RECEIPTS")
    accepted = [_safe_row(row) for row in rows]
    results = [row for row in accepted if row is not None]
    valid = [r for r in results if r["receipt_status"] == "JOURNAL_CONSISTENCY_CHECK_PASSED"]
    result.update({
        "paired_baseline": compare_synthetic_cases(
            results, total_actual_attempts=actual_count,
            malformed_rows=actual_count - len(results), read_limit=50,
        ),
        "actual_provider_attempts_recorded": actual_count,
        "mock_rows_excluded": mock_count,
        "actual_valid_receipts": len(valid),
        "correct_against_synthetic_gold": sum(r["matches_expected"] is True for r in valid),
        "incorrect_against_synthetic_gold": sum(r["matches_expected"] is False for r in valid),
        "unverified_receipt_rows": actual_count - len(results),
        "results": results,
    })
    return result
