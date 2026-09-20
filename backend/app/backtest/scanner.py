from __future__ import annotations

import asyncio
import hashlib
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
from app.backtest.sector_rs_input import HistoricalSectorInput
from app.backtest.sector_rs_prefetch import HistoricalSectorInputPrefetcher
from app.backtest.historical_evidence import build_historical_evidence, validation_start_for_years
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.reproducibility_audit import write_scanner_reproducibility_audit
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

    VERSION = "0.21.3.7"
    HISTORY_CALENDAR_DAYS = 485  # local-only historical evidence window
    FAST_HISTORY_CALENDAR_DAYS = 220  # current-condition scan only; ~150 weekdays
    EVIDENCE_CALENDAR_DAYS = 365
    THREE_YEAR_WARMUP_DAYS = 220
    HISTORICAL_EVIDENCE_POLICY_VERSION = "v2"
    HISTORICAL_VALIDATION_MIN_ROWS = 220  # legacy diagnostic only; never selects production current path
    QUICK_LIMIT_PER_MARKET = 160
    DEEP_LIMIT = 18
    EXTRA_RESULT_LIMIT = 10
    MIN_HISTORY_ROWS = 61
    FETCH_CONCURRENCY_MIN = 4
    FETCH_CONCURRENCY_INITIAL = 8
    FETCH_CONCURRENCY_MAX = 12
    FETCH_CONCURRENCY_RAMP_SUCCESSES = 16
    DEFAULT_FAST_REQUEST_LIMIT = 60
    LATEST_CONFIRM_LOOKBACK_DAYS = 14
    DATA_INTEGRITY_VERSION = "v0.21.4-B.2.2.2d"
    CACHE_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "scanner"

    def __init__(
        self,
        krx: KrxProvider,
        *,
        market_store: HistoricalMarketStore | None = None,
        engine: BacktestEngine | None = None,
        sector_company_provider: Any | None = None,
        sector_prefetcher: HistoricalSectorInputPrefetcher | None = None,
    ) -> None:
        self.krx = krx
        self.market_store = market_store or HistoricalMarketStore()
        self.engine = engine or BacktestEngine()
        self.multi = MultiStrategyBacktestEngine(self.engine)
        # c.4f: optional audit-only sector input source. Current OpenDART metadata is
        # STATIC_CURRENT, so the temporal gate in BacktestEngine prevents it from
        # changing Production strategy scores. Scanner itself never calls DART.
        self.sector_prefetcher = sector_prefetcher
        if self.sector_prefetcher is None and sector_company_provider is not None:
            self.sector_prefetcher = HistoricalSectorInputPrefetcher(self.krx, sector_company_provider)

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

    @staticmethod
    def _common_available_date(values: dict[str, str | None]) -> str | None:
        available = [value for value in values.values() if value]
        if not available or len(available) != len(values):
            return None
        return min(available)

    @staticmethod
    def _normalize_iso_date(value: str | None) -> str | None:
        if not value:
            return None
        raw = str(value).strip()
        if len(raw) == 8 and raw.isdigit():
            raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            return None

    def _day_has_data(self, market: str, bas_dd: str, kind: str) -> bool:
        """Return True only when the exact day contains persisted data.

        HistoricalMarketStore.day_complete() intentionally treats both 'data' and
        stable 'empty' markers as checked days. That is useful for avoiding repeated
        holiday/weekend requests, but an empty marker must never qualify as an
        analysis-ready EOD day.
        """
        return self.market_store.latest_complete_date(market, kind, bas_dd) == bas_dd

    def _date_complete_for_markets(self, markets: list[str], iso_date: str | None) -> bool:
        normalized = self._normalize_iso_date(iso_date)
        if not normalized:
            return False
        key = normalized.replace("-", "")
        return all(
            self._day_has_data(market, key, "stock")
            and self._day_has_data(market, key, "index")
            for market in markets
        )

    def _latest_common_complete_date(
        self,
        markets: list[str],
        *,
        end_date: date | str | None = None,
    ) -> str | None:
        if not markets:
            return None
        if isinstance(end_date, date):
            end_key = self._compact(end_date)
        elif end_date:
            normalized = self._normalize_iso_date(str(end_date))
            end_key = normalized.replace("-", "") if normalized else str(end_date).replace("-", "")
        else:
            end_key = None

        # Every candidate must exist for both stock rows and the representative
        # market index in every selected market. Repeatedly lower the upper bound
        # until all four (or two for a single-market scan) converge on one day.
        for _ in range(self.LATEST_CONFIRM_LOOKBACK_DAYS * 2):
            latest_values: list[str] = []
            for market in markets:
                for kind in ("stock", "index"):
                    value = self.market_store.latest_complete_date(market, kind, end_key)
                    if not value:
                        return None
                    latest_values.append(str(value))
            candidate = min(latest_values)
            candidate_iso = self._iso(candidate)
            if self._date_complete_for_markets(markets, candidate_iso):
                return candidate_iso
            try:
                candidate_day = date.fromisoformat(candidate_iso)
            except ValueError:
                return None
            end_key = self._compact(candidate_day - timedelta(days=1))
        return None

    async def _krx_stock_daily(self, market: str, day: date, *, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh:
            return await self.krx.stock_daily(market, day)
        try:
            return await self.krx.stock_daily(market, day, force_refresh=True)
        except TypeError as exc:
            if "force_refresh" not in str(exc):
                raise
            return await self.krx.stock_daily(market, day)

    async def _krx_index_daily(self, market: str, day: date, *, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh:
            return await self.krx.index_daily(market, day)
        try:
            return await self.krx.index_daily(market, day, force_refresh=True)
        except TypeError as exc:
            if "force_refresh" not in str(exc):
                raise
            return await self.krx.index_daily(market, day)

    async def _store_stock_rows(self, market: str, bas_dd: str) -> list[dict[str, Any]]:
        if hasattr(self.market_store, "stock_day_rows"):
            return await asyncio.to_thread(self.market_store.stock_day_rows, market, bas_dd)
        source = getattr(self.market_store, "stock_days", {})
        return [dict(row) for row in source.get((market, bas_dd), [])]

    async def _store_index_row(self, market: str, bas_dd: str) -> dict[str, Any] | None:
        if hasattr(self.market_store, "index_day_row"):
            return await asyncio.to_thread(self.market_store.index_day_row, market, bas_dd)
        source = getattr(self.market_store, "index_days", {})
        row = source.get((market, bas_dd))
        return dict(row) if isinstance(row, dict) else None

    async def _replace_stock_snapshot(self, market: str, bas_dd: str, rows: list[dict[str, Any]]) -> int:
        writer = getattr(self.market_store, "replace_stock_day", self.market_store.put_stock_day)
        return await asyncio.to_thread(writer, market, bas_dd, rows, stable=True)

    async def _replace_index_snapshot(self, market: str, bas_dd: str, row: dict[str, Any]) -> None:
        writer = getattr(self.market_store, "replace_index_day", self.market_store.put_index_day)
        await asyncio.to_thread(writer, market, bas_dd, row, stable=True)

    @staticmethod
    def _result_date_aligned(payload: dict[str, Any], scope: str, expected_date: date) -> bool:
        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
        data_dates = payload.get("data_dates") or {}
        expected = expected_date.isoformat()
        return all(str(data_dates.get(market) or "") == expected for market in markets)

    @staticmethod
    def _compare_stock_snapshots(expected: list[dict[str, Any]], actual: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
        fields = ("open", "high", "low", "close", "volume")
        exp = {str(row.get("code") or "").strip().upper(): row for row in expected if str(row.get("code") or "").strip()}
        act = {str(row.get("code") or "").strip().upper(): row for row in actual if str(row.get("code") or "").strip()}
        missing = sorted(set(exp) - set(act))
        unexpected = sorted(set(act) - set(exp))
        mismatches: list[dict[str, Any]] = []
        mismatch_count = 0
        for code in sorted(set(exp) & set(act)):
            changed = {field: {"expected": exp[code].get(field), "actual": act[code].get(field)} for field in fields if exp[code].get(field) != act[code].get(field)}
            if changed:
                mismatch_count += 1
                if len(mismatches) < limit:
                    mismatches.append({"code": code, "name": exp[code].get("name") or act[code].get("name"), "fields": changed})
        return {
            "expected_rows": len(exp),
            "actual_rows": len(act),
            "missing_tickers": len(missing),
            "unexpected_tickers": len(unexpected),
            "ohlcv_mismatch": mismatch_count,
            "missing_sample": missing[:limit],
            "unexpected_sample": unexpected[:limit],
            "mismatch_sample": mismatches,
            "matches": not missing and not unexpected and mismatch_count == 0,
        }

    async def audit_input_data(
        self,
        *,
        market_scope: str = "ALL",
        as_of_date: str | None = None,
        trace_code: str = "192820",
    ) -> dict[str, Any]:
        """Force-read KRX and verify KRX cache -> Market Store -> Scanner input integrity."""
        scope = market_scope.upper().strip()
        if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
            raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")
        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
        if as_of_date:
            audit_day = date.fromisoformat(as_of_date)
        else:
            requested_end = self.krx._today_kst() - timedelta(days=1)  # noqa: SLF001
            stored_common = self._latest_common_complete_date(markets, end_date=requested_end)
            audit_day = date.fromisoformat(stored_common) if stored_common else requested_end
        compact = self._compact(audit_day)
        iso = audit_day.isoformat()
        results: dict[str, Any] = {}
        corrected = False
        await self.krx.open_session()
        try:
            for market in markets:
                cache_stock = self.krx.cached_daily_snapshot(market, audit_day, "stock")
                cache_index = self.krx.cached_daily_snapshot(market, audit_day, "index")
                store_before = await self._store_stock_rows(market, compact)
                index_before = await self._store_index_row(market, compact)

                direct_stock_result = await self._krx_stock_daily(market, audit_day, force_refresh=True)
                direct_rows = list(direct_stock_result.get("rows") or [])
                if not direct_rows:
                    raise ProviderError(f"{market} {iso} KRX 직접 주식 시세가 비어 있습니다.")
                if any(self._iso(str(row.get("date") or "")) != iso for row in direct_rows):
                    raise ProviderError(f"{market} {iso} KRX 주식 응답 기준일이 요청일과 다릅니다.")

                direct_index_result = await self._krx_index_daily(market, audit_day, force_refresh=True)
                direct_index_rows = list(direct_index_result.get("rows") or [])
                direct_index = self.krx._select_main_index(direct_index_rows, market) if direct_index_rows else None  # noqa: SLF001
                if direct_index is None or self._iso(str(direct_index.get("date") or "")) != iso:
                    raise ProviderError(f"{market} {iso} KRX 대표지수를 확인하지 못했습니다.")

                cache_compare = self._compare_stock_snapshots(direct_rows, list(cache_stock.get("rows") or [])) if cache_stock.get("source") != "none" else None
                store_compare_before = self._compare_stock_snapshots(direct_rows, store_before)
                index_cache_rows = list(cache_index.get("rows") or [])
                cached_main = self.krx._select_main_index(index_cache_rows, market) if index_cache_rows else None  # noqa: SLF001
                index_cache_match = cached_main == direct_index if cache_index.get("source") != "none" else None
                index_store_match_before = index_before == direct_index

                await self._replace_stock_snapshot(market, compact, direct_rows)
                await self._replace_index_snapshot(market, compact, direct_index)
                store_after = await self._store_stock_rows(market, compact)
                index_after = await self._store_index_row(market, compact)
                store_compare_after = self._compare_stock_snapshots(direct_rows, store_after)
                if not store_compare_after["matches"] or index_after != direct_index:
                    raise ProviderError(f"{market} {iso} Market Store read-back 검증에 실패했습니다.")
                if hasattr(self.market_store, "mark_integrity_verified"):
                    await asyncio.to_thread(
                        self.market_store.mark_integrity_verified,
                        market,
                        compact,
                        self.DATA_INTEGRITY_VERSION,
                        stock_rows=len(store_after),
                        stock_hash=self._fingerprint_rows(store_after),
                        index_hash=self._fingerprint_rows([index_after]),
                        verified_at=datetime.now().isoformat(timespec="seconds"),
                    )

                had_difference = (cache_compare is not None and not cache_compare["matches"]) or not store_compare_before["matches"] or index_cache_match is False or not index_store_match_before
                corrected = corrected or had_difference
                direct_map = {str(row.get("code") or "").strip().upper(): row for row in direct_rows}
                before_map = {str(row.get("code") or "").strip().upper(): row for row in store_before}
                after_map = {str(row.get("code") or "").strip().upper(): row for row in store_after}
                trace = {
                    "code": trace_code,
                    "krx_direct": direct_map.get(trace_code),
                    "store_before": before_map.get(trace_code),
                    "store_after": after_map.get(trace_code),
                    "scanner_input": after_map.get(trace_code),
                }
                results[market] = {
                    "date": iso,
                    "krx_rows": len(direct_rows),
                    "raw_cache_source_before": cache_stock.get("source"),
                    "raw_cache_compare_before": cache_compare,
                    "market_store_compare_before": store_compare_before,
                    "market_store_compare_after": store_compare_after,
                    "index_cache_match_before": index_cache_match,
                    "index_store_match_before": index_store_match_before,
                    "index_store_match_after": index_after == direct_index,
                    "stock_hash": self._fingerprint_rows(direct_rows),
                    "trace": trace,
                }
        finally:
            await self.krx.close_session()

        fingerprint_payload = {market: {"date": item["date"], "stock_hash": item["stock_hash"], "krx_rows": item["krx_rows"]} for market, item in results.items()}
        fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
        return {
            "status": "CORRECTED" if corrected else "PASS",
            "analysis_date": iso,
            "market_scope": scope,
            "input_fingerprint": fingerprint,
            "markets": results,
            "message": "KRX 원본과 저장 데이터를 비교해 불일치를 교정했습니다." if corrected else "KRX 원본과 저장 데이터가 일치합니다.",
        }

    async def prepare_latest_confirmed_data(
        self,
        *,
        market_scope: str = "ALL",
        known_data_date: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Resolve one effective EOD date without ever regressing a valid current date.

        The date shown by Scanner is only considered valid when stock rows and the
        representative index are complete for every selected market on that exact
        date. A refresh may advance that date, but a provider failure cannot silently
        move a valid analysis backward.
        """
        scope = market_scope.upper().strip()
        if scope not in {"ALL", "KOSPI", "KOSDAQ"}:
            raise ValueError("market_scope은 ALL, KOSPI, KOSDAQ 중 하나여야 합니다.")
        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]
        prepare_total = 3 + 2 * len(markets)
        today = self.krx._today_kst()  # noqa: SLF001 - provider and Scanner share KST boundary
        requested_end = today - timedelta(days=1)
        normalized_known = self._normalize_iso_date(known_data_date)
        prepare_started_at = time.perf_counter()
        completed_stages: list[str] = []
        reused_stages: list[str] = []
        current_prepare_stage = "scanner_prepare_local"

        def prepare_details(*, status: str, current_item: str | None = None, **extra: Any) -> dict[str, Any]:
            return {
                "stage_status": status,
                "market_scope": scope,
                "completed_stages": list(completed_stages),
                "reused_stages": list(reused_stages),
                "current_item": current_item,
                "elapsed_seconds": round(max(0.0, time.perf_counter() - prepare_started_at), 1),
                "heartbeat_at": datetime.now().isoformat(timespec="seconds"),
                **extra,
            }

        def emit_prepare(
            stage: str,
            message: str,
            *,
            status: str = "RUNNING",
            current_item: str | None = None,
            reused: bool = False,
            complete: bool = False,
            **extra: Any,
        ) -> None:
            nonlocal current_prepare_stage
            current_prepare_stage = stage
            if complete and stage not in completed_stages:
                completed_stages.append(stage)
            if reused and stage not in reused_stages:
                reused_stages.append(stage)
            self._emit(
                progress,
                stage=stage,
                message=message,
                current=len(completed_stages),
                total=prepare_total,
                details=prepare_details(
                    status="REUSED" if reused else ("COMPLETED" if complete else status),
                    current_item=current_item,
                    **extra,
                ),
            )

        async def await_with_heartbeat(awaitable: Any, *, stage: str, message: str, current_item: str | None = None) -> Any:
            task = asyncio.create_task(awaitable)
            while True:
                try:
                    return await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except asyncio.TimeoutError:
                    emit_prepare(
                        stage,
                        message,
                        status="RUNNING",
                        current_item=current_item,
                        waiting_for_provider=True,
                    )

        emit_prepare(
            "scanner_prepare_local",
            "로컬 저장 데이터를 확인하는 중",
            current_item="Market Store",
        )

        previous_stock_dates = {
            market: (
                self._iso(value)
                if (value := self.market_store.latest_complete_date(market, "stock", self._compact(requested_end)))
                else None
            )
            for market in markets
        }
        previous_index_dates = {
            market: (
                self._iso(value)
                if (value := self.market_store.latest_complete_date(market, "index", self._compact(requested_end)))
                else None
            )
            for market in markets
        }
        stored_common_before = self._latest_common_complete_date(markets, end_date=requested_end)
        known_date_valid_before = bool(
            normalized_known and self._date_complete_for_markets(markets, normalized_known)
        )
        current_valid_date = normalized_known if known_date_valid_before else None
        effective_before = current_valid_date or stored_common_before
        emit_prepare(
            "scanner_prepare_local",
            "로컬 저장 데이터 확인 완료",
            current_item=effective_before or "저장 데이터 없음",
            complete=True,
        )

        before = self.krx.request_stats()
        updated_dates: set[str] = set()

        def diagnostics() -> dict[str, int]:
            delta = self._stats_delta(before, self.krx.request_stats())
            return {
                "network_requests": int(delta.get("network_requests", 0)),
                "raw_cache_hits": int(
                    delta.get("disk_hits", 0)
                    + delta.get("memory_hits", 0)
                    + delta.get("empty_marker_hits", 0)
                ),
                "retries": int(delta.get("retries", 0)),
                "forced_network_requests": int(delta.get("forced_network_requests", 0)),
            }

        try:
            await self.krx.open_session()
            primary_market = markets[0]
            primary_result: dict[str, Any] | None = None
            resolved_day: date | None = None

            # Fast path only when every selected market has both stock and index data
            # for the requested date. Stock-only presence is not sufficient.
            requested_iso = requested_end.isoformat()
            emit_prepare(
                "scanner_prepare_probe",
                "최신 확정 거래일을 확인하는 중",
                current_item=requested_iso,
            )
            if self._date_complete_for_markets(markets, requested_iso):
                resolved_day = requested_end
                emit_prepare(
                    "scanner_prepare_probe",
                    f"최신 분석 기준일 {requested_iso} 확인",
                    current_item=requested_iso,
                    reused=True,
                    complete=True,
                )
            else:
                for candidate in self.krx._candidate_dates(
                    requested_end, self.LATEST_CONFIRM_LOOKBACK_DAYS
                ):  # noqa: SLF001
                    candidate_iso = candidate.isoformat()
                    probe = await await_with_heartbeat(
                        self._krx_stock_daily(primary_market, candidate, force_refresh=True),
                        stage="scanner_prepare_probe",
                        message="최신 확정 거래일을 확인하는 중",
                        current_item=candidate_iso,
                    )
                    if int(probe.get("count") or 0) > 0:
                        primary_result = probe
                        resolved_day = candidate
                        emit_prepare(
                            "scanner_prepare_probe",
                            f"최신 분석 기준일 {candidate_iso} 확인",
                            current_item=candidate_iso,
                            complete=True,
                        )
                        break

            if resolved_day is None:
                raise ProviderError(
                    f"최근 {self.LATEST_CONFIRM_LOOKBACK_DAYS}일 범위에서 최신 확정 KRX 일봉을 찾지 못했습니다."
                )

            resolved_key = self._compact(resolved_day)
            resolved_iso = resolved_day.isoformat()

            # A provider temporarily returning an older day must never make a valid
            # current analysis move backward. Keep the locally verified date and report
            # that no newer confirmed day was adopted.
            if current_valid_date and resolved_iso < current_valid_date:
                for market in markets:
                    emit_prepare(
                        f"scanner_prepare_{market.lower()}_stock",
                        f"{market} 종목 데이터 · 현재 저장 데이터 유지",
                        current_item=f"{market} 종목",
                        reused=True,
                        complete=True,
                    )
                    emit_prepare(
                        f"scanner_prepare_{market.lower()}_index",
                        f"{market} 지수 · 현재 저장 데이터 유지",
                        current_item=f"{market} 지수",
                        reused=True,
                        complete=True,
                    )
                emit_prepare(
                    "scanner_prepare_store",
                    "현재 분석 기준 데이터를 유지합니다.",
                    current_item=current_valid_date,
                    reused=True,
                    complete=True,
                )
                return {
                    "status": "READY",
                    "market_scope": scope,
                    "requested_date": requested_iso,
                    "latest_confirmed_date": resolved_iso,
                    "resolved_as_of_date": current_valid_date,
                    "known_data_date": normalized_known,
                    "previous_data_dates": previous_stock_dates,
                    "previous_index_dates": previous_index_dates,
                    "data_dates": {market: current_valid_date for market in markets},
                    "available_data_date": current_valid_date,
                    "stored_common_date": stored_common_before,
                    "current_date_valid": True,
                    "fallback_allowed": False,
                    "consistency_status": "CURRENT_RETAINED",
                    "market_data_updated": False,
                    "date_changed": False,
                    "updated_dates": [],
                    "diagnostics": diagnostics(),
                    "failure_reason": None,
                    "message": f"현재 {current_valid_date} 확정 일봉이 더 최신이므로 기존 분석 기준을 유지합니다.",
                }

            integrity_markets: dict[str, dict[str, Any]] = {}
            for market in markets:
                stock_stage = f"scanner_prepare_{market.lower()}_stock"
                index_stage = f"scanner_prepare_{market.lower()}_index"
                emit_prepare(
                    stock_stage,
                    f"{market} 종목 데이터를 확인하는 중",
                    current_item=f"{market} 종목",
                )
                previous_rows = await self._store_stock_rows(market, resolved_key)
                previous_index = await self._store_index_row(market, resolved_key)
                verification = (
                    await asyncio.to_thread(
                        self.market_store.integrity_verification,
                        market,
                        resolved_key,
                        self.DATA_INTEGRITY_VERSION,
                    )
                    if hasattr(self.market_store, "integrity_verification")
                    else None
                )
                current_stock_hash = self._fingerprint_rows(previous_rows) if previous_rows else None
                current_index_hash = self._fingerprint_rows([previous_index]) if previous_index else None
                verification_matches_store = bool(
                    verification
                    and int(verification.get("stock_rows") or 0) == len(previous_rows)
                    and verification.get("stock_hash") == current_stock_hash
                    and verification.get("index_hash") == current_index_hash
                    and self._day_has_data(market, resolved_key, "stock")
                    and self._day_has_data(market, resolved_key, "index")
                )

                if verification_matches_store:
                    emit_prepare(
                        stock_stage,
                        f"{market} 종목 데이터 · 저장 데이터 재사용",
                        current_item=f"{market} 종목",
                        reused=True,
                        complete=True,
                    )
                    emit_prepare(
                        index_stage,
                        f"{market} 지수 · 저장 데이터 재사용",
                        current_item=f"{market} 지수",
                        reused=True,
                        complete=True,
                    )
                    integrity_markets[market] = {
                        "mode": "VERIFIED_REUSE",
                        "krx_rows": len(previous_rows),
                        "stored_rows": len(previous_rows),
                        "ticker_mismatch": 0,
                        "ohlcv_mismatch": 0,
                        "snapshot_changed": False,
                        "verified_at": verification.get("verified_at"),
                    }
                    continue

                stock_result = (
                    primary_result
                    if market == primary_market and primary_result is not None
                    else await await_with_heartbeat(
                        self._krx_stock_daily(market, resolved_day, force_refresh=True),
                        stage=stock_stage,
                        message=f"{market} 종목 데이터를 KRX에서 확인하는 중",
                        current_item=f"{market} {resolved_iso} 종목",
                    )
                )
                stock_rows = list(stock_result.get("rows") or [])
                if not stock_rows:
                    raise ProviderError(f"{market} {resolved_iso} 확정 주식 시세를 확인하지 못했습니다.")
                wrong_stock_dates = [row for row in stock_rows if self._iso(str(row.get("date") or "")) != resolved_iso]
                if wrong_stock_dates:
                    raise ProviderError(f"{market} {resolved_iso} KRX 주식 응답의 기준일이 요청일과 일치하지 않습니다.")
                emit_prepare(
                    stock_stage,
                    f"{market} 종목 데이터 확인 완료",
                    current_item=f"{market} {len(stock_rows)}종목",
                    complete=True,
                    source="KRX",
                )

                emit_prepare(
                    index_stage,
                    f"{market} 지수를 확인하는 중",
                    current_item=f"{market} 지수",
                )
                index_result = await await_with_heartbeat(
                    self._krx_index_daily(market, resolved_day, force_refresh=True),
                    stage=index_stage,
                    message=f"{market} 지수를 KRX에서 확인하는 중",
                    current_item=f"{market} {resolved_iso} 지수",
                )
                index_rows = list(index_result.get("rows") or [])
                main_index = self.krx._select_main_index(index_rows, market) if index_rows else None  # noqa: SLF001
                if main_index is None:
                    raise ProviderError(f"{market} {resolved_iso} 확정 시장지수를 확인하지 못했습니다.")
                if self._iso(str(main_index.get("date") or "")) != resolved_iso:
                    raise ProviderError(f"{market} {resolved_iso} KRX 지수 응답의 기준일이 요청일과 일치하지 않습니다.")
                emit_prepare(
                    index_stage,
                    f"{market} 지수 확인 완료",
                    current_item=f"{market} {resolved_iso} 지수",
                    complete=True,
                    source="KRX",
                )

                await self._replace_stock_snapshot(market, resolved_key, stock_rows)
                await self._replace_index_snapshot(market, resolved_key, main_index)
                readback_rows = await self._store_stock_rows(market, resolved_key)
                readback_index = (await self._store_index_row(market, resolved_key)) or main_index
                if len(readback_rows) != len(stock_rows):
                    raise ProviderError(
                        f"{market} {resolved_iso} 저장 검증 실패: KRX {len(stock_rows)}건 / 저장 {len(readback_rows)}건"
                    )
                direct_map = {str(row.get("code") or "").strip().upper(): row for row in stock_rows}
                store_map = {str(row.get("code") or "").strip().upper(): row for row in readback_rows}
                mismatch = 0
                for code, direct_row in direct_map.items():
                    stored_row = store_map.get(code)
                    if stored_row is None or any(
                        direct_row.get(field) != stored_row.get(field)
                        for field in ("open", "high", "low", "close", "volume")
                    ):
                        mismatch += 1
                if mismatch or set(direct_map) != set(store_map) or readback_index != main_index:
                    raise ProviderError(f"{market} {resolved_iso} 저장된 KRX 데이터가 원본과 일치하지 않습니다.")

                stock_hash = self._fingerprint_rows(readback_rows)
                index_hash = self._fingerprint_rows([readback_index])
                if hasattr(self.market_store, "mark_integrity_verified"):
                    await asyncio.to_thread(
                        self.market_store.mark_integrity_verified,
                        market,
                        resolved_key,
                        self.DATA_INTEGRITY_VERSION,
                        stock_rows=len(readback_rows),
                        stock_hash=stock_hash,
                        index_hash=index_hash,
                        verified_at=datetime.now().isoformat(timespec="seconds"),
                    )
                changed = previous_rows != readback_rows or previous_index != readback_index
                if changed:
                    updated_dates.add(resolved_iso)
                integrity_markets[market] = {
                    "mode": "FORCED_KRX_VERIFY",
                    "krx_rows": len(stock_rows),
                    "stored_rows": len(readback_rows),
                    "ticker_mismatch": len(set(direct_map) ^ set(store_map)),
                    "ohlcv_mismatch": mismatch,
                    "snapshot_changed": changed,
                    "verified_at": datetime.now().isoformat(timespec="seconds"),
                }

            emit_prepare(
                "scanner_prepare_store",
                "저장 데이터를 최종 검증하는 중",
                current_item=resolved_iso,
            )
            if not self._date_complete_for_markets(markets, resolved_iso):
                raise ProviderError("최신 시세 저장 후 공통 분석 기준일을 확인하지 못했습니다.")
            emit_prepare(
                "scanner_prepare_store",
                "최신 확정 시세 준비 완료",
                current_item=resolved_iso,
                complete=True,
            )

            stored_common_after = self._latest_common_complete_date(markets, end_date=requested_end)
            effective_date = resolved_iso
            if current_valid_date and current_valid_date > effective_date:
                effective_date = current_valid_date

            comparison_date = effective_before
            date_changed = bool(comparison_date and comparison_date < effective_date)
            status = "UPDATED" if date_changed else "READY"
            return {
                "status": status,
                "market_scope": scope,
                "requested_date": requested_iso,
                "latest_confirmed_date": resolved_iso,
                "resolved_as_of_date": effective_date,
                "known_data_date": normalized_known,
                "previous_data_dates": previous_stock_dates,
                "previous_index_dates": previous_index_dates,
                "data_dates": {market: effective_date for market in markets},
                "available_data_date": effective_date,
                "stored_common_date": stored_common_after,
                "current_date_valid": bool(
                    normalized_known and self._date_complete_for_markets(markets, normalized_known)
                ),
                "fallback_allowed": False,
                "consistency_status": "ALIGNED",
                "market_data_updated": bool(updated_dates),
                "date_changed": date_changed,
                "updated_dates": sorted(updated_dates),
                "diagnostics": {
                    **diagnostics(),
                    "data_integrity": integrity_markets,
                    "progress": {
                        "completed_stages": list(completed_stages),
                        "reused_stages": list(reused_stages),
                    },
                },
                "failure_reason": None,
                "message": (
                    f"새로운 확정 시세를 확인했습니다. {effective_date} 기준으로 분석합니다."
                    if date_changed
                    else f"{effective_date} 확정 일봉 기준으로 분석할 수 있습니다."
                ),
            }
        except (ProviderError, ValueError) as exc:
            stored_common_after = self._latest_common_complete_date(markets, end_date=requested_end)
            known_date_valid_after = bool(
                normalized_known and self._date_complete_for_markets(markets, normalized_known)
            )
            if known_date_valid_after:
                available_date = normalized_known
                status = "UPDATE_FAILED"
                fallback_allowed = False
                consistency_status = "CURRENT_VALID_REFRESH_FAILED"
                message = (
                    f"새로운 확정 시세를 가져오지 못했습니다. 현재 {normalized_known} 확정 일봉은 계속 사용할 수 있습니다."
                )
                resolved_as_of = normalized_known
            elif normalized_known:
                available_date = stored_common_after
                status = "DATA_INCONSISTENT"
                fallback_allowed = bool(stored_common_after)
                consistency_status = "CURRENT_DATE_INVALID"
                message = (
                    "현재 분석 기준 데이터를 다시 확인해야 합니다. "
                    "저장된 시세와 현재 분석 기준일이 일치하지 않습니다."
                )
                resolved_as_of = None
            else:
                available_date = stored_common_after
                status = "UPDATE_FAILED"
                fallback_allowed = bool(stored_common_after)
                consistency_status = "NO_CURRENT_ANALYSIS"
                message = "최신 확정 시세를 가져오지 못했습니다."
                resolved_as_of = None

            return {
                "status": status,
                "market_scope": scope,
                "requested_date": requested_end.isoformat(),
                "latest_confirmed_date": None,
                "resolved_as_of_date": resolved_as_of,
                "known_data_date": normalized_known,
                "previous_data_dates": previous_stock_dates,
                "previous_index_dates": previous_index_dates,
                "data_dates": previous_stock_dates,
                "available_data_date": available_date,
                "stored_common_date": stored_common_after,
                "current_date_valid": known_date_valid_after,
                "fallback_allowed": fallback_allowed,
                "consistency_status": consistency_status,
                "market_data_updated": False,
                "date_changed": False,
                "updated_dates": [],
                "diagnostics": {
                    **diagnostics(),
                    "progress": {
                        "completed_stages": list(completed_stages),
                        "reused_stages": list(reused_stages),
                        "failed_stage": current_prepare_stage,
                    },
                },
                "failure_reason": str(exc),
                "message": message,
            }
        finally:
            await self.krx.close_session()

    def _history_plan(self, *, market: str, start: date, end: date) -> dict[str, Any]:
        dates = self._weekdays(start, end)
        start_key = self._compact(start)
        end_key = self._compact(end)
        if hasattr(self.market_store, "day_status_range"):
            statuses = self.market_store.day_status_range(market, start_key, end_key)
        else:
            statuses = {}

        work: list[tuple[str, date]] = []
        for day in dates:
            key = self._compact(day)
            for kind in ("stock", "index"):
                complete = (key, kind) in statuses if statuses else self.market_store.day_complete(market, key, kind)
                if not complete:
                    work.append((kind, day))
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
    def _fingerprint_rows(rows: list[dict[str, Any]]) -> str:
        canonical = [
            {key: row.get(key) for key in ("date", "code", "name", "open", "high", "low", "close", "volume")}
            for row in sorted(rows, key=lambda item: str(item.get("code") or ""))
        ]
        raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def _build_input_fingerprint(self, markets: list[str], data_dates: dict[str, str]) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for market in markets:
            market_date = str(data_dates.get(market) or "")
            key = market_date.replace("-", "")
            stock_snapshot = self.market_store.stock_day_rows(market, key) if key else []
            index_snapshot = self.market_store.index_day_row(market, key) if key and hasattr(self.market_store, "index_day_row") else None
            details[market] = {
                "date": market_date or None,
                "stock_rows": len(stock_snapshot),
                "stock_hash": self._fingerprint_rows(stock_snapshot) if stock_snapshot else None,
                "index_hash": self._fingerprint_rows([index_snapshot]) if index_snapshot else None,
            }
        payload = {"scanner_version": self.VERSION, "markets": details}
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return {"id": fingerprint, **payload}

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

    async def _prepare_sector_inputs_for_quick_pool(
        self,
        *,
        quick_inputs: list[tuple[str, dict[str, Any]]],
        latest_dates: dict[str, str],
    ) -> tuple[dict[tuple[str, str], HistoricalSectorInput], dict[str, Any]]:
        """Prefetch current-metadata Sector RS inputs once per code/date for audit.

        Disabled by default. When enabled, company metadata is resolved once per
        unique code and KRX index_daily is fetched once per market/date, then shared
        by every sector mapping. BacktestEngine receives only prepared rows and does
        no network I/O.
        """
        if self.sector_prefetcher is None:
            return {}, {"enabled": False, "temporal_status": None, "markets": {}}

        by_market: dict[str, list[str]] = {}
        for market, row in quick_inputs:
            code = str(row.get("code") or "").strip()
            if code:
                by_market.setdefault(str(market), []).append(code)

        prepared: dict[tuple[str, str], HistoricalSectorInput] = {}
        market_stats: dict[str, Any] = {}
        totals = {
            "unique_codes": 0,
            "company_requests": 0,
            "company_cache_hits": 0,
            "industry_code_available": 0,
            "industry_mapped": 0,
            "industry_unmapped": 0,
            "unique_sector_alias_sets": 0,
            "index_daily_calls": 0,
            "index_cache_hits": 0,
            "index_days_with_data": 0,
            "benchmark_resolved": 0,
            "sector_history_available": 0,
            "errors": 0,
        }
        for market, codes in by_market.items():
            as_of = latest_dates.get(market)
            if not as_of:
                continue
            sector_map, stats = await self.sector_prefetcher.prepare(
                market=market,
                codes=codes,
                as_of=as_of,
                points=self.engine.RELATIVE_STRENGTH_POINTS,
                lookback_days=140,
            )
            market_stats[market] = stats
            for code, sector_input in sector_map.items():
                prepared[(market, code)] = sector_input
            for key in totals:
                totals[key] += int(stats.get(key) or 0)

        return prepared, {
            "enabled": True,
            "temporal_status": "STATIC_CURRENT",
            "production_enabled": False,
            "production_gate": "POINT_IN_TIME_REQUIRED",
            "totals": totals,
            "markets": market_stats,
        }

    def _quick_current_candidate(
        self,
        *,
        market: str,
        latest_date: str,
        row: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        sector_input: HistoricalSectorInput | None = None,
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
            sector_input=sector_input,
        )
        if snapshot is None:
            return None

        evaluations = list((snapshot.get("evaluations") or {}).values())
        evaluations.sort(
            key=lambda item: (bool(getattr(item, "eligible", False)), int(getattr(item, "score", 0) or 0)),
            reverse=True,
        )
        best: dict[str, Any] | None = None
        strategy_trace: list[dict[str, Any]] = []
        for index, evaluation in enumerate(evaluations):
            strategy = evaluation.strategy
            strategy_name = str(getattr(strategy, "value", strategy) or "")
            trace_row: dict[str, Any] = {
                "strategy": strategy_name,
                "selector_rank": index + 1,
                "selector_eligible": bool(getattr(evaluation, "eligible", False)),
                "selector_score": int(getattr(evaluation, "score", 0) or 0),
                "selector_reasons": [str(item) for item in (getattr(evaluation, "reasons", None) or [])],
                "selector_unmet": [str(item) for item in (getattr(evaluation, "unmet", None) or [])],
                "current_evaluated": index < 3,
            }
            if index >= 3:
                strategy_trace.append(trace_row)
                continue

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
            trace_row.update({
                "current_status": str(current.get("status") or ""),
                "current_internal_score": round(score, 4),
                "passed": int(current.get("passed") or condition_state.get("passed") or 0),
                "total": int(current.get("total") or condition_state.get("total") or 0),
                "missing": int(
                    current.get("missing")
                    or condition_state.get("missing")
                    or max(
                        0,
                        int(current.get("total") or condition_state.get("total") or 0)
                        - int(current.get("passed") or condition_state.get("passed") or 0),
                    )
                ),
                "risk_status": current.get("risk_status"),
                "risk_warning": bool(current.get("risk_warning")),
                "warnings": [str(item) for item in (current.get("warnings") or [])],
            })
            strategy_trace.append(trace_row)
            if best is None or score > float(best["current"].get("internal_score") or 0.0):
                best = {
                    "strategy": strategy_name,
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
            "_strategy_trace": {
                "selection_method": "selector eligible/score 상위 3개를 현재 조건·Risk로 재평가한 뒤 current_internal_score 최대 전략 선택",
                "selected_strategy": best["strategy"],
                "evaluations": [
                    {**row, "selected": str(row.get("strategy") or "") == str(best["strategy"])}
                    for row in strategy_trace
                ],
            },
            "_sector_input_audit": dict(snapshot.get("sector_input_audit") or {}),
        }

    def _current_candidate(self, item: dict[str, Any]) -> dict[str, Any] | None:
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
            "_repro_condition_details": list(condition_state.get("conditions") or []),
            "_repro_trade_value": item.get("trade_value"),
            "_repro_market_cap": item.get("market_cap"),
            "_repro_history_points": item.get("history_points"),
            "_repro_strategy_trace": item.get("_strategy_trace") or {},
        }

    def _fast_candidate(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Backward-compatible alias for the canonical current-only candidate builder."""
        return self._current_candidate(item)

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
            "_repro_condition_details": list(current.get("conditions") or []),
            "_repro_trade_value": item.get("trade_value"),
            "_repro_market_cap": item.get("market_cap"),
            "_repro_history_points": item.get("history_points"),
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
        B.2.3.4b uses the result only as explanatory evidence after the current
        candidate and rank are determined. Local history never changes production
        strategy selection, tier, or rank.
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
        markets = ["KOSPI", "KOSDAQ"] if scope == "ALL" else [scope]

        if not force_refresh:
            cached = self._load_cache(scope, stable_end, candidate_limit)
            expected_dates = {market: stable_end.isoformat() for market in markets}
            current_fingerprint = (
                self._build_input_fingerprint(markets, expected_dates)
                if self._date_complete_for_markets(markets, stable_end.isoformat())
                else None
            )
            cached_fingerprint = ((cached or {}).get("input_fingerprint") or {}).get("id")
            if (
                cached is not None
                and self._result_date_aligned(cached, scope, stable_end)
                and current_fingerprint is not None
                and cached_fingerprint == current_fingerprint.get("id")
            ):
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
                cached_diagnostics = cached.setdefault("diagnostics", {})
                cached_diagnostics["reproducibility_audit"] = {
                    "written": False,
                    "skipped": "backend_cache",
                    "analysis_date": stable_end.isoformat(),
                    "result_source": "backend_cache",
                    "message": "재현성 비교 파일은 새 계산 결과만 기록합니다. '다시 분석'으로 새 계산을 실행하세요.",
                }
                return cached

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

        plans: dict[str, dict[str, Any]] = {}
        for plan_position, market in enumerate(markets, start=1):
            plans[market] = self._history_plan(market=market, start=fast_start, end=stable_end)
            self._emit(
                progress,
                stage="scanner_plan",
                message=f"{market} 저장 데이터 상태를 확인했습니다.",
                current=plan_position,
                total=max(len(markets), 1),
                details=self._progress_payload(
                    overall_percent=4 + 4.0 * plan_position / max(len(markets), 1),
                    started_at=started_at,
                    current_item=market,
                    items_done=plan_position,
                    items_total=len(markets),
                ),
            )
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

            if as_of_date is not None:
                expected_iso = stable_end.isoformat()
                missing_or_misaligned = [
                    market for market in markets if latest_dates.get(market) != expected_iso
                ]
                if missing_or_misaligned:
                    joined = ", ".join(missing_or_misaligned)
                    raise ProviderError(
                        f"종목 찾기 분석 기준일을 {expected_iso}로 맞추지 못했습니다. "
                        f"다시 최신 확정 시세를 확인해 주세요. ({joined})"
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

            sector_inputs_by_code, sector_prefetch_stats = await self._prepare_sector_inputs_for_quick_pool(
                quick_inputs=quick_inputs,
                latest_dates=latest_dates,
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
                    sector_input=sector_inputs_by_code.get((market, code)),
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

            # Production current decisions are intentionally history-coverage agnostic.
            # Optional long history is attached later as Historical Evidence only.
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
                code = str(item["code"])
                deep = self._current_candidate(item)
                if deep is not None:
                    current_only_count += 1
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
            # attaches local three-year evidence only as explanation, then applies a
            # deterministic current-only priority rule. Optional local history never
            # changes today's strategy or production rank.
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
                message="현재 조건·Risk·진입 거리·현재 전략 적합도로 후보 우선순위를 확정하는 중",
                current=1,
                total=1,
                details=self._progress_payload(overall_percent=99, started_at=started_at),
            )
            ranked_actionable, ranking_changes = rank_candidates(actionable)
            top = ranked_actionable[:candidate_limit]
            more = ranked_actionable[candidate_limit : candidate_limit + self.EXTRA_RESULT_LIMIT]

            delta = self._stats_delta(provider_before, self.krx.request_stats())
            budget = self.krx.budget_snapshot()
            input_fingerprint = self._build_input_fingerprint(markets, latest_dates)
            reproducibility_audit = write_scanner_reproducibility_audit(
                market_store=self.market_store,
                scanner_version=self.VERSION,
                market_scope=scope,
                analysis_date=stable_end,
                history_start=fast_start,
                candidate_history_start=validation_start_for_years(stable_end) - timedelta(days=self.THREE_YEAR_WARMUP_DAYS),
                markets=markets,
                latest_dates=latest_dates,
                ranked_candidates=ranked_actionable,
                input_fingerprint=input_fingerprint,
                ranking_changes=ranking_changes,
                result_source="fresh_analysis",
                candidate_pool_complete=True,
                project_root_hint=Path(__file__).resolve().parents[3],
            )
            for item in ranked_actionable:
                item.pop("internal_rank", None)
                item.pop("_strategy_fit_score", None)
                item.pop("_repro_condition_details", None)
                item.pop("_repro_trade_value", None)
                item.pop("_repro_market_cap", None)
                item.pop("_repro_history_points", None)
                item.pop("_repro_strategy_trace", None)
                item.pop("_sector_input_audit", None)

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
                "input_fingerprint": input_fingerprint,
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
                    "meaning": "상승 확률 순위가 아니라 현재 조건, Risk, 실제 진입 기준까지의 거리, 현재 전략 적합도로 먼저 확인할 후보를 정합니다. 3년 과거 근거는 현재 판단과 분리된 참고 정보입니다.",
                    "pipeline": ["최근 데이터 확인", "전체 종목 빠른 필터", "현재 10개 전략·Risk 확인", "현재 조건 → Risk → 진입 근접도 → 전략 적합도로 최종 우선순위", "후보별 3년 과거 근거를 참고 정보로 부착"],
                    "guardrail": "로컬 3년 데이터 보유량은 현재 전략·Risk·순위를 바꾸지 않습니다. 이 순위는 미래 상승 확률이나 매수 추천이 아닙니다.",
                },
                "diagnostics": {
                    "market_store_reused_items": aggregate_sync["store_hits"],
                    "estimated_network_requests": estimated_total,
                    "network_requests": int(delta.get("network_requests", aggregate_sync["network_requests"])),
                    "raw_cache_hits": int(delta.get("disk_hits", 0) + delta.get("memory_hits", 0) + delta.get("empty_marker_hits", 0)),
                    "retries": int(delta.get("retries", 0)),
                    "forced_network_requests": int(delta.get("forced_network_requests", 0)),
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
                    "sector_rs_prefetch": sector_prefetch_stats,
                    "reproducibility_audit": reproducibility_audit,
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

