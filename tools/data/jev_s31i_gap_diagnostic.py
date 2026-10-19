"""S31-I: explain source-day market regime separately from future open gaps."""
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
from app.jev.s31i_market_gap_diagnostic import VERSION, analyze_market_gap
from tools.data.jev_s31e_observe import DEFAULT_RECEIPT
from tools.data.krx_datewise_collector import RESEARCH_DB
from tools.data.q7_rank_explain import MAX_SOURCE_BYTES


def korean_report(report: dict[str, object]) -> str:
    ctx = report["signal_day_known_information"]
    rate = ctx["original_index_daily_change_rate_pct"]
    lines = [
        "StockScope S31-I · 시장·갭 리스크 진단 (사후 검토, 주문 아님)",
        f"원본 {report['signal_date']} / 사후 관측 ~ {report['as_of_date']}",
        f"14일 KOSPI 당일 지수변화: {rate if rate is not None else '자료 없음'}% "
        f"· 기존 레짐 분류 {ctx['production_regime_rule']}",
        "※ 위 줄만 신호일 시점 자료에 근거합니다. 미래 하락을 사전에 알았던 것은 아닙니다.",
        "※ RANGE/ABOVE는 전략 조건 참고 가격대이지 실제 매수 주문/체결이 아닙니다.",
        f"확정 EOD {report['complete_eod_sessions']}일, "
        f"시가가 기존 참고 무효화선 이하인 관측 {report['post_signal_open_below_invalidation_event_count']}건",
    ]
    if report["unresolved_prior_weekdays"]:
        lines.append("검증 보류: 거래일 누락 " + ", ".join(report["unresolved_prior_weekdays"]))
    for row in report["candidates"]:
        lines.extend([
            "",
            f"· {row['name']} ({row['code']}) / {row['original_strategy']}",
            f"  원본 {row['original_action']}, Risk {row['original_risk_status']}, "
            f"전략 조건 {row['original_conditions']['passed']}/{row['original_conditions']['total']}",
            f"  신호 종가 {row['signal_close']} / Risk 참고 진입기준 "
            f"{row['reference_entry']} / 참고 무효화선 {row['reference_invalidation']}",
        ])
        for event in row["days"]:
            name = event["opening_gap_class"]
            desc = {
                "OPEN_AT_OR_BELOW_REFERENCE_INVALIDATION": "시가부터 참고 무효화선 이하",
                "OPEN_BELOW_SIGNAL_CLOSE_ABOVE_INVALIDATION": "하락 출발, 참고 무효화선 위",
                "OPEN_AT_OR_ABOVE_SIGNAL_CLOSE": "전일 신호 종가 이상 출발",
                "OPENING_PRICE_UNAVAILABLE_OR_INVALID_BAR": "시가 자료 불충분",
                "ORIGINAL_INVALIDATION_REFERENCE_UNAVAILABLE": "무효화선 미검증",
                "OPEN_ABOVE_INVALIDATION_SIGNAL_CLOSE_UNKNOWN": "기준 종가 자료 없음",
            }.get(name, name)
            pct = event["opening_gap_from_signal_close_pct"]
            gap = f"{pct:+.2f}%" if pct is not None else "확인 불가"
            lines.append(
                f"  {event['date']}: 시가 {event['opening_price']} (신호 종가 대비 {gap}), {desc}"
            )
    lines.extend([
        "",
        "실제 매수·보유·손절 주문/체결 및 Risk 실시간 경고 이력은 미검증.",
        "KRX/JEV 호출 0회 · 원본/연구 DB 쓰기 0회 · 주문 0건.",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-I read-only frozen market/open-gap audit")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--market-db", type=Path, default=RESEARCH_DB)
    parser.add_argument("--as-of", default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.receipt.is_file() or args.receipt.stat().st_size > MAX_SOURCE_BYTES:
            raise ResearchCaptureError("S31I_RECEIPT_MISSING_OR_TOO_LARGE")
        with args.receipt.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        report = analyze_market_gap(payload, args.market_db, as_of=args.as_of)
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
    return 0 if report["status"] == "LOCAL_SIGNAL_ASOF_AND_POSTHOC_GAP_DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
