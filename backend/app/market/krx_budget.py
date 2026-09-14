from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.market.kst import now_kst
from app.market.providers.base import ProviderError


class KrxBudgetExceeded(ProviderError):
    """Raised before a KRX network call would exceed StockScope's safe daily budget."""


@dataclass(frozen=True)
class KrxBudgetSnapshot:
    day: str
    used: int
    retries: int
    safe_limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.safe_limit - self.used)

    def as_dict(self) -> dict[str, int | str]:
        return {
            "day": self.day,
            "used": self.used,
            "retries": self.retries,
            "safe_limit": self.safe_limit,
            "remaining": self.remaining,
        }


class KrxApiBudget:
    """Persistent local ledger for real KRX HTTP requests.

    The counter is intentionally local to StockScope. Calls made with the same API
    key outside StockScope are unknowable here, which is why the default safe limit
    leaves headroom instead of consuming the provider's whole allowance.
    """

    DEFAULT_SAFE_LIMIT = 8_000
    _default_db = Path(__file__).resolve().parents[2] / "runtime" / "krx" / "budget.sqlite3"

    def __init__(self, db_path: Path | None = None, safe_limit: int | None = None) -> None:
        self.db_path = db_path or self._default_db
        configured = safe_limit
        if configured is None:
            raw = os.getenv("KRX_DAILY_SAFE_LIMIT", str(self.DEFAULT_SAFE_LIMIT)).strip()
            try:
                configured = int(raw)
            except ValueError:
                configured = self.DEFAULT_SAFE_LIMIT
        self.safe_limit = max(1, int(configured))
        self._lock = threading.RLock()
        self._ensure_schema()

    @staticmethod
    def _today_key() -> str:
        return now_kst().date().isoformat()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS krx_daily_usage (
                    day TEXT PRIMARY KEY,
                    requests INTEGER NOT NULL DEFAULT 0,
                    retries INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def snapshot(self, day: str | None = None) -> KrxBudgetSnapshot:
        target = day or self._today_key()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT requests, retries FROM krx_daily_usage WHERE day = ?",
                (target,),
            ).fetchone()
        used = int(row[0]) if row else 0
        retries = int(row[1]) if row else 0
        return KrxBudgetSnapshot(target, used, retries, self.safe_limit)

    def assert_can_start(self, estimated_requests: int) -> KrxBudgetSnapshot:
        estimate = max(0, int(estimated_requests))
        snapshot = self.snapshot()
        if snapshot.used + estimate > snapshot.safe_limit:
            raise KrxBudgetExceeded(
                "오늘 KRX 안전 사용량을 넘을 가능성이 있어 데이터 동기화를 시작하지 않았습니다. "
                f"현재 {snapshot.used:,}/{snapshot.safe_limit:,}회, 이번 작업 예상 기본 요청은 {estimate:,}회입니다. "
                "이미 저장된 데이터는 그대로 사용할 수 있으며 다음 날 남은 데이터부터 이어받을 수 있습니다."
            )
        return snapshot

    def consume(self, *, retry: bool = False) -> KrxBudgetSnapshot:
        """Atomically reserve one real HTTP attempt before it is sent."""
        day = self._today_key()
        now = now_kst().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT requests, retries FROM krx_daily_usage WHERE day = ?",
                (day,),
            ).fetchone()
            used = int(row[0]) if row else 0
            retries = int(row[1]) if row else 0
            if used + 1 > self.safe_limit:
                conn.rollback()
                raise KrxBudgetExceeded(
                    "KRX 일일 안전 사용량에 도달해 추가 네트워크 요청을 중단했습니다. "
                    f"현재 {used:,}/{self.safe_limit:,}회입니다. 저장된 데이터는 유지됩니다."
                )
            used += 1
            retries += 1 if retry else 0
            conn.execute(
                """
                INSERT INTO krx_daily_usage(day, requests, retries, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    requests = excluded.requests,
                    retries = excluded.retries,
                    updated_at = excluded.updated_at
                """,
                (day, used, retries, now),
            )
            conn.commit()
        return KrxBudgetSnapshot(day, used, retries, self.safe_limit)
