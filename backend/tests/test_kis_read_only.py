from app.market.kis.client import DAILY_CHART_PATH, QUOTE_PATH, READ_ONLY_ENDPOINTS, KisApiError, KisReadOnlyClient


def test_kis_allowlist_contains_market_data_only() -> None:
    assert READ_ONLY_ENDPOINTS == {QUOTE_PATH, DAILY_CHART_PATH}
    assert all("order" not in path.lower() for path in READ_ONLY_ENDPOINTS)


def test_non_allowlisted_kis_endpoint_is_blocked() -> None:
    try:
        KisReadOnlyClient._assert_allowed_path("/uapi/domestic-stock/v1/trading/order-cash")
    except KisApiError as exc:
        assert "Blocked non-read-only" in str(exc)
    else:
        raise AssertionError("A non-read-only KIS endpoint was not blocked")


def test_domestic_symbol_validation() -> None:
    assert KisReadOnlyClient._validate_symbol("005930") == "005930"
    for invalid in ("5930", "AAPL", "0059307", ""):
        try:
            KisReadOnlyClient._validate_symbol(invalid)
        except KisApiError:
            pass
        else:
            raise AssertionError(f"Invalid symbol was accepted: {invalid}")
