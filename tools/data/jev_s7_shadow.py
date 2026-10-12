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
from app.jev.scanner_lineage_s7_4 import diagnose_capture, source_audit, REASONS_KO as LINEAGE_REASONS_KO
from app.jev.scanner_integrity_s7_1 import EXPLAIN
from app.jev.scanner_shadow_s7_3 import (
    S73PreflightJournal, REASONS_KO, prepare_capture,
)
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
        choices=(
            "status", "inspect", "capture", "report", "run-approved",
            "prepare", "preflight", "source-audit", "lineage",
        ),
    )
    parser.add_argument("--capture-id", default=None)
    parser.add_argument("--sample-index", type=int, default=None)
    parser.add_argument(
        "--save-preflight", action="store_true",
        help="Append unchanged preflight verdicts to isolated research DB.",
    )
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
    if args.mode in ("source-audit", "lineage"):
        if args.save_preflight:
            raise DecisionReviewContractError("S7_4_DIAGNOSTIC_READ_ONLY")
        if args.mode == "source-audit":
            if args.capture_id or args.sample_index is not None:
                raise DecisionReviewContractError("S7_4_SOURCE_AUDIT_ARGUMENT_INVALID")
            return source_audit()
        return diagnose_capture(
            args.simulation_db or simulation_db_path(),
            capture_id=args.capture_id, limit=args.limit,
            sample_index=args.sample_index,
        )
    if args.mode == "report":
        return S7ShadowJournal(research_db).report()
    if args.mode in ("prepare", "preflight"):
        if args.save_preflight and args.mode != "preflight":
            raise DecisionReviewContractError("S7_3_SAVE_PREFLIGHT_MODE_INVALID")
        result = prepare_capture(
            args.simulation_db or simulation_db_path(),
            capture_id=args.capture_id,
            limit=args.limit, sample_index=args.sample_index,
            include_preflight=args.mode == "preflight",
        )
        if args.save_preflight:
            result["research_write"] = S73PreflightJournal(research_db).record(result)
        return result
    if args.save_preflight or args.sample_index is not None:
        raise DecisionReviewContractError("S7_3_OPTION_REQUIRES_PREPARE_OR_PREFLIGHT")
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
    if value.get("status") == "SOURCE_AUDIT_PROVIDER_HOLD":
        print("KRX OPEN API 기본 Scanner 경로 (코드 기준, 실제 개별 행 인증 아님):")
        for item in value["products"]:
            print(f"  {item['name']} · {item['expected_endpoint']}")
            print("    원본 제3자 제공: 공개 약관상 제한"
                  " | 파생정보의 외부 AI 처리: 미확인"
                  " | 실제 계정 허가: 미확인")
        print("별도 경로: KIS / OpenDART / FRED / NAVER (기본 S7.3 입력 아님)")
        print("추가 확인 필요:")
        for item in value["next_evidence"]:
            print(f"  - {item}")
        print("실제 시장 데이터 외부 TypeSafe 호출: 0건 (계속 보류)")
        return
    if value.get("status") == "LINEAGE_DIAGNOSTIC_PROVIDER_HOLD":
        print(f"조회 {value['total_records']}건"
              f" | 로컬 패킷 {value['local_packets_ready']}건"
              f" | 미분류 필드 {value['unclassified_fields']}건")
        for record in value["records"]:
            ident = record["identity"]
            print(f"{ident.get('name') or ident.get('ticker') or '후보'}"
                  f" ({ident.get('ticker') or '식별자 없음'})"
                  f" · {record['category']} · {record['integrity_status']}")
            for field in record["field_diagnostics"]:
                parents = ", ".join(field.get("expected_parents", [])) or "내부 정의/기록"
                print(f"  {field['path']}: {field['origin_type']}"
                      f" | 예상 의존: {parents}"
                      f" | 실제 원천: {field['actual_source']}"
                      f" | 전송권한: {field['rights_status']}"
                      f" | 시각: {field['time_quality']}")
                if field.get("local_source_ref"):
                    print(f"    로컬 근거: {field['local_source_ref']}")
                if field.get("producer_ref") and (
                    field["path"].endswith(".statement")
                    or field["path"] in ("baseline.rank", "baseline.risk.status")
                ):
                    print(f"    생성 함수: {field['producer_ref']}")
            for code in record["reason_codes"]:
                print(f"  보류 사유: {LINEAGE_REASONS_KO.get(code, code)} [{code}]")
        print("※ 코드상 예상 출처는 개별 자료의 실제 출처/이용권 증명이 아닙니다.")
        print("※ 원본과 Runtime은 변경되지 않았으며 외부 호출은 0건입니다.")
        return
    if "local_packets_ready" in value:
        print(
            f"실제 조회 {value['total_records']}건"
            f" | 진입 {value['entry_candidates']}건"
            f" | 로컬 JEV 입력 준비 {value['local_packets_ready']}건"
        )
        print(
            f"완전 검증 {value['local_validated']}건"
            f" | 제한적 레거시 {value['legacy_limited']}건"
            f" | 제외 {value['invalid']}건"
            f" | 참고 {value['references']}건"
        )
        print("실제 종목 TypeSafe 전송 허용: 0건 / 유료 호출: 0건")
        print("-" * 63)
        for item in value.get("records", []):
            ident = item["identity"]
            if item["category"] == "REFERENCE_ONLY":
                continue
            print(f"{ident['name'] or ident['ticker']} ({ident['ticker']})"
                  f" · {item['category']} · {item['status']}"
                  f" · {item['temporal_status']}")
            for code in item.get("blocking_reasons", item.get("reason_codes", [])):
                print(f"  제한: {REASONS_KO.get(code, code)} [{code}]")
        if value.get("research_write"):
            print(f"사전 점검 기록: 신규 {value['research_write']['inserted']}건"
                  f" / 재사용 {value['research_write']['reused']}건")
        print("※ 로컬 준비 성공은 외부 AI 전송 승인이나 수익률 개선을 의미하지 않습니다.")
        return
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
        print("가격 관찰 (진입 후보만 집계, 실제 체결 성과 아님):")
        for name, item in value["window_summaries"].items():
            average = item["average_signal_close_change_pct"]
            avg = f"{average:+.2f}%" if average is not None else "아직 없음"
            print(
                f"{name} 관찰: {item['observed']}건, "
                f"추천일 종가 대비 평균 변화 {avg}, "
                f"관찰 미완료 {item['not_yet_observed']}건"
                f" (거래일 데이터 부족 {item.get('awaiting_future_trading_days', 0)}건,"
                f" 가격 자료 부족·불명확 {item.get('price_unavailable_or_incomplete', 0)}건)"
            )
    print(
        f"실제 JEV 검토: "
        f"{value.get('actual_jev_reviews', value.get('real_jev_review_count', 0))}건"
    )
    if "real_stock_provider_eligible" in value:
        print(f"외부 AI 전송 허용 후보: {value['real_stock_provider_eligible']}건")
    if value.get("entry_window_summaries_by_integrity"):
        category_labels = {
            "LOCAL_VALIDATED": "로컬 정합성 통과",
            "LEGACY_LIMITED": "레거시 제한",
            "INVALID": "정합성 제외",
            "NOT_DIAGNOSED": "진단 전 기록",
        }
        for category, windows in value["entry_window_summaries_by_integrity"].items():
            denominator = windows["5d"]["entry_candidate_denominator"]
            if denominator == 0:
                continue
            print(f"{category_labels.get(category, category)} {denominator}건의 가격 관찰:")
            for name, item in windows.items():
                average = item["average_signal_close_change_pct"]
                avg = f"{average:+.2f}%" if average is not None else "아직 없음"
                print(f"  {name}: 완료 {item['observed']}건"
                      f" / 미완료 {item['not_yet_observed']}건"
                      f" / 평균 종가 변화 {avg}")
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
