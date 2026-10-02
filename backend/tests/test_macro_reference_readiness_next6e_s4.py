from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.macro.identity import content_hash
from app.macro.reference_readiness import (
    NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION,
    ProspectiveReferenceSummaryReader,
    ReferenceReadinessError,
    assess_next6e_reference_readiness,
    build_next6e_reference_readiness,
)
from app.macro.validation_entry_gate import (
    build_next6e_validation_entry_gate,
)
from app.prospective.reference_capture import (
    NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
    REFERENCE_TEMPORAL_MODE,
)


ROOT = Path(__file__).resolve().parents[2]


def _gate() -> dict[str, object]:
    return build_next6e_validation_entry_gate(
        scanner_version=StockScannerService.VERSION,
        macro_numeric_policy="NONE",
        reference_adequacy="UNRESOLVED",
        rate_spike_calibration_status="UNCALIBRATED",
        historical_sector_status="BLOCKED_EXTERNAL_SOURCE",
        historical_impact_mode="MARKET_STOCK_ONLY",
        prospective_sector_status="NOT_STARTED",
        p6_asof_mode="SYSTEM_OBSERVED_AS_OF",
        p6_historical_completeness_proven=False,
        p6_historical_evaluation_approved=False,
        prediction_status="NOT_VALIDATED",
    )


def _development_report(
    gate: dict[str, object],
    *,
    status: str = "COMPLETE",
    unavailable_reason: str | None = None,
    sample_count: int = 2,
) -> dict[str, object]:
    summary = {
        "sample_count": sample_count,
        "unique_trading_day_count": 2 if sample_count else 0,
        "unique_ticker_count": 2 if sample_count else 0,
        "result_bucket_counts": {"TOP": sample_count} if sample_count else {},
        "macro": {
            "status_counts": {"AVAILABLE": sample_count}
            if sample_count
            else {},
            "reason_counts": {},
            "historical_evaluation_eligible_counts": {
                "false": sample_count
            }
            if sample_count
            else {},
        },
        "market_reader": {
            "status_counts": {"COMPLETE": sample_count}
            if sample_count
            else {},
            "reason_counts": {},
        },
        "impact": {
            "status_counts": {"COMPLETE": sample_count}
            if sample_count
            else {},
            "reason_counts": {},
        },
        "event": {
            "reader_status_counts": {"AVAILABLE": sample_count}
            if sample_count
            else {},
            "reader_reason_counts": {},
            "status_counts": {"REFERENCE_AVAILABLE": sample_count}
            if sample_count
            else {},
            "total_reference_count": sample_count,
            "total_projected_reference_count": sample_count,
            "diagnostic_totals": {},
        },
        "sector": {
            "historical_sector_status_counts": {
                "BLOCKED_EXTERNAL_SOURCE": sample_count
            }
            if sample_count
            else {},
        },
        "composition": {
            "status_counts": {"AVAILABLE": sample_count}
            if sample_count
            else {},
            "limitation_counts": {},
        },
    }
    payload = {
        "contract_version": "VN_NEXT6E_S2_DEVELOPMENT_REFERENCE_COVERAGE_V1",
        "status": status,
        "unavailable_reason": unavailable_reason,
        "entry_gate": {
            "gate_id": gate["gate_id"],
            "gate_hash": gate["gate_hash"],
        },
        "scope": {
            "validation_id": "validation-dev",
            "scanner_version": StockScannerService.VERSION,
            "development_start": "2026-01-01",
            "development_end": "2026-06-30",
            "cutoff_policy_version": (
                "VN_NEXT6E_S2_DEVELOPMENT_DAY_END_CUTOFF_V1"
            ),
        },
        "sample_manifest": {
            "input_sample_count": sample_count,
            "unique_sample_count": sample_count,
            "sample_manifest_hash": "a" * 64,
        },
        "summary": summary,
        "limitations": [
            "DAY_END_COVERAGE_NOT_SIGNAL_TIME",
            "DEVELOPMENT_ONLY",
            "EVENT_HISTORICAL_COMPLETENESS_NOT_PROVEN",
            "HISTORICAL_SECTOR_NOT_AVAILABLE",
            "NO_EFFECTIVENESS_CLAIM",
            "NO_EXECUTION_COMPARISON",
            "NO_PREDICTION",
            "REFERENCE_COVERAGE_ONLY",
        ],
        "governance": {
            "claim_scope": "DEVELOPMENT_REFERENCE_COVERAGE_ONLY",
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
        },
        "source_immutability_verified": True,
    }
    digest = content_hash(payload)
    return {
        **payload,
        "report_id": f"DEVREFCOV-{digest[:16]}",
        "report_hash": digest,
    }


