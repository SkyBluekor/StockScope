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

from app.macro.calibration_candidate import summarize_candidate_set
from app.macro.identity import content_hash


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError("Candidate artifact root must be an object.")
    return payload


def _validate_hash(candidate_set: dict[str, Any]) -> None:
    identity_payload = {
        "contract_version": candidate_set["contract_version"],
        "development_dataset_hash": candidate_set[
            "development_dataset_hash"
        ],
        "protocol_hash": candidate_set["protocol_hash"],
        "research_hash": candidate_set["research_hash"],
        "holdout_dataset_hash_reference": candidate_set[
            "holdout_dataset_hash_reference"
        ],
        "exploration_manifest": candidate_set["exploration_manifest"],
        "candidate_set_status": candidate_set["candidate_set_status"],
        "holdout_locked": candidate_set["holdout_locked"],
        "holdout_accessed": candidate_set["holdout_accessed"],
        "final_candidate_selected": candidate_set[
            "final_candidate_selected"
        ],
        "rate_spike_state": candidate_set["rate_spike_state"],
        "production_decision_approved": candidate_set[
            "production_decision_approved"
        ],
    }
    expected = content_hash(identity_payload)
    if expected != candidate_set.get("candidate_set_hash"):
        raise ValueError("Candidate set hash mismatch.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NEXT-6B-S4 immutable candidate set을 read-only로 요약합니다."
    )
    parser.add_argument("artifact", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidate_set = _load_json(args.artifact)
    _validate_hash(candidate_set)
    print(
        json.dumps(
            summarize_candidate_set(candidate_set),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
