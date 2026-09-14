from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.models import BacktestConfig
from app.backtest.multi_strategy import MultiStrategyBacktestEngine, SUPPORTED_STRATEGIES
from app.backtest.selector import build_condition_state, current_readiness, strategy_guide
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError
from app.strategy.context import regime_from_index

ProgressCallback = Callable[[dict[str, Any]], None]


class StockScannerService:
    """EOD market scanner built on the shared KRX HistoricalMarketStore.

    v0.21 deliberately uses a two-stage pipeline:
    1) inspect the whole latest market and quickly shortlist liquid ordinary stocks;
    2) run the existing 10-strategy historical selector only on the strongest current candidates.

    Internal ranking scores are ordering aids, not upward probabilities and are never
    presented to the user as probabilities.
    """

    VERSION = "0.21.0"
    HISTORY_CALENDAR_DAYS = 485  # ~1y evidence + enough 60-row warmup
    EVIDENCE_CALENDAR_DAYS = 365
    QUICK_LIMIT_PER_MARKET = 160
    DEEP_LIMIT = 18
    EXTRA_RESULT_LIMIT = 10
    MIN_HISTORY_ROWS = 61
    FETCH_CONCURRENCY = 8
    CACHE_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "scanner"

    def __init__(
        self,
        krx: KrxProvider,
        *,
        market_store: HistoricalMarketStore | None = None,
        engine: BacktestEngine | None = None,
    ) -> None:
        self.krx = krx
        self.market_store = market_store or HistoricalMarketStore()
        self.engine = engine or BacktestEngine()
        self.multi = MultiStrategyBacktestEngine(self.engine)

    @staticmethod
    def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
        if callback is not None:
            callback(payload)

    @staticmethod
    def _compact(value: date) -> str:
        return value.strftime("%Y%m%d")

    @staticmethod
    def _iso(compact: str) -> str:
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}" if len(compact) == 8 else compact

    @staticmethod
    def _weekdays(start: date, end: date) -> list[date]:
        result: list[date] = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                result.append(cursor)
            cursor += timedelta(days=1)
        return result

    @staticmethod
    def _parse_as_of(value: str | None, today: date) -> date:
        if not value:
            return today - timedelta(days=1)
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("기준일은 YYYY-MM-DD 형식이어야 합니다.") from exc
        return min(parsed, today - timedelta(days=1))

    @classmethod
    def _cache_path(cls, scope: str, stable_end: date, candidate_limit: int) -> Path:
        cls.CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        return cls.CACHE_ROOT / f"scanner_{scope.lower()}_{stable_end.isoformat()}_{candidate_limit}_{cls.VERSION}.json"

    @classmethod
    def _load_cache(cls, scope: str, stable_end: date, candidate_limit: int) -> dict[str, Any] | None:
        path = cls._cache_path(scope, stable_end, candidate_limit)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("version") != cls.VERSION:
            return None
        payload["scanner_cache_hit"] = True
        return payload

    @classmethod
    def _save_cache(cls, scope: str, stable_end: date, candidate_limit: int, payload: dict[str, Any]) -> None:
        path = cls._cache_path(scope, stable_end, candidate_limit)
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            # Scanner result caching is an optimization only; analysis must still return.
            pass

    @staticmethod
    def _stats_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        keys = set(before) | set(after)
        return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}

    async def _ensure_market_history(
        self,
        *,
        market: str,
        start: date,
        end: date,
        progress: ProgressCallback | None,
        phase_index: int,
        phase_total: int,
    ) -> dict[str, int]:
        dates = self._weekdays(start, end)
        work: list[tuple[str, date]] = []
        for day in dates:
            key = self._compact(day)
            if not self.market_store.day_complete(market, key, "stock"):
                work.append(("stock", day))
            if not self.market_store.day_complete(market, key, "index"):
                work.append(("index", day))

        total = len(dates) * 2
        reused = total - len(work)
        estimated = sum(1 for kind, day in work if not self.krx.has_cached_day(market, day, kind))
        self.krx.assert_budget(estimated)
        before = self.krx.request_stats()
        completed = reused
        errors = 0

        self._emit(
            progress,
            stage="scanner_data_prepare",
            message=f"{market} 시장 데이터 준비 중",
            current=phase_index - 1,
            total=phase_total,
            details={
                "market": market,
                "reused_items": reused,
                "estimated_network_requests": estimated,
                "items_done": completed,
                "items_total": total,
            },
        )

        for offset in range(0, len(work), self.FETCH_CONCURRENCY):
            batch = work[offset : offset + self.FETCH_CONCURRENCY]

            async def fetch_one(kind: str, day: date) -> dict[str, Any]:
                if kind == "stock":
                    return await self.krx.stock_daily(market, day)
                return await self.krx.index_daily(market, day)

            results = await asyncio.gather(
                *(fetch_one(kind, day) for kind, day in batch),
                return_exceptions=True,
            )
            for (kind, day), result in zip(batch, results, strict=True):
                completed += 1
                key = self._compact(day)
                if isinstance(result, Exception):
                    errors += 1
                    continue
                if kind == "stock":
                    rows = list(result.get("rows") or [])
                    self.market_store.put_stock_day(market, key, rows, stable=True)
                else:
                    rows = list(result.get("rows") or [])
                    main = self.krx._select_main_index(rows, market) if rows else None  # noqa: SLF001
                    self.market_store.put_index_day(market, key, main, stable=True)

            self._emit(
                progress,
                stage="scanner_data_prepare",
                message=f"{market} 시장 데이터 준비 중",
                current=phase_index - 1,
                total=phase_total,
                details={
                    "market": market,
                    "reused_items": reused,
                    "estimated_network_requests": estimated,
                    "items_done": completed,
                    "items_total": total,
                },
            )

        delta = self._stats_delta(before, self.krx.request_stats())
        return {
            "store_hits": reused,
            "estimated_network_requests": estimated,
            "network_requests": int(delta.get("network_requests", 0)),
            "raw_cache_hits": int(delta.get("disk_hits", 0) + delta.get("memory_hits", 0) + delta.get("empty_marker_hits", 0)),
            "errors": errors,
        }

    @staticmethod
    def _special_reason(row: dict[str, Any]) -> str | None:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        upper_name = name.upper()
        section = str(row.get("section") or "").upper()
        if not re.fullmatch(r"\d{6}", code):
            return "일반 6자리 주식코드 아님"
        if not name:
            return "종목명 없음"
        if "스팩" in name or "SPAC" in upper_name:
            return "SPAC"
        if "우선주" in name or re.search(r"우(?:B|C|\d+)?$", name, flags=re.IGNORECASE):
            return "우선주"
        if "ETF" in section or "ETN" in section or "ETF" in upper_name or " ETN" in upper_name:
            return "ETF/ETN"
        close = row.get("close")
        volume = row.get("volume")
        trade_value = row.get("trade_value")
        if close is None or float(close) <= 0:
            return "가격 데이터 없음"
        if volume is None or float(volume) <= 0 or trade_value is None or float(trade_value) <= 0:
            return "거래정지 또는 거래 없음"
        return None

    @staticmethod
    def _row_date(row: dict[str, Any]) -> str:
        return str(row.get("date") or "").replace("-", "")

    def _quick_current_candidate(
        self,
        *,
        market: str,
        latest_date: str,
        row: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if len(stock_rows) < self.MIN_HISTORY_ROWS:
            return None
        rows = sorted(stock_rows, key=self._row_date)
        indices = sorted(index_rows, key=self._row_date)
        config = BacktestConfig(
            code=str(row.get("code") or ""),
            market=market,
            start_date=self._iso(latest_date),
            end_date=self._iso(latest_date),
            initial_capital=10_000_000,
            max_holding_days=20,
            round_trip_cost_pct=0.0,
        )
        snapshot = self.engine._signal_snapshot(  # noqa: SLF001 - shared live/backtest snapshot by design
            stock_rows=rows,
            index_rows=indices,
            index=len(rows) - 1,
            config=config,
        )
        if snapshot is None:
            return None

        evaluations = list((snapshot.get("evaluations") or {}).values())
        evaluations.sort(
            key=lambda item: (bool(getattr(item, "eligible", False)), int(getattr(item, "score", 0) or 0)),
            reverse=True,
        )
        best: dict[str, Any] | None = None
        for evaluation in evaluations[:3]:
            strategy = evaluation.strategy
            condition_state = build_condition_state(
                evaluation,
                data=snapshot.get("strategy_input"),
                technical=snapshot.get("technical") or {},
            )
            risk_plan = self.multi._current_risk_plan(snapshot, strategy)  # noqa: SLF001
            current = current_readiness(
                evaluation=evaluation,
                risk_plan=risk_plan,
                condition_state=condition_state,
            )
            score = float(current.get("internal_score") or 0.0)
            if best is None or score > float(best["current"].get("internal_score") or 0.0):
                best = {
                    "strategy": strategy.value,
                    "guide": strategy_guide(strategy),
                    "current": current,
                }
        if best is None:
            return None
        current = best["current"]
        total = int(current.get("total") or 0)
        passed = int(current.get("passed") or 0)
        ratio = passed / total if total else 0.0
        risk_penalty = 18.0 if current.get("risk_warning") else 0.0
        quick_score = float(current.get("internal_score") or 0.0) + ratio * 20.0 - risk_penalty
        return {
            "code": str(row.get("code") or ""),
            "name": str(row.get("name") or ""),
            "market": market,
            "latest_date": latest_date,
            "current_price": row.get("close"),
            "trade_value": row.get("trade_value"),
            "market_cap": row.get("market_cap"),
            "history_points": len(rows),
            "quick_strategy": best["strategy"],
            "quick_guide": best["guide"],
            "quick_current": current,
            "quick_score": round(quick_score, 4),
        }

    def _deep_candidate(
        self,
        *,
        item: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        latest = date.fromisoformat(self._iso(str(item["latest_date"])))
        evidence_start = latest - timedelta(days=self.EVIDENCE_CALENDAR_DAYS)
        config = BacktestConfig(
            code=str(item["code"]),
            market=str(item["market"]),
            start_date=evidence_start.isoformat(),
            end_date=latest.isoformat(),
            initial_capital=10_000_000,
            max_holding_days=20,
            round_trip_cost_pct=0.0,
        )
        result = self.multi.run(stock_rows=stock_rows, index_rows=index_rows, config=config)
        recommendation = result.get("recommendation") or {}
        strategy = recommendation.get("strategy")
        if not strategy:
            return None
        strategy_row = next((row for row in result.get("strategies") or [] if row.get("strategy") == strategy), None)
        if strategy_row is None:
            return None
        current = strategy_row.get("current") or {}
        hist = strategy_row.get("historical_fit") or {}
        metrics = strategy_row.get("historical_metrics") or {}
        total = int(current.get("total") or 0)
        passed = int(current.get("passed") or 0)
        ratio = passed / total if total else 0.0
        action = str(recommendation.get("action") or "NO_TRADE")
        hist_status = str(hist.get("status") or "INSUFFICIENT")
        risk_warning = bool(current.get("risk_warning"))

        action_weight = {"ENTRY_CANDIDATE": 40.0, "WAIT": 22.0, "NEEDS_VALIDATION": 10.0, "NO_TRADE": 0.0}.get(action, 0.0)
        history_weight = {"GOOD": 24.0, "FAIR": 15.0, "INSUFFICIENT": 5.0, "WEAK": -8.0}.get(hist_status, 0.0)
        selector_score = float(strategy_row.get("selector_score") or 0.0)
        internal_rank = action_weight + ratio * 35.0 + history_weight + min(25.0, max(0.0, selector_score) * 0.25)
        if risk_warning:
            internal_rank -= 18.0

        if action == "ENTRY_CANDIDATE":
            candidate_state = "READY"
            candidate_label = "진입 후보에 가까움"
        elif action == "WAIT" and ratio >= 0.65 and hist_status in {"GOOD", "FAIR"}:
            candidate_state = "WATCH"
            candidate_label = "조금 더 기다릴 후보"
        elif action == "NEEDS_VALIDATION" and ratio >= 0.75:
            candidate_state = "VALIDATION"
            candidate_label = "현재 조건은 좋지만 과거 근거 추가 필요"
        else:
            candidate_state = "EXCLUDED"
            candidate_label = "현재 우선 후보 아님"

        guide = strategy_row.get("guide") or strategy_guide(strategy)
        missing_details = list(current.get("unmet_details") or [])
        user_action = recommendation.get("user_action") or {}
        return {
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "data_date": self._iso(str(item["latest_date"])),
            "current_price": item.get("current_price"),
            "candidate_state": candidate_state,
            "candidate_label": candidate_label,
            "strategy": strategy,
            "strategy_easy_name": recommendation.get("strategy_easy_name") or guide.get("easy_name"),
            "strategy_name": recommendation.get("strategy_label") or guide.get("professional_name"),
            "strategy_description": recommendation.get("strategy_description") or guide.get("description"),
            "action": action,
            "action_label": recommendation.get("action_label"),
            "headline": recommendation.get("headline"),
            "reason": recommendation.get("reason"),
            "conditions": {
                "passed": passed,
                "total": total,
                "missing": int(current.get("missing") or max(0, total - passed)),
                "top_missing": missing_details[:3],
            },
            "risk": {
                "status": current.get("risk_status"),
                "warning": risk_warning,
                "warnings": list(current.get("warnings") or []),
            },
            "historical_fit": {
                "status": hist_status,
                "label": hist.get("label"),
                "summary": hist.get("summary"),
                "trades": int(metrics.get("trades") or 0),
            },
            "user_action": {
                "title": user_action.get("title"),
                "detail": user_action.get("detail"),
                "next_transition": user_action.get("next_transition"),
            },
            "internal_rank": round(internal_rank, 4),
        }

    async def run(
        self,
        *,
        market_scope: str = "ALL",
        as_of_date: str | None = None,
        candidate_limit: int = 5,
        force_refresh: bool = False,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        scope = market_scope.upper().strip()
        if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
            raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")
        candidate_limit = max(1, min(int(candidate_limit), 10))
        today = self.krx._today_kst()  # noqa: SLF001 - same EOD freshness boundary as provider
        stable_end = self._parse_as_of(as_of_date, today)

        if not force_refresh:
            cached = self._load_cache(scope, stable_end, candidate_limit)
            if cached is not None:
                self._emit(progress, stage="scanner_cache", message="오늘의 Scanner 결과 재사용", current=1, total=1, details={"cache_hit": True})
                return cached

        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
        start = stable_end - timedelta(days=self.HISTORY_CALENDAR_DAYS)
        provider_before = self.krx.request_stats()
        aggregate_sync = {"store_hits": 0, "estimated_network_requests": 0, "network_requests": 0, "raw_cache_hits": 0, "errors": 0}

        await self.krx.open_session()
        try:
            for position, market in enumerate(markets, start=1):
                sync = await self._ensure_market_history(
                    market=market,
                    start=start,
                    end=stable_end,
                    progress=progress,
                    phase_index=position,
                    phase_total=len(markets),
                )
                for key in aggregate_sync:
                    aggregate_sync[key] += int(sync.get(key, 0))

            universe_rows: list[dict[str, Any]] = []
            latest_dates: dict[str, str] = {}
            market_summaries: list[dict[str, Any]] = []
            index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
            prefiltered_by_market: dict[str, list[dict[str, Any]]] = {}
            special_excluded = 0
            liquidity_filtered = 0

            for market in markets:
                end_key = self._compact(stable_end)
                latest_date = self.market_store.latest_complete_date(market, "stock", end_key)
                if not latest_date:
                    continue
                latest_dates[market] = self._iso(latest_date)
                day_rows = self.market_store.stock_day_rows(market, latest_date)
                universe_rows.extend(day_rows)

                ordinary: list[dict[str, Any]] = []
                for row in day_rows:
                    reason = self._special_reason(row)
                    if reason is not None:
                        special_excluded += 1
                        continue
                    if float(row.get("trade_value") or 0) < self.engine.LIQUIDITY_THRESHOLD:
                        liquidity_filtered += 1
                        continue
                    ordinary.append(row)
                ordinary.sort(key=lambda row: (float(row.get("trade_value") or 0), float(row.get("market_cap") or 0)), reverse=True)
                prefiltered_by_market[market] = ordinary[: self.QUICK_LIMIT_PER_MARKET]

                index_series = self.market_store.index_series(market, self._compact(start), latest_date)
                index_rows = sorted(index_series.rows.values(), key=self._row_date)
                index_rows_by_market[market] = index_rows
                last_index = index_rows[-1] if index_rows else {}
                rate = last_index.get("change_rate")
                regime = regime_from_index(float(rate) if rate is not None else None)
                market_summaries.append({"market": market, "data_date": self._iso(latest_date), "regime": regime.value})

            quick_inputs: list[tuple[str, dict[str, Any]]] = []
            series_by_market: dict[str, dict[str, Any]] = {}
            for market, rows in prefiltered_by_market.items():
                quick_inputs.extend((market, row) for row in rows)
                latest_date = latest_dates.get(market, "").replace("-", "")
                series_by_market[market] = self.market_store.stock_series_many(
                    market,
                    [str(row.get("code") or "") for row in rows],
                    self._compact(start),
                    latest_date,
                )

            self._emit(progress, stage="scanner_quick_filter", message="현재 조건으로 빠르게 후보를 추리는 중", current=0, total=max(len(quick_inputs), 1), details={"universe": len(universe_rows)})

            quick_candidates: list[dict[str, Any]] = []
            data_insufficient = 0
            for position, (market, row) in enumerate(quick_inputs, start=1):
                latest_date = latest_dates.get(market, "").replace("-", "")
                code = str(row.get("code") or "")
                series = series_by_market.get(market, {}).get(code)
                stock_rows = list(series.rows.values()) if series is not None else []
                quick = self._quick_current_candidate(
                    market=market,
                    latest_date=latest_date,
                    row=row,
                    stock_rows=stock_rows,
                    index_rows=index_rows_by_market.get(market, []),
                )
                if quick is None:
                    data_insufficient += 1
                else:
                    quick_candidates.append(quick)
                if position == 1 or position % 20 == 0 or position == len(quick_inputs):
                    self._emit(progress, stage="scanner_quick_filter", message="현재 조건으로 빠르게 후보를 추리는 중", current=position, total=max(len(quick_inputs), 1), details={"shortlisted": len(quick_candidates)})

            quick_candidates.sort(key=lambda item: (float(item.get("quick_score") or 0), float(item.get("trade_value") or 0)), reverse=True)
            deep_inputs = quick_candidates[: self.DEEP_LIMIT]
            deep_results: list[dict[str, Any]] = []

            self._emit(progress, stage="scanner_deep_analysis", message="상위 후보의 10가지 전략과 과거 근거를 검증 중", current=0, total=max(len(deep_inputs), 1), details={"shortlisted": len(deep_inputs)})
            for position, item in enumerate(deep_inputs, start=1):
                market = str(item["market"])
                code = str(item["code"])
                series = series_by_market.get(market, {}).get(code)
                deep = self._deep_candidate(
                    item=item,
                    stock_rows=list(series.rows.values()) if series is not None else [],
                    index_rows=index_rows_by_market.get(market, []),
                )
                if deep is not None:
                    deep_results.append(deep)
                self._emit(progress, stage="scanner_deep_analysis", message="상위 후보의 10가지 전략과 과거 근거를 검증 중", current=position, total=max(len(deep_inputs), 1), details={"candidates": len(deep_results)})

            deep_results.sort(key=lambda item: float(item.get("internal_rank") or 0.0), reverse=True)
            actionable = [item for item in deep_results if item.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}]
            top = actionable[:candidate_limit]
            more = actionable[candidate_limit : candidate_limit + self.EXTRA_RESULT_LIMIT]
            for collection in (top, more):
                for item in collection:
                    item.pop("internal_rank", None)
            excluded_deep = len(deep_results) - len(actionable)

            delta = self._stats_delta(provider_before, self.krx.request_stats())
            budget = self.krx.budget_snapshot()
            result = {
                "version": self.VERSION,
                "scanner_cache_hit": False,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "requested_as_of": stable_end.isoformat(),
                "market_scope": scope,
                "data_dates": latest_dates,
                "market_summary": market_summaries,
                "summary": {
                    "universe_total": len(universe_rows),
                    "special_excluded": special_excluded,
                    "liquidity_filtered": liquidity_filtered,
                    "quick_analyzed": len(quick_inputs),
                    "data_insufficient": data_insufficient,
                    "deep_analyzed": len(deep_results),
                    "candidate_count": len(actionable),
                    "shown_count": len(top),
                    "excluded_after_analysis": excluded_deep,
                },
                "candidates": top,
                "more_candidates": more,
                "empty_message": None if top else "현재 조건과 위험 기준을 함께 통과해 먼저 볼 만한 종목이 없습니다. 억지로 후보 수를 채우지 않습니다.",
                "exclusion_policy": {
                    "default": ["우선주", "SPAC", "ETF/ETN", "거래정지·거래 없음", "데이터 부족"],
                    "liquidity": "최근 거래대금이 StockScope 기본 유동성 기준에 미달하면 빠른 후보에서 제외합니다.",
                },
                "methodology": {
                    "meaning": "상승 확률 순위가 아니라 현재 전략 준비도, 위험, 시장 환경, 과거 전략 근거를 함께 본 우선 확인 목록입니다.",
                    "pipeline": ["전체 종목 빠른 필터", "현재 10개 전략 비교", "Risk 확인", "상위 후보 1년 과거 근거 검증", "최종 후보 정렬"],
                    "guardrail": "후보 1위라도 현재 진입 조건이 부족하면 신규 진입하지 않도록 안내합니다.",
                },
                "diagnostics": {
                    "market_store_reused_items": aggregate_sync["store_hits"],
                    "estimated_network_requests": aggregate_sync["estimated_network_requests"],
                    "network_requests": int(delta.get("network_requests", aggregate_sync["network_requests"])),
                    "raw_cache_hits": int(delta.get("disk_hits", 0) + delta.get("memory_hits", 0) + delta.get("empty_marker_hits", 0)),
                    "retries": int(delta.get("retries", 0)),
                    "budget_used": budget.get("used", 0),
                    "budget_limit": budget.get("safe_limit", 0),
                    "budget_remaining": budget.get("remaining", 0),
                },
            }
            self._save_cache(scope, stable_end, candidate_limit, result)
            self._emit(progress, stage="scanner_complete", message="오늘 먼저 볼 후보 정리 완료", current=1, total=1, details={"candidates": len(top), "all_candidates": len(actionable)})
            return result
        finally:
            await self.krx.close_session()
