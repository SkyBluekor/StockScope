from __future__ import annotations

from pathlib import Path

import pytest

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro import (
    LocalMacroReader,
    MacroContractError,
    MacroObservation,
    MacroPreparedRangeManifest,
    MacroResearchProtocol,
    MacroStore,
    fred_dgs10_candidate_contract,
)
from tools.data.migrate_macro_next6a_s1 import migrate_macro_store


NOW = "2026-09-29T07:30:00+00:00"


def _temporal(
    *,
    available_at: str,
    fetched_at: str,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.PROVIDER_TIME,
) -> TemporalEvidence:
    return TemporalEvidence(
        event_time=None,
        source_published_at=None,
        provider_published_at=available_at if quality is not EvidenceTimeQuality.DATE_ONLY else None,
        first_seen_at=available_at,
        available_at=available_at,
        fetched_at=fetched_at,
        time_quality=quality,
    )


def _observation(
    *,
    value: str,
    source_hash: str,
    available_at: str,
    fetched_at: str,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.PROVIDER_TIME,
    vintage_id: str | None = None,
) -> MacroObservation:
    return MacroObservation(
        series_id="US_10Y_CONSTANT_MATURITY_YIELD",
        native_observation_id="DGS10:2026-09-28",
        observation_date="2026-09-28",
        source_value=value,
        normalized_value=value,
        source_unit="PERCENT",
        source_payload_hash=source_hash,
        normalizer_version="DGS10-PERCENT-V1",
        realtime_start="2026-09-28",
        realtime_end="2026-09-28",
        vintage_id=vintage_id,
        temporal=_temporal(
            available_at=available_at,
            fetched_at=fetched_at,
            quality=quality,
        ),
    )


def _store(tmp_path: Path) -> MacroStore:
    path = tmp_path / "macro.db"
    store = MacroStore(path, clock=lambda: NOW)
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    return store


def test_migration_is_idempotent_and_has_zero_external_requests(tmp_path: Path):
    path = tmp_path / "macro.db"
    first = migrate_macro_store(path)
    second = migrate_macro_store(path)

    assert first["schema_version"] == "VN_NEXT6A_S1_MACRO_STORE_V1"
    assert first["external_network_requests"] == 0
    assert first["historical_backfill_performed"] is False
    assert second["counts"] == first["counts"]


def test_same_observation_is_noop_but_changed_source_is_new_revision(tmp_path: Path):
    store = _store(tmp_path)
    run1 = store.begin_collection_run(provider="FRED", run_id="RUN-1")
    first = store.store_observation(
        run_id=run1["run_id"],
        observation=_observation(
            value="4.10",
            source_hash="a" * 64,
            available_at="2026-09-29T06:00:00+00:00",
            fetched_at="2026-09-29T06:01:00+00:00",
            vintage_id="2026-09-29",
        ),
    )
    duplicate = store.store_observation(
        run_id=run1["run_id"],
        observation=_observation(
            value="4.10",
            source_hash="a" * 64,
            available_at="2026-09-29T06:00:00+00:00",
            fetched_at="2026-09-29T06:01:00+00:00",
            vintage_id="2026-09-29",
        ),
    )
    store.publish_collection_run("RUN-1")

    run2 = store.begin_collection_run(provider="FRED", run_id="RUN-2")
    revised = store.store_observation(
        run_id=run2["run_id"],
        observation=_observation(
            value="4.12",
            source_hash="b" * 64,
            available_at="2026-09-30T06:00:00+00:00",
            fetched_at="2026-09-30T06:01:00+00:00",
            vintage_id="2026-09-30",
        ),
    )
    store.publish_collection_run("RUN-2")

    assert first["revision_no"] == 1
    assert duplicate["duplicate"] is True
    assert duplicate["revision_no"] == 1
    assert revised["revision_no"] == 2
    state = store.inspect()
    assert state["counts"]["observation_revision_count"] == 2
    assert state["counts"]["published_observation_count"] == 2


def test_failed_batch_never_becomes_visible_to_reader(tmp_path: Path):
    store = _store(tmp_path)
    run = store.begin_collection_run(provider="FRED", run_id="FAILED-RUN")
    store.store_observation(
        run_id=run["run_id"],
        observation=_observation(
            value="4.10",
            source_hash="a" * 64,
            available_at="2026-09-29T06:00:00+00:00",
            fetched_at="2026-09-29T06:01:00+00:00",
        ),
    )
    store.fail_collection_run(run["run_id"])

    reader = LocalMacroReader(store.db_path)
    result = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff="2026-09-29T07:00:00+00:00",
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "DATA_ABSENT"
    assert store.inspect()["counts"]["published_observation_count"] == 0


