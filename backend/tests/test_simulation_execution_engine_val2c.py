from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backtest.models import BacktestTrade
from app.simulation.execution_catalog import HistoricalExecutionCatalog
from app.simulation.execution_engine import (
    ExecutionEngineError,
    HistoricalExecutionEngine,
)
from app.simulation.validation_catalog import HistoricalValidationCatalog


@dataclass
class FakeSeries:
    rows: dict[str, dict]


class FakeMarketStore:
    def __init__(self, stock_rows: dict[str, dict]):
        self.stock_rows = stock_rows

    def stock_series_many(self, market, codes, start_dd=None, end_dd=None):
        code = list(codes)[0]
        rows = {
            key: value
            for key, value in self.stock_rows.items()
            if (start_dd is None or key >= start_dd)
            and (end_dd is None or key <= end_dd)
        }
        return {code: FakeSeries(rows)}

    def index_series(self, market, start_dd=None, end_dd=None):
        rows = {
            "20260102": {
                "date": "20260102",
                "change_rate": 0.1,
            }
        }
        return FakeSeries(rows)


class FakePlan:
    reference_only = False
    invalidation_price = 90.0
    target1_price = 120.0
    target2_price = 130.0


class FakeEvaluation:
    score = 80
    eligible = True


class FakeEngine:
    def _signal_snapshot(self, *, stock_rows, index_rows, index, config, sector_input=None):
        return {
            "signal_index": index,
            "signal_date": "20260102",
            "strategy_score": 0,
            "strategy_eligible": True,
            "evaluations": {"pullback": FakeEvaluation()},
            "audit_context": {"future_data_used": False},
        }

    def _build_risk_plan_for_policy(self, *, signal, entry_price, risk_policy, strategy):
        return FakePlan(), {"policy_id": risk_policy}


class FakeResolution:
    def to_dict(self):
        return {"policy_id": "TARGET1_FULL_EXIT"}


class FakeProductionExit:
    def __init__(self, trade):
        self.trade = trade

    def simulate_trade(self, *, signal, stock_rows, config, strategy):
        return self.trade, 2, FakeResolution()


class FakeScanner:
    def __init__(self, trade):
        self.engine = FakeEngine()
        self.multi = SimpleNamespace(
            production_exit=FakeProductionExit(trade)
        )

    def _quick_current_candidate(
        self,
        *,
        market,
        latest_date,
        row,
        stock_rows,
        index_rows,
        sector_input=None,
    ):
        return {"quick_strategy": "pullback"}

    def _current_candidate(self, quick):
        return {
            "action": "ENTRY_CANDIDATE",
            "candidate_state": "READY",
        }


def _source(db: Path, *, action="ENTRY_CANDIDATE", state="READY"):
    source = HistoricalValidationCatalog(db)
    source.initialize()
    draft = source.create_draft(
        name="VAL.2-C source",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-01",
        resolved_start_date="2026-01-02",
        resolved_end_date="2026-01-02",
        trading_day_count=1,
    )
    source.save_completed_day(
        validation_id=draft.id,
        trading_date="2026-01-02",
        scanner_version="0.21.3.7",
        market_scope="KOSPI",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint={"fp": "x"},
        market_summary=[],
        summary={"candidate_count": 1},
        methodology={},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI",
                "ticker": "005930",
                "name": "삼성전자",
                "rank": 1,
                "result_bucket": "TOP",
                "strategy": "pullback",
                "decision_status": state,
                "snapshot": {
                    "code": "005930",
                    "data_date": "2026-01-02",
                    "action": action,
                },
            }
        ],
    )
    source.mark_replay_completed(draft.id)
    return source, source.get(draft.id)


def _run(db: Path, validation_id: str):
    catalog = HistoricalExecutionCatalog(db)
    catalog.initialize()
    run = catalog.create_run(
        validation_id=validation_id,
        market_data_cutoff_date="2026-02-03",
        production_exit_policy_token="TOKEN",
    )
    return catalog, run


def _closed_trade(exit_reason="TARGET_1"):
    return BacktestTrade(
        signal_date="20260102",
        entry_date="20260105",
        entry_price=100.0,
        exit_date="20260106",
        exit_price=120.0,
        exit_reason=exit_reason,
        holding_days=2,
        strategy_score=80,
        entry_timing_passed=7,
        entry_timing_total=7,
        entry_timing_state="READY",
        market_regime="TREND_UP",
        stop_price=90.0,
        target1_price=120.0,
        target2_price=130.0,
        gross_return_pct=20.0,
        net_return_pct=20.0,
        risk_plan_status="OK",
        metadata={},
    )


def test_val2c_wait_candidate_is_not_executed_without_market_read(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db, action="WAIT", state="WATCH")
    assert validation is not None
    catalog, run = _run(db, validation.id)

    class MustNotRead:
        def stock_series_many(self, *args, **kwargs):
            raise AssertionError("WAIT candidate must not read future market data")

    engine = HistoricalExecutionEngine(
        catalog,
        MustNotRead(),
        policy_token_provider=lambda: "TOKEN",
    )
    candidate = source.list_candidates(validation.id)[0]
    outcome = engine.evaluate_candidate(run.id, candidate)

    assert outcome.outcome_status == "NOT_EXECUTED"
    assert outcome.outcome_reason == "SCANNER_WAIT"
    assert outcome.entry_date is None


