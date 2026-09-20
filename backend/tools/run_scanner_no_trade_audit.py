from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
BUNDLED_BASELINE = (
    BACKEND_ROOT
    / "runtime"
    / "quality_audit"
    / "no_trade"
    / "source"
    / "scanner-strategy-audit_b25d-baseline-80d.json"
)
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.no_trade_audit import audit_history_payload, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Scanner NO_TRADE / weak-market sanity audit")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="scanner-strategy-audit JSON path; omitted = newest local audit, otherwise bundled 80D baseline",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "no_trade",
    )
    return parser.parse_args()


def local_history_audits() -> list[Path]:
    roots = [
        BACKEND_ROOT / "runtime",
        PROJECT_ROOT / "runtime",
        PROJECT_ROOT,
    ]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("scanner-strategy-audit_*.json"):
            if not path.is_file():
                continue
            # The bundled snapshot is fallback evidence, not a local/current audit.
            if path.name == BUNDLED_BASELINE.name or "b25d-baseline" in path.name:
                continue
            try:
                key = str(path.resolve()).lower()
            except OSError:
                key = str(path).lower()
            found[key] = path
    return list(found.values())


def resolve_source(explicit: Path | None) -> tuple[Path | None, str]:
    if explicit is not None:
        return explicit, "EXPLICIT_INPUT"

    local = local_history_audits()
    if local:
        return max(local, key=lambda path: path.stat().st_mtime), "LOCAL_HISTORY"

    if BUNDLED_BASELINE.exists():
        return BUNDLED_BASELINE, "BUNDLED_BASELINE_80D"

    return None, "MISSING"


def main() -> int:
    args = parse_args()
    source, source_mode = resolve_source(args.input)
    if source is None:
        print("strategy audit JSON과 B.2.5-D baseline snapshot을 모두 찾지 못했습니다.")
        return 2
    if not source.exists():
        print(f"입력 파일이 없습니다: {source}")
        return 2

    payload = json.loads(source.read_text(encoding="utf-8"))
    report = audit_history_payload(payload)
    report["source_mode"] = source_mode
    paths = write_report(report, output_dir=args.output_dir, source_name=source.name)
    summary = report.get("summary") or {}

    print(f"source_mode={source_mode}")
    print(f"source={source}")
    if source_mode == "BUNDLED_BASELINE_80D":
        print("note=로컬 strategy audit가 없어 B.2.5-D에 포함된 경량 80D baseline snapshot으로 검사했습니다.")
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
