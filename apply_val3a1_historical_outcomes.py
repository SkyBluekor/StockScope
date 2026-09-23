from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

CATALOG = BACKEND / "app" / "simulation" / "validation_catalog.py"
OUTCOME = BACKEND / "app" / "simulation" / "validation_outcome.py"
API = BACKEND / "app" / "api" / "simulation.py"
TEST = BACKEND / "tests" / "test_validation_outcome_val3a1.py"
WORKSPACE = FRONTEND / "src" / "components" / "SimulationWorkspace.tsx"
SERVICE = FRONTEND / "src" / "services" / "simulationApi.ts"
CSS = FRONTEND / "src" / "simulation.css"
PACKAGE = FRONTEND / "package.json"

OUTCOME_CONTENT = 'from __future__ import annotations\n\nimport json\nimport sqlite3\nimport statistics\nfrom datetime import datetime, timezone\nfrom decimal import Decimal, InvalidOperation\nfrom pathlib import Path\nfrom typing import Any\n\nfrom .validation_catalog import HistoricalValidationCandidate, HistoricalValidationCatalog\n\n\nDEFAULT_MARKET_STORE_DB = (\n    Path(__file__).resolve().parents[2]\n    / "runtime"\n    / "market_history"\n    / "market_history.db"\n)\n\n\nclass HistoricalValidationOutcomeError(RuntimeError):\n    def __init__(self, code: str, message: str) -> None:\n        super().__init__(message)\n        self.code = code\n        self.message = message\n\n\ndef _decimal(value: Any) -> Decimal | None:\n    if value in (None, ""):\n        return None\n    try:\n        result = Decimal(str(value))\n    except (InvalidOperation, TypeError, ValueError):\n        return None\n    return result if result.is_finite() and result > 0 else None\n\n\ndef _pct(value: Decimal | None, reference: Decimal | None) -> float | None:\n    if value is None or reference is None or reference <= 0:\n        return None\n    return round(float((value - reference) / reference * Decimal("100")), 4)\n\n\ndef _json_dict(raw: str | None) -> dict[str, Any]:\n    if not raw:\n        return {}\n    try:\n        value = json.loads(raw)\n    except json.JSONDecodeError:\n        return {}\n    return value if isinstance(value, dict) else {}\n\n\ndef _candidate_root(snapshot: dict[str, Any]) -> dict[str, Any]:\n    if isinstance(snapshot.get("entry_risk_guide"), dict):\n        return snapshot\n    nested = snapshot.get("candidate")\n    return nested if isinstance(nested, dict) else snapshot\n\n\ndef _plan_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:\n    root = _candidate_root(snapshot)\n    guide = root.get("entry_risk_guide")\n    guide = guide if isinstance(guide, dict) else {}\n    price_rule = guide.get("price_rule")\n    price_rule = price_rule if isinstance(price_rule, dict) else {}\n    risk = guide.get("risk")\n    risk = risk if isinstance(risk, dict) else {}\n    return {\n        "entry_rule": {\n            "kind": str(price_rule.get("kind") or "UNAVAILABLE").upper(),\n            "range_low": price_rule.get("range_low"),\n            "range_high": price_rule.get("range_high"),\n            "trigger_price": price_rule.get("trigger_price"),\n        },\n        "stop_price": _decimal(risk.get("invalidation_price")),\n        "target1_price": _decimal(risk.get("target1_price")),\n        "target2_price": _decimal(risk.get("target2_price")),\n    }\n\n\ndef _entry_comparable(rule: dict[str, Any]) -> bool:\n    kind = str(rule.get("kind") or "").upper()\n    if kind == "RANGE":\n        return _decimal(rule.get("range_low")) is not None and _decimal(rule.get("range_high")) is not None\n    if kind in {"ABOVE", "AT_OR_BELOW"}:\n        return _decimal(rule.get("trigger_price")) is not None\n    return False\n\n\ndef _entry_touched(rule: dict[str, Any], *, low: Decimal, high: Decimal) -> bool:\n    kind = str(rule.get("kind") or "").upper()\n    if kind == "RANGE":\n        lower = _decimal(rule.get("range_low"))\n        upper = _decimal(rule.get("range_high"))\n        if lower is None or upper is None:\n            return False\n        if lower > upper:\n            lower, upper = upper, lower\n        return high >= lower and low <= upper\n    if kind == "ABOVE":\n        trigger = _decimal(rule.get("trigger_price"))\n        return trigger is not None and high >= trigger\n    if kind == "AT_OR_BELOW":\n        trigger = _decimal(rule.get("trigger_price"))\n        return trigger is not None and low <= trigger\n    return False\n\n\nclass HistoricalValidationOutcomeService:\n    """Evaluate stored VAL.1 candidates using D+1..D+20 confirmed local EOD bars."""\n\n    HORIZON = 20\n\n    def __init__(\n        self,\n        catalog: HistoricalValidationCatalog,\n        market_store_db: Path | None = None,\n    ) -> None:\n        self.catalog = catalog\n        self.catalog.initialize()\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n\n    def _market_conn(self) -> sqlite3.Connection:\n        if not self.market_store_db.is_file():\n            raise HistoricalValidationOutcomeError(\n                "VAL3_MARKET_STORE_NOT_FOUND",\n                f"Market Store를 찾을 수 없습니다: {self.market_store_db}",\n            )\n        uri = f"{self.market_store_db.resolve().as_uri()}?mode=ro"\n        conn = sqlite3.connect(uri, uri=True)\n        conn.row_factory = sqlite3.Row\n        conn.execute("PRAGMA query_only=ON")\n        return conn\n\n    @staticmethod\n    def _market_days(\n        conn: sqlite3.Connection,\n        *,\n        market: str,\n        after_date: str,\n        limit: int,\n    ) -> list[str]:\n        rows = conn.execute(\n            """\n            SELECT bas_dd\n            FROM day_status\n            WHERE market=? AND kind=\'stock\' AND status=\'data\' AND bas_dd>?\n            ORDER BY bas_dd\n            LIMIT ?\n            """,\n            (market, after_date.replace("-", ""), int(limit)),\n        ).fetchall()\n        return [str(row["bas_dd"]) for row in rows]\n\n    @staticmethod\n    def _stock_row(\n        conn: sqlite3.Connection,\n        *,\n        market: str,\n        ticker: str,\n        bas_dd: str,\n    ) -> dict[str, Any] | None:\n        row = conn.execute(\n            """\n            SELECT row_json\n            FROM stock_daily\n            WHERE market=? AND stock_code=? AND bas_dd=?\n            """,\n            (market, ticker, bas_dd),\n        ).fetchone()\n        return _json_dict(str(row["row_json"])) if row is not None else None\n\n    @staticmethod\n    def _stock_rows(\n        conn: sqlite3.Connection,\n        *,\n        market: str,\n        ticker: str,\n        first_dd: str,\n        last_dd: str,\n    ) -> dict[str, dict[str, Any]]:\n        rows = conn.execute(\n            """\n            SELECT bas_dd,row_json\n            FROM stock_daily\n            WHERE market=? AND stock_code=? AND bas_dd>=? AND bas_dd<=?\n            ORDER BY bas_dd\n            """,\n            (market, ticker, first_dd, last_dd),\n        ).fetchall()\n        return {\n            str(row["bas_dd"]): _json_dict(str(row["row_json"]))\n            for row in rows\n        }\n\n    @staticmethod\n    def _price(row: dict[str, Any] | None, key: str) -> Decimal | None:\n        return _decimal(row.get(key)) if row else None\n\n    def _evaluate_candidate(\n        self,\n        conn: sqlite3.Connection,\n        candidate: HistoricalValidationCandidate,\n    ) -> dict[str, Any]:\n        signal_key = candidate.trading_date.replace("-", "")\n        signal_row = self._stock_row(\n            conn,\n            market=candidate.market,\n            ticker=candidate.ticker,\n            bas_dd=signal_key,\n        )\n        reference = self._price(signal_row, "close")\n        plan = _plan_from_snapshot(candidate.snapshot)\n\n        market_days = self._market_days(\n            conn,\n            market=candidate.market,\n            after_date=candidate.trading_date,\n            limit=self.HORIZON,\n        )\n        rows_by_day = (\n            self._stock_rows(\n                conn,\n                market=candidate.market,\n                ticker=candidate.ticker,\n                first_dd=market_days[0],\n                last_dd=market_days[-1],\n            )\n            if market_days\n            else {}\n        )\n\n        returns: dict[int, float | None] = {}\n        for horizon in (5, 10, 20):\n            if len(market_days) < horizon:\n                returns[horizon] = None\n                continue\n            horizon_day = market_days[horizon - 1]\n            returns[horizon] = _pct(\n                self._price(rows_by_day.get(horizon_day), "close"),\n                reference,\n            )\n\n        highest: Decimal | None = None\n        lowest: Decimal | None = None\n\n        entry_rule = plan["entry_rule"]\n        entry_comparable = _entry_comparable(entry_rule)\n        entry_touched = False\n        entry_touch_date: str | None = None\n\n        stop = plan["stop_price"]\n        target1 = plan["target1_price"]\n        target2 = plan["target2_price"]\n        stop_touched = False\n        stop_touch_date: str | None = None\n        target1_touched = False\n        target1_touch_date: str | None = None\n        target2_touched = False\n        target2_touch_date: str | None = None\n\n        for bas_dd in market_days:\n            row = rows_by_day.get(bas_dd)\n            high = self._price(row, "high")\n            low = self._price(row, "low")\n            if high is None or low is None:\n                continue\n\n            highest = high if highest is None or high > highest else highest\n            lowest = low if lowest is None or low < lowest else lowest\n            iso = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"\n\n            if entry_comparable and not entry_touched and _entry_touched(entry_rule, low=low, high=high):\n                entry_touched = True\n                entry_touch_date = iso\n\n            # Independent checks: no intraday order is inferred from one daily bar.\n            if stop is not None and not stop_touched and low <= stop:\n                stop_touched = True\n                stop_touch_date = iso\n            if target1 is not None and not target1_touched and high >= target1:\n                target1_touched = True\n                target1_touch_date = iso\n            if target2 is not None and not target2_touched and high >= target2:\n                target2_touched = True\n                target2_touch_date = iso\n\n        return {\n            "validation_id": candidate.validation_id,\n            "trading_date": candidate.trading_date,\n            "market": candidate.market,\n            "ticker": candidate.ticker,\n            "reference_price": None if reference is None else format(reference, "f"),\n            "entry_rule_json": json.dumps(entry_rule, ensure_ascii=False, sort_keys=True, separators=(",", ":")),\n            "stop_price": None if stop is None else format(stop, "f"),\n            "target1_price": None if target1 is None else format(target1, "f"),\n            "target2_price": None if target2 is None else format(target2, "f"),\n            "available_trading_days": len(market_days),\n            "evaluated_through": (\n                f"{market_days[-1][:4]}-{market_days[-1][4:6]}-{market_days[-1][6:8]}"\n                if market_days else None\n            ),\n            "return_5d": returns[5],\n            "return_10d": returns[10],\n            "return_20d": returns[20],\n            "mfe_pct": _pct(highest, reference),\n            "mae_pct": _pct(lowest, reference),\n            "entry_comparable": 1 if entry_comparable else 0,\n            "entry_touched": 1 if entry_touched else 0,\n            "entry_touch_date": entry_touch_date,\n            "stop_comparable": 1 if stop is not None else 0,\n            "stop_touched": 1 if stop_touched else 0,\n            "stop_touch_date": stop_touch_date,\n            "target1_comparable": 1 if target1 is not None else 0,\n            "target1_touched": 1 if target1_touched else 0,\n            "target1_touch_date": target1_touch_date,\n            "target2_comparable": 1 if target2 is not None else 0,\n            "target2_touched": 1 if target2_touched else 0,\n            "target2_touch_date": target2_touch_date,\n            "computed_at": datetime.now(timezone.utc).isoformat(),\n        }\n\n    def refresh(self, validation_id: str) -> dict[str, Any]:\n        draft = self.catalog.get(validation_id)\n        if draft is None:\n            raise HistoricalValidationOutcomeError(\n                "VAL3_VALIDATION_NOT_FOUND",\n                "저장된 Historical Validation을 찾을 수 없습니다.",\n            )\n        if draft.status != "COMPLETED":\n            raise HistoricalValidationOutcomeError(\n                "VAL3_REPLAY_NOT_COMPLETED",\n                "과거 판단 재현이 완료된 검증만 성과를 계산할 수 있습니다.",\n            )\n\n        candidates = self.catalog.list_candidates(validation_id)\n        with self._market_conn() as market_conn:\n            outcomes = [\n                self._evaluate_candidate(market_conn, candidate)\n                for candidate in candidates\n            ]\n\n        with self.catalog.connect() as conn:\n            conn.execute(\n                "DELETE FROM historical_validation_candidate_outcome WHERE validation_id=?",\n                (validation_id,),\n            )\n            if outcomes:\n                conn.executemany(\n                    """\n                    INSERT INTO historical_validation_candidate_outcome(\n                        validation_id,trading_date,market,ticker,\n                        reference_price,entry_rule_json,stop_price,target1_price,target2_price,\n                        available_trading_days,evaluated_through,\n                        return_5d,return_10d,return_20d,mfe_pct,mae_pct,\n                        entry_comparable,entry_touched,entry_touch_date,\n                        stop_comparable,stop_touched,stop_touch_date,\n                        target1_comparable,target1_touched,target1_touch_date,\n                        target2_comparable,target2_touched,target2_touch_date,\n                        computed_at\n                    ) VALUES(\n                        :validation_id,:trading_date,:market,:ticker,\n                        :reference_price,:entry_rule_json,:stop_price,:target1_price,:target2_price,\n                        :available_trading_days,:evaluated_through,\n                        :return_5d,:return_10d,:return_20d,:mfe_pct,:mae_pct,\n                        :entry_comparable,:entry_touched,:entry_touch_date,\n                        :stop_comparable,:stop_touched,:stop_touch_date,\n                        :target1_comparable,:target1_touched,:target1_touch_date,\n                        :target2_comparable,:target2_touched,:target2_touch_date,\n                        :computed_at\n                    )\n                    """,\n                    outcomes,\n                )\n        return self.summary(validation_id)\n\n    def list_outcomes(self, validation_id: str) -> list[dict[str, Any]]:\n        with self.catalog.connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT *\n                FROM historical_validation_candidate_outcome\n                WHERE validation_id=?\n                ORDER BY trading_date,market,ticker\n                """,\n                (validation_id,),\n            ).fetchall()\n        return [dict(row) for row in rows]\n\n    @staticmethod\n    def _metric(\n        rows: list[dict[str, Any]],\n        key: str,\n        *,\n        mature_only: bool = False,\n    ) -> dict[str, Any]:\n        selected = [\n            row\n            for row in rows\n            if not mature_only or int(row.get("available_trading_days") or 0) >= 20\n        ]\n        values = [float(row[key]) for row in selected if row.get(key) is not None]\n        return {\n            "sample_count": len(values),\n            "average_pct": round(sum(values) / len(values), 4) if values else None,\n            "median_pct": round(float(statistics.median(values)), 4) if values else None,\n        }\n\n    @staticmethod\n    def _touch(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:\n        # An immature candidate is not a failed 20D touch case.\n        matured = [\n            row for row in rows\n            if int(row.get("available_trading_days") or 0) >= 20\n        ]\n        comparable = sum(1 for row in matured if int(row.get(f"{prefix}_comparable") or 0) == 1)\n        touched = sum(1 for row in matured if int(row.get(f"{prefix}_touched") or 0) == 1)\n        return {\n            "comparable_count": comparable,\n            "touched_count": touched,\n            "touched_pct": round(touched / comparable * 100.0, 2) if comparable else None,\n        }\n\n    def summary(self, validation_id: str) -> dict[str, Any]:\n        draft = self.catalog.get(validation_id)\n        if draft is None:\n            raise HistoricalValidationOutcomeError(\n                "VAL3_VALIDATION_NOT_FOUND",\n                "저장된 Historical Validation을 찾을 수 없습니다.",\n            )\n\n        with self.catalog.connect() as conn:\n            candidate_row = conn.execute(\n                "SELECT COUNT(*) AS n FROM historical_validation_candidate WHERE validation_id=?",\n                (validation_id,),\n            ).fetchone()\n        total_candidates = int(candidate_row["n"] if candidate_row else 0)\n        rows = self.list_outcomes(validation_id)\n\n        replay = {\n            "target_trading_days": int(draft.trading_day_count),\n            "processed_trading_days": int(draft.processed_day_count),\n            "consistent": (\n                int(draft.trading_day_count) == int(draft.processed_day_count)\n                if draft.status == "COMPLETED" else None\n            ),\n            "last_completed_date": draft.last_completed_date,\n        }\n\n        empty_metric = {"sample_count": 0, "average_pct": None, "median_pct": None}\n        empty_touch = {"comparable_count": 0, "touched_count": 0, "touched_pct": None}\n\n        if not rows:\n            return {\n                "validation_id": validation_id,\n                "status": "NOT_CALCULATED",\n                "replay": replay,\n                "total_candidates": total_candidates,\n                "outcome_count": 0,\n                "evaluated_candidates": 0,\n                "horizons": {\n                    "5d": dict(empty_metric),\n                    "10d": dict(empty_metric),\n                    "20d": dict(empty_metric),\n                },\n                "mfe_20d": dict(empty_metric),\n                "mae_20d": dict(empty_metric),\n                "touches": {\n                    "entry": dict(empty_touch),\n                    "stop": dict(empty_touch),\n                    "target1": dict(empty_touch),\n                    "target2": dict(empty_touch),\n                },\n                "computed_at": None,\n            }\n\n        return {\n            "validation_id": validation_id,\n            "status": "READY",\n            "replay": replay,\n            "total_candidates": total_candidates,\n            "outcome_count": len(rows),\n            "evaluated_candidates": sum(\n                1 for row in rows\n                if row.get("reference_price") is not None\n                and int(row.get("available_trading_days") or 0) > 0\n            ),\n            "horizons": {\n                "5d": self._metric(rows, "return_5d"),\n                "10d": self._metric(rows, "return_10d"),\n                "20d": self._metric(rows, "return_20d"),\n            },\n            "mfe_20d": self._metric(rows, "mfe_pct", mature_only=True),\n            "mae_20d": self._metric(rows, "mae_pct", mature_only=True),\n            "touches": {\n                key: self._touch(rows, key)\n                for key in ("entry", "stop", "target1", "target2")\n            },\n            "computed_at": max(str(row.get("computed_at") or "") for row in rows) or None,\n        }\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport json\nimport sqlite3\nfrom datetime import date, timedelta\nfrom pathlib import Path\n\nfrom app.simulation.validation_catalog import HistoricalValidationCatalog\nfrom app.simulation.validation_outcome import HistoricalValidationOutcomeService\n\n\ndef _business_days(start: date, count: int) -> list[date]:\n    rows: list[date] = []\n    cursor = start\n    while len(rows) < count:\n        if cursor.weekday() < 5:\n            rows.append(cursor)\n        cursor += timedelta(days=1)\n    return rows\n\n\ndef _write_market_db(path: Path) -> tuple[str, list[str]]:\n    signal = date(2026, 1, 2)\n    future = _business_days(signal + timedelta(days=1), 20)\n    signal_key = signal.strftime("%Y%m%d")\n    future_keys = [day.strftime("%Y%m%d") for day in future]\n\n    with sqlite3.connect(path) as conn:\n        conn.executescript(\n            """\n            CREATE TABLE day_status(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                kind TEXT NOT NULL,\n                status TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,kind)\n            );\n            CREATE TABLE stock_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                stock_code TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,stock_code)\n            );\n            """\n        )\n        conn.executemany(\n            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES(\'KOSPI\',?,\'stock\',\'data\')",\n            [(key,) for key in [signal_key, *future_keys]],\n        )\n\n        def row(code: str, key: str, close: float, high: float | None = None, low: float | None = None):\n            payload = {\n                "date": key, "code": code, "open": close,\n                "high": high if high is not None else close + 1,\n                "low": low if low is not None else close - 1,\n                "close": close, "volume": 1000,\n            }\n            conn.execute(\n                "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES(\'KOSPI\',?,?,?)",\n                (key, code, json.dumps(payload)),\n            )\n\n        row("000001", signal_key, 100)\n        for index, key in enumerate(future_keys, start=1):\n            close, high, low = 100 + index, 101 + index, 99 + index\n            if index == 3:\n                high, low = 116, 89\n            if index == 12:\n                high = 126\n            if index == 5:\n                close = 105\n            elif index == 10:\n                close = 110\n            elif index == 20:\n                close = 120\n            row("000001", key, close, high=high, low=low)\n\n        second_signal_key = future_keys[12]\n        row("000002", second_signal_key, 200)\n        for index, key in enumerate(future_keys[13:], start=1):\n            row("000002", key, 200 + index)\n\n    return signal.isoformat(), [f"{key[:4]}-{key[4:6]}-{key[6:8]}" for key in future_keys]\n\n\ndef _snapshot() -> dict:\n    return {\n        "action": "WAIT",\n        "candidate_state": "WATCH",\n        "entry_risk_guide": {\n            "price_rule": {"kind": "RANGE", "range_low": 99, "range_high": 101, "trigger_price": None},\n            "risk": {"invalidation_price": 90, "target1_price": 115, "target2_price": 125},\n        },\n    }\n\n\ndef _validation(tmp_path: Path, signal_date: str, future_dates: list[str]):\n    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")\n    catalog.initialize()\n    draft = catalog.create_draft(\n        name="VAL.3-A1 fixture",\n        market_scope="KOSPI",\n        requested_period_type="custom",\n        requested_start_month="2026-01",\n        requested_end_month="2026-02",\n        resolved_start_date=signal_date,\n        resolved_end_date=future_dates[12],\n        trading_day_count=2,\n    )\n    catalog.save_completed_day(\n        validation_id=draft.id, trading_date=signal_date,\n        scanner_version=draft.scanner_version, market_scope="KOSPI",\n        scanner_cache_hit=False, partial_data=False,\n        input_fingerprint={"fixture": 1}, market_summary={}, summary={}, methodology={},\n        diagnostics={"network_requests": 0},\n        candidates=[{\n            "market": "KOSPI", "ticker": "000001", "name": "Fixture A",\n            "rank": 1, "result_bucket": "TOP",\n            "strategy": "momentum_continuation", "decision_status": "WATCH",\n            "snapshot": _snapshot(),\n        }],\n    )\n    catalog.save_completed_day(\n        validation_id=draft.id, trading_date=future_dates[12],\n        scanner_version=draft.scanner_version, market_scope="KOSPI",\n        scanner_cache_hit=False, partial_data=False,\n        input_fingerprint={"fixture": 2}, market_summary={}, summary={}, methodology={},\n        diagnostics={"network_requests": 0},\n        candidates=[{\n            "market": "KOSPI", "ticker": "000002", "name": "Fixture B",\n            "rank": 1, "result_bucket": "TOP",\n            "strategy": "pullback", "decision_status": "READY",\n            "snapshot": _snapshot(),\n        }],\n    )\n    with catalog.connect() as conn:\n        conn.execute(\n            "UPDATE historical_validation_run SET status=\'COMPLETED\',processed_day_count=trading_day_count WHERE id=?",\n            (draft.id,),\n        )\n    return catalog, draft.id\n\n\ndef test_forward_outcomes_are_d_plus_1_and_maturity_aware(tmp_path: Path):\n    market_db = tmp_path / "market.db"\n    signal_date, future_dates = _write_market_db(market_db)\n    catalog, validation_id = _validation(tmp_path, signal_date, future_dates)\n\n    service = HistoricalValidationOutcomeService(catalog, market_db)\n    summary = service.refresh(validation_id)\n    outcomes = service.list_outcomes(validation_id)\n    first = next(row for row in outcomes if row["ticker"] == "000001")\n    second = next(row for row in outcomes if row["ticker"] == "000002")\n\n    assert first["reference_price"] == "100"\n    assert first["return_5d"] == 5.0\n    assert first["return_10d"] == 10.0\n    assert first["return_20d"] == 20.0\n    assert first["available_trading_days"] == 20\n    assert second["available_trading_days"] == 7\n    assert second["return_5d"] is not None\n    assert second["return_10d"] is None\n    assert second["return_20d"] is None\n    assert summary["horizons"]["5d"]["sample_count"] == 2\n    assert summary["horizons"]["10d"]["sample_count"] == 1\n    assert summary["horizons"]["20d"]["sample_count"] == 1\n    assert summary["replay"]["consistent"] is True\n\n\ndef test_mfe_mae_and_same_day_touch_order_is_not_inferred(tmp_path: Path):\n    market_db = tmp_path / "market.db"\n    signal_date, future_dates = _write_market_db(market_db)\n    catalog, validation_id = _validation(tmp_path, signal_date, future_dates)\n\n    service = HistoricalValidationOutcomeService(catalog, market_db)\n    service.refresh(validation_id)\n    first = next(row for row in service.list_outcomes(validation_id) if row["ticker"] == "000001")\n\n    assert first["mfe_pct"] == 26.0\n    assert first["mae_pct"] == -11.0\n    assert first["entry_touched"] == 1\n    assert first["stop_touched"] == 1\n    assert first["target1_touched"] == 1\n    assert first["target2_touched"] == 1\n    assert first["stop_touch_date"] == first["target1_touch_date"]\n\n\ndef test_market_store_is_read_only_and_scanner_is_not_called() -> None:\n    source = Path("backend/app/simulation/validation_outcome.py").read_text(encoding="utf-8")\n    assert "?mode=ro" in source\n    assert "PRAGMA query_only=ON" in source\n    assert "StockScannerService" not in source\n    assert "KrxProvider" not in source\n    assert "requests." not in source\n    assert "httpx." not in source\n    assert "HistoricalMarketStore(" not in source\n'
CSS_APPEND = '/* VAL.3-A1 — forward outcome summary */\n.sim-outcome-status{margin-top:20px;padding-top:18px;border-top:1px solid var(--border-default)}\n.sim-outcome-head{display:flex;align-items:flex-end;justify-content:space-between;gap:22px}\n.sim-outcome-head h4{margin:3px 0 0;font-size:var(--font-body)}\n.sim-outcome-head p{margin:5px 0 0;color:var(--text-secondary);font-size:var(--font-meta);line-height:1.55}\n.sim-outcome-summary,.sim-outcome-returns{display:grid;border-top:1px solid var(--border-subtle);border-bottom:1px solid var(--border-subtle)}\n.sim-outcome-summary{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:14px}\n.sim-outcome-returns{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:12px}\n.sim-outcome-summary>div,.sim-outcome-returns>div{padding:12px 13px;border-right:1px solid var(--border-subtle)}\n.sim-outcome-summary>div:last-child,.sim-outcome-returns>div:last-child{border-right:0}\n.sim-outcome-summary span,.sim-outcome-returns span{display:block;color:var(--text-muted);font-size:var(--font-meta)}\n.sim-outcome-summary strong,.sim-outcome-returns strong{display:block;margin-top:4px;color:var(--text-primary)}\n.sim-outcome-summary small,.sim-outcome-returns small{display:block;margin-top:3px;color:var(--text-muted);font-size:var(--font-badge)}\n.sim-outcome-touch{width:100%;margin-top:12px;border-collapse:collapse;font-size:var(--font-meta)}\n.sim-outcome-touch th,.sim-outcome-touch td{padding:8px 6px;border-bottom:1px solid var(--border-subtle);text-align:left}\n.sim-outcome-touch th{color:var(--text-muted);font-weight:800}.sim-outcome-touch td{color:var(--text-primary)}\n.sim-outcome-footnote{margin:11px 0 0!important;color:var(--text-muted)!important;font-size:var(--font-meta)!important}\n@media(max-width:800px){.sim-outcome-head{align-items:flex-start;flex-direction:column}.sim-outcome-summary,.sim-outcome-returns{grid-template-columns:repeat(2,minmax(0,1fr))}.sim-outcome-summary>div:nth-child(2),.sim-outcome-returns>div:nth-child(2){border-right:0}}\n@media(max-width:520px){.sim-outcome-summary,.sim-outcome-returns{grid-template-columns:1fr}.sim-outcome-summary>div,.sim-outcome-returns>div{border-right:0}}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        p for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_catalog(source: str) -> str:
    if "historical_validation_candidate_outcome" in source:
        fail("validation_catalog.py already appears to contain VAL.3-A1.")

    anchor = '''                CREATE INDEX IF NOT EXISTS idx_historical_validation_day_status_date
                    ON historical_validation_day(validation_id, status, trading_date);
'''
    addition = '''                CREATE TABLE IF NOT EXISTS historical_validation_candidate_outcome (
                    validation_id TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    reference_price TEXT,
                    entry_rule_json TEXT,
                    stop_price TEXT,
                    target1_price TEXT,
                    target2_price TEXT,
                    available_trading_days INTEGER NOT NULL DEFAULT 0,
                    evaluated_through TEXT,
                    return_5d REAL,
                    return_10d REAL,
                    return_20d REAL,
                    mfe_pct REAL,
                    mae_pct REAL,
                    entry_comparable INTEGER NOT NULL DEFAULT 0,
                    entry_touched INTEGER NOT NULL DEFAULT 0,
                    entry_touch_date TEXT,
                    stop_comparable INTEGER NOT NULL DEFAULT 0,
                    stop_touched INTEGER NOT NULL DEFAULT 0,
                    stop_touch_date TEXT,
                    target1_comparable INTEGER NOT NULL DEFAULT 0,
                    target1_touched INTEGER NOT NULL DEFAULT 0,
                    target1_touch_date TEXT,
                    target2_comparable INTEGER NOT NULL DEFAULT 0,
                    target2_touched INTEGER NOT NULL DEFAULT 0,
                    target2_touch_date TEXT,
                    computed_at TEXT NOT NULL,
                    PRIMARY KEY(validation_id,trading_date,market,ticker),
                    FOREIGN KEY(validation_id,trading_date,market,ticker)
                        REFERENCES historical_validation_candidate(
                            validation_id,trading_date,market,ticker
                        )
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_validation_outcome_validation_date
                    ON historical_validation_candidate_outcome(validation_id,trading_date);

''' + anchor
    return replace_once(source, anchor, addition, "validation outcome schema")


