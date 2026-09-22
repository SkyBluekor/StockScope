from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SCANNER = ROOT / "backend" / "app" / "backtest" / "scanner.py"
HOLDINGS_INIT = ROOT / "backend" / "app" / "holdings" / "__init__.py"
ANALYSIS = ROOT / "backend" / "app" / "holdings" / "analysis.py"
TEST = ROOT / "backend" / "tests" / "test_holdings_analysis_hold1b.py"

ANALYSIS_CONTENT = 'from __future__ import annotations\n\nimport hashlib\nimport json\nimport sqlite3\nfrom dataclasses import asdict, dataclass\nfrom datetime import date, timedelta\nfrom pathlib import Path\nfrom typing import Any\n\nfrom app.backtest.production_exit_policy import production_policy_cache_token\nfrom app.backtest.scanner import StockScannerService\nfrom app.core.config import PROJECT_ROOT\n\n\nANALYSIS_ENGINE_VERSION = "HOLD_SINGLE_STOCK_V1"\nDEFAULT_MARKET_STORE_DB = (\n    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"\n)\n\n\nclass HoldingsAnalysisError(RuntimeError):\n    def __init__(self, code: str, message: str):\n        super().__init__(message)\n        self.code = code\n        self.message = message\n\n\n@dataclass(frozen=True, slots=True)\nclass SingleStockAnalysis:\n    market: str\n    ticker: str\n    market_date: str\n    strategy_key: str\n    action_state: str\n    risk_state: str | None\n    reference_price: float\n    stop_price: float | None\n    target1_price: float | None\n    target2_price: float | None\n    condition_state: dict[str, Any]\n    readiness_state: dict[str, Any]\n    scanner_version: str\n    analysis_engine_version: str\n    policy_version: str\n    input_fingerprint: str\n    source_versions: dict[str, Any]\n    snapshot: dict[str, Any]\n\n    def to_dict(self) -> dict[str, Any]:\n        return asdict(self)\n\n\nclass _NoNetworkProvider:\n    """Fails loudly if HOLD.1-B ever drifts into provider/network behavior."""\n\n    def __getattr__(self, name: str) -> Any:\n        raise HoldingsAnalysisError(\n            "HOLD_ANALYSIS_NETWORK_FORBIDDEN",\n            f"Single-stock EOD analysis must not access a provider: {name}",\n        )\n\n\nclass _ReadOnlyMarketStore:\n    """Minimal read-only view over the existing Market Store SQLite schema."""\n\n    def __init__(self, db_path: Path):\n        self.db_path = Path(db_path)\n\n    def _connect(self) -> sqlite3.Connection:\n        if not self.db_path.is_file():\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_MARKET_STORE_NOT_FOUND",\n                f"Market Store를 찾을 수 없습니다: {self.db_path}",\n            )\n        uri = self.db_path.resolve().as_uri() + "?mode=ro"\n        conn = sqlite3.connect(uri, uri=True, timeout=20.0)\n        conn.row_factory = sqlite3.Row\n        return conn\n\n    @staticmethod\n    def _load(raw: str) -> dict[str, Any]:\n        value = json.loads(raw)\n        return value if isinstance(value, dict) else {}\n\n    def has_data_day(self, market: str, bas_dd: str, kind: str) -> bool:\n        with self._connect() as conn:\n            row = conn.execute(\n                """\n                SELECT 1\n                FROM day_status\n                WHERE market=? AND bas_dd=? AND kind=? AND status=\'data\'\n                LIMIT 1\n                """,\n                (market, bas_dd, kind),\n            ).fetchone()\n        return row is not None\n\n    def stock_rows(\n        self,\n        market: str,\n        ticker: str,\n        start_dd: str,\n        end_dd: str,\n    ) -> list[dict[str, Any]]:\n        with self._connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT bas_dd,row_json\n                FROM stock_daily\n                WHERE market=? AND stock_code=? AND bas_dd>=? AND bas_dd<=?\n                ORDER BY bas_dd\n                """,\n                (market, ticker, start_dd, end_dd),\n            ).fetchall()\n        return [self._load(str(row["row_json"])) for row in rows]\n\n    def exact_stock_row(\n        self,\n        market: str,\n        ticker: str,\n        bas_dd: str,\n    ) -> dict[str, Any] | None:\n        with self._connect() as conn:\n            row = conn.execute(\n                """\n                SELECT row_json\n                FROM stock_daily\n                WHERE market=? AND stock_code=? AND bas_dd=?\n                """,\n                (market, ticker, bas_dd),\n            ).fetchone()\n        return self._load(str(row["row_json"])) if row is not None else None\n\n    def index_rows(\n        self,\n        market: str,\n        start_dd: str,\n        end_dd: str,\n    ) -> list[dict[str, Any]]:\n        with self._connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT bas_dd,row_json\n                FROM main_index_daily\n                WHERE market=? AND bas_dd>=? AND bas_dd<=?\n                ORDER BY bas_dd\n                """,\n                (market, start_dd, end_dd),\n            ).fetchall()\n        return [self._load(str(row["row_json"])) for row in rows]\n\n\ndef _canonical_json(value: Any) -> str:\n    return json.dumps(\n        value,\n        ensure_ascii=False,\n        sort_keys=True,\n        separators=(",", ":"),\n        default=str,\n    )\n\n\ndef _normalize_market(market: str) -> str:\n    value = (market or "").strip().upper()\n    if value not in {"KOSPI", "KOSDAQ"}:\n        raise HoldingsAnalysisError(\n            "HOLD_ANALYSIS_MARKET_INVALID",\n            "market은 KOSPI 또는 KOSDAQ이어야 합니다.",\n        )\n    return value\n\n\ndef _normalize_ticker(ticker: str) -> str:\n    value = (ticker or "").strip()\n    if len(value) != 6 or not value.isdigit():\n        raise HoldingsAnalysisError(\n            "HOLD_ANALYSIS_TICKER_INVALID",\n            "국내주식 종목코드는 6자리 숫자여야 합니다.",\n        )\n    return value\n\n\ndef _normalize_market_date(market_date: str) -> date:\n    try:\n        return date.fromisoformat((market_date or "").strip())\n    except ValueError as exc:\n        raise HoldingsAnalysisError(\n            "HOLD_ANALYSIS_DATE_INVALID",\n            "market_date는 YYYY-MM-DD 형식이어야 합니다.",\n        ) from exc\n\n\ndef _decision_state(candidate_state: str) -> str:\n    state = candidate_state.strip().upper()\n    if state == "READY":\n        return "READY"\n    if state in {"WATCH", "VALIDATION"}:\n        return "WATCH"\n    return "NO_TRADE"\n\n\ndef _optional_float(value: Any) -> float | None:\n    if value in (None, ""):\n        return None\n    return float(value)\n\n\nclass SingleStockAnalysisAdapter:\n    """Pure EOD single-stock adapter over the Production Scanner current path.\n\n    It reads Market Store rows in SQLite read-only mode, calls only the Scanner\'s\n    current single-stock helpers, and never calls StockScannerService.run().\n    """\n\n    def __init__(\n        self,\n        *,\n        market_store_db: Path | None = None,\n        scanner: StockScannerService | None = None,\n    ) -> None:\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n        self.store = _ReadOnlyMarketStore(self.market_store_db)\n        self.scanner = scanner or StockScannerService(\n            _NoNetworkProvider(),\n            market_store=object(),\n        )\n\n    def analyze(\n        self,\n        *,\n        market: str,\n        ticker: str,\n        market_date: str,\n    ) -> SingleStockAnalysis:\n        clean_market = _normalize_market(market)\n        clean_ticker = _normalize_ticker(ticker)\n        target_date = _normalize_market_date(market_date)\n        end_dd = target_date.strftime("%Y%m%d")\n\n        if not self.store.has_data_day(clean_market, end_dd, "stock"):\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND",\n                f"{target_date.isoformat()}의 확정 종목 EOD 데이터가 없습니다.",\n            )\n        if not self.store.has_data_day(clean_market, end_dd, "index"):\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_BENCHMARK_MISSING",\n                f"{target_date.isoformat()}의 확정 시장지수 데이터가 없습니다.",\n            )\n\n        current_row = self.store.exact_stock_row(\n            clean_market,\n            clean_ticker,\n            end_dd,\n        )\n        if current_row is None:\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_STOCK_NOT_FOUND",\n                f"{clean_market}/{clean_ticker} 종목을 해당 거래일 Market Store에서 찾을 수 없습니다.",\n            )\n\n        fast_start = target_date - timedelta(\n            days=self.scanner.FAST_HISTORY_CALENDAR_DAYS\n        )\n        start_dd = fast_start.strftime("%Y%m%d")\n        stock_rows = self.store.stock_rows(\n            clean_market,\n            clean_ticker,\n            start_dd,\n            end_dd,\n        )\n        index_rows = self.store.index_rows(\n            clean_market,\n            start_dd,\n            end_dd,\n        )\n\n        if len(stock_rows) < self.scanner.MIN_HISTORY_ROWS:\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_HISTORY_INSUFFICIENT",\n                (\n                    f"분석에 필요한 종목 이력이 부족합니다: "\n                    f"{len(stock_rows)}/{self.scanner.MIN_HISTORY_ROWS}"\n                ),\n            )\n        if not index_rows:\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_BENCHMARK_MISSING",\n                "분석 기간의 시장지수 이력이 없습니다.",\n            )\n\n        try:\n            quick = self.scanner._quick_current_candidate(  # noqa: SLF001\n                market=clean_market,\n                latest_date=end_dd,\n                row=current_row,\n                stock_rows=stock_rows,\n                index_rows=index_rows,\n                sector_input=None,\n            )\n            if quick is None:\n                raise HoldingsAnalysisError(\n                    "HOLD_ANALYSIS_FAILED",\n                    "Production Scanner current-path snapshot을 만들지 못했습니다.",\n                )\n            candidate = self.scanner._current_candidate(quick)  # noqa: SLF001\n            if candidate is None:\n                raise HoldingsAnalysisError(\n                    "HOLD_ANALYSIS_FAILED",\n                    "Production Scanner current-path 판단을 만들지 못했습니다.",\n                )\n        except HoldingsAnalysisError:\n            raise\n        except Exception as exc:\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_FAILED",\n                f"단일 종목 EOD 분석에 실패했습니다: {exc}",\n            ) from exc\n\n        strategy_key = str(candidate.get("strategy") or "").strip()\n        if not strategy_key:\n            raise HoldingsAnalysisError(\n                "HOLD_ANALYSIS_FAILED",\n                "Production Scanner가 전략 식별자를 반환하지 않았습니다.",\n            )\n\n        condition_state = dict(quick.get("quick_condition_state") or {})\n        readiness_state = dict(quick.get("quick_current") or {})\n        entry_risk_guide = dict(candidate.get("entry_risk_guide") or {})\n        risk_payload = dict(entry_risk_guide.get("risk") or {})\n        candidate_state = str(candidate.get("candidate_state") or "EXCLUDED")\n        action_state = _decision_state(candidate_state)\n        policy_version = production_policy_cache_token()\n\n        # Hash only rows that can influence the shared current snapshot:\n        # stock: technical 60, RS 61, long SMA up to 120; index: RS up to 61.\n        fingerprint_stock_rows = stock_rows[-120:]\n        fingerprint_index_rows = index_rows[-61:]\n        fingerprint_payload = {\n            "market": clean_market,\n            "ticker": clean_ticker,\n            "market_date": target_date.isoformat(),\n            "scanner_version": self.scanner.VERSION,\n            "scanner_data_integrity_version": self.scanner.DATA_INTEGRITY_VERSION,\n            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,\n            "policy_version": policy_version,\n            "stock_rows": fingerprint_stock_rows,\n            "index_rows": fingerprint_index_rows,\n            "sector_input": None,\n        }\n        input_fingerprint = hashlib.sha256(\n            _canonical_json(fingerprint_payload).encode("utf-8")\n        ).hexdigest()\n\n        source_versions = {\n            "scanner_version": self.scanner.VERSION,\n            "scanner_data_integrity_version": self.scanner.DATA_INTEGRITY_VERSION,\n            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,\n            "policy_version": policy_version,\n            "market_store": "market_history.db",\n            "price_basis": "CONFIRMED_EOD",\n            "fast_history_calendar_days": self.scanner.FAST_HISTORY_CALENDAR_DAYS,\n            "stock_history_rows": len(stock_rows),\n            "index_history_rows": len(index_rows),\n            "fingerprinted_stock_rows": len(fingerprint_stock_rows),\n            "fingerprinted_index_rows": len(fingerprint_index_rows),\n            "sector_input_mode": "NONE_PRODUCTION_SAFE",\n        }\n\n        snapshot = {\n            "strategy_key": strategy_key,\n            "action_state": action_state,\n            "scanner_action": candidate.get("action"),\n            "candidate_state": candidate_state,\n            "condition_state": condition_state,\n            "readiness_state": readiness_state,\n            "risk": risk_payload,\n            "entry_risk_guide": entry_risk_guide,\n            "strategy_trace": dict(quick.get("_strategy_trace") or {}),\n            "sector_input_audit": dict(quick.get("_sector_input_audit") or {}),\n            "source": {\n                "market": clean_market,\n                "ticker": clean_ticker,\n                "market_date": target_date.isoformat(),\n                "stock_history_rows": len(stock_rows),\n                "index_history_rows": len(index_rows),\n                "price_basis": "CONFIRMED_EOD",\n            },\n        }\n\n        return SingleStockAnalysis(\n            market=clean_market,\n            ticker=clean_ticker,\n            market_date=target_date.isoformat(),\n            strategy_key=strategy_key,\n            action_state=action_state,\n            risk_state=(\n                str(candidate.get("risk", {}).get("status"))\n                if candidate.get("risk", {}).get("status") not in (None, "")\n                else None\n            ),\n            reference_price=float(candidate.get("current_price")),\n            stop_price=_optional_float(risk_payload.get("invalidation_price")),\n            target1_price=_optional_float(risk_payload.get("target1_price")),\n            target2_price=_optional_float(risk_payload.get("target2_price")),\n            condition_state=condition_state,\n            readiness_state=readiness_state,\n            scanner_version=self.scanner.VERSION,\n            analysis_engine_version=ANALYSIS_ENGINE_VERSION,\n            policy_version=policy_version,\n            input_fingerprint=input_fingerprint,\n            source_versions=source_versions,\n            snapshot=snapshot,\n        )\n\n\ndef analyze_single_stock(\n    *,\n    market: str,\n    ticker: str,\n    market_date: str,\n    market_store_db: Path | None = None,\n) -> SingleStockAnalysis:\n    return SingleStockAnalysisAdapter(\n        market_store_db=market_store_db,\n    ).analyze(\n        market=market,\n        ticker=ticker,\n        market_date=market_date,\n    )\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport hashlib\nimport json\nimport sqlite3\nfrom datetime import date, timedelta\nfrom pathlib import Path\n\nimport pytest\n\nfrom app.backtest.scanner import StockScannerService\nfrom app.holdings.analysis import (\n    HoldingsAnalysisError,\n    SingleStockAnalysisAdapter,\n    analyze_single_stock,\n)\n\n\nTARGET_DATE = date(2026, 9, 22)\n\n\ndef _trading_dates(count: int = 130) -> list[date]:\n    values = []\n    cursor = TARGET_DATE\n    while len(values) < count:\n        if cursor.weekday() < 5:\n            values.append(cursor)\n        cursor -= timedelta(days=1)\n    return sorted(values)\n\n\ndef _stock_row(index: int, day: date) -> dict:\n    close = 70000.0 + index * 120.0\n    return {\n        "date": day.isoformat(),\n        "code": "005930",\n        "name": "삼성전자",\n        "open": close - 80.0,\n        "high": close + 260.0,\n        "low": close - 240.0,\n        "close": close,\n        "volume": 1_500_000 + index * 2500,\n        "trade_value": 20_000_000_000 + index * 1_000_000,\n        "market_cap": 400_000_000_000_000,\n        "change_rate": 0.4,\n    }\n\n\ndef _index_row(index: int, day: date) -> dict:\n    close = 3000.0 + index * 2.0\n    return {\n        "date": day.isoformat(),\n        "open": close - 2.0,\n        "high": close + 5.0,\n        "low": close - 5.0,\n        "close": close,\n        "change_rate": 0.15,\n    }\n\n\ndef _build_market_store(path: Path) -> tuple[list[dict], list[dict]]:\n    dates = _trading_dates()\n    stocks = [_stock_row(i, day) for i, day in enumerate(dates)]\n    indices = [_index_row(i, day) for i, day in enumerate(dates)]\n\n    with sqlite3.connect(path) as conn:\n        conn.executescript(\n            """\n            CREATE TABLE stock_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                stock_code TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,stock_code)\n            );\n            CREATE TABLE main_index_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd)\n            );\n            CREATE TABLE day_status(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                kind TEXT NOT NULL,\n                status TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,kind)\n            );\n            """\n        )\n        for stock, index_row, day in zip(stocks, indices, dates, strict=True):\n            bas_dd = day.strftime("%Y%m%d")\n            conn.execute(\n                "INSERT INTO stock_daily VALUES(?,?,?,?)",\n                (\n                    "KOSPI",\n                    bas_dd,\n                    "005930",\n                    json.dumps(stock, ensure_ascii=False),\n                ),\n            )\n            conn.execute(\n                "INSERT INTO main_index_daily VALUES(?,?,?)",\n                (\n                    "KOSPI",\n                    bas_dd,\n                    json.dumps(index_row, ensure_ascii=False),\n                ),\n            )\n            conn.execute(\n                "INSERT INTO day_status VALUES(?,?,?,?)",\n                ("KOSPI", bas_dd, "stock", "data"),\n            )\n            conn.execute(\n                "INSERT INTO day_status VALUES(?,?,?,?)",\n                ("KOSPI", bas_dd, "index", "data"),\n            )\n    return stocks, indices\n\n\n@pytest.fixture()\ndef market_db(tmp_path):\n    path = tmp_path / "market_history.db"\n    stocks, indices = _build_market_store(path)\n    return path, stocks, indices\n\n\ndef _decision_state(candidate_state: str) -> str:\n    if candidate_state == "READY":\n        return "READY"\n    if candidate_state in {"WATCH", "VALIDATION"}:\n        return "WATCH"\n    return "NO_TRADE"\n\n\ndef test_adapter_matches_production_scanner_current_path(market_db):\n    db_path, stocks, indices = market_db\n    adapter = SingleStockAnalysisAdapter(market_store_db=db_path)\n\n    result = adapter.analyze(\n        market="KOSPI",\n        ticker="005930",\n        market_date=TARGET_DATE.isoformat(),\n    )\n\n    fast_start = TARGET_DATE - timedelta(\n        days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS\n    )\n    stock_rows = [\n        row for row in stocks\n        if date.fromisoformat(row["date"]) >= fast_start\n    ]\n    index_rows = [\n        row for row in indices\n        if date.fromisoformat(row["date"]) >= fast_start\n    ]\n\n    scanner = StockScannerService(object(), market_store=object())\n    quick = scanner._quick_current_candidate(  # noqa: SLF001\n        market="KOSPI",\n        latest_date=TARGET_DATE.strftime("%Y%m%d"),\n        row=stock_rows[-1],\n        stock_rows=stock_rows,\n        index_rows=index_rows,\n        sector_input=None,\n    )\n    assert quick is not None\n    candidate = scanner._current_candidate(quick)  # noqa: SLF001\n    assert candidate is not None\n\n    risk = candidate["entry_risk_guide"]["risk"]\n    assert result.strategy_key == candidate["strategy"]\n    assert result.action_state == _decision_state(candidate["candidate_state"])\n    assert result.risk_state == candidate["risk"]["status"]\n    assert result.reference_price == float(candidate["current_price"])\n    assert result.stop_price == risk["invalidation_price"]\n    assert result.target1_price == risk["target1_price"]\n    assert result.target2_price == risk["target2_price"]\n\n\ndef test_same_input_same_fingerprint_and_history_change_changes_it(market_db):\n    db_path, _, _ = market_db\n\n    first = analyze_single_stock(\n        market="KOSPI",\n        ticker="005930",\n        market_date=TARGET_DATE.isoformat(),\n        market_store_db=db_path,\n    )\n    second = analyze_single_stock(\n        market="KOSPI",\n        ticker="005930",\n        market_date=TARGET_DATE.isoformat(),\n        market_store_db=db_path,\n    )\n    assert first.input_fingerprint == second.input_fingerprint\n\n    changed_day = (TARGET_DATE - timedelta(days=7)).strftime("%Y%m%d")\n    with sqlite3.connect(db_path) as conn:\n        raw = conn.execute(\n            """\n            SELECT row_json FROM stock_daily\n            WHERE market=\'KOSPI\' AND bas_dd=? AND stock_code=\'005930\'\n            """,\n            (changed_day,),\n        ).fetchone()\n        if raw is None:\n            raw = conn.execute(\n                """\n                SELECT bas_dd,row_json FROM stock_daily\n                WHERE market=\'KOSPI\' AND stock_code=\'005930\'\n                ORDER BY bas_dd DESC LIMIT 10,1\n                """\n            ).fetchone()\n            changed_day = raw[0]\n            payload = json.loads(raw[1])\n        else:\n            payload = json.loads(raw[0])\n        payload["close"] = float(payload["close"]) + 777.0\n        conn.execute(\n            """\n            UPDATE stock_daily SET row_json=?\n            WHERE market=\'KOSPI\' AND bas_dd=? AND stock_code=\'005930\'\n            """,\n            (json.dumps(payload, ensure_ascii=False), changed_day),\n        )\n\n    changed = analyze_single_stock(\n        market="KOSPI",\n        ticker="005930",\n        market_date=TARGET_DATE.isoformat(),\n        market_store_db=db_path,\n    )\n    assert changed.input_fingerprint != first.input_fingerprint\n\n\ndef test_missing_market_date_is_error_not_no_trade(market_db):\n    db_path, _, _ = market_db\n    with pytest.raises(HoldingsAnalysisError) as exc_info:\n        analyze_single_stock(\n            market="KOSPI",\n            ticker="005930",\n            market_date="2026-09-23",\n            market_store_db=db_path,\n        )\n    assert exc_info.value.code == "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND"\n\n\ndef test_missing_stock_is_error_not_no_trade(market_db):\n    db_path, _, _ = market_db\n    with pytest.raises(HoldingsAnalysisError) as exc_info:\n        analyze_single_stock(\n            market="KOSPI",\n            ticker="000001",\n            market_date=TARGET_DATE.isoformat(),\n            market_store_db=db_path,\n        )\n    assert exc_info.value.code == "HOLD_ANALYSIS_STOCK_NOT_FOUND"\n\n\ndef test_analysis_is_read_only_and_has_no_rank_or_live_price_input(market_db, monkeypatch):\n    db_path, _, _ = market_db\n    before = hashlib.sha256(db_path.read_bytes()).hexdigest()\n\n    async def forbidden_run(*args, **kwargs):\n        raise AssertionError("StockScannerService.run() must not be called")\n\n    monkeypatch.setattr(StockScannerService, "run", forbidden_run)\n\n    result = analyze_single_stock(\n        market="KOSPI",\n        ticker="005930",\n        market_date=TARGET_DATE.isoformat(),\n        market_store_db=db_path,\n    )\n    after = hashlib.sha256(db_path.read_bytes()).hexdigest()\n\n    assert before == after\n    assert "rank" not in result.to_dict()\n    assert "internal_rank" not in json.dumps(result.snapshot)\n    assert "scanner_rank" not in json.dumps(result.snapshot)\n\n    with pytest.raises(TypeError):\n        analyze_single_stock(\n            market="KOSPI",\n            ticker="005930",\n            market_date=TARGET_DATE.isoformat(),\n            market_store_db=db_path,\n            reference_price=99999,  # type: ignore[call-arg]\n        )\n\n\ndef test_analysis_module_has_no_kis_or_holdings_db_dependency():\n    source = Path("backend/app/holdings/analysis.py").read_text(encoding="utf-8")\n    assert "integrations.kis" not in source\n    assert "HoldingsCatalog" not in source\n    assert "holdings.db" not in source\n    assert "self.scanner.run(" not in source\n'
INIT_APPEND = '\nfrom .analysis import (\n    ANALYSIS_ENGINE_VERSION,\n    HoldingsAnalysisError,\n    SingleStockAnalysis,\n    SingleStockAnalysisAdapter,\n    analyze_single_stock,\n)\n\n__all__.extend(\n    [\n        "ANALYSIS_ENGINE_VERSION",\n        "HoldingsAnalysisError",\n        "SingleStockAnalysis",\n        "SingleStockAnalysisAdapter",\n        "analyze_single_stock",\n    ]\n)\n'


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


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-B Single-Stock Analysis Adapter")
    print("Mode: Production current-path reuse / read-only Market Store")
    print("Scanner.run(): FORBIDDEN")
    print("Scanner/Strategy/Risk source modification: NO")
    print("KIS usage: NO")
    print("HOLD DB write: NO")

    for required in (SCANNER, HOLDINGS_INIT):
        if not required.is_file():
            fail(f"Required file missing: {required}")
    for target in (ANALYSIS, TEST):
        if target.exists():
            fail(f"Target already exists: {target}")

    scanner_text = SCANNER.read_text(encoding="utf-8-sig")
    required_markers = [
        'VERSION = "0.21.3.7"',
        "def _quick_current_candidate(",
        "def _current_candidate(",
        "selector eligible/score",
        "current_internal_score",
    ]
    missing = [marker for marker in required_markers if marker not in scanner_text]
    if missing:
        print()
        print("B.0 SOURCE AUDIT: STOP")
        print("Unexpected local scanner.py; no files were changed.")
        print("Missing markers:", missing)
        return 2

    scanner_before = sha256(SCANNER)
    init_before = HOLDINGS_INIT.read_text(encoding="utf-8-sig")

    compile(ANALYSIS_CONTENT, str(ANALYSIS), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    created = []
    init_changed = False
    try:
        ANALYSIS.write_text(ANALYSIS_CONTENT, encoding="utf-8", newline="\n")
        created.append(ANALYSIS)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        init_text = init_before
        if "from .analysis import (" in init_text:
            fail("holdings/__init__.py already contains analysis exports.")
        HOLDINGS_INIT.write_text(
            init_text.rstrip() + "\n" + INIT_APPEND.lstrip(),
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
                "backend/tests/test_holdings_analysis_hold1b.py",
                "-q",
            ],
            "HOLD.1-B adapter + parity tests",
        )

        hold1a_regression = (
            ROOT / "backend" / "tests" / "test_holdings_catalog_hold1a.py"
        )
        if hold1a_regression.is_file():
            run(
                [
                    python_exe,
                    "-m",
                    "pytest",
                    str(hold1a_regression.relative_to(ROOT)),
                    "-q",
                ],
                "HOLD.1-A persistence regression",
            )

        legacy_scanner_test = (
            ROOT / "backend" / "tests" / "test_scanner_determinism_v0214b234b.py"
        )
        if legacy_scanner_test.is_file():
            legacy_source = legacy_scanner_test.read_text(encoding="utf-8-sig")
            if 'VERSION = "0.21.3.4"' in legacy_source:
                print()
                print("=== Legacy Scanner regression note ===")
                print("SKIP: test_scanner_determinism_v0214b234b.py")
                print("Reason: this legacy test hard-codes Scanner VERSION 0.21.3.4,")
                print("while the protected production Scanner is 0.21.3.7.")
                print("HOLD.1-B parity is already verified by test_holdings_analysis_hold1b.py,")
                print("and scanner.py SHA is checked before/after this task.")

        scanner_after = sha256(SCANNER)
        if scanner_after != scanner_before:
            fail("scanner.py changed during HOLD.1-B; STOP.")

        smoke = (
            "import sys\n"
            "sys.path.insert(0, 'backend')\n"
            "from app.holdings import analyze_single_stock\n"
            "r = analyze_single_stock(market='KOSPI', ticker='005930', market_date='2026-09-22')\n"
            "print('HOLD.1-B REAL MARKET STORE: PASS')\n"
            "print('TICKER:', r.ticker)\n"
            "print('MARKET_DATE:', r.market_date)\n"
            "print('STRATEGY:', r.strategy_key)\n"
            "print('ACTION_STATE:', r.action_state)\n"
            "print('RISK_STATE:', r.risk_state)\n"
            "print('REFERENCE_PRICE:', r.reference_price)\n"
            "print('STOP:', r.stop_price)\n"
            "print('TARGET1:', r.target1_price)\n"
            "print('TARGET2:', r.target2_price)\n"
            "print('FINGERPRINT:', r.input_fingerprint[:16] + '...')\n"
            "print('SCANNER_RUN_CALLED: NO')\n"
            "print('KIS_CALLED: NO')\n"
            "print('HOLD_DB_WRITE: NO')\n"
        )
        run(
            [python_exe, "-c", smoke],
            "HOLD.1-B real Market Store smoke",
        )

        if sha256(SCANNER) != scanner_before:
            fail("scanner.py changed after real smoke; STOP.")

        print()
        print("HOLD.1-B CLOSED")
        print("Added:")
        print(" - backend/app/holdings/analysis.py")
        print(" - backend/tests/test_holdings_analysis_hold1b.py")
        print("Modified:")
        print(" - backend/app/holdings/__init__.py (exports only)")
        print("Production Scanner current-path parity: PASS")
        print("Read-only Market Store: PASS")
        print("Scanner.run() called: NO")
        print("Scanner source changed: NO")
        print("Strategy/Risk source changed: NO")
        print("KIS called: NO")
        print("HOLD DB write: NO")
        return 0

    except Exception:
        if init_changed:
            HOLDINGS_INIT.write_text(init_before, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — HOLD.1-B additions were rolled back.")
        print("scanner.py was never modified by this script.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
