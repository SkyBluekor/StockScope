from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
HOLDINGS_DIR = ROOT / "backend" / "app" / "holdings"

CATALOG = HOLDINGS_DIR / "catalog.py"
DOMAIN = HOLDINGS_DIR / "domain.py"
ANALYSIS = HOLDINGS_DIR / "analysis.py"
LIFECYCLE = HOLDINGS_DIR / "lifecycle.py"
KIS_SYNC = HOLDINGS_DIR / "kis_sync.py"
INIT = HOLDINGS_DIR / "__init__.py"
HISTORY = HOLDINGS_DIR / "analysis_history.py"
TEST = ROOT / "backend" / "tests" / "test_holdings_analysis_history_hold1e.py"

ANALYSIS_HISTORY_CONTENT = 'from __future__ import annotations\n\nimport json\nimport sqlite3\nfrom dataclasses import dataclass\nfrom datetime import datetime, timezone\nfrom decimal import Decimal\nfrom pathlib import Path\nfrom typing import Any, Callable\nfrom uuid import uuid4\n\nfrom app.core.config import PROJECT_ROOT\n\nfrom .analysis import (\n    HoldingsAnalysisError,\n    SingleStockAnalysis,\n    analyze_single_stock,\n)\nfrom .catalog import HoldingsCatalog\nfrom .domain import MonitoredStock, StockAnalysisRevision\n\n\nDEFAULT_MARKET_STORE_DB = (\n    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"\n)\n\n\nclass HoldingsAnalysisHistoryError(RuntimeError):\n    def __init__(\n        self,\n        code: str,\n        message: str,\n        *,\n        cause_code: str | None = None,\n    ) -> None:\n        super().__init__(message)\n        self.code = code\n        self.message = message\n        self.cause_code = cause_code\n\n\n@dataclass(frozen=True, slots=True)\nclass StoredAnalysisResult:\n    monitored_stock_id: str\n    analysis_day_id: str\n    revision: StockAnalysisRevision\n    created_revision: bool\n    promoted_current: bool\n\n\n@dataclass(frozen=True, slots=True)\nclass AnalysisTimelineItem:\n    market_date: str\n    analysis_day_id: str\n    revision_id: str\n    revision_no: int\n    computed_at: str\n    strategy_key: str | None\n    action_state: str | None\n    risk_state: str | None\n    reference_price: Decimal | None\n    stop_price: Decimal | None\n    target1_price: Decimal | None\n    target2_price: Decimal | None\n    previous_strategy_key: str | None\n    previous_action_state: str | None\n    previous_risk_state: str | None\n    previous_reference_price: Decimal | None\n    previous_stop_price: Decimal | None\n    previous_target1_price: Decimal | None\n    previous_target2_price: Decimal | None\n    strategy_changed: bool\n    action_changed: bool\n    risk_changed: bool\n    reference_price_changed: bool\n    stop_price_changed: bool\n    target1_price_changed: bool\n    target2_price_changed: bool\n    reference_price_delta: Decimal | None\n    stop_price_delta: Decimal | None\n    target1_price_delta: Decimal | None\n    target2_price_delta: Decimal | None\n\n\n@dataclass(frozen=True, slots=True)\nclass StockTimelineItem:\n    kind: str\n    occurred_at: str\n    market_date: str | None\n    analysis_revision_id: str | None\n    position_id: str | None\n    event_type: str | None\n    payload: dict[str, Any]\n\n\ndef _now() -> str:\n    return datetime.now(timezone.utc).isoformat()\n\n\ndef _json_text(value: Any) -> str:\n    return json.dumps(\n        value,\n        ensure_ascii=False,\n        sort_keys=True,\n        separators=(",", ":"),\n        default=str,\n    )\n\n\ndef _decimal_text(value: Decimal | float | int | str | None) -> str | None:\n    if value is None:\n        return None\n    return format(Decimal(str(value)), "f")\n\n\ndef _decimal_value(value: Any) -> Decimal | None:\n    if value is None:\n        return None\n    return Decimal(str(value))\n\n\ndef _delta(current: Decimal | None, previous: Decimal | None) -> Decimal | None:\n    if current is None or previous is None:\n        return None\n    return current - previous\n\n\ndef _sort_time(value: str) -> datetime:\n    raw = (value or "").strip()\n    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw\n    try:\n        parsed = datetime.fromisoformat(normalized)\n    except ValueError:\n        return datetime.min.replace(tzinfo=timezone.utc)\n    if parsed.tzinfo is None or parsed.utcoffset() is None:\n        return parsed.replace(tzinfo=timezone.utc)\n    return parsed.astimezone(timezone.utc)\n\n\nclass HoldingAnalysisHistoryService:\n    """Persist immutable daily HOLD analysis revisions and project timelines."""\n\n    def __init__(\n        self,\n        catalog: HoldingsCatalog,\n        *,\n        market_store_db: Path | None = None,\n        analyzer: Callable[..., SingleStockAnalysis] | None = None,\n        clock: Callable[[], str] | None = None,\n    ) -> None:\n        self.catalog = catalog\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n        self.analyzer = analyzer or analyze_single_stock\n        self.clock = clock or _now\n\n    def _stock(self, monitored_stock_id: str) -> MonitoredStock:\n        try:\n            return self.catalog.get_monitored_stock(monitored_stock_id)\n        except Exception as exc:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_STOCK_NOT_FOUND",\n                "분석 대상 종목을 찾을 수 없습니다.",\n            ) from exc\n\n    @staticmethod\n    def _reason(\n        previous: StockAnalysisRevision | None,\n        result: SingleStockAnalysis,\n    ) -> str:\n        if previous is None:\n            return "INITIAL"\n        if (\n            previous.scanner_version != result.scanner_version\n            or previous.analysis_engine_version != result.analysis_engine_version\n        ):\n            return "ENGINE_CHANGED"\n        if previous.policy_version != result.policy_version:\n            return "POLICY_CHANGED"\n        return "INPUT_CHANGED"\n\n    @staticmethod\n    def _revision_from_row(\n        catalog: HoldingsCatalog,\n        row: sqlite3.Row,\n    ) -> StockAnalysisRevision:\n        return catalog._revision_from_row(row)  # noqa: SLF001\n\n    def _store_result(\n        self,\n        *,\n        stock: MonitoredStock,\n        result: SingleStockAnalysis,\n        computed_at: str,\n    ) -> StoredAnalysisResult:\n        if result.market.upper() != stock.market.upper():\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_CONFLICT",\n                "분석 결과의 market이 관리 종목과 일치하지 않습니다.",\n            )\n        if result.ticker != stock.ticker:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_CONFLICT",\n                "분석 결과의 ticker가 관리 종목과 일치하지 않습니다.",\n            )\n\n        conn = self.catalog.connect()\n        try:\n            conn.execute("BEGIN IMMEDIATE")\n            stock_row = conn.execute(\n                "SELECT id FROM monitored_stock WHERE id=?",\n                (stock.id,),\n            ).fetchone()\n            if stock_row is None:\n                raise HoldingsAnalysisHistoryError(\n                    "HOLD_ANALYSIS_HISTORY_STOCK_NOT_FOUND",\n                    "분석 대상 종목이 저장 중 사라졌습니다.",\n                )\n\n            day = conn.execute(\n                """\n                SELECT * FROM stock_analysis_day\n                WHERE monitored_stock_id=? AND market_date=?\n                """,\n                (stock.id, result.market_date),\n            ).fetchone()\n            now = self.clock()\n            if day is None:\n                day_id = str(uuid4())\n                conn.execute(\n                    """\n                    INSERT INTO stock_analysis_day(\n                        id,monitored_stock_id,market_date,current_revision_id,\n                        created_at,updated_at\n                    ) VALUES(?,?,?,?,?,?)\n                    """,\n                    (\n                        day_id,\n                        stock.id,\n                        result.market_date,\n                        None,\n                        now,\n                        now,\n                    ),\n                )\n                day = conn.execute(\n                    "SELECT * FROM stock_analysis_day WHERE id=?",\n                    (day_id,),\n                ).fetchone()\n            else:\n                day_id = str(day["id"])\n\n            current: StockAnalysisRevision | None = None\n            if day["current_revision_id"]:\n                current_row = conn.execute(\n                    "SELECT * FROM stock_analysis_revision WHERE id=?",\n                    (day["current_revision_id"],),\n                ).fetchone()\n                if current_row is not None:\n                    current = self._revision_from_row(self.catalog, current_row)\n\n            existing = conn.execute(\n                """\n                SELECT * FROM stock_analysis_revision\n                WHERE analysis_day_id=? AND input_fingerprint=?\n                """,\n                (day_id, result.input_fingerprint),\n            ).fetchone()\n\n            created_revision = existing is None\n            if existing is None:\n                next_revision = int(\n                    conn.execute(\n                        """\n                        SELECT COALESCE(MAX(revision_no),0)+1 AS next_revision\n                        FROM stock_analysis_revision\n                        WHERE analysis_day_id=?\n                        """,\n                        (day_id,),\n                    ).fetchone()["next_revision"]\n                )\n                revision_id = str(uuid4())\n                reason = self._reason(current, result)\n                conn.execute(\n                    """\n                    INSERT INTO stock_analysis_revision(\n                        id,analysis_day_id,revision_no,input_fingerprint,\n                        strategy_key,action_state,risk_state,\n                        reference_price,stop_price,target1_price,target2_price,\n                        scanner_version,analysis_engine_version,policy_version,\n                        source_versions_json,snapshot_json,revision_reason,\n                        computed_at,created_at\n                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\n                    """,\n                    (\n                        revision_id,\n                        day_id,\n                        next_revision,\n                        result.input_fingerprint,\n                        result.strategy_key,\n                        result.action_state,\n                        result.risk_state,\n                        _decimal_text(result.reference_price),\n                        _decimal_text(result.stop_price),\n                        _decimal_text(result.target1_price),\n                        _decimal_text(result.target2_price),\n                        result.scanner_version,\n                        result.analysis_engine_version,\n                        result.policy_version,\n                        _json_text(result.source_versions),\n                        _json_text(result.snapshot),\n                        reason,\n                        computed_at,\n                        now,\n                    ),\n                )\n                existing = conn.execute(\n                    "SELECT * FROM stock_analysis_revision WHERE id=?",\n                    (revision_id,),\n                ).fetchone()\n\n            revision = self._revision_from_row(self.catalog, existing)\n            promoted_current = day["current_revision_id"] != revision.id\n            if promoted_current:\n                cursor = conn.execute(\n                    """\n                    UPDATE stock_analysis_day\n                    SET current_revision_id=?,updated_at=?\n                    WHERE id=?\n                    """,\n                    (revision.id, now, day_id),\n                )\n                if cursor.rowcount != 1:\n                    raise HoldingsAnalysisHistoryError(\n                        "HOLD_ANALYSIS_HISTORY_CONFLICT",\n                        "현재 Analysis Revision을 저장하지 못했습니다.",\n                    )\n            conn.commit()\n            return StoredAnalysisResult(\n                monitored_stock_id=stock.id,\n                analysis_day_id=day_id,\n                revision=revision,\n                created_revision=created_revision,\n                promoted_current=promoted_current,\n            )\n        except sqlite3.IntegrityError as exc:\n            conn.rollback()\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_CONFLICT",\n                "Analysis Day/Revision 저장 중 충돌이 발생했습니다.",\n            ) from exc\n        except Exception:\n            conn.rollback()\n            raise\n        finally:\n            conn.close()\n\n    def analyze_and_record(\n        self,\n        *,\n        monitored_stock_id: str,\n        market_date: str,\n    ) -> StoredAnalysisResult:\n        stock = self._stock(monitored_stock_id)\n        try:\n            result = self.analyzer(\n                market=stock.market,\n                ticker=stock.ticker,\n                market_date=market_date,\n                market_store_db=self.market_store_db,\n            )\n        except HoldingsAnalysisError as exc:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_FAILED",\n                f"종목 분석을 저장하지 못했습니다: {exc}",\n                cause_code=getattr(exc, "code", None),\n            ) from exc\n        except Exception as exc:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_FAILED",\n                f"종목 분석을 저장하지 못했습니다: {exc}",\n            ) from exc\n\n        if result.market_date != market_date:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",\n                "요청한 market_date와 실제 분석 market_date가 일치하지 않습니다.",\n            )\n        computed_at = self.clock()\n        return self._store_result(\n            stock=stock,\n            result=result,\n            computed_at=computed_at,\n        )\n\n    def latest_confirmed_market_date(\n        self,\n        monitored_stock_id: str,\n    ) -> str:\n        stock = self._stock(monitored_stock_id)\n        if not self.market_store_db.is_file():\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",\n                "Market Store를 찾을 수 없습니다.",\n            )\n        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"\n        try:\n            with sqlite3.connect(uri, uri=True) as conn:\n                row = conn.execute(\n                    """\n                    SELECT MAX(s.bas_dd)\n                    FROM stock_daily s\n                    WHERE s.market=?\n                      AND s.stock_code=?\n                      AND EXISTS (\n                          SELECT 1\n                          FROM day_status ds\n                          WHERE ds.market=s.market\n                            AND ds.bas_dd=s.bas_dd\n                            AND ds.kind=\'stock\'\n                            AND ds.status=\'data\'\n                      )\n                      AND EXISTS (\n                          SELECT 1\n                          FROM day_status di\n                          WHERE di.market=s.market\n                            AND di.bas_dd=s.bas_dd\n                            AND di.kind=\'index\'\n                            AND di.status=\'data\'\n                      )\n                    """,\n                    (stock.market, stock.ticker),\n                ).fetchone()\n        except sqlite3.Error as exc:\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",\n                "Market Store에서 최신 확정 거래일을 확인하지 못했습니다.",\n            ) from exc\n        bas_dd = str(row[0] or "") if row else ""\n        if len(bas_dd) != 8 or not bas_dd.isdigit():\n            raise HoldingsAnalysisHistoryError(\n                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",\n                "해당 종목의 확정 EOD 거래일을 찾을 수 없습니다.",\n            )\n        return f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"\n\n    def analyze_latest_confirmed(\n        self,\n        *,\n        monitored_stock_id: str,\n    ) -> StoredAnalysisResult:\n        market_date = self.latest_confirmed_market_date(monitored_stock_id)\n        return self.analyze_and_record(\n            monitored_stock_id=monitored_stock_id,\n            market_date=market_date,\n        )\n\n    def list_analysis_targets(self) -> tuple[MonitoredStock, ...]:\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT DISTINCT s.*\n                FROM monitored_stock s\n                WHERE s.archived_at IS NULL\n                  AND (\n                      s.watch_enabled=1\n                      OR EXISTS (\n                          SELECT 1\n                          FROM holding_position p\n                          WHERE p.monitored_stock_id=s.id\n                            AND p.status=\'OPEN\'\n                      )\n                  )\n                ORDER BY s.market,s.ticker\n                """\n            ).fetchall()\n        return tuple(self.catalog._stock_from_row(row) for row in rows)  # noqa: SLF001\n\n    def get_current_analysis(\n        self,\n        monitored_stock_id: str,\n    ) -> StockAnalysisRevision | None:\n        self._stock(monitored_stock_id)\n        with self.catalog.connection() as conn:\n            row = conn.execute(\n                """\n                SELECT r.*\n                FROM stock_analysis_day d\n                JOIN stock_analysis_revision r ON r.id=d.current_revision_id\n                WHERE d.monitored_stock_id=?\n                ORDER BY d.market_date DESC\n                LIMIT 1\n                """,\n                (monitored_stock_id,),\n            ).fetchone()\n        return self._revision_from_row(self.catalog, row) if row else None\n\n    def get_day_revisions(\n        self,\n        *,\n        monitored_stock_id: str,\n        market_date: str,\n    ) -> tuple[StockAnalysisRevision, ...]:\n        self._stock(monitored_stock_id)\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT r.*\n                FROM stock_analysis_day d\n                JOIN stock_analysis_revision r ON r.analysis_day_id=d.id\n                WHERE d.monitored_stock_id=? AND d.market_date=?\n                ORDER BY r.revision_no ASC\n                """,\n                (monitored_stock_id, market_date),\n            ).fetchall()\n        return tuple(self._revision_from_row(self.catalog, row) for row in rows)\n\n    def get_analysis_timeline(\n        self,\n        monitored_stock_id: str,\n        *,\n        limit: int = 30,\n    ) -> tuple[AnalysisTimelineItem, ...]:\n        self._stock(monitored_stock_id)\n        if limit <= 0:\n            return ()\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT d.id AS analysis_day_id,d.market_date,r.*\n                FROM stock_analysis_day d\n                JOIN stock_analysis_revision r ON r.id=d.current_revision_id\n                WHERE d.monitored_stock_id=?\n                ORDER BY d.market_date ASC\n                """,\n                (monitored_stock_id,),\n            ).fetchall()\n\n        items: list[AnalysisTimelineItem] = []\n        previous: sqlite3.Row | None = None\n        for row in rows:\n            current_reference = _decimal_value(row["reference_price"])\n            current_stop = _decimal_value(row["stop_price"])\n            current_target1 = _decimal_value(row["target1_price"])\n            current_target2 = _decimal_value(row["target2_price"])\n\n            previous_reference = (\n                _decimal_value(previous["reference_price"]) if previous else None\n            )\n            previous_stop = _decimal_value(previous["stop_price"]) if previous else None\n            previous_target1 = (\n                _decimal_value(previous["target1_price"]) if previous else None\n            )\n            previous_target2 = (\n                _decimal_value(previous["target2_price"]) if previous else None\n            )\n\n            items.append(\n                AnalysisTimelineItem(\n                    market_date=str(row["market_date"]),\n                    analysis_day_id=str(row["analysis_day_id"]),\n                    revision_id=str(row["id"]),\n                    revision_no=int(row["revision_no"]),\n                    computed_at=str(row["computed_at"]),\n                    strategy_key=row["strategy_key"],\n                    action_state=row["action_state"],\n                    risk_state=row["risk_state"],\n                    reference_price=current_reference,\n                    stop_price=current_stop,\n                    target1_price=current_target1,\n                    target2_price=current_target2,\n                    previous_strategy_key=previous["strategy_key"] if previous else None,\n                    previous_action_state=previous["action_state"] if previous else None,\n                    previous_risk_state=previous["risk_state"] if previous else None,\n                    previous_reference_price=previous_reference,\n                    previous_stop_price=previous_stop,\n                    previous_target1_price=previous_target1,\n                    previous_target2_price=previous_target2,\n                    strategy_changed=(\n                        previous is not None\n                        and previous["strategy_key"] != row["strategy_key"]\n                    ),\n                    action_changed=(\n                        previous is not None\n                        and previous["action_state"] != row["action_state"]\n                    ),\n                    risk_changed=(\n                        previous is not None\n                        and previous["risk_state"] != row["risk_state"]\n                    ),\n                    reference_price_changed=(\n                        previous is not None\n                        and previous_reference != current_reference\n                    ),\n                    stop_price_changed=(\n                        previous is not None and previous_stop != current_stop\n                    ),\n                    target1_price_changed=(\n                        previous is not None\n                        and previous_target1 != current_target1\n                    ),\n                    target2_price_changed=(\n                        previous is not None\n                        and previous_target2 != current_target2\n                    ),\n                    reference_price_delta=_delta(current_reference, previous_reference),\n                    stop_price_delta=_delta(current_stop, previous_stop),\n                    target1_price_delta=_delta(current_target1, previous_target1),\n                    target2_price_delta=_delta(current_target2, previous_target2),\n                )\n            )\n            previous = row\n\n        return tuple(reversed(items[-limit:]))\n\n    def get_stock_timeline(\n        self,\n        monitored_stock_id: str,\n        *,\n        limit: int = 100,\n    ) -> tuple[StockTimelineItem, ...]:\n        self._stock(monitored_stock_id)\n        if limit <= 0:\n            return ()\n\n        analysis_items = self.get_analysis_timeline(\n            monitored_stock_id,\n            limit=max(limit, 30),\n        )\n        combined: list[StockTimelineItem] = []\n        for item in analysis_items:\n            combined.append(\n                StockTimelineItem(\n                    kind="ANALYSIS",\n                    occurred_at=item.computed_at,\n                    market_date=item.market_date,\n                    analysis_revision_id=item.revision_id,\n                    position_id=None,\n                    event_type=None,\n                    payload={\n                        "revision_no": item.revision_no,\n                        "strategy_key": item.strategy_key,\n                        "action_state": item.action_state,\n                        "risk_state": item.risk_state,\n                        "reference_price": item.reference_price,\n                        "stop_price": item.stop_price,\n                        "target1_price": item.target1_price,\n                        "target2_price": item.target2_price,\n                        "strategy_changed": item.strategy_changed,\n                        "action_changed": item.action_changed,\n                        "risk_changed": item.risk_changed,\n                        "reference_price_delta": item.reference_price_delta,\n                    },\n                )\n            )\n\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT e.*\n                FROM holding_position_event e\n                JOIN holding_position p ON p.id=e.position_id\n                WHERE p.monitored_stock_id=?\n                """,\n                (monitored_stock_id,),\n            ).fetchall()\n        for row in rows:\n            occurred_at = (\n                str(row["effective_at"] or "")\n                or str(row["observed_at"] or "")\n                or str(row["created_at"])\n            )\n            combined.append(\n                StockTimelineItem(\n                    kind="POSITION_EVENT",\n                    occurred_at=occurred_at,\n                    market_date=None,\n                    analysis_revision_id=row["analysis_revision_id"],\n                    position_id=str(row["position_id"]),\n                    event_type=str(row["event_type"]),\n                    payload={\n                        "quantity_delta": _decimal_value(row["quantity_delta"]),\n                        "unit_price": _decimal_value(row["unit_price"]),\n                        "before_quantity": _decimal_value(row["before_quantity"]),\n                        "after_quantity": _decimal_value(row["after_quantity"]),\n                        "before_average_price": _decimal_value(\n                            row["before_average_price"]\n                        ),\n                        "after_average_price": _decimal_value(\n                            row["after_average_price"]\n                        ),\n                        "note": row["note"],\n                    },\n                )\n            )\n\n        combined.sort(\n            key=lambda item: (_sort_time(item.occurred_at), item.kind),\n            reverse=True,\n        )\n        return tuple(combined[:limit])\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport sqlite3\nfrom decimal import Decimal\nfrom pathlib import Path\n\nimport pytest\n\nfrom app.holdings import HoldingsCatalog\nfrom app.holdings.analysis import HoldingsAnalysisError, SingleStockAnalysis\nfrom app.holdings.analysis_history import (\n    HoldingAnalysisHistoryService,\n    HoldingsAnalysisHistoryError,\n)\nfrom app.holdings.lifecycle import PositionLifecycleService\n\n\ndef _analysis(\n    *,\n    market_date: str = "2026-09-18",\n    fingerprint: str = "fp-1",\n    strategy: str = "ma20_rebound",\n    action: str = "WATCH",\n    risk: str = "READY",\n    reference: float = 261000.0,\n    stop: float | None = 254124.8,\n    target1: float | None = 271000.0,\n    target2: float | None = 274750.4,\n    scanner_version: str = "0.21.3.7",\n    engine_version: str = "HOLD_SINGLE_STOCK_V1",\n    policy_version: str = "P1",\n) -> SingleStockAnalysis:\n    return SingleStockAnalysis(\n        market="KOSPI",\n        ticker="005930",\n        market_date=market_date,\n        strategy_key=strategy,\n        action_state=action,\n        risk_state=risk,\n        reference_price=reference,\n        stop_price=stop,\n        target1_price=target1,\n        target2_price=target2,\n        condition_state={"state": "READY"},\n        readiness_state={"status": action},\n        scanner_version=scanner_version,\n        analysis_engine_version=engine_version,\n        policy_version=policy_version,\n        input_fingerprint=fingerprint,\n        source_versions={"fixture": fingerprint},\n        snapshot={"strategy": strategy, "action": action},\n    )\n\n\nclass MutableAnalyzer:\n    def __init__(self, result: SingleStockAnalysis):\n        self.result = result\n        self.calls = []\n\n    def __call__(self, **kwargs):\n        self.calls.append(kwargs)\n        return self.result\n\n\n@pytest.fixture()\ndef env(tmp_path):\n    catalog = HoldingsCatalog(tmp_path / "holdings.db")\n    catalog.initialize()\n    stock = catalog.create_monitored_stock(\n        market="KOSPI",\n        ticker="005930",\n        name="삼성전자",\n        watch_enabled=True,\n    )\n    analyzer = MutableAnalyzer(_analysis())\n    ticks = iter(\n        [f"2026-09-22T12:00:{second:02d}+00:00" for second in range(40)]\n    )\n    service = HoldingAnalysisHistoryService(\n        catalog,\n        analyzer=analyzer,\n        market_store_db=tmp_path / "market.db",\n        clock=lambda: next(ticks),\n    )\n    return catalog, stock, analyzer, service\n\n\ndef _counts(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        return {\n            "days": conn.execute(\n                "SELECT COUNT(*) FROM stock_analysis_day"\n            ).fetchone()[0],\n            "revisions": conn.execute(\n                "SELECT COUNT(*) FROM stock_analysis_revision"\n            ).fetchone()[0],\n        }\n\n\ndef _schema(catalog: HoldingsCatalog):\n    with catalog.connection() as conn:\n        rows = conn.execute(\n            """\n            SELECT type,name,sql FROM sqlite_master\n            WHERE type IN (\'table\',\'index\',\'trigger\')\n            ORDER BY type,name\n            """\n        ).fetchall()\n    return [(row["type"], row["name"], row["sql"]) for row in rows]\n\n\ndef test_first_analysis_creates_day_revision_and_current(env):\n    catalog, stock, analyzer, service = env\n    stored = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    assert stored.created_revision is True\n    assert stored.revision.revision_no == 1\n    assert stored.revision.revision_reason == "INITIAL"\n    assert stored.revision.strategy_key == "ma20_rebound"\n    assert _counts(catalog) == {"days": 1, "revisions": 1}\n\n    with catalog.connection() as conn:\n        day = conn.execute(\n            "SELECT * FROM stock_analysis_day WHERE id=?",\n            (stored.analysis_day_id,),\n        ).fetchone()\n    assert day["current_revision_id"] == stored.revision.id\n    assert analyzer.calls[0]["market"] == "KOSPI"\n    assert analyzer.calls[0]["ticker"] == "005930"\n    assert analyzer.calls[0]["market_date"] == "2026-09-18"\n\n\ndef test_same_fingerprint_reuses_revision(env):\n    catalog, stock, analyzer, service = env\n    first = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    second = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    assert second.revision.id == first.revision.id\n    assert second.created_revision is False\n    assert second.promoted_current is False\n    assert _counts(catalog) == {"days": 1, "revisions": 1}\n\n\n@pytest.mark.parametrize(\n    ("changes", "expected_reason"),\n    [\n        ({"fingerprint": "fp-2", "reference": 262000.0}, "INPUT_CHANGED"),\n        (\n            {\n                "fingerprint": "fp-engine",\n                "engine_version": "HOLD_SINGLE_STOCK_V2",\n            },\n            "ENGINE_CHANGED",\n        ),\n        (\n            {\n                "fingerprint": "fp-policy",\n                "policy_version": "P2",\n            },\n            "POLICY_CHANGED",\n        ),\n    ],\n)\ndef test_changed_input_creates_immutable_new_revision(env, changes, expected_reason):\n    catalog, stock, analyzer, service = env\n    first = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n\n    second_result = _analysis(\n        fingerprint=changes.get("fingerprint", "fp-2"),\n        reference=changes.get("reference", 261000.0),\n        engine_version=changes.get("engine_version", "HOLD_SINGLE_STOCK_V1"),\n        policy_version=changes.get("policy_version", "P1"),\n    )\n    analyzer.result = second_result\n    second = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n\n    assert second.created_revision is True\n    assert second.revision.revision_no == 2\n    assert second.revision.revision_reason == expected_reason\n    revisions = service.get_day_revisions(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    assert [r.id for r in revisions] == [first.revision.id, second.revision.id]\n    assert revisions[0].input_fingerprint == "fp-1"\n    assert service.get_current_analysis(stock.id).id == second.revision.id\n\n\ndef test_new_market_date_creates_new_day_and_revision_number_restarts(env):\n    catalog, stock, analyzer, service = env\n    first = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    analyzer.result = _analysis(\n        market_date="2026-09-21",\n        fingerprint="day-2",\n        strategy="trend_recovery",\n        action="READY",\n        reference=268000.0,\n    )\n    second = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-21",\n    )\n    assert second.analysis_day_id != first.analysis_day_id\n    assert second.revision.revision_no == 1\n    assert second.revision.revision_reason == "INITIAL"\n    assert _counts(catalog) == {"days": 2, "revisions": 2}\n\n\ndef test_analysis_failure_creates_no_revision_and_keeps_current(env):\n    catalog, stock, analyzer, service = env\n    first = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n\n    def fail(**kwargs):\n        raise HoldingsAnalysisError(\n            "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND",\n            "no exact eod",\n        )\n\n    service.analyzer = fail\n    with pytest.raises(HoldingsAnalysisHistoryError) as exc_info:\n        service.analyze_and_record(\n            monitored_stock_id=stock.id,\n            market_date="2026-09-21",\n        )\n    assert exc_info.value.code == "HOLD_ANALYSIS_HISTORY_FAILED"\n    assert exc_info.value.cause_code == "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND"\n    assert _counts(catalog) == {"days": 1, "revisions": 1}\n    assert service.get_current_analysis(stock.id).id == first.revision.id\n\n\ndef test_result_date_mismatch_is_not_persisted(env):\n    catalog, stock, analyzer, service = env\n    analyzer.result = _analysis(market_date="2026-09-17")\n    with pytest.raises(HoldingsAnalysisHistoryError) as exc_info:\n        service.analyze_and_record(\n            monitored_stock_id=stock.id,\n            market_date="2026-09-18",\n        )\n    assert exc_info.value.code == "HOLD_ANALYSIS_HISTORY_DATE_INVALID"\n    assert _counts(catalog) == {"days": 0, "revisions": 0}\n\n\ndef test_analysis_timeline_uses_current_revision_and_computes_changes(env):\n    catalog, stock, analyzer, service = env\n    service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    analyzer.result = _analysis(\n        fingerprint="same-day-new",\n        strategy="pullback",\n        reference=262000.0,\n    )\n    same_day = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n\n    analyzer.result = _analysis(\n        market_date="2026-09-21",\n        fingerprint="next-day",\n        strategy="trend_recovery",\n        action="READY",\n        reference=268000.0,\n        stop=260000.0,\n        target1=280000.0,\n        target2=290000.0,\n    )\n    service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-21",\n    )\n\n    timeline = service.get_analysis_timeline(stock.id)\n    assert [item.market_date for item in timeline] == [\n        "2026-09-21",\n        "2026-09-18",\n    ]\n    assert timeline[1].revision_id == same_day.revision.id\n    newest = timeline[0]\n    assert newest.previous_strategy_key == "pullback"\n    assert newest.strategy_changed is True\n    assert newest.action_changed is True\n    assert newest.risk_changed is False\n    assert newest.reference_price_delta == Decimal("6000")\n    assert newest.stop_price_changed is True\n\n\ndef test_buy_event_revision_reference_never_moves_with_current_revision(env):\n    catalog, stock, analyzer, service = env\n    first = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    account = catalog.create_position_account(\n        provider="MANUAL",\n        account_kind="MANUAL",\n        display_name="수동",\n    )\n    lifecycle = PositionLifecycleService(catalog)\n    bought = lifecycle.record_buy(\n        monitored_stock_id=stock.id,\n        position_account_id=account.id,\n        quantity="1",\n        unit_price="261000",\n        effective_at="2026-09-22T12:30:00+00:00",\n        analysis_revision_id=first.revision.id,\n    )\n\n    analyzer.result = _analysis(\n        fingerprint="fp-new",\n        strategy="trend_recovery",\n    )\n    second = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    assert second.revision.id != first.revision.id\n    event = catalog.list_position_events(bought.position.id)[0]\n    assert event.analysis_revision_id == first.revision.id\n\n\ndef test_analysis_targets_are_watch_or_open_position_and_deduplicated(env):\n    catalog, stock, analyzer, service = env\n    catalog.set_watch_enabled(stock.id, False)\n    assert service.list_analysis_targets() == ()\n\n    manual = catalog.create_position_account(\n        provider="MANUAL",\n        account_kind="MANUAL",\n        display_name="m1",\n    )\n    virtual = catalog.create_position_account(\n        provider="VIRTUAL",\n        account_kind="VIRTUAL",\n        display_name="v1",\n    )\n    catalog.open_position(\n        monitored_stock_id=stock.id,\n        position_account_id=manual.id,\n        opened_reason="MANUAL",\n        current_quantity="1",\n        current_average_price="1",\n        current_cost_basis="1",\n    )\n    catalog.open_position(\n        monitored_stock_id=stock.id,\n        position_account_id=virtual.id,\n        opened_reason="VIRTUAL",\n        current_quantity="2",\n        current_average_price="1",\n        current_cost_basis="2",\n    )\n    targets = service.list_analysis_targets()\n    assert [item.id for item in targets] == [stock.id]\n\n    other = catalog.create_monitored_stock(\n        market="KOSPI",\n        ticker="000660",\n        name="SK하이닉스",\n        watch_enabled=True,\n    )\n    assert {item.id for item in service.list_analysis_targets()} == {\n        stock.id,\n        other.id,\n    }\n\n\ndef test_combined_timeline_projects_analysis_and_position_events(env):\n    catalog, stock, analyzer, service = env\n    stored = service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    account = catalog.create_position_account(\n        provider="MANUAL",\n        account_kind="MANUAL",\n        display_name="수동",\n    )\n    lifecycle = PositionLifecycleService(catalog)\n    lifecycle.record_buy(\n        monitored_stock_id=stock.id,\n        position_account_id=account.id,\n        quantity="2",\n        unit_price="260000",\n        effective_at="2026-09-22T13:00:00+00:00",\n        analysis_revision_id=stored.revision.id,\n    )\n\n    timeline = service.get_stock_timeline(stock.id)\n    assert {item.kind for item in timeline} == {"ANALYSIS", "POSITION_EVENT"}\n    position_item = next(item for item in timeline if item.kind == "POSITION_EVENT")\n    assert position_item.event_type == "BUY"\n    assert position_item.analysis_revision_id == stored.revision.id\n\n\ndef test_latest_confirmed_date_is_resolved_before_exact_analysis(env, tmp_path):\n    catalog, stock, analyzer, service = env\n    market_db = tmp_path / "market_history.db"\n    with sqlite3.connect(market_db) as conn:\n        conn.executescript(\n            """\n            CREATE TABLE stock_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                stock_code TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,stock_code)\n            );\n            CREATE TABLE day_status(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                kind TEXT NOT NULL,\n                status TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,kind)\n            );\n            """\n        )\n        for day in ("20260918", "20260921"):\n            conn.execute(\n                "INSERT INTO stock_daily VALUES(?,?,?,?)",\n                ("KOSPI", day, "005930", "{}"),\n            )\n        conn.execute(\n            "INSERT INTO day_status VALUES(?,?,?,?)",\n            ("KOSPI", "20260918", "stock", "data"),\n        )\n        conn.execute(\n            "INSERT INTO day_status VALUES(?,?,?,?)",\n            ("KOSPI", "20260918", "index", "data"),\n        )\n        conn.execute(\n            "INSERT INTO day_status VALUES(?,?,?,?)",\n            ("KOSPI", "20260921", "stock", "data"),\n        )\n        conn.execute(\n            "INSERT INTO day_status VALUES(?,?,?,?)",\n            ("KOSPI", "20260921", "index", "missing"),\n        )\n\n    service.market_store_db = market_db\n    assert service.latest_confirmed_market_date(stock.id) == "2026-09-18"\n    analyzer.result = _analysis(market_date="2026-09-18")\n    service.analyze_latest_confirmed(monitored_stock_id=stock.id)\n    assert analyzer.calls[-1]["market_date"] == "2026-09-18"\n\n\ndef test_schema_is_unchanged_and_history_has_no_kis_scanner_or_live_price_dependency(env):\n    catalog, stock, analyzer, service = env\n    before = _schema(catalog)\n    service.analyze_and_record(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-18",\n    )\n    after = _schema(catalog)\n    assert after == before\n\n    source = Path("backend/app/holdings/analysis_history.py").read_text(\n        encoding="utf-8"\n    )\n    assert "app.integrations.kis" not in source\n    assert "StockScannerService" not in source\n    assert "current_price" not in source\n    assert "record_buy(" not in source\n    assert "record_sell(" not in source\n'
INIT_APPEND = '\nfrom .analysis_history import (\n    AnalysisTimelineItem,\n    HoldingAnalysisHistoryService,\n    HoldingsAnalysisHistoryError,\n    StockTimelineItem,\n    StoredAnalysisResult,\n)\n\n__all__.extend(\n    [\n        "AnalysisTimelineItem",\n        "HoldingAnalysisHistoryService",\n        "HoldingsAnalysisHistoryError",\n        "StockTimelineItem",\n        "StoredAnalysisResult",\n    ]\n)\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


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


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-E Daily Analysis Revision / Timeline")
    print("Analysis engine: HOLD.1-B adapter reuse")
    print("DB schema change: NO")
    print("KIS/live price usage: NO")
    print("Scanner/Strategy/Risk direct call: NO")

    required = [CATALOG, DOMAIN, ANALYSIS, LIFECYCLE, KIS_SYNC, INIT]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    for target in (HISTORY, TEST):
        if target.exists():
            fail(f"Target already exists: {target}")

    catalog_text = CATALOG.read_text(encoding="utf-8-sig")
    analysis_text = ANALYSIS.read_text(encoding="utf-8-sig")
    init_before = INIT.read_text(encoding="utf-8-sig")

    required_catalog_markers = [
        "def connection(self)",
        "CREATE TABLE IF NOT EXISTS stock_analysis_day (",
        "CREATE TABLE IF NOT EXISTS stock_analysis_revision (",
        "trg_stock_analysis_revision_no_update",
        "trg_stock_analysis_revision_no_delete",
        "CREATE TABLE IF NOT EXISTS holding_position_event (",
    ]
    missing = [marker for marker in required_catalog_markers if marker not in catalog_text]
    if missing:
        print()
        print("E.0 SOURCE AUDIT: STOP")
        print("Unexpected HOLD catalog structure; no files were changed.")
        print("Missing markers:", missing)
        return 2

    required_analysis_markers = [
        "class SingleStockAnalysis",
        "def analyze_single_stock(",
        "ANALYSIS_ENGINE_VERSION =",
    ]
    missing_analysis = [
        marker for marker in required_analysis_markers if marker not in analysis_text
    ]
    if missing_analysis:
        print()
        print("E.0 SOURCE AUDIT: STOP")
        print("Unexpected HOLD.1-B analysis adapter; no files were changed.")
        print("Missing markers:", missing_analysis)
        return 2

    if "from .kis_sync import (" not in init_before:
        print()
        print("E.0 SOURCE AUDIT: STOP")
        print("HOLD.1-D exports were not found; no files were changed.")
        return 2

    compile(ANALYSIS_HISTORY_CONTENT, str(HISTORY), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    protected = {
        "catalog": sha256(CATALOG),
        "domain": sha256(DOMAIN),
        "analysis": sha256(ANALYSIS),
        "lifecycle": sha256(LIFECYCLE),
        "kis_sync": sha256(KIS_SYNC),
        "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
        "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
        "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
        "kis": tree_hash(ROOT / "backend" / "app" / "integrations" / "kis"),
    }

    created: list[Path] = []
    init_changed = False
    tests_passed = False

    try:
        HISTORY.write_text(
            ANALYSIS_HISTORY_CONTENT,
            encoding="utf-8",
            newline="\n",
        )
        created.append(HISTORY)

        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        if "from .analysis_history import (" in init_before:
            fail("holdings/__init__.py already contains HOLD.1-E exports.")
        INIT.write_text(
            init_before.rstrip() + "\n" + INIT_APPEND.lstrip(),
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
                "backend/tests/test_holdings_analysis_history_hold1e.py",
                "-q",
            ],
            "HOLD.1-E analysis history tests",
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_holdings_catalog_hold1a.py",
                "backend/tests/test_holdings_analysis_hold1b.py",
                "backend/tests/test_holdings_lifecycle_hold1c.py",
                "backend/tests/test_holdings_kis_sync_hold1d.py",
                "-q",
            ],
            "HOLD.1-A/B/C/D regression",
        )
        tests_passed = True

        after = {
            "catalog": sha256(CATALOG),
            "domain": sha256(DOMAIN),
            "analysis": sha256(ANALYSIS),
            "lifecycle": sha256(LIFECYCLE),
            "kis_sync": sha256(KIS_SYNC),
            "scanner": tree_hash(ROOT / "backend" / "app" / "backtest" / "scanner.py"),
            "strategy": tree_hash(ROOT / "backend" / "app" / "strategy"),
            "risk": tree_hash(ROOT / "backend" / "app" / "risk"),
            "kis": tree_hash(ROOT / "backend" / "app" / "integrations" / "kis"),
        }
        changed = [key for key in protected if protected[key] != after[key]]
        if changed:
            fail("Protected source changed during HOLD.1-E: " + ", ".join(changed))

        print()
        print("=== HOLD.1-E REAL MARKET STORE + TEMP DB SMOKE ===")
        smoke = r"""
import sys
import tempfile
sys.path.insert(0, "backend")
from pathlib import Path

from app.holdings import HoldingsCatalog, HoldingAnalysisHistoryService

with tempfile.TemporaryDirectory() as td:
    db = Path(td) / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    stock = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        watch_enabled=True,
    )
    service = HoldingAnalysisHistoryService(catalog)

    first = service.analyze_latest_confirmed(monitored_stock_id=stock.id)
    second = service.analyze_latest_confirmed(monitored_stock_id=stock.id)

    revisions = service.get_day_revisions(
        monitored_stock_id=stock.id,
        market_date=first.revision.snapshot.get("source", {}).get(
            "market_date",
            service.latest_confirmed_market_date(stock.id),
        ),
    )
    with catalog.connection() as conn:
        day_count = conn.execute(
            "SELECT COUNT(*) FROM stock_analysis_day"
        ).fetchone()[0]
        revision_count = conn.execute(
            "SELECT COUNT(*) FROM stock_analysis_revision"
        ).fetchone()[0]

    timeline = service.get_analysis_timeline(stock.id)
    assert first.revision.id == second.revision.id
    assert first.created_revision is True
    assert second.created_revision is False
    assert day_count == 1
    assert revision_count == 1
    assert len(timeline) == 1

    print("MARKET_DATE:", timeline[0].market_date)
    print("STRATEGY:", timeline[0].strategy_key)
    print("ACTION_STATE:", timeline[0].action_state)
    print("RISK_STATE:", timeline[0].risk_state)
    print("REVISION_1_CREATED: YES")
    print("SECOND_RUN_REUSED: YES")
    print("ANALYSIS_DAYS:", day_count)
    print("REVISION_COUNT:", revision_count)
    print("TIMELINE_ITEMS:", len(timeline))
    print("ACTUAL HOLDINGS DB TOUCHED: NO")
    print("KIS_CALLED: NO")
"""
        result = subprocess.run([python_exe, "-c", smoke], cwd=ROOT)
        if result.returncode != 0:
            print()
            print("HOLD.1-E REAL MARKET STORE SMOKE: FAILED")
            print("Local HOLD.1-E tests and A/B/C/D regressions already passed.")
            print("Source changes are kept for diagnosis; actual holdings.db was not used.")
            return result.returncode

        print()
        print("HOLD.1-E CLOSED")
        print("Added:")
        print(" - backend/app/holdings/analysis_history.py")
        print(" - backend/tests/test_holdings_analysis_history_hold1e.py")
        print("Modified:")
        print(" - backend/app/holdings/__init__.py (exports only)")
        print("Daily Analysis Day persistence: PASS")
        print("Immutable Revision history: PASS")
        print("Same fingerprint reuse: PASS")
        print("Current Revision promotion: PASS")
        print("Failed analysis keeps prior current: PASS")
        print("Revision reason classification: PASS")
        print("Analysis timeline + change projection: PASS")
        print("Combined analysis/position timeline: PASS")
        print("Watch/Open-position target selection: PASS")
        print("Latest confirmed EOD resolution: PASS")
        print("DB schema changed: NO")
        print("HOLD.1-A/B/C/D regression: PASS")
        print("Scanner/Strategy/Risk/KIS changed: NO")
        print("KIS/live price used: NO")
        return 0

    except Exception:
        if not tests_passed:
            if init_changed:
                INIT.write_text(init_before, encoding="utf-8", newline="\n")
            for path in reversed(created):
                if path.exists():
                    path.unlink()
            print()
            print("FAILED — HOLD.1-E additions were rolled back.")
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
