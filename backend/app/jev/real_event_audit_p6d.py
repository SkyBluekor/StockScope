"""P6-D: auditable real Scanner/EventEvidence inventory, WITHOUT a model request.

This is a diagnostic, not a permission grant. It reads ONLY an existing
SQLite database in read-only mode. A missing DB or schema is NOT an empty
corpus. Stored event/link/quality counts are NOT historical as-of proofs.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
from typing import Any

from app.event_evidence.asof import EventEvidenceAsOfReader
from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.policy import EvidenceCapability, policy_for_event_source
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.event_v5 import route_event_v5
from app.jev.independent_assertion_p6b import inspect_frozen_event_assertions, _registry
from app.jev.independent_event_reference_p6 import inspect_frozen_event_reference
from app.jev.scanner_shadow_s7 import load_frozen_candidates

VERSION = "JEV_P6D_REAL_EVENT_INVENTORY_V1"
CAPTURE_SCOPE = "EXISTING_CANONICAL_COMPLETE_ONLY"
STORE_TABLES = {
    "event_evidence_policy_snapshot": "source_policy_snapshots",
    "event_evidence_source_ref": "source_refs",
    "event_evidence_record": "event_revisions",
    "event_evidence_entity": "entities",
    "event_evidence_entity_relevance": "entity_relevances",
    "event_evidence_quality_assessment": "quality_assessments",
}
MIN_ASOF_TABLES = {
    "event_evidence_policy_snapshot", "event_evidence_source_ref",
    "event_evidence_record", "event_evidence_record_source",
    "event_evidence_entity", "event_evidence_entity_relevance",
    "event_evidence_canonical_group", "event_evidence_resolution",
    "event_evidence_quality_assessment",
}
MIN_COLUMNS = {
    "event_evidence_entity": {"entity_id", "market", "ticker", "entity_type"},
    "event_evidence_entity_relevance": {"entity_id", "event_id", "event_version"},
    "event_evidence_quality_assessment": {"entity_id", "quality_state"},
    "event_evidence_source_ref": {"source_kind"},
}


def _readonly(db: Path) -> sqlite3.Connection:
    if not db.is_file():
        raise FileNotFoundError("P6D_SIMULATION_DB_NOT_FOUND")
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _store_inventory(db: Path) -> dict[str, Any]:
    # Never treat schema absence as zero independent events.
    with _readonly(db) as conn:
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = sorted(MIN_ASOF_TABLES - tables)
        found = sorted(MIN_ASOF_TABLES & tables)
        invalid_columns = []
        for table, required in MIN_COLUMNS.items():
            if table not in tables:
                continue
            columns = {
                str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")
            }
            invalid_columns.extend(f"{table}.{col}" for col in sorted(required - columns))
        ready = not missing and not invalid_columns
        counts: dict[str, int | None] = {}
        for table, field in STORE_TABLES.items():
            counts[field] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if ready else None
        sources = (
            {str(row["source_kind"]): int(row["n"]) for row in conn.execute(
                "SELECT source_kind,COUNT(*) n FROM event_evidence_source_ref GROUP BY source_kind"
            )}
            if ready else {}
        )
        quality = (
            {str(row["quality_state"]): int(row["n"]) for row in conn.execute(
                "SELECT quality_state,COUNT(*) n FROM event_evidence_quality_assessment GROUP BY quality_state"
            )}
            if ready else {}
        )
        return {
            "status": "READY" if ready else ("SCHEMA_MISSING" if not found else "SCHEMA_INCOMPLETE"),
            "schema_ready": ready, "present_asof_table_count": len(found),
            "required_asof_table_count": len(MIN_ASOF_TABLES),
            "missing_tables": missing, "invalid_columns": invalid_columns,
            "stored_counts_not_asof": counts,
            "source_kind_counts": sources, "quality_state_counts": quality,
        }


def _candidate_links(conn: sqlite3.Connection, *, ticker: str, market: str) -> dict[str, int]:
    entity_ids = [
        str(row["entity_id"]) for row in conn.execute(
            "SELECT entity_id FROM event_evidence_entity "
            "WHERE entity_type='LISTED_COMPANY' AND market=? AND ticker=?",
            (market, ticker),
        )
    ]
    if not entity_ids:
        return {"entity_count": 0, "relevance_count": 0, "quality_count": 0}
    # Bind all IDs, never interpolate data into SQL.
    marks = ",".join("?" for _ in entity_ids)
    relevance_count = int(conn.execute(
        "SELECT COUNT(*) FROM event_evidence_entity_relevance WHERE entity_id IN ("+marks+")",
        entity_ids,
    ).fetchone()[0])
    quality_count = int(conn.execute(
        "SELECT COUNT(*) FROM event_evidence_quality_assessment WHERE entity_id IN ("+marks+")",
        entity_ids,
    ).fetchone()[0])
    return {
        "entity_count": len(entity_ids),
        "relevance_count": relevance_count,
        "quality_count": quality_count,
    }


def _local_source_rights(kinds: list[str], naver_provider_kind: str | None) -> dict[str, dict[str, Any]]:
    verdicts = {}
    for kind in sorted(kinds):
        try:
            policy = policy_for_event_source(
                kind, provider_kind=naver_provider_kind if kind == "NAVER_NEWS" else None,
            )
            verdicts[kind] = {
                "known_policy": True,
                "derived_retention": policy.allows(EvidenceCapability.DERIVED_RETENTION),
                "ai_transform": policy.allows(EvidenceCapability.AI_TRANSFORM),
                "historical_evaluation": policy.allows(EvidenceCapability.HISTORICAL_EVALUATION),
                "prediction_input": policy.allows(EvidenceCapability.PREDICTION_INPUT),
                "basis": policy.policy_basis,
            }
        except (EventEvidenceContractError, ValueError):
            verdicts[kind] = {
                "known_policy": False, "derived_retention": False,
                "ai_transform": False, "historical_evaluation": False,
                "prediction_input": False, "basis": "NO_VERIFIED_P6_SOURCE_POLICY",
            }
    return verdicts


def audit_existing_capture(
    simulation_db: Path, *, capture_id: str,
    naver_provider_kind: str | None = None,
) -> dict[str, Any]:
    """Count only what the exact existing local DB proves, never perform ingestion."""
    db = Path(simulation_db)
    if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 200:
        raise ValueError("P6D_CAPTURE_ID_INVALID")
    # Frozen loader verifies canonical COMPLETE and the snapshot hashes.
    pairs = load_frozen_candidates(db, capture_id=capture_id, limit=500)
    entries = sorted(
        ((capture, sample) for capture, sample in pairs
         if sample["action"] == "ENTRY_CANDIDATE"),
        key=lambda pair: int(pair[1]["sample_index"]),
    )
    inventory = _store_inventory(db)
    registry, registry_error = _registry()
    rows = []
    categories = Counter()
    source_kinds = set(inventory["source_kind_counts"])
    with _readonly(db) as conn:
        for capture, sample in entries:
            index = int(sample["sample_index"])
            base = {
                "sample_index": index, "ticker": sample["ticker"],
                "market": sample["market"], "snapshot_hash": sample["snapshot_hash"],
            }
            links = (
                _candidate_links(conn, ticker=sample["ticker"], market=sample["market"])
                if inventory["schema_ready"] else
                {"entity_count": None, "relevance_count": None, "quality_count": None}
            )
            if not inventory["schema_ready"]:
                row = {**base, **links, "reference_status": "NOT_QUERIED",
                       "assertion_status": "NOT_QUERIED", "v5_route": "BLOCKED_EVIDENCE",
                       "cause": inventory["status"], "reason_codes": ["P6D_EVENT_SCHEMA_NOT_READY"],
                       "reference_count": None, "approved_assertions": None}
            else:
                reference = inspect_frozen_event_reference(
                    db, capture_id=capture_id, sample_index=index,
                    naver_provider_kind=naver_provider_kind,
                )
                assessment = inspect_frozen_event_assertions(
                    db, capture_id=capture_id, sample_index=index,
                    naver_provider_kind=naver_provider_kind,
                )
                routing = route_event_v5(assessment)
                source_kinds.update(reference["source_kinds"])
                if links["entity_count"] == 0:
                    cause = "ENTITY_NOT_LINKED"
                elif links["relevance_count"] == 0:
                    cause = "NO_RELEVANCE_LINK"
                elif links["quality_count"] == 0:
                    cause = "NO_QUALITY_ASSESSMENT"
                elif reference["status"] == "NO_INDEPENDENT_EVIDENCE":
                    cause = "NO_ELIGIBLE_ASOF_REFERENCE"
                elif reference["status"] == "EVIDENCE_NOT_USABLE":
                    cause = "SOURCE_OR_TIME_OR_INTEGRITY_BLOCKED"
                elif registry_error:
                    cause = "ASSERTION_REGISTRY_INVALID"
                elif assessment["approved_assertion_count"] == 0:
                    cause = "NO_PROSPECTIVE_APPROVED_ASSERTION"
                elif routing["routing"] == "REVIEW_CANDIDATE_PROVIDER_HOLD":
                    cause = "PROVIDER_RIGHTS_NOT_APPROVED"
                else:
                    cause = "LOCAL_EVENT_REVIEW_RESOLVED_OR_BLOCKED"
                row = {
                    **base, **links,
                    "reference_status": reference["status"],
                    "assertion_status": assessment["status"],
                    "v5_route": routing["routing"], "cause": cause,
                    "reason_codes": sorted(set(reference["reason_codes"] +
                                                assessment["reason_codes"])),
                    "reference_count": reference["reference_count"],
                    "approved_assertions": assessment["approved_assertion_count"],
                }
            categories[row["cause"]] += 1
            rows.append(row)

    rights = _local_source_rights(sorted(source_kinds), naver_provider_kind)
    return {
        "version": VERSION, "read_only": True,
        "capture_id": capture_id,
        "canonical_capture_id": entries[0][0]["id"] if entries else (pairs[0][0]["id"] if pairs else None),
        "entry_count": len(entries),
        "store": inventory, "registry_status": (
            "INVALID" if registry_error else "PRESENT" if registry else "ABSENT_OR_EMPTY"
        ),
        "registry_record_count": None if registry_error else len(registry),
        "cause_counts": dict(sorted(categories.items())),
        "source_rights_current_code": rights,
        "rows": rows,
        "ready_for_live_jev": False,
        "real_market_model_calls": 0, "mock_model_calls": 0, "db_writes": 0,
        "historical_completeness_proven": False,
        "notes": [
            "Stored table counts are not evidence available at the Scanner decision time.",
            "A capture.created_at cutoff is NOT the market source publication time.",
            "An empty registry is not an approved real-world contradiction.",
            "No real data may be transmitted to TypeSafe from this audit.",
        ],
    }
