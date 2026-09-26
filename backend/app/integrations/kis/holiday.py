from __future__ import annotations

import threading
from datetime import date
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, validate_settings
from .token_cache import get_access_token


_HOLIDAY_PATH = "/uapi/domestic-stock/v1/quotations/chk-holiday"
_HOLIDAY_TR_ID = "CTCA0903R"


class KisHolidayError(RuntimeError):
    pass


class KisHolidayProvider:
    """KIS domestic holiday/open-day adapter with a process-local daily cache.

    KIS documents this service as sensitive to repeated calls, so successful
    date results are cached and guarded by a single process-local lock.
    """

    def __init__(self) -> None:
        self._cache: dict[date, bool] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def is_open_day(
        self,
        target_date: date,
        settings: Settings | None = None,
        *,
        timeout_seconds: float = 15.0,
        http_client: httpx.Client | None = None,
    ) -> bool:
        cached = self._cache.get(target_date)
        if cached is not None:
            return cached

        with self._lock:
            cached = self._cache.get(target_date)
            if cached is not None:
                return cached

            resolved = self._fetch_open_day(
                target_date,
                settings or get_settings(),
                timeout_seconds=timeout_seconds,
                http_client=http_client,
            )
            self._cache[target_date] = resolved
            return resolved

    @staticmethod
    def _fetch_open_day(
        target_date: date,
        settings: Settings,
        *,
        timeout_seconds: float,
        http_client: httpx.Client | None,
    ) -> bool:
        settings = validate_settings(settings)
        token = get_access_token(settings).access_token

        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key or "",
            "appsecret": settings.kis_app_secret or "",
            "tr_id": _HOLIDAY_TR_ID,
            "custtype": "P",
        }
        params = {
            "BASS_DT": target_date.strftime("%Y%m%d"),
            "CTX_AREA_FK": "",
            "CTX_AREA_NK": "",
        }

        owns_client = http_client is None
        client = http_client or httpx.Client(timeout=timeout_seconds)
        try:
            try:
                response = client.get(
                    f"{base_url(settings.kis_env)}{_HOLIDAY_PATH}",
                    headers=headers,
                    params=params,
                    timeout=timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise KisHolidayError(
                    f"KIS holiday request failed before receiving a response: {exc}"
                ) from exc

            if response.status_code != 200:
                raise KisHolidayError(
                    f"KIS holiday request returned HTTP {response.status_code}."
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise KisHolidayError("KIS holiday response was not valid JSON.") from exc

            if not isinstance(body, dict):
                raise KisHolidayError("KIS holiday response had an unexpected shape.")
            if str(body.get("rt_cd") or "") != "0":
                raise KisHolidayError(
                    str(body.get("msg1") or "KIS holiday request failed.")
                )

            output: Any = body.get("output")
            rows = output if isinstance(output, list) else [output] if isinstance(output, dict) else []
            target = target_date.strftime("%Y%m%d")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("bass_dt") or "").strip() != target:
                    continue
                open_flag = str(row.get("opnd_yn") or "").strip().upper()
                if open_flag == "Y":
                    return True
                if open_flag == "N":
                    return False
                raise KisHolidayError("KIS holiday row did not contain a valid opnd_yn value.")

            raise KisHolidayError("KIS holiday response did not contain the requested date.")
        finally:
            if owns_client:
                client.close()


kis_holiday_provider = KisHolidayProvider()
