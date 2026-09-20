from __future__ import annotations

import csv
from pathlib import Path

from app.backtest.scanner_quality.entry_stability_volume_holdout import write_outputs


def test_write_outputs_accepts_extended_candidate_fields(tmp_path: Path):
    payload = {
        "production_changed": False,
        "verdict": "KEEP_RESEARCH_ONLY",
        "holdout": {"valid_date_count": 1, "overlap_with_excluded": 0},
        "comparisons": {"top3": {"CURRENT": {}, "VOLUME_LOW_GUARD": {}}},
        "date_outcomes": {},
        "swaps": {},
        "ranking_impact": {},
        "blocks": [],
        "verdict_reasons": [],
        "dates": [
            {
                "current_candidates": [
                    {
                        "analysis_date": "2026-01-01",
                        "code": "005930",
                        "name": "삼성전자",
                        "market": "KOSPI",
                        "current_rank": 1,
                        "guard_rank": 1,
                        "candidate_state": "READY",
                        "strategy": "pullback",
                        "volume_ratio_prev20": 0.75,
                        "volume_q25": 0.50,
                        "volume_low": False,
                        "conditions_missing": 0,
                        "atr14_pct": 2.5,
                        "return_std_20d_pct": 1.8,
                        "close_location": 0.7,
                        "event_5d": "NO_EVENT",
                        "event_r_10d": 0.2,
                        "risk_status": "READY",
                        "guard_rule": "VOLUME_LOW_GUARD",
                        "event_20d": "TARGET1_FIRST",
                        "event_r_20d": 1.5,
                        "return_20d": 7.0,
                        "mfe_20d": 9.0,
                        "mae_20d": -2.0,
                    }
                ]
            }
        ],
    }

    paths = write_outputs(payload, tmp_path)
    csv_path = Path(paths["csv"])
    assert csv_path.exists()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["conditions_missing"] == "0"
    assert rows[0]["atr14_pct"] == "2.5"
    assert rows[0]["event_r_10d"] == "0.2"
    assert rows[0]["guard_rule"] == "VOLUME_LOW_GUARD"


def test_write_outputs_handles_no_candidate_rows(tmp_path: Path):
    payload = {
        "production_changed": False,
        "verdict": "KEEP_RESEARCH_ONLY",
        "holdout": {"valid_date_count": 1, "overlap_with_excluded": 0},
        "comparisons": {"top3": {"CURRENT": {}, "VOLUME_LOW_GUARD": {}}},
        "date_outcomes": {},
        "swaps": {},
        "ranking_impact": {},
        "blocks": [],
        "verdict_reasons": [],
        "dates": [{"current_candidates": []}],
    }
    paths = write_outputs(payload, tmp_path)
    assert Path(paths["csv"]).exists()

from app.backtest.scanner_quality.entry_stability_volume_holdout import (
    CURRENT,
    RULE_ID,
    _date_outcome,
    _ranking_impact,
    _select,
)


def test_topn_metrics_ignore_watch_and_validation_rows():
    date_results = [
        {
            "status": "OK",
            "current_candidates": [
                {"code": "W", "candidate_state": "WATCH", "event_r_20d": 99.0},
                {"code": "A", "candidate_state": "READY", "event_r_20d": 1.0},
                {"code": "B", "candidate_state": "READY", "event_r_20d": 2.0},
            ],
            "guard_candidates": [
                {"code": "W", "candidate_state": "WATCH", "event_r_20d": 99.0},
                {"code": "B", "candidate_state": "READY", "event_r_20d": 2.0},
                {"code": "A", "candidate_state": "READY", "event_r_20d": 1.0},
            ],
        }
    ]
    assert [r["code"] for r in _select(date_results, CURRENT, 3)] == ["A", "B"]
    assert [r["code"] for r in _select(date_results, RULE_ID, 3)] == ["B", "A"]


def test_no_ready_date_is_not_counted_as_event_r_tie_and_not_ranking_checked():
    current = [{"code": "W", "candidate_state": "WATCH", "event_r_20d": 1.0}]
    guard = [{"code": "W", "candidate_state": "WATCH", "event_r_20d": 1.0}]
    assert _date_outcome(current, guard)["status"] == "NO_READY"
    impact = _ranking_impact([{"status": "OK", "current_candidates": current, "guard_candidates": guard}])
    assert impact["checked_dates"] == 0
    assert impact["no_ready_dates"] == 1
