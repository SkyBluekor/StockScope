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

from app.macro.r4_contract import (
    build_design_manifest,
    validate_model_use_dossier,
    validate_theorem_review,
)


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("DOSSIER_ROOT_MUST_BE_OBJECT")
    return value


def run_preflight(
    *,
    theorem_review: dict[str, Any] | None,
    model_use: dict[str, Any] | None,
    expected_diagnostic_hash: str | None,
    expected_source_scope_hash: str | None,
) -> dict[str, Any]:
    design = build_design_manifest()
    theorem_status, theorem_reasons, theorem_hash = validate_theorem_review(
        theorem_review, design_hash=design["design_hash"]
    )

    if model_use is None:
        model_status, model_reasons, model_hash = validate_model_use_dossier(
            None, diagnostic_hash="", source_scope_hash=""
        )
    elif not expected_diagnostic_hash or not expected_source_scope_hash:
        model_status = "UNRESOLVED"
        model_reasons = ["CLEAN_DIAGNOSTIC_BINDING_REQUIRED"]
        model_hash = None
    else:
        model_status, model_reasons, model_hash = validate_model_use_dossier(
            model_use,
            diagnostic_hash=expected_diagnostic_hash,
            source_scope_hash=expected_source_scope_hash,
        )

    approvals_ready = theorem_status == "PASS" and model_status == "ASSUMPTION_ACCEPTED_FOR_MODEL_USE"
    return {
        "stage": "NEXT-6E-S6A-R4B",
        "design_hash": design["design_hash"],
        "method_id": design["method_id"],
        "target_id": design["target_id"],
        "theorem_review": {
            "status": theorem_status,
            "reason_codes": theorem_reasons,
            "dossier_hash": theorem_hash,
        },
        "model_use": {
            "status": model_status,
            "reason_codes": model_reasons,
            "dossier_hash": model_hash,
        },
        "ready_for_external_review": True,
        "approval_inputs_ready_for_clean_gate_assessment": approvals_ready,
        "formal_clean_replay_executed": False,
        "ga_status": "BLOCKED",
        "downstream_execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXT-6E-S6A-R4B approval preflight. Does not read DEV, Holdout, DB, or runtime state."
    )
    parser.add_argument("--theorem-review-dossier", type=Path)
    parser.add_argument("--model-use-dossier", type=Path)
    parser.add_argument("--expected-diagnostic-hash")
    parser.add_argument("--expected-source-scope-hash")
    parser.add_argument("--format", choices=("summary", "json"), default="summary")
    args = parser.parse_args()

    result = run_preflight(
        theorem_review=_load(args.theorem_review_dossier),
        model_use=_load(args.model_use_dossier),
        expected_diagnostic_hash=args.expected_diagnostic_hash,
        expected_source_scope_hash=args.expected_source_scope_hash,
    )

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print("NEXT-6E-S6A-R4B APPROVAL PREFLIGHT")
        print("Design:", result["design_hash"])
        print("Theorem review:", result["theorem_review"]["status"])
        if result["theorem_review"]["reason_codes"]:
            print("  reasons:", ",".join(result["theorem_review"]["reason_codes"]))
        print("Model use:", result["model_use"]["status"])
        if result["model_use"]["reason_codes"]:
            print("  reasons:", ",".join(result["model_use"]["reason_codes"]))
        print("Ready for external review: YES")
        print("Formal clean replay executed: NO")
        print("G-A: BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
