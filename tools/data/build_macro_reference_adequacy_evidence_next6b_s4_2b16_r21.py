from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.reference_adequacy_evidence import (
    build_reference_adequacy_evidence,
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


def _write_immutable_json(
    *,
    directory: Path,
    identity: str,
    payload: dict[str, Any],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"REFERENCE-ADEQUACY-EVIDENCE-{identity}.json"
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    if target.exists():
        current = target.read_text(encoding="utf-8")
        if current == serialized:
            return target
        raise RuntimeError(
            f"Immutable reference adequacy evidence collision: {target}"
        )

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f"{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            fp.write(serialized)
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
            "NEXT-6B-S4.2-B.1.6-R2.1 Development-only boundary-anchored "
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
        "--write-artifact",
        action="store_true",
        help="immutable REFERENCE-ADEQUACY-EVIDENCE-*.json을 저장합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifact = build_reference_adequacy_evidence(
        development_dataset=_load_json(args.development_artifact),
        protocol=_load_json(args.protocol_artifact),
        research=_load_json(args.research_artifact),
        reconstruction=_load_json(args.reconstruction_artifact),
        stability=_load_json(args.reference_stability_artifact),
        adequacy_protocol=_load_json(args.reference_adequacy_protocol_artifact),
        source_main_sha=_git_head(),
    )
    validate_reference_adequacy_evidence(artifact)
    print(render_reference_adequacy_evidence_text(artifact))

    if args.write_artifact:
        target = _write_immutable_json(
            directory=BACKEND / "runtime" / "macro" / "calibration",
            identity=artifact["evidence_hash"][:16],
            payload=artifact,
        )
        print("")
        print(f"Artifact            : {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
