from __future__ import annotations

import gzip
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HistorySeries:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    checked_dates: set[str] = field(default_factory=set)

    def sorted_rows(self) -> list[dict[str, Any]]:
        return [self.rows[key] for key in sorted(self.rows)]


class HistoricalStore:
    """Compact per-symbol/index cache used by backtests.

    KRX's raw cache stores one market-wide payload per date. That is ideal for reuse
    across symbols, but expensive to reopen hundreds of gzip files every time a
    backtest runs. This store materializes the already-normalized rows into one
    compact file per symbol plus one file per benchmark market.
    """

    VERSION = 1
    _root = Path(__file__).resolve().parents[2] / "runtime" / "backtest" / "history"
    _lock = threading.RLock()

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or self._root

    @staticmethod
    def _safe_market(market: str) -> str:
        key = market.upper().strip()
        if key not in {"KOSPI", "KOSDAQ"}:
            raise ValueError("market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        return key

    def stock_path(self, market: str, code: str) -> Path:
        return self.root / self._safe_market(market) / f"stock_{code.upper()}.json.gz"

    def index_path(self, market: str) -> Path:
        return self.root / self._safe_market(market) / "market_index.json.gz"

    def _load(self, path: Path) -> HistorySeries:
        if not path.exists():
            return HistorySeries()
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return HistorySeries()
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            return HistorySeries()
        raw_rows = payload.get("rows") or {}
        rows: dict[str, dict[str, Any]] = {}
        if isinstance(raw_rows, dict):
            for key, row in raw_rows.items():
                if isinstance(key, str) and isinstance(row, dict):
                    rows[key] = row
        checked = payload.get("checked_dates") or []
        return HistorySeries(
            rows=rows,
            checked_dates={str(value) for value in checked if str(value)},
        )

    def load_stock(self, market: str, code: str) -> HistorySeries:
        with self._lock:
            return self._load(self.stock_path(market, code))

    def load_index(self, market: str) -> HistorySeries:
        with self._lock:
            return self._load(self.index_path(market))

    def _save_merge(self, path: Path, series: HistorySeries) -> None:
        with self._lock:
            current = self._load(path)
            current.rows.update(series.rows)
            current.checked_dates.update(series.checked_dates)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as fp:
                    json.dump(
                        {
                            "version": self.VERSION,
                            "rows": current.rows,
                            "checked_dates": sorted(current.checked_dates),
                        },
                        fp,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                tmp.replace(path)
            except OSError:
                # Historical cache failure must not make the actual backtest fail.
                try:
                    tmp.unlink(missing_ok=True)  # type: ignore[possibly-undefined]
                except (OSError, UnboundLocalError):
                    pass

    def save_stock(self, market: str, code: str, series: HistorySeries) -> None:
        self._save_merge(self.stock_path(market, code), series)

    def save_index(self, market: str, series: HistorySeries) -> None:
        self._save_merge(self.index_path(market), series)