def patch_api(source: str) -> str:
    if "HistoricalValidationOutcomeService" in source:
        fail("simulation.py already appears to contain VAL.3-A1.")

    import_anchor = '''from app.simulation.validation_replay import (
    HistoricalValidationReplayError,
    HistoricalValidationReplayService,
)
'''
    import_new = import_anchor + '''from app.simulation.validation_outcome import (
    HistoricalValidationOutcomeError,
    HistoricalValidationOutcomeService,
)
'''
    source = replace_once(source, import_anchor, import_new, "simulation API outcome import")

    helper_anchor = '''def _validation_replay_service() -> HistoricalValidationReplayService:
    provider = HistoricalMarketStoreProvider()
    return HistoricalValidationReplayService(
        _validation_catalog(),
        provider.store,
    )


def _validation_replay_http_error(code: str, message: str) -> None:
'''
    helper_new = '''def _validation_replay_service() -> HistoricalValidationReplayService:
    provider = HistoricalMarketStoreProvider()
    return HistoricalValidationReplayService(
        _validation_catalog(),
        provider.store,
    )


def _validation_outcome_service() -> HistoricalValidationOutcomeService:
    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
    return HistoricalValidationOutcomeService(
        _validation_catalog(),
        Path(raw) if raw else None,
    )


def _validation_outcome_http_error(error: HistoricalValidationOutcomeError) -> None:
    if error.code == "VAL3_VALIDATION_NOT_FOUND":
        status = 404
    elif error.code == "VAL3_REPLAY_NOT_COMPLETED":
        status = 409
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={"code": error.code, "message": error.message},
    )


def _validation_replay_http_error(code: str, message: str) -> None:
'''
    source = replace_once(source, helper_anchor, helper_new, "simulation API outcome helper")

    endpoint_anchor = '''@router.get(
    "/simulation/validations/{validation_id}/days",
    tags=["simulation-validation"],
)
def list_validation_days(validation_id: str):
    catalog = _validation_catalog()
    item = catalog.get(validation_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "VAL_REPLAY_NOT_FOUND", "message": "저장된 검증을 찾을 수 없습니다."},
        )
    return [_validation_day_payload(day) for day in catalog.list_days(validation_id)]


# --- VAL.2-D: execution validation API lifecycle ---------------------------
'''
    endpoint_new = '''@router.get(
    "/simulation/validations/{validation_id}/days",
    tags=["simulation-validation"],
)
def list_validation_days(validation_id: str):
    catalog = _validation_catalog()
    item = catalog.get(validation_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "VAL_REPLAY_NOT_FOUND", "message": "저장된 검증을 찾을 수 없습니다."},
        )
    return [_validation_day_payload(day) for day in catalog.list_days(validation_id)]


@router.get(
    "/simulation/validations/{validation_id}/outcomes/summary",
    tags=["simulation-validation"],
)
def get_validation_outcome_summary(validation_id: str):
    try:
        return _validation_outcome_service().summary(validation_id)
    except HistoricalValidationOutcomeError as error:
        _validation_outcome_http_error(error)


@router.post(
    "/simulation/validations/{validation_id}/outcomes/refresh",
    tags=["simulation-validation"],
)
def refresh_validation_outcomes(validation_id: str):
    try:
        return _validation_outcome_service().refresh(validation_id)
    except HistoricalValidationOutcomeError as error:
        _validation_outcome_http_error(error)


# --- VAL.2-D: execution validation API lifecycle ---------------------------
'''
    return replace_once(source, endpoint_anchor, endpoint_new, "simulation API outcome endpoints")


