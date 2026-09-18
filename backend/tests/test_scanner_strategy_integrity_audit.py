from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backtest.scanner_quality.models import AuditHorizons
from app.backtest.scanner_quality.strategy_integrity_audit import (
    BASELINE,
    BREAKOUT_RS_CONDITION,
    MA120_CONDITION,
    MA120_FIXED,
    RS_KEEP_4,
    RS_KEEP_8,
    RS_RESTORE_10_8,
    _restore_breakout_evaluation,
    StrategyIntegrityAuditor,
    _breakout_rs_definition_from_source,
    _dedup_exact_condition,
    _eligible_threshold_from_source,
    _sma,
    _validate_breakout_rs_definition,
    compact_integrity_payload,
    write_integrity_outputs,
)


@dataclass(frozen=True)
class Eval:
    strategy: str
    score: int
    eligible: bool
    reasons: list[str]
    unmet: list[str]
    passed: int
    total: int


@dataclass(frozen=True)
class Input:
    current_price: float
    ma20: float | None
    ma60: float | None
    ma120: float | None
    relative_strength_market_pct: float | None = 2.0
    relative_strength_sector_pct: float | None = None


class Series:
    def __init__(self, rows):
        self.rows = rows


class Store:
    def __init__(self, rows_count: int = 130, codes: tuple[str, ...] = ("000001", "000002"), *, include_future: bool = False):
        self.analysis = date(2026, 1, 30)
        key = self.analysis.strftime("%Y%m%d")
        self.days = {
            ("KOSPI", key): [
                {"code": code, "name": f"N{idx+1}", "close": 200.0 - idx * 10, "trade_value": 1000 - idx * 10, "market_cap": 100 - idx}
                for idx, code in enumerate(codes)
            ]
        }
        self.index_days = {("KOSPI", key): {"date": key, "close": 1000.0}}
        self.series = {}
        for idx, code in enumerate(codes):
            base = 100.0 - idx * 3
            hist = {}
            cursor = self.analysis - timedelta(days=230)
            weekdays = []
            while cursor <= self.analysis:
                if cursor.weekday() < 5:
                    weekdays.append(cursor)
                cursor += timedelta(days=1)
            weekdays = weekdays[-rows_count:]
            for i, day in enumerate(weekdays):
                close = base + i * 0.7
                hist[day.strftime("%Y%m%d")] = {
                    "date": day.strftime("%Y%m%d"), "close": close, "high": close + 1, "low": close - 1
                }
            if include_future:
                day = self.analysis + timedelta(days=1)
                added = 0
                while added < 25:
                    if day.weekday() < 5:
                        close = 5000.0 + added * 100
                        hist[day.strftime("%Y%m%d")] = {"date": day.strftime("%Y%m%d"), "close": close, "high": close + 2, "low": close - 2}
                        added += 1
                    day += timedelta(days=1)
            self.series[("KOSPI", code)] = hist

    def latest_complete_date(self, market, kind, end_dd):
        if kind == "stock":
            keys = [d for (m, d) in self.days if m == market and d <= end_dd]
        else:
            keys = [d for (m, d) in self.index_days if m == market and d <= end_dd]
        return max(keys) if keys else None

    def stock_day_rows(self, market, bas_dd):
        return list(self.days.get((market, bas_dd), []))

    def index_series(self, market, start_dd, end_dd):
        rows = {d: r for (m, d), r in self.index_days.items() if m == market and start_dd <= d <= end_dd}
        return Series(rows)

    def stock_series_many(self, market, codes, start_dd, end_dd):
        result = {}
        for code in codes:
            rows = {d: r for d, r in self.series[(market, code)].items() if start_dd <= d <= end_dd}
            result[code] = Series(rows)
        return result


