"""S31-B actual Scanner-candidate review preflight, strictly local/read-only.

inspect --receipt <saved S27 capture> [--limit 5] [--json]
review  --receipt <saved S27 capture> --limit 1 --model jev-latest

'preflight' review is deliberately blocked: TypeSafe S6 synthetic approvals
do not authorize transmission of real KRX-derived facts. No HTTP, API key,
provider calls, DB writes, CLI consent flags, or orders exist in this command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for directory in (ROOT, BACKEND):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from app.jev.s31_real_candidate_trial import inspect_frozen_candidates, VERSION
from app.jev.research_scanner_s24 import ResearchCaptureError
from tools.data.q7_rank_explain import load_file_readonly


def korean_report(report: dict) -> str:
    lines = [
        "StockScope JEV S31-B · 실제 Scanner 후보 로컬 검토",
        f"기준: {report['source_date']} / {report['market']} · "
        f"원본 진입 후보 {report['original_entry_count']}개",
        f"상태: {report['status']}",
        "※ JEV 실제 종목 추론은 실행되지 않았습니다. S6 합성 실험과는 별개입니다.",
        "",
    ]
    for record in report["candidates"]:
        base = record["baseline"]
        local = record["local_evidence"]
        lines.extend([
            f"· {record['name']} ({record['code']}) / {base['strategy']}",
            f"  기본 Scanner: {base['action']} · Risk {base['risk_status']}"
            f" · 조건 {base['conditions_passed']}/{base['conditions_total']}",
            f"  1차 목표 참고 손익비: "
            f"{local['target1_r_multiple'] if local['target1_r_multiple'] is not None else '근거 없음'}R",
            f"  로컬 점검: {', '.join(local['alerts']) or '추가 경고 없음'}",
            "  JEV: 미실행 (외부 전송 권한 확인 전)",
        ])
    lines.extend([
        "",
        "외부 모델 전송 차단 사유:",
        *("  - " + reason for reason in report["blockers"]),
        "다음 확인: KRX 파생정보 전송 허가 · TypeSafe 계정 계약 "
        "· 소스 공개 시점 증명 · 별도 실험 승인",
        "외부 요청 0회 · 실제 JEV 호출 0회 · 운영 DB 변경 0건 · 주문 0건",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S31-B frozen real Scanner evidence only; provider is blocked",
    )
    parser.add_argument("mode", choices=("inspect", "review"))
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = load_file_readonly(args.receipt)
        # Load the original *unchanged* bytes separately for full identities;
        # load_file_readonly already verifies the frozen hash and size.
        # Parse a second time: no writes, no runtime or network.
        with args.receipt.open("r", encoding="utf-8") as handle:
            receipt = json.load(handle)
        if receipt.get("payload_hash") != source["original_payload_hash"]:
            raise ResearchCaptureError("S31B_SOURCE_CHANGED_DURING_INSPECTION")
        result = inspect_frozen_candidates(
            receipt, limit=args.limit, review=args.mode == "review",
            model=args.model,
        )
    except (ResearchCaptureError, OSError, ValueError, TypeError,
            json.JSONDecodeError) as exc:
        result = {
            "version": VERSION,
            "status": "HOLD_SOURCE_INVALID",
            "reason_code": getattr(exc, "code", type(exc).__name__),
            "external_requests": 0,
            "jev_model_calls": 0,
            "production_market_db_writes": 0,
            "production_simulation_db_writes": 0,
            "orders": 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.json else korean_report(result)
    )
    return 0 if result["status"] == "LOCAL_REAL_CANDIDATE_COMPARISON_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
