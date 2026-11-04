from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.integrations.kis.client import (
    KisAuthenticationError,
    KisConfigurationError,
    base_url,
    validate_settings,
)
from app.integrations.kis.token_cache import get_access_token
from app.macro.capability import CapabilityStatus, ProviderCapability


_KIS_DAILY_PATH = "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
_KIS_DAILY_TR_ID = "FHKST03030100"
_ALLOWED_DIVISIONS = {"N", "X", "I"}
_COMPONENTS = {
    "N": "OVERSEAS_INDEX",
    "X": "FX",
    "I": "TREASURY",
}

# Only codes verified against the provider's published index examples are
# recognized without a provider-returned name. This is request-code identity,
# not an assertion that the API echoed the index name.
_KNOWN_INDEX_CODES = {
    ".DJI": "다우존스 산업평균지수",
}



def _validated_index_pair(
    rows: list[dict[str, Any]], *, start_date: str, end_date: str,
) -> dict[str, Any] | None:
    """Return only the last two distinct valid daily values, never raw KIS rows.

    This is a date-only observation, not proof of a finalized US close.
    Conflicting values for the same observation date fail closed.
    """
    start_dd = start_date.replace("-", "")
    end_dd = end_date.replace("-", "")
    selected: dict[str, Decimal] = {}
    for row in rows:
        day = str(row.get("stck_bsop_date") or "").strip()
        if len(day) != 8 or not day.isascii() or not day.isdigit():
            continue
        try:
            date.fromisoformat(f"{day[:4]}-{day[4:6]}-{day[6:]}")
            value = Decimal(str(row.get("ovrs_nmix_prpr")))
        except (ValueError, InvalidOperation, TypeError):
            continue
        if day < start_dd or day > end_dd or not value.is_finite() or value <= 0:
            continue
        if day in selected and selected[day] != value:
            return None
        selected[day] = value
    if len(selected) < 2:
        return None
    previous_day, current_day = sorted(selected)[-2:]
    previous = selected[previous_day]
    current = selected[current_day]
    return {
        "previous_observation_date": date.fromisoformat(previous_day).isoformat(),
        "observation_date": date.fromisoformat(current_day).isoformat(),
        "previous_index_value": str(previous),
        "index_value": str(current),
        "daily_change_pct": str(
            ((current / previous) - Decimal("1")) * Decimal("100")
        ),
    }


