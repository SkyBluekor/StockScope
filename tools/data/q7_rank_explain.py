"""S28 frozen Scanner rank diagnostic: readable Korean or machine-readable JSON.

Usage:
 python tools/data/q7_rank_explain.py --file data/q7_research_scanner/smoke_only/2026-10-14_kospi/scanner_research_capture.json
 python tools/data/q7_rank_explain.py --file ... --json

Read-only. Does not issue orders, query KRX, mutate captures or recompute rank.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for root in (ROOT, BACKEND):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from app.jev.rank_evidence_s28 import inspect_receipt
from app.jev.research_scanner_s24 import ResearchCaptureError

MAX_SOURCE_BYTES = 10 * 1024 * 1024


def load_file_readonly(path: Path) -> dict:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ResearchCaptureError("S28_RECEIPT_FILE_MISSING_OR_TOO_LARGE")
    with source.open("r", encoding="utf-8") as fp:
        result = json.load(fp)
    return inspect_receipt(result)


def _num(value: float | None, suffix: str = "") -> str:
    return "근거 없음" if value is None else f"{value:,.2f}{suffix}"


def korean_summary(report: dict) -> str:
    out = [
        "S28 | 저장된 Scanner 순위 근거 점검 (읽기 전용)",
        f"기준: {report['source_date']} / {report['market']}",
        f"상태: {report['status']}",
        f"전체 후보 {report['candidate_count']}개 · 현재 진입 검토 후보 {report['entry_candidates']}개",
        "",
        "※ 표시 번호는 기대수익률·투자 성과의 우열을 증명하지 않습니다.",
        "※ 구조 저항까지 거리와 실제 Target1은 다를 수 있습니다.",
        "",
    ]
    for group in report["tie_groups"]:
        if group["declared_size"] > 1:
            out.append(
                f"동률 그룹 {group['tie_group']} · {group['visible_members']}/{group['declared_size']}개"
                f" · {group['status']}"
            )
            out.append(f"  {group['reason'] or '그룹 일부만 관측되어 순위 검증 불가'}")
        if group["status"] == "INCONSISTENT_TIE_METADATA":
            out.append("  경고: 정렬 기록 불일치 — 원본과 코드 재검토 필요")
    out.append("")
    for row in report["candidates"]:
        price = row["price_evidence"]
        if row["action"] == "ENTRY_CANDIDATE":
            out.extend([
                f"[화면 {row['display_rank']}번 · 동률 {row['tie_size']}개] "
                f"{row['name']} ({row['code']}) / {row['strategy']}",
                f"  상태: {row['tier']} · Risk {row['risk_status']} "
                f"· 3년 과거 검증: {row['historical_status']}",
                f"  현재 진입 기준과의 거리: {_num(row['entry_gap_pct'], '%')} "
                f"({row['entry_gap_basis'] or '설명 없음'})",
                f"  구조 저항 거리: {_num(row['structural_target_distance_pct'], '%')} "
                f"({row['structural_target_basis'] or '설명 없음'})",
                f"  분석 기준가 {_num(price['entry_reference_price'])} / "
                f"무효화 기준 {_num(price['invalidation_reference_price'])} / "
                f"1차 목표 {_num(price['target1_reference_price'])}",
                f"  참고 손익비 1차: {_num(price['target1_r_multiple'], 'R')} "
                f"· 구조 저항 기준: {_num(price['structural_r_multiple'], 'R')} "
                f"· {price['status']}",
                "  (과거 순위 변화가 아니라 같은 실행 내 정렬 전후 순위입니다.)",
                "",
            ])
    out.extend([
        f"원본 해시: {report['original_payload_hash']}",
        "자료 성격: 사후/연구용 설명만 가능. Q7 승인·실제 수익·독립 예측 시점 증명 아님.",
    ])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S28 explain a frozen research Scanner result (no writes)",
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = load_file_readonly(args.file)
    except (ResearchCaptureError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "version": "Q7_S28_FROZEN_RANK_EVIDENCE_DIAGNOSTIC_V1",
            "status": "HOLD",
            "reason_code": getattr(exc, "code", type(exc).__name__),
            "network_requests": 0, "runtime_db_writes": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(korean_summary(report))
    return 0 if report["status"] == "DESCRIPTIVE_DIAGNOSTIC_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
