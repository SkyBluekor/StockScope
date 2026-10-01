from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro import (
    SECTOR_MEMBERSHIP_EVIDENCE_CONTRACT_VERSION,
    SECTOR_TEMPORAL_POINT_IN_TIME,
    SECTOR_TEMPORAL_STATIC_CURRENT,
    assess_sector_membership_evidence,
    build_sector_membership_evidence,
    validate_sector_membership_evidence,
)


CUTOFF = "2024-06-03T06:30:00+00:00"
BENCHMARKS = {"KRX-SECTOR-ELECTRONICS"}


def _evidence(**overrides):
    values = {
        "ticker": "005930",
        "market": "KOSPI",
        "sector_group": "전기·전자",
        "benchmark_name": "전기·전자",
        "benchmark_identity": "KRX-SECTOR-ELECTRONICS",
        "effective_from": "2024-01-01",
        "effective_to": "2024-12-31",
        "known_at": "2024-01-02T00:00:00+00:00",
        "source": "TEST_PIT_MEMBERSHIP",
        "source_revision": "v1",
        "source_hash": "a" * 64,
        "temporal_status": SECTOR_TEMPORAL_POINT_IN_TIME,
        "mapping_method": "TEST_EXPLICIT_MEMBERSHIP",
        "historical_membership_proven": True,
        "source_time_proven": True,
    }
    values.update(overrides)
    return build_sector_membership_evidence(**values)


def test_point_in_time_membership_requires_explicit_temporal_evidence():
    evidence = _evidence()

    assert (
        evidence["contract_version"]
        == SECTOR_MEMBERSHIP_EVIDENCE_CONTRACT_VERSION
    )
    assert evidence["effective_from"] == "2024-01-01"
    assert evidence["effective_to"] == "2024-12-31"
    assert evidence["known_at"] == "2024-01-02T00:00:00+00:00"
    assert evidence["historical_membership_proven"] is True
    assert evidence["source_time_proven"] is True

    result = assess_sector_membership_evidence(
        evidence,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    assert result["status"] == "PIT_ELIGIBLE"
    assert result["production_safe"] is True
    assert result["benchmark_identity"] == "KRX-SECTOR-ELECTRONICS"


def test_static_current_mapping_cannot_be_promoted_to_historical_pit():
    evidence = _evidence(
        temporal_status=SECTOR_TEMPORAL_STATIC_CURRENT,
        historical_membership_proven=False,
        source_hash="b" * 64,
    )

    result = assess_sector_membership_evidence(
        evidence,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    assert result["status"] == "STATIC_ONLY"
    assert result["production_safe"] is False
    assert "STATIC_CURRENT_NOT_HISTORICAL_PIT" in evidence["limitations"]

    with pytest.raises(
        ValueError,
        match="cannot claim historical membership proof",
    ):
        _evidence(
            temporal_status=SECTOR_TEMPORAL_STATIC_CURRENT,
            historical_membership_proven=True,
            source_hash="c" * 64,
        )


def test_effective_range_and_known_at_are_independent_boundaries():
    evidence = _evidence(
        effective_from="2024-07-01",
        effective_to=None,
        known_at="2024-01-02T00:00:00+00:00",
    )

    outside = assess_sector_membership_evidence(
        evidence,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )
    assert outside["status"] == "EFFECTIVE_RANGE_MISMATCH"

    future_known = _evidence(
        known_at="2024-06-04T00:00:00+00:00",
        source_hash="d" * 64,
    )
    hidden = assess_sector_membership_evidence(
        future_known,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )
    assert hidden["status"] == "FUTURE_KNOWN_EVIDENCE"
    assert hidden["reason"] == "MAPPING_NOT_KNOWN_BY_DECISION_CUTOFF"


def test_benchmark_history_does_not_prove_membership_without_resolved_identity():
    missing = _evidence(
        benchmark_identity=None,
        source_hash="e" * 64,
    )
    result = assess_sector_membership_evidence(
        missing,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )
    assert result["status"] == "BENCHMARK_UNRESOLVED"

    unavailable = _evidence(
        benchmark_identity="KRX-SECTOR-OTHER",
        source_hash="f" * 64,
    )
    result = assess_sector_membership_evidence(
        unavailable,
        target_date="2024-06-03",
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )
    assert result["status"] == "BENCHMARK_UNRESOLVED"


def test_evidence_identity_is_deterministic_and_tamper_evident():
    first = _evidence()
    second = _evidence()

    assert first["evidence_id"] == second["evidence_id"]
    assert first["evidence_hash"] == second["evidence_hash"]

    tampered = deepcopy(first)
    tampered["sector_group"] = "금융"
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_sector_membership_evidence(tampered)
