from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

from app.backtest.scanner_quality import AuditHorizons, EarlyPruningAuditor, PruningVariant


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
        candidates = sorted({key[1] for key in source if key[0] == market and (end_dd is None or key[1] <= end_dd)})
        return candidates[-1] if candidates else None

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
    QUICK_LIMIT_PER_MARKET = 2
    DEEP_LIMIT = 1

    def __init__(self) -> None:
        self.engine = SimpleNamespace(LIQUIDITY_THRESHOLD=1)

    @staticmethod
    def _special_reason(row):
        return None

    def _quick_current_candidate(self, *, market, latest_date, row, stock_rows, index_rows):
        if not stock_rows:
            return None
        score = float(row["score"])
        return {
            "code": row["code"],
            "name": row["name"],
            "market": market,
            "latest_date": latest_date,
            "current_price": row["close"],
            "trade_value": row["trade_value"],
            "market_cap": row.get("market_cap", 0),
            "history_points": len(stock_rows),
            "quick_strategy": "fake",
            "quick_score": score,
        }

    @staticmethod
    def _current_candidate(item):
        score = float(item["quick_score"])
        return {
            "code": item["code"],
            "name": item["name"],
            "market": item["market"],
            "data_date": "2026-01-30",
            "current_price": item["current_price"],
            "candidate_state": "READY",
            "action": "ENTRY_CANDIDATE",
            "strategy": "fake",
            "conditions": {"passed": 1, "total": 1, "missing": 0, "top_missing": []},
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": {
                "risk": {
                    "entry_reference_price": item["current_price"],
                    "invalidation_price": item["current_price"] * 0.95,
                    "target1_price": item["current_price"] * 1.05,
                    "rr1": 1.0,
                },
                "price_rule": {"kind": "ABOVE", "gap_pct": 0.0, "label": "test"},
            },
            "_strategy_fit_score": score,
            "internal_rank": score,
        }


def make_store() -> FakeStore:
    store = FakeStore()
    analysis = date(2026, 1, 30)
    key = analysis.strftime("%Y%m%d")
    rows = [
        {"code": "000001", "name": "A", "close": 100, "trade_value": 400, "market_cap": 10, "score": 50},
        {"code": "000002", "name": "B", "close": 100, "trade_value": 300, "market_cap": 10, "score": 40},
        {"code": "000003", "name": "C", "close": 100, "trade_value": 200, "market_cap": 10, "score": 99},
        {"code": "000004", "name": "D", "close": 100, "trade_value": 100, "market_cap": 10, "score": 30},
    ]
    store.days[("KOSPI", key)] = rows
    store.index_days[("KOSPI", key)] = {"date": key, "close": 1000}
    for row in rows:
        code = row["code"]
        history = {}
        for offset in range(70):
            day = analysis - timedelta(days=100 - offset)
            if day.weekday() < 5:
                history[day.strftime("%Y%m%d")] = {"date": day.strftime("%Y%m%d"), "close": 100, "high": 101, "low": 99}
        # Give C a strong future path so expanded market pool can reveal it.
        future_price = 100
        for offset in range(1, 35):
            day = analysis + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            if code == "000003":
                future_price += 1.5
            history[day.strftime("%Y%m%d")] = {
                "date": day.strftime("%Y%m%d"),
                "close": future_price,
                "high": future_price + 1,
                "low": future_price - 1,
            }
        store.series[("KOSPI", code)] = history
    return store


def test_variant_isolation_and_candidate_recovery():
    store = make_store()
    auditor = EarlyPruningAuditor(FakeScanner(), store)
    variants = [
        PruningVariant("BASELINE", 2, 1),
        PruningVariant("MARKET_EXPANDED", 4, 1),
        PruningVariant("QUICK_EXPANDED", 2, 2),
        PruningVariant("BOTH_EXPANDED", 4, 2),
    ]
    result = auditor.run_date(
        as_of=date(2026, 1, 30),
        variants=variants,
        market_scope="KOSPI",
        horizons=AuditHorizons((5, 10, 20)),
    )
    assert result["status"] == "OK"
    assert result["variants"]["BASELINE"]["candidates"][0]["code"] == "000001"
    assert result["variants"]["MARKET_EXPANDED"]["candidates"][0]["code"] == "000003"
    assert result["variants"]["QUICK_EXPANDED"]["config"]["market_limit"] == 2
    assert result["variants"]["QUICK_EXPANDED"]["config"]["quick_limit"] == 2
    assert result["baseline_comparisons"]["MARKET_EXPANDED"]["new_candidate_count"] == 1


