"""B4: local-only operator-authored stock observations, source binding and cost guard.

No third-party market facts are imported, transformed or transferred.
Original authorship is self-declared and *not* independently established.
The server will only construct first-party text for one immutable local
capture with an explicit authorship attestation. The provider model list
must be checked by an explicit action before a priced preview is available.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Callable

from .models import digest_json
from .stock_choice_execution import (
    StockChoiceExecutionError, TrustedChoiceInput,
)
from .stock_choice_catalog import StockChoiceStorageError


TABLE = "jev_stock_choice_authored_evidence_v1"
SCHEMA = "STOCKSCOPE_JEV_B4_AUTHORED_V1"
ORIGIN = "USER_ORIGINALLY_AUTHORED_SELF_ATTESTED"
RATE_USD_PER_MILLION_INPUT = 0.042
RATE_REFERENCE = "https://help.typesafe.ai/articles/5187202169-how-much-does-jev-cost"
RATE_VERIFIED_DATE = "2026-11-03"
# Client-side budget guard only, NOT a provider-enforced hard spending cap.
MAX_REQUEST_BYTES = 3500
MAX_ESTIMATED_INPUT_TOKENS = 12000   # conservative allowance, not actual tokenizer measurement
MAX_ESTIMATED_COST_USD = 0.001
MODEL_VERIFICATION_TTL_SECONDS = 3600
_INTENT = (
    "A user-authored qualitative hypothesis about the selected stored stock "
    "is being considered for a current, manual follow-up check. This text "
    "contains no externally sourced market prices or news."
)
_RISK = (
    "An unconfirmed observation must remain unconfirmed. Treat a follow-up "
    "review priority as informational, not as permission to buy or sell."
)
_FORBIDDEN = re.compile(
    r"https?://|www\.|(?:\d[\d,]*\s*(?:원|달러|usd|%|주|배))|"
    r"(?:krx|dart|kis|네이버\s*뉴스|공시\s*원문|기사\s*인용|"
    r"api[_-]?key|app[_-]?secret|bearer\s|계좌번호|주민등록)",
    re.IGNORECASE,
)
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db(db_path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file():
        raise StockChoiceStorageError("CHOICE_DB_NOT_FOUND")
    db = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro" if readonly else str(path),
        uri=readonly, timeout=15,
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    if readonly:
        db.execute("PRAGMA query_only=ON")
    return db


def migrate_authored_b4(db_path: Path) -> dict[str, Any]:
    db = _db(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = {x["name"] for x in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "jev_stock_choice_review" not in existing:
            raise StockChoiceStorageError("CHOICE_MIGRATION_REQUIRED")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE}(
            id TEXT PRIMARY KEY,
            canonical_capture_id TEXT NOT NULL,
            sample_index INTEGER NOT NULL,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            horizon_intent TEXT NOT NULL,
            note_version INTEGER NOT NULL CHECK(note_version>=1),
            authored_note TEXT NOT NULL,
            note_sha256 TEXT NOT NULL,
            origin TEXT NOT NULL,
            purpose TEXT NOT NULL,
            original_authorship_attested INTEGER NOT NULL CHECK(original_authorship_attested=1),
            no_third_party_material_attested INTEGER NOT NULL CHECK(no_third_party_material_attested=1),
            external_ai_transfer_attested INTEGER NOT NULL CHECK(external_ai_transfer_attested=1),
            authored_at_utc TEXT NOT NULL,
            current_review_only INTEGER NOT NULL CHECK(current_review_only=1),
            UNIQUE(canonical_capture_id,sample_index,snapshot_hash,market,ticker,note_version)
        )""")
        db.execute(f"""CREATE INDEX IF NOT EXISTS idx_jev_b4_authored_lookup
            ON {TABLE}(canonical_capture_id,sample_index,snapshot_hash,note_version)""")
        db.commit()
        return {"schema_version": SCHEMA, "status": "READY",
                "writes_to_scanner": 0, "external_model_calls": 0}
    except (sqlite3.Error, StockChoiceStorageError) as exc:
        db.rollback()
        if isinstance(exc, StockChoiceStorageError):
            raise
        raise StockChoiceStorageError("CHOICE_B4_MIGRATION_FAILED") from exc
    finally:
        db.close()


def validate_note(raw: Any) -> str:
    if not isinstance(raw, str):
        raise StockChoiceExecutionError("B4_NOTE_INVALID")
    note = raw.strip()
    if (not 24 <= len(note) <= 380 or "\n" in note or "\r" in note
            or any(ord(ch) < 32 for ch in note)
            or _FORBIDDEN.search(note)):
        raise StockChoiceExecutionError("B4_NOTE_INVALID_OR_EXTERNAL_MATERIAL")
    # Cannot automatically prove originality; do not claim such verification.
    return note


class AuthoredEvidenceStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def latest(self, identity: dict[str, Any]) -> dict[str, Any] | None:
        db = _db(self.db_path, readonly=True)
        try:
            try:
                row = db.execute(
                    f"""SELECT * FROM {TABLE} WHERE canonical_capture_id=?
                    AND sample_index=? AND snapshot_hash=? AND market=? AND ticker=?
                    ORDER BY note_version DESC LIMIT 1""",
                    (identity["capture_id"], identity["sample_index"],
                     identity["snapshot_hash"], identity["market"], identity["ticker"]),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                raise StockChoiceStorageError("CHOICE_B4_MIGRATION_REQUIRED") from exc
            if row is None:
                return None
            return dict(row)
        finally:
            db.close()

    def save(self, identity: dict[str, Any], note: str, *,
             original_authorship_attested: bool,
             no_third_party_material_attested: bool,
             external_ai_transfer_attested: bool) -> dict[str, Any]:
        note = validate_note(note)
        if (original_authorship_attested is not True
                or no_third_party_material_attested is not True
                or external_ai_transfer_attested is not True):
            raise StockChoiceExecutionError("B4_AUTHORED_ATTESTATION_REQUIRED")
        db = _db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = db.execute(
                    f"""SELECT * FROM {TABLE} WHERE canonical_capture_id=?
                    AND sample_index=? AND snapshot_hash=? AND market=? AND ticker=?
                    ORDER BY note_version DESC LIMIT 1""",
                    (identity["capture_id"], identity["sample_index"],
                     identity["snapshot_hash"], identity["market"], identity["ticker"]),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                raise StockChoiceStorageError("CHOICE_B4_MIGRATION_REQUIRED") from exc
            note_sha = hashlib.sha256(note.encode("utf-8")).hexdigest()
            if previous and previous["note_sha256"] == note_sha:
                db.rollback()
                return {"status": "UNCHANGED", "note_version": previous["note_version"],
                        "authored_at_utc": previous["authored_at_utc"],
                        "candidate": identity}
            version = (previous["note_version"] + 1) if previous else 1
            row_id = digest_json({"identity": identity, "note_version": version})
            db.execute(f"""INSERT INTO {TABLE}(
                id,canonical_capture_id,sample_index,market,ticker,snapshot_hash,
                horizon_intent,note_version,authored_note,note_sha256,origin,purpose,
                original_authorship_attested,no_third_party_material_attested,
                external_ai_transfer_attested,authored_at_utc,current_review_only
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                row_id,identity["capture_id"],identity["sample_index"],
                identity["market"],identity["ticker"],identity["snapshot_hash"],
                identity["horizon_intent"],version,note,note_sha,ORIGIN,
                "CURRENT_SINGLE_STOCK_FOLLOWUP_REVIEW_ONLY",
                1,1,1,_now(),1,
            ))
            db.commit()
            return {"status": "STORED", "note_version": version,
                    "candidate": identity, "authored_at_utc": self.latest(identity)["authored_at_utc"]}
        except (sqlite3.Error, StockChoiceStorageError) as exc:
            db.rollback()
            if isinstance(exc, StockChoiceStorageError):
                raise
            raise StockChoiceStorageError("CHOICE_B4_NOTE_SAVE_FAILED") from exc
        finally:
            db.close()

    def resolver(self, capture: dict[str, Any], sample: dict[str, Any]) -> TrustedChoiceInput | None:
        identity = {
            "capture_id": capture["id"], "sample_index": sample["sample_index"],
            "market": sample["market"], "ticker": sample["ticker"],
            "snapshot_hash": sample["snapshot_hash"],
            "horizon_intent": capture["horizon_intent"],
        }
        record = self.latest(identity)
        if record is None:
            return None
        if record["origin"] != ORIGIN or record["purpose"] != "CURRENT_SINGLE_STOCK_FOLLOWUP_REVIEW_ONLY":
            return None
        if (not all(record[k] == 1 for k in (
            "original_authorship_attested", "no_third_party_material_attested",
            "external_ai_transfer_attested", "current_review_only"
        )) or record["horizon_intent"] != identity["horizon_intent"]):
            return None
        note = validate_note(record["authored_note"])
        if hashlib.sha256(note.encode("utf-8")).hexdigest() != record["note_sha256"]:
            return None
        try:
            created = datetime.fromisoformat(record["authored_at_utc"])
            if (created.tzinfo is None or created.utcoffset() != timedelta(0)
                    or created > datetime.now(timezone.utc)):
                return None
        except (ValueError, TypeError):
            return None
        return TrustedChoiceInput(
            scope="VERIFIED_STOCK_CHOICE_AI_TRANSFER_V1",
            # Source is restricted to this local user-attested original note,
            # NEVER a claim that market-provider data is redistributable.
            source_policy_ref=f"B4_LOCAL_USER_ORIGINAL:{record['id']}:{record['note_sha256']}",
            observed_at_utc=record["authored_at_utc"],
            authored_for_capture=identity["capture_id"],
            authored_for_sample=identity["sample_index"],
            authored_for_snapshot=identity["snapshot_hash"],
            fields={
                "horizon_intent": identity["horizon_intent"],
                "strategy_intent": _INTENT,
                "review_notes": note,
                "internal_risk_rule_description": _RISK,
            },
        )


class LocalModelRegistry:
    """Only user-triggered read-only provider discovery adds active models."""
    def __init__(self):
        self._lock = RLock()
        self._name: str | None = None
        self._verified_at: datetime | None = None

    def confirm_from_provider(self, models: list[dict[str, str]]) -> dict[str, Any]:
        candidates = sorted({
            row["name"] for row in models
            if isinstance(row, dict) and isinstance(row.get("name"), str)
            and _MODEL_RE.fullmatch(row["name"])
            and row["name"].startswith("jev-")
        })
        if not candidates:
            raise StockChoiceExecutionError("B4_MODELS_EMPTY")
        name = "jev-1.14.0" if "jev-1.14.0" in candidates else candidates[-1]
        with self._lock:
            self._name, self._verified_at = name, datetime.now(timezone.utc)
        return {"status": "VERIFIED", "model": name,
                "expires_in_seconds": MODEL_VERIFICATION_TTL_SECONDS,
                "model_count": len(candidates), "paid_model_calls": 0}

    def active(self) -> str | None:
        with self._lock:
            if (self._name is not None and self._verified_at is not None
                    and datetime.now(timezone.utc)-self._verified_at <
                    timedelta(seconds=MODEL_VERIFICATION_TTL_SECONDS)):
                return self._name
        return None


MODEL_REGISTRY = LocalModelRegistry()


class ChoiceCostPolicy:
    """Bounded conservative *estimate*; no provider-side hard billing cap."""
    def __init__(self, registry: LocalModelRegistry = MODEL_REGISTRY):
        self.registry = registry

    def check(self, prepared: dict[str, Any], *, model: str) -> dict[str, Any]:
        if self.registry.active() != model:
            raise StockChoiceExecutionError("B4_MODEL_NOT_DISCOVERED")
        from .typesafe_provider import load_typesafe_jev_api_key
        if load_typesafe_jev_api_key() is None:
            raise StockChoiceExecutionError("B4_PROVIDER_KEY_MISSING")
        from .stock_review_contract_v1 import MAX_WIRE_BYTES
        from .typesafe_provider import TYPESAFE_SYSTEM_ONE_URL
        import httpx
        wire = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL,
                             json=prepared["request_body"]).content
        if len(wire) > min(MAX_WIRE_BYTES, MAX_REQUEST_BYTES):
            raise StockChoiceExecutionError("B4_COST_WIRE_LIMIT")
        estimated = MAX_ESTIMATED_INPUT_TOKENS * RATE_USD_PER_MILLION_INPUT / 1_000_000
        if estimated > MAX_ESTIMATED_COST_USD:
            raise StockChoiceExecutionError("B4_COST_LIMIT")
        return {
            "price_ref": RATE_REFERENCE, "price_verified_date": RATE_VERIFIED_DATE,
            "usd_per_million_input_tokens": RATE_USD_PER_MILLION_INPUT,
            "estimated_token_allowance": MAX_ESTIMATED_INPUT_TOKENS,
            "estimated_cost_ceiling_usd": estimated,
            "user_single_call_limit_usd": MAX_ESTIMATED_COST_USD,
            "wire_bytes": len(wire),
            "provider_hard_billing_limit": False,
            "rate_is_estimate": True,
        }

    def after_response(self, tokens: int) -> tuple[float, str]:
        if type(tokens) is not int or tokens < 0:
            raise StockChoiceExecutionError("B4_USAGE_INVALID")
        return tokens * RATE_USD_PER_MILLION_INPUT / 1_000_000, (
            f"USD_0.042_PER_1M_INPUT_{RATE_VERIFIED_DATE}_ESTIMATE"
        )


def local_authored_enabled() -> bool:
    return os.getenv("STOCKSCOPE_JEV_B4_LOCAL_AUTHORED", "").strip() == "1"
