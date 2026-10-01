from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.event_evidence.errors import EventEvidenceContractError
from app.macro.development_coverage import (
    NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION,
    NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION,
    DevelopmentCoverageAuditError,
    DevelopmentCoverageSampleReader,
    audit_development_reference_coverage,
)
from app.macro.identity import content_hash
from app.macro.validation_entry_gate import (
    build_next6e_validation_entry_gate,
)


ROOT = Path(__file__).resolve().parents[2]


def _gate() -> dict[str, object]:
    return build_next6e_validation_entry_gate(
        scanner_version=StockScannerService.VERSION,
        macro_numeric_policy="NONE",
        reference_adequacy="UNRESOLVED",
        rate_spike_calibration_status="UNCALIBRATED",
        historical_sector_status="BLOCKED_EXTERNAL_SOURCE",
        historical_impact_mode="MARKET_STOCK_ONLY",
        prospective_sector_status="NOT_STARTED",
        p6_asof_mode="SYSTEM_OBSERVED_AS_OF",
        p6_historical_completeness_proven=False,
        p6_historical_evaluation_approved=False,
        prediction_status="NOT_VALIDATED",
    )


def _create_simulation_db(path: Path, *, scanner_version: str | None = None) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE historical_validation_run (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                validation_target TEXT NOT NULL,
                scanner_version TEXT NOT NULL
            );

            CREATE TABLE historical_validation_day (
                validation_id TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(validation_id,trading_date)
            );

            CREATE TABLE historical_validation_candidate (
                validation_id TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                rank INTEGER,
                result_bucket TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                PRIMARY KEY(validation_id,trading_date,market,ticker)
            );

            CREATE TABLE historical_validation_candidate_outcome (
                validation_id TEXT,
                trading_date TEXT,
                market TEXT,
                ticker TEXT,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                mfe_pct REAL,
                mae_pct REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO historical_validation_run(
                id,status,validation_target,scanner_version
            ) VALUES(?,?,?,?)
            """,
            (
                "validation-dev",
                "COMPLETED",
                "PRODUCTION_SCANNER",
                scanner_version or StockScannerService.VERSION,
            ),
        )
        for day in ("2023-01-03", "2023-01-04"):
            conn.execute(
                """
                INSERT INTO historical_validation_day(
                    validation_id,trading_date,status
                ) VALUES(?,?,?)
                """,
                ("validation-dev", day, "COMPLETED"),
            )
        conn.execute(
            """
            INSERT INTO historical_validation_candidate(
                validation_id,trading_date,market,ticker,rank,
                result_bucket,snapshot_hash
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                "validation-dev",
                "2023-01-03",
                "KOSPI",
                "005930",
                1,
                "TOP",
                "a" * 64,
            ),
        )
        conn.execute(
            """
            INSERT INTO historical_validation_candidate(
                validation_id,trading_date,market,ticker,rank,
                result_bucket,snapshot_hash
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                "validation-dev",
                "2023-01-04",
                "KOSPI",
                "000660",
                8,
                "MORE",
                "b" * 64,
            ),
        )
        conn.execute(
            """
            INSERT INTO historical_validation_candidate_outcome(
                validation_id,trading_date,market,ticker,
                return_5d,return_10d,return_20d,mfe_pct,mae_pct
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                "validation-dev",
                "2023-01-03",
                "KOSPI",
                "005930",
                99.0,
                88.0,
                77.0,
                66.0,
                -55.0,
            ),
        )


def _market_row(close: int) -> str:
    return json.dumps({"close": close}, separators=(",", ":"))


