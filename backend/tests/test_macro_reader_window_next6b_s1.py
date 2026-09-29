from __future__ import annotations

from pathlib import Path

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro import (
    LocalMacroReader,
    MacroObservation,
    MacroStore,
    fred_dgs10_candidate_contract,
)


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"


def _store(tmp_path: Path) -> MacroStore:
    store = MacroStore(tmp_path / "macro.db")
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    return store


def _obs(
    *,
    date: str,
    value: str,
    available_at: str,
    source_hash: str,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.DATE_ONLY,
) -> MacroObservation:
    return MacroObservation(
        series_id=SERIES,
        native_observation_id=f"DGS10:{date}",
        observation_date=date,
        source_value=value,
        normalized_value=value,
        source_unit="PERCENT",
        source_payload_hash=source_hash,
        normalizer_version="TEST-NORMALIZER-V1",
        realtime_start=date,
        realtime_end=date,
        vintage_id=date,
        temporal=TemporalEvidence(
            event_time=date if quality is EvidenceTimeQuality.DATE_ONLY else None,
            source_published_at=None,
            provider_published_at=None,
            first_seen_at=available_at,
            available_at=available_at,
            fetched_at=available_at,
            time_quality=quality,
        ),
    )


def _publish(
    store: MacroStore,
    *,
    run_id: str,
    observation: MacroObservation,
) -> None:
    store.begin_collection_run(provider="FRED", run_id=run_id)
    store.store_observation(run_id=run_id, observation=observation)
    store.publish_collection_run(run_id)


def test_window_blocks_rows_not_available_by_cutoff(tmp_path: Path):
    store = _store(tmp_path)
    _publish(
        store,
        run_id="R1",
        observation=_obs(
            date="2026-09-01",
            value="4.00",
            available_at="2026-09-29T10:00:00+00:00",
            source_hash="a" * 64,
        ),
    )
    _publish(
        store,
        run_id="R2",
        observation=_obs(
            date="2026-09-02",
            value="4.10",
            available_at="2026-09-29T12:00:00+00:00",
            source_hash="b" * 64,
        ),
    )

    result = LocalMacroReader(store.db_path).read_series_window(
        SERIES,
        cutoff="2026-09-29T11:00:00+00:00",
        observation_limit=10,
        historical_eligible_only=False,
    )

    assert result["status"] == "COMPLETE"
    assert [row["observation_date"] for row in result["observations"]] == [
        "2026-09-01"
    ]


def test_window_selects_latest_revision_available_by_cutoff(tmp_path: Path):
    store = _store(tmp_path)
    original = _obs(
        date="2026-09-01",
        value="4.00",
        available_at="2026-09-29T10:00:00+00:00",
        source_hash="a" * 64,
    )
    revised = _obs(
        date="2026-09-01",
        value="4.20",
        available_at="2026-09-29T12:00:00+00:00",
        source_hash="b" * 64,
    )
    _publish(store, run_id="R1", observation=original)
    _publish(store, run_id="R2", observation=revised)

    reader = LocalMacroReader(store.db_path)
    before = reader.read_series_window(
        SERIES,
        cutoff="2026-09-29T11:00:00+00:00",
        observation_limit=10,
        historical_eligible_only=False,
    )
    after = reader.read_series_window(
        SERIES,
        cutoff="2026-09-29T13:00:00+00:00",
        observation_limit=10,
        historical_eligible_only=False,
    )

    assert before["observations"][0]["normalized_value"] == "4.00"
    assert before["observations"][0]["revision_no"] == 1
    assert after["observations"][0]["normalized_value"] == "4.20"
    assert after["observations"][0]["revision_no"] == 2


def test_historical_window_distinguishes_date_only_from_future_exact(tmp_path: Path):
    store = _store(tmp_path)
    _publish(
        store,
        run_id="DATE-ONLY",
        observation=_obs(
            date="2026-09-01",
            value="4.00",
            available_at="2026-09-29T10:00:00+00:00",
            source_hash="a" * 64,
            quality=EvidenceTimeQuality.DATE_ONLY,
        ),
    )

    reader = LocalMacroReader(store.db_path)
    date_only = reader.read_series_window(
        SERIES,
        cutoff="2026-09-29T11:00:00+00:00",
        observation_limit=10,
        historical_eligible_only=True,
    )
    assert date_only["status"] == "UNAVAILABLE"
    assert date_only["reason"] == "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"

    _publish(
        store,
        run_id="EXACT-FUTURE",
        observation=_obs(
            date="2026-09-02",
            value="4.10",
            available_at="2026-09-29T12:00:00+00:00",
            source_hash="b" * 64,
            quality=EvidenceTimeQuality.EXACT,
        ),
    )
    future_only = reader.read_series_window(
        SERIES,
        cutoff="2026-09-29T11:00:00+00:00",
        observation_limit=10,
        historical_eligible_only=True,
    )
    assert future_only["status"] == "UNAVAILABLE"
    assert future_only["reason"] == "DATA_NOT_AVAILABLE_BY_CUTOFF"


def test_window_requires_timezone_aware_cutoff(tmp_path: Path):
    store = _store(tmp_path)
    reader = LocalMacroReader(store.db_path)

    try:
        reader.read_series_window(
            SERIES,
            cutoff="2026-09-29T11:00:00",
            observation_limit=10,
            historical_eligible_only=False,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("timezone-less cutoff must be rejected")
