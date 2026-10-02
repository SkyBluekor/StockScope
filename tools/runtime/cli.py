from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.simulation.sim1_store import SimulationRepository
from tools.data.common import (
    DataToolError,
    validate_holdings_db,
    validate_market_db,
)
from tools.dev.sync_local import RuntimePaths, build_runtime_plan, sync_runtime
from tools.runtime.handoff import (
    DEFAULT_EXPORT_DOMAINS,
    RuntimeLocations,
    export_handoff,
    import_handoff,
)


def _domains(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _bootstrap_status() -> dict:
    paths = RuntimePaths.current()
    plan = build_runtime_plan(paths)
    simulation_missing = not paths.simulation.is_file()
    recommendation = (
        "RESTORE_EXISTING_PROJECT"
        if simulation_missing
        else "SYNC_EXISTING_RUNTIME"
    )
    return {
        "status": "INSPECTED",
        "environment": plan["environment"],
        "simulation_present": not simulation_missing,
        "recommendation": recommendation,
        "next": (
            ".\\stockscope.ps1 bootstrap --from-bundle <bundle>"
            if simulation_missing
            else ".\\stockscope.ps1 sync"
        ),
        "runtime_plan": plan,
    }


def _bootstrap_new_simulation(confirm: bool) -> dict:
    if not confirm:
        raise DataToolError(
            "새 Simulation history 생성에는 --confirm-new-history가 필요합니다."
        )
    paths = RuntimePaths.current()
    if paths.simulation.exists():
        raise DataToolError(
            f"Simulation DB가 이미 존재합니다: {paths.simulation}"
        )
    validate_holdings_db(paths.holdings)
    validate_market_db(paths.market)
    SimulationRepository(paths.simulation).initialize()
    result = sync_runtime(paths=paths)
    return {
        "status": "NEW_SIMULATION_HISTORY_CREATED",
        "warning": (
            "기존 Historical Validation/Execution, Prospective, Governance, "
            "Event Evidence, NEXT-6E-S3 history를 복구한 것이 아닙니다."
        ),
        "sync": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockScope ENV-V2 runtime continuity commands."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    handoff = sub.add_parser("handoff")
    handoff_sub = handoff.add_subparsers(dest="handoff_command", required=True)

    export = handoff_sub.add_parser("export")
    export.add_argument(
        "--domains",
        help=(
            "쉼표 구분 domain 목록. 기본: "
            + ",".join(DEFAULT_EXPORT_DOMAINS)
        ),
    )
    export.add_argument("--include-market", action="store_true")
    export.add_argument("--destination", type=Path)

    imp = handoff_sub.add_parser("import")
    imp.add_argument("bundle", type=Path)
    imp.add_argument("--domains", help="쉼표 구분 domain 목록")
    imp.add_argument(
        "--strict",
        action="store_true",
        help="하나라도 conflict가 있으면 아무 domain도 설치하지 않습니다.",
    )

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--from-bundle", type=Path)
    bootstrap.add_argument("--domains", help="쉼표 구분 domain 목록")
    bootstrap.add_argument("--strict", action="store_true")
    bootstrap.add_argument("--new-simulation-history", action="store_true")
    bootstrap.add_argument("--confirm-new-history", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "handoff" and args.handoff_command == "export":
            domains = _domains(args.domains)
            if domains is None:
                domains = list(DEFAULT_EXPORT_DOMAINS)
            if args.include_market and "market" not in domains:
                domains.append("market")
            _print_json(
                export_handoff(
                    domains=domains,
                    destination=args.destination,
                )
            )
            return 0

        if args.command == "handoff" and args.handoff_command == "import":
            _print_json(
                import_handoff(
                    args.bundle,
                    domains=_domains(args.domains),
                    strict=bool(args.strict),
                )
            )
            return 0

        if args.command == "bootstrap":
            if args.from_bundle is not None:
                _print_json(
                    import_handoff(
                        args.from_bundle,
                        domains=_domains(args.domains),
                        strict=bool(args.strict),
                    )
                )
                return 0
            if args.new_simulation_history:
                _print_json(
                    _bootstrap_new_simulation(
                        confirm=bool(args.confirm_new_history)
                    )
                )
                return 0
            _print_json(_bootstrap_status())
            return 0

        raise DataToolError("지원하지 않는 ENV-V2 command입니다.")
    except (DataToolError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
