from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

from app.backtest.scanner_quality.models import AuditHorizons
from app.backtest.scanner_quality.strategy_search_audit import StrategySearchAuditor


@dataclass
class FakeSeries:
    rows: dict[str, dict]


class FakeStore:
    def __init__(self) -> None:
        self.days: dict[tuple[str, str], list[dict]] = {}
        self.index_days: dict[tuple[str, str], dict] = {}
        self.series: dict[tuple[str, str], dict[str, dict]] = {}

    def latest_complete_date(self, market, kind="stock", end_dd=None):
        source = self.days if kind == "stock" else self.index_days
        values = sorted({key[1] for key in source if key[0] == market and (end_dd is None or key[1] <= end_dd)})
        return values[-1] if values else None

    def stock_day_rows(self, market, bas_dd):
        return [dict(row) for row in self.days.get((market, bas_dd), [])]

    def index_series(self, market, start_dd, end_dd):
        rows = {
            bas_dd: dict(row)
            for (mkt, bas_dd), row in self.index_days.items()
            if mkt == market and start_dd <= bas_dd <= end_dd
        }
        return FakeSeries(rows)

    def stock_series_many(self, market, codes, start_dd=None, end_dd=None):
        result = {}
        for code in codes:
            rows = {
                bas_dd: dict(row)
                for bas_dd, row in self.series.get((market, code), {}).items()
                if (start_dd is None or bas_dd >= start_dd) and (end_dd is None or bas_dd <= end_dd)
            }
            result[code] = FakeSeries(rows)
        return result


class FakeScanner:
    VERSION = "test"
    FAST_HISTORY_CALENDAR_DAYS = 220
    QUICK_LIMIT_PER_MARKET = 10
    DEEP_LIMIT = 4
    MIN_HISTORY_ROWS = 10

    def __init__(self) -> None:
        self.engine = SimpleNamespace(LIQUIDITY_THRESHOLD=1)

    @staticmethod
    def _special_reason(row):
        return None

    @staticmethod
    def _quick_current_candidate(*, market, latest_date, row, stock_rows, index_rows):
        if not stock_rows:
            return None
        return {
            "code": row["code"],
            "name": row["name"],
            "market": market,
            "latest_date": latest_date,
            "current_price": row["close"],
            "trade_value": row["trade_value"],
            "market_cap": row.get("market_cap", 0),
            "quick_strategy": "base",
            "quick_score": float(row["score"]),
        }

    def _strategy_search_audit_evaluate(self, *, market, latest_date, row, stock_rows, index_rows, strategy_limit):
        all_mode = strategy_limit is None
        switch = bool(row.get("outside_top3")) and all_mode
        strategy = "rank4_good" if switch else "base"
        initial_rank = 4 if switch else 1
        current_status = "READY" if switch or row.get("ready", True) else "NOT_READY"
        internal_score = float(row["score"]) + (20 if switch else 0)
        quick = {
            "code": row["code"],
            "name": row["name"],
            "market": market,
            "latest_date": latest_date,
            "current_price": row["close"],
            "trade_value": row["trade_value"],
            "market_cap": row.get("market_cap", 0),
            "quick_strategy": strategy,
            "quick_guide": {"label": strategy},
            "quick_current": {
                "status": current_status,
                "total": 1,
                "passed": 1 if current_status == "READY" else 0,
                "missing": 0 if current_status == "READY" else 1,
                "risk_warning": False,
                "internal_score": internal_score,
            },
            "quick_condition_state": {"total": 1, "passed": 1, "missing": 0, "items": []},
            "quick_entry_risk_guide": {
                "risk": {
                    "entry_reference_price": row["close"],
                    "invalidation_price": row["close"] * (0.96 if switch else 0.95),
                    "target1_price": row["close"] * (1.08 if switch else 1.04),
                    "target2_price": row["close"] * 1.12,
                    "rr1": 2.0 if switch else 0.8,
                    "rr2": 3.0,
                },
                "price_rule": {"kind": "ABOVE", "gap_pct": 0.0, "label": "test"},
            },
            "quick_score": internal_score,
            "_audit_initial_strategy_rank": initial_rank,
        }
        trace = [
            {"initial_rank": rank, "strategy": "rank4_good" if rank == 4 else ("base" if rank == 1 else f"s{rank}"),
             "initial_score": 100-rank, "eligible": True, "current_evaluated": all_mode or rank <= 3,
             "selected": rank == initial_rank}
            for rank in range(1, 6)
        ]
        return quick, trace, 0.003 if all_mode else 0.001

    @staticmethod
    def _current_candidate(item):
        if item is None:
            return None
        current = item["quick_current"]
        if current["status"] != "READY" and current.get("missing", 0) > 0:
            state = "WATCH"
            action = "WAIT"
        else:
            state = "READY"
            action = "ENTRY_CANDIDATE"
        score = float(current["internal_score"])
        return {
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "data_date": item["latest_date"],
            "current_price": item["current_price"],
            "candidate_state": state,
            "action": action,
            "strategy": item["quick_strategy"],
            "conditions": {"passed": current["passed"], "total": current["total"], "missing": current["missing"], "top_missing": []},
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": item["quick_entry_risk_guide"],
            "_strategy_fit_score": score,
            "internal_rank": score,
        }


