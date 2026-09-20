from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.market.sector_relative_strength import SectorRelativeStrengthAnalyzer

TEMPORAL_POINT_IN_TIME = "POINT_IN_TIME"
TEMPORAL_STATIC_CURRENT = "STATIC_CURRENT"
TEMPORAL_UNKNOWN = "UNKNOWN"

_ALLOWED_TEMPORAL = {
    TEMPORAL_POINT_IN_TIME,
    TEMPORAL_STATIC_CURRENT,
    TEMPORAL_UNKNOWN,
}


def _compact_date(value: Any) -> str:
    return str(value or "").replace("-", "").strip()


@dataclass(frozen=True)
class HistoricalSectorInput:
    """Prepared sector benchmark input for deterministic historical evaluation.

    This object contains only already-fetched data.  BacktestEngine must never perform
    network I/O while producing a signal snapshot.

    temporal_status controls whether the sector value may affect Production strategy
    input.  Current OpenDART company metadata is not proven point-in-time historical
    metadata, so it must be marked STATIC_CURRENT and remains audit-only.
    """

    industry_code: str | None
    sector_group: str | None
    benchmark_name: str | None
    sector_rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    mapping: dict[str, Any] = field(default_factory=dict)
    mapping_method: str | None = None
    temporal_status: str = TEMPORAL_UNKNOWN
    source: str = "OpenDART+KRX_EOD"

    def __post_init__(self) -> None:
        if self.temporal_status not in _ALLOWED_TEMPORAL:
            raise ValueError(f"Unsupported sector temporal_status: {self.temporal_status}")

    @property
    def production_safe(self) -> bool:
        return self.temporal_status == TEMPORAL_POINT_IN_TIME

    def rows_asof(self, signal_date: str) -> list[dict[str, Any]]:
        cutoff = _compact_date(signal_date)
        rows = [
            dict(row)
            for row in self.sector_rows
            if _compact_date(row.get("date")) and _compact_date(row.get("date")) <= cutoff
        ]
        rows.sort(key=lambda row: _compact_date(row.get("date")))
        return rows


@dataclass(frozen=True)
class SectorInputEvaluation:
    production_relative_strength_pct: float | None
    production_context: dict[str, Any] | None
    audit_relative_strength_pct: float | None
    audit_context: dict[str, Any] | None
    audit: dict[str, Any]


def evaluate_historical_sector_input(
    *,
    analyzer: SectorRelativeStrengthAnalyzer,
    prepared: HistoricalSectorInput | None,
    stock_rows_asof: list[dict[str, Any]],
    signal_date: str,
    market: str,
    market_relative: dict[str, Any],
    position_mode: str = "NOT_HELD",
) -> SectorInputEvaluation:
    """Evaluate a pre-fetched sector series without lookahead.

    The function always slices sector rows at signal_date again, even when the caller
    already did so.  This is the temporal-integrity boundary for Backtest/Scanner.
    STATIC_CURRENT and UNKNOWN mappings may be inspected in audit output, but they are
    never allowed to alter Production strategy input.
    """

    if prepared is None:
        return SectorInputEvaluation(
            production_relative_strength_pct=None,
            production_context=None,
            audit_relative_strength_pct=None,
            audit_context=None,
            audit={
                "input_status": "NO_SECTOR_INPUT",
                "temporal_status": None,
                "production_safe": False,
                "sector_history_end_date": None,
                "future_rows_ignored": 0,
                "primary_period": None,
                "unavailable_reason": "SECTOR_INPUT_NOT_PREPARED",
            },
        )

    cutoff = _compact_date(signal_date)
    all_rows = [dict(row) for row in prepared.sector_rows]
    sector_rows = prepared.rows_asof(signal_date)
    future_rows_ignored = sum(
        1
        for row in all_rows
        if _compact_date(row.get("date")) and _compact_date(row.get("date")) > cutoff
    )
    sector_history_end = _compact_date(sector_rows[-1].get("date")) if sector_rows else None

    if not prepared.industry_code:
        context = analyzer.unavailable(
            market=market,
            industry_code=None,
            reason="Historical Sector RS input has no industry code.",
            market_relative=market_relative,
            position_mode=position_mode,
            mapping=prepared.mapping,
        )
        unavailable_reason = "NO_INDUSTRY_CODE"
    elif not prepared.benchmark_name:
        context = analyzer.unavailable(
            market=market,
            industry_code=prepared.industry_code,
            reason="Historical Sector RS input has no resolved benchmark.",
            market_relative=market_relative,
            position_mode=position_mode,
            mapping=prepared.mapping,
        )
        unavailable_reason = "BENCHMARK_NOT_FOUND"
    elif not sector_rows:
        context = analyzer.unavailable(
            market=market,
            industry_code=prepared.industry_code,
            reason="Historical sector benchmark rows are missing as of the signal date.",
            market_relative=market_relative,
            position_mode=position_mode,
            mapping=prepared.mapping,
        )
        unavailable_reason = "SECTOR_HISTORY_MISSING"
    else:
        context = analyzer.analyze(
            stock_rows_asof,
            sector_rows,
            market=market,
            industry_code=prepared.industry_code,
            mapping=prepared.mapping,
            benchmark_name=prepared.benchmark_name,
            market_relative=market_relative,
            position_mode=position_mode,
        )
        unavailable_reason = (
            None
            if context.get("available") and context.get("primary_period") == 20
            else "INSUFFICIENT_COMMON_DATES"
        )

    audit_value = (
        context.get("primary_excess_pct")
        if context.get("primary_period") == 20
        else None
    )
    production_value = float(audit_value) if prepared.production_safe and audit_value is not None else None
    production_context = context if prepared.production_safe else None

    return SectorInputEvaluation(
        production_relative_strength_pct=production_value,
        production_context=production_context,
        audit_relative_strength_pct=(float(audit_value) if audit_value is not None else None),
        audit_context=context,
        audit={
            "input_status": "AVAILABLE" if audit_value is not None else "UNAVAILABLE",
            "temporal_status": prepared.temporal_status,
            "production_safe": prepared.production_safe,
            "sector_group": prepared.sector_group,
            "benchmark_name": prepared.benchmark_name,
            "mapping_method": prepared.mapping_method,
            "sector_history_end_date": sector_history_end,
            "future_rows_ignored": future_rows_ignored,
            "primary_period": context.get("primary_period"),
            "audit_relative_strength_pct": (float(audit_value) if audit_value is not None else None),
            "unavailable_reason": (
                "TEMPORAL_MAPPING_UNSAFE"
                if audit_value is not None and not prepared.production_safe
                else unavailable_reason
            ),
        },
    )
