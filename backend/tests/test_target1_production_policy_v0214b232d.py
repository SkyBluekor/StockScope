from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backtest.target1_audit import build_current_target1_audit
from app.backtest.target1_realism_validation import POLICY_CAP_1_5R, build_target_variants
from app.risk.engine import RiskEngine
from app.risk.target1_policy import TARGET1_CAP_BASIS, TARGET1_FALLBACK_BASIS, select_target1
from app.strategy.models import StrategyName


ENTRY = 48_500.0
INVALIDATION = 46_025.04
RISK = ENTRY - INVALIDATION


def _structural_at(r_multiple: float) -> float:
    return ENTRY + RISK * r_multiple


def _data(**overrides):
    payload = dict(
        current_price=ENTRY,
        atr_pct=((47_950.0 - INVALIDATION) / 0.5) / ENTRY * 100.0,
        support_price=47_950.0,
        ma20=50_000.0,
        resistance_price=61_000.0,
        extreme_move=False,
        data_stale=False,
    )
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_structural_target_below_cap_is_preserved():
    price = _structural_at(1.2)
    result = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[(price, "최근 저항 후보", "RESISTANCE")],
    )
    assert result.target1_price == pytest.approx(price)
    assert result.target1_basis == "최근 저항 후보"
    assert result.cap_applied is False
    assert result.fallback_used is False


def test_structural_target_exactly_at_cap_is_preserved():
    price = _structural_at(1.5)
    result = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[(price, "최근 저항 후보", "RESISTANCE")],
    )
    assert result.target1_price == pytest.approx(price)
    assert result.target1_basis == "최근 저항 후보"
    assert result.cap_applied is False


@pytest.mark.parametrize("r_multiple", [2.0, 5.0])
def test_structural_target_above_cap_uses_1_5r(r_multiple: float):
    structural = _structural_at(r_multiple)
    result = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[(structural, "최근 저항 후보", "RESISTANCE")],
    )
    assert result.target1_price == pytest.approx(_structural_at(1.5))
    assert result.target1_basis == TARGET1_CAP_BASIS
    assert result.structural_target1_price == pytest.approx(structural)
    assert result.cap_applied is True
    assert result.fallback_used is False


def test_missing_structural_target_keeps_existing_1_5r_fallback():
    result = select_target1(entry=ENTRY, risk_amount=RISK, structural_candidates=[])
    assert result.target1_price == pytest.approx(_structural_at(1.5))
    assert result.target1_basis == TARGET1_FALLBACK_BASIS
    assert result.structural_target1_price is None
    assert result.cap_applied is False
    assert result.fallback_used is True


def test_equal_resistance_and_high20_preserves_resistance_as_structural_source():
    result = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[
            (61_000.0, "최근 저항 후보", "RESISTANCE"),
            (61_000.0, "최근 20일 고점", "HIGH20"),
        ],
    )
    assert result.structural_target1_price == 61_000.0
    assert result.structural_target1_basis == "최근 저항 후보"
    assert result.structural_target1_kind == "RESISTANCE"
    assert result.cap_applied is True


def test_hanmi_science_production_plan_caps_target1_but_preserves_target2():
    plan = RiskEngine().build_plan(
        data=_data(),
        strategy=StrategyName.PULLBACK,
        technical={"low20": 40_000.0, "high20": 61_000.0},
        risk_gate_active=False,
        risk_gate_reasons=[],
        basis="CONFIRMED_EOD",
    )

    assert plan.invalidation_price == pytest.approx(INVALIDATION, abs=0.01)
    assert plan.target1_price == pytest.approx(52_212.44, abs=0.01)
    assert plan.target1_basis == TARGET1_CAP_BASIS
    assert plan.rr1 == pytest.approx(1.50, abs=0.01)
    assert plan.structural_target1_price == 61_000.0
    assert plan.structural_target1_basis == "최근 저항 후보"
    assert plan.target1_cap_applied is True
    assert plan.target1_fallback_used is False

    # Legacy Target2 = max(2R, legacy structural Target1 + 0.5R).
    assert plan.target2_price == pytest.approx(62_237.48, abs=0.01)
    assert plan.rr2 == pytest.approx(5.55, abs=0.01)


def test_target1_audit_matches_new_production_cap_and_retains_structural_trace():
    decision = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[
            (61_000.0, "최근 저항 후보", "RESISTANCE"),
            (61_000.0, "최근 20일 고점", "HIGH20"),
        ],
    )
    plan = SimpleNamespace(
        entry_price=ENTRY,
        invalidation_price=INVALIDATION,
        target1_price=decision.target1_price,
        target1_basis=decision.target1_basis,
        target2_price=62_237.48,
    )
    audit = build_current_target1_audit(
        risk_plan=plan,
        data=SimpleNamespace(resistance_price=61_000.0),
        technical={"high20": 61_000.0},
    )
    assert audit["formula_status"] == "MATCH"
    assert audit["target1_basis_code"] == "RISK_1_5R_CAP"
    assert audit["target1_cap_applied"] is True
    assert audit["structural_target1_price"] == 61_000.0
    assert audit["structural_target1_basis"] == "최근 저항 후보"
    selected = [row for row in audit["structural_candidates"] if row["selected"]]
    assert len(selected) == 1
    assert selected[0]["kind"] == "RISK_1_5R_CAP"


def test_production_cap_matches_b232c_counterfactual_formula():
    legacy_target = 61_000.0
    audit_cap = build_target_variants(
        entry=ENTRY,
        stop=INVALIDATION,
        current_target=legacy_target,
    )[POLICY_CAP_1_5R]
    production = select_target1(
        entry=ENTRY,
        risk_amount=RISK,
        structural_candidates=[(legacy_target, "최근 저항 후보", "RESISTANCE")],
    )
    assert production.target1_price == pytest.approx(audit_cap)


def test_scanner_decision_versions_are_bumped_without_session_schema_change():
    repo_root = Path(__file__).resolve().parents[2]
    scanner_source = (repo_root / "backend/app/backtest/scanner.py").read_text(encoding="utf-8")
    session_source = (repo_root / "frontend/src/components/scannerSession.ts").read_text(encoding="utf-8")
    assert 'VERSION = "0.21.3.7"' in scanner_source
    assert 'HISTORICAL_EVIDENCE_POLICY_VERSION = "v2"' in scanner_source
    assert "SCANNER_DECISION_VERSION" not in session_source
    assert "SCANNER_SESSION_SCHEMA_VERSION = 1" in session_source
    assert "algorithm version belongs to the" in session_source