def test_val2c_entry_candidate_uses_next_open_and_production_trade(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db)
    assert validation is not None
    catalog, run = _run(db, validation.id)

    rows = {
        "20260102": {
            "date": "20260102",
            "code": "005930",
            "name": "삼성전자",
            "open": 98.0,
            "high": 101.0,
            "low": 97.0,
            "close": 100.0,
        },
        "20260105": {
            "date": "20260105",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
        },
        "20260106": {
            "date": "20260106",
            "open": 108.0,
            "high": 121.0,
            "low": 107.0,
            "close": 120.0,
        },
    }
    fake_scanner = FakeScanner(_closed_trade())
    engine = HistoricalExecutionEngine(
        catalog,
        FakeMarketStore(rows),
        scanner_factory=lambda: fake_scanner,
        policy_token_provider=lambda: "TOKEN",
    )

    candidate = source.list_candidates(validation.id)[0]
    outcome = engine.evaluate_candidate(run.id, candidate)

    assert outcome.outcome_status == "CLOSED"
    assert outcome.entry_reference_date == "2026-01-05"
    assert outcome.entry_reference_price == 100.0
    assert outcome.entry_date == "20260105"
    assert outcome.exit_reason == "TARGET_1"
    assert outcome.gross_return_pct == 20.0
    assert outcome.details["signal_parity"]["future_data_used"] is False
    assert outcome.details["execution_rule"]["entry"] == "NEXT_TRADING_DAY_OPEN"


def test_val2c_end_of_data_is_censored_not_realized(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db)
    assert validation is not None
    catalog, run = _run(db, validation.id)

    rows = {
        "20260102": {
            "date": "20260102",
            "code": "005930",
            "name": "삼성전자",
            "open": 98.0,
            "high": 101.0,
            "low": 97.0,
            "close": 100.0,
        },
        "20260105": {
            "date": "20260105",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
        },
    }
    censored_trade = _closed_trade("END_OF_DATA")
    censored_trade.exit_date = "20260105"
    censored_trade.exit_price = 105.0
    censored_trade.gross_return_pct = 5.0
    censored_trade.net_return_pct = 5.0

    engine = HistoricalExecutionEngine(
        catalog,
        FakeMarketStore(rows),
        scanner_factory=lambda: FakeScanner(censored_trade),
        policy_token_provider=lambda: "TOKEN",
    )
    candidate = source.list_candidates(validation.id)[0]
    outcome = engine.evaluate_candidate(run.id, candidate)

    assert outcome.outcome_status == "CENSORED"
    assert outcome.outcome_reason == "CENSORED_END_OF_DATA"
    assert outcome.exit_date is None
    assert outcome.exit_price is None
    assert outcome.gross_return_pct is None
    assert outcome.net_return_pct is None
    assert outcome.mark_date == "20260105"
    assert outcome.mark_price == 105.0
    assert outcome.mark_return_pct == 5.0


def test_val2c_no_next_open_is_no_entry_data(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db)
    assert validation is not None
    catalog, run = _run(db, validation.id)

    rows = {
        "20260102": {
            "date": "20260102",
            "code": "005930",
            "name": "삼성전자",
            "open": 98.0,
            "high": 101.0,
            "low": 97.0,
            "close": 100.0,
        }
    }
    engine = HistoricalExecutionEngine(
        catalog,
        FakeMarketStore(rows),
        scanner_factory=lambda: FakeScanner(_closed_trade()),
        policy_token_provider=lambda: "TOKEN",
    )
    candidate = source.list_candidates(validation.id)[0]
    outcome = engine.evaluate_candidate(run.id, candidate)

    assert outcome.outcome_status == "NO_ENTRY_DATA"
    assert outcome.outcome_reason == "PENDING_FUTURE_DATA"


def test_val2c_signal_parity_mismatch_stops_without_outcome(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db)
    assert validation is not None
    catalog, run = _run(db, validation.id)

    rows = {
        "20260102": {
            "date": "20260102",
            "code": "005930",
            "name": "삼성전자",
            "open": 98.0,
            "high": 101.0,
            "low": 97.0,
            "close": 100.0,
        },
        "20260105": {
            "date": "20260105",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
        },
    }

    class MismatchScanner(FakeScanner):
        def _current_candidate(self, quick):
            return {
                "action": "WAIT",
                "candidate_state": "WATCH",
            }

    engine = HistoricalExecutionEngine(
        catalog,
        FakeMarketStore(rows),
        scanner_factory=lambda: MismatchScanner(_closed_trade()),
        policy_token_provider=lambda: "TOKEN",
    )
    candidate = source.list_candidates(validation.id)[0]

    with pytest.raises(ExecutionEngineError) as exc:
        engine.evaluate_candidate(run.id, candidate)

    assert exc.value.code == "VAL2_SIGNAL_PARITY_MISMATCH"
    assert catalog.list_outcomes(run.id) == []


def test_val2c_exit_policy_token_change_stops_execution(tmp_path: Path):
    db = tmp_path / "simulation.db"
    source, validation = _source(db)
    assert validation is not None
    catalog, run = _run(db, validation.id)

    engine = HistoricalExecutionEngine(
        catalog,
        FakeMarketStore({}),
        scanner_factory=lambda: FakeScanner(_closed_trade()),
        policy_token_provider=lambda: "CHANGED",
    )
    candidate = source.list_candidates(validation.id)[0]

    with pytest.raises(ExecutionEngineError) as exc:
        engine.evaluate_candidate(run.id, candidate)

    assert exc.value.code == "VAL2_EXIT_POLICY_TOKEN_MISMATCH"