def patch_service(source: str) -> str:
    if "HistoricalValidationOutcomeSummary" in source:
        fail("simulationApi.ts already appears to contain VAL.3-A1.")

    anchor = '''export type ValidationReplayResponse = {
  accepted: boolean;
  id: string;
  status: string;
  cancel_requested?: boolean;
};
'''
    types = anchor + '''
export type ValidationOutcomeMetric = {
  sample_count: number;
  average_pct: number | null;
  median_pct: number | null;
};

export type ValidationOutcomeTouch = {
  comparable_count: number;
  touched_count: number;
  touched_pct: number | null;
};

export type HistoricalValidationOutcomeSummary = {
  validation_id: string;
  status: "NOT_CALCULATED" | "READY" | string;
  replay: {
    target_trading_days: number;
    processed_trading_days: number;
    consistent: boolean | null;
    last_completed_date: string | null;
  };
  total_candidates: number;
  outcome_count: number;
  evaluated_candidates: number;
  horizons: {
    "5d": ValidationOutcomeMetric;
    "10d": ValidationOutcomeMetric;
    "20d": ValidationOutcomeMetric;
  };
  mfe_20d: ValidationOutcomeMetric;
  mae_20d: ValidationOutcomeMetric;
  touches: {
    entry: ValidationOutcomeTouch;
    stop: ValidationOutcomeTouch;
    target1: ValidationOutcomeTouch;
    target2: ValidationOutcomeTouch;
  };
  computed_at: string | null;
};
'''
    source = replace_once(source, anchor, types, "simulationApi outcome types")

    fn_anchor = '''export function deleteValidationDraft(id: string) {
'''
    functions = '''export function getValidationOutcomeSummary(id: string) {
  return apiJson<HistoricalValidationOutcomeSummary>(
    `/api/simulation/validations/${encodeURIComponent(id)}/outcomes/summary`,
  );
}

export function refreshValidationOutcomes(id: string) {
  return apiJson<HistoricalValidationOutcomeSummary>(
    `/api/simulation/validations/${encodeURIComponent(id)}/outcomes/refresh`,
    { method: "POST" },
  );
}

''' + fn_anchor
    return replace_once(source, fn_anchor, functions, "simulationApi outcome functions")


