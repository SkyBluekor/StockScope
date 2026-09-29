from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.identity import content_hash


RATE_SPIKE_EPISODE_POLICY_VERSION = (
    "VN_NEXT6B_S4_CONSECUTIVE_TRUE_RUN_V1"
)


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def build_consecutive_true_episodes(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group adjacent TRUE observations into episodes.

    Adjacency follows the ordered observation sequence, not calendar-day
    distance. Any non-TRUE row ends the current episode. There is no gap
    tolerance in S4.
    """

    episodes: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        member_hashes = [str(row["row_hash"]) for row in current]
        identity = {
            "policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
            "start_date": str(current[0]["observation_date"]),
            "end_date": str(current[-1]["observation_date"]),
            "member_row_hashes": member_hashes,
        }
        episode_hash = content_hash(identity)
        episodes.append(
            {
                "episode_id": f"RATEEP-{episode_hash[:16]}",
                "episode_hash": episode_hash,
                "start_date": identity["start_date"],
                "end_date": identity["end_date"],
                "length_observations": len(current),
                "member_row_hashes": member_hashes,
            }
        )
        current = []

    for row in rows:
        if bool(row.get("signal")):
            current.append(row)
        else:
            flush()
    flush()

    signal_count = sum(bool(row.get("signal")) for row in rows)
    lengths = [int(episode["length_observations"]) for episode in episodes]
    yearly_episode_counts: dict[str, int] = {}
    for episode in episodes:
        year = str(episode["start_date"])[:4]
        yearly_episode_counts[year] = yearly_episode_counts.get(year, 0) + 1

    average_length = (
        _decimal_text(Decimal(sum(lengths)) / Decimal(len(lengths)))
        if lengths
        else None
    )
    return {
        "policy_version": RATE_SPIKE_EPISODE_POLICY_VERSION,
        "start_rule": "FALSE_OR_UNKNOWN_TO_TRUE",
        "continue_rule": "ADJACENT_OBSERVATION_TRUE",
        "end_rule": "TRUE_TO_FALSE_OR_UNKNOWN",
        "gap_tolerance_observations": 0,
        "repeat_alert_rule": "EPISODE_START_ONCE",
        "signal_row_count": signal_count,
        "episode_count": len(episodes),
        "average_length_observations": average_length,
        "max_length_observations": max(lengths) if lengths else 0,
        "yearly_episode_counts": dict(sorted(yearly_episode_counts.items())),
        "episodes": episodes,
    }
