from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
CALIBRATION_DIR = BACKEND / "runtime" / "macro" / "calibration"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.macro.reference_adequacy_evidence import (
    COMPACT_ENCODING,
    REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION,
    load_reference_adequacy_evidence_file,
    validate_reference_adequacy_evidence,
)
from app.macro.reference_adequacy_protocol import validate_reference_adequacy_protocol
from app.macro.reference_stability import validate_reference_stability_evidence

SYNC_VERSION = "MACRO_ARTIFACT_SYNC_V3"

DEV_NAME = "DEV-7c3f6660b3aae03f.json"
PROTOCOL_NAME = "PROTOCOL-e1de868dc8f16670.json"
RESEARCH_NAME = "RESEARCH-cdd96e164e12017d.json"
DIAGNOSTIC_NAME = "FRONTIER-DIAGNOSTIC-74458592d2e610da.json"
EVIDENCE_NAME = "ADMISSIBILITY-EVIDENCE-da7b94a2a51e3ff6.json"
RECONSTRUCTION_NAME = "ELIGIBILITY-RECONSTRUCTION-c6db8f9dd260fdd4.json"
LEGACY_R21_V1_NAME = "REFERENCE-ADEQUACY-EVIDENCE-3888bb11cb1fc0de.json"

DEV_HASH = "7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1"
PROTOCOL_HASH = "e1de868dc8f1667040e1825f459a8b92516d094a14cfb3a010fc37137850c3bc"
RESEARCH_HASH = "cdd96e164e12017d6043e6b1c855310e45c4f5a86c32b04e2ff0cbf07f6fe5ff"
RECONSTRUCTION_HASH = "c6db8f9dd260fdd45dd580aa84ffd2bc0a684a09170e94b13e701a935930e3c4"


class MacroArtifactSyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FixedArtifactSpec:
    key: str
    label: str
    filename: str
    hash_field: str
    expected_prefix: str
    script: str
    arguments: tuple[str, ...]


def _artifact_path(directory: Path, name: str) -> Path:
    return directory / name


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _identity_ok(path: Path, hash_field: str, expected_prefix: str) -> bool:
    if not path.is_file():
        return False
    try:
        payload = _load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return str(payload.get(hash_field) or "").startswith(expected_prefix)


def fixed_artifact_specs(directory: Path) -> tuple[FixedArtifactSpec, ...]:
    dev = str(_artifact_path(directory, DEV_NAME))
    protocol = str(_artifact_path(directory, PROTOCOL_NAME))
    research = str(_artifact_path(directory, RESEARCH_NAME))
    diagnostic = str(_artifact_path(directory, DIAGNOSTIC_NAME))
    evidence = str(_artifact_path(directory, EVIDENCE_NAME))
    return (
        FixedArtifactSpec(
            "research",
            "Development Research",
            RESEARCH_NAME,
            "research_hash",
            "cdd96e164e12017d",
            "tools/data/research_macro_distribution_next6b_s3.py",
            ("--development-artifact", dev, "--protocol-artifact", protocol, "--write-artifact"),
        ),
        FixedArtifactSpec(
            "diagnostic",
            "Frontier Diagnostic",
            DIAGNOSTIC_NAME,
            "diagnostic_hash",
            "74458592d2e610da",
            "tools/data/diagnose_macro_calibration_frontier_next6b_s4_1r.py",
            (
                "--development-artifact", dev,
                "--protocol-artifact", protocol,
                "--research-artifact", research,
                "--write-artifact",
            ),
        ),
        FixedArtifactSpec(
            "evidence",
            "Admissibility Evidence",
            EVIDENCE_NAME,
            "evidence_hash",
            "da7b94a2a51e3ff6",
            "tools/data/build_macro_admissibility_evidence_next6b_s4_2b.py",
            (
                "--diagnostic-artifact", diagnostic,
                "--development-artifact", dev,
                "--protocol-artifact", protocol,
                "--research-artifact", research,
                "--write-artifact",
            ),
        ),
        FixedArtifactSpec(
            "reconstruction",
            "Eligibility Reconstruction",
            RECONSTRUCTION_NAME,
            "reconstruction_hash",
            "c6db8f9dd260fdd4",
            "tools/data/reconstruct_macro_eligibility_next6b_s4_2b1.py",
            (
                "--development-artifact", dev,
                "--protocol-artifact", protocol,
                "--research-artifact", research,
                "--diagnostic-artifact", diagnostic,
                "--evidence-artifact", evidence,
                "--write-artifact",
            ),
        ),
    )


