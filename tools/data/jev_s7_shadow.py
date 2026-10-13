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
from app.jev.scanner_v4_readiness_s7_5 import diagnose_capture as diagnose_v4_readiness
from app.jev.scanner_eligibility_s8 import diagnose_capture as diagnose_s8_eligibility
from app.jev.local_evidence_audit import diagnose_capture as diagnose_local_evidence
from app.jev.local_history_review import review_capture as review_local_history
from app.jev.local_shadow_cohort_s10 import measure_capture as measure_local_cohort
from app.jev.local_outcome_link_s11 import evaluate_capture_readonly as evaluate_local_outcomes
from app.jev.local_first_check_s12 import first_local_check
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
            "prepare", "preflight", "source-audit", "lineage", "v4-readiness",
            "s8-readiness", "local-evidence", "local-history", "local-cohort", "local-outcomes",
            "local-first-check",
        ),
    )
    parser.add_argument("--capture-id", default=None)
    parser.add_argument("--sample-index", type=int, default=None)
    parser.add_argument("--evaluation-run-id", default=None)
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
    if args.mode in ("source-audit", "lineage", "v4-readiness", "s8-readiness", "local-evidence", "local-history", "local-cohort", "local-outcomes", "local-first-check"):
        if args.save_preflight:
            raise DecisionReviewContractError("S7_4_DIAGNOSTIC_READ_ONLY")
        if args.mode == "source-audit":
            if args.capture_id or args.sample_index is not None:
                raise DecisionReviewContractError("S7_4_SOURCE_AUDIT_ARGUMENT_INVALID")
            return source_audit()
        if args.mode == "local-first-check":
            if args.capture_id or args.evaluation_run_id or args.sample_index is not None:
                raise DecisionReviewContractError("S12_AUTO_DISCOVERY_ARGUMENT_CONFLICT")
            return first_local_check(args.simulation_db or simulation_db_path())
        if args.mode == "local-outcomes":
            if args.sample_index is not None:
                raise DecisionReviewContractError("S11_SAMPLE_INDEX_UNSUPPORTED")
            return evaluate_local_outcomes(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id,
                evaluation_run_id=args.evaluation_run_id,
                limit=args.limit,
            )
        if args.mode == "local-cohort":
            if args.sample_index is not None:
                raise DecisionReviewContractError("LOCAL_COHORT_SAMPLE_INDEX_UNSUPPORTED")
            return measure_local_cohort(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id, limit=args.limit,
            )
        if args.mode == "local-history":
            return review_local_history(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id, limit=args.limit,
                sample_index=args.sample_index,
            )
        if args.mode == "local-evidence":
            return diagnose_local_evidence(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id, limit=args.limit,
                sample_index=args.sample_index,
            )
        if args.mode == "s8-readiness":
            return diagnose_s8_eligibility(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id, limit=args.limit,
                sample_index=args.sample_index,
            )
        if args.mode == "v4-readiness":
            return diagnose_v4_readiness(
                args.simulation_db or simulation_db_path(),
                capture_id=args.capture_id, limit=args.limit,
                sample_index=args.sample_index,
            )
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
    if value.get("version") == "JEV_LOCAL_FIRST_CHECK_V1":
        explanations = {
            "NO_LOCAL_SIMULATION_DB": "이 컴퓨터에 Simulation 데이터베이스가 없습니다.",
            "PROSPECTIVE_SCHEMA_NOT_READY": "Prospective 테이블이 아직 준비되지 않았습니다.",
            "NO_COMPLETED_FROZEN_CAPTURE": "완료된 동결 Scanner 후보가 없습니다.",
            "NO_COMPLETED_PROSPECTIVE_EVALUATION": "완료된 Prospective 미래 결과 평가가 없습니다.",
            "LATEST_EVALUATION_HAS_NO_UNITS": "최신 완료 평가에 후보별 결과가 없습니다.",
            "EVALUATION_CAPTURE_NOT_COMPLETE": "최신 평가에 연결된 동결 후보가 완료 상태가 아닙니다.",
            "EVALUATED_CAPTURE_HAS_NO_FROZEN_SAMPLES": "해당 동결 Capture에 저장된 후보가 없습니다.",
            "FROZEN_SAMPLE_COUNT_EXCEEDS_READ_LIMIT": "한도 초과로 전체 후보 분석을 중지했습니다.",
            "LOCAL_PROSPECTIVE_READ_UNAVAILABLE": "로컬 Prospective DB를 안전하게 읽을 수 없습니다.",
            "LOCAL_EVIDENCE_NOT_COMPARABLE": "기존 평가와 동결 후보의 정합성 검증이 통과하지 못했습니다.",
        }
        status = value["status"]
        if status in ("DESCRIPTIVE_OUTCOMES_AVAILABLE", "NO_COMPARABLE_CLOSED_OUTCOMES"):
            print(
                f"동결 후보 {value['frozen_sample_count']}건"
                f" | 진입 후보 {value['entry_candidates']}건"
                f" | 로컬 검토 가능 {value['reviewable']}건"
            )
            print(
                f"잠정 재검토 {value['provisional_recheck']}건"
                f" | 유보 {value['abstained']}건"
                f" | 정합성 차단 {value['integrity_blocked']}건"
            )
            for split, label in (("DEVELOPMENT", "개발용"), ("HOLDOUT", "검증용")):
                part = value["split_descriptive"][split]
                print(
                    f"{label} 결과 비교 가능 {part['closed_comparable']}건"
                    f" | 재검토 {part['flagged_closed']}건"
                    f" | 반대 신호 없음 {part['unflagged_closed']}건"
                )
            if status == "NO_COMPARABLE_CLOSED_OUTCOMES":
                print("현재 연결된 표본 중 종료되어 비교 가능한 결과는 없습니다.")
            print("※ 최근 완료된 평가의 가장 최근 신호일 Capture 1개만 확인했습니다.")
        else:
            print(explanations.get(status, "진단 차단: " + status))
            if value.get("reason_code"):
                print("차단 사유: " + value["reason_code"])
        print("※ 관찰용이며 JEV 수익 개선이나 손실 회피가 입증된 것은 아닙니다.")
        print("※ 외부 AI 호출 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "S11_LOCAL_OUTCOME_LINK_DESCRIPTIVE_ONLY":
        c = value["cohort_counts"]
        print(
            f"진입 후보 {c['entry_candidates']}건"
            f" | 검토 가능 {c['reviewable']}건"
            f" | 유보 {c['abstained']}건"
            f" | 정합성 차단 {c['integrity_blocked']}건"
        )
        for part, label in (("DEVELOPMENT", "개발 표본"), ("HOLDOUT", "검증 표본")):
            row = value["split_descriptive"][part]
            print(
                f"{label}: 결과 비교 가능 {row['closed_comparable']}건"
                f" | 재검토 {row['flagged_closed']}건"
                f" | 과거 반대 신호 없음 {row['unflagged_closed']}건"
            )
        print("이 수치는 기존 Prospective 종료 결과의 관찰적 비교이지, JEV의 손실 회피·성능 향상 증명이 아닙니다.")
        print("※ 외부 AI 호출 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "LOCAL_SHADOW_COHORT_MEASUREMENT_ONLY":
        counts = value["counts"]
        scope = value["scope"]
        print(
            f"조회 {scope['returned_samples']}건"
            f" | 진입 후보 {counts['entry_candidates']}건"
            f" | 참고 {counts['reference_only']}건"
        )
        print(
            f"검토 가능 {counts['reviewable']}건"
            f" | 잠정 재검토 {counts['provisional_recheck']}건"
            f" | 유보 {counts['abstained']}건"
            f" | 정합성 차단 {counts['integrity_blocked']}건"
        )
        if scope["completeness"] == "UNKNOWN_LIMIT_REACHED":
            print("※ 조회 한도에 도달했습니다. 전체 Capture 비율이라고 해석하면 안 됩니다.")
        else:
            print("※ 지정한 Capture에서 조회 한도 미만의 후보를 확인했습니다.")
        print("과거 참고자료와의 불일치만 관찰한 결과로, 판단 오류 발견률이나 투자 성과 개선율은 아닙니다.")
        print("※ 외부 AI 호출 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "LOCAL_HISTORY_SHADOW_OBSERVATION_ONLY":
        counts = value["counts"]
        print(f"조회 {value['total_records']}건"
              f" | 과거 반대 근거 재검토 {counts.get('LOCAL_SHADOW_REVIEW_ONLY', 0)}건"
              f" | 유보 {counts.get('ABSTAIN', 0)}건"
              f" | 과거 반대 근거 미발견 {counts.get('NO_ADVERSE_HISTORY_SIGNAL', 0)}건")
        print("과거 3년 근거는 후보 순위에 반영되지 않은 별도 참고자료입니다.")
        print("재검토는 관찰용 의견이며 현재 추천·실제 매매·성과 평가를 바꾸지 않습니다.")
        print("※ 외부 AI 호출 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "LOCAL_REVIEW_EVIDENCE_DIAGNOSTIC_ONLY":
        counts = value["counts"]
        print(f"조회 {value['total_records']}건"
              f" | 독립 근거 미확보 {counts.get('NO_INDEPENDENT_REVIEW_EVIDENCE', 0)}건"
              f" | 정합성 차단 {counts.get('BLOCKED_INTEGRITY', 0)}건"
              f" | 참고 {counts.get('REFERENCE_ONLY', 0)}건")
        print("현재 PASS 조건·진입 의미·Risk는 기존 검사가 이미 확인한 근거입니다.")
        print("추가 독립 근거를 증명하기 전에는 로컬 AI 검토 의견을 만들지 않습니다.")
        print("※ 실제 시장 데이터 전송 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "S8_SOURCE_RIGHTS_TIME_PROVIDER_HOLD":
        print(
            f"조회 {value['total_records']}건"
            f" | 진입 후보 {value['entry_candidates']}건"
            f" | 참고 {value['reference_count']}건"
        )
        print(
            f"로컬 V4 입력 구성 가능 {value['v4_projectable_count']}건"
            f" | V4 전송필드 계보 미검사 {value['v4_outbound_lineage_unverified_count']}건"
            f" | AI 검토 불필요 {value['v4_local_skipped_count']}건"
        )
        print(
            f"개별 원천 미확인 {value['origin_unverified_count']}건"
            f" | 외부 AI 이용권 미확인 {value['rights_unverified_count']}건"
            f" | 공개 시각 미확인 {value['source_time_unverified_count']}건"
        )
        print(
            "KRX OPEN API 약관: 받은 원본 자료의 제3자 제공 제한"
            " (제11조 2항)."
        )
        print(
            "조건·Risk·순위 등 파생정보의 TypeSafe 처리 권한:"
            " 공식 개별 승인/계정 증거 미확인."
        )
        for record in value["records"]:
            if record["category"] == "REFERENCE_ONLY":
                continue
            ident = record["identity"]
            name = ident.get("name") or ident.get("ticker") or "진입 후보"
            print(
                f"{name} · V4 {record['v4_local_status']}"
                f" · 외부 전송 {record['transmission_decision']}"
            )
            if record["v4_local_status"] == "BLOCKED_HORIZON":
                print("  현재 기록의 투자 기간이 미확정이라 V4 로컬 입력도 만들 수 없습니다.")
            elif record["v4_local_status"] == "BLOCKED_INTEGRITY":
                print("  Scanner 원본·전략·조건 증거가 충분하지 않습니다.")
            elif record["v4_local_status"] == "BLOCKED_SEMANTIC_SOURCE":
                print("  V4가 요구하는 전략 관계·의미 자료가 부족합니다.")
            elif record["v4_local_status"] == "LOCAL_V4_PROJECTABLE":
                print("  로컬 V4 입력은 가능하지만 실제 TypeSafe 처리 권한은 없습니다.")
        print("다음 확인에 필요한 증거:")
        for item in value["next_evidence"]:
            print(f"  - {item}")
        if value["decision"] == "NO_GO_CURRENT_REQUEST":
            print("결론: 데이터 적격성 HOLD / 현재 외부 TypeSafe 전송 NO-GO")
        elif value["decision"] == "NOT_REQUIRED":
            print("결론: AI 호출 대상 없음 / 별도 외부 전송 불필요")
        else:
            print("결론: 진입 검토 대상 없음")
        print("※ 공식 계정 허가, 공개·수집 시각, 자료별 계보는 자동으로 증명되지 않습니다.")
        print("※ 실제 시장 데이터 전송 0건 / Runtime DB 쓰기 0건")
        return
    if value.get("status") == "V4_READINESS_PROVIDER_HOLD":
        counts = value["counts"]
        print(
            f"조회 {value['total_records']}건"
            f" | 진입 후보 {value['entry_candidates']}건"
            f" | 단순 참고 {counts['REFERENCE_ONLY']}건"
        )
        print(
            f"V4 입력 구성 가능 {counts['LOCAL_V4_PROJECTABLE']}건"
            f" | V4 로컬 의미 판단으로 생략 {counts['SKIPPED_LOCAL']}건"
            f" | 원본 정합성 차단 {counts['BLOCKED_INTEGRITY']}건"
            f" | 기간 차단 {counts['BLOCKED_HORIZON']}건"
            f" | 의미 자료 차단 {counts['BLOCKED_SEMANTIC_SOURCE']}건"
        )
        translations = {
            **EXPLAIN, **REASONS_KO, **LINEAGE_REASONS_KO,
            "V4_HORIZON_UNSUPPORTED": (
                "당시 투자 기간이 단기·중기로 확정되지 않아 V4 검토를 진행할 수 없습니다."
            ),
            "S7_4_LINEAGE_NOT_COMPLETE": (
                "로컬 입력의 필드 계보 검사가 완료되지 않았습니다."
            ),
        }
        for record in value["records"]:
            if record["category"] == "REFERENCE_ONLY":
                continue
            ident = record["identity"]
            category = record["category"]
            local_status = record["local_v4_status"]
            print(
                f"{ident.get('name') or ident.get('ticker') or '후보'}"
                f" ({ident.get('ticker') or '식별자 없음'})"
                f" · {category} · {local_status}"
            )
            if local_status == "BLOCKED_HORIZON":
                primary_codes = ["V4_HORIZON_UNSUPPORTED"]
            elif local_status == "BLOCKED_INTEGRITY":
                primary_codes = [
                    code for code in record["integrity_reason_codes"]
                    if code != "LEGACY_DERIVED_IDENTITY"
                ]
                if "S7_4_LINEAGE_NOT_COMPLETE" in record["reason_codes"]:
                    primary_codes.append("S7_4_LINEAGE_NOT_COMPLETE")
            elif local_status == "BLOCKED_SEMANTIC_SOURCE":
                primary_codes = [
                    code for code in record["reason_codes"]
                    if code not in record["provider_blocking_reasons"]
                    and code not in record["integrity_reason_codes"]
                ]
            elif local_status == "SKIPPED_LOCAL":
                primary_codes = [
                    code for code in record["reason_codes"]
                    if code.startswith("SKIPPED_")
                ]
            else:
                primary_codes = []
            for code in dict.fromkeys(primary_codes):
                message = translations.get(code, code)
                if code == "STRATEGY_IDENTITY_MISMATCH" and category == "LEGACY_LIMITED":
                    message = (
                        "원본 전략 버전이 없어 S3 엄격 검사를 통과하지 못했습니다."
                        " 전략 내용이 실제로 서로 다르다고 확인된 것은 아닙니다."
                    )
                print(f"  주된 사유: {message} [{code}]")
            if category == "LEGACY_LIMITED":
                print(
                    "  원본 제한: 당시 전략 버전이 없고 검증된 유도 식별자만"
                    " 있어 완전 검증 기록으로 취급하지 않습니다."
                )
            if local_status == "LOCAL_V4_PROJECTABLE":
                print("  V4 로컬 입력 구성 가능 (실제 TypeSafe 전송은 계속 차단)")
        print(
            "외부 AI 전송: 원천 공개 시각·자료 이용 권한·모델/실행 승인"
            " 확인 전까지 일괄 보류"
        )
        print("※ 모든 원본 진단 코드는 --json 출력에 그대로 보존됩니다.")
        print("※ 실제 시장 데이터 TypeSafe 전송 0건 / DB 쓰기 0건")
        return
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
        captions = {
            "COMPLETE": "필드 분류 검사 완료 (이용 권한 승인 아님)",
            "NOT_RUN": "계보 검사 미수행",
            "PARTIAL": "일부 계보 검사만 완료",
            "NOT_APPLICABLE": "계보 검사 대상 없음",
        }
        status = value["lineage_analysis_status"]
        examined = value["lineage_examined_count"]
        print(f"계보 검사: {captions.get(status, status)}")
        print(
            f"조회 {value['total_records']}건"
            f" | 진입 {value['entry_candidates']}건"
            f" | 정합성 제외 {value['invalid_count']}건"
            f" | 참고 {value['reference_count']}건"
        )
        print(
            f"로컬 JEV 패킷 {value['local_packets_ready']}건"
            f" | 계보 검사 완료 {examined}건"
            f" | 미수행 {value['lineage_not_run_count']}건"
        )
        if examined == 0:
            print("미분류 필드: 검사 미수행 (0건이라고 해서 정상 분류된 것은 아닙니다)")
        else:
            print(f"분류를 검사한 패킷의 미분류 필드: {value['unclassified_fields']}건")
        print("-" * 63)
        explanations = {
            **EXPLAIN,
            **REASONS_KO,
            **LINEAGE_REASONS_KO,
            "BASELINE_RANK_MISMATCH": "저장된 기준 추천 순위와 원본 순위의 정합성을 확인할 수 없습니다.",
            "PACKET_HASH_MISMATCH": "로컬 패킷 내용과 무결성 해시가 일치하지 않습니다.",
            "S7_4_PACKET_SHAPE_INVALID": "계보 검사 도중 패킷 형식을 확인할 수 없었습니다.",
        }
        for record in value["records"]:
            ident = record["identity"]
            category = record["category"]
            stage = record["lineage_analysis_status"]
            print(
                f"{ident.get('name') or ident.get('ticker') or '후보'}"
                f" ({ident.get('ticker') or '식별자 없음'})"
                f" · {category} · {record['integrity_status']}"
            )
            if stage == "NOT_APPLICABLE":
                print("  참고 기록: 원래 진입 후보가 아니므로 계보 검사 대상이 아닙니다.")
                continue
            if stage == "NOT_RUN":
                print("  계보 검사 미수행: 유효한 로컬 패킷이 없습니다.")
            elif stage == "PARTIAL":
                print("  계보 검사 중단: 일부 또는 전체 필드의 검사가 완료되지 않았습니다.")
            else:
                print("  필드 분류 검사 완료 (원천 권한·공개 시각은 별도 미확인)")
            if stage == "COMPLETE":
                for field in record["field_diagnostics"]:
                    parents = ", ".join(field.get("expected_parents", [])) or "내부 정의/기록"
                    print(
                        f"  {field['path']}: {field['origin_type']}"
                        f" | 예상 의존: {parents}"
                        f" | 실제 원천: {field['actual_source']}"
                        f" | 전송권한: {field['rights_status']}"
                        f" | 시각: {field['time_quality']}"
                    )
                    if field.get("local_source_ref"):
                        print(f"    로컬 근거: {field['local_source_ref']}")
                    if field.get("producer_ref") and (
                        field["path"].endswith(".statement")
                        or field["path"] in ("baseline.rank", "baseline.risk.status")
                    ):
                        print(f"    생성 함수: {field['producer_ref']}")
            original_codes = record.get("integrity_reason_codes", [])
            for code in original_codes:
                print(f"  원본 정합성: {explanations.get(code, code)} [{code}]")
            for code in record["reason_codes"]:
                if code in original_codes or (original_codes and code == "LOCAL_INTEGRITY_NOT_VERIFIED"):
                    continue
                print(f"  진단 제한: {explanations.get(code, code)} [{code}]")
        print("※ 필드 분류 완료는 원천 확인이나 외부 AI 전송 허가를 뜻하지 않습니다.")
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
        if value["local_packets_ready"] == 0:
            print("※ 실제 로컬 JEV 패킷 0건: 준비된 입력이 없어 계보 검사를 진행할 수 없습니다.")
            print("※ 위 상태명은 데이터 전송 또는 개별 후보 준비 성공을 뜻하지 않습니다.")
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