class Scanner:
    VERSION = "test"
    FAST_HISTORY_CALENDAR_DAYS = 220
    QUICK_LIMIT_PER_MARKET = 10
    DEEP_LIMIT = 2
    MIN_HISTORY_ROWS = 61

    def __init__(self, profiles: dict[str, dict] | None = None, *, bad_source: bool = False):
        self.engine = SimpleNamespace(LIQUIDITY_THRESHOLD=1)
        self.profiles = profiles or {}
        self.bad_source = bad_source

    def _strategy_integrity_audit_breakout_source(self):
        weights = [1.0, 4.0, 8.0] if self.bad_source else [4.0, 8.0]
        return {
            "source_file": "fixture/app/strategy/engine.py",
            "condition_label": BREAKOUT_RS_CONDITION,
            "market_weights": [6.0],
            "duplicate_count": len(weights),
            "weights": weights,
            "predicate_equivalent": True,
            "entries": [{"weight": value, "predicate_ast": "same"} for value in weights],
            "eligible_score_threshold": 40.0,
        }

    @staticmethod
    def _special_reason(row):
        return None

    def _profile(self, code: str) -> dict:
        return {
            "trend_score": 95,
            "breakout_score": 100,
            "duplicate_pass": True,
            **self.profiles.get(code, {}),
        }

    def _strategy_integrity_audit_snapshot(self, *, market, latest_date, row, stock_rows, index_rows):
        closes = [float(r["close"]) for r in stock_rows]
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        profile = self._profile(row["code"])
        data = Input(current_price=float(row["close"]), ma20=ma20, ma60=ma60, ma120=None)
        trend = Eval(
            "trend_following", int(profile["trend_score"]), True,
            ["현재가가 20일 이동평균선 위"], [MA120_CONDITION], 8, 9,
        )
        if profile["duplicate_pass"]:
            breakout_reasons = [BREAKOUT_RS_CONDITION, BREAKOUT_RS_CONDITION]
            breakout_unmet = []
            passed = 2
        else:
            breakout_reasons = []
            breakout_unmet = [BREAKOUT_RS_CONDITION, BREAKOUT_RS_CONDITION]
            passed = 0
        breakout_score = int(profile["breakout_score"])
        breakout = Eval(
            "breakout", breakout_score, breakout_score >= 40,
            breakout_reasons, breakout_unmet, passed, 2,
        )
        return {
            "strategy_input": data,
            "technical": {},
            "evaluations": {"trend_following": trend, "breakout": breakout},
        }

    @staticmethod
    def _strategy_integrity_audit_revaluate(*, snapshot, strategy_input):
        result = dict(snapshot["evaluations"])
        trend = result["trend_following"]
        if strategy_input.ma120 is not None and strategy_input.ma60 > strategy_input.ma120:
            result["trend_following"] = replace(
                trend,
                score=max(120, trend.score + 12),
                eligible=True,
                reasons=trend.reasons + [MA120_CONDITION],
                unmet=[],
                passed=9,
                total=9,
            )
        return result

    @staticmethod
    def _strategy_integrity_audit_quick_from_snapshot(*, snapshot, market, latest_date, row, strategy_limit):
        evaluations = sorted(
            snapshot["evaluations"].values(),
            key=lambda x: (bool(x.eligible), x.score),
            reverse=True,
        )[:strategy_limit]
        best = evaluations[0]
        score = float(best.score)
        close = float(row["close"])
        quick = {
            "code": row["code"], "name": row["name"], "market": market, "latest_date": latest_date,
            "current_price": close, "trade_value": row["trade_value"], "market_cap": row["market_cap"],
            "quick_strategy": best.strategy,
            "quick_current": {"status": "READY", "total": best.total, "passed": best.passed,
                              "missing": len(best.unmet), "risk_warning": False, "internal_score": score},
            "quick_condition_state": {"total": best.total, "passed": best.passed, "missing": len(best.unmet), "items": []},
            "quick_entry_risk_guide": {"risk": {"entry_reference_price": close, "invalidation_price": close * .95,
                                                  "target1_price": close * 1.05, "target2_price": close * 1.10,
                                                  "rr1": 1.0, "rr2": 2.0},
                                       "price_rule": {"kind": "ABOVE", "gap_pct": 0.0, "label": "test"}},
            "quick_score": score,
        }
        trace = [{"initial_rank": i + 1, "strategy": e.strategy, "initial_score": e.score, "selected": i == 0}
                 for i, e in enumerate(evaluations)]
        return quick, trace

    @staticmethod
    def _current_candidate(item):
        score = float(item["quick_score"])
        return {
            "code": item["code"], "name": item["name"], "market": item["market"], "data_date": item["latest_date"],
            "current_price": item["current_price"], "candidate_state": "READY", "action": "ENTRY_CANDIDATE",
            "strategy": item["quick_strategy"], "conditions": {"passed": 1, "total": 1, "missing": 0, "top_missing": []},
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": item["quick_entry_risk_guide"], "_strategy_fit_score": score, "internal_rank": score,
        }


