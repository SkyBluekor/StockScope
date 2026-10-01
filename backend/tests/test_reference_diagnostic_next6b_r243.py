from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import pytest

import app.macro.reference_diagnostic as reference_diagnostic
from app.macro.reference_diagnostic import (
    MAD_METHOD,
    TAIL_METHOD,
    build_as_of_reference_diagnostic,
    build_retrospective_reference_diagnostic,
    validate_reference_diagnostic,
)


CUTOFF = "2026-10-01T10:00:00+00:00"


def _rows(count: int, *, constant: bool = False) -> list[dict[str, object]]:
    start = date(2026, 9, 1)
    rows: list[dict[str, object]] = []
    for index in range(count):
        current_date = (start + timedelta(days=index)).isoformat()
        value = (
            "4.00"
            if constant
            else f"{4 + (index * index) / 1000:.3f}"
        )
        rows.append(
            {
                "id": f"OBS-{index}",
                "observation_key": f"DGS10:{current_date}",
                "revision_no": 1,
                "observation_date": current_date,
                "normalized_value": value,
                "normalized_hash": f"{index + 1:064x}",
                "available_at": "2026-09-30T10:00:00+00:00",
                "time_quality": "DATE_ONLY",
            }
        )
    return rows


def _horizon(
    diagnostic: dict[str, object],
    feature_id: str,
) -> dict[str, object]:
    for item in diagnostic["horizons"]:  # type: ignore[index]
        if item["feature_id"] == feature_id:
            return item
    raise AssertionError(feature_id)


def test_as_of_diagnostic_is_descriptive_and_keeps_rate_spike_uncalibrated():
    result = build_as_of_reference_diagnostic(
        _rows(15),
        decision_cutoff=CUTOFF,
    )

    assert result["projection_mode"] == "AS_OF"
    assert result["status"] == "AVAILABLE"
    assert [item["feature_id"] for item in result["horizons"]] == [
        "delta_bp_1obs",
        "delta_bp_5obs",
        "delta_bp_10obs",
    ]
    assert result["governance"]["claim_scope"] == "DESCRIPTIVE_ONLY"
    assert result["governance"]["reference_adequacy"] == "UNRESOLVED"
    assert result["governance"]["minimum_prior_observations"] is None
    assert result["governance"]["recommended_support"] is None
    assert result["governance"]["rate_spike_state"] == "UNCALIBRATED"
    assert result["governance"]["production_decision_approved"] is False
    assert "RISK_GATE" in result["governance"]["prohibited_consumers"]
    assert "STRATEGY_INPUT" in result["governance"]["prohibited_consumers"]

    one = _horizon(result, "delta_bp_1obs")
    assert one["tail"]["status"] == "AVAILABLE"
    assert one["tail"]["ecdf_sup_drift_from_previous"] is not None
    assert one["tail"]["adequacy_pass"] is None
    assert one["tail"]["threshold"] is None
    assert one["mad"]["median"] is not None
    assert one["mad"]["mad"] is not None
    assert one["mad"]["adequacy_pass"] is None
    assert one["mad"]["threshold"] is None

    validated = validate_reference_diagnostic(result)
    assert validated["reference_adequacy"] == "UNRESOLVED"
    assert validated["rate_spike_state"] == "UNCALIBRATED"


def test_future_rows_and_future_revisions_do_not_change_past_as_of_diagnostic():
    original = _rows(15)
    before = build_as_of_reference_diagnostic(
        original,
        decision_cutoff=CUTOFF,
    )

    future_row = {
        "id": "OBS-FUTURE",
        "observation_key": "DGS10:2026-09-30",
        "revision_no": 1,
        "observation_date": "2026-09-30",
        "normalized_value": "8.00",
        "normalized_hash": "f" * 64,
        "available_at": "2026-10-02T10:00:00+00:00",
        "time_quality": "DATE_ONLY",
    }
    future_revision = {
        **original[5],
        "id": "OBS-REVISION",
        "revision_no": 2,
        "normalized_value": "9.00",
        "normalized_hash": "e" * 64,
        "available_at": "2026-10-02T11:00:00+00:00",
    }

    after = build_as_of_reference_diagnostic(
        [*original, future_row, future_revision],
        decision_cutoff=CUTOFF,
    )

    assert after["diagnostic_hash"] == before["diagnostic_hash"]
    assert after["diagnostic_id"] == before["diagnostic_id"]
    assert after["source"] == before["source"]
    assert after["horizons"] == before["horizons"]


