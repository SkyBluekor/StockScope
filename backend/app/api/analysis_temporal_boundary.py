from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.market.event_risk import EventRiskAnalyzer
from app.market.providers.base import ProviderError


def _parse_as_of(value: str) -> date:
    raw = str(value or "").strip()
    if len(raw) == 8 and raw.isdigit():
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    try:
        return min(date.fromisoformat(raw), date.today())
    except ValueError as exc:
        raise ValueError("as_of는 YYYY-MM-DD 형식이어야 합니다.") from exc


class _PointInTimeOpenDartProxy:
    """Expose only OpenDART facts whose receipt date can be bounded by as_of.

    Current structured-detail/document/revenue helpers do not carry a proven
    point-in-time availability contract, so historical analysis fails closed on
    those enrichments instead of mixing current facts into a past decision.
    """

    def __init__(self, dart: Any, as_of: date) -> None:
        self._dart = dart
        self.as_of = as_of
        self.last_begin: str | None = None
        self.last_end: str | None = None

    async def resolve_corp_code(self, stock_code: str):
        return await self._dart.resolve_corp_code(stock_code)

    async def disclosures(
        self,
        corp_code: str,
        begin_date: str,
        end_date: str,
        page_count: int = 20,
    ):
        try:
            original_begin = date(
                int(begin_date[:4]), int(begin_date[4:6]), int(begin_date[6:8])
            )
            original_end = date(
                int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8])
            )
            span_days = max(7, (original_end - original_begin).days)
        except (TypeError, ValueError):
            span_days = 60

        bounded_end = self.as_of
        bounded_begin = bounded_end - timedelta(days=span_days)
        self.last_begin = bounded_begin.strftime("%Y%m%d")
        self.last_end = bounded_end.strftime("%Y%m%d")
        return await self._dart.disclosures(
            corp_code,
            self.last_begin,
            self.last_end,
            page_count,
        )

    async def major_event(self, *args: Any, **kwargs: Any):
        raise ProviderError(
            "Historical OpenDART structured detail is not point-in-time verified."
        )

    async def document_text(self, *args: Any, **kwargs: Any):
        raise ProviderError(
            "Historical OpenDART document enrichment is not point-in-time verified."
        )

    async def latest_annual_revenue(self, *args: Any, **kwargs: Any):
        raise ProviderError(
            "Historical OpenDART revenue enrichment is not point-in-time verified."
        )


class PointInTimeEventRiskAnalyzer:
    def __init__(self, dart: Any, as_of: str) -> None:
        self.as_of = _parse_as_of(as_of)
        self.proxy = _PointInTimeOpenDartProxy(dart, self.as_of)
        self.delegate = EventRiskAnalyzer(self.proxy)

    async def analyze(self, stock_code: str, **kwargs: Any) -> dict[str, Any]:
        days = int(kwargs.get("days") or 60)
        result = await self.delegate.analyze(stock_code, **kwargs)
        end = self.as_of.strftime("%Y%m%d")
        begin = (
            self.as_of - timedelta(days=max(7, days))
        ).strftime("%Y%m%d")
        result["period"] = {
            "begin": self.proxy.last_begin or begin,
            "end": self.proxy.last_end or end,
            "days": days,
        }
        result["temporal_mode"] = "POINT_IN_TIME_LIST_ONLY"
        return result