def _default_runner(script: str, arguments: tuple[str, ...]) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / script), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if len(detail) > 5000:
            detail = detail[-5000:]
        raise MacroArtifactSyncError(
            f"{script} failed with exit code {completed.returncode}: {detail}"
        )


def _valid_stabilities(directory: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(directory.glob("REFERENCE-STABILITY-*.json")):
        try:
            payload = _load_json(path)
            state = validate_reference_stability_evidence(payload)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        source = payload.get("source") or {}
        if source.get("development_dataset_hash") != DEV_HASH:
            continue
        if source.get("protocol_hash") != PROTOCOL_HASH:
            continue
        if source.get("research_hash") != RESEARCH_HASH:
            continue
        if source.get("reconstruction_hash") != RECONSTRUCTION_HASH:
            continue
        stability_hash = str(state["stability_hash"])
        if path.name != f"REFERENCE-STABILITY-{stability_hash[:16]}.json":
            continue
        found[stability_hash] = (path, payload)
    return found


def _valid_adequacy_pairs(
    directory: Path,
    stabilities: dict[str, tuple[Path, dict[str, Any]]],
) -> list[tuple[Path, dict[str, Any], Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any], Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("REFERENCE-ADEQUACY-PROTOCOL-*.json")):
        try:
            payload = _load_json(path)
            state = validate_reference_adequacy_protocol(payload)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        source = payload.get("source") or {}
        if source.get("development_dataset_hash") != DEV_HASH:
            continue
        if source.get("protocol_hash") != PROTOCOL_HASH:
            continue
        if source.get("research_hash") != RESEARCH_HASH:
            continue
        if source.get("reconstruction_hash") != RECONSTRUCTION_HASH:
            continue
        stability_hash = str(source.get("reference_stability_hash") or "")
        stability = stabilities.get(stability_hash)
        if stability is None:
            continue
        adequacy_hash = str(state["adequacy_protocol_hash"])
        if path.name != f"REFERENCE-ADEQUACY-PROTOCOL-{adequacy_hash[:16]}.json":
            continue
        found.append((path, payload, stability[0], stability[1]))
    return found


def _valid_evidence(
    directory: Path,
    adequacy_pairs: list[tuple[Path, dict[str, Any], Path, dict[str, Any]]],
) -> list[tuple[Path, dict[str, Any], Path, Path]]:
    adequacy_by_hash = {
        str(payload["adequacy_protocol_hash"]): (protocol_path, stability_path)
        for protocol_path, payload, stability_path, _ in adequacy_pairs
    }
    found: list[tuple[Path, dict[str, Any], Path, Path]] = []
    for path in sorted(directory.glob("REFERENCE-ADEQUACY-EVIDENCE-*.json.gz")):
        try:
            payload = load_reference_adequacy_evidence_file(path)
            if payload.get("contract_version") != (
                REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION
            ):
                continue
            state = validate_reference_adequacy_evidence(payload)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        protocol_hash = str(
            (payload.get("source") or {}).get("adequacy_protocol_hash") or ""
        )
        pair = adequacy_by_hash.get(protocol_hash)
        if pair is None:
            continue
        evidence_hash = str(state["evidence_hash"])
        if path.name != (
            f"REFERENCE-ADEQUACY-EVIDENCE-{evidence_hash[:16]}.json.gz"
        ):
            continue
        found.append((path, payload, pair[0], pair[1]))
    return found


def _legacy_v1_path(directory: Path) -> Path | None:
    path = directory / LEGACY_R21_V1_NAME
    return path if path.is_file() else None


def _evidence_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload["counts"]
    return {
        "contract": "V2_COMPACT",
        "artifact": path.name,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
        "support_points": int(counts["common_support_point_count"]),
        "families": int(counts["reference_family_count"]),
        "forward_comparisons": int(counts["forward_comparison_count"]),
        "encoding": (payload.get("encoding") or {}).get(
            "representation", COMPACT_ENCODING
        ),
        "logical_evidence_hash": payload.get("logical_evidence_hash"),
        "macro_db_writes": int(payload.get("macro_db_writes") or 0),
        "production_impact": payload.get("production_impact"),
    }


def _base_result(check_only: bool, statuses: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "sync_version": SYNC_VERSION,
        "check_only": check_only,
        "ready": False,
        "blocked": False,
        "missing_seeds": [],
        "generated": [],
        "statuses": statuses,
        "holdout_accessed": False,
        "network_requests": 0,
    }


def sync_macro_artifacts(
    *,
    calibration_dir: Path = CALIBRATION_DIR,
    check_only: bool = False,
    runner: Callable[[str, tuple[str, ...]], None] = _default_runner,
) -> dict[str, Any]:
    calibration_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, str]] = []
    generated: list[str] = []

    missing_seeds: list[str] = []
    for key, filename in (("development", DEV_NAME), ("protocol", PROTOCOL_NAME)):
        present = _artifact_path(calibration_dir, filename).is_file()
        statuses.append(
            {"key": key, "label": filename, "state": "CURRENT" if present else "MISSING"}
        )
        if not present:
            missing_seeds.append(filename)

    if missing_seeds:
        result = _base_result(check_only, statuses)
        result["blocked"] = True
        result["missing_seeds"] = missing_seeds
        return result

    for spec in fixed_artifact_specs(calibration_dir):
        target = _artifact_path(calibration_dir, spec.filename)
        if target.exists() and not _identity_ok(target, spec.hash_field, spec.expected_prefix):
            raise MacroArtifactSyncError(f"Existing immutable artifact is invalid: {target}")
        if _identity_ok(target, spec.hash_field, spec.expected_prefix):
            state = "CURRENT"
        elif check_only:
            state = "MISSING"
        else:
            runner(spec.script, spec.arguments)
            if not _identity_ok(target, spec.hash_field, spec.expected_prefix):
                raise MacroArtifactSyncError(
                    f"{spec.label} did not reproduce expected artifact: {target}"
                )
            state = "GENERATED"
            generated.append(spec.filename)
        statuses.append({"key": spec.key, "label": spec.label, "state": state})

    if check_only and any(item["state"] == "MISSING" for item in statuses):
        return _base_result(True, statuses)

    stabilities = _valid_stabilities(calibration_dir)
    adequacy_pairs = _valid_adequacy_pairs(calibration_dir, stabilities)
    evidence = _valid_evidence(calibration_dir, adequacy_pairs)

    if evidence:
        evidence_path, evidence_payload, adequacy_path, stability_path = evidence[-1]
        statuses.extend(
            [
                {"key": "stability", "label": stability_path.name, "state": "CURRENT"},
                {"key": "adequacy", "label": adequacy_path.name, "state": "CURRENT"},
                {"key": "adequacy_evidence", "label": evidence_path.name, "state": "CURRENT"},
            ]
        )
        return {
            "sync_version": SYNC_VERSION,
            "check_only": check_only,
            "ready": True,
            "blocked": False,
            "missing_seeds": [],
            "generated": generated,
            "statuses": statuses,
            "reference_stability": str(stability_path),
            "reference_adequacy_protocol": str(adequacy_path),
            "reference_adequacy_evidence": str(evidence_path),
            "evidence_summary": _evidence_summary(evidence_path, evidence_payload),
            "holdout_accessed": False,
            "network_requests": 0,
        }

    if check_only:
        if stabilities:
            stability_path = sorted(
                (item[0] for item in stabilities.values()),
                key=lambda p: p.stat().st_mtime_ns,
            )[-1]
            statuses.append(
                {"key": "stability", "label": stability_path.name, "state": "CURRENT"}
            )
        else:
            statuses.append(
                {"key": "stability", "label": "Reference Stability", "state": "MISSING"}
            )
        if adequacy_pairs:
            statuses.append(
                {"key": "adequacy", "label": adequacy_pairs[-1][0].name, "state": "CURRENT"}
            )
        else:
            statuses.append(
                {"key": "adequacy", "label": "Reference Adequacy Protocol V3", "state": "MISSING"}
            )
        legacy = _legacy_v1_path(calibration_dir)
        if legacy is not None:
            statuses.append(
                {
                    "key": "adequacy_evidence_v1",
                    "label": legacy.name,
                    "state": "HISTORICAL",
                }
            )
        statuses.append(
            {
                "key": "adequacy_evidence",
                "label": "Reference Adequacy Evidence V2 Compact",
                "state": "MISSING",
            }
        )
        return _base_result(True, statuses)

    if not stabilities:
        runner(
            "tools/data/analyze_macro_reference_stability_next6b_s4_2b15.py",
            (
                "--development-artifact", str(_artifact_path(calibration_dir, DEV_NAME)),
                "--protocol-artifact", str(_artifact_path(calibration_dir, PROTOCOL_NAME)),
                "--research-artifact", str(_artifact_path(calibration_dir, RESEARCH_NAME)),
                "--reconstruction-artifact", str(_artifact_path(calibration_dir, RECONSTRUCTION_NAME)),
                "--write-artifact",
            ),
        )
        stabilities = _valid_stabilities(calibration_dir)
        if not stabilities:
            raise MacroArtifactSyncError("Reference Stability artifact did not validate.")
        generated.append("REFERENCE-STABILITY-*.json")

    if not adequacy_pairs:
        stability_path = sorted(
            (item[0] for item in stabilities.values()),
            key=lambda p: p.stat().st_mtime_ns,
        )[-1]
        runner(
            "tools/data/preregister_macro_reference_adequacy_next6b_s4_2b16.py",
            (
                "--development-artifact", str(_artifact_path(calibration_dir, DEV_NAME)),
                "--protocol-artifact", str(_artifact_path(calibration_dir, PROTOCOL_NAME)),
                "--research-artifact", str(_artifact_path(calibration_dir, RESEARCH_NAME)),
                "--reconstruction-artifact", str(_artifact_path(calibration_dir, RECONSTRUCTION_NAME)),
                "--reference-stability-artifact", str(stability_path),
                "--write-artifact",
            ),
        )
        adequacy_pairs = _valid_adequacy_pairs(calibration_dir, stabilities)
        if not adequacy_pairs:
            raise MacroArtifactSyncError("Reference Adequacy Protocol V3 did not validate.")
        generated.append("REFERENCE-ADEQUACY-PROTOCOL-*.json")

    adequacy_path, _, stability_path, _ = adequacy_pairs[-1]
    statuses.extend(
        [
            {
                "key": "stability",
                "label": stability_path.name,
                "state": "GENERATED" if "REFERENCE-STABILITY-*.json" in generated else "CURRENT",
            },
            {
                "key": "adequacy",
                "label": adequacy_path.name,
                "state": "GENERATED" if "REFERENCE-ADEQUACY-PROTOCOL-*.json" in generated else "CURRENT",
            },
        ]
    )

    evidence_arguments = [
        "--development-artifact", str(_artifact_path(calibration_dir, DEV_NAME)),
        "--protocol-artifact", str(_artifact_path(calibration_dir, PROTOCOL_NAME)),
        "--research-artifact", str(_artifact_path(calibration_dir, RESEARCH_NAME)),
        "--reconstruction-artifact", str(_artifact_path(calibration_dir, RECONSTRUCTION_NAME)),
        "--reference-stability-artifact", str(stability_path),
        "--reference-adequacy-protocol-artifact", str(adequacy_path),
    ]
    legacy = _legacy_v1_path(calibration_dir)
    if legacy is not None:
        evidence_arguments.extend(["--legacy-v1-artifact", str(legacy)])
    evidence_arguments.append("--write-artifact")
    runner(
        "tools/data/build_macro_reference_adequacy_evidence_next6b_s4_2b16_r21.py",
        tuple(evidence_arguments),
    )
    evidence = _valid_evidence(calibration_dir, adequacy_pairs)
    if not evidence:
        raise MacroArtifactSyncError("Reference Adequacy Evidence did not validate.")
    evidence_path, evidence_payload, adequacy_path, stability_path = evidence[-1]
    generated.append("REFERENCE-ADEQUACY-EVIDENCE-*.json.gz")
    statuses.append(
        {"key": "adequacy_evidence", "label": evidence_path.name, "state": "GENERATED"}
    )
    return {
        "sync_version": SYNC_VERSION,
        "check_only": False,
        "ready": True,
        "blocked": False,
        "missing_seeds": [],
        "generated": generated,
        "statuses": statuses,
        "reference_stability": str(stability_path),
        "reference_adequacy_protocol": str(adequacy_path),
        "reference_adequacy_evidence": str(evidence_path),
        "evidence_summary": _evidence_summary(evidence_path, evidence_payload),
        "holdout_accessed": False,
        "network_requests": 0,
    }


