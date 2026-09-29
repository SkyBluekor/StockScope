from __future__ import annotations

from app.macro.features import build_dgs10_features


def _row(date: str, value: str, suffix: str) -> dict[str, object]:
    return {
        "id": f"OBS-{suffix}",
        "observation_key": f"KEY-{suffix}",
        "observation_date": date,
        "normalized_value": value,
        "normalized_hash": suffix * 64,
    }


def _feature(result: dict[str, object], feature_id: str) -> dict[str, object]:
    for feature in result["features"]:  # type: ignore[index]
        if feature["feature_id"] == feature_id:
            return feature
    raise AssertionError(feature_id)


def test_dgs10_one_observation_change_is_basis_points_not_percent_return():
    up = build_dgs10_features(
        [
            _row("2026-09-02", "4.10", "b"),
            _row("2026-09-01", "4.00", "a"),
        ]
    )
    down = build_dgs10_features(
        [
            _row("2026-09-02", "4.00", "d"),
            _row("2026-09-01", "4.10", "c"),
        ]
    )

    assert _feature(up, "delta_bp_1obs")["value"] == "10"
    assert _feature(up, "delta_bp_1obs")["unit"] == "BASIS_POINT"
    assert _feature(down, "delta_bp_1obs")["value"] == "-10"


def test_dgs10_feature_windows_are_observation_distance_not_calendar_days():
    rows = [
        _row("2026-09-11", "4.20", "k"),
        _row("2026-09-10", "4.19", "j"),
        _row("2026-09-09", "4.18", "i"),
        _row("2026-09-08", "4.17", "h"),
        _row("2026-09-07", "4.16", "g"),
        _row("2026-09-04", "4.15", "f"),
        _row("2026-09-03", "4.14", "e"),
        _row("2026-09-02", "4.13", "d"),
        _row("2026-09-01", "4.12", "c"),
        _row("2026-08-31", "4.11", "b"),
        _row("2026-08-28", "4.10", "a"),
    ]

    result = build_dgs10_features(rows)
    five = _feature(result, "delta_bp_5obs")
    ten = _feature(result, "delta_bp_10obs")

    assert five["status"] == "AVAILABLE"
    assert five["observation_distance"] == 5
    assert five["calendar_distance_days"] == 7
    assert ten["status"] == "AVAILABLE"
    assert ten["observation_distance"] == 10
    assert ten["calendar_distance_days"] == 14


def test_insufficient_feature_history_is_not_zero():
    result = build_dgs10_features(
        [
            _row("2026-09-02", "4.10", "b"),
            _row("2026-09-01", "4.00", "a"),
        ]
    )

    five = _feature(result, "delta_bp_5obs")
    ten = _feature(result, "delta_bp_10obs")
    assert five["status"] == "INSUFFICIENT_HISTORY"
    assert five["value"] is None
    assert ten["status"] == "INSUFFICIENT_HISTORY"
    assert ten["value"] is None


def test_missing_numeric_reference_is_not_coerced_to_zero():
    result = build_dgs10_features(
        [
            _row("2026-09-02", "4.10", "b"),
            _row("2026-09-01", ".", "a"),
        ]
    )

    one = _feature(result, "delta_bp_1obs")
    assert one["status"] == "MISSING_REFERENCE"
    assert one["value"] is None
