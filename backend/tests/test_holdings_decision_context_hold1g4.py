from __future__ import annotations

from pathlib import Path

import pytest

from app.holdings.catalog import HoldingsCatalog
from app.holdings.decision_context import HoldingDecisionContextService


def _catalog(tmp_path: Path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    stock = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        watch_enabled=True,
    )
    return catalog, stock


def _store(
    catalog: HoldingsCatalog,
    stock_id: str,
    *,
    market_date: str,
    fingerprint: str,
    strategy: str = "momentum_continuation",
    action: str = "WATCH",
    readiness: str = "WATCH",
    reference: str = "100",
    stop: str | None = "90",
    target1: str | None = "110",
    target2: str | None = "120",
    summary: str | None = None,
):
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock_id,
        market_date=market_date,
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint=fingerprint,
        strategy_key=strategy,
        action_state=action,
        risk_state="READY",
        reference_price=reference,
        stop_price=stop,
        target1_price=target1,
        target2_price=target2,
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="P1",
        source_versions={"fixture": fingerprint},
        snapshot={
            "candidate_state": action,
            "readiness_state": {
                "status": readiness,
                "summary": summary,
                "decision_reason": "ENTRY_CONDITIONS_MISSING",
                "missing": 2,
                "total": 8,
                "warnings": [],
            },
        },
        revision_reason="INITIAL",
        computed_at=f"{market_date}T08:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    return revision


@pytest.mark.parametrize(
    ("state", "label"),
    [
        ("READY", "진입 후보"),
        ("WATCH", "관심 유지"),
        ("NOT_READY", "현재 우선순위 낮음"),
        ("BLOCKED", "위험 때문에 보류"),
        ("CAUTION", "주의하며 관찰"),
    ],
)
def test_entry_state_preserves_readiness_variation(tmp_path: Path, state: str, label: str):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint=f"fp-{state}",
        readiness=state,
        action="WATCH",
        summary="기존 readiness 설명",
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context is not None
    assert context["entry"]["state"] == state
    assert context["entry"]["label"] == label
    assert context["entry"]["summary"] == "기존 readiness 설명"


def test_previous_plan_stop_breach_and_same_day_revision_is_not_previous_plan(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-21",
        fingerprint="prev",
        strategy="pullback",
        reference="105",
        stop="100",
        target1="110",
        target2="120",
    )
    first_today = _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint="today-1",
        strategy="trend_recovery",
        reference="99",
        stop="95",
        target1="115",
        target2="125",
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id,
        market_date="2026-09-22",
    )
    same_day_second = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="today-2",
        strategy_key="momentum_continuation",
        action_state="WATCH",
        risk_state="READY",
        reference_price="95",
        stop_price="90",
        target1_price="112",
        target2_price="130",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="P1",
        source_versions={"fixture": "today-2"},
        snapshot={"readiness_state": {"status": "NOT_READY"}},
        revision_reason="INPUT_CHANGED",
        computed_at="2026-09-22T09:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=same_day_second.id,
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["previous_plan"]["state"] == "STOP_BREACHED"
    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"
    assert context["previous_plan"]["previous_reference_price"] == "105"
    assert context["previous_plan"]["previous_stop_price"] == "100"
    assert context["previous_plan"]["current_close"] == "95"
    assert context["strategy"]["state"] == "CHANGED"
    assert context["strategy"]["previous"] == "pullback"
    assert context["strategy"]["current"] == "momentum_continuation"
    assert first_today.id != same_day_second.id


@pytest.mark.parametrize(
    ("current_close", "expected"),
    [
        ("105", "WITHIN_PLAN"),
        ("115", "TARGET1_REACHED"),
        ("125", "TARGET2_REACHED"),
    ],
)
def test_previous_plan_price_states(tmp_path: Path, current_close: str, expected: str):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-21",
        fingerprint="prev",
        reference="100",
        stop="90",
        target1="110",
        target2="120",
    )
    _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint="current",
        reference=current_close,
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)
    assert context["previous_plan"]["state"] == expected


def test_first_analysis_has_initial_strategy_and_first_plan(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint="first",
        strategy="ma20_rebound",
        readiness="READY",
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["strategy"] == {
        "state": "INITIAL",
        "current": "ma20_rebound",
        "previous": None,
        "previous_market_date": None,
    }
    assert context["previous_plan"]["state"] == "FIRST_PLAN"
    assert context["previous_plan"]["label"] == "첫 계획 설정됨"


def test_missing_condition_details_are_exposed_from_snapshot(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id,
        market_date="2026-09-22",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="details",
        strategy_key="momentum_continuation",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="110",
        target2_price="120",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="P1",
        source_versions={"fixture": "details"},
        snapshot={
            "readiness_state": {
                "status": "WATCH",
                "missing": 2,
                "total": 8,
            },
            "condition_state": {
                "passed": 6,
                "missing": 2,
                "total": 8,
                "missing_details": [
                    {
                        "raw": "조건 A",
                        "label": "최근 저점이 무너지지 않기",
                        "detail": "최근 저점 구조가 유지되는지 확인합니다.",
                        "current_value": "낮아짐",
                        "required_value": "최근 저점 유지 또는 상승",
                    },
                    {
                        "raw": "조건 B",
                        "label": "거래량 조건 충족",
                        "detail": "거래 참여가 충분한지 확인합니다.",
                        "current_value": "0.8배",
                        "required_value": "1.2배 이상",
                    },
                ],
            },
        },
        revision_reason="INITIAL",
        computed_at="2026-09-22T08:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["entry"]["passed"] == 6
    assert context["entry"]["missing"] == 2
    assert context["entry"]["total"] == 8
    assert len(context["entry"]["missing_details"]) == 2
    assert context["entry"]["missing_details"][0]["label"] == "최근 저점이 무너지지 않기"
    assert context["entry"]["missing_details"][0]["current_value"] == "낮아짐"
    assert context["entry"]["missing_details"][0]["required_value"] == "최근 저점 유지 또는 상승"


def test_previous_analysis_without_price_plan_is_distinguished(tmp_path: Path):
    catalog, stock = _catalog(tmp_path)
    _store(
        catalog,
        stock.id,
        market_date="2026-09-21",
        fingerprint="previous-no-plan",
        reference="100",
        stop=None,
        target1=None,
        target2=None,
    )
    _store(
        catalog,
        stock.id,
        market_date="2026-09-22",
        fingerprint="current",
        reference="102",
    )

    context = HoldingDecisionContextService(catalog).build(stock.id)

    assert context["previous_plan"]["state"] == "PREVIOUS_PLAN_UNAVAILABLE"
    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"
    assert context["previous_plan"]["previous_reference_price"] == "100"


def test_decision_context_is_database_only() -> None:
    source = Path("backend/app/holdings/decision_context.py").read_text(encoding="utf-8")
    assert "KrxProvider" not in source
    assert "StockScannerService" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "sqlite3.connect" not in source
