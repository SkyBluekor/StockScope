from __future__ import annotations

from types import SimpleNamespace

from app.data_contract.builder import _realtime_contract
from app.data_contract.models import RealtimeQuoteObservation


def _state(**overrides):
    values = {
        "capable": True,
        "present": True,
        "source": "KIS_WEBSOCKET",
        "market": "KOSPI",
        "ticker": "005930",
        "provider": "KIS",
        "mode": "SNAPSHOT",
        "venue": "INTEGRATED",
        "current_price": "84200",
        "provider_timestamp": "2026-09-28T09:30:12+09:00",
        "received_at": "2026-09-28T09:30:12.084+09:00",
        "age_ms": 120000,
        "freshness_seconds": None,
        "session_phase": "REGULAR",
        "trading_day": True,
        "market_active": True,
        "reason": None,
    }
    values.update(overrides)
    return SimpleNamespace(realtime=RealtimeQuoteObservation(**values))


def test_healthy_websocket_snapshot_is_valid_even_when_last_trade_is_old() -> None:
    contract = _realtime_contract(_state())

    assert contract.status == "VALID"
    assert contract.source == "KIS_WEBSOCKET"
    assert contract.reason_code is None


def test_disconnected_websocket_last_tick_is_unverified() -> None:
    contract = _realtime_contract(
        _state(reason="WEBSOCKET_DISCONNECTED_LAST_TICK")
    )

    assert contract.status == "UNVERIFIED"
    assert contract.reason_code == "WEBSOCKET_DISCONNECTED_LAST_TICK"


def test_closed_market_keeps_last_snapshot_valid() -> None:
    contract = _realtime_contract(
        _state(
            session_phase="CLOSED",
            trading_day=False,
            market_active=False,
            reason="WEBSOCKET_DISCONNECTED_LAST_TICK",
        )
    )

    assert contract.status == "VALID"
    assert contract.reason_code == "MARKET_CLOSED_LAST_SNAPSHOT"
