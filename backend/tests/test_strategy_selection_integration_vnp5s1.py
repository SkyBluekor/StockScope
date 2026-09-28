from __future__ import annotations

from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.baseline.scanner_production_baseline import (
    load_manifest,
    manifest_path,
    verify_baseline,
)
from app.core.config import PROJECT_ROOT
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.strategy import (
    MarketRegime,
    StrategyEngine,
    StrategyInput,
    StrategyName,
)
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION,
    SelectionPolicyPin,
)
from app.strategy.service import StrategyAnalysisService


def _full_allowed() -> frozenset[StrategyName]:
    return frozenset(
        item for item in StrategyName if item is not StrategyName.NO_TRADE
    )


def _pin(
    *,
    policy_id: str = "POLICY-A",
    policy_hash: str = "a" * 64,
    keys: tuple[StrategyName, ...] | None = None,
) -> SelectionPolicyPin:
    selected = keys or tuple(_full_allowed())
    return SelectionPolicyPin(
        policy_id=policy_id,
        policy_hash=policy_hash,
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source="ACTIVE_SELECTION_POLICY",
        fallback_used=False,
        fallback_reason=None,
        operating_strategies=tuple(
            (
                f"version-{item.value}",
                item.value,
                f"definition-{item.value}",
            )
            for item in selected
        ),
        scanner_baseline_id="BASELINE-A",
        production_fingerprint="PROD-A",
        production_policy_fingerprint="POLICY-FP-A",
    )


def _breakout_input(*, event_risk: bool = False) -> StrategyInput:
    return StrategyInput(
        code="000660",
        market="KOSPI",
        current_price=200000,
        ma20=185000,
        ma60=170000,
        ma120=160000,
        ma20_slope_pct=2.0,
        rsi14=66,
        atr_pct=3.0,
        volume_ratio_20=2.1,
        distance_to_20d_high_pct=0.8,
        support_distance_pct=9,
        resistance_distance_pct=1,
        higher_high=True,
        higher_low=True,
        relative_strength_market_pct=4.5,
        relative_strength_sector_pct=2.1,
        market_regime=MarketRegime.TREND_UP,
        event_risk=event_risk,
    )


def test_full_selection_pool_is_exactly_legacy_engine_behavior():
    engine = StrategyEngine()
    data = _breakout_input()

    legacy = [item.to_dict() for item in engine.evaluate_all(data)]
    pinned = [
        item.to_dict()
        for item in engine.evaluate_all(
            data,
            allowed_strategies=_full_allowed(),
        )
    ]

    assert pinned == legacy


def test_restricted_pool_excludes_strategy_without_reweighting_remaining_scores():
    engine = StrategyEngine()
    data = _breakout_input()
    original = engine.evaluate_all(data)
    allowed = frozenset(
        item
        for item in _full_allowed()
        if item is not StrategyName.BREAKOUT
    )

    filtered = engine.evaluate_all(data, allowed_strategies=allowed)

    assert all(item.strategy is not StrategyName.BREAKOUT for item in filtered)
    original_scores = {
        item.strategy: item.score
        for item in original
        if item.strategy not in {StrategyName.NO_TRADE, StrategyName.BREAKOUT}
    }
    filtered_scores = {
        item.strategy: item.score
        for item in filtered
        if item.strategy is not StrategyName.NO_TRADE
    }
    assert filtered_scores == original_scores


def test_risk_gate_is_identical_after_strategy_pool_filtering():
    engine = StrategyEngine()
    data = _breakout_input(event_risk=True)
    legacy = engine.evaluate_all(data)
    restricted = engine.evaluate_all(
        data,
        allowed_strategies=frozenset(
            {StrategyName.PULLBACK, StrategyName.BREAKOUT}
        ),
    )

    assert legacy[0].strategy is StrategyName.NO_TRADE
    assert restricted[0].strategy is StrategyName.NO_TRADE
    assert restricted[0].blockers == legacy[0].blockers
    assert {
        item.strategy
        for item in restricted
        if item.strategy is not StrategyName.NO_TRADE
    } == {StrategyName.PULLBACK, StrategyName.BREAKOUT}
    assert all(
        item.eligible is False
        for item in restricted
        if item.strategy is not StrategyName.NO_TRADE
    )


