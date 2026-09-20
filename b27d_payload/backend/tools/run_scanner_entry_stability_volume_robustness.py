from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.entry_stability_volume_robustness import run_robustness, write_outputs


def _latest(directory: Path, pattern: str) -> Path | None:
    items = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return items[0] if items else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.7-D Volume signal robustness/aggressiveness audit")
    parser.add_argument("--development-json", type=Path, default=None)
    parser.add_argument("--validation-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability_volume_robustness")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dev = args.development_json or _latest(BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability", "scanner-entry-stability_*.json")
    val = args.validation_json or _latest(BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability_validation", "scanner-entry-stability-validation_*.json")
    if dev is None or not dev.exists():
        print("B.2.7-D missing B.2.7-A/B JSON. Run B.2.7-A/B first or pass --development-json.")
        return 2
    if val is None or not val.exists():
        print("B.2.7-D missing B.2.7-C JSON. Run B.2.7-C first or pass --validation-json.")
        return 2
    print(f"B.2.7-D development source: {dev}")
    print(f"B.2.7-D validation source:  {val}")
    try:
        development = json.loads(dev.read_text(encoding="utf-8-sig"))
        validation = json.loads(val.read_text(encoding="utf-8-sig"))
        payload = run_robustness(development, validation)
    except Exception as exc:
        print(f"B.2.7-D failed: {type(exc).__name__}: {exc}")
        return 2
    paths = write_outputs(payload, args.output_dir)
    d, v = payload["development"], payload["validation"]
    print(f"B.2.7-D: {payload['verdict']} | Production changed=False")
    print(f"Development T1 {d['current_top3']['target1_first_20d_rate']} -> {d['guard_top3']['target1_first_20d_rate']} | Stop {d['current_top3']['stop_first_20d_rate']} -> {d['guard_top3']['stop_first_20d_rate']} | EventR {d['current_top3']['event_r_20d_mean']} -> {d['guard_top3']['event_r_20d_mean']}")
    print(f"Validation  T1 {v['current_top3']['target1_first_20d_rate']} -> {v['guard_top3']['target1_first_20d_rate']} | Stop {v['current_top3']['stop_first_20d_rate']} -> {v['guard_top3']['stop_first_20d_rate']} | EventR {v['current_top3']['event_r_20d_mean']} -> {v['guard_top3']['event_r_20d_mean']}")
    print(f"Validation swaps GOOD/BAD={v['swaps'].get('GOOD_SWAP',0)}/{v['swaps'].get('BAD_SWAP',0)} | dates WIN/TIE/LOSS={v['date_outcomes'].get('WIN',0)}/{v['date_outcomes'].get('TIE',0)}/{v['date_outcomes'].get('LOSS',0)}")
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
