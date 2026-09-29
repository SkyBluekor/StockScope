from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.integrations.fred import (
    FredApiError,
    FredClient,
    FredConfigurationError,
    FredSettings,
)
from app.macro.capability import CapabilityStatus, ProviderCapability
from app.macro.identity import content_hash
from app.macro.manifest import MacroPreparedRangeManifest
from app.macro.models import MacroObservation, fred_dgs10_research_contract
from app.macro.normalization import (
    FRED_DGS10_NORMALIZER_VERSION,
    normalize_fred_dgs10_row,
)
from app.macro.store import MacroStore


DGS10_PROVIDER_SERIES_ID = "DGS10"
DGS10_SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_dgs10_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "title",
        "observation_start",
        "observation_end",
        "frequency",
        "frequency_short",
        "units",
        "units_short",
        "seasonal_adjustment",
        "seasonal_adjustment_short",
        "last_updated",
        "popularity",
    )
    return {key: metadata.get(key) for key in keys if key in metadata}


def _dgs10_semantics_ok(metadata: dict[str, Any]) -> tuple[bool, list[str]]:
    limitations: list[str] = []
    if str(metadata.get("id") or "").upper() != DGS10_PROVIDER_SERIES_ID:
        limitations.append("series_id_mismatch")
    frequency = str(metadata.get("frequency") or "").strip().lower()
    if frequency != "daily":
        limitations.append("frequency_not_daily")
    units = str(metadata.get("units") or "").strip().lower()
    if units != "percent":
        limitations.append("units_not_percent")
    title = str(metadata.get("title") or "").strip().lower()
    if "10-year" not in title or "treasury" not in title:
        limitations.append("measurement_definition_unverified")
    return not limitations, limitations


def probe_fred_dgs10(
    *,
    settings: FredSettings | None = None,
    client: FredClient | None = None,
    observation_start: str,
    observation_end: str,
) -> ProviderCapability:
    owns_client = client is None
    try:
        resolved = client or FredClient(settings)
    except FredConfigurationError:
        return ProviderCapability(
            provider="FRED",
            component="DGS10",
            status=CapabilityStatus.NOT_CONFIGURED,
            configured=False,
            authenticated=False,
            details={"series_id": DGS10_PROVIDER_SERIES_ID},
            limitations=("FRED_API_KEY_NOT_CONFIGURED",),
        )

    try:
        metadata = resolved.series(DGS10_PROVIDER_SERIES_ID)
        semantics_ok, limitations = _dgs10_semantics_ok(metadata)
        batch = resolved.observations(
            DGS10_PROVIDER_SERIES_ID,
            observation_start=observation_start,
            observation_end=observation_end,
        )
        vintage = resolved.vintage_dates(DGS10_PROVIDER_SERIES_ID, limit=5)
        status = (
            CapabilityStatus.SUPPORTED
            if semantics_ok
            else CapabilityStatus.SUPPORTED_WITH_LIMITATIONS
        )
        return ProviderCapability(
            provider="FRED",
            component="DGS10",
            status=status,
            configured=True,
            authenticated=True,
            details={
                "series": _safe_dgs10_metadata(metadata),
                "observation_probe": {
                    "start": observation_start,
                    "end": observation_end,
                    "row_count": len(batch.observations),
                    "page_count": len(batch.pages),
                },
                "vintage_probe": {
                    "count": vintage["count"],
                    "returned": len(vintage["vintage_dates"]),
                    "realtime_start": vintage["realtime_start"],
                    "realtime_end": vintage["realtime_end"],
                },
                "research_owner_eligible": semantics_ok,
                "production_decision_approved": False,
            },
            limitations=tuple(limitations),
        )
    except FredApiError as exc:
        status = (
            CapabilityStatus.NOT_AUTHORIZED
            if exc.status_code in {401, 403}
            else CapabilityStatus.ERROR
        )
        return ProviderCapability(
            provider="FRED",
            component="DGS10",
            status=status,
            configured=True,
            authenticated=False,
            details={
                "series_id": DGS10_PROVIDER_SERIES_ID,
                "status_code": exc.status_code,
                "endpoint": exc.endpoint,
                "production_decision_approved": False,
            },
            limitations=("FRED_LIVE_PROBE_FAILED",),
        )
    finally:
        if owns_client:
            resolved.close()


