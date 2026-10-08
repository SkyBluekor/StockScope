from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from app.prospective.models import canonical_json, digest_json


RANK_EVIDENCE_CONTRACT_VERSION = "SCANNER_RANK_EVIDENCE_V1"


def _unavailable(code: str) -> dict[str, Any]:
    return {"status": code, "stored": 0}


def persist_rank_evidence(
    *, db_path: Path, capture: dict[str, Any], evidence_rows: Any
) -> dict[str, Any]:
    """Store only actual ranking-time evidence for an already-frozen capture."""
    status = str(capture.get("status") or "")
    if status == "DUPLICATE":
        return _unavailable("DUPLICATE_USE_CANONICAL_IF_PRESENT")
    if status not in {"COMPLETE", "PARTIAL"}:
        return _unavailable("CAPTURE_NOT_FINALIZED")
    if not isinstance(evidence_rows, list) or not evidence_rows:
        return _unavailable("NOT_AVAILABLE_LEGACY")
    capture_id = str(capture.get("capture_id") or "")
    if not capture_id:
        return _unavailable("CAPTURE_NOT_FINALIZED")

    conn: sqlite3.Connection | None = None
    try:
        conn = ProspectiveCatalog(db_path).connect()
        conn.execute("BEGIN IMMEDIATE")
        available = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='scanner_rank_evidence'"
        ).fetchone()
        if available is None:
            return _unavailable("RANK_EVIDENCE_MIGRATION_REQUIRED")

        frozen = conn.execute(
            "SELECT status FROM prospective_capture_run WHERE id=?",
            (capture_id,),
        ).fetchone()
        if frozen is None or str(frozen["status"]) != status:
            return _unavailable("CAPTURE_IDENTITY_MISMATCH")
        samples = conn.execute(
            "SELECT sample_index,market,ticker,rank,strategy,snapshot_hash "
            "FROM prospective_recommendation_sample "
            "WHERE capture_run_id=? ORDER BY sample_index",
            (capture_id,),
        ).fetchall()
        if len(samples) != len(evidence_rows):
            return _unavailable("EVIDENCE_SAMPLE_COUNT_MISMATCH")

        new_rows = []
        for index, (sample, evidence) in enumerate(zip(samples, evidence_rows)):
            if not isinstance(evidence, dict) or int(sample["sample_index"]) != index:
                return _unavailable("EVIDENCE_INVALID")
            if (
                str(sample["market"]) != str(evidence.get("market") or "").upper()
                or str(sample["ticker"]) != str(evidence.get("code") or "").upper()
                or int(evidence.get("final_rank") or 0) != index + 1
                or (
                    sample["rank"] is not None
                    and int(sample["rank"]) != evidence.get("final_rank")
                )
                or str(sample["strategy"] or "") != str(evidence.get("strategy") or "")
                or evidence.get("contract_version") != RANK_EVIDENCE_CONTRACT_VERSION
            ):
                return _unavailable("EVIDENCE_SAMPLE_IDENTITY_MISMATCH")
            body = {
                **evidence,
                "scanner_version": capture.get("scanner_version"),
                "market_scope": capture.get("market_scope"),
                "requested_as_of": capture.get("requested_as_of"),
                "data_date": capture.get("actual_data_date"),
                "source_snapshot_hash": capture.get("source_snapshot_hash"),
                "sample_snapshot_hash": sample["snapshot_hash"],
            }
            new_rows.append((
                capture_id, index, RANK_EVIDENCE_CONTRACT_VERSION,
                canonical_json(body), digest_json(body),
                datetime.now(timezone.utc).isoformat(),
            ))

        stored = conn.execute(
            "SELECT sample_index,evidence_hash FROM scanner_rank_evidence "
            "WHERE capture_run_id=? ORDER BY sample_index",
            (capture_id,),
        ).fetchall()
        if stored:
            if len(stored) != len(new_rows) or any(
                int(existing["sample_index"]) != row[1]
                or str(existing["evidence_hash"]) != row[4]
                for existing, row in zip(stored, new_rows)
            ):
                return _unavailable("EVIDENCE_CONFLICT")
            return {"status": "REUSED", "stored": len(stored)}

        conn.executemany(
            "INSERT INTO scanner_rank_evidence("
            "capture_run_id,sample_index,contract_version,evidence_json,"
            "evidence_hash,created_at) VALUES(?,?,?,?,?,?)",
            new_rows,
        )
        conn.commit()
        return {"status": "STORED", "stored": len(new_rows)}
    except (ProspectiveCatalogError, sqlite3.Error, OSError, ValueError, TypeError):
        return _unavailable("RANK_EVIDENCE_STORE_UNAVAILABLE")
    finally:
        if conn is not None:
            conn.close()


def read_rank_evidence(
    *, db_path: Path, capture_id: str, sample_index: int
) -> dict[str, Any]:
    """Resolve an existing canonical record; never fabricate historical evidence."""
    conn: sqlite3.Connection | None = None
    try:
        conn = ProspectiveCatalog(db_path).connect()
        cap = conn.execute(
            "SELECT status,canonical_capture_id FROM prospective_capture_run "
            "WHERE id=?", (capture_id,),
        ).fetchone()
        if cap is None:
            return _unavailable("CAPTURE_NOT_FOUND")
        canonical = (
            str(cap["canonical_capture_id"])
            if cap["status"] == "DUPLICATE" and cap["canonical_capture_id"]
            else capture_id
        )
        row = conn.execute(
            "SELECT evidence_json,evidence_hash FROM scanner_rank_evidence "
            "WHERE capture_run_id=? AND sample_index=?",
            (canonical, sample_index),
        ).fetchone()
        if row is None:
            return _unavailable("NOT_AVAILABLE_LEGACY")
        evidence = json.loads(str(row["evidence_json"]))
        if digest_json(evidence) != row["evidence_hash"]:
            return _unavailable("EVIDENCE_HASH_MISMATCH")
        return {
            "status": "AVAILABLE",
            "capture_id": canonical,
            "sample_index": sample_index,
            "evidence_hash": row["evidence_hash"],
            "evidence": evidence,
        }
    except (ProspectiveCatalogError, sqlite3.Error, OSError, ValueError, TypeError):
        return _unavailable("RANK_EVIDENCE_STORE_UNAVAILABLE")
    finally:
        if conn is not None:
            conn.close()
