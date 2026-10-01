from __future__ import annotations

from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.macro.validation_entry_gate import (
    NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION,
    build_next6e_validation_entry_gate,
)


ROOT = Path(__file__).resolve().parents[2]


def _current_input() -> dict[str, object]:
    return {
        "scanner_version": StockScannerService.VERSION,
        "macro_numeric_policy": "NONE",
        "reference_adequacy": "UNRESOLVED",
        "rate_spike_calibration_status": "UNCALIBRATED",
        "historical_sector_status": "BLOCKED_EXTERNAL_SOURCE",
        "historical_impact_mode": "MARKET_STOCK_ONLY",
        "prospective_sector_status": "NOT_STARTED",
        "p6_asof_mode": "SYSTEM_OBSERVED_AS_OF",
        "p6_historical_completeness_proven": False,
        "p6_historical_evaluation_approved": False,
        "prediction_status": "NOT_VALIDATED",
    }


def test_current_next6_state_is_reference_validation_only() -> None:
    gate = build_next6e_validation_entry_gate(**_current_input())

    assert gate["contract_version"] == (
        "VN_NEXT6E_S1_VALIDATION_ENTRY_GATE_V1"
    )
    assert gate["overall_scope"] == "REFERENCE_VALIDATION_ONLY"
    assert gate["baseline"] == {
        "target": "PRODUCTION_SCANNER",
        "scanner_version": "0.21.3.9",
        "selection_policy_pin_required": True,
    }
    assert StockScannerService.VERSION == "0.21.3.9"


def test_current_lane_states_are_frozen_before_effectiveness_work() -> None:
    gate = build_next6e_validation_entry_gate(**_current_input())

    assert gate["lanes"] == {
        "reference_reproducibility": "ELIGIBLE",
        "development_coverage": "ELIGIBLE",
        "prospective_reference_capture": "READY_TO_IMPLEMENT",
        "shock_effectiveness": "BLOCKED",
        "sector_effectiveness": "BLOCKED",
        "event_incremental_value": "BLOCKED",
        "execution_policy_comparison": "BLOCKED",
        "holdout_evaluation": "LOCKED",
        "production_readiness": "BLOCKED",
    }


def test_current_blockers_are_complete_and_deterministically_ordered() -> None:
    gate = build_next6e_validation_entry_gate(**_current_input())

    assert gate["blockers"] == [
        "MACRO_NUMERIC_POLICY_UNDEFINED",
        "REFERENCE_ADEQUACY_UNRESOLVED",
        "RATE_SPIKE_UNCALIBRATED",
        "HISTORICAL_SECTOR_BLOCKED",
        "P6_HISTORICAL_COMPLETENESS_UNPROVEN",
        "P6_HISTORICAL_EVALUATION_NOT_APPROVED",
        "PREDICTION_NOT_VALIDATED",
        "ALTERNATIVE_EXECUTION_POLICY_NOT_DEFINED",
        "HOLDOUT_LOCKED",
    ]


def test_numeric_criteria_are_explicitly_undefined() -> None:
    gate = build_next6e_validation_entry_gate(**_current_input())

    assert gate["numeric_criteria"] == {
        "defined": False,
        "minimum_sample": None,
        "minimum_effect_size": None,
        "maximum_allowed_degradation": None,
        "promotion_threshold": None,
    }


def test_governance_keeps_all_decision_paths_disabled() -> None:
    gate = build_next6e_validation_entry_gate(**_current_input())

    assert gate["governance"] == {
        "holdout_access": False,
        "holdout_evaluation_approved": False,
        "historical_effectiveness_approved": False,
        "execution_policy_evaluation_approved": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
        "network_access": False,
        "database_write": False,
    }


def test_identical_input_produces_identical_identity() -> None:
    first = build_next6e_validation_entry_gate(**_current_input())
    second = build_next6e_validation_entry_gate(**_current_input())

    assert first["gate_id"] == second["gate_id"]
    assert first["gate_hash"] == second["gate_hash"]
    assert first == second


def test_blocker_state_change_changes_identity_without_unlocking_production() -> None:
    current = _current_input()
    before = build_next6e_validation_entry_gate(**current)

    changed = dict(current)
    changed["p6_historical_completeness_proven"] = True
    changed["p6_historical_evaluation_approved"] = True
    after = build_next6e_validation_entry_gate(**changed)

    assert after["gate_id"] != before["gate_id"]
    assert after["gate_hash"] != before["gate_hash"]
    assert "P6_HISTORICAL_COMPLETENESS_UNPROVEN" not in after["blockers"]
    assert "P6_HISTORICAL_EVALUATION_NOT_APPROVED" not in after["blockers"]
    assert after["lanes"]["event_incremental_value"] == "ELIGIBLE"
    assert after["overall_scope"] == "REFERENCE_VALIDATION_ONLY"
    assert after["lanes"]["production_readiness"] == "BLOCKED"
    assert after["governance"]["production_decision_approved"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("macro_numeric_policy", "MADE_UP_POLICY"),
        ("reference_adequacy", "UNKNOWN"),
        ("rate_spike_calibration_status", "MAGIC_THRESHOLD"),
        ("historical_sector_status", "ASSUMED_AVAILABLE"),
        ("historical_impact_mode", "INVENTED_MODE"),
        ("prospective_sector_status", "AUTO_READY"),
        ("p6_asof_mode", "LATEST_CURRENT"),
        ("prediction_status", "VALIDATED"),
    ],
)
def test_unknown_state_fails_closed(field: str, value: str) -> None:
    payload = _current_input()
    payload[field] = value

    with pytest.raises(ValueError, match="not supported by NEXT-6E-S1"):
        build_next6e_validation_entry_gate(**payload)


@pytest.mark.parametrize(
    "field",
    [
        "p6_historical_completeness_proven",
        "p6_historical_evaluation_approved",
    ],
)
def test_boolean_contract_does_not_accept_truthy_non_boolean(field: str) -> None:
    payload = _current_input()
    payload[field] = 1

    with pytest.raises(ValueError, match="must be a boolean"):
        build_next6e_validation_entry_gate(**payload)


def test_builder_source_has_no_runtime_io_or_nondeterministic_identity() -> None:
    source = (
        ROOT / "backend/app/macro/validation_entry_gate.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "Path(",
        "open(",
        "datetime.now",
        "datetime.utcnow",
        "uuid4",
        "random.",
        "os.getenv",
    ):
        assert forbidden not in source


def test_macro_package_exports_next6e_s1_contract() -> None:
    import app.macro as macro

    assert macro.NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION == (
        NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION
    )
    assert callable(macro.build_next6e_validation_entry_gate)
