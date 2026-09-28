from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.event_evidence import (
    ControlMethod,
    EvidenceQualityScope,
    EvidenceTimeQuality,
    EventEntityRef,
    EventEntityRelevance,
    EventEntityService,
    EventEvaluationProtocol,
    EventEvidenceContractError,
    EventEvidenceQualityService,
    EventEvidenceSourcePolicy,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventEvidenceStore,
    EventResolutionService,
    EventRevisionIdentity,
    HistoricalEventEvaluator,
    RelevanceEvidenceKind,
    RelevanceRelation,
    RelevanceState,
    TemporalEvidence,
)
from tools.data.migrate_event_evidence_vnp6s1 import (
    migrate_event_evidence_store,
)


NOW = "2026-09-28T06:20:00+00:00"
ASSESSMENT_AS_OF = "2026-09-28T10:00:00+09:00"


def _business_days(start: date, count: int) -> list[date]:
    rows: list[date] = []
    current = start
    while len(rows) < count:
        if current.weekday() < 5:
            rows.append(current)
        current += timedelta(days=1)
    return rows


def _market_db(
    tmp_path: Path,
    *,
    reaction_count: int = 25,
) -> tuple[Path, list[str]]:
    path = tmp_path / "market_history.db"
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

    fixed = [
        date(2026, 9, 24),
        date(2026, 9, 25),
        date(2026, 9, 28),
    ]
    reaction = [
        item
        for item in _business_days(date(2026, 9, 29), reaction_count)
    ]
    dates = fixed + reaction

    stock_overrides: dict[str, float] = {
        "20260924": 99.0,
        "20260925": 100.0,
        "20260928": 101.0,
    }
    index_overrides: dict[str, float] = {
        "20260924": 198.0,
        "20260925": 200.0,
        "20260928": 201.0,
    }
    if len(reaction) >= 1:
        stock_overrides[reaction[0].strftime("%Y%m%d")] = 102.0
        index_overrides[reaction[0].strftime("%Y%m%d")] = 202.0
    if len(reaction) >= 5:
        stock_overrides[reaction[4].strftime("%Y%m%d")] = 105.0
        index_overrides[reaction[4].strftime("%Y%m%d")] = 204.0
    if len(reaction) >= 20:
        stock_overrides[reaction[19].strftime("%Y%m%d")] = 95.0
        index_overrides[reaction[19].strftime("%Y%m%d")] = 210.0

    for offset, trading_day in enumerate(dates):
        bas_dd = trading_day.strftime("%Y%m%d")
        stock_close = stock_overrides.get(bas_dd, 100.0 + offset / 10)
        index_close = index_overrides.get(bas_dd, 200.0 + offset / 10)
        conn.execute(
            """
            INSERT INTO stock_daily(market,bas_dd,stock_code,row_json)
            VALUES('KOSPI',?,?,?)
            """,
            (
                bas_dd,
                "005930",
                json.dumps(
                    {
                        "code": "005930",
                        "date": bas_dd,
                        "close": stock_close,
                    },
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
    return path, [item.strftime("%Y%m%d") for item in reaction]


def _policy() -> EventEvidenceSourcePolicy:
    return EventEvidenceSourcePolicy(
        policy_id="TEST-P6-E-HIST-V1",
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


def _temporal(
    available_at: str = "2026-09-28T09:10:00+09:00",
) -> TemporalEvidence:
    return TemporalEvidence(
        event_time="2026-09-28T09:00:00+09:00",
        source_published_at="2026-09-28T09:03:00+09:00",
        provider_published_at="2026-09-28T09:05:00+09:00",
        first_seen_at=available_at,
        available_at=available_at,
        fetched_at=available_at,
        time_quality=EvidenceTimeQuality.EXACT,
    )


def _base(tmp_path: Path, *, reaction_count: int = 25):
    simulation_db = tmp_path / "simulation.db"
    sqlite3.connect(simulation_db).close()
    migrate_event_evidence_store(simulation_db)
    market_db, reaction_days = _market_db(
        tmp_path,
        reaction_count=reaction_count,
    )
    policy = _policy()
    store = EventEvidenceStore(simulation_db, clock=lambda: NOW)
    entities = EventEntityService(simulation_db, clock=lambda: NOW)
    resolver = EventResolutionService(simulation_db, clock=lambda: NOW)
    quality = EventEvidenceQualityService(simulation_db, clock=lambda: NOW)
    evaluator = HistoricalEventEvaluator(
        simulation_db,
        market_db,
        clock=lambda: NOW,
    )
    company = entities.register_entity(
        EventEntityRef.listed_company(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            identity_source="KRX_MASTER",
            identity_as_of="2026-09-28T00:00:00+09:00",
        )
    )
    return (
        simulation_db,
        market_db,
        reaction_days,
        policy,
        store,
        entities,
        resolver,
        quality,
        evaluator,
        company,
    )


def _add_event(
    *,
    policy: EventEvidenceSourcePolicy,
    store: EventEvidenceStore,
    entities: EventEntityService,
    company: dict,
    event_id: str,
    source_id: str,
    content_char: str,
    official_id: str | None = None,
):
    temporal = _temporal()
    source = EventEvidenceSourceRef(
        source_ref_id=source_id,
        source_kind=policy.source_kind,
        source_native_id=f"native-{source_id}",
        rights_policy_id=policy.policy_id,
        content_hash=content_char * 64,
        source_name=f"origin-{source_id}",
        temporal=temporal,
    )
    store.store_source_ref(policy=policy, source_ref=source)
    payload = {}
    if official_id is not None:
        payload["official_event_id"] = official_id
    store.create_event_revision(
        identity=EventRevisionIdentity(
            event_id=event_id,
            version=1,
            state=EventEvidenceState.ORIGINAL,
        ),
        event_type="RIGHTS_ISSUE",
        scope="COMPANY",
        temporal=temporal,
        event_payload=payload,
        source_ref_ids=[source_id],
    )
    return entities.attach_relevance(
        EventEntityRelevance(
            event_id=event_id,
            event_version=1,
            entity_id=company["entity_id"],
            relation_type=RelevanceRelation.DIRECT_COMPANY,
            relevance_state=RelevanceState.CONFIRMED,
            evidence_kind=RelevanceEvidenceKind.SOURCE_DIRECT,
            evidence_ref=f"source:{source_id}",
            evidence_as_of="2026-09-28T09:10:00+09:00",
            relation_payload={"source_ref_id": source_id},
        )
    )


def _historical_quality(
    *,
    quality: EventEvidenceQualityService,
    event_id: str,
    company: dict,
    relevance: dict,
):
    return quality.assess_event_entity(
        event_id=event_id,
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.HISTORICAL_EVALUATION,
        assessment_as_of=ASSESSMENT_AS_OF,
    )


def test_evaluation_migration_is_idempotent_and_performs_no_real_evaluation(
    tmp_path: Path,
):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    first = migrate_event_evidence_store(db)
    second = migrate_event_evidence_store(db)

    for key in (
        "evaluation_protocol_count",
        "outcome_observation_count",
        "control_match_count",
        "evaluation_report_count",
    ):
        assert first[key] == 0
        assert second[key] == 0
    assert first["real_corpus_evaluation_performed"] is False
    assert first["external_network_requests"] == 0


def test_outcome_uses_previous_confirmed_close_and_1_5_20_trading_days(
    tmp_path: Path,
):
    (
        _,
        _,
        reaction_days,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-1",
        source_id="SRC-1",
        content_char="a",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-1",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-V1"))

    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-V1",
    )

    assert outcome["reference_trading_day"] == "2026-09-25"
    assert outcome["reference_close"] == 100.0
    assert outcome["horizons"]["1"]["trading_day"] == (
        f"{reaction_days[0][:4]}-{reaction_days[0][4:6]}-{reaction_days[0][6:]}"
    )
    assert outcome["horizons"]["1"]["stock_return_pct"] == 2.0
    assert outcome["horizons"]["1"]["market_return_pct"] == 1.0
    assert outcome["horizons"]["1"]["market_adjusted_return_pct"] == 1.0
    assert outcome["horizons"]["5"]["stock_return_pct"] == 5.0
    assert outcome["horizons"]["5"]["market_return_pct"] == 2.0
    assert outcome["horizons"]["5"]["market_adjusted_return_pct"] == 3.0
    assert outcome["horizons"]["20"]["stock_return_pct"] == -5.0
    assert outcome["horizons"]["20"]["market_return_pct"] == 5.0
    assert outcome["horizons"]["20"]["market_adjusted_return_pct"] == -10.0
    assert outcome["evaluation_status"] == "COMPLETE"
    assert evaluator.verify_observation(outcome["observation_id"])["status"] == "MATCH"


def test_horizon_maturity_is_recorded_independently(tmp_path: Path):
    (
        _,
        _,
        _,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path, reaction_count=5)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-PARTIAL",
        source_id="SRC-PARTIAL",
        content_char="b",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-PARTIAL",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-PARTIAL"))
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-PARTIAL",
    )

    assert outcome["evaluation_status"] == "PARTIAL"
    assert outcome["horizons"]["1"]["status"] == "MATURE"
    assert outcome["horizons"]["5"]["status"] == "MATURE"
    assert outcome["horizons"]["20"]["status"] == "NOT_MATURED"


