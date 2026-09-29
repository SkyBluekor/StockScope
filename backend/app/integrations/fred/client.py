from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.macro.identity import content_hash


_FRED_BASE_URL = "https://api.stlouisfed.org/fred"


class FredConfigurationError(RuntimeError):
    pass


class FredApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


@dataclass(frozen=True, slots=True)
class FredPage:
    endpoint: str
    safe_params: dict[str, Any]
    response_hash: str
    row_count: int
    offset: int
    limit: int
    count: int


@dataclass(frozen=True, slots=True)
class FredObservationBatch:
    observations: tuple[dict[str, Any], ...]
    pages: tuple[FredPage, ...]
    observation_start: str
    observation_end: str


def validate_settings(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    if not settings.fred_api_key:
        raise FredConfigurationError(
            "FRED_API_KEY is not configured."
        )
    return settings


class FredClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        timeout_seconds: float = 20.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = validate_settings(settings)
        self.timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "FredClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        safe_params = {
            key: value
            for key, value in params.items()
            if key != "api_key"
        }
        request_params = {
            **safe_params,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
        }
        try:
            response = self._http.get(
                f"{_FRED_BASE_URL}/{endpoint.lstrip('/')}",
                params=request_params,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise FredApiError(
                f"FRED request failed before response: endpoint={endpoint}",
                endpoint=endpoint,
            ) from exc

        if response.status_code != 200:
            raise FredApiError(
                f"FRED request failed: status={response.status_code} endpoint={endpoint}",
                status_code=response.status_code,
                endpoint=endpoint,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FredApiError(
                f"FRED response was not valid JSON: endpoint={endpoint}",
                status_code=response.status_code,
                endpoint=endpoint,
            ) from exc
        if not isinstance(payload, dict):
            raise FredApiError(
                f"FRED response had an unexpected shape: endpoint={endpoint}",
                status_code=response.status_code,
                endpoint=endpoint,
            )
        return payload

    def series(self, series_id: str) -> dict[str, Any]:
        payload = self._get(
            "series",
            params={"series_id": series_id},
        )
        rows = payload.get("seriess")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise FredApiError(
                "FRED series response did not contain series metadata.",
                endpoint="series",
            )
        return dict(rows[0])

    def vintage_dates(
        self,
        series_id: str,
        *,
        limit: int = 10000,
        offset: int = 0,
    ) -> dict[str, Any]:
        payload = self._get(
            "series/vintagedates",
            params={
                "series_id": series_id,
                "limit": int(limit),
                "offset": int(offset),
                "sort_order": "asc",
            },
        )
        rows = payload.get("vintage_dates")
        if not isinstance(rows, list):
            raise FredApiError(
                "FRED vintage response did not contain vintage_dates.",
                endpoint="series/vintagedates",
            )
        return {
            "realtime_start": payload.get("realtime_start"),
            "realtime_end": payload.get("realtime_end"),
            "count": int(payload.get("count") or len(rows)),
            "offset": int(payload.get("offset") or offset),
            "limit": int(payload.get("limit") or limit),
            "vintage_dates": tuple(str(value) for value in rows),
        }

    def observations(
        self,
        series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
        page_limit: int = 10000,
    ) -> FredObservationBatch:
        if page_limit < 1 or page_limit > 100000:
            raise ValueError("page_limit must be between 1 and 100000.")
        offset = 0
        rows: list[dict[str, Any]] = []
        pages: list[FredPage] = []
        while True:
            params: dict[str, Any] = {
                "series_id": series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "sort_order": "asc",
                "limit": page_limit,
                "offset": offset,
            }
            if realtime_start:
                params["realtime_start"] = realtime_start
            if realtime_end:
                params["realtime_end"] = realtime_end
            payload = self._get("series/observations", params=params)
            page_rows = payload.get("observations")
            if not isinstance(page_rows, list):
                raise FredApiError(
                    "FRED observations response did not contain observations.",
                    endpoint="series/observations",
                )
            typed_rows = [dict(row) for row in page_rows if isinstance(row, dict)]
            count = int(payload.get("count") or len(typed_rows))
            response_limit = int(payload.get("limit") or page_limit)
            response_offset = int(payload.get("offset") or offset)
            safe_params = {
                key: value
                for key, value in params.items()
                if key != "api_key"
            }
            pages.append(
                FredPage(
                    endpoint="series/observations",
                    safe_params=safe_params,
                    response_hash=content_hash(payload),
                    row_count=len(typed_rows),
                    offset=response_offset,
                    limit=response_limit,
                    count=count,
                )
            )
            rows.extend(typed_rows)
            next_offset = response_offset + len(typed_rows)
            if not typed_rows or next_offset >= count:
                break
            if next_offset <= offset:
                raise FredApiError(
                    "FRED observations pagination did not advance.",
                    endpoint="series/observations",
                )
            offset = next_offset
        return FredObservationBatch(
            observations=tuple(rows),
            pages=tuple(pages),
            observation_start=observation_start,
            observation_end=observation_end,
        )
