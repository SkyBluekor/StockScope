from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from app.macro.development_coverage import (
    NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION,
)
from app.macro.identity import content_hash
from app.macro.validation_entry_gate import (
    NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION,
    OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY,
)
from app.prospective.reference_capture import (
    NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
    REFERENCE_TEMPORAL_MODE,
)


NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION = (
    "VN_NEXT6E_S4_REFERENCE_READINESS_V1"
)

READINESS_REFERENCE_VALIDATION_READY = "REFERENCE_VALIDATION_READY"
READINESS_PROSPECTIVE_ACCUMULATION_REQUIRED = (
    "PROSPECTIVE_ACCUMULATION_REQUIRED"
)
READINESS_DEVELOPMENT_COVERAGE_INSUFFICIENT = (
    "DEVELOPMENT_COVERAGE_INSUFFICIENT"
)
READINESS_SOURCE_COVERAGE_UNAVAILABLE = "SOURCE_COVERAGE_UNAVAILABLE"
READINESS_REFERENCE_ADEQUACY_UNRESOLVED = (
    "REFERENCE_ADEQUACY_UNRESOLVED"
)
READINESS_BLOCKED = "BLOCKED"

_REQUIRED_REFERENCE_TABLES = {
    "prospective_reference_schema_meta",
    "prospective_reference_capture",
    "prospective_reference_attachment",
}

_LIMITATIONS = (
    "NO_EFFECTIVENESS_CLAIM",
    "NO_EXECUTION_COMPARISON",
    "NO_NUMERIC_PROMOTION_CRITERIA",
    "NO_PREDICTION",
    "POST_SCANNER_CAPTURE_NOT_DECISION_INPUT",
    "REFERENCE_READINESS_ONLY",
)


class ReferenceReadinessError(RuntimeError):
    pass


class ProspectiveReferenceSummaryReader:
    """Read NEXT-6E-S3 reference-capture state without mutating runtime."""

    def __init__(self, simulation_db: Path) -> None:
        self.simulation_db = Path(simulation_db)

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise ReferenceReadinessError(
                f"Simulation DB not found: {self.simulation_db}"
            )
        uri = self.simulation_db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def read(self) -> dict[str, Any]:
        with self._connect() as conn:
            tables = self._tables(conn)
            missing = sorted(_REQUIRED_REFERENCE_TABLES - tables)
            if missing:
                return {
                    "status": "NOT_READY",
                    "reason": "PROSPECTIVE_REFERENCE_SCHEMA_MISSING",
                    "storage_version": None,
                    "capture_contract_version": (
                        NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
                    ),
                    "reference_temporal_mode": REFERENCE_TEMPORAL_MODE,
                    "decision_input": False,
                    "signal_time_equivalence": False,
                    "completed_capture_count": 0,
                    "attachment_count": 0,
                    "capture_status_counts": {},
                    "attachment_sets": [],
                }

            version_row = conn.execute(
                """
                SELECT value
                FROM prospective_reference_schema_meta
                WHERE key='schema_version'
                LIMIT 1
                """
            ).fetchone()
            storage_version = (
                str(version_row["value"]) if version_row is not None else None
            )
            if storage_version != NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION:
                return {
                    "status": "NOT_READY",
                    "reason": "PROSPECTIVE_REFERENCE_SCHEMA_UNSUPPORTED",
                    "storage_version": storage_version,
                    "capture_contract_version": (
                        NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
                    ),
                    "reference_temporal_mode": REFERENCE_TEMPORAL_MODE,
                    "decision_input": False,
                    "signal_time_equivalence": False,
                    "completed_capture_count": 0,
                    "attachment_count": 0,
                    "capture_status_counts": {},
                    "attachment_sets": [],
                }

            rows = conn.execute(
                """
                SELECT
                    capture_run_id,capture_contract_version,storage_version,
                    status,reference_temporal_mode,source_sample_count,
                    attachment_count,attachment_set_hash,source_manifest_hash
                FROM prospective_reference_capture
                ORDER BY capture_run_id
                """
            ).fetchall()

        status_counts: Counter[str] = Counter()
        completed: list[dict[str, Any]] = []
        total_attachments = 0
        for row in rows:
            status = str(row["status"])
            status_counts[status] += 1
            if status != "COMPLETE":
                continue
            if (
                str(row["capture_contract_version"])
                != NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
                or str(row["storage_version"])
                != NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
                or str(row["reference_temporal_mode"])
                != REFERENCE_TEMPORAL_MODE
            ):
                raise ReferenceReadinessError(
                    "Stored prospective reference contract mismatch."
                )
            count = int(row["attachment_count"] or 0)
            total_attachments += count
            completed.append(
                {
                    "capture_run_id": str(row["capture_run_id"]),
                    "source_sample_count": int(
                        row["source_sample_count"] or 0
                    ),
                    "attachment_count": count,
                    "attachment_set_hash": str(
                        row["attachment_set_hash"] or ""
                    ),
                    "source_manifest_hash": str(
                        row["source_manifest_hash"] or ""
                    ),
                }
            )

        return {
            "status": "READY",
            "reason": None,
            "storage_version": storage_version,
            "capture_contract_version": (
                NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
            ),
            "reference_temporal_mode": REFERENCE_TEMPORAL_MODE,
            "decision_input": False,
            "signal_time_equivalence": False,
            "completed_capture_count": len(completed),
            "attachment_count": total_attachments,
            "capture_status_counts": {
                key: int(status_counts[key])
                for key in sorted(status_counts)
            },
            "attachment_sets": completed,
        }


