"""S31-J local read-only prior READY recheck; user-facing Korean console."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for folder in (ROOT, BACKEND):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.jev.research_scanner_s24 import ResearchCaptureError
from app.jev.s31j_prior_ready_recheck import VERSION, evaluate_prior_ready
from tools.data.jev_s31e_observe import DEFAULT_RECEIPT
from tools.data.krx_datewise_collector import RESEARCH_DB
from tools.data.q7_rank_explain import MAX_SOURCE_BYTES


def korean_report(report: dict[str, object]) -> str:
    index = report["market_context_latest_completed_eod"]
    lines = [
        "StockScope S31-J · 기존 READY 신규 진입 전 재검증",
        f"원본 {report['signal_date']} / 요청 기준 {report['as_of_date']}",
        f"상태: {report['status']}",
        f"최근 확정 로컬 KOSPI EOD: {report['last_confirmed_market_eod'] or '없음'}",
        f"해당 일 KOSPI 등락률: {index['daily_index_change_rate_pct']}% · "
        f"시장 분류: {index['production_regime']}",
        "※ 원본은 사후 기술 점검이며 과거 READY는 현재 매수 허가가 아닙니다.",
        "※ 이 도구는 확정 일봉만 조회하며 실시간 호가·보유정보·자동주문을 사용하지 않습니다.",
    ]
    if report["unconfirmed_market_dates_through_asof"]:
        lines.append(
            "EOD 미확인 날짜: "
            + ", ".join(report["unconfirmed_market_dates_through_asof"])
            + " (휴장 여부까지 확정된 것은 아님)"
        )
    for entry in report["candidates"]:
        lines.extend([
            "",
            f"· {entry['name']} ({entry['code']}) / {entry['original_strategy']}",
            f"  이전 Risk READY: {entry['original_ready']} · 재검증: {entry['recheck_status']}",
            f"  {entry['reason']}",
            f"  기존 참고 무효화선: {entry['original_reference_invalidation_not_executed_stop']}",
            f"  과거 위험 참고선 도달 거래일: {entry['past_reference_breach_day_count']}일 "
            f"({', '.join(entry['past_reference_breach_market_days']) or '없음'})",
            f"  시가·저가·종가의 별도 비교 신호: {entry['past_reference_breach_count']}개 "
            "(독립적인 거래/손절 횟수가 아님)",
        ])
        if entry["additional_market_context"]:
            lines.append("  시장 참고: " + ", ".join(entry["additional_market_context"]))
    lines.extend([
        "",
        "결론: 과거 READY를 신규 매수 추천으로 재사용하지 않습니다. "
        "확정 데이터 갱신 후 현재 시점 Scanner·Risk를 다시 확인해야 합니다.",
        "원본·연구 DB 수정 0회 / KRX·JEV 호출 0회 / 주문 0건",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-J frozen READY recheck (read only)")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--market-db", type=Path, default=RESEARCH_DB)
    parser.add_argument(
        "--as-of",
        default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        help="YYYY-MM-DD, future not allowed",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.receipt.is_file() or args.receipt.stat().st_size > MAX_SOURCE_BYTES:
            raise ResearchCaptureError("S31J_RECEIPT_MISSING_OR_TOO_LARGE")
        with args.receipt.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        report = evaluate_prior_ready(payload, args.market_db, as_of=args.as_of)
    except (ResearchCaptureError, OSError, sqlite3.Error, ValueError, TypeError,
            KeyError, json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, ResearchCaptureError) else type(exc).__name__
        print(json.dumps({
            "version": VERSION, "status": "HOLD",
            "reason_code": code, "market_network_requests": 0,
            "jev_model_calls": 0, "orders": 0, "production_db_writes": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
          if args.json else korean_report(report))
    return 0 if report["status"] == "LOCAL_PRIOR_READY_RECHECK_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
