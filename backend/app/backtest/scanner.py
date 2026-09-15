from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.backtest.engine import BacktestEngine
from app.backtest.candidate_priority import rank_candidates
from app.backtest.entry_risk_guide import build_entry_risk_guide
from app.backtest.production_exit_policy import production_policy_cache_token
from app.backtest.historical_evidence import build_historical_evidence, validation_start_for_years
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

    VERSION = "0.21.3"
    HISTORY_CALENDAR_DAYS = 485  # local-only historical evidence window
    FAST_HISTORY_CALENDAR_DAYS = 220  # current-condition scan only; ~150 weekdays
    EVIDENCE_CALENDAR_DAYS = 365
    THREE_YEAR_WARMUP_DAYS = 220
    HISTORICAL_EVIDENCE_POLICY_VERSION = "v1"
    HISTORICAL_VALIDATION_MIN_ROWS = 220
    QUICK_LIMIT_PER_MARKET = 160
    DEEP_LIMIT = 18
    EXTRA_RESULT_LIMIT = 10
    MIN_HISTORY_ROWS = 61
    FETCH_CONCURRENCY_MIN = 4
    FETCH_CONCURRENCY_INITIAL = 8
    FETCH_CONCURRENCY_MAX = 12
    FETCH_CONCURRENCY_RAMP_SUCCESSES = 16
    DEFAULT_FAST_REQUEST_LIMIT = 60
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
        exit_token = re.sub(r"[^A-Za-z0-9_-]+", "_", production_policy_cache_token())
        return cls.CACHE_ROOT / f"scanner_{scope.lower()}_{stable_end.isoformat()}_{candidate_limit}_{cls.VERSION}_{exit_token}.json"

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

    @classmethod
    def _evidence_cache_path(cls, *, market: str, code: str, strategy: str, data_end: date) -> Path:
        root = cls.CACHE_ROOT / "historical_evidence"
        root.mkdir(parents=True, exist_ok=True)
        safe_strategy = re.sub(r"[^A-Za-z0-9_-]+", "_", strategy)
        exit_token = re.sub(r"[^A-Za-z0-9_-]+", "_", production_policy_cache_token())
        return root / f"{market}_{code}_{safe_strategy}_{data_end.isoformat()}_{cls.HISTORICAL_EVIDENCE_POLICY_VERSION}_{exit_token}.json"

    @classmethod
    def _load_evidence_cache(cls, *, market: str, code: str, strategy: str, data_end: date) -> dict[str, Any] | None:
        path = cls._evidence_cache_path(market=market, code=code, strategy=strategy, data_end=data_end)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("policy_version") != cls.HISTORICAL_EVIDENCE_POLICY_VERSION:
            return None
        if payload.get("exit_policy_cache_token") != production_policy_cache_token():
            return None
        evidence = payload.get("evidence")
        if not isinstance(evidence, dict) or not bool(evidence.get("verified")):
            return None
        return dict(evidence)

    @classmethod
    def _save_evidence_cache(cls, *, market: str, code: str, strategy: str, data_end: date, evidence: dict[str, Any]) -> None:
        if not bool(evidence.get("verified")):
            return
        path = cls._evidence_cache_path(market=market, code=code, strategy=strategy, data_end=data_end)
        payload = {
            "policy_version": cls.HISTORICAL_EVIDENCE_POLICY_VERSION,
            "exit_policy_cache_token": production_policy_cache_token(),
            "market": market,
            "code": code,
            "strategy": strategy,
            "data_end": data_end.isoformat(),
            "evidence": evidence,
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _stats_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        keys = set(before) | set(after)
        return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in keys}

    @classmethod
    def fast_request_limit(cls) -> int:
        raw = os.getenv("KRX_SCANNER_FAST_REQUEST_LIMIT", str(cls.DEFAULT_FAST_REQUEST_LIMIT))
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return cls.DEFAULT_FAST_REQUEST_LIMIT

    def _history_plan(self, *, market: str, start: date, end: date) -> dict[str, Any]:
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
        return {
            "market": market,
            "dates": dates,
            "work": work,
            "total": total,
            "reused": reused,
            "estimated_network_requests": estimated,
        }

    @staticmethod
    def _progress_payload(
        *,
        overall_percent: float,
        started_at: float,
        current_item: str | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        return {
            "overall_percent": round(max(0.0, min(100.0, overall_percent)), 1),
            "elapsed_seconds": round(max(0.0, time.perf_counter() - started_at), 1),
            "heartbeat_at": datetime.now().isoformat(timespec="seconds"),
            "current_item": current_item,
            **details,
        }

    async def _ensure_market_history(
        self,
        *,
        market: str,
        start: date,
        end: date,
        progress: ProgressCallback | None,
        progress_base: float,
        progress_span: float,
        started_at: float,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare one market with adaptive network concurrency and non-blocking persistence.

        Network requests are kept in flight continuously instead of waiting for fixed
        batches. KRX raw gzip writes happen inside the provider without blocking the
        event loop, while Market Store writes are serialized on a background writer.
        This keeps the first-PC bootstrap responsive without changing request count.
        """
        planned = plan or self._history_plan(market=market, start=start, end=end)
        work = list(planned["work"])
        total = int(planned["total"])
        reused = int(planned["reused"])
        estimated = int(planned["estimated_network_requests"])
        self.krx.assert_budget(estimated)
        before = self.krx.request_stats()
        completed = reused
        errors = 0
        current_limit = min(self.FETCH_CONCURRENCY_INITIAL, self.FETCH_CONCURRENCY_MAX)
        current_limit = max(self.FETCH_CONCURRENCY_MIN, current_limit)
        peak_concurrency = 0
        stable_successes = 0
        sync_started_at = time.perf_counter()
        current_item: str | None = None
        active_requests = 0

        writer_queue: asyncio.Queue[tuple[str, date, dict[str, Any] | Exception] | None] = asyncio.Queue(
            maxsize=max(8, self.FETCH_CONCURRENCY_MAX * 2)
        )

        def progress_metrics() -> dict[str, Any]:
            elapsed = max(0.001, time.perf_counter() - sync_started_at)
            newly_completed = max(0, completed - reused)
            rate = newly_completed / elapsed
            remaining = max(0, total - completed)
            eta = (remaining / rate) if rate > 0.05 else None
            delta_now = self._stats_delta(before, self.krx.request_stats())
            return {
                "network_requests_so_far": int(delta_now.get("network_requests", 0)),
                "retry_count": int(delta_now.get("retries", 0)),
                "items_done": completed,
                "items_total": total,
                "items_remaining": remaining,
                "processing_rate": round(rate, 2),
                "eta_seconds": None if eta is None else round(eta, 1),
                "concurrency_limit": current_limit,
                "active_requests": active_requests,
                "peak_concurrency": peak_concurrency,
                "errors": errors,
            }

        def emit_state(message: str) -> None:
            fraction = 1.0 if total <= 0 else completed / total
            percent = progress_base + progress_span * fraction
            self._emit(
                progress,
                stage="scanner_data_prepare",
                message=message,
                current=completed,
                total=max(total, 1),
                details=self._progress_payload(
                    overall_percent=percent,
                    started_at=started_at,
                    current_item=current_item,
                    market=market,
                    reused_items=reused,
                    estimated_network_requests=estimated,
                    **progress_metrics(),
                ),
            )

        async def persist_worker() -> None:
            nonlocal completed, errors, current_item
            while True:
                payload = await writer_queue.get()
                try:
                    if payload is None:
                        return
                    kind, day, result = payload
                    current_item = f"{market} {day.isoformat()} {'주식' if kind == 'stock' else '지수'}"
                    if isinstance(result, Exception):
                        errors += 1
                    else:
                        try:
                            key = self._compact(day)
                            if kind == "stock":
                                rows = list(result.get("rows") or [])
                                await asyncio.to_thread(self.market_store.put_stock_day, market, key, rows, stable=True)
                            else:
                                rows = list(result.get("rows") or [])
                                main = self.krx._select_main_index(rows, market) if rows else None  # noqa: SLF001
                                await asyncio.to_thread(self.market_store.put_index_day, market, key, main, stable=True)
                        except Exception:
                            errors += 1
                    completed += 1
                    emit_state(f"{market} 최근 시장 데이터 준비 중")
                finally:
                    writer_queue.task_done()

        async def fetch_one(kind: str, day: date) -> dict[str, Any]:
            if kind == "stock":
                return await self.krx.stock_daily(market, day)
            return await self.krx.index_daily(market, day)

        emit_state(f"{market} 최근 시장 데이터 준비 중")
        writer_task = asyncio.create_task(persist_worker())
        active: dict[asyncio.Task[dict[str, Any]], tuple[str, date]] = {}
        next_index = 0
        last_retry_count = int(before.get("retries", 0))

        def launch_more() -> None:
            nonlocal next_index, active_requests, peak_concurrency
            while next_index < len(work) and len(active) < current_limit:
                kind, day = work[next_index]
                next_index += 1
                task = asyncio.create_task(fetch_one(kind, day))
                active[task] = (kind, day)
            active_requests = len(active)
            peak_concurrency = max(peak_concurrency, active_requests)

        try:
            launch_more()
            while active:
                done, _ = await asyncio.wait(tuple(active), return_when=asyncio.FIRST_COMPLETED)
                had_error = False
                for task in done:
                    kind, day = active.pop(task)
                    try:
                        result: dict[str, Any] | Exception = task.result()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # keep already-fetched days and continue remaining bootstrap
                        result = exc
                        had_error = True
                    await writer_queue.put((kind, day, result))

                current_retries = int(self.krx.request_stats().get("retries", 0))
                retry_delta = max(0, current_retries - last_retry_count)
                last_retry_count = current_retries
                if had_error or retry_delta > 0:
                    current_limit = max(self.FETCH_CONCURRENCY_MIN, current_limit - 2)
                    stable_successes = 0
                else:
                    stable_successes += len(done)
                    if stable_successes >= self.FETCH_CONCURRENCY_RAMP_SUCCESSES and current_limit < self.FETCH_CONCURRENCY_MAX:
                        current_limit += 1
                        stable_successes = 0
                launch_more()

            await writer_queue.join()
        except asyncio.CancelledError:
            for task in active:
                task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            # Completed HTTP responses already queued for persistence are preserved.
            await writer_queue.join()
            raise
        finally:
            await writer_queue.put(None)
            await writer_task

        delta = self._stats_delta(before, self.krx.request_stats())
        sync_elapsed = max(0.001, time.perf_counter() - sync_started_at)
        processed = max(0, completed - reused)
        return {
            "store_hits": reused,
            "estimated_network_requests": estimated,
            "network_requests": int(delta.get("network_requests", 0)),
            "raw_cache_hits": int(delta.get("disk_hits", 0) + delta.get("memory_hits", 0) + delta.get("empty_marker_hits", 0)),
            "errors": errors,
            "processed_items": processed,
            "sync_seconds": round(sync_elapsed, 3),
            "processing_rate": round(processed / sync_elapsed, 3),
            "peak_concurrency": peak_concurrency,
            "final_concurrency_limit": current_limit,
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
                    "condition_state": condition_state,
                    "risk_plan": risk_plan,
                    "strategy_input": snapshot.get("strategy_input"),
                    "technical": snapshot.get("technical") or {},
                    "entry_timing": snapshot.get("entry_timing") or None,
                }
        if best is None:
            return None
        current = best["current"]
        total = int(current.get("total") or 0)
        passed = int(current.get("passed") or 0)
        ratio = passed / total if total else 0.0
        risk_penalty = 18.0 if current.get("risk_warning") else 0.0
        quick_score = float(current.get("internal_score") or 0.0) + ratio * 20.0 - risk_penalty
        entry_risk_guide = build_entry_risk_guide(
            strategy=best["strategy"],
            data=best.get("strategy_input"),
            technical=best.get("technical") or {},
            condition_state=best.get("condition_state") or {},
            risk_plan=best.get("risk_plan"),
            current_state=current,
            historical_verified=False,
            historical_status="NOT_RUN",
            as_of_date=str(latest_date or "") or None,
            entry_timing=best.get("entry_timing"),
        )
        quick_exit_resolution = self.multi.production_exit.registry.resolve(best["strategy"])
        entry_risk_guide["historical_policy"] = self.multi.production_exit.historical_policy_metadata(
            quick_exit_resolution
        )
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
            "quick_condition_state": best.get("condition_state") or {},
            "quick_entry_risk_guide": entry_risk_guide,
            "quick_score": round(quick_score, 4),
        }

    def _fast_candidate(self, item: dict[str, Any]) -> dict[str, Any] | None:
        current = dict(item.get("quick_current") or {})
        guide = dict(item.get("quick_guide") or {})
        condition_state = dict(item.get("quick_condition_state") or {})
        total = int(current.get("total") or condition_state.get("total") or 0)
        passed = int(current.get("passed") or condition_state.get("passed") or 0)
        missing = int(current.get("missing") or condition_state.get("missing") or max(0, total - passed))
        ratio = passed / total if total else 0.0
        risk_warning = bool(current.get("risk_warning"))
        status = str(current.get("status") or "NOT_READY")

        if status == "READY" and not risk_warning:
            candidate_state = "READY"
            candidate_label = "현재 조건상 진입 후보 · 과거 검증 전"
            action = "ENTRY_CANDIDATE"
            action_label = "현재 조건상 진입 후보"
            headline = "현재 전략 조건과 Risk 기준은 통과했습니다. 과거 근거는 아직 검증 전입니다."
        elif status in {"BLOCKED", "CAUTION"} or (risk_warning and missing == 0):
            candidate_state = "WATCH"
            candidate_label = "조건은 갖췄지만 위험 확인 필요"
            action = "WAIT"
            action_label = "위험 때문에 진입 보류"
            headline = "현재 조건은 갖춰졌지만 손절·목표 위험 구조 때문에 진입을 보류합니다."
        elif ratio >= 0.65:
            candidate_state = "WATCH"
            candidate_label = "조금 더 기다릴 후보 · 과거 검증 전"
            action = "WAIT"
            action_label = "아직 진입 조건 부족"
            headline = "현재 조건은 가까워졌지만 아직 부족한 조건이 있습니다."
        else:
            candidate_state = "EXCLUDED"
            candidate_label = "현재 우선 후보 아님"
            action = "NO_TRADE"
            action_label = "관망"
            headline = "현재 조건이 아직 충분하지 않습니다."

        missing_details = list(condition_state.get("missing_details") or [])
        warnings = list(current.get("warnings") or [])
        reason = str(current.get("summary") or headline)
        internal_rank = float(item.get("quick_score") or 0.0) - 12.0
        if risk_warning:
            internal_rank -= 10.0

        return {
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "data_date": self._iso(str(item["latest_date"])),
            "current_price": item.get("current_price"),
            "candidate_state": candidate_state,
            "candidate_label": candidate_label,
            "strategy": item.get("quick_strategy"),
            "strategy_easy_name": guide.get("easy_name") or guide.get("professional_name") or str(item.get("quick_strategy") or ""),
            "strategy_name": guide.get("professional_name") or str(item.get("quick_strategy") or ""),
            "strategy_description": guide.get("description") or "현재 조건을 바탕으로 먼저 확인할 후보입니다.",
            "action": action,
            "action_label": action_label,
            "headline": headline,
            "reason": reason,
            "conditions": {
                "passed": passed,
                "total": total,
                "missing": missing,
                "top_missing": missing_details[:3],
            },
            "risk": {
                "status": current.get("risk_status"),
                "warning": risk_warning,
                "warnings": warnings,
            },
            "historical_fit": {
                "status": "NOT_RUN",
                "label": "과거 검증 전",
                "summary": "현재 조건으로 먼저 추렸습니다. 과거 근거는 아직 장기 검증하지 않았습니다.",
                "trades": 0,
                "verified": False,
            },
            "verification_level": "CURRENT_ONLY",
            "entry_risk_guide": item.get("quick_entry_risk_guide"),
            "user_action": {
                "title": (
                    "현재 조건상 진입 후보로 검토할 수 있습니다."
                    if action == "ENTRY_CANDIDATE"
                    else "지금은 신규 진입하지 마세요."
                ),
                "detail": (
                    "현재 조건과 Risk 기준은 통과했습니다. 다만 과거 근거는 아직 검증 전이며 실제 주문은 자동 실행하지 않습니다."
                    if action == "ENTRY_CANDIDATE"
                    else "부족한 조건이나 위험 구조가 개선된 뒤 다시 판단하세요. 과거 검증 여부는 현재 조건과 별도로 표시합니다."
                ),
                "next_transition": (
                    "과거 근거를 추가 확인하거나 다음 확정 데이터에서 현재 조건을 다시 계산"
                    if action == "ENTRY_CANDIDATE"
                    else "남은 조건과 Risk를 다시 계산"
                ),
            },
            "_strategy_fit_score": round(float(item.get("quick_score") or 0.0), 4),
            "internal_rank": round(internal_rank, 4),
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

        concrete_guide = current.get("entry_risk_guide") or {}
        concrete_action = concrete_guide.get("action") or {}
        guide_action = str(concrete_action.get("status") or "")
        missing_count = int(current.get("missing") or max(0, total - passed))
        if guide_action == "ENTRY_CANDIDATE" or (missing_count == 0 and not risk_warning):
            candidate_state = "READY"
            candidate_label = "현재 조건상 진입 후보"
        elif guide_action == "RISK_BLOCKED" and missing_count == 0:
            candidate_state = "WATCH"
            candidate_label = "조건은 갖췄지만 위험 확인 필요"
        elif ratio >= 0.65:
            candidate_state = "VALIDATION" if action == "NEEDS_VALIDATION" else "WATCH"
            candidate_label = "진입 후보에 가까움" if missing_count <= 2 else "조건 확인 필요"
        else:
            candidate_state = "EXCLUDED"
            candidate_label = "현재 우선 후보 아님"

        guide = strategy_row.get("guide") or strategy_guide(strategy)
        missing_details = list(current.get("unmet_details") or [])
        user_action = recommendation.get("user_action") or {}
        if guide_action == "ENTRY_CANDIDATE":
            display_action = "ENTRY_CANDIDATE"
        elif guide_action == "RISK_BLOCKED":
            display_action = "WAIT"
        elif guide_action == "WAIT":
            display_action = "WAIT"
        else:
            display_action = action
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
            "action": display_action,
            "action_label": concrete_action.get("title") or recommendation.get("action_label"),
            "headline": concrete_action.get("detail") or recommendation.get("headline"),
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
                "verified": True,
            },
            "verification_level": "CURRENT_AND_HISTORY",
            "entry_risk_guide": concrete_guide,
            "user_action": {
                "title": concrete_action.get("title") or user_action.get("title"),
                "detail": concrete_action.get("detail") or user_action.get("detail"),
                "next_transition": user_action.get("next_transition"),
            },
            "_strategy_fit_score": round(selector_score, 4),
            "internal_rank": round(internal_rank, 4),
        }

    async def _attach_three_year_historical_evidence(
        self,
        *,
        candidates: list[dict[str, Any]],
        progress: ProgressCallback | None,
        started_at: float,
    ) -> dict[str, int]:
        """Attach three-year same-strategy evidence to the bounded final ranking pool.

        This path is intentionally local-only. It never calls KRX and therefore cannot
        turn a fast Scanner request into a multi-hundred-request historical bootstrap.
        v0.21.3 uses the result only after current conditions and Risk have established
        the candidate tier; history can refine a tie but cannot convert a current FAIL
        into a current PASS.
        """
        stats = {"verified": 0, "data_unavailable": 0, "sample_insufficient": 0, "cache_hits": 0}
        if not candidates:
            return stats

        grouped: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            grouped.setdefault(str(candidate.get("market") or ""), []).append(candidate)

        position = 0
        total = len(candidates)
        for market, market_candidates in grouped.items():
            valid_dates = [str(item.get("data_date") or "") for item in market_candidates if item.get("data_date")]
            if not valid_dates:
                continue
            market_end = max(date.fromisoformat(value) for value in valid_dates)
            market_start = validation_start_for_years(market_end)
            warmup_start = market_start - timedelta(days=self.THREE_YEAR_WARMUP_DAYS)
            end_key = self._compact(market_end)
            start_key = self._compact(warmup_start)
            codes = [str(item.get("code") or "") for item in market_candidates]
            stock_map = self.market_store.stock_series_many(market, codes, start_key, end_key)
            index_series = self.market_store.index_series(market, start_key, end_key)
            index_rows = sorted(index_series.rows.values(), key=self._row_date)

            for candidate in market_candidates:
                position += 1
                code = str(candidate.get("code") or "")
                strategy = str(candidate.get("strategy") or "")
                data_end = date.fromisoformat(str(candidate.get("data_date")))
                validation_start = validation_start_for_years(data_end)
                cached = self._load_evidence_cache(market=market, code=code, strategy=strategy, data_end=data_end)
                if cached is not None:
                    evidence = cached
                    stats["cache_hits"] += 1
                else:
                    series = stock_map.get(code)
                    stock_rows = list(series.rows.values()) if series is not None else []
                    evidence = await asyncio.to_thread(
                        build_historical_evidence,
                        engine=self.multi,
                        strategy=strategy,
                        code=code,
                        market=market,
                        stock_rows=stock_rows,
                        index_rows=index_rows,
                        validation_start=validation_start,
                        validation_end=data_end,
                        round_trip_cost_pct=0.0,
                    )
                    # Missing local history can be filled later on the same day.
                    # Cache only completed historical calculations so an unavailable
                    # result never becomes a stale "검증 전" snapshot.
                    if bool(evidence.get("verified")):
                        self._save_evidence_cache(
                            market=market, code=code, strategy=strategy, data_end=data_end, evidence=evidence
                        )

                candidate["historical_evidence"] = evidence
                if bool(evidence.get("verified")):
                    stats["verified"] += 1
                    candidate["verification_level"] = "CURRENT_AND_3Y_EVIDENCE"
                else:
                    stats["data_unavailable"] += 1
                if evidence.get("status") in {"INSUFFICIENT", "NO_CASES"}:
                    stats["sample_insufficient"] += 1

                self._emit(
                    progress,
                    stage="scanner_historical_evidence",
                    message="후보 풀의 3년 과거 근거를 확인하는 중",
                    current=position,
                    total=max(total, 1),
                    details=self._progress_payload(
                        overall_percent=92 + 6.0 * position / max(total, 1),
                        started_at=started_at,
                        current_item=f"{candidate.get('name') or code} ({code})",
                        evidence_verified=stats["verified"],
                        evidence_data_unavailable=stats["data_unavailable"],
                        evidence_cache_hits=stats["cache_hits"],
                        items_done=position,
                        items_total=total,
                    ),
                )
        return stats

    async def run(
        self,
        *,
        market_scope: str = "ALL",
        as_of_date: str | None = None,
        candidate_limit: int = 5,
        force_refresh: bool = False,
        allow_large_sync: bool = False,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        scope = market_scope.upper().strip()
        if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
            raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")
        candidate_limit = max(1, min(int(candidate_limit), 10))
        today = self.krx._today_kst()  # noqa: SLF001 - same EOD freshness boundary as provider
        stable_end = self._parse_as_of(as_of_date, today)
        started_at = time.perf_counter()

        if not force_refresh:
            cached = self._load_cache(scope, stable_end, candidate_limit)
            if cached is not None:
                self._emit(
                    progress,
                    stage="scanner_cache",
                    message="오늘의 Scanner 결과 재사용",
                    current=1,
                    total=1,
                    details=self._progress_payload(
                        overall_percent=100,
                        started_at=started_at,
                        cache_hit=True,
                    ),
                )
                return cached

        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
        fast_start = stable_end - timedelta(days=self.FAST_HISTORY_CALENDAR_DAYS)
        evidence_start = stable_end - timedelta(days=self.HISTORY_CALENDAR_DAYS)
        provider_before = self.krx.request_stats()
        aggregate_sync: dict[str, float] = {
            "store_hits": 0,
            "estimated_network_requests": 0,
            "network_requests": 0,
            "raw_cache_hits": 0,
            "errors": 0,
            "processed_items": 0,
            "sync_seconds": 0,
            "peak_concurrency": 0,
        }
        timings: dict[str, float] = {}
        preparation_required: list[dict[str, Any]] = []

        self._emit(
            progress,
            stage="scanner_plan",
            message="필요한 시장 데이터를 확인하는 중",
            current=0,
            total=1,
            details=self._progress_payload(overall_percent=4, started_at=started_at),
        )

        plans = {market: self._history_plan(market=market, start=fast_start, end=stable_end) for market in markets}
        estimated_total = sum(int(plan["estimated_network_requests"]) for plan in plans.values())
        fast_limit = self.fast_request_limit()
        large_sync_blocked = estimated_total > fast_limit and not allow_large_sync

        if large_sync_blocked:
            for market, plan in plans.items():
                estimated = int(plan["estimated_network_requests"])
                if estimated <= 0:
                    continue
                preparation_required.append({
                    "market": market,
                    "estimated_network_requests": estimated,
                    "items_missing": len(plan["work"]),
                    "message": f"{market} 최근 기술지표 계산용 시장 데이터가 부족합니다.",
                })
            self._emit(
                progress,
                stage="scanner_fast_budget",
                message="대량 다운로드 없이 저장된 데이터로 먼저 검색합니다.",
                current=1,
                total=1,
                details=self._progress_payload(
                    overall_percent=10,
                    started_at=started_at,
                    estimated_network_requests=estimated_total,
                    fast_request_limit=fast_limit,
                    large_sync_blocked=True,
                ),
            )

        t_data = time.perf_counter()
        await self.krx.open_session()
        try:
            if not large_sync_blocked:
                market_count = max(len(markets), 1)
                for position, market in enumerate(markets):
                    base = 10 + (15.0 / market_count) * position
                    span = 15.0 / market_count
                    sync = await self._ensure_market_history(
                        market=market,
                        start=fast_start,
                        end=stable_end,
                        progress=progress,
                        progress_base=base,
                        progress_span=span,
                        started_at=started_at,
                        plan=plans[market],
                    )
                    for key in ("store_hits", "estimated_network_requests", "network_requests", "raw_cache_hits", "errors", "processed_items"):
                        aggregate_sync[key] += float(sync.get(key, 0) or 0)
                    aggregate_sync["sync_seconds"] += float(sync.get("sync_seconds", 0) or 0)
                    aggregate_sync["peak_concurrency"] = max(
                        aggregate_sync["peak_concurrency"],
                        float(sync.get("peak_concurrency", 0) or 0),
                    )
            else:
                # Store/raw-cache reuse is still counted even when network sync is skipped.
                for market, plan in plans.items():
                    aggregate_sync["store_hits"] += float(plan["reused"])
                    aggregate_sync["estimated_network_requests"] += float(plan["estimated_network_requests"])

            timings["data_prepare_seconds"] = time.perf_counter() - t_data

            universe_rows: list[dict[str, Any]] = []
            latest_dates: dict[str, str] = {}
            market_summaries: list[dict[str, Any]] = []
            index_rows_by_market: dict[str, list[dict[str, Any]]] = {}
            prefiltered_by_market: dict[str, list[dict[str, Any]]] = {}
            special_excluded = 0
            liquidity_filtered = 0

            self._emit(
                progress,
                stage="scanner_universe",
                message="현재 시장 종목을 정리하는 중",
                current=0,
                total=max(len(markets), 1),
                details=self._progress_payload(overall_percent=25, started_at=started_at),
            )

            for market_index, market in enumerate(markets, start=1):
                end_key = self._compact(stable_end)
                latest_date = self.market_store.latest_complete_date(market, "stock", end_key)
                if not latest_date:
                    self._emit(
                        progress,
                        stage="scanner_universe",
                        message=f"{market} 저장 데이터가 없어 빠른 검색에서 건너뜁니다.",
                        current=market_index,
                        total=max(len(markets), 1),
                        details=self._progress_payload(
                            overall_percent=25 + 5 * market_index / max(len(markets), 1),
                            started_at=started_at,
                            current_item=market,
                        ),
                    )
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

                index_series = self.market_store.index_series(market, self._compact(fast_start), latest_date)
                index_rows = sorted(index_series.rows.values(), key=self._row_date)
                index_rows_by_market[market] = index_rows
                last_index = index_rows[-1] if index_rows else {}
                rate = last_index.get("change_rate")
                regime = regime_from_index(float(rate) if rate is not None else None)
                market_summaries.append({"market": market, "data_date": self._iso(latest_date), "regime": regime.value})
                self._emit(
                    progress,
                    stage="scanner_universe",
                    message="현재 시장 종목을 정리하는 중",
                    current=market_index,
                    total=max(len(markets), 1),
                    details=self._progress_payload(
                        overall_percent=25 + 5 * market_index / max(len(markets), 1),
                        started_at=started_at,
                        current_item=market,
                        universe=len(universe_rows),
                    ),
                )

            quick_inputs: list[tuple[str, dict[str, Any]]] = []
            series_by_market: dict[str, dict[str, Any]] = {}
            for market, rows in prefiltered_by_market.items():
                quick_inputs.extend((market, row) for row in rows)
                latest_date = latest_dates.get(market, "").replace("-", "")
                series_by_market[market] = self.market_store.stock_series_many(
                    market,
                    [str(row.get("code") or "") for row in rows],
                    self._compact(fast_start),
                    latest_date,
                )

            t_quick = time.perf_counter()
            self._emit(
                progress,
                stage="scanner_quick_filter",
                message="현재 조건으로 빠르게 후보를 추리는 중",
                current=0,
                total=max(len(quick_inputs), 1),
                details=self._progress_payload(
                    overall_percent=30,
                    started_at=started_at,
                    universe=len(universe_rows),
                    shortlisted=0,
                ),
            )

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
                if position == 1 or position % 10 == 0 or position == len(quick_inputs):
                    percent = 30 + 35.0 * position / max(len(quick_inputs), 1)
                    self._emit(
                        progress,
                        stage="scanner_quick_filter",
                        message="현재 조건으로 빠르게 후보를 추리는 중",
                        current=position,
                        total=max(len(quick_inputs), 1),
                        details=self._progress_payload(
                            overall_percent=percent,
                            started_at=started_at,
                            current_item=f"{row.get('name') or code} ({code})",
                            shortlisted=len(quick_candidates),
                            items_done=position,
                            items_total=len(quick_inputs),
                        ),
                    )
            timings["quick_filter_seconds"] = time.perf_counter() - t_quick

            quick_candidates.sort(key=lambda item: (float(item.get("quick_score") or 0), float(item.get("trade_value") or 0)), reverse=True)
            deep_inputs = quick_candidates[: self.DEEP_LIMIT]
            deep_results: list[dict[str, Any]] = []
            verified_count = 0
            current_only_count = 0

            # Historical evidence is local-only here. Scanner never downloads a year of
            # history merely to finish one search. Existing Market Store data is reused.
            deep_codes_by_market: dict[str, list[str]] = {}
            for item in deep_inputs:
                deep_codes_by_market.setdefault(str(item["market"]), []).append(str(item["code"]))
            deep_series_by_market: dict[str, dict[str, Any]] = {}
            deep_index_by_market: dict[str, list[dict[str, Any]]] = {}
            for market, codes in deep_codes_by_market.items():
                latest_date = latest_dates.get(market, "").replace("-", "")
                deep_series_by_market[market] = self.market_store.stock_series_many(
                    market, codes, self._compact(evidence_start), latest_date
                )
                index_series = self.market_store.index_series(market, self._compact(evidence_start), latest_date)
                deep_index_by_market[market] = sorted(index_series.rows.values(), key=self._row_date)

            t_deep = time.perf_counter()
            self._emit(
                progress,
                stage="scanner_deep_analysis",
                message="상위 후보의 전략과 위험을 확인하는 중",
                current=0,
                total=max(len(deep_inputs), 1),
                details=self._progress_payload(
                    overall_percent=65,
                    started_at=started_at,
                    shortlisted=len(deep_inputs),
                    verified=0,
                ),
            )
            for position, item in enumerate(deep_inputs, start=1):
                market = str(item["market"])
                code = str(item["code"])
                deep_series = deep_series_by_market.get(market, {}).get(code)
                deep_stock_rows = list(deep_series.rows.values()) if deep_series is not None else []
                deep_index_rows = deep_index_by_market.get(market, [])
                enough_history = (
                    len(deep_stock_rows) >= self.HISTORICAL_VALIDATION_MIN_ROWS
                    and len(deep_index_rows) >= self.HISTORICAL_VALIDATION_MIN_ROWS
                )
                if enough_history:
                    deep = self._deep_candidate(
                        item=item,
                        stock_rows=deep_stock_rows,
                        index_rows=deep_index_rows,
                    )
                    if deep is not None:
                        verified_count += 1
                else:
                    deep = self._fast_candidate(item)
                    if deep is not None:
                        current_only_count += 1
                if deep is not None:
                    deep_results.append(deep)

                percent = 65 + 25.0 * position / max(len(deep_inputs), 1)
                self._emit(
                    progress,
                    stage="scanner_deep_analysis",
                    message="상위 후보의 전략과 위험을 확인하는 중",
                    current=position,
                    total=max(len(deep_inputs), 1),
                    details=self._progress_payload(
                        overall_percent=percent,
                        started_at=started_at,
                        current_item=f"{item.get('name') or code} ({code})",
                        candidates=len(deep_results),
                        verified=verified_count,
                        current_only=current_only_count,
                        items_done=position,
                        items_total=len(deep_inputs),
                    ),
                )
            timings["deep_analysis_seconds"] = time.perf_counter() - t_deep

            self._emit(
                progress,
                stage="scanner_finalize",
                message="현재 조건 기준 후보 우선순위를 확정하는 중",
                current=0,
                total=1,
                details=self._progress_payload(overall_percent=90, started_at=started_at),
            )
            # Preliminary order is kept only as a diagnostic baseline. v0.21.3 then
            # validates the bounded actionable pool with local three-year evidence and
            # applies a tier-first priority rule: current conditions > Risk > concrete
            # entry proximity > historical evidence > strategy fit. No probability score
            # is exposed or used to let history override a current condition failure.
            deep_results.sort(key=lambda item: float(item.get("internal_rank") or 0.0), reverse=True)
            actionable = [item for item in deep_results if item.get("candidate_state") in {"READY", "WATCH", "VALIDATION"}]
            excluded_deep = len(deep_results) - len(actionable)

            evidence_stats = await self._attach_three_year_historical_evidence(
                candidates=actionable,
                progress=progress,
                started_at=started_at,
            )
            self._emit(
                progress,
                stage="scanner_priority_rank",
                message="현재 조건·Risk·진입 거리·과거 근거 순서로 후보 우선순위를 설명하는 중",
                current=1,
                total=1,
                details=self._progress_payload(overall_percent=99, started_at=started_at),
            )
            ranked_actionable, ranking_changes = rank_candidates(actionable)
            top = ranked_actionable[:candidate_limit]
            more = ranked_actionable[candidate_limit : candidate_limit + self.EXTRA_RESULT_LIMIT]
            for item in ranked_actionable:
                item.pop("internal_rank", None)
                item.pop("_strategy_fit_score", None)

            delta = self._stats_delta(provider_before, self.krx.request_stats())
            budget = self.krx.budget_snapshot()
            timings["total_seconds"] = time.perf_counter() - started_at
            # Do not freeze the same-day Scanner result while a ranked candidate's
            # three-year evidence is still unavailable. If Market Store history is
            # populated later, the next scan can validate it immediately.
            partial_data = bool(preparation_required) or evidence_stats["data_unavailable"] > 0
            result = {
                "version": self.VERSION,
                "scanner_cache_hit": False,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "requested_as_of": stable_end.isoformat(),
                "market_scope": scope,
                "data_dates": latest_dates,
                "market_summary": market_summaries,
                "partial_data": partial_data,
                "preparation_required": preparation_required,
                "fast_request_limit": fast_limit,
                "summary": {
                    "universe_total": len(universe_rows),
                    "special_excluded": special_excluded,
                    "liquidity_filtered": liquidity_filtered,
                    "quick_analyzed": len(quick_inputs),
                    "data_insufficient": data_insufficient,
                    "deep_analyzed": len(deep_results),
                    "historically_verified": verified_count,
                    "current_only": current_only_count,
                    "three_year_evidence_verified": evidence_stats["verified"],
                    "three_year_evidence_data_unavailable": evidence_stats["data_unavailable"],
                    "three_year_evidence_sample_insufficient": evidence_stats["sample_insufficient"],
                    "three_year_evidence_cache_hits": evidence_stats["cache_hits"],
                    "candidate_count": len(actionable),
                    "shown_count": len(top),
                    "excluded_after_analysis": excluded_deep,
                },
                "candidates": top,
                "more_candidates": more,
                "empty_message": None if top else (
                    "시장 데이터가 부족해 아직 종목 검사를 충분히 시작하지 못했습니다. 시장 데이터를 준비한 뒤 다시 찾으면 후보 여부를 판단할 수 있습니다."
                    if preparation_required and len(universe_rows) == 0
                    else "저장된 최근 데이터만으로는 먼저 볼 만한 후보를 만들지 못했습니다. 필요한 시장 데이터를 준비하면 검색 범위를 넓힐 수 있습니다."
                    if preparation_required
                    else "현재 조건과 위험 기준을 함께 통과해 먼저 볼 만한 종목이 없습니다. 억지로 후보 수를 채우지 않습니다."
                ),
                "exclusion_policy": {
                    "default": ["우선주", "SPAC", "ETF/ETN", "거래정지·거래 없음", "데이터 부족"],
                    "liquidity": "최근 거래대금이 StockScope 기본 유동성 기준에 미달하면 빠른 후보에서 제외합니다.",
                },
                "methodology": {
                    "meaning": "상승 확률 순위가 아니라 현재 조건을 가장 먼저 보고, Risk와 실제 진입 기준까지의 거리, 같은 전략의 3년 과거 근거를 순서대로 비교해 먼저 확인할 후보를 정합니다.",
                    "pipeline": ["최근 데이터 확인", "전체 종목 빠른 필터", "현재 10개 전략·Risk 확인", "후보 풀 3년 과거검증", "조건 → Risk → 진입 근접도 → 과거 근거 순으로 최종 우선순위"],
                    "guardrail": "과거 근거가 좋아도 현재 조건 실패를 통과로 바꾸지 않으며, Risk가 나쁜 종목을 조건 점수만으로 상위에 올리지 않습니다. 이 순위는 미래 상승 확률이나 매수 추천이 아닙니다.",
                },
                "diagnostics": {
                    "market_store_reused_items": aggregate_sync["store_hits"],
                    "estimated_network_requests": estimated_total,
                    "network_requests": int(delta.get("network_requests", aggregate_sync["network_requests"])),
                    "raw_cache_hits": int(delta.get("disk_hits", 0) + delta.get("memory_hits", 0) + delta.get("empty_marker_hits", 0)),
                    "retries": int(delta.get("retries", 0)),
                    "budget_used": budget.get("used", 0),
                    "budget_limit": budget.get("safe_limit", 0),
                    "budget_remaining": budget.get("remaining", 0),
                    "fast_request_limit": fast_limit,
                    "large_sync_blocked": large_sync_blocked,
                    "bootstrap_processed_items": int(aggregate_sync.get("processed_items", 0)),
                    "bootstrap_peak_concurrency": int(aggregate_sync.get("peak_concurrency", 0)),
                    "bootstrap_errors": int(aggregate_sync.get("errors", 0)),
                    "bootstrap_request_rate": round(
                        float(aggregate_sync.get("processed_items", 0)) / max(float(aggregate_sync.get("sync_seconds", 0)), 0.001),
                        3,
                    ),
                    "ranking_changes": ranking_changes,
                    **{key: round(value, 3) for key, value in timings.items()},
                },
            }
            # A partial result should not be frozen for the whole day; once the user
            # prepares missing recent data, a subsequent scan must recompute it.
            if not partial_data:
                self._save_cache(scope, stable_end, candidate_limit, result)
            self._emit(
                progress,
                stage="scanner_complete",
                message="오늘 먼저 볼 후보 정리 완료",
                current=1,
                total=1,
                details=self._progress_payload(
                    overall_percent=100,
                    started_at=started_at,
                    candidates=len(top),
                    all_candidates=len(actionable),
                ),
            )
            return result
        finally:
            await self.krx.close_session()