def _validate_entry_gate(entry_gate: dict[str, Any]) -> None:
    if entry_gate.get("contract_version") != (
        NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION
    ):
        raise ReferenceReadinessError(
            "NEXT-6E-S1 entry gate contract mismatch."
        )
    if entry_gate.get("overall_scope") != (
        OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY
    ):
        raise ReferenceReadinessError(
            "NEXT-6E-S4 requires REFERENCE_VALIDATION_ONLY scope."
        )
    governance = entry_gate.get("governance") or {}
    if governance.get("holdout_access") is not False:
        raise ReferenceReadinessError("Holdout must remain inaccessible.")
    if governance.get("network_access") is not False:
        raise ReferenceReadinessError("Network access must remain disabled.")
    if governance.get("database_write") is not False:
        raise ReferenceReadinessError("Database writes must remain disabled.")


def _validate_development_report(
    entry_gate: dict[str, Any],
    report: dict[str, Any],
) -> None:
    if report.get("contract_version") != (
        NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION
    ):
        raise ReferenceReadinessError(
            "NEXT-6E-S2 development coverage contract mismatch."
        )
    linked_gate = report.get("entry_gate") or {}
    if (
        linked_gate.get("gate_id") != entry_gate.get("gate_id")
        or linked_gate.get("gate_hash") != entry_gate.get("gate_hash")
    ):
        raise ReferenceReadinessError(
            "Development coverage is not linked to the supplied entry gate."
        )
    scope = report.get("scope") or {}
    scanner = str(
        (entry_gate.get("baseline") or {}).get("scanner_version") or ""
    )
    if not scanner or str(scope.get("scanner_version") or "") != scanner:
        raise ReferenceReadinessError(
            "Development Scanner baseline does not match the entry gate."
        )
    governance = report.get("governance") or {}
    if governance.get("network_access") is not False:
        raise ReferenceReadinessError(
            "Development coverage must be local-only."
        )
    if governance.get("database_write") is not False:
        raise ReferenceReadinessError(
            "Development coverage must be read-only."
        )
    if governance.get("production_decision_approved") is not False:
        raise ReferenceReadinessError(
            "Development coverage cannot approve Production."
        )
    if report.get("source_immutability_verified") is not True:
        raise ReferenceReadinessError(
            "Development source immutability is not verified."
        )


