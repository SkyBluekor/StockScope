from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.event_evidence import (
    EvidencePopulation,
    EventEvidenceContractError,
    EventIncrementalValueGate,
    IncrementalValueGateProtocol,
    ValueGateProtocolStatus,
)
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


NOW = "2026-09-28T07:00:00+00:00"


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    return path


def _market_db(tmp_path: Path) -> Path:
    path = tmp_path / "market.db"
    sqlite3.connect(path).close()
    return path


def _insert_report(
    db: Path,
    *,
    report_id: str,
    sample_count: int,
    clean_controls: int,
    contaminated_controls: int,
    differences: dict[str, float | None],
) -> dict:
    evaluation_protocol = {
        "contract_version": "TEST",
        "protocol_id": "EVAL-PROTOCOL",
    }
    evaluation_protocol_hash = _digest(evaluation_protocol)
    horizons = {}
    for horizon in ("1", "5", "20"):
        difference = differences.get(horizon)
        event_average = 2.0 if difference is not None else None
        control_average = (
            event_average - float(difference)
            if event_average is not None and difference is not None
            else None
        )
        horizons[horizon] = {
            "stock_return": {
                "sample_count": sample_count,
                "average_pct": 3.0 if sample_count else None,
                "median_pct": 3.0 if sample_count else None,
                "observed_positive_rate_pct": 100.0 if sample_count else None,
            },
            "market_return": {
                "sample_count": sample_count,
                "average_pct": 1.0 if sample_count else None,
                "median_pct": 1.0 if sample_count else None,
                "observed_positive_rate_pct": 100.0 if sample_count else None,
            },
            "market_adjusted_return": {
                "sample_count": sample_count,
                "average_pct": event_average,
                "median_pct": event_average,
                "observed_positive_rate_pct": 100.0 if sample_count else None,
            },
            "control_market_adjusted_return": {
                "sample_count": clean_controls,
                "average_pct": control_average,
                "median_pct": control_average,
                "observed_positive_rate_pct": 100.0 if clean_controls else None,
            },
            "observed_event_minus_control_pct_points": difference,
        }
    report_payload = {
        "report_contract_version": "VN_P6_S1_EVENT_REPORT_V1",
        "protocol_id": "EVAL-PROTOCOL",
        "protocol_hash": evaluation_protocol_hash,
        "observations": [
            {
                "observation_id": f"OBS-{index}",
                "observation_hash": f"hash-{index}",
                "sample_identity": f"SAMPLE-{index}",
            }
            for index in range(sample_count)
        ],
        "controls": [],
        "report_id": report_id,
        "report_status": "COMPLETE",
        "sample_count": sample_count,
        "sample_sufficiency": "UNDECIDED",
        "statistical_test_status": "NOT_CONFIGURED",
        "deduplicated_observation_ids": [],
        "horizons": horizons,
        "control_summary": {
            "approved": clean_controls + contaminated_controls > 0,
            "method": (
                "EXPLICIT_MATCH_SET"
                if clean_controls + contaminated_controls > 0
                else "NONE"
            ),
            "clean_match_count": clean_controls,
            "contaminated_match_count": contaminated_controls,
        },
        "guardrail": "fixture",
    }
    report_hash = _digest(report_payload)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO event_evidence_evaluation_protocol(
                protocol_id,protocol_contract_version,control_method,
                control_approved,observation_windows_json,
                reference_price_rule,benchmark_rule,
                statistical_test_status,minimum_control_count,
                protocol_json,protocol_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "EVAL-PROTOCOL",
                "VN_P6_S1_EVENT_EVALUATION_PROTOCOL_V1",
                (
                    "EXPLICIT_MATCH_SET"
                    if clean_controls + contaminated_controls > 0
                    else "NONE"
                ),
                int(clean_controls + contaminated_controls > 0),
                "[1,5,20]",
                "PREVIOUS_CONFIRMED_DAILY_CLOSE",
                "MAIN_MARKET_INDEX",
                "NOT_CONFIGURED",
                None,
                _canonical_json(evaluation_protocol),
                evaluation_protocol_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_evaluation_report(
                report_id,report_contract_version,protocol_id,protocol_hash,
                report_status,sample_count,sample_sufficiency,
                statistical_test_status,observation_bundle_json,
                report_json,report_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                report_id,
                "VN_P6_S1_EVENT_REPORT_V1",
                "EVAL-PROTOCOL",
                evaluation_protocol_hash,
                "COMPLETE",
                sample_count,
                "UNDECIDED",
                "NOT_CONFIGURED",
                _canonical_json(report_payload["observations"]),
                _canonical_json(report_payload),
                report_hash,
                NOW,
            ),
        )
    return {
        "report_id": report_id,
        "report_hash": report_hash,
        "sample_count": sample_count,
        "sample_sufficiency": "UNDECIDED",
        "statistical_test_status": "NOT_CONFIGURED",
        "observation_bundle": report_payload["observations"],
        "report": report_payload,
    }


