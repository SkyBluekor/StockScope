from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog
from app.simulation.sim1_store import SimulationRepository
from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.event_evidence.entity import (
    EventEntityRef,
    EventEntityRelevance,
    EventEntityService,
    RelevanceEvidenceKind,
    RelevanceRelation,
    RelevanceState,
)
from app.event_evidence.evaluation import (
    EventEvaluationProtocol,
    HistoricalEventEvaluator,
)
from app.event_evidence.models import (
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventRevisionIdentity,
)
from app.event_evidence.policy import EventEvidenceSourcePolicy
from app.event_evidence.product import EventEvidenceProductQuery
from app.event_evidence.quality import (
    EvidenceQualityScope,
    EventEvidenceQualityService,
)
from app.event_evidence.store import EventEvidenceStore
from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.event_evidence.value_gate import (
    EventIncrementalValueGate,
    IncrementalValueGateProtocol,
)
from tools.data.backup_runtime import create_backup
from tools.data.common import DataToolError
from tools.data.event_evidence_runtime import (
    EVENT_EVIDENCE_BACKUP_TABLES,
    inspect_event_evidence_store,
)
from tools.data.migrate_event_evidence_vnp6s1 import (
    migrate_event_evidence_store,
)
from tools.data.restore_runtime import restore_backup


NOW = "2026-09-28T07:30:00+00:00"
AS_OF = "2026-09-28T10:00:00+09:00"


def _holdings_db(path: Path) -> Path:
    HoldingsCatalog(path).initialize()
    return path


def _simulation_db(path: Path) -> Path:
    SimulationRepository(path).initialize()
    HistoricalValidationCatalog(path).initialize()
    return path


def _market_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE stock_daily(
            market TEXT NOT NULL,
            bas_dd TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY(market,bas_dd,stock_code)
        );
        CREATE TABLE main_index_daily(
            market TEXT NOT NULL,
            bas_dd TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY(market,bas_dd)
        );
        CREATE TABLE day_status(
            market TEXT NOT NULL,
            bas_dd TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY(market,bas_dd,kind)
        );
        """
    )
    days = [date(2026, 9, 25)]
    cursor = date(2026, 9, 29)
    while len(days) < 26:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)

    for index, item in enumerate(days):
        bas_dd = item.strftime("%Y%m%d")
        stock_close = 100.0 + index
        index_close = 200.0 + index
        conn.execute(
            """
            INSERT INTO stock_daily(market,bas_dd,stock_code,row_json)
            VALUES('KOSPI',?,'005930',?)
            """,
            (
                bas_dd,
                json.dumps(
                    {"date": bas_dd, "code": "005930", "close": stock_close},
                    separators=(",", ":"),
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO main_index_daily(market,bas_dd,row_json)
            VALUES('KOSPI',?,?)
            """,
            (
                bas_dd,
                json.dumps(
                    {"date": bas_dd, "close": index_close},
                    separators=(",", ":"),
                ),
            ),
        )
        conn.executemany(
            """
            INSERT INTO day_status(market,bas_dd,kind,status)
            VALUES('KOSPI',?,?,'data')
            """,
            [(bas_dd, "stock"), (bas_dd, "index")],
        )
    conn.commit()
    conn.close()
    return path


