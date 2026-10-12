"""S7 real-candidate Scanner baseline and forward-price observation CLI.

All modes are read-only on Prospective and market stores; 'capture' only
appends observations to an isolated gitignored research SQLite file.
No TypeSafe networking / credential access / production orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_integrity_s7_1 import EXPLAIN
from app.jev.scanner_shadow_s7 import (
    VERSION, S7ShadowJournal, inspect_real_candidates,
)
from tools.data.common import market_db_path, simulation_db_path

RESEARCH_DB = ROOT / "data" / "jev_research" / "s7_shadow.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope S7 actual Scanner outcomes, offline-only."
    )
    parser.add_argument(
        "mode", nargs="?", default="status",
        choices=("status", "inspect", "capture", "report", "run-approved"),
    )
    parser.add_argument("--capture-id", default=None)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--simulation-db", type=Path, default=None)
    parser.add_argument("--market-db", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def execute(
    args: argparse.Namespace, *, research_db: Path = RESEARCH_DB,
) -> dict[str, Any]:
    if args.mode == "status":
        return {
            "version": VERSION, "status": "LOCAL_OBSERVATION_READY_PROVIDER_HOLD",
            "real_candidates_can_be_read": True,
            "external_model_requests_supported": False,
            "reason": "SOURCE_RELEASE_TIME_AND_RIGHTS_AND_HORIZON_UNVERIFIED",
            "actual_provider_calls": 0,
        }
    if args.mode == "run-approved":
        # Explicitly impossible to 'fix' legal/right provenance by a flag or
        # owner typing a broad permission. Never load tokens in this branch.
        return {
            "version": VERSION, "status": "HOLD",
            "reason": "REAL_MARKET_PROVIDER_ADAPTER_NOT_AUTHORIZED",
            "next": "SOURCE_AVAILABLE_AT_RIGHTS_HORIZON_EVIDENCE_REQUIRED",
            "actual_provider_calls": 0,
            "db_writes": 0,
        }
    if args.mode == "report":
        return S7ShadowJournal(research_db).report()
    if args.mode not in ("inspect", "capture"):
        raise DecisionReviewContractError("S7_MODE_INVALID")
    report = inspect_real_candidates(
        args.simulation_db or simulation_db_path(),
        args.market_db or market_db_path(),
        capture_id=args.capture_id,
        limit=args.limit,
    )
    if args.mode == "capture":
        result = S7ShadowJournal(research_db).capture(report)
        report["research_write"] = result
    return report


def display(value: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    print("=" * 63)
    print("StockScope S7 · 실제 추천 후보 관찰")
    print("=" * 63)
    print(f"상태: {value.get('status', 'UNKNOWN')}")
    if "candidate_count" in value:
        print(f"전체 조회 기록: {value['candidate_count']}건")
        if "entry_candidate_count" in value:
            print(
                f"실제 진입 후보: {value['entry_candidate_count']}건"
                f" | 비추천·참고 기록: {value.get('reference_count', 0)}건"
            )
        if "local_validated_count" in value:
            print(
                f"로컬 정합성 확인: {value['local_validated_count']}건"
                f" | 제한적 레거시: {value.get('legacy_limited_count', 0)}건"
                f" | 정합성 제외: {value.get('integrity_invalid_count', 0)}건"
            )
        if value.get("not_diagnosed_count"):
            print(
                f"이전 기록 미진단: {value['not_diagnosed_count']}건"
                " (최신 코드로 capture 재실행 필요)"
            )
    if value.get("integrity_issue_counts"):
        print("후보 정합성 진단 (한 후보에 복수 사유 가능):")
        for code, count in value["integrity_issue_counts"].items():
            print(f"  {EXPLAIN.get(code, code)} [{code}]: {count}건")
    if "observed_price_count" in value:
        print(f"가격 관찰 가능: {value['observed_price_count']}건")
    if "window_summaries" in value:
        print("가격 관찰 (과거 진입 후보 전체이며 정합성 통과 성과가 아님):")
        for name, item in value["window_summaries"].items():
            average = item["average_signal_close_change_pct"]
            avg = f"{average:+.2f}%" if average is not None else "아직 없음"
            print(
                f"{name} 관찰: {item['observed']}건, "
                f"추천일 종가 대비 평균 변화 {avg}, "
                f"미확정 {item['not_yet_observed']}건"
            )
    print(
        f"실제 JEV 검토: "
        f"{value.get('actual_jev_reviews', value.get('real_jev_review_count', 0))}건"
    )
    if "real_stock_provider_eligible" in value:
        print(f"외부 AI 전송 허용 후보: {value['real_stock_provider_eligible']}건")
    if value.get("validated_window_summaries"):
        print("정합성 통과 후보의 가격 관찰 (체결 수익률 아님):")
        for name, item in value["validated_window_summaries"].items():
            average = item["average_signal_close_change_pct"]
            avg = f"{average:+.2f}%" if average is not None else "아직 없음"
            print(f"  {name}: {item['observed']}건 / 평균 종가 변화 {avg}")
    if value.get("blocker_counts"):
        print("외부 전송 및 로컬 검증 제한 사유별 발생 수:")
        for key, count in value["blocker_counts"].items():
            print(f"  {key}: {count}건")
    if value.get("research_write"):
        entry = value["research_write"]
        print(f"관찰 기록: 신규 {entry['inserted']}건 / 재사용 {entry['reused']}건")
    if value.get("records"):
        print("-" * 63)
        eligible = [
            rec for rec in value["records"]
            if rec.get("baseline_action") == "ENTRY_CANDIDATE"
        ]
        for rec in eligible[:10]:
            ob = rec["observation"]
            vals = [
                f"{i}일: " + (
                    f"{ob.get(f'return_{i}d'):+.2f}%"
                    if ob.get(f"return_{i}d") is not None else "관찰 중"
                )
                for i in (5, 10, 20)
            ]
            print(
                f"{rec['name'] or rec['ticker']} ({rec['ticker']})"
                f" · 신호 {rec['signal_date']}"
                f" · 정합성 {(rec.get('integrity') or {}).get('category', 'NOT_DIAGNOSED')}"
                " · " + " / ".join(vals)
            )
    if value.get("status") == "HOLD":
        print(f"차단 사유: {value.get('reason')}")
    print(
        "※ 추천일 종가 기준 가격 관찰이며 실제 체결 수익률이 아닙니다. "
        "JEV의 실전 성과 개선은 검증되지 않았습니다."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute(args)
        display(result, as_json=args.json)
        return 0 if result.get("status") != "HOLD" else 2
    except (DecisionReviewContractError, ValueError) as exc:
        print(f"S7 검증 중단: {getattr(exc, 'code', str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