def _test_protocol(protocol_id: str, *, threshold: float = 0.5):
    return IncrementalValueGateProtocol(
        protocol_id=protocol_id,
        status=ValueGateProtocolStatus.SYNTHETIC_TEST_ONLY,
        criteria_precommitted=True,
        sample_rule_approved=True,
        uncertainty_rule_approved=True,
        multiple_testing_policy_approved=True,
        control_rule_approved=True,
        required_horizons=(1, 5, 20),
        minimum_sample_count=2,
        minimum_clean_control_count=2,
        minimum_observed_difference_pct_points=threshold,
    )


def _stub_report_integrity(gate: EventIncrementalValueGate, report: dict):
    gate.evaluator.get_report = lambda report_id: report
    gate.evaluator.verify_report = lambda report_id: {
        "status": "MATCH",
        "report_id": report_id,
        "report_hash": report["report_hash"],
        "sample_count": report["sample_count"],
    }


def test_value_gate_migration_is_idempotent_and_empty(tmp_path: Path):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    first = migrate_event_evidence_store(db)
    second = migrate_event_evidence_store(db)

    assert first["value_gate_protocol_count"] == 0
    assert first["value_gate_decision_count"] == 0
    assert second["value_gate_protocol_count"] == 0
    assert second["value_gate_decision_count"] == 0
    assert first["real_corpus_evaluation_performed"] is False
    assert first["external_network_requests"] == 0


def test_production_unapproved_protocol_holds_without_invented_thresholds(
    tmp_path: Path,
):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    protocol = gate.register_protocol(
        IncrementalValueGateProtocol(protocol_id="PRODUCTION-HOLD")
    )
    report = _insert_report(
        db,
        report_id="REPORT-HOLD",
        sample_count=3,
        clean_controls=0,
        contaminated_controls=0,
        differences={"1": 3.0, "5": 3.0, "20": 3.0},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.UNKNOWN

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id=protocol["protocol_id"],
    )

    assert decision["decision"] == "HOLD"
    assert decision["product_scope"] == "RESEARCH_ONLY"
    assert decision["prediction_eligible"] is False
    assert "GATE_CRITERIA_UNAPPROVED" in decision["decision_reasons"]
    assert "SAMPLE_SUFFICIENCY_UNDECIDED" in decision["decision_reasons"]
    assert "CONTROL_COMPARISON_NOT_AVAILABLE" in decision["decision_reasons"]
    assert "REAL_CORPUS_NOT_AVAILABLE" in decision["decision_reasons"]


def test_synthetic_test_protocol_can_exercise_pass_engine_only(tmp_path: Path):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(_test_protocol("SYNTHETIC-PASS"))
    report = _insert_report(
        db,
        report_id="REPORT-PASS",
        sample_count=3,
        clean_controls=3,
        contaminated_controls=0,
        differences={"1": 1.0, "5": 1.5, "20": 0.8},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.SYNTHETIC_ONLY

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="SYNTHETIC-PASS",
    )

    assert decision["decision"] == "PASS"
    assert decision["evidence_population"] == "SYNTHETIC_ONLY"
    assert decision["product_scope"] == "REFERENCE_CONTEXT"
    assert decision["prediction_eligible"] is False
    assert "INCREMENTAL_VALUE_CRITERIA_MET" in decision["decision_reasons"]
    assert all(
        item["status"] == "PASS"
        for item in decision["horizon_results"].values()
    )