def test_selection_pin_cache_token_and_strategy_reference_are_stable():
    pin = _pin(
        keys=(StrategyName.PULLBACK, StrategyName.BREAKOUT),
    )

    assert pin.cache_token.startswith(SELECTION_POLICY_CONTRACT_VERSION)
    assert pin.operating_strategy_keys == ("pullback", "breakout")
    assert pin.strategy_reference("breakout") == {
        "strategy_version_id": "version-breakout",
        "strategy_key": "breakout",
        "definition_hash": "definition-breakout",
    }
    assert pin.strategy_reference("trend_following") is None


def test_scanner_cache_path_separates_selection_policy_identity(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        StockScannerService,
        "CACHE_ROOT",
        tmp_path / "scanner-cache",
    )
    day = __import__("datetime").date(2026, 9, 28)
    a = _pin(policy_id="A", policy_hash="a" * 64)
    b = _pin(policy_id="B", policy_hash="b" * 64)

    path_a = StockScannerService._cache_path(
        "ALL",
        day,
        5,
        a.cache_token,
    )
    path_b = StockScannerService._cache_path(
        "ALL",
        day,
        5,
        b.cache_token,
    )

    assert path_a != path_b
    assert a.cache_token in path_a.name
    assert b.cache_token in path_b.name


def test_prospective_execution_identity_changes_with_selection_policy(
    tmp_path: Path,
):
    catalog = ProspectiveCatalog(tmp_path / "simulation.db")
    base = {
        "version": StockScannerService.VERSION,
        "requested_as_of": "2026-09-28",
        "market_scope": "ALL",
        "data_dates": {
            "KOSPI": "2026-09-28",
            "KOSDAQ": "2026-09-28",
        },
        "input_fingerprint": {"id": "same-input"},
        "partial_data": False,
        "summary": {"candidate_count": 1},
        "candidates": [
            {
                "code": "005930",
                "market": "KOSPI",
                "strategy": "pullback",
            }
        ],
        "more_candidates": [],
        "horizon_context": {"intent": "LEGACY_UNSPECIFIED"},
    }
    request_a = ProspectiveCaptureRequest(
        market_scope="ALL",
        requested_as_of="2026-09-28",
        candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version=None,
        selection_policy_id="A",
        selection_policy_hash="a" * 64,
    )
    request_b = ProspectiveCaptureRequest(
        market_scope="ALL",
        requested_as_of="2026-09-28",
        candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version=None,
        selection_policy_id="B",
        selection_policy_hash="b" * 64,
    )
    candidates = list(base["candidates"])

    key_a, snapshot_a, _ = catalog._result_identity(
        request=request_a,
        result={
            **base,
            "strategy_selection_policy": {
                "policy_id": "A",
                "policy_hash": "a" * 64,
            },
        },
        candidates=candidates,
    )
    key_b, snapshot_b, _ = catalog._result_identity(
        request=request_b,
        result={
            **base,
            "strategy_selection_policy": {
                "policy_id": "B",
                "policy_hash": "b" * 64,
            },
        },
        candidates=candidates,
    )

    assert snapshot_a != snapshot_b
    assert key_a != key_b


class _AnalysisKrx:
    async def stock_history(
        self,
        market,
        code,
        as_of=None,
        points=30,
        lookback_days=60,
    ):
        rows = []
        price = 100.0
        for index in range(max(points, 61)):
            price += 1.0
            rows.append(
                {
                    "date": f"2026{7 + index // 28:02d}{index % 28 + 1:02d}",
                    "code": code,
                    "name": "테스트",
                    "market": market,
                    "open": price - 0.5,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 1_000_000,
                    "trade_value": 5_000_000_000,
                }
            )
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {
            "main_index": {
                "name": "코스피",
                "change_rate": 1.5,
            },
            "rows": [],
        }

    async def index_history(
        self,
        market,
        as_of=None,
        points=61,
        lookback_days=120,
    ):
        return []