class OneSlotScanner(Scanner):
    DEEP_LIMIT = 1


def test_sma120_requires_120_rows():
    rows = [{"close": float(i)} for i in range(1, 120)]
    assert _sma(rows, 120) is None
    rows.append({"close": 120.0})
    assert _sma(rows, 120) == 60.5


def test_exact_breakout_ast_detection_ignores_unrelated_numbers(tmp_path: Path):
    source = tmp_path / "engine.py"
    source.write_text(
        '''\nclass X:\n    noise = 1.0\n    def _evaluate(self, score):\n        eligible = score >= 40\n        return eligible\n    def _breakout(self, d):\n        return self._evaluate(0, [\n            ("20일 시장 대비 상대강도 양호", 6, lambda x: x.relative_strength_market_pct > 0),\n            ("20일 업종 대비 상대강도 양호", 4, lambda x: x.relative_strength_sector_pct > 0 if x.relative_strength_sector_pct is not None else x.relative_strength_market_pct > 0),\n            ("20일 업종 대비 상대강도 양호", 8, lambda x: x.relative_strength_sector_pct > 0 if x.relative_strength_sector_pct is not None else x.relative_strength_market_pct > 0),\n        ])\n''',
        encoding="utf-8",
    )
    definition = _breakout_rs_definition_from_source(source)
    assert definition is not None
    assert definition["market_weights"] == [6.0]
    assert definition["weights"] == [4.0, 8.0]
    assert definition["duplicate_count"] == 2
    assert definition["predicate_equivalent"] is True
    assert _eligible_threshold_from_source(source) == 40.0


def test_fail_fast_rejects_broad_wrong_weight_candidates():
    with pytest.raises(RuntimeError, match=r"expected exactly two equivalent Breakout RS conditions"):
        StrategyIntegrityAuditor(Scanner(bad_source=True), Store())


def test_pass_only_score_removal_and_original_is_immutable():
    original = Eval("breakout", 100, True, [BREAKOUT_RS_CONDITION, BREAKOUT_RS_CONDITION], [], 2, 2)
    fixed, meta = _dedup_exact_condition(original, BREAKOUT_RS_CONDITION, 8, eligible_threshold=40)
    assert meta["passed_duplicate_removed"] is True
    assert fixed.score == 92
    assert fixed.reasons == [BREAKOUT_RS_CONDITION]
    assert fixed.total == 1 and fixed.passed == 1
    assert original.score == 100 and original.reasons == [BREAKOUT_RS_CONDITION, BREAKOUT_RS_CONDITION]

    failed = Eval("breakout", 100, True, [], [BREAKOUT_RS_CONDITION, BREAKOUT_RS_CONDITION], 0, 2)
    fixed_failed, failed_meta = _dedup_exact_condition(failed, BREAKOUT_RS_CONDITION, 8, eligible_threshold=40)
    assert failed_meta["passed_duplicate_removed"] is False
    assert fixed_failed.score == 100
    assert fixed_failed.unmet == [BREAKOUT_RS_CONDITION]
    assert fixed_failed.total == 1


def test_keep4_removes_8_keep8_removes_4_and_reselects_strategy():
    scanner = Scanner(profiles={"000001": {"trend_score": 95, "breakout_score": 100}})
    auditor = StrategyIntegrityAuditor(scanner, Store(codes=("000001",)))
    result = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    run = result["runs"][0]
    trace = run["trace"]["KOSPI:000001"]
    assert result["strategy_integrity_validation"]["breakout_rs"]["detected_duplicate_weights"] == [4.0, 8.0]
    assert trace["baseline_quick_strategy"] == "breakout"
    assert trace["rs_keep4_removed_weight"] == 8.0
    assert trace["rs_keep4_quick_strategy"] == "trend_following"  # 100-8=92 < 95
    assert trace["rs_keep8_removed_weight"] == 4.0
    assert trace["rs_keep8_quick_strategy"] == "breakout"  # 100-4=96 > 95


