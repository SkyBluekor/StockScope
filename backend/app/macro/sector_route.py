from __future__ import annotations

from typing import Any


SECTOR_ROUTE_CONTRACT_VERSION = "VN_NEXT6C_S32_SECTOR_ROUTE_V1"

HISTORICAL_SECTOR_BLOCKED_EXTERNAL_SOURCE = "BLOCKED_EXTERNAL_SOURCE"
HISTORICAL_IMPACT_MARKET_STOCK_ONLY = "MARKET_STOCK_ONLY"
PROSPECTIVE_SECTOR_NOT_STARTED = "NOT_STARTED"

SECTOR_ROUTE_UNLOCK_REQUIREMENTS = (
    "AUTHORIZED_KRX_SOURCE",
    "KNOWN_AT_PROVEN",
    "EFFECTIVE_MEMBERSHIP_PROVEN",
    "BENCHMARK_IDENTITY_PROVEN",
    "S2_PIT_COMPATIBLE",
)


def build_sector_route() -> dict[str, Any]:
    """Return the frozen NEXT-6C-S3.2 historical-sector route boundary.

    Historical sector impact remains blocked until an explicitly authorized
    KRX source can satisfy the S2 point-in-time evidence contract. Current
    OpenDART STATIC_CURRENT metadata is never an unlock signal.
    """

    return {
        "contract_version": SECTOR_ROUTE_CONTRACT_VERSION,
        "historical_sector_status": (
            HISTORICAL_SECTOR_BLOCKED_EXTERNAL_SOURCE
        ),
        "historical_impact_mode": HISTORICAL_IMPACT_MARKET_STOCK_ONLY,
        "prospective_sector_status": PROSPECTIVE_SECTOR_NOT_STARTED,
        "unlock_requirements": list(SECTOR_ROUTE_UNLOCK_REQUIREMENTS),
        "current_unlock_state": {
            "authorized_krx_source": False,
            "known_at_proven": False,
            "effective_membership_proven": False,
            "benchmark_identity_proven": False,
            "s2_pit_compatible": False,
        },
        "prohibited_unlock_inputs": [
            "OPENDART_STATIC_CURRENT",
            "CURRENT_INDUSTRY_BACKFILL",
            "QUERY_DATE_AS_KNOWN_AT",
            "FETCH_TIME_AS_KNOWN_AT",
            "UNAUTHORIZED_KRX_WEB_BACKEND",
        ],
        "limitations": [
            "HISTORICAL_SECTOR_EXTERNAL_SOURCE_BLOCK",
            "MARKET_STOCK_ONLY_UNTIL_UNLOCK",
        ],
        "production_decision_approved": False,
    }
