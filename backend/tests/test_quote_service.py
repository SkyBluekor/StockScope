from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.integrations.kis.client import KisAccessToken
from app.integrations.kis.quote import KisDomesticPrice, KisQuoteError
from app.quotes.service import QuoteService, QuoteServiceError
from app.quotes.store import QuoteStore


def _settings(**overrides) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_env": "real",
        "kis_quote_cache_ttl_seconds": 2.0,
        "kis_quote_freshness_seconds": 15.0,
        "kis_quote_min_upstream_interval_seconds": 0.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _token(value: str = "token") -> KisAccessToken:
    return KisAccessToken(
        access_token=value,
        token_type="Bearer",
        expires_in=3600,
        expires_at=None,
    )


def _quote(ticker: str = "005930", market_division: str = "UN") -> KisDomesticPrice:
    return KisDomesticPrice(
        ticker=ticker,
        name="삼성전자",
        market_division=market_division,
        current_price=Decimal("84200"),
        change_amount=Decimal("1200"),
        change_rate=Decimal("1.45"),
        change_sign="2",
        open_price=Decimal("83300"),
        high_price=Decimal("85000"),
        low_price=Decimal("82900"),
        base_price=Decimal("83000"),
        volume=Decimal("12345678"),
    )


def test_quote_cache_avoids_duplicate_upstream_calls() -> None:
    calls = {"count": 0}

    def fetcher(ticker, market_division, settings, *, access_token):
        calls["count"] += 1
        return _quote(ticker, market_division)

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        quote_fetcher=fetcher,
        cache_ttl_seconds=60,
        min_upstream_interval_seconds=0,
    )

    first = service.get_quote(market="KOSPI", ticker="005930")
    second = service.get_quote(market="KOSPI", ticker="005930")

    assert calls["count"] == 1
    assert first.delivery_source == "UPSTREAM"
    assert second.delivery_source == "CACHE"
    assert second.snapshot.current_price == Decimal("84200")


def test_same_symbol_concurrency_is_single_flight() -> None:
    calls = {"count": 0}

    def fetcher(ticker, market_division, settings, *, access_token):
        calls["count"] += 1
        time.sleep(0.05)
        return _quote(ticker, market_division)

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        quote_fetcher=fetcher,
        cache_ttl_seconds=60,
        min_upstream_interval_seconds=0,
    )

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(
            pool.map(
                lambda _index: service.get_quote(market="KOSPI", ticker="005930"),
                range(10),
            )
        )

    assert calls["count"] == 1
    assert {item.snapshot.current_price for item in results} == {Decimal("84200")}
    assert sum(item.delivery_source == "UPSTREAM" for item in results) == 1
    assert all(
        item.delivery_source in {"UPSTREAM", "SINGLE_FLIGHT", "CACHE"}
        for item in results
    )


def test_single_flight_failure_releases_followers() -> None:
    calls = {"count": 0}

    def fetcher(ticker, market_division, settings, *, access_token):
        calls["count"] += 1
        time.sleep(0.03)
        raise KisQuoteError("provider down", code="TEST001")

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        quote_fetcher=fetcher,
        cache_ttl_seconds=60,
        min_upstream_interval_seconds=0,
    )

    def run():
        with pytest.raises(QuoteServiceError) as exc_info:
            service.get_quote(market="KOSPI", ticker="005930")
        return exc_info.value.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        errors = list(pool.map(lambda _index: run(), range(6)))

    assert calls["count"] == 1
    assert set(errors) == {"KIS_QUOTE_UPSTREAM_FAILED"}


