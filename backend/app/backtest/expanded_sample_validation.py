from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from time import monotonic
from typing import Any, Callable

from app.backtest.exit_policy_validation_runner import ExitPolicyValidationRunnerConfig
from app.backtest.market_store import HistoricalMarketStore
from app.market.kst import today_kst
from app.market.providers import KrxProvider

ProgressCallback = Callable[[dict[str, Any]], None]

EXPANDED_SAMPLE_VERSION = "0.21.4-B.2.1.10"
ALLOWED_EXPANDED_TARGETS = (20, 40, 60)
DEFAULT_WARMUP_CALENDAR_DAYS = 730


def _stock_key(row: dict[str, Any]) -> str:
    return f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').strip().upper()}"


def _market_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("market") or "").upper() for row in rows)
    return {market: int(count) for market, count in sorted(counts.items()) if market}


def validation_config_from_report(report: dict[str, Any], target_stocks: int) -> ExitPolicyValidationRunnerConfig:
    if target_stocks not in ALLOWED_EXPANDED_TARGETS:
        raise ValueError("확대 검증 종목 수는 20, 40, 60 중 하나여야 합니다.")
    raw = report.get("validation_config") or {}
    period = report.get("period") or {}
    markets_raw = raw.get("markets") or list((report.get("market_availability") or {}).keys()) or ["KOSPI", "KOSDAQ"]
    markets = tuple(str(market).upper() for market in markets_raw if str(market).upper() in {"KOSPI", "KOSDAQ"})
    if not markets:
        markets = ("KOSPI", "KOSDAQ")
    return ExitPolicyValidationRunnerConfig(
        start_date=str(period.get("start") or raw.get("start_date") or ""),
        end_date=str(period.get("end") or raw.get("end_date") or ""),
        markets=markets,
        max_stocks=target_stocks,
        minimum_coverage_pct=float(raw.get("minimum_coverage_pct") or 90.0),
        initial_capital=float(raw.get("initial_capital") or 10_000_000),
        max_holding_days=int(raw.get("max_holding_days") or 20),
        round_trip_cost_pct=float(raw.get("round_trip_cost_pct") or 0.0),
        minimum_stock_count=int(raw.get("minimum_stock_count") or 3),
        minimum_total_trades=int(raw.get("minimum_total_trades") or 30),
        post_target2_research_days=int(raw.get("post_target2_research_days") or 60),
    )