def patch_workspace(source: str) -> str:
    if "outcomeSummary" in source:
        fail("SimulationWorkspace.tsx already appears to contain VAL.3-A1.")

    source = replace_once(
        source,
        '''  getValidationDraft,
  listLegacyValidations,
  listValidationDrafts,
''',
        '''  getValidationDraft,
  getValidationOutcomeSummary,
  listLegacyValidations,
  listValidationDrafts,
''',
        "workspace outcome import 1",
    )
    source = replace_once(
        source,
        '''  previewValidationPeriod,
  runValidationReplay,
  SimulationApiError,
  type HistoricalValidationDraft,
''',
        '''  previewValidationPeriod,
  refreshValidationOutcomes,
  runValidationReplay,
  SimulationApiError,
  type HistoricalValidationDraft,
  type HistoricalValidationOutcomeSummary,
''',
        "workspace outcome import 2",
    )

    helper_anchor = '''function replayStatusLabel(row: HistoricalValidationDraft) {
  if (row.status === "RUNNING" && row.runtime_active === false) return "실행 중단됨";
  return statusLabel(row.status);
}
'''
    helper_new = helper_anchor + '''
function pctText(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
function touchText(value: { touched_count: number; comparable_count: number; touched_pct: number | null }) {
  if (value.comparable_count <= 0) return "비교 기준 없음";
  const rate = value.touched_pct == null ? "-" : `${value.touched_pct.toFixed(1)}%`;
  return `${value.touched_count} / ${value.comparable_count} · ${rate}`;
}
'''
    source = replace_once(source, helper_anchor, helper_new, "workspace outcome formatters")

    source = replace_once(
        source,
        '''  const [replayBusy, setReplayBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
''',
        '''  const [replayBusy, setReplayBusy] = useState(false);
  const [outcomeBusy, setOutcomeBusy] = useState(false);
  const [outcomeSummary, setOutcomeSummary] = useState<HistoricalValidationOutcomeSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);
''',
        "workspace outcome state",
    )

    effect_anchor = '''  useEffect(() => { if (mode === "saved") void loadSaved(); }, [mode]);

  useEffect(() => {
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "RUNNING") return;
'''
    effect_new = '''  useEffect(() => { if (mode === "saved") void loadSaved(); }, [mode]);

  useEffect(() => {
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "COMPLETED") {
      setOutcomeSummary(null);
      return;
    }
    let disposed = false;
    setOutcomeBusy(true);
    void getValidationOutcomeSummary(selectedDraft.id)
      .then((summary) => { if (!disposed) setOutcomeSummary(summary); })
      .catch((error) => { if (!disposed) setMessage(errorText(error)); })
      .finally(() => { if (!disposed) setOutcomeBusy(false); });
    return () => { disposed = true; };
  }, [mode, selectedDraft?.id, selectedDraft?.status]);

  useEffect(() => {
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "RUNNING") return;
'''
    source = replace_once(source, effect_anchor, effect_new, "workspace outcome load effect")

    fn_anchor = '''  async function removeDraft(row: HistoricalValidationDraft) {
'''
    fn_new = '''  async function calculateOutcomes(row: HistoricalValidationDraft) {
    if (outcomeBusy || row.status !== "COMPLETED") return;
    setOutcomeBusy(true); setMessage(null);
    try {
      const summary = await refreshValidationOutcomes(row.id);
      setOutcomeSummary(summary);
      setMessage(`'${row.name}' 후보 ${summary.outcome_count}건의 D+1~D+20 성과를 계산했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function removeDraft(row: HistoricalValidationDraft) {
'''
    source = replace_once(source, fn_anchor, fn_new, "workspace outcome action")

    source = source.replace(
        "<th>진행</th><th>상태</th>",
        "<th>재현</th><th>상태</th>",
        1,
    )
    source = source.replace(
        "<td>{row.processed_day_count ?? 0} / {row.trading_day_count}</td>",
        "<td>{row.processed_day_count ?? 0} / {row.trading_day_count}일</td>",
        1,
    )

    source = replace_once(
        source,
        '''              {selectedDraft.status === "COMPLETED" && <p className="sim-replay-note">모든 대상 거래일의 Scanner 판단 저장이 완료되었습니다. 체결·수익률 평가는 다음 검증 단계에서 수행합니다.</p>}
''',
        '''              {selectedDraft.status === "COMPLETED" && <p className="sim-replay-note">모든 대상 거래일의 당시 Scanner 판단을 저장했습니다. 아래 성과 평가는 추천 당일을 제외하고 D+1부터 최대 20거래일까지 실제 확정 일봉을 관측합니다.</p>}
''',
        "workspace replay completion explanation",
    )

    insert_anchor = '''            </div>
          </div>}

          <div className="sim-saved-group sim-legacy-group">
'''
    outcome_block = '''            </div>

            {selectedDraft.status === "COMPLETED" && <div className="sim-outcome-status">
              <div className="sim-outcome-head">
                <div>
                  <span className="sim-section-kicker">후보 실제 결과</span>
                  <h4>성과 평가</h4>
                  <p>추천 당일은 제외하고 D+1~D+20 확정 일봉만 사용합니다. 실제 주문 체결을 의미하지 않습니다.</p>
                </div>
                <button className="sim-secondary" disabled={outcomeBusy} onClick={() => void calculateOutcomes(selectedDraft)}>
                  {outcomeBusy ? "계산 중…" : outcomeSummary?.status === "READY" ? "성과 갱신" : "성과 계산"}
                </button>
              </div>

              {outcomeBusy && !outcomeSummary ? <div className="sim-empty">성과 정보를 확인하는 중…</div> :
              outcomeSummary?.status !== "READY" ? <div className="sim-outcome-summary">
                <div><span>과거 판단 재현</span><strong>{selectedDraft.processed_day_count} / {selectedDraft.trading_day_count} 거래일</strong></div>
                <div><span>저장된 후보</span><strong>{selectedDraft.candidate_count}</strong></div>
                <div><span>성과 평가</span><strong>아직 계산하지 않음</strong></div>
                <div><span>평가 구간</span><strong>D+1 ~ D+20</strong></div>
              </div> : <>
                <div className="sim-outcome-summary">
                  <div><span>과거 판단 재현</span><strong>{outcomeSummary.replay.processed_trading_days} / {outcomeSummary.replay.target_trading_days} 거래일</strong><small>{outcomeSummary.replay.consistent === false ? "저장 건수 확인 필요" : "재현 완료"}</small></div>
                  <div><span>전체 후보</span><strong>{outcomeSummary.total_candidates}</strong></div>
                  <div><span>5D 평가 가능</span><strong>{outcomeSummary.horizons["5d"].sample_count}</strong></div>
                  <div><span>20D 평가 가능</span><strong>{outcomeSummary.horizons["20d"].sample_count}</strong></div>
                </div>
                <div className="sim-outcome-returns">
                  <div><span>5D 평균</span><strong>{pctText(outcomeSummary.horizons["5d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["5d"].sample_count}</small></div>
                  <div><span>10D 평균</span><strong>{pctText(outcomeSummary.horizons["10d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["10d"].sample_count}</small></div>
                  <div><span>20D 평균</span><strong>{pctText(outcomeSummary.horizons["20d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["20d"].sample_count}</small></div>
                  <div><span>20D 중앙값</span><strong>{pctText(outcomeSummary.horizons["20d"].median_pct)}</strong><small>MFE 평균 {pctText(outcomeSummary.mfe_20d.average_pct)} · MAE 평균 {pctText(outcomeSummary.mae_20d.average_pct)}</small></div>
                </div>
                <table className="sim-outcome-touch">
                  <thead><tr><th>가격 조건 관측</th><th>도달 / 비교 가능</th></tr></thead>
                  <tbody>
                    <tr><td>진입 가격 조건</td><td>{touchText(outcomeSummary.touches.entry)}</td></tr>
                    <tr><td>손절 기준</td><td>{touchText(outcomeSummary.touches.stop)}</td></tr>
                    <tr><td>1차 목표</td><td>{touchText(outcomeSummary.touches.target1)}</td></tr>
                    <tr><td>2차 목표</td><td>{touchText(outcomeSummary.touches.target2)}</td></tr>
                  </tbody>
                </table>
                <p className="sim-outcome-footnote">같은 일봉에서 손절·목표가 모두 닿으면 둘 다 기록하며 어떤 가격이 먼저 닿았는지는 추론하지 않습니다. 최근 후보의 10D·20D 데이터가 아직 없으면 해당 표본에서 제외됩니다.</p>
              </>}
            </div>}
          </div>}

          <div className="sim-saved-group sim-legacy-group">
'''
    source = replace_once(source, insert_anchor, outcome_block, "workspace outcome block")

    return replace_once(
        source,
        '''        <div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>과거 시점의 Production Scanner 판단을 실제 거래일별로 재현합니다.</p></div>
''',
        '''        <div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>과거 판단을 거래일별로 재현하고, 저장된 후보가 이후 실제로 어떻게 움직였는지 확인합니다.</p></div>
''',
        "workspace page description",
    )


