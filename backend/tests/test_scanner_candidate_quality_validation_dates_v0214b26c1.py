from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path


def _load_runner_module():
    # The parser lives in the CLI runner. Stub unrelated integration imports so
    # this regression test remains focused on date-file parsing only.
    market_store = types.ModuleType("app.backtest.market_store")
    market_store.HistoricalMarketStore = object
    scanner = types.ModuleType("app.backtest.scanner")
    scanner.StockScannerService = object
    validation = types.ModuleType("app.backtest.scanner_quality.candidate_quality_validation")
    validation.EXPECTED_SCANNER_VERSION = "0.21.3.7"
    validation.OfflineAuditKrx = object
    validation.ensure_scanner_version = lambda value: None
    validation.run_validation = lambda *args, **kwargs: None
    validation.write_outputs = lambda *args, **kwargs: None

    saved = {}
    stubs = {
        "app.backtest.market_store": market_store,
        "app.backtest.scanner": scanner,
        "app.backtest.scanner_quality.candidate_quality_validation": validation,
    }
    for name, module in stubs.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module

    try:
        path = Path(__file__).resolve().parents[1] / "tools" / "run_scanner_candidate_quality_validation.py"
        spec = importlib.util.spec_from_file_location("b26c_runner_for_date_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def test_date_loader_ignores_commas_inside_comment_lines(tmp_path):
    runner = _load_runner_module()
    path = tmp_path / "dates.txt"
    path.write_text(
        "# Same 20 validation dates used by B.2.6-A/B, held fixed for current-version comparison.\n"
        "2025-08-29\n"
        "2025-09-16, 2025-10-02  # inline comment, also ignored\n",
        encoding="utf-8",
    )

    assert runner.load_dates(path) == [
        date(2025, 8, 29),
        date(2025, 9, 16),
        date(2025, 10, 2),
    ]
