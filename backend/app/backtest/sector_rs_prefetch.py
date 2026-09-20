from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.backtest.sector_rs_input import HistoricalSectorInput, TEMPORAL_STATIC_CURRENT
from app.market.sector_relative_strength import SectorRelativeStrengthAnalyzer


def _as_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    return date.fromisoformat(raw)


def _candidate_dates(as_of: str | date, lookback_days: int) -> list[date]:
    """Return weekdays from as_of backwards; never create a future date."""
    current = _as_date(as_of)
    result: list[date] = []
    for offset in range(max(1, int(lookback_days))):
        candidate = current - timedelta(days=offset)
        if candidate.weekday() < 5:
            result.append(candidate)
    return result


@dataclass
class SectorPrefetchStats:
    enabled: bool = True
    temporal_status: str = TEMPORAL_STATIC_CURRENT
    unique_codes: int = 0
    company_requests: int = 0
    company_cache_hits: int = 0
    industry_code_available: int = 0
    industry_mapped: int = 0
    industry_unmapped: int = 0
    unique_sector_alias_sets: int = 0
    index_daily_calls: int = 0
    index_cache_hits: int = 0
    index_days_with_data: int = 0
    benchmark_resolved: int = 0
    sector_history_available: int = 0
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "temporal_status": self.temporal_status,
            "unique_codes": self.unique_codes,
            "company_requests": self.company_requests,
            "company_cache_hits": self.company_cache_hits,
            "industry_code_available": self.industry_code_available,
            "industry_mapped": self.industry_mapped,
            "industry_unmapped": self.industry_unmapped,
            "unique_sector_alias_sets": self.unique_sector_alias_sets,
            "index_daily_calls": self.index_daily_calls,
            "index_cache_hits": self.index_cache_hits,
            "index_days_with_data": self.index_days_with_data,
            "benchmark_resolved": self.benchmark_resolved,
            "sector_history_available": self.sector_history_available,
            "errors": self.errors,
            "error_samples": list(self.error_samples),
        }


