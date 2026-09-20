from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.backtest.scanner import StockScannerService
from app.core.config import get_settings
from app.market.providers import KrxProvider

VERSION = "v0.21.4-B.2.3.4c.4f.5"
DEFAULT_EVALUATION_DATES_FILE = BACKEND_ROOT / "tools" / "audit_inputs" / "c4c_10days.txt"


def _parse_day(value: str) -> date:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"날짜 형식 오류: {value!r} (YYYY-MM-DD 또는 YYYYMMDD)")


def _read_evaluation_dates(path: Path) -> list[date]:
    if not path.exists():
        raise FileNotFoundError(f"평가일 파일을 찾을 수 없습니다: {path}")
    values: list[date] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        values.append(_parse_day(line))
    if not values:
        raise ValueError(f"평가일 파일이 비어 있습니다: {path}")
    return sorted(set(values))


def _resolve_range(args: argparse.Namespace, today: date) -> tuple[date, date, list[date]]:
    if args.start or args.end:
        if not (args.start and args.end):
            raise ValueError("--start와 --end는 함께 지정해야 합니다.")
        start = _parse_day(args.start)
        end = _parse_day(args.end)
        evaluation_dates: list[date] = []
    else:
        path = Path(args.evaluation_dates_file)
        evaluation_dates = _read_evaluation_dates(path)
        start = min(evaluation_dates) - timedelta(days=max(0, args.warmup_days))
        end = max(evaluation_dates) + timedelta(days=max(0, args.forward_days))

    if end > today:
        end = today
    if start > end:
        raise ValueError(f"시작일이 종료일보다 늦습니다: {start} > {end}")
    return start, end, evaluation_dates


def _progress_printer() -> Any:
    last_done: dict[str, int] = {}
    last_time: dict[str, float] = {}

    def emit(payload: dict[str, Any]) -> None:
        details = payload.get("details") or {}
        market = str(details.get("market") or "")
        if not market:
            return
        done = int(details.get("items_done") or payload.get("current") or 0)
        total = int(details.get("items_total") or payload.get("total") or 0)
        now = time.perf_counter()
        previous_done = last_done.get(market, -999)
        previous_time = last_time.get(market, 0.0)
        should_print = done >= total or done - previous_done >= 25 or now - previous_time >= 10.0
        if not should_print:
            return
        last_done[market] = done
        last_time[market] = now
        rate = details.get("processing_rate")
        eta = details.get("eta_seconds")
        requests = details.get("network_requests_so_far")
        retries = details.get("retry_count")
        errors = details.get("errors")
        print(
            f"[{market}] {done}/{total}"
            f" | rate={rate if rate is not None else '-'} items/s"
            f" | ETA={eta if eta is not None else '-'}s"
            f" | KRX={requests if requests is not None else '-'}"
            f" | retry={retries if retries is not None else '-'}"
            f" | errors={errors if errors is not None else '-'}",
            flush=True,
        )

    return emit


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    krx = KrxProvider(settings.krx_api_key)
    service = StockScannerService(krx)
    today = krx._today_kst()  # noqa: SLF001 - use the provider's KST boundary
    start, end, evaluation_dates = _resolve_range(args, today)
    markets = ["KOSPI", "KOSDAQ"] if args.market_scope == "ALL" else [args.market_scope]

    print(f"Market Store audit backfill — {VERSION}")
    print(f"range: {start.isoformat()} ~ {end.isoformat()}")
    if evaluation_dates:
        print(
            f"evaluation dates: {len(evaluation_dates)} "
            f"({evaluation_dates[0].isoformat()} ~ {evaluation_dates[-1].isoformat()})"
        )
        print(f"warmup/forward: {args.warmup_days}/{args.forward_days} calendar days")
    print(f"markets: {', '.join(markets)}")

    plans: dict[str, dict[str, Any]] = {}
    estimated_total = 0
    missing_total = 0
    for market in markets:
        plan = service._history_plan(market=market, start=start, end=end)  # noqa: SLF001
        plans[market] = plan
        estimated = int(plan.get("estimated_network_requests") or 0)
        missing = len(plan.get("work") or [])
        estimated_total += estimated
        missing_total += missing
        print(
            f"plan {market}: missing={missing}, reused={int(plan.get('reused') or 0)}, "
            f"estimated_network={estimated}"
        )

    budget = krx.budget_snapshot()
    print(f"KRX budget before: {budget}")
    print(f"total missing items={missing_total}, estimated network requests={estimated_total}")

    if args.dry_run:
        print("dry-run: Market Store는 변경하지 않았습니다.")
        return 0

    # Check the whole job before starting. Individual market syncs also guard budget.
    krx.assert_budget(estimated_total)
    started = time.perf_counter()
    progress = _progress_printer()
    totals = {
        "store_hits": 0,
        "estimated_network_requests": 0,
        "network_requests": 0,
        "raw_cache_hits": 0,
        "errors": 0,
        "processed_items": 0,
        "sync_seconds": 0.0,
    }

    await krx.open_session()
    try:
        market_count = max(1, len(markets))
        for position, market in enumerate(markets):
            result = await service._ensure_market_history(  # noqa: SLF001
                market=market,
                start=start,
                end=end,
                progress=progress,
                progress_base=100.0 * position / market_count,
                progress_span=100.0 / market_count,
                started_at=started,
                plan=plans[market],
            )
            for key in ("store_hits", "estimated_network_requests", "network_requests", "raw_cache_hits", "errors", "processed_items"):
                totals[key] += int(result.get(key) or 0)
            totals["sync_seconds"] += float(result.get("sync_seconds") or 0.0)
            print(f"done {market}: {result}")
    finally:
        await krx.close_session()

    elapsed = time.perf_counter() - started
    print("\nBackfill complete")
    print(f"elapsed={elapsed:.1f}s")
    print(f"totals={totals}")
    print(f"KRX budget after: {krx.budget_snapshot()}")
    if int(totals["errors"]) > 0:
        print("WARNING: 일부 날짜가 실패했습니다. 같은 명령을 다시 실행하면 완료된 날짜는 재사용하고 누락분만 재시도합니다.")
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate HistoricalMarketStore for c.4f/c.4g integrity audits without changing Production policy."
    )
    parser.add_argument("--market-scope", choices=("ALL", "KOSPI", "KOSDAQ"), default="ALL")
    parser.add_argument(
        "--evaluation-dates-file",
        default=str(DEFAULT_EVALUATION_DATES_FILE),
        help="Explicit audit dates. Ignored when --start/--end are supplied.",
    )
    parser.add_argument("--warmup-days", type=int, default=220, help="Calendar-day history before earliest evaluation date.")
    parser.add_argument("--forward-days", type=int, default=35, help="Calendar days after latest evaluation date for 20D outcomes.")
    parser.add_argument("--start", default=None, help="Optional explicit start date (YYYY-MM-DD).")
    parser.add_argument("--end", default=None, help="Optional explicit end date (YYYY-MM-DD).")
    parser.add_argument("--dry-run", action="store_true", help="Show missing items/request estimate only.")
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        code = asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("중단했습니다. 이미 저장된 날짜는 유지되므로 같은 명령으로 재개할 수 있습니다.")
        code = 130
    except Exception as exc:
        print(f"ERROR: {exc}")
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
