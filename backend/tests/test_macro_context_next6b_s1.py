from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro import (
    CalibrationStatus,
    LocalMacroReader,
    MacroObservation,
    MacroShockCalibration,
    MacroStore,
    build_macro_context,
    fred_dgs10_candidate_contract,
)


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
AVAILABLE_AT = "2026-09-29T10:00:00+00:00"
CUTOFF = "2026-09-29T11:00:00+00:00"


def _store(tmp_path: Path) -> MacroStore:
    store = MacroStore(tmp_path / "macro.db")
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    return store


def _add_series(
    store: MacroStore,
    *,
    count: int,
    quality: EvidenceTimeQuality,
    available_at: str = AVAILABLE_AT,
) -> None:
    start = date(2026, 9, 1)
    store.begin_collection_run(provider="FRED", run_id="SERIES-RUN")
    for index in range(count):
        current_date = (start + timedelta(days=index)).isoformat()
        value = f"{4 + index / 100:.2f}"
        observation = MacroObservation(
            series_id=SERIES,
            native_observation_id=f"DGS10:{current_date}",
            observation_date=current_date,
            source_value=value,
            normalized_value=value,
            source_unit="PERCENT",
            source_payload_hash=f"{index + 1:064x}",
            normalizer_version="TEST-NORMALIZER-V1",
            realtime_start=current_date,
            realtime_end=current_date,
            vintage_id="2026-09-28",
            temporal=TemporalEvidence(
                event_time=(
                    current_date
                    if quality is EvidenceTimeQuality.DATE_ONLY
                    else None
                ),
                source_published_at=None,
                provider_published_at=None,
                first_seen_at=available_at,
                available_at=available_at,
                fetched_at=available_at,
                time_quality=quality,
            ),
        )
        store.store_observation(
            run_id="SERIES-RUN",
            observation=observation,
        )
    store.publish_collection_run("SERIES-RUN")


def _feature(context: dict[str, object], feature_id: str) -> dict[str, object]:
    features = context["features"]  # type: ignore[index]
    for feature in features["features"]:
        if feature["feature_id"] == feature_id:
            return feature
    raise AssertionError(feature_id)


def _rate_shock(context: dict[str, object]) -> dict[str, object]:
    assessment = context["shock_assessment"]  # type: ignore[index]
    for component in assessment["components"]:
        if component["shock_type"] == "RATE_SPIKE":
            return component
    raise AssertionError("RATE_SPIKE")


def test_reference_context_uses_date_only_data_but_preserves_limitation(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=11,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )

    context = build_macro_context(
        reader=LocalMacroReader(store.db_path),
        decision_cutoff=CUTOFF,
        usage="REFERENCE_SHADOW",
    )

    assert context["status"] == "COMPLETE_REFERENCE"
    assert context["availability"]["returned_observations"] == 11
    assert context["availability"]["historical_evaluation_eligible"] is False
    assert context["availability"]["time_qualities"] == ["DATE_ONLY"]
    assert "HISTORICAL_TIME_NOT_PROVEN" in context["limitations"]

    assert _feature(context, "rate_level_pct")["value"] == "4.1"
    assert _feature(context, "delta_bp_1obs")["value"] == "1"
    assert _feature(context, "delta_bp_5obs")["value"] == "5"
    assert _feature(context, "delta_bp_10obs")["value"] == "10"

    rate = _rate_shock(context)
    assert rate["state"] == "UNCALIBRATED"
    assert rate["reason"] == "CALIBRATION_NOT_DEFINED"
    assert context["shock_assessment"]["composite"]["weighted_severity"] is None
    assert context["shock_assessment"]["episode"]["enabled"] is False
    assert all(
        component["state"] != "NORMAL"
        for component in context["shock_assessment"]["components"]
    )
    assert context["production_decision_approved"] is False


def test_historical_context_does_not_fallback_to_reference_date_only_data(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=11,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )

    context = build_macro_context(
        reader=LocalMacroReader(store.db_path),
        decision_cutoff=CUTOFF,
        usage="HISTORICAL_EVALUATION",
    )

    assert context["status"] == "UNAVAILABLE"
    assert context["reason"] == "NOT_EVALUATION_ELIGIBLE"
    assert context["availability"]["returned_observations"] == 0
    assert "HISTORICAL_TIME_NOT_PROVEN" in context["limitations"]
    assert _rate_shock(context)["state"] == "UNKNOWN"


