"""Preview Scanner uses the same selected market DB as read-only preflight."""
from pathlib import Path
import sqlite3

from app.api import backtest as api
from app.backtest.market_store import HistoricalMarketStore


def test_scanner_job_service_uses_explicit_preview_market_db(tmp_path, monkeypatch):
    preview_db = tmp_path / "preview" / "market_history.db"
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(preview_db))
    monkeypatch.delenv("STOCKSCOPE_MARKET_DB", raising=False)

    scanner = api._scanner_service(None)
    assert scanner.market_store.db_path == preview_db
    assert preview_db.is_file()
    assert isinstance(scanner.market_store, HistoricalMarketStore)
    assert scanner.krx.api_key == ""

    with sqlite3.connect(preview_db) as connection:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='day_status'"
        ).fetchone() is not None


def test_legacy_scanner_default_still_unmodified_without_override(monkeypatch):
    monkeypatch.delenv("STOCKSCOPE_MARKET_STORE_DB", raising=False)
    monkeypatch.delenv("STOCKSCOPE_MARKET_DB", raising=False)
    from app.backtest.scanner import StockScannerService
    import inspect
    from unittest.mock import patch

    with patch.object(api, "StockScannerService", wraps=StockScannerService) as factory:
        scanner = api._scanner_service(None)
    assert scanner.market_store.db_path == HistoricalMarketStore._default_db
    assert factory.call_count == 1
    assert "market_store" not in factory.call_args.kwargs


def test_preview_scanner_market_fallback_alias_is_honored(tmp_path, monkeypatch):
    alias_db = tmp_path / "market.db"
    monkeypatch.delenv("STOCKSCOPE_MARKET_STORE_DB", raising=False)
    monkeypatch.setenv("STOCKSCOPE_MARKET_DB", str(alias_db))
    scanner = api._scanner_service(None)
    assert scanner.market_store.db_path == alias_db
