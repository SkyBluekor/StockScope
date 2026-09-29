from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro import (
    CalibrationSplitRole,
    LocalMacroReader,
    MacroObservation,
    MacroStore,
    build_calibration_dataset,
    fred_dgs10_candidate_contract,
)


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"


def _store(tmp_path: Path) -> MacroStore:
    store = MacroStore(tmp_path / "macro.db")
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    return store


def _add_vintage(
    store: MacroStore,
    *,
    run_id: str,
    vintage_id: str,
    start: str,
    count: int,
    value_offset: float = 0.0,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.DATE_ONLY,
) -> None:
    start_date = date.fromisoformat(start)
    store.begin_collection_run(provider="FRED", run_id=run_id)
    for index in range(count):
        obs_date = (start_date + timedelta(days=index)).isoformat()
        value = f"{4.0 + value_offset + index / 100:.2f}"
        available_at = "2026-09-29T10:00:00+00:00"
        store.store_observation(
            run_id=run_id,
            observation=MacroObservation(
                series_id=SERIES,
                native_observation_id=f"DGS10:{obs_date}",
                observation_date=obs_date,
                source_value=value,
                normalized_value=value,
                source_unit="PERCENT",
                source_payload_hash=(
                    f"{vintage_id}-{obs_date}-{value}".encode().hex()[:64].ljust(64, "0")
                ),
                normalizer_version="TEST-NORMALIZER-V1",
                realtime_start=vintage_id,
                realtime_end=vintage_id,
                vintage_id=vintage_id,
                temporal=TemporalEvidence(
                    event_time=obs_date if quality is EvidenceTimeQuality.DATE_ONLY else None,
                    source_published_at=None,
                    provider_published_at=None,
                    first_seen_at=available_at,
                    available_at=available_at,
                    fetched_at=available_at,
                    time_quality=quality,
                ),
            ),
        )
    store.publish_collection_run(run_id)


def _dataset(
    reader: LocalMacroReader,
    *,
    vintage: str,
    start: str,
    end: str,
    role: CalibrationSplitRole = CalibrationSplitRole.DEVELOPMENT,
):
    archive = reader.read_reference_archive_range(
        SERIES,
        observation_start=start,
        observation_end=end,
        vintage_id=vintage,
        warmup_observations=10,
    )
    return build_calibration_dataset(archive=archive, split_role=role)


def test_fixed_vintage_reader_keeps_warmup_separate_and_filters_other_vintage(
    tmp_path: Path,
):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="V1",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
    )
    _add_vintage(
        store,
        run_id="V2",
        vintage_id="2026-09-21",
        start="2026-09-01",
        count=15,
        value_offset=1.0,
    )

    archive = LocalMacroReader(store.db_path).read_reference_archive_range(
        SERIES,
        observation_start="2026-09-11",
        observation_end="2026-09-15",
        vintage_id="2026-09-20",
        warmup_observations=10,
    )

    assert archive["status"] == "READY_REFERENCE_RESEARCH"
    assert archive["warmup_count"] == 10
    assert archive["analysis_count"] == 5
    assert {
        row["vintage_id"]
        for row in archive["warmup_observations"] + archive["analysis_observations"]
    } == {"2026-09-20"}
    assert archive["usage_scope"] == "REFERENCE_RESEARCH_ONLY"
    assert archive["historical_evaluation_eligible"] is False


def test_dataset_excludes_warmup_from_samples_and_reuses_s1_features(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="DEV",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
    )
    dataset = _dataset(
        LocalMacroReader(store.db_path),
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )

    assert dataset["status"] == "READY_REFERENCE_RESEARCH"
    assert dataset["manifest"]["warmup_count"] == 10
    assert dataset["manifest"]["analysis_row_count"] == 5
    assert len(dataset["rows"]) == 5
    assert dataset["rows"][0]["observation_date"] == "2026-09-11"
    ids = {feature["feature_id"] for feature in dataset["rows"][0]["features"]}
    assert ids == {
        "rate_level_pct",
        "delta_bp_1obs",
        "delta_bp_5obs",
        "delta_bp_10obs",
    }
    assert all("shock_label" not in row for row in dataset["rows"])


