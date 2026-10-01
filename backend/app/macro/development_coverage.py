from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

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
from app.macro.validation_entry_gate import (
    NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION,
    OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY,
)


NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION = (
    "VN_NEXT6E_S2_DEVELOPMENT_REFERENCE_COVERAGE_V1"
)
NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION = (
    "VN_NEXT6E_S2_DEVELOPMENT_DAY_END_CUTOFF_V1"
)

_CLAIM_SCOPE = "DEVELOPMENT_REFERENCE_COVERAGE_ONLY"
_INFRA_REASONS = {
    "STORE_NOT_FOUND",
    "SCHEMA_UNAVAILABLE",
    "SCHEMA_VERSION_MISMATCH",
    "READ_FAILED",
}
_LIMITATIONS = (
    "DAY_END_COVERAGE_NOT_SIGNAL_TIME",
    "DEVELOPMENT_ONLY",
    "EVENT_HISTORICAL_COMPLETENESS_NOT_PROVEN",
    "HISTORICAL_SECTOR_NOT_AVAILABLE",
    "NO_EFFECTIVENESS_CLAIM",
    "NO_EXECUTION_COMPARISON",
    "NO_PREDICTION",
    "REFERENCE_COVERAGE_ONLY",
)


class DevelopmentCoverageAuditError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DevelopmentCoverageSampleReader:
    """Read only frozen Historical Validation day/candidate samples.

    This reader deliberately queries only the run, day and candidate tables
    required by NEXT-6E-S2. It never initializes schema or reads candidate
    outcomes/execution results.
    """

    def __init__(self, simulation_db: Path) -> None:
        self.simulation_db = Path(simulation_db)

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_SAMPLE_STORE_NOT_FOUND",
                f"Simulation DB not found: {self.simulation_db}",
            )
        uri = self.simulation_db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _date_text(value: str, field: str) -> str:
        text = str(value or "").strip()
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_DATE_INVALID",
                f"{field} must be YYYY-MM-DD.",
            ) from exc
        return text

    def read_manifest(
        self,
        *,
        validation_id: str,
        development_start: str,
        development_end: str,
    ) -> dict[str, Any]:
        validation_key = str(validation_id or "").strip()
        if not validation_key:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_VALIDATION_ID_REQUIRED",
                "validation_id is required.",
            )
        start = self._date_text(development_start, "development_start")
        end = self._date_text(development_end, "development_end")
        if start > end:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_DATE_RANGE_INVALID",
                "development_start must be <= development_end.",
            )

        try:
            with self._connect() as conn:
                run = conn.execute(
                    """
                    SELECT id,status,validation_target,scanner_version
                    FROM historical_validation_run
                    WHERE id=?
                    LIMIT 1
                    """,
                    (validation_key,),
                ).fetchone()
                if run is None:
                    raise DevelopmentCoverageAuditError(
                        "DEVELOPMENT_VALIDATION_NOT_FOUND",
                        f"Historical Validation not found: {validation_key}",
                    )
                if str(run["status"]) != "COMPLETED":
                    raise DevelopmentCoverageAuditError(
                        "DEVELOPMENT_VALIDATION_NOT_COMPLETED",
                        "Historical Validation must be COMPLETED.",
                    )
                if str(run["validation_target"]) != "PRODUCTION_SCANNER":
                    raise DevelopmentCoverageAuditError(
                        "DEVELOPMENT_VALIDATION_TARGET_INVALID",
                        "Historical Validation target must be PRODUCTION_SCANNER.",
                    )

                rows = conn.execute(
                    """
                    SELECT
                        c.trading_date,
                        c.market,
                        c.ticker,
                        c.rank,
                        c.result_bucket,
                        c.snapshot_hash
                    FROM historical_validation_candidate AS c
                    JOIN historical_validation_day AS d
                      ON d.validation_id=c.validation_id
                     AND d.trading_date=c.trading_date
                    WHERE c.validation_id=?
                      AND d.status='COMPLETED'
                      AND c.trading_date>=?
                      AND c.trading_date<=?
                    ORDER BY
                        c.trading_date,
                        c.market,
                        c.ticker,
                        c.snapshot_hash
                    """,
                    (validation_key, start, end),
                ).fetchall()
        except DevelopmentCoverageAuditError:
            raise
        except sqlite3.Error as exc:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_SAMPLE_SCHEMA_UNAVAILABLE",
                f"Development sample tables are unavailable: {exc}",
            ) from exc

        raw_samples = [
            {
                "validation_id": validation_key,
                "trading_date": str(row["trading_date"]),
                "market": str(row["market"]).strip().upper(),
                "ticker": str(row["ticker"]).strip().upper(),
                "rank": int(row["rank"]) if row["rank"] is not None else None,
                "result_bucket": str(row["result_bucket"]).strip().upper(),
                "candidate_snapshot_hash": str(row["snapshot_hash"]),
            }
            for row in rows
        ]

        seen: set[tuple[str, str, str, str]] = set()
        samples: list[dict[str, Any]] = []
        for sample in raw_samples:
            identity_key = (
                sample["trading_date"],
                sample["market"],
                sample["ticker"],
                sample["candidate_snapshot_hash"],
            )
            if identity_key in seen:
                continue
            seen.add(identity_key)
            identity_payload = {
                "validation_id": validation_key,
                "trading_date": sample["trading_date"],
                "market": sample["market"],
                "ticker": sample["ticker"],
                "candidate_snapshot_hash": sample[
                    "candidate_snapshot_hash"
                ],
            }
            sample_hash = content_hash(identity_payload)
            samples.append(
                {
                    **sample,
                    "sample_id": f"DEVSAMPLE-{sample_hash[:16]}",
                    "sample_identity_hash": sample_hash,
                }
            )

        samples.sort(
            key=lambda item: (
                item["trading_date"],
                item["market"],
                item["ticker"],
                item["candidate_snapshot_hash"],
            )
        )

        manifest_payload = {
            "contract_version": NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION,
            "validation_id": validation_key,
            "scanner_version": str(run["scanner_version"]),
            "development_start": start,
            "development_end": end,
            "sample_identities": [
                {
                    "sample_id": item["sample_id"],
                    "sample_identity_hash": item["sample_identity_hash"],
                    "trading_date": item["trading_date"],
                    "market": item["market"],
                    "ticker": item["ticker"],
                    "rank": item["rank"],
                    "result_bucket": item["result_bucket"],
                    "candidate_snapshot_hash": item[
                        "candidate_snapshot_hash"
                    ],
                }
                for item in samples
            ],
        }
        manifest_hash = content_hash(manifest_payload)
        return {
            "validation_id": validation_key,
            "validation_target": str(run["validation_target"]),
            "scanner_version": str(run["scanner_version"]),
            "development_start": start,
            "development_end": end,
            "input_sample_count": len(raw_samples),
            "unique_sample_count": len(samples),
            "samples": samples,
            "sample_manifest_hash": manifest_hash,
        }