def test_zero_mad_is_explicitly_non_computable_not_zero_or_pass():
    result = build_as_of_reference_diagnostic(
        _rows(15, constant=True),
        decision_cutoff=CUTOFF,
    )

    for feature_id in (
        "delta_bp_1obs",
        "delta_bp_5obs",
        "delta_bp_10obs",
    ):
        horizon = _horizon(result, feature_id)
        mad = horizon["mad"]
        assert mad["mad"] == "0"
        assert mad["scale_status"] == "NON_COMPUTABLE_ZERO_SCALE"
        assert (
            mad["normalized_median_shift_status"]
            == "NON_COMPUTABLE_ZERO_SCALE"
        )
        assert (
            mad["relative_mad_change_status"]
            == "NON_COMPUTABLE_ZERO_SCALE"
        )
        assert mad["normalized_median_shift_from_previous"] is None
        assert mad["relative_mad_change_from_previous"] is None
        assert mad["adequacy_pass"] is None

    assert result["status"] == "PARTIAL"


def test_short_history_discloses_all_horizons_instead_of_hiding_them():
    result = build_as_of_reference_diagnostic(
        _rows(3),
        decision_cutoff=CUTOFF,
    )

    assert len(result["horizons"]) == 3
    assert result["status"] == "PARTIAL"

    five = _horizon(result, "delta_bp_5obs")
    ten = _horizon(result, "delta_bp_10obs")
    assert five["reference_count"] == 0
    assert ten["reference_count"] == 0
    assert five["tail"]["status"] == "INSUFFICIENT_HISTORY"
    assert five["mad"]["status"] == "INSUFFICIENT_HISTORY"
    assert ten["tail"]["status"] == "INSUFFICIENT_HISTORY"
    assert ten["mad"]["status"] == "INSUFFICIENT_HISTORY"


def test_validator_rejects_diagnostic_to_policy_promotion():
    result = build_as_of_reference_diagnostic(
        _rows(15),
        decision_cutoff=CUTOFF,
    )
    promoted = deepcopy(result)
    promoted["governance"]["rate_spike_state"] = "DETECTED"

    with pytest.raises(ValueError, match="cannot calibrate RATE_SPIKE"):
        validate_reference_diagnostic(promoted)


def test_retrospective_projection_is_research_only_not_point_in_time(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        reference_diagnostic,
        "validate_reference_stability_evidence",
        lambda artifact: {"stability_hash": artifact["stability_hash"]},
    )
    families = []
    for feature_id in (
        "delta_bp_1obs",
        "delta_bp_5obs",
        "delta_bp_10obs",
    ):
        for method in (TAIL_METHOD, MAD_METHOD):
            families.append(
                {
                    "feature_id": feature_id,
                    "method": method,
                    "transition_count": 3,
                    "descriptive_summaries": {
                        "sample": {
                            "status": "DESCRIPTIVE_ONLY",
                            "count": 3,
                        }
                    },
                }
            )
    stability = {
        "stability_id": "RATESTAB-test",
        "stability_hash": "a" * 64,
        "families": families,
    }

    result = build_retrospective_reference_diagnostic(stability)

    assert result["projection_mode"] == "RETROSPECTIVE"
    assert result["governance"]["point_in_time_eligible"] is False
    assert result["governance"]["reference_adequacy"] == "UNRESOLVED"
    assert result["governance"]["rate_spike_state"] == "UNCALIBRATED"
    assert "RETROSPECTIVE_RESEARCH_ONLY" in result["limitations"]
    assert "NOT_POINT_IN_TIME" in result["limitations"]
    assert "NOT_POLICY_INPUT" in result["limitations"]
    assert "REFERENCE_CONTEXT" not in result["governance"]["allowed_usage"]
