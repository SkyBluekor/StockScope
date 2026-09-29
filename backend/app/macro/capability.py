from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


MACRO_CAPABILITY_CONTRACT_VERSION = "VN_NEXT6A_S2_PROVIDER_CAPABILITY_V1"


class CapabilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    SEMANTICS_UNVERIFIED = "SEMANTICS_UNVERIFIED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider: str
    component: str
    status: CapabilityStatus
    configured: bool
    authenticated: bool
    details: dict[str, Any]
    limitations: tuple[str, ...] = ()
    contract_version: str = MACRO_CAPABILITY_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["limitations"] = list(self.limitations)
        return payload