def collect_fred_dgs10(
    *,
    store: MacroStore,
    client: FredClient,
    observation_start: str,
    observation_end: str,
    as_of_date: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    metadata = client.series(DGS10_PROVIDER_SERIES_ID)
    semantics_ok, limitations = _dgs10_semantics_ok(metadata)
    if not semantics_ok:
        raise ValueError(
            "FRED DGS10 semantics verification failed: " + ", ".join(limitations)
        )

    contract = fred_dgs10_research_contract()
    store.register_series_contract(contract)

    fixed_as_of = str(as_of_date or observation_end)
    fetched = fetched_at or _now()
    batch = client.observations(
        DGS10_PROVIDER_SERIES_ID,
        observation_start=observation_start,
        observation_end=observation_end,
        realtime_start=fixed_as_of,
        realtime_end=fixed_as_of,
    )
    page_manifest = [
        {
            "endpoint": page.endpoint,
            "safe_params": page.safe_params,
            "response_hash": page.response_hash,
            "row_count": page.row_count,
            "offset": page.offset,
            "limit": page.limit,
            "count": page.count,
        }
        for page in batch.pages
    ]
    source_manifest_hash = content_hash(page_manifest)

    run = store.begin_collection_run(
        provider="FRED",
        metadata={
            "contract_version": "VN_NEXT6A_S2_FRED_COLLECTION_V1",
            "series_id": DGS10_PROVIDER_SERIES_ID,
            "semantic_id": DGS10_SERIES_ID,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "realtime_start": fixed_as_of,
            "realtime_end": fixed_as_of,
            "source_manifest_hash": source_manifest_hash,
            "network_scope": "EXPLICIT_BOUNDED_COLLECTION",
            "production_decision_approved": False,
        },
    )

    stored_count = 0
    missing_count = 0
    new_revision_count = 0
    duplicate_count = 0
    try:
        for raw_row in batch.observations:
            row = normalize_fred_dgs10_row(raw_row)
            if row.missing:
                missing_count += 1
                continue
            assert row.normalized_value is not None
            temporal = TemporalEvidence(
                event_time=row.observation_date,
                source_published_at=None,
                provider_published_at=None,
                first_seen_at=fetched,
                available_at=fetched,
                fetched_at=fetched,
                time_quality=EvidenceTimeQuality.DATE_ONLY,
            )
            result = store.store_observation(
                run_id=run["run_id"],
                observation=MacroObservation(
                    series_id=DGS10_SERIES_ID,
                    native_observation_id=(
                        f"{DGS10_PROVIDER_SERIES_ID}:{row.observation_date}"
                    ),
                    observation_date=row.observation_date,
                    source_value=row.raw_value,
                    normalized_value=row.normalized_value,
                    source_unit="PERCENT",
                    source_payload_hash=row.source_payload_hash,
                    normalizer_version=FRED_DGS10_NORMALIZER_VERSION,
                    realtime_start=row.realtime_start,
                    realtime_end=row.realtime_end,
                    vintage_id=fixed_as_of,
                    temporal=temporal,
                ),
            )
            stored_count += 1
            if result["duplicate"]:
                duplicate_count += 1
            else:
                new_revision_count += 1
        publish = store.publish_collection_run(run["run_id"])
    except Exception:
        store.fail_collection_run(run["run_id"])
        raise

    manifest = MacroPreparedRangeManifest(
        series_id=DGS10_SERIES_ID,
        start_date=observation_start,
        end_date=observation_end,
        expected_count=len(batch.observations),
        stored_count=stored_count,
        missing_count=missing_count,
        unavailable_count=0,
        date_only_count=stored_count,
        eligible_count=0,
        source_contract_version=contract.contract_version,
        normalizer_version=FRED_DGS10_NORMALIZER_VERSION,
        source_manifest_hash=source_manifest_hash,
        prepared_at=fetched,
    )
    stored_manifest = store.store_prepared_range(manifest)

    return {
        "provider": "FRED",
        "series_id": DGS10_SERIES_ID,
        "provider_series_id": DGS10_PROVIDER_SERIES_ID,
        "observation_start": observation_start,
        "observation_end": observation_end,
        "as_of_date": fixed_as_of,
        "fetched_at": fetched,
        "expected_count": len(batch.observations),
        "stored_count": stored_count,
        "missing_count": missing_count,
        "new_revision_count": new_revision_count,
        "duplicate_count": duplicate_count,
        "published_count": publish["published_count"],
        "prepared_range_status": manifest.status,
        "prepared_range_hash": manifest.content_hash,
        "prepared_range_duplicate": stored_manifest["duplicate"],
        "historical_pit_eligible_count": 0,
        "time_quality": EvidenceTimeQuality.DATE_ONLY.value,
        "production_decision_approved": False,
    }
