from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.calibration_research import summarize_distribution_research
from app.macro.identity import content_hash


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError("Research artifact root must be an object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NEXT-6B-S3 immutable research artifact를 read-only로 요약합니다."
    )
    parser.add_argument("artifact", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    research = _load_json(args.artifact)
    feature_hashes = {
        feature_id: content_hash(result)
        for feature_id, result in research.get("feature_results", {}).items()
    }
    identity_payload = {
        "contract_version": research["contract_version"],
        "distribution_contract_version": next(iter(
            research["feature_results"].values()
        ))["contract_version"],
        "development_dataset_hash": research["development_dataset_hash"],
        "protocol_hash": research["protocol_hash"],
        "feature_hashes": feature_hashes,
        "holdout_accessed": research["holdout_accessed"],
        "candidate_selection_status": research["candidate_selection_status"],
        "threshold_selected": research["selected_threshold"] is not None,
        "minimum_sample_selected": research["selected_minimum_sample"] is not None,
        "rolling_lookback_selected": research["selected_rolling_lookback"] is not None,
        "episode_policy_selected": research["episode_policy_selected"],
        "rate_spike_state": research["rate_spike_state"],
        "production_decision_approved": research["production_decision_approved"],
    }
    expected = content_hash(identity_payload)
    if expected != research.get("research_hash"):
        raise ValueError("Research artifact hash mismatch.")
    print(json.dumps(summarize_distribution_research(research), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
