"""User-invoked S22 incremental 5/10/20 EOD observation revisions.

Usage (project root):
    .venv/Scripts/python -B tools/data/prospective_incremental_s22.py plan
    .venv/Scripts/python -B tools/data/prospective_incremental_s22.py apply --acknowledge-simulation-writes

No KRX network, Scanner, trading, JEV provider or scheduled jobs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.jev.prospective_incremental_s22 import (
    IncrementalObservationError, apply_batch, evaluate_batch, _result,
)
from tools.data.common import market_db_path, simulation_db_path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="S22 incremental read-only plan / explicit write of matured EOD evidence"
    )
    p.add_argument("mode", choices=("plan", "apply"))
    p.add_argument("--simulation-db", type=Path, default=None)
    p.add_argument("--market-db", type=Path, default=None)
    p.add_argument("--as-of", default=None)
    p.add_argument("--after", default=None, help="next_cursor emitted by previous page")
    p.add_argument("--limit-captures", type=int, default=20)
    p.add_argument("--acknowledge-simulation-writes", action="store_true")
    p.add_argument("--details-limit", type=int, default=12)
    return p


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if not 0 <= args.details_limit <= 50:
        raise IncrementalObservationError("DETAIL_LIMIT_INVALID")
    sim = args.simulation_db or simulation_db_path()
    market = args.market_db or market_db_path()
    kw = {
        "as_of": args.as_of, "after": args.after,
        "limit_captures": args.limit_captures,
    }
    if args.mode == "plan":
        result = evaluate_batch(sim, market, **kw)
    else:
        if not args.acknowledge_simulation_writes:
            raise IncrementalObservationError("EXPLICIT_SIMULATION_WRITE_ACK_REQUIRED")
        result = apply_batch(sim, market, **kw)
    # Cap the visible JSON without limiting the complete source denominator
    # or changing the internally executed batch.
    rows = result.pop("observed_or_cached", [])
    result["observation_items"] = len(rows)
    result["observation_examples"] = rows[:args.details_limit]
    result["observation_examples_truncated"] = len(rows) > args.details_limit
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        answer = execute(args)
    except (IncrementalObservationError, ValueError, OSError, json.JSONDecodeError) as exc:
        answer = _result(
            "BLOCKED", reason=str(exc), simulation_db_writes=0, market_db_writes=0,
        )
    print(json.dumps(answer, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if answer["status"] in (
        "PLAN_ONLY", "NO_NEW_MATURE_OBSERVATIONS", "SAVED_INCREMENTAL_OBSERVATIONS"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
