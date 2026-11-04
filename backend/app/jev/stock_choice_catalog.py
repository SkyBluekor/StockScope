"""JEV-B3 Choice-only result store: separate from TypeSafe V4 Noul reviews.

An explicit migration owns schema creation. Ordinary GETs never create or
modify database objects. A UNIQUE identity and BEGIN IMMEDIATE reserve at
most one *application request*; provider-side exactly-once billing is not
claimed. In-flight failures are unknown-billing and never automatically retried.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


SCHEMA = "JEV_STOCK_CHOICE_STORAGE_V1"
TABLE = "jev_stock_choice_review"
STATUSES = frozenset({"RESERVED", "VALID", "UNKNOWN_BILLING"})


class StockChoiceStorageError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if not Path(path).is_file():
        raise StockChoiceStorageError("CHOICE_DB_NOT_FOUND")
    try:
        db = sqlite3.connect(
            Path(path).resolve().as_uri() + "?mode=ro" if readonly else str(path),
            uri=readonly, timeout=15,
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        else:
            db.execute("PRAGMA foreign_keys=ON")
        return db
    except sqlite3.Error as exc:
        raise StockChoiceStorageError("CHOICE_DB_UNAVAILABLE") from exc


def migrate_stock_choice(db_path: Path) -> dict[str, Any]:
    """Idempotent, explicitly requested migration; never auto-run on GET."""
    db = _connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        required = {"prospective_capture_run", "prospective_recommendation_sample"}
        present = {str(r["name"]) for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if not required.issubset(present):
            raise StockChoiceStorageError("CHOICE_PROSPECTIVE_SCHEMA_REQUIRED")
        db.execute("""CREATE TABLE IF NOT EXISTS jev_stock_choice_schema_meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        version = db.execute(
            "SELECT value FROM jev_stock_choice_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if version is not None and version["value"] != SCHEMA:
            raise StockChoiceStorageError("CHOICE_SCHEMA_UNSUPPORTED")
        db.execute("""
            INSERT OR IGNORE INTO jev_stock_choice_schema_meta(key,value)
            VALUES('schema_version',?)
        """, (SCHEMA,))
        db.execute("""CREATE TABLE IF NOT EXISTS jev_stock_choice_review (
            id TEXT PRIMARY KEY,
            review_identity TEXT NOT NULL UNIQUE,
            canonical_capture_id TEXT NOT NULL,
            sample_index INTEGER NOT NULL,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            question_hash TEXT NOT NULL,
            model_requested TEXT NOT NULL,
            model_returned TEXT,
            request_body_sha256 TEXT NOT NULL,
            approval_digest TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK(status IN (
                'RESERVED','VALID','UNKNOWN_BILLING')),
            priority_choice TEXT,
            confidence REAL,
            usage_json TEXT,
            cost_usd REAL,
            cost_unknown INTEGER NOT NULL DEFAULT 1,
            error_code TEXT,
            cost_basis_ref TEXT,
            CHECK ((status = 'VALID' AND priority_choice IS NOT NULL)
              OR (status <> 'VALID' AND priority_choice IS NULL))
        )""")
        existing_cols = {r["name"] for r in db.execute(
            "PRAGMA table_info(jev_stock_choice_review)"
        )}
        if "cost_basis_ref" not in existing_cols:
            db.execute("ALTER TABLE jev_stock_choice_review ADD COLUMN cost_basis_ref TEXT")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_jev_stock_choice_capture
            ON jev_stock_choice_review(canonical_capture_id,sample_index)""")
        db.commit()
        return {"schema_version": SCHEMA, "status": "READY", "writes_to_scanner": 0}
    except (sqlite3.Error, StockChoiceStorageError) as exc:
        db.rollback()
        if isinstance(exc, StockChoiceStorageError):
            raise
        raise StockChoiceStorageError("CHOICE_MIGRATION_FAILED") from exc
    finally:
        db.close()


class StockChoiceCatalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @staticmethod
    def _ready(db: sqlite3.Connection) -> None:
        found = {r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if TABLE not in found or "jev_stock_choice_schema_meta" not in found:
            raise StockChoiceStorageError("CHOICE_MIGRATION_REQUIRED")
        version = db.execute(
            "SELECT value FROM jev_stock_choice_schema_meta WHERE key='schema_version'"
        ).fetchone()
        if version is None or version["value"] != SCHEMA:
            raise StockChoiceStorageError("CHOICE_SCHEMA_UNSUPPORTED")
        columns = {r["name"] for r in db.execute(
            "PRAGMA table_info(jev_stock_choice_review)"
        )}
        if "cost_basis_ref" not in columns:
            raise StockChoiceStorageError("CHOICE_MIGRATION_REQUIRED")

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        result = {key: row[key] for key in (
            "id", "review_identity", "canonical_capture_id", "sample_index",
            "market", "ticker", "snapshot_hash", "input_hash", "question_hash",
            "model_requested", "model_returned", "request_body_sha256",
            "approved_at", "requested_at", "completed_at", "status",
            "priority_choice", "confidence", "cost_usd", "error_code",
            "cost_basis_ref",
        )}
        result["cost_unknown"] = bool(row["cost_unknown"])
        result["usage"] = (json.loads(row["usage_json"])
                           if row["usage_json"] else None)
        # No approval bearer token, private review text, or raw model response.
        return result

    def mark_pending_unknown_after_restart(self) -> int:
        """At startup a RESERVED row may have reached TypeSafe. Never retry it."""
        db = _connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            self._ready(db)
            changed = db.execute("""
                UPDATE jev_stock_choice_review SET status='UNKNOWN_BILLING',
                    completed_at=?,error_code='CHOICE_PROCESS_RESTART_UNKNOWN_BILLING'
                WHERE status='RESERVED'
            """, (_now(),)).rowcount
            db.commit()
            return changed
        except (sqlite3.Error, StockChoiceStorageError) as exc:
            if db.in_transaction:
                db.rollback()
            if isinstance(exc, StockChoiceStorageError):
                raise
            raise StockChoiceStorageError("CHOICE_RESTART_RECONCILE_FAILED") from exc
        finally:
            db.close()

    def get_for_candidate(
        self, *, capture_id: str, sample_index: int, snapshot_hash: str,
        market: str, ticker: str,
    ) -> list[dict[str, Any]]:
        db = _connect(self.db_path, readonly=True)
        try:
            self._ready(db)
            rows = db.execute("""
                SELECT * FROM jev_stock_choice_review
                WHERE canonical_capture_id=? AND sample_index=?
                AND snapshot_hash=? AND market=? AND ticker=?
                ORDER BY requested_at DESC LIMIT 5
            """, (capture_id, sample_index, snapshot_hash, market, ticker)).fetchall()
            return [self._public(x) for x in rows]
        except sqlite3.Error as exc:
            raise StockChoiceStorageError("CHOICE_QUERY_FAILED") from exc
        finally:
            db.close()

    def reserve(self, *, review_identity: str, candidate: dict[str, Any],
                input_hash: str, question_hash: str, model_requested: str,
                request_body_sha256: str, approval_digest: str) -> tuple[dict[str, Any], bool]:
        db = _connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            self._ready(db)
            row = db.execute(
                "SELECT * FROM jev_stock_choice_review WHERE review_identity=?",
                (review_identity,),
            ).fetchone()
            if row is not None:
                db.rollback()
                return self._public(row), False
            db.execute("""INSERT INTO jev_stock_choice_review(
                id,review_identity,canonical_capture_id,sample_index,market,ticker,
                snapshot_hash,input_hash,question_hash,model_requested,
                request_body_sha256,approval_digest,approved_at,requested_at,status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid4()), review_identity, candidate["capture_id"],
                 candidate["sample_index"], candidate["market"], candidate["ticker"],
                 candidate["snapshot_hash"], input_hash, question_hash, model_requested,
                 request_body_sha256, approval_digest, _now(), _now(), "RESERVED"))
            db.commit()
            with _connect(self.db_path, readonly=True) as reader:
                saved = reader.execute(
                    "SELECT * FROM jev_stock_choice_review WHERE review_identity=?",
                    (review_identity,),
                ).fetchone()
                return self._public(saved), True
        except (sqlite3.Error, StockChoiceStorageError) as exc:
            if db.in_transaction:
                db.rollback()
            if isinstance(exc, StockChoiceStorageError):
                raise
            raise StockChoiceStorageError("CHOICE_RESERVATION_FAILED") from exc
        finally:
            db.close()

    def finish(self, *, review_identity: str, result: dict[str, Any] | None,
               error_code: str | None = None, cost_estimate_usd: float | None = None,
               cost_basis_ref: str | None = None) -> dict[str, Any]:
        db = _connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            self._ready(db)
            row = db.execute(
                "SELECT * FROM jev_stock_choice_review WHERE review_identity=?",
                (review_identity,),
            ).fetchone()
            if row is None or row["status"] != "RESERVED":
                raise StockChoiceStorageError("CHOICE_RESERVATION_NOT_PENDING")
            if result is None:
                db.execute("""UPDATE jev_stock_choice_review
                    SET status='UNKNOWN_BILLING',completed_at=?,error_code=?
                    WHERE review_identity=? AND status='RESERVED'""",
                    (_now(), error_code or "CHOICE_RESULT_UNCERTAIN", review_identity))
            else:
                if result.get("choice") is None or result.get("model") is None:
                    raise StockChoiceStorageError("CHOICE_RESULT_INVALID")
                db.execute("""UPDATE jev_stock_choice_review SET
                    status='VALID',completed_at=?,priority_choice=?,confidence=?,
                    model_returned=?,usage_json=?,cost_unknown=?,cost_usd=?,
                    cost_basis_ref=?
                    WHERE review_identity=? AND status='RESERVED'""",
                    (_now(), result["choice"], result["confidence"],
                     result["model"], json.dumps(result["usage"], sort_keys=True),
                     0 if cost_estimate_usd is not None and cost_basis_ref else 1,
                     cost_estimate_usd, cost_basis_ref, review_identity))
            db.commit()
            with _connect(self.db_path, readonly=True) as reader:
                saved = reader.execute(
                    "SELECT * FROM jev_stock_choice_review WHERE review_identity=?",
                    (review_identity,),
                ).fetchone()
                return self._public(saved)
        except (sqlite3.Error, StockChoiceStorageError) as exc:
            if db.in_transaction:
                db.rollback()
            if isinstance(exc, StockChoiceStorageError):
                raise
            raise StockChoiceStorageError("CHOICE_RESULT_SAVE_FAILED") from exc
        finally:
            db.close()