class HistoricalSectorInputPrefetcher:
    """Prepare audit-only historical Sector RS inputs outside BacktestEngine.

    The company provider is intentionally injected structurally instead of imported.
    It only needs an async ``company_by_stock_code(code)`` method.  This keeps Scanner
    independent from OpenDART implementation details and, more importantly, keeps all
    network I/O outside the deterministic BacktestEngine boundary.

    Current OpenDART company metadata is classified STATIC_CURRENT.  The resulting
    input can be evaluated for audit coverage, but c.4f's temporal gate prevents it
    from changing Production StrategyInput until a point-in-time mapping source exists.
    """

    def __init__(
        self,
        krx: Any,
        company_provider: Any,
        *,
        analyzer: SectorRelativeStrengthAnalyzer | None = None,
        concurrency: int = 5,
    ) -> None:
        self.krx = krx
        self.company_provider = company_provider
        self.analyzer = analyzer or SectorRelativeStrengthAnalyzer()
        self.concurrency = max(1, int(concurrency))
        self._industry_cache: dict[str, str | None] = {}
        # c.4f.3: reuse KRX index-day responses across multiple audit dates.
        # Keyed by (market, YYYYMMDD); the provider may also cache, but keeping an
        # in-process cache avoids repeated provider calls during fixed 10D/80D audits.
        self._index_day_cache: dict[tuple[str, str], dict[str, Any] | Exception] = {}

    async def _industry_code(self, code: str, stats: SectorPrefetchStats) -> str | None:
        if code in self._industry_cache:
            stats.company_cache_hits += 1
            return self._industry_cache[code]
        stats.company_requests += 1
        try:
            company = await self.company_provider.company_by_stock_code(code)
            industry_code = str((company or {}).get("industry_code") or "").strip() or None
        except Exception as exc:  # provider failure is an audit-coverage outcome, not a Scanner crash
            stats.errors += 1
            if len(stats.error_samples) < 5:
                stats.error_samples.append(f"company:{code}:{exc}")
            industry_code = None
        self._industry_cache[code] = industry_code
        return industry_code

    async def _index_daily_cached(
        self,
        market: str,
        candidate: date,
        stats: SectorPrefetchStats,
    ) -> dict[str, Any] | Exception:
        key = (str(market).upper().strip(), candidate.strftime("%Y%m%d"))
        if key in self._index_day_cache:
            setattr(stats, "index_cache_hits", getattr(stats, "index_cache_hits", 0) + 1)
            return self._index_day_cache[key]
        stats.index_daily_calls += 1
        try:
            result = await self.krx.index_daily(key[0], candidate)
        except Exception as exc:  # noqa: BLE001 - provider errors are coverage outcomes
            result = exc
        self._index_day_cache[key] = result
        return result

    async def prepare(
        self,
        *,
        market: str,
        codes: list[str],
        as_of: str | date,
        points: int = 61,
        lookback_days: int = 140,
    ) -> tuple[dict[str, HistoricalSectorInput], dict[str, Any]]:
        unique_codes = list(dict.fromkeys(str(code or "").strip() for code in codes if str(code or "").strip()))
        stats = SectorPrefetchStats(unique_codes=len(unique_codes))
        if not unique_codes:
            return {}, stats.to_dict()

        industry_by_code: dict[str, str | None] = {}
        mapping_by_code: dict[str, dict[str, Any]] = {}
        semaphore = asyncio.Semaphore(self.concurrency)

        async def _fetch_industry(code: str) -> tuple[str, str | None]:
            async with semaphore:
                return code, await self._industry_code(code, stats)

        industry_pairs = await asyncio.gather(*(_fetch_industry(code) for code in unique_codes))
        for code, industry_code in industry_pairs:
            industry_by_code[code] = industry_code
            if industry_code:
                stats.industry_code_available += 1
            mapping = self.analyzer.map_industry_code(industry_code)
            mapping_by_code[code] = mapping
            if mapping.get("available"):
                stats.industry_mapped += 1
            else:
                stats.industry_unmapped += 1

        alias_sets: dict[tuple[str, ...], list[str]] = {}
        for code, mapping in mapping_by_code.items():
            if not mapping.get("available"):
                continue
            aliases = tuple(str(item) for item in (mapping.get("aliases") or []) if str(item))
            if aliases:
                alias_sets.setdefault(aliases, []).append(code)
        stats.unique_sector_alias_sets = len(alias_sets)

        wanted = min(max(int(points), 2), 120)
        series_by_aliases: dict[tuple[str, ...], list[dict[str, Any]]] = {key: [] for key in alias_sets}
        matched_meta: dict[tuple[str, ...], dict[str, Any]] = {}
        seen_dates_by_aliases: dict[tuple[str, ...], set[str]] = {key: set() for key in alias_sets}

        dates = _candidate_dates(as_of, lookback_days)
        for start in range(0, len(dates), self.concurrency):
            if alias_sets and all(len(series_by_aliases[key]) >= wanted for key in alias_sets):
                break
            batch = dates[start : start + self.concurrency]
            results = await asyncio.gather(
                *(self._index_daily_cached(str(market).upper().strip(), candidate, stats) for candidate in batch),
            )
            for result in results:
                if isinstance(result, Exception):
                    stats.errors += 1
                    if len(stats.error_samples) < 5:
                        stats.error_samples.append(f"index:{result}")
                    continue
                if not isinstance(result, dict) or int(result.get("count") or 0) <= 0:
                    continue
                rows = list(result.get("rows") or [])
                if not rows:
                    continue
                stats.index_days_with_data += 1
                for aliases in alias_sets:
                    if len(series_by_aliases[aliases]) >= wanted:
                        continue
                    selected = self.analyzer.match_index_row(rows, list(aliases))
                    if selected is None:
                        continue
                    row_date = str(selected.get("date") or result.get("date") or "").replace("-", "")
                    if not row_date or row_date in seen_dates_by_aliases[aliases]:
                        continue
                    seen_dates_by_aliases[aliases].add(row_date)
                    selected = dict(selected)
                    selected["date"] = row_date
                    series_by_aliases[aliases].append(selected)
                    matched_meta.setdefault(aliases, selected)

        prepared: dict[str, HistoricalSectorInput] = {}
        for code in unique_codes:
            mapping = mapping_by_code[code]
            aliases = tuple(str(item) for item in (mapping.get("aliases") or []) if str(item))
            rows = list(series_by_aliases.get(aliases, []))
            rows.sort(key=lambda row: str(row.get("date") or "").replace("-", ""))
            rows = rows[-wanted:]
            matched = matched_meta.get(aliases) or {}
            benchmark_name = str(matched.get("name") or "").strip() or None
            resolved_mapping = dict(mapping)
            if benchmark_name:
                resolved_mapping.update(
                    {
                        "benchmark_name": benchmark_name,
                        "benchmark_class": matched.get("class"),
                        "matched_alias": matched.get("matched_alias"),
                        "index_match_confidence": matched.get("match_confidence"),
                        "index_match_confidence_label": matched.get("match_confidence_label"),
                    }
                )
                stats.benchmark_resolved += 1
            if rows:
                stats.sector_history_available += 1
            prepared[code] = HistoricalSectorInput(
                industry_code=industry_by_code[code],
                sector_group=mapping.get("sector_group"),
                benchmark_name=benchmark_name,
                sector_rows=tuple(rows),
                mapping=resolved_mapping,
                mapping_method=mapping.get("mapping_method"),
                temporal_status=TEMPORAL_STATIC_CURRENT,
            )

        return prepared, stats.to_dict()
