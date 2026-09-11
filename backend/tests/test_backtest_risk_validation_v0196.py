from __future__ import annotations

from app.backtest.policy_lab import (
    POLICY_BLOCK_ALL_CAUTION,
    POLICY_BLOCK_WIDE_STOP,
    POLICY_CURRENT,
    POLICY_NEAREST_VALID_ANCHOR,
    build_risk_policy_comparison,
)
from app.backtest.risk_validation import (
    RiskPolicyValidationService,
    build_cross_stock_policy_decision,
)


def _metrics(*, trades: int, expectancy: float, mdd: float) -> dict:
    return {
        "trades": trades,
        "wins": trades // 2,
        "losses": trades - trades // 2,
        "win_rate_pct": 50.0 if trades else None,
        "average_gross_return_pct": expectancy,
        "average_net_return_pct": expectancy,
        "median_net_return_pct": expectancy,
        "average_win_pct": 2.0,
        "average_loss_pct": -2.0,
        "expectancy_pct": expectancy,
        "profit_factor": 1.0,
        "average_holding_days": 5.0,
        "max_consecutive_losses": 1,
        "max_drawdown_pct": mdd,
        "initial_capital": 10_000_000.0,
        "final_capital": 10_000_000.0,
        "total_net_return_pct": expectancy * trades,
    }


def _scenario(
    policy_id: str,
    *,
    trades: int,
    expectancy: float,
    mdd: float,
    blocked: int = 0,
    caution: int = 0,
    wide: int = 0,
    changed: int = 0,
    stop_distance: float = 6.0,
) -> dict:
    return {
        "id": policy_id,
        "metrics": _metrics(trades=trades, expectancy=expectancy, mdd=mdd),
        "eligible_attempts": trades + blocked,
        "blocked_by_policy": blocked,
        "blocked_reasons": {},
        "unusable_risk_plan": 0,
        "caution_trades": caution,
        "wide_stop_trades": wide,
        "average_initial_stop_distance_pct": stop_distance,
        "anchor_changed_signals": changed,
        "anchor_changed_trades": changed,
    }


def _stock(
    code: str,
    *,
    wide_better: bool,
    caution_overfilters: bool = True,
    nearest_better: bool = False,
) -> dict:
    baseline = _scenario(
        POLICY_CURRENT,
        trades=10,
        expectancy=-1.0,
        mdd=-15.0,
        caution=6,
        wide=1,
        stop_distance=7.0,
    )
    caution = _scenario(
        POLICY_BLOCK_ALL_CAUTION,
        trades=3 if caution_overfilters else 7,
        expectancy=0.8,
        mdd=-6.0,
        blocked=7 if caution_overfilters else 3,
        caution=0,
        wide=0,
        stop_distance=5.0,
    )
    wide = _scenario(
        POLICY_BLOCK_WIDE_STOP,
        trades=9,
        expectancy=0.2 if wide_better else -1.4,
        mdd=-8.0 if wide_better else -17.0,
        blocked=1,
        caution=5,
        wide=0,
        stop_distance=5.2,
    )
    nearest = _scenario(
        POLICY_NEAREST_VALID_ANCHOR,
        trades=10,
        expectancy=0.1 if nearest_better else -1.2,
        mdd=-9.0 if nearest_better else -16.0,
        caution=5,
        wide=0 if nearest_better else 1,
        changed=3,
        stop_distance=5.0 if nearest_better else 7.2,
    )
    comparison = build_risk_policy_comparison([baseline, caution, wide, nearest])
    return {
        "code": code,
        "name": f"종목-{code}",
        "size_band": "테스트",
        "summary": baseline["metrics"],
        "risk_policy_comparison": comparison,
    }


def _selection() -> dict:
    return {
        "method": "START_DATE_MARKET_CAP_STRATIFIED",
        "label": "자동 표본",
        "snapshot_date": "20230908",
        "market": "KOSPI",
        "requested_stock_count": 6,
        "selected_stock_count": 6,
        "description": "테스트",
    }


def test_cross_stock_decision_prefers_repeated_targeted_fix_not_highest_return() -> None:
    stocks = [
        _stock("005930", wide_better=True),
        _stock("000001", wide_better=True),
        _stock("000002", wide_better=True),
        _stock("000003", wide_better=True),
        _stock("000004", wide_better=False),
        _stock("000005", wide_better=False),
    ]

    result = build_cross_stock_policy_decision(
        stocks,
        target_code="005930",
        market="KOSPI",
        period={"start": "2023-09-10", "end": "2026-09-10"},
        selection=_selection(),
    )

    assert result["decision"]["status"] == "PROMOTION_CANDIDATE"
    assert result["decision"]["recommended_policy_id"] == POLICY_BLOCK_WIDE_STOP
    wide = next(row for row in result["policies"] if row["policy_id"] == POLICY_BLOCK_WIDE_STOP)
    caution = next(row for row in result["policies"] if row["policy_id"] == POLICY_BLOCK_ALL_CAUTION)
    assert wide["problem_solved_stocks"] == 6
    assert wide["balanced_improvement_stocks"] == 4
    assert caution["verdict"]["status"] == "TOO_AGGRESSIVE"


