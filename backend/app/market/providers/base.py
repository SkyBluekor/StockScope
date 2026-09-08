class ProviderError(RuntimeError):
    """Raised when an external market-data provider returns an invalid response."""


class ProviderNotConfigured(ProviderError):
    """Raised when a required provider key is not configured."""
