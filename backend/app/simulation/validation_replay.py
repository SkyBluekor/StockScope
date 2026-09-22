from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from types import FunctionType
from typing import Any, Callable

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.market.providers.krx import KrxProvider

from .validation_catalog import (
    HistoricalValidationCatalog,
    HistoricalValidationDraft,
    ValidationCatalogError,
)


ProgressCallback = Callable[[dict[str, Any]], None]


# PERF.1 — isolate Production reproducibility audit from Historical Replay
def _skip_replay_reproducibility_audit(**kwargs: Any) -> dict[str, Any]:
    analysis_date = kwargs.get("analysis_date")
    analysis_text = (
        analysis_date.isoformat()
        if hasattr(analysis_date, "isoformat")
        else str(analysis_date or "")
    )
    return {
        "written": False,
        "skipped": "historical_validation_replay",
        "analysis_date": analysis_text,
        "result_source": "historical_validation_replay",
    }


def _clone_scanner_run_for_replay():
    # Exact frozen Production Scanner.run code object; only this clone's
    # globals map replaces the heavy reproducibility-audit writer.
    production_run = StockScannerService.run
    replay_globals = dict(production_run.__globals__)
    if "write_scanner_reproducibility_audit" not in replay_globals:
        raise RuntimeError("Production Scanner.run audit dependency was not found.")

    replay_globals["write_scanner_reproducibility_audit"] = (
        _skip_replay_reproducibility_audit
    )
    replay_run = FunctionType(
        production_run.__code__,
        replay_globals,
        name=production_run.__name__,
        argdefs=production_run.__defaults__,
        closure=production_run.__closure__,
    )
    replay_run.__kwdefaults__ = dict(production_run.__kwdefaults__ or {})
    replay_run.__annotations__ = dict(production_run.__annotations__)
    replay_run.__doc__ = production_run.__doc__
    replay_run.__module__ = __name__
    replay_run.__qualname__ = "_ReplayStockScannerService.run"
    return replay_run


class _ReplayStockScannerService(StockScannerService):
    run = _clone_scanner_run_for_replay()


