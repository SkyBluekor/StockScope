from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.simulation.strategy_evidence import STRATEGY_EVALUATION_ARTIFACT_VERSION
from app.simulation.strategy_governance import (
    STRATEGY_BOOTSTRAP_DEFINITION_VERSION,
    STRATEGY_BOOTSTRAP_SOURCE,
    STRATEGY_FINGERPRINT_CONTRACT_VERSION,
    STRATEGY_GOVERNANCE_SCHEMA_VERSION,
    current_strategy_definitions,
    current_strategy_set_fingerprint,
)
from tools.data.common import DataToolError, simulation_db_path, sqlite_readonly


PROSPECTIVE_REQUIRED_TABLES = frozenset(
    {
        "prospective_schema_meta",
        "prospective_capture_run",
        "prospective_recommendation_sample",
        "prospective_evaluation_protocol",
        "prospective_evaluation_run",
        "prospective_evaluation_unit",
        "prospective_evaluation_report",
    }
)

STRATEGY_GOVERNANCE_TABLES = frozenset(
    {
        "strategy_governance_schema_meta",
        "strategy_registry_version",
        "strategy_evaluation_artifact",
    }
)

TABLE_COLUMNS: dict[str, set[str]] = {
    "strategy_registry_version": {
        "strategy_version_id",
        "strategy_key",
        "definition_version",
        "definition_hash",
        "fingerprint_contract_version",
        "implementation_key",
        "operational_status",
        "validation_status",
        "source",
        "definition_json",
        "created_at",
        "retired_at",
    },
    "strategy_evaluation_artifact": {
        "id",
        "strategy_version_id",
        "strategy_key",
        "artifact_version",
        "source_kind",
        "source_report_id",
        "source_report_version",
        "source_parent_id",
        "source_set_hash",
        "source_summary_hash",
        "evidence_state",
        "evidence_json",
        "limitations_json",
        "source_contract_json",
        "artifact_hash",
        "created_at",
    },
}


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            f"{table} schema가 VN-P5-S1과 호환되지 않습니다: "
            + ", ".join(missing)
        )


