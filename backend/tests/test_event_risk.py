import pytest

from app.market.event_risk import EventRiskAnalyzer


class FakeDart:
    async def resolve_corp_code(self, stock_code):
        return "00126380"

    async def disclosures(self, corp_code, begin_date, end_date, page_count=20):
        return {
            "count": 3,
            "rows": [
                {
                    "receipt_no": "20260908000001",
                    "receipt_date": "20260908",
                    "report_name": "유상증자 결정",
                },
                {
                    "receipt_no": "20260907000002",
                    "receipt_date": "20260907",
                    "report_name": "단일판매ㆍ공급계약체결",
                },
                {
                    "receipt_no": "20260906000003",
                    "receipt_date": "20260906",
                    "report_name": "임원ㆍ주요주주특정증권등소유상황보고서",
                },
            ],
        }

    async def major_event(self, path, corp_code, begin_date, end_date):
        if path != "piicDecsn.json":
            return {"rows": []}
        return {
            "rows": [
                {
                    "rcept_no": "20260908000001",
                    "nstk_ostk_cnt": "10000000",
                    "bfic_tisstk_ostk": "50000000",
                    "fv_ps": "5000",
                    "ic_mthn": "주주배정후 실권주 일반공모",
                    "fdpp_fclt": "70000000000",
                    "fdpp_op": "30000000000",
                }
            ]
        }

    async def document_text(self, receipt_no):
        return "계약금액 100억원. 계약기간은 2026년 9월부터 2028년 8월까지입니다."


def test_title_classification():
    rule, _ = EventRiskAnalyzer.classify_title("[정정] 전환사채권 발행결정")
    assert rule is not None
    assert rule.event_type == "CONVERTIBLE_BOND"
    assert rule.level == "HIGH"


@pytest.mark.asyncio
async def test_rights_issue_activates_high_event_gate_and_structured_summary():
    result = await EventRiskAnalyzer(FakeDart()).analyze(
        "005930",
        position_mode="HOLDING",
        days=60,
    )

    assert result["available"] is True
    assert result["risk_gate"] is True
    assert result["high_count"] == 1
    rights = next(event for event in result["events"] if event["event_type"] == "RIGHTS_ISSUE")
    assert rights["detail_source"] == "STRUCTURED_API"
    assert "20.0%" in rights["easy_summary"]
    assert any("신규 보통주" in str(fact.get("label")) for fact in rights["facts"])
    assert rights["user_response"]["action"] == "보유 논리 재평가"
    assert "추가매수" in rights["user_response"]["summary"]


@pytest.mark.asyncio
async def test_medium_event_does_not_activate_gate_without_high():
    class MediumOnlyDart(FakeDart):
        async def disclosures(self, corp_code, begin_date, end_date, page_count=20):
            return {
                "count": 1,
                "rows": [{
                    "receipt_no": "20260907000002",
                    "receipt_date": "20260907",
                    "report_name": "단일판매ㆍ공급계약체결",
                }],
            }

    result = await EventRiskAnalyzer(MediumOnlyDart()).analyze("005930")
    assert result["risk_gate"] is False
    assert result["medium_count"] == 1


@pytest.mark.asyncio
async def test_positive_contract_is_impact_not_hard_risk_gate_and_uses_price_reaction():
    class ContractDart(FakeDart):
        async def disclosures(self, corp_code, begin_date, end_date, page_count=20):
            return {
                "count": 1,
                "rows": [{
                    "receipt_no": "20260908000002",
                    "receipt_date": "20260908",
                    "report_name": "단일판매ㆍ공급계약체결",
                }],
            }

        async def document_text(self, receipt_no):
            return """
            계약금액: 20,000,000,000원
            계약상대방: HMM
            계약기간: 2026.09.08 ~ 2027.06.30
            대금 지급: 청구 후 10영업일 이내
            """

        async def latest_annual_revenue(self, corp_code):
            return {
                "business_year": 2025,
                "revenue": 100_000_000_000,
                "fs_div": "CFS",
                "account_name": "매출액",
            }

    history = [
        {
            "date": "20260904",
            "close": 10000,
            "volume": 1_000_000,
        },
        {
            "date": "20260907",
            "close": 10500,
            "volume": 1_100_000,
        },
    ]

    result = await EventRiskAnalyzer(ContractDart()).analyze(
        "005930",
        history=history,
        reference_price=12000,
        reference_volume=2_000_000,
    )

    event = result["events"][0]
    assert result["risk_gate"] is False
    assert event["direction"] == "POSITIVE"
    assert event["impact_level"] == "MEDIUM"
    assert event["metrics"]["contract_to_revenue_pct"] == pytest.approx(20.0)
    assert event["price_reaction"]["price_change_pct"] == pytest.approx(14.29, abs=0.02)
    assert event["user_response"]["action"] == "신규 추격 주의"
    assert any(item["direction"] == "UP" for item in event["strategy_effects"])
