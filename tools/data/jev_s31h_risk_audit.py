"""S31-H frozen real candidate Risk threshold audit (no execution)."""
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
from app.jev.s31h_frozen_risk_event_audit import VERSION, audit_frozen_risk
from tools.data.krx_datewise_collector import RESEARCH_DB
from tools.data.jev_s31e_observe import DEFAULT_RECEIPT
from tools.data.q7_rank_explain import MAX_SOURCE_BYTES


def _percent(v: float | None) -> str:
    return "근거 없음" if v is None else f"{v:+.2f}%"


def korean_report(report: dict) -> str:
    lines = [
        "StockScope S31-H · 실제 후보의 원본 Risk 참고선 대조",
        f"{report['source_date']} KOSPI · 관측 상한 {report['as_of_date']}",
        f"상태: {report['status']}, 확정 EOD {report['complete_eod_sessions']}일",
        f"참고 무효화선 일중 도달: {report['stock_count_with_invalidation_touch']}개",
        f"참고 무효화선 이하 종가 기록: {report['stock_count_below_invalidation_at_close']}개",
        "※ RANGE/ABOVE는 전략 조건 가격대이며 실제 매수 범위나 체결을 뜻하지 않습니다.",
        "※ 실제 매수 여부, 손절 실행 여부 및 당일 위험 대응은 확인되지 않았습니다.",
        "※ 시장지수 대비 변화폭은 단순 가격 비교로 전략 우월성을 뜻하지 않습니다.",
    ]
    if report["unresolved_prior_weekdays"]:
        lines.append(
            "주의: 불확실한 거래일 기록 누락으로 일봉 순서 판정 중지: "
            + ", ".join(report["unresolved_prior_weekdays"])
        )
    for entry in report["records"]:
        lines.extend([
            "",
            f"· {entry['name']} ({entry['code']}) / {entry['original_strategy']}",
            f"  당시 기록: {entry['original_action']}, Risk {entry['original_risk_status']}, "
            f"조건 {entry['original_conditions']['passed']}/{entry['original_conditions']['total']}",
            f"  참고 진입가 {entry['risk_reference_entry']} / 무효화선 {entry['risk_reference_invalidation']} / 목표1 {entry['risk_reference_target1']}",
            f"  신호일 종가 {entry['signal_close']} · 전략 조건 기준 {entry['scanner_entry_price_rule']['kind']}",
        ])
        for day in entry["sessions"]:
            def flag(value):
                return "확인 불가" if value is None else ("도달" if value else "미도달")
            lines.append(
                f"  {day['date']}: 종가변화 {_percent(day['stock_change_from_signal_close_pct'])}, "
                f"KOSPI {_percent(day['index_change_from_signal_close_pct'])}, "
                f"무효화 저가 {flag(day['invalidation_low_touched'])}, "
                f"무효화 종가 {flag(day['invalidation_close_at_or_below'])}, "
                f"전략조건 고저 {flag(day['entry_rule_touched'])}"
            )
            if day["entry_and_invalidation_same_bar_order_unknown"]:
                lines.append("    동일 일봉에 전략조건·무효화선 모두 도달: 선후관계 알 수 없음")
        first = entry["earliest_eod_flags"]
        lines.append(
            f"  최초 참고 무효화 저가 도달: {first['invalidation_low_touch'] or '없음/검증 불가'}"
        )
    lines.extend([
        "",
        "결론: 참고 가격선 사후 대조만 가능. 실제 손절 여부와 JEV 개선 효과는 미검증.",
        "원본·연구 DB 수정 0회 / KRX·JEV 호출 0회 / 주문 0건",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-H local posthoc Risk reference audit")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--market-db", type=Path, default=RESEARCH_DB)
    parser.add_argument(
        "--as-of", default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        help="as-of cutoff in KST (YYYY-MM-DD), future not permitted",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.receipt.is_file() or args.receipt.stat().st_size > MAX_SOURCE_BYTES:
            raise ResearchCaptureError("S31H_RECEIPT_MISSING_OR_TOO_LARGE")
        with args.receipt.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        report = audit_frozen_risk(payload, args.market_db, as_of=args.as_of)
    except (ResearchCaptureError, OSError, sqlite3.Error, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, ResearchCaptureError) else type(exc).__name__
        print(json.dumps({
            "version": VERSION, "status": "HOLD",
            "reason_code": code, "market_network_requests": 0,
            "production_db_writes": 0, "jev_model_calls": 0, "orders": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.json else korean_report(report)
    )
    return 0 if report["status"] == "LOCAL_POSTHOC_RISK_EVENT_AUDIT_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
