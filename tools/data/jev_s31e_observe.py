"""Inspect one frozen real Scanner receipt vs already stored local EOD prices.

Network/protocol/DB write and actual JEV capabilities deliberately absent.
Use --as-of YYYY-MM-DD to pin a repeatable as-of cutoff.
"""
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
from app.jev.s31e_frozen_price_observation import (
    VERSION, observe_frozen_candidates,
)
from tools.data.common import market_db_path
from tools.data.q7_rank_explain import MAX_SOURCE_BYTES

DEFAULT_RECEIPT = (
    ROOT / "data" / "q7_research_scanner" / "smoke_only" /
    "2026-10-14_kospi" / "scanner_research_capture.json"
)


def korean_report(report: dict) -> str:
    lines = [
        "StockScope JEV S31-E · 10/14 실제 Scanner 후보의 로컬 사후 가격 관측",
        f"상태: {report['status']} · 원본 {report['source_date']} / 관측 상한 {report['as_of_date']}",
        f"진입 후보 {report['candidate_count']}개 · 종가 관측 완료 "
        + ", ".join(f"{k} {v}개" for k, v in report["observed_window_counts"].items()),
        "중간 관측 1·2·3거래일: "
        + ", ".join(f"{k} {v}개" for k, v in report["early_observed_counts"].items()),
        "※ 중간 관측은 5·10·20거래일 평가를 대체하지 않습니다.",
        "※ 원본은 사후 기술 점검이며, 사전 추천 적중률이 아닙니다.",
        "※ 수익률은 매매 성과가 아니라 기준일 종가 대비 시장 종가 변화율입니다.",
        "",
    ]
    for record in report["candidates"]:
        lines.extend([
            f"· {record['name']} ({record['code']}) / {record['baseline']['strategy']}",
            f"  데이터: {record['observation_status']} · 완료 EOD {record['completed_market_days_after_signal']}일",
            f"  기준일 종가: {record['signal_close_reference'] if record['signal_close_reference'] is not None else '없음'}",
        ])
        for label, window in record["early_windows"].items():
            lines.append(
                f"  중간 {label}: "
                + (
                    f"{window['return_pct']:+.4f}% (종료일 {window['end_date']})"
                    if window["return_pct"] is not None else
                    f"관측 불가 ({window['status']})"
                )
            )
        for label, window in record["windows"].items():
            lines.append(
                f"  평가 {label}: "
                + (
                    f"{window['return_pct']:+.4f}% (종료일 {window['end_date']})"
                    if window["return_pct"] is not None else
                    f"관측 불가 ({window['status']})"
                )
            )
    lines.extend([
        "",
        "JEV 실종목 추론 0회 · 외부 조회 0회 · 운영 DB 변경 0건 · 주문 0건",
        "기존 Risk/Scanner 기준과 실제 투자 성과를 비교한 결과는 아닙니다.",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-E local EOD observation only")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--market-db", type=Path, default=None)
    parser.add_argument(
        "--as-of",
        default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        help="Korean local observation ceiling YYYY-MM-DD; never after today",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = args.receipt
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ResearchCaptureError("S31E_RECEIPT_FILE_MISSING_OR_TOO_LARGE")
        # Parse exactly once; S31-B's source validation verifies the receipt
        # hash and frozen identities before consulting any market data.
        with path.open("r", encoding="utf-8") as fh:
            receipt = json.load(fh)
        report = observe_frozen_candidates(
            receipt, args.market_db or market_db_path(), as_of=args.as_of,
        )
    except (ResearchCaptureError, ValueError, TypeError, OSError,
            sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({
            "version": VERSION,
            "status": "HOLD_LOCAL_EVIDENCE",
            "reason_code": (
                exc.code if isinstance(exc, ResearchCaptureError)
                else type(exc).__name__
            ),
            "jev_model_calls": 0, "market_network_requests": 0,
            "production_db_writes": 0, "research_db_writes": 0, "orders": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.json else korean_report(report)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
