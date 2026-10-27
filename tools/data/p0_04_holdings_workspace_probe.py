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

VERSION = "STOCKSCOPE_P0_04_STORED_HOLDING_WORKSPACE_PROBE_V1"
SAFE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
SAFE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _token(raw: Any) -> str:
    value = str(raw or "")
    return value if SAFE_TOKEN.fullmatch(value) else "UNCLASSIFIED"


def _date(raw: Any) -> str | None:
    value = str(raw or "")
    return value if SAFE_DATE.fullmatch(value) else None


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
        summaries.append({
            "active_plan_present": isinstance(active, dict),
            # Management state derives from *stored EOD*, not realtime quotes.
            "stored_eod_management_state": _token(mgmt.get("management_state")),
            "latest_proposal_state": _token(proposal.get("state")),
            "proposal_structurally_applicable": proposal.get("can_apply") is True,
            "decision_present": bool(decision),
            "decision_effective_status": _token(decision.get("effective_status") or decision.get("status")),
            "decision_stale": decision.get("stale") is True,
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
        "groups": results,
        "notes": [
            "Stored EOD and management states are historical evidence, never live trading instructions.",
            "A proposal's structural can_apply flag does not grant permission to apply without current-use approval, a fresh decision and explicit user review.",
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