def test_quick18_and_top5_propagation_from_dedup():
    profiles = {
        "000001": {"trend_score": 95, "breakout_score": 100},
        "000002": {"trend_score": 97, "breakout_score": 60},
    }
    auditor = StrategyIntegrityAuditor(OneSlotScanner(profiles=profiles), Store(codes=("000001", "000002")))
    result = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    run = result["runs"][0]
    assert run["variants"][BASELINE]["quick_selected_keys"] == ["KOSPI:000001"]
    assert run["variants"][RS_KEEP_4]["quick_selected_keys"] == ["KOSPI:000002"]
    assert run["comparisons"][RS_KEEP_4]["quick_pool_changed"] is True
    assert run["comparisons"][RS_KEEP_4]["top5_changed"] is True


def test_ma120_counterfactual_regression_is_preserved():
    auditor = StrategyIntegrityAuditor(Scanner(), Store(rows_count=130))
    result = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    ma = result["strategy_integrity_validation"]["ma120"]
    assert ma["verdict"] == "CONFIRMED_MA120_INPUT_DEFECT"
    assert ma["availability_count"] == 0
    assert ma["condition_missing_count"] == 2
    assert ma["would_pass_if_sma120_available_count"] == 2
    assert ma["counterfactual_supported"] == 2


def test_future_rows_do_not_change_current_selection():
    profiles = {"000001": {"trend_score": 95, "breakout_score": 100}}
    auditor_a = StrategyIntegrityAuditor(Scanner(profiles=profiles), Store(codes=("000001",), include_future=False))
    auditor_b = StrategyIntegrityAuditor(Scanner(profiles=profiles), Store(codes=("000001",), include_future=True))
    a = auditor_a.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    b = auditor_b.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    for variant in (BASELINE, MA120_FIXED, RS_KEEP_4, RS_KEEP_8, RS_RESTORE_10_8):
        assert a["runs"][0]["variants"][variant]["quick_selected_keys"] == b["runs"][0]["variants"][variant]["quick_selected_keys"]


def test_inspect_mode_stays_inconclusive_and_reports_variant_stats():
    auditor = StrategyIntegrityAuditor(Scanner(), Store())
    result = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    validation = result["strategy_integrity_validation"]
    assert validation["overall_verdict"] == "INCONCLUSIVE"
    assert validation["rs_policy_verdict"] == "INCONCLUSIVE"
    assert validation["rs_variants"][RS_KEEP_4]["removed_weight"] == 8.0
    assert validation["rs_variants"][RS_KEEP_8]["removed_weight"] == 4.0


def test_output_writer_emits_four_files_and_hotfix_summary(tmp_path: Path):
    auditor = StrategyIntegrityAuditor(Scanner(), Store())
    payload = auditor.run_dates(
        dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect", horizons=AuditHorizons((5, 10, 20))
    )
    compact = compact_integrity_payload(payload)
    paths = write_integrity_outputs(compact, output_dir=tmp_path)
    assert set(paths) == {"json", "csv", "pairs_csv", "markdown"}
    assert all(Path(path).exists() for path in paths.values())
    summary = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "Detected duplicate weights: **[4.0, 8.0]**" in summary
    assert "### RS_KEEP_4" in summary
    assert "### RS_KEEP_8" in summary
    assert "### RS_RESTORE_10_8" in summary
    assert "v0.21.4-B.2.3.4c.4b" in summary
    assert "Historical intended: market 10 + sector 8" in summary