class _PinRegistry:
    def __init__(self, pin: SelectionPolicyPin):
        self.pin = pin
        self.calls = 0

    def pin_active_selection_policy(self) -> SelectionPolicyPin:
        self.calls += 1
        return self.pin


@pytest.mark.asyncio
async def test_single_stock_eod_and_reference_share_one_selection_pin():
    pin = _pin(
        keys=(StrategyName.PULLBACK, StrategyName.TREND_FOLLOWING),
    )
    registry = _PinRegistry(pin)
    service = StrategyAnalysisService(
        _AnalysisKrx(),
        selection_registry=registry,
    )

    result = await service.analyze(
        "005930",
        "KOSPI",
        history_points=60,
        reference_price=170.0,
    )

    assert registry.calls == 1
    assert result["strategy_selection_policy"]["policy_id"] == pin.policy_id
    for key in ("strategies", "eod_strategies", "reference_strategies"):
        regular = [
            item
            for item in (result[key] or [])
            if item["strategy"] != StrategyName.NO_TRADE.value
        ]
        assert {
            item["strategy"] for item in regular
        } <= {"pullback", "trend_following"}
        for item in regular:
            assert item["strategy_version_id"] == (
                f"version-{item['strategy']}"
            )



def test_committed_scanner_02138_baseline_matches_current_production():
    manifest = load_manifest(manifest_path(PROJECT_ROOT))
    result = verify_baseline(PROJECT_ROOT, manifest)

    assert manifest["scanner_version"] == StockScannerService.VERSION
    for changed in result.changed_files:
        print("BASELINE_CHANGED_FILE", changed)
    print(
        "BASELINE_FINGERPRINTS",
        result.production_fingerprint_expected,
        result.production_fingerprint_current,
        result.policy_fingerprint_expected,
        result.policy_fingerprint_current,
    )
    assert result.valid is True, {
        "production_fingerprint_expected": result.production_fingerprint_expected,
        "production_fingerprint_current": result.production_fingerprint_current,
        "policy_fingerprint_expected": result.policy_fingerprint_expected,
        "policy_fingerprint_current": result.policy_fingerprint_current,
        "changed_files": result.changed_files,
        "missing_files": result.missing_files,
        "extra_relevant_files": result.extra_relevant_files,
    }
    assert result.changed_files == ()
    assert result.missing_files == ()
    assert result.extra_relevant_files == ()



def test_historical_evidence_cache_isolated_by_strategy_version(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        StockScannerService,
        "CACHE_ROOT",
        tmp_path / "scanner-cache",
    )
    day = __import__("datetime").date(2026, 9, 28)

    v1 = StockScannerService._evidence_cache_path(
        market="KOSPI",
        code="005930",
        strategy="breakout",
        data_end=day,
        strategy_version_id="breakout-v1",
        definition_hash="1" * 64,
    )
    v2 = StockScannerService._evidence_cache_path(
        market="KOSPI",
        code="005930",
        strategy="breakout",
        data_end=day,
        strategy_version_id="breakout-v2",
        definition_hash="2" * 64,
    )

    assert v1 != v2


class _NeverResolveRegistry:
    def __init__(self):
        self.calls = 0

    def pin_active_selection_policy(self):
        self.calls += 1
        raise AssertionError("supplied run pin must be reused")


class _NoopKrx:
    def _today_kst(self):
        return __import__("datetime").date(2026, 9, 29)


@pytest.mark.asyncio
async def test_scanner_supplied_run_pin_is_not_reresolved():
    registry = _NeverResolveRegistry()
    scanner = StockScannerService(
        _NoopKrx(),
        selection_registry=registry,
    )

    with pytest.raises(ValueError):
        await scanner.run(
            market_scope="INVALID",
            selection_policy_pin=_pin(),
        )

    assert registry.calls == 0