def _create_market_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily (
                market TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL
            );
            CREATE TABLE main_index_daily (
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL
            );
            CREATE TABLE day_status (
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        for day, index_close in (
            ("20230102", 100),
            ("20230103", 101),
            ("20230104", 102),
        ):
            conn.execute(
                "INSERT INTO main_index_daily VALUES(?,?,?)",
                ("KOSPI", day, _market_row(index_close)),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", day, "index", "data"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", day, "stock", "data"),
            )
        for ticker, values in {
            "005930": {
                "20230102": 60000,
                "20230103": 61000,
            },
            "000660": {
                "20230103": 80000,
                "20230104": 82000,
            },
        }.items():
            for day, close in values.items():
                conn.execute(
                    "INSERT INTO stock_daily VALUES(?,?,?,?)",
                    ("KOSPI", ticker, day, _market_row(close)),
                )


class _UnusedMacroReader:
    def __init__(self, path: Path) -> None:
        self.path = path


def _context_builder(*, reader, decision_cutoff: str, usage: str):
    del reader
    assert usage == "REFERENCE_SHADOW"
    parsed = datetime.fromisoformat(decision_cutoff).astimezone(timezone.utc)
    cutoff = parsed.isoformat()
    payload = {
        "cutoff": cutoff,
        "usage": usage,
    }
    digest = content_hash(payload)
    return {
        "contract_version": "TEST_MACRO_CONTEXT",
        "context_id": f"MACROCTX-{digest[:16]}",
        "context_hash": digest,
        "decision_cutoff": cutoff,
        "usage_mode": usage,
        "status": "COMPLETE_REFERENCE",
        "reason": None,
        "availability": {
            "historical_evaluation_eligible": False,
            "time_qualities": ["DATE_ONLY"],
            "reader_reason": None,
        },
        "production_decision_approved": False,
    }


class _EventReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def stock_reference_as_of(
        self,
        code: str,
        market: str,
        decision_cutoff: str,
    ) -> dict[str, object]:
        return {
            "contract_version": "TEST_EVENT",
            "status": "AVAILABLE",
            "code": code,
            "market": market,
            "decision_cutoff": decision_cutoff,
            "event_evidence": {
                "status": "REFERENCE_AVAILABLE",
                "reference_count": 1,
                "projected_reference_count": 1,
                "items": [
                    {
                        "event_type": "DIVIDEND",
                        "relation_type": "DIRECT",
                        "relevance_state": "RELEVANT",
                        "quality_state": "USABLE",
                        "source_kinds": ["OPENDART"],
                        "available_at": decision_cutoff,
                        "evidence_as_of": decision_cutoff,
                        "revision_state": "ORIGINAL",
                        "assessment_as_of": decision_cutoff,
                    }
                ],
                "diagnostics": {
                    "candidate_count": 1,
                    "excluded_after_cutoff_count": 0,
                    "excluded_late_ingest_count": 0,
                    "excluded_inactive_revision_count": 0,
                    "excluded_integrity_count": 0,
                    "excluded_synthetic_count": 0,
                    "excluded_duplicate_count": 0,
                },
            },
            "value_validation": {
                "status": "NOT_PROJECTED_AS_OF",
                "product_scope": "RESEARCH_ONLY",
            },
            "prediction": {
                "status": "NOT_VALIDATED",
                "direction": None,
                "horizon_sessions": None,
                "probability": None,
            },
        }


class _UnavailableEventReader(_EventReader):
    def stock_reference_as_of(
        self,
        code: str,
        market: str,
        decision_cutoff: str,
    ) -> dict[str, object]:
        del code, market, decision_cutoff
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_SCHEMA_NOT_READY",
            "event schema unavailable",
        )


class _UnavailableMarketReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_pair_as_of(self, **kwargs):
        return {
            "status": "UNAVAILABLE",
            "reason": "STORE_NOT_FOUND",
            "stock_rows": [],
            "market_rows": [],
        }