@pytest.mark.parametrize("market,sector,baseline_score,restore_score,baseline_passed,restore_passed", [
    (2, 1, 100, 100, 9, 8),
    (2, 0, 88, 92, 7, 7),
    (0, 1, 94, 90, 8, 7),
    (0, 0, 82, 82, 6, 6),
    (2, None, 100, 100, 9, 8),
    (0, None, 82, 82, 6, 6),
    (2, -1, 88, 92, 7, 7),
    (-1, 1, 94, 90, 8, 7),
    (-1, -1, 82, 82, 6, 6),
])
def test_restore_sector_cases(market, sector, baseline_score, restore_score, baseline_passed, restore_passed):
    from app.strategy import StrategyEngine, StrategyInput, MarketRegime
    data = StrategyInput(code="test", market="KOSPI", current_price=100,
                         ma20=90, ma20_slope_pct=1, volume_ratio_20=2,
                         distance_to_20d_high_pct=1, rsi14=60,
                         market_regime=MarketRegime.TREND_UP,
                         relative_strength_market_pct=market, relative_strength_sector_pct=sector)
    baseline = StrategyEngine()._breakout(data)
    original = baseline.to_dict()
    restored, metadata = _restore_breakout_evaluation(data, baseline)
    assert baseline.score == baseline_score and restored.score == restore_score
    assert (baseline.passed, restored.passed) == (baseline_passed, restore_passed)
    assert (baseline.total, restored.total) == (9, 8)
    assert restored.eligible == (restore_score >= 40)
    assert len(restored.reasons) == restored.passed
    assert len(restored.reasons) + len(restored.unmet) == restored.total
    assert (restored.reasons + restored.unmet).count(BREAKOUT_RS_CONDITION) == 1
    assert metadata["market_weight"] == 10
    assert metadata["sector_weights"] == [8] and metadata["sector_condition_count"] == 1
    assert baseline.to_dict() == original


@pytest.mark.parametrize("market_weights", [[], [4], [8], [6, 6]])
def test_fail_fast_rejects_changed_market_definition(market_weights):
    report = {"breakout_rs_definition": Scanner()._strategy_integrity_audit_breakout_source()}
    report["breakout_rs_definition"]["market_weights"] = market_weights
    with pytest.raises(RuntimeError, match="market_weights"):
        _validate_breakout_rs_definition(report)


def test_actual_baseline_definition_and_production_invariant():
    import hashlib
    from app.strategy import StrategyEngine, StrategyInput
    import inspect
    path = Path(inspect.getfile(StrategyEngine))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    definition = _breakout_rs_definition_from_source(path)
    assert definition["market_weights"] == [6]
    assert definition["weights"] == [4, 8]
    _validate_breakout_rs_definition({"breakout_rs_definition": definition})
    data = StrategyInput(code="test", market="KOSPI", current_price=100)
    baseline = StrategyEngine()._breakout(data)
    restored, _ = _restore_breakout_evaluation(data, baseline)
    assert restored.eligible is False
    assert StrategyEngine()._breakout(data).to_dict() == baseline.to_dict()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


class RestorePathScanner(OneSlotScanner):
    def _strategy_integrity_audit_snapshot(self, **kwargs):
        from app.strategy import StrategyEngine, StrategyInput, MarketRegime
        snapshot = super()._strategy_integrity_audit_snapshot(**kwargs)
        code = kwargs["row"]["code"]
        data = StrategyInput(code=code, market="KOSPI", current_price=200,
                             ma20=190, ma60=180, ma20_slope_pct=1, rsi14=60,
                             volume_ratio_20=2, distance_to_20d_high_pct=1,
                             market_regime=MarketRegime.TREND_UP,
                             relative_strength_market_pct=2,
                             relative_strength_sector_pct=-1 if code == "000001" else 1)
        snapshot["strategy_input"] = data
        snapshot["evaluations"]["breakout"] = StrategyEngine()._breakout(data)
        snapshot["evaluations"]["trend_following"] = replace(snapshot["evaluations"]["trend_following"], score=90)
        return snapshot


def test_restore_reselection_quick18_top5_and_full_metrics():
    scanner = RestorePathScanner()
    auditor = StrategyIntegrityAuditor(scanner, Store(include_future=True))
    payload = auditor.run_dates(dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="full")
    run = payload["runs"][0]
    stats = payload["strategy_integrity_validation"]["rs_variants"][RS_RESTORE_10_8]
    assert stats["condition_count_changed_signals"] == 2
    assert stats["score_changed_signals"] == 1
    assert stats["other_to_breakout"] == 1
    assert run["trace"]["KOSPI:000001"]["baseline_quick_strategy"] == "trend_following"
    assert run["trace"]["KOSPI:000001"]["rs_restore_quick_strategy"] == "breakout"
    for horizon in ("5", "10", "20"):
        metric = stats["impact"]["horizons"][horizon]
        for key in ("mean_return_delta_pct", "median_return_delta_pct", "trimmed_return_delta_pct",
                    "mean_r_delta", "median_r_delta", "target1_first_delta_pct", "stop_first_delta_pct",
                    "mfe_delta_pct", "mae_delta_pct"):
            assert metric[key] is not None
    assert RS_RESTORE_10_8 in run["variants"]


