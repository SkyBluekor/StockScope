from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ConditionSpec:
    key: str
    label: str
    weight: int
    evaluator: Callable[[], tuple[str, str, str]]


class InvestorStyleAnalyzer:
    """Heuristic investor-style fit engine.

    This module models widely known investment philosophies with StockScope data.
    It does not claim to reproduce an investor's real decision process and style
    scores are condition-fit scores, not return probabilities or buy signals.
    """

    STYLE_META: dict[str, dict[str, Any]] = {
        "BUFFETT": {
            "label": "Buffett 스타일",
            "short_label": "Buffett",
            "core": "좋은 사업을 합리적인 가격에 사서 오래 보유하는 방식",
            "horizon": "장기",
            "philosophy": "가격이 조금 싸다는 이유보다 수익성·현금창출력·재무안정성이 오래 유지되는 기업의 질을 먼저 봅니다.",
            "suited_for": [
                "좋은 기업을 몇 년 이상 길게 보유하고 싶은 사용자",
                "단기 급등보다 꾸준한 이익과 현금흐름을 중요하게 보는 사용자",
                "잦은 매매보다 기업의 질과 가격을 함께 보고 싶은 사용자",
            ],
            "less_suited_for": [
                "단기간의 강한 모멘텀이나 빠른 회전매매를 우선하는 사용자",
                "기업 실적보다 차트 돌파 자체를 가장 중요하게 보는 사용자",
            ],
            "process": [
                "StockScope가 최근 여러 해의 이익 지속성을 자동 비교",
                "ROE·이익률·현금흐름을 조합해 기업 품질 자동 판정",
                "부채와 유동성을 계산해 재무 부담 자동 판정",
                "순이익과 영업현금흐름을 비교해 이익의 질 자동 판정",
                "PER 등 현재 가격 배수를 반영해 가격 부담 자동 판정",
                "새 실적이 들어오면 품질·가격 조건을 자동 재평가",
            ],
        },
        "GRAHAM": {
            "label": "Graham 스타일",
            "short_label": "Graham",
            "core": "재무가 버틸 수 있는 기업을 충분히 싼 가격에 사는 보수적 가치투자",
            "horizon": "중장기",
            "philosophy": "기업이 좋아 보여도 가격이 충분히 싸지 않으면 기다립니다. 안전마진과 재무 안정성을 특히 중요하게 봅니다.",
            "suited_for": [
                "인기보다 가격 대비 가치를 중요하게 보는 사용자",
                "시장 관심이 적은 종목도 충분히 싸다면 검토할 수 있는 사용자",
                "빠른 주가 움직임보다 안전마진을 우선하는 사용자",
            ],
            "less_suited_for": [
                "높은 성장률과 시장 주도주를 가장 우선하는 사용자",
                "비싸더라도 강한 종목을 추격하는 방식을 선호하는 사용자",
            ],
            "process": [
                "StockScope가 지속 적자·재무 위험을 먼저 자동 분류",
                "PER·PBR을 보수적 가치 기준과 자동 비교",
                "유동비율·부채비율로 재무 버팀목 자동 판정",
                "최근 여러 해의 흑자 지속성을 자동 확인",
                "가격 배수와 재무안정성을 함께 보고 안전마진 수준 판정",
                "가격 또는 기업가치 조건이 바뀌면 자동 재평가",
            ],
        },
        "LYNCH": {
            "label": "Peter Lynch 스타일",
            "short_label": "Lynch",
            "core": "잘 성장하는 기업을 찾되 성장 속도에 비해 가격이 과하지 않은지 보는 방식",
            "horizon": "중장기",
            "philosophy": "성장 자체보다 성장과 가격의 균형을 봅니다. 이익이 늘어도 기대가 이미 가격에 과도하게 반영됐다면 매력도가 낮아질 수 있습니다.",
            "suited_for": [
                "성장기업을 좋아하지만 무조건 비싼 가격을 지불하고 싶지 않은 사용자",
                "매출·이익 성장률과 PER을 같이 비교하고 싶은 사용자",
                "기업의 성장 단계가 바뀌는지 주기적으로 확인할 수 있는 사용자",
            ],
            "less_suited_for": [
                "성장률보다 자산가치 할인만을 우선하는 사용자",
                "실적보다 단기 가격 돌파만으로 판단하고 싶은 사용자",
            ],
            "process": [
                "StockScope가 최신 매출·이익 YoY를 자동 계산",
                "최근 여러 해 성장 지속성을 자동 비교",
                "PER과 이익 성장률로 PEG를 계산해 성장 대비 가격 자동 판정",
                "부채·현금흐름으로 성장의 재무 건전성 자동 판정",
                "새 실적에서 성장 둔화·가격 부담 변화를 자동 재평가",
            ],
        },
        "CAN_SLIM": {
            "label": "CAN SLIM 스타일",
            "short_label": "CAN SLIM",
            "core": "최근 실적이 빠르게 좋아지고 시장에서도 실제로 강한 주도주를 찾는 방식",
            "horizon": "적극적 성장·모멘텀",
            "philosophy": "좋은 기업이라는 사실만으로 부족합니다. 최근 실적 성장, 시장·업종 주도력, 거래량, 가격 흐름과 시장 환경이 함께 강한지를 봅니다.",
            "suited_for": [
                "실적 성장과 강한 가격 흐름을 함께 보고 싶은 사용자",
                "시장·업종 주도주를 적극적으로 찾는 사용자",
                "가격 구조가 꺾이면 빠르게 재평가할 수 있는 사용자",
            ],
            "less_suited_for": [
                "낮은 가격만 보고 오래 기다리는 가치투자를 선호하는 사용자",
                "시장 흐름을 자주 확인하기 어려운 사용자",
            ],
            "process": [
                "최근 분기·반기 이익 성장(C)을 자동 판정",
                "최근 연간 이익 성장(A)을 자동 판정",
                "새로운 성장 재료(N)는 OpenDART에서 확인 가능한 공시만 자동 반영",
                "거래량과 가격 구조로 수요(S)를 자동 판정",
                "시장·업종 대비 상대강도로 주도력(L)을 자동 판정",
                "기관 후원(I)은 데이터가 없으면 UNKNOWN으로 유지",
                "현재 시장 레짐으로 시장 방향(M)을 자동 판정",
            ],
        },
    }

    @staticmethod
    def unavailable(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "engine": "INVESTOR_STYLE",
            "version": "0.18.2",
            "top_style": None,
            "styles": [],
            "comparison": [],
            "message": reason,
            "policy": "투자 스타일 적합도는 상승확률이나 실제 매수·매도 지시가 아닙니다.",
        }

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _status_points(status: str) -> float:
        return {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}.get(status, 0.0)

    @staticmethod
    def _fit_label(score: float | None, coverage: int) -> tuple[str, str]:
        if score is None or coverage < 35:
            return "UNKNOWN", "판단 보류"
        if score >= 80:
            return "VERY_HIGH", "매우 높음"
        if score >= 68:
            return "HIGH", "높음"
        if score >= 52:
            return "MEDIUM", "중간"
        if score >= 38:
            return "LOW", "낮음"
        return "VERY_LOW", "매우 낮음"

    @staticmethod
    def _annual_growth(years: list[dict[str, Any]], key: str) -> float | None:
        rows = [row for row in years if row.get(key) not in (None, 0)]
        if len(rows) < 2:
            return None
        # years payload is newest first.
        newest = rows[0]
        oldest = rows[min(len(rows) - 1, 2)]
        newest_value = float(newest[key])
        oldest_value = float(oldest[key])
        years_gap = max(1, int(newest["year"]) - int(oldest["year"]))
        if newest_value <= 0 or oldest_value <= 0:
            return None
        return round(((newest_value / oldest_value) ** (1 / years_gap) - 1) * 100, 2)

    @staticmethod
    def _positive_years(years: list[dict[str, Any]], key: str, limit: int = 3) -> tuple[int, int]:
        values = [row.get(key) for row in years[:limit] if row.get(key) is not None]
        return sum(float(value) > 0 for value in values), len(values)

    @classmethod
    def _condition(cls, key: str, label: str, weight: int, status: str, value: str, explanation: str) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "weight": weight,
            "status": status,
            "status_label": {"PASS": "충족", "WARN": "부분 충족", "FAIL": "미충족", "UNKNOWN": "데이터 부족"}.get(status, status),
            "value": value,
            "explanation": explanation,
        }

    @classmethod
    def _score_style(cls, code: str, conditions: list[dict[str, Any]], *, company_type: str | None = None) -> dict[str, Any]:
        known = [item for item in conditions if item["status"] != "UNKNOWN"]
        known_weight = sum(int(item["weight"]) for item in known)
        total_weight = sum(int(item["weight"]) for item in conditions)
        points = sum(int(item["weight"]) * cls._status_points(str(item["status"])) for item in known)
        score = round(points / known_weight * 100, 1) if known_weight else None
        coverage = round(known_weight / total_weight * 100) if total_weight else 0
        fit_code, fit_label = cls._fit_label(score, coverage)
        meta = cls.STYLE_META[code]

        strengths = [f"{item['label']}: {item['explanation']}" for item in conditions if item["status"] == "PASS"][:4]
        weaknesses = [f"{item['label']}: {item['explanation']}" for item in conditions if item["status"] == "FAIL"][:4]
        unknowns = [item["label"] for item in conditions if item["status"] == "UNKNOWN"][:4]

        if fit_code in {"VERY_HIGH", "HIGH"}:
            company_headline = f"이 종목은 {meta['short_label']} 관점의 핵심 조건과 비교적 잘 맞습니다."
        elif fit_code == "MEDIUM":
            company_headline = f"{meta['short_label']} 관점의 장점과 부족한 조건이 함께 있습니다."
        elif fit_code in {"LOW", "VERY_LOW"}:
            company_headline = f"현재 데이터만 보면 {meta['short_label']} 방식의 우선 후보로 보기 어렵습니다."
        else:
            company_headline = f"{meta['short_label']} 방식으로 평가하기에는 데이터가 부족합니다."

        return {
            "code": code,
            "label": meta["label"],
            "short_label": meta["short_label"],
            "score": score,
            "fit": fit_code,
            "fit_label": fit_label,
            "coverage": {
                "known_weight": known_weight,
                "total_weight": total_weight,
                "percent": coverage,
                "known_conditions": len(known),
                "total_conditions": len(conditions),
            },
            "overview": {
                "core": meta["core"],
                "horizon": meta["horizon"],
                "philosophy": meta["philosophy"],
                "suited_for": meta["suited_for"],
                "less_suited_for": meta["less_suited_for"],
                "process": meta["process"],
            },
            "company_type": company_type,
            "company_fit": {
                "headline": company_headline,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "unknowns": unknowns,
            },
            "conditions": conditions,
        }

    @staticmethod
    def _style_action(
        style: dict[str, Any],
        position_mode: str,
        *,
        pullback_confirmation: dict[str, Any] | None = None,
        risk_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        code = str(style["code"])
        fit = str(style.get("fit") or "UNKNOWN")
        holding = position_mode == "HOLDING"
        pullback_confirmation = pullback_confirmation or {}
        risk_gate = risk_gate or {}
        conditions = {str(item.get("key")): item for item in style.get("conditions") or []}

        def cond(key: str) -> dict[str, Any]:
            return conditions.get(key, {"status": "UNKNOWN", "value": "데이터 없음", "explanation": "현재 데이터로 자동 판단할 수 없습니다."})

        def judgement(key: str, label: str, keys: list[str]) -> dict[str, Any]:
            rows = [cond(item) for item in keys]
            known = [row for row in rows if row.get("status") != "UNKNOWN"]
            if not known:
                state, state_label = "UNKNOWN", "판단 보류"
            else:
                score = sum({"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}.get(str(row.get("status")), 0.0) for row in known) / len(known)
                if score >= 0.75:
                    state, state_label = "GOOD", "좋음"
                elif score >= 0.35:
                    state, state_label = "CAUTION", "보통·주의"
                else:
                    state, state_label = "WEAK", "약함"
            pass_rows = [row for row in rows if row.get("status") == "PASS"]
            fail_rows = [row for row in rows if row.get("status") == "FAIL"]
            warn_rows = [row for row in rows if row.get("status") == "WARN"]
            if fail_rows:
                summary = str(fail_rows[0].get("explanation") or "약한 조건이 있습니다.")
            elif warn_rows:
                summary = str(warn_rows[0].get("explanation") or "일부 조건은 보통 수준입니다.")
            elif pass_rows:
                summary = str(pass_rows[0].get("explanation") or "핵심 조건이 양호합니다.")
            else:
                summary = "현재 데이터가 부족해 자동 판정을 보류합니다."
            return {"key": key, "label": label, "status": state, "status_label": state_label, "summary": summary}

        if code == "BUFFETT":
            judgments = [
                judgement("quality", "기업 품질", ["roe", "margin", "earnings_consistency", "cash_quality"]),
                judgement("financial_safety", "재무 안정성", ["stability"]),
                judgement("cash", "현금창출력", ["cashflow", "fcf"]),
                judgement("price", "가격 매력", ["valuation"]),
            ]
            price = cond("valuation")
            blockers = []
            if price.get("status") == "FAIL": blockers.append("기업 품질과 별개로 현재 가격 부담이 높은 편입니다.")
            if cond("cashflow").get("status") == "FAIL": blockers.append("영업현금흐름이 장기 품질 판단을 약화시킵니다.")
            if fit in {"VERY_HIGH", "HIGH"} and price.get("status") == "PASS":
                style_action = "장기 관심 후보 · 가격 조건도 양호"
                style_summary = "기업의 질과 현재 가격 조건이 함께 비교적 잘 맞습니다. 장기 후보로 우선 검토할 수 있습니다."
            elif fit in {"VERY_HIGH", "HIGH"}:
                style_action = "기업은 관심 후보 · 가격 매력 개선 대기"
                style_summary = "기업 품질은 양호하지만 현재 가격 조건이 충분히 매력적인지는 보수적으로 봅니다."
            elif fit == "MEDIUM":
                style_action = "장기 후보 관찰"
                style_summary = "품질 강점과 약점이 섞여 있어 핵심 재무 조건이 개선되는지를 앱이 계속 재평가합니다."
            else:
                style_action = "Buffett 관점 우선순위 낮음"
                style_summary = "현재 데이터에서는 장기 품질 기준이 충분히 맞지 않습니다."
            monitors = [
                {"label": "ROE·수익성", "current": cond("roe").get("explanation"), "effect": "장기 수익성이 약해지면 Buffett 적합도를 낮춥니다."},
                {"label": "현금흐름", "current": cond("cashflow").get("explanation"), "effect": "현금창출력이 악화되면 기업 품질 판단을 낮춥니다."},
                {"label": "가격 부담", "current": cond("valuation").get("explanation"), "effect": "가격 부담이 완화되면 신규 후보 우선순위를 높입니다."},
            ]
        elif code == "GRAHAM":
            judgments = [
                judgement("discount", "가격 할인", ["per", "pbr", "combined"]),
                judgement("financial_safety", "재무 안전성", ["stability", "current_ratio", "debt_ratio"]),
                judgement("earnings", "흑자 지속성", ["earnings"]),
            ]
            discount_rows = [cond("per"), cond("pbr"), cond("combined")]
            discount_pass = sum(row.get("status") == "PASS" for row in discount_rows)
            discount_fail = sum(row.get("status") == "FAIL" for row in discount_rows)
            blockers = []
            if discount_fail >= 2: blockers.append("현재 가격은 Graham식 안전마진 기준에서 충분히 싸다고 보기 어렵습니다.")
            if cond("stability").get("status") == "FAIL": blockers.append("재무안정성 약화가 안전마진을 훼손합니다.")
            if fit in {"VERY_HIGH", "HIGH"} and discount_pass >= 2:
                style_action = "가치 후보 검토 가능"
                style_summary = "재무 버팀목과 가격 할인 조건이 함께 비교적 잘 맞습니다."
            elif fit in {"VERY_HIGH", "HIGH", "MEDIUM"}:
                style_action = "현재 가격에서는 대기"
                style_summary = "기업이 버틸 수 있어도 가격 할인 폭이 충분하지 않으면 Graham 방식에서는 기다리는 쪽에 가깝습니다."
            else:
                style_action = "Graham 관점 우선순위 낮음"
                style_summary = "가격 할인 또는 재무안전성 조건이 현재 기준에 충분히 맞지 않습니다."
            monitors = [
                {"label": "PER·PBR 할인", "current": cond("combined").get("explanation"), "effect": "가격 할인 폭이 커지면 가치 후보 우선순위를 높입니다."},
                {"label": "재무 안전성", "current": cond("stability").get("explanation"), "effect": "부채·유동성이 악화되면 가격이 싸져도 적합도를 낮춥니다."},
                {"label": "흑자 지속", "current": cond("earnings").get("explanation"), "effect": "적자 지속이 확인되면 Graham 후보에서 멀어집니다."},
            ]
        elif code == "LYNCH":
            judgments = [
                judgement("growth", "성장성", ["recent_earnings_growth", "annual_earnings_growth", "revenue_growth"]),
                judgement("growth_price", "성장 대비 가격", ["peg", "valuation"]),
                judgement("financial_safety", "재무 안정성", ["stability"]),
                judgement("cash", "현금흐름", ["cashflow"]),
            ]
            peg_row = cond("peg")
            blockers = []
            if peg_row.get("status") == "FAIL": blockers.append("성장 속도에 비해 현재 가격 기대가 높은 편입니다.")
            if cond("recent_earnings_growth").get("status") == "FAIL": blockers.append("최근 이익 성장세가 Lynch식 성장 후보 기준에 약합니다.")
            if fit in {"VERY_HIGH", "HIGH"} and peg_row.get("status") in {"PASS", "WARN"}:
                style_action = "관심 후보 유지"
                style_summary = "성장성과 성장 대비 가격의 균형이 비교적 잘 맞아 Lynch 관점의 관심 후보로 유지할 수 있습니다."
            elif fit == "MEDIUM":
                style_action = "성장·가격 균형 개선 대기"
                style_summary = "성장성 또는 가격 조건 중 하나가 약해 현재는 우선순위를 높이기 어렵습니다."
            else:
                style_action = "Lynch 관점 우선순위 낮음"
                style_summary = "현재 성장률과 가격의 조합은 Lynch 기준에 충분히 맞지 않습니다."
            monitors = [
                {"label": "최근 이익 성장", "current": cond("recent_earnings_growth").get("explanation"), "effect": "다음 실적에서 성장률이 유지되면 후보 근거를 유지하고 둔화되면 낮춥니다."},
                {"label": "PEG·가격 부담", "current": cond("peg").get("explanation"), "effect": "PEG가 개선되면 성장 대비 가격 매력도를 높입니다."},
                {"label": "현금흐름", "current": cond("cashflow").get("explanation"), "effect": "성장과 현금흐름이 엇갈리면 적합도를 낮춥니다."},
            ]
        else:
            judgments = [
                judgement("earnings_growth", "실적 성장", ["C", "A"]),
                judgement("demand", "수요·거래량", ["S"]),
                judgement("leadership", "시장 주도력", ["L"]),
                judgement("market", "시장 환경", ["M"]),
                judgement("new", "신규 성장 재료", ["N"]),
            ]
            blockers = []
            for key, text in (("S", "거래량·가격 수요가 아직 강하게 확인되지 않았습니다."), ("L", "시장·업종 주도력이 약합니다."), ("M", "현재 시장 환경이 CAN SLIM식 적극적 접근에 불리합니다.")):
                if cond(key).get("status") == "FAIL": blockers.append(text)
            core_ready = all(cond(key).get("status") == "PASS" for key in ("C", "S", "L", "M"))
            if fit in {"VERY_HIGH", "HIGH"} and core_ready:
                style_action = "주도주 후보 검토 가능"
                style_summary = "최근 실적 성장과 수요·주도력·시장 환경이 함께 강해 CAN SLIM 후보 조건이 잘 맞습니다."
            elif fit in {"VERY_HIGH", "HIGH", "MEDIUM"}:
                style_action = "후보 유지 · 핵심 신호 자동 확인 대기"
                style_summary = "일부 성장 조건은 좋지만 주도력·거래량·시장 조건이 모두 맞을 때까지 앱이 자동 재평가합니다."
            else:
                style_action = "CAN SLIM 후보 우선순위 낮음"
                style_summary = "현재 실적 성장과 시장 주도력 조합이 충분히 강하지 않습니다."
            monitors = [
                {"label": "최근 실적(C/A)", "current": f"C {cond('C').get('status_label')} · A {cond('A').get('status_label')}", "effect": "실적 성장 둔화 시 후보 우선순위를 낮춥니다."},
                {"label": "수요·거래량(S)", "current": cond("S").get("explanation"), "effect": "거래량과 가격 구조가 강화되면 후보 신뢰도를 높입니다."},
                {"label": "주도력·시장(L/M)", "current": f"L {cond('L').get('status_label')} · M {cond('M').get('status_label')}", "effect": "상대강도와 시장 환경이 개선되면 후보 우선순위를 높입니다."},
            ]

        risk_active = bool(risk_gate.get("active"))
        pull_state = str(pullback_confirmation.get("state") or "UNKNOWN")
        pull_entry = pullback_confirmation.get("entry_timing") or {}
        short_label = str(pull_entry.get("label") or pullback_confirmation.get("label") or "기술적 진입 상태 별도 판단")
        short_summary = str(pull_entry.get("summary") or pullback_confirmation.get("summary") or "현재 가격 위치는 별도 기술적 분석 결과와 함께 봅니다.")
        pull_progress = pull_entry.get("progress") or {}
        pull_missing = [str(item) for item in (pull_entry.get("most_missing") or []) if item]
        timing_meta = {
            "BUFFETT": ("보조", "단기 반등보다 기업 품질과 가격 매력이 더 중요합니다."),
            "GRAHAM": ("보조", "단기 반등보다 안전마진과 재무 안정성이 더 중요합니다."),
            "LYNCH": ("중요", "기업 성장성과 가격 조건이 좋아도 현재 가격 타이밍이 불완전하면 신규 추격은 대기합니다."),
            "CAN_SLIM": ("매우 중요", "돌파·거래량·상대강도 같은 현재 타이밍이 행동 단계에서 핵심입니다."),
        }
        timing_importance, timing_note = timing_meta.get(code, ("참고", "기업 적합도와 단기 타이밍을 함께 봅니다."))
        entry_progress_label = str(pull_progress.get("label") or "")
        entry_missing = pull_missing[:3]

        # CAN SLIM must not inherit a pullback-only timing gate. Its action timing is
        # driven by current earnings, demand/volume, leadership and market regime.
        if code == "CAN_SLIM":
            can_slim_timing = (("C", "최근 실적 성장"), ("S", "거래량·수요"), ("L", "시장 주도력"), ("M", "시장 환경"))
            can_slim_passed = sum(cond(key).get("status") == "PASS" for key, _ in can_slim_timing)
            entry_progress_label = f"{can_slim_passed}/4 핵심 타이밍 확인"
            entry_missing = [label for key, label in can_slim_timing if cond(key).get("status") != "PASS"][:3]

        if risk_active:
            final_action = "위험 우선 · 신규 진입 판단 보류" if not holding else "위험 우선 · 보유 논리 재점검"
            entry_status = "RISK_FIRST"
            entry_label = "위험 우선"
            entry_summary = str(risk_gate.get("message") or "현재 Risk Gate가 활성화되어 스타일 적합도보다 위험 조건을 먼저 봅니다.")
        elif code == "CAN_SLIM":
            if not entry_missing:
                final_action = style_action + (" · 핵심 타이밍 확인" if not holding else " · 주도력 유지 관찰")
                entry_status = "REVIEW"
                entry_label = "핵심 타이밍 확인"
                entry_summary = "최근 실적(C)·수요/거래량(S)·주도력(L)·시장 환경(M)이 모두 현재 행동 기준을 충족합니다."
            else:
                final_action = style_action + (" · 핵심 타이밍 확인 대기" if not holding else " · 타이밍 재확인")
                entry_status = "WAIT"
                entry_label = "핵심 타이밍 대기"
                entry_summary = f"{entry_progress_label}. 아직 {' · '.join(entry_missing)} 조건이 부족해 CAN SLIM식 적극적 행동 단계는 대기합니다."
        elif code in {"BUFFETT", "GRAHAM"}:
            # These styles are long-horizon/value oriented. A pullback signal is useful
            # context but must not become the primary gate for company/style fit.
            if pull_state == "SUPPORT_FAILED":
                final_action = style_action + (" · 단기 가격 구조 주의" if not holding else " · 단기 지지 이탈 반영")
                entry_status = "CAUTION"
                entry_label = "단기 가격 구조 주의"
                entry_summary = f"눌림·지지 자동판정은 '{short_label}'입니다. 다만 {timing_note} 이 신호 하나로 장기 스타일 적합도를 무효화하지 않습니다."
            elif pull_state == "REBOUND_CONFIRMED":
                final_action = style_action + (" · 단기 반등은 보조 확인" if not holding else " · 단기 반등 확인")
                entry_status = "NEUTRAL"
                entry_label = "단기 반등 확인"
                entry_summary = f"단기 반등은 확인됐습니다. 다만 {timing_note} 현재 행동의 중심은 기업·가치 조건입니다."
            else:
                final_action = style_action + (" · 단기 타이밍은 보조" if not holding else " · 보유 관찰")
                entry_status = "NEUTRAL"
                entry_label = short_label if short_label else "단기 타이밍 보조"
                entry_summary = f"현재 눌림·지지 상태는 '{short_label}'입니다. {timing_note} 기업 적합도 판단을 이 조건만으로 막지 않습니다."
        elif pull_state == "SUPPORT_FAILED":
            final_action = "관심 후보는 유지 가능 · 현재 진입은 보류" if not holding else "보유 근거 재점검 · 지지 실패 반영"
            entry_status = "WAIT"
            entry_label = "진입 보류"
            entry_summary = "기업 스타일 적합성과 별개로 현재 가격 구조에서 지지 실패가 확인됐습니다."
        elif pull_state == "REBOUND_CONFIRMED":
            final_action = style_action + (" · 현재 가격 구조도 검토 가능" if not holding else " · 보유 근거 유지")
            entry_status = "REVIEW"
            entry_label = "검토 가능"
            entry_summary = "앱의 눌림·지지 자동판정에서 반등 확인 상태입니다. 스타일 조건과 현재 가격 구조를 함께 검토할 수 있습니다."
        elif pull_state in {"SUPPORT_APPROACH", "SUPPORT_TESTING", "REBOUND_WAITING", "PULLBACK_IN_PROGRESS"}:
            final_action = (style_action + " · 신규 추격은 대기") if not holding else (style_action + " · 보유 관찰")
            entry_status = "WAIT"
            entry_label = short_label
            progress_text = entry_progress_label
            missing_text = " · ".join(entry_missing[:2])
            entry_summary = (
                f"현재 기술적 상태는 '{short_label}'입니다."
                + (f" {progress_text}." if progress_text else "")
                + (f" 아직 부족한 핵심 조건은 {missing_text}입니다." if missing_text else "")
                + " 다음 데이터에서 앱이 자동 재판정합니다."
            )
        else:
            final_action = style_action
            entry_status = "NEUTRAL"
            entry_label = "별도 기술 판단"
            entry_summary = short_summary

        if blockers:
            reasons = [item for item in style.get("company_fit", {}).get("strengths", [])[:3]]
        else:
            reasons = [item for item in style.get("company_fit", {}).get("strengths", [])[:4]]
        if not reasons:
            reasons = [style_summary]

        do_now = []
        if holding:
            do_now.append("현재 보유 논리가 이 스타일의 핵심 조건과 계속 맞는지 앱의 자동 재평가 결과를 기준으로 관리")
            if entry_status == "RISK_FIRST": do_now.append("추가 판단보다 Risk Gate 해제 여부를 우선")
            elif fit in {"VERY_HIGH", "HIGH"}: do_now.append("스타일 핵심 조건이 유지되는 동안 보유 근거는 유지")
            else: do_now.append("핵심 조건 약화가 이어지면 보유 논리를 재검토")
        else:
            if entry_status in {"RISK_FIRST", "WAIT"}: do_now.append("현재는 신규 진입을 서두르지 않고 앱의 다음 자동판정을 대기")
            elif entry_status == "REVIEW": do_now.append("스타일 적합성과 현재 가격 구조가 함께 맞는 후보로 우선 검토")
            else: do_now.append("스타일 관점의 관심 후보로 유지하고 현재 기술적 행동 단계와 함께 판단")
            if fit in {"VERY_HIGH", "HIGH"}: do_now.append("종목 자체는 이 스타일의 우선 관심 후보로 유지")
            elif fit in {"LOW", "VERY_LOW"}: do_now.append("같은 스타일의 더 적합한 종목과 비교 우선")

        avoid = [
            "스타일 적합도 점수를 상승확률이나 즉시 매수 신호로 해석하지 않기",
            "앱이 이미 계산한 재무·가격 조건을 사용자가 다시 수동 계산할 필요 없음",
        ]

        scenarios = []
        if code == "LYNCH":
            scenarios += [
                {"condition": "다음 실적에서도 이익 성장 유지 + PEG 양호", "effect": "Lynch 관점 우선순위 유지 또는 상승", "tone": "POSITIVE"},
                {"condition": "이익 성장 둔화 또는 PEG 악화", "effect": "성장 대비 가격 매력이 낮아져 우선순위 하락", "tone": "NEGATIVE"},
            ]
        elif code == "BUFFETT":
            scenarios += [
                {"condition": "ROE·현금흐름 유지 + 가격 부담 완화", "effect": "Buffett 관점 장기 후보 매력 상승", "tone": "POSITIVE"},
                {"condition": "수익성·현금흐름 구조적 악화", "effect": "기업 품질 판단 하향", "tone": "NEGATIVE"},
            ]
        elif code == "GRAHAM":
            scenarios += [
                {"condition": "재무안정성 유지 + PER/PBR 할인 확대", "effect": "안전마진 개선으로 가치 후보 우선순위 상승", "tone": "POSITIVE"},
                {"condition": "가격 하락과 함께 재무가 훼손", "effect": "단순 저평가가 아닌 가치 훼손으로 판단해 우선순위 하락", "tone": "NEGATIVE"},
            ]
        else:
            scenarios += [
                {"condition": "실적 성장 유지 + 거래량·주도력·시장 환경 동시 개선", "effect": "CAN SLIM 주도주 후보 우선순위 상승", "tone": "POSITIVE"},
                {"condition": "실적 성장 또는 상대강도 약화", "effect": "CAN SLIM 후보 우선순위 하락", "tone": "NEGATIVE"},
            ]
        if code == "LYNCH" and pull_state in {"SUPPORT_APPROACH", "SUPPORT_TESTING", "REBOUND_WAITING", "PULLBACK_IN_PROGRESS"}:
            scenarios.append({"condition": "앱의 눌림·지지 자동판정이 반등 확인으로 변경", "effect": "현재 단기 진입 단계가 '검토 가능' 쪽으로 개선", "tone": "POSITIVE"})
        if risk_active:
            scenarios.append({"condition": "Risk Gate 해제", "effect": "스타일 적합도를 현재 행동 판단에 다시 정상 반영", "tone": "POSITIVE"})

        return {
            "decision_code": entry_status,
            "current_action": final_action,
            "style_action": style_action,
            "headline": style_summary,
            "summary": f"{style_summary} {entry_summary}",
            "company_judgment": {
                "label": "기업 스타일 적합성",
                "value": style.get("fit_label") or "판단 보류",
                "status": "GOOD" if fit in {"VERY_HIGH", "HIGH"} else "CAUTION" if fit == "MEDIUM" else "WEAK" if fit in {"LOW", "VERY_LOW"} else "UNKNOWN",
                "summary": style.get("company_fit", {}).get("headline") or style_summary,
            },
            "entry_judgment": {
                "label": "현재 진입 단계",
                "value": entry_label,
                "status": entry_status,
                "summary": entry_summary,
                "progress_label": entry_progress_label,
                "missing": entry_missing,
                "timing_importance": timing_importance,
                "timing_note": timing_note,
            },
            "judgments": judgments,
            "reasons": reasons,
            "blockers": blockers,
            "do_now": do_now,
            "avoid_now": avoid,
            "auto_monitor": monitors,
            "decision_scenarios": scenarios,
            "watch": [item["label"] for item in monitors],
            "recheck_conditions": [item["condition"] for item in scenarios],
            "score_note": f"적합도 {style.get('score'):.0f}/100" if style.get("score") is not None else "점수 계산 보류",
            "automation_note": "재무·가격·시장 데이터가 갱신되면 StockScope가 위 조건을 자동으로 다시 판정합니다.",
        }

    def analyze(
        self,
        *,
        fundamental: dict[str, Any],
        relative_strength: dict[str, Any],
        sector_relative_strength: dict[str, Any],
        event_analysis: dict[str, Any],
        effective: dict[str, Any],
        market_context: dict[str, Any],
        position_mode: str,
        pullback_confirmation: dict[str, Any] | None = None,
        risk_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not fundamental.get("available"):
            return self.unavailable("재무 데이터가 부족해 투자 스타일 적합도를 신뢰성 있게 계산할 수 없습니다.")

        latest = fundamental.get("latest_metrics") or {}
        recent = fundamental.get("recent_performance") or {}
        years = list(fundamental.get("years") or [])
        axes = fundamental.get("axes") or {}
        valuation = fundamental.get("valuation") or {}
        eod_val = valuation.get("eod") or {}
        preview_val = valuation.get("preview") or {}

        roe = self._num(latest.get("roe_pct"))
        op_margin = self._num(latest.get("operating_margin_pct"))
        debt_ratio = self._num(latest.get("debt_ratio_pct"))
        current_ratio = self._num(latest.get("current_ratio_pct"))
        ocf = self._num(latest.get("operating_cash_flow"))
        fcf = self._num(latest.get("free_cash_flow"))
        net_income = self._num(latest.get("net_income"))
        per = self._num(preview_val.get("per")) if preview_val else self._num(eod_val.get("per"))
        pbr = self._num(preview_val.get("pbr")) if preview_val else self._num(eod_val.get("pbr"))
        annual_net_growth = self._annual_growth(years, "net_income")
        annual_rev_growth = self._annual_growth(years, "revenue")
        positive_net_years, net_year_count = self._positive_years(years, "net_income", 3)
        recent_op_growth = self._num(recent.get("operating_profit_yoy_pct"))
        recent_net_growth = self._num(recent.get("net_income_yoy_pct"))
        recent_rev_growth = self._num(recent.get("revenue_yoy_pct"))

        stability_status = str((axes.get("stability") or {}).get("status") or "UNKNOWN")
        cash_status = str((axes.get("cashflow") or {}).get("status") or "UNKNOWN")

        def num_condition(key: str, label: str, weight: int, value: float | None, pass_if: Callable[[float], bool], warn_if: Callable[[float], bool], fmt: str, pass_text: str, warn_text: str, fail_text: str) -> dict[str, Any]:
            if value is None:
                return self._condition(key, label, weight, "UNKNOWN", "데이터 없음", "현재 데이터로 자동 판단할 수 없습니다.")
            status = "PASS" if pass_if(value) else "WARN" if warn_if(value) else "FAIL"
            text = pass_text if status == "PASS" else warn_text if status == "WARN" else fail_text
            return self._condition(key, label, weight, status, fmt.format(value), text)

        def axis_condition(key: str, label: str, weight: int, status_code: str, good_text: str, warn_text: str, fail_text: str) -> dict[str, Any]:
            if status_code in {"STRONG", "GOOD"}:
                return self._condition(key, label, weight, "PASS", status_code, good_text)
            if status_code in {"NEUTRAL", "CAUTION"}:
                return self._condition(key, label, weight, "WARN", status_code, warn_text)
            if status_code == "WEAK":
                return self._condition(key, label, weight, "FAIL", status_code, fail_text)
            return self._condition(key, label, weight, "UNKNOWN", "데이터 없음", "현재 데이터로 자동 판단할 수 없습니다.")

        earnings_status = (
            "PASS" if net_year_count >= 3 and positive_net_years == net_year_count
            else "WARN" if net_year_count >= 2 and positive_net_years >= max(1, net_year_count - 1)
            else "FAIL" if net_year_count else "UNKNOWN"
        )
        earnings_expl = (
            f"최근 확인 가능한 {net_year_count}개 연도 모두 순이익 흑자입니다."
            if earnings_status == "PASS"
            else f"최근 {net_year_count}개 연도 중 {positive_net_years}개가 흑자입니다."
            if net_year_count
            else "연간 순이익 이력이 부족합니다."
        )

        cash_quality_status = "UNKNOWN"
        cash_quality_value = "데이터 없음"
        cash_quality_expl = "순이익과 영업현금흐름을 함께 계산할 수 없습니다."
        if net_income is not None and ocf is not None:
            if net_income <= 0:
                cash_quality_status = "WARN" if ocf > 0 else "FAIL"
                cash_quality_value = "적자 구간"
                cash_quality_expl = "순이익이 적자여서 현금 전환 품질을 정상 구간처럼 비교하기 어렵습니다."
            else:
                ratio = ocf / net_income
                cash_quality_value = f"영업현금/순이익 {ratio:.2f}배"
                cash_quality_status = "PASS" if ratio >= 0.8 else "WARN" if ratio >= 0.5 else "FAIL"
                cash_quality_expl = (
                    "장부상 이익이 실제 영업현금으로 비교적 잘 이어집니다."
                    if cash_quality_status == "PASS"
                    else "이익 대비 현금 유입이 다소 약해 이익의 질을 더 확인합니다."
                    if cash_quality_status == "WARN"
                    else "순이익에 비해 영업현금 유입이 약해 이익의 질에 주의가 필요합니다."
                )

        buffett_conditions = [
            num_condition("roe", "ROE", 16, roe, lambda x: x >= 15, lambda x: x >= 8, "{:.1f}%", "자기자본 대비 이익 창출력이 좋은 편입니다.", "수익성은 보통 이상이지만 압도적인 수준은 아닙니다.", "장기 품질 기준에서 자본 효율이 약한 편입니다."),
            num_condition("margin", "영업이익률", 10, op_margin, lambda x: x >= 12, lambda x: x > 0, "{:.1f}%", "영업이익률이 충분히 양수이며 사업 수익성이 좋습니다.", "흑자 수익성은 유지하지만 높은 마진이라고 보긴 어렵습니다.", "영업 수익성이 취약합니다."),
            self._condition("earnings_consistency", "이익 지속성", 14, earnings_status, f"흑자 {positive_net_years}/{net_year_count}년", earnings_expl),
            axis_condition("stability", "재무 안정성", 12, stability_status, "부채·유동성 구조가 장기 보유를 크게 방해하지 않습니다.", "재무 구조에 일부 확인할 부분이 있습니다.", "부채·유동성 부담이 장기 품질을 약화시킵니다."),
            axis_condition("cashflow", "현금흐름", 13, cash_status, "영업현금흐름이 기업 이익을 보조합니다.", "현금흐름이 아주 강하다고 보긴 어렵습니다.", "현금흐름이 장기 품질 판단의 약점입니다."),
            self._condition("cash_quality", "이익의 질", 10, cash_quality_status, cash_quality_value, cash_quality_expl),
            num_condition("fcf", "FCF", 8, fcf, lambda x: x > 0, lambda x: x == 0, "{:.0f}", "투자 후에도 잉여현금이 남는 구조입니다.", "FCF가 거의 남지 않습니다.", "FCF가 음수여서 현금창출의 지속성을 더 확인해야 합니다."),
            num_condition("growth", "장기 이익 성장", 7, annual_net_growth, lambda x: x >= 8, lambda x: x >= 0, "{:+.1f}%/년", "최근 연간 이익이 장기적으로 성장했습니다.", "이익은 유지되지만 성장 속도는 크지 않습니다.", "최근 연간 이익 방향이 약합니다."),
            num_condition("valuation", "가격 부담", 10, per, lambda x: 0 < x <= 25, lambda x: 0 < x <= 35, "PER {:.1f}배", "최근 연간 이익 대비 가격이 과도하게 높다고 보긴 어렵습니다.", "기업 품질이 좋아도 가격 부담을 함께 봐야 합니다.", "현재 이익 대비 가격 배수가 높은 편입니다."),
        ]

        graham_conditions = [
            self._condition("earnings", "흑자 지속성", 15, earnings_status, f"흑자 {positive_net_years}/{net_year_count}년", earnings_expl),
            axis_condition("stability", "재무 안정성", 15, stability_status, "보수적 가치투자 관점에서 재무 버팀목이 있습니다.", "재무안정성이 아주 강하다고 단정하기 어렵습니다.", "재무 위험이 안전마진을 약화시킵니다."),
            num_condition("current_ratio", "유동비율", 10, current_ratio, lambda x: x >= 150, lambda x: x >= 100, "{:.1f}%", "단기 채무 대응 여력이 비교적 충분합니다.", "단기 유동성은 최소 수준은 넘지만 여유가 크지 않습니다.", "단기 유동성 부담이 있습니다."),
            num_condition("debt_ratio", "부채비율", 10, debt_ratio, lambda x: x <= 80, lambda x: x <= 150, "{:.1f}%", "부채 부담이 보수적인 편입니다.", "부채가 아주 낮진 않지만 과도하다고 단정하긴 어렵습니다.", "부채 부담이 보수적 가치 기준에 높습니다."),
            num_condition("per", "PER", 20, per, lambda x: 0 < x <= 15, lambda x: 0 < x <= 22.5, "{:.1f}배", "이익 대비 가격이 보수적 가치 기준에 가까운 편입니다.", "가격이 아주 싸다고 보긴 어렵지만 극단적 부담은 아닙니다.", "이익 대비 가격이 Graham식 보수 기준에는 부담스럽습니다."),
            num_condition("pbr", "PBR", 20, pbr, lambda x: 0 < x <= 1.5, lambda x: 0 < x <= 2.5, "{:.2f}배", "장부가 대비 가격이 보수적인 편입니다.", "장부가 대비 할인 매력은 제한적입니다.", "장부가 대비 가격이 높아 안전마진이 작습니다."),
        ]
        combined = per * pbr if per is not None and pbr is not None and per > 0 and pbr > 0 else None
        graham_conditions.append(num_condition("combined", "PER×PBR", 10, combined, lambda x: x <= 22.5, lambda x: x <= 40, "{:.1f}", "이익과 자산 가격을 함께 본 보수적 배수 조건에 가깝습니다.", "보수적 기준보다 다소 높습니다.", "가격 할인 폭이 Graham식 안전마진 기준에는 부족합니다."))

        lynch_growth = recent_net_growth if recent_net_growth is not None else recent_op_growth
        if lynch_growth is None or lynch_growth <= 0 or per is None or per <= 0:
            peg = None
        else:
            peg = per / lynch_growth
        company_type = "판단 보류"
        growth_basis = lynch_growth if lynch_growth is not None else annual_net_growth
        if growth_basis is not None:
            if growth_basis >= 20:
                company_type = "고성장형에 가까움"
            elif growth_basis >= 8:
                company_type = "안정성장형에 가까움"
            elif growth_basis >= 0:
                company_type = "저성장형에 가까움"
            else:
                company_type = "성장 둔화·회복 확인형"

        lynch_conditions = [
            num_condition("recent_earnings_growth", "최근 이익 성장", 20, lynch_growth, lambda x: x >= 15, lambda x: x >= 5, "{:+.1f}% YoY", "최근 이익 성장 속도가 충분히 강합니다.", "이익은 성장하지만 고성장으로 보기엔 제한적입니다.", "최근 이익 성장이 약하거나 감소했습니다."),
            num_condition("annual_earnings_growth", "연간 이익 성장", 16, annual_net_growth, lambda x: x >= 12, lambda x: x >= 3, "{:+.1f}%/년", "최근 여러 해 이익 성장도 이어졌습니다.", "장기 성장 속도는 완만합니다.", "연간 이익 흐름이 약합니다."),
            num_condition("revenue_growth", "최근 매출 성장", 12, recent_rev_growth, lambda x: x >= 10, lambda x: x >= 0, "{:+.1f}% YoY", "외형 성장도 이익 성장과 함께 확인됩니다.", "매출은 유지·소폭 성장 중입니다.", "최근 매출이 감소했습니다."),
            num_condition("peg", "PEG", 22, peg, lambda x: x <= 1.2, lambda x: x <= 2.0, "{:.2f}", "현재 PER이 최근 이익 성장률에 비해 과도해 보이지 않습니다.", "성장 대비 가격은 중간 수준입니다.", "성장 속도에 비해 가격 기대가 높은 편입니다."),
            axis_condition("stability", "재무 안정성", 10, stability_status, "성장을 버틸 재무 기반이 양호합니다.", "성장 지속성 판단에 재무 확인이 더 필요합니다.", "부채·유동성 부담이 성장 지속성을 약화시킵니다."),
            axis_condition("cashflow", "현금흐름", 10, cash_status, "성장이 실제 현금흐름으로도 이어지는 편입니다.", "현금흐름이 성장성을 강하게 뒷받침하진 못합니다.", "실적 성장과 현금흐름 사이의 괴리가 큽니다."),
            num_condition("valuation", "PER 부담", 10, per, lambda x: 0 < x <= 25, lambda x: 0 < x <= 40, "{:.1f}배", "성장주 관점에서도 가격 부담이 지나치게 크진 않습니다.", "성장 지속성이 확인돼야 현재 가격을 정당화할 수 있습니다.", "높은 가격 배수 때문에 성장 둔화에 민감할 수 있습니다."),
        ]

        positive_events = [event for event in (event_analysis.get("events") or []) if event.get("direction") == "POSITIVE"]
        strong_new = [event for event in positive_events if event.get("impact_level") in {"HIGH", "MEDIUM"}]
        if strong_new:
            n_cond = self._condition("N", "N · 새로운 성장 재료", 10, "PASS", str(strong_new[0].get("report_name") or "긍정 중요 공시"), "확인 가능한 최근 공시 중 의미 있는 긍정 재료가 있습니다.")
        elif positive_events:
            n_cond = self._condition("N", "N · 새로운 성장 재료", 10, "WARN", str(positive_events[0].get("report_name") or "긍정 공시"), "긍정 공시는 있으나 강한 신규 성장 재료로 단정하기엔 제한적입니다.")
        else:
            n_cond = self._condition("N", "N · 새로운 성장 재료", 10, "UNKNOWN", "확인 불가", "공시에서 확인되지 않았다고 새로운 제품·사업이 없다고 단정할 수 없어 UNKNOWN으로 둡니다.")

        market_excess = self._num(relative_strength.get("primary_excess_pct"))
        sector_excess = self._num(sector_relative_strength.get("primary_excess_pct")) if sector_relative_strength.get("available") else None
        if market_excess is None:
            leader_status, leader_value, leader_expl = "UNKNOWN", "데이터 없음", "시장 상대강도를 계산하지 못했습니다."
        elif sector_excess is None:
            leader_status = "PASS" if market_excess >= 5 else "WARN" if market_excess >= 0 else "FAIL"
            leader_value = f"시장 대비 {market_excess:+.1f}%p"
            leader_expl = "업종 비교는 없지만 시장 대비 주도력을 기준으로 봅니다."
        else:
            if market_excess >= 3 and sector_excess >= 2:
                leader_status = "PASS"
            elif market_excess >= 0 or sector_excess >= 0:
                leader_status = "WARN"
            else:
                leader_status = "FAIL"
            leader_value = f"시장 {market_excess:+.1f}%p · 업종 {sector_excess:+.1f}%p"
            leader_expl = "시장과 업종을 동시에 이기는지가 CAN SLIM의 주도주 조건에 중요합니다."

        volume_ratio = self._num(effective.get("volume_ratio_20"))
        distance_high = self._num(effective.get("distance_to_20d_high_pct"))
        if volume_ratio is None and distance_high is None:
            supply_status, supply_value, supply_expl = "UNKNOWN", "데이터 없음", "거래량과 고점 거리 데이터가 부족합니다."
        else:
            vol_good = volume_ratio is not None and volume_ratio >= 1.3
            near_high = distance_high is not None and distance_high >= -3
            supply_status = "PASS" if vol_good and near_high else "WARN" if vol_good or near_high else "FAIL"
            supply_value = f"거래량 {volume_ratio:.2f}배" if volume_ratio is not None else f"20일 고점 거리 {distance_high:+.1f}%"
            supply_expl = "평균 대비 거래량과 최근 고점 접근 여부로 실제 수요가 붙는지 봅니다."

        regime = str(market_context.get("regime") or "UNKNOWN")
        market_status = "PASS" if regime == "TREND_UP" else "WARN" if regime == "RANGE" else "FAIL" if regime in {"TREND_DOWN", "PANIC"} else "UNKNOWN"
        market_expl = {
            "PASS": "시장 방향이 상승 쪽이라 성장·모멘텀 전략에 우호적입니다.",
            "WARN": "시장 방향이 뚜렷한 상승은 아니라 종목 강도를 더 엄격히 봅니다.",
            "FAIL": "시장 방향이 약해 CAN SLIM식 적극적 접근에는 불리합니다.",
            "UNKNOWN": "시장 방향을 충분히 확인하지 못했습니다.",
        }[market_status]

        c_growth = max([value for value in (recent_net_growth, recent_op_growth) if value is not None], default=None)
        can_slim_conditions = [
            num_condition("C", "C · 최근 실적 성장", 18, c_growth, lambda x: x >= 25, lambda x: x >= 10, "{:+.1f}% YoY", "최근 이익 성장률이 강합니다.", "최근 실적은 성장하지만 CAN SLIM식 강한 성장 기준에는 다소 부족합니다.", "최근 이익 성장 속도가 약합니다."),
            num_condition("A", "A · 연간 이익 성장", 15, annual_net_growth, lambda x: x >= 20, lambda x: x >= 5, "{:+.1f}%/년", "연간 이익 성장도 강하게 이어집니다.", "연간 이익은 성장하지만 속도가 아주 높진 않습니다.", "연간 이익 성장 흐름이 약합니다."),
            n_cond,
            self._condition("S", "S · 수요/거래량", 15, supply_status, supply_value, supply_expl),
            self._condition("L", "L · 시장 주도력", 18, leader_status, leader_value, leader_expl),
            self._condition("I", "I · 기관 후원", 10, "UNKNOWN", "현재 미수집", "현재 StockScope는 기관 보유·후원 데이터를 신뢰성 있게 수집하지 않아 0점 처리하지 않습니다."),
            self._condition("M", "M · 시장 방향", 14, market_status, regime, market_expl),
        ]

        styles = [
            self._score_style("BUFFETT", buffett_conditions),
            self._score_style("GRAHAM", graham_conditions),
            self._score_style("LYNCH", lynch_conditions, company_type=company_type),
            self._score_style("CAN_SLIM", can_slim_conditions),
        ]
        for style in styles:
            style["action_plan"] = self._style_action(style, position_mode, pullback_confirmation=pullback_confirmation, risk_gate=risk_gate)

        ranked = sorted(styles, key=lambda item: (-1 if item.get("score") is None else float(item["score"])), reverse=True)
        top = ranked[0] if ranked else None
        top_style = None if top is None else {
            "code": top["code"],
            "label": top["label"],
            "score": top["score"],
            "fit": top["fit"],
            "fit_label": top["fit_label"],
            "coverage_percent": top["coverage"]["percent"],
            "summary": top["company_fit"]["headline"],
            "current_action": top["action_plan"]["current_action"],
            "action_summary": top["action_plan"]["summary"],
        }

        comparison = [
            {
                "code": style["code"],
                "label": style["short_label"],
                "score": style["score"],
                "fit_label": style["fit_label"],
                "core": style["overview"]["core"],
                "horizon": style["overview"]["horizon"],
            }
            for style in ranked
        ]

        return {
            "available": True,
            "engine": "INVESTOR_STYLE",
            "version": "0.18.2",
            "top_style": top_style,
            "styles": styles,
            "comparison": comparison,
            "message": (
                f"현재 데이터에서는 {top_style['label']} 적합도가 가장 높습니다."
                if top_style and top_style.get("score") is not None
                else "투자 스타일 적합도를 충분히 계산하지 못했습니다."
            ),
            "data_basis": {
                "fundamental": fundamental.get("data_basis", {}).get("financial"),
                "relative_strength": "KRX 확정 EOD 시장·업종 상대강도",
                "event": "OpenDART 최근 공시 Event Impact",
                "market": str(market_context.get("regime") or "UNKNOWN"),
            },
            "policy": (
                "각 점수는 공개적으로 알려진 투자 철학을 StockScope 데이터 조건으로 모델링한 적합도입니다. "
                "실제 Buffett·Graham·Lynch·O'Neil의 개별 투자결정을 복제하지 않으며 상승확률·수익률 예측·매수 신호가 아닙니다. "
                "UNKNOWN 조건은 0점으로 벌점 처리하지 않고 평가 커버리지에 별도 표시합니다."
            ),
        }
