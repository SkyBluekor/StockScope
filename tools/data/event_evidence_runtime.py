from __future__ import annotations

from pathlib import Path
from typing import Any

from app.event_evidence.entity import (
    ENTITY_IDENTITY_CONTRACT_VERSION,
    EVENT_RELEVANCE_CONTRACT_VERSION,
)
from app.event_evidence.evaluation import (
    EVENT_EVALUATION_CONTRACT_VERSION,
    EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION,
    EVENT_EVALUATION_REPORT_CONTRACT_VERSION,
    EVENT_OUTCOME_CONTRACT_VERSION,
)
from app.event_evidence.models import (
    REVISION_IDENTITY_CONTRACT_VERSION,
    SOURCE_REF_CONTRACT_VERSION,
)
from app.event_evidence.policy import SOURCE_POLICY_CONTRACT_VERSION
from app.event_evidence.quality import EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION
from app.event_evidence.resolution import EVENT_RESOLUTION_CONTRACT_VERSION
from app.event_evidence.store import (
    EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
    EVENT_EVIDENCE_RECORD_VERSION,
    EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
)
from app.event_evidence.time import TEMPORAL_EVIDENCE_CONTRACT_VERSION
from app.event_evidence.value_gate import (
    INCREMENTAL_VALUE_GATE_CONTRACT_VERSION,
    VALUE_GATE_DECISION_CONTRACT_VERSION,
    VALUE_GATE_PROTOCOL_CONTRACT_VERSION,
)
from tools.data.common import DataToolError, sqlite_readonly
from tools.data.migrate_event_evidence_vnp6s1 import TABLE_COLUMNS


EVENT_EVIDENCE_BACKUP_EXTENSION = "event_evidence_v1"

EVENT_EVIDENCE_META_EXPECTED: dict[str, str] = {
    "schema_version": EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
    "source_policy_contract_version": SOURCE_POLICY_CONTRACT_VERSION,
    "temporal_evidence_contract_version": TEMPORAL_EVIDENCE_CONTRACT_VERSION,
    "source_ref_contract_version": SOURCE_REF_CONTRACT_VERSION,
    "revision_identity_contract_version": REVISION_IDENTITY_CONTRACT_VERSION,
    "event_record_version": EVENT_EVIDENCE_RECORD_VERSION,
    "hash_contract_version": EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
    "entity_contract_version": ENTITY_IDENTITY_CONTRACT_VERSION,
    "relevance_contract_version": EVENT_RELEVANCE_CONTRACT_VERSION,
    "resolution_contract_version": EVENT_RESOLUTION_CONTRACT_VERSION,
    "quality_contract_version": EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION,
    "evaluation_contract_version": EVENT_EVALUATION_CONTRACT_VERSION,
    "evaluation_protocol_contract_version": (
        EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION
    ),
    "outcome_contract_version": EVENT_OUTCOME_CONTRACT_VERSION,
    "evaluation_report_contract_version": (
        EVENT_EVALUATION_REPORT_CONTRACT_VERSION
    ),
    "incremental_value_gate_contract_version": (
        INCREMENTAL_VALUE_GATE_CONTRACT_VERSION
    ),
    "value_gate_protocol_contract_version": (
        VALUE_GATE_PROTOCOL_CONTRACT_VERSION
    ),
    "value_gate_decision_contract_version": (
        VALUE_GATE_DECISION_CONTRACT_VERSION
    ),
}

EVENT_EVIDENCE_BACKUP_TABLES = (
    "event_evidence_schema_meta",
    *tuple(TABLE_COLUMNS.keys()),
)

