from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.overextension_context_audit import (
    REFINED_GUARD,
    run_context_audit,
    write_outputs,
)

DEFAULT_DEVELOPMENT = BACKEND_ROOT / "tools" / "audit_inputs" / "b26_candidate_quality_baseline_75d.json"
DEFAULT_CURRENT_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "candidate_quality_validation"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "overextension_context"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.6-D overextension risk/momentum split audit")
    parser.add_argument("--development", type=Path, default=DEFAULT_DEVELOPMENT)
    parser.add_argument("--current-validation", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def _latest_current_validation() -> Path | None:
    if not DEFAULT_CURRENT_DIR.exists():
        return None
    files = sorted(DEFAULT_CURRENT_DIR.glob("scanner-candidate-quality-validation_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    args = parse_args()
    current_path = args.current_validation or _latest_current_validation()
    if current_path is None:
        print(
            "B.2.6-D current validation JSON을 찾지 못했습니다. "
            "먼저 B.2.6-C를 실행하거나 --current-validation으로 JSON 경로를 지정하세요."
        )
        return 2
    if not args.development.exists():
        print(f"B.2.6-D development baseline not found: {args.development}")
        return 2
    if not current_path.exists():
        print(f"B.2.6-D current validation not found: {current_path}")
        return 2

    try:
        development = _load_json(args.development)
        current = _load_json(current_path)
        payload = run_context_audit(development, current)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"B.2.6-D input error: {exc}")
        return 2

    paths = write_outputs(payload, args.output_dir)
    top3 = (payload.get("current_validation") or {}).get("top3") or {}
    cur = top3.get("CURRENT") or {}
    refined = top3.get(REFINED_GUARD) or {}
    print(
        f"B.2.6-D: {payload.get('verdict')} | "
        f"Top3 20D {cur.get('return_20d_mean')} -> {refined.get('return_20d_mean')} | "
        f"T1 {cur.get('target1_first_20d_rate')} -> {refined.get('target1_first_20d_rate')} | "
        f"Stop {cur.get('stop_first_20d_rate')} -> {refined.get('stop_first_20d_rate')} | "
        "production_changed=False"
    )
    print(f"current source: {current_path}")
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
