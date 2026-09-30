from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.reference_adequacy_evidence import (
    build_reference_adequacy_evidence,
    canonical_compact_json_bytes,
    compare_legacy_v1_to_compact_v2,
    deterministic_gzip_bytes,
    load_reference_adequacy_evidence_file,
    render_reference_adequacy_evidence_text,
    validate_reference_adequacy_evidence,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if not value:
        raise RuntimeError("Unable to resolve git HEAD.")
    return value


def _write_immutable_gzip_json(
    *,
    directory: Path,
    identity: str,
    payload: dict[str, Any],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"REFERENCE-ADEQUACY-EVIDENCE-{identity}.json.gz"
    serialized = canonical_compact_json_bytes(payload)

    if target.exists():
        current = load_reference_adequacy_evidence_file(target)
        if canonical_compact_json_bytes(current) == serialized:
            return target
        raise RuntimeError(
            f"Immutable reference adequacy evidence collision: {target}"
        )

    compressed = deterministic_gzip_bytes(payload)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=f"{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            fp.write(compressed)
            fp.flush()
            os.fsync(fp.fileno())
            temporary_path = fp.name
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6B-S4.2-B.1.6-R2.1 Development-only compact boundary-anchored "
            "reference adequacy evidence. Selection/tolerance/Holdout inputs "
            "are intentionally unsupported."
        )
    )
    parser.add_argument("--development-artifact", required=True, type=Path)
    parser.add_argument("--protocol-artifact", required=True, type=Path)
    parser.add_argument("--research-artifact", required=True, type=Path)
    parser.add_argument("--reconstruction-artifact", required=True, type=Path)
    parser.add_argument("--reference-stability-artifact", required=True, type=Path)
    parser.add_argument(
        "--reference-adequacy-protocol-artifact",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--legacy-v1-artifact",
        type=Path,
        help=(
            "Optional historical V1 evidence used only for full logical-equivalence "
            "verification. It never influences N, tolerance, or policy."
        ),
    )
    parser.add_argument(
        "--write-artifact",
        action="store_true",
        help="immutable compact REFERENCE-ADEQUACY-EVIDENCE-*.json.gz를 저장합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    generation_started = time.perf_counter()
    artifact = build_reference_adequacy_evidence(
        development_dataset=_load_json(args.development_artifact),
        protocol=_load_json(args.protocol_artifact),
        research=_load_json(args.research_artifact),
        reconstruction=_load_json(args.reconstruction_artifact),
        stability=_load_json(args.reference_stability_artifact),
        adequacy_protocol=_load_json(args.reference_adequacy_protocol_artifact),
        source_main_sha=_git_head(),
    )
    generation_seconds = time.perf_counter() - generation_started

    validation_started = time.perf_counter()
    state = validate_reference_adequacy_evidence(artifact)
    validation_seconds = time.perf_counter() - validation_started

    equivalence = None
    legacy_size = None
    if args.legacy_v1_artifact is not None:
        legacy_size = args.legacy_v1_artifact.stat().st_size
        legacy = load_reference_adequacy_evidence_file(args.legacy_v1_artifact)
        equivalence = compare_legacy_v1_to_compact_v2(legacy, artifact)
        del legacy

    print(render_reference_adequacy_evidence_text(artifact))
    print("")
    print(f"Generation time       : {generation_seconds:.3f} sec")
    print(f"Validation time       : {validation_seconds:.3f} sec")
    if equivalence is not None:
        print(
            "Legacy V1 equivalence : "
            f"{equivalence['status']} ({equivalence['forward_comparison_count']} comparisons)"
        )

    if args.write_artifact:
        predicted_size = len(deterministic_gzip_bytes(artifact))
        if legacy_size is not None and predicted_size > legacy_size * 0.25:
            raise RuntimeError(
                "Compact evidence exceeds the PERF hard gate: "
                f"{predicted_size} bytes > 25% of legacy V1 ({legacy_size} bytes)."
            )
        target = _write_immutable_gzip_json(
            directory=BACKEND / "runtime" / "macro" / "calibration",
            identity=artifact["evidence_hash"][:16],
            payload=artifact,
        )
        size = target.stat().st_size
        print("")
        print(f"Artifact              : {target}")
        print(f"Artifact size         : {size / 1024 / 1024:.2f} MB")
        if legacy_size:
            reduction = (1 - (size / legacy_size)) * 100
            print(f"Legacy V1 size        : {legacy_size / 1024 / 1024:.2f} MB")
            print(f"Size reduction        : {reduction:.2f}%")
        print(f"Support points        : {state['common_support_point_count']}")
        print(f"Families              : {state['reference_family_count']}")
        print(f"Forward comparisons   : {state['forward_comparison_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
