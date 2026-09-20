from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.no_trade_audit import audit_history_payload, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Scanner NO_TRADE / weak-market sanity audit")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="scanner-strategy-audit JSON path; default = newest matching file under backend/runtime or project root",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "no_trade",
    )
    return parser.parse_args()


def latest_history_audit() -> Path | None:
    roots = [BACKEND_ROOT / "runtime", PROJECT_ROOT]
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        found.extend(root.rglob("scanner-strategy-audit_*.json"))
    found = [path for path in found if path.is_file()]
    return max(found, key=lambda path: path.stat().st_mtime) if found else None


def main() -> int:
    args = parse_args()
    source = args.input or latest_history_audit()
    if source is None:
        print("scanner-strategy-audit JSON을 찾지 못했습니다. --input으로 기존 strategy audit JSON을 지정하세요.")
        return 2
    if not source.exists():
        print(f"입력 파일이 없습니다: {source}")
        return 2

    payload = json.loads(source.read_text(encoding="utf-8"))
    report = audit_history_payload(payload)
    paths = write_report(report, output_dir=args.output_dir, source_name=source.name)
    summary = report.get("summary") or {}
    print(
        f"NO_TRADE audit: {report.get('verdict')} | dates={summary.get('checked_dates')} "
        f"candidates={summary.get('checked_candidates')} READY=0 dates={summary.get('no_ready_date_count')} "
        f"errors={summary.get('error_count')} reviews={summary.get('review_count')}"
    )
    for sample in report.get("representative_samples") or []:
        print(
            f"sample {sample.get('sample_kind')}: {sample.get('analysis_date')} | "
            f"READY={sample.get('ready_count')} WATCH={sample.get('watch_count')} "
            f"ENTRY={sample.get('entry_count')} WAIT={sample.get('wait_count')} "
            f"bad_risk={sample.get('bad_risk_count')}"
        )
    for issue in report.get("issues") or []:
        print(
            f"[{issue.get('severity')}] {issue.get('kind')} {issue.get('analysis_date')} "
            f"{issue.get('code')} :: {issue.get('message')}"
        )
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 1 if report.get("verdict") == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