def test_deterministic_same_input_same_result():
    store = make_store()
    auditor = EarlyPruningAuditor(FakeScanner(), store)
    variants = [PruningVariant("BASELINE", 2, 1), PruningVariant("BOTH_EXPANDED", 4, 2)]
    first = auditor.run_date(as_of=date(2026, 1, 30), variants=variants, market_scope="KOSPI")
    second = auditor.run_date(as_of=date(2026, 1, 30), variants=variants, market_scope="KOSPI")
    first.pop("runtime_seconds", None)
    second.pop("runtime_seconds", None)
    for result in (first, second):
        for variant in (result.get("variants") or {}).values():
            variant.pop("evaluation_runtime_seconds", None)
    assert first == second


def test_future_rows_do_not_affect_candidate_selection():
    store = make_store()
    auditor = EarlyPruningAuditor(FakeScanner(), store)
    variants = [PruningVariant("BASELINE", 2, 1)]
    first = auditor.run_date(as_of=date(2026, 1, 30), variants=variants, market_scope="KOSPI")
    first_code = first["variants"]["BASELINE"]["candidates"][0]["code"]
    # Mutate only future data. Candidate selection must remain unchanged.
    for code in ("000001", "000002"):
        for bas_dd, row in store.series[("KOSPI", code)].items():
            if bas_dd > "20260130":
                row["close"] = 1 if code == "000001" else 9999
                row["high"] = row["close"]
                row["low"] = row["close"]
    second = auditor.run_date(as_of=date(2026, 1, 30), variants=variants, market_scope="KOSPI")
    second_code = second["variants"]["BASELINE"]["candidates"][0]["code"]
    assert first_code == second_code == "000001"


def test_missing_exact_analysis_day_is_skipped():
    store = make_store()
    auditor = EarlyPruningAuditor(FakeScanner(), store)
    result = auditor.run_date(
        as_of=date(2026, 1, 29),
        variants=[PruningVariant("BASELINE", 2, 1)],
        market_scope="KOSPI",
    )
    assert result["status"] == "SKIPPED_INSUFFICIENT_DATA"


def test_temporal_sampling_is_deterministic_and_spread():
    from app.backtest.scanner_quality import discover_temporal_evaluation_dates

    class TemporalStore:
        def __init__(self):
            start = date(2025, 1, 1)
            self.keys = []
            cursor = start
            while len(self.keys) < 200:
                if cursor.weekday() < 5:
                    self.keys.append(cursor.strftime("%Y%m%d"))
                cursor += timedelta(days=1)

        def latest_complete_date(self, market, kind="stock", end_dd=None):
            values = [value for value in self.keys if end_dd is None or value <= end_dd]
            return values[-1] if values else None

        def day_status_range(self, market, start_dd, end_dd):
            return {
                (value, kind): "data"
                for value in self.keys
                if start_dd <= value <= end_dd
                for kind in ("stock", "index")
            }

    store = TemporalStore()
    first, meta1 = discover_temporal_evaluation_dates(
        store,
        market_scope="KOSPI",
        sample_size=80,
        min_date_gap=3,
        min_required_dates=60,
        future_horizon_trading_days=20,
    )
    second, meta2 = discover_temporal_evaluation_dates(
        store,
        market_scope="KOSPI",
        sample_size=80,
        min_date_gap=3,
        min_required_dates=60,
        future_horizon_trading_days=20,
    )
    assert first == second
    assert meta1 == meta2
    assert len(first) >= 60
    assert meta1["effective_min_date_gap"] == 3
    # 180 eligible dates, every third common trading date -> 60 spread samples.
    assert first[0] < first[-1]
    assert (first[-1] - first[0]).days > 150