def make_store() -> FakeStore:
    store = FakeStore()
    analysis = date(2026, 1, 30)
    key = analysis.strftime("%Y%m%d")
    rows = []
    for idx in range(1, 7):
        rows.append({
            "code": f"00000{idx}",
            "name": f"S{idx}",
            "close": 100.0,
            "trade_value": 1000 - idx,
            "market_cap": 100,
            "score": 100 - idx,
            "outside_top3": idx in {2, 4},
        })
    store.days[("KOSPI", key)] = rows
    store.index_days[("KOSPI", key)] = {"date": key, "close": 1000}
    for row in rows:
        history = {}
        cursor = analysis - timedelta(days=100)
        while cursor <= analysis + timedelta(days=45):
            if cursor.weekday() < 5:
                step = (cursor - analysis).days
                base = 100.0
                if step > 0 and row["outside_top3"]:
                    base += step * 0.8
                elif step > 0:
                    base += step * 0.1
                history[cursor.strftime("%Y%m%d")] = {
                    "date": cursor.strftime("%Y%m%d"),
                    "close": base,
                    "high": base + 1,
                    "low": base - 1,
                }
            cursor += timedelta(days=1)
        store.series[("KOSPI", row["code"])] = history
    return store


def test_top3_vs_all_detects_outside_strategy_and_keeps_pool_fixed():
    auditor = StrategySearchAuditor(FakeScanner(), make_store())
    result = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI", horizons=AuditHorizons((5, 10, 20)))
    assert result["status"] == "OK"
    assert result["production_quick_pool_count"] == 4
    assert result["outside_top3_selected_count"] == 2
    assert result["strategy_changed_signal_count"] == 2
    assert result["baseline_parity_mismatches"] == 0
    assert result["variants"]["BASELINE_TOP3"]["selected_stock_count"] == result["variants"]["ALL_STRATEGIES"]["selected_stock_count"] == 4


def test_same_input_is_deterministic_ignoring_runtime():
    auditor = StrategySearchAuditor(FakeScanner(), make_store())
    first = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    second = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    for item in (first, second):
        item.pop("runtime_seconds", None)
        for variant in item["variants"].values():
            variant.pop("current_evaluation_seconds", None)
    assert first == second


def test_future_mutation_does_not_change_strategy_selection():
    store = make_store()
    auditor = StrategySearchAuditor(FakeScanner(), store)
    first = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    first_pairs = [(p["code"], p["baseline_strategy"], p["all_strategy"]) for p in first["strategy_pairs"]]
    for (market, code), rows in store.series.items():
        for bas_dd, row in rows.items():
            if bas_dd > "20260130":
                row["close"] = 9999 if code == "000001" else 1
                row["high"] = row["close"]
                row["low"] = row["close"]
    second = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    second_pairs = [(p["code"], p["baseline_strategy"], p["all_strategy"]) for p in second["strategy_pairs"]]
    assert first_pairs == second_pairs


def test_run_dates_can_recommend_expanded_k_when_rank4_5_add_value_but_all_is_slower():
    auditor = StrategySearchAuditor(FakeScanner(), make_store())
    # Reuse one exact local day multiple times only for verdict fixture purposes.
    dates = [date(2026, 1, 30)] * 6
    result = auditor.run_dates(dates=dates, market_scope="KOSPI")
    validation = result["strategy_search_validation"]
    assert validation["outside_top3_selected_count"] >= 6
    assert validation["runtime"]["all_over_top3_ratio"] == 3.0
    assert validation["verdict"] in {"CONSIDER_EXPANDED_K", "CONSIDER_ALL", "INCONCLUSIVE"}
