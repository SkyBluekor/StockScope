from __future__ import annotations

import argparse
import json

from app.jev.typesafe_canary_v4 import (
    CANARY_V4_PROTOCOL_PATH,
    TypeSafeCanaryV4Error,
    load_frozen_canary_v4_protocol,
    validate_canary_v4_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the frozen TypeSafe Jev Canary V4 protocol. "
            "Default mode performs zero network calls and does not read credentials."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Reserved for the separately approved actual Canary step. "
            "I5 deliberately does not enable network execution."
        ),
    )
    return parser


def _preflight() -> int:
    artifact = load_frozen_canary_v4_protocol()
    spec = artifact["spec"]
    budget = spec["budget"]
    summary = {
        "status": "FROZEN_PREFLIGHT_PASS",
        "protocol_path": str(CANARY_V4_PROTOCOL_PATH),
        "protocol_id": artifact["protocol_id"],
        "protocol_hash": artifact["protocol_hash"],
        "artifact_hash": artifact["artifact_hash"],
        "canonicalization_version": artifact["canonicalization_version"],
        "selection_unique_provider_wires": spec["partition_contract"][
            "selection_unique_provider_wires"
        ],
        "validation_unique_provider_wires": spec["partition_contract"][
            "validation_unique_provider_wires"
        ],
        "repetitions_per_unique_q1_wire": spec[
            "repetitions_per_unique_q1_wire"
        ],
        "planned_systemone_calls": spec["planned_systemone_calls"],
        "model_discovery_attempts_max": spec[
            "model_discovery_attempts_max"
        ],
        "total_api_attempts_hard_cap": spec[
            "total_api_attempts_hard_cap"
        ],
        "per_call_reservation_usd": budget["per_call_reservation_usd"],
        "max_reserved_exposure_usd": budget[
            "max_reserved_exposure_usd"
        ],
        "project_absolute_ceiling_usd": budget[
            "project_absolute_ceiling_usd"
        ],
        "max_request_bytes": spec["max_request_bytes"],
        "network_calls": 0,
        "credential_access": 0,
        "holdout_access": 0,
        "actual_canary_executed": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        validate_canary_v4_contract()
        if args.execute:
            raise TypeSafeCanaryV4Error(
                "CANARY_V4_EXECUTION_REQUIRES_SEPARATE_APPROVAL"
            )
        return _preflight()
    except TypeSafeCanaryV4Error as exc:
        print(f"TYPE-JEV CANARY V4 PREFLIGHT FAIL: {exc.code}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
