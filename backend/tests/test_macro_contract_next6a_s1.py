from __future__ import annotations

from pathlib import Path

import pytest

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro import (
    LocalMacroReader,
    MacroContractError,
    MacroPreparedRangeManifest,
    MacroResearchProtocol,
    fred_dgs10_candidate_contract,
)


NOW = "2026-09-29T07:30:00+00:00"


def test_dgs10_candidate_contract_preserves_measurement_meaning_without_production_approval():
    contract = fred_dgs10_candidate_contract()

    assert contract.series_id == "US_10Y_CONSTANT_MATURITY_YIELD"
    assert contract.provider == "FRED"
    assert contract.provider_series_id == "DGS10"
    assert contract.unit == "PERCENT"
    assert contract.active_owner is False
    assert "PRODUCTION_DECISION" not in contract.allowed_usage_scope
    assert len(contract.contract_hash) == 64


def test_temporal_contract_rejects_timezone_less_available_at():
    with pytest.raises(Exception):
        TemporalEvidence(
            event_time=None,
            source_published_at=None,
            provider_published_at=None,
            first_seen_at=None,
            available_at="2026-09-29T07:00:00",
            fetched_at="2026-09-29T07:01:00+00:00",
            time_quality=EvidenceTimeQuality.PROVIDER_TIME,
        )


def test_date_only_is_not_historical_evaluation_eligible():
    temporal = TemporalEvidence(
        event_time="2026-09-28",
        source_published_at=None,
        provider_published_at=None,
        first_seen_at="2026-09-29T07:00:00+00:00",
        available_at="2026-09-29T07:00:00+00:00",
        fetched_at="2026-09-29T07:00:01+00:00",
        time_quality=EvidenceTimeQuality.DATE_ONLY,
    )

    assert temporal.historical_evaluation_eligible is False
    with pytest.raises(Exception):
        temporal.require_historical_time_quality()


def test_prepared_range_content_identity_excludes_operational_prepared_at():
    common = dict(
        series_id="US_10Y_CONSTANT_MATURITY_YIELD",
        start_date="2026-01-01",
        end_date="2026-09-28",
        expected_count=180,
        stored_count=180,
        missing_count=0,
        unavailable_count=0,
        date_only_count=0,
        eligible_count=180,
        source_contract_version="FRED-DGS10-CANDIDATE-V1",
        normalizer_version="DGS10-PERCENT-V1",
        source_manifest_hash="a" * 64,
    )
    a = MacroPreparedRangeManifest(
        **common,
        prepared_at="2026-09-29T07:00:00+00:00",
    )
    b = MacroPreparedRangeManifest(
        **common,
        prepared_at="2026-09-29T08:00:00+00:00",
    )

    assert a.status == "COMPLETE"
    assert a.content_hash == b.content_hash


def test_research_protocol_does_not_smuggle_numeric_threshold_approval():
    protocol = MacroResearchProtocol(
        protocol_id="NEXT6-MACRO-SHADOW-V1",
        protocol_version="v1",
        baseline_identity="SCANNER-0.21.3.9",
        cutoff_policy="KOREA_EOD_CONFIRMED_AS_OF",
        development_rule="DEVELOPMENT_SEPARATE",
        holdout_rule="HOLDOUT_SEPARATE",
        prospective_rule="PROSPECTIVE_FORWARD_ONLY",
        pit_requirement="AVAILABLE_AT_LE_DECISION_CUTOFF",
        ablation_sequence=(
            "RATE_ONLY",
            "RATE_PLUS_VOLATILITY",
            "ADD_FX_AND_US_INDEX",
        ),
        missing_data_reporting_rule="REPORT_ALL_EXCLUSIONS",
    )
    assert protocol.numeric_thresholds_defined is False
    assert len(protocol.protocol_hash) == 64

    with pytest.raises(MacroContractError, match="최소 표본/충격/승격"):
        MacroResearchProtocol(
            protocol_id="BAD",
            protocol_version="v1",
            baseline_identity="BASELINE",
            cutoff_policy="CUT",
            development_rule="DEV",
            holdout_rule="HOLDOUT",
            prospective_rule="PROSPECTIVE",
            pit_requirement="PIT",
            ablation_sequence=("RATE_ONLY",),
            missing_data_reporting_rule="REPORT",
            numeric_thresholds_defined=True,
        )


def test_read_only_reader_does_not_create_missing_store(tmp_path: Path):
    missing = tmp_path / "nested" / "macro.db"
    reader = LocalMacroReader(missing)

    result = reader.read_series_as_of(
        "US_10Y_CONSTANT_MATURITY_YIELD",
        cutoff=NOW,
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "STORE_NOT_FOUND"
    assert not missing.exists()
    assert not missing.parent.exists()
