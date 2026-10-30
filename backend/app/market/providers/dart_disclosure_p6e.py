"""P6-E bounded OpenDART public disclosure listing, outside pinned Scanner sources.

The existing OpenDartProvider module is a frozen scanner dependency: never
modify it for P6-E. This wrapper uses its existing authenticated transport.
No storage, EventEvidence mutation, third-party AI, or inferred publish time.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

from app.market.providers.base import ProviderError
from app.market.providers.dart import OpenDartProvider


def _parse_day(value: str) -> date:
    if not isinstance(value, str) or not (
        re.fullmatch(r"\d{8}", value) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    ):
        raise ValueError("공시 조회일은 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("OpenDART 공시 조회일이 올바르지 않습니다.") from exc


async def fetch_bounded_disclosures(
    provider: OpenDartProvider, corp_code: str,
    begin_date: str, end_date: str, *,
    page_count: int = 20, max_pages: int = 1,
) -> dict[str, Any]:
    """Bounded multi-page read-only disclosure list with source identity checks."""
    code = corp_code.strip()
    if not re.fullmatch(r"\d{8}", code):
        raise ValueError("OpenDART corp_code는 8자리 숫자여야 합니다.")
    begin_day, end_day = _parse_day(begin_date), _parse_day(end_date)
    if begin_day > end_day:
        raise ValueError("공시 시작일이 종료일 이후일 수 없습니다.")
    if type(page_count) is not int or not 1 <= page_count <= 100:
        raise ValueError("공시 page_count는 1~100이어야 합니다.")
    if type(max_pages) is not int or not 1 <= max_pages <= 5:
        raise ValueError("공시 max_pages는 1~5여야 합니다.")
    begin, end = begin_day.strftime("%Y%m%d"), end_day.strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_count: int | None = None
    total_page: int | None = None
    duplicates = 0
    pages_fetched = 0
    for page_no in range(1, max_pages + 1):
        try:
            payload = await provider._get("list.json", {
                "corp_code": code, "bgn_de": begin, "end_de": end,
                "page_no": page_no, "page_count": page_count,
            })
        except ProviderError as exc:
            # OpenDartProvider._get rejects status 013, which is an ordinary
            # no-data status for list.json. Do not swallow other status codes.
            if not str(exc).startswith("OpenDART 오류 013:"):
                raise
            if page_no == 1:
                total_count, total_page = 0, 0
            break
        pages_fetched += 1
        try:
            counted, paged = int(payload["total_count"]), int(payload["total_page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("OpenDART 페이지 정보가 없습니다.") from exc
        if counted < 0 or paged < 0 or (counted > 0 and paged == 0):
            raise ProviderError("OpenDART 공시 페이지 수가 부정확합니다.")
        if total_count is None:
            total_count, total_page = counted, paged
        elif total_count != counted or total_page != paged:
            raise ProviderError("OpenDART 조회 도중 페이지 정보가 바뀌었습니다.")
        items = payload.get("list") or []
        if not isinstance(items, list):
            raise ProviderError("OpenDART 공시 목록 형식 오류")
        for item in items:
            if not isinstance(item, dict):
                raise ProviderError("OpenDART 공시 항목 형식 오류")
            receipt = str(item.get("rcept_no") or "")
            receipt_day = str(item.get("rcept_dt") or "")
            if not re.fullmatch(r"\d{14}", receipt) or not re.fullmatch(r"\d{8}", receipt_day):
                raise ProviderError("OpenDART 접수번호/접수일 형식 오류")
            try:
                actual_day = date.fromisoformat(receipt_day)
            except ValueError as exc:
                raise ProviderError("OpenDART 접수일 값 오류") from exc
            if not begin_day <= actual_day <= end_day:
                raise ProviderError("OpenDART 접수일이 조회 범위 밖입니다.")
            source_corp = item.get("corp_code")
            if source_corp and str(source_corp) != code:
                raise ProviderError("OpenDART 공시 기업 고유번호가 다릅니다.")
            if receipt in seen:
                duplicates += 1
                continue
            seen.add(receipt)
            rows.append({
                "receipt_no": receipt,
                "corp_name": item.get("corp_name"),
                "report_name": item.get("report_nm"),
                "filer_name": item.get("flr_nm"),
                "receipt_date": receipt_day,
                "remark": item.get("rm"),
                "corp_code": code,
                "stock_code": item.get("stock_code"),
                "viewer_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                "source_time_quality": "DATE_ONLY",
                "source_published_at": None,
            })
        if paged == 0 or page_no >= paged:
            break
    return {
        "provider": "OpenDART", "corp_code": code,
        "begin_date": begin, "end_date": end,
        "count": len(rows), "rows": rows,
        "total_count": total_count if total_count is not None else 0,
        "total_page": total_page if total_page is not None else 0,
        "pages_fetched": pages_fetched,
        "truncated": bool(total_page and pages_fetched < total_page),
        "duplicate_receipt_count": duplicates,
        "persisted": False, "model_calls": 0,
    }
