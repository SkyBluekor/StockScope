from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.macro.assumption_acceptance import (
    _bandwidth,
    _mval,
    _prefix_scales,
    _rank_sums,
    _reconstruct,
    _ties,
    _validate_representation,
)


ROOT = Path(__file__).resolve().parents[2]


def _synthetic_rows(count: int = 6) -> list[dict[str, object]]:
    start = date(2026, 1, 1)
    levels = {
        position: Decimal("4.00") + Decimal(position + 10) / Decimal("100")
        for position in range(-10, count)
    }
    dates = {
        position: (start + timedelta(days=position + 10)).isoformat()
        for position in range(-10, count)
    }
    refs = {position: f"ref-{position}" for position in range(-10, count)}
    rows: list[dict[str, object]] = []
    for index in range(count):
        features: list[dict[str, object]] = [
            {
                "feature_id": "rate_level_pct",
                "status": "AVAILABLE",
                "value": str(levels[index]),
                "unit": "PERCENT",
                "current_observation_ref": refs[index],
                "baseline_observation_ref": None,
                "current_observation_date": dates[index],
                "baseline_observation_date": None,
                "observation_distance": None,
                "calendar_distance_days": None,
                "reason": None,
                "contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
            }
        ]
        for horizon in (1, 5, 10):
            delta = (levels[index] - levels[index - horizon]) * Decimal("100")
            features.append(
                {
                    "feature_id": f"delta_bp_{horizon}obs",
                    "status": "AVAILABLE",
                    "value": str(delta),
                    "unit": "BASIS_POINT",
                    "current_observation_ref": refs[index],
                    "baseline_observation_ref": refs[index - horizon],
                    "current_observation_date": dates[index],
                    "baseline_observation_date": dates[index - horizon],
                    "observation_distance": horizon,
                    "calendar_distance_days": horizon,
                    "reason": None,
                    "contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
                }
            )
        rows.append(
            {
                "observation_date": dates[index],
                "normalized_hash": refs[index],
                "features": features,
            }
        )
    return rows


def test_native_positions_and_w_to_x_identity_reconstruct_exactly() -> None:
    rows = _synthetic_rows()
    refs, dates, levels = _reconstruct(rows)
    comparison_count = _validate_representation(rows, levels)

    assert sorted(refs) == list(range(-10, len(rows)))
    assert dates[-10] == "2026-01-01"
    assert comparison_count == len(rows) * 3


def test_rank_rule_matches_average_tie_ranks_without_floats() -> None:
    values = [Decimal("1"), Decimal("1"), Decimal("3"), Decimal("2")]
    assert _rank_sums(values) == [3, 3, 8, 6]


def test_tie_profile_preserves_quantization_and_no_jitter_semantics() -> None:
    profile = _ties(
        [Decimal("0"), Decimal("0"), Decimal("1"), Decimal("2")]
    )
    assert profile["integer_basis_point_grid"] is True
    assert profile["unique_value_count"] == 3
    assert profile["maximum_tie_multiplicity"] == 2
    assert profile["zero_count"] == 2


def test_approved_domain_prefix_mad_reports_zero_scale_without_rescue() -> None:
    values = [Decimal("0")] * 6 + [Decimal("1"), Decimal("2"), Decimal("3")]
    profile = _prefix_scales(values, 3)
    assert profile["zero_scale_anchor_count"] > 0
    assert profile["first_zero_scale_anchors"][0] == 3


def test_corrected_lag_selector_reference_fallbacks_are_deterministic() -> None:
    assert _mval([0.01] * 10, 5, 0.1) == 1
    assert _mval([0.2, 0.01, 0.01, 0.01, 0.01, 0.01], 5, 0.1) == 2
    assert _mval([0.2, 0.01, 0.2, 0.01, 0.2, 0.01], 5, 0.1) == 5


def test_bk_reference_preprocessor_is_replay_deterministic() -> None:
    columns: list[list[Decimal]] = []
    for horizon in (1, 5, 10):
        columns.append(
            [
                Decimal(((index * 7 + (index // horizon) * 3 + (index % 11) * horizon) % 31) - 15)
                for index in range(120)
            ]
        )

    first = _bandwidth(columns)
    second = _bandwidth(columns)

    assert second == first
    assert first["coordinate_m"] == [4, 2, 1]
    assert first["lag_cutoff_L"] == 4
    assert first["bandwidth_b"] == 5
    assert first["effective_ell"] == 9
    assert first["manual_fallback_used"] is False


def test_r3_cli_is_stdout_only_and_has_no_runtime_output_switch() -> None:
    cli = (
        ROOT / "tools/data/analyze_macro_assumption_acceptance_next6e_s6a_r3.py"
    ).read_text(encoding="utf-8")
    assert "--development-artifact" in cli
    assert "--format" in cli
    assert "--output" not in cli
    assert "--write-artifact" not in cli
    assert "runtime/macro" not in cli
    assert "sqlite3" not in cli
    assert "httpx" not in cli
    assert "requests" not in cli
