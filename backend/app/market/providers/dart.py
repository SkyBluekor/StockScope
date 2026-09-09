from __future__ import annotations

from io import BytesIO
import html
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

from app.core.stock_code import normalize_stock_code
from app.market.providers.base import ProviderError, ProviderNotConfigured


class OpenDartProvider:
    BASE_URL = "https://opendart.fss.or.kr/api"
    _stock_to_corp_cache: dict[str, str] | None = None
    _document_text_cache: dict[str, str] = {}
    _annual_revenue_cache: dict[str, dict[str, Any] | None] = {}
    _annual_statement_cache: dict[tuple[str, int, str], dict[str, Any]] = {}
    _financial_statement_cache: dict[tuple[str, int, str, str], dict[str, Any]] = {}

    def __init__(self, api_key: str | None) -> None:
        self.api_key = (api_key or "").strip()

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderNotConfigured("DART_API_KEY가 설정되지 않았습니다.")

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self._require_key()
        query = {"crtfc_key": self.api_key, **params}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{self.BASE_URL}/{path}", params=query)
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenDART 연결 실패: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(f"OpenDART 요청 실패 ({response.status_code})")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("OpenDART가 JSON이 아닌 응답을 반환했습니다.") from exc

        status = payload.get("status")
        if status not in (None, "000"):
            message = payload.get("message") or "알 수 없는 OpenDART 오류"
            raise ProviderError(f"OpenDART 오류 {status}: {message}")
        return payload

    async def _load_stock_corp_map(self) -> dict[str, str]:
        if self.__class__._stock_to_corp_cache is not None:
            return self.__class__._stock_to_corp_cache

        self._require_key()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/corpCode.xml",
                    params={"crtfc_key": self.api_key},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenDART 기업코드 목록 연결 실패: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(f"OpenDART 기업코드 목록 요청 실패 ({response.status_code})")

        try:
            with ZipFile(BytesIO(response.content)) as archive:
                xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
                if xml_name is None:
                    raise ProviderError("OpenDART 기업코드 ZIP에 XML 파일이 없습니다.")
                root = ElementTree.fromstring(archive.read(xml_name))
        except (BadZipFile, ElementTree.ParseError) as exc:
            raise ProviderError("OpenDART 기업코드 목록을 해석하지 못했습니다.") from exc

        mapping: dict[str, str] = {}
        for item in root.findall("list"):
            stock_code = (item.findtext("stock_code") or "").strip().upper()
            corp_code = (item.findtext("corp_code") or "").strip()
            if len(stock_code) == 6 and stock_code.isalnum() and len(corp_code) == 8:
                mapping[stock_code] = corp_code

        if not mapping:
            raise ProviderError("OpenDART 기업코드 목록에서 상장 종목 매핑을 찾지 못했습니다.")

        self.__class__._stock_to_corp_cache = mapping
        return mapping

    async def resolve_corp_code(self, stock_code: str) -> str:
        code = normalize_stock_code(stock_code)
        mapping = await self._load_stock_corp_map()
        corp_code = mapping.get(code)
        if not corp_code:
            raise ProviderError(f"OpenDART에서 종목코드 {code}의 corp_code를 찾지 못했습니다.")
        return corp_code


    async def major_event(
        self,
        path: str,
        corp_code: str,
        begin_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Call one of OpenDART's structured major-event endpoints.

        `path` is intentionally supplied only by internal allowlisted code.
        """
        allowed = {
            "piicDecsn.json",
            "cvbdIsDecsn.json",
            "bdwtIsDecsn.json",
            "cmpMgDecsn.json",
        }
        if path not in allowed:
            raise ValueError("허용되지 않은 OpenDART 주요사항 endpoint입니다.")

        code = corp_code.strip()
        begin = begin_date.replace("-", "")
        end = end_date.replace("-", "")
        payload = await self._get(
            path,
            {
                "corp_code": code,
                "bgn_de": begin,
                "end_de": end,
            },
        )
        rows = payload.get("list") or []
        return {
            "provider": "OpenDART",
            "endpoint": path,
            "corp_code": code,
            "begin_date": begin,
            "end_date": end,
            "count": len(rows),
            "rows": rows,
        }

    async def document_text(self, receipt_no: str, max_chars: int = 30000) -> str:
        """Download DART original disclosure ZIP and return normalized plain text."""
        receipt = receipt_no.strip()
        if len(receipt) != 14 or not receipt.isdigit():
            raise ValueError("OpenDART 접수번호는 14자리 숫자여야 합니다.")

        cached = self.__class__._document_text_cache.get(receipt)
        if cached is not None:
            return cached

        self._require_key()
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/document.xml",
                    params={"crtfc_key": self.api_key, "rcept_no": receipt},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenDART 공시원문 연결 실패: {exc}") from exc

        if response.status_code != 200:
            raise ProviderError(f"OpenDART 공시원문 요청 실패 ({response.status_code})")

        try:
            with ZipFile(BytesIO(response.content)) as archive:
                names = [
                    name for name in archive.namelist()
                    if name.lower().endswith((".xml", ".html", ".htm"))
                ]
                if not names:
                    raise ProviderError("OpenDART 원문 ZIP에 해석 가능한 문서가 없습니다.")

                pieces: list[str] = []
                for name in names[:8]:
                    raw = archive.read(name)
                    decoded = None
                    for encoding in ("utf-8", "cp949", "euc-kr"):
                        try:
                            decoded = raw.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    if decoded is None:
                        decoded = raw.decode("utf-8", errors="ignore")

                    decoded = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", decoded)
                    decoded = re.sub(r"(?i)</?(?:p|br|tr|div|li|h[1-6])[^>]*>", "\n", decoded)
                    decoded = re.sub(r"(?s)<[^>]+>", " ", decoded)
                    decoded = html.unescape(decoded)
                    decoded = re.sub(r"[ \t\r\f\v]+", " ", decoded)
                    decoded = re.sub(r"\n\s*\n+", "\n", decoded)
                    pieces.append(decoded.strip())

                text = "\n".join(piece for piece in pieces if piece)
        except BadZipFile as exc:
            raise ProviderError("OpenDART 공시원문 ZIP을 해석하지 못했습니다.") from exc

        text = text[: max(1000, min(max_chars, 100000))]
        self.__class__._document_text_cache[receipt] = text
        return text

    async def financial_statement(
        self,
        corp_code: str,
        business_year: int,
        report_code: str,
        *,
        fs_div: str = "CFS",
    ) -> dict[str, Any]:
        """Return one official periodic financial statement from OpenDART.

        `report_code` follows OpenDART periodic report codes:
        11013=1분기, 11012=반기, 11014=3분기, 11011=사업보고서.
        Raw rows are returned so the fundamental layer can compare the same
        period year-over-year instead of mixing annual and interim figures.
        """
        code = corp_code.strip()
        if len(code) != 8 or not code.isdigit():
            raise ValueError("OpenDART corp_code는 8자리 숫자여야 합니다.")
        year = int(business_year)
        if year < 1990 or year > 2100:
            raise ValueError("business_year가 올바르지 않습니다.")
        report_key = str(report_code).strip()
        if report_key not in {"11013", "11012", "11014", "11011"}:
            raise ValueError("지원하지 않는 OpenDART 정기보고서 코드입니다.")
        fs_key = fs_div.upper().strip()
        if fs_key not in {"CFS", "OFS"}:
            raise ValueError("fs_div는 CFS 또는 OFS여야 합니다.")

        cache_key = (code, year, report_key, fs_key)
        cached = self.__class__._financial_statement_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._get(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": code,
                "bsns_year": str(year),
                "reprt_code": report_key,
                "fs_div": fs_key,
            },
        )
        rows = payload.get("list") or []
        result = {
            "provider": "OpenDART",
            "endpoint": "fnlttSinglAcntAll.json",
            "corp_code": code,
            "business_year": year,
            "report_code": report_key,
            "fs_div": fs_key,
            "count": len(rows),
            "rows": rows,
        }
        self.__class__._financial_statement_cache[cache_key] = result
        return result

    async def annual_statement(
        self,
        corp_code: str,
        business_year: int,
        *,
        fs_div: str = "CFS",
    ) -> dict[str, Any]:
        """Backward-compatible annual statement wrapper."""
        code = corp_code.strip()
        year = int(business_year)
        fs_key = fs_div.upper().strip()
        cache_key = (code, year, fs_key)
        cached = self.__class__._annual_statement_cache.get(cache_key)
        if cached is not None:
            return cached
        result = await self.financial_statement(code, year, "11011", fs_div=fs_key)
        self.__class__._annual_statement_cache[cache_key] = result
        return result

    async def latest_annual_revenue(self, corp_code: str) -> dict[str, Any] | None:
        """Return latest available annual revenue from official OpenDART statements.

        CFS is preferred, OFS is fallback. This comparison is best-effort and never
        blocks the rest of the disclosure analysis if revenue cannot be resolved.
        """
        code = corp_code.strip()
        if len(code) != 8 or not code.isdigit():
            raise ValueError("OpenDART corp_code는 8자리 숫자여야 합니다.")

        if code in self.__class__._annual_revenue_cache:
            return self.__class__._annual_revenue_cache[code]

        revenue_names = ("매출액", "수익(매출액)", "영업수익", "매출")
        today_year = __import__("datetime").date.today().year

        for year in range(today_year - 1, today_year - 4, -1):
            for fs_div in ("CFS", "OFS"):
                try:
                    payload = await self._get(
                        "fnlttSinglAcntAll.json",
                        {
                            "corp_code": code,
                            "bsns_year": str(year),
                            "reprt_code": "11011",
                            "fs_div": fs_div,
                        },
                    )
                except ProviderError:
                    continue

                rows = payload.get("list") or []
                if not rows:
                    continue

                candidates = [
                    row
                    for row in rows
                    if str(row.get("sj_div") or "").upper() in {"IS", "CIS"}
                ] or rows

                selected = None
                for name in revenue_names:
                    selected = next(
                        (
                            row
                            for row in candidates
                            if str(row.get("account_nm") or "").strip() == name
                        ),
                        None,
                    )
                    if selected is not None:
                        break

                if selected is None:
                    selected = next(
                        (
                            row
                            for row in candidates
                            if "매출" in str(row.get("account_nm") or "")
                            or "영업수익" in str(row.get("account_nm") or "")
                        ),
                        None,
                    )

                if selected is None:
                    continue

                raw = selected.get("thstrm_amount") or selected.get("thstrm_add_amount")
                if raw in (None, "", "-"):
                    continue
                try:
                    revenue = float(str(raw).replace(",", ""))
                except ValueError:
                    continue
                if revenue <= 0:
                    continue

                result = {
                    "provider": "OpenDART",
                    "endpoint": "fnlttSinglAcntAll.json",
                    "corp_code": code,
                    "business_year": year,
                    "report_code": "11011",
                    "fs_div": fs_div,
                    "account_name": selected.get("account_nm"),
                    "revenue": revenue,
                    "currency": selected.get("currency") or "KRW",
                }
                self.__class__._annual_revenue_cache[code] = result
                return result

        self.__class__._annual_revenue_cache[code] = None
        return None

    async def company(self, corp_code: str) -> dict[str, Any]:
        code = corp_code.strip()
        if len(code) != 8 or not code.isdigit():
            raise ValueError("OpenDART corp_code는 8자리 숫자여야 합니다.")
        payload = await self._get("company.json", {"corp_code": code})
        return {
            "provider": "OpenDART",
            "corp_code": payload.get("corp_code"),
            "corp_name": payload.get("corp_name"),
            "corp_name_eng": payload.get("corp_name_eng"),
            "stock_name": payload.get("stock_name"),
            "stock_code": payload.get("stock_code"),
            "ceo": payload.get("ceo_nm"),
            "corp_class": payload.get("corp_cls"),
            "business_number": payload.get("jurir_no"),
            "established_date": payload.get("est_dt"),
            "address": payload.get("adres"),
            "homepage": payload.get("hm_url"),
            "ir_url": payload.get("ir_url"),
            "phone": payload.get("phn_no"),
            "industry_code": payload.get("induty_code"),
            "fiscal_month": payload.get("acc_mt"),
        }

    async def company_by_stock_code(self, stock_code: str) -> dict[str, Any]:
        corp_code = await self.resolve_corp_code(stock_code)
        return await self.company(corp_code)

    async def disclosures(
        self,
        corp_code: str,
        begin_date: str,
        end_date: str,
        page_count: int = 20,
    ) -> dict[str, Any]:
        code = corp_code.strip()
        if len(code) != 8 or not code.isdigit():
            raise ValueError("OpenDART corp_code는 8자리 숫자여야 합니다.")
        begin = begin_date.replace("-", "")
        end = end_date.replace("-", "")
        if not (len(begin) == 8 and begin.isdigit() and len(end) == 8 and end.isdigit()):
            raise ValueError("공시 조회일은 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.")

        payload = await self._get(
            "list.json",
            {
                "corp_code": code,
                "bgn_de": begin,
                "end_de": end,
                "page_no": 1,
                "page_count": min(max(page_count, 1), 100),
            },
        )
        rows = payload.get("list") or []
        return {
            "provider": "OpenDART",
            "corp_code": code,
            "begin_date": begin,
            "end_date": end,
            "count": len(rows),
            "rows": [
                {
                    "receipt_no": row.get("rcept_no"),
                    "corp_name": row.get("corp_name"),
                    "report_name": row.get("report_nm"),
                    "filer_name": row.get("flr_nm"),
                    "receipt_date": row.get("rcept_dt"),
                    "remark": row.get("rm"),
                }
                for row in rows
            ],
        }
