from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.macro.r4c_replay import (
    R4CError,
    approval_binding_status,
    build_phase_a_result,
    build_phase_b_assessment,
    validate_clean_attestation,
)


def _load_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise R4CError("INPUT_OBJECT_INVALID", f"{path} root must be an object")
    return value


def _load_optional(path: Path | None) -> dict[str, Any] | None:
    return None if path is None else _load_object(path)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    if not path.parent.exists():
        raise R4CError("OUTPUT_PARENT_MISSING", str(path.parent))
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _print_status(value: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return
    print("NEXT-6E-S6A-R4C")
    print("Phase A:", value["phase_a_status"])
    print("Theorem review:", value["theorem_review"]["status"])
    if value["theorem_review"]["reason_codes"]:
        print("  reasons:", ",".join(value["theorem_review"]["reason_codes"]))
    print("Model use:", value["model_use"]["status"])
    if value["model_use"]["reason_codes"]:
        print("  reasons:", ",".join(value["model_use"]["reason_codes"]))
    print("Checkpoint:", value["checkpoint_status"])
    print("Ready for Phase B:", "YES" if value["ready_for_phase_b"] else "NO")
    print("G-A: BLOCKED")


def _phase_a(args: argparse.Namespace) -> int:
    attestation = _load_object(args.clean_attestation)

    # Validate clean-scope governance before opening the Development artifact.
    validate_clean_attestation(attestation)

    try:
        development_bytes = args.development_artifact.read_bytes()
    except FileNotFoundError as exc:
        raise R4CError("SOURCE_UNAVAILABLE", str(args.development_artifact)) from exc

    result = build_phase_a_result(
        development_bytes=development_bytes,
        attestation=attestation,
    )
    _write_json(args.output, result)
    print("NEXT-6E-S6A-R4C PHASE A")
    print("Status:", result["phase_a_status"])
    print("Diagnostic:", result["diagnostic_hash"])
    print("Source scope:", result["source_scope_hash"])
    print("G-A: BLOCKED (approval binding required)")
    return 0


def _phase_b(args: argparse.Namespace) -> int:
    result = build_phase_b_assessment(
        phase_a_result=_load_object(args.phase_a_result),
        theorem_review=_load_optional(args.theorem_review_dossier),
        model_use=_load_optional(args.model_use_dossier),
    )
    _write_json(args.output, result)
    print("NEXT-6E-S6A-R4C PHASE B")
    print("G-A:", result["ga_status"])
    print("Method state:", result["method_state"])
    print("G-B:", result["g_b_state"])
    print("Downstream execution authorized: NO")
    return 0


def _status(args: argparse.Namespace) -> int:
    value = approval_binding_status(
        phase_a_result=_load_object(args.phase_a_result),
        theorem_review=_load_optional(args.theorem_review_dossier),
        model_use=_load_optional(args.model_use_dossier),
    )
    _print_status(value, as_json=args.format == "json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6E-S6A-R4C two-phase clean replay. "
            "No Holdout, Reference Adequacy, DB/runtime discovery, network retrieval, or multiplier simulation."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("phase-a", help="Run explicit clean Development diagnostic and seal Phase A evidence.")
    a.add_argument("--development-artifact", type=Path, required=True)
    a.add_argument("--clean-attestation", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=_phase_a)

    b = sub.add_parser("phase-b", help="Evaluate sealed Phase A evidence with approved dossiers.")
    b.add_argument("--phase-a-result", type=Path, required=True)
    b.add_argument("--theorem-review-dossier", type=Path, required=True)
    b.add_argument("--model-use-dossier", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    b.set_defaults(func=_phase_b)

    s = sub.add_parser("status", help="Report approval-binding checkpoint without changing gate state.")
    s.add_argument("--phase-a-result", type=Path, required=True)
    s.add_argument("--theorem-review-dossier", type=Path)
    s.add_argument("--model-use-dossier", type=Path)
    s.add_argument("--format", choices=("summary", "json"), default="summary")
    s.set_defaults(func=_status)

    args = parser.parse_args()
    try:
        return args.func(args)
    except R4CError as exc:
        print(f"R4C BLOCKED [{exc.code}] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
