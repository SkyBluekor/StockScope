from __future__ import annotations

import sqlite3
from pathlib import Path

from .catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalog, HoldingsCatalogError


class ReadOnlyHoldingsCatalog(HoldingsCatalog):
    """HoldingsCatalog read surface backed by SQLite mode=ro with no initialization."""

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(Path(db_path or DEFAULT_HOLDINGS_DB))

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise HoldingsCatalogError(
                "HOLDINGS_STORE_NOT_FOUND",
                "Holdings 저장소를 찾을 수 없습니다.",
            )
        uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
