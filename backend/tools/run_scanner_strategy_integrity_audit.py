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
from app.backtest.scanner_quality.strategy_integrity_audit import (
    AUDIT_VERSION,
    RS_RESTORE_10_8,
    MA120_FIXED,
    RS_KEEP_4,
    RS_KEEP_8,
    StrategyIntegrityAuditor,
    compact_integrity_payload,
    write_integrity_outputs,
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
        raise RuntimeError("Strategy-integrity audit is offline-only; KRX network access is disabled.")

    async def index_daily(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("Strategy-integrity audit is offline-only; KRX network access is disabled.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StockScope Scanner strategy-definition integrity audit")
    parser.add_argument("--market-store", type=Path, default=None, help="market_history.db path")
    parser.add_argument("--market-scope", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--mode", default="full", choices=["inspect", "full"])
    parser.add_argument("--dates", default="", help="comma-separated YYYY-MM-DD dates")
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--min-date-gap", type=int, default=3)
    parser.add_argument("--min-required-dates", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "strategy_integrity",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Audit version: {AUDIT_VERSION}", flush=True)
    sample_size = int(args.sample_size if args.sample_size is not None else (10 if args.mode == "inspect" else 80))
    min_required = int(args.min_required_dates if args.min_required_dates is not None else (1 if args.mode == "inspect" else 60))

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        auditor = StrategyIntegrityAuditor(scanner, store)
    except RuntimeError as exc:
        print(str(exc))
        return 2

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
            sample_size=max(1, sample_size),
            min_date_gap=max(1, int(args.min_date_gap)),
            future_horizon_trading_days=20,
            min_required_dates=max(1, min_required),
        )

    if not dates:
        print("No complete local evaluation dates were found. Audit did not call KRX.")
        return 2

    source = auditor.source_report
    print(
        f"Scanner strategy-integrity audit: mode={args.mode}, dates={len(dates)}, "
        f"range={dates[0].isoformat()}..{dates[-1].isoformat()}, "
        f"market={scanner.QUICK_LIMIT_PER_MARKET}, quick={scanner.DEEP_LIMIT}"
    )
    print(
        "Temporal sampling: "
        f"requested={sampling.get('requested_sample_size')}, selected={sampling.get('selected_sample_size')}, "
        f"gap={sampling.get('requested_min_date_gap')}->{sampling.get('effective_min_date_gap')}"
    )
    print(
        "Source inspection: "
        f"files={source.get('files_scanned')}, "
        f"signal-window-candidates={source.get('signal_snapshot_window_candidates')}, "
        f"duplicate-weights={(source.get('breakout_rs_definition') or {}).get('weights')}, "
        f"sector->market-fallback-hits={len(source.get('sector_market_fallback_source_hits') or [])}"
    )

    def report_progress(index: int, total: int, as_of: date, run: dict) -> None:
        integrity = run.get("integrity") or {}
        ma = integrity.get("ma120") or {}
        rs = integrity.get("breakout_rs") or {}
        comparisons = run.get("comparisons") or {}
        ma_cmp = comparisons.get("MA120_FIXED_AUDIT") or {}
        keep4_cmp = comparisons.get(RS_KEEP_4) or {}
        keep8_cmp = comparisons.get(RS_KEEP_8) or {}
        print(
            f"[{index:>3}/{total}] {as_of.isoformat()} {run.get('status')} "
            f"maMissing={ma.get('ma120_unavailable', 0)} "
            f"maWouldPass={ma.get('ma120_would_pass', 0)} "
            f"rsDup={rs.get('exact_duplicate_evaluations', 0)} "
            f"maQΔ={ma_cmp.get('quick_pool_replacements', 0)} "
            f"k4QΔ={keep4_cmp.get('quick_pool_replacements', 0)} "
            f"k8QΔ={keep8_cmp.get('quick_pool_replacements', 0)} "
            f"{run.get('runtime_seconds')}s",
            flush=True,
        )

    payload = auditor.run_dates(
        dates=dates,
        market_scope=args.market_scope,
        horizons=AuditHorizons((5, 10, 20)),
        mode=args.mode,
        progress_callback=report_progress,
    )
    payload["sampling"] = sampling
    payload = compact_integrity_payload(payload)
    payload = add_audit_metadata(payload, market_store=store, project_root=BACKEND_ROOT.parent)
    paths = write_integrity_outputs(payload, output_dir=args.output_dir)

    validation = payload.get("strategy_integrity_validation") or {}
    ma = validation.get("ma120") or {}
    rs = validation.get("breakout_rs") or {}
    ma_imp = validation.get("ma120_impact") or {}
    rs_variants = validation.get("rs_variants") or {}
    print(f"Audit complete: {payload.get('valid_date_count')} valid dates")
    print(
        f"MA120: verdict={ma.get('verdict')}, availability={ma.get('availability_rate_pct')}%, "
        f"missing={ma.get('condition_missing_count')}, wouldPass={ma.get('would_pass_if_sma120_available_count')}, "
        f"Quick18Δ={ma_imp.get('quick_pool_changed_date_count')}, Top5Δ={ma_imp.get('top5_changed_date_count')}"
    )
    print(
        f"Breakout RS: verdict={rs.get('verdict')}, weights={rs.get('detected_duplicate_weights')}, "
        f"exactDup={rs.get('exact_duplicate_evaluation_count')}, fallback={rs.get('market_fallback_count')}"
    )
    for variant_name in (RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8):
        item = rs_variants.get(variant_name) or {}
        impact = item.get("impact") or {}
        print(
            f"{variant_name}: removed={item.get('removed_weight')}, scoreChanged={item.get('score_changed_signals')}, "
            f"market={item.get('market_weight', 6)}, sector={item.get('kept_weight')}, "
            f"conditionCountChanged={item.get('condition_count_changed_signals', 0)}, "
            f"strategyChanged={item.get('strategy_changed_signals')}, "
            f"Quick18Δ={impact.get('quick_pool_changed_date_count')}, Top5Δ={impact.get('top5_changed_date_count')}"
        )
    print(f"RS policy verdict={validation.get('rs_policy_verdict')}")
    print(f"Overall verdict={validation.get('overall_verdict')}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