class HistoricalValidationReplayError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _ReplayLocalOnlyKrxProvider(KrxProvider):
    """KRX-compatible helper surface with network data calls hard-blocked."""

    def __init__(self) -> None:
        super().__init__(None)

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    async def stock_daily(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HistoricalValidationReplayError(
            "VAL_REPLAY_NETWORK_USED",
            "Historical Validation은 Market Store 전용입니다. KRX 네트워크 접근이 시도되었습니다.",
        )

    async def index_daily(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise HistoricalValidationReplayError(
            "VAL_REPLAY_NETWORK_USED",
            "Historical Validation은 Market Store 전용입니다. KRX 네트워크 접근이 시도되었습니다.",
        )


class HistoricalValidationReplayService:
    """Replay the frozen Production Scanner one confirmed market day at a time."""

    CANDIDATE_LIMIT = 5

    def __init__(
        self,
        catalog: HistoricalValidationCatalog,
        market_store: HistoricalMarketStore | Any | None = None,
        *,
        scanner_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.catalog = catalog
        self.catalog.initialize()
        self.market_store = market_store or HistoricalMarketStore()
        self.scanner_factory = scanner_factory or self._production_scanner

    def _production_scanner(self) -> StockScannerService:
        return _ReplayStockScannerService(
            _ReplayLocalOnlyKrxProvider(),
            market_store=self.market_store,
        )

    @staticmethod
    def _markets(scope: str) -> tuple[str, ...]:
        normalized = scope.strip().upper()
        if normalized == "ALL":
            return ("KOSPI", "KOSDAQ")
        if normalized in {"KOSPI", "KOSDAQ"}:
            return (normalized,)
        raise HistoricalValidationReplayError(
            "VAL_REPLAY_DATA_INCOMPLETE",
            f"지원하지 않는 시장 범위입니다: {scope}",
        )

    @staticmethod
    def _compact(day: date) -> str:
        return day.strftime("%Y%m%d")

    @staticmethod
    def _iso_from_value(value: Any) -> str:
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return text

    def _resolve_replay_days(self, draft: HistoricalValidationDraft) -> list[date]:
        start = date.fromisoformat(draft.resolved_start_date)
        end = date.fromisoformat(draft.resolved_end_date)
        start_key = self._compact(start)
        end_key = self._compact(end)

        market_days: list[set[str]] = []
        for market in self._markets(draft.market_scope):
            statuses = self.market_store.day_status_range(market, start_key, end_key)
            market_days.append(
                {
                    day_key
                    for (day_key, kind), status in statuses.items()
                    if kind == "stock" and status == "data"
                }
            )

        common = set.intersection(*market_days) if market_days else set()
        days = [date(int(key[:4]), int(key[4:6]), int(key[6:8])) for key in sorted(common)]

        if (
            len(days) != int(draft.trading_day_count)
            or not days
            or days[0].isoformat() != draft.resolved_start_date
            or days[-1].isoformat() != draft.resolved_end_date
        ):
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_DATA_INCOMPLETE",
                "저장된 검증 기간과 현재 Market Store의 거래일 구성이 일치하지 않습니다.",
            )
        return days

    def _assert_local_inputs(self, draft: HistoricalValidationDraft, replay_day: date) -> None:
        history_start = replay_day - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS)
        start_key = self._compact(history_start)
        end_key = self._compact(replay_day)
        missing: list[str] = []

        for market in self._markets(draft.market_scope):
            statuses = self.market_store.day_status_range(market, start_key, end_key)
            replay_stock = statuses.get((end_key, "stock"))
            replay_index = statuses.get((end_key, "index"))
            if replay_stock != "data" or replay_index != "data":
                missing.append(f"{market}:{replay_day.isoformat()}:stock/index")

            cursor = history_start
            while cursor <= replay_day:
                if cursor.weekday() < 5:
                    key = self._compact(cursor)
                    for kind in ("stock", "index"):
                        if (key, kind) not in statuses:
                            missing.append(f"{market}:{cursor.isoformat()}:{kind}")
                            if len(missing) >= 8:
                                break
                if len(missing) >= 8:
                    break
                cursor += timedelta(days=1)
            if len(missing) >= 8:
                break

        if missing:
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_DATA_INCOMPLETE",
                "Replay에 필요한 Market Store 이력이 부족합니다: " + ", ".join(missing),
            )

    def _validate_point_in_time(
        self,
        draft: HistoricalValidationDraft,
        replay_day: date,
        result: dict[str, Any],
    ) -> None:
        expected = replay_day.isoformat()
        requested_as_of = self._iso_from_value(result.get("requested_as_of"))
        if requested_as_of != expected:
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_DATE_MISMATCH",
                f"Scanner requested_as_of가 Replay 날짜와 다릅니다: {requested_as_of!r} != {expected}",
            )

        data_dates = result.get("data_dates") or {}
        for market in self._markets(draft.market_scope):
            actual = self._iso_from_value(data_dates.get(market))
            if actual > expected:
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_LOOKAHEAD_DETECTED",
                    f"{market} 데이터 날짜가 Replay 날짜보다 미래입니다: {actual} > {expected}",
                )
            if actual != expected:
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_DATE_MISMATCH",
                    f"{market} 데이터 날짜가 Replay 날짜와 다릅니다: {actual!r} != {expected}",
                )

        for bucket in ("candidates", "more_candidates"):
            for candidate in list(result.get(bucket) or []):
                actual = self._iso_from_value(candidate.get("data_date"))
                if actual > expected:
                    raise HistoricalValidationReplayError(
                        "VAL_REPLAY_LOOKAHEAD_DETECTED",
                        f"후보 {candidate.get('code')}가 미래 데이터를 사용했습니다: {actual} > {expected}",
                    )
                if actual != expected:
                    raise HistoricalValidationReplayError(
                        "VAL_REPLAY_DATE_MISMATCH",
                        f"후보 {candidate.get('code')} 데이터 날짜가 Replay 날짜와 다릅니다: {actual!r} != {expected}",
                    )

        diagnostics = result.get("diagnostics") or {}
        if int(diagnostics.get("network_requests") or 0) != 0:
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_NETWORK_USED",
                "Historical Validation 중 네트워크 요청이 감지되었습니다.",
            )

        if bool(result.get("partial_data")):
            preparation_required = list(result.get("preparation_required") or [])
            summary = result.get("summary") or {}
            evidence_unavailable = int(summary.get("three_year_evidence_data_unavailable") or 0)

            # Production Scanner v0.21.3.7 marks the whole response partial when
            # three-year Historical Evidence is unavailable. That evidence is
            # explanatory only: Scanner strategy, Risk and ranking are determined
            # before it is attached. Historical Validation therefore accepts this
            # evidence-only partial state while preserving DATA_UNAVAILABLE inside
            # each candidate snapshot. Missing recent Scanner inputs still fail.
            evidence_only_partial = not preparation_required and evidence_unavailable > 0
            if not evidence_only_partial:
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_DATA_INCOMPLETE",
                    "Scanner 핵심 판단에 필요한 Market Store 데이터가 부족해 Historical Validation을 중단합니다.",
                )

    @staticmethod
    def _normalize_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for source_key, bucket in (("candidates", "TOP"), ("more_candidates", "MORE")):
            for candidate in list(result.get(source_key) or []):
                snapshot = dict(candidate)
                normalized.append(
                    {
                        "market": str(candidate.get("market") or "").strip().upper(),
                        "ticker": str(candidate.get("code") or "").strip(),
                        "name": str(candidate.get("name") or "").strip(),
                        "rank": candidate.get("rank"),
                        "result_bucket": bucket,
                        "strategy": candidate.get("strategy"),
                        "decision_status": candidate.get("candidate_state"),
                        "snapshot": snapshot,
                    }
                )
        return normalized

    @staticmethod
    def _emit(progress: ProgressCallback | None, payload: dict[str, Any]) -> None:
        if progress is not None:
            progress(payload)

    async def run(
        self,
        validation_id: str,
        *,
        progress: ProgressCallback | None = None,
        preclaimed: bool = False,
    ) -> HistoricalValidationDraft:
        draft = self.catalog.get(validation_id)
        if draft is None:
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_NOT_FOUND",
                "저장된 검증을 찾을 수 없습니다.",
            )

        if preclaimed:
            if draft.status != "RUNNING":
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_INVALID_STATUS",
                    f"API에서 선점한 검증은 RUNNING 상태여야 합니다: {draft.status}",
                )
        elif draft.status == "RUNNING":
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_ALREADY_RUNNING",
                "이미 실행 중인 검증입니다.",
            )

        if draft.status == "COMPLETED":
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_ALREADY_COMPLETED",
                "이미 완료된 검증입니다.",
            )

        try:
            if draft.scanner_version != StockScannerService.VERSION:
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_SCANNER_VERSION_MISMATCH",
                    f"저장된 Scanner {draft.scanner_version}와 현재 Production Scanner {StockScannerService.VERSION}가 다릅니다.",
                )
            replay_days = self._resolve_replay_days(draft)
        except HistoricalValidationReplayError as exc:
            if preclaimed:
                self.catalog.mark_replay_failed(validation_id, exc.code, exc.message)
            raise

        if not preclaimed:
            try:
                self.catalog.begin_replay(validation_id)
            except ValidationCatalogError as exc:
                raise HistoricalValidationReplayError(exc.code, exc.message) from exc

        completed = self.catalog.completed_dates(validation_id)
        total = len(replay_days)

        for replay_day in replay_days:
            replay_iso = replay_day.isoformat()
            if replay_iso in completed:
                continue

            if self.catalog.cancel_requested(validation_id):
                return self.catalog.mark_replay_cancelled(validation_id)

            started_at = datetime.now(timezone.utc).isoformat()
            started_clock = perf_counter()
            try:
                self._assert_local_inputs(draft, replay_day)
                scanner = self.scanner_factory()
                result = await scanner.run(
                    market_scope=draft.market_scope,
                    as_of_date=replay_iso,
                    candidate_limit=self.CANDIDATE_LIMIT,
                    force_refresh=False,
                    allow_large_sync=False,
                )
                if not isinstance(result, dict):
                    raise HistoricalValidationReplayError(
                        "VAL_REPLAY_SCANNER_FAILED",
                        "Scanner 결과 형식이 올바르지 않습니다.",
                    )
                self._validate_point_in_time(draft, replay_day, result)
                candidates = self._normalize_candidates(result)
                duration_ms = max(0, int((perf_counter() - started_clock) * 1000))

                self.catalog.save_completed_day(
                    validation_id=validation_id,
                    trading_date=replay_iso,
                    scanner_version=draft.scanner_version,
                    market_scope=draft.market_scope,
                    scanner_cache_hit=bool(result.get("scanner_cache_hit")),
                    partial_data=bool(result.get("partial_data")),
                    input_fingerprint=result.get("input_fingerprint"),
                    market_summary=result.get("market_summary"),
                    summary=result.get("summary"),
                    methodology=result.get("methodology"),
                    diagnostics=result.get("diagnostics"),
                    candidates=candidates,
                    duration_ms=duration_ms,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                completed.add(replay_iso)
            except HistoricalValidationReplayError as exc:
                duration_ms = max(0, int((perf_counter() - started_clock) * 1000))
                self.catalog.record_failed_day(
                    validation_id=validation_id,
                    trading_date=replay_iso,
                    scanner_version=draft.scanner_version,
                    market_scope=draft.market_scope,
                    error_code=exc.code,
                    error_message=exc.message,
                    duration_ms=duration_ms,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                self.catalog.mark_replay_failed(validation_id, exc.code, exc.message)
                raise
            except Exception as exc:
                wrapped = HistoricalValidationReplayError(
                    "VAL_REPLAY_SCANNER_FAILED",
                    f"{replay_iso} Scanner 재생 중 오류가 발생했습니다: {exc}",
                )
                duration_ms = max(0, int((perf_counter() - started_clock) * 1000))
                self.catalog.record_failed_day(
                    validation_id=validation_id,
                    trading_date=replay_iso,
                    scanner_version=draft.scanner_version,
                    market_scope=draft.market_scope,
                    error_code=wrapped.code,
                    error_message=wrapped.message,
                    duration_ms=duration_ms,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                self.catalog.mark_replay_failed(validation_id, wrapped.code, wrapped.message)
                raise wrapped from exc

            current = self.catalog.get(validation_id)
            if current is None:
                raise HistoricalValidationReplayError(
                    "VAL_REPLAY_NOT_FOUND",
                    "실행 중 검증 레코드가 사라졌습니다.",
                )
            self._emit(
                progress,
                {
                    "validation_id": validation_id,
                    "current": current.processed_day_count,
                    "total": total,
                    "trading_date": replay_iso,
                    "candidate_count": current.candidate_count,
                    "message": f"{replay_iso} Scanner 재생 완료",
                },
            )

            if self.catalog.cancel_requested(validation_id):
                return self.catalog.mark_replay_cancelled(validation_id)

        final = self.catalog.get(validation_id)
        if final is None:
            raise HistoricalValidationReplayError(
                "VAL_REPLAY_NOT_FOUND",
                "실행 완료 시 검증 레코드를 찾을 수 없습니다.",
            )
        if final.processed_day_count != total or len(self.catalog.completed_dates(validation_id)) != total:
            error = HistoricalValidationReplayError(
                "VAL_REPLAY_DATA_INCOMPLETE",
                f"완료 거래일 수가 일치하지 않습니다: {final.processed_day_count}/{total}",
            )
            self.catalog.mark_replay_failed(validation_id, error.code, error.message)
            raise error

        return self.catalog.mark_replay_completed(validation_id)
