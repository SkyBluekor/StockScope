from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

PROSPECTIVE_SCHEMA_VERSION = "VN_P2_S2_PROSPECTIVE_STORAGE_V1"
PROSPECTIVE_CAPTURE_VERSION = "VN_P2_S2_CAPTURE_V1"
PROSPECTIVE_PROTOCOL_VERSION = "VN_P2_S2_PROTOCOL_V1"
PROSPECTIVE_EVALUATION_VERSION = "VN_P2_S2_EVALUATION_V1"
PROSPECTIVE_REPORT_VERSION = "VN_P2_S2_REPORT_V1"

CAPTURE_TERMINAL_STATUSES = {
    "COMPLETE",
    "DUPLICATE",
    "FAILED",
    "CANCELLED",
    "INTERRUPTED",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProspectiveCaptureRequest:
    market_scope: str
    requested_as_of: str | None
    candidate_limit: int
    horizon_intent: str
    horizon_policy_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvaluationProtocolSpec:
    name: str
    market_scope: str
    strategy: str | None
    development_start: str | None
    development_end: str | None
    holdout_start: str | None
    holdout_end: str | None
    observation_windows: tuple[int, ...] = (5, 10, 20)
    purge_trading_days: int = 20
    execution_mode: str = "PRODUCTION_POLICY"
    max_holding_days: int = 20
    round_trip_cost_pct: float = 0.0
    fee_pct: float = 0.0
    tax_pct: float = 0.0
    slippage_pct: float = 0.0
    execution_policy_version: str = "VAL2_EXECUTION_V1"
    exit_policy_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation_windows"] = list(self.observation_windows)
        return payload
