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

from app.macro.assumption_acceptance import (
    build_r3_assumption_evidence,
    render_r3_assumption_evidence_text,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError("Development artifact root must be an object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6E-S6A-R3 Development-input assumption evidence gate. "
            "Only the explicitly supplied frozen DEV artifact is accepted. "
            "No network, database, adequacy-outcome, or alternate-dataset input "
            "is supported."
        )
    )
    parser.add_argument(
        "--development-artifact",
        required=True,
        type=Path,
        help="Exact frozen DEV-7c3f6660b3aae03f.json artifact.",
    )
    parser.add_argument(
        "--certify-clean-isolation",
        action="store_true",
        help=(
            "Explicit operator attestation that this execution context has not "
            "surfaced prohibited evaluation metadata. Omit to fail closed."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="stdout rendering only; no runtime artifact is written.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    evidence = build_r3_assumption_evidence(
        _load_json(args.development_artifact),
        clean_isolation_certified=args.certify_clean_isolation,
    )
    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_r3_assumption_evidence_text(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