def comparison_fingerprint(report: dict[str, Any]) -> str:
    raw = report.get("validation_config") or {}
    period = report.get("period") or {}
    payload = {
        "period": {"start": period.get("start"), "end": period.get("end")},
        "markets": list(raw.get("markets") or list((report.get("market_availability") or {}).keys())),
        "minimum_coverage_pct": raw.get("minimum_coverage_pct"),
        "initial_capital": raw.get("initial_capital"),
        "max_holding_days": raw.get("max_holding_days"),
        "round_trip_cost_pct": raw.get("round_trip_cost_pct"),
        "minimum_stock_count": raw.get("minimum_stock_count"),
        "minimum_total_trades": raw.get("minimum_total_trades"),
        "post_target2_research_days": raw.get("post_target2_research_days"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _expand_candidates(
    base_rows: list[dict[str, Any]],
    by_market: dict[str, list[dict[str, Any]]],
    markets: tuple[str, ...],
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    available = {_stock_key(row): row for rows in by_market.values() for row in rows}
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    missing_base: list[str] = []

    for row in base_rows:
        key = _stock_key(row)
        candidate = available.get(key)
        if candidate is None:
            missing_base.append(key)
            continue
        selected.append(candidate)
        selected_keys.add(key)

    queues: dict[str, list[dict[str, Any]]] = {
        market: [row for row in by_market.get(market, []) if _stock_key(row) not in selected_keys]
        for market in markets
    }
    counts = Counter(str(row.get("market") or "").upper() for row in selected)

    while len(selected) < limit:
        available_markets = [market for market in markets if queues.get(market)]
        if not available_markets:
            break
        # Keep the expanded sample as balanced as the locally available data allows.
        market = min(available_markets, key=lambda item: (counts[item], markets.index(item)))
        row = queues[market].pop(0)
        key = _stock_key(row)
        if key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(key)
        counts[market] += 1

    return selected[:limit], missing_base


class ExpandedSamplePlanner:
    def __init__(self, market_store: HistoricalMarketStore | None = None, provider: KrxProvider | None = None) -> None:
        self.market_store = market_store or HistoricalMarketStore()
        self.provider = provider

    @staticmethod
    def _weekdays(start: date, end: date) -> list[date]:
        rows: list[date] = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                rows.append(cursor)
            cursor += timedelta(days=1)
        return rows

    def _missing_history_work(self, config: ExitPolicyValidationRunnerConfig) -> list[tuple[str, str, date]]:
        start = date.fromisoformat(config.start_date)
        end = date.fromisoformat(config.end_date)
        stable_end = min(end, today_kst() - timedelta(days=1))
        if stable_end < start:
            return []
        warmup_start = max(start - timedelta(days=DEFAULT_WARMUP_CALENDAR_DAYS), date(1990, 1, 1))
        weekdays = self._weekdays(warmup_start, stable_end)
        work: list[tuple[str, str, date]] = []
        for market in config.markets:
            for kind in ("stock", "index"):
                completed = self.market_store.completed_days(
                    market,
                    warmup_start.strftime("%Y%m%d"),
                    stable_end.strftime("%Y%m%d"),
                    kind,
                )
                for day in weekdays:
                    key = day.strftime("%Y%m%d")
                    if key not in completed:
                        work.append((market, kind, day))
        return work

    def plan(self, base_report: dict[str, Any], target_stocks: int) -> dict[str, Any]:
        if str(base_report.get("status") or "") != "COMPLETED":
            raise ValueError("완료된 연구 결과가 있어야 확대 표본 검증을 준비할 수 있습니다.")
        base_rows = list(base_report.get("selected_stocks") or base_report.get("validated_stocks") or [])
        base_count = len(base_rows)
        if target_stocks not in ALLOWED_EXPANDED_TARGETS:
            raise ValueError("확대 검증 종목 수는 20, 40, 60 중 하나여야 합니다.")
        if target_stocks <= base_count:
            raise ValueError(f"현재 연구가 이미 {base_count}종목입니다. 더 큰 표본을 선택해 주세요.")

        config = validation_config_from_report(base_report, target_stocks)
        config.validate()
        start_dd = config.start_date.replace("-", "")
        end_dd = config.end_date.replace("-", "")
        candidate_groups: dict[str, list[dict[str, Any]]] = {}
        availability: dict[str, Any] = {}
        for market in config.markets:
            row = self.market_store.research_candidates(
                market,
                start_dd,
                end_dd,
                minimum_coverage_pct=config.minimum_coverage_pct,
                limit=5000,
            )
            availability[market] = row
            if float(row.get("index_coverage_pct") or 0.0) + 1e-9 < config.minimum_coverage_pct:
                candidate_groups[market] = []
            else:
                candidate_groups[market] = list(row.get("candidates") or [])

        selected, missing_base = _expand_candidates(base_rows, candidate_groups, config.markets, target_stocks)
        ready_count = len(selected)
        ready_to_run = ready_count >= target_stocks and not missing_base
        missing_work = [] if ready_to_run else self._missing_history_work(config)
        estimated_network = None
        cached_items = None
        if self.provider is not None and missing_work:
            cached = sum(1 for market, kind, day in missing_work if self.provider.has_cached_day(market, day, kind))
            cached_items = cached
            estimated_network = len(missing_work) - cached

        return {
            "version": EXPANDED_SAMPLE_VERSION,
            "base_signature": str(base_report.get("signature") or ""),
            "comparison_fingerprint": comparison_fingerprint(base_report),
            "period": {"start": config.start_date, "end": config.end_date},
            "markets": list(config.markets),
            "base_stock_count": base_count,
            "target_stock_count": target_stocks,
            "ready_stock_count": ready_count,
            "additional_stock_count": max(0, ready_count - base_count),
            "ready_to_run": ready_to_run,
            "missing_base_stocks": missing_base,
            "base_market_counts": _market_counts(base_rows),
            "target_market_counts": _market_counts(selected),
            "selected_stocks": selected,
            "market_availability": availability,
            "data_preparation": {
                "needed": not ready_to_run,
                "can_prepare": bool(missing_work),
                "missing_history_items": len(missing_work),
                "cached_history_items": cached_items,
                "estimated_network_requests": estimated_network,
                "note": (
                    "부족한 시장 일별 데이터만 준비하면 후보 표본을 다시 계산할 수 있습니다."
                    if missing_work
                    else "현재 저장 데이터에서 목표 종목 수를 만들 수 없습니다. 더 작은 표본을 선택하거나 데이터 범위를 확인해 주세요."
                ),
            },
        }


class ExpandedSamplePreparationService:
    def __init__(self, provider: KrxProvider, market_store: HistoricalMarketStore | None = None) -> None:
        self.provider = provider
        self.market_store = market_store or HistoricalMarketStore()
        self.planner = ExpandedSamplePlanner(self.market_store, provider)

    @staticmethod
    def _emit(progress: ProgressCallback | None, **payload: Any) -> None:
        if progress is not None:
            progress(payload)

    async def prepare(
        self,
        base_report: dict[str, Any],
        target_stocks: int,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        started = monotonic()
        before_plan = self.planner.plan(base_report, target_stocks)
        if before_plan.get("ready_to_run"):
            return {
                "version": EXPANDED_SAMPLE_VERSION,
                "status": "READY",
                "message": "이미 저장된 데이터만으로 확대 표본 검증을 실행할 수 있습니다.",
                "plan": before_plan,
                "performance": {"total_seconds": round(monotonic() - started, 3), "network_requests": 0},
            }

        config = validation_config_from_report(base_report, target_stocks)
        work = self.planner._missing_history_work(config)
        if not work:
            return {
                "version": EXPANDED_SAMPLE_VERSION,
                "status": "DATA_LIMIT",
                "message": "추가로 준비할 시장 일별 데이터가 없지만 목표 종목 수를 확보하지 못했습니다.",
                "plan": before_plan,
                "performance": {"total_seconds": round(monotonic() - started, 3), "network_requests": 0},
            }

        cached = sum(1 for market, kind, day in work if self.provider.has_cached_day(market, day, kind))
        estimated_network = len(work) - cached
        self.provider.assert_budget(estimated_network)
        stats_before = self.provider.request_stats()
        await self.provider.open_session()
        completed = 0
        errors: list[str] = []
        concurrency = min(8, max(1, len(work)))
        queue: asyncio.Queue[tuple[str, str, date]] = asyncio.Queue()
        for item in work:
            queue.put_nowait(item)

        def emit(current_item: str) -> None:
            self._emit(
                progress,
                stage="expanded_sample_data_prepare",
                message="확대 표본 검증에 필요한 저장 시세를 준비하고 있습니다.",
                current=completed,
                total=max(len(work), 1),
                details={
                    "current_item": current_item,
                    "items_done": completed,
                    "items_total": len(work),
                    "estimated_network_requests": estimated_network,
                    "cached_items": cached,
                },
            )

        async def worker() -> None:
            nonlocal completed
            while True:
                try:
                    market, kind, day = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                label = f"{market} {day.isoformat()} {'주식' if kind == 'stock' else '지수'}"
                try:
                    if kind == "stock":
                        result = await self.provider.stock_daily(market, day)
                        rows = list(result.get("rows") or [])
                        await asyncio.to_thread(
                            self.market_store.put_stock_day,
                            market,
                            day.strftime("%Y%m%d"),
                            rows,
                            stable=True,
                        )
                    else:
                        result = await self.provider.index_daily(market, day)
                        rows = list(result.get("rows") or [])
                        main = self.provider._select_main_index(rows, market) if rows else None  # noqa: SLF001
                        await asyncio.to_thread(
                            self.market_store.put_index_day,
                            market,
                            day.strftime("%Y%m%d"),
                            main,
                            stable=True,
                        )
                except Exception as exc:  # preserve successfully prepared days and report partial progress
                    errors.append(f"{label}: {exc}")
                finally:
                    completed += 1
                    queue.task_done()
                    if completed == len(work) or completed % max(1, concurrency) == 0:
                        emit(label)

        try:
            emit("준비 시작")
            await asyncio.gather(*(worker() for _ in range(concurrency)))
        finally:
            await self.provider.close_session()

        after_plan = self.planner.plan(base_report, target_stocks)
        stats_after = self.provider.request_stats()
        network_requests = int(stats_after.get("network_requests", 0)) - int(stats_before.get("network_requests", 0))
        status = "READY" if after_plan.get("ready_to_run") else "PARTIAL"
        return {
            "version": EXPANDED_SAMPLE_VERSION,
            "status": status,
            "message": (
                "확대 표본 검증에 필요한 데이터 준비가 완료됐습니다."
                if status == "READY"
                else "일부 데이터는 준비했지만 아직 목표 종목 수가 확보되지 않았습니다."
            ),
            "plan": after_plan,
            "errors": errors[:20],
            "performance": {
                "total_seconds": round(monotonic() - started, 3),
                "prepared_items": completed,
                "error_count": len(errors),
                "network_requests": max(0, network_requests),
            },
        }


def compare_validation_reports(
    base_report: dict[str, Any],
    expanded_report: dict[str, Any],
    base_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_by_strategy = {str(row.get("strategy") or ""): row for row in base_report.get("strategies", []) or []}
    expanded_by_strategy = {str(row.get("strategy") or ""): row for row in expanded_report.get("strategies", []) or []}
    strategies = sorted(set(base_by_strategy) | set(expanded_by_strategy))
    rows: list[dict[str, Any]] = []
    same_status = 0
    same_policy = 0
    for strategy in strategies:
        before = base_by_strategy.get(strategy) or {}
        after = expanded_by_strategy.get(strategy) or {}
        before_status = str(before.get("status") or "")
        after_status = str(after.get("status") or "")
        before_policy = str(before.get("selected_policy_id") or "")
        after_policy = str(after.get("selected_policy_id") or "")
        status_same = bool(before_status and before_status == after_status)
        policy_same = bool(before_policy == after_policy)
        same_status += int(status_same)
        same_policy += int(policy_same)
        rows.append(
            {
                "strategy": strategy,
                "before_status": before_status,
                "after_status": after_status,
                "before_policy_id": before_policy,
                "after_policy_id": after_policy,
                "status_same": status_same,
                "policy_same": policy_same,
            }
        )

    sensitive: list[str] = []
    if base_audit and str(base_audit.get("validation_signature") or "") == str(base_report.get("signature") or ""):
        sensitive = [
            str(row.get("strategy") or "")
            for row in base_audit.get("strategies", []) or []
            if str((row.get("leave_one_out") or {}).get("status") or "") == "SENSITIVE"
        ]
    sensitive_set = set(sensitive)
    sensitive_rows = [row for row in rows if row["strategy"] in sensitive_set]

    base_count = len(base_report.get("validated_stocks") or base_report.get("selected_stocks") or [])
    expanded_count = len(expanded_report.get("validated_stocks") or expanded_report.get("selected_stocks") or [])
    base_summary = base_report.get("summary") or {}
    expanded_summary = expanded_report.get("summary") or {}
    transitions: dict[str, int] = {}
    for row in rows:
        if row["status_same"]:
            continue
        key = f"{row['before_status']}->{row['after_status']}"
        transitions[key] = transitions.get(key, 0) + 1

    expanded_selected = int(expanded_summary.get("selected") or 0)
    changed_rows = [row for row in rows if not row["status_same"]]
    if expanded_selected > 0:
        outcome = "NEW_CANDIDATE"
    elif not changed_rows:
        outcome = "NO_CANDIDATE_STABLE"
    elif changed_rows and all(
        row["after_status"] == "BASELINE_BETTER"
        and row["before_status"] in {"UNRESOLVED", "BASELINE_BETTER", "SELECTED"}
        for row in changed_rows
    ):
        outcome = "BASELINE_STRENGTHENED"
    else:
        outcome = "MIXED_OR_UNSTABLE"

    return {
        "version": EXPANDED_SAMPLE_VERSION,
        "base_signature": str(base_report.get("signature") or ""),
        "expanded_signature": str(expanded_report.get("signature") or ""),
        "base_stock_count": base_count,
        "expanded_stock_count": expanded_count,
        "conditions_match": comparison_fingerprint(base_report) == comparison_fingerprint(expanded_report),
        "comparison_fingerprint": comparison_fingerprint(base_report),
        "strategy_count": len(rows),
        "same_status_count": same_status,
        "changed_status_count": len(rows) - same_status,
        "same_policy_count": same_policy,
        "strategies": rows,
        "transitions": transitions,
        "outcome": outcome,
        "previously_sensitive_strategies": sensitive,
        "previously_sensitive_same_status": sum(1 for row in sensitive_rows if row["status_same"]),
        "previously_sensitive_changed_status": sum(1 for row in sensitive_rows if not row["status_same"]),
        "base_summary": base_summary,
        "expanded_summary": expanded_summary,
    }
