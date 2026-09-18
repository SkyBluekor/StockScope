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
from app.backtest.scanner_quality.early_pruning_audit import add_audit_metadata, discover_temporal_evaluation_dates
from app.backtest.scanner_quality.models import AuditHorizons
from app.backtest.scanner_quality.prepool_strategy_audit import (
    PrepoolStrategyAuditor,
    compact_prepool_payload,
    write_prepool_outputs,
)


class OfflineAuditKrx:
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

    async def stock_daily(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("Pre-pool strategy audit is offline-only; KRX network access is disabled.")

    async def index_daily(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("Pre-pool strategy audit is offline-only; KRX network access is disabled.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Scanner pre-pool Top3-vs-All strategy audit")
    parser.add_argument("--market-store", type=Path, default=None, help="market_history.db path")
    parser.add_argument("--market-scope", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--dates", default="", help="comma-separated YYYY-MM-DD dates")
    parser.add_argument("--sample-size", type=int, default=80)
    parser.add_argument("--min-date-gap", type=int, default=3)
    parser.add_argument("--min-required-dates", type=int, default=60)
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT / "runtime" / "quality_audit" / "prepool_strategy")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    auditor = PrepoolStrategyAuditor(scanner, store)

    if args.dates.strip():
        dates = [date.fromisoformat(value.strip()) for value in args.dates.split(",") if value.strip()]
        sampling = {
            "source": "explicit_dates",
            "requested_sample_size": len(dates),
            "selected_sample_size": len(dates),
            "requested_min_date_gap": None,
            "effective_min_date_gap": None,
            "first_selected_date": dates[0].isoformat() if dates else None,
            "last_selected_date": dates[-1].isoformat() if dates else None,
        }
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
        f"Scanner pre-pool strategy audit: dates={len(dates)}, "
        f"range={dates[0].isoformat()}..{dates[-1].isoformat()}, "
        f"market={scanner.QUICK_LIMIT_PER_MARKET}, quick={scanner.DEEP_LIMIT}"
    )
    print(
        "Temporal sampling: "
        f"requested={sampling.get('requested_sample_size')}, selected={sampling.get('selected_sample_size')}, "
        f"gap={sampling.get('requested_min_date_gap')}->{sampling.get('effective_min_date_gap')}"
    )

    def report_progress(index: int, total: int, as_of: date, run: dict) -> None:
        print(
            f"[{index:>3}/{total}] {as_of.isoformat()} {run.get('status')} "
            f"poolΔ={run.get('quick_pool_replacement_count', 0)} "
            f"rescued={run.get('rescued_candidate_count', 0)} "
            f"{run.get('runtime_seconds')}s",
            flush=True,
        )

    payload = auditor.run_dates(
        dates=dates,
        market_scope=args.market_scope,
        horizons=AuditHorizons((5, 10, 20)),
        market_limit=int(scanner.QUICK_LIMIT_PER_MARKET),
        quick_limit=int(scanner.DEEP_LIMIT),
        progress_callback=report_progress,
    )
    payload["sampling"] = sampling
    payload = compact_prepool_payload(payload)
    payload = add_audit_metadata(payload, market_store=store, project_root=BACKEND_ROOT.parent)
    paths = write_prepool_outputs(payload, output_dir=args.output_dir)

    validation = payload.get("prepool_strategy_validation") or {}
    print(f"Audit complete: {payload.get('valid_date_count')} valid dates")
    print(
        f"Quick18 changes: {validation.get('quick_pool_changed_date_count')} dates "
        f"({validation.get('quick_pool_changed_rate_pct')}%), "
        f"rescued={validation.get('rescued_candidate_count')}, "
        f"rescuedTop5={validation.get('rescued_top5_count')}, "
        f"verdict={validation.get('verdict')}"
    )
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
