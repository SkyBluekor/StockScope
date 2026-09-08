import pytest

from app.strategy.service import StrategyAnalysisService


class FakeKrx:
    async def stock_history(self, market, code, as_of=None, points=60, lookback_days=120):
        rows = []
        price = 100.0
        for i in range(60):
            price += 0.8
            rows.append({
                "date": f"20260{1 + (i // 28)}{(i % 28) + 1:02d}",
                "code": code,
                "name": "테스트",
                "market": market,
                "open": price - 0.4,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1_200_000,
                "trade_value": 5_000_000_000,
            })
        return rows

    async def latest_index_daily(self, market, as_of=None):
        return {"main_index": {"name": "코스피", "change_rate": 0.8}}


class HighEventDart:
    async def resolve_corp_code(self, stock_code):
        return "00126380"

    async def disclosures(self, corp_code, begin_date, end_date, page_count=20):
        return {
            "count": 1,
            "rows": [{
                "receipt_no": "20260908000001",
                "receipt_date": "20260908",
                "report_name": "유상증자 결정",
            }],
        }

    async def major_event(self, path, corp_code, begin_date, end_date):
        return {
            "rows": [{
                "rcept_no": "20260908000001",
                "nstk_ostk_cnt": "10000000",
                "bfic_tisstk_ostk": "50000000",
                "ic_mthn": "주주배정",
            }]
        }

    async def document_text(self, receipt_no):
        return ""


@pytest.mark.asyncio
async def test_high_event_flows_into_strategy_risk_gate_and_holding_action():
    result = await StrategyAnalysisService(FakeKrx(), HighEventDart()).analyze(
        "005930",
        "KOSPI",
        position_mode="HOLDING",
        average_price=130.0,
        quantity=10,
    )

    assert result["event_risk"]["risk_gate"] is True
    assert result["risk_gate"]["active"] is True
    assert any("이벤트" in reason or "공시" in reason for reason in result["risk_gate"]["reasons"])
    assert result["position_action_guide"]["primary_code"] == "EVENT_REVIEW"
    assert result["position_action_guide"]["add_position"]["label"] == "추가매수 보류"
