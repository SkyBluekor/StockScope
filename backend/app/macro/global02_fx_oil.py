"""GLOBAL-02-S1: strictly retrospective, personal-local FRED FX/Brent study.

No production signal, no JEV, no raw provider data retention. FRED API access
does not grant third-party redistribution, publication or AI processing rights.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

GLOBAL02_CONTRACT_VERSION = "STOCKSCOPE_GLOBAL02_S1_FX_OIL_RETRO_V1"
SPECS = {
    "DEXKOUS": {
        "semantic": "USD_KRW_NEW_YORK_NOON",
        "unit": "KRW_PER_USD",
        "fred_unit": "South Korean Won to One U.S. Dollar",
        "title_fragments": ("korean won", "u.s. dollar"),
        "source": "BOARD_OF_GOVERNORS_FEDERAL_RESERVE_H10",
        "positive_direction": "KRW_WEAKENS",
    },
    "DCOILBRENTEU": {
        "semantic": "BRENT_EUROPE_SPOT",
        "unit": "USD_PER_BARREL",
        "fred_unit": "Dollars per Barrel",
        "title_fragments": ("crude oil", "brent"),
        "source": "US_ENERGY_INFORMATION_ADMINISTRATION",
        "positive_direction": "BRENT_PRICE_RISES",
    },
}


class Global02SeriesError(ValueError):
    """Only stable reason codes are exposed; never propagate provider data."""


def _date(value: Any) -> date:
    try:
        parsed = date.fromisoformat(str(value))
        return parsed
    except (ValueError, TypeError):
        raise Global02SeriesError("INVALID_OBSERVATION_DATE") from None


def _value(value: Any) -> Decimal | None:
    if str(value).strip() in {"", "."}:
        return None
    try:
        val = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None
    return val if val.is_finite() and val > 0 else None


def validate_series_metadata(series_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if units/direction/identity differ from the official catalog."""
    spec = SPECS.get(series_id)
    if spec is None or str(metadata.get("id") or "") != series_id:
        raise Global02SeriesError("SERIES_IDENTITY_UNVERIFIED")
    if str(metadata.get("frequency") or "").strip().lower() != "daily":
        raise Global02SeriesError("SERIES_FREQUENCY_UNVERIFIED")
    if str(metadata.get("units") or "").strip().lower() != spec["fred_unit"].lower():
        raise Global02SeriesError("SERIES_UNIT_UNVERIFIED")
    title = str(metadata.get("title") or "").lower()
    if not all(fragment in title for fragment in spec["title_fragments"]):
        raise Global02SeriesError("SERIES_MEANING_UNVERIFIED")
    adjustment = str(metadata.get("seasonal_adjustment") or "Not Seasonally Adjusted").lower()
    if adjustment not in {"not seasonally adjusted", "nsa"}:
        raise Global02SeriesError("SERIES_ADJUSTMENT_UNVERIFIED")
    return {
        "series_id": series_id,
        "semantic_id": spec["semantic"],
        "unit": spec["unit"],
        "direction_if_increasing": spec["positive_direction"],
        "original_source_catalog_label": spec["source"],
        "identity_validation": "FRED_METADATA_ID_TITLE_UNITS_FREQUENCY",
        "original_source_verification": "OFFICIAL_FRED_CATALOG_NOT_SEPARATE_SOURCE_AGREEMENT",
        "provider_publish_time_status": "PER_OBSERVATION_TIME_UNAVAILABLE",
        "revision_status": "HISTORICAL_VINTAGES_NOT_RECONSTRUCTED",
        "rights_status": "PERSONAL_NONCOMMERCIAL_RESEARCH_ONLY_NOT_REDISTRIBUTION_APPROVED",
    }


