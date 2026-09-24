from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data.common import (
    DataToolError,
    ensure_backend_import_path,
    holdings_db_path,
    market_db_path,
    monitored_targets,
)


def _resolve_markets(
    *,
    market_filter: str | None,
    ticker: str | None,
) -> list[str]:
    holdings = holdings_db_path()
    if ticker:
        value = ticker.strip()
        if len(value) != 6 or not value.isdigit():
            raise DataToolError("--ticker는 국내주식 6자리 종목코드여야 합니다.")

    targets = monitored_targets(holdings)
    if ticker:
        matches = [
            item
            for item in targets
            if item["ticker"] == ticker
            and (
                market_filter is None
                or item["market"] == market_filter
            )
        ]
        if not matches:
            if market_filter:
                return [market_filter]
            raise DataToolError(
                "해당 ticker의 market을 관리 종목에서 찾지 못했습니다. --market을 함께 지정하세요."
            )
        return sorted({item["market"] for item in matches})

    if market_filter:
        return [market_filter]

    markets = sorted({item["market"] for item in targets})
    if not markets:
        raise DataToolError(
            "관심/보유 종목이 없어 준비할 시장이 없습니다. --market을 지정할 수 있습니다."
        )
    return markets


def _progress(payload: dict[str, Any]) -> None:
    stage = str(payload.get("stage") or "")
    message = str(payload.get("message") or "")
    details = dict(payload.get("details") or {})
    current = details.get("current_item")
    suffix = f" · {current}" if current else ""
    print(f"[{stage}] {message}{suffix}")


async def prepare_markets(
    markets: list[str],
    *,
    allow_large: bool,
) -> dict[str, Any]:
    ensure_backend_import_path()

    from app.backtest.market_store import HistoricalMarketStore
    from app.backtest.scanner import StockScannerService
    from app.core.config import get_settings
    from app.market.providers import KrxProvider

    settings = get_settings()
    if not settings.krx_api_key:
        raise DataToolError(
            "KRX_API_KEY가 설정되지 않았습니다. .env를 확인하세요."
        )

    store = HistoricalMarketStore(market_db_path())
    provider = KrxProvider(settings.krx_api_key)
    scanner = StockScannerService(
        provider,
        market_store=store,
    )

    results: dict[str, Any] = {}
    for market in markets:
        print("")
        print(f"[{market}] 최신 확정 EOD 기준일 확인")
        known_compact = store.latest_complete_date(market, "stock")
        known = (
            f"{known_compact[:4]}-{known_compact[4:6]}-{known_compact[6:8]}"
            if known_compact and len(known_compact) == 8
            else None
        )
        latest = await scanner.prepare_latest_confirmed_data(
            market_scope=market,
            known_data_date=known,
            progress=_progress,
        )
        resolved = str(latest.get("resolved_as_of_date") or "")
        if not resolved:
            raise DataToolError(
                f"{market} 최신 확정 EOD 기준일을 확인하지 못했습니다."
            )

        stable_end = date.fromisoformat(resolved)
        start = stable_end - timedelta(
            days=scanner.FAST_HISTORY_CALENDAR_DAYS
        )
        plan = scanner._history_plan(  # noqa: SLF001
            market=market,
            start=start,
            end=stable_end,
        )
        estimated = int(plan["estimated_network_requests"])
        fast_limit = int(
            getattr(
                scanner,
                "DEFAULT_FAST_REQUEST_LIMIT",
                60,
            )
        )
        print(
            f"[{market}] 분석 이력 준비 계획: "
            f"missing items={len(plan['work'])}, "
            f"estimated network={estimated}, "
            f"window={scanner.FAST_HISTORY_CALENDAR_DAYS} calendar days"
        )

        if estimated > fast_limit and not allow_large:
            results[market] = {
                "status": "BLOCKED_LARGE_SYNC",
                "resolved_as_of_date": resolved,
                "estimated_network_requests": estimated,
                "fast_limit": fast_limit,
            }
            print(
                f"[{market}] 대량 요청이 필요해 중단했습니다. "
                f"확인 후 --allow-large를 붙여 다시 실행하세요."
            )
            continue

        await provider.open_session()
        try:
            started = time.perf_counter()
            sync = await scanner._ensure_market_history(  # noqa: SLF001
                market=market,
                start=start,
                end=stable_end,
                progress=_progress,
                progress_base=0,
                progress_span=100,
                started_at=started,
                plan=plan,
            )
        finally:
            await provider.close_session()

        results[market] = {
            "status": "READY" if int(sync.get("errors") or 0) == 0 else "PARTIAL",
            "resolved_as_of_date": resolved,
            "history_start": start.isoformat(),
            **sync,
        }

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "관심/보유 종목에 필요한 시장의 확정 EOD 데이터만 준비합니다. "
            "Scanner ranking은 실행하지 않습니다."
        )
    )
    parser.add_argument(
        "--market",
        choices=["KOSPI", "KOSDAQ"],
        help="특정 시장만 준비합니다.",
    )
    parser.add_argument(
        "--ticker",
        help="특정 관리 종목의 시장만 준비합니다. KRX 일별 API 특성상 날짜 스냅샷은 시장 단위입니다.",
    )
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help="기본 빠른 요청 한도를 넘는 초기 데이터 준비를 명시적으로 허용합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        markets = _resolve_markets(
            market_filter=args.market,
            ticker=args.ticker,
        )
        print("=" * 78)
        print("STOCKSCOPE DATA PREPARE")
        print("=" * 78)
        print("Markets:", ", ".join(markets))
        print("Scanner ranking: NOT RUN")
        print("Target source: 관심/보유 종목의 시장")
        print(
            "Note: KRX 일별 주식 API는 날짜별 시장 스냅샷을 반환하므로 "
            "필요 종목이 있는 시장의 부족 날짜만 요청합니다."
        )
        results = asyncio.run(
            prepare_markets(
                markets,
                allow_large=args.allow_large,
            )
        )
        print("")
        print("RESULT")
        blocked = False
        for market, result in results.items():
            print(
                f" - {market}: {result['status']} "
                f"({result.get('resolved_as_of_date') or '-'})"
            )
            if result["status"] == "BLOCKED_LARGE_SYNC":
                blocked = True
        return 2 if blocked else 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