def _readiness_state(
    *,
    entry_gate: dict[str, Any],
    development_report: dict[str, Any],
    prospective: dict[str, Any],
) -> str:
    if prospective.get("status") != "READY":
        return READINESS_SOURCE_COVERAGE_UNAVAILABLE

    development_status = str(development_report.get("status") or "")
    if development_status == "AUDIT_UNAVAILABLE":
        return READINESS_SOURCE_COVERAGE_UNAVAILABLE
    if development_status == "NO_DEVELOPMENT_SAMPLES":
        return READINESS_DEVELOPMENT_COVERAGE_INSUFFICIENT
    if development_status != "COMPLETE":
        return READINESS_BLOCKED

    if int(prospective.get("completed_capture_count") or 0) == 0:
        return READINESS_PROSPECTIVE_ACCUMULATION_REQUIRED

    input_state = entry_gate.get("input_state") or {}
    if str(input_state.get("reference_adequacy") or "") == "UNRESOLVED":
        return READINESS_REFERENCE_ADEQUACY_UNRESOLVED

    blockers = set(entry_gate.get("blockers") or [])
    structural = {
        "REFERENCE_ADEQUACY_UNRESOLVED",
        "HOLDOUT_LOCKED",
        "HISTORICAL_SECTOR_BLOCKED",
    }
    if blockers - structural:
        return READINESS_BLOCKED

    return READINESS_REFERENCE_VALIDATION_READY


def _next_allowed_scope(
    *,
    development_report: dict[str, Any],
    prospective: dict[str, Any],
) -> dict[str, bool]:
    development_complete = development_report.get("status") == "COMPLETE"
    prospective_ready = prospective.get("status") == "READY"
    has_prospective = (
        int(prospective.get("completed_capture_count") or 0) > 0
    )
    return {
        "reference_adequacy_review": (
            development_complete and prospective_ready and has_prospective
        ),
        "prospective_accumulation": prospective_ready,
        "shock_effectiveness": False,
        "sector_effectiveness": False,
        "event_incremental_value": False,
        "execution_policy_comparison": False,
        "holdout_evaluation": False,
        "production_activation": False,
    }


def _coverage_summary(
    *,
    development_report: dict[str, Any],
    prospective_reference: dict[str, Any],
) -> dict[str, Any]:
    summary = development_report.get("summary") or {}
    return {
        "development": {
            "samples": int(summary.get("sample_count") or 0),
            "unique_days": int(
                summary.get("unique_trading_day_count") or 0
            ),
            "unique_tickers": int(
                summary.get("unique_ticker_count") or 0
            ),
        },
        "macro": dict(summary.get("macro") or {}),
        "market_impact": {
            "market_reader": dict(
                summary.get("market_reader") or {}
            ),
            "impact": dict(summary.get("impact") or {}),
        },
        "event": dict(summary.get("event") or {}),
        "sector": dict(summary.get("sector") or {}),
        "composition": dict(summary.get("composition") or {}),
        "prospective": {
            "completed_capture_count": int(
                prospective_reference.get("completed_capture_count") or 0
            ),
            "attachment_count": int(
                prospective_reference.get("attachment_count") or 0
            ),
        },
    }


def _source_availability(
    *,
    development_report: dict[str, Any],
    prospective_reference: dict[str, Any],
) -> dict[str, Any]:
    summary = development_report.get("summary") or {}
    return {
        "development": {
            "status": development_report.get("status"),
            "unavailable_reason": development_report.get(
                "unavailable_reason"
            ),
        },
        "macro": dict(summary.get("macro") or {}),
        "market_reader": dict(summary.get("market_reader") or {}),
        "event": dict(summary.get("event") or {}),
        "prospective": {
            "status": prospective_reference.get("status"),
            "reason": prospective_reference.get("reason"),
        },
    }


def _governance() -> dict[str, Any]:
    return {
        "claim_scope": "REFERENCE_READINESS_ONLY",
        "holdout_access": False,
        "network_access": False,
        "database_write": False,
        "historical_effectiveness_approved": False,
        "execution_policy_evaluation_approved": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
    }


