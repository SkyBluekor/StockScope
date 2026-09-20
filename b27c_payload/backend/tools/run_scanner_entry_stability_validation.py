from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.backtest.scanner_quality.entry_stability_validation import (
    EXPECTED_SCANNER_VERSION,
    OfflineAuditKrx,
    RULE_ORDER,
    ensure_scanner_version,
    run_validation,
    write_outputs,
)

DEFAULT_DATES = BACKEND_ROOT / "tools" / "audit_inputs" / "b27c_validation_dates.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.7-C current-version Entry Stability validation")
    parser.add_argument("--market-store", type=Path, default=None)
    parser.add_argument("--market-scope", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--evaluation-dates-file", type=Path, default=DEFAULT_DATES)
    parser.add_argument("--min-required-dates", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability_validation",
    )
    return parser.parse_args()


def load_dates(path: Path) -> list[date]:
    raw = path.read_text(encoding="utf-8-sig")
    # Strip comments before splitting commas so prose comments cannot become date tokens.
    lines = [line.split("#", 1)[0] for line in raw.splitlines()]
    result: list[date] = []
    for token in "\n".join(lines).replace(",", "\n").splitlines():
        value = token.strip()
        if value:
            result.append(date.fromisoformat(value))
    if len(result) != len(set(result)):
        raise ValueError("evaluation dates contain duplicates")
    return result


def main() -> int:
    args = parse_args()
    try:
        dates = load_dates(args.evaluation_dates_file)
    except (OSError, ValueError) as exc:
        print(f"B.2.7-C date input error: {exc}")
        return 2
    if len(dates) < int(args.min_required_dates):
        print(f"B.2.7-C requires at least {args.min_required_dates} dates; got {len(dates)}")
        return 2

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        ensure_scanner_version(getattr(scanner, "VERSION", None))
    except RuntimeError as exc:
        print(str(exc))
        return 2

    print(
        f"B.2.7-C Entry Stability validation: Scanner={scanner.VERSION} "
        f"(expected {EXPECTED_SCANNER_VERSION}), dates={len(dates)}, "
        f"range={dates[0].isoformat()}..{dates[-1].isoformat()}"
    )

    def progress(index: int, total: int, result: dict) -> None:
        meta = result.get("rule_meta") or {}
        summary = " ".join(f"{rule}={((meta.get(rule) or {}).get('unstable_count', 0))}" for rule in RULE_ORDER)
        print(
            f"[{index:>2}/{total}] {result.get('analysis_date')} {result.get('status')} "
            f"candidates={result.get('candidate_count', 0)} {summary}",
            flush=True,
        )

    try:
        payload = run_validation(scanner, store, evaluation_dates=dates, market_scope=args.market_scope, progress=progress)
    except Exception as exc:
        print(f"B.2.7-C validation failed: {type(exc).__name__}: {exc}")
        return 2

    if int(payload.get("valid_date_count") or 0) < int(args.min_required_dates):
        print(
            f"B.2.7-C incomplete: valid dates={payload.get('valid_date_count')} "
            f"required={args.min_required_dates}; missing={payload.get('missing_dates')}"
        )
        return 2

    paths = write_outputs(payload, args.output_dir)
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    current = top3.get("CURRENT") or {}
    print(f"B.2.7-C: {payload.get('verdict')} | Production changed=False")
    print(
        f"CURRENT Top3 T1={current.get('target1_first_20d_rate')} "
        f"Stop={current.get('stop_first_20d_rate')}"
    )
    for rule in RULE_ORDER:
        metrics = top3.get(rule) or {}
        decision = ((payload.get("rule_verdicts") or {}).get(rule) or {}).get("verdict")
        print(
            f"{rule}: {decision} | T1={metrics.get('target1_first_20d_rate')} "
            f"Stop={metrics.get('stop_first_20d_rate')} | 20D={metrics.get('return_20d_mean')} "
            f"MAE={metrics.get('mae_20d_mean')}"
        )
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
