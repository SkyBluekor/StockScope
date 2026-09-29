from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.macro.errors import MacroContractError
from app.macro.identity import (
    MACRO_IDENTITY_CONTRACT_VERSION,
    canonical_json,
    content_hash,
    observation_key,
)
from app.macro.manifest import MacroPreparedRangeManifest
from app.macro.models import (
    MACRO_OBSERVATION_CONTRACT_VERSION,
    MACRO_PREPARED_RANGE_CONTRACT_VERSION,
    MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION,
    MACRO_SERIES_CONTRACT_VERSION,
    MacroObservation,
    MacroResearchProtocol,
    MacroSeriesContract,
)


MACRO_STORE_SCHEMA_VERSION = "VN_NEXT6A_S1_MACRO_STORE_V1"
MACRO_NORMALIZATION_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_NORMALIZATION_V1"

MACRO_STORE_TABLES = (
    "macro_schema_meta",
    "macro_series_contract",
    "macro_collection_run",
    "macro_observation_revision",
    "macro_prepared_range",
    "macro_research_protocol",
)

MACRO_META_EXPECTED = {
    "schema_version": MACRO_STORE_SCHEMA_VERSION,
    "series_contract_version": MACRO_SERIES_CONTRACT_VERSION,
    "observation_contract_version": MACRO_OBSERVATION_CONTRACT_VERSION,
    "prepared_range_contract_version": MACRO_PREPARED_RANGE_CONTRACT_VERSION,
    "research_protocol_contract_version": MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION,
    "identity_contract_version": MACRO_IDENTITY_CONTRACT_VERSION,
    "normalization_contract_version": MACRO_NORMALIZATION_CONTRACT_VERSION,
}

