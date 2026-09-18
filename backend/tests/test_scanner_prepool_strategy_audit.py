from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

from app.backtest.scanner_quality.models import AuditHorizons
from app.backtest.scanner_quality.prepool_strategy_audit import (
    BASELINE,
    EXPANDED,
    PrepoolStrategyAuditor,
    compact_prepool_payload,
)


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
    QUICK_LIMIT_PER_MARKET = 6
    DEEP_LIMIT = 3
    MIN_HISTORY_ROWS = 10

    def __init__(self) -> None:
        self.engine = SimpleNamespace(LIQUIDITY_THRESHOLD=1)

    @staticmethod
    def _special_reason(row):
        return None

    @staticmethod
    def _make_quick(*, market, latest_date, row, strategy, score, initial_rank=1):
        close = float(row["close"])
        return {
            "code": row["code"],
            "name": row["name"],
            "market": market,
            "latest_date": latest_date,
            "current_price": close,
            "trade_value": row["trade_value"],
            "market_cap": row.get("market_cap", 0),
            "quick_strategy": strategy,
            "quick_guide": {"label": strategy},
            "quick_current": {
                "status": "READY",
                "total": 1,
                "passed": 1,
                "missing": 0,
                "risk_warning": False,
                "internal_score": float(score),
            },
            "quick_condition_state": {"total": 1, "passed": 1, "missing": 0, "items": []},
            "quick_entry_risk_guide": {
                "risk": {
                    "entry_reference_price": close,
                    "invalidation_price": close * 0.95,
                    "target1_price": close * (1.10 if strategy == "rank4_rescue" else 1.04),
                    "target2_price": close * 1.15,
                    "rr1": 2.0 if strategy == "rank4_rescue" else 0.8,
                    "rr2": 3.0,
                },
                "price_rule": {"kind": "ABOVE", "gap_pct": 0.0, "label": "test"},
            },
            "quick_score": float(score),
            "_audit_initial_strategy_rank": initial_rank,
        }

    @classmethod
    def _quick_current_candidate(cls, *, market, latest_date, row, stock_rows, index_rows):
        if not stock_rows:
            return None
        return cls._make_quick(
            market=market,
            latest_date=latest_date,
            row=row,
            strategy="base",
            score=float(row["score"]),
            initial_rank=1,
        )

    def _strategy_search_audit_evaluate(self, *, market, latest_date, row, stock_rows, index_rows, strategy_limit):
        if not stock_rows:
            return None, [], 0.0
        all_mode = strategy_limit is None
        rescue = bool(row.get("rescue")) and all_mode
        strategy = "rank4_rescue" if rescue else "base"
        selected_rank = 4 if rescue else 1
        score = float(row["score"]) + (15.0 if rescue else 0.0)
        quick = self._make_quick(
            market=market,
            latest_date=latest_date,
            row=row,
            strategy=strategy,
            score=score,
            initial_rank=selected_rank,
        )
        trace = [
            {
                "initial_rank": rank,
                "strategy": "rank4_rescue" if rank == 4 else ("base" if rank == 1 else f"s{rank}"),
                "initial_score": 100 - rank,
                "eligible": True,
                "current_evaluated": all_mode or rank <= 3,
                "selected": rank == selected_rank,
            }
            for rank in range(1, 6)
        ]
        return quick, trace, 0.003 if all_mode else 0.001

    @staticmethod
    def _current_candidate(item):
        if item is None:
            return None
        current = item["quick_current"]
        score = float(current["internal_score"])
        return {
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "data_date": item["latest_date"],
            "current_price": item["current_price"],
            "candidate_state": "READY",
            "action": "ENTRY_CANDIDATE",
            "strategy": item["quick_strategy"],
            "conditions": {"passed": 1, "total": 1, "missing": 0, "top_missing": []},
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": item["quick_entry_risk_guide"],
            "_strategy_fit_score": score,
            "internal_rank": score,
        }


def make_store(*, rescue: bool = True) -> FakeStore:
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
            "score": 101 - idx,  # 100,99,98,97,96,95
            "rescue": rescue and idx == 4,
        })
    store.days[("KOSPI", key)] = rows
    store.index_days[("KOSPI", key)] = {"date": key, "close": 1000}
    for row in rows:
        history = {}
        cursor = analysis - timedelta(days=100)
        while cursor <= analysis + timedelta(days=45):
            if cursor.weekday() < 5:
                step = (cursor - analysis).days
                close = 100.0
                if step > 0:
                    if row["code"] == "000004":
                        close += step * 0.7
                    elif row["code"] == "000003":
                        close -= step * 0.25
                    else:
                        close += step * 0.05
                history[cursor.strftime("%Y%m%d")] = {
                    "date": cursor.strftime("%Y%m%d"),
                    "close": close,
                    "high": close + 1,
                    "low": close - 1,
                }
            cursor += timedelta(days=1)
        store.series[("KOSPI", row["code"])] = history
    return store


