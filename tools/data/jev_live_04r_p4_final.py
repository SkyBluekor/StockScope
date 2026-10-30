"""Inspect a previously saved Scanner SHORT capture without rerunning it.

Examples:
  python -m tools.data.jev_live_04r_p4_final --find-short
  python -m tools.data.jev_live_04r_p4_final --capture-id UUID
  python -m tools.data.jev_live_04r_p4_final --policy-status

Works on the configured simulation DB with SQLite mode=ro/query_only.
Never calls KRX, TypeSafe, or makes a DB write. Listing does not auto-select.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.live_04r_p4_final import (
    VERSION, find_stored_horizon_captures, inspect_stored_horizon_capture,
)
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry, SelectionPolicyError,
)


def _policy_status() -> dict[str, object]:
    override = (os.getenv("STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR") or "").strip()
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=Path(override) if override else None,
    )
    resolution = registry.resolve_active_selection_policy()
    pin = registry.pin_active_selection_policy()
    return {
        "version": VERSION,
        "read_only": True,
        "raw_resolution": resolution.policy_source,
        "effective_pin_source": pin.policy_source,
        "fallback_reason": pin.fallback_reason,
        "reference_valid": resolution.active_reference_valid,
        "snapshot_hash_valid": resolution.policy_hash_valid,
        "policy_id": pin.policy_id,
        "policy_hash": pin.policy_hash,
        "original_strategy_identity_count": sum(
            1 for version, _, definition in pin.operating_strategies
            if version is not None and definition is not None
        ),
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--find-short", action="store_true",
                       help="Read metadata for recent frozen SHORT captures, no auto-selection")
    group.add_argument("--capture-id", help="Explicit COMPLETE or DUPLICATE capture ID")
    group.add_argument("--policy-status", action="store_true",
                       help="Read active/rollback/legacy policy resolution without activation")
    parser.add_argument("--sample-index", type=int, default=None)
    parser.add_argument("--simulation-db", type=Path, default=Path(
        os.environ.get("STOCKSCOPE_SIM_DB")
        or PROJECT_ROOT / "backend/runtime/simulation/simulation.db"
    ))
    args = parser.parse_args(argv)
    try:
        if (args.find_short or args.policy_status) and args.sample_index is not None:
            raise ValueError("P4_SAMPLE_INDEX_REQUIRES_CAPTURE_ID")
        if args.find_short:
            report = find_stored_horizon_captures(args.simulation_db)
        elif args.policy_status:
            report = _policy_status()
        else:
            report = inspect_stored_horizon_capture(
                args.simulation_db, capture_id=args.capture_id,
                sample_index=args.sample_index,
            )
    except (ValueError, DecisionReviewContractError, SelectionPolicyError, OSError) as exc:
        code = getattr(exc, "code", None)
        if code is None and str(exc).startswith("P4_"):
            code = str(exc)
        print(json.dumps({
            "version": VERSION,
            "read_only": True,
            "status": "BLOCKED",
            "reason_code": code or "P4_READONLY_INSPECTION_FAILED",
            "actual_provider_calls": 0,
            "db_writes": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
