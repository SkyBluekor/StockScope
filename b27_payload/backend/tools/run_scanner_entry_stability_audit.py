from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner_quality.entry_stability_audit import load_snapshot, run_audit, write_outputs

DEFAULT_INPUT = BACKEND_ROOT / "tools" / "audit_inputs" / "b27_entry_stability_development_53d.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.7-A/B Entry Stability discovery audit")
    parser.add_argument("--market-store", type=Path, default=None)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshot = load_snapshot(args.input)
    except (OSError, ValueError) as exc:
        print(f"B.2.7-A/B input error: {exc}")
        return 2

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    source = snapshot.get("source") or {}
    print(
        "B.2.7-A/B Entry Stability discovery: "
        f"dates={source.get('development_dates')} candidates={source.get('ready_candidates')} "
        f"source_scanner={source.get('scanner_version')}"
    )

    def progress(index: int, total: int, day: str, candidates: int, missing_history: int) -> None:
        print(
            f"[{index:>2}/{total}] {day} candidates={candidates} missing_history={missing_history}",
            flush=True,
        )

    try:
        payload = run_audit(snapshot, store, progress=progress)
    except Exception as exc:
        print(f"B.2.7-A/B failed: {type(exc).__name__}: {exc}")
        return 2

    paths = write_outputs(payload, args.output_dir)
    smoke = payload.get("development_top3_smoke") or {}
    current = smoke.get("CURRENT") or {}
    rules = payload.get("rule_candidates") or []
    best = rules[0] if rules else None
    best_metrics = smoke.get(str((best or {}).get("rule_id"))) or {}
    print(
        f"B.2.7-A/B: {payload.get('verdict')} | "
        f"best={(best or {}).get('rule_id')} | "
        f"Top3 T1 {current.get('target1_first_20d_rate')} -> {best_metrics.get('target1_first_20d_rate')} | "
        f"Stop {current.get('stop_first_20d_rate')} -> {best_metrics.get('stop_first_20d_rate')} | "
        "production_changed=False"
    )
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
