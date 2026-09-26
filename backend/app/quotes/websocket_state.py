from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import QuoteCacheKey


TransportState = Literal[
    "DISABLED",
    "IDLE",
    "CONNECTING",
    "CONNECTED",
    "BACKOFF",
    "DEGRADED",
    "STOPPING",
]
SubscriptionState = Literal[
    "REQUESTED",
    "SUBSCRIBING",
    "SUBSCRIBED",
    "ERROR",
    "EXPIRING",
]


@dataclass(slots=True)
class SubscriptionLease:
    key: QuoteCacheKey
    touched_at: float
    state: SubscriptionState = "REQUESTED"
    error_code: str | None = None
