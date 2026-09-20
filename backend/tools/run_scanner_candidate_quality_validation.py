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
from app.backtest.scanner_quality.candidate_quality_validation import (
    EXPECTED_SCANNER_VERSION,
    OfflineAuditKrx,
    ensure_scanner_version,
    run_validation,
    write_outputs,
)

DEFAULT_DATES = BACKEND_ROOT / "tools" / "audit_inputs" / "b26c_validation_dates.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.6-C current-version overextension validation")
    parser.add_argument("--market-store", type=Path, default=None)
    parser.add_argument("--market-scope", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--evaluation-dates-file", type=Path, default=DEFAULT_DATES)
    parser.add_argument("--min-required-dates", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "candidate_quality_validation",
    )
    return parser.parse_args()


def load_dates(path: Path) -> list[date]:
    raw = path.read_text(encoding="utf-8-sig")
    result: list[date] = []
    for raw_line in raw.splitlines():
        # Remove comments before comma expansion. Otherwise a comment such as
        # "# dates, held fixed" is split into a non-comment token and parsed as a date.
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        for token in line.split(","):
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
        print(f"B.2.6-C date input error: {exc}")
        return 2
    if len(dates) < int(args.min_required_dates):
        print(f"B.2.6-C requires at least {args.min_required_dates} dates; got {len(dates)}")
        return 2

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        ensure_scanner_version(getattr(scanner, "VERSION", None))
    except RuntimeError as exc:
        print(str(exc))
        return 2

    print(
        f"B.2.6-C current-version validation: Scanner={scanner.VERSION} "
        f"(expected {EXPECTED_SCANNER_VERSION}), dates={len(dates)}, "
        f"range={dates[0].isoformat()}..{dates[-1].isoformat()}"
    )

    def progress(index: int, total: int, result: dict) -> None:
        meta = result.get("guard_meta") or {}
        print(
            f"[{index:>2}/{total}] {result.get('analysis_date')} {result.get('status')} "
            f"candidates={result.get('candidate_count', 0)} "
            f"ready={meta.get('ready_count', 0)} overext={meta.get('overextended_count', 0)}",
            flush=True,
        )

    try:
        payload = run_validation(
            scanner,
            store,
            evaluation_dates=dates,
            market_scope=args.market_scope,
            progress=progress,
        )
    except Exception as exc:  # integration failures should be visible, not hidden
        print(f"B.2.6-C validation failed: {type(exc).__name__}: {exc}")
        return 2

    if int(payload.get("valid_date_count") or 0) < int(args.min_required_dates):
        print(
            f"B.2.6-C incomplete: valid dates={payload.get('valid_date_count')} "
            f"required={args.min_required_dates}; missing={payload.get('missing_dates')}"
        )
        return 2

    paths = write_outputs(payload, args.output_dir)
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    current = top3.get("CURRENT") or {}
    guard = top3.get("OVEREXTENSION_Q75_GUARD") or {}
    print(
        f"B.2.6-C: {payload.get('verdict')} | "
        f"Top3 20D {current.get('return_20d_mean')} -> {guard.get('return_20d_mean')} | "
        f"MAE {current.get('mae_20d_mean')} -> {guard.get('mae_20d_mean')} | "
        f"production_changed=False"
    )
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
