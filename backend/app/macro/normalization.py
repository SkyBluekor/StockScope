from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.macro.identity import content_hash


FRED_DGS10_NORMALIZER_VERSION = "VN_NEXT6A_S2_FRED_DGS10_PERCENT_V1"


@dataclass(frozen=True, slots=True)
class NormalizedFredDgs10:
    observation_date: str
    raw_value: str
    normalized_value: str | None
    missing: bool
    realtime_start: str | None
    realtime_end: str | None
    source_payload_hash: str


def normalize_fred_dgs10_row(row: dict[str, Any]) -> NormalizedFredDgs10:
    observation_date = str(row.get("date") or "").strip()
    if not observation_date:
        raise ValueError("FRED DGS10 observation is missing date.")

    raw = "" if row.get("value") is None else str(row.get("value")).strip()
    missing = raw in {"", "."}
    normalized: str | None = None
    if not missing:
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("FRED DGS10 observation value is not numeric.") from exc
        if not value.is_finite():
            raise ValueError("FRED DGS10 observation value must be finite.")
        normalized = format(value.normalize(), "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"", "-0"}:
            normalized = "0"

    return NormalizedFredDgs10(
        observation_date=observation_date,
        raw_value=raw,
        normalized_value=normalized,
        missing=missing,
        realtime_start=(
            str(row.get("realtime_start")).strip()
            if row.get("realtime_start") not in (None, "")
            else None
        ),
        realtime_end=(
            str(row.get("realtime_end")).strip()
            if row.get("realtime_end") not in (None, "")
            else None
        ),
        source_payload_hash=content_hash(row),
    )
