"""Read-only local Windows/CI audit of a *previously saved* Scanner capture.

Example:
  python -m tools.data.jev_p6d_real_audit --simulation-db path/to/simulation.db --capture-id UUID

Does not create a DB, ingest market/news data, load credentials or call TypeSafe.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.real_event_audit_p6d import audit_existing_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation-db", default=os.getenv("STOCKSCOPE_SIM_DB"),
                        help="Existing SQLite DB. Never created by this command.")
    parser.add_argument("--capture-id", required=True,
                        help="Exact COMPLETE or canonical-linked DUPLICATE capture ID.")
    parser.add_argument("--naver-provider-kind",
                        choices=("developer_center", "api_hub"), default=None)
    args = parser.parse_args(argv)
    if not args.simulation_db:
        parser.error("--simulation-db or STOCKSCOPE_SIM_DB is required")
    try:
        report = audit_existing_capture(
            Path(args.simulation_db),
            capture_id=args.capture_id,
            naver_provider_kind=args.naver_provider_kind,
        )
    except (DecisionReviewContractError, FileNotFoundError, ValueError) as exc:
        # Do not claim that an absent local DB is an empty EventEvidence store.
        code = getattr(exc, "code", None) or str(exc)
        print(json.dumps({"status": "AUDIT_UNAVAILABLE", "code": code,
                          "read_only": True, "real_market_model_calls": 0},
                         ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
