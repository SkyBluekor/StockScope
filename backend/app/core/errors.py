class StockScopeError(Exception):
    """Base application exception."""


class ExternalApiError(StockScopeError):
    """Raised when a read-only external data provider request fails."""


class TradingOperationBlocked(StockScopeError):
    """Raised whenever code attempts to perform a real brokerage order action."""