def test_auth_failure_invalidates_failed_token_and_retries_once() -> None:
    token_calls = {"count": 0}
    quote_calls = {"count": 0}
    invalidated: list[str] = []

    def token_getter(_settings):
        token_calls["count"] += 1
        return _token("old-token" if token_calls["count"] == 1 else "new-token")

    def invalidator(_settings, *, expected_access_token=None):
        invalidated.append(expected_access_token)
        return True

    def fetcher(ticker, market_division, settings, *, access_token):
        quote_calls["count"] += 1
        if access_token == "old-token":
            raise KisQuoteError("token expired", code="EGW00123")
        return _quote(ticker, market_division)

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=token_getter,
        token_invalidator=invalidator,
        quote_fetcher=fetcher,
        cache_ttl_seconds=0,
        min_upstream_interval_seconds=0,
    )

    result = service.get_quote(market="KOSPI", ticker="005930")

    assert result.snapshot.current_price == Decimal("84200")
    assert token_calls["count"] == 2
    assert quote_calls["count"] == 2
    assert invalidated == ["old-token"]


def test_auth_retry_is_never_recursive() -> None:
    token_calls = {"count": 0}
    quote_calls = {"count": 0}

    def token_getter(_settings):
        token_calls["count"] += 1
        return _token(f"token-{token_calls['count']}")

    def fetcher(ticker, market_division, settings, *, access_token):
        quote_calls["count"] += 1
        raise KisQuoteError("token expired", status_code=401, code="EGW00123")

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=token_getter,
        token_invalidator=lambda *_args, **_kwargs: True,
        quote_fetcher=fetcher,
        cache_ttl_seconds=0,
        min_upstream_interval_seconds=0,
    )

    with pytest.raises(QuoteServiceError) as exc_info:
        service.get_quote(market="KOSPI", ticker="005930")

    assert exc_info.value.code == "KIS_QUOTE_AUTH_FAILED"
    assert token_calls["count"] == 2
    assert quote_calls["count"] == 2


def test_business_error_does_not_refresh_token() -> None:
    invalidations = {"count": 0}

    def fetcher(ticker, market_division, settings, *, access_token):
        raise KisQuoteError("조회 실패", code="TEST001")

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        token_invalidator=lambda *_args, **_kwargs: invalidations.__setitem__("count", invalidations["count"] + 1) or True,
        quote_fetcher=fetcher,
        min_upstream_interval_seconds=0,
    )

    with pytest.raises(QuoteServiceError) as exc_info:
        service.get_quote(market="KOSPI", ticker="005930")

    assert exc_info.value.code == "KIS_QUOTE_UPSTREAM_FAILED"
    assert invalidations["count"] == 0


def test_venue_is_part_of_cache_identity() -> None:
    calls: list[str] = []

    def fetcher(ticker, market_division, settings, *, access_token):
        calls.append(market_division)
        return _quote(ticker, market_division)

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        quote_fetcher=fetcher,
        cache_ttl_seconds=60,
        min_upstream_interval_seconds=0,
    )

    integrated = service.get_quote(market="KOSPI", ticker="005930", venue="INTEGRATED")
    krx = service.get_quote(market="KOSPI", ticker="005930", venue="KRX")
    nxt = service.get_quote(market="KOSPI", ticker="005930", venue="NXT")

    assert calls == ["UN", "J", "NX"]
    assert integrated.snapshot.venue == "INTEGRATED"
    assert krx.snapshot.venue == "KRX"
    assert nxt.snapshot.venue == "NXT"

def test_global_upstream_rate_guard_spaces_distinct_symbols() -> None:
    clock = {"value": 100.0}
    sleeps: list[float] = []
    calls: list[str] = []

    def monotonic():
        return clock["value"]

    def sleep(seconds):
        sleeps.append(seconds)
        clock["value"] += seconds

    def fetcher(ticker, market_division, settings, *, access_token):
        calls.append(ticker)
        return _quote(ticker, market_division)

    service = QuoteService(
        store=QuoteStore(),
        settings_getter=_settings,
        token_getter=lambda _settings: _token(),
        quote_fetcher=fetcher,
        cache_ttl_seconds=0,
        min_upstream_interval_seconds=0.25,
        monotonic=monotonic,
        sleep=sleep,
    )

    service.get_quote(market="KOSPI", ticker="005930")
    service.get_quote(market="KOSPI", ticker="000660")

    assert calls == ["005930", "000660"]
    assert sleeps == [pytest.approx(0.25)]

