from __future__ import annotations

import asyncio
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from app.core.stock_code import normalize_stock_code
from app.market.providers import KrxProvider, OpenDartProvider


class MarketDataService:
    def __init__(self, krx: KrxProvider, dart: OpenDartProvider) -> None:
        self.krx = krx
        self.dart = dart

    async def stock_context(
        self,
        code: str,
        market: str,
        as_of: str | None = None,
        disclosure_days: int = 60,
    ) -> dict[str, Any]:
        code = normalize_stock_code(code)
        stock_task = self.krx.latest_stock_daily(market, code, as_of)
        index_task = self.krx.latest_index_daily(market, as_of)
        corp_task = self.dart.resolve_corp_code(code)

        stock_result, index_result, corp_code = await asyncio.gather(
            stock_task,
            index_task,
            corp_task,
        )

        company_task = self.dart.company(corp_code)
        today = date.today()
        disclosure_task = self.dart.disclosures(
            corp_code,
            (today - timedelta(days=disclosure_days)).isoformat(),
            today.isoformat(),
            20,
        )
        company, disclosures = await asyncio.gather(company_task, disclosure_task)

        return {
            "code": code,
            "market": market.upper(),
            "real_trading": False,
            "data_date": stock_result["date"],
            "requested_date": stock_result.get("requested_date"),
            "fallback_used": stock_result.get("fallback_used", False),
            "stock": stock_result["rows"][0],
            "market_index": index_result.get("main_index"),
            "company": company,
            "disclosures": disclosures,
            "sources": {
                "price": "KRX",
                "index": "KRX",
                "company": "OpenDART",
                "disclosures": "OpenDART",
            },
        }

    async def market_snapshot(self, as_of: str | None = None) -> dict[str, Any]:
        kospi, kosdaq = await asyncio.gather(
            self.krx.latest_index_daily("KOSPI", as_of),
            self.krx.latest_index_daily("KOSDAQ", as_of),
        )
        return {
            "real_trading": False,
            "requested_date": kospi.get("requested_date"),
            "kospi": {
                "data_date": kospi["date"],
                "fallback_used": kospi.get("fallback_used", False),
                "index": kospi.get("main_index"),
            },
            "kosdaq": {
                "data_date": kosdaq["date"],
                "fallback_used": kosdaq.get("fallback_used", False),
                "index": kosdaq.get("main_index"),
            },
        }

    @staticmethod
    def _breadth(rows: list[dict[str, Any]]) -> dict[str, Any]:
        valid = [row for row in rows if row.get("change_rate") is not None]
        up = sum(1 for row in valid if float(row["change_rate"]) > 0)
        down = sum(1 for row in valid if float(row["change_rate"]) < 0)
        flat = len(valid) - up - down
        total = len(valid)
        up_ratio = (up / total) if total else 0.0
        avg_abs_move = (
            fmean(abs(float(row["change_rate"])) for row in valid) if valid else 0.0
        )
        return {
            "total": total,
            "up": up,
            "down": down,
            "flat": flat,
            "up_ratio": round(up_ratio, 4),
            "avg_abs_change_rate": round(avg_abs_move, 3),
        }

    @staticmethod
    def _volatility_label(avg_abs_move: float) -> str:
        if avg_abs_move >= 4.0:
            return "높음"
        if avg_abs_move >= 2.0:
            return "보통"
        return "낮음"

    @staticmethod
    def _market_regime(
        kospi_rate: float,
        kosdaq_rate: float,
        up_ratio: float,
    ) -> tuple[str, str]:
        index_rate = (kospi_rate + kosdaq_rate) / 2
        if index_rate >= 0.8 and up_ratio >= 0.60:
            return "강한 상승", "지수와 시장 폭이 함께 강한 상승 흐름입니다."
        if index_rate >= 0.2 and up_ratio >= 0.52:
            return "상승 우세", "상승 종목 비중과 주요 지수가 대체로 우호적입니다."
        if index_rate <= -0.8 and up_ratio <= 0.40:
            return "강한 하락", "지수 하락과 하락 종목 확산이 동시에 나타나고 있습니다."
        if index_rate <= -0.2 and up_ratio <= 0.48:
            return "하락 우세", "하락 종목 비중이 높아 공격적인 진입에는 주의가 필요합니다."
        return "혼조 / 중립", "지수와 시장 폭의 방향이 뚜렷하지 않아 선별 접근이 필요한 구간입니다."

    @staticmethod
    def _top_turnover(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        eligible = [
            row
            for row in rows
            if row.get("trade_value") is not None
            and row.get("close") is not None
            and row.get("code")
        ]
        eligible.sort(key=lambda row: int(row.get("trade_value") or 0), reverse=True)
        return eligible[:limit]

    @staticmethod
    def _strong_groups(index_rows: list[dict[str, Any]], main_name: str, limit: int = 4) -> list[dict[str, Any]]:
        candidates = [
            row
            for row in index_rows
            if row.get("name")
            and str(row.get("name")).upper() != main_name.upper()
            and row.get("change_rate") is not None
            and float(row.get("change_rate") or 0) > 0
        ]

        sector_like = [
            row for row in candidates
            if "업종" in str(row.get("class") or "")
            or "산업" in str(row.get("class") or "")
        ]
        pool = sector_like if sector_like else candidates
        pool.sort(key=lambda row: float(row.get("change_rate") or 0), reverse=True)
        return [
            {
                "name": row.get("name"),
                "change_rate": row.get("change_rate"),
                "class": row.get("class"),
                "kind": "업종" if sector_like else "지수",
            }
            for row in pool[:limit]
        ]

    async def market_dashboard(
        self,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        kospi_index, kosdaq_index = await asyncio.gather(
            self.krx.latest_index_daily("KOSPI", as_of),
            self.krx.latest_index_daily("KOSDAQ", as_of),
        )

        kospi_date = kospi_index["date"]
        kosdaq_date = kosdaq_index["date"]

        # 첫 화면에 필요한 최신 시장 데이터만 먼저 가져옵니다.
        # 최근 N거래일 차트는 별도 endpoint에서 지연 로딩하여
        # 히스토리 조회가 대시보드 전체 표시를 막지 않도록 합니다.
        kospi_stocks, kosdaq_stocks = await asyncio.gather(
            self.krx.stock_daily("KOSPI", kospi_date),
            self.krx.stock_daily("KOSDAQ", kosdaq_date),
        )

        kospi_main = kospi_index.get("main_index") or {}
        kosdaq_main = kosdaq_index.get("main_index") or {}
        all_stocks = kospi_stocks["rows"] + kosdaq_stocks["rows"]
        breadth = self._breadth(all_stocks)

        kospi_rate = float(kospi_main.get("change_rate") or 0)
        kosdaq_rate = float(kosdaq_main.get("change_rate") or 0)
        regime, regime_note = self._market_regime(
            kospi_rate,
            kosdaq_rate,
            float(breadth["up_ratio"]),
        )

        volatility = self._volatility_label(float(breadth["avg_abs_change_rate"]))
        strong_groups = self._strong_groups(kospi_index["rows"], "KOSPI", 3)
        strong_groups += self._strong_groups(kosdaq_index["rows"], "KOSDAQ", 2)
        strong_groups.sort(key=lambda row: float(row.get("change_rate") or 0), reverse=True)
        strong_groups = strong_groups[:4]

        top_turnover = self._top_turnover(all_stocks, 8)

        summary_parts = [regime_note]
        summary_parts.append(
            f"상승 종목은 {breadth['up']}개, 하락 종목은 {breadth['down']}개로 집계됐습니다."
        )
        if strong_groups:
            names = ", ".join(str(item["name"]) for item in strong_groups[:3])
            summary_parts.append(f"상대적으로 강한 지수/업종 그룹은 {names}입니다.")
        summary_parts.append(
            "전략 추천 점수는 아직 전략 엔진 검증 전이므로 표시하지 않습니다."
        )

        return {
            "real_trading": False,
            "data_date": min(kospi_date, kosdaq_date),
            "requested_date": kospi_index.get("requested_date"),
            "fallback_used": bool(
                kospi_index.get("fallback_used") or kosdaq_index.get("fallback_used")
            ),
            "market": {
                "regime": regime,
                "volatility_proxy": volatility,
                "volatility_note": "당일 종목 등락률 절대값 평균을 이용한 초기 프록시입니다.",
                "breadth": breadth,
            },
            "indices": {
                "kospi": kospi_main,
                "kosdaq": kosdaq_main,
            },
            "history": {
                "kospi": [],
                "kosdaq": [],
            },
            "strong_groups": strong_groups,
            "top_turnover": top_turnover,
            "summary": " ".join(summary_parts),
            "sources": {
                "indices": "KRX",
                "breadth": "KRX",
                "turnover": "KRX",
                "summary": "StockScope rule-based summary",
            },
        }
    async def market_history(
        self,
        as_of: str | None = None,
        points: int = 7,
    ) -> dict[str, Any]:
        """Load chart history separately so the main dashboard can render first."""
        kospi, kosdaq = await asyncio.gather(
            self.krx.index_history("KOSPI", as_of, points),
            self.krx.index_history("KOSDAQ", as_of, points),
        )
        return {
            "real_trading": False,
            "kospi": kospi,
            "kosdaq": kosdaq,
        }

