from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.calibration_research import (
    build_distribution_research,
    summarize_distribution_research,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _write_immutable_json(
    *,
    directory: Path,
    identity: str,
    payload: dict[str, Any],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"RESEARCH-{identity}.json"
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
        raise RuntimeError(f"Immutable research artifact collision: {target}")

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
            "NEXT-6B-S3 Development distribution research. "
            "Holdout input is intentionally unsupported."
        )
    )
    parser.add_argument(
        "--development-artifact",
        required=True,
        type=Path,
        help="NEXT-6B-S2 DEV-*.json artifact",
    )
    parser.add_argument(
        "--protocol-artifact",
        required=True,
        type=Path,
        help="NEXT-6B-S2 PROTOCOL-*.json artifact",
    )
    parser.add_argument(
        "--write-artifact",
        action="store_true",
        help="full research result를 runtime/macro/calibration에 immutable JSON으로 저장합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    development = _load_json(args.development_artifact)
    protocol = _load_json(args.protocol_artifact)

    research = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )
    report = summarize_distribution_research(research)
    if args.write_artifact:
        directory = BACKEND / "runtime" / "macro" / "calibration"
        target = _write_immutable_json(
            directory=directory,
            identity=research["research_hash"][:16],
            payload=research,
        )
        report["artifact"] = str(target)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