def test_future_revision_does_not_change_past_snapshot_hash(tmp_path: Path):
    store = _store(tmp_path)
    run1 = store.begin_collection_run(provider="FRED", run_id="PIT-1")
    store.store_observation(
        run_id=run1["run_id"],
        observation=_observation(
            value="4.10",
            source_hash="a" * 64,
            available_at="2026-09-29T06:00:00+00:00",
            fetched_at="2026-09-29T06:01:00+00:00",
            vintage_id="V1",
        ),
    )
    store.publish_collection_run("PIT-1")

    reader = LocalMacroReader(store.db_path)
    before = reader.read_snapshot(
        ["US_10Y_CONSTANT_MATURITY_YIELD"],
        cutoff="2026-09-29T07:00:00+00:00",
    )

    run2 = store.begin_collection_run(provider="FRED", run_id="PIT-2")
    store.store_observation(
        run_id=run2["run_id"],
        observation=_observation(
            value="4.12",
            source_hash="b" * 64,
            available_at="2026-09-30T06:00:00+00:00",
            fetched_at="2026-09-30T06:01:00+00:00",
            vintage_id="V2",
        ),
    )
    store.publish_collection_run("PIT-2")

    past_again = reader.read_snapshot(
        ["US_10Y_CONSTANT_MATURITY_YIELD"],
        cutoff="2026-09-29T07:00:00+00:00",
    )
    later = reader.read_snapshot(
        ["US_10Y_CONSTANT_MATURITY_YIELD"],
        cutoff="2026-09-30T07:00:00+00:00",
    )

    assert past_again == before
    assert later["snapshot_hash"] != before["snapshot_hash"]
    assert later["components"][0]["observation"]["normalized_value"] == "4.12"


def test_date_only_can_be_read_for_reference_but_not_historical_evaluation(tmp_path: Path):
    store = _store(tmp_path)
    run = store.begin_collection_run(provider="FRED", run_id="DATE-ONLY")
    store.store_observation(
        run_id=run["run_id"],
        observation=_observation(
            value="4.10",
            source_hash="d" * 64,
            available_at="2026-09-29T06:00:00+00:00",
            fetched_at="2026-09-29T06:01:00+00:00",
            quality=EvidenceTimeQuality.DATE_ONLY,
        ),
    )
    store.publish_collection_run(run["run_id"])

    reader = LocalMacroReader(store.db_path)
    strict = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff="2026-09-29T07:00:00+00:00",
        historical_eligible_only=True,
    )
    reference = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff="2026-09-29T07:00:00+00:00",
        historical_eligible_only=False,
    )

    assert strict["status"] == "UNAVAILABLE"
    assert strict["reason"] == "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"
    assert reference["status"] == "COMPLETE"
    assert reference["observation"]["time_quality"] == "DATE_ONLY"


def test_store_rejects_secret_like_collection_metadata(tmp_path: Path):
    store = _store(tmp_path)
    with pytest.raises(MacroContractError, match="secret/credential"):
        store.begin_collection_run(
            provider="FRED",
            metadata={"api_key": "must-not-be-stored"},
        )


def test_prepared_range_and_research_protocol_are_immutable_and_deduplicated(tmp_path: Path):
    store = _store(tmp_path)
    manifest = MacroPreparedRangeManifest(
        series_id="US_10Y_CONSTANT_MATURITY_YIELD",
        start_date="2026-01-01",
        end_date="2026-09-28",
        expected_count=180,
        stored_count=180,
        missing_count=0,
        unavailable_count=0,
        date_only_count=0,
        eligible_count=180,
        source_contract_version="FRED-DGS10-CANDIDATE-V1",
        normalizer_version="DGS10-PERCENT-V1",
        source_manifest_hash="f" * 64,
        prepared_at=NOW,
    )
    first = store.store_prepared_range(manifest)
    second = store.store_prepared_range(manifest)

    protocol = MacroResearchProtocol(
        protocol_id="NEXT6-MACRO-SHADOW-V1",
        protocol_version="v1",
        baseline_identity="SCANNER-0.21.3.9",
        cutoff_policy="KOREA_EOD_CONFIRMED_AS_OF",
        development_rule="DEVELOPMENT_SEPARATE",
        holdout_rule="HOLDOUT_SEPARATE",
        prospective_rule="PROSPECTIVE_FORWARD_ONLY",
        pit_requirement="AVAILABLE_AT_LE_DECISION_CUTOFF",
        ablation_sequence=("RATE_ONLY", "RATE_PLUS_VOLATILITY"),
        missing_data_reporting_rule="REPORT_ALL_EXCLUSIONS",
    )
    p1 = store.register_research_protocol(protocol)
    p2 = store.register_research_protocol(protocol)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert p1["duplicate"] is False
    assert p2["duplicate"] is True

    reader = LocalMacroReader(store.db_path)
    prepared = reader.read_prepared_range(
        manifest.series_id,
        start_date=manifest.start_date,
        end_date=manifest.end_date,
    )
    assert prepared["status"] == "COMPLETE"
    assert prepared["manifest"]["content_hash"] == manifest.content_hash
