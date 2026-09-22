from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from app.backtest.models import BacktestConfig
from app.backtest.policy_lab import POLICY_CURRENT
from app.backtest.production_exit_policy import production_policy_cache_token
from app.backtest.scanner import StockScannerService
from app.market.providers.krx import KrxProvider
from app.strategy.models import StrategyName

from .execution_catalog import (
    HistoricalExecutionCatalog,
    HistoricalExecutionOutcome,
    HistoricalExecutionRun,
)
from .validation_catalog import HistoricalValidationCandidate


class ExecutionEngineError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _ExecutionLocalOnlyKrxProvider(KrxProvider):
    """Provider-compatible surface with every market-data network path blocked."""

    def __init__(self) -> None:
        super().__init__(None)

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    async def stock_daily(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ExecutionEngineError(
            "VAL2_NETWORK_USED",
            "Execution Validation은 Market Store 전용입니다.",
        )

    async def index_daily(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ExecutionEngineError(
            "VAL2_NETWORK_USED",
            "Execution Validation은 Market Store 전용입니다.",
        )


class HistoricalExecutionEngine:
    """Evaluate immutable VAL.1 candidates with the frozen execution policy.

    Signal reconstruction reads only rows <= D. D+1 and later rows are passed only
    to the existing Production execution simulator after the D signal is frozen.
    """

    MAX_HOLDING_DAYS = 20
    ROUND_TRIP_COST_PCT = 0.0

    def __init__(
        self,
        catalog: HistoricalExecutionCatalog,
        market_store: Any,
        *,
        scanner_factory: Callable[[], Any] | None = None,
        policy_token_provider: Callable[[], str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.catalog.initialize()
        self.market_store = market_store
        self.scanner_factory = scanner_factory or self._production_scanner
        self.policy_token_provider = (
            policy_token_provider or production_policy_cache_token
        )

    def _production_scanner(self) -> StockScannerService:
        return StockScannerService(
            _ExecutionLocalOnlyKrxProvider(),
            market_store=self.market_store,
        )

    @staticmethod
    def _compact(value: str) -> str:
        return str(value or "").replace("-", "")

    @staticmethod
    def _iso(value: str) -> str:
        text = str(value or "").replace("-", "")
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return str(value or "")

    @classmethod
    def _row_date(cls, row: dict[str, Any]) -> str:
        return cls._compact(str(row.get("date") or ""))

    @classmethod
    def _series_rows(cls, series: Any) -> list[dict[str, Any]]:
        rows_map = getattr(series, "rows", None)
        if not isinstance(rows_map, dict):
            return []
        rows: list[dict[str, Any]] = []
        for key, raw in sorted(rows_map.items(), key=lambda item: str(item[0])):
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if not row.get("date"):
                row["date"] = str(key)
            rows.append(row)
        rows.sort(key=cls._row_date)
        return rows

    @staticmethod
    def _number(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _strategy(candidate: HistoricalValidationCandidate) -> StrategyName:
        raw = str(candidate.strategy or "").strip()
        try:
            return StrategyName(raw)
        except ValueError as exc:
            raise ExecutionEngineError(
                "VAL2_STRATEGY_INVALID",
                f"VAL.1 candidate strategy를 해석할 수 없습니다: {raw!r}",
            ) from exc

    def _load_market_context(
        self,
        run: HistoricalExecutionRun,
        candidate: HistoricalValidationCandidate,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        signal_day = date.fromisoformat(candidate.trading_date)
        history_start = signal_day - timedelta(
            days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS
        )
        start_key = history_start.strftime("%Y%m%d")
        signal_key = signal_day.strftime("%Y%m%d")
        cutoff_key = self._compact(run.market_data_cutoff_date)

        series_map = self.market_store.stock_series_many(
            candidate.market,
            [candidate.ticker],
            start_key,
            cutoff_key,
        )
        stock_series = series_map.get(candidate.ticker)
        stock_rows = self._series_rows(stock_series)
        if not stock_rows:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_DATA_MISSING",
                f"{candidate.market}:{candidate.ticker} Market Store 이력이 없습니다.",
            )

        signal_indices = [
            index
            for index, row in enumerate(stock_rows)
            if self._row_date(row) == signal_key
        ]
        if len(signal_indices) != 1:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_DATA_MISSING",
                f"VAL.1 signal date 행을 정확히 찾지 못했습니다: "
                f"{candidate.ticker} {candidate.trading_date}",
            )
        signal_index = signal_indices[0]

        index_series = self.market_store.index_series(
            candidate.market,
            start_key,
            signal_key,
        )
        index_rows = self._series_rows(index_series)
        return stock_rows, index_rows, signal_index

    def _freeze_signal(
        self,
        scanner: Any,
        candidate: HistoricalValidationCandidate,
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        signal_index: int,
        config: BacktestConfig,
    ) -> tuple[dict[str, Any], StrategyName, dict[str, Any]]:
        signal_row = dict(stock_rows[signal_index])
        signal_row.setdefault("code", candidate.ticker)
        signal_row.setdefault("name", candidate.name)
        asof_rows = stock_rows[: signal_index + 1]

        quick = scanner._quick_current_candidate(  # noqa: SLF001
            market=candidate.market,
            latest_date=self._compact(candidate.trading_date),
            row=signal_row,
            stock_rows=asof_rows,
            index_rows=index_rows,
            sector_input=None,
        )
        if quick is None:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                f"D 시점 Scanner candidate를 재구성하지 못했습니다: "
                f"{candidate.ticker} {candidate.trading_date}",
            )

        rebuilt = scanner._current_candidate(quick)  # noqa: SLF001
        if rebuilt is None:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                "D 시점 Scanner current candidate 재구성에 실패했습니다.",
            )

        stored_action = str(candidate.snapshot.get("action") or "").strip()
        rebuilt_action = str(rebuilt.get("action") or "").strip()
        stored_state = str(candidate.decision_status or "").strip()
        rebuilt_state = str(rebuilt.get("candidate_state") or "").strip()
        stored_strategy = str(candidate.strategy or "").strip()
        rebuilt_strategy = str(quick.get("quick_strategy") or "").strip()

        mismatches: list[str] = []
        if rebuilt_strategy != stored_strategy:
            mismatches.append(
                f"strategy {rebuilt_strategy!r}!={stored_strategy!r}"
            )
        if rebuilt_action != stored_action:
            mismatches.append(f"action {rebuilt_action!r}!={stored_action!r}")
        if rebuilt_state != stored_state:
            mismatches.append(f"state {rebuilt_state!r}!={stored_state!r}")

        if mismatches:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                "; ".join(mismatches),
            )

        signal = scanner.engine._signal_snapshot(  # noqa: SLF001
            stock_rows=stock_rows,
            index_rows=index_rows,
            index=signal_index,
            config=config,
            sector_input=None,
        )
        if signal is None:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                "BacktestEngine D 시점 signal snapshot 재구성에 실패했습니다.",
            )

        audit = dict(signal.get("audit_context") or {})
        if bool(audit.get("future_data_used")):
            raise ExecutionEngineError(
                "VAL2_LOOKAHEAD_DETECTED",
                "D 시점 signal 재구성에서 미래 데이터 사용이 감지되었습니다.",
            )
        signal_date = self._iso(str(signal.get("signal_date") or ""))
        if signal_date != candidate.trading_date:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                f"signal date mismatch: {signal_date!r}!={candidate.trading_date!r}",
            )

        strategy = self._strategy(candidate)
        evaluation = (signal.get("evaluations") or {}).get(strategy.value)
        if evaluation is None:
            raise ExecutionEngineError(
                "VAL2_SIGNAL_PARITY_MISMATCH",
                f"D 시점 strategy evaluation이 없습니다: {strategy.value}",
            )

        # _signal_snapshot carries Pullback score fields for historical backtest
        # compatibility. Execution outcome decisions do not depend on these fields,
        # but keep the stored strategy's score in the emitted BacktestTrade metadata.
        score = getattr(evaluation, "score", None)
        signal["strategy_score"] = int(score or 0)
        signal["strategy_eligible"] = bool(getattr(evaluation, "eligible", False))

        parity = {
            "strategy": stored_strategy,
            "action": stored_action,
            "candidate_state": stored_state,
            "signal_date": candidate.trading_date,
            "future_data_used": False,
        }
        return signal, strategy, parity

    @staticmethod
    def _plan_prices(plan: Any) -> tuple[float | None, float | None, float | None]:
        stop = HistoricalExecutionEngine._number(
            getattr(plan, "invalidation_price", None)
        )
        target1 = HistoricalExecutionEngine._number(
            getattr(plan, "target1_price", None)
        )
        target2 = HistoricalExecutionEngine._number(
            getattr(plan, "target2_price", None)
        )
        return stop, target1, target2

    def evaluate_candidate(
        self,
        execution_run_id: str,
        candidate: HistoricalValidationCandidate,
    ) -> HistoricalExecutionOutcome:
        run = self.catalog.get_run(execution_run_id)
        if run is None:
            raise ExecutionEngineError(
                "VAL2_RUN_NOT_FOUND",
                f"Execution Validation run을 찾을 수 없습니다: {execution_run_id}",
            )
        if candidate.validation_id != run.validation_id:
            raise ExecutionEngineError(
                "VAL2_SOURCE_MISMATCH",
                "candidate가 Execution Validation source와 다릅니다.",
            )

        current_policy_token = str(self.policy_token_provider())
        if current_policy_token != run.production_exit_policy_token:
            raise ExecutionEngineError(
                "VAL2_EXIT_POLICY_TOKEN_MISMATCH",
                "Execution run 생성 후 Production Exit Policy가 변경되었습니다.",
            )

        existing = self.catalog.get_outcome(
            execution_run_id,
            candidate.trading_date,
            candidate.market,
            candidate.ticker,
        )
        if existing is not None:
            return existing

        action = str(candidate.snapshot.get("action") or "").strip()
        if action != "ENTRY_CANDIDATE":
            reason = {
                "WAIT": "SCANNER_WAIT",
                "NO_TRADE": "SCANNER_NO_TRADE",
            }.get(action, "SCANNER_NOT_ENTRY_CANDIDATE")
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="NOT_EXECUTED",
                outcome_reason=reason,
                details={
                    "source_action": action or None,
                    "execution_rule": "ENTRY_CANDIDATE_ONLY",
                },
            )

        scanner = self.scanner_factory()
        stock_rows, index_rows, signal_index = self._load_market_context(
            run,
            candidate,
        )

        config = BacktestConfig(
            code=candidate.ticker,
            market=candidate.market,
            start_date=candidate.trading_date,
            end_date=run.market_data_cutoff_date,
            initial_capital=10_000_000,
            max_holding_days=self.MAX_HOLDING_DAYS,
            round_trip_cost_pct=self.ROUND_TRIP_COST_PCT,
        )

        signal, strategy, parity = self._freeze_signal(
            scanner,
            candidate,
            stock_rows,
            index_rows,
            signal_index,
            config,
        )

        entry_index = signal_index + 1
        if entry_index >= len(stock_rows):
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="NO_ENTRY_DATA",
                outcome_reason="PENDING_FUTURE_DATA",
                details={
                    "signal_parity": parity,
                    "market_data_cutoff_date": run.market_data_cutoff_date,
                },
            )

        entry_row = stock_rows[entry_index]
        entry_date = self._iso(self._row_date(entry_row))
        entry_price = self._number(entry_row.get("open"))
        if entry_price is None or entry_price <= 0:
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="NO_ENTRY_DATA",
                outcome_reason="NEXT_TRADING_DAY_OPEN_UNAVAILABLE",
                entry_reference_date=entry_date or None,
                details={
                    "signal_parity": parity,
                    "market_data_cutoff_date": run.market_data_cutoff_date,
                },
            )

        plan, risk_trace = scanner.engine._build_risk_plan_for_policy(  # noqa: SLF001
            signal=signal,
            entry_price=entry_price,
            risk_policy=POLICY_CURRENT,
            strategy=strategy,
        )
        stop_price, target1_price, target2_price = self._plan_prices(plan)
        reference_only = bool(getattr(plan, "reference_only", False))

        if (
            reference_only
            or stop_price is None
            or target1_price is None
            or stop_price <= 0
            or stop_price >= entry_price
            or target1_price <= entry_price
        ):
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="RISK_PLAN_BLOCKED",
                outcome_reason=(
                    "REFERENCE_OR_MISSING_PLAN"
                    if reference_only or stop_price is None or target1_price is None
                    else "INVALID_PRICE_GEOMETRY"
                ),
                entry_reference_date=entry_date,
                entry_reference_price=entry_price,
                details={
                    "signal_parity": parity,
                    "risk_policy": POLICY_CURRENT,
                    "risk_trace": risk_trace,
                },
            )

        trade, _, resolution = scanner.multi.production_exit.simulate_trade(
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            strategy=strategy,
        )
        resolution_payload = (
            resolution.to_dict()
            if hasattr(resolution, "to_dict")
            else {"value": str(resolution)}
        )

        if trade is None:
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="RISK_PLAN_BLOCKED",
                outcome_reason="PRODUCTION_EXECUTION_UNAVAILABLE",
                entry_reference_date=entry_date,
                entry_reference_price=entry_price,
                stop_price=stop_price,
                target1_price=target1_price,
                target2_price=target2_price,
                details={
                    "signal_parity": parity,
                    "risk_trace": risk_trace,
                    "exit_policy": resolution_payload,
                },
            )

        trade_exit_reason = str(getattr(trade, "exit_reason", "") or "")
        details = {
            "signal_parity": parity,
            "signal_audit": dict(signal.get("audit_context") or {}),
            "risk_policy": POLICY_CURRENT,
            "risk_trace": risk_trace,
            "exit_policy": resolution_payload,
            "trade_metadata": dict(getattr(trade, "metadata", {}) or {}),
            "execution_rule": {
                "entry": "NEXT_TRADING_DAY_OPEN",
                "same_day_conflict": "STOP_FIRST",
                "max_holding_days": self.MAX_HOLDING_DAYS,
                "round_trip_cost_pct": self.ROUND_TRIP_COST_PCT,
            },
        }

        if trade_exit_reason == "END_OF_DATA":
            return self.catalog.save_outcome(
                execution_run_id=execution_run_id,
                signal_date=candidate.trading_date,
                market=candidate.market,
                ticker=candidate.ticker,
                outcome_status="CENSORED",
                outcome_reason="CENSORED_END_OF_DATA",
                entry_reference_date=entry_date,
                entry_reference_price=entry_price,
                entry_date=str(getattr(trade, "entry_date", entry_date)),
                entry_price=float(getattr(trade, "entry_price", entry_price)),
                stop_price=float(getattr(trade, "stop_price", stop_price)),
                target1_price=float(
                    getattr(trade, "target1_price", target1_price)
                ),
                target2_price=self._number(
                    getattr(trade, "target2_price", target2_price)
                ),
                holding_days=int(getattr(trade, "holding_days", 0) or 0),
                mark_date=str(getattr(trade, "exit_date", "") or "") or None,
                mark_price=self._number(getattr(trade, "exit_price", None)),
                mark_return_pct=self._number(
                    getattr(trade, "gross_return_pct", None)
                ),
                details=details,
            )

        return self.catalog.save_outcome(
            execution_run_id=execution_run_id,
            signal_date=candidate.trading_date,
            market=candidate.market,
            ticker=candidate.ticker,
            outcome_status="CLOSED",
            outcome_reason=trade_exit_reason or None,
            entry_reference_date=entry_date,
            entry_reference_price=entry_price,
            entry_date=str(getattr(trade, "entry_date", entry_date)),
            entry_price=float(getattr(trade, "entry_price", entry_price)),
            stop_price=float(getattr(trade, "stop_price", stop_price)),
            target1_price=float(
                getattr(trade, "target1_price", target1_price)
            ),
            target2_price=self._number(
                getattr(trade, "target2_price", target2_price)
            ),
            exit_date=str(getattr(trade, "exit_date", "") or "") or None,
            exit_price=self._number(getattr(trade, "exit_price", None)),
            exit_reason=trade_exit_reason or None,
            holding_days=int(getattr(trade, "holding_days", 0) or 0),
            gross_return_pct=self._number(
                getattr(trade, "gross_return_pct", None)
            ),
            net_return_pct=self._number(
                getattr(trade, "net_return_pct", None)
            ),
            fee_pct=0.0,
            tax_pct=0.0,
            slippage_pct=0.0,
            details=details,
        )

    def run_pending(
        self,
        execution_run_id: str,
        *,
        limit: int | None = None,
    ) -> list[HistoricalExecutionOutcome]:
        pending = self.catalog.pending_candidates(execution_run_id)
        if limit is not None:
            pending = pending[: max(0, int(limit))]
        return [
            self.evaluate_candidate(execution_run_id, candidate)
            for candidate in pending
        ]
