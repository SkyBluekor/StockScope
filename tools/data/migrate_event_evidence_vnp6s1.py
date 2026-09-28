from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.event_evidence.entity import (
    ENTITY_IDENTITY_CONTRACT_VERSION,
    EVENT_RELEVANCE_CONTRACT_VERSION,
)
from app.event_evidence.models import (
    REVISION_IDENTITY_CONTRACT_VERSION,
    SOURCE_REF_CONTRACT_VERSION,
)
from app.event_evidence.resolution import EVENT_RESOLUTION_CONTRACT_VERSION
from app.event_evidence.quality import EVENT_EVIDENCE_QUALITY_CONTRACT_VERSION
from app.event_evidence.evaluation import (
    EVENT_EVALUATION_CONTRACT_VERSION,
    EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION,
    EVENT_OUTCOME_CONTRACT_VERSION,
    EVENT_EVALUATION_REPORT_CONTRACT_VERSION,
)
from app.event_evidence.policy import SOURCE_POLICY_CONTRACT_VERSION
from app.event_evidence.store import (
    EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
    EVENT_EVIDENCE_RECORD_VERSION,
    EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
)
from app.event_evidence.time import TEMPORAL_EVIDENCE_CONTRACT_VERSION
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


TABLE_COLUMNS: dict[str, set[str]] = {
    "event_evidence_policy_snapshot": {
        "policy_id","policy_contract_version","source_kind","policy_version",
        "display_allowed","normalization_allowed","raw_retention_allowed",
        "derived_retention_allowed","ai_transform_allowed",
        "historical_evaluation_allowed","prediction_input_allowed",
        "attribution_required","effective_from","policy_basis",
        "policy_json","policy_hash","created_at",
    },
    "event_evidence_source_ref": {
        "source_ref_id","source_ref_contract_version","source_kind",
        "source_native_id","rights_policy_id","rights_policy_hash",
        "source_url","source_name","content_hash","event_time",
        "source_published_at","provider_published_at","first_seen_at",
        "available_at","fetched_at","corrected_at","time_quality",
        "temporal_contract_version","source_ref_json","source_ref_hash",
        "created_at",
    },
    "event_evidence_record": {
        "event_id","event_version","record_version","hash_contract_version",
        "event_state","supersedes_version","event_type","scope",
        "event_time","available_at","time_quality","temporal_json",
        "event_payload_json","source_bundle_hash","event_hash","created_at",
    },
    "event_evidence_record_source": {
        "event_id","event_version","sequence","source_ref_id","source_ref_hash",
    },
    "event_evidence_entity": {
        "entity_id","entity_contract_version","entity_type","entity_key",
        "market","ticker","name","identity_source","identity_as_of",
        "identity_json","identity_hash","created_at",
    },
    "event_evidence_entity_relevance": {
        "relevance_id","relevance_contract_version","event_id","event_version",
        "event_hash","entity_id","entity_hash","relation_type",
        "relevance_state","evidence_kind","evidence_ref","evidence_as_of",
        "relation_json","relation_hash","created_at",
    },
    "event_evidence_canonical_group": {
        "canonical_event_id","canonical_version","resolution_contract_version",
        "representative_event_id","representative_event_version",
        "resolution_method","resolution_confidence","canonical_fingerprint",
        "canonical_hash","created_at",
    },
    "event_evidence_resolution": {
        "resolution_id","resolution_contract_version","event_id","event_version",
        "canonical_event_id","canonical_version","resolution_type",
        "resolution_basis_json","resolution_hash","created_at",
    },
    "event_evidence_quality_assessment": {
        "assessment_id","quality_contract_version","assessment_scope",
        "assessment_as_of","event_id","event_version","event_hash",
        "source_bundle_hash","entity_id","entity_hash","relevance_id",
        "relevance_hash","relation_type","rights_policy_bundle_hash",
        "canonical_event_id","canonical_version","canonical_hash",
        "resolution_hash","rights_state","integrity_state","temporal_state",
        "relevance_state","resolution_state","revision_state",
        "corroboration_state","source_count","distinct_source_origin_count",
        "quality_state","blocking_reasons_json","insufficient_reasons_json",
        "limitations_json","quality_json","quality_hash","created_at",
    },
    "event_evidence_evaluation_protocol": {
        "protocol_id","protocol_contract_version","control_method",
        "control_approved","observation_windows_json","reference_price_rule",
        "benchmark_rule","statistical_test_status","minimum_control_count",
        "protocol_json","protocol_hash","created_at",
    },
    "event_evidence_outcome_observation": {
        "observation_id","evaluation_contract_version",
        "outcome_contract_version","protocol_id","protocol_hash",
        "quality_assessment_id","quality_hash","event_id","event_version",
        "entity_id","entity_hash","canonical_event_id","sample_identity",
        "assessment_as_of","market","ticker","reference_price_rule",
        "benchmark_rule","sector_benchmark_status","market_evidence_hash",
        "evaluation_status","evaluation_reason","reference_trading_day",
        "reference_close","benchmark_reference_close","price_basis",
        "adjustment_basis","horizons_json","observation_json",
        "observation_hash","created_at",
    },
    "event_evidence_control_match": {
        "control_id","evaluation_contract_version","observation_id",
        "protocol_id","protocol_hash","control_as_of_date",
        "contamination_state","contaminated_by_json","market_evidence_hash",
        "evaluation_status","reference_trading_day","reference_close",
        "benchmark_reference_close","horizons_json","control_json",
        "control_hash","created_at",
    },
    "event_evidence_evaluation_report": {
        "report_id","report_contract_version","protocol_id","protocol_hash",
        "report_status","sample_count","sample_sufficiency",
        "statistical_test_status","observation_bundle_json","report_json",
        "report_hash","created_at",
    },
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _require_columns(conn: sqlite3.Connection, table: str) -> None:
    missing = sorted(TABLE_COLUMNS[table] - _columns(conn, table))
    if missing:
        raise DataToolError(
            f"{table} schema가 VN-P6-S1과 호환되지 않습니다: "
            + ", ".join(missing)
        )


def _inspect_simulation_db(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")
    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")
        tables = _table_names(conn)
        return {
            "existing_table_count": len(tables),
            "strategy_governance_present": (
                "strategy_governance_schema_meta" in tables
            ),
            "prospective_present": "prospective_schema_meta" in tables,
        }


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    expected = {
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
    }
    for key, value in expected.items():
        row = conn.execute(
            "SELECT value FROM event_evidence_schema_meta WHERE key=?",
            (key,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO event_evidence_schema_meta(key,value) VALUES(?,?)",
                (key, value),
            )
        elif str(row[0]) != value:
            raise DataToolError(
                f"Event Evidence meta 불일치: {key}={row[0]}"
            )


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_policy_snapshot(
            policy_id TEXT PRIMARY KEY,
            policy_contract_version TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            display_allowed INTEGER NOT NULL CHECK(display_allowed IN (0,1)),
            normalization_allowed INTEGER NOT NULL CHECK(normalization_allowed IN (0,1)),
            raw_retention_allowed INTEGER NOT NULL CHECK(raw_retention_allowed IN (0,1)),
            derived_retention_allowed INTEGER NOT NULL CHECK(derived_retention_allowed IN (0,1)),
            ai_transform_allowed INTEGER NOT NULL CHECK(ai_transform_allowed IN (0,1)),
            historical_evaluation_allowed INTEGER NOT NULL CHECK(historical_evaluation_allowed IN (0,1)),
            prediction_input_allowed INTEGER NOT NULL CHECK(prediction_input_allowed IN (0,1)),
            attribution_required INTEGER NOT NULL CHECK(attribution_required IN (0,1)),
            effective_from TEXT,
            policy_basis TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            policy_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_source_ref(
            source_ref_id TEXT PRIMARY KEY,
            source_ref_contract_version TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_native_id TEXT NOT NULL,
            rights_policy_id TEXT NOT NULL,
            rights_policy_hash TEXT NOT NULL,
            source_url TEXT,
            source_name TEXT,
            content_hash TEXT NOT NULL,
            event_time TEXT,
            source_published_at TEXT,
            provider_published_at TEXT,
            first_seen_at TEXT,
            available_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            corrected_at TEXT,
            time_quality TEXT NOT NULL CHECK(
                time_quality IN (
                    'EXACT','PROVIDER_TIME','DATE_ONLY','INFERRED','UNKNOWN'
                )
            ),
            temporal_contract_version TEXT NOT NULL,
            source_ref_json TEXT NOT NULL,
            source_ref_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(rights_policy_id)
                REFERENCES event_evidence_policy_snapshot(policy_id)
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_record(
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL CHECK(event_version >= 1),
            record_version TEXT NOT NULL,
            hash_contract_version TEXT NOT NULL,
            event_state TEXT NOT NULL CHECK(
                event_state IN ('ORIGINAL','CORRECTED','WITHDRAWN','SUPERSEDED')
            ),
            supersedes_version INTEGER,
            event_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            event_time TEXT,
            available_at TEXT NOT NULL,
            time_quality TEXT NOT NULL CHECK(
                time_quality IN (
                    'EXACT','PROVIDER_TIME','DATE_ONLY','INFERRED','UNKNOWN'
                )
            ),
            temporal_json TEXT NOT NULL,
            event_payload_json TEXT NOT NULL,
            source_bundle_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(event_id,event_version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_record_source(
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence >= 1),
            source_ref_id TEXT NOT NULL,
            source_ref_hash TEXT NOT NULL,
            PRIMARY KEY(event_id,event_version,sequence),
            UNIQUE(event_id,event_version,source_ref_id),
            FOREIGN KEY(event_id,event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT,
            FOREIGN KEY(source_ref_id)
                REFERENCES event_evidence_source_ref(source_ref_id)
                ON DELETE RESTRICT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_entity(
            entity_id TEXT PRIMARY KEY,
            entity_contract_version TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(
                entity_type IN (
                    'LISTED_COMPANY','INDUSTRY','POLICY','MACRO',
                    'COUNTRY','COMMODITY','OTHER'
                )
            ),
            entity_key TEXT NOT NULL,
            market TEXT,
            ticker TEXT,
            name TEXT NOT NULL,
            identity_source TEXT NOT NULL,
            identity_as_of TEXT NOT NULL,
            identity_json TEXT NOT NULL,
            identity_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(entity_type,entity_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_entity_relevance(
            relevance_id TEXT PRIMARY KEY,
            relevance_contract_version TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL,
            event_hash TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_hash TEXT NOT NULL,
            relation_type TEXT NOT NULL CHECK(
                relation_type IN (
                    'DIRECT_COMPANY','SUBSIDIARY','CUSTOMER','SUPPLIER',
                    'COMPETITOR','INDUSTRY','POLICY_EXPOSURE','MACRO_EXPOSURE'
                )
            ),
            relevance_state TEXT NOT NULL CHECK(
                relevance_state IN (
                    'CONFIRMED','SUPPORTED','WEAK','UNKNOWN','REJECTED'
                )
            ),
            evidence_kind TEXT NOT NULL CHECK(
                evidence_kind IN (
                    'SOURCE_DIRECT','CORP_CODE_MAPPING','STRUCTURED_RELATION',
                    'MANUAL_REVIEW','TITLE_HINT'
                )
            ),
            evidence_ref TEXT NOT NULL,
            evidence_as_of TEXT NOT NULL,
            relation_json TEXT NOT NULL,
            relation_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(event_id,event_version,entity_id,relation_type),
            FOREIGN KEY(event_id,event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT,
            FOREIGN KEY(entity_id)
                REFERENCES event_evidence_entity(entity_id)
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_canonical_group(
            canonical_event_id TEXT NOT NULL,
            canonical_version INTEGER NOT NULL CHECK(canonical_version >= 1),
            resolution_contract_version TEXT NOT NULL,
            representative_event_id TEXT NOT NULL,
            representative_event_version INTEGER NOT NULL,
            resolution_method TEXT NOT NULL,
            resolution_confidence TEXT NOT NULL,
            canonical_fingerprint TEXT NOT NULL,
            canonical_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(canonical_event_id,canonical_version),
            FOREIGN KEY(representative_event_id,representative_event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_resolution(
            resolution_id TEXT PRIMARY KEY,
            resolution_contract_version TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL,
            canonical_event_id TEXT NOT NULL,
            canonical_version INTEGER NOT NULL,
            resolution_type TEXT NOT NULL CHECK(
                resolution_type IN ('CANONICAL','EXACT_DUPLICATE')
            ),
            resolution_basis_json TEXT NOT NULL,
            resolution_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(event_id,event_version),
            UNIQUE(canonical_event_id,canonical_version,event_id),
            FOREIGN KEY(event_id,event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT,
            FOREIGN KEY(canonical_event_id,canonical_version)
                REFERENCES event_evidence_canonical_group(
                    canonical_event_id,canonical_version
                )
                ON DELETE RESTRICT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_quality_assessment(
            assessment_id TEXT PRIMARY KEY,
            quality_contract_version TEXT NOT NULL,
            assessment_scope TEXT NOT NULL CHECK(
                assessment_scope IN ('REFERENCE','HISTORICAL_EVALUATION')
            ),
            assessment_as_of TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL,
            event_hash TEXT NOT NULL,
            source_bundle_hash TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_hash TEXT NOT NULL,
            relevance_id TEXT NOT NULL,
            relevance_hash TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            rights_policy_bundle_hash TEXT NOT NULL,
            canonical_event_id TEXT,
            canonical_version INTEGER,
            canonical_hash TEXT,
            resolution_hash TEXT,
            rights_state TEXT NOT NULL,
            integrity_state TEXT NOT NULL,
            temporal_state TEXT NOT NULL,
            relevance_state TEXT NOT NULL,
            resolution_state TEXT NOT NULL,
            revision_state TEXT NOT NULL,
            corroboration_state TEXT NOT NULL,
            source_count INTEGER NOT NULL CHECK(source_count >= 0),
            distinct_source_origin_count INTEGER NOT NULL CHECK(
                distinct_source_origin_count >= 0
            ),
            quality_state TEXT NOT NULL CHECK(
                quality_state IN ('USABLE','LIMITED','INSUFFICIENT','BLOCKED')
            ),
            blocking_reasons_json TEXT NOT NULL,
            insufficient_reasons_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            quality_json TEXT NOT NULL,
            quality_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(event_id,event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT,
            FOREIGN KEY(entity_id)
                REFERENCES event_evidence_entity(entity_id)
                ON DELETE RESTRICT,
            FOREIGN KEY(relevance_id)
                REFERENCES event_evidence_entity_relevance(relevance_id)
                ON DELETE RESTRICT,
            FOREIGN KEY(canonical_event_id,canonical_version)
                REFERENCES event_evidence_canonical_group(
                    canonical_event_id,canonical_version
                )
                ON DELETE RESTRICT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_evaluation_protocol(
            protocol_id TEXT PRIMARY KEY,
            protocol_contract_version TEXT NOT NULL,
            control_method TEXT NOT NULL CHECK(
                control_method IN ('NONE','EXPLICIT_MATCH_SET')
            ),
            control_approved INTEGER NOT NULL CHECK(control_approved IN (0,1)),
            observation_windows_json TEXT NOT NULL,
            reference_price_rule TEXT NOT NULL,
            benchmark_rule TEXT NOT NULL,
            statistical_test_status TEXT NOT NULL,
            minimum_control_count INTEGER,
            protocol_json TEXT NOT NULL,
            protocol_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_outcome_observation(
            observation_id TEXT PRIMARY KEY,
            evaluation_contract_version TEXT NOT NULL,
            outcome_contract_version TEXT NOT NULL,
            protocol_id TEXT NOT NULL,
            protocol_hash TEXT NOT NULL,
            quality_assessment_id TEXT NOT NULL,
            quality_hash TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_version INTEGER NOT NULL,
            entity_id TEXT NOT NULL,
            entity_hash TEXT NOT NULL,
            canonical_event_id TEXT,
            sample_identity TEXT NOT NULL,
            assessment_as_of TEXT NOT NULL,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            reference_price_rule TEXT NOT NULL,
            benchmark_rule TEXT NOT NULL,
            sector_benchmark_status TEXT NOT NULL,
            market_evidence_hash TEXT NOT NULL,
            evaluation_status TEXT NOT NULL,
            evaluation_reason TEXT,
            reference_trading_day TEXT,
            reference_close REAL,
            benchmark_reference_close REAL,
            price_basis TEXT NOT NULL,
            adjustment_basis TEXT NOT NULL,
            horizons_json TEXT NOT NULL,
            observation_json TEXT NOT NULL,
            observation_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(protocol_id)
                REFERENCES event_evidence_evaluation_protocol(protocol_id)
                ON DELETE RESTRICT,
            FOREIGN KEY(quality_assessment_id)
                REFERENCES event_evidence_quality_assessment(assessment_id)
                ON DELETE RESTRICT,
            FOREIGN KEY(event_id,event_version)
                REFERENCES event_evidence_record(event_id,event_version)
                ON DELETE RESTRICT,
            FOREIGN KEY(entity_id)
                REFERENCES event_evidence_entity(entity_id)
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_control_match(
            control_id TEXT PRIMARY KEY,
            evaluation_contract_version TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            protocol_id TEXT NOT NULL,
            protocol_hash TEXT NOT NULL,
            control_as_of_date TEXT NOT NULL,
            contamination_state TEXT NOT NULL CHECK(
                contamination_state IN ('CLEAN','CONTAMINATED')
            ),
            contaminated_by_json TEXT NOT NULL,
            market_evidence_hash TEXT NOT NULL,
            evaluation_status TEXT NOT NULL,
            reference_trading_day TEXT,
            reference_close REAL,
            benchmark_reference_close REAL,
            horizons_json TEXT NOT NULL,
            control_json TEXT NOT NULL,
            control_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(observation_id)
                REFERENCES event_evidence_outcome_observation(observation_id)
                ON DELETE RESTRICT,
            FOREIGN KEY(protocol_id)
                REFERENCES event_evidence_evaluation_protocol(protocol_id)
                ON DELETE RESTRICT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_evidence_evaluation_report(
            report_id TEXT PRIMARY KEY,
            report_contract_version TEXT NOT NULL,
            protocol_id TEXT NOT NULL,
            protocol_hash TEXT NOT NULL,
            report_status TEXT NOT NULL,
            sample_count INTEGER NOT NULL CHECK(sample_count >= 0),
            sample_sufficiency TEXT NOT NULL,
            statistical_test_status TEXT NOT NULL,
            observation_bundle_json TEXT NOT NULL,
            report_json TEXT NOT NULL,
            report_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(protocol_id)
                REFERENCES event_evidence_evaluation_protocol(protocol_id)
                ON DELETE RESTRICT
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_evidence_source_kind_available
        ON event_evidence_source_ref(source_kind,available_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_evidence_record_available
        ON event_evidence_record(event_type,available_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_evidence_record_source_ref
        ON event_evidence_record_source(source_ref_id,event_id,event_version)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_entity_key
        ON event_evidence_entity(entity_type,entity_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_relevance_event
        ON event_evidence_entity_relevance(event_id,event_version,relevance_state)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_resolution_group
        ON event_evidence_resolution(canonical_event_id,canonical_version)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_quality_event_asof
        ON event_evidence_quality_assessment(
            event_id,entity_id,assessment_as_of
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_quality_state
        ON event_evidence_quality_assessment(
            assessment_scope,quality_state,assessment_as_of
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_outcome_sample
        ON event_evidence_outcome_observation(
            protocol_id,sample_identity,assessment_as_of
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_control_observation
        ON event_evidence_control_match(
            observation_id,control_as_of_date
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_report_protocol
        ON event_evidence_evaluation_report(protocol_id,created_at)
        """
    )

    for name, table in (
        ("trg_event_policy_immutable_update", "event_evidence_policy_snapshot"),
        ("trg_event_policy_immutable_delete", "event_evidence_policy_snapshot"),
        ("trg_event_source_immutable_update", "event_evidence_source_ref"),
        ("trg_event_source_immutable_delete", "event_evidence_source_ref"),
        ("trg_event_record_immutable_update", "event_evidence_record"),
        ("trg_event_record_immutable_delete", "event_evidence_record"),
        ("trg_event_record_source_immutable_update", "event_evidence_record_source"),
        ("trg_event_record_source_immutable_delete", "event_evidence_record_source"),
        ("trg_event_entity_immutable_update", "event_evidence_entity"),
        ("trg_event_entity_immutable_delete", "event_evidence_entity"),
        ("trg_event_relevance_immutable_update", "event_evidence_entity_relevance"),
        ("trg_event_relevance_immutable_delete", "event_evidence_entity_relevance"),
        ("trg_event_canonical_immutable_update", "event_evidence_canonical_group"),
        ("trg_event_canonical_immutable_delete", "event_evidence_canonical_group"),
        ("trg_event_resolution_immutable_update", "event_evidence_resolution"),
        ("trg_event_resolution_immutable_delete", "event_evidence_resolution"),
        (
            "trg_event_quality_immutable_update",
            "event_evidence_quality_assessment",
        ),
        (
            "trg_event_quality_immutable_delete",
            "event_evidence_quality_assessment",
        ),
        (
            "trg_event_eval_protocol_immutable_update",
            "event_evidence_evaluation_protocol",
        ),
        (
            "trg_event_eval_protocol_immutable_delete",
            "event_evidence_evaluation_protocol",
        ),
        (
            "trg_event_outcome_immutable_update",
            "event_evidence_outcome_observation",
        ),
        (
            "trg_event_outcome_immutable_delete",
            "event_evidence_outcome_observation",
        ),
        (
            "trg_event_control_immutable_update",
            "event_evidence_control_match",
        ),
        (
            "trg_event_control_immutable_delete",
            "event_evidence_control_match",
        ),
        (
            "trg_event_eval_report_immutable_update",
            "event_evidence_evaluation_report",
        ),
        (
            "trg_event_eval_report_immutable_delete",
            "event_evidence_evaluation_report",
        ),
    ):
        operation = "UPDATE" if name.endswith("update") else "DELETE"
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {name}
            BEFORE {operation} ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is immutable');
            END
            """
        )

    for table in TABLE_COLUMNS:
        _require_columns(conn, table)


def migrate_event_evidence_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_simulation_db(path)
    conn = sqlite3.connect(path, timeout=20.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_meta(conn)
        _create_tables(conn)

        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("VN-P6-S1 Event Evidence integrity_check 실패")
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise DataToolError(
                f"VN-P6-S1 Event Evidence FK 검증 실패: {len(foreign_keys)}건"
            )

        counts = {
            "policy_snapshot_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_policy_snapshot"
                ).fetchone()[0]
            ),
            "source_ref_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_source_ref"
                ).fetchone()[0]
            ),
            "event_evidence_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_record"
                ).fetchone()[0]
            ),
            "entity_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_entity"
                ).fetchone()[0]
            ),
            "relevance_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_entity_relevance"
                ).fetchone()[0]
            ),
            "canonical_group_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_canonical_group"
                ).fetchone()[0]
            ),
            "resolution_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_resolution"
                ).fetchone()[0]
            ),
            "quality_assessment_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_quality_assessment"
                ).fetchone()[0]
            ),
            "evaluation_protocol_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_evaluation_protocol"
                ).fetchone()[0]
            ),
            "outcome_observation_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_outcome_observation"
                ).fetchone()[0]
            ),
            "control_match_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_control_match"
                ).fetchone()[0]
            ),
            "evaluation_report_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM event_evidence_evaluation_report"
                ).fetchone()[0]
            ),
        }
        conn.commit()
        return {
            "schema_version": EVENT_EVIDENCE_STORE_SCHEMA_VERSION,
            "event_record_version": EVENT_EVIDENCE_RECORD_VERSION,
            "hash_contract_version": EVENT_EVIDENCE_HASH_CONTRACT_VERSION,
            **counts,
            "historical_backfill_performed": False,
            "news_backfill_performed": False,
            "dart_eventrisk_backfill_performed": False,
            "external_network_requests": 0,
            "real_corpus_evaluation_performed": False,
            "source_state": source_state,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_event_evidence(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_event_evidence_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VN-P6-S1 Event Evidence immutable store schema를 생성합니다. "
            "기존 NEWS.1/DART 자료를 backfill하거나 외부 API를 호출하지 않습니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_event_evidence(simulation_db=args.simulation_db)
        print("VN-P6-S1 EVENT EVIDENCE MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