def _inspect_simulation_db(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise DataToolError(f"Simulation DB를 찾을 수 없습니다: {path}")

    with sqlite_readonly(path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Simulation DB integrity_check에 실패했습니다.")

        names = _table_names(conn)
        missing = sorted(PROSPECTIVE_REQUIRED_TABLES - names)
        if missing:
            raise DataToolError(
                "VN-P5-S1 선행 VN-P2-S2 prospective schema가 없습니다: "
                + ", ".join(missing)
            )

        row = conn.execute(
            """
            SELECT value FROM prospective_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None or str(row[0]) != PROSPECTIVE_SCHEMA_VERSION:
            raise DataToolError(
                "VN-P2-S2 prospective migration/version이 호환되지 않습니다."
            )

        return {
            "prospective_schema_version": str(row[0]),
            "prospective_capture_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM prospective_capture_run"
                ).fetchone()[0]
            ),
            "prospective_evaluation_report_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM prospective_evaluation_report"
                ).fetchone()[0]
            ),
        }


def _ensure_meta(
    conn: sqlite3.Connection,
    *,
    strategy_set_fingerprint: str,
) -> bool:
    names = _table_names(conn)
    newly_created = "strategy_governance_schema_meta" not in names
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_governance_schema_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    values = {
        "schema_version": STRATEGY_GOVERNANCE_SCHEMA_VERSION,
        "fingerprint_contract_version": STRATEGY_FINGERPRINT_CONTRACT_VERSION,
        "bootstrap_definition_version": STRATEGY_BOOTSTRAP_DEFINITION_VERSION,
        "bootstrap_source": STRATEGY_BOOTSTRAP_SOURCE,
        "bootstrap_strategy_set_fingerprint": strategy_set_fingerprint,
        "evaluation_artifact_version": STRATEGY_EVALUATION_ARTIFACT_VERSION,
    }
    for key, expected in values.items():
        row = conn.execute(
            """
            SELECT value FROM strategy_governance_schema_meta
            WHERE key=?
            """,
            (key,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO strategy_governance_schema_meta(key,value)
                VALUES(?,?)
                """,
                (key, expected),
            )
            continue
        actual = str(row[0])
        if actual != expected:
            if key == "bootstrap_strategy_set_fingerprint":
                raise DataToolError(
                    "현재 StrategyEngine 구현이 VN-P5-S1 bootstrap fingerprint와 "
                    "달라졌습니다. migration으로 새 운영 version을 자동 등록할 수 없습니다."
                )
            raise DataToolError(
                f"Strategy governance meta 불일치: {key}={actual}"
            )
    return newly_created


def _create_registry(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_registry_version(
            strategy_version_id TEXT PRIMARY KEY,
            strategy_key TEXT NOT NULL,
            definition_version TEXT NOT NULL,
            definition_hash TEXT NOT NULL,
            fingerprint_contract_version TEXT NOT NULL,
            implementation_key TEXT NOT NULL,
            operational_status TEXT NOT NULL CHECK(
                operational_status IN (
                    'CANDIDATE','OPERATING','ON_HOLD','DEMOTED'
                )
            ),
            validation_status TEXT NOT NULL CHECK(
                validation_status IN (
                    'UNVERIFIED','EVALUATING','VALIDATED',
                    'INSUFFICIENT_EVIDENCE','BLOCKED'
                )
            ),
            source TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            retired_at TEXT,
            UNIQUE(strategy_key,definition_hash)
        )
        """
    )
    _require_columns(conn, "strategy_registry_version")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_strategy_registry_key_status
        ON strategy_registry_version(strategy_key,operational_status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_registry_operating_key
        ON strategy_registry_version(strategy_key)
        WHERE operational_status='OPERATING'
        """
    )


def _create_evidence_artifacts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_evaluation_artifact(
            id TEXT PRIMARY KEY,
            strategy_version_id TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            artifact_version TEXT NOT NULL,
            source_kind TEXT NOT NULL CHECK(
                source_kind IN ('FEEDBACK_REPORT','PROSPECTIVE_REPORT')
            ),
            source_report_id TEXT NOT NULL,
            source_report_version TEXT NOT NULL,
            source_parent_id TEXT NOT NULL,
            source_set_hash TEXT NOT NULL,
            source_summary_hash TEXT NOT NULL,
            evidence_state TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            source_contract_json TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(
                strategy_version_id,
                source_kind,
                source_report_id,
                source_set_hash
            ),
            FOREIGN KEY(strategy_version_id)
                REFERENCES strategy_registry_version(strategy_version_id)
                ON DELETE RESTRICT
        )
        """
    )
    _require_columns(conn, "strategy_evaluation_artifact")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_strategy_evidence_strategy_created
        ON strategy_evaluation_artifact(
            strategy_version_id,
            created_at DESC
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_strategy_evidence_source
        ON strategy_evaluation_artifact(
            source_kind,
            source_report_id
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_strategy_evidence_immutable_update
        BEFORE UPDATE ON strategy_evaluation_artifact
        BEGIN
            SELECT RAISE(
                ABORT,
                'strategy_evaluation_artifact is immutable'
            );
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_strategy_evidence_immutable_delete
        BEFORE DELETE ON strategy_evaluation_artifact
        BEGIN
            SELECT RAISE(
                ABORT,
                'strategy_evaluation_artifact is immutable'
            );
        END
        """
    )


def _bootstrap_registry(conn: sqlite3.Connection) -> tuple[int, int]:
    definitions = current_strategy_definitions()
    bootstrap_rows = conn.execute(
        """
        SELECT * FROM strategy_registry_version
        WHERE source=? AND definition_version=?
        """,
        (STRATEGY_BOOTSTRAP_SOURCE, STRATEGY_BOOTSTRAP_DEFINITION_VERSION),
    ).fetchall()

    if not bootstrap_rows:
        created_at = _now_text()
        for item in definitions:
            conn.execute(
                """
                INSERT INTO strategy_registry_version(
                    strategy_version_id,strategy_key,definition_version,
                    definition_hash,fingerprint_contract_version,
                    implementation_key,operational_status,
                    validation_status,source,definition_json,
                    created_at,retired_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.strategy_version_id,
                    item.strategy_key,
                    item.definition_version,
                    item.definition_hash,
                    item.fingerprint_contract_version,
                    item.implementation_key,
                    item.operational_status,
                    item.validation_status,
                    item.source,
                    json.dumps(
                        item.definition,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    created_at,
                    None,
                ),
            )
        return len(definitions), 0

    by_key = {str(row["strategy_key"]): row for row in bootstrap_rows}
    expected_keys = {item.strategy_key for item in definitions}
    if set(by_key) != expected_keys:
        raise DataToolError(
            "기존 VN-P5-S1 bootstrap registry의 전략 집합이 현재 10전략과 다릅니다."
        )

    for item in definitions:
        row = by_key[item.strategy_key]
        immutable_pairs = {
            "strategy_version_id": item.strategy_version_id,
            "definition_hash": item.definition_hash,
            "fingerprint_contract_version": item.fingerprint_contract_version,
            "implementation_key": item.implementation_key,
            "source": item.source,
        }
        for column, expected in immutable_pairs.items():
            if str(row[column]) != str(expected):
                raise DataToolError(
                    "현재 StrategyEngine 구현 또는 bootstrap registry가 변경되었습니다: "
                    f"{item.strategy_key}.{column}"
                )
        if str(row["validation_status"]) == "VALIDATED":
            # Validation may legitimately become VALIDATED later, but the migration
            # itself must never be the action that creates that claim.
            continue

    return 0, len(definitions)


def migrate_strategy_governance_store(path: Path) -> dict[str, object]:
    path = Path(path)
    source_state = _inspect_simulation_db(path)
    definitions = current_strategy_definitions()
    strategy_set_fingerprint = current_strategy_set_fingerprint()

    conn = sqlite3.connect(path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")

        _ensure_meta(
            conn,
            strategy_set_fingerprint=strategy_set_fingerprint,
        )
        _create_registry(conn)
        _create_evidence_artifacts(conn)
        inserted, verified = _bootstrap_registry(conn)

        counts = {
            str(row["operational_status"]): int(row["count"])
            for row in conn.execute(
                """
                SELECT operational_status,COUNT(*) AS count
                FROM strategy_registry_version
                GROUP BY operational_status
                """
            ).fetchall()
        }
        no_trade_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM strategy_registry_version
                WHERE strategy_key='no_trade'
                """
            ).fetchone()[0]
        )
        if no_trade_count:
            raise DataToolError(
                "NO_TRADE는 Strategy Pool Registry에 포함할 수 없습니다."
            )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise DataToolError(
                f"VN-P5-S1 strategy registry FK 검증 실패: {len(fk)}건"
            )

        conn.commit()
        return {
            "schema_version": STRATEGY_GOVERNANCE_SCHEMA_VERSION,
            "fingerprint_contract_version": STRATEGY_FINGERPRINT_CONTRACT_VERSION,
            "bootstrap_definition_version": STRATEGY_BOOTSTRAP_DEFINITION_VERSION,
            "bootstrap_source": STRATEGY_BOOTSTRAP_SOURCE,
            "strategy_set_fingerprint": strategy_set_fingerprint,
            "strategy_count": len(definitions),
            "inserted_strategy_count": inserted,
            "verified_strategy_count": verified,
            "operational_status_counts": counts,
            "no_trade_registered": False,
            "performance_validation_backfill_performed": False,
            "production_selection_policy_changed": False,
            "evaluation_artifact_version": STRATEGY_EVALUATION_ARTIFACT_VERSION,
            "evaluation_artifact_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM strategy_evaluation_artifact"
                ).fetchone()[0]
            ),
            "source_state": source_state,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_strategy_governance(
    *,
    simulation_db: Path | None = None,
) -> dict[str, object]:
    return migrate_strategy_governance_store(
        Path(simulation_db or simulation_db_path())
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VN-P5-S1 Strategy Governance Registry schema를 생성하고 "
            "현재 10전략을 OPERATING/UNVERIFIED bootstrap으로 등록합니다. "
            "NO_TRADE와 성능 검증 완료 상태는 자동 등록하지 않습니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = migrate_strategy_governance(
            simulation_db=args.simulation_db,
        )
        print("VN-P5-S1 STRATEGY GOVERNANCE MIGRATION PASS")
        print(result)
        return 0
    except (DataToolError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
