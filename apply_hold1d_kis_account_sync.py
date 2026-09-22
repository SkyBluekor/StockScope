from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
HOLDINGS_DIR = ROOT / "backend" / "app" / "holdings"
KIS_DIR = ROOT / "backend" / "app" / "integrations" / "kis"

CATALOG = HOLDINGS_DIR / "catalog.py"
DOMAIN = HOLDINGS_DIR / "domain.py"
ANALYSIS = HOLDINGS_DIR / "analysis.py"
LIFECYCLE = HOLDINGS_DIR / "lifecycle.py"
HOLDINGS_INIT = HOLDINGS_DIR / "__init__.py"
KIS_SYNC = HOLDINGS_DIR / "kis_sync.py"
TEST = ROOT / "backend" / "tests" / "test_holdings_kis_sync_hold1d.py"

KIS_ACCOUNT = KIS_DIR / "account.py"
KIS_CLIENT = KIS_DIR / "client.py"
KIS_TOKEN_CACHE = KIS_DIR / "token_cache.py"
KIS_QUOTE = KIS_DIR / "quote.py"
KIS_WEBSOCKET = KIS_DIR / "websocket_client.py"

KIS_SYNC_CONTENT = 'from __future__ import annotations\n\nimport sqlite3\nfrom dataclasses import dataclass\nfrom datetime import datetime, timezone\nfrom decimal import Decimal, InvalidOperation\nfrom pathlib import Path\nfrom typing import Any, Callable\nfrom uuid import uuid4\n\nfrom app.core.config import PROJECT_ROOT, Settings, get_settings\nfrom app.integrations.kis.account import (\n    KisAccountError,\n    KisDomesticBalance,\n    KisHolding,\n    inquire_domestic_balance,\n)\nfrom app.integrations.kis.client import (\n    KisConfigurationError,\n    normalize_environment,\n    validate_account_settings,\n)\n\nfrom .catalog import HoldingsCatalog\nfrom .domain import account_fingerprint\n\n\nDEFAULT_MARKET_STORE_DB = (\n    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"\n)\n\n\nclass HoldingsKisSyncError(RuntimeError):\n    def __init__(self, code: str, message: str):\n        super().__init__(message)\n        self.code = code\n        self.message = message\n\n\n@dataclass(frozen=True, slots=True)\nclass KisAccountSyncResult:\n    sync_run_id: str\n    account_id: str\n    status: str\n    observed_at: str\n    page_count: int\n    holding_count: int\n    created_positions: int\n    reconciled_positions: int\n    closed_positions: int\n    unchanged_positions: int\n\n\ndef _now() -> str:\n    return datetime.now(timezone.utc).isoformat()\n\n\ndef _decimal(value: Any, *, field: str, non_negative: bool = False, positive: bool = False) -> Decimal:\n    try:\n        number = value if isinstance(value, Decimal) else Decimal(str(value))\n    except (InvalidOperation, ValueError, TypeError) as exc:\n        raise HoldingsKisSyncError(\n            "HOLD_KIS_SYNC_INVALID_HOLDING",\n            f"KIS holding field {field} is not a valid decimal.",\n        ) from exc\n    if not number.is_finite():\n        raise HoldingsKisSyncError(\n            "HOLD_KIS_SYNC_INVALID_HOLDING",\n            f"KIS holding field {field} must be finite.",\n        )\n    if positive and number <= 0:\n        raise HoldingsKisSyncError(\n            "HOLD_KIS_SYNC_INVALID_HOLDING",\n            f"KIS holding field {field} must be greater than zero.",\n        )\n    if non_negative and number < 0:\n        raise HoldingsKisSyncError(\n            "HOLD_KIS_SYNC_INVALID_HOLDING",\n            f"KIS holding field {field} must not be negative.",\n        )\n    return number\n\n\ndef _decimal_text(value: Decimal) -> str:\n    return format(value, "f")\n\n\nclass KisAccountSyncService:\n    """Read a complete KIS balance snapshot and reconcile BROKER positions.\n\n    This service never infers trades. KIS balance changes are recorded only as\n    BALANCE_OBSERVED or RECONCILED events.\n    """\n\n    def __init__(\n        self,\n        catalog: HoldingsCatalog,\n        *,\n        settings: Settings | None = None,\n        market_store_db: Path | None = None,\n        balance_reader: Callable[[Settings], KisDomesticBalance] | None = None,\n    ) -> None:\n        self.catalog = catalog\n        self.settings = settings\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n        self.balance_reader = balance_reader or inquire_domestic_balance\n\n    @staticmethod\n    def _account_display_name(environment: str) -> str:\n        return "한국투자증권 실계좌" if environment == "REAL" else "한국투자증권 모의계좌"\n\n    def _start_sync(self, settings: Settings) -> tuple[str, str]:\n        environment = normalize_environment(settings.kis_env).upper()\n        fingerprint = account_fingerprint(\n            provider="KIS",\n            broker_environment=environment,\n            account_number=settings.kis_account_no or "",\n            product_code=settings.kis_account_product_code,\n        )\n        now = _now()\n        conn = self.catalog.connect()\n        try:\n            conn.execute("BEGIN IMMEDIATE")\n            account = conn.execute(\n                """\n                SELECT * FROM position_account\n                WHERE provider=\'KIS\'\n                  AND broker_environment=?\n                  AND external_account_fingerprint=?\n                """,\n                (environment, fingerprint),\n            ).fetchone()\n            if account is None:\n                account_id = str(uuid4())\n                conn.execute(\n                    """\n                    INSERT INTO position_account(\n                        id,provider,account_kind,broker_environment,\n                        external_account_fingerprint,display_name,status,\n                        created_at,updated_at\n                    ) VALUES(?,?,?,?,?,?,?,?,?)\n                    """,\n                    (\n                        account_id,\n                        "KIS",\n                        "BROKER",\n                        environment,\n                        fingerprint,\n                        self._account_display_name(environment),\n                        "ACTIVE",\n                        now,\n                        now,\n                    ),\n                )\n            else:\n                if str(account["account_kind"]) != "BROKER" or str(account["status"]) != "ACTIVE":\n                    raise HoldingsKisSyncError(\n                        "HOLD_KIS_SYNC_ACCOUNT_CONFLICT",\n                        "기존 KIS 계좌 항목이 BROKER/ACTIVE 상태가 아닙니다.",\n                    )\n                account_id = str(account["id"])\n\n            sync_run_id = str(uuid4())\n            conn.execute(\n                """\n                INSERT INTO account_sync_run(\n                    id,position_account_id,status,started_at,completed_at,\n                    is_complete,observed_at,page_count,holding_count,\n                    error_code,error_message,created_at,updated_at\n                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)\n                """,\n                (\n                    sync_run_id,\n                    account_id,\n                    "RUNNING",\n                    now,\n                    None,\n                    0,\n                    None,\n                    0,\n                    0,\n                    None,\n                    None,\n                    now,\n                    now,\n                ),\n            )\n            conn.commit()\n            return account_id, sync_run_id\n        except Exception:\n            conn.rollback()\n            raise\n        finally:\n            conn.close()\n\n    def _mark_failed(self, sync_run_id: str, *, code: str, message: str) -> None:\n        now = _now()\n        conn = self.catalog.connect()\n        try:\n            conn.execute("BEGIN IMMEDIATE")\n            conn.execute(\n                """\n                UPDATE account_sync_run\n                SET status=\'FAILED\',completed_at=?,is_complete=0,\n                    error_code=?,error_message=?,updated_at=?\n                WHERE id=? AND status=\'RUNNING\'\n                """,\n                (now, code, message[:1000], now, sync_run_id),\n            )\n            conn.commit()\n        except Exception:\n            conn.rollback()\n            raise\n        finally:\n            conn.close()\n\n    @staticmethod\n    def _validate_snapshot(balance: KisDomesticBalance) -> tuple[list[KisHolding], int]:\n        if balance.is_complete is not True:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_INCOMPLETE",\n                "KIS 잔고 Snapshot이 끝까지 완료되지 않았습니다.",\n            )\n        try:\n            page_count = int(balance.page_count)\n        except (TypeError, ValueError) as exc:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_INCOMPLETE",\n                "KIS 잔고 page_count가 올바르지 않습니다.",\n            ) from exc\n        if page_count < 1:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_INCOMPLETE",\n                "완료된 KIS 잔고 Snapshot에는 최소 1페이지가 필요합니다.",\n            )\n\n        validated: list[KisHolding] = []\n        seen: set[str] = set()\n        for item in balance.holdings:\n            ticker = str(item.ticker or "").strip()\n            if len(ticker) != 6 or not ticker.isdigit():\n                raise HoldingsKisSyncError(\n                    "HOLD_KIS_SYNC_INVALID_HOLDING",\n                    "KIS 보유 종목코드는 6자리 숫자여야 합니다.",\n                )\n            if ticker in seen:\n                raise HoldingsKisSyncError(\n                    "HOLD_KIS_SYNC_DUPLICATE_TICKER",\n                    f"KIS 잔고 Snapshot에 종목코드 {ticker}가 중복되었습니다.",\n                )\n            seen.add(ticker)\n\n            quantity = _decimal(\n                item.quantity,\n                field="quantity",\n                non_negative=True,\n            )\n            if quantity > 0:\n                _decimal(\n                    item.average_price,\n                    field="average_price",\n                    positive=True,\n                )\n            if quantity > 0:\n                validated.append(item)\n        return validated, page_count\n\n    def _existing_stock_market(self, ticker: str) -> str | None:\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT market\n                FROM monitored_stock\n                WHERE ticker=?\n                ORDER BY market\n                """,\n                (ticker,),\n            ).fetchall()\n        markets = sorted({str(row["market"]).upper() for row in rows})\n        if len(markets) > 1:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n                f"{ticker} 종목이 여러 market으로 등록되어 있어 자동 동기화할 수 없습니다.",\n            )\n        return markets[0] if markets else None\n\n    def _market_from_store(self, ticker: str) -> str:\n        if not self.market_store_db.is_file():\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n                "Market Store가 없어 신규 KIS 보유 종목의 market을 확인할 수 없습니다.",\n            )\n        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"\n        try:\n            with sqlite3.connect(uri, uri=True) as conn:\n                rows = conn.execute(\n                    """\n                    SELECT DISTINCT market\n                    FROM stock_daily\n                    WHERE stock_code=?\n                    ORDER BY market\n                    """,\n                    (ticker,),\n                ).fetchall()\n        except sqlite3.Error as exc:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n                "Market Store에서 신규 KIS 보유 종목의 market을 확인하지 못했습니다.",\n            ) from exc\n        markets = sorted(\n            {\n                str(row[0]).upper()\n                for row in rows\n                if str(row[0]).upper() in {"KOSPI", "KOSDAQ"}\n            }\n        )\n        if len(markets) != 1:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n                f"{ticker} 종목의 KOSPI/KOSDAQ market을 하나로 확정하지 못했습니다.",\n            )\n        return markets[0]\n\n    def _resolve_markets(self, holdings: list[KisHolding]) -> dict[str, str]:\n        result: dict[str, str] = {}\n        for item in holdings:\n            ticker = str(item.ticker).strip()\n            market = self._existing_stock_market(ticker)\n            result[ticker] = market or self._market_from_store(ticker)\n        return result\n\n    @staticmethod\n    def _insert_event(\n        conn: sqlite3.Connection,\n        *,\n        position_id: str,\n        event_type: str,\n        before_quantity: Decimal,\n        after_quantity: Decimal,\n        before_average_price: Decimal | None,\n        after_average_price: Decimal | None,\n        observed_at: str,\n        sync_run_id: str,\n        note: str,\n    ) -> None:\n        if event_type not in {"BALANCE_OBSERVED", "RECONCILED"}:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n                "KIS 잔고 동기화는 거래 Event를 생성할 수 없습니다.",\n            )\n        now = _now()\n        conn.execute(\n            """\n            INSERT INTO holding_position_event(\n                id,position_id,event_type,quantity_delta,unit_price,\n                before_quantity,after_quantity,before_average_price,\n                after_average_price,observed_at,effective_at,\n                analysis_revision_id,account_sync_run_id,\n                external_event_key,note,created_at\n            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\n            """,\n            (\n                str(uuid4()),\n                position_id,\n                event_type,\n                _decimal_text(after_quantity - before_quantity),\n                None,\n                _decimal_text(before_quantity),\n                _decimal_text(after_quantity),\n                _decimal_text(before_average_price)\n                if before_average_price is not None\n                else None,\n                _decimal_text(after_average_price)\n                if after_average_price is not None\n                else None,\n                observed_at,\n                observed_at,\n                None,\n                sync_run_id,\n                None,\n                note,\n                now,\n            ),\n        )\n\n    @staticmethod\n    def _position_values(row: sqlite3.Row) -> tuple[Decimal, Decimal | None]:\n        quantity = _decimal(\n            row["current_quantity"],\n            field="stored_quantity",\n            non_negative=True,\n        )\n        average = (\n            None\n            if row["current_average_price"] is None\n            else _decimal(\n                row["current_average_price"],\n                field="stored_average_price",\n                positive=True,\n            )\n        )\n        if quantity > 0 and average is None:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n                "기존 KIS Position의 평균단가가 비어 있습니다.",\n            )\n        return quantity, average\n\n    def _apply_complete_snapshot(\n        self,\n        *,\n        account_id: str,\n        sync_run_id: str,\n        holdings: list[KisHolding],\n        page_count: int,\n        markets: dict[str, str],\n        observed_at: str,\n    ) -> KisAccountSyncResult:\n        conn = self.catalog.connect()\n        created = 0\n        reconciled = 0\n        closed = 0\n        unchanged = 0\n        desired_stock_ids: set[str] = set()\n        now = _now()\n\n        try:\n            conn.execute("BEGIN IMMEDIATE")\n            sync_row = conn.execute(\n                "SELECT status FROM account_sync_run WHERE id=? AND position_account_id=?",\n                (sync_run_id, account_id),\n            ).fetchone()\n            if sync_row is None or str(sync_row["status"]) != "RUNNING":\n                raise HoldingsKisSyncError(\n                    "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n                    "RUNNING 상태의 KIS Sync Run을 찾을 수 없습니다.",\n                )\n\n            for item in sorted(holdings, key=lambda value: value.ticker):\n                ticker = str(item.ticker).strip()\n                market = markets[ticker]\n                rows = conn.execute(\n                    "SELECT * FROM monitored_stock WHERE ticker=? ORDER BY market",\n                    (ticker,),\n                ).fetchall()\n                if len(rows) > 1:\n                    raise HoldingsKisSyncError(\n                        "HOLD_KIS_SYNC_MARKET_UNRESOLVED",\n                        f"{ticker} 종목이 여러 market으로 등록되어 있습니다.",\n                    )\n                if rows:\n                    stock = rows[0]\n                else:\n                    stock_id = str(uuid4())\n                    conn.execute(\n                        """\n                        INSERT INTO monitored_stock(\n                            id,market,ticker,name,watch_enabled,archived_at,\n                            created_at,updated_at\n                        ) VALUES(?,?,?,?,?,?,?,?)\n                        """,\n                        (\n                            stock_id,\n                            market,\n                            ticker,\n                            str(item.name or "").strip() or ticker,\n                            0,\n                            None,\n                            now,\n                            now,\n                        ),\n                    )\n                    stock = conn.execute(\n                        "SELECT * FROM monitored_stock WHERE id=?",\n                        (stock_id,),\n                    ).fetchone()\n\n                stock_id = str(stock["id"])\n                desired_stock_ids.add(stock_id)\n                quantity = _decimal(\n                    item.quantity,\n                    field="quantity",\n                    positive=True,\n                )\n                average = _decimal(\n                    item.average_price,\n                    field="average_price",\n                    positive=True,\n                )\n                cost_basis = quantity * average\n\n                position = conn.execute(\n                    """\n                    SELECT * FROM holding_position\n                    WHERE monitored_stock_id=? AND position_account_id=?\n                      AND status=\'OPEN\'\n                    """,\n                    (stock_id, account_id),\n                ).fetchone()\n\n                if position is None:\n                    position_id = str(uuid4())\n                    conn.execute(\n                        """\n                        INSERT INTO holding_position(\n                            id,monitored_stock_id,position_account_id,status,\n                            opened_at,closed_at,current_quantity,current_average_price,\n                            current_cost_basis,opened_reason,last_observed_at,\n                            last_sync_run_id,created_at,updated_at\n                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)\n                        """,\n                        (\n                            position_id,\n                            stock_id,\n                            account_id,\n                            "OPEN",\n                            observed_at,\n                            None,\n                            _decimal_text(quantity),\n                            _decimal_text(average),\n                            _decimal_text(cost_basis),\n                            "KIS_OBSERVED",\n                            observed_at,\n                            sync_run_id,\n                            now,\n                            now,\n                        ),\n                    )\n                    self._insert_event(\n                        conn,\n                        position_id=position_id,\n                        event_type="BALANCE_OBSERVED",\n                        before_quantity=Decimal("0"),\n                        after_quantity=quantity,\n                        before_average_price=None,\n                        after_average_price=average,\n                        observed_at=observed_at,\n                        sync_run_id=sync_run_id,\n                        note="KIS complete balance snapshot first observation",\n                    )\n                    created += 1\n                    continue\n\n                before_quantity, before_average = self._position_values(position)\n                changed = before_quantity != quantity or before_average != average\n                conn.execute(\n                    """\n                    UPDATE holding_position\n                    SET current_quantity=?,current_average_price=?,\n                        current_cost_basis=?,last_observed_at=?,\n                        last_sync_run_id=?,updated_at=?\n                    WHERE id=? AND status=\'OPEN\'\n                    """,\n                    (\n                        _decimal_text(quantity),\n                        _decimal_text(average),\n                        _decimal_text(cost_basis),\n                        observed_at,\n                        sync_run_id,\n                        now,\n                        str(position["id"]),\n                    ),\n                )\n                if changed:\n                    self._insert_event(\n                        conn,\n                        position_id=str(position["id"]),\n                        event_type="RECONCILED",\n                        before_quantity=before_quantity,\n                        after_quantity=quantity,\n                        before_average_price=before_average,\n                        after_average_price=average,\n                        observed_at=observed_at,\n                        sync_run_id=sync_run_id,\n                        note="KIS complete balance snapshot reconciliation",\n                    )\n                    reconciled += 1\n                else:\n                    unchanged += 1\n\n            open_rows = conn.execute(\n                """\n                SELECT * FROM holding_position\n                WHERE position_account_id=? AND status=\'OPEN\'\n                """,\n                (account_id,),\n            ).fetchall()\n            for position in open_rows:\n                stock_id = str(position["monitored_stock_id"])\n                if stock_id in desired_stock_ids:\n                    continue\n                before_quantity, before_average = self._position_values(position)\n                conn.execute(\n                    """\n                    UPDATE holding_position\n                    SET status=\'CLOSED\',closed_at=?,current_quantity=\'0\',\n                        current_cost_basis=\'0\',last_observed_at=?,\n                        last_sync_run_id=?,updated_at=?\n                    WHERE id=? AND status=\'OPEN\'\n                    """,\n                    (\n                        observed_at,\n                        observed_at,\n                        sync_run_id,\n                        now,\n                        str(position["id"]),\n                    ),\n                )\n                self._insert_event(\n                    conn,\n                    position_id=str(position["id"]),\n                    event_type="RECONCILED",\n                    before_quantity=before_quantity,\n                    after_quantity=Decimal("0"),\n                    before_average_price=before_average,\n                    after_average_price=before_average,\n                    observed_at=observed_at,\n                    sync_run_id=sync_run_id,\n                    note="KIS complete balance snapshot no longer contains this holding",\n                )\n                closed += 1\n\n            cursor = conn.execute(\n                """\n                UPDATE account_sync_run\n                SET status=\'COMPLETED\',completed_at=?,is_complete=1,\n                    observed_at=?,page_count=?,holding_count=?,\n                    error_code=NULL,error_message=NULL,updated_at=?\n                WHERE id=? AND status=\'RUNNING\'\n                """,\n                (\n                    now,\n                    observed_at,\n                    page_count,\n                    len(holdings),\n                    now,\n                    sync_run_id,\n                ),\n            )\n            if cursor.rowcount != 1:\n                raise HoldingsKisSyncError(\n                    "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n                    "KIS Sync Run 완료 상태를 원자적으로 저장하지 못했습니다.",\n                )\n            conn.commit()\n        except Exception:\n            conn.rollback()\n            raise\n        finally:\n            conn.close()\n\n        return KisAccountSyncResult(\n            sync_run_id=sync_run_id,\n            account_id=account_id,\n            status="COMPLETED",\n            observed_at=observed_at,\n            page_count=page_count,\n            holding_count=len(holdings),\n            created_positions=created,\n            reconciled_positions=reconciled,\n            closed_positions=closed,\n            unchanged_positions=unchanged,\n        )\n\n    def sync(self) -> KisAccountSyncResult:\n        try:\n            settings = validate_account_settings(self.settings or get_settings())\n        except KisConfigurationError as exc:\n            raise HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_CONFIGURATION_ERROR",\n                "KIS 계좌 설정이 올바르지 않습니다.",\n            ) from exc\n\n        account_id, sync_run_id = self._start_sync(settings)\n\n        try:\n            balance = self.balance_reader(settings)\n        except Exception as exc:\n            error = HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_BALANCE_FAILED",\n                f"KIS 잔고 조회에 실패했습니다: {exc}",\n            )\n            self._mark_failed(sync_run_id, code=error.code, message=error.message)\n            raise error from exc\n\n        try:\n            holdings, page_count = self._validate_snapshot(balance)\n            markets = self._resolve_markets(holdings)\n            observed_at = _now()\n            return self._apply_complete_snapshot(\n                account_id=account_id,\n                sync_run_id=sync_run_id,\n                holdings=holdings,\n                page_count=page_count,\n                markets=markets,\n                observed_at=observed_at,\n            )\n        except HoldingsKisSyncError as exc:\n            self._mark_failed(sync_run_id, code=exc.code, message=exc.message)\n            raise\n        except Exception as exc:\n            error = HoldingsKisSyncError(\n                "HOLD_KIS_SYNC_STORAGE_CONFLICT",\n                f"KIS 잔고를 StockScope Position에 반영하지 못했습니다: {exc}",\n            )\n            self._mark_failed(sync_run_id, code=error.code, message=error.message)\n            raise error from exc\n\n\ndef sync_configured_kis_account(\n    *,\n    catalog: HoldingsCatalog | None = None,\n    market_store_db: Path | None = None,\n) -> KisAccountSyncResult:\n    target_catalog = catalog or HoldingsCatalog()\n    if catalog is None:\n        target_catalog.initialize()\n    return KisAccountSyncService(\n        target_catalog,\n        market_store_db=market_store_db,\n    ).sync()\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport sqlite3\nfrom decimal import Decimal\nfrom pathlib import Path\n\nimport httpx\nimport pytest\n\nfrom app.core.config import Settings\nfrom app.holdings import HoldingsCatalog, account_fingerprint\nfrom app.holdings.kis_sync import (\n    HoldingsKisSyncError,\n    KisAccountSyncService,\n)\nfrom app.integrations.kis.account import (\n    KisAccountError,\n    KisDomesticBalance,\n    KisHolding,\n    inquire_domestic_balance,\n)\n\n\ndef _settings(**overrides) -> Settings:\n    values = {\n        "kis_app_key": "app-key",\n        "kis_app_secret": "app-secret",\n        "kis_account_no": "12345678",\n        "kis_account_product_code": "01",\n        "kis_env": "real",\n    }\n    values.update(overrides)\n    return Settings(_env_file=None, **values)\n\n\ndef _holding(\n    ticker: str = "005930",\n    *,\n    name: str = "삼성전자",\n    quantity: str = "10",\n    average_price: str = "70000",\n) -> KisHolding:\n    qty = Decimal(quantity)\n    avg = Decimal(average_price)\n    return KisHolding(\n        ticker=ticker,\n        name=name,\n        quantity=qty,\n        orderable_quantity=qty,\n        average_price=avg,\n        purchase_amount=qty * avg,\n        current_price=Decimal("80000"),\n        evaluation_amount=qty * Decimal("80000"),\n        pnl_amount=Decimal("0"),\n        pnl_rate=Decimal("0"),\n    )\n\n\ndef _balance(*holdings: KisHolding, complete: bool = True, pages: int = 1):\n    return KisDomesticBalance(\n        holdings=tuple(holdings),\n        summary=None,\n        page_count=pages,\n        is_complete=complete,\n    )\n\n\ndef _market_store(path: Path, rows=(("KOSPI", "005930"), ("KOSPI", "000660"))):\n    with sqlite3.connect(path) as conn:\n        conn.execute(\n            """\n            CREATE TABLE stock_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                stock_code TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,stock_code)\n            )\n            """\n        )\n        for market, ticker in rows:\n            conn.execute(\n                "INSERT INTO stock_daily VALUES(?,?,?,?)",\n                (market, "20260918", ticker, "{}"),\n            )\n\n\n@pytest.fixture()\ndef env(tmp_path):\n    catalog = HoldingsCatalog(tmp_path / "holdings.db")\n    catalog.initialize()\n    market_db = tmp_path / "market_history.db"\n    _market_store(market_db)\n    return catalog, market_db\n\n\ndef _service(catalog, market_db, balance_or_reader):\n    reader = (\n        balance_or_reader\n        if callable(balance_or_reader)\n        else lambda settings: balance_or_reader\n    )\n    return KisAccountSyncService(\n        catalog,\n        settings=_settings(),\n        market_store_db=market_db,\n        balance_reader=reader,\n    )\n\n\ndef _events(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        return conn.execute(\n            "SELECT * FROM holding_position_event ORDER BY created_at,id"\n        ).fetchall()\n\n\ndef _sync_runs(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        return conn.execute(\n            "SELECT * FROM account_sync_run ORDER BY created_at,id"\n        ).fetchall()\n\n\ndef _open_positions(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        return conn.execute(\n            """\n            SELECT p.*,s.ticker,s.watch_enabled\n            FROM holding_position p\n            JOIN monitored_stock s ON s.id=p.monitored_stock_id\n            WHERE p.status=\'OPEN\'\n            ORDER BY s.ticker\n            """\n        ).fetchall()\n\n\ndef _all_positions(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        return conn.execute(\n            """\n            SELECT p.*,s.ticker,s.watch_enabled\n            FROM holding_position p\n            JOIN monitored_stock s ON s.id=p.monitored_stock_id\n            ORDER BY p.created_at,p.id\n            """\n        ).fetchall()\n\n\ndef _schema(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        rows = conn.execute(\n            """\n            SELECT type,name,sql FROM sqlite_master\n            WHERE type IN (\'table\',\'index\',\'trigger\')\n            ORDER BY type,name\n            """\n        ).fetchall()\n    return [(row["type"], row["name"], row["sql"]) for row in rows]\n\n\ndef test_kis_balance_strict_critical_fields_and_completeness_metadata():\n    def handler(request: httpx.Request) -> httpx.Response:\n        return httpx.Response(\n            200,\n            headers={"tr_cont": ""},\n            json={\n                "rt_cd": "0",\n                "output1": [\n                    {\n                        "pdno": "005930",\n                        "prdt_name": "삼성전자",\n                        "hldg_qty": "10",\n                        "ord_psbl_qty": "10",\n                        "pchs_avg_pric": "70000",\n                        "pchs_amt": "700000",\n                        "prpr": "80000",\n                        "evlu_amt": "800000",\n                        "evlu_pfls_amt": "100000",\n                        "evlu_pfls_rt": "14.2",\n                    }\n                ],\n                "output2": [],\n                "ctx_area_fk100": "",\n                "ctx_area_nk100": "",\n            },\n        )\n\n    with httpx.Client(transport=httpx.MockTransport(handler)) as client:\n        result = inquire_domestic_balance(\n            _settings(),\n            access_token="test-token",\n            http_client=client,\n        )\n    assert result.page_count == 1\n    assert result.is_complete is True\n    assert result.holdings[0].quantity == Decimal("10")\n\n    for field, bad in (("hldg_qty", "bad"), ("pchs_avg_pric", "bad")):\n        def bad_handler(request: httpx.Request, field=field, bad=bad):\n            row = {\n                "pdno": "005930",\n                "prdt_name": "삼성전자",\n                "hldg_qty": "10",\n                "pchs_avg_pric": "70000",\n            }\n            row[field] = bad\n            return httpx.Response(\n                200,\n                headers={"tr_cont": ""},\n                json={\n                    "rt_cd": "0",\n                    "output1": [row],\n                    "output2": [],\n                    "ctx_area_fk100": "",\n                    "ctx_area_nk100": "",\n                },\n            )\n\n        with httpx.Client(transport=httpx.MockTransport(bad_handler)) as client:\n            with pytest.raises(KisAccountError):\n                inquire_domestic_balance(\n                    _settings(),\n                    access_token="test-token",\n                    http_client=client,\n                )\n\n\ndef test_pagination_failure_never_returns_partial_snapshot():\n    calls = {"count": 0}\n\n    def handler(request: httpx.Request) -> httpx.Response:\n        calls["count"] += 1\n        if calls["count"] == 1:\n            return httpx.Response(\n                200,\n                headers={"tr_cont": "M"},\n                json={\n                    "rt_cd": "0",\n                    "output1": [\n                        {\n                            "pdno": "005930",\n                            "prdt_name": "삼성전자",\n                            "hldg_qty": "10",\n                            "pchs_avg_pric": "70000",\n                        }\n                    ],\n                    "output2": [],\n                    "ctx_area_fk100": "NEXT",\n                    "ctx_area_nk100": "NEXT",\n                },\n            )\n        return httpx.Response(\n            200,\n            headers={"tr_cont": ""},\n            json={\n                "rt_cd": "1",\n                "msg_cd": "TEST_FAIL",\n                "msg1": "second page failed",\n                "output1": [],\n                "output2": [],\n            },\n        )\n\n    with httpx.Client(transport=httpx.MockTransport(handler)) as client:\n        with pytest.raises(KisAccountError):\n            inquire_domestic_balance(\n                _settings(),\n                access_token="test-token",\n                http_client=client,\n            )\n    assert calls["count"] == 2\n\n\ndef test_first_observation_and_same_snapshot_are_idempotent(env):\n    catalog, market_db = env\n    service = _service(catalog, market_db, _balance(_holding()))\n\n    first = service.sync()\n    assert first.status == "COMPLETED"\n    assert first.created_positions == 1\n    positions = _open_positions(catalog)\n    assert len(positions) == 1\n    assert positions[0]["ticker"] == "005930"\n    assert positions[0]["current_quantity"] == "10"\n    assert positions[0]["current_average_price"] == "70000"\n    assert positions[0]["opened_reason"] == "KIS_OBSERVED"\n    assert positions[0]["watch_enabled"] == 0\n    assert [row["event_type"] for row in _events(catalog)] == ["BALANCE_OBSERVED"]\n\n    second = service.sync()\n    assert second.created_positions == 0\n    assert second.reconciled_positions == 0\n    assert second.unchanged_positions == 1\n    assert len(_events(catalog)) == 1\n    runs = _sync_runs(catalog)\n    assert [row["status"] for row in runs] == ["COMPLETED", "COMPLETED"]\n    assert all(row["is_complete"] == 1 for row in runs)\n\n\ndef test_quantity_and_average_changes_are_reconciled_not_trades(env):\n    catalog, market_db = env\n    _service(catalog, market_db, _balance(_holding())).sync()\n\n    changed = _service(\n        catalog,\n        market_db,\n        _balance(_holding(quantity="15", average_price="73333")),\n    ).sync()\n    assert changed.reconciled_positions == 1\n\n    lower = _service(\n        catalog,\n        market_db,\n        _balance(_holding(quantity="8", average_price="73333")),\n    ).sync()\n    assert lower.reconciled_positions == 1\n\n    average_only = _service(\n        catalog,\n        market_db,\n        _balance(_holding(quantity="8", average_price="73000")),\n    ).sync()\n    assert average_only.reconciled_positions == 1\n\n    event_types = [row["event_type"] for row in _events(catalog)]\n    assert event_types == [\n        "BALANCE_OBSERVED",\n        "RECONCILED",\n        "RECONCILED",\n        "RECONCILED",\n    ]\n    assert not ({"BUY", "SELL", "CORRECTION"} & set(event_types))\n\n\ndef test_complete_absence_closes_and_reappearance_opens_new_episode(env):\n    catalog, market_db = env\n    first = _service(catalog, market_db, _balance(_holding())).sync()\n    assert first.created_positions == 1\n\n    closed = _service(catalog, market_db, _balance()).sync()\n    assert closed.closed_positions == 1\n    positions = _all_positions(catalog)\n    assert len(positions) == 1\n    assert positions[0]["status"] == "CLOSED"\n    assert positions[0]["current_quantity"] == "0"\n    assert positions[0]["current_cost_basis"] == "0"\n    assert _events(catalog)[-1]["event_type"] == "RECONCILED"\n\n    reopened = _service(catalog, market_db, _balance(_holding())).sync()\n    assert reopened.created_positions == 1\n    positions = _all_positions(catalog)\n    assert len(positions) == 2\n    assert [row["status"] for row in positions] == ["CLOSED", "OPEN"]\n\n\ndef test_failed_or_incomplete_snapshot_never_changes_positions(env):\n    catalog, market_db = env\n    _service(catalog, market_db, _balance(_holding())).sync()\n    before = _all_positions(catalog)\n    before_events = list(_events(catalog))\n\n    incomplete_service = _service(\n        catalog,\n        market_db,\n        _balance(complete=False, pages=1),\n    )\n    with pytest.raises(HoldingsKisSyncError) as exc_info:\n        incomplete_service.sync()\n    assert exc_info.value.code == "HOLD_KIS_SYNC_INCOMPLETE"\n    assert _all_positions(catalog) == before\n    assert list(_events(catalog)) == before_events\n    assert _sync_runs(catalog)[-1]["status"] == "FAILED"\n\n    def failed_reader(settings):\n        raise KisAccountError("network/page failure", code="TEST")\n\n    with pytest.raises(HoldingsKisSyncError) as exc_info:\n        _service(catalog, market_db, failed_reader).sync()\n    assert exc_info.value.code == "HOLD_KIS_SYNC_BALANCE_FAILED"\n    assert _all_positions(catalog) == before\n    assert list(_events(catalog)) == before_events\n    assert _sync_runs(catalog)[-1]["status"] == "FAILED"\n\n\ndef test_duplicate_invalid_and_unknown_market_snapshots_fail_without_apply(env, tmp_path):\n    catalog, market_db = env\n\n    duplicate = _balance(_holding(), _holding())\n    with pytest.raises(HoldingsKisSyncError) as dup_exc:\n        _service(catalog, market_db, duplicate).sync()\n    assert dup_exc.value.code == "HOLD_KIS_SYNC_DUPLICATE_TICKER"\n    assert _open_positions(catalog) == []\n\n    invalid = _holding()\n    object.__setattr__(invalid, "quantity", Decimal("NaN"))\n    with pytest.raises(HoldingsKisSyncError) as invalid_exc:\n        _service(catalog, market_db, _balance(invalid)).sync()\n    assert invalid_exc.value.code == "HOLD_KIS_SYNC_INVALID_HOLDING"\n    assert _open_positions(catalog) == []\n\n    unknown = _holding("123456", name="미확인종목")\n    with pytest.raises(HoldingsKisSyncError) as market_exc:\n        _service(catalog, market_db, _balance(unknown)).sync()\n    assert market_exc.value.code == "HOLD_KIS_SYNC_MARKET_UNRESOLVED"\n    assert _open_positions(catalog) == []\n\n\ndef test_existing_watch_intent_is_preserved(env):\n    catalog, market_db = env\n    stock = catalog.create_monitored_stock(\n        market="KOSPI",\n        ticker="005930",\n        name="삼성전자",\n        watch_enabled=True,\n    )\n    _service(catalog, market_db, _balance(_holding())).sync()\n    assert catalog.get_monitored_stock(stock.id).watch_enabled is True\n\n    _service(catalog, market_db, _balance()).sync()\n    assert catalog.get_monitored_stock(stock.id).watch_enabled is True\n\n\ndef test_raw_account_number_is_not_persisted_and_account_is_reused(env):\n    catalog, market_db = env\n    service = _service(catalog, market_db, _balance())\n    first = service.sync()\n    second = service.sync()\n    assert first.account_id == second.account_id\n    assert b"12345678" not in catalog.db_path.read_bytes()\n\n    with catalog.connection() as conn:\n        account = conn.execute(\n            "SELECT * FROM position_account WHERE id=?",\n            (first.account_id,),\n        ).fetchone()\n    expected = account_fingerprint(\n        provider="KIS",\n        broker_environment="REAL",\n        account_number="12345678",\n        product_code="01",\n    )\n    assert account["account_kind"] == "BROKER"\n    assert account["external_account_fingerprint"] == expected\n\n\ndef test_reconciliation_is_atomic_and_failed_run_is_preserved(env, monkeypatch):\n    catalog, market_db = env\n    _service(catalog, market_db, _balance(_holding())).sync()\n    before = _all_positions(catalog)\n    before_events = list(_events(catalog))\n\n    service = _service(\n        catalog,\n        market_db,\n        _balance(_holding(quantity="20", average_price="75000")),\n    )\n\n    def fail_event(*args, **kwargs):\n        raise RuntimeError("forced event failure")\n\n    monkeypatch.setattr(service, "_insert_event", fail_event)\n    with pytest.raises(HoldingsKisSyncError) as exc_info:\n        service.sync()\n    assert exc_info.value.code == "HOLD_KIS_SYNC_STORAGE_CONFLICT"\n    assert _all_positions(catalog) == before\n    assert list(_events(catalog)) == before_events\n    assert _sync_runs(catalog)[-1]["status"] == "FAILED"\n    assert _sync_runs(catalog)[-1]["is_complete"] == 0\n\n\ndef test_schema_unchanged_and_sync_has_no_trade_or_analysis_dependency(env):\n    catalog, market_db = env\n    before = _schema(catalog)\n    _service(catalog, market_db, _balance(_holding())).sync()\n    after = _schema(catalog)\n    assert after == before\n\n    source = Path("backend/app/holdings/kis_sync.py").read_text(encoding="utf-8")\n    assert "record_buy(" not in source\n    assert "record_sell(" not in source\n    assert "record_correction(" not in source\n    assert "current_price" not in source\n    assert "app.backtest" not in source\n'
INIT_APPEND = '\nfrom .kis_sync import (\n    HoldingsKisSyncError,\n    KisAccountSyncResult,\n    KisAccountSyncService,\n    sync_configured_kis_account,\n)\n\n__all__.extend(\n    [\n        "HoldingsKisSyncError",\n        "KisAccountSyncResult",\n        "KisAccountSyncService",\n        "sync_configured_kis_account",\n    ]\n)\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        item for item in path.rglob("*.py")
        if "__pycache__" not in item.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_kis_account(text: str) -> str:
    if "page_count: int" in text or "is_complete: bool" in text:
        fail("KIS account.py already appears to contain HOLD.1-D completeness metadata.")

    old_dataclass = """@dataclass(frozen=True, slots=True)
class KisDomesticBalance:
    holdings: tuple[KisHolding, ...]
    summary: KisBalanceSummary | None
"""
    new_dataclass = """@dataclass(frozen=True, slots=True)
class KisDomesticBalance:
    holdings: tuple[KisHolding, ...]
    summary: KisBalanceSummary | None
    page_count: int
    is_complete: bool
"""
    if text.count(old_dataclass) != 1:
        fail("KisDomesticBalance dataclass anchor not found exactly once.")
    text = text.replace(old_dataclass, new_dataclass, 1)

    pattern = re.compile(
        r"def _holding_from_row\(row: dict\[str, Any\]\) -> KisHolding:\n.*?\n\n\ndef _summary_from_row",
        re.DOTALL,
    )
    replacement = """def _required_decimal(
    row: dict[str, Any],
    field: str,
    *,
    non_negative: bool = False,
    positive: bool = False,
) -> Decimal:
    raw = row.get(field)
    if raw is None or str(raw).strip() == "":
        raise KisAccountError(f"KIS balance holding is missing required field: {field}")
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KisAccountError(
            f"KIS balance holding field {field} is not a valid number."
        ) from exc
    if not value.is_finite():
        raise KisAccountError(f"KIS balance holding field {field} is not finite.")
    if positive and value <= 0:
        raise KisAccountError(
            f"KIS balance holding field {field} must be greater than zero."
        )
    if non_negative and value < 0:
        raise KisAccountError(
            f"KIS balance holding field {field} must not be negative."
        )
    return value


def _holding_from_row(row: dict[str, Any]) -> KisHolding | None:
    ticker = str(row.get("pdno") or "").strip()
    raw_quantity = row.get("hldg_qty")
    if not ticker:
        # KIS may include a blank placeholder row. It is safe to ignore only when
        # the row also does not claim a positive/meaningful holding quantity.
        if raw_quantity in (None, "", "0", "0.0", 0):
            return None
        raise KisAccountError("KIS balance holding is missing required ticker.")
    if len(ticker) != 6 or not ticker.isdigit():
        raise KisAccountError("KIS balance holding ticker must be exactly 6 digits.")

    quantity = _required_decimal(
        row,
        "hldg_qty",
        non_negative=True,
    )
    average_price = (
        _required_decimal(row, "pchs_avg_pric", positive=True)
        if quantity > 0
        else _dec(row.get("pchs_avg_pric"))
    )

    return KisHolding(
        ticker=ticker,
        name=str(row.get("prdt_name") or "").strip(),
        quantity=quantity,
        orderable_quantity=_dec(row.get("ord_psbl_qty")),
        average_price=average_price,
        purchase_amount=_dec(row.get("pchs_amt")),
        current_price=_dec(row.get("prpr")),
        evaluation_amount=_dec(row.get("evlu_amt")),
        pnl_amount=_dec(row.get("evlu_pfls_amt")),
        pnl_rate=_dec(row.get("evlu_pfls_rt") or row.get("evlu_erng_rt")),
    )


def _summary_from_row"""
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        fail("KIS _holding_from_row block was not found exactly once.")

    old_loop = """                item = _holding_from_row(raw)
                if not item.ticker:
                    continue
                if not include_zero_quantity and item.quantity <= 0:
"""
    new_loop = """                item = _holding_from_row(raw)
                if item is None:
                    continue
                if not include_zero_quantity and item.quantity <= 0:
"""
    if text.count(old_loop) != 1:
        fail("KIS holding parse loop anchor not found exactly once.")
    text = text.replace(old_loop, new_loop, 1)

    if text.count("    page = 0\n") != 1:
        fail("KIS pagination counter anchor not found exactly once.")
    text = text.replace("    page = 0\n", "    page_count = 0\n", 1)

    rows_anchor = '            rows = body.get("output1") or []\n'
    if text.count(rows_anchor) != 1:
        fail("KIS output1 anchor not found exactly once.")
    text = text.replace(
        rows_anchor,
        """            page_count += 1
            if page_count > 11:
                raise KisAccountError("KIS balance pagination exceeded the safety limit.")

            rows = body.get("output1") or []
""",
        1,
    )

    old_page_guard = """            page += 1
            if page > 10:
                raise KisAccountError("KIS balance pagination exceeded the safety limit.")

"""
    if text.count(old_page_guard) != 1:
        fail("Legacy KIS page guard anchor not found exactly once.")
    text = text.replace(old_page_guard, "", 1)

    old_return = "    return KisDomesticBalance(holdings=tuple(holdings), summary=summary)\n"
    new_return = """    return KisDomesticBalance(
        holdings=tuple(holdings),
        summary=summary,
        page_count=page_count,
        is_complete=True,
    )
"""
    if text.count(old_return) != 1:
        fail("KisDomesticBalance return anchor not found exactly once.")
    text = text.replace(old_return, new_return, 1)
    return text


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-D KIS Account Sync")
    print("Mode: read-only KIS balance -> StockScope reconciliation")
    print("Order API called: NO")
    print("BUY/SELL inferred from balance: NO")
    print("DB schema change: NO")

    required = [
        CATALOG,
        DOMAIN,
        ANALYSIS,
        LIFECYCLE,
        HOLDINGS_INIT,
        KIS_ACCOUNT,
        KIS_CLIENT,
        KIS_TOKEN_CACHE,
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    for target in (KIS_SYNC, TEST):
        if target.exists():
            fail(f"Target already exists: {target}")

    catalog_text = CATALOG.read_text(encoding="utf-8-sig")
    for marker in (
        "def connection(self)",
        "CREATE TABLE IF NOT EXISTS account_sync_run (",
        "CREATE TABLE IF NOT EXISTS holding_position (",
        "CREATE TABLE IF NOT EXISTS holding_position_event (",
    ):
        if marker not in catalog_text:
            print()
            print("D.0 SOURCE AUDIT: STOP")
            print("Unexpected HOLD catalog structure; no files were changed.")
            print("Missing marker:", marker)
            return 2

    account_before = KIS_ACCOUNT.read_text(encoding="utf-8-sig")
    holdings_init_before = HOLDINGS_INIT.read_text(encoding="utf-8-sig")
    account_after = patch_kis_account(account_before)

    compile(account_after, str(KIS_ACCOUNT), "exec")
    compile(KIS_SYNC_CONTENT, str(KIS_SYNC), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    protected = {
        "catalog": sha256(CATALOG),
        "domain": sha256(DOMAIN),
        "analysis": sha256(ANALYSIS),
        "lifecycle": sha256(LIFECYCLE),
        "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
        "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
        "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
        "kis_client": sha256(KIS_CLIENT),
        "kis_token_cache": sha256(KIS_TOKEN_CACHE),
        "kis_quote": sha256(KIS_QUOTE) if KIS_QUOTE.is_file() else "MISSING",
        "kis_websocket": sha256(KIS_WEBSOCKET) if KIS_WEBSOCKET.is_file() else "MISSING",
    }

    created: list[Path] = []
    init_changed = False
    account_changed = False
    local_tests_passed = False

    try:
        KIS_ACCOUNT.write_text(account_after, encoding="utf-8", newline="\n")
        account_changed = True

        KIS_SYNC.write_text(KIS_SYNC_CONTENT, encoding="utf-8", newline="\n")
        created.append(KIS_SYNC)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        if "from .kis_sync import (" in holdings_init_before:
            fail("holdings/__init__.py already contains HOLD.1-D exports.")
        HOLDINGS_INIT.write_text(
            holdings_init_before.rstrip() + "\n" + INIT_APPEND.lstrip(),
            encoding="utf-8",
            newline="\n",
        )
        init_changed = True

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(
            venv_python if venv_python.is_file() else Path(sys.executable)
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_kis_sync_hold1d.py",
                "-q",
            ],
            "HOLD.1-D KIS sync tests",
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_catalog_hold1a.py",
                "backend/tests/test_holdings_analysis_hold1b.py",
                "backend/tests/test_holdings_lifecycle_hold1c.py",
                "backend/tests/test_kis_client.py",
                "backend/tests/test_kis_account.py",
                "-q",
            ],
            "HOLD.1-A/B/C + KIS account regression",
        )
        local_tests_passed = True

        after = {
            "catalog": sha256(CATALOG),
            "domain": sha256(DOMAIN),
            "analysis": sha256(ANALYSIS),
            "lifecycle": sha256(LIFECYCLE),
            "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
            "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
            "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
            "kis_client": sha256(KIS_CLIENT),
            "kis_token_cache": sha256(KIS_TOKEN_CACHE),
            "kis_quote": sha256(KIS_QUOTE) if KIS_QUOTE.is_file() else "MISSING",
            "kis_websocket": sha256(KIS_WEBSOCKET) if KIS_WEBSOCKET.is_file() else "MISSING",
        }
        changed = [key for key in protected if protected[key] != after[key]]
        if changed:
            fail("Protected source changed during HOLD.1-D: " + ", ".join(changed))

        print()
        print("=== HOLD.1-D REAL KIS READ + TEMP DB UAT ===")
        print("One read-only KIS balance sync will run against a temporary holdings DB.")
        uat_code = r"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, "backend")

