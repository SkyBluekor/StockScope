from __future__ import annotations

import argparse
import asyncio
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
    MA120_FIXED,
    MA120_INPUT_ONLY,
    RS_KEEP_4,
    RS_KEEP_8,
    RS_RESTORE_10_8,
    RS_AUDIT_CURRENT,
    RS_AUDIT_KEEP_4,
    RS_AUDIT_KEEP_8,
    RS_AUDIT_RESTORE_10_8,
    StrategyIntegrityAuditor,
    audit_code_fingerprint,
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
    parser.add_argument("--dates", default="", help="legacy alias: comma-separated YYYY-MM-DD dates")
    parser.add_argument("--evaluation-dates", default="", help="comma-separated YYYY-MM-DD dates")
    parser.add_argument("--evaluation-dates-file", type=Path, default=None, help="text file with one YYYY-MM-DD date per line or comma-separated dates")
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--min-date-gap", type=int, default=3)
    parser.add_argument("--min-required-dates", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "runtime" / "quality_audit" / "strategy_integrity",
    )
    parser.add_argument(
        "--sector-rs-audit-live",
        action="store_true",
        help=(
            "Enable c.4g audit-only historical Sector RS verification using current OpenDART industry metadata "
            "and historical KRX EOD sector indices. Production StrategyInput remains gated because "
            "the mapping is STATIC_CURRENT, not point-in-time."
        ),
    )
    return parser.parse_args()



def _explicit_dates(args: argparse.Namespace) -> list[date]:
    sources = [bool(args.dates.strip()), bool(args.evaluation_dates.strip()), args.evaluation_dates_file is not None]
    if sum(sources) > 1:
        raise ValueError("Use only one of --dates, --evaluation-dates, --evaluation-dates-file")
    raw = args.evaluation_dates.strip() or args.dates.strip()
    if args.evaluation_dates_file is not None:
        raw = args.evaluation_dates_file.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return []
    tokens = [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip() and not item.strip().startswith("#")]
    result = [date.fromisoformat(value) for value in tokens]
    if len(set(result)) != len(result):
        raise ValueError("Explicit evaluation dates contain duplicates")
    return result

