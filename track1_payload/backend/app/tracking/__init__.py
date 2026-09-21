"""Recommendation tracking domain for StockScope."""

from .service import RecommendationTrackingService
from .store import RecommendationTrackingRepository

__all__ = ["RecommendationTrackingRepository", "RecommendationTrackingService"]