def _run(
    tmp_path: Path,
    *,
    event_reader_factory=_EventReader,
    market_reader_factory=None,
    sample_reader_factory=DevelopmentCoverageSampleReader,
):
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"
    macro = tmp_path / "macro.db"
    if not simulation.exists():
        _create_simulation_db(simulation)
    if not market.exists():
        _create_market_db(market)

    kwargs = {
        "entry_gate": _gate(),
        "validation_id": "validation-dev",
        "development_start": "2023-01-03",
        "development_end": "2023-01-04",
        "macro_db": macro,
        "market_db": market,
        "simulation_db": simulation,
        "sample_reader_factory": sample_reader_factory,
        "macro_reader_factory": _UnusedMacroReader,
        "event_reader_factory": event_reader_factory,
        "context_builder": _context_builder,
    }
    if market_reader_factory is not None:
        kwargs["market_reader_factory"] = market_reader_factory
    return audit_development_reference_coverage(**kwargs)


def test_sample_reader_is_read_only_and_never_reads_outcomes(tmp_path: Path) -> None:
    simulation = tmp_path / "simulation.db"
    _create_simulation_db(simulation)
    before = (simulation.stat().st_size, simulation.stat().st_mtime_ns)

    manifest = DevelopmentCoverageSampleReader(simulation).read_manifest(
        validation_id="validation-dev",
        development_start="2023-01-03",
        development_end="2023-01-04",
    )

    after = (simulation.stat().st_size, simulation.stat().st_mtime_ns)
    assert before == after
    assert manifest["input_sample_count"] == 2
    assert manifest["unique_sample_count"] == 2
    assert [item["result_bucket"] for item in manifest["samples"]] == [
        "TOP",
        "MORE",
    ]

    source = (
        ROOT / "backend/app/macro/development_coverage.py"
    ).read_text(encoding="utf-8")
    assert "?mode=ro" in source
    assert "PRAGMA query_only=ON" in source
    assert "historical_validation_candidate_outcome" not in source
    for forbidden in (
        "return_5d",
        "return_10d",
        "return_20d",
        "mfe_pct",
        "mae_pct",
    ):
        assert forbidden not in source


def test_development_audit_reports_reference_coverage_only(tmp_path: Path) -> None:
    report = _run(tmp_path)

    assert report["contract_version"] == (
        NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION
    )
    assert report["status"] == "COMPLETE"
    assert report["scope"]["cutoff_policy_version"] == (
        NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION
    )
    assert report["sample_manifest"]["unique_sample_count"] == 2
    assert report["summary"]["result_bucket_counts"] == {
        "MORE": 1,
        "TOP": 1,
    }
    assert report["summary"]["macro"]["status_counts"] == {
        "COMPLETE_REFERENCE": 2
    }
    assert report["summary"]["macro"][
        "historical_evaluation_eligible_counts"
    ] == {"false": 2}
    assert report["summary"]["impact"]["status_counts"] == {
        "AVAILABLE": 2
    }
    assert report["summary"]["event"]["status_counts"] == {
        "REFERENCE_AVAILABLE": 2
    }
    assert report["summary"]["event"]["total_reference_count"] == 2
    assert report["summary"]["composition"]["status_counts"] == {
        "AVAILABLE": 2
    }
    assert report["summary"]["sector"][
        "historical_sector_status_counts"
    ] == {"BLOCKED_EXTERNAL_SOURCE": 2}
    assert report["governance"]["claim_scope"] == (
        "DEVELOPMENT_REFERENCE_COVERAGE_ONLY"
    )
    assert report["governance"]["historical_effectiveness_approved"] is False
    assert report["governance"]["execution_policy_evaluation_approved"] is False
    assert report["governance"]["production_decision_approved"] is False
    assert report["governance"]["network_access"] is False
    assert report["governance"]["database_write"] is False
    assert "NO_EFFECTIVENESS_CLAIM" in report["limitations"]
    assert "DAY_END_COVERAGE_NOT_SIGNAL_TIME" in report["limitations"]

    serialized = json.dumps(report, ensure_ascii=False)
    for forbidden in (
        "return_5d",
        "return_10d",
        "return_20d",
        "mfe_pct",
        "mae_pct",
        "probability",
    ):
        assert forbidden not in serialized


