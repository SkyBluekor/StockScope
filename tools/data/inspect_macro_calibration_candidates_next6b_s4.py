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

from app.macro.calibration_candidate import (
    summarize_candidate_set,
    validate_candidate_set_artifact,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError("Candidate artifact root must be an object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NEXT-6B-S4 immutable candidate set을 read-only로 요약합니다."
    )
    parser.add_argument("artifact", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidate_set = _load_json(args.artifact)
    validate_candidate_set_artifact(candidate_set)
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