def _strip_runtime(result: dict) -> dict:
    result = dict(result)
    result.pop("runtime_seconds", None)
    result["runtime"] = {
        key: value
        for key, value in (result.get("runtime") or {}).items()
        if not key.endswith("seconds")
    }
    for variant in (result.get("variants") or {}).values():
        variant.pop("prepool_evaluation_seconds", None)
    return result


def test_prepool_all_can_rescue_rank4_into_quick18_before_final_ranking():
    result = PrepoolStrategyAuditor(FakeScanner(), make_store()).run_date(
        as_of=date(2026, 1, 30), market_scope="KOSPI", horizons=AuditHorizons((5, 10, 20))
    )
    assert result["status"] == "OK"
    assert result["quick_pool_changed"] is True
    assert result["quick_pool_replacement_count"] == 1
    assert result["rescued_candidate_count"] == 1
    assert result["rescued_top5_count"] == 1
    pair = result["replacement_pairs"][0]
    assert pair["entrant_code"] == "000004"
    assert pair["displaced_code"] == "000003"
    assert pair["rescued"] is True
    assert pair["entrant_all_initial_rank"] == 4
    assert pair["entrant_baseline_quick_rank"] == 4
    assert pair["entrant_all_quick_rank"] == 1
    assert pair["r_20d_delta"] is not None and pair["r_20d_delta"] > 0


def test_variant_isolation_keeps_market_and_quick_limits_fixed():
    result = PrepoolStrategyAuditor(FakeScanner(), make_store()).run_date(
        as_of=date(2026, 1, 30), market_scope="KOSPI"
    )
    assert result["market_limit"] == 6
    assert result["quick_limit"] == 3
    assert result["variants"][BASELINE]["quick_selected_count"] == 3
    assert result["variants"][EXPANDED]["quick_selected_count"] == 3


def test_future_mutation_does_not_change_quick18_or_rescue_detection():
    store = make_store()
    auditor = PrepoolStrategyAuditor(FakeScanner(), store)
    first = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    first_signature = (
        first["quick_pool_replacement_count"],
        first["rescued_candidate_count"],
        [(p["entrant_code"], p["displaced_code"], p["rescued"]) for p in first["replacement_pairs"]],
    )
    for (_, _), rows in store.series.items():
        for bas_dd, row in rows.items():
            if bas_dd > "20260130":
                row["close"] = 9999.0
                row["high"] = 10000.0
                row["low"] = 9998.0
    second = auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI")
    second_signature = (
        second["quick_pool_replacement_count"],
        second["rescued_candidate_count"],
        [(p["entrant_code"], p["displaced_code"], p["rescued"]) for p in second["replacement_pairs"]],
    )
    assert first_signature == second_signature


def test_same_input_is_deterministic_ignoring_timing_fields():
    auditor = PrepoolStrategyAuditor(FakeScanner(), make_store())
    first = _strip_runtime(auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI"))
    second = _strip_runtime(auditor.run_date(as_of=date(2026, 1, 30), market_scope="KOSPI"))
    assert first == second


def test_no_rescue_dates_keep_top3_prepool():
    auditor = PrepoolStrategyAuditor(FakeScanner(), make_store(rescue=False))
    result = auditor.run_dates(dates=[date(2026, 1, 30)] * 4, market_scope="KOSPI")
    validation = result["prepool_strategy_validation"]
    assert validation["quick_pool_changed_date_count"] == 0
    assert validation["rescued_candidate_count"] == 0
    assert validation["verdict"] == "KEEP_TOP3_PREPOOL"


def test_all_strategy_coverage_and_compaction_keep_only_changed_trace():
    auditor = PrepoolStrategyAuditor(FakeScanner(), make_store())
    result = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI")
    validation = result["prepool_strategy_validation"]
    assert validation["runtime"]["baseline_symbol_evaluations"] == 6
    assert validation["runtime"]["all_current_strategy_evaluations"] == 30
    compact = compact_prepool_payload(result)
    trace = compact["runs"][0]["trace"]
    assert set(trace) == {"KOSPI:000003", "KOSPI:000004"}
