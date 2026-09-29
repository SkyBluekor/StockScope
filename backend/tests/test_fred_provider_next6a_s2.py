from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.integrations.fred.client import FredApiError, FredClient, FredSettings
from app.macro import LocalMacroReader, MacroStore
from app.macro.providers.fred import collect_fred_dgs10, probe_fred_dgs10


def _settings(key: str | None = "a" * 32) -> FredSettings:
    return FredSettings(_env_file=None, fred_api_key=key)


def test_fred_client_paginates_without_exposing_api_key():
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        params = dict(request.url.params)
        assert params["api_key"] == "a" * 32
        assert params["file_type"] == "json"
        offset = int(params["offset"])
        payload = {
            "count": 3,
            "offset": offset,
            "limit": 2,
            "observations": (
                [
                    {
                        "realtime_start": "2026-09-28",
                        "realtime_end": "2026-09-28",
                        "date": "2026-09-25",
                        "value": "4.10",
                    },
                    {
                        "realtime_start": "2026-09-28",
                        "realtime_end": "2026-09-28",
                        "date": "2026-09-26",
                        "value": ".",
                    },
                ]
                if offset == 0
                else [
                    {
                        "realtime_start": "2026-09-28",
                        "realtime_end": "2026-09-28",
                        "date": "2026-09-28",
                        "value": "4.12",
                    }
                ]
            ),
        }
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = FredClient(_settings(), http_client=http)
    batch = client.observations(
        "DGS10",
        observation_start="2026-09-25",
        observation_end="2026-09-28",
        page_limit=2,
    )

    assert len(batch.observations) == 3
    assert len(batch.pages) == 2
    assert batch.pages[0].safe_params["series_id"] == "DGS10"
    assert "api_key" not in batch.pages[0].safe_params
    assert all("a" * 32 in url for url in seen_urls)


def test_fred_error_message_never_contains_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error_message": str(request.url)})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = FredClient(_settings(), http_client=http)

    with pytest.raises(FredApiError) as exc_info:
        client.series("DGS10")

    assert "a" * 32 not in str(exc_info.value)
    assert "api_key" not in str(exc_info.value)
    assert exc_info.value.status_code == 403


def test_fred_probe_reports_not_configured_without_network():
    capability = probe_fred_dgs10(
        settings=_settings(None),
        observation_start="2026-09-20",
        observation_end="2026-09-28",
    )

    assert capability.status.value == "NOT_CONFIGURED"
    assert capability.authenticated is False
    assert capability.details["series_id"] == "DGS10"


class _FakeFred:
    def __init__(self) -> None:
        from app.integrations.fred.client import FredObservationBatch, FredPage

        self._batch = FredObservationBatch(
            observations=(
                {
                    "realtime_start": "2026-09-28",
                    "realtime_end": "2026-09-28",
                    "date": "2026-09-25",
                    "value": "4.10",
                },
                {
                    "realtime_start": "2026-09-28",
                    "realtime_end": "2026-09-28",
                    "date": "2026-09-26",
                    "value": ".",
                },
                {
                    "realtime_start": "2026-09-28",
                    "realtime_end": "2026-09-28",
                    "date": "2026-09-28",
                    "value": "4.12",
                },
            ),
            pages=(
                FredPage(
                    endpoint="series/observations",
                    safe_params={
                        "series_id": "DGS10",
                        "observation_start": "2026-09-25",
                        "observation_end": "2026-09-28",
                        "realtime_start": "2026-09-28",
                        "realtime_end": "2026-09-28",
                        "limit": 10000,
                        "offset": 0,
                        "sort_order": "asc",
                    },
                    response_hash="c" * 64,
                    row_count=3,
                    offset=0,
                    limit=10000,
                    count=3,
                ),
            ),
            observation_start="2026-09-25",
            observation_end="2026-09-28",
        )

    def series(self, series_id: str):
        assert series_id == "DGS10"
        return {
            "id": "DGS10",
            "title": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
            "frequency": "Daily",
            "units": "Percent",
            "observation_start": "1962-01-02",
            "observation_end": "2026-09-28",
        }

    def observations(self, series_id: str, **kwargs):
        assert series_id == "DGS10"
        assert kwargs["realtime_start"] == "2026-09-28"
        assert kwargs["realtime_end"] == "2026-09-28"
        return self._batch


def test_dgs10_live_ingestion_is_bounded_missing_safe_and_refetch_noop(tmp_path: Path):
    db = tmp_path / "macro.db"
    store = MacroStore(db, clock=lambda: "2026-09-29T08:00:00+00:00")
    store.initialize()
    fake = _FakeFred()

    first = collect_fred_dgs10(
        store=store,
        client=fake,  # type: ignore[arg-type]
        observation_start="2026-09-25",
        observation_end="2026-09-28",
        as_of_date="2026-09-28",
        fetched_at="2026-09-29T08:00:00+00:00",
    )
    second = collect_fred_dgs10(
        store=store,
        client=fake,  # type: ignore[arg-type]
        observation_start="2026-09-25",
        observation_end="2026-09-28",
        as_of_date="2026-09-28",
        fetched_at="2026-09-29T09:00:00+00:00",
    )

    assert first["expected_count"] == 3
    assert first["stored_count"] == 2
    assert first["missing_count"] == 1
    assert first["new_revision_count"] == 2
    assert first["historical_pit_eligible_count"] == 0
    assert first["time_quality"] == "DATE_ONLY"
    assert first["production_decision_approved"] is False

    assert second["new_revision_count"] == 0
    assert second["duplicate_count"] == 2
    assert store.inspect()["counts"]["observation_revision_count"] == 2

    reader = LocalMacroReader(db)
    strict = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff="2026-10-01T00:00:00+00:00",
        historical_eligible_only=True,
    )
    reference = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff="2026-10-01T00:00:00+00:00",
        historical_eligible_only=False,
    )
    assert strict["status"] == "UNAVAILABLE"
    assert strict["reason"] == "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"
    assert reference["status"] == "COMPLETE"
    assert reference["observation"]["normalized_value"] == "4.12"
    assert reference["observation"]["time_quality"] == "DATE_ONLY"
