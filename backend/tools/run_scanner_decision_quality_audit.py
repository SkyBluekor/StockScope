from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.decision_quality_audit import audit_repro_payload, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Scanner decision-quality smoke audit")
    parser.add_argument("--input", type=Path, default=None, help="scanner-repro JSON path; default = latest in project/scanner-repro")
    parser.add_argument("--top", type=int, default=5, help="Top N candidates to inspect")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "decision_quality",
    )
    return parser.parse_args()


def latest_repro(root: Path) -> Path | None:
    candidates = sorted(root.glob("scanner-repro_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def main() -> int:
    args = parse_args()
    source = args.input or latest_repro(PROJECT_ROOT / "scanner-repro")
    if source is None:
        print("scanner-repro JSON을 찾지 못했습니다. Scanner에서 '다시 분석'을 한 번 실행한 뒤 다시 시도하세요.")
        return 2
    if not source.exists():
        print(f"입력 파일이 없습니다: {source}")
        return 2

    payload = json.loads(source.read_text(encoding="utf-8"))
    report = audit_repro_payload(payload, top_n=max(1, args.top))
    paths = write_report(report, output_dir=args.output_dir, source_name=source.name)

    summary = report.get("summary") or {}
    print(
        f"Decision quality audit: {report.get('verdict')} | "
        f"analysis={((report.get('source') or {}).get('analysis_date'))} | "
        f"Top {report.get('top_n')} | errors={summary.get('error_count')} reviews={summary.get('review_count')}"
    )
    print(f"ranking_order_consistent={summary.get('ranking_order_consistent')}")
    print(f"strategy_trace_available={summary.get('strategy_trace_available_count')}/{report.get('top_n')}")
    for issue in report.get("issues") or []:
        print(
            f"[{issue.get('severity')}] {issue.get('kind')} "
            f"rank={issue.get('rank')} code={issue.get('code')} :: {issue.get('message')}"
        )
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 1 if report.get("verdict") == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
