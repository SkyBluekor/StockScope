from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PruningVariant:
    name: str
    market_limit: int
    quick_limit: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditHorizons:
    values: tuple[int, ...] = (5, 10, 20)

    def normalized(self) -> tuple[int, ...]:
        return tuple(sorted({max(1, int(value)) for value in self.values}))
