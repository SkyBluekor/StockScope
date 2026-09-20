from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner_quality.candidate_quality_audit import run_candidate_quality_audit, write_outputs

DEFAULT_BASELINE = BACKEND_ROOT / "tools" / "audit_inputs" / "b26_candidate_quality_baseline_75d.json"
DEFAULT_CAP = BACKEND_ROOT / "tools" / "audit_inputs" / "b26_target1_cap_validation_20d.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.6 candidate-quality research audit")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--cap-validation", type=Path, default=DEFAULT_CAP)
    parser.add_argument("--validation-dates", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "candidate_quality",
    )
    return parser.parse_args()


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    args = parse_args()
    try:
        baseline = _load(args.baseline)
        cap = _load(args.cap_validation) if args.cap_validation else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Candidate-quality audit input error: {exc}")
        return 2

    payload = run_candidate_quality_audit(
        baseline,
        cap,
        validation_dates=max(1, int(args.validation_dates)),
    )
    paths = write_outputs(payload, args.output_dir)

    split = payload.get("split") or {}
    stability = payload.get("stability") or {}
    print(
        f"Candidate quality audit: {payload.get('verdict')} | "
        f"dev={split.get('development_dates')} val={split.get('validation_dates')} | "
        f"overext Top3 wins={stability.get('overextension_guard_top3_return20_improved_blocks')}/"
        f"{stability.get('block_count')} blocks | production_changed=False"
    )
    print(f"json: {paths['json']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
