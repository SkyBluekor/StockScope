from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import app.prospective.reference_capture as reference_module
from app.event_evidence.errors import EventEvidenceContractError
from app.macro.identity import content_hash
from app.prospective.models import PROSPECTIVE_SCHEMA_VERSION
from app.prospective.reference_capture import (
    NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
    NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION,
    NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
    REFERENCE_TEMPORAL_MODE,
    ProspectiveReferenceCaptureService,
)
from tools.data.migrate_prospective_reference_next6e_s3 import (
    migrate_prospective_reference_store,
)


ROOT = Path(__file__).resolve().parents[2]
CUTOFF = "2026-10-02T00:00:00+00:00"


def _create_base_db(
    path: Path,
    *,
    status: str = "COMPLETE",
    requested_as_of: str | None = None,
    sample_count: int = 2,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE prospective_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE prospective_capture_run(
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                requested_as_of TEXT,
                actual_data_date TEXT,
                scanner_version TEXT,
                source_execution_key TEXT,
                source_snapshot_hash TEXT,
                result_hash TEXT,
                completed_at TEXT
            );

            CREATE TABLE prospective_recommendation_sample(
                capture_run_id TEXT NOT NULL,
                sample_index INTEGER NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                signal_date TEXT,
                snapshot_hash TEXT NOT NULL,
                PRIMARY KEY(capture_run_id,sample_index),
                FOREIGN KEY(capture_run_id)
                    REFERENCES prospective_capture_run(id)
                    ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            INSERT INTO prospective_schema_meta(key,value)
            VALUES('schema_version',?)
            """,
            (PROSPECTIVE_SCHEMA_VERSION,),
        )
        request = {
            "market_scope": "ALL",
            "requested_as_of": requested_as_of,
            "candidate_limit": 5,
            "horizon_intent": "SHORT",
        }
        conn.execute(
            """
            INSERT INTO prospective_capture_run(
                id,status,request_json,requested_as_of,actual_data_date,
                scanner_version,source_execution_key,source_snapshot_hash,
                result_hash,completed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "capture-1",
                status,
                json.dumps(request),
                requested_as_of,
                "2026-10-01",
                "0.21.3.9",
                "execution-key",
                "capture-source-hash",
                "capture-result-hash",
                CUTOFF,
            ),
        )
        samples = [
            ("KOSPI", "005930", "a" * 64),
            ("KOSPI", "000660", "b" * 64),
        ]
        for index, (market, ticker, snapshot_hash) in enumerate(
            samples[:sample_count]
        ):
            conn.execute(
                """
                INSERT INTO prospective_recommendation_sample(
                    capture_run_id,sample_index,market,ticker,
                    signal_date,snapshot_hash
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    "capture-1",
                    index,
                    market,
                    ticker,
                    "2026-10-01",
                    snapshot_hash,
                ),
            )


def _base_identity(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as conn:
        capture = conn.execute(
            """
            SELECT
                status,requested_as_of,actual_data_date,scanner_version,
                source_execution_key,source_snapshot_hash,result_hash,
                completed_at
            FROM prospective_capture_run
            WHERE id='capture-1'
            """
        ).fetchone()
        samples = conn.execute(
            """
            SELECT sample_index,snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id='capture-1'
            ORDER BY sample_index
            """
        ).fetchall()
        schema_version = conn.execute(
            """
            SELECT value
            FROM prospective_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()[0]
    return {
        "capture": tuple(capture),
        "samples": [tuple(row) for row in samples],
        "schema_version": schema_version,
    }


def _install_reference_schema(path: Path) -> None:
    result = migrate_prospective_reference_store(path)
    assert result["historical_backfill_performed"] is False


def _patch_available_reference_chain(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_unavailable: bool = False,
    macro_unavailable: bool = False,
    market_unavailable: bool = False,
) -> dict[str, list[object]]:
    calls: dict[str, list[object]] = {
        "macro": [],
        "market": [],
        "event": [],
    }

    class FakeMacroReader:
        def __init__(self, path: Path) -> None:
            self.path = path

    def fake_context(*, reader, decision_cutoff: str, usage: str):
        del reader
        calls["macro"].append((decision_cutoff, usage))
        payload = {
            "decision_cutoff": decision_cutoff,
            "usage": usage,
            "unavailable": macro_unavailable,
        }
        digest = content_hash(payload)
        return {
            "contract_version": "TEST_MACRO_CONTEXT",
            "context_id": f"MACROCTX-{digest[:16]}",
            "context_hash": digest,
            "decision_cutoff": decision_cutoff,
            "usage_mode": usage,
            "status": (
                "UNAVAILABLE"
                if macro_unavailable
                else "COMPLETE_REFERENCE"
            ),
            "reason": (
                "STORE_NOT_FOUND"
                if macro_unavailable
                else None
            ),
            "availability": {
                "reader_reason": (
                    "STORE_NOT_FOUND"
                    if macro_unavailable
                    else None
                ),
            },
            "production_decision_approved": False,
        }

    class FakeMarketReader:
        def __init__(self, path: Path) -> None:
            self.path = path

        def read_pair_as_of(
            self,
            *,
            market: str,
            ticker: str,
            end_date: str,
        ):
            calls["market"].append((market, ticker, end_date))
            if market_unavailable:
                return {
                    "status": "UNAVAILABLE",
                    "reason": "STORE_NOT_FOUND",
                    "stock_rows": [],
                    "market_rows": [],
                }
            return {
                "status": "COMPLETE",
                "reason": None,
                "stock_rows": [
                    {"date": "20260930", "close": 100},
                    {"date": "20261001", "close": 102},
                ],
                "market_rows": [
                    {"date": "20260930", "close": 100},
                    {"date": "20261001", "close": 101},
                ],
            }

    class FakeEventReader:
        def __init__(self, path: Path) -> None:
            self.path = path

        def stock_reference_as_of(
            self,
            code: str,
            market: str,
            decision_cutoff: str,
        ):
            calls["event"].append((code, market, decision_cutoff))
            if event_unavailable:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SCHEMA_NOT_READY",
                    "event schema unavailable",
                )
            event_hash = content_hash(
                {
                    "code": code,
                    "market": market,
                    "cutoff": decision_cutoff,
                }
            )
            return {
                "contract_version": "TEST_EVENT_ASOF",
                "projection_id": f"EVASOF-{event_hash[:16]}",
                "projection_hash": event_hash,
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
                    "diagnostics": {},
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

    monkeypatch.setattr(
        reference_module,
        "LocalMacroReader",
        FakeMacroReader,
    )
    monkeypatch.setattr(
        reference_module,
        "build_macro_context",
        fake_context,
    )
    monkeypatch.setattr(
        reference_module,
        "LocalMarketImpactReader",
        FakeMarketReader,
    )
    monkeypatch.setattr(
        reference_module,
        "EventEvidenceAsOfReader",
        FakeEventReader,
    )
    return calls


def _service(path: Path, tmp_path: Path) -> ProspectiveReferenceCaptureService:
    return ProspectiveReferenceCaptureService(
        simulation_db=path,
        market_db=tmp_path / "market.db",
        macro_db=tmp_path / "macro.db",
    )


def _stored_attachments(path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM prospective_reference_attachment
            ORDER BY sample_index
            """
        ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["projection"] = json.loads(str(item["projection_json"]))
        result.append(item)
    return result


def test_migration_is_explicit_separate_and_does_not_backfill(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db)
    before = _base_identity(db)

    result = migrate_prospective_reference_store(db)

    after = _base_identity(db)
    assert before == after
    assert result["schema_version"] == (
        NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
    )
    assert result["historical_backfill_performed"] is False

    with sqlite3.connect(db) as conn:
        ref_count = conn.execute(
            "SELECT COUNT(*) FROM prospective_reference_capture"
        ).fetchone()[0]
        attachment_count = conn.execute(
            "SELECT COUNT(*) FROM prospective_reference_attachment"
        ).fetchone()[0]
    assert ref_count == 0
    assert attachment_count == 0
    assert before["schema_version"] == PROSPECTIVE_SCHEMA_VERSION


def test_schema_missing_does_not_block_existing_capture(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db)

    result = _service(db, tmp_path).try_capture("capture-1")

    assert result["status"] == "NOT_READY"
    assert result["code"] == "PROSPECTIVE_REFERENCE_MIGRATION_REQUIRED"
    assert _base_identity(db)["capture"][0] == "COMPLETE"


@pytest.mark.parametrize(
    ("status", "requested_as_of", "expected"),
    [
        ("COMPLETE", "2026-09-30", "SKIPPED_EXPLICIT_AS_OF"),
        ("PARTIAL", None, "SKIPPED_SOURCE_PARTIAL"),
        ("DUPLICATE", None, "SKIPPED_DUPLICATE"),
        ("FAILED", None, "SKIPPED_SOURCE_FAILED"),
        ("CANCELLED", None, "SKIPPED_SOURCE_CANCELLED"),
        ("INTERRUPTED", None, "SKIPPED_SOURCE_INTERRUPTED"),
    ],
)
def test_only_forward_complete_capture_is_eligible(
    tmp_path: Path,
    status: str,
    requested_as_of: str | None,
    expected: str,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(
        db,
        status=status,
        requested_as_of=requested_as_of,
    )

    result = _service(db, tmp_path).try_capture("capture-1")

    assert result["status"] == expected
    assert result["attachment_count"] == 0


def test_forward_capture_uses_completed_at_for_every_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db)
    _install_reference_schema(db)
    before = _base_identity(db)
    calls = _patch_available_reference_chain(monkeypatch)

    result = _service(db, tmp_path).try_capture("capture-1")

    assert result["status"] == "COMPLETE"
    assert result["reference_cutoff"] == CUTOFF
    assert result["attachment_count"] == 2
    assert calls["macro"] == [
        (CUTOFF, "REFERENCE_SHADOW"),
        (CUTOFF, "REFERENCE_SHADOW"),
    ]
    assert calls["market"] == [
        ("KOSPI", "005930", "2026-10-01"),
        ("KOSPI", "000660", "2026-10-01"),
    ]
    assert calls["event"] == [
        ("005930", "KOSPI", CUTOFF),
        ("000660", "KOSPI", CUTOFF),
    ]

    attachments = _stored_attachments(db)
    assert len(attachments) == 2
    for stored in attachments:
        projection = stored["projection"]
        assert stored["reference_cutoff"] == CUTOFF
        assert projection["reference_cutoff"] == CUTOFF
        assert projection["reference_temporal_mode"] == (
            REFERENCE_TEMPORAL_MODE
        )
        assert projection["decision_input"] is False
        assert projection["signal_time_equivalence"] is False
        assert projection["cutoff_policy_version"] == (
            NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION
        )
        assert projection["contract_version"] == (
            NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
        )
        assert projection["macro"]["usage_mode"] == "REFERENCE_SHADOW"
        assert projection["composition"]["status"] == "AVAILABLE"
        assert projection["governance"]["scanner_input_approved"] is False
        assert projection["governance"]["production_decision_approved"] is False
        assert projection["governance"]["network_access"] is False

    assert _base_identity(db) == before


def test_event_unavailable_is_captured_as_degradation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db, sample_count=1)
    _install_reference_schema(db)
    _patch_available_reference_chain(
        monkeypatch,
        event_unavailable=True,
    )

    result = _service(db, tmp_path).try_capture("capture-1")
    projection = _stored_attachments(db)[0]["projection"]

    assert result["status"] == "COMPLETE"
    assert projection["event"]["reader_status"] == "UNAVAILABLE"
    assert projection["event"]["reader_reason"] == (
        "EVENT_EVIDENCE_SCHEMA_NOT_READY"
    )
    assert projection["composition"]["status"] == "PARTIAL"


def test_macro_unavailable_is_preserved_without_policy_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db, sample_count=1)
    _install_reference_schema(db)
    _patch_available_reference_chain(
        monkeypatch,
        macro_unavailable=True,
    )

    result = _service(db, tmp_path).try_capture("capture-1")
    projection = _stored_attachments(db)[0]["projection"]

    assert result["status"] == "COMPLETE"
    assert projection["macro"]["status"] == "UNAVAILABLE"
    assert projection["impact"]["status"] == (
        "NOT_BUILT_MACRO_UNAVAILABLE"
    )
    assert projection["composition"]["status"] == (
        "NOT_BUILT_MACRO_UNAVAILABLE"
    )
    assert projection["governance"]["strategy_input_approved"] is False


def test_market_unavailable_is_preserved_without_aborting_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db, sample_count=1)
    _install_reference_schema(db)
    _patch_available_reference_chain(
        monkeypatch,
        market_unavailable=True,
    )

    result = _service(db, tmp_path).try_capture("capture-1")
    projection = _stored_attachments(db)[0]["projection"]

    assert result["status"] == "COMPLETE"
    assert projection["market_reader"] == {
        "status": "UNAVAILABLE",
        "reason": "STORE_NOT_FOUND",
    }
    assert projection["impact"]["status"] == (
        "NOT_BUILT_SOURCE_UNAVAILABLE"
    )
    assert projection["composition"]["status"] == (
        "NOT_BUILT_SOURCE_UNAVAILABLE"
    )


def test_capture_is_idempotent_and_hashes_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db)
    _install_reference_schema(db)
    calls = _patch_available_reference_chain(monkeypatch)
    service = _service(db, tmp_path)

    first = service.try_capture("capture-1")
    first_rows = _stored_attachments(db)
    second = service.try_capture("capture-1")
    second_rows = _stored_attachments(db)

    assert first["status"] == "COMPLETE"
    assert second["status"] == "COMPLETE"
    assert first["attachment_set_hash"] == second["attachment_set_hash"]
    assert [
        row["attachment_hash"] for row in first_rows
    ] == [
        row["attachment_hash"] for row in second_rows
    ]
    assert len(calls["macro"]) == 2
    assert len(calls["event"]) == 2


def test_existing_attachment_detects_source_manifest_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db, sample_count=1)
    _install_reference_schema(db)
    _patch_available_reference_chain(monkeypatch)
    service = _service(db, tmp_path)

    first = service.try_capture("capture-1")
    assert first["status"] == "COMPLETE"

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE prospective_recommendation_sample
            SET snapshot_hash=?
            WHERE capture_run_id='capture-1' AND sample_index=0
            """,
            ("c" * 64,),
        )

    second = service.try_capture("capture-1")
    assert second["status"] == "FAILED"
    assert second["code"] == "PROSPECTIVE_REFERENCE_SOURCE_CONFLICT"


def test_reference_rows_are_immutable(tmp_path: Path) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db)
    _install_reference_schema(db)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO prospective_reference_capture(
                capture_run_id,capture_contract_version,storage_version,
                status,reference_cutoff,cutoff_policy_version,
                reference_temporal_mode,source_sample_count,
                attachment_count,attachment_set_hash,source_manifest_hash,
                error_code,error_message,created_at,completed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "capture-1",
                NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION,
                NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION,
                "COMPLETE",
                CUTOFF,
                NEXT6E_PROSPECTIVE_REFERENCE_CUTOFF_POLICY_VERSION,
                REFERENCE_TEMPORAL_MODE,
                2,
                0,
                "d" * 64,
                "e" * 64,
                None,
                None,
                CUTOFF,
                CUTOFF,
            ),
        )

    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE prospective_reference_capture
                SET attachment_count=1
                WHERE capture_run_id='capture-1'
                """
            )


def test_projection_finishes_before_reference_write_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "simulation.db"
    _create_base_db(db, sample_count=1)
    _install_reference_schema(db)
    _patch_available_reference_chain(monkeypatch)
    service = _service(db, tmp_path)

    write_started = {"value": False}
    original_connect_write = service._connect_write

    def wrapped_connect_write():
        write_started["value"] = True
        return original_connect_write()

    original_project = service._project_sample

    def wrapped_project(**kwargs):
        assert write_started["value"] is False
        return original_project(**kwargs)

    monkeypatch.setattr(service, "_connect_write", wrapped_connect_write)
    monkeypatch.setattr(service, "_project_sample", wrapped_project)

    result = service.try_capture("capture-1")

    assert result["status"] == "COMPLETE"
    assert write_started["value"] is True


def test_backtest_integration_is_post_finalize_and_non_blocking_by_contract() -> None:
    source = (
        ROOT / "backend/app/api/backtest.py"
    ).read_text(encoding="utf-8")

    finalize_pos = source.index(
        "prospective.try_finalize_scanner_capture("
    )
    reference_pos = source.index(
        "_prospective_reference_capture_service().try_capture("
    )
    assert finalize_pos < reference_pos
    assert 'result["prospective_capture"] = prospective_capture' in source
    assert 'result["prospective_reference_capture"]' in source
    assert '"SKIPPED_BASE_CAPTURE_NOT_READY"' in source


def test_reference_module_has_no_network_or_evaluation_wiring() -> None:
    source = (
        ROOT / "backend/app/prospective/reference_capture.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests",
        "httpx",
        "urllib.request",
        "ProspectiveEvaluator",
        "ProductionExitPolicyEngine",
        "StrategyChange",
        "app.holdings",
    ):
        assert forbidden not in source

    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "REFERENCE_SHADOW" in source
    assert "decision_input" in source
    assert "scanner_input_approved" in source
    assert "production_decision_approved" in source


def test_prospective_package_exports_next6e_s3_contract() -> None:
    import app.prospective as prospective

    assert (
        prospective.NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
        == NEXT6E_PROSPECTIVE_REFERENCE_CAPTURE_CONTRACT_VERSION
    )
    assert (
        prospective.NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
        == NEXT6E_PROSPECTIVE_REFERENCE_STORAGE_VERSION
    )
    assert prospective.ProspectiveReferenceCaptureService is (
        ProspectiveReferenceCaptureService
    )