def test_day_end_cutoff_is_explicit_and_not_claimed_as_signal_time(
    tmp_path: Path,
) -> None:
    report = _run(tmp_path)
    samples = report["samples"]

    assert samples[0]["coverage_cutoff"] == "2023-01-03T23:59:59+09:00"
    assert samples[1]["coverage_cutoff"] == "2023-01-04T23:59:59+09:00"
    assert "DAY_END_COVERAGE_NOT_SIGNAL_TIME" in report["limitations"]


def test_event_source_unavailable_degrades_without_aborting_audit(
    tmp_path: Path,
) -> None:
    report = _run(
        tmp_path,
        event_reader_factory=_UnavailableEventReader,
    )

    assert report["status"] == "COMPLETE"
    assert report["summary"]["event"]["reader_status_counts"] == {
        "UNAVAILABLE": 2
    }
    assert report["summary"]["event"]["status_counts"] == {
        "SOURCE_UNAVAILABLE": 2
    }
    assert report["summary"]["composition"]["status_counts"] == {
        "PARTIAL": 2
    }


def test_market_infrastructure_unavailable_fails_fast_as_audit_unavailable(
    tmp_path: Path,
) -> None:
    report = _run(
        tmp_path,
        market_reader_factory=_UnavailableMarketReader,
    )

    assert report["status"] == "AUDIT_UNAVAILABLE"
    assert report["unavailable_reason"] == (
        "MARKET_SOURCE_UNAVAILABLE:STORE_NOT_FOUND"
    )
    assert report["summary"]["sample_count"] == 0


def test_same_inputs_produce_same_report_identity_and_do_not_modify_sources(
    tmp_path: Path,
) -> None:
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"
    _create_simulation_db(simulation)
    _create_market_db(market)
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (simulation, market)
    }

    first = _run(tmp_path)
    second = _run(tmp_path)

    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in (simulation, market)
    }
    assert before == after
    assert first["report_id"] == second["report_id"]
    assert first["report_hash"] == second["report_hash"]
    assert [
        sample["sample_result_hash"] for sample in first["samples"]
    ] == [
        sample["sample_result_hash"] for sample in second["samples"]
    ]
    assert first["source_immutability_verified"] is True


