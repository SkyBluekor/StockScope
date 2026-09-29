from __future__ import annotations

from app.macro.shock_episode import build_consecutive_true_episodes


def _row(index: int, signal: bool) -> dict[str, object]:
    return {
        "observation_date": f"2020-01-{index + 1:02d}",
        "row_hash": f"row-{index}",
        "signal": signal,
    }


def test_consecutive_true_run_episode_policy_has_zero_gap_tolerance():
    result = build_consecutive_true_episodes(
        [
            _row(0, False),
            _row(1, True),
            _row(2, True),
            _row(3, True),
            _row(4, False),
            _row(5, True),
        ]
    )

    assert result["gap_tolerance_observations"] == 0
    assert result["repeat_alert_rule"] == "EPISODE_START_ONCE"
    assert result["signal_row_count"] == 4
    assert result["episode_count"] == 2
    assert result["episodes"][0]["length_observations"] == 3
    assert result["episodes"][1]["length_observations"] == 1
    assert result["average_length_observations"] == "2"
    assert result["max_length_observations"] == 3


def test_unknown_or_false_row_breaks_an_episode():
    rows = [
        _row(0, True),
        {
            "observation_date": "2020-01-02",
            "row_hash": "unknown",
            "signal": False,
            "eligible": False,
        },
        _row(2, True),
    ]
    result = build_consecutive_true_episodes(rows)

    assert result["episode_count"] == 2