def test_reference_quality_scope_cannot_bypass_historical_gate(tmp_path: Path):
    (
        _,
        _,
        _,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-REF",
        source_id="SRC-REF",
        content_char="c",
    )
    reference = quality.assess_event_entity(
        event_id="EVENT-REF",
        entity_id=company["entity_id"],
        relevance_id=relevance["relevance_id"],
        assessment_scope=EvidenceQualityScope.REFERENCE,
        assessment_as_of=ASSESSMENT_AS_OF,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-REF"))

    with pytest.raises(EventEvidenceContractError) as blocked:
        evaluator.evaluate_outcome(
            quality_assessment_id=reference["assessment_id"],
            protocol_id="P6-E-REF",
        )
    assert blocked.value.code == "EVENT_EVALUATION_SCOPE_BLOCKED"


def test_existing_partial_observation_remains_verifiable_when_future_rows_arrive(
    tmp_path: Path,
):
    (
        _,
        market_db,
        _,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path, reaction_count=5)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-FROZEN",
        source_id="SRC-FROZEN",
        content_char="d",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-FROZEN",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-FROZEN"))
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-FROZEN",
    )

    with sqlite3.connect(market_db) as conn:
        bas_dd = "20261007"
        conn.execute(
            """
            INSERT INTO stock_daily(market,bas_dd,stock_code,row_json)
            VALUES('KOSPI',?,'005930',?)
            """,
            (
                bas_dd,
                json.dumps(
                    {"code":"005930","date":bas_dd,"close":103.0},
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
                    {"date":bas_dd,"close":203.0},
                    separators=(",", ":"),
                ),
            ),
        )
        conn.executemany(
            """
            INSERT INTO day_status(market,bas_dd,kind,status)
            VALUES('KOSPI',?,?,'data')
            """,
            [(bas_dd,"stock"),(bas_dd,"index")],
        )

    assert evaluator.verify_observation(outcome["observation_id"])["status"] == "MATCH"


