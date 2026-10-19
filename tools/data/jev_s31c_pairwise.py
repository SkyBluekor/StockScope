"""S31-C read-only paired S6 synthetic results; no network or provider calls.

Usage: .venv/Scripts/python.exe tools/data/jev_s31c_pairwise.py [--json]
Reads ONLY the default gitignored S6 journal, never production databases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for folder in (ROOT, BACKEND):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.jev.decision_reviewer_micro_canary import MicroJournal
from app.jev.s31c_synthetic_pairwise import VERSION, compare_actual_s6_records

RESEARCH_DB = ROOT / "data" / "jev_research" / "s6_micro_canary.sqlite3"


def read_s6_journal_readonly(path: Path = RESEARCH_DB) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise ValueError("S31C_S6_JOURNAL_NOT_FOUND")
    # No default sqlite3.connect(path): that would create a missing DB.
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        return MicroJournal(connection).list_records()
    finally:
        connection.close()


def korean_report(report: dict) -> str:
    lines = [
        "StockScope JEV S31-C · 이미 호출한 JEV의 합성 판단 비교",
        f"상태: {report['status']}",
        "비교 기준: S6 합성 '진입 후보 유지' 가정 vs 실제 TypeSafe JEV 응답",
        "※ 실제 Scanner 종목 분석이나 수익률 검증이 아닙니다.",
        f"누적 실제 호출 기록 {report['actual_provider_journal_records']}건 "
        f"/ 현재 근거와 비교 가능 {report['comparable_actual_responses']}건 "
        f"/ 비교 제외 {report['invalid_or_noncomparable_actual_records']}건",
        f"Mock·비실제 기록 제외: {report['mock_or_nonactual_records_excluded']}건",
        "",
    ]
    for i, cohort in enumerate(report["cohorts"], 1):
        lines.extend([
            f"[비교 그룹 {i}] 요청 모델 {cohort['model_requested']} "
            f"/ 응답 모델 {cohort['model_reported']}",
            f"  합성 정답 일치: 진입 유지 가정 {cohort['baseline_matches']}/{cohort['case_count']}, "
            f"JEV {cohort['jev_matches']}/{cohort['case_count']}",
            f"  동일 사례 내 일치 건수 차이: {cohort['paired_correct_count_difference']:+d}건 "
            "(수익 개선 수치 아님)",
            f"  명시적 모순 놓침 {cohort['explicit_conflicts_missed']}건 / "
            f"정상 사례 불필요한 경고 {cohort['normal_cases_falsely_flagged']}건 / "
            f"근거 부족 상황 보류 실패 {cohort['insufficient_cases_not_abstained']}건",
            f"  평균 지연시간: {cohort['mean_latency_ms'] if cohort['mean_latency_ms'] is not None else '미기록'}ms",
            f"  다섯 합성 사례 모두 비교: {'예' if cohort['full_five_case_coverage'] else '아니오 (표본 제한)'}",
        ])
        if cohort["moving_alias_or_revision_not_proven"]:
            lines.append("  주의: 모델 alias의 실제 revision은 검증되지 않았습니다.")
        if cohort["reported_model_changed_within_protocol"]:
            lines.append("  주의: 동일 프로토콜에서 서로 다른 응답 모델이 관측되어 별도 그룹으로 분리했습니다.")
        for case in cohort["cases"]:
            lines.append(
                f"  · {case['case']}: 합성 기대 {case['synthetic_expected']} "
                f"/ 기본 가정 {case['authored_baseline']} "
                f"/ JEV {case['actual_jev_decision']} "
                f"({'일치' if case['jev_matches_synthetic_gold'] else '불일치'})"
            )
        lines.append("")
    if report["excluded"]:
        lines.append("비교 제외: " + ", ".join(
            f"{item['case']}({item['reason_code']})" for item in report["excluded"]
        ))
    lines.extend([
        "그룹 간 정답률은 합산하지 않습니다. 실제 모델 추가 호출·비용 발생 없음.",
        "JEV가 투자 손실을 줄이거나 수익률을 높인다는 근거는 아직 없습니다.",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-C offline paired synthetic review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        records = read_s6_journal_readonly(RESEARCH_DB)
        result = compare_actual_s6_records(records)
    except (sqlite3.Error, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result = {
            "version": VERSION,
            "status": "HOLD_READ_ONLY",
            "reason_code": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "new_provider_requests": 0,
            "runtime_db_writes": 0,
            "research_db_writes": 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.json else korean_report(result)
    )
    return 0 if result["status"] == "SYNTHETIC_PAIRED_EVIDENCE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
