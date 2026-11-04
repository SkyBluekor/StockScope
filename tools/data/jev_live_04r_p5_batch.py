"""Read-only P5 routing for all ENTRY candidates of one stored capture.

  python -m tools.data.jev_live_04r_p5_batch --capture-id UUID
No Scanner, KRX, TypeSafe, migrations, DB writes, or hidden auto-selection.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.live_04r_p5_batch import VERSION, inspect_frozen_entry_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--simulation-db", type=Path, default=Path(
        os.environ.get("STOCKSCOPE_SIM_DB") or
        PROJECT_ROOT / "backend/runtime/simulation/simulation.db"
    ))
    args = parser.parse_args(argv)
    try:
        report = inspect_frozen_entry_batch(args.simulation_db, capture_id=args.capture_id)
    except (ValueError, DecisionReviewContractError, OSError) as exc:
        code = getattr(exc, "code", None)
        if code is None and str(exc).startswith(("P4_", "P5_")):
            code = str(exc)
        report = {
            "version": VERSION, "read_only": True, "status": "BLOCKED",
            "reason_code": code or "P5_READONLY_DIAGNOSIS_FAILED",
            "actual_provider_calls": 0, "db_writes": 0,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