def test_mutating_a_pinned_market_row_breaks_observation_verification(
    tmp_path: Path,
):
    (
        _,
        market_db,
        reaction_days,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-MARKET-HASH",
        source_id="SRC-MARKET-HASH",
        content_char="e",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-MARKET-HASH",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-HASH"))
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-HASH",
    )

    with sqlite3.connect(market_db) as conn:
        target = reaction_days[4]
        conn.execute(
            """
            UPDATE stock_daily
            SET row_json=?
            WHERE market='KOSPI' AND bas_dd=? AND stock_code='005930'
            """,
            (
                json.dumps(
                    {"code":"005930","date":target,"close":999.0},
                    separators=(",", ":"),
                ),
                target,
            ),
        )

    with pytest.raises(EventEvidenceContractError) as mismatch:
        evaluator.verify_observation(outcome["observation_id"])
    assert mismatch.value.code == "EVENT_OUTCOME_MARKET_EVIDENCE_MISMATCH"


def test_canonical_duplicate_observations_count_as_one_report_sample(
    tmp_path: Path,
):
    (
        _,
        _,
        _,
        policy,
        store,
        entities,
        resolver,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    rel_a = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-A",
        source_id="SRC-A",
        content_char="a",
        official_id="OFFICIAL-1",
    )
    rel_b = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-B",
        source_id="SRC-B",
        content_char="b",
        official_id="OFFICIAL-1",
    )
    resolver.resolve_duplicate("EVENT-A",1,"EVENT-B",1)
    qa = _historical_quality(
        quality=quality,event_id="EVENT-A",company=company,relevance=rel_a
    )
    qb = _historical_quality(
        quality=quality,event_id="EVENT-B",company=company,relevance=rel_b
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-REPORT"))
    oa = evaluator.evaluate_outcome(
        quality_assessment_id=qa["assessment_id"],
        protocol_id="P6-E-REPORT",
    )
    ob = evaluator.evaluate_outcome(
        quality_assessment_id=qb["assessment_id"],
        protocol_id="P6-E-REPORT",
    )
    report = evaluator.create_report(
        protocol_id="P6-E-REPORT",
        observation_ids=[oa["observation_id"],ob["observation_id"]],
    )

    assert report["sample_count"] == 1
    assert len(report["report"]["deduplicated_observation_ids"]) == 1
    assert report["sample_sufficiency"] == "UNDECIDED"
    assert report["statistical_test_status"] == "NOT_CONFIGURED"
    assert report["report"]["horizons"]["5"]["stock_return"]["average_pct"] == 5.0


def test_explicit_control_is_excluded_when_usable_event_contaminates_window(
    tmp_path: Path,
):
    (
        _,
        _,
        _,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-CONTAMINATION",
        source_id="SRC-CONTAMINATION",
        content_char="f",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-CONTAMINATION",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(
        EventEvaluationProtocol(
            protocol_id="P6-E-CONTROL",
            control_method=ControlMethod.EXPLICIT_MATCH_SET,
            control_approved=True,
        )
    )
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-CONTROL",
    )
    control = evaluator.create_control_match(
        observation_id=outcome["observation_id"],
        control_as_of_date="2026-09-25",
    )

    assert control["contamination_state"] == "CONTAMINATED"
    assert control["evaluation_status"] == "CONTROL_CONTAMINATED"
    assert "EVENT-CONTAMINATION" in control["contaminated_by_event_ids"]