def test_restore_changes_pool_and_top5_when_market_and_sector_disagree():
    class OpposingScanner(RestorePathScanner):
        def _strategy_integrity_audit_snapshot(self, **kwargs):
            from app.strategy import StrategyEngine
            snapshot = super()._strategy_integrity_audit_snapshot(**kwargs)
            code = kwargs["row"]["code"]
            data = replace(snapshot["strategy_input"],
                           relative_strength_market_pct=2 if code == "000001" else -2,
                           relative_strength_sector_pct=-1 if code == "000001" else 1)
            snapshot["strategy_input"] = data
            snapshot["evaluations"]["breakout"] = StrategyEngine()._breakout(data)
            snapshot["evaluations"]["trend_following"] = replace(snapshot["evaluations"]["trend_following"], score=80)
            return snapshot
    payload = StrategyIntegrityAuditor(OpposingScanner(), Store()).run_dates(
        dates=[date(2026, 1, 30)], market_scope="KOSPI", mode="inspect")
    run = payload["runs"][0]
    assert run["variants"][BASELINE]["quick_selected_keys"] == ["KOSPI:000002"]
    assert run["variants"][RS_RESTORE_10_8]["quick_selected_keys"] == ["KOSPI:000001"]
    assert run["comparisons"][RS_RESTORE_10_8]["quick_pool_changed"]
    assert run["comparisons"][RS_RESTORE_10_8]["top5_changed"]


@pytest.mark.parametrize("gate", [{"event_risk": True}, {"tradable": False}, {"liquidity_ok": False}])
def test_restore_preserves_risk_gate(gate):
    from app.strategy import StrategyEngine, StrategyInput
    data = StrategyInput(code="test", market="KOSPI", current_price=100, **gate)
    baseline = next(e for e in StrategyEngine().evaluate_all(data) if str(e.strategy) == "breakout")
    restored, _ = _restore_breakout_evaluation(data, baseline)
    assert baseline.eligible is False and restored.eligible is False


def test_same_score_fallback_rebuilds_real_readiness_and_quick_score():
    from app.backtest.scanner import StockScannerService
    from app.strategy import StrategyEngine, StrategyInput, MarketRegime
    scanner = StockScannerService(SimpleNamespace(), market_store=Store())
    auditor = StrategyIntegrityAuditor(scanner, Store())
    # RSI fails while all RS conditions pass: normalized score stays 90,
    # but condition ratio changes from 8/9 to 7/8.
    data = StrategyInput(code="000001", market="KOSPI", current_price=200,
                         ma20=190, ma60=180, ma20_slope_pct=1, rsi14=80,
                         volume_ratio_20=2, distance_to_20d_high_pct=1,
                         market_regime=MarketRegime.TREND_UP,
                         relative_strength_market_pct=2, relative_strength_sector_pct=None,
                         support_price=190, resistance_price=210, atr_pct=2)
    baseline = StrategyEngine()._breakout(data)
    restored, _ = _restore_breakout_evaluation(data, baseline)
    row = {"code": "000001", "name": "test", "close": 200, "trade_value": 1000, "market_cap": 100}
    def quick(evaluation):
        return auditor._quick_from_snapshot(snapshot={"strategy_input": data, "technical": {},
                                            "evaluations": {evaluation.strategy: evaluation}},
                                            market="KOSPI", latest_date="20260130", row=row)[0]
    old, new = quick(baseline), quick(restored)
    assert baseline.score == restored.score == 90
    assert old["quick_condition_state"]["consistency"]["ok"]
    assert new["quick_condition_state"]["consistency"]["ok"]
    assert (old["quick_current"]["passed"], old["quick_current"]["total"]) == (8, 9)
    assert (new["quick_current"]["passed"], new["quick_current"]["total"]) == (7, 8)
    assert old["quick_score"] != new["quick_score"]
    assert new["quick_entry_risk_guide"]