def patch_css(source: str) -> str:
    if "VAL.3-A1" in source:
        fail("simulation.css already appears to contain VAL.3-A1.")
    return source.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n"


def audit_saved_counts() -> None:
    db = ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
    if not db.is_file():
        print("Saved validation count audit: SKIP (simulation.db not found)")
        return
    try:
        uri = f"{db.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                "SELECT name,trading_day_count,processed_day_count FROM historical_validation_run "
                "WHERE status='COMPLETED' ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
        print()
        print("=== Saved validation count audit ===")
        if not rows:
            print("no completed validation")
        for name, target, processed in rows:
            state = "MATCH" if int(target) == int(processed) else "MISMATCH"
            print(f"{name}: target={target}, processed={processed} -> {state}")
    except Exception as exc:
        print(f"Saved validation count audit: WARNING ({exc})")


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("VAL.3-A1 — Historical Validation 후보별 실제 성과 계산")
    print("Evaluation window: D+1 ~ D+20 market trading days")
    print("Scanner rerun: NO")
    print("External network: NO")
    print("Market Store: READ ONLY")
    print("Tracking source modification: NO")

    required = [CATALOG, API, WORKSPACE, SERVICE, CSS, PACKAGE]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    if OUTCOME.exists() or TEST.exists():
        fail("VAL.3-A1 target file already exists; stop to avoid double apply.")

    originals = {
        CATALOG: CATALOG.read_text(encoding="utf-8-sig"),
        API: API.read_text(encoding="utf-8-sig"),
        WORKSPACE: WORKSPACE.read_text(encoding="utf-8-sig"),
        SERVICE: SERVICE.read_text(encoding="utf-8-sig"),
        CSS: CSS.read_text(encoding="utf-8-sig"),
    }

    preflight = {
        "VAL.1 candidate table": "historical_validation_candidate" in originals[CATALOG],
        "VAL.1 replay endpoint": "/simulation/validations/{validation_id}/run" in originals[API],
        "saved validation UI": "과거 Scanner 재생" in originals[WORKSPACE],
        "candidate count UI": "selectedDraft.candidate_count" in originals[WORKSPACE],
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("Historical Validation source is not in the expected pre-VAL.3-A1 state.")

    protected = {
        "scanner": sha256(BACKEND / "app" / "backtest" / "scanner.py"),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "tracking": tree_hash(BACKEND / "app" / "tracking"),
        "execution_engine": sha256(BACKEND / "app" / "simulation" / "execution_engine.py"),
        "holdings": tree_hash(BACKEND / "app" / "holdings"),
    }
    created: list[Path] = []

    try:
        CATALOG.write_text(patch_catalog(originals[CATALOG]), encoding="utf-8", newline="\n")
        API.write_text(patch_api(originals[API]), encoding="utf-8", newline="\n")
        SERVICE.write_text(patch_service(originals[SERVICE]), encoding="utf-8", newline="\n")
        WORKSPACE.write_text(patch_workspace(originals[WORKSPACE]), encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(originals[CSS]), encoding="utf-8", newline="\n")
        OUTCOME.write_text(OUTCOME_CONTENT, encoding="utf-8", newline="\n")
        created.append(OUTCOME)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        print()
        print("=== VAL.3-A1 STATIC CONTRACT ===")
        catalog_now = CATALOG.read_text(encoding="utf-8")
        api_now = API.read_text(encoding="utf-8")
        outcome_now = OUTCOME.read_text(encoding="utf-8")
        service_now = SERVICE.read_text(encoding="utf-8")
        workspace_now = WORKSPACE.read_text(encoding="utf-8")
        css_now = CSS.read_text(encoding="utf-8")
        package_now = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "outcome persistence table": "historical_validation_candidate_outcome" in catalog_now,
            "D excluded": "bas_dd>?" in outcome_now,
            "20 trading day horizon": "HORIZON = 20" in outcome_now,
            "5D/10D/20D": all(token in outcome_now for token in ("returns[5]", "returns[10]", "returns[20]")),
            "immature horizon null": "if len(market_days) < horizon" in outcome_now,
            "MFE/MAE": '"mfe_pct"' in outcome_now and '"mae_pct"' in outcome_now,
            "touch order not inferred": "Independent checks" in outcome_now,
            "Market Store mode=ro": "?mode=ro" in outcome_now and "PRAGMA query_only=ON" in outcome_now,
            "Scanner not imported": "StockScannerService" not in outcome_now and "KrxProvider" not in outcome_now,
            "summary endpoint": "/outcomes/summary" in api_now,
            "refresh endpoint": "/outcomes/refresh" in api_now,
            "typed frontend summary": "HistoricalValidationOutcomeSummary" in service_now,
            "replay wording": "과거 판단 재현" in workspace_now,
            "no win-rate label": "승률" not in workspace_now,
            "no execution claim": "실제 주문 체결을 의미하지 않습니다" in workspace_now,
            "horizon samples shown": 'horizons["20d"].sample_count' in workspace_now,
            "touch order UI guardrail": "어떤 가격이 먼저 닿았는지는 추론하지 않습니다" in workspace_now,
            "theme tokens": "var(--text-primary)" in css_now and "var(--border-subtle)" in css_now,
            "no theme fork": 'html[data-theme=' not in css_now and ":root" not in css_now,
            "no paid dependency": all(name not in package_now for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            fail(f"Project venv python not found: {python}")

        tests = [
            "backend/tests/test_validation_outcome_val3a1.py",
            "backend/tests/test_simulation_validation_replay_val1b.py",
            "backend/tests/test_simulation_validation_api_val1c.py",
            "backend/tests/test_tracking_performance_track1.py",
        ]
        for name in tests:
            if not (ROOT / name).is_file():
                fail(f"Expected regression test missing: {name}")

        run([str(python), "-m", "pytest", *tests, "-q"], ROOT, "Focused backend regression")

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        protected_after = {
            "scanner": sha256(BACKEND / "app" / "backtest" / "scanner.py"),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "tracking": tree_hash(BACKEND / "app" / "tracking"),
            "execution_engine": sha256(BACKEND / "app" / "simulation" / "execution_engine.py"),
            "holdings": tree_hash(BACKEND / "app" / "holdings"),
        }
        if protected_after != protected:
            fail("Protected Scanner/Strategy/Risk/Tracking/Execution/HOLD source changed.")

        audit_saved_counts()

        print()
        print("VAL.3-A1 IMPLEMENTATION READY")
        print("Added:")
        print(" - backend/app/simulation/validation_outcome.py")
        print(" - backend/tests/test_validation_outcome_val3a1.py")
        print("Modified:")
        print(" - backend/app/simulation/validation_catalog.py")
        print(" - backend/app/api/simulation.py")
        print(" - frontend/src/services/simulationApi.ts")
        print(" - frontend/src/components/SimulationWorkspace.tsx")
        print(" - frontend/src/simulation.css")
        print("D+1 evaluation: PASS")
        print("5D/10D/20D maturity-aware returns: PASS")
        print("20D MFE/MAE: PASS")
        print("Entry/Stop/T1/T2 touch: PASS")
        print("Same-day touch order inference: NO")
        print("Scanner rerun: 0")
        print("External network: 0")
        print("Market Store write: 0 (SQLite mode=ro)")
        print("Tracking source changes: 0")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Open 전략 성과 검증 > 저장된 검증.")
        print(" 2) Open a COMPLETED validation.")
        print(" 3) Confirm the count is labeled 과거 판단 재현.")
        print(" 4) Click 성과 계산.")
        print(" 5) Check 5D/10D/20D sample counts and touch rows.")
        print(" 6) Capture one Dark screenshot.")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — VAL.3-A1 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
