from __future__ import annotations

import re
from typing import Any


class SectorRelativeStrengthAnalyzer:
    """Resolve a broad KRX sector benchmark and compare a stock with that sector.

    OpenDART exposes an industry code for each listed company, while the KRX Open API
    used by StockScope exposes daily index series but no constituent->sector mapping
    endpoint.  We therefore use a conservative ruleset from the OpenDART industry code
    to a small set of KRX industry-index aliases.  If a reliable KRX index row cannot be
    found, sector-relative analysis is left unavailable rather than guessed.
    """

    PERIODS = (5, 20, 60)

    # Keys are the first two digits of the OpenDART industry code (KSIC-like grouping).
    # The first alias is the preferred current KRX industry name; older names are kept
    # only as fallbacks because KRX industry classifications can change over time.
    INDUSTRY_MAP: dict[str, dict[str, Any]] = {
        "10": {"group": "음식료·담배", "aliases": ["음식료·담배", "음식료품", "음식료"]},
        "11": {"group": "음식료·담배", "aliases": ["음식료·담배", "음식료품", "음식료"]},
        "12": {"group": "음식료·담배", "aliases": ["음식료·담배", "음식료품", "음식료"]},
        "13": {"group": "섬유·의류", "aliases": ["섬유·의류", "섬유·의복", "섬유의류", "섬유의복"]},
        "14": {"group": "섬유·의류", "aliases": ["섬유·의류", "섬유·의복", "섬유의류", "섬유의복"]},
        "15": {"group": "섬유·의류", "aliases": ["섬유·의류", "섬유·의복", "섬유의류", "섬유의복"]},
        "16": {"group": "종이·목재", "aliases": ["종이·목재", "종이목재"]},
        "17": {"group": "종이·목재", "aliases": ["종이·목재", "종이목재"]},
        "19": {"group": "화학", "aliases": ["화학"]},
        "20": {"group": "화학", "aliases": ["화학"]},
        "21": {"group": "제약", "aliases": ["제약", "의약품"]},
        "22": {"group": "화학", "aliases": ["화학"]},
        "23": {"group": "비금속", "aliases": ["비금속", "비금속광물"]},
        "24": {"group": "금속", "aliases": ["금속", "철강·금속", "철강금속"]},
        "25": {"group": "금속", "aliases": ["금속", "철강·금속", "철강금속"]},
        "26": {"group": "전기·전자", "aliases": ["전기·전자", "전기전자", "반도체"]},
        "27": {"group": "의료·정밀기기", "aliases": ["의료·정밀기기", "의료정밀", "의료정밀기기"]},
        "28": {"group": "전기·전자", "aliases": ["전기·전자", "전기전자", "일반전기전자"]},
        "29": {"group": "기계·장비", "aliases": ["기계·장비", "기계장비", "기계"]},
        "30": {"group": "운송장비·부품", "aliases": ["운송장비·부품", "운송장비부품", "운수장비", "자동차"]},
        "31": {"group": "운송장비·부품", "aliases": ["운송장비·부품", "운송장비부품", "운수장비"]},
        "35": {"group": "전기·가스", "aliases": ["전기·가스", "전기가스", "전기·가스업", "전기가스업"]},
        "41": {"group": "건설", "aliases": ["건설", "건설업"]},
        "42": {"group": "건설", "aliases": ["건설", "건설업"]},
        "45": {"group": "유통", "aliases": ["유통", "유통업"]},
        "46": {"group": "유통", "aliases": ["유통", "유통업"]},
        "47": {"group": "유통", "aliases": ["유통", "유통업"]},
        "49": {"group": "운송·창고", "aliases": ["운송·창고", "운송창고", "운수·창고", "운수창고"]},
        "50": {"group": "운송·창고", "aliases": ["운송·창고", "운송창고", "운수·창고", "운수창고"]},
        "51": {"group": "운송·창고", "aliases": ["운송·창고", "운송창고", "운수·창고", "운수창고"]},
        "52": {"group": "운송·창고", "aliases": ["운송·창고", "운송창고", "운수·창고", "운수창고"]},
        "58": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업", "서비스"]},
        "59": {"group": "오락·문화", "aliases": ["오락·문화", "오락문화", "일반서비스", "서비스업"]},
        "60": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업", "방송서비스"]},
        "61": {"group": "통신", "aliases": ["통신", "통신업", "통신서비스"]},
        "62": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업", "소프트웨어"]},
        "63": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업", "인터넷"]},
        "64": {"group": "금융", "aliases": ["금융", "금융업", "은행", "증권"]},
        "65": {"group": "금융", "aliases": ["금융", "금융업", "보험"]},
        "66": {"group": "금융", "aliases": ["금융", "금융업", "증권"]},
        "68": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "69": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "70": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "71": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "72": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "73": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "74": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "75": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "85": {"group": "일반서비스", "aliases": ["일반서비스", "서비스업"]},
        "86": {"group": "의료·정밀기기", "aliases": ["의료·정밀기기", "의료정밀", "일반서비스"]},
        "90": {"group": "오락·문화", "aliases": ["오락·문화", "오락문화", "일반서비스"]},
        "91": {"group": "오락·문화", "aliases": ["오락·문화", "오락문화", "일반서비스"]},
    }

    @staticmethod
    def normalize_index_name(value: str | None) -> str:
        return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "")).lower()

    @classmethod
    def map_industry_code(cls, industry_code: str | None) -> dict[str, Any]:
        code = re.sub(r"\D", "", str(industry_code or ""))
        if len(code) < 2:
            return {
                "available": False,
                "industry_code": industry_code,
                "sector_group": None,
                "aliases": [],
                "reason": "OpenDART 업종코드를 확인하지 못했습니다.",
            }
        prefix = code[:2]
        mapped = cls.INDUSTRY_MAP.get(prefix)
        if mapped is None:
            return {
                "available": False,
                "industry_code": code,
                "industry_prefix": prefix,
                "sector_group": None,
                "aliases": [],
                "reason": f"업종코드 {code}는 현재 KRX 업종지수 자동 매핑 범위에 없습니다.",
            }
        return {
            "available": True,
            "industry_code": code,
            "industry_prefix": prefix,
            "sector_group": mapped["group"],
            "aliases": list(mapped["aliases"]),
            "mapping_method": "OpenDART 업종코드 → KRX 업종지수 규칙 매핑",
            "mapping_confidence": "MEDIUM",
            "mapping_confidence_label": "보통",
            "reason": "OpenDART 업종코드를 KRX 업종지수 후보로 보수적으로 매핑했습니다.",
        }

    @classmethod
    def match_index_row(
        cls,
        rows: list[dict[str, Any]],
        aliases: list[str],
    ) -> dict[str, Any] | None:
        if not aliases:
            return None
        normalized_aliases = [(alias, cls.normalize_index_name(alias)) for alias in aliases]
        scored: list[tuple[int, int, dict[str, Any], str]] = []

        for row in rows:
            if row.get("close") is None or not row.get("name"):
                continue
            name = str(row.get("name") or "")
            norm_name = cls.normalize_index_name(name)
            class_text = str(row.get("class") or "")
            sector_class = "업종" in class_text or "산업" in class_text

            for alias_index, (alias, norm_alias) in enumerate(normalized_aliases):
                if not norm_alias:
                    continue
                if norm_name == norm_alias:
                    score = 0
                elif norm_alias in norm_name or norm_name in norm_alias:
                    score = 3
                else:
                    continue
                if not sector_class:
                    score += 2
                scored.append((score, alias_index, row, alias))

        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1], len(str(item[2].get("name") or ""))))
        score, _, row, alias = scored[0]
        return {
            **row,
            "matched_alias": alias,
            "match_confidence": "HIGH" if score <= 1 else "MEDIUM",
            "match_confidence_label": "높음" if score <= 1 else "보통",
        }

    @staticmethod
    def _close_by_date(rows: list[dict[str, Any]]) -> dict[str, float]:
        result: dict[str, float] = {}
        for row in rows:
            raw = row.get("close")
            row_date = str(row.get("date") or "")
            if not row_date or raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[row_date] = value
        return result

    @staticmethod
    def _period_label(excess: float) -> tuple[str, str]:
        if excess >= 5:
            return "STRONG", "강함"
        if excess >= 1:
            return "OUTPERFORM", "다소 강함"
        if excess > -1:
            return "NEUTRAL", "중립"
        if excess > -5:
            return "UNDERPERFORM", "다소 약함"
        return "WEAK", "약함"

    @staticmethod
    def _strategy_effects(primary_excess: float | None) -> list[dict[str, Any]]:
        specs = [
            ("trend_following", "추세추종", 4, lambda value: value > 0),
            ("pullback", "눌림목", 4, lambda value: value >= 0),
            ("breakout", "돌파", 8, lambda value: value > 0),
            ("momentum_continuation", "모멘텀 지속", 4, lambda value: value > 0),
        ]
        effects: list[dict[str, Any]] = []
        for strategy, label, weight, condition in specs:
            if primary_excess is None:
                effects.append({
                    "strategy": strategy,
                    "label": label,
                    "weight": weight,
                    "condition_met": None,
                    "direction": "NEUTRAL",
                    "message": "업종 대비 상대강도 데이터가 없어 기존 시장 상대강도 조건을 fallback으로 사용합니다.",
                })
                continue
            met = bool(condition(primary_excess))
            effects.append({
                "strategy": strategy,
                "label": label,
                "weight": weight,
                "condition_met": met,
                "direction": "UP" if met else "DOWN",
                "message": (
                    f"20일 업종 대비 {primary_excess:+.2f}%p로 업종 상대강도 조건을 충족합니다."
                    if met
                    else f"20일 업종 대비 {primary_excess:+.2f}%p로 업종 상대강도 조건을 충족하지 못합니다."
                ),
            })
        return effects

    @staticmethod
    def _trend(relative_ratios: list[float]) -> tuple[str, str, str]:
        if len(relative_ratios) < 11:
            return "UNKNOWN", "판단 보류", "업종 대비 상대강도 추세를 비교할 데이터가 부족합니다."
        recent = (relative_ratios[-1] / relative_ratios[-6] - 1) * 100
        previous = (relative_ratios[-6] / relative_ratios[-11] - 1) * 100
        delta = recent - previous
        if delta >= 1.5:
            return "IMPROVING", "개선 중", f"최근 업종 대비 상대 흐름이 직전 구간보다 {delta:+.2f}%p 개선됐습니다."
        if delta <= -1.5:
            return "DETERIORATING", "약화 중", f"최근 업종 대비 상대 흐름이 직전 구간보다 {delta:+.2f}%p 약해졌습니다."
        return "STABLE", "유지", f"최근 업종 대비 상대강도 변화가 {delta:+.2f}%p로 큰 변화는 없습니다."

    @classmethod
    def _combined_decision(
        cls,
        *,
        market_excess: float | None,
        sector_excess: float | None,
        sector_name: str,
        market_name: str,
        position_mode: str,
    ) -> dict[str, Any]:
        perspective = "보유 관리" if position_mode == "HOLDING" else "신규 진입"
        if market_excess is None or sector_excess is None:
            return {
                "archetype": "UNKNOWN",
                "label": "업종 비교 판단 보류",
                "headline": "시장과 업종을 함께 비교할 데이터가 부족합니다.",
                "summary": "시장 상대강도 결과는 사용할 수 있지만 업종 내 위치는 아직 판단하지 않습니다.",
                "user_response": {
                    "perspective": perspective,
                    "action": "시장 상대강도 결과 우선",
                    "summary": "업종 비교가 가능한 데이터가 확보될 때까지 기존 시장·기술·리스크 분석을 우선합니다.",
                },
                "preferred_strategies": [],
                "deprioritized_strategies": [],
                "why": ["20거래일 시장/업종 공통 데이터를 충분히 맞추지 못했습니다."],
                "watch_points": ["업종지수 데이터와 종목 거래일이 충분히 맞는지 재확인"],
                "market_excess_pct": market_excess,
                "sector_excess_pct": sector_excess,
                "sector_vs_market_pct": None,
            }

        sector_vs_market = market_excess - sector_excess
        why: list[str] = [
            f"20일 기준 {market_name} 대비 {market_excess:+.2f}%p입니다.",
            f"20일 기준 {sector_name} 업종 대비 {sector_excess:+.2f}%p입니다.",
        ]
        watch: list[str] = []
        preferred: list[str] = []
        deprioritized: list[str] = []

        if market_excess >= 1 and sector_excess >= 1:
            if sector_vs_market <= -1:
                archetype = "INDEPENDENT_LEADER"
                label = "독립 강세형"
                headline = "업종 자체는 시장보다 약하지만 이 종목은 시장과 업종을 모두 이기고 있습니다."
                summary = "업종 전체 흐름보다 종목 자체의 재료·실적·수급이 더 강할 가능성이 있는 구조입니다."
                new_action = "종목 고유 강세 원인 확인 후 우선 검토"
                hold_action = "보유 근거 강화 · 종목 고유 재료 확인"
                preferred = ["추세추종", "돌파", "모멘텀 지속"]
                why.append(f"{sector_name} 업종 자체는 {market_name}보다 약 {abs(sector_vs_market):.2f}%p 약합니다.")
                watch += ["업종이 약한데도 종목 상대강도가 계속 유지되는지", "공시·실적 등 종목 고유 재료가 약화되지 않는지"]
            else:
                archetype = "DUAL_LEADER"
                label = "시장·업종 동시 주도형"
                headline = "시장보다 강하고 같은 업종 안에서도 강한 종목입니다."
                summary = "시장 상승에 편승한 것만이 아니라 동종 업종 안에서도 상대적인 힘이 확인됩니다."
                new_action = "추세·돌파 후보 우선 검토"
                hold_action = "상대강도 측면 보유 근거 강화"
                preferred = ["추세추종", "돌파", "모멘텀 지속"]
                watch += ["업종 대비 우위가 0%p 아래로 내려가는지", "시장 대비 우위가 약화되는지"]
        elif market_excess >= 1 and sector_excess <= -1:
            archetype = "SECTOR_LAGGARD"
            label = "업종 내 열위형"
            headline = "시장보다 강해 보이지만 같은 업종 안에서는 뒤처지고 있습니다."
            summary = "업종 전체가 더 강해서 종목이 좋아 보일 수 있습니다. 같은 업종의 더 강한 대안을 비교할 가치가 큽니다."
            new_action = "같은 업종의 더 강한 종목과 비교 우선"
            hold_action = "보유 유지 전 업종 내 상대약세 원인 점검"
            preferred = ["눌림목", "지지선 반등"]
            deprioritized = ["추격 돌파", "모멘텀 지속"]
            why.append(f"{sector_name} 업종은 {market_name}보다 약 {sector_vs_market:+.2f}%p 강한데 이 종목은 업종보다 약합니다.")
            watch += ["업종 대비 성과가 0%p 이상으로 회복하는지", "같은 업종 강세주와 격차가 더 벌어지는지"]
        elif market_excess >= 1 and -1 < sector_excess < 1:
            archetype = "SECTOR_DRIVEN"
            label = "업종 수혜형"
            headline = "시장보다 강하지만 같은 업종 안에서는 특별히 앞서지 않습니다."
            summary = "종목 자체의 독립 강세라기보다 업종 전체의 강한 흐름에 함께 올라가는 성격이 큽니다."
            new_action = "같은 업종 대안 비교 후 선별"
            hold_action = "업종 흐름 유지 여부와 함께 보유 관찰"
            preferred = ["추세추종", "눌림목"]
            why.append(f"{sector_name} 업종과 종목의 20일 성과 차이는 {sector_excess:+.2f}%p로 거의 비슷합니다.")
            watch += ["업종 대비 +1%p 이상 우위가 생기는지", "업종 전체 상대강도가 꺾이는지"]
        elif market_excess <= -1 and sector_excess >= 1:
            archetype = "WEAK_SECTOR_WINNER"
            label = "약한 시장 속 업종 내 상대우위"
            headline = "시장 전체보다 약하지만 같은 업종 안에서는 상대적으로 선방하고 있습니다."
            summary = "동종 종목 중에서는 강하지만 시장을 이기지 못해 공격적인 추세 후보로 보기에는 한 단계 부족합니다."
            new_action = "시장 대비 회복 확인 전 관찰 우선"
            hold_action = "업종 내 우위는 긍정 · 시장 회복 여부 확인"
            preferred = ["추세 회복", "지지선 반등"]
            deprioritized = ["추격 돌파"]
            watch += ["시장 대비 성과가 0%p 이상으로 회복하는지", "업종 대비 우위가 유지되는지"]
        elif market_excess <= -1 and sector_excess <= -1:
            archetype = "DOUBLE_LAGGARD"
            label = "시장·업종 동시 소외형"
            headline = "시장보다도 약하고 같은 업종 안에서도 약한 위치입니다."
            summary = "추세·돌파 관점에서 굳이 우선할 이유가 적어 상대강도 회복 전까지 후보 우선순위를 낮추는 편이 합리적입니다."
            new_action = "신규 추세·돌파 후보 우선순위 낮춤"
            hold_action = "보유 근거 재점검 요소"
            preferred = ["과매도 반등", "추세 회복"]
            deprioritized = ["추세추종", "돌파", "모멘텀 지속"]
            watch += ["시장 대비 0%p 회복", "업종 대비 0%p 회복"]
        else:
            archetype = "MIXED"
            label = "혼합형"
            headline = "시장과 업종 비교 신호가 서로 엇갈려 상대강도만으로 우선순위를 정하기 어렵습니다."
            summary = "기술적 위치·공시·리스크·가격 구조를 함께 보는 것이 더 중요합니다."
            new_action = "다른 분석 근거와 함께 선별"
            hold_action = "상대강도 영향 중립"
            watch += ["시장/업종 대비 방향이 같은 쪽으로 정렬되는지"]

        user_action = hold_action if position_mode == "HOLDING" else new_action
        user_summary = (
            "현재 보유 중이므로 상대강도는 즉시 매도 신호가 아니라 보유 논리를 강화하거나 재점검하는 보조 기준으로 사용합니다."
            if position_mode == "HOLDING"
            else "신규 진입 관점에서는 같은 시장·업종의 다른 후보와 비교해 우선순위를 정하는 데 사용합니다."
        )

        return {
            "archetype": archetype,
            "label": label,
            "headline": headline,
            "summary": summary,
            "user_response": {
                "perspective": perspective,
                "action": user_action,
                "summary": user_summary,
            },
            "preferred_strategies": preferred,
            "deprioritized_strategies": deprioritized,
            "why": why,
            "watch_points": list(dict.fromkeys(watch)),
            "market_excess_pct": round(market_excess, 3),
            "sector_excess_pct": round(sector_excess, 3),
            "sector_vs_market_pct": round(sector_vs_market, 3),
        }

    def unavailable(
        self,
        *,
        market: str,
        industry_code: str | None,
        reason: str,
        market_relative: dict[str, Any] | None,
        position_mode: str,
        mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market_name = str(((market_relative or {}).get("benchmark") or {}).get("name") or market.upper())
        decision = self._combined_decision(
            market_excess=(market_relative or {}).get("primary_excess_pct"),
            sector_excess=None,
            sector_name=(mapping or {}).get("sector_group") or "업종",
            market_name=market_name,
            position_mode=position_mode,
        )
        return {
            "available": False,
            "source": "OpenDART+KRX_EOD",
            "price_basis": "CONFIRMED_EOD",
            "industry_code": industry_code,
            "mapping": mapping or {},
            "benchmark": None,
            "as_of": None,
            "aligned_points": 0,
            "primary_period": None,
            "primary_excess_pct": None,
            "status": "UNKNOWN",
            "label": "업종 비교 불가",
            "trend": "UNKNOWN",
            "trend_label": "판단 보류",
            "trend_message": reason,
            "periods": [],
            "strategy_effects": self._strategy_effects(None),
            "decision": decision,
            "message": reason,
            "note": "업종 매핑이 불확실하면 임의 추정하지 않고 시장 상대강도만 사용합니다.",
        }

    def analyze(
        self,
        stock_rows: list[dict[str, Any]],
        sector_rows: list[dict[str, Any]],
        *,
        market: str,
        industry_code: str | None,
        mapping: dict[str, Any],
        benchmark_name: str,
        market_relative: dict[str, Any],
        position_mode: str,
    ) -> dict[str, Any]:
        stock = self._close_by_date(stock_rows)
        sector = self._close_by_date(sector_rows)
        common_dates = sorted(set(stock) & set(sector))

        if len(common_dates) < 2:
            return self.unavailable(
                market=market,
                industry_code=industry_code,
                reason="종목과 업종지수의 공통 KRX 거래일 데이터가 부족합니다.",
                market_relative=market_relative,
                position_mode=position_mode,
                mapping=mapping,
            )

        stock_values = [stock[d] for d in common_dates]
        sector_values = [sector[d] for d in common_dates]
        ratios = [s / b for s, b in zip(stock_values, sector_values, strict=True) if b > 0]

        periods: list[dict[str, Any]] = []
        by_period: dict[int, dict[str, Any]] = {}
        for days in self.PERIODS:
            if len(common_dates) < days + 1:
                row = {
                    "days": days,
                    "available": False,
                    "stock_return_pct": None,
                    "sector_return_pct": None,
                    "excess_return_pct": None,
                    "status": "UNKNOWN",
                    "label": "데이터 부족",
                }
            else:
                stock_return = (stock_values[-1] / stock_values[-(days + 1)] - 1) * 100
                sector_return = (sector_values[-1] / sector_values[-(days + 1)] - 1) * 100
                excess = stock_return - sector_return
                status, label = self._period_label(excess)
                row = {
                    "days": days,
                    "available": True,
                    "stock_return_pct": round(stock_return, 3),
                    "sector_return_pct": round(sector_return, 3),
                    "excess_return_pct": round(excess, 3),
                    "status": status,
                    "label": label,
                }
            periods.append(row)
            by_period[days] = row

        primary = by_period[20] if by_period[20]["available"] else by_period[5]
        primary_excess = primary.get("excess_return_pct") if primary.get("available") else None
        status, label = self._period_label(float(primary_excess)) if primary_excess is not None else ("UNKNOWN", "데이터 부족")
        trend, trend_label, trend_message = self._trend(ratios)
        market_name = str((market_relative.get("benchmark") or {}).get("name") or market.upper())
        decision = self._combined_decision(
            market_excess=market_relative.get("primary_excess_pct"),
            sector_excess=float(primary_excess) if primary_excess is not None else None,
            sector_name=benchmark_name,
            market_name=market_name,
            position_mode=position_mode,
        )

        return {
            "available": primary_excess is not None,
            "source": "OpenDART+KRX_EOD",
            "price_basis": "CONFIRMED_EOD",
            "industry_code": industry_code,
            "mapping": mapping,
            "benchmark": {"market": market.upper(), "name": benchmark_name},
            "as_of": common_dates[-1],
            "aligned_points": len(common_dates),
            "primary_period": int(primary["days"]) if primary.get("available") else None,
            "primary_excess_pct": primary_excess,
            "status": status,
            "label": label,
            "trend": trend,
            "trend_label": trend_label,
            "trend_message": trend_message,
            "periods": periods,
            "strategy_effects": self._strategy_effects(float(primary_excess) if primary_excess is not None else None),
            "decision": decision,
            "message": (
                f"20거래일 기준 {benchmark_name} 업종 대비 {float(primary_excess):+.2f}%p입니다."
                if primary_excess is not None
                else "업종 대비 상대강도 데이터가 부족합니다."
            ),
            "note": "OpenDART 업종코드로 KRX 업종지수 후보를 매핑한 뒤, 종목과 해당 지수의 같은 거래일 확정 EOD만 비교합니다.",
        }
