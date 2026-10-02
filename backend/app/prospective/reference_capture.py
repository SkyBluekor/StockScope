from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.stock_code import normalize_stock_code
from app.event_evidence.asof import (
    EVENT_REFERENCE_AS_OF_MODE,
    EventEvidenceAsOfReader,
)
from app.event_evidence.errors import EventEvidenceContractError
from app.macro.context import build_macro_context
from app.macro.event_composition import (
    build_macro_event_reference_composition,
)
from app.macro.identity import content_hash
from app.macro.impact import (
    LocalMarketImpactReader,
    build_market_stock_impact,
)
from app.macro.reader import LocalMacroReader
from app.macro.sector_route import build_sector_route


NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION = (
    "VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_CAPTURE_V1"
)
NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION = (
    "VN_NEXT6E_S3_PROSPECTIVE_REFERENCE_STORAGE_V1"
)
NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION = (
    "VN_NEXT6E_S3_CAPTURE_COMPLETED_AT_CUTOFF_V1"
)
REFERENCE_TEMPORAL_MODE = "POST_SCANNER_CAPTURE"

_REFERENCE_TABLES = {
    "prospective_reference_schema_meta",
    "prospective_reference_capture",
    "prospective_reference_attachment",
}
_MARKET_INFRA_REASONS = {
    "STORE_NOT_FOUND",
    "SCHEMA_UNAVAILABLE",
    "READ_FAILED",
}
_LIMITATIONS = [
    "EVENT_HISTORICAL_COMPLETENESS_NOT_PROVEN",
    "HISTORICAL_SECTOR_NOT_AVAILABLE",
    "NO_CAUSAL_ATTRIBUTION",
    "NO_PREDICTION",
    "NOT_SCANNER_DECISION_INPUT",
    "POST_SCANNER_CAPTURE",
    "REFERENCE_ONLY",
    "SIGNAL_TIME_EQUIVALENCE_NOT_PROVEN",
]


class ProspectiveReferenceCaptureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProspectiveReferenceCaptureService:
    """Attach post-Scanner Macro/Event references to frozen Prospective samples.

    The source Prospective capture is already committed before this service runs.
    All Macro/Market/Event reads happen before the final attachment write
    transaction, so Event Evidence can safely read the same simulation DB.
    """

    def __init__(
        self,
        *,
        simulation_db: Path,
        market_db: Path,
        macro_db: Path,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.market_db = Path(market_db)
        self.macro_db = Path(macro_db)

    def _connect_readonly(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_MIGRATION_REQUIRED",
                f"Simulation DB not found: {self.simulation_db}",
            )
        uri = self.simulation_db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA query_only=ON")
        return conn

    def _connect_write(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_MIGRATION_REQUIRED",
                f"Simulation DB not found: {self.simulation_db}",
            )
        conn = sqlite3.connect(self.simulation_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=20000")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _require_reference_ready(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        if not _REFERENCE_TABLES.issubset(self._tables(conn)):
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_MIGRATION_REQUIRED",
                "NEXT-6E-S3 prospective reference migration is required.",
            )
        row = conn.execute(
            """
            SELECT value
            FROM prospective_reference_schema_meta
            WHERE key='schema_version'
            LIMIT 1
            """
        ).fetchone()
        if (
            row is None
            or str(row["value"])
            != NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
        ):
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_SCHEMA_UNSUPPORTED",
                "Unsupported prospective reference schema version.",
            )

    @staticmethod
    def _source_from_conn(
        conn: sqlite3.Connection,
        capture_id: str,
    ) -> dict[str, Any]:
        capture = conn.execute(
            """
            SELECT
                id,status,request_json,requested_as_of,actual_data_date,
                scanner_version,source_execution_key,source_snapshot_hash,
                result_hash,completed_at
            FROM prospective_capture_run
            WHERE id=?
            LIMIT 1
            """,
            (capture_id,),
        ).fetchone()
        if capture is None:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_CAPTURE_NOT_FOUND",
                f"Prospective capture not found: {capture_id}",
            )

        rows = conn.execute(
            """
            SELECT
                capture_run_id,sample_index,market,ticker,signal_date,
                snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id=?
            ORDER BY sample_index
            """,
            (capture_id,),
        ).fetchall()

        try:
            request = json.loads(str(capture["request_json"]))
        except json.JSONDecodeError:
            request = {}
        requested_as_of = (
            capture["requested_as_of"]
            if capture["requested_as_of"] not in (None, "")
            else request.get("requested_as_of")
        )

        samples = [
            {
                "capture_run_id": str(row["capture_run_id"]),
                "sample_index": int(row["sample_index"]),
                "market": str(row["market"]).strip().upper(),
                "ticker": str(row["ticker"]).strip().upper(),
                "signal_date": str(row["signal_date"] or ""),
                "source_snapshot_hash": str(row["snapshot_hash"]),
            }
            for row in rows
        ]
        manifest_payload = {
            "capture_run_id": str(capture["id"]),
            "status": str(capture["status"]),
            "requested_as_of": requested_as_of,
            "actual_data_date": capture["actual_data_date"],
            "scanner_version": capture["scanner_version"],
            "source_execution_key": capture["source_execution_key"],
            "source_snapshot_hash": capture["source_snapshot_hash"],
            "result_hash": capture["result_hash"],
            "completed_at": capture["completed_at"],
            "samples": samples,
        }
        return {
            **manifest_payload,
            "source_manifest_hash": content_hash(manifest_payload),
        }

    def _read_source(self, capture_id: str) -> dict[str, Any]:
        try:
            with self._connect_readonly() as conn:
                return self._source_from_conn(conn, capture_id)
        except ProspectiveReferenceCaptureError:
            raise
        except sqlite3.Error as exc:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_SOURCE_READ_FAILED",
                str(exc),
            ) from exc

    def _existing_capture(
        self,
        capture_id: str,
    ) -> dict[str, Any] | None:
        try:
            with self._connect_readonly() as conn:
                self._require_reference_ready(conn)
                row = conn.execute(
                    """
                    SELECT *
                    FROM prospective_reference_capture
                    WHERE capture_run_id=?
                    LIMIT 1
                    """,
                    (capture_id,),
                ).fetchone()
        except ProspectiveReferenceCaptureError:
            raise
        except sqlite3.Error as exc:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_READ_FAILED",
                str(exc),
            ) from exc
        if row is None:
            return None
        return {
            "status": str(row["status"]),
            "capture_id": str(row["capture_run_id"]),
            "reference_cutoff": row["reference_cutoff"],
            "attachment_count": int(row["attachment_count"] or 0),
            "attachment_set_hash": row["attachment_set_hash"],
            "source_manifest_hash": row["source_manifest_hash"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
        }

    @staticmethod
    def _skip_status(source: dict[str, Any]) -> str | None:
        status = str(source.get("status") or "")
        if status == "DUPLICATE":
            return "SKIPPED_DUPLICATE"
        if status == "PARTIAL":
            return "SKIPPED_SOURCE_PARTIAL"
        if status in {"FAILED", "CANCELLED", "INTERRUPTED"}:
            return f"SKIPPED_SOURCE_{status}"
        if status != "COMPLETE":
            return "SKIPPED_SOURCE_NOT_COMPLETE"
        if source.get("requested_as_of") not in (None, ""):
            return "SKIPPED_EXPLICIT_AS_OF"
        return None

    @staticmethod
    def _governance() -> dict[str, Any]:
        return {
            "claim_scope": "POST_SCANNER_REFERENCE_CAPTURE_ONLY",
            "decision_input": False,
            "historical_effectiveness_approved": False,
            "execution_policy_evaluation_approved": False,
            "prediction_approved": False,
            "strategy_input_approved": False,
            "scanner_input_approved": False,
            "risk_gate_input_approved": False,
            "holdings_plan_input_approved": False,
            "production_decision_approved": False,
            "network_access": False,
        }

    def _project_sample(
        self,
        *,
        sample: dict[str, Any],
        reference_cutoff: str,
        macro_reader: LocalMacroReader,
        market_reader: LocalMarketImpactReader,
        event_reader: EventEvidenceAsOfReader,
    ) -> dict[str, Any]:
        market = str(sample["market"]).upper()
        ticker = normalize_stock_code(str(sample["ticker"]))
        signal_date = str(sample.get("signal_date") or "")
        if not signal_date:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_SIGNAL_DATE_MISSING",
                "Prospective sample signal_date is required.",
            )

        try:
            context = build_macro_context(
                reader=macro_reader,
                decision_cutoff=reference_cutoff,
                usage="REFERENCE_SHADOW",
            )
        except ValueError as exc:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_MACRO_CONTRACT_ERROR",
                str(exc),
            ) from exc

        market_input = market_reader.read_pair_as_of(
            market=market,
            ticker=ticker,
            end_date=signal_date,
        )
        market_reader_status = str(
            market_input.get("status") or "UNAVAILABLE"
        )
        market_reader_reason = (
            str(market_input.get("reason"))
            if market_input.get("reason")
            else None
        )

        impact: dict[str, Any] | None = None
        impact_status = "NOT_BUILT_MACRO_UNAVAILABLE"
        impact_reason: str | None = (
            str(context.get("reason") or "MACRO_CONTEXT_UNAVAILABLE")
            if context.get("status") == "UNAVAILABLE"
            else None
        )
        if context.get("status") != "UNAVAILABLE":
            if market_reader_reason in _MARKET_INFRA_REASONS:
                impact_status = "NOT_BUILT_SOURCE_UNAVAILABLE"
                impact_reason = market_reader_reason
            else:
                try:
                    impact = build_market_stock_impact(
                        stock_rows=market_input.get("stock_rows") or [],
                        market_rows=market_input.get("market_rows") or [],
                        market=market,
                        ticker=ticker,
                        end_date=signal_date,
                        macro_context_id=context["context_id"],
                        macro_context_hash=context["context_hash"],
                        decision_cutoff=context["decision_cutoff"],
                        sector_temporal_status=None,
                    )
                except ValueError as exc:
                    raise ProspectiveReferenceCaptureError(
                        "PROSPECTIVE_REFERENCE_IMPACT_CONTRACT_ERROR",
                        str(exc),
                    ) from exc
                impact_status = str(impact.get("status") or "UNAVAILABLE")
                impact_reason = (
                    str(impact.get("reason"))
                    if impact.get("reason")
                    else None
                )

        event_product: dict[str, Any] | None = None
        event_reader_status = "AVAILABLE"
        event_reader_reason: str | None = None
        try:
            event_product = event_reader.stock_reference_as_of(
                ticker,
                market,
                reference_cutoff,
            )
        except EventEvidenceContractError as exc:
            event_reader_status = "UNAVAILABLE"
            event_reader_reason = exc.code

        sector = build_sector_route()
        composition: dict[str, Any] | None = None
        if context.get("status") != "UNAVAILABLE" and impact is not None:
            try:
                composition = build_macro_event_reference_composition(
                    macro_context=context,
                    impact=impact,
                    sector_route=sector,
                    event_product=event_product,
                )
            except ValueError as exc:
                raise ProspectiveReferenceCaptureError(
                    "PROSPECTIVE_REFERENCE_COMPOSITION_CONTRACT_ERROR",
                    str(exc),
                ) from exc

        event_evidence = (
            (event_product or {}).get("event_evidence") or {}
        )
        projection = {
            "contract_version": (
                NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
            ),
            "reference_temporal_mode": REFERENCE_TEMPORAL_MODE,
            "decision_input": False,
            "signal_time_equivalence": False,
            "capture_run_id": sample["capture_run_id"],
            "sample_index": int(sample["sample_index"]),
            "source_snapshot_hash": sample["source_snapshot_hash"],
            "market": market,
            "ticker": ticker,
            "signal_date": signal_date,
            "reference_cutoff": reference_cutoff,
            "cutoff_policy_version": (
                NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION
            ),
            "macro": {
                "context_id": context.get("context_id"),
                "context_hash": context.get("context_hash"),
                "status": context.get("status"),
                "reason": context.get("reason"),
                "usage_mode": context.get("usage_mode"),
            },
            "market_reader": {
                "status": market_reader_status,
                "reason": market_reader_reason,
            },
            "impact": {
                "impact_id": impact.get("impact_id") if impact else None,
                "impact_hash": impact.get("impact_hash") if impact else None,
                "status": impact_status,
                "reason": impact_reason,
            },
            "event": {
                "reader_status": event_reader_status,
                "reader_reason": event_reader_reason,
                "projection_mode": EVENT_REFERENCE_AS_OF_MODE,
                "projection_id": (
                    event_product.get("projection_id")
                    if event_product
                    else None
                ),
                "projection_hash": (
                    event_product.get("projection_hash")
                    if event_product
                    else None
                ),
                "status": str(
                    event_evidence.get("status")
                    or (
                        "SOURCE_UNAVAILABLE"
                        if event_reader_status == "UNAVAILABLE"
                        else "NO_VALIDATED_EVIDENCE"
                    )
                ),
                "reference_count": int(
                    event_evidence.get("reference_count") or 0
                ),
                "projected_reference_count": int(
                    event_evidence.get("projected_reference_count") or 0
                ),
            },
            "sector": {
                "historical_sector_status": sector.get(
                    "historical_sector_status"
                ),
                "historical_impact_mode": sector.get(
                    "historical_impact_mode"
                ),
                "prospective_sector_status": sector.get(
                    "prospective_sector_status"
                ),
            },
            "composition": {
                "composition_id": (
                    composition.get("composition_id")
                    if composition
                    else None
                ),
                "composition_hash": (
                    composition.get("composition_hash")
                    if composition
                    else None
                ),
                "status": (
                    str(composition.get("status"))
                    if composition
                    else (
                        "NOT_BUILT_MACRO_UNAVAILABLE"
                        if context.get("status") == "UNAVAILABLE"
                        else "NOT_BUILT_SOURCE_UNAVAILABLE"
                    )
                ),
                "limitations": (
                    list(composition.get("limitations") or [])
                    if composition
                    else []
                ),
            },
            "limitations": list(_LIMITATIONS),
            "governance": self._governance(),
        }
        attachment_hash = content_hash(projection)
        return {
            **projection,
            "attachment_id": f"PREFATT-{attachment_hash[:16]}",
            "attachment_hash": attachment_hash,
        }

    def _write_attachments(
        self,
        *,
        source_before: dict[str, Any],
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        attachment_set_payload = [
            {
                "sample_index": int(item["sample_index"]),
                "attachment_hash": item["attachment_hash"],
            }
            for item in sorted(
                attachments,
                key=lambda item: int(item["sample_index"]),
            )
        ]
        attachment_set_hash = content_hash(attachment_set_payload)
        reference_cutoff = str(source_before["completed_at"])

        conn = self._connect_write()
        try:
            self._require_reference_ready(conn)
            conn.execute("BEGIN IMMEDIATE")

            source_after = self._source_from_conn(
                conn,
                str(source_before["capture_run_id"]),
            )
            if (
                source_after["source_manifest_hash"]
                != source_before["source_manifest_hash"]
            ):
                raise ProspectiveReferenceCaptureError(
                    "PROSPECTIVE_REFERENCE_SOURCE_CHANGED",
                    "Prospective source changed during reference projection.",
                )

            existing = conn.execute(
                """
                SELECT status,attachment_count,attachment_set_hash
                FROM prospective_reference_capture
                WHERE capture_run_id=?
                LIMIT 1
                """,
                (source_before["capture_run_id"],),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["status"]) == "COMPLETE"
                    and int(existing["attachment_count"] or 0)
                    == len(attachments)
                    and str(existing["attachment_set_hash"] or "")
                    == attachment_set_hash
                ):
                    conn.rollback()
                    return {
                        "status": "COMPLETE",
                        "capture_id": source_before["capture_run_id"],
                        "reference_cutoff": reference_cutoff,
                        "attachment_count": len(attachments),
                        "attachment_set_hash": attachment_set_hash,
                    }
                raise ProspectiveReferenceCaptureError(
                    "PROSPECTIVE_REFERENCE_SOURCE_CONFLICT",
                    "Existing reference attachment set conflicts with source.",
                )

            for item in attachments:
                source_sample = next(
                    (
                        sample
                        for sample in source_after["samples"]
                        if int(sample["sample_index"])
                        == int(item["sample_index"])
                    ),
                    None,
                )
                if (
                    source_sample is None
                    or source_sample["source_snapshot_hash"]
                    != item["source_snapshot_hash"]
                ):
                    raise ProspectiveReferenceCaptureError(
                        "PROSPECTIVE_REFERENCE_SOURCE_CONFLICT",
                        "Source sample hash does not match reference attachment.",
                    )

            conn.execute(
                """
                INSERT INTO prospective_reference_capture(
                    capture_run_id,capture_contract_version,storage_version,
                    status,reference_cutoff,cutoff_policy_version,
                    reference_temporal_mode,source_sample_count,
                    attachment_count,attachment_set_hash,error_code,
                    error_message,created_at,completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_before["capture_run_id"],
                    NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
                    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
                    "COMPLETE",
                    reference_cutoff,
                    NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION,
                    REFERENCE_TEMPORAL_MODE,
                    len(source_before["samples"]),
                    len(attachments),
                    attachment_set_hash,
                    source_before["source_manifest_hash"],
                    None,
                    None,
                    reference_cutoff,
                    reference_cutoff,
                ),
            )
            for item in attachments:
                conn.execute(
                    """
                    INSERT INTO prospective_reference_attachment(
                        capture_run_id,sample_index,attachment_id,
                        attachment_hash,source_snapshot_hash,market,ticker,
                        signal_date,reference_cutoff,projection_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        item["capture_run_id"],
                        int(item["sample_index"]),
                        item["attachment_id"],
                        item["attachment_hash"],
                        item["source_snapshot_hash"],
                        item["market"],
                        item["ticker"],
                        item["signal_date"],
                        reference_cutoff,
                        json.dumps(
                            item,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        reference_cutoff,
                    ),
                )

            fk_errors = conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if fk_errors:
                raise ProspectiveReferenceCaptureError(
                    "PROSPECTIVE_REFERENCE_FOREIGN_KEY_ERROR",
                    "Foreign key validation failed for reference attachments.",
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "status": "COMPLETE",
            "capture_id": source_before["capture_run_id"],
            "reference_cutoff": reference_cutoff,
            "attachment_count": len(attachments),
            "attachment_set_hash": attachment_set_hash,
        }

    def capture(self, capture_id: str) -> dict[str, Any]:
        capture_key = str(capture_id or "").strip()
        if not capture_key:
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_CAPTURE_ID_REQUIRED",
                "capture_id is required.",
            )

        source = self._read_source(capture_key)
        skip = self._skip_status(source)
        if skip is not None:
            return {
                "status": skip,
                "capture_id": capture_key,
                "attachment_count": 0,
            }

        if not source.get("completed_at"):
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_CUTOFF_MISSING",
                "Completed Prospective capture has no completed_at cutoff.",
            )

        existing = self._existing_capture(capture_key)
        if existing is not None:
            if (
                existing["status"] == "COMPLETE"
                and existing.get("source_manifest_hash")
                == source["source_manifest_hash"]
            ):
                return existing
            if existing["status"] == "COMPLETE":
                raise ProspectiveReferenceCaptureError(
                    "PROSPECTIVE_REFERENCE_SOURCE_CONFLICT",
                    "Existing reference capture source identity has changed.",
                )
            raise ProspectiveReferenceCaptureError(
                "PROSPECTIVE_REFERENCE_SOURCE_CONFLICT",
                "Existing reference capture is not reusable.",
            )

        macro_reader = LocalMacroReader(self.macro_db)
        market_reader = LocalMarketImpactReader(self.market_db)
        event_reader = EventEvidenceAsOfReader(self.simulation_db)
        reference_cutoff = str(source["completed_at"])

        attachments = [
            self._project_sample(
                sample=sample,
                reference_cutoff=reference_cutoff,
                macro_reader=macro_reader,
                market_reader=market_reader,
                event_reader=event_reader,
            )
            for sample in source["samples"]
        ]
        return self._write_attachments(
            source_before=source,
            attachments=attachments,
        )

    def try_capture(self, capture_id: str) -> dict[str, Any]:
        try:
            return self.capture(capture_id)
        except ProspectiveReferenceCaptureError as exc:
            if exc.code in {
                "PROSPECTIVE_REFERENCE_MIGRATION_REQUIRED",
                "PROSPECTIVE_REFERENCE_SCHEMA_UNSUPPORTED",
            }:
                return {
                    "status": "NOT_READY",
                    "capture_id": capture_id,
                    "code": exc.code,
                    "message": exc.message,
                }
            return {
                "status": "FAILED",
                "capture_id": capture_id,
                "code": exc.code,
                "message": exc.message,
            }
        except Exception as exc:
            return {
                "status": "FAILED",
                "capture_id": capture_id,
                "code": "PROSPECTIVE_REFERENCE_CAPTURE_FAILED",
                "message": str(exc),
            }
