from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.backtest.scanner import StockScannerService  # noqa: E402
from app.macro.development_coverage import (  # noqa: E402
    DevelopmentCoverageAuditError,
    audit_development_reference_coverage,
)
from app.macro.validation_entry_gate import (  # noqa: E402
    build_next6e_validation_entry_gate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Development-only Macro/Event reference coverage without "
            "running Scanner replay, outcomes, execution, network, or writes."
        )
    )
    parser.add_argument("--validation-id", required=True)
    parser.add_argument("--development-start", required=True)
    parser.add_argument("--development-end", required=True)
    parser.add_argument("--macro-db", required=True, type=Path)
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--simulation-db", required=True, type=Path)
    return parser


def _current_entry_gate() -> dict[str, object]:
    return build_next6e_validation_entry_gate(
        scanner_version=StockScannerService.VERSION,
        macro_numeric_policy="NONE",
        reference_adequacy="UNRESOLVED",
        rate_spike_calibration_status="UNCALIBRATED",
        historical_sector_status="BLOCKED_EXTERNAL_SOURCE",
        historical_impact_mode="MARKET_STOCK_ONLY",
        prospective_sector_status="NOT_STARTED",
        p6_asof_mode="SYSTEM_OBSERVED_AS_OF",
        p6_historical_completeness_proven=False,
        p6_historical_evaluation_approved=False,
        prediction_status="NOT_VALIDATED",
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        report = audit_development_reference_coverage(
            entry_gate=_current_entry_gate(),
            validation_id=args.validation_id,
            development_start=args.development_start,
            development_end=args.development_end,
            macro_db=args.macro_db,
            market_db=args.market_db,
            simulation_db=args.simulation_db,
        )
    except DevelopmentCoverageAuditError as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "code": exc.code,
                    "message": exc.message,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 2

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
