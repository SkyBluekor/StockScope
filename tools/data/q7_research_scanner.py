"""S24 manually opted-in research Scanner; zero production Scanner/Prospective writes.

Plan: no API, no writes. Capture: only in morning, explicit KRX/network
consent, isolated market DB snapshot, isolated scanner cache/repro audit and
research-only (NOT ACTIVE) selection pin. Do not schedule or backfill missed days.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for folder in (ROOT, BACKEND):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.jev.research_scanner_s24 import (
    ResearchCaptureError, KST, START, END, canonical_json, research_pin,
    recent_eod_source_date, receipt_for_scanner,
)
from tools.data.common import market_db_path

VERSION = "Q7_S24_RESEARCH_CAPTURE_CLI_V1"
DEFAULT_ROOT = ROOT / "data" / "q7_research_scanner"


def _report(status: str, **kw: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "trusted_prediction_precommit_proven": False,
        "independent_timing_proven": False,
        "jev_model_calls": 0,
        "orders": 0,
        "production_scanner_runs": 0,
        "production_simulation_db_writes": 0,
        "production_market_db_writes": 0,
        **kw,
    }


def _root_guard(root: Path, original_market: Path) -> Path:
    destination = Path(root).resolve()
    production = ROOT / "backend" / "runtime"
    if (destination == production.resolve()
            or production.resolve() in destination.parents
            or destination == original_market.resolve()
            or destination in original_market.resolve().parents
            or original_market.resolve() in destination.parents):
        raise ResearchCaptureError("RESEARCH_ROOT_OVERLAPS_PRODUCTION_SOURCE")
    return destination


def _latest_complete_day(market_db: Path, market: str, today: date) -> date | None:
    if not market_db.is_file():
        return None
    # A local SQLite read does not establish a KRX release timestamp. Both
    # EOD markers AND physical market + index source rows must be present.
    try:
        with sqlite3.connect(market_db.resolve().as_uri() + "?mode=ro", uri=True) as c:
            row = c.execute(
                "SELECT ds.bas_dd FROM day_status ds "
                "JOIN day_status di ON di.market=ds.market AND di.bas_dd=ds.bas_dd "
                "AND di.kind='index' AND di.status='data' "
                "WHERE ds.market=? AND ds.kind='stock' AND ds.status='data' "
                "AND ds.bas_dd<? "
                "AND EXISTS(SELECT 1 FROM stock_daily s "
                "WHERE s.market=ds.market AND s.bas_dd=ds.bas_dd) "
                "AND EXISTS(SELECT 1 FROM main_index_daily i "
                "WHERE i.market=ds.market AND i.bas_dd=ds.bas_dd) "
                "ORDER BY ds.bas_dd DESC LIMIT 1",
                (market, today.strftime("%Y%m%d")),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ResearchCaptureError("RESEARCH_SOURCE_MARKET_SCHEMA_UNAVAILABLE") from exc
    try:
        return datetime.strptime(row[0], "%Y%m%d").date() if row else None
    except (TypeError, ValueError) as exc:
        raise ResearchCaptureError("RESEARCH_SOURCE_MARKET_DATE_INVALID") from exc


def plan(*, market: str = "KOSPI", market_db: Path | None = None,
         now: datetime | None = None) -> dict[str, Any]:
    """Read-only at ANY hour. Report data readiness separately from run eligibility.

    An out-of-window plan must NOT conceal EOD/data/strategy information, and
    must NOT grant permission to perform an out-of-window capture.
    """
    if market not in ("KOSPI", "KOSDAQ"):
        raise ResearchCaptureError("RESEARCH_MARKET_INVALID")
    clock = now or datetime.now(KST)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ResearchCaptureError("RESEARCH_AWARE_KST_CLOCK_REQUIRED")
    local = clock.astimezone(KST)
    source = Path(market_db or market_db_path())
    latest = _latest_complete_day(source, market, local.date())
    pin = research_pin()
    market_data_ready = (
        latest is not None and 1 <= (local.date() - latest).days <= 4
    )
    window_open = (
        local.weekday() < 5
        and START <= local.time().replace(tzinfo=None) <= END
    )

    # Reuse the exact capture gate for the final result, rather than
    # reimplementing authorization in plan. A data-ready plan outside the
    # window remains BLOCKED for capture.
    try:
        allowed_day = recent_eod_source_date(
            clock, complete_market_day=latest,
        )
        reason = None
    except ResearchCaptureError as exc:
        allowed_day = None
        reason = exc.code
    return _report(
        "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED"
        if allowed_day is not None else "PLAN_ONLY_CAPTURE_BLOCKED",
        market=market,
        source_date=latest.isoformat() if latest is not None else None,
        latest_complete_eod_date=latest.isoformat() if latest is not None else None,
        market_data_ready=market_data_ready,
        local_market_date_age_days=(
            (local.date() - latest).days if latest is not None else None
        ),
        data_readiness_reason=(
            "RECENT_LOCAL_COMPLETE_EOD" if market_data_ready
            else "RESEARCH_FRESH_EOD_REQUIRED"
        ),
        collection_window_open=window_open,
        collection_window_kst="05:00-08:45, weekdays",
        capture_permitted_now=allowed_day is not None,
        capture_block_reason=reason,
        reason_code=reason,
        strategy_count=len(pin.operating_strategies),
        research_policy_source=pin.policy_source,
        network_requests=0,
        research_db_writes=0,
        if_executed_network_access_may_occur=True,
        note=(
            "Local EOD completeness does not establish exchange release time, "
            "latest actual market session, independently attested precommit, "
            "or Q7 eligibility."
        ),
    )


async def _execute_scan(*, root: Path, market: str, source_date: date, policy) -> dict[str, Any]:
    from app.backtest.scanner import StockScannerService
    from app.backtest import scanner as scanner_module
    from unittest.mock import patch as scoped_patch
    from app.backtest.market_store import HistoricalMarketStore
    from app.core.config import get_settings
    from app.market.krx_budget import KrxApiBudget
    from app.market.providers.krx import KrxProvider

    api_key = get_settings().krx_api_key
    if not api_key:
        raise ResearchCaptureError("RESEARCH_KRX_API_KEY_REQUIRED")

    class ResearchKrx(KrxProvider):
        _cache_dir = root / "krx_cache"
        _rows_cache = {}
        _cache_expiry = {}
        _inflight_tasks = {}

    class ResearchScanner(StockScannerService):
        CACHE_ROOT = root / "scanner_cache"

    # Isolated budget and caches. The 60-request cap is intentionally far
    # below the KRX daily limit; other API users may consume separate quota.
    provider = ResearchKrx(
        api_key, budget=KrxApiBudget(db_path=root / "budget.sqlite3", safe_limit=60),
    )
    scanner = ResearchScanner(
        provider, market_store=HistoricalMarketStore(root / "market_snapshot.db"),
    )

    # Scanner production implementation and its audited fingerprint remain
    # BYTE-FOR-BYTE unchanged. Only this isolated CLI process substitutes the
    # diagnostic *writer* while the research run is in progress. It still calls
    # the canonical reproducibility payload builder with original raw inputs.
    def isolated_repro_writer(**inputs):
        from app.backtest.reproducibility_audit import (
            build_scanner_reproducibility_payload,
        )
        from datetime import datetime
        output = root / "scanner-repro"
        runtime_identity = root / "repro_identity"
        output.mkdir(parents=True, exist_ok=True)
        runtime_identity.mkdir(parents=True, exist_ok=True)
        payload = build_scanner_reproducibility_payload(
            **inputs, runtime_root=runtime_identity,
        )
        generated = datetime.fromisoformat(payload["generated_at"])
        filename = (
            "scanner-repro_research_" + generated.strftime("%Y%m%d-%H%M%S-%f")
            + "_analysis-" + source_date.strftime("%Y%m%d") + ".json"
        )
        file = output / filename
        with file.open("x", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return {
            "written": True,
            "path": str(file),
            "filename": filename,
            "analysis_date": source_date.isoformat(),
            "candidate_count": len(inputs["ranked_candidates"]),
            "result_source": inputs["result_source"],
            "research_isolated_not_authoritative_production_repro": True,
        }

    with scoped_patch.object(
        scanner_module, "write_scanner_reproducibility_audit", isolated_repro_writer,
    ):
        return await scanner.run(
            market_scope=market, as_of_date=source_date.isoformat(),
            candidate_limit=5, force_refresh=True, allow_large_sync=False,
            selection_policy_pin=policy,
        )


def _clone_readonly_source(source: Path, dest: Path) -> None:
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(dest) as target:
            original.backup(target)


async def capture(*, market: str = "KOSPI", market_db: Path | None = None,
                  root: Path = DEFAULT_ROOT, now: datetime | None = None,
                  acknowledge: bool = False,
                  execute_scan: Callable[..., Awaitable[dict[str, Any]]] | None = None,
                  ) -> dict[str, Any]:
    if not acknowledge:
        raise ResearchCaptureError("RESEARCH_EXPLICIT_NETWORK_AND_LOCAL_WRITES_ACK_REQUIRED")
    clock = now or datetime.now(KST)
    source = Path(market_db or market_db_path())
    root = _root_guard(root, source)
    readiness = plan(market=market, market_db=source, now=clock)
    if readiness["status"] != "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED":
        return readiness
    source_date = date.fromisoformat(readiness["source_date"])
    policy = research_pin()
    folder = root / f"{source_date.isoformat()}_{market.lower()}"
    # Directory creation is atomic. Replays cannot replace a prior file or
    # silently fabricate an earlier study precommit. Failed runs stay visible.
    root.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir(exist_ok=False)
    except FileExistsError:
        return _report(
            "HOLD", reason_code="RESEARCH_DAY_ALREADY_ATTEMPTED",
            market=market, source_date=source_date.isoformat(),
            research_db_writes=0, network_requests=0,
        )
    started = datetime.now(KST)
    try:
        _clone_readonly_source(source, folder / "market_snapshot.db")
        scanner = execute_scan or _execute_scan
        result = await scanner(
            root=folder, market=market, source_date=source_date, policy=policy,
        )
        payload = receipt_for_scanner(
            result, policy=policy, source_date=source_date,
            market=market, recorded_at=datetime.now(KST),
        )
        payload["research_started_at_local_unverified"] = started.isoformat()
        # Re-hash after adding the start timestamp; no approval or attestation.
        from app.jev.research_scanner_s24 import digest
        payload["payload_hash"] = digest({
            k: v for k, v in payload.items() if k != "payload_hash"
        })
        destination = folder / "scanner_research_capture.json"
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(canonical_json(payload) + "\n")
        return _report(
            "RESEARCH_CAPTURE_SAVED_NOT_Q7_APPROVED",
            market=market, source_date=source_date.isoformat(),
            capture_file=str(destination),
            payload_hash=payload["payload_hash"],
            original_strategy_rows=len(policy.operating_strategies),
            original_candidates=payload["candidate_count"],
            entry_candidates=payload["entry_candidates"],
            research_scanner_runs=1,
            krx_network_requests_reported=payload["krx_network_requests_reported"],
            research_only_local_clock=True,
            isolated_market_db_writes=True,
        )
    except Exception:
        # Preserve the attempted-day directory for investigation; do not
        # restart an analysis until a human has verified what actually ran.
        raise


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="S24 isolated manual research scanner (never Q7 approval)")
    p.add_argument("mode", choices=("plan", "capture"))
    p.add_argument("--market", choices=("KOSPI", "KOSDAQ"), default="KOSPI")
    p.add_argument("--market-db", type=Path, default=None)
    p.add_argument("--acknowledge-network-and-research-writes", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.mode == "plan":
            result = plan(market=args.market, market_db=args.market_db)
        else:
            result = asyncio.run(capture(
                market=args.market, market_db=args.market_db,
                acknowledge=args.acknowledge_network_and_research_writes,
            ))
    except (ResearchCaptureError, sqlite3.Error, OSError, ValueError) as exc:
        result = _report("HOLD", reason_code=getattr(exc, "code", type(exc).__name__))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in (
        "PLAN_ONLY_CAPTURE_BLOCKED",
        "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED",
        "RESEARCH_CAPTURE_SAVED_NOT_Q7_APPROVED",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
