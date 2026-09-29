from __future__ import annotations

from pathlib import Path
from typing import Any

from app.macro.store import (
    MACRO_META_EXPECTED,
    MACRO_STORE_SCHEMA_VERSION,
    MACRO_STORE_TABLES,
)
from tools.data.common import DataToolError, sqlite_readonly


MACRO_BACKUP_EXTENSION = "macro_store_v1"
MACRO_BACKUP_TABLES = tuple(MACRO_STORE_TABLES)


def _absent_state() -> dict[str, Any]:
    return {
        "schema_version": MACRO_STORE_SCHEMA_VERSION,
        "present": False,
        "tables": [],
        "restorable": False,
        "contract_versions": dict(MACRO_META_EXPECTED),
        "counts": {
            "series_contract_count": 0,
            "collection_run_count": 0,
            "observation_revision_count": 0,
            "published_observation_count": 0,
            "prepared_range_count": 0,
            "research_protocol_count": 0,
        },
    }


def inspect_macro_store(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _absent_state()
    db = Path(path)
    if not db.is_file():
        return _absent_state()

    with sqlite_readonly(db) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise DataToolError("Macro Store integrity_check에 실패했습니다.")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise DataToolError("Macro Store foreign_key_check에 실패했습니다.")

        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = set(MACRO_BACKUP_TABLES)
        present = expected & tables
        if not present:
            return _absent_state()
        if present != expected:
            missing = sorted(expected - present)
            raise DataToolError(
                "Macro Store가 부분 migration 상태입니다: "
                + ", ".join(missing)
            )

        meta = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                "SELECT key,value FROM macro_schema_meta"
            ).fetchall()
        }
        for key, expected_value in MACRO_META_EXPECTED.items():
            if meta.get(key) != expected_value:
                raise DataToolError(
                    "Macro Store contract version 불일치: "
                    f"{key}={meta.get(key)!r}, expected={expected_value!r}"
                )

        counts = {
            "series_contract_count": int(
                conn.execute("SELECT COUNT(*) FROM macro_series_contract").fetchone()[0]
            ),
            "collection_run_count": int(
                conn.execute("SELECT COUNT(*) FROM macro_collection_run").fetchone()[0]
            ),
            "observation_revision_count": int(
                conn.execute("SELECT COUNT(*) FROM macro_observation_revision").fetchone()[0]
            ),
            "published_observation_count": int(
                conn.execute(
                    "SELECT COUNT(*) FROM macro_observation_revision WHERE published=1"
                ).fetchone()[0]
            ),
            "prepared_range_count": int(
                conn.execute("SELECT COUNT(*) FROM macro_prepared_range").fetchone()[0]
            ),
            "research_protocol_count": int(
                conn.execute("SELECT COUNT(*) FROM macro_research_protocol").fetchone()[0]
            ),
        }

    return {
        "schema_version": MACRO_STORE_SCHEMA_VERSION,
        "present": True,
        "tables": list(MACRO_BACKUP_TABLES),
        "restorable": True,
        "contract_versions": dict(MACRO_META_EXPECTED),
        "counts": counts,
    }


def validate_macro_db(path: Path) -> dict[str, Any]:
    state = inspect_macro_store(path)
    if not state.get("present") or not state.get("restorable"):
        raise DataToolError("Macro Store가 초기화되지 않았거나 복원 가능 상태가 아닙니다.")
    return state


def validate_macro_state(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    label: str,
) -> None:
    for key in (
        "schema_version",
        "present",
        "tables",
        "restorable",
        "contract_versions",
        "counts",
    ):
        if expected.get(key) != actual.get(key):
            raise DataToolError(
                f"Macro Store {label} metadata가 실제 상태와 다릅니다: {key}"
            )
