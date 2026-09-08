from enum import StrEnum

from app.core.errors import TradingOperationBlocked


class BrokerageCapability(StrEnum):
    MARKET_DATA = "market_data"
    STOCK_INFO = "stock_info"
    CHART_DATA = "chart_data"
    DISCLOSURE_DATA = "disclosure_data"


READ_ONLY_CAPABILITIES = frozenset(BrokerageCapability)

FORBIDDEN_ORDER_TERMS = frozenset(
    {
        "order",
        "buy",
        "sell",
        "cancel_order",
        "modify_order",
        "place_order",
        "broker_order",
        "매수",
        "매도",
        "주문",
        "정정",
        "취소",
    }
)


def assert_read_only_capability(capability: BrokerageCapability) -> None:
    if capability not in READ_ONLY_CAPABILITIES:
        raise TradingOperationBlocked(
            "StockScope is analysis/simulation only. Real brokerage orders are prohibited."
        )


def block_real_trading(*_: object, **__: object) -> None:
    raise TradingOperationBlocked(
        "Real buy/sell/order operations are permanently disabled in StockScope."
    )