def _validate_gate(gate: dict[str, Any]) -> None:
    if gate.get("contract_version") != (
        NEXT6E_VALIDATION_ENTRY_GATE_CONTRACT_VERSION
    ):
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_GATE_CONTRACT_MISMATCH",
            "NEXT-6E-S1 gate contract does not match.",
        )
    if gate.get("overall_scope") != OVERALL_SCOPE_REFERENCE_VALIDATION_ONLY:
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_GATE_SCOPE_INVALID",
            "S2 requires REFERENCE_VALIDATION_ONLY scope.",
        )
    if (gate.get("lanes") or {}).get("development_coverage") != "ELIGIBLE":
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_GATE_NOT_ELIGIBLE",
            "Development coverage lane is not ELIGIBLE.",
        )
    governance = gate.get("governance") or {}
    if governance.get("database_write") is not False:
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_GATE_DB_WRITE_NOT_BLOCKED",
            "S2 requires database_write=false.",
        )
    if governance.get("production_decision_approved") is not False:
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_GATE_PRODUCTION_NOT_BLOCKED",
            "S2 requires production_decision_approved=false.",
        )


def _coverage_cutoff(trading_date: str) -> str:
    date.fromisoformat(trading_date)
    return f"{trading_date}T23:59:59+09:00"


def _file_stamp(path: Path) -> tuple[bool, int | None, int | None]:
    value = Path(path)
    if not value.is_file():
        return (False, None, None)
    stat = value.stat()
    return (True, int(stat.st_size), int(stat.st_mtime_ns))