def _prospective(
    *,
    completed: int = 1,
    attachments: int = 2,
    status: str = "READY",
    reason: str | None = None,
) -> dict[str, object]:
    sets = [
        {
            "capture_run_id": f"capture-{index + 1}",
            "source_sample_count": attachments,
            "attachment_count": attachments,
            "attachment_set_hash": f"{index + 1:064x}",
            "source_manifest_hash": f"{index + 101:064x}",
        }
        for index in range(completed)
    ]
    return {
        "status": status,
        "reason": reason,
        "storage_version": (
            NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
            if status == "READY"
            else None
        ),
        "capture_contract_version": (
            NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
        ),
        "reference_temporal_mode": REFERENCE_TEMPORAL_MODE,
        "decision_input": False,
        "signal_time_equivalence": False,
        "completed_capture_count": completed,
        "attachment_count": attachments * completed,
        "capture_status_counts": {"COMPLETE": completed}
        if completed
        else {},
        "attachment_sets": sets,
    }


def _create_reference_store(path: Path, *, completed: int = 1) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE prospective_reference_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE prospective_reference_capture(
                capture_run_id TEXT PRIMARY KEY,
                capture_contract_version TEXT NOT NULL,
                storage_version TEXT NOT NULL,
                status TEXT NOT NULL,
                reference_cutoff TEXT NOT NULL,
                cutoff_policy_version TEXT NOT NULL,
                reference_temporal_mode TEXT NOT NULL,
                source_sample_count INTEGER NOT NULL,
                attachment_count INTEGER NOT NULL,
                attachment_set_hash TEXT NOT NULL,
                source_manifest_hash TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE prospective_reference_attachment(
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                attachment_id TEXT NOT NULL,
                attachment_hash TEXT NOT NULL,
                source_snapshot_hash TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                reference_cutoff TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(capture_run_id,sample_index)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO prospective_reference_schema_meta(key,value)
            VALUES('schema_version',?)
            """,
            (NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,),
        )
        for index in range(completed):
            conn.execute(
                """
                INSERT INTO prospective_reference_capture(
                    capture_run_id,capture_contract_version,storage_version,
                    status,reference_cutoff,cutoff_policy_version,
                    reference_temporal_mode,source_sample_count,
                    attachment_count,attachment_set_hash,
                    source_manifest_hash,error_code,error_message,
                    created_at,completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"capture-{index + 1}",
                    NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
                    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
                    "COMPLETE",
                    "2026-10-01T15:30:00+09:00",
                    "VN_NEXT6E_S3_CAPTURE_COMPLETED_AT_CUTOFF_V1",
                    REFERENCE_TEMPORAL_MODE,
                    2,
                    2,
                    f"{index + 1:064x}",
                    f"{index + 101:064x}",
                    None,
                    None,
                    "2026-10-01T15:30:00+09:00",
                    "2026-10-01T15:30:00+09:00",
                ),
            )


def test_current_s1_s2_s3_consolidates_without_unlocking_effectiveness() -> None:
    gate = _gate()
    report = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=_development_report(gate),
        prospective_reference=_prospective(),
    )

    assert report["contract_version"] == (
        NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION
    )
    assert report["readiness_state"] == "REFERENCE_ADEQUACY_UNRESOLVED"
    assert report["prospective_reference"]["reference_temporal_mode"] == (
        "POST_SCANNER_CAPTURE"
    )
    assert report["prospective_reference"]["decision_input"] is False
    assert report["prospective_reference"]["signal_time_equivalence"] is False
    assert report["next_allowed_scope"] == {
        "reference_adequacy_review": True,
        "prospective_accumulation": True,
        "shock_effectiveness": False,
        "sector_effectiveness": False,
        "event_incremental_value": False,
        "execution_policy_comparison": False,
        "holdout_evaluation": False,
        "production_activation": False,
    }
    assert report["governance"]["holdout_access"] is False
    assert report["governance"]["network_access"] is False
    assert report["governance"]["database_write"] is False
    assert report["governance"]["production_decision_approved"] is False


def test_identical_inputs_produce_identical_readiness_identity() -> None:
    gate = _gate()
    development = _development_report(gate)
    prospective = _prospective()

    first = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=development,
        prospective_reference=prospective,
    )
    second = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=development,
        prospective_reference=prospective,
    )

    assert first == second
    assert first["reference_readiness_id"] == second["reference_readiness_id"]
    assert first["reference_readiness_hash"] == (
        second["reference_readiness_hash"]
    )


def test_no_prospective_capture_requires_accumulation_without_threshold() -> None:
    gate = _gate()
    report = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=_development_report(gate),
        prospective_reference=_prospective(completed=0, attachments=0),
    )

    assert report["readiness_state"] == "PROSPECTIVE_ACCUMULATION_REQUIRED"
    assert report["prospective_reference"]["attachment_count"] == 0
    assert report["next_allowed_scope"]["reference_adequacy_review"] is False
    assert report["next_allowed_scope"]["prospective_accumulation"] is True


