from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.main import app
from app.macro import (
    MacroObservation,
    MacroStore,
    fred_dgs10_candidate_contract,
)


client = TestClient(app)
SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
CUTOFF = "2026-10-01T11:00:00+00:00"


def _create_macro_db(path: Path, *, count: int = 30) -> None:
    store = MacroStore(path)
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    store.begin_collection_run(provider="FRED", run_id="API-MACRO-RUN")

    start = date(2026, 9, 1)
    for index in range(count):
        current_date = (start + timedelta(days=index)).isoformat()
        value = f"{4 + (index * index) / 1000:.3f}"
        store.store_observation(
            run_id="API-MACRO-RUN",
            observation=MacroObservation(
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
                vintage_id="2026-09-30",
                temporal=TemporalEvidence(
                    event_time=current_date,
                    source_published_at=None,
                    provider_published_at=None,
                    first_seen_at="2026-09-30T10:00:00+00:00",
                    available_at="2026-09-30T10:00:00+00:00",
                    fetched_at="2026-09-30T10:00:00+00:00",
                    time_quality=EvidenceTimeQuality.DATE_ONLY,
                ),
            ),
        )
    store.publish_collection_run("API-MACRO-RUN")


def test_macro_reference_diagnostic_api_is_read_only_descriptive_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    _create_macro_db(macro_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))

    before = macro_db.stat()
    response = client.get(
        "/api/macro/reference-diagnostic",
        params={"cutoff": CUTOFF},
    )
    after = macro_db.stat()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()

    assert (
        body["contract_version"]
        == "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_API_V1"
    )
    assert body["decision_cutoff"] == "2026-10-01T11:00:00+00:00"
    assert body["reference_diagnostic"]["projection_mode"] == "AS_OF"
    assert body["reference_diagnostic"]["diagnostic_id"].startswith(
        "RATEDIAG-"
    )
    assert len(body["reference_diagnostic"]["diagnostic_hash"]) == 64

    source = body["reference_diagnostic"]["source"]
    assert source["eligible_observation_count"] == 30
    assert source["observation_refs_hash"]
    assert "observation_refs" not in source

    horizons = body["reference_diagnostic"]["horizons"]
    assert [item["feature_id"] for item in horizons] == [
        "delta_bp_1obs",
        "delta_bp_5obs",
        "delta_bp_10obs",
    ]
    assert all(item["tail"]["adequacy_pass"] is None for item in horizons)
    assert all(item["tail"]["threshold"] is None for item in horizons)
    assert all(item["mad"]["adequacy_pass"] is None for item in horizons)
    assert all(item["mad"]["threshold"] is None for item in horizons)

    assert body["reference_adequacy"] == {
        "state": "UNRESOLVED",
        "numeric_policy_defined": False,
        "minimum_prior_observations": None,
        "recommended_support": None,
    }
    assert body["rate_spike"]["state"] == "UNCALIBRATED"
    assert body["production_decision_approved"] is False
    assert "STRATEGY_INPUT" in body["reference_diagnostic"]["governance"][
        "prohibited_consumers"
    ]
    assert "RISK_GATE" in body["reference_diagnostic"]["governance"][
        "prohibited_consumers"
    ]
    assert "PRODUCTION_POLICY" in body["reference_diagnostic"]["governance"][
        "prohibited_consumers"
    ]

    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_macro_reference_diagnostic_api_rejects_timezone_less_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    _create_macro_db(macro_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))

    response = client.get(
        "/api/macro/reference-diagnostic",
        params={"cutoff": "2026-10-01T11:00:00"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "MACRO_REFERENCE_INVALID_REQUEST"
    assert "timezone-aware" in detail["message"]


def test_macro_reference_diagnostic_api_fails_closed_when_store_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing" / "macro.db"
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(missing))

    response = client.get(
        "/api/macro/reference-diagnostic",
        params={"cutoff": CUTOFF},
    )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    detail = response.json()["detail"]
    assert detail["code"] == "MACRO_REFERENCE_UNAVAILABLE"
    assert detail["reason"] == "STORE_NOT_FOUND"
    assert not missing.exists()


def test_macro_reference_diagnostic_api_uses_current_utc_cutoff_when_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    _create_macro_db(macro_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))

    import app.api.macro as macro_api

    monkeypatch.setattr(
        macro_api,
        "_default_cutoff",
        lambda: "2026-10-01T12:34:56+00:00",
    )

    response = client.get("/api/macro/reference-diagnostic")

    assert response.status_code == 200
    assert response.json()["decision_cutoff"] == "2026-10-01T12:34:56+00:00"
