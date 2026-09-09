from types import SimpleNamespace

from app.market.pullback_confirmation import PullbackConfirmationAnalyzer
from app.strategy.analysis_hub import AnalysisHubBuilder


def make_history(count: int = 40):
    rows = []
    for i in range(count):
        close = 100.0 + (1.0 if i % 2 else 0.0)
        rows.append({
            "date": f"202608{(i % 28) + 1:02d}",
            "open": close - 0.3,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        })
    return rows


def technical():
    return {
        "support": 100.0,
        "distance_to_20d_high_pct": 5.0,
        "ma20_slope_pct": 0.8,
        "higher_low": True,
    }


def test_entry_timing_eod_exposes_action_progress_and_only_derived_levels():
    history = make_history()
    history[-1].update({"open": 100.0, "low": 99.5, "high": 102.0, "close": 101.0})

    result = PullbackConfirmationAnalyzer.analyze(
        history=history,
        technical=technical(),
        current_price=101.0,
        current_ma20=100.5,
        current_rsi14=35.0,
        current_volume_ratio=0.6,
        source="KRX_EOD",
        position_mode="NOT_HELD",
    )

    entry = result["entry_timing"]
    assert result["version"] == "0.18.2"
    assert entry["version"] == "0.18.2"
    assert entry["progress"]["total"] == 7
    assert entry["action"]["primary"] == "신규 추격 대기"
    assert entry["levels"]["current_price"] == 101.0
    assert entry["levels"]["ma20"] == 100.5
    assert entry["levels"]["support"] == 100.0
    # Candidate is derived from the actual EOD open/support anchor, not an invented target.
    assert entry["levels"]["rebound_confirmation"] == 100.5
    assert "상승확률" in entry["policy"]
    assert "시가" in entry["rules"]["price_rebound"]


def test_intraday_preview_can_confirm_price_and_rsi_recovery_from_supplied_data():
    history = make_history()
    confirmed_rsi = PullbackConfirmationAnalyzer._rsi14([float(row["close"]) for row in history])
    assert confirmed_rsi is not None

    result = PullbackConfirmationAnalyzer.analyze(
        history=history,
        technical=technical(),
        current_price=101.0,
        current_ma20=100.5,
        current_rsi14=max(40.0, confirmed_rsi + 2.0),
        current_volume_ratio=1.1,
        source="USER_INPUT",
        position_mode="NOT_HELD",
        reference_low=99.8,
        reference_high=101.5,
        reference_volume=1_200_000,
    )

    checks = {item["key"]: item for item in result["checks"]}
    assert checks["rebound_candle"]["status"] == "PASS"
    assert checks["rsi_turn"]["status"] == "PASS"
    assert "최신 확정 RSI" in checks["rsi_turn"]["explanation"]
    assert result["entry_timing"]["basis"] == "INTRADAY_PREVIEW"
    assert result["entry_timing"]["levels"]["rebound_confirmation"] == 100.5
    assert "오늘 저가" in result["entry_timing"]["rules"]["price_rebound"]


def test_holding_and_not_held_use_different_current_actions():
    kwargs = dict(
        history=make_history(),
        technical=technical(),
        current_price=101.0,
        current_ma20=100.5,
        current_rsi14=35.0,
        current_volume_ratio=0.6,
        source="USER_INPUT",
        reference_low=99.8,
    )
    not_held = PullbackConfirmationAnalyzer.analyze(position_mode="NOT_HELD", **kwargs)
    holding = PullbackConfirmationAnalyzer.analyze(position_mode="HOLDING", **kwargs)

    assert not_held["entry_timing"]["action"]["primary"] == "신규 추격 대기"
    assert holding["entry_timing"]["action"]["primary"] == "보유 관찰"
    assert "추가매수" in holding["entry_timing"]["action"]["avoid"]


def test_analysis_hub_merges_entry_timing_risk_level_and_style_context():
    pullback = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=technical(),
        current_price=101.0,
        current_ma20=100.5,
        current_rsi14=35.0,
        current_volume_ratio=0.6,
        source="USER_INPUT",
        position_mode="NOT_HELD",
        reference_low=99.8,
    )

    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "손익 구조 확인", "selected_plan": {"invalidation_price": 98.5}},
        best_regular=SimpleNamespace(strategy=SimpleNamespace(value="pullback"), score=78),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "OUTPERFORMING", "label": "시장 우위", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": False, "decision": {}},
        event_analysis={"risk_gate": False, "positive_count": 0, "negative_count": 0, "message": "큰 이벤트 없음"},
        pullback_confirmation=pullback,
        strategy_payloads=[{"strategy": "pullback", "score": 78, "suitability": "높음"}],
        fundamental_analysis={"available": True, "overall": {"status": "GOOD", "label": "양호", "summary": "재무 양호"}, "watch_points": []},
        investor_style_analysis={"top_style": {"label": "Peter Lynch", "score": 90, "fit_label": "매우 높음"}},
    )

    entry = hub["entry_timing"]
    assert hub["version"] == "0.18.2"
    assert entry["relevant"] is True
    assert entry["levels"]["invalidation"] == 98.5
    assert entry["style_context"]["label"] == "Peter Lynch"
    assert "단기 진입 타이밍" in entry["style_context"]["summary"]
    assert entry["progress"]["total"] == 7


def test_non_pullback_top_strategy_is_not_blocked_by_pullback_failure():
    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "손익 구조 확인", "selected_plan": {}},
        best_regular=SimpleNamespace(strategy=SimpleNamespace(value="breakout"), score=82),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "OUTPERFORMING", "label": "시장 우위", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": False, "decision": {}},
        event_analysis={"risk_gate": False, "positive_count": 0, "negative_count": 0, "message": "큰 이벤트 없음"},
        pullback_confirmation={
            "state": "SUPPORT_FAILED",
            "label": "지지 실패",
            "summary": "눌림 지지가 깨졌습니다.",
            "waiting_for": ["새 지지 구조"],
            "auto_check": {"progress_label": "3/7 조건 확인", "passed": 3, "failed": 1, "pending": 3, "total": 7, "progress_pct": 43},
            "entry_timing": {"status": "INVALIDATED", "label": "지지 실패", "progress": {"passed": 3, "failed": 1, "pending": 3, "total": 7, "percent": 43, "label": "3/7 조건 확인"}},
        },
        strategy_payloads=[{"strategy": "breakout", "score": 82, "suitability": "높음"}],
        fundamental_analysis={"available": True, "overall": {"status": "GOOD", "label": "양호", "summary": "재무 양호"}, "watch_points": []},
    )

    assert hub["entry_timing"]["relevant"] is False
    assert hub["primary_action"] == "우선 관찰 후보"
    pull_signal = next(item for item in hub["signals"] if item["key"] == "pullback")
    assert pull_signal["status"] == "NEUTRAL"
    assert "직접 연동하지 않음" in pull_signal["value"]
