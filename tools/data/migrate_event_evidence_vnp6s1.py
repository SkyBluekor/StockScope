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

from app.event_evidence.models import (
    REVISION_IDENTITY_CONTRACT_VERSION,
    SOURCE_REF_CONTRACT_VERSION,
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

    for name, table in (
        ("trg_event_policy_immutable_update", "event_evidence_policy_snapshot"),
        ("trg_event_policy_immutable_delete", "event_evidence_policy_snapshot"),
        ("trg_event_source_immutable_update", "event_evidence_source_ref"),
        ("trg_event_source_immutable_delete", "event_evidence_source_ref"),
        ("trg_event_record_immutable_update", "event_evidence_record"),
        ("trg_event_record_immutable_delete", "event_evidence_record"),
        ("trg_event_record_source_immutable_update", "event_evidence_record_source"),
        ("trg_event_record_source_immutable_delete", "event_evidence_record_source"),
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
