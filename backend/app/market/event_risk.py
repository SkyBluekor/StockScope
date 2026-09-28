from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.market.providers import OpenDartProvider
from app.market.providers.base import ProviderError


@dataclass(frozen=True)
class EventRule:
    event_type: str
    impact_level: str
    direction: str
    keywords: tuple[str, ...]
    easy_meaning: str

    @property
    def level(self) -> str:
        # Backward compatibility with v0.12 tests/callers.
        return self.impact_level


class EventRiskAnalyzer:
    """OpenDART disclosure -> Event Impact analysis for decision support.

    Kept under the legacy class name for compatibility with the existing strategy service.
    The output is no longer "risk only": it evaluates direction, impact, confidence,
    price reaction and conditional user response.
    """

    RULES: tuple[EventRule, ...] = (
        EventRule(
            "RIGHTS_ISSUE",
            "HIGH",
            "NEGATIVE",
            ("유상증자",),
            "회사가 새 주식을 발행해 자금을 조달하는 공시입니다. 발행 규모가 크면 기존 주주의 지분가치 희석 가능성과 단기 변동성 확대를 함께 봐야 합니다.",
        ),
        EventRule(
            "CONVERTIBLE_BOND",
            "HIGH",
            "NEGATIVE",
            ("전환사채권 발행결정", "전환사채 발행결정"),
            "향후 주식으로 전환될 수 있는 채권 발행 공시입니다. 전환 시 주식 수 증가와 희석 가능성이 생길 수 있습니다.",
        ),
        EventRule(
            "BW",
            "HIGH",
            "NEGATIVE",
            ("신주인수권부사채권 발행결정", "신주인수권부사채 발행결정"),
            "신주를 살 수 있는 권리가 붙은 사채 발행 공시입니다. 행사 시 주식 수가 늘어날 수 있어 잠재 희석 가능성을 확인해야 합니다.",
        ),
        EventRule(
            "CAPITAL_REDUCTION",
            "HIGH",
            "MIXED",
            ("감자 결정",),
            "회사가 자본금을 줄이는 공시입니다. 목적과 방식에 따라 재무구조 개선일 수도 있지만 주식 수와 주주가치에 직접 영향을 줄 수 있습니다.",
        ),
        EventRule(
            "MERGER",
            "HIGH",
            "MIXED",
            ("회사합병 결정", "합병 결정"),
            "다른 회사와 합치는 기업행동입니다. 합병비율과 상대회사, 일정에 따라 기존 가격 기준이 크게 달라질 수 있습니다.",
        ),
        EventRule(
            "SPLIT",
            "HIGH",
            "MIXED",
            ("회사분할 결정", "회사분할합병 결정"),
            "회사를 나누거나 분할 후 합병하는 기업행동으로 사업가치와 주식 구조가 달라질 수 있습니다.",
        ),
        EventRule(
            "DISTRESS",
            "HIGH",
            "NEGATIVE",
            ("부도발생", "영업정지", "회생절차 개시신청", "해산사유 발생", "상장폐지", "거래정지"),
            "회사의 정상 영업이나 상장 유지에 직접 영향을 줄 수 있는 매우 중요한 공시입니다.",
        ),
        EventRule(
            "MAJOR_SHAREHOLDER",
            "MEDIUM",
            "MIXED",
            ("최대주주 변경",),
            "회사의 지배구조가 바뀌는 공시로 경영방향이나 수급에 영향을 줄 수 있습니다.",
        ),
        EventRule(
            "LARGE_CONTRACT",
            "MEDIUM",
            "POSITIVE",
            ("단일판매", "공급계약"),
            "회사 매출에 영향을 줄 수 있는 판매·공급계약 공시입니다. 계약금액과 최근 매출 대비 규모를 같이 보면 의미를 더 정확히 판단할 수 있습니다.",
        ),
        EventRule(
            "EARNINGS_CHANGE",
            "MEDIUM",
            "MIXED",
            ("매출액또는손익구조", "영업(잠정)실적", "연결재무제표기준영업(잠정)실적"),
            "최근 실적이 크게 변했거나 잠정 실적이 발표된 공시입니다. 숫자의 방향과 시장 반응을 함께 봐야 합니다.",
        ),
        EventRule(
            "LITIGATION",
            "MEDIUM",
            "NEGATIVE",
            ("소송 등의 제기", "소송등의제기"),
            "회사가 중요한 소송에 연관됐다는 공시입니다. 청구금액과 사업 영향도를 확인해야 합니다.",
        ),
        EventRule(
            "TREASURY",
            "LOW",
            "MIXED",
            ("자기주식 취득 결정", "자기주식 처분 결정"),
            "회사가 자기 주식을 사거나 처분하는 공시입니다. 취득은 수급에 긍정적일 수 있고 처분은 반대일 수 있어 세부조건 확인이 필요합니다.",
        ),
        EventRule(
            "DIVIDEND",
            "LOW",
            "POSITIVE",
            ("현금ㆍ현물배당", "배당"),
            "주주에게 이익을 배분하는 공시입니다. 배당금과 기준일, 배당락 영향을 함께 보면 됩니다.",
        ),
    )

    STRUCTURED_ENDPOINTS: dict[str, tuple[str, dict[str, str]]] = {
        "RIGHTS_ISSUE": (
            "piicDecsn.json",
            {
                "nstk_ostk_cnt": "신규 보통주",
                "bfic_tisstk_ostk": "증자 전 보통주",
                "fv_ps": "액면가",
                "ic_mthn": "증자 방식",
                "fdpp_fclt": "시설자금",
                "fdpp_op": "운영자금",
                "fdpp_dtrp": "채무상환자금",
                "fdpp_ocsa": "타법인증권 취득자금",
                "fdpp_etc": "기타자금",
            },
        ),
        "CONVERTIBLE_BOND": (
            "cvbdIsDecsn.json",
            {
                "bd_tm": "회차",
                "bd_knd": "사채 종류",
                "bd_fta": "발행 총액",
                "cv_rt": "전환비율",
                "cv_prc": "전환가액",
                "bd_mtd": "만기일",
                "bdis_mthn": "발행방법",
                "fdpp_fclt": "시설자금",
                "fdpp_op": "운영자금",
                "fdpp_dtrp": "채무상환자금",
                "fdpp_ocsa": "타법인증권 취득자금",
                "fdpp_etc": "기타자금",
            },
        ),
        "BW": (
            "bdwtIsDecsn.json",
            {
                "bd_tm": "회차",
                "bd_knd": "사채 종류",
                "bd_fta": "발행 총액",
                "ex_rt": "행사비율",
                "ex_prc": "행사가액",
                "nstk_isstk_cnt": "행사 시 발행주식수",
                "nstk_isstk_tisstk_vs": "총주식 대비 비율",
                "expd_bgd": "권리행사 시작일",
                "expd_edd": "권리행사 종료일",
                "fdpp_fclt": "시설자금",
                "fdpp_op": "운영자금",
                "fdpp_dtrp": "채무상환자금",
                "fdpp_ocsa": "타법인증권 취득자금",
                "fdpp_etc": "기타자금",
            },
        ),
        "MERGER": (
            "cmpMgDecsn.json",
            {
                "mg_mth": "합병방법",
                "mg_stn": "합병형태",
                "mg_pp": "합병목적",
                "mg_rt": "합병비율",
                "mgptncmp_cmpnm": "합병 상대회사",
                "mgptncmp_mbsn": "상대회사 주요사업",
                "mgnstk_ostk_cnt": "합병신주 보통주",
            },
        ),
    }

    def __init__(self, dart: OpenDartProvider) -> None:
        self.dart = dart

    @classmethod
    def classify_title(cls, report_name: str | None) -> tuple[EventRule | None, str]:
        title = (report_name or "").strip()
        clean = re.sub(r"^\[?정정\]?\s*", "", title)
        clean = clean.replace("정정", "")
        for rule in cls.RULES:
            if any(keyword in clean for keyword in rule.keywords):
                return rule, clean
        return None, clean

    @staticmethod
    def _num(value: Any) -> float | None:
        if value in (None, "", "-"):
            return None
        text = re.sub(r"[^0-9.\-]", "", str(value))
        if not text or text in {"-", ".", "-."}:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _compact_number(value: float | None, suffix: str = "") -> str:
        if value is None:
            return "-"
        abs_value = abs(value)
        if abs_value >= 100_000_000:
            return f"{value / 100_000_000:,.1f}억원"
        if abs_value >= 10_000:
            return f"{value / 10_000:,.1f}만원"
        return f"{value:,.0f}{suffix}"

    @classmethod
    def _format_fact(cls, label: str, value: Any) -> dict[str, Any] | None:
        if value in (None, "", "-"):
            return None
        text = str(value).strip()
        if not text:
            return None
        number = cls._num(value)
        money_like = any(key in label for key in ("자금", "총액", "가액", "액면가", "금액"))
        share_like = "주식" in label or "보통주" in label
        display = text
        if number is not None and money_like:
            display = f"{number:,.0f}원"
        elif number is not None and share_like and "비율" not in label:
            display = f"{number:,.0f}주"
        elif number is not None and "비율" in label:
            display = f"{number:g}%"
        return {"label": label, "value": display, "raw": number if number is not None else text}

    @classmethod
    def _easy_summary_from_structured(
        cls,
        event_type: str,
        row: dict[str, Any],
        fallback: str,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        endpoint = cls.STRUCTURED_ENDPOINTS.get(event_type)
        if endpoint:
            _, fields = endpoint
            for key, label in fields.items():
                fact = cls._format_fact(label, row.get(key))
                if fact:
                    facts.append(fact)

        if event_type == "RIGHTS_ISSUE":
            new_shares = cls._num(row.get("nstk_ostk_cnt"))
            before = cls._num(row.get("bfic_tisstk_ostk"))
            ratio = (new_shares / before * 100) if new_shares is not None and before else None
            method = (row.get("ic_mthn") or "").strip()
            metrics["dilution_ratio_pct"] = ratio
            metrics["new_shares"] = new_shares
            parts = ["회사가 새 보통주를 발행하는 유상증자를 결정했습니다."]
            if new_shares is not None:
                parts.append(f"신규 발행 예정 보통주는 약 {new_shares:,.0f}주입니다.")
            if ratio is not None:
                parts.append(f"증자 전 보통주 대비 약 {ratio:.1f}% 규모로 계산됩니다.")
                facts.append({"label": "증자 규모", "value": f"기존 보통주 대비 {ratio:.1f}%", "raw": ratio})
            if method:
                parts.append(f"증자 방식은 {method}입니다.")
            return " ".join(parts), facts, metrics

        if event_type == "CONVERTIBLE_BOND":
            total = cls._num(row.get("bd_fta"))
            cv_price = cls._num(row.get("cv_prc"))
            metrics.update({"issue_amount": total, "conversion_price": cv_price})
            parts = ["향후 주식으로 전환될 수 있는 전환사채 발행을 결정했습니다."]
            if total is not None:
                parts.append(f"발행 총액은 약 {cls._compact_number(total)}입니다.")
            if cv_price is not None:
                parts.append(f"현재 공시상 전환가액은 {cv_price:,.0f}원입니다.")
            parts.append("전환이 실제로 이뤄지면 주식 수 증가와 희석 가능성을 확인해야 합니다.")
            return " ".join(parts), facts, metrics

        if event_type == "BW":
            total = cls._num(row.get("bd_fta"))
            exercise = cls._num(row.get("ex_prc"))
            stock_ratio = cls._num(row.get("nstk_isstk_tisstk_vs"))
            metrics.update({"issue_amount": total, "exercise_price": exercise, "potential_share_ratio_pct": stock_ratio})
            parts = ["신주를 살 수 있는 권리가 붙은 신주인수권부사채 발행을 결정했습니다."]
            if total is not None:
                parts.append(f"발행 총액은 약 {cls._compact_number(total)}입니다.")
            if exercise is not None:
                parts.append(f"공시상 행사가액은 {exercise:,.0f}원입니다.")
            if stock_ratio is not None:
                parts.append(f"행사 시 발행 가능 주식은 총주식 대비 약 {stock_ratio:g}%로 표시됩니다.")
            return " ".join(parts), facts, metrics

        if event_type == "MERGER":
            other = (row.get("mgptncmp_cmpnm") or "").strip()
            ratio = (row.get("mg_rt") or "").strip()
            purpose = (row.get("mg_pp") or "").strip()
            metrics.update({"counterparty": other or None, "merger_ratio": ratio or None})
            parts = ["회사합병을 결정한 공시입니다."]
            if other:
                parts.append(f"합병 상대회사는 {other}입니다.")
            if ratio:
                parts.append(f"공시된 합병비율은 {ratio}입니다.")
            if purpose:
                parts.append(f"합병 목적은 {purpose}로 기재돼 있습니다.")
            return " ".join(parts), facts, metrics

        return fallback, facts, metrics

    async def _structured_detail(
        self,
        rule: EventRule,
        corp_code: str,
        begin: str,
        end: str,
        receipt_no: str | None,
    ) -> tuple[str | None, list[dict[str, Any]], str | None, dict[str, Any]]:
        spec = self.STRUCTURED_ENDPOINTS.get(rule.event_type)
        if spec is None:
            return None, [], None, {}
        path, _ = spec
        try:
            payload = await self.dart.major_event(path, corp_code, begin, end)
        except ProviderError:
            return None, [], None, {}
        rows = payload.get("rows") or []
        selected = None
        if receipt_no:
            selected = next((row for row in rows if str(row.get("rcept_no")) == receipt_no), None)
        if selected is None and rows:
            selected = rows[0]
        if selected is None:
            return None, [], None, {}
        summary, facts, metrics = self._easy_summary_from_structured(rule.event_type, selected, rule.easy_meaning)
        return summary, facts, path, metrics

    @staticmethod
    def _extract_text_value(text: str, labels: tuple[str, ...], *, max_len: int = 80) -> str | None:
        compact = re.sub(r"[ \t]+", " ", text)
        for label in labels:
            patterns = (
                rf"{re.escape(label)}\s*[:：\-]?\s*([^\n]{{1,{max_len}}})",
                rf"{re.escape(label)}\s+([^\n]{{1,{max_len}}})",
            )
            for pattern in patterns:
                match = re.search(pattern, compact, re.IGNORECASE)
                if match:
                    value = " ".join(match.group(1).split())
                    if value:
                        return value
        return None

    @classmethod
    def _extract_amount_near_label(cls, text: str, labels: tuple[str, ...]) -> float | None:
        compact = re.sub(r"[ \t]+", " ", text)
        for label in labels:
            start = compact.find(label)
            if start < 0:
                continue
            snippet = compact[start : start + 220]
            # Prefer explicit 원-denominated values.
            m = re.search(r"([0-9][0-9,]{3,})\s*원", snippet)
            if m:
                return cls._num(m.group(1))
            # Fallback to a long integer right after the label.
            m = re.search(r"([0-9][0-9,]{5,})", snippet)
            if m:
                return cls._num(m.group(1))
        return None

    @classmethod
    def _contract_detail_from_document(cls, text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        amount = cls._extract_amount_near_label(text, ("계약금액", "계약 금액", "계약내역"))
        counterparty = cls._extract_text_value(text, ("계약상대방", "계약 상대방", "계약상대", "상대방"), max_len=60)
        period = cls._extract_text_value(text, ("계약기간", "계약 기간"), max_len=100)
        payment = cls._extract_text_value(text, ("대금지급", "대금 지급", "지급조건", "지급 조건"), max_len=120)

        if amount is not None:
            facts.append({"label": "계약금액", "value": cls._compact_number(amount), "raw": amount})
            metrics["contract_amount"] = amount
        if counterparty:
            # Avoid swallowing another field.
            counterparty = re.split(r"\s{2,}|계약기간|계약금액|대금", counterparty)[0].strip(" -:")
            if counterparty:
                facts.append({"label": "계약 상대방", "value": counterparty, "raw": counterparty})
                metrics["counterparty"] = counterparty
        if period:
            period = re.split(r"\s{2,}|계약금액|대금지급|대금 지급", period)[0].strip(" -:")
            if period:
                facts.append({"label": "계약기간", "value": period, "raw": period})
                metrics["contract_period"] = period
        if payment:
            payment = re.split(r"\s{2,}|계약기간|계약금액", payment)[0].strip(" -:")
            if payment:
                facts.append({"label": "대금 지급", "value": payment, "raw": payment})
                metrics["payment_terms"] = payment
        return facts, metrics

    async def _document_detail(
        self,
        rule: EventRule,
        receipt_no: str | None,
    ) -> tuple[list[dict[str, Any]], list[str], dict[str, Any], str | None]:
        if not receipt_no:
            return [], [], {}, None
        try:
            text = await self.dart.document_text(receipt_no)
        except ProviderError:
            return [], [], {}, None

        facts: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        if rule.event_type == "LARGE_CONTRACT":
            facts, metrics = self._contract_detail_from_document(text)

        # Raw highlights are fallback only, not the main user-facing output.
        keywords = (
            "발행", "자금", "목적", "비율", "금액", "계약", "상대방", "기간",
            "합병", "분할", "소송", "배당", "영업", "정지", "주식", "전환",
        )
        sentences = re.split(r"(?<=[.!?。])\s+|\n+", text)
        highlights: list[str] = []
        for sentence in sentences:
            compact = " ".join(sentence.split())
            if 20 <= len(compact) <= 180 and any(key in compact for key in keywords):
                if compact not in highlights:
                    highlights.append(compact)
            if len(highlights) >= 2:
                break
        return facts, highlights, metrics, "DOCUMENT_XML"

    async def _latest_revenue(self, corp_code: str) -> dict[str, Any] | None:
        method = getattr(self.dart, "latest_annual_revenue", None)
        if method is None:
            return None
        try:
            return await method(corp_code)
        except (ProviderError, ValueError):
            return None

    @staticmethod
    def _price_reaction(
        receipt_date: str | None,
        history: list[dict[str, Any]] | None,
        *,
        reference_price: float | None,
        reference_volume: float | None,
    ) -> dict[str, Any]:
        if not receipt_date or not history:
            return {
                "available": False,
                "label": "가격 반응 데이터 부족",
                "source": None,
            }

        rows = sorted(
            [row for row in history if row.get("date") and row.get("close") is not None],
            key=lambda row: str(row.get("date")),
        )
        event_date = receipt_date.replace("-", "")
        before_rows = [row for row in rows if str(row.get("date")) < event_date]
        after_rows = [row for row in rows if str(row.get("date")) >= event_date]
        pre = before_rows[-1] if before_rows else None
        post = after_rows[-1] if after_rows else None

        pre_close = float(pre["close"]) if pre and pre.get("close") is not None else None
        latest_eod_close = float(post["close"]) if post and post.get("close") is not None else None
        price = reference_price if reference_price is not None else latest_eod_close
        source = "USER_REFERENCE" if reference_price is not None else ("KRX_EOD" if latest_eod_close is not None else None)

        change_pct = None
        if pre_close and price is not None:
            change_pct = (float(price) / pre_close - 1) * 100

        volume_ratio = None
        if reference_volume is not None:
            prior_volumes = [
                float(row["volume"])
                for row in before_rows[-20:]
                if row.get("volume") is not None
            ]
            if prior_volumes:
                avg = sum(prior_volumes) / len(prior_volumes)
                if avg:
                    volume_ratio = float(reference_volume) / avg
        elif post and post.get("volume") is not None:
            prior_volumes = [
                float(row["volume"])
                for row in before_rows[-20:]
                if row.get("volume") is not None
            ]
            if prior_volumes:
                avg = sum(prior_volumes) / len(prior_volumes)
                if avg:
                    volume_ratio = float(post["volume"]) / avg

        if change_pct is None:
            reaction = "UNKNOWN"
            label = "가격 반응 확인 불가"
        else:
            abs_change = abs(change_pct)
            if abs_change >= 15:
                reaction, label = "EXTREME", "가격 반응 매우 큼"
            elif abs_change >= 7:
                reaction, label = "STRONG", "가격 반응 큼"
            elif abs_change >= 3:
                reaction, label = "MODERATE", "가격 반응 확인"
            else:
                reaction, label = "MUTED", "가격 반응 제한적"

        return {
            "available": pre_close is not None and price is not None,
            "event_date": event_date,
            "pre_event_close": pre_close,
            "analysis_price": price,
            "analysis_price_source": source,
            "price_change_pct": round(change_pct, 2) if change_pct is not None else None,
            "volume_ratio_20": round(volume_ratio, 2) if volume_ratio is not None else None,
            "reaction": reaction,
            "label": label,
        }

    @staticmethod
    def _impact_confidence(
        *,
        structured: bool,
        facts_count: int,
        has_company_scale: bool,
        price_reaction_available: bool,
    ) -> tuple[str, str]:
        score = 0
        score += 2 if structured else 0
        score += 1 if facts_count >= 2 else 0
        score += 1 if has_company_scale else 0
        score += 1 if price_reaction_available else 0
        if score >= 4:
            return "HIGH", "높음"
        if score >= 2:
            return "MEDIUM", "보통"
        return "LOW", "낮음"

    @staticmethod
    def _strategy_effects(
        rule: EventRule,
        price_reaction: dict[str, Any],
    ) -> list[dict[str, str]]:
        reaction = str(price_reaction.get("reaction") or "UNKNOWN")
        effects: list[dict[str, str]] = []

        def add(strategy: str, direction: str, label: str, reason: str) -> None:
            effects.append({
                "strategy": strategy,
                "direction": direction,
                "label": label,
                "reason": reason,
            })

        if rule.direction == "NEGATIVE":
            add("breakout", "DOWN", "약화", "부정 이벤트는 돌파 후 변동성 확대와 되돌림 위험을 키울 수 있습니다.")
            add("momentum_continuation", "DOWN", "약화", "모멘텀보다 이벤트 불확실성을 먼저 봐야 합니다.")
            add("trend_following", "DOWN", "약화", "기존 추세가 유지돼도 기업 이벤트가 전제를 바꿀 수 있습니다.")
            add("pullback", "DOWN", "약화", "눌림목이 아니라 악재 재평가 구간일 수 있습니다.")
            return effects

        if rule.direction == "POSITIVE":
            if reaction in {"STRONG", "EXTREME"}:
                add("breakout", "UP", "강화", "긍정 이벤트와 강한 가격 반응이 함께 나타나 돌파 조건에 우호적입니다.")
                add("momentum_continuation", "UP", "강화", "가격 반응이 강해 모멘텀 계열 조건은 강화됩니다.")
                add("trend_following", "UP", "소폭 강화", "기존 추세에 긍정 이벤트가 추가됐습니다.")
                add("pullback", "DOWN", "약화", "가격이 빠르게 올라 지지구간과 멀어졌다면 눌림목 진입에는 불리합니다.")
            else:
                add("breakout", "NEUTRAL", "관찰", "긍정 이벤트지만 가격 반응이 아직 강하지 않아 돌파 확인이 더 필요합니다.")
                add("momentum_continuation", "NEUTRAL", "관찰", "거래량과 가격 반응 확인이 필요합니다.")
                add("trend_following", "UP", "소폭 강화", "기업 이벤트 방향은 추세에 우호적입니다.")
                add("pullback", "NEUTRAL", "중립", "가격이 지지구간에 접근하는지 별도로 봐야 합니다.")
            return effects

        add("breakout", "NEUTRAL", "중립", "이벤트 방향이 혼재돼 가격 확인이 우선입니다.")
        add("trend_following", "NEUTRAL", "중립", "기술 추세와 이벤트 조건을 함께 봅니다.")
        add("pullback", "NEUTRAL", "중립", "기업 이벤트 자체로 눌림목을 강화/약화하기 어렵습니다.")
        return effects

    @classmethod
    def _current_conclusion(
        cls,
        rule: EventRule,
        *,
        metrics: dict[str, Any],
        price_reaction: dict[str, Any],
        revenue: dict[str, Any] | None,
    ) -> tuple[str, str, list[str]]:
        watch_points: list[str] = []
        change = price_reaction.get("price_change_pct")
        reaction = price_reaction.get("reaction")
        sales_ratio = metrics.get("contract_to_revenue_pct")

        if rule.event_type == "LARGE_CONTRACT":
            if sales_ratio is not None:
                if sales_ratio >= 20:
                    significance = "회사 규모 대비 매우 큰 계약"
                elif sales_ratio >= 10:
                    significance = "회사 규모 대비 의미 있는 계약"
                elif sales_ratio >= 5:
                    significance = "실적에 영향을 줄 수 있는 계약"
                else:
                    significance = "회사 규모 대비 제한적인 계약"
            else:
                significance = "계약 규모의 회사 매출 대비 비중은 자동 계산하지 못함"

            if reaction in {"STRONG", "EXTREME"} and change is not None and change > 0:
                headline = "긍정 재료지만 이미 가격 반응이 큰 편입니다."
                summary = f"{significance}으로 보이지만 공시 전 기준가격 대비 현재 분석가격이 {change:+.2f}% 움직였습니다. 신규 진입은 계약 자체보다 추격 부담과 새 지지구간 형성 여부를 같이 봐야 합니다."
            elif reaction in {"MODERATE"} and change is not None and change > 0:
                headline = "긍정 재료와 가격 반응이 함께 확인됩니다."
                summary = f"{significance}이며 공시 이후 가격도 {change:+.2f}% 반응했습니다. 돌파·모멘텀에는 우호적이지만 손익비와 거래량 확인이 필요합니다."
            else:
                headline = "긍정 가능성이 있는 계약 공시입니다."
                summary = f"{significance}입니다. 다만 가격 반응이 아직 제한적이거나 데이터가 부족해 계약 조건과 향후 실적 반영 여부를 추가로 확인할 필요가 있습니다."
            watch_points.extend(["계약 매출 인식 시점", "계약 변경·해지 공시", "다음 실적 발표에서 매출 반영 여부"])
            return headline, summary, watch_points

        if rule.direction == "NEGATIVE":
            headline = "부정 가능성이 높은 이벤트입니다."
            summary = "기술적 지표보다 공시 세부조건이 우선입니다. 신규 진입과 추가매수는 보수적으로 보고, 기존 전략 전제가 유지되는지 다시 평가하는 편이 합리적입니다."
            watch_points.extend(["정정공시 여부", "후속 일정", "주식 수·재무구조 변화"])
            return headline, summary, watch_points

        if rule.direction == "POSITIVE":
            headline = "긍정 가능성이 있는 이벤트입니다."
            summary = "재료 자체는 우호적이지만 가격에 이미 반영됐는지와 실제 실적 기여 정도를 함께 봐야 합니다."
            watch_points.extend(["가격 반응 지속 여부", "실적 반영 여부"])
            return headline, summary, watch_points

        headline = "조건에 따라 해석이 달라지는 이벤트입니다."
        summary = "공시 방향을 단정하기보다 세부조건과 가격 반응을 함께 확인해야 합니다."
        watch_points.extend(["세부조건", "후속 공시", "가격·거래량 반응"])
        return headline, summary, watch_points

    @staticmethod
    def _user_response(
        rule: EventRule,
        *,
        position_mode: str,
        price_reaction: dict[str, Any],
        conclusion_headline: str,
    ) -> dict[str, str]:
        reaction = price_reaction.get("reaction")
        change = price_reaction.get("price_change_pct")

        if position_mode == "HOLDING":
            if rule.direction == "NEGATIVE" and rule.impact_level == "HIGH":
                return {
                    "action": "보유 논리 재평가",
                    "summary": "추가매수는 보류하고 공시가 기존 보유전략의 무효화 기준을 바꾸는지 먼저 확인합니다. 영향이 크다면 비중 축소·정리 여부를 검토합니다.",
                }
            if rule.direction == "POSITIVE" and reaction in {"STRONG", "EXTREME"} and change is not None and change > 0:
                return {
                    "action": "보유 관찰 + 이익 보호 기준 확인",
                    "summary": "긍정 이벤트와 강한 가격 반응이 확인됩니다. 급등 뒤 변동성 확대에 대비해 최근 저점·20일선·전략 무효화 가격을 기준으로 보유 논리를 관리합니다.",
                }
            return {
                "action": "보유 관찰",
                "summary": "공시 방향과 기술 구조를 함께 보면서 기존 전략 무효화 기준이 유지되는지 확인합니다.",
            }

        if rule.direction == "NEGATIVE" and rule.impact_level == "HIGH":
            return {
                "action": "신규 진입 보류",
                "summary": "공시 세부조건과 가격 반응이 안정되기 전까지 기술 신호만으로 신규 진입하지 않는 편이 합리적입니다.",
            }
        if rule.direction == "POSITIVE" and reaction in {"STRONG", "EXTREME"} and change is not None and change > 0:
            return {
                "action": "신규 추격 주의",
                "summary": "긍정 재료가 이미 가격에 크게 반영됐을 수 있습니다. 즉시 추격보다 거래량 안정과 새 지지구간 형성을 확인하는 편이 낫습니다.",
            }
        if rule.direction == "POSITIVE":
            return {
                "action": "조건부 신규 진입 검토",
                "summary": "재료 방향은 우호적이지만 전략 적합도·손익비·가격 위치가 함께 맞을 때만 진입을 검토합니다.",
            }
        return {
            "action": "조건 확인 후 판단",
            "summary": "이벤트 방향이 혼재돼 세부조건과 가격 반응 확인이 우선입니다.",
        }

    async def analyze(
        self,
        stock_code: str,
        *,
        position_mode: str = "NOT_HELD",
        days: int = 60,
        detail_limit: int = 4,
        history: list[dict[str, Any]] | None = None,
        reference_price: float | None = None,
        reference_volume: float | None = None,
    ) -> dict[str, Any]:
        try:
            corp_code = await self.dart.resolve_corp_code(stock_code)
        except ProviderError as exc:
            return {
                "available": False,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "mixed_count": 0,
                "risk_gate": False,
                "message": f"OpenDART 이벤트 분석 불가: {exc}",
                "events": [],
            }

        end_date = date.today()
        begin_date = end_date - timedelta(days=max(7, days))
        begin = begin_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")

        try:
            disclosures = await self.dart.disclosures(
                corp_code,
                begin,
                end,
                min(100, max(30, detail_limit * 10)),
            )
        except ProviderError as exc:
            return {
                "available": False,
                "corp_code": corp_code,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "mixed_count": 0,
                "risk_gate": False,
                "message": f"최근 공시 조회 실패: {exc}",
                "events": [],
            }

        classified: list[dict[str, Any]] = []
        for row in disclosures.get("rows", []):
            rule, clean_title = self.classify_title(row.get("report_name"))
            if rule is None:
                continue
            classified.append({
                "rule": rule,
                "receipt_no": row.get("receipt_no"),
                "receipt_date": row.get("receipt_date"),
                "report_name": row.get("report_name"),
                "clean_title": clean_title,
            })

        level_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        classified.sort(
            key=lambda item: (
                level_order.get(item["rule"].impact_level, 9),
                -(int(item.get("receipt_date") or "0") if str(item.get("receipt_date") or "").isdigit() else 0),
            )
        )

        # Company-scale comparison is most useful for contract-like events.
        revenue = await self._latest_revenue(corp_code) if any(
            item["rule"].event_type == "LARGE_CONTRACT" for item in classified[: max(1, detail_limit)]
        ) else None

        async def detail(item: dict[str, Any]) -> dict[str, Any]:
            rule: EventRule = item["rule"]
            summary, structured_facts, structured_source, metrics = await self._structured_detail(
                rule,
                corp_code,
                begin,
                end,
                item.get("receipt_no"),
            )
            document_facts, highlights, document_metrics, document_source = await self._document_detail(
                rule,
                item.get("receipt_no"),
            )
            facts = structured_facts[:]
            existing_labels = {fact.get("label") for fact in facts}
            for fact in document_facts:
                if fact.get("label") not in existing_labels:
                    facts.append(fact)
                    existing_labels.add(fact.get("label"))
            metrics = {**document_metrics, **metrics}

            if rule.event_type == "LARGE_CONTRACT":
                contract_amount = metrics.get("contract_amount")
                annual_revenue = (revenue or {}).get("revenue") if revenue else None
                if contract_amount is not None and annual_revenue:
                    ratio = float(contract_amount) / float(annual_revenue) * 100
                    metrics["contract_to_revenue_pct"] = ratio
                    facts.append({
                        "label": "최근 연매출 대비",
                        "value": f"{ratio:.1f}%",
                        "raw": ratio,
                    })
                    facts.append({
                        "label": "비교 기준 연매출",
                        "value": self._compact_number(float(annual_revenue)),
                        "raw": float(annual_revenue),
                    })

            price_reaction = self._price_reaction(
                item.get("receipt_date"),
                history,
                reference_price=reference_price,
                reference_volume=reference_volume,
            )
            confidence, confidence_label = self._impact_confidence(
                structured=structured_source is not None,
                facts_count=len(facts),
                has_company_scale=metrics.get("contract_to_revenue_pct") is not None,
                price_reaction_available=bool(price_reaction.get("available")),
            )
            headline, conclusion_summary, watch_points = self._current_conclusion(
                rule,
                metrics=metrics,
                price_reaction=price_reaction,
                revenue=revenue,
            )
            user_response = self._user_response(
                rule,
                position_mode=position_mode,
                price_reaction=price_reaction,
                conclusion_headline=headline,
            )
            strategy_effects = self._strategy_effects(rule, price_reaction)

            return {
                "event_type": rule.event_type,
                "level": rule.impact_level,  # backward compatibility
                "impact_level": rule.impact_level,
                "direction": rule.direction,
                "confidence": confidence,
                "confidence_label": confidence_label,
                "receipt_no": item.get("receipt_no"),
                "receipt_date": item.get("receipt_date"),
                "report_name": item.get("report_name"),
                "easy_summary": summary or rule.easy_meaning,
                "facts": facts[:10],
                "document_highlights": highlights if not facts else [],
                "metrics": metrics,
                "price_reaction": price_reaction,
                "current_conclusion": {
                    "headline": headline,
                    "summary": conclusion_summary,
                },
                "strategy_effects": strategy_effects,
                "user_response": user_response,
                "watch_points": watch_points,
                "detail_source": (
                    "STRUCTURED_API"
                    if structured_source
                    else (document_source or "TITLE_RULE")
                ),
                "viewer_url": (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('receipt_no')}"
                    if item.get("receipt_no")
                    else None
                ),
            }

        selected = classified[: max(1, detail_limit)]
        detailed = await asyncio.gather(*(detail(item) for item in selected)) if selected else []

        counts = {
            "HIGH": sum(1 for item in classified if item["rule"].impact_level == "HIGH"),
            "MEDIUM": sum(1 for item in classified if item["rule"].impact_level == "MEDIUM"),
            "LOW": sum(1 for item in classified if item["rule"].impact_level == "LOW"),
            "POSITIVE": sum(1 for item in classified if item["rule"].direction == "POSITIVE"),
            "NEGATIVE": sum(1 for item in classified if item["rule"].direction == "NEGATIVE"),
            "MIXED": sum(1 for item in classified if item["rule"].direction == "MIXED"),
        }

        # Hard gate only for materially negative HIGH events.
        risk_gate = any(
            item["rule"].impact_level == "HIGH" and item["rule"].direction == "NEGATIVE"
            for item in classified
        )

        if risk_gate:
            message = "최근 부정 가능성이 높은 HIGH 이벤트가 확인되어 신규 진입 Risk Gate를 활성화했습니다."
        elif counts["POSITIVE"] > 0:
            message = "최근 긍정 가능성 이벤트가 있습니다. 회사 규모 대비 의미와 가격 반영 정도까지 함께 분석합니다."
        elif counts["MEDIUM"] > 0 or counts["MIXED"] > 0:
            message = "즉시 차단할 이벤트는 없지만 조건에 따라 해석이 달라질 공시가 있습니다."
        else:
            message = "최근 분류 대상 공시에서 중요한 이벤트 영향이 확인되지 않았습니다."

        return {
            "available": True,
            "engine": "EVENT_IMPACT",
            "version": "0.13",
            "corp_code": corp_code,
            "period": {"begin": begin, "end": end, "days": days},
            "total_disclosures": disclosures.get("count", 0),
            "classified_count": len(classified),
            "high_count": counts["HIGH"],
            "medium_count": counts["MEDIUM"],
            "low_count": counts["LOW"],
            "positive_count": counts["POSITIVE"],
            "negative_count": counts["NEGATIVE"],
            "mixed_count": counts["MIXED"],
            "risk_gate": risk_gate,
            "message": message,
            "events": detailed,
            "policy": (
                "Event Impact는 공시 사실·회사 규모·가격 반응을 분리해 계산하는 의사결정 보조 기능입니다. "
                "자동 해석이 불완전하면 원문 확인이 우선이며 실제 주문은 실행하지 않습니다."
            ),
        }