def _print_result(result: dict[str, Any]) -> None:
    print("=" * 78)
    print("STOCKSCOPE MACRO ARTIFACT SYNC")
    print("=" * 78)
    print(f"Mode                    {'CHECK ONLY' if result['check_only'] else 'SYNC'}")
    for item in result["statuses"]:
        print(f"  {item['key']:<18} {item['state']:<10} {item['label']}")
    print("")
    if result.get("missing_seeds"):
        print("Required seeds missing  " + ", ".join(result["missing_seeds"]))
    summary = result.get("evidence_summary")
    if summary:
        print("Reference Adequacy Evidence")
        print(f"  Contract             {summary['contract']}")
        print(f"  Artifact             {summary['artifact']}")
        print(f"  Size                 {summary['size_mb']:.2f} MB")
        print(f"  Support points       {summary['support_points']}")
        print(f"  Families             {summary['families']}")
        print(f"  Forward comparisons  {summary['forward_comparisons']}")
        print(f"  Encoding             {summary['encoding']}")
        print("")
    print("Holdout accessed        NO")
    print("External network        0")
    print(
        "Macro DB writes        "
        f"{summary['macro_db_writes'] if summary else 0}"
    )
    print(
        "Production             "
        f"{summary['production_impact'] if summary else 'NONE'}"
    )
    print(f"Action required         {'NO' if result.get('ready') else 'YES'}")
    if result.get("ready"):
        print("MACRO ARTIFACTS READY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Restore/check the Development-only NEXT-6 Macro calibration artifact "
            "chain used by StockScope Local Sync. Holdout is never read."
        )
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = sync_macro_artifacts(check_only=args.check_only)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            _print_result(result)
        if result.get("blocked") and not args.check_only:
            missing = ", ".join(result.get("missing_seeds") or [])
            raise MacroArtifactSyncError(
                "Macro calibration seed artifacts are missing: " + missing
            )
        return 0
    except (
        MacroArtifactSyncError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print("=" * 78, file=sys.stderr)
        print("STOCKSCOPE MACRO ARTIFACT SYNC FAILED", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Holdout was not accessed. No immutable artifact was overwritten.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