def build_next6e_reference_readiness(
    *,
    entry_gate: dict[str, Any],
    development_report: dict[str, Any],
    prospective_reference: dict[str, Any],
) -> dict[str, Any]:
    """Consolidate S1/S2/S3 reference evidence without effectiveness claims."""

    _validate_entry_gate(entry_gate)
    _validate_development_report(entry_gate, development_report)

    if prospective_reference.get("capture_contract_version") != (
        NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
    ):
        raise ReferenceReadinessError(
            "NEXT-6E-S3 capture contract mismatch."
        )
    if prospective_reference.get("reference_temporal_mode") != (
        REFERENCE_TEMPORAL_MODE
    ):
        raise ReferenceReadinessError(
            "Prospective reference temporal mode mismatch."
        )
    if prospective_reference.get("decision_input") is not False:
        raise ReferenceReadinessError(
            "Prospective reference cannot be a Scanner decision input."
        )
    if prospective_reference.get("signal_time_equivalence") is not False:
        raise ReferenceReadinessError(
            "Signal-time equivalence must remain unproven."
        )

    state = _readiness_state(
        entry_gate=entry_gate,
        development_report=development_report,
        prospective=prospective_reference,
    )
    next_scope = _next_allowed_scope(
        development_report=development_report,
        prospective=prospective_reference,
    )
    governance = _governance()

    development = {
        "report_id": development_report.get("report_id"),
        "report_hash": development_report.get("report_hash"),
        "status": development_report.get("status"),
        "unavailable_reason": development_report.get(
            "unavailable_reason"
        ),
        "scope": development_report.get("scope"),
        "sample_manifest": development_report.get("sample_manifest"),
        "summary": development_report.get("summary"),
        "limitations": list(development_report.get("limitations") or []),
        "source_immutability_verified": development_report.get(
            "source_immutability_verified"
        ),
    }
    prospective = {
        "status": prospective_reference.get("status"),
        "reason": prospective_reference.get("reason"),
        "capture_contract_version": prospective_reference.get(
            "capture_contract_version"
        ),
        "storage_version": prospective_reference.get("storage_version"),
        "reference_temporal_mode": prospective_reference.get(
            "reference_temporal_mode"
        ),
        "decision_input": False,
        "signal_time_equivalence": False,
        "completed_capture_count": int(
            prospective_reference.get("completed_capture_count") or 0
        ),
        "attachment_count": int(
            prospective_reference.get("attachment_count") or 0
        ),
        "capture_status_counts": prospective_reference.get(
            "capture_status_counts"
        ) or {},
        "attachment_sets": list(
            prospective_reference.get("attachment_sets") or []
        ),
    }

    coverage_summary = _coverage_summary(
        development_report=development_report,
        prospective_reference=prospective,
    )
    source_availability = _source_availability(
        development_report=development_report,
        prospective_reference=prospective,
    )

    identity_payload = {
        "contract_version": NEXT6E_REFERENCE_READINESS_CONTRACT_VERSION,
        "entry_gate": {
            "gate_id": entry_gate.get("gate_id"),
            "gate_hash": entry_gate.get("gate_hash"),
        },
        "development_reference": development,
        "prospective_reference": prospective,
        "coverage_summary": coverage_summary,
        "source_availability": source_availability,
        "readiness_state": state,
        "next_allowed_scope": next_scope,
        "blockers": list(entry_gate.get("blockers") or []),
        "limitations": list(_LIMITATIONS),
        "governance": governance,
    }
    report_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "reference_readiness_id": f"NEXT6EREADY-{report_hash[:16]}",
        "reference_readiness_hash": report_hash,
    }


def assess_next6e_reference_readiness(
    *,
    entry_gate: dict[str, Any],
    development_report: dict[str, Any],
    simulation_db: Path,
) -> dict[str, Any]:
    prospective = ProspectiveReferenceSummaryReader(simulation_db).read()
    return build_next6e_reference_readiness(
        entry_gate=entry_gate,
        development_report=development_report,
        prospective_reference=prospective,
    )
