from __future__ import annotations

from app.macro import (
    SECTOR_TEMPORAL_POINT_IN_TIME,
    SECTOR_TEMPORAL_STATIC_CURRENT,
    build_sector_membership_evidence,
    build_sector_pit_coverage_audit,
)


CUTOFF = "2024-06-03T06:30:00+00:00"
BENCHMARKS = {
    "KRX-SECTOR-ELECTRONICS",
    "KRX-SECTOR-FINANCE",
}


def _evidence(
    *,
    ticker: str,
    benchmark_identity: str | None,
    sector_group: str,
    temporal_status: str,
    known_at: str = "2024-01-02T00:00:00+00:00",
    effective_from: str = "2024-01-01",
    effective_to: str | None = "2024-12-31",
    source_hash: str,
    historical_membership_proven: bool | None = None,
    source_time_proven: bool = True,
):
    if historical_membership_proven is None:
        historical_membership_proven = (
            temporal_status == SECTOR_TEMPORAL_POINT_IN_TIME
        )
    return build_sector_membership_evidence(
        ticker=ticker,
        market="KOSPI",
        sector_group=sector_group,
        benchmark_name=sector_group,
        benchmark_identity=benchmark_identity,
        effective_from=effective_from,
        effective_to=effective_to,
        known_at=known_at,
        source="TEST_SECTOR_MEMBERSHIP",
        source_revision="v1",
        source_hash=source_hash,
        temporal_status=temporal_status,
        mapping_method="TEST_MAPPING",
        historical_membership_proven=historical_membership_proven,
        source_time_proven=source_time_proven,
    )


def _target(ticker: str, target_date: str = "2024-06-03"):
    return {
        "ticker": ticker,
        "market": "KOSPI",
        "target_date": target_date,
    }


def test_coverage_audit_preserves_each_exclusion_reason():
    evidences = [
        _evidence(
            ticker="005930",
            benchmark_identity="KRX-SECTOR-ELECTRONICS",
            sector_group="전기·전자",
            temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
            source_hash="1" * 64,
        ),
        _evidence(
            ticker="000660",
            benchmark_identity="KRX-SECTOR-ELECTRONICS",
            sector_group="전기·전자",
            temporal_status=SECTOR_TEMPORAL_STATIC_CURRENT,
            source_hash="2" * 64,
        ),
        _evidence(
            ticker="035420",
            benchmark_identity="KRX-SECTOR-ELECTRONICS",
            sector_group="전기·전자",
            temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
            effective_from="2025-01-01",
            effective_to=None,
            source_hash="3" * 64,
        ),
        _evidence(
            ticker="105560",
            benchmark_identity="KRX-SECTOR-FINANCE",
            sector_group="금융",
            temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
            source_time_proven=False,
            source_hash="4" * 64,
        ),
        _evidence(
            ticker="055550",
            benchmark_identity="KRX-SECTOR-NOT-PREPARED",
            sector_group="금융",
            temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
            source_hash="5" * 64,
        ),
    ]

    audit = build_sector_pit_coverage_audit(
        targets=[
            _target("005930"),
            _target("000660"),
            _target("035420"),
            _target("105560"),
            _target("055550"),
            _target("999999"),
        ],
        evidences=evidences,
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    by_ticker = {
        row["ticker"]: row
        for row in audit["results"]
    }
    assert by_ticker["005930"]["status"] == "PIT_ELIGIBLE"
    assert by_ticker["000660"]["status"] == "STATIC_ONLY"
    assert by_ticker["035420"]["status"] == "EFFECTIVE_RANGE_MISMATCH"
    assert by_ticker["105560"]["status"] == "SOURCE_TIME_UNPROVEN"
    assert by_ticker["055550"]["status"] == "BENCHMARK_UNRESOLVED"
    assert by_ticker["999999"]["status"] == "MAPPING_MISSING"

    summary = audit["summary"]
    assert summary["status"] == "PARTIAL"
    assert summary["total_targets"] == 6
    assert summary["pit_eligible"] == 1
    assert summary["status_counts"]["STATIC_ONLY"] == 1
    assert summary["status_counts"]["MAPPING_MISSING"] == 1
    assert audit["governance"]["static_current_promotable"] is False
    assert audit["governance"]["production_decision_approved"] is False
    assert audit["governance"]["network_access"] is False


def test_future_known_evidence_cannot_rewrite_frozen_coverage_audit():
    static = _evidence(
        ticker="005930",
        benchmark_identity="KRX-SECTOR-ELECTRONICS",
        sector_group="전기·전자",
        temporal_status=SECTOR_TEMPORAL_STATIC_CURRENT,
        source_hash="6" * 64,
    )
    before = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[static],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    future_pit = _evidence(
        ticker="005930",
        benchmark_identity="KRX-SECTOR-ELECTRONICS",
        sector_group="전기·전자",
        temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
        known_at="2024-06-04T00:00:00+00:00",
        source_hash="7" * 64,
    )
    after = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[static, future_pit],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    assert after["audit_hash"] == before["audit_hash"]
    assert after["audit_id"] == before["audit_id"]
    assert after["results"] == before["results"]


def test_unrelated_evidence_does_not_change_requested_audit_identity():
    target_evidence = _evidence(
        ticker="005930",
        benchmark_identity="KRX-SECTOR-ELECTRONICS",
        sector_group="전기·전자",
        temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
        source_hash="8" * 64,
    )
    before = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[target_evidence],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    unrelated = _evidence(
        ticker="000660",
        benchmark_identity="KRX-SECTOR-ELECTRONICS",
        sector_group="전기·전자",
        temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
        source_hash="9" * 64,
    )
    after = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[target_evidence, unrelated],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    assert after["audit_hash"] == before["audit_hash"]


def test_conflicting_point_in_time_membership_fails_closed():
    electronics = _evidence(
        ticker="005930",
        benchmark_identity="KRX-SECTOR-ELECTRONICS",
        sector_group="전기·전자",
        temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
        source_hash="a" * 64,
    )
    finance = _evidence(
        ticker="005930",
        benchmark_identity="KRX-SECTOR-FINANCE",
        sector_group="금융",
        temporal_status=SECTOR_TEMPORAL_POINT_IN_TIME,
        source_hash="b" * 64,
    )

    audit = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[electronics, finance],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    row = audit["results"][0]
    assert row["status"] == "CONFLICTING_PIT_EVIDENCE"
    assert row["production_safe"] is False
    assert row["selected_evidence_hash"] is None
    assert audit["summary"]["pit_eligible"] == 0
    assert audit["summary"]["status"] == "UNAVAILABLE"


def test_benchmark_availability_alone_never_creates_membership():
    audit = build_sector_pit_coverage_audit(
        targets=[_target("005930")],
        evidences=[],
        decision_cutoff=CUTOFF,
        available_benchmark_identities=BENCHMARKS,
    )

    row = audit["results"][0]
    assert row["status"] == "MAPPING_MISSING"
    assert row["benchmark_identity"] is None
    assert row["production_safe"] is False
