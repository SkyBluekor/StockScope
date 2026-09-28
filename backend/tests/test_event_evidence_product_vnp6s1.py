from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import event_evidence as event_evidence_api
from app.event_evidence.product import EventEvidenceProductQuery
from tools.data.migrate_event_evidence_vnp6s1 import migrate_event_evidence_store


NOW = "2026-09-28T08:00:00+09:00"


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "simulation.db"
    sqlite3.connect(path).close()
    migrate_event_evidence_store(path)
    return path


def _insert_reference(
    db: Path,
    *,
    suffix: str,
    source_kind: str,
    quality_state: str = "USABLE",
) -> None:
    policy_id = f"POL-{suffix}"
    policy_hash = (suffix[0].lower() if suffix else "a") * 64
    source_id = f"SRC-{suffix}"
    source_hash = ("b" if suffix[0].lower() != "b" else "c") * 64
    event_id = f"EVENT-{suffix}"
    event_hash = ("d" if suffix[0].lower() != "d" else "e") * 64
    source_bundle_hash = "f" * 64
    entity_id = "ENTITY-005930"
    entity_hash = "1" * 64
    relevance_id = f"REL-{suffix}"
    relevance_hash = ("2" if suffix[0].lower() != "2" else "3") * 64
    assessment_id = f"QA-{suffix}"

    quality_payload = {
        "assessment_id": assessment_id,
        "source_refs": [
            {
                "source_ref_id": source_id,
                "source_ref_hash": source_hash,
                "rights_policy_id": policy_id,
                "policy_hash": policy_hash,
            }
        ],
    }
    quality_hash = _digest(quality_payload)

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO event_evidence_policy_snapshot(
                policy_id,policy_contract_version,source_kind,policy_version,
                display_allowed,normalization_allowed,raw_retention_allowed,
                derived_retention_allowed,ai_transform_allowed,
                historical_evaluation_allowed,prediction_input_allowed,
                attribution_required,effective_from,policy_basis,
                policy_json,policy_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                policy_id,
                "TEST_POLICY_CONTRACT",
                source_kind,
                "test-v1",
                1,1,0,1,0,1,0,0,
                None,
                "TEST_FIXTURE_ONLY",
                _canonical_json({"policy_id": policy_id}),
                policy_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_source_ref(
                source_ref_id,source_ref_contract_version,source_kind,
                source_native_id,rights_policy_id,rights_policy_hash,
                source_url,source_name,content_hash,event_time,
                source_published_at,provider_published_at,first_seen_at,
                available_at,fetched_at,corrected_at,time_quality,
                temporal_contract_version,source_ref_json,source_ref_hash,
                created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source_id,
                "TEST_SOURCE_REF",
                source_kind,
                f"native-{suffix}",
                policy_id,
                policy_hash,
                None,
                "OpenDART" if source_kind != "TEST_SYNTHETIC" else "Fixture",
                "9" * 64,
                "2026-09-28T07:30:00+09:00",
                "2026-09-28T07:35:00+09:00",
                "2026-09-28T07:35:00+09:00",
                "2026-09-28T07:40:00+09:00",
                "2026-09-28T07:40:00+09:00",
                "2026-09-28T07:40:00+09:00",
                None,
                "EXACT",
                "TEST_TEMPORAL",
                _canonical_json({"source_ref_id": source_id}),
                source_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_record(
                event_id,event_version,record_version,hash_contract_version,
                event_state,supersedes_version,event_type,scope,event_time,
                available_at,time_quality,temporal_json,event_payload_json,
                source_bundle_hash,event_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,1,"TEST_RECORD","TEST_HASH","ORIGINAL",None,
                "RIGHTS_ISSUE","COMPANY",
                "2026-09-28T07:30:00+09:00",
                "2026-09-28T07:40:00+09:00",
                "EXACT",
                _canonical_json({"available_at":"2026-09-28T07:40:00+09:00"}),
                "{}",
                source_bundle_hash,
                event_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_record_source(
                event_id,event_version,sequence,source_ref_id,source_ref_hash
            ) VALUES(?,?,?,?,?)
            """,
            (event_id,1,1,source_id,source_hash),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO event_evidence_entity(
                entity_id,entity_contract_version,entity_type,entity_key,
                market,ticker,name,identity_source,identity_as_of,
                identity_json,identity_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entity_id,
                "TEST_ENTITY",
                "LISTED_COMPANY",
                "KOSPI:005930",
                "KOSPI",
                "005930",
                "삼성전자",
                "TEST_MASTER",
                "2026-09-28T00:00:00+09:00",
                _canonical_json({"market":"KOSPI","ticker":"005930"}),
                entity_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_entity_relevance(
                relevance_id,relevance_contract_version,event_id,event_version,
                event_hash,entity_id,entity_hash,relation_type,
                relevance_state,evidence_kind,evidence_ref,evidence_as_of,
                relation_json,relation_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                relevance_id,
                "TEST_REL",
                event_id,
                1,
                event_hash,
                entity_id,
                entity_hash,
                "DIRECT_COMPANY",
                "CONFIRMED",
                "SOURCE_DIRECT",
                f"source:{source_id}",
                "2026-09-28T07:45:00+09:00",
                _canonical_json({"source_ref_id":source_id}),
                relevance_hash,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_quality_assessment(
                assessment_id,quality_contract_version,assessment_scope,
                assessment_as_of,event_id,event_version,event_hash,
                source_bundle_hash,entity_id,entity_hash,relevance_id,
                relevance_hash,relation_type,rights_policy_bundle_hash,
                canonical_event_id,canonical_version,canonical_hash,
                resolution_hash,rights_state,integrity_state,temporal_state,
                relevance_state,resolution_state,revision_state,
                corroboration_state,source_count,distinct_source_origin_count,
                quality_state,blocking_reasons_json,insufficient_reasons_json,
                limitations_json,quality_json,quality_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                assessment_id,
                "TEST_QUALITY",
                "REFERENCE",
                "2026-09-28T07:50:00+09:00",
                event_id,
                1,
                event_hash,
                source_bundle_hash,
                entity_id,
                entity_hash,
                relevance_id,
                relevance_hash,
                "DIRECT_COMPANY",
                "7" * 64,
                None,None,None,None,
                "ALLOWED",
                "MATCH",
                "ELIGIBLE",
                "CONFIRMED",
                "DISTINCT",
                "ORIGINAL",
                "SINGLE_SOURCE",
                1,
                1,
                quality_state,
                "[]","[]","[]",
                _canonical_json(quality_payload),
                quality_hash,
                NOW,
            ),
        )


def _insert_synthetic_gate_pass(db: Path) -> None:
    eval_protocol_json = _canonical_json({"protocol_id":"EVAL-SYN"})
    eval_protocol_hash = _digest({"protocol_id":"EVAL-SYN"})
    report_payload = {
        "report_id":"REPORT-SYN",
        "observations":[],
        "controls":[],
    }
    report_hash = _digest(report_payload)
    gate_protocol_json = _canonical_json({"protocol_id":"GATE-SYN"})
    gate_protocol_hash = _digest({"protocol_id":"GATE-SYN"})
    decision_payload = {
        "decision_id":"DECISION-SYN",
        "decision":"PASS",
        "prediction_eligible":False,
    }
    decision_hash = _digest(decision_payload)

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO event_evidence_evaluation_protocol(
                protocol_id,protocol_contract_version,control_method,
                control_approved,observation_windows_json,
                reference_price_rule,benchmark_rule,statistical_test_status,
                minimum_control_count,protocol_json,protocol_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "EVAL-SYN","TEST","NONE",0,"[1,5,20]",
                "PREVIOUS_CONFIRMED_DAILY_CLOSE","MAIN_MARKET_INDEX",
                "NOT_CONFIGURED",None,eval_protocol_json,eval_protocol_hash,NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_evaluation_report(
                report_id,report_contract_version,protocol_id,protocol_hash,
                report_status,sample_count,sample_sufficiency,
                statistical_test_status,observation_bundle_json,
                report_json,report_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "REPORT-SYN","TEST","EVAL-SYN",eval_protocol_hash,
                "COMPLETE",0,"UNDECIDED","NOT_CONFIGURED","[]",
                _canonical_json(report_payload),report_hash,NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_value_gate_protocol(
                protocol_id,protocol_contract_version,status,gate_kind,
                criteria_precommitted,sample_rule_approved,
                uncertainty_rule_approved,multiple_testing_policy_approved,
                control_rule_approved,required_horizons_json,
                minimum_sample_count,minimum_clean_control_count,
                minimum_observed_difference_pct_points,
                protocol_json,protocol_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "GATE-SYN","TEST","SYNTHETIC_TEST_ONLY",
                "OBSERVATIONAL_INCREMENTAL_VALUE",
                1,1,1,1,1,"[1,5,20]",1,1,0.0,
                gate_protocol_json,gate_protocol_hash,NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_evidence_value_gate_decision(
                decision_id,decision_contract_version,gate_protocol_id,
                gate_protocol_hash,evaluation_report_id,
                evaluation_report_hash,evidence_population,integrity_state,
                decision,decision_reasons_json,sample_sufficiency,
                control_status_json,uncertainty_status,
                multiple_testing_status,horizon_results_json,
                product_scope,prediction_eligible,decision_json,
                decision_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "DECISION-SYN","TEST","GATE-SYN",gate_protocol_hash,
                "REPORT-SYN",report_hash,"SYNTHETIC_ONLY","MATCH","PASS",
                '["INCREMENTAL_VALUE_CRITERIA_MET"]',"UNDECIDED",
                "{}","NOT_CONFIGURED","APPROVED_FOR_SYNTHETIC_TEST",
                "{}","REFERENCE_CONTEXT",0,
                _canonical_json(decision_payload),decision_hash,NOW,
            ),
        )


def _counts(db: Path) -> dict[str, int]:
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name LIKE 'event_evidence_%'
            ORDER BY name
            """
        ).fetchall()
        return {
            str(row[0]): int(
                conn.execute(f"SELECT COUNT(*) FROM {row[0]}").fetchone()[0]
            )
            for row in rows
        }


def test_empty_store_returns_normal_no_evidence_state(tmp_path: Path):
    db = _db(tmp_path)
    result = EventEvidenceProductQuery(db).stock_status("005930", "KOSPI")

    assert result["event_evidence"] == {
        "status":"NO_VALIDATED_EVIDENCE",
        "reference_count":0,
        "latest_as_of":None,
        "items":[],
    }
    assert result["value_validation"] == {
        "status":"NOT_EVALUATED",
        "product_scope":"RESEARCH_ONLY",
    }
    assert result["recent_news"]["mode"] == "DISPLAY_ONLY"
    assert result["recent_news"]["decision_input"] is False
    assert result["prediction"] == {
        "status":"NOT_VALIDATED",
        "direction":None,
        "horizon_sessions":None,
        "probability":None,
    }


def test_real_reference_is_projected_without_internal_artifact_ids(tmp_path: Path):
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="REAL",
        source_kind="OPENDART_DISCLOSURE",
        quality_state="USABLE",
    )

    result = EventEvidenceProductQuery(db).stock_status("005930", "KOSPI")

    assert result["event_evidence"]["status"] == "REFERENCE_AVAILABLE"
    assert result["event_evidence"]["reference_count"] == 1
    item = result["event_evidence"]["items"][0]
    assert item["event_type"] == "RIGHTS_ISSUE"
    assert item["relation_type"] == "DIRECT_COMPANY"
    assert item["quality_state"] == "USABLE"
    assert item["source_kinds"] == ["OPENDART_DISCLOSURE"]
    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in (
        "assessment_id",
        "event_id",
        "entity_id",
        "quality_hash",
        "source_ref_id",
        "decision_hash",
    ):
        assert forbidden not in serialized


def test_synthetic_and_insufficient_evidence_are_not_product_references(
    tmp_path: Path,
):
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="SYN",
        source_kind="TEST_SYNTHETIC",
        quality_state="USABLE",
    )
    _insert_reference(
        db,
        suffix="WEAK",
        source_kind="OPENDART_DISCLOSURE",
        quality_state="INSUFFICIENT",
    )

    result = EventEvidenceProductQuery(db).stock_status("005930", "KOSPI")
    assert result["event_evidence"]["status"] == "NO_VALIDATED_EVIDENCE"
    assert result["event_evidence"]["items"] == []


