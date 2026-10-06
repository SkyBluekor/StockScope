from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.jev import (
    JevEvaluationCatalogError,
    JevReviewerEvaluationError,
    JevReviewerEvaluationService,
)
from tools.data.common import market_db_path, simulation_db_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "저장된 JEV Shadow review와 local Market Store만 사용해 "
            "JEV Reviewer Evaluation V1 snapshot을 생성합니다. "
            "외부 provider 호출이나 JEV_API_KEY 접근은 수행하지 않습니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    parser.add_argument("--market-db", type=Path)
    parser.add_argument("--client-request-id")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="생성한 또는 지정한 evaluation run을 local-only로 계산합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    service = JevReviewerEvaluationService(
        Path(args.simulation_db or simulation_db_path()),
        Path(args.market_db or market_db_path()),
    )
    try:
        if args.run_id:
            if not args.execute:
                detail = service.detail(args.run_id)
                print("JEV REVIEWER EVALUATION DETAIL")
                print(detail)
                return 0
            detail = service.execute_run(args.run_id)
            print("JEV REVIEWER EVALUATION EXECUTION PASS")
            print(detail)
            return 0

        request_id = (
            args.client_request_id
            or "JEV-EVAL-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        run = service.create_run(
            client_request_id=request_id,
        )
        if not args.execute:
            print("JEV REVIEWER EVALUATION RUN READY")
            print(run)
            print("model_calls_executed=0")
            return 0

        detail = service.execute_run(run["id"])
        print("JEV REVIEWER EVALUATION EXECUTION PASS")
        print(detail)
        print("model_calls_executed=0")
        return 0
    except (JevReviewerEvaluationError, JevEvaluationCatalogError) as exc:
        print(
            f"ERROR [{getattr(exc, 'code', 'JEV_EVALUATION_ERROR')}]: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