def normalize_observations(
    series_id: str,
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    metadata: dict[str, Any],
    *,
    start: date,
    end: date,
    retrieved_at_utc: str,
) -> dict[str, Any]:
    """Validate US series and build in-memory changes; no raw values in reports."""
    details = validate_series_metadata(series_id, metadata)
    try:
        now = datetime.fromisoformat(retrieved_at_utc.replace("Z", "+00:00"))
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Global02SeriesError("FETCH_TIME_INVALID") from None
    if start > end:
        raise Global02SeriesError("REQUEST_RANGE_INVALID")
    unique: dict[date, Decimal] = {}
    missing = 0
    rejected = 0
    duplicated = 0
    revision_markers = 0
    for row in rows:
        try:
            day = _date(row.get("date"))
        except Global02SeriesError:
            rejected += 1
            continue
        if day < start or day > end:
            rejected += 1
            continue
        val = _value(row.get("value"))
        if val is None:
            missing += 1
            continue
        if day in unique:
            duplicated += 1
            if unique[day] != val:
                raise Global02SeriesError("DUPLICATE_DATE_CONFLICT")
            continue
        unique[day] = val
        if row.get("realtime_start") or row.get("realtime_end"):
            revision_markers += 1
    ordered = sorted(unique)
    points = []
    for i, day in enumerate(ordered):
        previous = ordered[i-1] if i else None
        delta = ((unique[day] / unique[previous]) - 1) * 100 if previous else None
        points.append({
            "date": day,
            "change_pct": delta,
            "previous_date": previous,
            "previous_gap_calendar_days": (day-previous).days if previous else None,
        })
    public = {
        **details,
        "retrieved_at_utc": now.astimezone(timezone.utc).isoformat(),
        "first_observation_date": ordered[0].isoformat() if ordered else None,
        "last_observation_date": ordered[-1].isoformat() if ordered else None,
        "observation_count": len(points),
        "missing_count": missing,
        "invalid_count": rejected,
        "duplicate_count": duplicated,
        "realtime_revision_marker_count": revision_markers,
        "time_quality": "DATE_ONLY",
        "source_published_at_utc": None,
        "staleness_calendar_days_at_fetch": (
            (now.date() - ordered[-1]).days if ordered else None
        ),
        "historical_decision_eligible": False,
        "production_decision_approved": False,
        "ai_transfer_approved": False,
        "redistribution_approved": False,
        "raw_values_in_report": False,
    }
    return {"public": public, "points": points}


def _mean_pct(values: list[Decimal]) -> float | None:
    if not values:
        return None
    return round(float(sum(values) / len(values)), 3)


def retrospective_relation(
    series: dict[str, Any], krx: dict[str, Any], *, series_id: str,
) -> dict[str, Any]:
    """Same calendar-day labels only, NEVER a publication-time or causal match."""
    domestic = krx.get("daily_returns") or {}
    paired = []
    excluded = {"NO_SAME_DATE_KRX": 0, "NO_PREVIOUS_US_OBSERVATION": 0,
                "US_BASELINE_GAP_GT_7D": 0, "KRX_SESSION_DATA_INVALID": 0}
    for point in series["points"]:
        d = point["date"].isoformat()
        if d not in domestic:
            excluded["NO_SAME_DATE_KRX"] += 1
            continue
        if point["change_pct"] is None:
            excluded["NO_PREVIOUS_US_OBSERVATION"] += 1
            continue
        if point["previous_gap_calendar_days"] > 7:
            excluded["US_BASELINE_GAP_GT_7D"] += 1
            continue
        returns = domestic[d]
        if set(returns) != {"KOSPI", "KOSDAQ"}:
            excluded["KRX_SESSION_DATA_INVALID"] += 1
            continue
        paired.append({"date": d, "change_pct": point["change_pct"], **returns})
    groups: dict[str, dict[str, Any]] = {}
    for key, subset in (
        ("fx_or_oil_up", [p for p in paired if p["change_pct"] > 0]),
        ("fx_or_oil_down", [p for p in paired if p["change_pct"] < 0]),
        ("unchanged", [p for p in paired if p["change_pct"] == 0]),
    ):
        groups[key] = {
            "count": len(subset),
            "kospi_mean_daily_return_pct": _mean_pct([p["KOSPI"] for p in subset]),
            "kosdaq_mean_daily_return_pct": _mean_pct([p["KOSDAQ"] for p in subset]),
        }
    return {
        "series_id": series_id,
        "status": "RETROSPECTIVE_DESCRIPTIVE_ONLY" if len(paired) >= 5
                  else "DATA_INSUFFICIENT",
        "reason": None if len(paired) >= 5 else "FEWER_THAN_FIVE_MATCHED_SESSIONS",
        "alignment": "SAME_CALENDAR_DATE_LABEL_NOT_AVAILABLE_AT_KRX_CLOSE",
        "krx_sessions": len(domestic),
        "fred_valid_observations": series["public"]["observation_count"],
        "paired_sessions": len(paired),
        "independent_pit_verified_pairs": 0,
        "excluded_counts": excluded,
        "groups": groups,
        "first_pair_date": paired[0]["date"] if paired else None,
        "last_pair_date": paired[-1]["date"] if paired else None,
        "claim_scope": "RETROSPECTIVE_ASSOCIATION_NOT_CAUSATION",
        "source_published_at_utc": None,
        "historical_decision_eligible": False,
        "production_decision_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "jev_input_approved": False,
    }
