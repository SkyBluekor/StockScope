from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.backtest.scanner_quality.entry_stability_validation import OfflineAuditKrx
from app.backtest.scanner_quality.entry_stability_volume_holdout import (
    EXPECTED_SCANNER_VERSION,
    MIN_REQUIRED_DATES,
    MIN_TRADING_DAY_GAP,
    RULE_ID,
    VERDICT_PROMOTE,
    build_common_trading_calendar,
    ensure_frozen_rule,
    ensure_scanner_version,
    run_holdout,
    select_fresh_holdout,
    validate_d_source,
    write_outputs,
)

DEFAULT_EXCLUSIONS = BACKEND_ROOT / "tools" / "audit_inputs" / "b27e_excluded_dates.json"
DEFAULT_D_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability_volume_robustness"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "entry_stability_volume_holdout"
DEFAULT_HOLDOUT_FILE = DEFAULT_OUTPUT_DIR / "b27e_frozen_holdout_dates.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.7-E frozen Volume-Low fresh independent holdout")
    parser.add_argument("--market-store", type=Path, default=None)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--min-required-dates", type=int, default=MIN_REQUIRED_DATES)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    parser.add_argument("--d-result", type=Path, default=None)
    parser.add_argument("--holdout-file", type=Path, default=DEFAULT_HOLDOUT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest_d_result() -> Path | None:
    if not DEFAULT_D_DIR.exists():
        return None
    files = sorted(DEFAULT_D_DIR.glob("scanner-entry-stability-volume-robustness_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def load_exclusions(path: Path) -> tuple[set[date], dict]:
    payload = _load_json(path)
    dates = {date.fromisoformat(str(value)) for value in (payload.get("excluded_dates") or [])}
    if len(dates) < 93:
        raise ValueError(f"B.2.7-E exclusion manifest expected >=93 unique prior dates, got {len(dates)}")
    return dates, payload


def load_holdout_dates(path: Path) -> list[date]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8-sig")
    result: list[date] = []
    for line in raw.splitlines():
        content = line.split("#", 1)[0]
        for token in content.split(","):
            value = token.strip()
            if value:
                result.append(date.fromisoformat(value))
    if len(result) != len(set(result)):
        raise ValueError("holdout dates contain duplicates")
    return result


def write_holdout_dates(path: Path, dates: list[date]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# B.2.7-E frozen fresh holdout. Do not edit after outcomes are observed.",
        "# Excludes B.2.7 73 dates + B.2.6-E 20 holdout dates, with >=3 common trading-session gap.",
        *[day.isoformat() for day in dates],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        ensure_frozen_rule()
        excluded_dates, exclusion_meta = load_exclusions(args.exclusions)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"B.2.7-E frozen rule/exclusion error: {exc}")
        return 2

    d_path = args.d_result or _latest_d_result()
    if d_path is None or not d_path.exists():
        print("B.2.7-E requires the B.2.7-D result JSON. Run B.2.7-D first or pass --d-result.")
        return 2
    try:
        d_source = validate_d_source(_load_json(d_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"B.2.7-E D-source error: {exc}")
        return 2

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        ensure_scanner_version(getattr(scanner, "VERSION", None))
    except RuntimeError as exc:
        print(str(exc))
        return 2

    try:
        calendar = build_common_trading_calendar(store)
        existing = load_holdout_dates(args.holdout_file)
        if len(existing) > int(args.sample_size):
            raise ValueError(
                f"holdout file has {len(existing)} dates but --sample-size={args.sample_size}; do not silently drop frozen dates"
            )
        dates = select_fresh_holdout(
            calendar,
            excluded_dates,
            sample_size=int(args.sample_size),
            existing_dates=existing,
            min_gap=MIN_TRADING_DAY_GAP,
        )
        if len(existing) < len(dates):
            write_holdout_dates(args.holdout_file, dates)
    except (OSError, ValueError) as exc:
        print(f"B.2.7-E holdout selection error: {exc}")
        return 2

    print(
        f"B.2.7-E frozen fresh holdout: Scanner={scanner.VERSION} (expected {EXPECTED_SCANNER_VERSION}), "
        f"dates={len(dates)}, range={dates[0].isoformat()}..{dates[-1].isoformat()}, "
        f"excluded={len(excluded_dates)}, overlap=0",
        flush=True,
    )
    print(
        "Exclusion manifest: "
        f"B27dev={((exclusion_meta.get('counts') or {}).get('b27_development'))} "
        f"B27val={((exclusion_meta.get('counts') or {}).get('b27_current_validation'))} "
        f"B26E={((exclusion_meta.get('counts') or {}).get('b26e_final_holdout'))}",
        flush=True,
    )

    def progress(index: int, total: int, result: dict) -> None:
        meta = result.get("frozen_rule_meta") or {}
        print(
            f"[{index:>2}/{total}] {result.get('analysis_date')} {result.get('status')} "
            f"candidates={result.get('candidate_count', 0)} ready={meta.get('ready_count', 0)} "
            f"low={meta.get('unstable_count', 0)} freeze={str(result.get('ranking_freeze_hash') or '')[:10]}",
            flush=True,
        )

    try:
        payload = run_holdout(
            scanner,
            store,
            evaluation_dates=dates,
            excluded_dates=excluded_dates,
            d_source=d_source,
            market_scope="ALL",
            progress=progress,
        )
    except Exception as exc:
        print(f"B.2.7-E holdout failed: {type(exc).__name__}: {exc}")
        return 2

    valid = int((payload.get("holdout") or {}).get("valid_date_count") or 0)
    if valid < int(args.min_required_dates):
        print(
            f"B.2.7-E incomplete: valid dates={valid}, required={args.min_required_dates}, "
            f"missing={(payload.get('holdout') or {}).get('missing_dates')}"
        )
        return 2

    paths = write_outputs(payload, args.output_dir)
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    current, guard = top3.get("CURRENT") or {}, top3.get(RULE_ID) or {}
    outcomes = payload.get("date_outcomes") or {}
    swaps = payload.get("swaps") or {}
    print(f"B.2.7-E: {payload.get('verdict')} | Production changed=False")
    print(
        f"Top3 T1 {current.get('target1_first_20d_rate')} -> {guard.get('target1_first_20d_rate')} | "
        f"Stop {current.get('stop_first_20d_rate')} -> {guard.get('stop_first_20d_rate')} | "
        f"EventR {current.get('event_r_20d_mean')} -> {guard.get('event_r_20d_mean')}"
    )
    print(
        f"20D {current.get('return_20d_mean')} -> {guard.get('return_20d_mean')} | "
        f"MAE {current.get('mae_20d_mean')} -> {guard.get('mae_20d_mean')} | "
        f"WIN/TIE/LOSS={outcomes.get('WIN',0)}/{outcomes.get('TIE',0)}/{outcomes.get('LOSS',0)} | "
        f"GOOD/BAD={swaps.get('GOOD_SWAP',0)}/{swaps.get('BAD_SWAP',0)}"
    )
    if payload.get("verdict") == VERDICT_PROMOTE:
        print("Frozen Volume-Low rule cleared the fresh holdout. Next: B.2.7-F Production integration.")
    else:
        print("Do not retune this holdout. B.2.7-F must not run unless the verdict is PROMOTE_VOLUME_LOW_GUARD.")
    print(f"holdout file: {args.holdout_file}")
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