def _synthetic_candidate(code: str, rank: int, return20: float, event_r: float = 0.5):
    return {
        "rank": rank,
        "market": "KOSPI",
        "code": code,
        "name": code,
        "strategy": "fake",
        "outcome": {
            "forward": {
                "5": {"complete": True, "return_pct": return20 / 4, "event_r": event_r, "event": {"status": "NO_EVENT"}},
                "10": {"complete": True, "return_pct": return20 / 2, "event_r": event_r, "event": {"status": "NO_EVENT"}},
                "20": {"complete": True, "return_pct": return20, "event_r": event_r, "event": {"status": "TARGET1_FIRST"}},
            }
        },
    }


def _top5_metrics(mean_return: float, mean_r: float = 0.5):
    return {
        "horizons": {
            str(h): {
                "complete": 5,
                "mean_return_pct": mean_return * (h / 20),
                "median_return_pct": mean_return * (h / 20),
                "mean_mfe_pct": max(mean_return, 0),
                "mean_mae_pct": min(mean_return, 0),
                "mean_event_r": mean_r,
                "target1_first_count": 2,
                "target1_first_pct": 40.0,
                "stop_first_count": 1,
                "stop_first_pct": 20.0,
            }
            for h in (5, 10, 20)
        }
    }


def test_temporal_validation_pairs_and_trimmed_metric():
    from app.backtest.scanner_quality import build_temporal_validation

    runs = []
    for index in range(60):
        baseline = [_synthetic_candidate(f"A{n}", n, 0.0) for n in range(1, 6)]
        added_return = 500.0 if index == 59 else 5.0
        expanded = [_synthetic_candidate(f"A{n}", n, 0.0) for n in range(1, 5)]
        expanded.append(_synthetic_candidate(f"B{index}", 5, added_return, event_r=1.0))
        # Top5 mean delta is added_return / 5.
        expanded_mean = added_return / 5.0
        runs.append({
            "analysis_date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            "status": "OK",
            "variants": {
                "BASELINE": {
                    "candidates": baseline,
                    "top5_metrics": _top5_metrics(0.0, 0.5),
                    "evaluation_runtime_seconds": 0.1,
                },
                "QUICK_EXPANDED": {
                    "candidates": expanded,
                    "top5_metrics": _top5_metrics(expanded_mean, 0.6),
                    "evaluation_runtime_seconds": 0.2,
                },
            },
        })
    payload = {"runs": runs, "valid_date_count": 60}
    result = build_temporal_validation(payload, minimum_valid_dates=60)
    assert result["changed_date_count"] == 60
    assert result["replacement_pairs"][0]["removed"]["code"] == "A5"
    assert result["replacement_pairs"][0]["added"]["code"] == "B0"
    h20 = result["horizons"]["20"]["all_dates"]
    assert h20["mean_return_delta_pct"] > h20["trimmed_mean_return_delta_pct"]
    assert h20["trimmed_mean_return_delta_pct"] == 1.0
    assert result["runtime"]["expanded_over_baseline_ratio"] == 2.0


def test_temporal_validation_unchanged_top5_is_counted():
    from app.backtest.scanner_quality import build_temporal_validation

    candidates = [_synthetic_candidate(f"A{n}", n, 1.0) for n in range(1, 6)]
    run = {
        "analysis_date": "2025-01-02",
        "status": "OK",
        "variants": {
            "BASELINE": {"candidates": candidates, "top5_metrics": _top5_metrics(1.0), "evaluation_runtime_seconds": 0.1},
            "QUICK_EXPANDED": {"candidates": candidates, "top5_metrics": _top5_metrics(1.0), "evaluation_runtime_seconds": 0.2},
        },
    }
    result = build_temporal_validation({"runs": [run], "valid_date_count": 1}, minimum_valid_dates=60)
    assert result["changed_date_count"] == 0
    assert result["unchanged_date_count"] == 1
    assert result["change_rate_pct"] == 0.0
    assert result["verdict"] == "INCONCLUSIVE"