from app.holdings import HoldingsCatalog, sync_configured_kis_account

with tempfile.TemporaryDirectory() as td:
    db = Path(td) / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    result = sync_configured_kis_account(catalog=catalog)
    with catalog.connection() as conn:
        event_types = [
            row["event_type"]
            for row in conn.execute(
                "SELECT event_type FROM holding_position_event ORDER BY created_at,id"
            ).fetchall()
        ]
        raw_account_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM position_account"
        ).fetchone()["cnt"]

    forbidden = sorted({"BUY", "SELL", "CORRECTION"} & set(event_types))
    assert not forbidden, forbidden
    print("KIS BALANCE READ: PASS")
    print("SYNC STATUS:", result.status)
    print("SNAPSHOT COMPLETE: YES")
    print("PAGES:", result.page_count)
    print("HOLDINGS:", result.holding_count)
    print("CREATED:", result.created_positions)
    print("RECONCILED:", result.reconciled_positions)
    print("CLOSED:", result.closed_positions)
    print("UNCHANGED:", result.unchanged_positions)
    print("POSITION_ACCOUNTS:", raw_account_count)
    print("TRADE_EVENTS_INFERRED: NO")
    print("ACTUAL HOLDINGS DB TOUCHED: NO")
    print("ORDER API CALLED: NO")
