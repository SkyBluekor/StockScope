from __future__ import annotations

import pytest

from app.market.fundamental import FundamentalAnalyzer
from app.strategy.analysis_hub import AnalysisHubBuilder


def row(account_nm: str, amount: float, account_id: str = "", sj_div: str = "") -> dict:
    return {
        "account_nm": account_nm,
        "account_id": account_id,
        "sj_div": sj_div,
        "thstrm_amount": f"{amount:,.0f}",
    }


def statement(year: int, *, revenue: float, op: float, net: float, equity: float, assets: float,
              liabilities: float, current_assets: float, current_liabilities: float,
              ocf: float, icf: float = -100.0, fcf: float = -20.0) -> dict:
    return {
        "business_year": year,
        "fs_div": "CFS",
        "rows": [
            row("매출액", revenue, "ifrs-full_Revenue", "IS"),
            row("영업이익", op, "dart_OperatingIncomeLoss", "IS"),
            row("당기순이익", net, "ifrs-full_ProfitLoss", "IS"),
            row("자산총계", assets, "ifrs-full_Assets", "BS"),
            row("부채총계", liabilities, "ifrs-full_Liabilities", "BS"),
            row("자본총계", equity, "ifrs-full_Equity", "BS"),
            row("유동자산", current_assets, "ifrs-full_CurrentAssets", "BS"),
            row("유동부채", current_liabilities, "ifrs-full_CurrentLiabilities", "BS"),
            row("영업활동현금흐름", ocf, "ifrs-full_CashFlowsFromUsedInOperatingActivities", "CF"),
            row("투자활동현금흐름", icf, "ifrs-full_CashFlowsFromUsedInInvestingActivities", "CF"),
            row("재무활동현금흐름", fcf, "ifrs-full_CashFlowsFromUsedInFinancingActivities", "CF"),
        ],
    }


class FakeDart:
    async def resolve_corp_code(self, stock_code: str) -> str:
        return "00126380"

    async def company(self, corp_code: str) -> dict:
        return {"corp_name": "테스트전자", "stock_name": "테스트전자", "industry_code": "26110", "fiscal_month": "12"}

    async def annual_statement(self, corp_code: str, business_year: int, *, fs_div: str = "CFS") -> dict:
        data = {
            2025: statement(2025, revenue=1500, op=220, net=180, equity=900, assets=1300, liabilities=400,
                            current_assets=600, current_liabilities=250, ocf=240),
            2024: statement(2024, revenue=1250, op=170, net=135, equity=760, assets=1150, liabilities=390,
                            current_assets=520, current_liabilities=240, ocf=185),
            2023: statement(2023, revenue=1100, op=140, net=110, equity=700, assets=1050, liabilities=350,
                            current_assets=470, current_liabilities=220, ocf=160),
        }
        if fs_div != "CFS" or business_year not in data:
            raise RuntimeError("no data")
        return data[business_year]


@pytest.mark.asyncio
async def test_fundamental_engine_returns_result_first_quality_growth():
    result = await FundamentalAnalyzer(FakeDart()).analyze(
        "005930",
        eod_price=30.0,
        reference_price=33.0,
        listed_shares=30.0,
        market_cap=900.0,
        as_of="20260909",
    )

    assert result["available"] is True
    assert result["latest_year"] == 2025
    assert result["archetype"]["code"] == "QUALITY_GROWTH"
    assert result["overall"]["status"] == "GOOD"
    assert result["axes"]["growth"]["status"] in {"STRONG", "GOOD"}
    assert result["axes"]["cashflow"]["status"] == "GOOD"
    assert result["valuation"]["preview"] is not None
    assert result["valuation"]["basis"] == "REFERENCE_PRICE_PREVIEW"
    assert len(result["years"]) >= 3


class CashMismatchDart(FakeDart):
    async def annual_statement(self, corp_code: str, business_year: int, *, fs_div: str = "CFS") -> dict:
        if business_year == 2025 and fs_div == "CFS":
            return statement(2025, revenue=1500, op=120, net=100, equity=500, assets=1000, liabilities=500,
                             current_assets=300, current_liabilities=350, ocf=-80)
        return await super().annual_statement(corp_code, business_year, fs_div=fs_div)


@pytest.mark.asyncio
async def test_cashflow_mismatch_is_explained_as_warning():
    result = await FundamentalAnalyzer(CashMismatchDart()).analyze(
        "005930",
        eod_price=30.0,
        reference_price=None,
        listed_shares=30.0,
        market_cap=900.0,
        as_of="20260909",
    )
    assert result["axes"]["cashflow"]["status"] == "WEAK"
    assert "영업현금흐름" in result["axes"]["cashflow"]["headline"]
    assert result["archetype"]["code"] == "FINANCIAL_CAUTION"


def test_analysis_hub_surfaces_financial_divergence():
    hub = AnalysisHubBuilder.build(
        position_mode="NOT_HELD",
        risk_gate={"active": False, "message": "정상"},
        risk_analysis={"status": "READY", "summary": "구조 양호"},
        best_regular=type("B", (), {"strategy": type("S", (), {"value": "breakout"})(), "score": 82})(),
        position_action={"available": False},
        relative_strength={"decision": {"archetype": "MARKET_LEADER", "label": "시장 주도형", "summary": "시장보다 강함", "watch_points": []}},
        sector_relative_strength={"available": True, "decision": {"archetype": "DUAL_LEADER", "label": "시장·업종 동시 주도형", "summary": "업종보다 강함", "watch_points": []}},
        event_analysis={"risk_gate": False, "positive_count": 0, "negative_count": 0, "message": "큰 이벤트 없음"},
        pullback_confirmation={"state": "NOT_PULLBACK", "label": "눌림 아님", "summary": "눌림 아님", "auto_check": {"progress_label": "0/0 조건 확인", "passed": 0, "failed": 0, "pending": 0, "total": 0, "progress_pct": 0, "pending_checks": [], "failed_checks": []}},
        strategy_payloads=[{"strategy": "breakout", "score": 82, "suitability": "높음"}],
        fundamental_analysis={
            "available": True,
            "overall": {"status": "WEAK", "label": "주의", "summary": "재무 체력이 약합니다."},
            "watch_points": ["영업현금흐름 회복"],
        },
    )
    assert hub["verdict_label"] == "가격 신호 긍정 · 재무 주의"
    assert any(signal["key"] == "fundamental" and signal["status"] == "NEGATIVE" for signal in hub["signals"])
    assert any(item["key"] == "fundamental" for item in hub["navigation"])
