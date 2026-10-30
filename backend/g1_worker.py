"""Isolated P0-05/G1 FastAPI entrypoint, never the normal StockScope app.

Load production Scanner code without modifying its pinned baseline sources.
Bind Market Store and KRX budget to *existing* operational SQLite files and
enforce a per-child-process HTTP-attempt cap across provider instances/retries.
Only started by tools/data/p0_05_g1_capture_once.py after explicit approval.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading

from app.market.providers.krx import KrxProvider  # noqa: F401 — import budget dependency in established order
from app.backtest.market_store import HistoricalMarketStore
from app.market.krx_budget import KrxApiBudget, KrxBudgetExceeded


def _required_path(name: str) -> Path:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        raise RuntimeError("Missing isolated G1 operational runtime binding.")
    result = Path(raw).resolve()
    if not result.is_file():
        raise RuntimeError("Isolated G1 operational database is unavailable.")
    return result


_market_db = _required_path("STOCKSCOPE_MARKET_STORE_DB")
_budget_db = _required_path("STOCKSCOPE_KRX_BUDGET_DB")
_sim_db = _required_path("STOCKSCOPE_SIM_DB")
_token = (os.getenv("STOCKSCOPE_G1_WORKER_NONCE") or "").strip()
if len(_token) != 32 or any(c not in "0123456789abcdef" for c in _token):
    raise RuntimeError("Missing isolated G1 worker session identity.")
try:
    _cap = int(os.environ["STOCKSCOPE_G1_MAX_KRX_CALLS"])
except (KeyError, ValueError) as exc:
    raise RuntimeError("Missing isolated G1 API request cap.") from exc
if not 16 <= _cap <= 1024:
    raise RuntimeError("Invalid isolated G1 API request cap.")

# These defaults are applied only inside this temporary single-worker process;
# baseline-protected source files remain byte-for-byte unchanged.
HistoricalMarketStore._default_db = _market_db
KrxApiBudget._default_db = _budget_db

_budget_guard = threading.RLock()
_budget_calls = 0
_original_consume = KrxApiBudget.consume


def _bounded_consume(self: KrxApiBudget, *, retry: bool = False):
    global _budget_calls
    with _budget_guard:
        if _budget_calls >= _cap:
            raise KrxBudgetExceeded("Approved G1 KRX request cap reached.")
        result = _original_consume(self, retry=retry)
        _budget_calls += 1
        return result


KrxApiBudget.consume = _bounded_consume

# The regular FastAPI app loads only after all operational bindings are fixed.
from app.main import app  # noqa: E402
