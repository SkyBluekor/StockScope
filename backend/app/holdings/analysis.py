from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.backtest.production_exit_policy import production_policy_cache_token
from app.backtest.scanner import StockScannerService
from app.core.config import PROJECT_ROOT


ANALYSIS_ENGINE_VERSION = "HOLD_SINGLE_STOCK_V1"
DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SingleStockAnalysis:
    market: str
    ticker: str
    market_date: str
    strategy_key: str
    action_state: str
    risk_state: str | None
    reference_price: float
    stop_price: float | None
    target1_price: float | None
    target2_price: float | None
    condition_state: dict[str, Any]
    readiness_state: dict[str, Any]
    scanner_version: str
    analysis_engine_version: str
    policy_version: str
    input_fingerprint: str
    source_versions: dict[str, Any]
    snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _NoNetworkProvider:
    """Fails loudly if HOLD.1-B ever drifts into provider/network behavior."""

    def __getattr__(self, name: str) -> Any:
        raise HoldingsAnalysisError(
            "HOLD_ANALYSIS_NETWORK_FORBIDDEN",
            f"Single-stock EOD analysis must not access a provider: {name}",
        )


class _ReadOnlyMarketStore:
    """Minimal read-only view over the existing Market Store SQLite schema."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_MARKET_STORE_NOT_FOUND",
                f"Market Store를 찾을 수 없습니다: {self.db_path}",
            )
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _load(raw: str) -> dict[str, Any]:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    def has_data_day(self, market: str, bas_dd: str, kind: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM day_status
                WHERE market=? AND bas_dd=? AND kind=? AND status='data'
                LIMIT 1
                """,
                (market, bas_dd, kind),
            ).fetchone()
        return row is not None

    def stock_rows(
        self,
        market: str,
        ticker: str,
        start_dd: str,
        end_dd: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT bas_dd,row_json
                FROM stock_daily
                WHERE market=? AND stock_code=? AND bas_dd>=? AND bas_dd<=?
                ORDER BY bas_dd
                """,
                (market, ticker, start_dd, end_dd),
            ).fetchall()
        return [self._load(str(row["row_json"])) for row in rows]

    def exact_stock_row(
        self,
        market: str,
        ticker: str,
        bas_dd: str,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT row_json
                FROM stock_daily
                WHERE market=? AND stock_code=? AND bas_dd=?
                """,
                (market, ticker, bas_dd),
            ).fetchone()
        return self._load(str(row["row_json"])) if row is not None else None

    def index_rows(
        self,
        market: str,
        start_dd: str,
        end_dd: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT bas_dd,row_json
                FROM main_index_daily
                WHERE market=? AND bas_dd>=? AND bas_dd<=?
                ORDER BY bas_dd
                """,
                (market, start_dd, end_dd),
            ).fetchall()
        return [self._load(str(row["row_json"])) for row in rows]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _normalize_market(market: str) -> str:
    value = (market or "").strip().upper()
    if value not in {"KOSPI", "KOSDAQ"}:
        raise HoldingsAnalysisError(
            "HOLD_ANALYSIS_MARKET_INVALID",
            "market은 KOSPI 또는 KOSDAQ이어야 합니다.",
        )
    return value


def _normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip()
    if len(value) != 6 or not value.isdigit():
        raise HoldingsAnalysisError(
            "HOLD_ANALYSIS_TICKER_INVALID",
            "국내주식 종목코드는 6자리 숫자여야 합니다.",
        )
    return value


def _normalize_market_date(market_date: str) -> date:
    try:
        return date.fromisoformat((market_date or "").strip())
    except ValueError as exc:
        raise HoldingsAnalysisError(
            "HOLD_ANALYSIS_DATE_INVALID",
            "market_date는 YYYY-MM-DD 형식이어야 합니다.",
        ) from exc


def _decision_state(candidate_state: str) -> str:
    state = candidate_state.strip().upper()
    if state == "READY":
        return "READY"
    if state in {"WATCH", "VALIDATION"}:
        return "WATCH"
    return "NO_TRADE"


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


class SingleStockAnalysisAdapter:
    """Pure EOD single-stock adapter over the Production Scanner current path.

    It reads Market Store rows in SQLite read-only mode, calls only the Scanner's
    current single-stock helpers, and never calls StockScannerService.run().
    """

    def __init__(
        self,
        *,
        market_store_db: Path | None = None,
        scanner: StockScannerService | None = None,
    ) -> None:
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)
        self.store = _ReadOnlyMarketStore(self.market_store_db)
        self.scanner = scanner or StockScannerService(
            _NoNetworkProvider(),
            market_store=object(),
        )

    def analyze(
        self,
        *,
        market: str,
        ticker: str,
        market_date: str,
    ) -> SingleStockAnalysis:
        clean_market = _normalize_market(market)
        clean_ticker = _normalize_ticker(ticker)
        target_date = _normalize_market_date(market_date)
        end_dd = target_date.strftime("%Y%m%d")

        if not self.store.has_data_day(clean_market, end_dd, "stock"):
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND",
                f"{target_date.isoformat()}의 확정 종목 EOD 데이터가 없습니다.",
            )
        if not self.store.has_data_day(clean_market, end_dd, "index"):
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_BENCHMARK_MISSING",
                f"{target_date.isoformat()}의 확정 시장지수 데이터가 없습니다.",
            )

        current_row = self.store.exact_stock_row(
            clean_market,
            clean_ticker,
            end_dd,
        )
        if current_row is None:
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_STOCK_NOT_FOUND",
                f"{clean_market}/{clean_ticker} 종목을 해당 거래일 Market Store에서 찾을 수 없습니다.",
            )

        fast_start = target_date - timedelta(
            days=self.scanner.FAST_HISTORY_CALENDAR_DAYS
        )
        start_dd = fast_start.strftime("%Y%m%d")
        stock_rows = self.store.stock_rows(
            clean_market,
            clean_ticker,
            start_dd,
            end_dd,
        )
        index_rows = self.store.index_rows(
            clean_market,
            start_dd,
            end_dd,
        )

        if len(stock_rows) < self.scanner.MIN_HISTORY_ROWS:
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_HISTORY_INSUFFICIENT",
                (
                    f"분석에 필요한 종목 이력이 부족합니다: "
                    f"{len(stock_rows)}/{self.scanner.MIN_HISTORY_ROWS}"
                ),
            )
        if not index_rows:
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_BENCHMARK_MISSING",
                "분석 기간의 시장지수 이력이 없습니다.",
            )

        try:
            quick = self.scanner._quick_current_candidate(  # noqa: SLF001
                market=clean_market,
                latest_date=end_dd,
                row=current_row,
                stock_rows=stock_rows,
                index_rows=index_rows,
                sector_input=None,
            )
            if quick is None:
                raise HoldingsAnalysisError(
                    "HOLD_ANALYSIS_FAILED",
                    "Production Scanner current-path snapshot을 만들지 못했습니다.",
                )
            candidate = self.scanner._current_candidate(quick)  # noqa: SLF001
            if candidate is None:
                raise HoldingsAnalysisError(
                    "HOLD_ANALYSIS_FAILED",
                    "Production Scanner current-path 판단을 만들지 못했습니다.",
                )
        except HoldingsAnalysisError:
            raise
        except Exception as exc:
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_FAILED",
                f"단일 종목 EOD 분석에 실패했습니다: {exc}",
            ) from exc

        strategy_key = str(candidate.get("strategy") or "").strip()
        if not strategy_key:
            raise HoldingsAnalysisError(
                "HOLD_ANALYSIS_FAILED",
                "Production Scanner가 전략 식별자를 반환하지 않았습니다.",
            )

        condition_state = dict(quick.get("quick_condition_state") or {})
        readiness_state = dict(quick.get("quick_current") or {})
        entry_risk_guide = dict(candidate.get("entry_risk_guide") or {})
        risk_payload = dict(entry_risk_guide.get("risk") or {})
        candidate_state = str(candidate.get("candidate_state") or "EXCLUDED")
        action_state = _decision_state(candidate_state)
        policy_version = production_policy_cache_token()

        # Hash only rows that can influence the shared current snapshot:
        # stock: technical 60, RS 61, long SMA up to 120; index: RS up to 61.
        fingerprint_stock_rows = stock_rows[-120:]
        fingerprint_index_rows = index_rows[-61:]
        fingerprint_payload = {
            "market": clean_market,
            "ticker": clean_ticker,
            "market_date": target_date.isoformat(),
            "scanner_version": self.scanner.VERSION,
            "scanner_data_integrity_version": self.scanner.DATA_INTEGRITY_VERSION,
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "policy_version": policy_version,
            "stock_rows": fingerprint_stock_rows,
            "index_rows": fingerprint_index_rows,
            "sector_input": None,
        }
        input_fingerprint = hashlib.sha256(
            _canonical_json(fingerprint_payload).encode("utf-8")
        ).hexdigest()

        source_versions = {
            "scanner_version": self.scanner.VERSION,
            "scanner_data_integrity_version": self.scanner.DATA_INTEGRITY_VERSION,
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "policy_version": policy_version,
            "market_store": "market_history.db",
            "price_basis": "CONFIRMED_EOD",
            "fast_history_calendar_days": self.scanner.FAST_HISTORY_CALENDAR_DAYS,
            "stock_history_rows": len(stock_rows),
            "index_history_rows": len(index_rows),
            "fingerprinted_stock_rows": len(fingerprint_stock_rows),
            "fingerprinted_index_rows": len(fingerprint_index_rows),
            "sector_input_mode": "NONE_PRODUCTION_SAFE",
        }

        snapshot = {
            "strategy_key": strategy_key,
            "action_state": action_state,
            "scanner_action": candidate.get("action"),
            "candidate_state": candidate_state,
            "condition_state": condition_state,
            "readiness_state": readiness_state,
            "risk": risk_payload,
            "entry_risk_guide": entry_risk_guide,
            "strategy_trace": dict(quick.get("_strategy_trace") or {}),
            "sector_input_audit": dict(quick.get("_sector_input_audit") or {}),
            "source": {
                "market": clean_market,
                "ticker": clean_ticker,
                "market_date": target_date.isoformat(),
                "stock_history_rows": len(stock_rows),
                "index_history_rows": len(index_rows),
                "price_basis": "CONFIRMED_EOD",
            },
        }

        return SingleStockAnalysis(
            market=clean_market,
            ticker=clean_ticker,
            market_date=target_date.isoformat(),
            strategy_key=strategy_key,
            action_state=action_state,
            risk_state=(
                str(candidate.get("risk", {}).get("status"))
                if candidate.get("risk", {}).get("status") not in (None, "")
                else None
            ),
            reference_price=float(candidate.get("current_price")),
            stop_price=_optional_float(risk_payload.get("invalidation_price")),
            target1_price=_optional_float(risk_payload.get("target1_price")),
            target2_price=_optional_float(risk_payload.get("target2_price")),
            condition_state=condition_state,
            readiness_state=readiness_state,
            scanner_version=self.scanner.VERSION,
            analysis_engine_version=ANALYSIS_ENGINE_VERSION,
            policy_version=policy_version,
            input_fingerprint=input_fingerprint,
            source_versions=source_versions,
            snapshot=snapshot,
        )


def analyze_single_stock(
    *,
    market: str,
    ticker: str,
    market_date: str,
    market_store_db: Path | None = None,
) -> SingleStockAnalysis:
    return SingleStockAnalysisAdapter(
        market_store_db=market_store_db,
    ).analyze(
        market=market,
        ticker=ticker,
        market_date=market_date,
    )
