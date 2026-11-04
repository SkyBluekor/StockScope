"""Personal-local reference for KIS .DJI. No persistence, no strategy input.

A single process-wide, short-lived in-memory result is shared across Scanner
candidates. No KIS call is made without explicit local-use opt-in. Observations
are DATE_ONLY, and *never* historical decision evidence.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import PROJECT_ROOT, get_settings
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.integrations.kis.client import KisAuthenticationError, KisConfigurationError
from app.macro.capability import CapabilityStatus
from app.macro.providers.kis import KisMacroProbeError, probe_kis_daily_chart

_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None
_CACHE_UNTIL = 0.0
_CACHE_TTL_OK_SECONDS = 600
_CACHE_TTL_FAILED_SECONDS = 45


class _LocalDjiOptions(BaseSettings):
    # Opt-in is private to this reference module, outside pinned core config.
    # Users must independently verify their permitted PERSONAL/LOCAL use.
    stockscope_kis_dji_personal_local_reference_enabled: bool = False
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def personal_local_opted_in() -> bool:
    try:
        return _LocalDjiOptions().stockscope_kis_dji_personal_local_reference_enabled
    except (ValueError, TypeError):
        return False


def _base(reason: str | None) -> dict[str, Any]:
    return {
        "contract_version": "STOCKSCOPE_GLOBAL01_S2_DJI_REFERENCE_V1",
        "status": "UNAVAILABLE",
        "reason": reason,
        "source": "KIS_OVERSEAS_INDEX_LOCAL",
        "index_code": ".DJI",
        "index_name": "다우존스 산업평균지수",
        "index_name_source": "OFFICIAL_KIS_REQUEST_CODE",
        "observation_date": None,
        "previous_observation_date": None,
        "index_value": None,
        "previous_index_value": None,
        "daily_change_pct": None,
        "fetched_at_utc": None,
        "source_time_quality": "DATE_ONLY",
        "session_close_verified": False,
        "usage_scope": "PERSONAL_LOCAL_REFERENCE_ONLY",
        # User opt-in is not an assertion of provider-approved redistribution.
        "display_rights_approved": False,
        "retention_rights_approved": False,
        "ai_transfer_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "production_decision_approved": False,
    }


def _query_once(now: datetime) -> dict[str, Any]:
    result = _base("SOURCE_UNAVAILABLE")
    # KIS US daily chart may contain today's unfinished session. Describe
    # date-only observations, never call these finalized closes.
    kst_today = now.astimezone(timezone(timedelta(hours=9))).date()
    end_date = kst_today.isoformat()
    start_date = (kst_today - timedelta(days=21)).isoformat()
    try:
        capability = probe_kis_daily_chart(
            division="N",
            instrument_code=".DJI",
            start_date=start_date,
            end_date=end_date,
            settings=get_settings(),
            include_reference_pair=True,
        )
    except KisConfigurationError:
        return {**result, "reason": "KIS_NOT_CONFIGURED"}
    except KisAuthenticationError:
        return {**result, "reason": "KIS_AUTH_FAILED"}
    except (KisMacroProbeError, ValueError):
        return {**result, "reason": "KIS_REQUEST_FAILED"}
    except Exception:
        # Never place provider HTTP bodies or credentials into a UI error.
        return {**result, "reason": "SOURCE_UNAVAILABLE"}

    if capability.status != CapabilityStatus.SUPPORTED_WITH_LIMITATIONS:
        return {**result, "reason": "INDEX_SOURCE_UNVERIFIED"}
    details = capability.details
    sample = details.get("index_sample") or {}
    pair = details.get("index_reference_pair") or {}
    identity_source = details.get("index_name_source")
    received_name = str(details.get("index_name") or "").lower()
    known_identity = (
        identity_source == "OFFICIAL_KIS_REQUEST_CODE"
        and received_name == "다우존스 산업평균지수"
    ) or (
        identity_source == "PROVIDER_RESPONSE"
        and any(token in received_name for token in ("다우", "dow", "dji"))
    )
    if (
        not known_identity
        or sample.get("invalid_index_rows") != 0
        or not pair
    ):
        return {**result, "reason": "INDEX_PAIR_UNVERIFIED"}
    try:
        observed = datetime.strptime(pair["observation_date"], "%Y-%m-%d").date()
        previous = datetime.strptime(pair["previous_observation_date"], "%Y-%m-%d").date()
        latest_age = (kst_today - observed).days
    except (KeyError, TypeError, ValueError):
        return {**result, "reason": "INDEX_DATE_INVALID"}
    if previous >= observed or latest_age < 0 or latest_age > 7:
        return {**result, "reason": "INDEX_STALE_OR_FUTURE"}

    # Distinguish the time StockScope fetched this sample from an unknown
    # official data publication timestamp; neither is a historical PIT proof.
    return {
        **result,
        "status": "PARTIAL",
        "reason": "SOURCE_PUBLISHED_TIME_UNVERIFIED",
        "index_name_source": details["index_name_source"],
        "observation_date": pair["observation_date"],
        "previous_observation_date": pair["previous_observation_date"],
        "index_value": pair["index_value"],
        "previous_index_value": pair["previous_index_value"],
        "daily_change_pct": pair["daily_change_pct"],
        "fetched_at_utc": now.isoformat(),
    }


def read_local_dji_reference(
    *, enabled: bool, reason: str = "PERSONAL_LOCAL_OPT_IN_REQUIRED",
) -> dict[str, Any]:
    """No env/permission gate is bypassed by a direct caller by default."""
    global _CACHE, _CACHE_UNTIL
    if not enabled:
        return _base(reason)
    with _LOCK:
        now_mono = time.monotonic()
        if _CACHE is not None and now_mono < _CACHE_UNTIL:
            return dict(_CACHE)
        snapshot = _query_once(datetime.now(timezone.utc))
        _CACHE = snapshot
        _CACHE_UNTIL = now_mono + (
            _CACHE_TTL_OK_SECONDS if snapshot["status"] == "PARTIAL"
            else _CACHE_TTL_FAILED_SECONDS
        )
        return dict(snapshot)
