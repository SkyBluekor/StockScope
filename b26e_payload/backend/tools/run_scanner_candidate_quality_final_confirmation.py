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
from app.backtest.scanner_quality.candidate_quality_final_confirmation import (
    EXPECTED_SCANNER_VERSION,
    FROZEN_REFINED,
    MIN_TRADING_DAY_GAP_FROM_USED,
    VERDICT_INSUFFICIENT,
    build_common_trading_calendar,
    ensure_frozen_rule,
    run_final_confirmation,
    select_holdout_from_calendar,
    used_dates_from_baseline,
    validate_d_source,
    write_outputs,
)
from app.backtest.scanner_quality.candidate_quality_validation import OfflineAuditKrx, ensure_scanner_version

DEFAULT_BASELINE = BACKEND_ROOT / "tools" / "audit_inputs" / "b26_candidate_quality_baseline_75d.json"
DEFAULT_HOLDOUT = BACKEND_ROOT / "tools" / "audit_inputs" / "b26e_holdout_dates.txt"
DEFAULT_D_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "overextension_context"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "runtime" / "quality_audit" / "candidate_quality_final"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope B.2.6-E frozen refined guard final confirmation")
    parser.add_argument("--market-store", type=Path, default=None)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--min-required-dates", type=int, default=20)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--holdout-file", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--d-result", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest_d_result() -> Path | None:
    if not DEFAULT_D_DIR.exists():
        return None
    files = sorted(DEFAULT_D_DIR.glob("scanner-overextension-context_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


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
        "# B.2.6-E frozen independent holdout. Do not hand-tune these dates after outcomes are seen.",
        "# Existing B.2.6-A/B/C evaluation dates are excluded with a >=3 trading-day gap.",
        *[day.isoformat() for day in dates],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        ensure_frozen_rule()
        baseline = _load_json(args.baseline)
        used_dates = used_dates_from_baseline(baseline)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"B.2.6-E baseline/rule error: {exc}")
        return 2

    d_path = args.d_result or _latest_d_result()
    if d_path is None or not d_path.exists():
        print("B.2.6-E requires the B.2.6-D result JSON. Run B.2.6-D first or pass --d-result.")
        return 2
    try:
        d_source = validate_d_source(_load_json(d_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"B.2.6-E D-source error: {exc}")
        return 2

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        ensure_scanner_version(getattr(scanner, "VERSION", None))
    except RuntimeError as exc:
        print(str(exc))
        return 2

    try:
        existing = load_holdout_dates(args.holdout_file)
        if len(existing) > int(args.sample_size):
            raise ValueError(
                f"holdout file has {len(existing)} dates but --sample-size={args.sample_size}; "
                "do not silently drop frozen holdout dates"
            )
        if len(existing) < int(args.sample_size):
            print(
                f"B.2.6-E selecting frozen holdout from local market store: "
                f"existing={len(existing)} target={args.sample_size} min_gap={MIN_TRADING_DAY_GAP_FROM_USED}",
                flush=True,
            )
            calendar = build_common_trading_calendar(store)
            dates = select_holdout_from_calendar(
                calendar,
                used_dates,
                sample_size=int(args.sample_size),
                existing_dates=existing,
                min_gap=MIN_TRADING_DAY_GAP_FROM_USED,
            )
            write_holdout_dates(args.holdout_file, dates)
        else:
            calendar = build_common_trading_calendar(store)
            dates = select_holdout_from_calendar(
                calendar,
                used_dates,
                sample_size=int(args.sample_size),
                existing_dates=existing,
                min_gap=MIN_TRADING_DAY_GAP_FROM_USED,
            )
    except (OSError, ValueError) as exc:
        print(f"B.2.6-E holdout selection error: {exc}")
        return 2

    print(
        f"B.2.6-E frozen confirmation: Scanner={scanner.VERSION} (expected {EXPECTED_SCANNER_VERSION}), "
        f"dates={len(dates)}, range={dates[0].isoformat()}..{dates[-1].isoformat()}, overlap=0",
        flush=True,
    )

    def progress(index: int, total: int, result: dict) -> None:
        meta = result.get("guard_meta") or {}
        print(
            f"[{index:>2}/{total}] {result.get('analysis_date')} {result.get('status')} "
            f"candidates={result.get('candidate_count', 0)} ready={meta.get('ready_count', 0)} "
            f"overext={meta.get('overextended_count', 0)} exempt={meta.get('refined_exception_used', 0)}",
            flush=True,
        )

    try:
        payload = run_final_confirmation(
            scanner,
            store,
            evaluation_dates=dates,
            used_dates=used_dates,
            market_scope="ALL",
            progress=progress,
            frozen_rule_source=d_source,
        )
    except Exception as exc:
        print(f"B.2.6-E confirmation failed: {type(exc).__name__}: {exc}")
        return 2

    valid_count = int((payload.get("holdout") or {}).get("valid_date_count") or 0)
    if valid_count < int(args.min_required_dates):
        print(
            f"B.2.6-E incomplete: valid dates={valid_count}, required={args.min_required_dates}, "
            f"missing={(payload.get('holdout') or {}).get('missing_dates')}"
        )
        return 2

    paths = write_outputs(payload, args.output_dir)
    top3 = (payload.get("comparisons") or {}).get("top3") or {}
    cur = top3.get("CURRENT") or {}
    refined = top3.get(FROZEN_REFINED) or {}
    impact = payload.get("ranking_impact") or {}
    print(
        f"B.2.6-E: {payload.get('verdict')} | "
        f"Top3 20D {cur.get('return_20d_mean')} -> {refined.get('return_20d_mean')} | "
        f"MAE {cur.get('mae_20d_mean')} -> {refined.get('mae_20d_mean')} | "
        f"T1 {cur.get('target1_first_20d_rate')} -> {refined.get('target1_first_20d_rate')} | "
        f"Stop {cur.get('stop_first_20d_rate')} -> {refined.get('stop_first_20d_rate')} | "
        f"overext={impact.get('overextended_candidates')} exempt={impact.get('refined_exception_opportunities')} | "
        "production_changed=False"
    )
    if payload.get("verdict") == VERDICT_INSUFFICIENT:
        print("Sample guardrail not met. Re-run with --sample-size 30 to extend the frozen holdout by 10 dates.")
    print(f"holdout file: {args.holdout_file}")
    print(f"json: {paths['json']}")
    print(f"csv: {paths['csv']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