"""
        result = subprocess.run([python_exe, "-c", uat_code], cwd=ROOT)
        if result.returncode != 0:
            print()
            print("HOLD.1-D LIVE UAT: PENDING/FAILED")
            print("Local HOLD.1-D tests and regressions already passed.")
            print("Source changes are kept for diagnosis; actual holdings.db was not used.")
            print("Order API called: NO")
            return result.returncode

        print()
        print("HOLD.1-D CLOSED")
        print("Added:")
        print(" - backend/app/holdings/kis_sync.py")
        print(" - backend/tests/test_holdings_kis_sync_hold1d.py")
        print("Modified:")
        print(" - backend/app/integrations/kis/account.py (strict critical parsing + completeness metadata)")
        print(" - backend/app/holdings/__init__.py (exports only)")
        print("Complete snapshot only reconciliation: PASS")
        print("BALANCE_OBSERVED / RECONCILED only: PASS")
        print("BUY/SELL inferred: NO")
        print("Failed/incomplete snapshot preserves positions: PASS")
        print("Atomic reconciliation: PASS")
        print("Raw account number persisted: NO")
        print("DB schema changed: NO")
        print("HOLD.1-A/B/C regression: PASS")
        print("KIS client/account regression: PASS")
        print("Scanner/Strategy/Risk/Lifecycle changed: NO")
        print("Order API called: NO")
        return 0

    except Exception:
        if not local_tests_passed:
            if init_changed:
                HOLDINGS_INIT.write_text(
                    holdings_init_before,
                    encoding="utf-8",
                    newline="\n",
                )
            if account_changed:
                KIS_ACCOUNT.write_text(
                    account_before,
                    encoding="utf-8",
                    newline="\n",
                )
            for path in reversed(created):
                if path.exists():
                    path.unlink()
            print()
            print("FAILED — HOLD.1-D source changes were rolled back.")
        else:
            print()
            print("FAILED after local regression validation; source changes were kept for diagnosis.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