def test_date_only_dataset_is_reference_research_not_historical_pit(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="DEV",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )
    dataset = _dataset(
        LocalMacroReader(store.db_path),
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )

    assert dataset["historical_evaluation_eligible"] is False
    assert dataset["manifest"]["historical_pit_eligible_count"] == 0
    assert dataset["manifest"]["time_quality_counts"] == {"DATE_ONLY": 5}
    assert "HISTORICAL_TIME_NOT_PROVEN" in dataset["manifest"]["limitations"]


def test_dataset_hash_is_deterministic_and_ignores_other_vintages(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="V1",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
    )
    reader = LocalMacroReader(store.db_path)
    first = _dataset(
        reader,
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )
    second = _dataset(
        reader,
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )
    assert second["dataset_hash"] == first["dataset_hash"]

    _add_vintage(
        store,
        run_id="V2",
        vintage_id="2026-09-21",
        start="2026-09-01",
        count=15,
        value_offset=1.0,
    )
    after_other_vintage = _dataset(
        reader,
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )
    assert after_other_vintage["dataset_hash"] == first["dataset_hash"]


def test_new_revision_within_same_vintage_creates_new_dataset_identity(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="V1",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
    )
    reader = LocalMacroReader(store.db_path)
    original = _dataset(
        reader,
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )

    available_at = "2026-09-30T10:00:00+00:00"
    store.begin_collection_run(provider="FRED", run_id="REV")
    store.store_observation(
        run_id="REV",
        observation=MacroObservation(
            series_id=SERIES,
            native_observation_id="DGS10:2026-09-15",
            observation_date="2026-09-15",
            source_value="9.99",
            normalized_value="9.99",
            source_unit="PERCENT",
            source_payload_hash="f" * 64,
            normalizer_version="TEST-NORMALIZER-V1",
            realtime_start="2026-09-20",
            realtime_end="2026-09-20",
            vintage_id="2026-09-20",
            temporal=TemporalEvidence(
                event_time="2026-09-15",
                source_published_at=None,
                provider_published_at=None,
                first_seen_at=available_at,
                available_at=available_at,
                fetched_at=available_at,
                time_quality=EvidenceTimeQuality.DATE_ONLY,
            ),
        ),
    )
    store.publish_collection_run("REV")

    revised = _dataset(
        reader,
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )
    assert revised["dataset_hash"] != original["dataset_hash"]
    assert original["rows"][-1]["features"][0]["value"] != "9.99"
    assert revised["rows"][-1]["features"][0]["value"] == "9.99"


def test_insufficient_warmup_is_partial_and_not_imputed(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="SHORT",
        vintage_id="2026-09-20",
        start="2026-09-08",
        count=8,
    )
    dataset = _dataset(
        LocalMacroReader(store.db_path),
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )

    assert dataset["status"] == "PARTIAL_REFERENCE_RESEARCH"
    assert dataset["manifest"]["warmup_count"] < 10
    assert "WARMUP_INSUFFICIENT" in dataset["manifest"]["limitations"]
    first_features = {
        feature["feature_id"]: feature
        for feature in dataset["rows"][0]["features"]
    }
    assert first_features["delta_bp_10obs"]["value"] is None
    assert first_features["delta_bp_10obs"]["status"] == "INSUFFICIENT_HISTORY"


def test_archive_and_dataset_build_do_not_write_macro_store(tmp_path: Path):
    store = _store(tmp_path)
    _add_vintage(
        store,
        run_id="DEV",
        vintage_id="2026-09-20",
        start="2026-09-01",
        count=15,
    )
    before = store.inspect()["counts"].copy()
    _dataset(
        LocalMacroReader(store.db_path),
        vintage="2026-09-20",
        start="2026-09-11",
        end="2026-09-15",
    )
    after = store.inspect()["counts"].copy()
    assert after == before