def _validated_index_sample(
    rows: list[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Check real date/positive close semantics without retaining provider rows."""
    valid: list[tuple[str, Decimal]] = []
    invalid = 0
    from_day = start_date.replace("-", "")
    to_day = end_date.replace("-", "")
    for row in rows:
        day = str(row.get("stck_bsop_date") or "").strip()
        try:
            if len(day) != 8 or not day.isascii() or not day.isdigit():
                raise ValueError("invalid trade date")
            date.fromisoformat(f"{day[:4]}-{day[4:6]}-{day[6:]}")
            if not from_day <= day <= to_day:
                raise ValueError("date outside requested range")
            level = Decimal(str(row.get("ovrs_nmix_prpr")))
            if not level.is_finite() or level <= 0:
                raise ValueError("invalid index level")
        except (ValueError, InvalidOperation, TypeError):
            invalid += 1
            continue
        valid.append((day, level))
    latest = max(valid, key=lambda item: item[0]) if valid else None
    return {
        "valid_index_rows": len(valid),
        "invalid_index_rows": invalid,
        "latest_observation_date": (
            f"{latest[0][:4]}-{latest[0][4:6]}-{latest[0][6:]}"
            if latest else None
        ),
        "latest_index_level": str(latest[1]) if latest else None,
    }


class KisMacroProbeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def probe_kis_daily_chart(
    *,
    division: str,
    instrument_code: str,
    start_date: str,
    end_date: str,
    settings: Settings | None = None,
    access_token: str | None = None,
    http_client: httpx.Client | None = None,
    timeout_seconds: float = 20.0,
    include_reference_pair: bool = False,
) -> ProviderCapability:
    settings = validate_settings(settings or get_settings())
    normalized_division = str(division or "").strip().upper()
    if normalized_division not in _ALLOWED_DIVISIONS:
        raise ValueError("division must be one of N, X, I.")
    code = str(instrument_code or "").strip()
    if not code:
        return ProviderCapability(
            provider="KIS",
            component=_COMPONENTS[normalized_division],
            status=CapabilityStatus.SEMANTICS_UNVERIFIED,
            configured=True,
            authenticated=False,
            details={
                "market_division": normalized_division,
                "instrument_code": None,
                "endpoint": _KIS_DAILY_PATH,
                "production_decision_approved": False,
            },
            limitations=("OFFICIAL_INSTRUMENT_CODE_REQUIRED",),
        )

    token_value = access_token or get_access_token(settings).access_token
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token_value}",
        "appkey": settings.kis_app_key or "",
        "appsecret": settings.kis_app_secret or "",
        "tr_id": _KIS_DAILY_TR_ID,
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": normalized_division,
        "FID_INPUT_ISCD": code,
        "FID_INPUT_DATE_1": start_date.replace("-", ""),
        "FID_INPUT_DATE_2": end_date.replace("-", ""),
        "FID_PERIOD_DIV_CODE": "D",
    }
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    try:
        try:
            response = client.get(
                f"{base_url(settings.kis_env)}{_KIS_DAILY_PATH}",
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise KisMacroProbeError(
                "KIS macro capability request failed before receiving a response."
            ) from exc

        if response.status_code != 200:
            status = (
                CapabilityStatus.NOT_AUTHORIZED
                if response.status_code in {401, 403}
                else CapabilityStatus.ERROR
            )
            return ProviderCapability(
                provider="KIS",
                component=_COMPONENTS[normalized_division],
                status=status,
                configured=True,
                authenticated=False,
                details={
                    "market_division": normalized_division,
                    "instrument_code": code,
                    "endpoint": _KIS_DAILY_PATH,
                    "status_code": response.status_code,
                    "environment": settings.kis_env,
                    "production_decision_approved": False,
                },
                limitations=("KIS_LIVE_PROBE_FAILED",),
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise KisMacroProbeError(
                "KIS macro capability response was not valid JSON.",
                status_code=response.status_code,
            ) from exc
        if not isinstance(body, dict):
            raise KisMacroProbeError(
                "KIS macro capability response had an unexpected shape.",
                status_code=response.status_code,
            )

        if str(body.get("rt_cd") or "") != "0":
            code_value = str(body.get("msg_cd") or "") or None
            message = str(body.get("msg1") or "KIS macro capability request failed.")
            lowered = message.lower()
            not_authorized = any(
                token in lowered
                for token in ("권한", "인증", "authorization", "permission")
            )
            return ProviderCapability(
                provider="KIS",
                component=_COMPONENTS[normalized_division],
                status=(
                    CapabilityStatus.NOT_AUTHORIZED
                    if not_authorized
                    else CapabilityStatus.NOT_SUPPORTED
                ),
                configured=True,
                authenticated=not not_authorized,
                details={
                    "market_division": normalized_division,
                    "instrument_code": code,
                    "endpoint": _KIS_DAILY_PATH,
                    "message_code": code_value,
                    "environment": settings.kis_env,
                    "production_decision_approved": False,
                },
                limitations=("KIS_PROVIDER_REJECTED_PROBE",),
            )

        output1 = body.get("output1")
        output2 = body.get("output2")
        if isinstance(output2, dict):
            rows = [output2]
        elif isinstance(output2, list):
            rows = [row for row in output2 if isinstance(row, dict)]
        else:
            rows = []
        meta_fields = sorted(output1.keys()) if isinstance(output1, dict) else []
        row_fields = sorted(rows[0].keys()) if rows else []

        # The provider accepted the HTTP request, but that alone does not
        # establish a real index observation or permission to reuse it.
        index_sample = (
            _validated_index_sample(
                rows, start_date=start_date, end_date=end_date,
            )
            if normalized_division == "N"
            else None
        )
        provider_index_name = (
            str(output1.get("hts_kor_isnm") or "").strip()[:80]
            if normalized_division == "N" and isinstance(output1, dict)
            else ""
        )
        official_request_name = (
            _KNOWN_INDEX_CODES.get(code.upper())
            if normalized_division == "N"
            else None
        )
        # The live KIS daily-chart index response often omits hts_kor_isnm.
        # An official request code is an acceptable identity hint, but do not
        # mislabel it as a provider-returned name or infer usage rights.
        index_name = provider_index_name or official_request_name or ""
        index_name_source = (
            "PROVIDER_RESPONSE" if provider_index_name
            else "OFFICIAL_KIS_REQUEST_CODE" if official_request_name
            else "UNVERIFIED"
        )
        conflicting_name = bool(
            official_request_name
            and provider_index_name
            and code.upper() == ".DJI"
            and not any(token in provider_index_name.lower() for token in ("다우", "dow", "dji"))
        )
        index_confirmed = (
            index_sample is not None
            and index_sample["valid_index_rows"] > 0
            and bool(index_name)
            and not conflicting_name
        )
        supported = (
            index_confirmed
            if normalized_division == "N"
            else bool(rows)
        )
        limitations = [
            "AVAILABILITY_TIMESTAMP_UNVERIFIED",
            "SESSION_CLOSE_SEMANTICS_REQUIRE_REVIEW",
            "RETENTION_SCOPE_UNVERIFIED",
            "DISPLAY_AND_REDISTRIBUTION_RIGHTS_UNVERIFIED",
            "REQUESTED_RANGE_COVERAGE_NOT_PROVEN",
        ]
        if not rows:
            limitations.append("NO_PROVIDER_DATA_ROWS")
        if normalized_division == "N":
            if not index_name:
                limitations.append("INDEX_IDENTITY_UNVERIFIED")
            if official_request_name and not provider_index_name:
                limitations.append("INDEX_NAME_FROM_OFFICIAL_REQUEST_CODE_ONLY")
            if conflicting_name:
                limitations.append("INDEX_NAME_CONFLICT_WITH_REQUEST_CODE")
            if not index_sample["valid_index_rows"]:
                limitations.append("NO_VALID_INDEX_OBSERVATION")
            if index_sample["invalid_index_rows"]:
                limitations.append("INVALID_OR_OUT_OF_RANGE_INDEX_ROWS")
        return ProviderCapability(
            provider="KIS",
            component=_COMPONENTS[normalized_division],
            status=(
                CapabilityStatus.SUPPORTED_WITH_LIMITATIONS
                if supported else CapabilityStatus.SEMANTICS_UNVERIFIED
            ),
            configured=True,
            authenticated=True,
            details={
                "market_division": normalized_division,
                "instrument_code": code,
                "endpoint": _KIS_DAILY_PATH,
                "tr_id": _KIS_DAILY_TR_ID,
                "environment": settings.kis_env,
                "row_count": len(rows),
                "metadata_fields": meta_fields,
                "row_fields": row_fields,
                "index_name": index_name or None,
                "index_name_source": index_name_source if normalized_division == "N" else None,
                "provider_index_name": provider_index_name or None,
                "index_sample": index_sample,
                **(
                    {"index_reference_pair": _validated_index_pair(
                        rows, start_date=start_date, end_date=end_date,
                    )}
                    if include_reference_pair and normalized_division == "N"
                    else {}
                ),
                "has_continuation": bool(
                    response.headers.get("tr_cont")
                    or response.headers.get("tr-cont")
                ),
                "display_rights_approved": False,
                "retention_rights_approved": False,
                "ai_transfer_approved": False,
                "production_decision_approved": False,
            },
            limitations=tuple(limitations),
        )
    finally:
        if owns_client:
            client.close()


def probe_kis_macro_capabilities(
    *,
    start_date: str,
    end_date: str,
    index_code: str = ".DJI",
    fx_code: str | None = None,
    treasury_code: str | None = None,
    settings: Settings | None = None,
) -> list[ProviderCapability]:
    settings = settings or get_settings()
    try:
        validate_settings(settings)
    except KisConfigurationError:
        return [
            ProviderCapability(
                provider="KIS",
                component=component,
                status=CapabilityStatus.NOT_CONFIGURED,
                configured=False,
                authenticated=False,
                details={
                    "market_division": division,
                    "production_decision_approved": False,
                },
                limitations=("KIS_CREDENTIALS_NOT_CONFIGURED",),
            )
            for division, component in _COMPONENTS.items()
        ]

    try:
        token = get_access_token(settings).access_token
    except KisAuthenticationError as exc:
        status = (
            CapabilityStatus.NOT_AUTHORIZED
            if exc.status_code in {401, 403}
            else CapabilityStatus.ERROR
        )
        return [
            ProviderCapability(
                provider="KIS",
                component=component,
                status=status,
                configured=True,
                authenticated=False,
                details={
                    "market_division": division,
                    "status_code": exc.status_code,
                    "production_decision_approved": False,
                },
                limitations=("KIS_AUTHENTICATION_FAILED",),
            )
            for division, component in _COMPONENTS.items()
        ]

    probes = (
        ("N", index_code),
        ("X", fx_code),
        ("I", treasury_code),
    )
    return [
        probe_kis_daily_chart(
            division=division,
            instrument_code=code or "",
            start_date=start_date,
            end_date=end_date,
            settings=settings,
            access_token=token,
        )
        for division, code in probes
    ]