def test_evaluation_artifacts_are_db_immutable(tmp_path: Path):
    (
        simulation_db,
        _,
        _,
        policy,
        store,
        entities,
        _,
        quality,
        evaluator,
        company,
    ) = _base(tmp_path)
    relevance = _add_event(
        policy=policy,
        store=store,
        entities=entities,
        company=company,
        event_id="EVENT-IMMUTABLE",
        source_id="SRC-IMMUTABLE",
        content_char="a",
    )
    assessment = _historical_quality(
        quality=quality,
        event_id="EVENT-IMMUTABLE",
        company=company,
        relevance=relevance,
    )
    evaluator.register_protocol(EventEvaluationProtocol(protocol_id="P6-E-IMMUTABLE"))
    outcome = evaluator.evaluate_outcome(
        quality_assessment_id=assessment["assessment_id"],
        protocol_id="P6-E-IMMUTABLE",
    )
    report = evaluator.create_report(
        protocol_id="P6-E-IMMUTABLE",
        observation_ids=[outcome["observation_id"]],
    )

    with sqlite3.connect(simulation_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_evaluation_protocol
                SET benchmark_rule='CHANGED'
                WHERE protocol_id='P6-E-IMMUTABLE'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                DELETE FROM event_evidence_outcome_observation
                WHERE observation_id=?
                """,
                (outcome["observation_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE event_evidence_evaluation_report
                SET sample_count=999
                WHERE report_id=?
                """,
                (report["report_id"],),
            )


def test_unapproved_sample_threshold_is_not_invented():
    with pytest.raises(EventEvidenceContractError) as caught:
        EventEvaluationProtocol(
            protocol_id="BAD-THRESHOLD",
            minimum_control_count=5,
        )
    assert caught.value.code == "EVENT_EVALUATION_SAMPLE_THRESHOLD_UNAPPROVED"