EVENT_EVIDENCE_COUNT_TABLES: dict[str, str] = {
    "policy_snapshot_count": "event_evidence_policy_snapshot",
    "source_ref_count": "event_evidence_source_ref",
    "event_evidence_count": "event_evidence_record",
    "event_source_link_count": "event_evidence_record_source",
    "entity_count": "event_evidence_entity",
    "relevance_count": "event_evidence_entity_relevance",
    "canonical_group_count": "event_evidence_canonical_group",
    "resolution_count": "event_evidence_resolution",
    "quality_assessment_count": "event_evidence_quality_assessment",
    "evaluation_protocol_count": "event_evidence_evaluation_protocol",
    "outcome_observation_count": "event_evidence_outcome_observation",
    "control_match_count": "event_evidence_control_match",
    "evaluation_report_count": "event_evidence_evaluation_report",
    "value_gate_protocol_count": "event_evidence_value_gate_protocol",
    "value_gate_decision_count": "event_evidence_value_gate_decision",
}


def _absent_state() -> dict[str, Any]:
    return {
        "schema_version": EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
        "present": False,
        "tables": [],
        "restorable": False,
        "contract_versions": dict(EVENT_EVIDENCE_META_EXPECTED),
        "counts": {
            key: 0 for key in EVENT_EVIDENCE_COUNT_TABLES
        },
        "prediction_enabled": False,
    }


def _table_names(conn) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def inspect_event_evidence_store(
    simulation_db: Path | None,
) -> dict[str, Any]:
    if simulation_db is None:
        return _absent_state()
    path = Path(simulation_db)
    if not path.is_file():
        return _absent_state()

    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError(
                "P6 Event Evidence Simulation DB integrity_check에 실패했습니다."
            )
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise DataToolError(
                "P6 Event Evidence Simulation DB foreign_key_check에 실패했습니다."
            )

        all_tables = _table_names(conn)
        expected_tables = set(EVENT_EVIDENCE_BACKUP_TABLES)
        present_tables = sorted(expected_tables & all_tables)
        if not present_tables:
            return _absent_state()
        if set(present_tables) != expected_tables:
            missing = sorted(expected_tables - set(present_tables))
            raise DataToolError(
                "P6 Event Evidence가 부분 migration 상태입니다: "
                + ", ".join(missing)
            )

        for table, required_columns in TABLE_COLUMNS.items():
            missing_columns = sorted(
                set(required_columns) - _columns(conn, table)
            )
            if missing_columns:
                raise DataToolError(
                    f"P6 Event Evidence table schema 불일치: {table}: "
                    + ", ".join(missing_columns)
                )

        meta = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                "SELECT key,value FROM event_evidence_schema_meta"
            ).fetchall()
        }
        for key, expected in EVENT_EVIDENCE_META_EXPECTED.items():
            actual = meta.get(key)
            if actual != expected:
                raise DataToolError(
                    "P6 Event Evidence contract version 불일치: "
                    f"{key}={actual!r}, expected={expected!r}"
                )

        counts = {
            key: int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
            )
            for key, table in EVENT_EVIDENCE_COUNT_TABLES.items()
        }
        prediction_rows = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM event_evidence_value_gate_decision
                WHERE prediction_eligible<>0
                """
            ).fetchone()[0]
        )
        if prediction_rows:
            raise DataToolError(
                "P6-S1-F V1 backup에서 prediction_eligible=True "
                "Decision을 허용할 수 없습니다."
            )

    return {
        "schema_version": EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
        "present": True,
        "tables": list(EVENT_EVIDENCE_BACKUP_TABLES),
        "restorable": True,
        "contract_versions": dict(EVENT_EVIDENCE_META_EXPECTED),
        "counts": counts,
        "prediction_enabled": False,
    }


def validate_event_evidence_state(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    label: str,
) -> None:
    keys = (
        "schema_version",
        "present",
        "tables",
        "restorable",
        "contract_versions",
        "counts",
        "prediction_enabled",
    )
    for key in keys:
        if expected.get(key) != actual.get(key):
            raise DataToolError(
                f"P6 Event Evidence {label} metadata가 실제 상태와 다릅니다: "
                + key
            )