def _source_stamps(
    macro_db: Path,
    market_db: Path,
    simulation_db: Path,
) -> dict[str, tuple[bool, int | None, int | None]]:
    return {
        "macro": _file_stamp(macro_db),
        "market": _file_stamp(market_db),
        "simulation": _file_stamp(simulation_db),
    }


def _count(counter: Counter[str], value: Any) -> None:
    text = str(value or "").strip()
    if text:
        counter[text] += 1


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    bucket = Counter[str]()
    macro_status = Counter[str]()
    macro_reason = Counter[str]()
    macro_historical = Counter[str]()
    market_reader_status = Counter[str]()
    market_reader_reason = Counter[str]()
    impact_status = Counter[str]()
    impact_reason = Counter[str]()
    event_reader_status = Counter[str]()
    event_reader_reason = Counter[str]()
    event_status = Counter[str]()
    event_diagnostics = Counter[str]()
    sector_status = Counter[str]()
    composition_status = Counter[str]()
    composition_limitations = Counter[str]()

    total_reference_count = 0
    total_projected_reference_count = 0

    for sample in samples:
        _count(bucket, sample.get("result_bucket"))

        macro = sample["macro"]
        _count(macro_status, macro.get("status"))
        _count(macro_reason, macro.get("reason"))
        macro_historical[
            "true" if macro.get("historical_evaluation_eligible") else "false"
        ] += 1

        market_reader = sample["market_reader"]
        _count(market_reader_status, market_reader.get("status"))
        _count(market_reader_reason, market_reader.get("reason"))

        impact = sample["impact"]
        _count(impact_status, impact.get("status"))
        _count(impact_reason, impact.get("reason"))

        event = sample["event"]
        _count(event_reader_status, event.get("reader_status"))
        _count(event_reader_reason, event.get("reader_reason"))
        _count(event_status, event.get("status"))
        total_reference_count += int(event.get("reference_count") or 0)
        total_projected_reference_count += int(
            event.get("projected_reference_count") or 0
        )
        for key, value in (event.get("diagnostics") or {}).items():
            event_diagnostics[str(key)] += int(value or 0)

        _count(
            sector_status,
            (sample.get("sector") or {}).get(
                "historical_sector_status"
            ),
        )

        composition = sample["composition"]
        _count(composition_status, composition.get("status"))
        for limitation in composition.get("limitations") or []:
            _count(composition_limitations, limitation)

    unique_days = sorted({item["trading_date"] for item in samples})
    unique_tickers = sorted(
        {(item["market"], item["ticker"]) for item in samples}
    )

    return {
        "sample_count": len(samples),
        "unique_trading_day_count": len(unique_days),
        "unique_ticker_count": len(unique_tickers),
        "result_bucket_counts": _counter_dict(bucket),
        "macro": {
            "status_counts": _counter_dict(macro_status),
            "reason_counts": _counter_dict(macro_reason),
            "historical_evaluation_eligible_counts": _counter_dict(
                macro_historical
            ),
        },
        "market_reader": {
            "status_counts": _counter_dict(market_reader_status),
            "reason_counts": _counter_dict(market_reader_reason),
        },
        "impact": {
            "status_counts": _counter_dict(impact_status),
            "reason_counts": _counter_dict(impact_reason),
        },
        "event": {
            "reader_status_counts": _counter_dict(event_reader_status),
            "reader_reason_counts": _counter_dict(event_reader_reason),
            "status_counts": _counter_dict(event_status),
            "total_reference_count": total_reference_count,
            "total_projected_reference_count": (
                total_projected_reference_count
            ),
            "diagnostic_totals": _counter_dict(event_diagnostics),
        },
        "sector": {
            "historical_sector_status_counts": _counter_dict(
                sector_status
            ),
        },
        "composition": {
            "status_counts": _counter_dict(composition_status),
            "limitation_counts": _counter_dict(composition_limitations),
        },
    }


