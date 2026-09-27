from __future__ import annotations

import json
import sqlite3
from typing import Any

INPUT_IDENTITY_SCHEMA_VERSION = "VN_P1_S1_INPUT_GENERATION_V1"
ANALYSIS_PROOF_VERSION = "VN_P1_S1_ANALYSIS_PROOF_V1"
VALIDATION_PROOF_VERSION = "VN_P1_S1_VALIDATION_PROOF_V1"
VALIDATION_INPUT_MANIFEST_VERSION = "VN_P1_S1_VALIDATION_INPUT_MANIFEST_V1"
META_TABLE = "input_identity_meta"
GENERATION_TABLE = "input_change_generation"
PROOF_TABLE = "analysis_input_proof"
VALIDATION_PROOF_TABLE = "historical_validation_input_proof"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def generation_schema_ready(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, META_TABLE) or not table_exists(conn, GENERATION_TABLE):
        return False
    row = conn.execute(
        f"SELECT value FROM {META_TABLE} WHERE key='schema_version' LIMIT 1"
    ).fetchone()
    return row is not None and str(row[0]) == INPUT_IDENTITY_SCHEMA_VERSION


def read_input_generation_token(
    conn: sqlite3.Connection,
    market: str,
    ticker: str,
) -> dict[str, Any] | None:
    """Read the persisted change generations used to prove input stability.

    This function is intentionally read-only. Missing migration metadata is not
    repaired here; callers must keep the resource UNVERIFIED until the explicit
    VN-P1-S1 migration is run.
    """
    clean_market = (market or "").strip().upper()
    clean_ticker = (ticker or "").strip().upper()
    if not generation_schema_ready(conn):
        return None

    rows = conn.execute(
        f"""
        SELECT scope,subject,generation
        FROM {GENERATION_TABLE}
        WHERE market=?
          AND (
            (scope='STOCK' AND subject=?)
            OR (scope='STOCK_STATUS' AND subject='*')
            OR (scope='INDEX' AND subject='*')
          )
        """,
        (clean_market, clean_ticker),
    ).fetchall()
    values = {(str(row[0]), str(row[1])): int(row[2]) for row in rows}
    keys = (
        ("STOCK", clean_ticker),
        ("STOCK_STATUS", "*"),
        ("INDEX", "*"),
    )
    if any(key not in values for key in keys):
        return None
    return {
        "schema_version": INPUT_IDENTITY_SCHEMA_VERSION,
        "stock_generation": values[("STOCK", clean_ticker)],
        "stock_status_generation": values[("STOCK_STATUS", "*")],
        "index_generation": values[("INDEX", "*")],
    }


def canonical_generation_token(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    if value.get("schema_version") != INPUT_IDENTITY_SCHEMA_VERSION:
        return None
    required = ("stock_generation", "stock_status_generation", "index_generation")
    try:
        normalized = {
            "schema_version": INPUT_IDENTITY_SCHEMA_VERSION,
            **{key: int(value[key]) for key in required},
        }
    except (KeyError, TypeError, ValueError):
        return None
    if any(normalized[key] < 1 for key in required):
        return None
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