def test_cross_stock_decision_does_not_promote_one_stock_only_success() -> None:
    stocks = [
        _stock("005930", wide_better=True),
        _stock("000001", wide_better=False),
        _stock("000002", wide_better=False),
        _stock("000003", wide_better=False),
    ]

    result = build_cross_stock_policy_decision(
        stocks,
        target_code="005930",
        market="KOSPI",
        period={"start": "2023-09-10", "end": "2026-09-10"},
        selection=_selection(),
    )

    assert result["decision"]["recommended_policy_id"] is None
    assert result["decision"]["status"] in {"MORE_VALIDATION", "INSUFFICIENT_EVIDENCE"}


def test_market_cap_peer_selection_is_deterministic_and_spans_size_bands() -> None:
    rows = [
        {
            "code": f"{index:06d}",
            "name": f"종목{index}",
            "market_cap": (101 - index) * 1_000_000,
            "close": 10_000,
            "volume": 1_000,
        }
        for index in range(1, 101)
    ]
    first = RiskPolicyValidationService._select_peer_rows(rows, "000001")
    second = RiskPolicyValidationService._select_peer_rows(rows, "000001")

    assert [row["code"] for row in first] == [row["code"] for row in second]
    assert len(first) == 5
    assert len({row["size_band"] for row in first}) >= 4
    assert all(row["code"] != "000001" for row in first)


def test_cross_stock_result_keeps_actual_rule_unchanged() -> None:
    result = build_cross_stock_policy_decision(
        [_stock("005930", wide_better=True), _stock("000001", wide_better=True), _stock("000002", wide_better=True)],
        target_code="005930",
        market="KOSPI",
        period={"start": "2023-09-10", "end": "2026-09-10"},
        selection=_selection(),
    )

    assert "자동 변경하지 않습니다" in result["guardrail"]
    assert result["status"] == "CROSS_STOCK_RESEARCH"

import pytest
from app.backtest.models import BacktestConfig


class _FakeKrx:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.opened = 0
        self.closed = 0

    async def open_session(self) -> None:
        self.opened += 1

    async def close_session(self) -> None:
        self.closed += 1

    async def stock_daily(self, market: str, bas_date, code: str | None = None) -> dict:
        date_text = bas_date.strftime("%Y%m%d") if hasattr(bas_date, "strftime") else str(bas_date).replace("-", "")
        return {"date": date_text, "count": len(self.rows), "rows": self.rows}


class _FakeBacktestService:
    def __init__(self, by_code: dict[str, dict]):
        self.by_code = by_code
        self.calls: list[str] = []

    async def run_pullback(self, config: BacktestConfig, *, progress=None) -> dict:
        self.calls.append(config.code)
        if progress:
            progress({"stage": "metrics", "message": "계산 중", "current": 1, "total": 2})
        stock = self.by_code[config.code]
        return {
            "summary": stock["summary"],
            "risk_policy_comparison": stock["risk_policy_comparison"],
            "accuracy_audit": {},
        }


@pytest.mark.asyncio
async def test_service_selects_peers_automatically_and_validates_without_manual_stock_list() -> None:
    universe = [
        {
            "code": f"{index:06d}",
            "name": "삼성전자" if index == 1 else f"종목{index}",
            "market_cap": (101 - index) * 1_000_000,
            "close": 10_000,
            "volume": 1_000,
        }
        for index in range(1, 101)
    ]
    selected_rows = RiskPolicyValidationService._select_peer_rows(universe, "000001")
    selected_codes = ["000001", *[row["code"] for row in selected_rows]]
    by_code = {code: _stock(code, wide_better=True) for code in selected_codes}
    fake_krx = _FakeKrx(universe)
    fake_backtest = _FakeBacktestService(by_code)
    service = RiskPolicyValidationService(fake_krx, backtest_service=fake_backtest)
    progress: list[dict] = []

    result = await service.run(
        BacktestConfig(
            code="000001",
            market="KOSPI",
            start_date="2023-09-10",
            end_date="2026-09-10",
        ),
        progress=progress.append,
    )

    assert result["tested_stock_count"] == 6
    assert result["selection"]["selected_stock_count"] == 6
    assert fake_backtest.calls == selected_codes
    assert result["decision"]["recommended_policy_id"] == POLICY_BLOCK_WIDE_STOP
    assert any(item["stage"] == "cross_validation" for item in progress)


def test_automatic_peer_sample_excludes_spac_and_preferred_share_patterns() -> None:
    rows = [
        {"code": "000001", "name": "기준주", "market_cap": 1000, "close": 10, "volume": 10},
        {"code": "000002", "name": "테스트우", "market_cap": 990, "close": 10, "volume": 10},
        {"code": "000003", "name": "테스트2우B", "market_cap": 980, "close": 10, "volume": 10},
        {"code": "000004", "name": "미래스팩1호", "market_cap": 970, "close": 10, "volume": 10},
    ]
    rows.extend(
        {"code": f"{index:06d}", "name": f"보통주{index}", "market_cap": 960 - index, "close": 10, "volume": 10}
        for index in range(5, 30)
    )

    selected = RiskPolicyValidationService._select_peer_rows(rows, "000001")
    names = {row["name"] for row in selected}

    assert "테스트우" not in names
    assert "테스트2우B" not in names
    assert "미래스팩1호" not in names
