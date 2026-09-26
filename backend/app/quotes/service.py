from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Callable

from app.core.config import Settings, get_settings
from app.integrations.kis.client import (
    KisAccessToken,
    KisAuthenticationError,
    KisConfigurationError,
    normalize_environment,
    validate_settings,
)
from app.integrations.kis.quote import KisDomesticPrice, KisQuoteError, inquire_domestic_price
from app.integrations.kis.token_cache import (
    credential_fingerprint,
    get_access_token,
    invalidate_access_token,
)

from .models import (
    CachedQuoteObservation,
    QuoteCacheKey,
    QuoteResult,
    QuoteSnapshot,
    QuoteVenue,
    VENUE_TO_KIS_MARKET_DIVISION,
)
from .store import QuoteStore, quote_store


_AUTH_ERROR_CODES = {"EGW00123"}


class QuoteServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.provider_code = provider_code


@dataclass(slots=True)
class _Flight:
    event: Event
    snapshot: QuoteSnapshot | None = None
    error: QuoteServiceError | None = None


class QuoteService:
    """Product quote service: cache, same-key single-flight, rate guard, auth retry."""

    def __init__(
        self,
        *,
        store: QuoteStore | None = None,
        settings_getter: Callable[[], Settings] = get_settings,
        token_getter: Callable[[Settings], KisAccessToken] = get_access_token,
        token_invalidator: Callable[..., bool] = invalidate_access_token,
        quote_fetcher: Callable[..., KisDomesticPrice] = inquire_domestic_price,
        cache_ttl_seconds: float | None = None,
        min_upstream_interval_seconds: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.store = store or quote_store
        self.settings_getter = settings_getter
        self.token_getter = token_getter
        self.token_invalidator = token_invalidator
        self.quote_fetcher = quote_fetcher
        self._cache_ttl_override = cache_ttl_seconds
        self._min_interval_override = min_upstream_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep

        self._flight_lock = Lock()
        self._flights: dict[QuoteCacheKey, _Flight] = {}
        self._rate_lock = Lock()
        self._last_upstream_started_at: float | None = None

    @staticmethod
    def _market(value: str) -> str:
        market = (value or "").strip().upper()
        if market not in {"KOSPI", "KOSDAQ"}:
            raise QuoteServiceError(
                "KIS_QUOTE_INVALID_REQUEST",
                "market은 KOSPI 또는 KOSDAQ이어야 합니다.",
                status_code=422,
            )
        return market

    @staticmethod
    def _ticker(value: str) -> str:
        ticker = (value or "").strip().upper()
        if len(ticker) != 6 or not ticker.isdigit():
            raise QuoteServiceError(
                "KIS_QUOTE_INVALID_REQUEST",
                "국내주식 종목코드는 6자리 숫자여야 합니다.",
                status_code=422,
            )
        return ticker

    @staticmethod
    def _venue(value: str) -> QuoteVenue:
        venue = (value or "INTEGRATED").strip().upper()
        if venue not in VENUE_TO_KIS_MARKET_DIVISION:
            raise QuoteServiceError(
                "KIS_QUOTE_INVALID_REQUEST",
                "venue는 INTEGRATED, KRX, NXT 중 하나여야 합니다.",
                status_code=422,
            )
        return venue  # type: ignore[return-value]

    def _settings(self) -> Settings:
        try:
            return validate_settings(self.settings_getter())
        except KisConfigurationError as exc:
            raise QuoteServiceError(
                "KIS_QUOTE_NOT_CONFIGURED",
                str(exc),
                status_code=409,
            ) from exc

    def _key(
        self,
        *,
        settings: Settings,
        market: str,
        ticker: str,
        venue: QuoteVenue,
    ) -> QuoteCacheKey:
        return QuoteCacheKey(
            environment=normalize_environment(settings.kis_env),
            credential_fingerprint=credential_fingerprint(settings),
            market=market,
            ticker=ticker,
            venue=venue,
        )

    def _cache_ttl(self, settings: Settings) -> float:
        raw = (
            self._cache_ttl_override
            if self._cache_ttl_override is not None
            else settings.kis_quote_cache_ttl_seconds
        )
        return max(0.0, float(raw))

    def _min_upstream_interval(self, settings: Settings) -> float:
        raw = (
            self._min_interval_override
            if self._min_interval_override is not None
            else settings.kis_quote_min_upstream_interval_seconds
        )
        return max(0.0, float(raw))

    def _fresh_cached(
        self,
        key: QuoteCacheKey,
        *,
        ttl_seconds: float,
    ) -> QuoteSnapshot | None:
        if ttl_seconds <= 0:
            return None
        snapshot = self.store.peek(key)
        if snapshot is None:
            return None
        if self.store.age_ms(snapshot) <= int(ttl_seconds * 1000):
            return snapshot
        return None

    def _acquire_rate_slot(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            return
        with self._rate_lock:
            now = self._monotonic()
            if self._last_upstream_started_at is not None:
                remaining = interval_seconds - (now - self._last_upstream_started_at)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._monotonic()
            self._last_upstream_started_at = now

    @staticmethod
    def _is_auth_failure(error: KisQuoteError) -> bool:
        return error.status_code == 401 or (error.code or "").strip().upper() in _AUTH_ERROR_CODES

    @staticmethod
    def _quote_error(error: KisQuoteError) -> QuoteServiceError:
        message = str(error)
        invalid_fragments = (
            "missing required field",
            "not a valid number",
            "not finite",
            "unexpected shape",
            "not valid json",
            "did not contain output",
            "greater than zero",
        )
        if any(fragment in message.lower() for fragment in invalid_fragments):
            return QuoteServiceError(
                "KIS_QUOTE_INVALID_RESPONSE",
                message,
                provider_code=error.code,
            )
        return QuoteServiceError(
            "KIS_QUOTE_UPSTREAM_FAILED",
            message,
            provider_code=error.code,
        )

    def _fetch_once(
        self,
        *,
        settings: Settings,
        ticker: str,
        venue: QuoteVenue,
        access_token: str,
    ) -> KisDomesticPrice:
        return self.quote_fetcher(
            ticker,
            VENUE_TO_KIS_MARKET_DIVISION[venue],
            settings,
            access_token=access_token,
        )

    def _fetch_upstream(
        self,
        *,
        settings: Settings,
        market: str,
        ticker: str,
        venue: QuoteVenue,
    ) -> QuoteSnapshot:
        self._acquire_rate_slot(self._min_upstream_interval(settings))
        try:
            token = self.token_getter(settings)
        except (KisConfigurationError, KisAuthenticationError) as exc:
            code = (
                "KIS_QUOTE_NOT_CONFIGURED"
                if isinstance(exc, KisConfigurationError)
                else "KIS_QUOTE_AUTH_FAILED"
            )
            raise QuoteServiceError(
                code,
                str(exc),
                status_code=409 if code == "KIS_QUOTE_NOT_CONFIGURED" else 502,
            ) from exc

        try:
            quote = self._fetch_once(
                settings=settings,
                ticker=ticker,
                venue=venue,
                access_token=token.access_token,
            )
        except KisQuoteError as first_error:
            if not self._is_auth_failure(first_error):
                raise self._quote_error(first_error) from first_error

            self.token_invalidator(
                settings,
                expected_access_token=token.access_token,
            )
            try:
                replacement = self.token_getter(settings)
                self._acquire_rate_slot(self._min_upstream_interval(settings))
                quote = self._fetch_once(
                    settings=settings,
                    ticker=ticker,
                    venue=venue,
                    access_token=replacement.access_token,
                )
            except (KisConfigurationError, KisAuthenticationError) as exc:
                raise QuoteServiceError(
                    "KIS_QUOTE_AUTH_FAILED",
                    str(exc),
                    provider_code=first_error.code,
                ) from exc
            except KisQuoteError as retry_error:
                if self._is_auth_failure(retry_error):
                    raise QuoteServiceError(
                        "KIS_QUOTE_AUTH_FAILED",
                        str(retry_error),
                        provider_code=retry_error.code,
                    ) from retry_error
                raise self._quote_error(retry_error) from retry_error

        return QuoteSnapshot(
            market=market,
            ticker=ticker,
            name=quote.name,
            venue=venue,
            provider_market_division=quote.market_division,
            environment=normalize_environment(settings.kis_env),
            current_price=quote.current_price,
            change_amount=quote.change_amount,
            change_rate=quote.change_rate,
            change_sign=quote.change_sign,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
            base_price=quote.base_price,
            accumulated_volume=quote.volume,
            provider_timestamp=None,
            received_at=datetime.now(timezone.utc),
        )

    def get_quote(
        self,
        *,
        market: str,
        ticker: str,
        venue: str = "INTEGRATED",
    ) -> QuoteResult:
        settings = self._settings()
        clean_market = self._market(market)
        clean_ticker = self._ticker(ticker)
        clean_venue = self._venue(venue)
        key = self._key(
            settings=settings,
            market=clean_market,
            ticker=clean_ticker,
            venue=clean_venue,
        )
        ttl = self._cache_ttl(settings)

        cached = self._fresh_cached(key, ttl_seconds=ttl)
        if cached is not None:
            return QuoteResult(
                snapshot=cached,
                delivery_source="CACHE",
                cache_age_ms=self.store.age_ms(cached),
            )

        with self._flight_lock:
            cached = self._fresh_cached(key, ttl_seconds=ttl)
            if cached is not None:
                return QuoteResult(
                    snapshot=cached,
                    delivery_source="CACHE",
                    cache_age_ms=self.store.age_ms(cached),
                )
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(event=Event())
                self._flights[key] = flight
                leader = True
            else:
                leader = False

        if not leader:
            if not flight.event.wait(timeout=30.0):
                raise QuoteServiceError(
                    "KIS_QUOTE_UPSTREAM_FAILED",
                    "동일 종목 현재가 조회가 제한 시간 안에 완료되지 않았습니다.",
                )
            if flight.error is not None:
                raise QuoteServiceError(
                    flight.error.code,
                    flight.error.message,
                    status_code=flight.error.status_code,
                    provider_code=flight.error.provider_code,
                )
            snapshot = flight.snapshot
            if snapshot is None:
                raise QuoteServiceError(
                    "KIS_QUOTE_UPSTREAM_FAILED",
                    "동일 종목 현재가 조회 결과를 확인하지 못했습니다.",
                )
            return QuoteResult(
                snapshot=snapshot,
                delivery_source="SINGLE_FLIGHT",
                cache_age_ms=self.store.age_ms(snapshot),
            )

        try:
            snapshot = self._fetch_upstream(
                settings=settings,
                market=clean_market,
                ticker=clean_ticker,
                venue=clean_venue,
            )
            self.store.put(key, snapshot)
            flight.snapshot = snapshot
            return QuoteResult(
                snapshot=snapshot,
                delivery_source="UPSTREAM",
                cache_age_ms=0,
            )
        except QuoteServiceError as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with self._flight_lock:
                if self._flights.get(key) is flight:
                    self._flights.pop(key, None)


def observe_cached_quote(
    *,
    market: str,
    ticker: str,
    venue: QuoteVenue = "INTEGRATED",
    settings: Settings | None = None,
    store: QuoteStore | None = None,
) -> CachedQuoteObservation:
    """Read quote capability/cache only. Never issues a token or calls KIS."""
    active_store = store or quote_store
    current_settings = settings or get_settings()
    clean_market = (market or "").strip().upper()
    clean_ticker = (ticker or "").strip().upper()

    if not current_settings.kis_app_key or not current_settings.kis_app_secret:
        return CachedQuoteObservation(
            capable=False,
            present=False,
            source="NONE",
            market=clean_market,
            ticker=clean_ticker,
            venue=venue,
            reason="KIS_QUOTE_NOT_CONFIGURED",
        )

    try:
        environment = normalize_environment(current_settings.kis_env)
        key = QuoteCacheKey(
            environment=environment,
            credential_fingerprint=credential_fingerprint(current_settings),
            market=clean_market,
            ticker=clean_ticker,
            venue=venue,
        )
    except KisConfigurationError:
        return CachedQuoteObservation(
            capable=False,
            present=False,
            source="NONE",
            market=clean_market,
            ticker=clean_ticker,
            venue=venue,
            reason="KIS_QUOTE_NOT_CONFIGURED",
        )

    snapshot = active_store.peek(key)
    freshness_seconds = max(
        0.0,
        float(current_settings.kis_quote_freshness_seconds),
    )
    if snapshot is None:
        return CachedQuoteObservation(
            capable=True,
            present=False,
            source="KIS_REST",
            market=clean_market,
            ticker=clean_ticker,
            venue=venue,
            freshness_seconds=freshness_seconds,
            reason="QUOTE_NOT_OBSERVED",
        )

    return CachedQuoteObservation(
        capable=True,
        present=True,
        source="KIS_REST",
        market=clean_market,
        ticker=clean_ticker,
        venue=venue,
        provider="KIS",
        mode="SNAPSHOT",
        current_price=snapshot.current_price,
        provider_timestamp=snapshot.provider_timestamp,
        received_at=snapshot.received_at,
        age_ms=active_store.age_ms(snapshot),
        freshness_seconds=freshness_seconds,
    )


quote_service = QuoteService()
