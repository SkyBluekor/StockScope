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

from app.macro.admissibility_review import (
    build_admissibility_review,
    render_admissibility_review_text,
    validate_admissibility_review,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6B-S4.2-A review-only RATE_SPIKE admissibility report. "
            "Reads one S4.1R diagnostic artifact and never accepts Holdout input."
        )
    )
    parser.add_argument(
        "--diagnostic-artifact",
        required=True,
        type=Path,
        help="NEXT-6B-S4.1R FRONTIER-DIAGNOSTIC-*.json artifact",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    diagnostic = _load_json(args.diagnostic_artifact)
    review = build_admissibility_review(diagnostic)
    validate_admissibility_review(review)
    print(render_admissibility_review_text(review))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