def test_synthetic_test_protocol_fails_when_required_horizon_misses(
    tmp_path: Path,
):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(_test_protocol("SYNTHETIC-FAIL"))
    report = _insert_report(
        db,
        report_id="REPORT-FAIL",
        sample_count=3,
        clean_controls=3,
        contaminated_controls=0,
        differences={"1": 1.0, "5": -0.1, "20": 0.8},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.SYNTHETIC_ONLY

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="SYNTHETIC-FAIL",
    )
    assert decision["decision"] == "FAIL"
    assert decision["horizon_results"]["5"]["status"] == "FAIL"
    assert "INCREMENTAL_VALUE_NOT_DEMONSTRATED" in decision["decision_reasons"]
    assert decision["prediction_eligible"] is False


def test_synthetic_protocol_cannot_be_used_on_real_corpus(tmp_path: Path):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(_test_protocol("TEST-ONLY"))
    report = _insert_report(
        db,
        report_id="REPORT-REAL",
        sample_count=3,
        clean_controls=3,
        contaminated_controls=0,
        differences={"1": 2.0, "5": 2.0, "20": 2.0},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.REAL_CORPUS

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="TEST-ONLY",
    )
    assert decision["decision"] == "BLOCKED"
    assert "TEST_PROTOCOL_REAL_DATA_FORBIDDEN" in decision["decision_reasons"]


def test_report_integrity_failure_creates_blocked_decision(tmp_path: Path):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(IncrementalValueGateProtocol(protocol_id="BLOCKED"))
    report = _insert_report(
        db,
        report_id="REPORT-BROKEN",
        sample_count=2,
        clean_controls=0,
        contaminated_controls=0,
        differences={"1": None, "5": None, "20": None},
    )
    gate.evaluator.get_report = lambda report_id: report

    def _broken(_):
        raise EventEvidenceContractError("BROKEN", "fixture")

    gate.evaluator.verify_report = _broken
    gate._population_for_report = lambda _: EvidencePopulation.UNKNOWN

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="BLOCKED",
    )
    assert decision["decision"] == "BLOCKED"
    assert decision["integrity_state"] == "MISMATCH"
    assert "REPORT_INTEGRITY_FAILED" in decision["decision_reasons"]


def test_clean_control_requirement_holds_if_controls_are_insufficient(
    tmp_path: Path,
):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(_test_protocol("CONTROL-HOLD"))
    report = _insert_report(
        db,
        report_id="REPORT-CONTROL-HOLD",
        sample_count=3,
        clean_controls=1,
        contaminated_controls=2,
        differences={"1": 1.0, "5": 1.0, "20": 1.0},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.SYNTHETIC_ONLY

    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="CONTROL-HOLD",
    )
    assert decision["decision"] == "HOLD"
    assert "CONTROL_EVIDENCE_INSUFFICIENT" in decision["decision_reasons"]


def test_gate_artifacts_are_immutable(tmp_path: Path):
    db = _db(tmp_path)
    gate = EventIncrementalValueGate(db, _market_db(tmp_path), clock=lambda: NOW)
    gate.register_protocol(IncrementalValueGateProtocol(protocol_id="IMMUTABLE"))
    report = _insert_report(
        db,
        report_id="REPORT-IMMUTABLE",
        sample_count=1,
        clean_controls=0,
        contaminated_controls=0,
        differences={"1": None, "5": None, "20": None},
    )
    _stub_report_integrity(gate, report)
    gate._population_for_report = lambda _: EvidencePopulation.UNKNOWN
    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="IMMUTABLE",
    )

    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_value_gate_protocol
                SET status='SYNTHETIC_TEST_ONLY'
                WHERE protocol_id='IMMUTABLE'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM event_evidence_value_gate_decision
                WHERE decision_id=?
                """,
                (decision["decision_id"],),
            )


def test_unapproved_protocol_rejects_numeric_criteria():
    with pytest.raises(EventEvidenceContractError) as caught:
        IncrementalValueGateProtocol(
            protocol_id="BAD",
            minimum_sample_count=10,
        )
    assert caught.value.code == "EVENT_VALUE_GATE_UNAPPROVED_CRITERIA_FORBIDDEN"
