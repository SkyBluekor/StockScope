from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

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
        # 핵심 데이터는 종목 시세와 DART 매핑입니다.
        # 시장 지수는 보조 데이터이므로 실패해도 전체 조회를 막지 않습니다.
        stock_task = self.krx.latest_stock_daily(market, code, as_of)
        index_task = self.krx.latest_index_daily(market, as_of)
        corp_task = self.dart.resolve_corp_code(code)

        stock_result, index_result, corp_code = await asyncio.gather(
            stock_task,
            index_task,
            corp_task,
            return_exceptions=True,
        )

        # 종목 시세는 필수
        if isinstance(stock_result, Exception):
            raise stock_result

        # DART 종목코드 매핑도 필수
        if isinstance(corp_code, Exception):
            raise corp_code

        warnings: list[str] = []

        # 지수는 선택 데이터
        if isinstance(index_result, Exception):
            warnings.append(
                f"시장 지수 조회 실패: {index_result}"
            )
            market_index = None
            index_source = "KRX unavailable"
        else:
            market_index = index_result.get("main_index")
            index_source = "KRX"

        today = date.today()

        company_task = self.dart.company(corp_code)
        disclosure_task = self.dart.disclosures(
            corp_code,
            (today - timedelta(days=disclosure_days)).isoformat(),
            today.isoformat(),
            20,
        )

        company, disclosures = await asyncio.gather(
            company_task,
            disclosure_task,
        )

        return {
            "code": code,
            "market": market.upper(),
            "real_trading": False,
            "data_date": stock_result["date"],
            "requested_date": stock_result.get("requested_date"),
            "fallback_used": stock_result.get("fallback_used", False),
            "stock": stock_result["rows"][0],
            "market_index": market_index,
            "company": company,
            "disclosures": disclosures,
            "warnings": warnings,
            "sources": {
                "price": "KRX",
                "index": index_source,
                "company": "OpenDART",
                "disclosures": "OpenDART",
            },
        }

    async def market_snapshot(
        self,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        kospi, kosdaq = await asyncio.gather(
            self.krx.latest_index_daily("KOSPI", as_of),
            self.krx.latest_index_daily("KOSDAQ", as_of),
            return_exceptions=True,
        )

        warnings: list[str] = []

        def normalize_market(
            name: str,
            result: Any,
        ) -> dict[str, Any] | None:
            if isinstance(result, Exception):
                warnings.append(
                    f"{name} 지수 조회 실패: {result}"
                )
                return None

            return {
                "data_date": result["date"],
                "fallback_used": result.get(
                    "fallback_used",
                    False,
                ),
                "index": result.get("main_index"),
            }

        return {
            "real_trading": False,
            "kospi": normalize_market("KOSPI", kospi),
            "kosdaq": normalize_market("KOSDAQ", kosdaq),
            "warnings": warnings,
        }