def _governance() -> dict[str, Any]:
    return {
        "claim_scope": _CLAIM_SCOPE,
        "historical_effectiveness_approved": False,
        "execution_policy_evaluation_approved": False,
        "prediction_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "production_decision_approved": False,
        "network_access": False,
        "database_write": False,
    }


def _final_report(
    *,
    status: str,
    unavailable_reason: str | None,
    gate: dict[str, Any],
    manifest: dict[str, Any],
    samples: list[dict[str, Any]],
    source_immutability_verified: bool,
) -> dict[str, Any]:
    summary = _summary(samples)
    governance = _governance()
    limitations = list(_LIMITATIONS)
    identity_payload = {
        "contract_version": NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION,
        "status": status,
        "unavailable_reason": unavailable_reason,
        "entry_gate_id": gate.get("gate_id"),
        "entry_gate_hash": gate.get("gate_hash"),
        "validation_id": manifest["validation_id"],
        "scanner_version": manifest["scanner_version"],
        "development_start": manifest["development_start"],
        "development_end": manifest["development_end"],
        "cutoff_policy_version": (
            NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION
        ),
        "sample_manifest_hash": manifest["sample_manifest_hash"],
        "ordered_sample_result_hashes": [
            item["sample_result_hash"] for item in samples
        ],
        "summary": summary,
        "limitations": limitations,
        "governance": governance,
        "source_immutability_verified": source_immutability_verified,
    }
    report_hash = content_hash(identity_payload)
    return {
        "contract_version": NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION,
        "report_id": f"DEVREFCOV-{report_hash[:16]}",
        "report_hash": report_hash,
        "status": status,
        "unavailable_reason": unavailable_reason,
        "entry_gate": {
            "gate_id": gate.get("gate_id"),
            "gate_hash": gate.get("gate_hash"),
        },
        "scope": {
            "validation_id": manifest["validation_id"],
            "scanner_version": manifest["scanner_version"],
            "development_start": manifest["development_start"],
            "development_end": manifest["development_end"],
            "cutoff_policy_version": (
                NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION
            ),
        },
        "sample_manifest": {
            "input_sample_count": manifest["input_sample_count"],
            "unique_sample_count": manifest["unique_sample_count"],
            "sample_manifest_hash": manifest["sample_manifest_hash"],
        },
        "samples": samples,
        "summary": summary,
        "limitations": limitations,
        "governance": governance,
        "source_immutability_verified": source_immutability_verified,
    }