def test_future_market_and_out_of_range_candidate_do_not_rewrite_report(
    tmp_path: Path,
) -> None:
    first = _run(tmp_path)
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"

    with sqlite3.connect(market) as conn:
        conn.execute(
            "INSERT INTO main_index_daily VALUES(?,?,?)",
            ("KOSPI", "20230201", _market_row(200)),
        )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20230201", "index", "data"),
        )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20230201", "stock", "data"),
        )
        conn.execute(
            "INSERT INTO stock_daily VALUES(?,?,?,?)",
            ("KOSPI", "005930", "20230201", _market_row(90000)),
        )

    with sqlite3.connect(simulation) as conn:
        conn.execute(
            """
            INSERT INTO historical_validation_day(
                validation_id,trading_date,status
            ) VALUES(?,?,?)
            """,
            ("validation-dev", "2023-02-01", "COMPLETED"),
        )
        conn.execute(
            """
            INSERT INTO historical_validation_candidate(
                validation_id,trading_date,market,ticker,rank,
                result_bucket,snapshot_hash
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                "validation-dev",
                "2023-02-01",
                "KOSPI",
                "005930",
                1,
                "TOP",
                "c" * 64,
            ),
        )

    second = _run(tmp_path)
    assert first["report_hash"] == second["report_hash"]
    assert first["sample_manifest"]["sample_manifest_hash"] == (
        second["sample_manifest"]["sample_manifest_hash"]
    )


def test_empty_development_range_is_not_zero_coverage(tmp_path: Path) -> None:
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"
    _create_simulation_db(simulation)
    _create_market_db(market)

    report = audit_development_reference_coverage(
        entry_gate=_gate(),
        validation_id="validation-dev",
        development_start="2022-01-01",
        development_end="2022-01-31",
        macro_db=tmp_path / "macro.db",
        market_db=market,
        simulation_db=simulation,
        macro_reader_factory=lambda path: (_ for _ in ()).throw(
            AssertionError("Macro reader should not be created")
        ),
    )

    assert report["status"] == "NO_DEVELOPMENT_SAMPLES"
    assert report["summary"]["sample_count"] == 0
    assert report["sample_manifest"]["unique_sample_count"] == 0


def test_scanner_baseline_mismatch_fails_closed(tmp_path: Path) -> None:
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"
    _create_simulation_db(simulation, scanner_version="0.0.0")
    _create_market_db(market)

    with pytest.raises(
        DevelopmentCoverageAuditError,
        match="Scanner version",
    ) as exc:
        audit_development_reference_coverage(
            entry_gate=_gate(),
            validation_id="validation-dev",
            development_start="2023-01-03",
            development_end="2023-01-04",
            macro_db=tmp_path / "macro.db",
            market_db=market,
            simulation_db=simulation,
            macro_reader_factory=_UnusedMacroReader,
            event_reader_factory=_EventReader,
            context_builder=_context_builder,
        )

    assert exc.value.code == "DEVELOPMENT_SCANNER_BASELINE_MISMATCH"


def test_s1_gate_must_keep_development_lane_eligible(tmp_path: Path) -> None:
    gate = _gate()
    gate["lanes"]["development_coverage"] = "BLOCKED"

    with pytest.raises(
        DevelopmentCoverageAuditError,
        match="not ELIGIBLE",
    ) as exc:
        audit_development_reference_coverage(
            entry_gate=gate,
            validation_id="validation-dev",
            development_start="2023-01-03",
            development_end="2023-01-04",
            macro_db=tmp_path / "macro.db",
            market_db=tmp_path / "market.db",
            simulation_db=tmp_path / "simulation.db",
        )

    assert exc.value.code == "DEVELOPMENT_GATE_NOT_ELIGIBLE"


def test_manifest_change_during_audit_fails_closed(tmp_path: Path) -> None:
    simulation = tmp_path / "simulation.db"
    market = tmp_path / "market.db"
    _create_simulation_db(simulation)
    _create_market_db(market)

    class _ChangingManifestReader(DevelopmentCoverageSampleReader):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self.calls = 0

        def read_manifest(self, **kwargs):
            result = super().read_manifest(**kwargs)
            self.calls += 1
            if self.calls > 1:
                result["sample_manifest_hash"] = "f" * 64
            return result

    with pytest.raises(
        DevelopmentCoverageAuditError,
        match="manifest changed",
    ) as exc:
        _run(
            tmp_path,
            sample_reader_factory=_ChangingManifestReader,
        )

    assert exc.value.code == "DEVELOPMENT_SAMPLE_CHANGED_DURING_AUDIT"


def test_macro_package_exports_next6e_s2_contract() -> None:
    import app.macro as macro

    assert macro.NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION == (
        NEXT6E_DEVELOPMENT_COVERAGE_CONTRACT_VERSION
    )
    assert macro.NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION == (
        NEXT6E_DEVELOPMENT_CUTOFF_POLICY_VERSION
    )
    assert callable(macro.audit_development_reference_coverage)


def test_cli_is_stdout_only_and_does_not_define_output_file() -> None:
    cli = (
        ROOT / "tools/macro/audit_development_reference_coverage.py"
    ).read_text(encoding="utf-8")

    assert "--validation-id" in cli
    assert "--development-start" in cli
    assert "--development-end" in cli
    assert "--macro-db" in cli
    assert "--market-db" in cli
    assert "--simulation-db" in cli
    assert "--output" not in cli
    assert "write_text(" not in cli
    assert "open(" not in cli