def test_context_hash_is_deterministic_for_same_cutoff_and_inputs(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=11,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )
    reader = LocalMacroReader(store.db_path)

    first = build_macro_context(
        reader=reader,
        decision_cutoff="2026-09-29T20:00:00+09:00",
        usage="REFERENCE_SHADOW",
    )
    second = build_macro_context(
        reader=reader,
        decision_cutoff="2026-09-29T11:00:00+00:00",
        usage="REFERENCE_SHADOW",
    )

    assert first["decision_cutoff"] == second["decision_cutoff"]
    assert first["context_hash"] == second["context_hash"]
    assert first["context_id"] == second["context_id"]


def test_future_revision_does_not_change_past_context_hash(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=11,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )
    reader = LocalMacroReader(store.db_path)
    before = build_macro_context(
        reader=reader,
        decision_cutoff=CUTOFF,
        usage="REFERENCE_SHADOW",
    )

    revised_date = date(2026, 9, 11).isoformat()
    store.begin_collection_run(provider="FRED", run_id="REVISION-RUN")
    store.store_observation(
        run_id="REVISION-RUN",
        observation=MacroObservation(
            series_id=SERIES,
            native_observation_id=f"DGS10:{revised_date}",
            observation_date=revised_date,
            source_value="4.50",
            normalized_value="4.50",
            source_unit="PERCENT",
            source_payload_hash="f" * 64,
            normalizer_version="TEST-NORMALIZER-V1",
            realtime_start=revised_date,
            realtime_end=revised_date,
            vintage_id="2026-09-30",
            temporal=TemporalEvidence(
                event_time=revised_date,
                source_published_at=None,
                provider_published_at=None,
                first_seen_at="2026-09-30T10:00:00+00:00",
                available_at="2026-09-30T10:00:00+00:00",
                fetched_at="2026-09-30T10:00:00+00:00",
                time_quality=EvidenceTimeQuality.DATE_ONLY,
            ),
        ),
    )
    store.publish_collection_run("REVISION-RUN")

    past_again = build_macro_context(
        reader=reader,
        decision_cutoff=CUTOFF,
        usage="REFERENCE_SHADOW",
    )
    future = build_macro_context(
        reader=reader,
        decision_cutoff="2026-09-30T11:00:00+00:00",
        usage="REFERENCE_SHADOW",
    )

    assert past_again["context_hash"] == before["context_hash"]
    assert future["context_hash"] != before["context_hash"]
    assert _feature(future, "rate_level_pct")["value"] == "4.5"


def test_short_reference_history_is_partial_not_normal(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=3,
        quality=EvidenceTimeQuality.DATE_ONLY,
    )

    context = build_macro_context(
        reader=LocalMacroReader(store.db_path),
        decision_cutoff=CUTOFF,
        usage="REFERENCE_SHADOW",
    )

    assert context["status"] == "PARTIAL"
    assert _feature(context, "delta_bp_5obs")["status"] == "INSUFFICIENT_HISTORY"
    assert _feature(context, "delta_bp_10obs")["status"] == "INSUFFICIENT_HISTORY"
    assert _rate_shock(context)["state"] == "UNCALIBRATED"
    assert all(
        component["state"] != "NORMAL"
        for component in context["shock_assessment"]["components"]
    )


def test_next6b_s1_refuses_to_execute_approved_calibration(tmp_path: Path):
    store = _store(tmp_path)
    _add_series(
        store,
        count=11,
        quality=EvidenceTimeQuality.EXACT,
    )
    approved = MacroShockCalibration(
        calibration_id="RATE-SPIKE-RESEARCH-V1",
        version="v1",
        shock_type="RATE_SPIKE",
        feature_contract_version="VN_NEXT6B_S1_MACRO_FEATURE_V1",
        training_scope="TRAIN",
        holdout_scope="HOLDOUT",
        lookback=100,
        minimum_sample=50,
        method="TEST_ONLY",
        threshold="TEST_ONLY",
        status=CalibrationStatus.APPROVED_RESEARCH,
    )

    with pytest.raises(ValueError, match="does not execute approved"):
        build_macro_context(
            reader=LocalMacroReader(store.db_path),
            decision_cutoff=CUTOFF,
            usage="HISTORICAL_EVALUATION",
            rate_calibration=approved,
        )
