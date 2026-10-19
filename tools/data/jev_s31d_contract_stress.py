"""S31-D local synthetic S3 adapter stress. No CLI mode makes network calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for location in (ROOT, BACKEND):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from app.jev.s31d_scanner_contract_stress import run_s31d_contract_stress, VERSION


def korean_report(report: dict) -> str:
    lines = [
        "StockScope JEV S31-D · 기존 Scanner 검토 계약 합성 스트레스",
        f"상태: {report['status']}",
        f"실제 S3 검토 계약 일치: {report['contract_expectations_met']}/{report['scenario_count']}",
        "※ 실제 Scanner 전체 실행이나 JEV 모델 호출이 아닙니다.",
        "",
    ]
    for case in report["cases"]:
        lines.append(
            f"· {case['scenario']}: 예상 {case['expected_s3_contract_result']} "
            f"/ 실제 {case['observed_s3_contract_result']} "
            f"({'PASS' if case['contract_expectation_match'] else 'FAIL'})"
        )
    lines.extend([
        "",
        "관찰: S3 계약에서는 Risk BLOCK은 제외하지만, warning=True는 검토 가능 상태로 남습니다.",
        "※ 경고가 있는 종목의 진입을 허가한다는 뜻은 아닙니다.",
        "이 실험에서 확인할 수 없는 항목:",
        *(f"  - {value}" for value in report["unmeasured"]),
        "JEV 실제 호출 0회 · 데이터 전송 0건 · 운영 DB 변경 0건 · 주문 0건",
        "S6 실제 JEV 결과와 입력 사례가 다르므로 성능 점수를 결합하지 않습니다.",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S31-D isolated synthetic contract stress")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_s31d_contract_stress()
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({
            "version": VERSION, "status": "HOLD_FIXTURE_INVALID",
            "reason_code": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "new_jev_provider_calls": 0, "production_db_writes": 0,
        }, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.json else korean_report(report)
    )
    return 0 if report["status"] == "SYNTHETIC_S3_CONTRACT_STRESS_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
