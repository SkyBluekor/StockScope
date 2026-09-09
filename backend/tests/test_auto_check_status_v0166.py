from types import SimpleNamespace

from app.market.pullback_confirmation import PullbackConfirmationAnalyzer
from app.strategy.analysis_hub import AnalysisHubBuilder


def make_history(count: int = 40):
    rows = []
    price = 100.0
    for i in range(count):
        price += 1.0
        rows.append({
            "date": f"202602{(i % 28) + 1:02d}",
            "open": price - 0.5,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1_000_000,
        })
    return rows


def technical():
    return {
        "support": 132.0,
        "distance_to_20d_high_pct": 5.0,
        "ma20_slope_pct": 0.8,
        "higher_low": True,
    }


def test_intraday_auto_check_explains_missing_optional_inputs():
    result = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=technical(),
        current_price=133.0,
        current_ma20=132.5,
        current_rsi14=50.0,
        current_volume_ratio=0.9,
        source="USER_INPUT",
        position_mode="NOT_HELD",
    )

    auto = result["auto_check"]
    assert auto["basis"] == "INTRADAY_PREVIEW"
    assert auto["total"] == len(result["checks"])
    assert auto["progress_label"].endswith("조건 확인")
    assert "상승확률" in auto["policy"]
    hint_labels = {item["label"] for item in auto["input_hints"]}
    assert "오늘 저가" in hint_labels
    assert "현재 누적 거래량" in hint_labels


def test_intermediate_response_no_longer_uses_vague_auto_wait_phrase():
    result = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=technical(),
        current_price=133.0,
        current_ma20=132.5,
        current_rsi14=50.0,
        current_volume_ratio=0.9,
        source="USER_INPUT",
        position_mode="NOT_HELD",
    )

    assert result["state"] in {"SUPPORT_TESTING", "SUPPORT_APPROACH", "REBOUND_WAITING"}
    assert result["new_entry"]["action"] != "앱 자동 확인 대기"


def test_support_hold_without_rebound_gets_rebound_waiting_stage():
    history = make_history()
    # KRX EOD candle tested support and recovered above it, but closes red and RSI/volume are not recovered.
    history[-1].update({"open": 136.0, "low": 131.5, "high": 136.5, "close": 133.0})
    result = PullbackConfirmationAnalyzer.analyze(
        history=history,
        technical=technical(),
        current_price=133.0,
        current_ma20=132.5,
        current_rsi14=35.0,
        current_volume_ratio=0.6,
        source="KRX_EOD",
        position_mode="NOT_HELD",
    )

    assert result["state"] == "REBOUND_WAITING"
    assert result["label"] == "반등 신호 대기"
    assert result["auto_check"]["pending"] > 0


def test_analysis_hub_exposes_exact_auto_check_stage_and_progress():
    pullback = PullbackConfirmationAnalyzer.analyze(
        history=make_history(),
        technical=technical(),
        current_price=133.0,
        current_ma20=132.5,
        current_rsi14=50.0,
        current_volume_ratio=0.9,
        source="USER_INPUT",
        position_mode="NOT_HELD",
    )

    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "손익 구조 양호"},
        best_regular=SimpleNamespace(strategy=SimpleNamespace(value="pullback"), score=78),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "OUTPERFORMING", "label": "완만한 시장 우위", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": False, "decision": {}},
        event_analysis={"risk_gate": False, "positive_count": 0, "negative_count": 0, "message": "큰 이벤트 없음"},
        pullback_confirmation=pullback,
        strategy_payloads=[{"strategy": "pullback", "score": 78, "suitability": "높음"}],
    )

    assert hub["version"] == "0.18.2"
    assert hub["primary_action"] != "앱 자동 확인 대기"
    assert hub["auto_check_status"]["label"] == pullback["label"]
    assert hub["auto_check_status"]["progress"]["total"] == len(pullback["checks"])
    assert hub["auto_check_status"]["pending"]