_SECRET_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "credential",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_secret_like(value: Any, *, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if any(fragment in normalized for fragment in _SECRET_FRAGMENTS):
                raise MacroContractError(
                    "MACRO_SECRET_METADATA_FORBIDDEN",
                    f"{path}.{key}에는 secret/credential 값을 저장할 수 없습니다.",
                )
            _reject_secret_like(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secret_like(item, path=f"{path}[{index}]")


class MacroStore:
    """Explicitly initialized writable Local Macro Store.

    Construction never creates files or schema. Call initialize() only from an
    explicit migration/preparation command. Product/query paths should use
    LocalMacroReader instead.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.clock = clock or _utc_now

    def initialize(self) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS macro_schema_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS macro_series_contract(
                    series_id TEXT PRIMARY KEY,
                    semantic_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_series_id TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    measurement_definition TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    currency TEXT,
                    session_definition TEXT NOT NULL,
                    observation_frequency TEXT NOT NULL,
                    owner_status TEXT NOT NULL,
                    active_owner INTEGER NOT NULL CHECK(active_owner IN (0,1)),
                    allowed_usage_scope_json TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    contract_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS macro_collection_run(
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('OPEN','PUBLISHED','FAILED')),
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    published_at TEXT,
                    metadata_json TEXT NOT NULL,
                    run_hash TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS macro_observation_revision(
                    id TEXT PRIMARY KEY,
                    observation_key TEXT NOT NULL,
                    revision_no INTEGER NOT NULL,
                    series_id TEXT NOT NULL REFERENCES macro_series_contract(series_id),
                    native_observation_id TEXT NOT NULL,
                    observation_date TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    source_unit TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    normalizer_version TEXT NOT NULL,
                    realtime_start TEXT,
                    realtime_end TEXT,
                    vintage_id TEXT,
                    available_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    time_quality TEXT NOT NULL,
                    first_seen_at TEXT,
                    source_published_at TEXT,
                    provider_available_at TEXT,
                    corrected_at TEXT,
                    normalized_hash TEXT NOT NULL,
                    collection_run_id TEXT NOT NULL REFERENCES macro_collection_run(id),
                    published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
                    created_at TEXT NOT NULL,
                    UNIQUE(observation_key, revision_no)
                );

                CREATE INDEX IF NOT EXISTS idx_macro_observation_series_date
                ON macro_observation_revision(series_id,observation_date,published);

                CREATE INDEX IF NOT EXISTS idx_macro_observation_available
                ON macro_observation_revision(series_id,available_at,published);

                CREATE TABLE IF NOT EXISTS macro_prepared_range(
                    id TEXT PRIMARY KEY,
                    series_id TEXT NOT NULL REFERENCES macro_series_contract(series_id),
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    expected_count INTEGER NOT NULL,
                    stored_count INTEGER NOT NULL,
                    missing_count INTEGER NOT NULL,
                    unavailable_count INTEGER NOT NULL,
                    date_only_count INTEGER NOT NULL,
                    eligible_count INTEGER NOT NULL,
                    source_contract_version TEXT NOT NULL,
                    normalizer_version TEXT NOT NULL,
                    source_manifest_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('COMPLETE','PARTIAL')),
                    content_hash TEXT NOT NULL UNIQUE,
                    prepared_at TEXT NOT NULL,
                    contract_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS macro_research_protocol(
                    protocol_id TEXT PRIMARY KEY,
                    protocol_version TEXT NOT NULL,
                    baseline_identity TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    protocol_hash TEXT NOT NULL UNIQUE,
                    numeric_thresholds_defined INTEGER NOT NULL CHECK(numeric_thresholds_defined IN (0,1)),
                    contract_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            for key, value in MACRO_META_EXPECTED.items():
                conn.execute(
                    """
                    INSERT INTO macro_schema_meta(key,value)
                    VALUES(?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (key, value),
                )
            conn.commit()
        return self.inspect()

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise MacroContractError(
                "MACRO_STORE_NOT_INITIALIZED",
                f"Macro Store가 준비되지 않았습니다: {self.db_path}",
            )
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def inspect(self) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {"present": False, "schema_version": MACRO_STORE_SCHEMA_VERSION}
        with self._connect() as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(set(MACRO_STORE_TABLES) - tables)
            if missing:
                raise MacroContractError(
                    "MACRO_STORE_PARTIAL_SCHEMA",
                    "Macro Store가 부분 schema 상태입니다: " + ", ".join(missing),
                )
            meta = {
                str(row["key"]): str(row["value"])
                for row in conn.execute(
                    "SELECT key,value FROM macro_schema_meta"
                ).fetchall()
            }
            for key, expected in MACRO_META_EXPECTED.items():
                if meta.get(key) != expected:
                    raise MacroContractError(
                        "MACRO_STORE_CONTRACT_MISMATCH",
                        f"Macro Store contract 불일치: {key}",
                    )
            return {
                "present": True,
                "schema_version": MACRO_STORE_SCHEMA_VERSION,
                "tables": list(MACRO_STORE_TABLES),
                "counts": {
                    "series_contract_count": int(conn.execute("SELECT COUNT(*) FROM macro_series_contract").fetchone()[0]),
                    "collection_run_count": int(conn.execute("SELECT COUNT(*) FROM macro_collection_run").fetchone()[0]),
                    "observation_revision_count": int(conn.execute("SELECT COUNT(*) FROM macro_observation_revision").fetchone()[0]),
                    "published_observation_count": int(conn.execute("SELECT COUNT(*) FROM macro_observation_revision WHERE published=1").fetchone()[0]),
                    "prepared_range_count": int(conn.execute("SELECT COUNT(*) FROM macro_prepared_range").fetchone()[0]),
                    "research_protocol_count": int(conn.execute("SELECT COUNT(*) FROM macro_research_protocol").fetchone()[0]),
                },
                "contract_versions": dict(MACRO_META_EXPECTED),
            }

    def register_series_contract(self, contract: MacroSeriesContract) -> dict[str, Any]:
        now = self.clock()
        payload = contract.to_dict()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT contract_hash FROM macro_series_contract WHERE series_id=?",
                (contract.series_id,),
            ).fetchone()
            if row is not None:
                if str(row["contract_hash"]) != contract.contract_hash:
                    raise MacroContractError(
                        "MACRO_SERIES_CONTRACT_IMMUTABLE",
                        "같은 series_id의 contract를 덮어쓸 수 없습니다. 새 series/version identity를 사용하세요.",
                    )
                return {"series_id": contract.series_id, "contract_hash": contract.contract_hash, "duplicate": True}
            if contract.active_owner:
                owner = conn.execute(
                    """
                    SELECT series_id FROM macro_series_contract
                    WHERE semantic_id=? AND active_owner=1
                    LIMIT 1
                    """,
                    (contract.semantic_id,),
                ).fetchone()
                if owner is not None:
                    raise MacroContractError(
                        "MACRO_ACTIVE_OWNER_DUPLICATE",
                        "동일 semantic_id에 active owner를 둘 이상 등록할 수 없습니다.",
                    )
            conn.execute(
                """
                INSERT INTO macro_series_contract(
                    series_id,semantic_id,provider,provider_series_id,
                    instrument_type,measurement_definition,unit,currency,
                    session_definition,observation_frequency,owner_status,
                    active_owner,allowed_usage_scope_json,contract_version,
                    contract_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    contract.series_id,
                    contract.semantic_id,
                    contract.provider,
                    contract.provider_series_id,
                    contract.instrument_type,
                    contract.measurement_definition,
                    contract.unit,
                    contract.currency,
                    contract.session_definition,
                    contract.observation_frequency,
                    contract.owner_status.value,
                    int(contract.active_owner),
                    canonical_json(list(contract.allowed_usage_scope)),
                    contract.contract_version,
                    contract.contract_hash,
                    now,
                ),
            )
            conn.commit()
        return {"series_id": contract.series_id, "contract_hash": contract.contract_hash, "duplicate": False, "payload": payload}

    def begin_collection_run(
        self,
        *,
        provider: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_provider = str(provider or "").strip()
        if not clean_provider:
            raise MacroContractError("MACRO_PROVIDER_REQUIRED", "provider가 필요합니다.")
        metadata = dict(metadata or {})
        _reject_secret_like(metadata)
        started_at = self.clock()
        resolved_id = run_id or f"MACRO-RUN-{uuid4().hex}"
        run_hash = content_hash(
            {
                "provider": clean_provider,
                "run_id": resolved_id,
                "started_at": started_at,
                "metadata": metadata,
            }
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO macro_collection_run(
                    id,provider,status,started_at,metadata_json,run_hash
                ) VALUES(?,?,'OPEN',?,?,?)
                """,
                (
                    resolved_id,
                    clean_provider,
                    started_at,
                    canonical_json(metadata),
                    run_hash,
                ),
            )
            conn.commit()
        return {"run_id": resolved_id, "status": "OPEN", "run_hash": run_hash}

    def store_observation(
        self,
        *,
        run_id: str,
        observation: MacroObservation,
    ) -> dict[str, Any]:
        key = observation_key(
            series_id=observation.series_id,
            native_observation_id=observation.native_observation_id,
            observation_date=observation.observation_date,
        )
        with self._connect() as conn:
            run = conn.execute(
                "SELECT status,provider FROM macro_collection_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if run is None or str(run["status"]) != "OPEN":
                raise MacroContractError(
                    "MACRO_COLLECTION_RUN_NOT_OPEN",
                    "Observation은 OPEN collection run에만 저장할 수 있습니다.",
                )
            series = conn.execute(
                "SELECT provider FROM macro_series_contract WHERE series_id=?",
                (observation.series_id,),
            ).fetchone()
            if series is None:
                raise MacroContractError(
                    "MACRO_SERIES_NOT_REGISTERED",
                    "Observation의 Series Contract가 등록되지 않았습니다.",
                )
            if str(series["provider"]).upper() != str(run["provider"]).upper():
                raise MacroContractError(
                    "MACRO_PROVIDER_SERIES_MISMATCH",
                    "Collection provider와 Series provider가 일치하지 않습니다.",
                )

            duplicate = conn.execute(
                """
                SELECT id,revision_no,published
                FROM macro_observation_revision
                WHERE observation_key=?
                  AND source_payload_hash=?
                  AND normalized_hash=?
                ORDER BY revision_no DESC
                LIMIT 1
                """,
                (
                    key,
                    observation.source_payload_hash,
                    observation.normalized_hash,
                ),
            ).fetchone()
            if duplicate is not None:
                return {
                    "id": str(duplicate["id"]),
                    "observation_key": key,
                    "revision_no": int(duplicate["revision_no"]),
                    "duplicate": True,
                    "published": bool(duplicate["published"]),
                }

            row = conn.execute(
                """
                SELECT COALESCE(MAX(revision_no),0) AS revision_no
                FROM macro_observation_revision
                WHERE observation_key=?
                """,
                (key,),
            ).fetchone()
            revision_no = int(row["revision_no"]) + 1
            observation_id = f"MACRO-OBS-{uuid4().hex}"
            temporal = observation.temporal
            conn.execute(
                """
                INSERT INTO macro_observation_revision(
                    id,observation_key,revision_no,series_id,native_observation_id,
                    observation_date,source_value,normalized_value,source_unit,
                    source_payload_hash,normalizer_version,realtime_start,realtime_end,
                    vintage_id,available_at,fetched_at,time_quality,first_seen_at,
                    source_published_at,provider_available_at,corrected_at,
                    normalized_hash,collection_run_id,published,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
                """,
                (
                    observation_id,
                    key,
                    revision_no,
                    observation.series_id,
                    observation.native_observation_id,
                    observation.observation_date,
                    observation.source_value,
                    observation.normalized_value,
                    observation.source_unit,
                    observation.source_payload_hash,
                    observation.normalizer_version,
                    observation.realtime_start,
                    observation.realtime_end,
                    observation.vintage_id,
                    temporal.available_at,
                    temporal.fetched_at,
                    temporal.time_quality.value,
                    temporal.first_seen_at,
                    temporal.source_published_at,
                    temporal.provider_published_at,
                    temporal.corrected_at,
                    observation.normalized_hash,
                    run_id,
                    self.clock(),
                ),
            )
            conn.commit()
        return {
            "id": observation_id,
            "observation_key": key,
            "revision_no": revision_no,
            "duplicate": False,
            "published": False,
        }

    def publish_collection_run(self, run_id: str) -> dict[str, Any]:
        now = self.clock()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM macro_collection_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise MacroContractError("MACRO_COLLECTION_RUN_NOT_FOUND", "Collection run을 찾을 수 없습니다.")
            status = str(row["status"])
            if status == "PUBLISHED":
                count = int(conn.execute(
                    "SELECT COUNT(*) FROM macro_observation_revision WHERE collection_run_id=? AND published=1",
                    (run_id,),
                ).fetchone()[0])
                return {"run_id": run_id, "status": "PUBLISHED", "published_count": count, "duplicate": True}
            if status != "OPEN":
                raise MacroContractError(
                    "MACRO_COLLECTION_RUN_NOT_OPEN",
                    "FAILED collection run은 publish할 수 없습니다.",
                )
            conn.execute(
                """
                UPDATE macro_observation_revision
                SET published=1
                WHERE collection_run_id=? AND published=0
                """,
                (run_id,),
            )
            conn.execute(
                """
                UPDATE macro_collection_run
                SET status='PUBLISHED',completed_at=?,published_at=?
                WHERE id=?
                """,
                (now, now, run_id),
            )
            count = int(conn.execute(
                "SELECT COUNT(*) FROM macro_observation_revision WHERE collection_run_id=? AND published=1",
                (run_id,),
            ).fetchone()[0])
            conn.commit()
        return {"run_id": run_id, "status": "PUBLISHED", "published_count": count, "duplicate": False}

    def fail_collection_run(self, run_id: str) -> dict[str, Any]:
        now = self.clock()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM macro_collection_run WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise MacroContractError("MACRO_COLLECTION_RUN_NOT_FOUND", "Collection run을 찾을 수 없습니다.")
            if str(row["status"]) == "PUBLISHED":
                raise MacroContractError(
                    "MACRO_COLLECTION_RUN_ALREADY_PUBLISHED",
                    "이미 publish된 collection run을 FAILED로 변경할 수 없습니다.",
                )
            conn.execute(
                """
                UPDATE macro_collection_run
                SET status='FAILED',completed_at=?
                WHERE id=?
                """,
                (now, run_id),
            )
            conn.commit()
        return {"run_id": run_id, "status": "FAILED"}

    def store_prepared_range(
        self,
        manifest: MacroPreparedRangeManifest,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM macro_series_contract WHERE series_id=?",
                (manifest.series_id,),
            ).fetchone() is None:
                raise MacroContractError(
                    "MACRO_SERIES_NOT_REGISTERED",
                    "Prepared range의 Series Contract가 등록되지 않았습니다.",
                )
            existing = conn.execute(
                "SELECT id FROM macro_prepared_range WHERE content_hash=?",
                (manifest.content_hash,),
            ).fetchone()
            if existing is not None:
                return {"id": str(existing["id"]), "content_hash": manifest.content_hash, "duplicate": True}
            row_id = f"MACRO-RANGE-{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO macro_prepared_range(
                    id,series_id,start_date,end_date,expected_count,stored_count,
                    missing_count,unavailable_count,date_only_count,eligible_count,
                    source_contract_version,normalizer_version,source_manifest_hash,
                    status,content_hash,prepared_at,contract_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row_id,
                    manifest.series_id,
                    manifest.start_date,
                    manifest.end_date,
                    manifest.expected_count,
                    manifest.stored_count,
                    manifest.missing_count,
                    manifest.unavailable_count,
                    manifest.date_only_count,
                    manifest.eligible_count,
                    manifest.source_contract_version,
                    manifest.normalizer_version,
                    manifest.source_manifest_hash,
                    manifest.status,
                    manifest.content_hash,
                    manifest.prepared_at,
                    manifest.contract_version,
                ),
            )
            conn.commit()
        return {"id": row_id, "content_hash": manifest.content_hash, "duplicate": False}

    def register_research_protocol(
        self,
        protocol: MacroResearchProtocol,
    ) -> dict[str, Any]:
        payload = protocol.to_dict()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT protocol_hash FROM macro_research_protocol WHERE protocol_id=?",
                (protocol.protocol_id,),
            ).fetchone()
            if row is not None:
                if str(row["protocol_hash"]) != protocol.protocol_hash:
                    raise MacroContractError(
                        "MACRO_RESEARCH_PROTOCOL_IMMUTABLE",
                        "같은 protocol_id의 연구 계약을 덮어쓸 수 없습니다.",
                    )
                return {"protocol_id": protocol.protocol_id, "protocol_hash": protocol.protocol_hash, "duplicate": True}
            conn.execute(
                """
                INSERT INTO macro_research_protocol(
                    protocol_id,protocol_version,baseline_identity,payload_json,
                    protocol_hash,numeric_thresholds_defined,contract_version,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    protocol.protocol_id,
                    protocol.protocol_version,
                    protocol.baseline_identity,
                    canonical_json(payload),
                    protocol.protocol_hash,
                    int(protocol.numeric_thresholds_defined),
                    protocol.contract_version,
                    self.clock(),
                ),
            )
            conn.commit()
        return {"protocol_id": protocol.protocol_id, "protocol_hash": protocol.protocol_hash, "duplicate": False}
