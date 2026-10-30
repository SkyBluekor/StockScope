"""P0-04 read-only real Holdings workspace diagnosis (no private position output).

Run AFTER p0_04_holdings_readonly_preflight.py. Uses existing app read services,
never starts FastAPI, initializes the catalog, evaluates decisions or applies plans.
The underlying Holdings and market connections are opened SQLite mode=ro.
All returned private IDs, names, quantities, prices and financial calculations
are intentionally discarded before printing.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "backend"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from app.holdings.workspace_query import HoldingsWorkspaceQueryService
from tools.data.p0_04_holdings_readonly_preflight import (
    _connect_readonly,
    inspect_holdings_environment,
)

VERSION = "STOCKSCOPE_P0_04_STORED_HOLDING_WORKSPACE_PROBE_V2"
# Enumerations fixed by the existing Decision/Recovery domain services. A
# novel or user-authored string is never echoed as a diagnostic reason.
STALE_REASON_CODES = frozenset({
    "POSITION_STATUS_CHANGED", "POSITION_QUANTITY_CHANGED",
    "POSITION_AVERAGE_PRICE_CHANGED", "ANALYSIS_REVISION_CHANGED",
    "ACTIVE_PLAN_CHANGED", "ACTIVE_PLAN_VERSION_CHANGED",
    "VALUATION_DATE_CHANGED", "VALUATION_PRICE_CHANGED",
    "PROPOSAL_READINESS_CHANGED", "HORIZON_APPLICABILITY_CHANGED",
})
RECOVERY_REVIEW_STATUSES = frozenset({"OPEN", "CLOSED"})
RECOVERY_THESIS_STATES = frozenset({"INTACT", "WEAKENED", "BROKEN", "UNKNOWN"})
RECOVERY_REVIEW_ACTIONS = frozenset({
    "UNDECIDED", "HOLD", "REDUCE", "EXIT", "ADD_REVIEW",
})
SAFE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
SAFE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _token(raw: Any) -> str:
    value = str(raw or "")
    return value if SAFE_TOKEN.fullmatch(value) else "UNCLASSIFIED"


def _date(raw: Any) -> str | None:
    value = str(raw or "")
    return value if SAFE_DATE.fullmatch(value) else None


def _iso_timestamp_date(raw: Any) -> str | None:
    value = str(raw or "")
    return _date(value[:10]) if len(value) >= 10 else None


def _enum(raw: Any, values: frozenset[str]) -> str:
    value = str(raw or "")
    return value if value in values else "UNCLASSIFIED"


def _stale_reason_codes(decision: dict[str, Any]) -> list[str]:
    if decision.get("stale") is not True:
        return []
    raw = decision.get("stale_reasons")
    if not isinstance(raw, list) or not raw:
        return ["STALE_REASONS_UNAVAILABLE"]
    codes = {
        value if isinstance(value, str) and value in STALE_REASON_CODES
        else "UNRECOGNIZED_STALE_REASON"
        for value in raw
    }
    return sorted(codes)


def _recovery_summary(row: dict[str, Any]) -> dict[str, Any]:
    recovery = row.get("recovery")
    if not isinstance(recovery, dict):
        return {
            "open_review_present": False,
            "open_review_status": "UNAVAILABLE",
            "opened_date": None,
            "open_review_assessment_count": None,
            "latest_assessment_present": False,
            "latest_assessment_thesis_state": None,
            "latest_assessment_review_action": None,
            "latest_assessment_date": None,
            "assessment_source_plan_matches_active": None,
            "assessment_source_analysis_matches_latest": None,
        }
    review = recovery.get("open_review")
    if not isinstance(review, dict):
        return {
            "open_review_present": False,
            "open_review_status": "NONE",
            "opened_date": None,
            "open_review_assessment_count": 0,
            "latest_assessment_present": False,
            "latest_assessment_thesis_state": None,
            "latest_assessment_review_action": None,
            "latest_assessment_date": None,
            "assessment_source_plan_matches_active": None,
            "assessment_source_analysis_matches_latest": None,
        }
    review_id = review.get("review_id")
    history = recovery.get("review_history")
    open_entries = (
        [item for item in history if isinstance(item, dict)
         and isinstance(item.get("review"), dict)
         and item["review"].get("review_id") == review_id]
        if isinstance(history, list) else []
    )
    assessments = open_entries[0].get("assessments") if len(open_entries) == 1 else None
    count = len(assessments) if isinstance(assessments, list) else None
    latest = recovery.get("latest_open_assessment")
    latest = latest if isinstance(latest, dict) else None
    management = row.get("management") or {}
    management = management if isinstance(management, dict) else {}
    active_plan = management.get("active_plan")
    active_id = active_plan.get("plan_id") if isinstance(active_plan, dict) else None
    analysis_id = (
        (recovery.get("current") or {}).get("analysis") or {}
    )
    analysis_id = analysis_id.get("revision_id") if isinstance(analysis_id, dict) else None
    return {
        "open_review_present": True,
        "open_review_status": _enum(review.get("status"), RECOVERY_REVIEW_STATUSES),
        "opened_date": _iso_timestamp_date(review.get("opened_at")),
        "open_review_assessment_count": count,
        "latest_assessment_present": latest is not None,
        "latest_assessment_thesis_state": (
            _enum(latest.get("thesis_state"), RECOVERY_THESIS_STATES) if latest else None
        ),
        "latest_assessment_review_action": (
            _enum(latest.get("review_action"), RECOVERY_REVIEW_ACTIONS) if latest else None
        ),
        "latest_assessment_date": (
            _iso_timestamp_date(latest.get("created_at")) if latest else None
        ),
        # A missing source ID is unknown, not a verified match.
        "assessment_source_plan_matches_active": (
            latest.get("source_active_plan_id") == active_id
            if latest and latest.get("source_active_plan_id") and active_id else None
        ),
        "assessment_source_analysis_matches_latest": (
            latest.get("source_analysis_revision_id") == analysis_id
            if latest and latest.get("source_analysis_revision_id") and analysis_id else None
        ),
    }


def summarize_workspace(payload: dict[str, Any]) -> dict[str, Any]:
    """Explicit allowlist: never emit raw API payload or its private metadata."""
    state = payload.get("current_state") or {}
    sources = payload.get("source_status") or {}
    contract = (payload.get("data_contract") or {}).get("resources") or {}
    analysis = contract.get("analysis_result") or {}
    rows = payload.get("positions") or []
    if not isinstance(rows, list):
        raise ValueError("invalid positions")

    summaries: list[dict[str, Any]] = []
    for row in rows:
        mgmt = row.get("management") if isinstance(row, dict) else None
        mgmt = mgmt if isinstance(mgmt, dict) else {}
        decision = row.get("decision") if isinstance(row, dict) else None
        decision = decision if isinstance(decision, dict) else {}
        proposal = mgmt.get("proposal")
        proposal = proposal if isinstance(proposal, dict) else {}
        active = mgmt.get("active_plan")
        conditions = row.get("review_conditions") or []
        reasons = _stale_reason_codes(decision)
        recovery = _recovery_summary(row) if isinstance(row, dict) else _recovery_summary({})
        summaries.append({
            "active_plan_present": isinstance(active, dict),
            # Management state derives from *stored EOD*, not realtime quotes.
            "stored_eod_management_state": _token(mgmt.get("management_state")),
            "latest_proposal_state": _token(proposal.get("state")),
            "proposal_structurally_applicable": proposal.get("can_apply") is True,
            "decision_present": bool(decision),
            "decision_effective_status": _token(decision.get("effective_status") or decision.get("status")),
            "decision_stale": decision.get("stale") is True,
            "decision_stale_reasons": reasons,
            "recovery": recovery,
            "review_conditions": sorted({_token(x) for x in conditions}),
        })

    return {
        "analysis_contract_status": _token(analysis.get("status")),
        "analysis_reason_code": _token(analysis.get("reason_code")) if analysis.get("reason_code") else None,
        "analysis_basis_date": _date(analysis.get("basis_date")),
        "analysis_current_use_allowed": state.get("analysis_current_use_allowed") is True,
        "source_status": {
            name: _token((sources.get(name) or {}).get("status"))
            for name in ("eod", "analysis", "ledger", "decision", "management", "recovery", "watch")
        },
        "open_positions_projected": len(summaries),
        "active_plan_count": sum(int(r["active_plan_present"]) for r in summaries),
        "stored_eod_management_states": dict(sorted(Counter(
            r["stored_eod_management_state"] for r in summaries
        ).items())),
        "decision_states": dict(sorted(Counter(
            r["decision_effective_status"] for r in summaries
        ).items())),
        "proposal_states": dict(sorted(Counter(
            r["latest_proposal_state"] for r in summaries
        ).items())),
        "positions_with_stale_decision": sum(int(r["decision_stale"]) for r in summaries),
        "stale_reason_counts": dict(sorted(Counter(
            code for r in summaries for code in r["decision_stale_reasons"]
        ).items())),
        "open_recovery_reviews": sum(int(r["recovery"]["open_review_present"]) for r in summaries),
        "open_recovery_reviews_without_assessment": sum(int(
            r["recovery"]["open_review_present"]
            and r["recovery"]["latest_assessment_present"] is False
        ) for r in summaries),
        "review_condition_counts": dict(sorted(Counter(
            code for r in summaries for code in r["review_conditions"]
        ).items())),
        "positions": summaries,
    }


def inspect_workspace(holdings_db: Path, market_db: Path) -> dict[str, Any]:
    base = {
        "version": VERSION,
        "status": "BLOCKED_WORKSPACE_PREFLIGHT",
        "operational_db_read_only": True,
        "db_write_calls": 0,
        "external_requests": 0,
        "plan_applied": False,
        "ready_for_plan_write": False,
        "user_confirmation_still_required": True,
        "realtime_price_verified": False,
        "latest_official_eod_verified": False,
    }
    first = inspect_holdings_environment(holdings_db, market_db)
    if first["status"] != "READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED":
        return {
            **base,
            "status": "BLOCKED_WORKSPACE_PREFLIGHT",
            "preflight_status": first["status"],
        }

    try:
        with closing(_connect_readonly(holdings_db)) as conn:
            ids = [
                str(row[0]) for row in conn.execute(
                    "SELECT DISTINCT monitored_stock_id FROM holding_position "
                    "WHERE status='OPEN' ORDER BY monitored_stock_id"
                )
            ]
        service = HoldingsWorkspaceQueryService(
            holdings_db, market_store_db=market_db,
        )
        results = [summarize_workspace(service.build(stock_id)) for stock_id in ids]
    except Exception:
        # Do not print arbitrary exception strings: they can contain stock IDs,
        # source paths, account names or price information.
        return {**base, "status": "BLOCKED_WORKSPACE_READ_FAILED"}

    rows = sum(item["open_positions_projected"] for item in results)
    if rows != first["counts"]["open_positions"]:
        return {**base, "status": "BLOCKED_CONCURRENT_POSITION_CHANGE"}
    if sum(item["active_plan_count"] for item in results) != first["counts"]["active_plans"]:
        return {**base, "status": "BLOCKED_CONCURRENT_PLAN_CHANGE"}

    return {
        **base,
        "status": "READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED",
        "held_stock_groups": len(results),
        "open_positions_projected": rows,
        "analysis_contract_statuses": dict(sorted(Counter(
            r["analysis_contract_status"] for r in results
        ).items())),
        "analysis_current_use_allowed_groups": sum(int(r["analysis_current_use_allowed"]) for r in results),
        "active_plan_count": sum(r["active_plan_count"] for r in results),
        "stale_reason_counts": dict(sorted(Counter(
            code for group in results for row in group["positions"]
            for code in row["decision_stale_reasons"]
        ).items())),
        "open_recovery_reviews": sum(g["open_recovery_reviews"] for g in results),
        "groups": results,
        "notes": [
            "Stored EOD and management states are historical evidence, never live trading instructions.",
            "A proposal's structural can_apply flag does not grant permission to apply without current-use approval, a fresh decision and explicit user review.",
            "STALE reasons and Recovery assessment fields are read-only historical codes; no review is automatically resolved or closed.",
            "No migrations, decisions, active plans or holdings transactions were written.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdings-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_workspace(args.holdings_db, args.market_db)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
