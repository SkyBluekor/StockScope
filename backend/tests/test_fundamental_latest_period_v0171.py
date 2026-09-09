from __future__ import annotations

import pytest

from app.market.fundamental import FundamentalAnalyzer


def row(
    name: str,
    current: float,
    *,
    cumulative: float | None = None,
    account_id: str = "",
    sj_div: str = "",
) -> dict:
    payload = {
        "account_nm": name,
        "account_id": account_id,
        "sj_div": sj_div,
        "thstrm_amount": f"{current:,.0f}",
    }
    if cumulative is not None:
        payload["thstrm_add_amount"] = f"{cumulative:,.0f}"
    return payload


def annual(year: int, revenue: float, op: float, net: float) -> dict:
    return {
        "business_year": year,
        "report_code": "11011",
        "fs_div": "CFS",
        "rows": [
            row("매출액", revenue, account_id="ifrs-full_Revenue", sj_div="IS"),
            row("영업이익", op, account_id="dart_OperatingIncomeLoss", sj_div="IS"),
            row("당기순이익", net, account_id="ifrs-full_ProfitLoss", sj_div="IS"),
            row("자산총계", 2000, account_id="ifrs-full_Assets", sj_div="BS"),
            row("부채총계", 600, account_id="ifrs-full_Liabilities", sj_div="BS"),
            row("자본총계", 1400, account_id="ifrs-full_Equity", sj_div="BS"),
            row("유동자산", 800, account_id="ifrs-full_CurrentAssets", sj_div="BS"),
            row("유동부채", 300, account_id="ifrs-full_CurrentLiabilities", sj_div="BS"),
            row(
                "영업활동현금흐름",
                260,
                account_id="ifrs-full_CashFlowsFromUsedInOperatingActivities",
                sj_div="CF",
            ),
        ],
    }


def half(year: int, revenue_q2: float, revenue_h1: float, op_h1: float, net_h1: float, ocf_h1: float) -> dict:
    return {
        "business_year": year,
        "report_code": "11012",
        "fs_div": "CFS",
        "rows": [
            # OpenDART interim income/cash rows may expose both current-quarter
            # and cumulative fields. The engine must use cumulative H1 amounts.
            row("매출액", revenue_q2, cumulative=revenue_h1, account_id="ifrs-full_Revenue", sj_div="IS"),
            row("영업이익", 90, cumulative=op_h1, account_id="dart_OperatingIncomeLoss", sj_div="IS"),
            row("당기순이익", 70, cumulative=net_h1, account_id="ifrs-full_ProfitLoss", sj_div="IS"),
            row("자산총계", 2150, account_id="ifrs-full_Assets", sj_div="BS"),
            row("부채총계", 620, account_id="ifrs-full_Liabilities", sj_div="BS"),
            row("자본총계", 1530, account_id="ifrs-full_Equity", sj_div="BS"),
            row("유동자산", 900, account_id="ifrs-full_CurrentAssets", sj_div="BS"),
            row("유동부채", 320, account_id="ifrs-full_CurrentLiabilities", sj_div="BS"),
            row(
                "영업활동현금흐름",
                120,
                cumulative=ocf_h1,
                account_id="ifrs-full_CashFlowsFromUsedInOperatingActivities",
                sj_div="CF",
            ),
        ],
    }


class InterimDart:
    async def resolve_corp_code(self, stock_code: str) -> str:
        return "00126380"

    async def company(self, corp_code: str) -> dict:
        return {
            "corp_name": "테스트전자",
            "stock_name": "테스트전자",
            "industry_code": "26110",
            "fiscal_month": "12",
        }

    async def annual_statement(self, corp_code: str, business_year: int, *, fs_div: str = "CFS") -> dict:
        data = {
            2025: annual(2025, 3000, 360, 300),
            2024: annual(2024, 2700, 300, 250),
            2023: annual(2023, 2500, 260, 220),
        }
        if fs_div != "CFS" or business_year not in data:
            raise RuntimeError("no annual")
        return data[business_year]

    async def financial_statement(
        self,
        corp_code: str,
        business_year: int,
        report_code: str,
        *,
        fs_div: str = "CFS",
    ) -> dict:
        if fs_div != "CFS":
            raise RuntimeError("no ofs")
        if report_code == "11011":
            return await self.annual_statement(corp_code, business_year, fs_div=fs_div)
        if (business_year, report_code) == (2026, "11012"):
            return half(2026, 900, 1700, 220, 180, 250)
        if (business_year, report_code) == (2025, "11012"):
            return half(2025, 780, 1500, 180, 145, 205)
        raise RuntimeError("report unavailable")


@pytest.mark.asyncio
async def test_latest_half_year_is_selected_and_compared_yoy():
    result = await FundamentalAnalyzer(InterimDart()).analyze(
        "005930",
        eod_price=30.0,
        reference_price=None,
        listed_shares=30.0,
        market_cap=900.0,
        as_of="20260909",
    )

    assert result["available"] is True
    assert result["version"] == "0.17.1"
    assert result["latest_year"] == 2026
    assert result["annual_latest_year"] == 2025
    assert result["latest_report"]["report_code"] == "11012"
    assert result["latest_report"]["period_label"] == "2026 상반기"
    assert result["latest_report"]["compare_label"] == "2025 상반기"
    assert result["freshness"]["status"] == "LATEST_INTERIM"

    # Must use cumulative H1, not the Q2-only 900 current-period amount.
    recent = result["recent_performance"]
    assert recent["revenue"] == 1700
    assert recent["operating_profit"] == 220
    assert recent["operating_cash_flow"] == 250
    assert recent["revenue_yoy_pct"] == pytest.approx(13.333, abs=0.001)
    assert recent["operating_profit_yoy_pct"] == pytest.approx(22.222, abs=0.001)

    # Long-term annual series is preserved separately.
    assert result["years"][0]["year"] == 2025
    assert "동일 기간" in result["data_basis"]["note"]


@pytest.mark.asyncio
async def test_interim_does_not_replace_annual_eps_basis_for_valuation():
    result = await FundamentalAnalyzer(InterimDart()).analyze(
        "005930",
        eod_price=30.0,
        reference_price=33.0,
        listed_shares=30.0,
        market_cap=900.0,
        as_of="20260909",
    )
    # 2025 annual net income 300 / 30 shares = EPS 10.
    assert result["valuation"]["eps"] == pytest.approx(10.0)
    assert result["valuation"]["eod"]["per"] == pytest.approx(3.0)
    assert result["valuation"]["preview"]["per"] == pytest.approx(3.3)
