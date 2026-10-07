from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.jev.typesafe_canary_v3 import (
    CANARY_V3_API_BUDGET_USD,
    MAX_MODEL_DISCOVERY_ATTEMPTS,
    MAX_SYSTEM_ONE_ATTEMPTS,
    MAX_TOTAL_API_ATTEMPTS,
    load_frozen_canary_v3_protocol,
    run_real_canary_v3,
    synthetic_canary_v3_fixtures,
    threshold_candidate_grid,
    validate_canary_v3_contract,
    write_canary_v3_outputs,
    write_canary_v3_protocol,
)
from app.jev.typesafe_provider import load_typesafe_jev_api_key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the TypeSafe Jev synthetic Canary V3. Default mode validates "
            "and freezes the exact protocol with zero network calls."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call TypeSafe with frozen Canary V3 synthetic fixtures only.",
    )
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=10.0,
        help="Per-call deadline. Frozen V3 default is 10 seconds.",
    )
    parser.add_argument(
        "--per-call-reservation-usd",
        type=float,
        default=None,
        help=(
            "Required for --execute. Must conservatively reserve worst-case "
            "System One cost while keeping all 72 calls within the $0.25 cap."
        ),
    )
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def _dry_run() -> int:
    artifact = validate_canary_v3_contract()
    protocol_path = write_canary_v3_protocol()
    fixtures = synthetic_canary_v3_fixtures()
    selection = [item for item in fixtures if item["partition"] == "selection"]
    validation = [item for item in fixtures if item["partition"] == "validation"]
    print("TYPE-JEV SYNTHETIC CANARY V3 DRY RUN PASS")
    print(f"protocol={artifact['protocol_id']}")
    print(f"protocol_hash={artifact['protocol_hash']}")
    print(f"protocol_path={protocol_path}")
    print(f"selection_contexts={len(selection)}")
    print(f"validation_contexts={len(validation)}")
    print(
        "selection_callable="
        + str(sum(item["route"] == "PROVIDER_CALL" for item in selection))
    )
    print(
        "selection_local_only="
        + str(sum(item["route"] == "LOCAL_ONLY" for item in selection))
    )
    print(
        "validation_callable="
        + str(sum(item["route"] == "PROVIDER_CALL" for item in validation))
    )
    print(
        "validation_local_only="
        + str(sum(item["route"] == "LOCAL_ONLY" for item in validation))
    )
    print(f"repetitions={artifact['spec']['repetitions']}")
    print(f"threshold_candidates={len(threshold_candidate_grid())}")
    print(f"model_discovery_attempt_cap={MAX_MODEL_DISCOVERY_ATTEMPTS}")
    print(f"systemone_attempt_cap={MAX_SYSTEM_ONE_ATTEMPTS}")
    print(f"total_api_attempt_cap={MAX_TOTAL_API_ATTEMPTS}")
    print(f"api_budget_usd={CANARY_V3_API_BUDGET_USD}")
    print("network_calls=0")
    print("real_stock_data_sent=false")
    print("actual_trial_activation=false")
    print("final_threshold_frozen=false")
    return 0


async def _execute(args: argparse.Namespace) -> int:
    # The exact frozen artifact and reservation are checked before credential lookup.
    try:
        artifact = load_frozen_canary_v3_protocol()
    except Exception as exc:
        print(
            "ERROR: Canary V3 protocol must exactly match the frozen artifact "
            f"before --execute ({exc}).",
            file=sys.stderr,
        )
        return 2

    reservation = args.per_call_reservation_usd
    if reservation is None or reservation <= 0:
        print(
            "ERROR: --per-call-reservation-usd is required before real Canary V3.",
            file=sys.stderr,
        )
        return 2
    if reservation * MAX_SYSTEM_ONE_ATTEMPTS > CANARY_V3_API_BUDGET_USD:
        print(
            "ERROR: reservation would exceed the Canary V3 hard budget.",
            file=sys.stderr,
        )
        return 2
    if float(args.deadline_seconds) != float(artifact["spec"]["deadline_seconds"]):
        print(
            "ERROR: --deadline-seconds must equal the frozen Canary V3 value.",
            file=sys.stderr,
        )
        return 2

    if not load_typesafe_jev_api_key():
        print("ERROR: JEV_API_KEY is not available.", file=sys.stderr)
        return 2

    print("TYPE-JEV SYNTHETIC CANARY V3 START")
    print("credential=PRESENT")
    print(f"protocol={artifact['protocol_id']}")
    print("real_stock_data_sent=false")
    print("actual_trial_activation=false")
    print("final_threshold_frozen=false")
    print(
        f"hard_limits=models:{MAX_MODEL_DISCOVERY_ATTEMPTS}, "
        f"systemone:{MAX_SYSTEM_ONE_ATTEMPTS}, "
        f"total:{MAX_TOTAL_API_ATTEMPTS}, "
        f"budget_usd:{CANARY_V3_API_BUDGET_USD}"
    )

    report = await run_real_canary_v3(
        per_call_reservation_usd=reservation,
        model_override=args.model,
        deadline_seconds=args.deadline_seconds,
    )
    report_path, binding_path = write_canary_v3_outputs(
        report,
        report_path=args.report_path,
    )
    print(f"status={report['status']}")
    print(f"report_path={report_path}")
    print(f"model_binding_path={binding_path}")
    print("api_attempts=" + json.dumps(report.get("api_attempts") or {}, sort_keys=True))
    print(
        "systemone_counts="
        + json.dumps(report.get("systemone_counts") or {}, sort_keys=True)
    )
    selected = report.get("selected_threshold")
    if selected:
        print("selected_threshold=" + json.dumps(selected, sort_keys=True))
    errors = report.get("errors") or []
    if errors:
        print("errors=" + ",".join(str(item) for item in errors))
    print("trial_freeze_readiness=" + str(report.get("trial_freeze_readiness")))
    return 0 if report.get("status") == "PASS" else 1


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute:
        return _dry_run()
    return asyncio.run(_execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