def main() -> int:
    args = parse_args()
    sample_size = int(args.sample_size if args.sample_size is not None else (10 if args.mode == "inspect" else 80))
    min_required = int(args.min_required_dates if args.min_required_dates is not None else (1 if args.mode == "inspect" else 60))

    store = HistoricalMarketStore(args.market_store) if args.market_store else HistoricalMarketStore()
    live_krx = None
    if args.sector_rs_audit_live:
        # Import lazily so the default strategy-integrity audit stays fully offline and
        # keeps its existing zero-network guarantee.
        from app.core.config import get_settings
        from app.market.providers import KrxProvider, OpenDartProvider

        settings = get_settings()
        live_krx = KrxProvider(settings.krx_api_key)
        dart = OpenDartProvider(settings.dart_api_key)
        scanner = StockScannerService(
            live_krx,
            market_store=store,
            sector_company_provider=dart,
        )
        print(
            "c.4g Sector RS live verification enabled: current OpenDART industry metadata is "
            "STATIC_CURRENT and remains audit-only; Production strategy input is not activated."
        )
    else:
        scanner = StockScannerService(OfflineAuditKrx(), market_store=store)
    try:
        auditor = StrategyIntegrityAuditor(scanner, store)
    except RuntimeError as exc:
        print(str(exc))
        return 2

    try:
        explicit_dates = _explicit_dates(args)
    except (OSError, ValueError) as exc:
        print(f"Invalid explicit evaluation dates: {exc}")
        return 2

    if explicit_dates:
        dates = explicit_dates
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
        f"market-weights={(source.get('breakout_rs_definition') or {}).get('market_weights')}, "
        f"sector-weights={(source.get('breakout_rs_definition') or {}).get('weights')}, "
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
        restore_cmp = comparisons.get(RS_RESTORE_10_8) or {}
        ma_input_cmp = comparisons.get(MA120_INPUT_ONLY) or {}
        sector_input = integrity.get("sector_rs_input") or {}
        sector_cmp = integrity.get("sector_rs_counterfactual") or {}
        sector_comparisons = run.get("sector_comparisons") or {}
        sector_keep8_cmp = sector_comparisons.get(RS_AUDIT_KEEP_8) or {}
        print(
            f"[{index:>3}/{total}] {as_of.isoformat()} {run.get('status')} "
            f"maMissing={ma.get('ma120_unavailable', 0)} "
            f"maWouldPass={ma.get('ma120_would_pass', 0)} "
            f"rsDup={rs.get('exact_duplicate_evaluations', 0)} "
            f"maQΔ={ma_cmp.get('quick_pool_replacements', 0)} "
            f"k4QΔ={keep4_cmp.get('quick_pool_replacements', 0)} "
            f"k8QΔ={keep8_cmp.get('quick_pool_replacements', 0)} "
            f"restoreQΔ={restore_cmp.get('quick_pool_replacements', 0)} "
            f"maInputQΔ={ma_input_cmp.get('quick_pool_replacements', 0)} "
            f"sector20={sector_input.get('sector_20d_available', 0)}/{sector_input.get('evaluations', 0)} "
            f"sectorCF={sector_cmp.get('supported', 0)}/{sector_cmp.get('attempted', 0)} "
            f"sectorK8QΔ={sector_keep8_cmp.get('quick_pool_replacements', 0)} "
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
    payload["audit_code_fingerprint"] = audit_code_fingerprint(BACKEND_ROOT.parent)
    paths = write_integrity_outputs(payload, output_dir=args.output_dir)

    validation = payload.get("strategy_integrity_validation") or {}
    ma = validation.get("ma120") or {}
    rs = validation.get("breakout_rs") or {}
    sector_input = validation.get("sector_rs_input") or {}
    ma_imp = validation.get("ma120_impact") or {}
    ma_input_imp = validation.get("ma120_input_only_impact") or {}
    rs_variants = validation.get("rs_variants") or {}
    acceptance = validation.get("c4g_production_rs_acceptance") or {}
    print(f"Audit complete: {payload.get('valid_date_count')} valid dates")
    print(
        "c.4g Production RS: "
        f"verdict={acceptance.get('verdict')}, definition={acceptance.get('production_definition')}, "
        f"market={acceptance.get('market_weights')}, sector={acceptance.get('sector_weights')}, "
        f"sectorConditions={acceptance.get('sector_condition_count')}, duplicate={acceptance.get('duplicate_present')}, "
        f"futureViolations={acceptance.get('future_boundary_violations')}, "
        f"historicalSectorActivation={acceptance.get('historical_sector_activation_allowed')}"
    )
    print(
        f"MA120: verdict={ma.get('verdict')}, availability={ma.get('availability_rate_pct')}%, "
        f"missing={ma.get('condition_missing_count')}, wouldPass={ma.get('would_pass_if_sma120_available_count')}, "
        f"Quick18Δ={ma_imp.get('quick_pool_changed_date_count')}, Top5Δ={ma_imp.get('top5_changed_date_count')}; "
        f"INPUT_ONLY Quick18 membership/order={ma_input_imp.get('quick_pool_changed_date_count')}/{ma_input_imp.get('quick_order_changed_date_count')}, "
        f"Top5 membership/order={ma_input_imp.get('top5_changed_date_count')}/{ma_input_imp.get('top5_order_changed_date_count')}"
    )
    print(
        "Sector RS input: "
        f"20D={sector_input.get('sector_20d_available')}/{sector_input.get('evaluations')} "
        f"({sector_input.get('sector_20d_availability_rate_pct')}%), "
        f"temporal={sector_input.get('temporal_status_counts')}, "
        f"productionSafe={sector_input.get('production_safe')}, "
        f"futureViolations={sector_input.get('future_boundary_violations')}"
    )
    sector_cf = validation.get("sector_rs_counterfactual") or {}
    print(
        "Sector-aware CF: "
        f"supported={sector_cf.get('supported')}/{sector_cf.get('attempted')}, "
        f"realSector={sector_cf.get('real_sector_available')}, "
        f"signDivergence={sector_cf.get('market_sector_sign_divergent')} "
        f"({sector_cf.get('market_sector_sign_divergence_rate_pct')}%), "
        f"breakoutScoreChanged={sector_cf.get('production_10_8_breakout_score_changed_signals')}, "
        f"strategyChanged={sector_cf.get('production_10_8_strategy_changed_signals')}, "
        f"ready={sector_cf.get('ready_for_production_validation')}"
    )
    if acceptance.get("verdict") != "PASS":
        for variant_name in (RS_AUDIT_KEEP_4, RS_AUDIT_KEEP_8, RS_AUDIT_RESTORE_10_8):
            item = (sector_cf.get("variants") or {}).get(variant_name) or {}
            impact = item.get("impact") or {}
            print(
                f"{variant_name}: removed={item.get('removed_weight')}, scoreChanged={item.get('score_changed_signals')}, "
                f"strategyChanged={item.get('strategy_changed_signals')}, "
                f"Quick18 membership/order={impact.get('quick_pool_changed_date_count')}/{impact.get('quick_order_changed_date_count')}, "
                f"Top5 membership/order={impact.get('top5_changed_date_count')}/{impact.get('top5_order_changed_date_count')}"
            )
    else:
        print("Legacy 6+4+8/KEEP_4/KEEP_8 comparison: not applicable after c.4g Production 10+8 correction")
    print(
        f"Breakout RS: verdict={rs.get('verdict')}, sectorWeights={rs.get('production_sector_weights')}, "
        f"exactDup={rs.get('exact_duplicate_evaluation_count')}, fallback={rs.get('market_fallback_count')}"
    )
    if acceptance.get("verdict") != "PASS":
        for variant_name in (RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8):
            item = rs_variants.get(variant_name) or {}
            impact = item.get("impact") or {}
            print(
                f"{variant_name}: removed={item.get('removed_weight')}, scoreChanged={item.get('score_changed_signals')}, "
                f"strategyChanged={item.get('strategy_changed_signals')}, "
                f"Quick18Δ={impact.get('quick_pool_changed_date_count')}, Top5Δ={impact.get('top5_changed_date_count')}"
            )
    print(f"RS policy verdict={validation.get('rs_policy_verdict')}")
    print(f"Overall verdict={validation.get('overall_verdict')}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    if live_krx is not None and hasattr(live_krx, "close_session"):
        try:
            asyncio.run(live_krx.close_session())
        except Exception as exc:
            print(f"Warning: failed to close KRX audit session cleanly: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