def test_corrupt_reference_fails_closed(tmp_path: Path):
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="BROKEN",
        source_kind="OPENDART_DISCLOSURE",
        quality_state="USABLE",
    )
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER trg_event_quality_immutable_update")
        conn.execute(
            """
            UPDATE event_evidence_quality_assessment
            SET quality_json='{"corrupt":true}'
            WHERE assessment_id='QA-BROKEN'
            """
        )

    result = EventEvidenceProductQuery(db).stock_status("005930", "KOSPI")
    assert result["event_evidence"]["status"] == "EVIDENCE_BLOCKED"
    assert result["event_evidence"]["items"] == []


def test_synthetic_value_gate_pass_is_not_product_pass(tmp_path: Path):
    db = _db(tmp_path)
    _insert_reference(
        db,
        suffix="ENTITY",
        source_kind="TEST_SYNTHETIC",
        quality_state="USABLE",
    )
    _insert_synthetic_gate_pass(db)

    result = EventEvidenceProductQuery(db).stock_status("005930", "KOSPI")
    assert result["value_validation"] == {
        "status":"NOT_EVALUATED",
        "product_scope":"RESEARCH_ONLY",
    }
    assert result["prediction"]["status"] == "NOT_VALIDATED"


def test_product_api_is_read_only_and_entity_absence_is_200(
    tmp_path: Path,
    monkeypatch,
):
    db = _db(tmp_path)
    before = _counts(db)
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))

    app = FastAPI()
    app.include_router(event_evidence_api.router, prefix="/api")
    client = TestClient(app)
    response = client.get("/api/stocks/005930/event-evidence?market=KOSPI")

    assert response.status_code == 200
    assert response.json()["event_evidence"]["status"] == "NO_VALIDATED_EVIDENCE"
    assert response.json()["prediction"]["direction"] is None
    assert _counts(db) == before


def test_product_api_reports_schema_not_ready_without_mutating_db(
    tmp_path: Path,
    monkeypatch,
):
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))

    app = FastAPI()
    app.include_router(event_evidence_api.router, prefix="/api")
    client = TestClient(app)
    response = client.get("/api/stocks/005930/event-evidence?market=KOSPI")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVENT_EVIDENCE_SCHEMA_NOT_READY"
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0] == 0
