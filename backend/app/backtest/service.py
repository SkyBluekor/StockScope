from __future__ import annotations

import asyncio
from datetime import date, timedelta
from time import monotonic
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.interpreter import build_problem_solver
from app.backtest.multi_strategy import MultiStrategyBacktestEngine
from app.backtest.models import BacktestConfig
from app.core.stock_code import normalize_stock_code
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError

ProgressCallback = Callable[[dict[str, Any]], None]


class BacktestService:
    MAX_CALENDAR_DAYS = 366 * 5
    INITIAL_WARMUP_CALENDAR_DAYS = 100
    WARMUP_EXTENSION_DAYS = 45
    MAX_WARMUP_CALENDAR_DAYS = 730
    REQUIRED_PRESTART_ROWS = 60
    FETCH_CONCURRENCY = 8
    MAX_FETCH_CONCURRENCY = 12
    MIN_FETCH_CONCURRENCY = 2

    def __init__(
        self,
        krx: KrxProvider,
        engine: BacktestEngine | None = None,
        history_store: HistoricalStore | None = None,
        market_store: HistoricalMarketStore | None = None,
    ) -> None:
        self.krx = krx
        self.engine = engine or BacktestEngine()
        self.multi_engine = MultiStrategyBacktestEngine(self.engine)
        self.history_store = history_store or HistoricalStore()
        self.market_store = market_store or HistoricalMarketStore()

    @staticmethod
    def _parse_iso(value: str, label: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label}은 YYYY-MM-DD 형식이어야 합니다.") from exc

    @staticmethod
    def _weekdays(start: date, end: date) -> list[date]:
        result: list[date] = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                result.append(current)
            current += timedelta(days=1)
        return result

    @staticmethod
    def _compact(value: date) -> str:
        return value.strftime("%Y%m%d")

    @staticmethod
    def _row_date(row: dict[str, Any]) -> str:
        return str(row.get("date") or "").replace("-", "")

    @staticmethod
    def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
        if callback is not None:
            callback(payload)

    @staticmethod
    def _stats_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        keys = set(before) | set(after)
        return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}

    @staticmethod
    def _persistent_copy(series: HistorySeries, today_compact: str) -> HistorySeries:
        return HistorySeries(
            rows={key: row for key, row in series.rows.items() if key < today_compact},
            checked_dates={key for key in series.checked_dates if key < today_compact},
        )

    def _covered(self, series: HistorySeries, day: date) -> bool:
        key = self._compact(day)
        return key in series.rows or key in series.checked_dates

    async def _ensure_range(
        self,
        *,
        code: str,
        market: str,
        start: date,
        end: date,
        stock_series: HistorySeries,
        index_series: HistorySeries,
        progress: ProgressCallback | None,
        phase_label: str,
    ) -> tuple[int, int, int, int]:
        dates = self._weekdays(start, end)
        work: list[tuple[str, date]] = []
        for day in dates:
            if not self._covered(stock_series, day):
                work.append(("stock", day))
            if not self._covered(index_series, day):
                work.append(("index", day))

        total_items = len(dates) * 2
        store_hits = total_items - len(work)
        completed = store_hits
        errors = 0
        concurrency = self.FETCH_CONCURRENCY
        clean_batches = 0
        today = self.krx._today_kst()  # noqa: SLF001 - same provider freshness policy
        today_compact = today.strftime("%Y%m%d")
        stats_before = self.krx.request_stats()

        # Raw KRX gzip/memory cache may already satisfy SQLite misses. Only the
        # remaining items are expected to become real HTTP requests. This check is
        # completed before the first network call so an oversized sync can be blocked.
        estimated_network = sum(
            1
            for kind, day in work
            if not self.krx.has_cached_day(market, day, kind)
        )
        budget_before = self.krx.assert_budget(estimated_network)

        self._emit(
            progress,
            stage="data_prepare",
            message=phase_label,
            current=completed,
            total=total_items,
            details={
                "history_store_hits": store_hits,
                "market_store_hits": store_hits,
                "estimated_network_requests": estimated_network,
                "network_requests": 0,
                "raw_cache_hits": 0,
                "concurrency": concurrency,
                "budget_used": budget_before.get("used", 0),
                "budget_limit": budget_before.get("safe_limit", 0),
                "budget_remaining": budget_before.get("remaining", 0),
            },
        )

        offset = 0
        while offset < len(work):
            batch = work[offset : offset + concurrency]
            batch_stats_before = self.krx.request_stats()

            async def fetch_one(kind: str, day: date) -> dict[str, Any]:
                if kind == "stock":
                    # Important: do NOT filter by symbol here. One KRX response already
                    # contains the whole market, so persist it once for every stock.
                    return await self.krx.stock_daily(market, day)
                return await self.krx.index_daily(market, day)

            results = await asyncio.gather(
                *(fetch_one(kind, day) for kind, day in batch),
                return_exceptions=True,
            )
            batch_errors = 0
            for descriptor, result in zip(batch, results, strict=True):
                kind, day = descriptor
                key = self._compact(day)
                completed += 1
                if isinstance(result, Exception):
                    errors += 1
                    batch_errors += 1
                    continue

                if kind == "stock":
                    rows = list(result.get("rows") or [])
                    selected = next(
                        (row for row in rows if str(row.get("code") or "").strip().upper() == code),
                        None,
                    )
                    if selected is not None and selected.get("close") is not None:
                        stock_series.rows[key] = selected
                    if rows and day < today:
                        stock_series.checked_dates.add(key)
                        self.market_store.put_stock_day(market, key, rows, stable=True)
                    elif not rows and self.krx._is_stable_empty_date(key):  # noqa: SLF001
                        stock_series.checked_dates.add(key)
                        self.market_store.put_stock_day(market, key, [], stable=True)
                    # Today's/recent volatile data remains provider-memory-only.
                else:
                    rows = list(result.get("rows") or [])
                    main = self.krx._select_main_index(rows, market) if rows else None  # noqa: SLF001
                    if main is not None:
                        index_series.rows[key] = main
                    if rows and day < today:
                        index_series.checked_dates.add(key)
                        self.market_store.put_index_day(market, key, main, stable=True)
                    elif not rows and self.krx._is_stable_empty_date(key):  # noqa: SLF001
                        index_series.checked_dates.add(key)
                        self.market_store.put_index_day(market, key, None, stable=True)

            # Be faster on healthy KRX responses, but back off when a batch is unstable
            # or when the provider had to retry 429/5xx/connection failures.
            batch_stats_after = self.krx.request_stats()
            batch_retries = max(0, batch_stats_after.get("retries", 0) - batch_stats_before.get("retries", 0))
            if batch_errors or batch_retries:
                clean_batches = 0
                if batch_errors / max(len(batch), 1) >= 0.25:
                    concurrency = max(self.MIN_FETCH_CONCURRENCY, concurrency // 2)
                elif batch_retries:
                    concurrency = max(self.MIN_FETCH_CONCURRENCY, concurrency - 2)
            else:
                clean_batches += 1
                if clean_batches >= 3 and concurrency < self.MAX_FETCH_CONCURRENCY:
                    concurrency += 1
                    clean_batches = 0

            offset += len(batch)
            stats_now = self._stats_delta(stats_before, batch_stats_after)
            budget_now = self.krx.budget_snapshot()
            self._emit(
                progress,
                stage="data_prepare",
                message=phase_label,
                current=completed,
                total=total_items,
                details={
                    "history_store_hits": store_hits,
                    "market_store_hits": store_hits,
                    "estimated_network_requests": estimated_network,
                    "network_requests": stats_now.get("network_requests", 0),
                    "raw_cache_hits": stats_now.get("disk_hits", 0) + stats_now.get("memory_hits", 0) + stats_now.get("empty_marker_hits", 0),
                    "retries": stats_now.get("retries", 0),
                    "concurrency": concurrency,
                    "budget_used": budget_now.get("used", 0),
                    "budget_limit": budget_now.get("safe_limit", 0),
                    "budget_remaining": budget_now.get("remaining", 0),
                },
            )

        # Keep the old compact per-symbol cache as a backwards-compatible fallback.
        # New cross-symbol reuse comes from HistoricalMarketStore above.
        self.history_store.save_stock(
            market,
            code,
            self._persistent_copy(stock_series, today_compact),
        )
        self.history_store.save_index(
            market,
            self._persistent_copy(index_series, today_compact),
        )
        stats_after = self._stats_delta(stats_before, self.krx.request_stats())
        return errors, store_hits, stats_after.get("network_requests", 0), estimated_network

    async def _prepare_history(
        self,
        *,
        config: BacktestConfig,
        start: date,
        end: date,
        progress: ProgressCallback | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], date, dict[str, int]]:
        # One-time/on-demand migration: existing compact history is imported instead
        # of being downloaded again. Raw market-wide gzip cache is still reused by
        # KrxProvider on any SQLite miss and then promoted into SQLite.
        legacy_stock = self.history_store.load_stock(config.market, config.code)
        legacy_index = self.history_store.load_index(config.market)
        imported_stock = self.market_store.import_legacy_stock(config.market, config.code, legacy_stock)
        imported_index = self.market_store.import_legacy_index(config.market, legacy_index)

        stock_series = self.market_store.stock_series(config.market, config.code)
        index_series = self.market_store.index_series(config.market)
        # Legacy checked_dates are symbol-specific. Reuse them for this run without
        # falsely marking the whole market/date complete for every other symbol.
        stock_series.rows.update(legacy_stock.rows)
        stock_series.checked_dates.update(legacy_stock.checked_dates)
        index_series.rows.update(legacy_index.rows)
        index_series.checked_dates.update(legacy_index.checked_dates)

        warnings: list[str] = []
        error_count = 0
        history_store_hits = 0
        network_requests = 0
        estimated_requests = 0
        provider_before = self.krx.request_stats()

        range_start = start - timedelta(days=self.INITIAL_WARMUP_CALENDAR_DAYS)
        errors, hits, requests, estimate = await self._ensure_range(
            code=config.code,
            market=config.market,
            start=range_start,
            end=end,
            stock_series=stock_series,
            index_series=index_series,
            progress=progress,
            phase_label="과거 KRX 데이터 준비 중",
        )
        error_count += errors
        history_store_hits += hits
        network_requests += requests
        estimated_requests += estimate

        start_key = self._compact(start)
        prestart_count = sum(1 for key in stock_series.rows if key < start_key)
        max_start = start - timedelta(days=self.MAX_WARMUP_CALENDAR_DAYS)
        while prestart_count < self.REQUIRED_PRESTART_ROWS and range_start > max_start:
            new_start = max(max_start, range_start - timedelta(days=self.WARMUP_EXTENSION_DAYS))
            extension_end = range_start - timedelta(days=1)
            errors, hits, requests, estimate = await self._ensure_range(
                code=config.code,
                market=config.market,
                start=new_start,
                end=extension_end,
                stock_series=stock_series,
                index_series=index_series,
                progress=progress,
                phase_label=f"지표 워밍업 확보 중 · {prestart_count}/{self.REQUIRED_PRESTART_ROWS} 거래일",
            )
            error_count += errors
            history_store_hits += hits
            network_requests += requests
            estimated_requests += estimate
            range_start = new_start
            prestart_count = sum(1 for key in stock_series.rows if key < start_key)

        end_key = self._compact(end)
        stock_rows = [
            row for key, row in stock_series.rows.items()
            if self._compact(range_start) <= key <= end_key
        ]
        index_rows = [
            row for key, row in index_series.rows.items()
            if self._compact(range_start) <= key <= end_key
        ]
        stock_rows.sort(key=self._row_date)
        index_rows.sort(key=self._row_date)

        if not stock_rows:
            raise ProviderError("선택 기간에서 백테스트에 사용할 KRX 종목 데이터를 찾지 못했습니다.")
        if not index_rows:
            warnings.append("대표 시장지수 데이터가 없어 시장 국면/상대강도 조건은 UNKNOWN으로 계산됩니다.")
        if error_count:
            warnings.append(
                f"기간 조회 중 {error_count}개 KRX 요청이 실패했습니다. 확보된 확정 데이터만 사용했습니다."
            )
        if prestart_count < self.REQUIRED_PRESTART_ROWS:
            warnings.append(
                f"시작일 이전 워밍업 데이터가 {prestart_count}거래일만 확보되어 초기 구간 일부는 신호 계산에서 제외될 수 있습니다."
            )

        provider_delta = self._stats_delta(provider_before, self.krx.request_stats())
        cache_hits = (
            provider_delta.get("memory_hits", 0)
            + provider_delta.get("disk_hits", 0)
            + provider_delta.get("empty_marker_hits", 0)
        )
        budget = self.krx.budget_snapshot()
        distinct_remote_fetches = max(0, provider_delta.get("network_requests", network_requests) - provider_delta.get("retries", 0))
        reused_items = history_store_hits + cache_hits
        reuse_denominator = reused_items + distinct_remote_fetches
        cache_reuse_pct = round(reused_items / reuse_denominator * 100.0, 1) if reuse_denominator else 100.0
        return stock_rows, index_rows, warnings, range_start, {
            "history_store_hits": history_store_hits,
            "market_store_hits": history_store_hits,
            "legacy_rows_imported": imported_stock + imported_index,
            "raw_cache_hits": cache_hits,
            "cache_reuse_pct": cache_reuse_pct,
            "estimated_network_requests": estimated_requests,
            "network_requests": provider_delta.get("network_requests", network_requests),
            "retries": provider_delta.get("retries", 0),
            "warmup_rows": prestart_count,
            "budget_used": int(budget.get("used", 0)),
            "budget_limit": int(budget.get("safe_limit", 0)),
            "budget_remaining": int(budget.get("remaining", 0)),
        }

    async def run_pullback(
        self,
        config: BacktestConfig,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        started = monotonic()
        start = self._parse_iso(config.start_date, "시작일")
        end = self._parse_iso(config.end_date, "종료일")
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if (end - start).days > self.MAX_CALENDAR_DAYS:
            raise ValueError("한 번에 최대 5년까지 백테스트할 수 있습니다.")
        if config.max_holding_days < 1 or config.max_holding_days > 120:
            raise ValueError("최대 보유기간은 1~120 거래일 범위여야 합니다.")
        if config.initial_capital <= 0:
            raise ValueError("초기 자본은 0보다 커야 합니다.")
        if config.round_trip_cost_pct < 0 or config.round_trip_cost_pct > 5:
            raise ValueError("왕복 비용률은 0~5% 범위여야 합니다.")

        config.code = normalize_stock_code(config.code)
        config.market = config.market.upper().strip()
        if config.market not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        self._emit(progress, stage="queued", message="백테스트 준비 중", current=0, total=1, details={})
        await self.krx.open_session()
        try:
            data_started = monotonic()
            stock_rows, index_rows, warnings, warmup_start, fetch_stats = await self._prepare_history(
                config=config,
                start=start,
                end=end,
                progress=progress,
            )
            data_seconds = monotonic() - data_started
        finally:
            await self.krx.close_session()

        self._emit(
            progress,
            stage="strategy_calculation",
            message="눌림목 전략 계산 준비 중",
            current=0,
            total=1,
            details={"stock_rows": len(stock_rows), "index_rows": len(index_rows)},
        )

        calculation_started = monotonic()

        def engine_progress(payload: dict[str, Any]) -> None:
            self._emit(progress, **payload)

        result = await asyncio.to_thread(
            self.engine.run,
            stock_rows=stock_rows,
            index_rows=index_rows,
            config=config,
            progress_callback=engine_progress,
        )
        calculation_seconds = monotonic() - calculation_started
        total_seconds = monotonic() - started

        result["version"] = "0.19.6"
        result["problem_solver"] = build_problem_solver(result, config)
        result["data_window"] = {
            "requested_start": config.start_date,
            "requested_end": config.end_date,
            "warmup_start": warmup_start.isoformat(),
            "first_stock_date": str(stock_rows[0].get("date") or ""),
            "last_stock_date": str(stock_rows[-1].get("date") or ""),
            "stock_rows": len(stock_rows),
            "index_rows": len(index_rows),
            "cache_note": "시장+날짜 단위 SQLite Historical Market Store를 우선 사용하고, 기존 종목별/GZIP 캐시를 가져온 뒤 정말 없는 날짜만 KRX에서 추가 조회합니다.",
        }
        result["performance"] = {
            "data_prepare_seconds": round(data_seconds, 3),
            "strategy_calculation_seconds": round(calculation_seconds, 3),
            "total_seconds": round(total_seconds, 3),
            **fetch_stats,
        }
        result["warnings"] = warnings
        self._emit(
            progress,
            stage="completed",
            message="백테스트 완료",
            current=1,
            total=1,
            details=result["performance"],
        )
        return result

    async def run_multi_strategy(
        self,
        config: BacktestConfig,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Validate all ten StockScope strategies on one shared historical dataset."""
        started = monotonic()
        start = self._parse_iso(config.start_date, "시작일")
        end = self._parse_iso(config.end_date, "종료일")
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if (end - start).days > self.MAX_CALENDAR_DAYS:
            raise ValueError("한 번에 최대 5년까지 백테스트할 수 있습니다.")
        if config.max_holding_days < 1 or config.max_holding_days > 120:
            raise ValueError("최대 보유기간은 1~120 거래일 범위여야 합니다.")
        if config.initial_capital <= 0:
            raise ValueError("초기 자본은 0보다 커야 합니다.")
        if config.round_trip_cost_pct < 0 or config.round_trip_cost_pct > 5:
            raise ValueError("왕복 비용률은 0~5% 범위여야 합니다.")

        config.code = normalize_stock_code(config.code)
        config.market = config.market.upper().strip()
        if config.market not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")

        self._emit(progress, stage="queued", message="전체 전략 검증 준비 중", current=0, total=1, details={})
        await self.krx.open_session()
        try:
            data_started = monotonic()
            stock_rows, index_rows, warnings, warmup_start, fetch_stats = await self._prepare_history(
                config=config,
                start=start,
                end=end,
                progress=progress,
            )
            data_seconds = monotonic() - data_started
        finally:
            await self.krx.close_session()

        calculation_started = monotonic()

        def engine_progress(payload: dict[str, Any]) -> None:
            self._emit(progress, **payload)

        result = await asyncio.to_thread(
            self.multi_engine.run,
            stock_rows=stock_rows,
            index_rows=index_rows,
            config=config,
            progress_callback=engine_progress,
        )
        calculation_seconds = monotonic() - calculation_started
        total_seconds = monotonic() - started
        result["data_window"] = {
            "requested_start": config.start_date,
            "requested_end": config.end_date,
            "warmup_start": warmup_start.isoformat(),
            "first_stock_date": str(stock_rows[0].get("date") or ""),
            "last_stock_date": str(stock_rows[-1].get("date") or ""),
            "stock_rows": len(stock_rows),
            "index_rows": len(index_rows),
            "cache_note": "10개 전략이 같은 SQLite 시장 데이터를 공유합니다. 같은 시장/날짜를 다른 종목이 다시 분석해도 저장된 데이터를 재사용합니다.",
        }
        result["performance"] = {
            "data_prepare_seconds": round(data_seconds, 3),
            "strategy_calculation_seconds": round(calculation_seconds, 3),
            "total_seconds": round(total_seconds, 3),
            **fetch_stats,
        }
        result["warnings"] = warnings
        self._emit(
            progress,
            stage="completed",
            message="10개 전략 비교 완료",
            current=1,
            total=1,
            details=result["performance"],
        )
        return result

