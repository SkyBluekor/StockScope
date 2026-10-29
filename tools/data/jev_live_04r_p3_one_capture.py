"""Read-only P3 validation for an explicitly selected *new* Scanner capture.

Run after a real local Scanner capture, e.g.
  python -m tools.data.jev_live_04r_p3_one_capture \
      --capture-id <uuid> --captured-after 2026-10-29T15:00:00+09:00

This program NEVER executes Scanner, invokes TypeSafe or modifies SQLite.
It does not prove external data licenses, actual source publication times, or
that a synthetic/local replay was a genuine market run.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.live_04r_p3_capture_probe import (
    discover_new_capture_ids,
    inspect_one_capture,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-id", help="Explicit new COMPLETE capture UUID")
    parser.add_argument("--find-new", action="store_true",
                        help="List new COMPLETE capture IDs since --captured-after (read only)")
    parser.add_argument("--captured-after", required=True,
                        help="Timezone-aware time saved BEFORE launching the new Scanner run")
    parser.add_argument("--sample-index", type=int, default=None,
                        help="0-based. Omit to inspect the first ENTRY_CANDIDATE only.")
    parser.add_argument("--simulation-db", type=Path,
                        default=Path(os.environ.get("STOCKSCOPE_SIM_DB")
                                     or PROJECT_ROOT / "backend/runtime/simulation/simulation.db"),
                        help="Existing isolated or operational simulation DB, mode=ro only")
    args = parser.parse_args(argv)
    try:
        if args.find_new:
            if args.capture_id or args.sample_index is not None:
                raise ValueError("P3_DISCOVER_AND_EXPLICIT_ID_CONFLICT")
            found = discover_new_capture_ids(
                args.simulation_db, captured_after=args.captured_after,
            )
            result = {
                "version": "JEV_LIVE_04R_P3_CAPTURE_DISCOVERY_V1",
                "read_only": True,
                "status": "FOUND" if found else "NONE_FOUND",
                "new_complete_entry_captures": found,
                "actual_provider_calls": 0,
                "db_writes": 0,
            }
        else:
            if not args.capture_id:
                raise ValueError("P3_CAPTURE_ID_REQUIRED")
            result = inspect_one_capture(
                args.simulation_db,
                capture_id=args.capture_id,
                captured_after=args.captured_after,
                sample_index=args.sample_index,
            )
    except (ValueError, DecisionReviewContractError, OSError) as exc:
        # Codes only: never dump SQL, file paths, tokens, candidate raw data.
        code = getattr(exc, "code", None)
        if code is None and str(exc).startswith("P3_"):
            code = str(exc)
        print(json.dumps({
            "version": "JEV_LIVE_04R_P3_ONE_CAPTURE_V1",
            "read_only": True,
            "status": "BLOCKED",
            "reason_code": code or "P3_READONLY_INSPECTION_FAILED",
            "actual_provider_calls": 0,
            "db_writes": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