def _seed_p6(simulation: Path, market: Path) -> dict[str, str]:
    migrate_event_evidence_store(simulation)

    policy = EventEvidenceSourcePolicy(
        policy_id="TEST-P6-H-BACKUP-V1",
        source_kind="TEST_SYNTHETIC",
        policy_version="test-v1",
        display_allowed=True,
        normalization_allowed=True,
        raw_retention_allowed=False,
        derived_retention_allowed=True,
        ai_transform_allowed=False,
        historical_evaluation_allowed=True,
        prediction_input_allowed=False,
        attribution_required=False,
        policy_basis="TEST_FIXTURE_ONLY",
    )
    temporal = TemporalEvidence(
        event_time="2026-09-28T09:00:00+09:00",
        source_published_at="2026-09-28T09:01:00+09:00",
        provider_published_at="2026-09-28T09:02:00+09:00",
        first_seen_at="2026-09-28T09:03:00+09:00",
        available_at="2026-09-28T09:03:00+09:00",
        fetched_at="2026-09-28T09:03:00+09:00",
        time_quality=EvidenceTimeQuality.EXACT,
    )

    store = EventEvidenceStore(simulation, clock=lambda: NOW)
    source = EventEvidenceSourceRef(
        source_ref_id="SRC-P6-H",
        source_kind=policy.source_kind,
        source_native_id="native-p6-h",
        rights_policy_id=policy.policy_id,
        content_hash="a" * 64,
        source_name="P6 H synthetic fixture",
        temporal=temporal,
    )
    stored_source = store.store_source_ref(
        policy=policy,
        source_ref=source,
    )
    event = store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id="EVENT-P6-H",
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=temporal,
        event_payload={"official_event_id": "TEST-OFFICIAL-P6-H"},
        source_ref_ids=[source.source_ref_id],
    )

    entities = EventEntityService(simulation, clock=lambda: NOW)
    entity = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="TEST_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    relevance = entities.attach_relevance(
        EventEntityRelevance(
            event_id="EVENT-P6-H",
            event_version=1,
            entity_id=entity["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
            evidence_ref="source:SRC-P6-H",
            evidence_as_of="2026-09-28T09:03:00+09:00",
            relation_payload={"source_ref_id": "SRC-P6-H"},
        )
    )

    quality = EventEvidenceQualityService(simulation, clock=lambda: NOW)
    reference = quality.assess_event_entity(
        event_id="EVENT-P6-H",
        entity_id=entity["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.REFERENCE,
        assessment_as_of=AS_OF,
    )
    historical = quality.assess_event_entity(
        event_id="EVENT-P6-H",
        entity_id=entity["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.HISTORICAL_EVALUATION,
        assessment_as_of=AS_OF,
    )

    evaluator = HistoricalEventEvaluator(
        simulation,
        market,
        clock=lambda: NOW,
    )
    evaluator.register_protocol(
        EventEvaluationProtocol(protocol_id="P6-H-EVAL")
    )
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=historical["assessment_id"],
        protocol_id="P6-H-EVAL",
    )
    report = evaluator.create_report(
        protocol_id="P6-H-EVAL",
        observation_ids=[outcome["observation_id"]],
    )

    gate = EventIncrementalValueGate(
        simulation,
        market,
        clock=lambda: NOW,
    )
    gate.register_protocol(
        IncrementalValueGateProtocol(protocol_id="P6-H-GATE")
    )
    decision = gate.evaluate_report(
        evaluation_report_id=report["report_id"],
        gate_protocol_id="P6-H-GATE",
    )
    assert decision["decision"] == "HOLD"
    assert decision["prediction_eligible"] is False

    return {
        "source_ref_hash": stored_source["source_ref_hash"],
        "event_hash": event["event_hash"],
        "entity_hash": entity["identity_hash"],
        "relevance_hash": relevance["relation_hash"],
        "reference_quality_hash": reference["quality_hash"],
        "historical_quality_hash": historical["quality_hash"],
        "report_hash": report["report_hash"],
        "decision_hash": decision["decision_hash"],
    }


def _hashes(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as conn:
        return {
            "source_ref_hash": conn.execute(
                "SELECT source_ref_hash FROM event_evidence_source_ref LIMIT 1"
            ).fetchone()[0],
            "event_hash": conn.execute(
                "SELECT event_hash FROM event_evidence_record LIMIT 1"
            ).fetchone()[0],
            "entity_hash": conn.execute(
                "SELECT identity_hash FROM event_evidence_entity LIMIT 1"
            ).fetchone()[0],
            "relevance_hash": conn.execute(
                "SELECT relation_hash FROM event_evidence_entity_relevance LIMIT 1"
            ).fetchone()[0],
            "reference_quality_hash": conn.execute(
                """
                SELECT quality_hash
                FROM event_evidence_quality_assessment
                WHERE assessment_scope='REFERENCE'
                LIMIT 1
                """
            ).fetchone()[0],
            "historical_quality_hash": conn.execute(
                """
                SELECT quality_hash
                FROM event_evidence_quality_assessment
                WHERE assessment_scope='HISTORICAL_EVALUATION'
                LIMIT 1
                """
            ).fetchone()[0],
            "report_hash": conn.execute(
                "SELECT report_hash FROM event_evidence_evaluation_report LIMIT 1"
            ).fetchone()[0],
            "decision_hash": conn.execute(
                "SELECT decision_hash FROM event_evidence_value_gate_decision LIMIT 1"
            ).fetchone()[0],
        }


def test_p6_backup_restore_and_product_projection_roundtrip(tmp_path: Path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    market = _market_db(tmp_path / "market.db")
    expected_hashes = _seed_p6(simulation, market)

    before_state = inspect_event_evidence_store(simulation)
    before_product = EventEvidenceProductQuery(simulation).stock_status(
        "005930",
        "KOSPI",
    )
    assert before_product["event_evidence"]["status"] == (
        "NO_VALIDATED_EVIDENCE"
    )
    assert before_product["value_validation"]["status"] == "NOT_EVALUATED"
    assert before_product["prediction"]["status"] == "NOT_VALIDATED"
    assert before_product["prediction"]["direction"] is None
    assert before_product["prediction"]["probability"] is None

    backup = create_backup(
        destination=tmp_path / "p6-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    extension = manifest["extensions"]["event_evidence_v1"]
    assert extension == before_state
    assert extension["present"] is True
    assert extension["restorable"] is True
    assert set(extension["tables"]) == set(EVENT_EVIDENCE_BACKUP_TABLES)
    assert extension["counts"]["policy_snapshot_count"] == 1
    assert extension["counts"]["source_ref_count"] == 1
    assert extension["counts"]["event_evidence_count"] == 1
    assert extension["counts"]["entity_count"] == 1
    assert extension["counts"]["relevance_count"] == 1
    assert extension["counts"]["quality_assessment_count"] == 2
    assert extension["counts"]["evaluation_protocol_count"] == 1
    assert extension["counts"]["outcome_observation_count"] == 1
    assert extension["counts"]["evaluation_report_count"] == 1
    assert extension["counts"]["value_gate_protocol_count"] == 1
    assert extension["counts"]["value_gate_decision_count"] == 1
    assert extension["prediction_enabled"] is False

    target_holdings = tmp_path / "restored-holdings.db"
    target_simulation = tmp_path / "restored-simulation.db"
    result = restore_backup(
        backup,
        restore_simulation=True,
        target_holdings=target_holdings,
        target_simulation=target_simulation,
    )

    after_state = inspect_event_evidence_store(target_simulation)
    after_product = EventEvidenceProductQuery(target_simulation).stock_status(
        "005930",
        "KOSPI",
    )
    assert after_state == before_state
    assert _hashes(target_simulation) == expected_hashes
    assert after_product == before_product
    assert result["event_evidence"]["manifest_present"] is True
    assert result["event_evidence"]["store_present_in_backup"] is True
    assert result["event_evidence"]["store_restored"] is True
    assert result["event_evidence"]["counts"] == before_state["counts"]
    assert result["event_evidence"]["prediction_enabled"] is False


def test_p6_partial_migration_blocks_backup_publication(tmp_path: Path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    with sqlite3.connect(simulation) as conn:
        conn.execute(
            """
            CREATE TABLE event_evidence_schema_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
    destination = tmp_path / "partial-p6-backup"

    with pytest.raises(DataToolError, match="부분 migration"):
        create_backup(
            destination=destination,
            holdings_db=holdings,
            simulation_db=simulation,
            include_tracking=False,
        )
    assert not destination.exists()


def test_p6_tampered_manifest_blocks_restore_before_target_change(
    tmp_path: Path,
):
    holdings = _holdings_db(tmp_path / "holdings.db")
    simulation = _simulation_db(tmp_path / "simulation.db")
    market = _market_db(tmp_path / "market.db")
    _seed_p6(simulation, market)

    backup = create_backup(
        destination=tmp_path / "p6-tampered-backup",
        holdings_db=holdings,
        simulation_db=simulation,
        include_tracking=False,
    )
    manifest_path = backup / "backup_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extensions"]["event_evidence_v1"]["counts"][
        "event_evidence_count"
    ] = 999
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    target_holdings = _holdings_db(tmp_path / "target-holdings.db")
    target_simulation = _simulation_db(tmp_path / "target-simulation.db")
    with sqlite3.connect(target_simulation) as conn:
        conn.execute("CREATE TABLE p6_restore_guard(value TEXT)")
        conn.execute("INSERT INTO p6_restore_guard VALUES('before')")
    before_guard = sqlite3.connect(target_simulation).execute(
        "SELECT value FROM p6_restore_guard"
    ).fetchone()[0]

    with pytest.raises(DataToolError, match="backup manifest"):
        restore_backup(
            backup,
            restore_simulation=True,
            target_holdings=target_holdings,
            target_simulation=target_simulation,
        )

    with sqlite3.connect(target_simulation) as conn:
        after_guard = conn.execute(
            "SELECT value FROM p6_restore_guard"
        ).fetchone()[0]
    assert after_guard == before_guard