def test_no_development_samples_is_explicitly_insufficient() -> None:
    gate = _gate()
    report = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=_development_report(
            gate,
            status="NO_DEVELOPMENT_SAMPLES",
            sample_count=0,
        ),
        prospective_reference=_prospective(),
    )

    assert report["readiness_state"] == (
        "DEVELOPMENT_COVERAGE_INSUFFICIENT"
    )
    assert report["next_allowed_scope"]["reference_adequacy_review"] is False


def test_unavailable_development_source_remains_unavailable() -> None:
    gate = _gate()
    report = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=_development_report(
            gate,
            status="AUDIT_UNAVAILABLE",
            unavailable_reason="MACRO_SOURCE_UNAVAILABLE:STORE_NOT_FOUND",
        ),
        prospective_reference=_prospective(),
    )

    assert report["readiness_state"] == "SOURCE_COVERAGE_UNAVAILABLE"
    assert report["development_reference"]["unavailable_reason"] == (
        "MACRO_SOURCE_UNAVAILABLE:STORE_NOT_FOUND"
    )


def test_s3_schema_not_ready_is_source_coverage_unavailable(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db):
        pass

    summary = ProspectiveReferenceSummaryReader(db).read()
    gate = _gate()
    report = build_next6e_reference_readiness(
        entry_gate=gate,
        development_report=_development_report(gate),
        prospective_reference=summary,
    )

    assert summary["status"] == "NOT_READY"
    assert summary["reason"] == "PROSPECTIVE_REFERENCE_SCHEMA_MISSING"
    assert report["readiness_state"] == "SOURCE_COVERAGE_UNAVAILABLE"


def test_readonly_s3_summary_preserves_file_and_attachment_set_identity(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    _create_reference_store(db, completed=2)
    before = db.read_bytes()

    summary = ProspectiveReferenceSummaryReader(db).read()

    after = db.read_bytes()
    assert before == after
    assert summary["status"] == "READY"
    assert summary["completed_capture_count"] == 2
    assert summary["attachment_count"] == 4
    assert [item["capture_run_id"] for item in summary["attachment_sets"]] == [
        "capture-1",
        "capture-2",
    ]


def test_assess_reads_s3_and_returns_deterministic_report(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    _create_reference_store(db, completed=1)
    gate = _gate()
    development = _development_report(gate)

    first = assess_next6e_reference_readiness(
        entry_gate=gate,
        development_report=development,
        simulation_db=db,
    )
    second = assess_next6e_reference_readiness(
        entry_gate=gate,
        development_report=development,
        simulation_db=db,
    )

    assert first == second
    assert first["prospective_reference"]["completed_capture_count"] == 1


def test_mismatched_gate_or_s3_contract_fails_closed() -> None:
    gate = _gate()
    development = _development_report(gate)

    wrong_development = dict(development)
    wrong_development["entry_gate"] = {
        "gate_id": "other",
        "gate_hash": "other",
    }
    with pytest.raises(ReferenceReadinessError, match="entry gate"):
        build_next6e_reference_readiness(
            entry_gate=gate,
            development_report=wrong_development,
            prospective_reference=_prospective(),
        )

    wrong_prospective = _prospective()
    wrong_prospective["decision_input"] = True
    with pytest.raises(ReferenceReadinessError, match="decision input"):
        build_next6e_reference_readiness(
            entry_gate=gate,
            development_report=development,
            prospective_reference=wrong_prospective,
        )


def test_s4_source_has_no_effectiveness_network_or_write_wiring() -> None:
    source = (
        ROOT / "backend/app/macro/reference_readiness.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "historical_validation_candidate_outcome",
        "historical_execution_",
        "prospective_evaluation_",
        "return_5d",
        "return_10d",
        "return_20d",
        "mfe_pct",
        "mae_pct",
        "requests",
        "httpx",
        "urllib.request",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "CREATE TABLE",
        "datetime.now",
        "datetime.utcnow",
        "uuid4",
        "random.",
    )
    for token in forbidden:
        assert token not in source

    assert "?mode=ro" in source
    assert "PRAGMA query_only=ON" in source


def test_macro_package_exports_next6e_s4_contract() -> None:
    import app.macro as macro

    assert macro.NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION == (
        NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION
    )
    assert macro.ProspectiveReferenceSummaryReader is (
        ProspectiveReferenceSummaryReader
    )
    assert callable(macro.build_next6e_reference_readiness)
    assert callable(macro.assess_next6e_reference_readiness)
