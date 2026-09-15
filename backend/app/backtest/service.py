from __future__ import annotations

import asyncio
from datetime import date, timedelta
from time import monotonic
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.exit_policy_research import DEFAULT_POST_TARGET2_RESEARCH_DAYS, ExitPolicyResearchEngine
from app.backtest.exit_policy_selection import (
    ExitPolicySelectionConfig,
    ExitPolicySelector,
    save_selection_report,
)
from app.backtest.exit_policy_validation_runner import (
    ExitPolicyValidationCheckpoint,
    ExitPolicyValidationRunnerConfig,
    VALIDATION_RUNNER_VERSION,
    interleave_market_candidates,
    validation_sample_signature,
)
from app.backtest.history_store import HistoricalStore, HistorySeries
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.interpreter import build_problem_solver
from app.backtest.multi_strategy import MultiStrategyBacktestEngine
from app.backtest.models import BacktestConfig
from app.backtest.production_exit_policy import ProductionExitPolicyEngine
from app.strategy.models import StrategyName
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
    FETCH_CONCURRENCY = 12
    MAX_FETCH_CONCURRENCY = 12
    MIN_FETCH_CONCURRENCY = 4

    def __init__(
        self,
        krx: KrxProvider,
        engine: BacktestEngine | None = None,
        history_store: HistoricalStore | None = None,
        market_store: HistoricalMarketStore | None = None,
    ) -> None:
        self.krx = krx
        self.engine = engine or BacktestEngine()
        self.production_exit = ProductionExitPolicyEngine(self.engine)
        self.multi_engine = MultiStrategyBacktestEngine(self.engine)
        self.exit_policy_research = ExitPolicyResearchEngine(self.engine)
        self.exit_policy_selector = ExitPolicySelector()
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
        prefer_single_symbol_cache: bool = True,
    ) -> tuple[int, int, int, int, int]:
        """Fill one stock + benchmark without full-market work on the request path.

        KRX's stock-by-date endpoint returns the entire market even when a backtest only
        needs one symbol.  The provider already persists that *raw* full-market payload
        to its gzip cache before ``stock_daily(..., code=...)`` filters the selected row.
        Therefore a single-stock cold start does not need to normalize ~1,000 peers or
        insert them into SQLite before the next batch can begin.

        This v0.21.4-A.1.1 path always requests the selected code only.  A true HTTP miss
        still seeds the provider's full-market raw cache, so a later symbol reuses the
        same downloaded day with zero additional KRX request.  Compact per-symbol/index
        history is persisted once after the range finishes.
        """
        dates = self._weekdays(start, end)
        processed: dict[str, set[str]] = {}
        work: list[tuple[str, date, bool]] = []
        for day in dates:
            key = self._compact(day)
            done: set[str] = set()
            if self._covered(stock_series, day):
                done.add("stock")
            else:
                work.append(("stock", day, self.krx.has_cached_day(market, day, "stock")))
            if self._covered(index_series, day):
                done.add("index")
            else:
                work.append(("index", day, self.krx.has_cached_day(market, day, "index")))
            processed[key] = done

        total_dates = len(dates)
        store_hits = sum(len(done) for done in processed.values())
        errors = 0
        concurrency = self.FETCH_CONCURRENCY
        clean_batches = 0
        cached_symbol_fast_path_hits = 0
        cached_index_fast_path_hits = 0
        network_symbol_fast_path_hits = 0
        network_index_fast_path_hits = 0
        today = self.krx._today_kst()  # noqa: SLF001 - same provider freshness policy
        today_compact = today.strftime("%Y%m%d")
        stats_before = self.krx.request_stats()

        estimated_network = sum(1 for _kind, _day, cached in work if not cached)
        budget_before = self.krx.assert_budget(estimated_network)

        def completed_dates() -> int:
            return sum(1 for done in processed.values() if len(done) == 2)

        def detail_payload(stats: dict[str, int], budget: dict[str, int | str]) -> dict[str, Any]:
            return {
                "history_store_hits": store_hits,
                "market_store_hits": store_hits,
                "estimated_network_requests": estimated_network,
                "network_requests": stats.get("network_requests", 0),
                "raw_cache_hits": stats.get("disk_hits", 0) + stats.get("memory_hits", 0) + stats.get("empty_marker_hits", 0),
                "cached_symbol_fast_path_hits": cached_symbol_fast_path_hits,
                "cached_index_fast_path_hits": cached_index_fast_path_hits,
                "network_symbol_fast_path_hits": network_symbol_fast_path_hits,
                "network_index_fast_path_hits": network_index_fast_path_hits,
                "market_wide_sqlite_promotions": 0,
                "raw_market_cache_seeded": network_symbol_fast_path_hits + network_index_fast_path_hits,
                "single_stock_fast_path": True,
                "cold_start_fast_path": True,
                "concurrency": concurrency,
                "retries": stats.get("retries", 0),
                "budget_used": budget.get("used", 0),
                "budget_limit": budget.get("safe_limit", 0),
                "budget_remaining": budget.get("remaining", 0),
            }

        self._emit(
            progress,
            stage="data_prepare",
            message=phase_label,
            current=completed_dates(),
            total=max(total_dates, 1),
            details=detail_payload({"network_requests": 0}, budget_before),
        )

        # Keep a continuous worker pool instead of stop-and-go batches.  The provider
        # has its own network semaphore/retry policy, so a batch barrier here only makes
        # every group wait for its slowest KRX response before the next group can start.
        # Continuous workers immediately take the next date when one request finishes.
        worker_count = min(self.FETCH_CONCURRENCY, max(len(work), 1))
        concurrency = worker_count
        queue: asyncio.Queue[tuple[str, date, bool]] = asyncio.Queue()
        for item in work:
            queue.put_nowait(item)

        completed_work = 0
        progress_stride = max(1, worker_count)

        async def fetch_one(kind: str, day: date, cached: bool) -> tuple[dict[str, Any], bool, bool]:
            if kind == "stock":
                try:
                    return await self.krx.stock_daily(market, day, code), cached, False
                except TypeError:
                    return await self.krx.stock_daily(market, day), cached, True
            return await self.krx.index_daily(market, day), cached, False

        async def worker() -> None:
            nonlocal errors
            nonlocal cached_symbol_fast_path_hits, cached_index_fast_path_hits
            nonlocal network_symbol_fast_path_hits, network_index_fast_path_hits
            nonlocal completed_work

            while True:
                try:
                    kind, day, cached = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                key = self._compact(day)
                try:
                    result = await fetch_one(kind, day, cached)
                except Exception:
                    errors += 1
                    processed[key].add(kind)
                else:
                    payload, was_cached, full_market_fallback = result
                    processed[key].add(kind)
                    if kind == "stock":
                        rows = list(payload.get("rows") or [])
                        selected = rows[0] if len(rows) == 1 else next(
                            (row for row in rows if str(row.get("code") or "").strip().upper() == code),
                            None,
                        )
                        if selected is not None and selected.get("close") is not None:
                            stock_series.rows[key] = selected
                        if day < today or self.krx._is_stable_empty_date(key):  # noqa: SLF001
                            stock_series.checked_dates.add(key)
                        if full_market_fallback and day < today:
                            self.market_store.put_stock_day(market, key, rows, stable=True)
                        if was_cached:
                            cached_symbol_fast_path_hits += 1
                        else:
                            network_symbol_fast_path_hits += 1
                    else:
                        rows = list(payload.get("rows") or [])
                        main = self.krx._select_main_index(rows, market) if rows else None  # noqa: SLF001
                        if main is not None:
                            index_series.rows[key] = main
                        if day < today or self.krx._is_stable_empty_date(key):  # noqa: SLF001
                            index_series.checked_dates.add(key)
                        if was_cached:
                            cached_index_fast_path_hits += 1
                        else:
                            network_index_fast_path_hits += 1
                finally:
                    queue.task_done()
                    completed_work += 1

                if completed_work % progress_stride == 0 or completed_work == len(work):
                    stats_now = self._stats_delta(stats_before, self.krx.request_stats())
                    budget_now = self.krx.budget_snapshot()
                    self._emit(
                        progress,
                        stage="data_prepare",
                        message=phase_label,
                        current=completed_dates(),
                        total=max(total_dates, 1),
                        details=detail_payload(stats_now, budget_now),
                    )

        if work:
            await asyncio.gather(*(worker() for _ in range(worker_count)))

        # One compact write per series.  The full-market HTTP payloads are already in
        # runtime/krx/*.json.gz and become the shared cache for every future symbol.
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
        return errors, store_hits, stats_after.get("network_requests", 0), estimated_network, cached_symbol_fast_path_hits

    async def _prepare_history(
        self,
        *,
        config: BacktestConfig,
        start: date,
        end: date,
        progress: ProgressCallback | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], date, dict[str, Any]]:
        """Prepare one-symbol history through the v0.21.4-A.1 fast path.

        Legacy per-symbol history is merged in memory instead of being re-imported into
        the market-wide SQLite tables on every click.  SQLite is read only for the
        bounded window that this run can actually need.
        """
        prepare_started = monotonic()
        max_start = start - timedelta(days=self.MAX_WARMUP_CALENDAR_DAYS)
        range_start = start - timedelta(days=self.INITIAL_WARMUP_CALENDAR_DAYS)
        max_start_key = self._compact(max_start)
        end_key = self._compact(end)

        legacy_started = monotonic()
        legacy_stock = self.history_store.load_stock(config.market, config.code)
        legacy_index = self.history_store.load_index(config.market)
        legacy_load_seconds = monotonic() - legacy_started

        market_store_started = monotonic()
        stock_series = self.market_store.stock_series(
            config.market,
            config.code,
            start_dd=max_start_key,
            end_dd=end_key,
        )
        index_series = self.market_store.index_series(
            config.market,
            start_dd=max_start_key,
            end_dd=end_key,
        )
        market_store_load_seconds = monotonic() - market_store_started

        # Legacy checked_dates are symbol-specific.  Merge only the window that could
        # be used by this run and avoid repeatedly bulk-importing it into SQLite.
        for key, row in legacy_stock.rows.items():
            if max_start_key <= key <= end_key:
                stock_series.rows[key] = row
        stock_series.checked_dates.update(
            key for key in legacy_stock.checked_dates if max_start_key <= key <= end_key
        )
        for key, row in legacy_index.rows.items():
            if max_start_key <= key <= end_key:
                index_series.rows[key] = row
        index_series.checked_dates.update(
            key for key in legacy_index.checked_dates if max_start_key <= key <= end_key
        )

        warnings: list[str] = []
        error_count = 0
        history_store_hits = 0
        network_requests = 0
        estimated_requests = 0
        cached_symbol_fast_path_hits = 0
        provider_before = self.krx.request_stats()

        fill_started = monotonic()
        errors, hits, requests, estimate, fast_hits = await self._ensure_range(
            code=config.code,
            market=config.market,
            start=range_start,
            end=end,
            stock_series=stock_series,
            index_series=index_series,
            progress=progress,
            phase_label="선택 종목 과거 데이터 준비 중",
            prefer_single_symbol_cache=True,
        )
        error_count += errors
        history_store_hits += hits
        network_requests += requests
        estimated_requests += estimate
        cached_symbol_fast_path_hits += fast_hits

        start_key = self._compact(start)
        prestart_count = sum(1 for key in stock_series.rows if key < start_key)
        while prestart_count < self.REQUIRED_PRESTART_ROWS and range_start > max_start:
            new_start = max(max_start, range_start - timedelta(days=self.WARMUP_EXTENSION_DAYS))
            extension_end = range_start - timedelta(days=1)
            errors, hits, requests, estimate, fast_hits = await self._ensure_range(
                code=config.code,
                market=config.market,
                start=new_start,
                end=extension_end,
                stock_series=stock_series,
                index_series=index_series,
                progress=progress,
                phase_label=f"지표 워밍업 확보 중 · {prestart_count}/{self.REQUIRED_PRESTART_ROWS} 거래일",
                prefer_single_symbol_cache=True,
            )
            error_count += errors
            history_store_hits += hits
            network_requests += requests
            estimated_requests += estimate
            cached_symbol_fast_path_hits += fast_hits
            range_start = new_start
            prestart_count = sum(1 for key in stock_series.rows if key < start_key)
        fill_seconds = monotonic() - fill_started

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
        total_prepare_seconds = monotonic() - prepare_started
        return stock_rows, index_rows, warnings, range_start, {
            "single_stock_fast_path": True,
            "cold_start_fast_path": True,
            "concurrency": self.FETCH_CONCURRENCY,
            "market_wide_sqlite_promotions": 0,
            "history_store_hits": history_store_hits,
            "market_store_hits": history_store_hits,
            "legacy_rows_imported": 0,
            "raw_cache_hits": cache_hits,
            "cached_symbol_fast_path_hits": cached_symbol_fast_path_hits,
            "cache_reuse_pct": cache_reuse_pct,
            "estimated_network_requests": estimated_requests,
            "network_requests": provider_delta.get("network_requests", network_requests),
            "retries": provider_delta.get("retries", 0),
            "warmup_rows": prestart_count,
            "legacy_load_ms": round(legacy_load_seconds * 1000.0, 2),
            "market_store_load_ms": round(market_store_load_seconds * 1000.0, 2),
            "history_fill_ms": round(fill_seconds * 1000.0, 2),
            "data_prepare_ms": round(total_prepare_seconds * 1000.0, 2),
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

        pullback_resolution = self.production_exit.registry.resolve(StrategyName.PULLBACK)
        production_trade_fallbacks = 0

        def simulate_actual_trade(*, signal: dict[str, Any], stock_rows: list[dict[str, Any]], config: BacktestConfig):
            nonlocal production_trade_fallbacks
            trade, exit_index, used_resolution = self.production_exit.simulate_trade(
                signal=signal,
                stock_rows=stock_rows,
                config=config,
                strategy=StrategyName.PULLBACK,
            )
            if used_resolution.fallback_used and used_resolution.fallback_reason == "SELECTED_POLICY_UNUSABLE_FOR_TRADE":
                production_trade_fallbacks += 1
            return trade, exit_index

        result = await asyncio.to_thread(
            self.engine.run,
            stock_rows=stock_rows,
            index_rows=index_rows,
            config=config,
            progress_callback=engine_progress,
            actual_trade_simulator=simulate_actual_trade,
        )
        calculation_seconds = monotonic() - calculation_started
        total_seconds = monotonic() - started

        result["version"] = "0.19.6"
        result["production_exit_policy"] = {
            **pullback_resolution.to_dict(),
            "trade_fallbacks": production_trade_fallbacks,
            "cache_token": self.production_exit.registry.cache_token(),
        }
        result["historical_policy"] = self.production_exit.historical_policy_metadata(pullback_resolution)
        if pullback_resolution.policy_id == "TARGET1_FULL_EXIT":
            result["config"]["target_policy"] = "TARGET_1_FULL_EXIT"
        else:
            result["config"]["target_policy"] = "PRODUCTION_PROFIT_PROTECTION_AFTER_TARGET2"
            result["methodology"]["target"] = (
                "검증된 Production Exit 정책을 사용합니다. 1차 목표는 milestone이며 2차 목표 도달 뒤 "
                f"{pullback_resolution.policy_id} 수익 보호 기준을 적용합니다."
            )
        result["problem_solver"] = build_problem_solver(result, config)
        result["data_window"] = {
            "requested_start": config.start_date,
            "requested_end": config.end_date,
            "warmup_start": warmup_start.isoformat(),
            "first_stock_date": str(stock_rows[0].get("date") or ""),
            "last_stock_date": str(stock_rows[-1].get("date") or ""),
            "stock_rows": len(stock_rows),
            "index_rows": len(index_rows),
            "cache_note": "Cold Start Fast Path를 사용합니다. KRX가 새 날짜를 반환해도 선택 종목만 정규화하며, 전체 시장 원본은 provider raw cache에 저장해 다음 종목이 재사용합니다. 시장 전체 SQLite 재삽입은 분석 경로에서 수행하지 않습니다.",
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

    async def run_exit_policy_audit(
        self,
        config: BacktestConfig,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Research-only audit of post-Target2 exit policies across all strategies."""
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

        self._emit(progress, stage="queued", message="Exit 정책 연구 준비 중", current=0, total=1, details={})
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
            self.exit_policy_research.run,
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
            "cache_note": "단일 종목 Fast Path로 과거 데이터를 한 번 준비한 뒤 Exit 정책 연구가 같은 데이터셋을 공유합니다.",
        }
        result["performance"] = {
            "data_prepare_seconds": round(data_seconds, 3),
            "exit_policy_calculation_seconds": round(calculation_seconds, 3),
            "total_seconds": round(total_seconds, 3),
            **fetch_stats,
        }
        result["warnings"] = warnings
        self._emit(
            progress,
            stage="completed",
            message="Exit 정책 연구 완료",
            current=1,
            total=1,
            details=result["performance"],
        )
        return result

    async def run_exit_policy_selection(
        self,
        configs: list[BacktestConfig],
        *,
        selection_config: ExitPolicySelectionConfig | None = None,
        post_target2_research_days: int = DEFAULT_POST_TARGET2_RESEARCH_DAYS,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Validate and select research Exit policies across several stocks.

        This is deliberately research-only. It reuses one KRX session and each stock's
        Market Store / raw cache, aggregates additive trade primitives, and writes a
        reproducible report. Production Scanner/Action Plan policies are not changed.
        """
        started = monotonic()
        if len(configs) < 2 or len(configs) > 30:
            raise ValueError("Exit 정책 선택 검증 종목은 2~30개여야 합니다.")
        selector = ExitPolicySelector(selection_config or ExitPolicySelectionConfig())
        if post_target2_research_days < 1 or post_target2_research_days > 240:
            raise ValueError("Target2 이후 연구 보유기간은 1~240 거래일 범위여야 합니다.")

        first = configs[0]
        common = (
            first.start_date,
            first.end_date,
            first.initial_capital,
            first.max_holding_days,
            first.round_trip_cost_pct,
        )
        normalized: list[BacktestConfig] = []
        for config in configs:
            if (
                config.start_date,
                config.end_date,
                config.initial_capital,
                config.max_holding_days,
                config.round_trip_cost_pct,
            ) != common:
                raise ValueError("정책 선택 검증 종목들은 동일한 기간/비용/보유기간 설정을 사용해야 합니다.")
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
            normalized.append(config)

        self._emit(
            progress,
            stage="exit_policy_selection_queued",
            message="전략별 Exit 정책 선택 검증 준비 중",
            current=0,
            total=len(normalized),
            details={"stocks": len(normalized)},
        )
        audits: list[dict[str, Any]] = []
        warnings: list[str] = []
        total_network_requests = 0
        data_prepare_seconds = 0.0
        calculation_seconds = 0.0

        await self.krx.open_session()
        try:
            for position, config in enumerate(normalized, start=1):
                start = self._parse_iso(config.start_date, "시작일")
                end = self._parse_iso(config.end_date, "종료일")

                def stock_progress(payload: dict[str, Any], *, _position: int = position, _config: BacktestConfig = config) -> None:
                    details = dict(payload.get("details") or {})
                    details.update({
                        "selection_stock_index": _position,
                        "selection_stock_total": len(normalized),
                        "selection_code": _config.code,
                        "selection_market": _config.market,
                    })
                    self._emit(progress, **{**payload, "details": details})

                data_started = monotonic()
                stock_rows, index_rows, stock_warnings, warmup_start, fetch_stats = await self._prepare_history(
                    config=config,
                    start=start,
                    end=end,
                    progress=stock_progress,
                )
                data_prepare_seconds += monotonic() - data_started
                total_network_requests += int(fetch_stats.get("network_requests", 0))
                warnings.extend(f"{config.code}: {message}" for message in stock_warnings)

                calc_started = monotonic()
                audit = await asyncio.to_thread(
                    self.exit_policy_research.run,
                    stock_rows=stock_rows,
                    index_rows=index_rows,
                    config=config,
                    post_target2_research_days=post_target2_research_days,
                    include_holding_policy_variants=True,
                    progress_callback=stock_progress,
                )
                calculation_seconds += monotonic() - calc_started
                audit["data_window"] = {
                    "requested_start": config.start_date,
                    "requested_end": config.end_date,
                    "warmup_start": warmup_start.isoformat(),
                    "stock_rows": len(stock_rows),
                    "index_rows": len(index_rows),
                }
                audits.append(audit)
                self._emit(
                    progress,
                    stage="exit_policy_selection_stock_completed",
                    message=f"{config.code} Exit 정책 연구 완료",
                    current=position,
                    total=len(normalized),
                    details={"code": config.code, "market": config.market},
                )
        finally:
            await self.krx.close_session()

        selection_started = monotonic()
        result = await asyncio.to_thread(selector.run, audits)
        selection_seconds = monotonic() - selection_started
        result["period"] = {"start": first.start_date, "end": first.end_date}
        result["stocks"] = [{"code": config.code, "market": config.market} for config in normalized]
        result["research_config"] = {
            "max_holding_days": first.max_holding_days,
            "post_target2_research_days": post_target2_research_days,
            "round_trip_cost_pct": first.round_trip_cost_pct,
            "minimum_stock_count": selector.config.minimum_stock_count,
            "minimum_total_trades": selector.config.minimum_total_trades,
        }
        report_path = await asyncio.to_thread(save_selection_report, result)
        result["report"] = {
            "saved": True,
            "filename": report_path.name,
            "runtime_area": "backend/runtime/research",
        }
        result["performance"] = {
            "data_prepare_seconds": round(data_prepare_seconds, 3),
            "exit_policy_calculation_seconds": round(calculation_seconds, 3),
            "selection_seconds": round(selection_seconds, 3),
            "total_seconds": round(monotonic() - started, 3),
            "network_requests": total_network_requests,
        }
        result["warnings"] = warnings
        self._emit(
            progress,
            stage="completed",
            message="전략별 Exit 정책 선택 검증 완료",
            current=len(normalized),
            total=len(normalized),
            details=result["performance"],
        )
        return result

    async def run_exit_policy_validation_runner(
        self,
        runner_config: ExitPolicyValidationRunnerConfig,
        *,
        force_refresh: bool = False,
        progress: ProgressCallback | None = None,
        checkpoint_store: ExitPolicyValidationCheckpoint | None = None,
    ) -> dict[str, Any]:
        """Run B.1 selection on a reproducible, local-only Market Store sample.

        The runner never fills missing history from KRX.  If the local Market Store is
        insufficient it reports that condition instead of turning a research action
        into hundreds of network requests.  Completed per-stock audits are checkpointed
        and reused when the exact same research signature is run again.
        """
        started = monotonic()
        runner_config.validate()
        start = self._parse_iso(runner_config.start_date, "시작일")
        end = self._parse_iso(runner_config.end_date, "종료일")
        if start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if (end - start).days > self.MAX_CALENDAR_DAYS:
            raise ValueError("한 번에 최대 5년까지 검증할 수 있습니다.")

        checkpoint_store = checkpoint_store or ExitPolicyValidationCheckpoint()

        start_dd = self._compact(start)
        end_dd = self._compact(end)
        market_availability: dict[str, Any] = {}
        candidate_groups: dict[str, list[dict[str, Any]]] = {}
        for market in runner_config.markets:
            availability = await asyncio.to_thread(
                self.market_store.research_candidates,
                market,
                start_dd,
                end_dd,
                minimum_coverage_pct=runner_config.minimum_coverage_pct,
                limit=runner_config.max_stocks,
            )
            market_availability[market] = availability
            # A missing benchmark would silently change market-regime conditions, so
            # do not use that market until its local index history is also sufficiently covered.
            if float(availability.get("index_coverage_pct") or 0.0) + 1e-9 < runner_config.minimum_coverage_pct:
                candidate_groups[market] = []
            else:
                candidate_groups[market] = list(availability.get("candidates") or [])

        selected = interleave_market_candidates(
            candidate_groups,
            runner_config.markets,
            runner_config.max_stocks,
        )
        signature = validation_sample_signature(runner_config, selected)
        if force_refresh:
            checkpoint_store.clear(signature)
        checkpoint = None if force_refresh else checkpoint_store.load(signature)
        audits: list[dict[str, Any]] = list((checkpoint or {}).get("audits") or [])
        completed = {
            f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').upper()}"
            for row in audits
        }
        if len(selected) < 2:
            return {
                "version": VALIDATION_RUNNER_VERSION,
                "research_only": True,
                "production_policy_changed": False,
                "status": "DATA_REQUIRED",
                "message": "현재 Market Store만으로 Exit 정책 검증에 필요한 종목/시장지수 표본이 부족합니다.",
                "signature": signature,
                "period": {"start": runner_config.start_date, "end": runner_config.end_date},
                "market_availability": market_availability,
                "selected_stocks": selected,
                "checkpoint": {"reused_stocks": len(audits), "completed_stocks": len(audits)},
                "performance": {"total_seconds": round(monotonic() - started, 3), "network_requests": 0},
            }

        self._emit(
            progress,
            stage="exit_policy_validation_sample",
            message="로컬 Market Store에서 검증 표본을 확정했습니다.",
            current=len(audits),
            total=len(selected),
            details={"selected_stocks": len(selected), "checkpoint_reused": len(audits), "network_requests": 0},
        )

        data_load_seconds = 0.0
        calculation_seconds = 0.0
        excluded: list[dict[str, Any]] = []
        warmup_start = max(start - timedelta(days=self.MAX_WARMUP_CALENDAR_DAYS), date(1990, 1, 1))
        warmup_dd = self._compact(warmup_start)
        start_key = self._compact(start)
        total = len(selected)

        for position, candidate in enumerate(selected, start=1):
            code = normalize_stock_code(str(candidate.get("code") or ""))
            market = str(candidate.get("market") or "").upper()
            key = f"{market}:{code}"
            if key in completed:
                self._emit(
                    progress,
                    stage="exit_policy_validation_checkpoint_hit",
                    message=f"{code} 기존 연구 결과 재사용",
                    current=position,
                    total=total,
                    details={"code": code, "market": market, "checkpoint_hit": True, "network_requests": 0},
                )
                continue

            load_started = monotonic()
            stock_series, index_series = await asyncio.gather(
                asyncio.to_thread(self.market_store.stock_series, market, code, warmup_dd, end_dd),
                asyncio.to_thread(self.market_store.index_series, market, warmup_dd, end_dd),
            )
            data_load_seconds += monotonic() - load_started
            stock_rows = [row for key_dd, row in stock_series.rows.items() if warmup_dd <= key_dd <= end_dd]
            index_rows = [row for key_dd, row in index_series.rows.items() if warmup_dd <= key_dd <= end_dd]
            stock_rows.sort(key=self._row_date)
            index_rows.sort(key=self._row_date)
            prestart_count = sum(1 for key_dd in stock_series.rows if key_dd < start_key)
            requested_rows = sum(1 for key_dd in stock_series.rows if start_key <= key_dd <= end_dd)

            if prestart_count < self.REQUIRED_PRESTART_ROWS or requested_rows <= 0:
                excluded.append({
                    "code": code,
                    "market": market,
                    "reason": "워밍업 또는 요청기간 로컬 데이터가 부족합니다.",
                    "prestart_rows": prestart_count,
                    "requested_rows": requested_rows,
                })
                self._emit(
                    progress,
                    stage="exit_policy_validation_stock_skipped",
                    message=f"{code} 로컬 데이터 부족으로 제외",
                    current=position,
                    total=total,
                    details={"code": code, "market": market, "network_requests": 0},
                )
                continue

            config = BacktestConfig(
                code=code,
                market=market,
                start_date=runner_config.start_date,
                end_date=runner_config.end_date,
                initial_capital=runner_config.initial_capital,
                max_holding_days=runner_config.max_holding_days,
                round_trip_cost_pct=runner_config.round_trip_cost_pct,
            )

            def stock_progress(payload: dict[str, Any], *, _position: int = position, _code: str = code, _market: str = market) -> None:
                details = dict(payload.get("details") or {})
                details.update({
                    "validation_stock_index": _position,
                    "validation_stock_total": total,
                    "validation_code": _code,
                    "validation_market": _market,
                    "network_requests": 0,
                })
                self._emit(progress, **{**payload, "details": details})

            calc_started = monotonic()
            audit = await asyncio.to_thread(
                self.exit_policy_research.run,
                stock_rows=stock_rows,
                index_rows=index_rows,
                config=config,
                post_target2_research_days=runner_config.post_target2_research_days,
                include_holding_policy_variants=True,
                progress_callback=stock_progress,
            )
            calculation_seconds += monotonic() - calc_started
            audit["data_window"] = {
                "requested_start": runner_config.start_date,
                "requested_end": runner_config.end_date,
                "warmup_start": warmup_start.isoformat(),
                "stock_rows": len(stock_rows),
                "index_rows": len(index_rows),
                "local_only": True,
            }
            audits.append(audit)
            completed.add(key)
            await asyncio.to_thread(checkpoint_store.save, signature, runner_config, audits)
            self._emit(
                progress,
                stage="exit_policy_validation_stock_completed",
                message=f"{code} Exit 정책 검증 완료",
                current=position,
                total=total,
                details={"code": code, "market": market, "checkpoint_saved": True, "network_requests": 0},
            )

        selector_config = ExitPolicySelectionConfig(
            minimum_stock_count=runner_config.minimum_stock_count,
            minimum_total_trades=runner_config.minimum_total_trades,
        )
        selection_started = monotonic()
        selector = ExitPolicySelector(selector_config)
        if len(audits) < 2:
            return {
                "version": VALIDATION_RUNNER_VERSION,
                "research_only": True,
                "production_policy_changed": False,
                "status": "DATA_REQUIRED",
                "message": "검증 가능한 로컬 종목이 2개 미만입니다.",
                "signature": signature,
                "period": {"start": runner_config.start_date, "end": runner_config.end_date},
                "market_availability": market_availability,
                "selected_stocks": selected,
                "excluded_stocks": excluded,
                "checkpoint": {"reused_stocks": len((checkpoint or {}).get("audits") or []), "completed_stocks": len(audits)},
                "performance": {
                    "market_store_load_seconds": round(data_load_seconds, 3),
                    "exit_policy_calculation_seconds": round(calculation_seconds, 3),
                    "selection_seconds": 0.0,
                    "total_seconds": round(monotonic() - started, 3),
                    "network_requests": 0,
                },
            }

        result = await asyncio.to_thread(selector.run, audits)
        selection_seconds = monotonic() - selection_started
        status_counts = result.get("status_counts") or {}
        report = {
            **result,
            "runner_version": VALIDATION_RUNNER_VERSION,
            "status": "COMPLETED",
            "signature": signature,
            "period": {"start": runner_config.start_date, "end": runner_config.end_date},
            "validation_config": runner_config.signature_payload(),
            "market_availability": market_availability,
            "selected_stocks": selected,
            "validated_stocks": [{"code": row.get("code"), "market": row.get("market")} for row in audits],
            "excluded_stocks": excluded,
            "checkpoint": {
                "reused_stocks": len((checkpoint or {}).get("audits") or []),
                "completed_stocks": len(audits),
                "resumable": True,
            },
            "summary": {
                "selected": int(status_counts.get("SELECTED", 0)),
                "baseline_better": int(status_counts.get("BASELINE_BETTER", 0)),
                "unresolved": int(status_counts.get("UNRESOLVED", 0)),
                "insufficient_sample": int(status_counts.get("INSUFFICIENT_SAMPLE", 0)),
                "production_policy_changed": False,
            },
            "performance": {
                "market_store_load_seconds": round(data_load_seconds, 3),
                "exit_policy_calculation_seconds": round(calculation_seconds, 3),
                "selection_seconds": round(selection_seconds, 3),
                "total_seconds": round(monotonic() - started, 3),
                "network_requests": 0,
            },
        }
        report_path = await asyncio.to_thread(checkpoint_store.save_report, report)
        report["report"] = {
            "saved": True,
            "filename": report_path.name,
            "runtime_area": "backend/runtime/research",
        }
        self._emit(
            progress,
            stage="completed",
            message="Exit 정책 검증 리포트 완료",
            current=total,
            total=total,
            details={**report["performance"], "production_policy_changed": False},
        )
        return report

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
            "cache_note": "단일 종목 Fast Path로 선택 종목과 시장지수 데이터를 한 번 준비하고 10개 전략이 같은 데이터셋을 공유합니다. raw KRX cache가 있으면 전체 시장 재적재 없이 선택 종목만 추출합니다.",
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

