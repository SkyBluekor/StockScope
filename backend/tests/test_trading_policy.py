import pytest

from app.core.errors import TradingOperationBlocked
from app.core.trading_policy import block_real_trading


def test_real_trading_is_hard_blocked() -> None:
    with pytest.raises(TradingOperationBlocked):
        block_real_trading()
