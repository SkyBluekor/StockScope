from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.r5r_binding import bind_r5r_evaluation_dataset


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as fp:
        raw = fp.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("R5R DEV artifact root must be an object.")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    path.write_text(serialized, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6E R5R evaluation binding only. "
            "This tool binds identity/chronology/structural metadata and "
            "intentionally does NOT calculate T_EMP, L_EMP, S_EMP, candidate "
            "support, Common-N, or Reference Adequacy results."
        )
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Frozen NEXT-6B-S2 DEV calibration dataset JSON.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output path for NEXT6E_R5R_EVALUATION_BINDING_V1 JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset = _load_json(args.dataset)
    source_file_sha256 = _sha256_file(args.dataset)

    result = bind_r5r_evaluation_dataset(
        dataset,
        source_file_sha256=source_file_sha256,
    )
    artifact = result["artifact"]
    _write_json(args.output, artifact)

    print("NEXT-6E R5R EVALUATION BINDING PASS")
    print(f"Dataset ID             : {artifact['dataset_id']}")
    print(f"Dataset hash           : {artifact['dataset_hash']}")
    print(f"Source file SHA256     : {artifact['source_file_sha256']}")
    print(f"Joint rows             : {artifact['joint_row_count']}")
    print(f"Excluded before bind   : {artifact['excluded_before_binding_count']}")
    print(f"Chronology SHA256      : {artifact['joint_chronology_hash']}")
    print(f"Window length          : {artifact['window_length']}")
    print(
        "Effective anchors      : "
        + ",".join(str(item["N"]) for item in artifact["effective_candidate_mapping"])
    )
    print(f"Binding ID             : {artifact['binding_id']}")
    print(f"Binding hash           : {artifact['binding_hash']}")
    print("Metrics computed       : False")
    print("Reference adequacy run : False")
    print("Holdout accessed       : False")
    print(f"Artifact               : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
