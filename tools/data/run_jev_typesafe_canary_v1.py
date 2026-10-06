from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.jev.typesafe_canary import (
    CANARY_API_BUDGET_USD,
    MAX_SYSTEM_ONE_CALLS,
    MAX_TOTAL_API_CALLS,
    build_canary_protocol_artifact,
    run_real_canary,
    validate_canary_contract,
    write_canary_outputs,
    write_canary_protocol,
)
from app.jev.typesafe_provider import load_typesafe_jev_api_key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the TypeSafe Jev synthetic canary. "
            "Default mode is dry-run and makes zero network calls."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Actually call TypeSafe using the project-root JEV_API_KEY. "
            "Only frozen synthetic fixtures are sent."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional model name returned by GET /v1/models.",
    )
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
    )
    return parser


def _dry_run() -> int:
    artifact = validate_canary_contract()
    protocol_path = write_canary_protocol()
    spec = artifact["spec"]
    print("TYPE-JEV CANARY DRY RUN PASS")
    print(f"protocol={artifact['protocol_id']}")
    print(f"protocol_hash={artifact['protocol_hash']}")
    print(f"protocol_path={protocol_path}")
    print(f"fixtures={len(spec['fixtures'])}")
    print(f"repetitions={spec['repetitions']}")
    print(f"systemone_call_cap={MAX_SYSTEM_ONE_CALLS}")
    print(f"total_api_call_cap={MAX_TOTAL_API_CALLS}")
    print(f"api_budget_usd={CANARY_API_BUDGET_USD}")
    print("network_calls=0")
    print("real_stock_data_sent=false")
    print("actual_trial_activation=false")
    return 0


async def _execute(args: argparse.Namespace) -> int:
    # This presence check intentionally never prints the secret, its prefix,
    # length, hash, or source location.
    if not load_typesafe_jev_api_key():
        print(
            "ERROR: JEV_API_KEY is not available in the process environment "
            "or project-root .env.",
            file=sys.stderr,
        )
        return 2

    protocol_path = write_canary_protocol()
    print("TYPE-JEV SYNTHETIC CANARY START")
    print("credential=PRESENT")
    print(f"protocol_path={protocol_path}")
    print("real_stock_data_sent=false")
    print("actual_trial_activation=false")
    print(
        f"hard_limits=models:1, systemone:{MAX_SYSTEM_ONE_CALLS}, "
        f"total:{MAX_TOTAL_API_CALLS}, budget_usd:{CANARY_API_BUDGET_USD}"
    )

    report = await run_real_canary(
        model_override=args.model,
        deadline_seconds=args.deadline_seconds,
    )
    report_path, binding_path = write_canary_outputs(
        report,
        report_path=args.report_path,
    )

    print(f"status={report['status']}")
    print(f"report_path={report_path}")
    print(f"model_binding_path={binding_path}")
    calls = report.get("api_calls") or {}
    usage = report.get("usage") or {}
    print(
        "api_calls="
        f"{calls.get('total', 0)} "
        f"(models={calls.get('model_discovery', 0)}, "
        f"systemone={calls.get('systemone', 0)})"
    )
    print(
        "usage="
        f"input_tokens={usage.get('input_tokens', 0)}, "
        f"output_tokens={usage.get('output_tokens', 0)}, "
        f"estimated_public_price_usd="
        f"{usage.get('estimated_public_price_usd', 0):.8f}"
    )
    selected = (report.get("threshold_analysis") or {}).get("selected")
    if selected:
        print(
            "selected_threshold="
            f"{selected['low']}/{selected['high']}"
        )
    errors = report.get("errors") or []
    if errors:
        print("errors=" + ",".join(str(item) for item in errors))
    print(
        "trial_freeze_readiness="
        + str(report.get("trial_freeze_readiness"))
    )
    return 0 if report.get("status") == "PASS" else 1


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute:
        return _dry_run()
    return asyncio.run(_execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