def audit_development_reference_coverage(
    *,
    entry_gate: dict[str, Any],
    validation_id: str,
    development_start: str,
    development_end: str,
    macro_db: Path,
    market_db: Path,
    simulation_db: Path,
    sample_reader_factory: Callable[
        [Path], DevelopmentCoverageSampleReader
    ] = DevelopmentCoverageSampleReader,
    macro_reader_factory: Callable[[Path], Any] = LocalMacroReader,
    market_reader_factory: Callable[[Path], Any] = LocalMarketImpactReader,
    event_reader_factory: Callable[[Path], Any] = EventEvidenceAsOfReader,
    context_builder: Callable[..., dict[str, Any]] = build_macro_context,
    impact_builder: Callable[..., dict[str, Any]] = build_market_stock_impact,
    sector_builder: Callable[[], dict[str, Any]] = build_sector_route,
    composition_builder: Callable[
        ..., dict[str, Any]
    ] = build_macro_event_reference_composition,
) -> dict[str, Any]:
    _validate_gate(entry_gate)

    macro_path = Path(macro_db)
    market_path = Path(market_db)
    simulation_path = Path(simulation_db)
    before_stamps = _source_stamps(
        macro_path,
        market_path,
        simulation_path,
    )

    sample_reader = sample_reader_factory(simulation_path)
    manifest = sample_reader.read_manifest(
        validation_id=validation_id,
        development_start=development_start,
        development_end=development_end,
    )

    expected_scanner = str(
        (entry_gate.get("baseline") or {}).get("scanner_version") or ""
    )
    if not expected_scanner or manifest["scanner_version"] != expected_scanner:
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_SCANNER_BASELINE_MISMATCH",
            "Historical sample Scanner version does not match the S1 gate.",
        )

    if not manifest["samples"]:
        manifest_after = sample_reader.read_manifest(
            validation_id=validation_id,
            development_start=development_start,
            development_end=development_end,
        )
        if (
            manifest_after["sample_manifest_hash"]
            != manifest["sample_manifest_hash"]
        ):
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_SAMPLE_CHANGED_DURING_AUDIT",
                "Development sample manifest changed during audit.",
            )
        after_stamps = _source_stamps(
            macro_path,
            market_path,
            simulation_path,
        )
        if after_stamps != before_stamps:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_SOURCE_CHANGED_DURING_AUDIT",
                "A source database changed during the read-only audit.",
            )
        return _final_report(
            status="NO_DEVELOPMENT_SAMPLES",
            unavailable_reason=None,
            gate=entry_gate,
            manifest=manifest,
            samples=[],
            source_immutability_verified=True,
        )

    macro_reader = macro_reader_factory(macro_path)
    market_reader = market_reader_factory(market_path)
    event_reader = event_reader_factory(simulation_path)
    samples: list[dict[str, Any]] = []
    fatal_reason: str | None = None

    for sample in manifest["samples"]:
        cutoff = _coverage_cutoff(sample["trading_date"])
        market = str(sample["market"]).upper()
        try:
            ticker = normalize_stock_code(str(sample["ticker"]))
            context = context_builder(
                reader=macro_reader,
                decision_cutoff=cutoff,
                usage="REFERENCE_SHADOW",
            )
        except ValueError as exc:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_REFERENCE_CONTRACT_ERROR",
                str(exc),
            ) from exc

        macro_reason = str(
            context.get("reason")
            or (context.get("availability") or {}).get("reader_reason")
            or ""
        ) or None
        if (
            context.get("status") == "UNAVAILABLE"
            and macro_reason in _INFRA_REASONS
        ):
            fatal_reason = f"MACRO_SOURCE_UNAVAILABLE:{macro_reason}"
            break

        try:
            market_input = market_reader.read_pair_as_of(
                market=market,
                ticker=ticker,
                end_date=sample["trading_date"],
            )
        except ValueError as exc:
            raise DevelopmentCoverageAuditError(
                "DEVELOPMENT_REFERENCE_CONTRACT_ERROR",
                str(exc),
            ) from exc

        market_reason = (
            str(market_input.get("reason"))
            if market_input.get("reason")
            else None
        )
        if market_reason in _INFRA_REASONS:
            fatal_reason = f"MARKET_SOURCE_UNAVAILABLE:{market_reason}"
            break

        impact: dict[str, Any] | None = None
        if market_input.get("status") == "COMPLETE":
            try:
                impact = impact_builder(
                    stock_rows=market_input.get("stock_rows") or [],
                    market_rows=market_input.get("market_rows") or [],
                    market=market,
                    ticker=ticker,
                    end_date=sample["trading_date"],
                    macro_context_id=context["context_id"],
                    macro_context_hash=context["context_hash"],
                    decision_cutoff=context["decision_cutoff"],
                    sector_temporal_status=None,
                )
            except ValueError as exc:
                raise DevelopmentCoverageAuditError(
                    "DEVELOPMENT_REFERENCE_CONTRACT_ERROR",
                    str(exc),
                ) from exc

        event_product: dict[str, Any] | None = None
        event_reader_status = "AVAILABLE"
        event_reader_reason: str | None = None
        try:
            event_product = event_reader.stock_reference_as_of(
                ticker,
                market,
                context["decision_cutoff"],
            )
        except EventEvidenceContractError as exc:
            event_reader_status = "UNAVAILABLE"
            event_reader_reason = exc.code

        sector = sector_builder()
        composition: dict[str, Any] | None = None
        if impact is not None:
            try:
                composition = composition_builder(
                    macro_context=context,
                    impact=impact,
                    sector_route=sector,
                    event_product=event_product,
                )
            except ValueError as exc:
                raise DevelopmentCoverageAuditError(
                    "DEVELOPMENT_REFERENCE_CONTRACT_ERROR",
                    str(exc),
                ) from exc

        event_evidence = (
            (event_product or {}).get("event_evidence") or {}
        )
        event_diagnostics = {
            str(key): int(value or 0)
            for key, value in (
                event_evidence.get("diagnostics") or {}
            ).items()
        }
        impact_status = (
            str(impact.get("status"))
            if impact is not None
            else "NOT_BUILT_SOURCE_UNAVAILABLE"
        )
        impact_reason = (
            impact.get("reason")
            if impact is not None
            else market_reason or "MARKET_INPUT_UNAVAILABLE"
        )
        composition_status = (
            str(composition.get("status"))
            if composition is not None
            else "NOT_BUILT_SOURCE_UNAVAILABLE"
        )
        composition_limitations = (
            list(composition.get("limitations") or [])
            if composition is not None
            else []
        )

        sample_payload = {
            "sample_id": sample["sample_id"],
            "sample_identity_hash": sample["sample_identity_hash"],
            "trading_date": sample["trading_date"],
            "market": market,
            "ticker": ticker,
            "result_bucket": sample["result_bucket"],
            "coverage_cutoff": cutoff,
            "macro": {
                "status": str(context.get("status") or "UNAVAILABLE"),
                "reason": macro_reason,
                "historical_evaluation_eligible": bool(
                    (context.get("availability") or {}).get(
                        "historical_evaluation_eligible"
                    )
                ),
                "time_qualities": sorted(
                    {
                        str(value)
                        for value in (
                            (context.get("availability") or {}).get(
                                "time_qualities"
                            )
                            or []
                        )
                        if str(value)
                    }
                ),
            },
            "market_reader": {
                "status": str(
                    market_input.get("status") or "UNAVAILABLE"
                ),
                "reason": market_reason,
            },
            "impact": {
                "status": impact_status,
                "reason": impact_reason,
            },
            "event": {
                "reader_status": event_reader_status,
                "reader_reason": event_reader_reason,
                "projection_mode": EVENT_REFERENCE_AS_OF_MODE,
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
                "diagnostics": event_diagnostics,
            },
            "sector": {
                "historical_sector_status": str(
                    sector.get("historical_sector_status")
                    or "UNAVAILABLE"
                ),
            },
            "composition": {
                "status": composition_status,
                "limitations": composition_limitations,
            },
        }
        sample_result_hash = content_hash(sample_payload)
        samples.append(
            {
                **sample_payload,
                "sample_result_hash": sample_result_hash,
            }
        )

    manifest_after = sample_reader.read_manifest(
        validation_id=validation_id,
        development_start=development_start,
        development_end=development_end,
    )
    if (
        manifest_after["sample_manifest_hash"]
        != manifest["sample_manifest_hash"]
    ):
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_SAMPLE_CHANGED_DURING_AUDIT",
            "Development sample manifest changed during audit.",
        )

    after_stamps = _source_stamps(
        macro_path,
        market_path,
        simulation_path,
    )
    if after_stamps != before_stamps:
        raise DevelopmentCoverageAuditError(
            "DEVELOPMENT_SOURCE_CHANGED_DURING_AUDIT",
            "A source database changed during the read-only audit.",
        )

    if fatal_reason:
        return _final_report(
            status="AUDIT_UNAVAILABLE",
            unavailable_reason=fatal_reason,
            gate=entry_gate,
            manifest=manifest,
            samples=samples,
            source_immutability_verified=True,
        )

    return _final_report(
        status="COMPLETE",
        unavailable_reason=None,
        gate=entry_gate,
        manifest=manifest,
        samples=samples,
        source_immutability_verified=True,
    )
