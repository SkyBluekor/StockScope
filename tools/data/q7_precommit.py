"""S15 research Q7 precommit CLI. All writes are opt-in, local and never production.

Examples:
  python tools/data/q7_precommit.py inventory
  python tools/data/q7_precommit.py template --strategy pullback > data/q7_draft.json
  python tools/data/q7_precommit.py check --file data/q7_draft.json
  python tools/data/q7_precommit.py freeze --file data/q7_draft.json --acknowledge-research-only
  python tools/data/q7_precommit.py verify --study-id a-study-id
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.jev.q7_diagnosis_s18 import diagnose as diagnose_captures
from app.jev.q7_observation_s16 import measure as measure_maturity
from app.jev.q7_study_audit import audit_study_readonly
from app.jev.q7_precommit_s15 import (
    Q7PrecommitError, freeze, inventory, load, template, validate_spec,
    verify_artifact,
)
from tools.data.common import market_db_path, simulation_db_path


def parser() -> argparse.ArgumentParser:
    cmd = argparse.ArgumentParser(description="Q7 S15 · local research-only precommit")
    cmd.add_argument("mode", choices=("inventory", "observe", "diagnose", "template", "check", "freeze", "verify", "study-audit"))
    cmd.add_argument("--simulation-db", type=Path, default=None)
    cmd.add_argument("--market-db", type=Path, default=None)
    cmd.add_argument("--as-of", default=None)
    cmd.add_argument("--detail-limit", type=int, default=40)
    cmd.add_argument("--max-samples", type=int, default=100_000)
    cmd.add_argument("--strategy", default=None)
    cmd.add_argument("--file", type=Path, default=None)
    cmd.add_argument("--study-id", default=None)
    cmd.add_argument("--store-dir", type=Path, default=None)
    cmd.add_argument("--acknowledge-research-only", action="store_true")
    return cmd


def execute(args: argparse.Namespace) -> dict:
    if args.mode == "inventory":
        return inventory(args.simulation_db or simulation_db_path())
    if args.mode == "study-audit":
        if not args.study_id:
            raise Q7PrecommitError("Q7_STUDY_ID_REQUIRED")
        try:
            cutoff = date.fromisoformat(args.as_of) if args.as_of else None
        except ValueError as exc:
            raise Q7PrecommitError("Q7_STUDY_AS_OF_INVALID") from exc
        return audit_study_readonly(
            args.simulation_db or simulation_db_path(),
            study_id=args.study_id,
            **({"root": args.store_dir} if args.store_dir else {}),
            as_of=cutoff,
        )
    if args.mode == "diagnose":
        try:
            return diagnose_captures(
                args.simulation_db or simulation_db_path(),
                detail_limit=args.detail_limit, max_samples=args.max_samples,
            )
        except ValueError as exc:
            raise Q7PrecommitError(str(exc)) from exc
    if args.mode == "observe":
        try:
            cutoff = date.fromisoformat(args.as_of) if args.as_of else None
            return measure_maturity(
                args.simulation_db or simulation_db_path(),
                args.market_db or market_db_path(), as_of=cutoff,
            )
        except ValueError as exc:
            raise Q7PrecommitError("Q7_S16_AS_OF_DATE_INVALID") from exc
    if args.mode == "template":
        if not args.strategy:
            raise Q7PrecommitError("Q7_STRATEGY_REQUIRED")
        return template(args.strategy)
    root_kw = {"root": args.store_dir} if args.store_dir else {}
    if args.mode == "verify":
        if not args.study_id:
            raise Q7PrecommitError("Q7_STUDY_ID_REQUIRED")
        return verify_artifact(
            load(args.study_id, **root_kw), expected_study_id=args.study_id
        )
    if args.file is None:
        raise Q7PrecommitError("Q7_SPEC_FILE_REQUIRED")
    try:
        value = json.loads(args.file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Q7PrecommitError("Q7_SPEC_READ_FAILED") from exc
    if args.mode == "check":
        validate_spec(value)
        return {
            "status": "RESEARCH_SPEC_VALID_NOT_FROZEN",
            "production_activation_allowed": False,
            "q7_approval_eligible": False,
            "actual_provider_calls": 0,
        }
    if not args.acknowledge_research_only:
        raise Q7PrecommitError("Q7_EXPLICIT_FREEZE_ACKNOWLEDGEMENT_REQUIRED")
    return {
        **freeze(value, **root_kw),
        "note": "로컬 기록은 공인 시각 증명이나 Q7 운영 승인이 아닙니다.",
        "actual_provider_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except Q7PrecommitError as exc:
        print("Q7 S15 차단: " + exc.code, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.mode == "diagnose" and result.get("status") != "DIAGNOSIS_ONLY":
        return 2
    if args.mode == "study-audit" and not result.get("counts_complete"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
