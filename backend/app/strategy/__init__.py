from typing import TYPE_CHECKING

from .engine import StrategyEngine
from .models import (
    MarketRegime,
    StrategyEvaluation,
    StrategyInput,
    StrategyName,
)

if TYPE_CHECKING:
    from .service import StrategyAnalysisService


def __getattr__(name: str):
    if name == "StrategyAnalysisService":
        from .service import StrategyAnalysisService

        return StrategyAnalysisService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MarketRegime",
    "StrategyEvaluation",
    "StrategyInput",
    "StrategyName",
    "StrategyEngine",
    "StrategyAnalysisService",
]
