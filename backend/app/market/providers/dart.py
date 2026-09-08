from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

from app.market.providers.base import ProviderError, ProviderNotConfigured


class OpenDartProvider:
    BASE_URL = "https://opendart.fss.or.kr/api"
    _stock_to_corp_cache: dict[str, str] | None = None

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
            stock_code = (item.findtext("stock_code") or "").strip()
            corp_code = (item.findtext("corp_code") or "").strip()
            if len(stock_code) == 6 and len(corp_code) == 8:
                mapping[stock_code] = corp_code

        if not mapping:
            raise ProviderError("OpenDART 기업코드 목록에서 상장 종목 매핑을 찾지 못했습니다.")

        self.__class__._stock_to_corp_cache = mapping
        return mapping

    async def resolve_corp_code(self, stock_code: str) -> str:
        code = stock_code.strip()
        if len(code) != 6 or not code.isdigit():
            raise ValueError("종목코드는 6자리 숫자여야 합니다.")
        mapping = await self._load_stock_corp_map()
        corp_code = mapping.get(code)
        if not corp_code:
            raise ProviderError(f"OpenDART에서 종목코드 {code}의 corp_code를 찾지 못했습니다.")
        return corp_code

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
