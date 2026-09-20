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
from app.backtest.scanner_quality import discover_temporal_evaluation_dates
from app.backtest.target1_realism_validation import Target1RealismAuditor, write_outputs


class OfflineAuditKrx:
    """Target1 audit is strictly local. Any attempted KRX download is a hard failure."""

    @staticmethod
    def _today_kst() -> date:
        return date.today()

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    @staticmethod
    def request_stats() -> dict[str, int]:
        return {"network_requests": 0}

    @staticmethod
    def budget_snapshot() -> dict[str, int]:
        return {"used": 0, "safe_limit": 0, "remaining": 0}

    async def stock_daily(self, *args, **kwargs):  # pragma: no cover - hard guard
        raise RuntimeError("Target1 realism audit is offline-only; KRX network access is disabled.")

    async def index_daily(self, *args, **kwargs):  # pragma: no cover - hard guard
        raise RuntimeError("Target1 realism audit is offline-only; KRX network access is disabled.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Target1 smoke-first realism audit")
    parser.add_argument("--market-store", type=Path, default=None, help="market_history.db path")
    parser.add_argument("--market-scope", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--dates", default="", help="comma-separated YYYY-MM-DD dates")
    parser.add_argument("--sample-size", type=int, default=20, help="default smoke run is 20 spread dates")
    parser.add_argument("--min-date-gap", type=int, default=3)
    parser.add_argument("--min-required-dates", type=int, default=10)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "target1_realism",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    auditor = Target1RealismAuditor(scanner, store)

    if args.dates.strip():
        dates = [date.fromisoformat(value.strip()) for value in args.dates.split(",") if value.strip()]
        sampling = {"source": "explicit_dates", "selected_sample_size": len(dates)}
    else:
        dates, sampling = discover_temporal_evaluation_dates(
            store,
            market_scope=args.market_scope,
            sample_size=max(1, int(args.sample_size)),
            min_date_gap=max(1, int(args.min_date_gap)),
            future_horizon_trading_days=20,
            min_required_dates=max(1, int(args.min_required_dates)),
        )

    if not dates:
        print("No complete local evaluation dates were found. Audit did not call KRX.")
        return 2

    print(
        f"Target1 realism smoke audit: dates={len(dates)}, "
        f"range={dates[0].isoformat()}..{dates[-1].isoformat()}, scope={args.market_scope}"
    )
    print(
        "Policies: CURRENT_STRUCTURAL vs CAP_1_5R vs FIXED_1_5R; "
        "Production Target1 is not modified."
    )

    def progress(index: int, total: int, as_of: date, run: dict) -> None:
        print(
            f"[{index:>2}/{total}] {as_of.isoformat()} {run.get('status')} "
            f"signals={run.get('signal_count', 0)} runtime={run.get('runtime_seconds')}s",
            flush=True,
        )

    payload = auditor.run_dates(
        dates=dates,
        market_scope=args.market_scope,
        horizons=(5, 10, 20),
        progress_callback=progress,
    )
    payload["sampling"] = sampling
    paths = write_outputs(payload, output_dir=args.output_dir)

    aggregate = payload.get("aggregate") or {}
    summary = aggregate.get("policy_summary") or {}
    print(f"Audit complete: {payload.get('valid_date_count')} valid dates, {aggregate.get('signal_count')} signals")
    for policy_id in ("CURRENT_STRUCTURAL", "CAP_1_5R", "FIXED_1_5R"):
        item = ((summary.get(policy_id) or {}).get("20") or {})
        print(
            f"{policy_id}: 20D target-first={item.get('target1_first_pct')}%, "
            f"stop-first={item.get('stop_first_pct')}%, n={item.get('complete_signals')}"
        )
    extreme = aggregate.get("extreme_20pct_or_4r") or {}
    extreme20 = extreme.get("current_20d") or {}
    print(
        "Extreme CURRENT (20%+ or 4R+): "
        f"n={extreme.get('sample_count')}, 20D target-first={extreme20.get('target1_first_pct')}%"
    )
    print(f"Smoke verdict={aggregate.get('smoke_verdict')} (review signal only)")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
