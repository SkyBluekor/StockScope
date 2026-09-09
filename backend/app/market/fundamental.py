from __future__ import annotations

import asyncio
from datetime import date, datetime
import re
from typing import Any

from app.market.providers import OpenDartProvider


class FundamentalAnalyzer:
    """Result-first fundamental analysis from official OpenDART statements.

    Annual statements provide the long-term baseline. The latest available periodic
    report (1Q / half-year / 3Q / annual) is compared only with the same report type
    from the prior year, so interim data is never compared against a full year.
    Valuation remains anchored to the latest annual EPS/BPS to avoid pretending a
    half-year cumulative EPS is a full-year earnings figure.
    """

    REPORT_META: dict[str, dict[str, Any]] = {
        "11013": {"label": "1분기보고서", "period_label": "1분기", "period_end": "03-31", "interim": True},
        "11012": {"label": "반기보고서", "period_label": "상반기", "period_end": "06-30", "interim": True},
        "11014": {"label": "3분기보고서", "period_label": "1~3분기", "period_end": "09-30", "interim": True},
        "11011": {"label": "사업보고서", "period_label": "연간", "period_end": "12-31", "interim": False},
    }

    ACCOUNT_RULES: dict[str, dict[str, tuple[str, ...]]] = {
        "revenue": {
            "ids": ("ifrs-full_Revenue", "ifrs_Revenue"),
            "names": ("매출액", "수익(매출액)", "영업수익", "매출"),
            "contains": ("매출액", "영업수익"),
        },
        "operating_profit": {
            "ids": ("dart_OperatingIncomeLoss",),
            "names": ("영업이익", "영업이익(손실)"),
            "contains": ("영업이익",),
        },
        "net_income": {
            "ids": ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss"),
            "names": ("당기순이익", "당기순이익(손실)", "연결당기순이익", "분기순이익"),
            "contains": ("당기순이익",),
        },
        "assets": {
            "ids": ("ifrs-full_Assets", "ifrs_Assets"),
            "names": ("자산총계",),
            "contains": ("자산총계",),
        },
        "liabilities": {
            "ids": ("ifrs-full_Liabilities", "ifrs_Liabilities"),
            "names": ("부채총계",),
            "contains": ("부채총계",),
        },
        "equity": {
            "ids": ("ifrs-full_Equity", "ifrs_Equity"),
            "names": ("자본총계",),
            "contains": ("자본총계",),
        },
        "current_assets": {
            "ids": ("ifrs-full_CurrentAssets", "ifrs_CurrentAssets"),
            "names": ("유동자산",),
            "contains": ("유동자산",),
        },
        "current_liabilities": {
            "ids": ("ifrs-full_CurrentLiabilities", "ifrs_CurrentLiabilities"),
            "names": ("유동부채",),
            "contains": ("유동부채",),
        },
        "operating_cash_flow": {
            "ids": (
                "ifrs-full_CashFlowsFromUsedInOperatingActivities",
                "ifrs_CashFlowsFromUsedInOperatingActivities",
            ),
            "names": ("영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동으로 인한 현금흐름"),
            "contains": ("영업활동", "현금흐름"),
        },
        "investing_cash_flow": {
            "ids": (
                "ifrs-full_CashFlowsFromUsedInInvestingActivities",
                "ifrs_CashFlowsFromUsedInInvestingActivities",
            ),
            "names": ("투자활동현금흐름", "투자활동으로인한현금흐름", "투자활동으로 인한 현금흐름"),
            "contains": ("투자활동", "현금흐름"),
        },
        "financing_cash_flow": {
            "ids": (
                "ifrs-full_CashFlowsFromUsedInFinancingActivities",
                "ifrs_CashFlowsFromUsedInFinancingActivities",
            ),
            "names": ("재무활동현금흐름", "재무활동으로인한현금흐름", "재무활동으로 인한 현금흐름"),
            "contains": ("재무활동", "현금흐름"),
        },
        "eps": {
            "ids": ("ifrs-full_BasicEarningsLossPerShare", "ifrs_BasicEarningsLossPerShare"),
            "names": ("기본주당이익", "기본주당이익(손실)", "주당이익"),
            "contains": ("기본주당이익",),
        },
    }

    def __init__(self, dart: OpenDartProvider | None) -> None:
        self.dart = dart

    @staticmethod
    def unavailable(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "engine": "FUNDAMENTAL",
            "version": "0.17.1",
            "source": "OpenDART",
            "overall": {
                "status": "UNKNOWN",
                "label": "분석 불가",
                "headline": "재무 데이터를 충분히 확인하지 못했습니다.",
                "summary": reason,
            },
            "archetype": {"code": "UNKNOWN", "label": "판단 보류", "summary": reason},
            "axes": {},
            "valuation": {
                "available": False,
                "status": "UNKNOWN",
                "label": "계산 불가",
                "message": "재무 또는 가격 데이터가 부족합니다.",
                "eod": {},
                "preview": None,
            },
            "latest_year": None,
            "latest_report": None,
            "recent_performance": None,
            "prior_same_period": None,
            "freshness": {
                "status": "UNKNOWN",
                "label": "최신성 확인 불가",
                "message": reason,
            },
            "years": [],
            "strengths": [],
            "warnings": [reason],
            "watch_points": [],
            "data_basis": {
                "financial": "OpenDART 정기보고서",
                "price": "KRX 확정 EOD",
                "note": "재무 분석을 사용할 수 없어 다른 분석축만 사용합니다.",
            },
            "policy": "재무 분석 실패가 기술적 분석·리스크 분석 전체를 막지 않습니다.",
        }

    @staticmethod
    def _amount(value: Any) -> float | None:
        if value in (None, "", "-"):
            return None
        text = str(value).strip().replace(",", "").replace(" ", "")
        if not text or text == "-":
            return None
        negative = text.startswith("(") and text.endswith(")")
        text = text.strip("()")
        text = re.sub(r"[^0-9.+-]", "", text)
        try:
            number = float(text)
        except ValueError:
            return None
        return -abs(number) if negative else number

    @classmethod
    def _row_amount(cls, row: dict[str, Any], *, prefer_cumulative: bool = False) -> float | None:
        statement_div = str(row.get("sj_div") or "").upper().strip()
        if prefer_cumulative and statement_div in {"IS", "CIS", "CF"}:
            raw = row.get("thstrm_add_amount")
            if raw in (None, "", "-"):
                raw = row.get("thstrm_amount")
        else:
            raw = row.get("thstrm_amount")
            if raw in (None, "", "-"):
                raw = row.get("thstrm_add_amount")
        return cls._amount(raw)

    @staticmethod
    def _pct(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return round(numerator / denominator * 100, 3)

    @staticmethod
    def _growth(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return round((current / previous - 1) * 100, 3)

    @classmethod
    def _find_metric(
        cls,
        rows: list[dict[str, Any]],
        key: str,
        *,
        prefer_cumulative: bool = False,
    ) -> float | None:
        rule = cls.ACCOUNT_RULES[key]
        candidates = list(rows)

        ids = {item.lower() for item in rule.get("ids", ())}
        for row in candidates:
            account_id = str(row.get("account_id") or "").strip().lower()
            if account_id and account_id in ids:
                value = cls._row_amount(row, prefer_cumulative=prefer_cumulative)
                if value is not None:
                    return value

        names = {item.replace(" ", "") for item in rule.get("names", ())}
        for row in candidates:
            name = str(row.get("account_nm") or "").strip().replace(" ", "")
            if name in names:
                value = cls._row_amount(row, prefer_cumulative=prefer_cumulative)
                if value is not None:
                    return value

        contains = tuple(item.replace(" ", "") for item in rule.get("contains", ()))
        for row in candidates:
            name = str(row.get("account_nm") or "").strip().replace(" ", "")
            if contains and all(token in name for token in contains):
                value = cls._row_amount(row, prefer_cumulative=prefer_cumulative)
                if value is not None:
                    return value
        return None

    @classmethod
    def _capex(cls, rows: list[dict[str, Any]], *, prefer_cumulative: bool = False) -> float | None:
        values: list[float] = []
        for row in rows:
            name = str(row.get("account_nm") or "").replace(" ", "")
            if "취득" not in name:
                continue
            if "유형자산" not in name and "무형자산" not in name:
                continue
            value = cls._row_amount(row, prefer_cumulative=prefer_cumulative)
            if value is not None:
                values.append(abs(value))
        return sum(values) if values else None

    async def _load_report(
        self,
        corp_code: str,
        business_year: int,
        report_code: str,
    ) -> dict[str, Any] | None:
        if self.dart is None:
            return None
        for fs_div in ("CFS", "OFS"):
            try:
                if hasattr(self.dart, "financial_statement"):
                    statement = await self.dart.financial_statement(
                        corp_code,
                        business_year,
                        report_code,
                        fs_div=fs_div,
                    )
                elif report_code == "11011":
                    statement = await self.dart.annual_statement(corp_code, business_year, fs_div=fs_div)
                else:
                    continue
            except Exception:
                continue
            rows = list(statement.get("rows") or [])
            if rows:
                statement = dict(statement)
                statement.setdefault("report_code", report_code)
                return statement
        return None

    async def _load_year(self, corp_code: str, business_year: int) -> dict[str, Any] | None:
        return await self._load_report(corp_code, business_year, "11011")

    @classmethod
    def _extract_statement_metrics(cls, statement: dict[str, Any]) -> dict[str, Any]:
        rows = list(statement.get("rows") or [])
        report_code = str(statement.get("report_code") or "11011")
        meta = cls.REPORT_META.get(report_code, cls.REPORT_META["11011"])
        interim = bool(meta["interim"])
        ocf = cls._find_metric(rows, "operating_cash_flow", prefer_cumulative=interim)
        capex = cls._capex(rows, prefer_cumulative=interim)
        return {
            "year": int(statement.get("business_year") or 0),
            "report_code": report_code,
            "report_label": meta["label"],
            "period_label": meta["period_label"],
            "period_end": f"{int(statement.get('business_year') or 0)}-{meta['period_end']}",
            "is_interim": interim,
            "fs_div": statement.get("fs_div") or "CFS",
            "fs_label": "연결" if statement.get("fs_div") == "CFS" else "별도",
            "revenue": cls._find_metric(rows, "revenue", prefer_cumulative=interim),
            "operating_profit": cls._find_metric(rows, "operating_profit", prefer_cumulative=interim),
            "net_income": cls._find_metric(rows, "net_income", prefer_cumulative=interim),
            "assets": cls._find_metric(rows, "assets"),
            "liabilities": cls._find_metric(rows, "liabilities"),
            "equity": cls._find_metric(rows, "equity"),
            "current_assets": cls._find_metric(rows, "current_assets"),
            "current_liabilities": cls._find_metric(rows, "current_liabilities"),
            "operating_cash_flow": ocf,
            "investing_cash_flow": cls._find_metric(rows, "investing_cash_flow", prefer_cumulative=interim),
            "financing_cash_flow": cls._find_metric(rows, "financing_cash_flow", prefer_cumulative=interim),
            "capex": capex,
            "free_cash_flow": None if ocf is None or capex is None else ocf - capex,
            "eps_reported": cls._find_metric(rows, "eps", prefer_cumulative=interim),
        }

    @classmethod
    def _decorate_period(
        cls,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
        *,
        annual_average_base: bool = False,
    ) -> dict[str, Any]:
        result = dict(current)
        previous_equity = previous.get("equity") if previous else None
        previous_assets = previous.get("assets") if previous else None
        avg_equity = None
        avg_assets = None
        if result.get("equity") is not None:
            avg_equity = result["equity"] if previous_equity is None else (result["equity"] + previous_equity) / 2
        if result.get("assets") is not None:
            avg_assets = result["assets"] if previous_assets is None else (result["assets"] + previous_assets) / 2

        # ROE/ROA are only shown for annual periods. Annualising an interim net
        # income number here would create a false precision signal.
        roe = cls._pct(result.get("net_income"), avg_equity) if annual_average_base and not result.get("is_interim") else None
        roa = cls._pct(result.get("net_income"), avg_assets) if annual_average_base and not result.get("is_interim") else None
        result.update({
            "operating_margin_pct": cls._pct(result.get("operating_profit"), result.get("revenue")),
            "net_margin_pct": cls._pct(result.get("net_income"), result.get("revenue")),
            "roe_pct": roe,
            "roa_pct": roa,
            "debt_ratio_pct": cls._pct(result.get("liabilities"), result.get("equity")),
            "current_ratio_pct": cls._pct(result.get("current_assets"), result.get("current_liabilities")),
            "revenue_growth_pct": cls._growth(result.get("revenue"), previous.get("revenue") if previous else None),
            "operating_profit_growth_pct": cls._growth(result.get("operating_profit"), previous.get("operating_profit") if previous else None),
            "net_income_growth_pct": cls._growth(result.get("net_income"), previous.get("net_income") if previous else None),
            "operating_cash_flow_growth_pct": cls._growth(
                result.get("operating_cash_flow"),
                previous.get("operating_cash_flow") if previous else None,
            ),
        })
        return result

    async def _latest_official_period(
        self,
        corp_code: str,
        base_year: int,
        as_of_date: date,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        # Never query a fiscal period that has not even ended yet. Once a period
        # has ended, missing/unfiled reports are simply skipped and OpenDART
        # availability remains the source of truth.
        current_candidates: list[tuple[int, str]] = []
        for report_code in ("11011", "11014", "11012", "11013"):
            meta = self.REPORT_META[report_code]
            month, day = (int(piece) for piece in str(meta["period_end"]).split("-"))
            if date(base_year, month, day) <= as_of_date:
                current_candidates.append((base_year, report_code))

        search_order = current_candidates + [
            (base_year - 1, "11011"),
            (base_year - 1, "11014"),
            (base_year - 1, "11012"),
            (base_year - 1, "11013"),
        ]
        latest_statement: dict[str, Any] | None = None
        for year, report_code in search_order:
            latest_statement = await self._load_report(corp_code, year, report_code)
            if latest_statement is not None:
                break
        if latest_statement is None:
            return None, None

        latest_metrics = self._extract_statement_metrics(latest_statement)
        prior_statement = await self._load_report(
            corp_code,
            int(latest_metrics["year"]) - 1,
            str(latest_metrics["report_code"]),
        )
        prior_metrics = self._extract_statement_metrics(prior_statement) if prior_statement is not None else None
        return latest_metrics, prior_metrics

    @staticmethod
    def _axis(code: str, label: str, status: str, status_label: str, headline: str, summary: str, evidence: list[str]) -> dict[str, Any]:
        return {
            "code": code,
            "label": label,
            "status": status,
            "status_label": status_label,
            "headline": headline,
            "summary": summary,
            "evidence": evidence,
        }

    @classmethod
    def _profitability_axis(cls, latest: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        op = latest.get("operating_profit")
        net = latest.get("net_income")
        roe = latest.get("roe_pct")
        margin = latest.get("operating_margin_pct")
        prior_margin = previous.get("operating_margin_pct") if previous else None
        evidence: list[str] = []
        if margin is not None:
            evidence.append(f"영업이익률 {margin:.1f}%")
        if roe is not None:
            evidence.append(f"ROE {roe:.1f}%")
        if prior_margin is not None and margin is not None:
            evidence.append(f"영업이익률 전년 대비 {margin - prior_margin:+.1f}%p")

        if op is not None and op <= 0 or net is not None and net <= 0:
            return cls._axis("profitability", "수익성", "WEAK", "취약", "이익 창출력이 약한 상태입니다.", "영업이익 또는 순이익이 적자여서 현재 수익성을 긍정적으로 보기 어렵습니다.", evidence)
        if roe is not None and roe >= 15 and margin is not None and margin > 0:
            return cls._axis("profitability", "수익성", "STRONG", "매우 양호", "자본 대비 이익 창출력이 좋은 편입니다.", "ROE와 영업이익률이 모두 양수이며 수익성이 비교적 탄탄합니다.", evidence)
        if (roe is not None and roe >= 8) or (margin is not None and margin >= 8):
            return cls._axis("profitability", "수익성", "GOOD", "양호", "회사가 이익을 내는 힘은 양호한 편입니다.", "현재 이익률과 자본 효율이 크게 취약한 수준은 아닙니다.", evidence)
        if op is not None and op > 0 and net is not None and net > 0:
            return cls._axis("profitability", "수익성", "NEUTRAL", "보통", "흑자는 유지하지만 수익성 우위는 크지 않습니다.", "이익은 나고 있으나 ROE나 이익률이 강하다고 단정할 근거는 제한적입니다.", evidence)
        return cls._axis("profitability", "수익성", "UNKNOWN", "판단 보류", "수익성을 판단할 데이터가 부족합니다.", "영업이익·순이익·ROE 중 일부가 없어 자동 판정을 보수적으로 유지합니다.", evidence)

    @classmethod
    def _growth_axis(cls, latest: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        if previous is None:
            return cls._axis("growth", "성장성", "UNKNOWN", "판단 보류", "전년 비교 데이터가 부족합니다.", "성장성은 한 해 숫자보다 전년 변화가 중요하므로 비교 가능한 연도가 필요합니다.", [])
        rev = latest.get("revenue_growth_pct")
        op = latest.get("operating_profit_growth_pct")
        net = latest.get("net_income_growth_pct")
        evidence = []
        if rev is not None:
            evidence.append(f"매출 {rev:+.1f}%")
        if op is not None:
            evidence.append(f"영업이익 {op:+.1f}%")
        if net is not None:
            evidence.append(f"순이익 {net:+.1f}%")

        if rev is not None and rev > 0 and op is not None and op < 0:
            return cls._axis("growth", "성장성", "CAUTION", "외형 성장·이익 부진", "매출은 늘지만 이익은 따라오지 못하고 있습니다.", "외형 확대가 실제 수익 증가로 이어지는지 추가 확인이 필요한 구조입니다.", evidence)
        if rev is not None and rev >= 8 and op is not None and op >= 8:
            return cls._axis("growth", "성장성", "STRONG", "성장", "매출과 영업이익이 함께 성장하고 있습니다.", "외형과 이익이 동시에 증가해 성장의 질이 비교적 좋은 편입니다.", evidence)
        if (rev is not None and rev > 0) or (op is not None and op > 0):
            return cls._axis("growth", "성장성", "GOOD", "개선", "최근 실적에 개선 신호가 있습니다.", "매출 또는 영업이익이 전년보다 증가해 성장 방향은 긍정적입니다.", evidence)
        if rev is not None and rev < 0 and op is not None and op < 0:
            return cls._axis("growth", "성장성", "WEAK", "둔화", "매출과 영업이익이 함께 감소했습니다.", "외형과 이익이 동시에 줄어 최근 성장 흐름은 약합니다.", evidence)
        return cls._axis("growth", "성장성", "NEUTRAL", "정체", "뚜렷한 성장 방향이 보이지 않습니다.", "전년 대비 변화가 크지 않거나 지표가 엇갈립니다.", evidence)

    @classmethod
    def _stability_axis(cls, latest: dict[str, Any], industry_code: str | None) -> dict[str, Any]:
        debt = latest.get("debt_ratio_pct")
        current = latest.get("current_ratio_pct")
        evidence: list[str] = []
        if debt is not None:
            evidence.append(f"부채비율 {debt:.1f}%")
        if current is not None:
            evidence.append(f"유동비율 {current:.1f}%")

        finance_like = bool(industry_code and str(industry_code).startswith(("64", "65", "66")))
        if finance_like:
            return cls._axis("stability", "재무 안정성", "NEUTRAL", "업종 특성 고려", "금융업은 일반 기업과 부채 구조가 달라 단순 부채비율 비교를 제한합니다.", "금융업의 레버리지는 사업모델 자체와 연결되므로 일반 제조·서비스업 기준으로 좋고 나쁨을 단정하지 않습니다.", evidence)

        if debt is not None and debt <= 50 and (current is None or current >= 120):
            return cls._axis("stability", "재무 안정성", "STRONG", "매우 양호", "부채 부담이 낮고 단기 지급능력도 비교적 안정적입니다.", "부채비율이 낮고 유동비율도 크게 부족하지 않아 재무 완충력이 좋은 편입니다.", evidence)
        if debt is not None and debt <= 100 and (current is None or current >= 100):
            return cls._axis("stability", "재무 안정성", "GOOD", "양호", "현재 부채와 단기 유동성 구조는 무난한 편입니다.", "자본 대비 부채 부담이 과도하지 않고 단기 유동성도 크게 불안한 수준은 아닙니다.", evidence)
        if debt is not None and debt >= 200 or current is not None and current < 70:
            return cls._axis("stability", "재무 안정성", "WEAK", "취약", "부채 또는 단기 유동성 부담이 큰 편입니다.", "재무 레버리지와 단기 지급능력을 보수적으로 볼 필요가 있습니다.", evidence)
        if debt is not None and debt > 100 or current is not None and current < 100:
            return cls._axis("stability", "재무 안정성", "CAUTION", "주의", "부채 또는 유동성 지표에 주의가 필요합니다.", "재무구조가 즉시 위험하다고 단정할 수준은 아니지만 완충력이 충분한지는 확인이 필요합니다.", evidence)
        return cls._axis("stability", "재무 안정성", "UNKNOWN", "판단 보류", "안정성 지표가 충분하지 않습니다.", "부채·자본·유동자산·유동부채 데이터 중 일부가 없어 보수적으로 판단합니다.", evidence)

    @classmethod
    def _cashflow_axis(cls, latest: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        ocf = latest.get("operating_cash_flow")
        net = latest.get("net_income")
        prev_ocf = previous.get("operating_cash_flow") if previous else None
        evidence: list[str] = []
        if ocf is not None:
            evidence.append(f"영업현금흐름 {'+' if ocf >= 0 else ''}{ocf:,.0f}원")
        if latest.get("free_cash_flow") is not None:
            evidence.append(f"FCF 추정 {'+' if latest['free_cash_flow'] >= 0 else ''}{latest['free_cash_flow']:,.0f}원")

        if ocf is None:
            return cls._axis("cashflow", "현금흐름", "UNKNOWN", "판단 보류", "영업현금흐름 데이터가 부족합니다.", "회계상 이익이 실제 현금으로 이어지는지 판단할 핵심 데이터가 없습니다.", evidence)
        if net is not None and net > 0 and ocf < 0:
            return cls._axis("cashflow", "현금흐름", "WEAK", "주의", "이익은 흑자인데 영업현금흐름은 마이너스입니다.", "장부상 이익과 실제 영업 현금 유입이 엇갈려 이익의 질을 추가 확인해야 합니다.", evidence)
        if ocf > 0 and (prev_ocf is None or prev_ocf > 0):
            return cls._axis("cashflow", "현금흐름", "GOOD", "양호", "영업활동에서 실제 현금을 만들어내고 있습니다.", "최근 영업현금흐름이 플러스로 유지돼 이익의 현금 전환이 비교적 안정적입니다.", evidence)
        if ocf > 0:
            return cls._axis("cashflow", "현금흐름", "NEUTRAL", "회복", "최근 영업현금흐름은 플러스로 돌아섰습니다.", "현금흐름이 개선됐지만 이전 연도까지 지속되는지 한 번 더 볼 필요가 있습니다.", evidence)
        return cls._axis("cashflow", "현금흐름", "WEAK", "취약", "영업활동 현금흐름이 마이너스입니다.", "본업에서 현금이 빠져나가는 상태가 지속되는지 주의해서 봐야 합니다.", evidence)

    @staticmethod
    def _valuation(price: float | None, eps: float | None, bps: float | None) -> dict[str, Any]:
        per = None if price is None or eps in (None, 0) or eps <= 0 else round(price / eps, 3)
        pbr = None if price is None or bps in (None, 0) or bps <= 0 else round(price / bps, 3)
        if price is None or (per is None and pbr is None):
            return {"price": price, "per": per, "pbr": pbr, "status": "UNKNOWN", "label": "계산 제한"}
        if per is None:
            return {"price": price, "per": per, "pbr": pbr, "status": "LOSS", "label": "PER 해석 제한"}
        if (per <= 10 and (pbr is None or pbr <= 1.5)):
            status, label = "LOW_MULTIPLE", "낮은 배수"
        elif per >= 30 or (pbr is not None and pbr >= 4):
            status, label = "HIGH_MULTIPLE", "높은 배수"
        else:
            status, label = "MID_MULTIPLE", "중간 배수"
        return {"price": price, "per": per, "pbr": pbr, "status": status, "label": label}

    @classmethod
    def _valuation_result(cls, *, eod_price: float | None, reference_price: float | None, eps: float | None, bps: float | None) -> dict[str, Any]:
        eod = cls._valuation(eod_price, eps, bps)
        preview = cls._valuation(reference_price, eps, bps) if reference_price is not None else None
        current = preview or eod
        status = current.get("status") or "UNKNOWN"
        if status == "LOW_MULTIPLE":
            message = "현재 실적·자본 대비 가격 배수는 낮은 편입니다. 다만 낮은 PER/PBR만으로 저평가를 확정할 수는 없습니다."
        elif status == "HIGH_MULTIPLE":
            message = "현재 실적·자본 대비 가격 배수는 높은 편이라 성장 기대가 이미 가격에 반영됐을 가능성을 함께 봅니다."
        elif status == "LOSS":
            message = "최근 순이익이 적자이거나 EPS가 0 이하라 PER을 일반적인 방식으로 해석하기 어렵습니다."
        elif status == "MID_MULTIPLE":
            message = "절대 배수만 보면 극단적으로 낮거나 높은 구간은 아닙니다. 업종 비교 없이 싸다·비싸다를 단정하지 않습니다."
        else:
            message = "EPS/BPS 또는 가격 데이터가 부족해 밸류에이션 배수를 충분히 계산하지 못했습니다."
        return {
            "available": bool(current.get("per") is not None or current.get("pbr") is not None),
            "status": status,
            "label": current.get("label") or "계산 제한",
            "message": message,
            "eps": eps,
            "bps": bps,
            "eod": eod,
            "preview": preview,
            "basis": "REFERENCE_PRICE_PREVIEW" if preview else "KRX_EOD",
            "policy": "PER/PBR은 업종·성장률에 따라 적정 수준이 달라 절대값만으로 저평가/고평가를 확정하지 않습니다.",
        }

    @staticmethod
    def _axis_points(axis: dict[str, Any]) -> int:
        status = axis.get("status")
        return {
            "STRONG": 2,
            "GOOD": 2,
            "NEUTRAL": 1,
            "CAUTION": 1,
            "WEAK": 0,
            "UNKNOWN": 1,
        }.get(str(status), 1)

    @classmethod
    def _archetype(cls, axes: dict[str, dict[str, Any]], latest: dict[str, Any]) -> dict[str, str]:
        profit = axes["profitability"]["status"]
        growth = axes["growth"]["status"]
        stability = axes["stability"]["status"]
        cash = axes["cashflow"]["status"]
        op = latest.get("operating_profit")
        net = latest.get("net_income")
        if (op is not None and op <= 0) or (net is not None and net <= 0):
            return {"code": "LOSS_MAKING", "label": "적자·수익성 주의형", "summary": "현재 손익이 적자여서 성장률보다 수익성 회복 여부를 먼저 봐야 합니다."}
        if stability == "WEAK" or cash == "WEAK":
            return {"code": "FINANCIAL_CAUTION", "label": "재무 주의형", "summary": "부채·유동성 또는 현금흐름에서 주의 신호가 있습니다."}
        if growth == "CAUTION":
            return {"code": "SALES_GROWTH_PROFIT_WEAK", "label": "외형 성장·이익 부진형", "summary": "매출은 늘지만 이익이 따라오지 못해 성장의 질을 확인해야 합니다."}
        if profit in {"STRONG", "GOOD"} and growth in {"STRONG", "GOOD"} and stability in {"STRONG", "GOOD"} and cash == "GOOD":
            return {"code": "QUALITY_GROWTH", "label": "고품질 성장형", "summary": "이익 성장과 재무 안정성, 영업현금흐름이 함께 받쳐주는 편입니다."}
        if growth in {"STRONG", "GOOD"} and profit in {"GOOD", "NEUTRAL"}:
            return {"code": "PROFITABILITY_IMPROVING", "label": "수익성 개선형", "summary": "최근 외형 또는 이익 개선이 나타나 수익성 방향이 좋아지고 있습니다."}
        if stability in {"STRONG", "GOOD"} and growth in {"NEUTRAL", "UNKNOWN"} and cash in {"GOOD", "NEUTRAL"}:
            return {"code": "STABLE_LOW_GROWTH", "label": "저성장 안정형", "summary": "성장 속도는 크지 않지만 재무와 현금흐름은 비교적 안정적인 편입니다."}
        return {"code": "MIXED", "label": "혼합형", "summary": "재무 강점과 약점이 함께 있어 한 가지 유형으로 단정하기 어렵습니다."}

    @classmethod
    def _overall(cls, axes: dict[str, dict[str, Any]], archetype: dict[str, str]) -> dict[str, str]:
        points = sum(cls._axis_points(axes[key]) for key in ("profitability", "growth", "stability", "cashflow"))
        weak_count = sum(axes[key]["status"] == "WEAK" for key in ("profitability", "growth", "stability", "cashflow"))
        if weak_count >= 2 or points <= 3:
            status, label = "WEAK", "주의"
            headline = "재무 체력이 현재 주가 흐름을 충분히 뒷받침하지 못합니다."
        elif points >= 7 and weak_count == 0:
            status, label = "GOOD", "양호"
            headline = "재무 체력은 전반적으로 양호한 편입니다."
        else:
            status, label = "CAUTION", "혼합"
            headline = "재무 상태는 강점과 주의점이 함께 있습니다."
        return {
            "status": status,
            "label": label,
            "headline": headline,
            "summary": archetype["summary"],
        }

    async def analyze(
        self,
        stock_code: str,
        *,
        eod_price: float | None,
        reference_price: float | None,
        listed_shares: float | None,
        market_cap: float | None,
        as_of: str | None,
        company: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.dart is None:
            return self.unavailable("OpenDART provider가 없어 재무제표를 조회할 수 없습니다.")

        try:
            supplied_company = company or {}
            supplied_corp_code = str(supplied_company.get("corp_code") or "").strip()
            corp_code = (
                supplied_corp_code
                if len(supplied_corp_code) == 8 and supplied_corp_code.isdigit()
                else await self.dart.resolve_corp_code(stock_code)
            )
            company = supplied_company if supplied_company else await self.dart.company(corp_code)
        except Exception as exc:
            return self.unavailable(f"OpenDART 기업정보 조회 실패: {exc}")

        if as_of:
            digits = re.sub(r"[^0-9]", "", str(as_of))
            try:
                as_of_date = datetime.strptime(digits[:8], "%Y%m%d").date()
            except ValueError:
                as_of_date = date.today()
        else:
            as_of_date = date.today()
        base_year = as_of_date.year

        # Long-term annual baseline.
        candidate_years = list(range(base_year - 1, base_year - 6, -1))
        statements = await asyncio.gather(*(self._load_year(corp_code, year) for year in candidate_years))
        statements = [item for item in statements if item is not None][:4]
        if not statements:
            return self.unavailable("최근 사업보고서의 연간 재무제표를 OpenDART에서 찾지 못했습니다.")

        annual_raw = [self._extract_statement_metrics(statement) for statement in statements]
        annual_raw = [row for row in annual_raw if row.get("year")]
        annual_raw.sort(key=lambda row: row["year"])

        periods: list[dict[str, Any]] = []
        for idx, row in enumerate(annual_raw):
            previous_raw = annual_raw[idx - 1] if idx > 0 else None
            periods.append(self._decorate_period(row, previous_raw, annual_average_base=True))

        if not periods:
            return self.unavailable("재무제표 원문은 조회됐지만 핵심 계정을 구조화하지 못했습니다.")

        annual_latest = periods[-1]
        annual_previous = periods[-2] if len(periods) >= 2 else None

        # Latest official periodic report and same-period YoY comparator.
        latest_raw, prior_same_raw = await self._latest_official_period(corp_code, base_year, as_of_date)
        if latest_raw is None:
            latest_period = annual_latest
            prior_same_period = annual_previous
        else:
            latest_period = self._decorate_period(latest_raw, prior_same_raw, annual_average_base=False)
            prior_same_period = (
                self._decorate_period(prior_same_raw, None, annual_average_base=False)
                if prior_same_raw is not None
                else None
            )
            # If the latest official report is the same annual statement already
            # decorated above, preserve annual ROE/ROA and growth calculations.
            if (
                not latest_period.get("is_interim")
                and latest_period.get("year") == annual_latest.get("year")
            ):
                latest_period = annual_latest
                prior_same_period = annual_previous

        shares = float(listed_shares) if listed_shares not in (None, 0) else None
        eps = annual_latest.get("eps_reported")
        if (eps is None or eps == 0) and shares and annual_latest.get("net_income") is not None:
            eps = annual_latest["net_income"] / shares
        bps = None if not shares or annual_latest.get("equity") is None else annual_latest["equity"] / shares

        # Current financial-health axes use the latest official period. Growth is
        # always same-period YoY; annual and interim amounts are never mixed.
        axes = {
            "profitability": self._profitability_axis(latest_period, prior_same_period),
            "growth": self._growth_axis(latest_period, prior_same_period),
            "stability": self._stability_axis(latest_period, company.get("industry_code")),
            "cashflow": self._cashflow_axis(latest_period, prior_same_period),
        }
        archetype = self._archetype(axes, latest_period)
        overall = self._overall(axes, archetype)
        valuation = self._valuation_result(
            eod_price=eod_price,
            reference_price=reference_price,
            eps=eps,
            bps=bps,
        )

        strengths = [axis["headline"] for axis in axes.values() if axis["status"] in {"STRONG", "GOOD"}][:4]
        warnings = [axis["headline"] for axis in axes.values() if axis["status"] in {"WEAK", "CAUTION"}][:4]
        if valuation["status"] == "HIGH_MULTIPLE":
            warnings.append("최근 연간 실적·자본 대비 가격 배수가 높은 편입니다.")

        watch_points: list[str] = []
        growth = axes["growth"]
        cashflow = axes["cashflow"]
        if growth["status"] in {"CAUTION", "WEAK", "NEUTRAL"}:
            watch_points.append("다음 정기실적에서 매출 변화가 영업이익 개선으로 이어지는지")
        if cashflow["status"] in {"WEAK", "NEUTRAL", "UNKNOWN"}:
            watch_points.append("다음 정기실적에서 영업현금흐름이 순이익과 같은 방향으로 개선되는지")
        if axes["stability"]["status"] in {"CAUTION", "WEAK"}:
            watch_points.append("다음 정기보고서에서 부채비율과 단기 유동성 부담이 더 커지는지")
        if valuation["status"] == "HIGH_MULTIPLE":
            watch_points.append("향후 이익 성장률이 현재 높은 가격 배수를 정당화하는지")

        latest_price_basis = "사용자 참고가격 Preview" if reference_price is not None else "KRX 확정 EOD"
        market_cap_preview = None if reference_price is None or not shares else reference_price * shares

        report_code = str(latest_period.get("report_code") or "11011")
        report_meta = self.REPORT_META.get(report_code, self.REPORT_META["11011"])
        latest_report_label = f"{latest_period['year']} {report_meta['label']}"
        period_label = f"{latest_period['year']} {report_meta['period_label']}"
        compare_label = (
            f"{prior_same_period['year']} {report_meta['period_label']}"
            if prior_same_period is not None
            else None
        )

        if latest_period.get("is_interim") and latest_period.get("year") == base_year:
            freshness_status = "LATEST_INTERIM"
            freshness_label = "최신 분기·반기 실적 반영"
            freshness_message = f"현재 분석은 OpenDART에서 확인 가능한 {latest_report_label}까지 반영합니다."
        elif latest_period.get("year") >= base_year - 1:
            freshness_status = "LATEST_ANNUAL"
            freshness_label = "최신 연간 실적 반영"
            freshness_message = f"현재 OpenDART에서 선택된 최신 정기실적은 {latest_report_label}입니다."
        else:
            freshness_status = "STALE"
            freshness_label = "재무 데이터 시점 주의"
            freshness_message = f"확인 가능한 최신 정기실적이 {latest_report_label}로 오래됐습니다."

        fiscal_month = str(company.get("fiscal_month") or "").strip()
        fiscal_note = ""
        if fiscal_month and fiscal_month != "12":
            fiscal_note = " 결산월이 12월이 아닌 기업은 표시된 분기 명칭을 해당 회사 회계연도 기준으로 해석해야 합니다."

        recent_performance = {
            "year": latest_period.get("year"),
            "report_code": report_code,
            "report_label": report_meta["label"],
            "period_label": period_label,
            "compare_label": compare_label,
            "is_interim": bool(latest_period.get("is_interim")),
            "fs_div": latest_period.get("fs_div"),
            "fs_label": latest_period.get("fs_label"),
            "period_end": latest_period.get("period_end"),
            "revenue": latest_period.get("revenue"),
            "operating_profit": latest_period.get("operating_profit"),
            "net_income": latest_period.get("net_income"),
            "operating_margin_pct": latest_period.get("operating_margin_pct"),
            "net_margin_pct": latest_period.get("net_margin_pct"),
            "debt_ratio_pct": latest_period.get("debt_ratio_pct"),
            "current_ratio_pct": latest_period.get("current_ratio_pct"),
            "operating_cash_flow": latest_period.get("operating_cash_flow"),
            "free_cash_flow": latest_period.get("free_cash_flow"),
            "revenue_yoy_pct": latest_period.get("revenue_growth_pct"),
            "operating_profit_yoy_pct": latest_period.get("operating_profit_growth_pct"),
            "net_income_yoy_pct": latest_period.get("net_income_growth_pct"),
            "operating_cash_flow_yoy_pct": latest_period.get("operating_cash_flow_growth_pct"),
        }

        prior_payload = None
        if prior_same_period is not None:
            prior_payload = {
                "year": prior_same_period.get("year"),
                "report_code": report_code,
                "report_label": report_meta["label"],
                "period_label": compare_label,
                "revenue": prior_same_period.get("revenue"),
                "operating_profit": prior_same_period.get("operating_profit"),
                "net_income": prior_same_period.get("net_income"),
                "operating_cash_flow": prior_same_period.get("operating_cash_flow"),
            }

        latest_report = {
            "business_year": latest_period.get("year"),
            "report_code": report_code,
            "report_label": report_meta["label"],
            "period_label": period_label,
            "period_end": latest_period.get("period_end"),
            "fs_div": latest_period.get("fs_div"),
            "fs_label": latest_period.get("fs_label"),
            "is_interim": bool(latest_period.get("is_interim")),
            "compare_available": prior_same_period is not None,
            "compare_label": compare_label,
        }

        return {
            "available": True,
            "engine": "FUNDAMENTAL",
            "version": "0.17.1",
            "source": "OpenDART+KRX_EOD",
            "corp_code": corp_code,
            "company": {
                "name": company.get("corp_name") or company.get("stock_name"),
                "industry_code": company.get("industry_code"),
                "fiscal_month": company.get("fiscal_month"),
            },
            "latest_year": latest_period["year"],
            "annual_latest_year": annual_latest["year"],
            "statement_basis": latest_period["fs_div"],
            "statement_basis_label": latest_period["fs_label"],
            "latest_report": latest_report,
            "recent_performance": recent_performance,
            "prior_same_period": prior_payload,
            "freshness": {
                "status": freshness_status,
                "label": freshness_label,
                "message": freshness_message + fiscal_note,
            },
            "overall": overall,
            "archetype": archetype,
            "axes": axes,
            "valuation": valuation,
            # Backward-compatible annual snapshot for valuation/long-term detail.
            "latest_metrics": {
                "revenue": annual_latest.get("revenue"),
                "operating_profit": annual_latest.get("operating_profit"),
                "net_income": annual_latest.get("net_income"),
                "operating_margin_pct": annual_latest.get("operating_margin_pct"),
                "net_margin_pct": annual_latest.get("net_margin_pct"),
                "roe_pct": annual_latest.get("roe_pct"),
                "roa_pct": annual_latest.get("roa_pct"),
                "debt_ratio_pct": annual_latest.get("debt_ratio_pct"),
                "current_ratio_pct": annual_latest.get("current_ratio_pct"),
                "operating_cash_flow": annual_latest.get("operating_cash_flow"),
                "free_cash_flow": annual_latest.get("free_cash_flow"),
                "eps": eps,
                "bps": bps,
                "market_cap_eod": market_cap,
                "market_cap_preview": market_cap_preview,
            },
            "years": list(reversed(periods)),
            "strengths": strengths,
            "warnings": list(dict.fromkeys(warnings)),
            "watch_points": list(dict.fromkeys(watch_points))[:5],
            "data_basis": {
                "financial": (
                    f"OpenDART {latest_report_label} · {latest_period['fs_label']}재무제표"
                    f" / 장기 추세는 {annual_latest['year']} 사업보고서까지"
                ),
                "price": latest_price_basis,
                "as_of": as_of,
                "note": (
                    "최신 분기·반기 실적은 전년 동일 기간과 YoY로 비교합니다. "
                    "연간 실적과 분기 실적을 직접 성장률로 섞지 않습니다. "
                    "PER/PBR은 최신 연간 EPS/BPS 기준이며 장중 참고가격은 Preview에만 사용합니다."
                    + fiscal_note
                ),
            },
            "policy": (
                "재무 체력은 기업 상태 평가이며 단기 주가 상승확률이 아닙니다. "
                "분기·반기 실적은 동일 기간 YoY로만 비교하고, 밸류에이션은 업종 비교 없이 "
                "저평가/고평가를 확정하지 않습니다."
            ),
        }

