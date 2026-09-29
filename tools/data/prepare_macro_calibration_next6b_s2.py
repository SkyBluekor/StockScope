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

from app.macro.calibration_dataset import (
    CalibrationSplitRole,
    build_calibration_dataset,
)
from app.macro.calibration_protocol import (
    build_calibration_research_protocol,
    validate_split_ranges,
)
from app.macro.features import DGS10_FEATURE_WINDOWS
from app.macro.reader import LocalMacroReader
from tools.data.common import macro_db_path


SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"


def write_immutable_json(
    *,
    directory: Path,
    prefix: str,
    identity: str,
    payload: dict[str, Any],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{prefix}-{identity}.json"
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
        raise RuntimeError(f"Immutable artifact collision: {target}")

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


def _dataset_summary(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("status") == "NOT_PREPARED":
        return {
            "status": dataset["status"],
            "reason": dataset.get("reason"),
            "dataset_id": dataset["dataset_id"],
            "dataset_hash": dataset["dataset_hash"],
            "split_role": dataset["split_role"],
        }
    manifest = dataset["manifest"]
    return {
        "status": dataset["status"],
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": dataset["dataset_hash"],
        "split_role": dataset["split_role"],
        "observation_start": manifest["observation_start"],
        "observation_end": manifest["observation_end"],
        "vintage_id": manifest["vintage_id"],
        "warmup_required": manifest["warmup_required"],
        "warmup_count": manifest["warmup_count"],
        "analysis_row_count": manifest["analysis_row_count"],
        "feature_status_counts": manifest["feature_status_counts"],
        "time_quality_counts": manifest["time_quality_counts"],
        "historical_pit_eligible_count": manifest[
            "historical_pit_eligible_count"
        ],
        "usage_scope": manifest["usage_scope"],
        "limitations": manifest["limitations"],
        "production_decision_approved": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "NEXT-6B-S2 fixed-vintage Development/Holdout calibration "
            "dataset을 Local Macro Store에서 준비합니다."
        )
    )
    parser.add_argument("--development-start", required=True)
    parser.add_argument("--development-end", required=True)
    parser.add_argument("--development-vintage", required=True)
    parser.add_argument("--holdout-start", required=True)
    parser.add_argument("--holdout-end", required=True)
    parser.add_argument("--holdout-vintage", required=True)
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="runtime/macro/calibration 아래 immutable JSON artifact를 저장합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ranges = validate_split_ranges(
        development_start=args.development_start,
        development_end=args.development_end,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
    )
    warmup = max(DGS10_FEATURE_WINDOWS)
    reader = LocalMacroReader(macro_db_path())

    development_archive = reader.read_reference_archive_range(
        SERIES_ID,
        observation_start=ranges["development_start"],
        observation_end=ranges["development_end"],
        vintage_id=args.development_vintage,
        warmup_observations=warmup,
    )
    holdout_archive = reader.read_reference_archive_range(
        SERIES_ID,
        observation_start=ranges["holdout_start"],
        observation_end=ranges["holdout_end"],
        vintage_id=args.holdout_vintage,
        warmup_observations=warmup,
    )
    development = build_calibration_dataset(
        archive=development_archive,
        split_role=CalibrationSplitRole.DEVELOPMENT,
    )
    holdout = build_calibration_dataset(
        archive=holdout_archive,
        split_role=CalibrationSplitRole.HOLDOUT,
    )

    protocol = None
    if (
        development["status"] != "NOT_PREPARED"
        and holdout["status"] != "NOT_PREPARED"
    ):
        protocol = build_calibration_research_protocol(
            development_dataset=development,
            holdout_dataset=holdout,
        )

    report = {
        "contract_version": "VN_NEXT6B_S2_PREPARATION_REPORT_V1",
        "series_id": SERIES_ID,
        "network_requests": 0,
        "macro_db_writes": 0,
        "development": _dataset_summary(development),
        "holdout": _dataset_summary(holdout),
        "protocol": protocol.to_dict() if protocol else None,
        "rate_spike_state": "UNCALIBRATED",
        "normal_labels_created": 0,
        "detected_labels_created": 0,
        "production_decision_approved": False,
    }

    artifacts: list[str] = []
    if args.write_artifacts and protocol is not None:
        directory = BACKEND / "runtime" / "macro" / "calibration"
        artifacts.extend(
            [
                str(
                    write_immutable_json(
                        directory=directory,
                        prefix="DEV",
                        identity=development["dataset_hash"][:16],
                        payload=development,
                    )
                ),
                str(
                    write_immutable_json(
                        directory=directory,
                        prefix="HOLDOUT",
                        identity=holdout["dataset_hash"][:16],
                        payload=holdout,
                    )
                ),
                str(
                    write_immutable_json(
                        directory=directory,
                        prefix="PROTOCOL",
                        identity=protocol.protocol_hash[:16],
                        payload=protocol.to_dict(),
                    )
                ),
            ]
        )
        report["artifacts"] = artifacts

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if protocol is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
