from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Callable

from app.backtest.models import BacktestConfig
from app.backtest.policy_lab import (
    POLICY_BLOCK_ALL_CAUTION,
    POLICY_BLOCK_WIDE_STOP,
    POLICY_CURRENT,
    POLICY_DEFINITIONS,
    POLICY_NEAREST_VALID_ANCHOR,
)
from app.backtest.service import BacktestService
from app.core.stock_code import normalize_stock_code
from app.market.providers import KrxProvider
from app.market.providers.base import ProviderError

ProgressCallback = Callable[[dict[str, Any]], None]

POLICY_ORDER = [
    POLICY_BLOCK_WIDE_STOP,
    POLICY_NEAREST_VALID_ANCHOR,
    POLICY_BLOCK_ALL_CAUTION,
]

# v0.19.5 already treats retaining less than half of the original trades as too
# aggressive. Cross-stock validation deliberately reuses the same guardrail instead
# of introducing a new fitted threshold.
MIN_TRADE_RETENTION_RATIO = 0.50
MIN_TESTED_STOCKS = 3
MIN_TRIGGERED_STOCKS = 2


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _scenario_map(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in (comparison.get("scenarios") or [])
        if item.get("id")
    }


def _trade_retention(candidate: dict[str, Any], baseline: dict[str, Any]) -> float | None:
    baseline_trades = _as_int((baseline.get("metrics") or {}).get("trades"))
    if baseline_trades <= 0:
        return None
    candidate_trades = _as_int((candidate.get("metrics") or {}).get("trades"))
    return max(0.0, candidate_trades / baseline_trades)


def _changed_count(policy_id: str, scenario: dict[str, Any]) -> int:
    if policy_id == POLICY_NEAREST_VALID_ANCHOR:
        return _as_int(scenario.get("anchor_changed_trades"))
    return _as_int(scenario.get("blocked_by_policy"))


def _problem_solved(
    policy_id: str,
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if policy_id == POLICY_BLOCK_ALL_CAUTION:
        return _as_int(candidate.get("caution_trades")) < _as_int(baseline.get("caution_trades"))
    if policy_id == POLICY_BLOCK_WIDE_STOP:
        return _as_int(candidate.get("wide_stop_trades")) < _as_int(baseline.get("wide_stop_trades"))
    if policy_id == POLICY_NEAREST_VALID_ANCHOR:
        if _as_int(candidate.get("anchor_changed_trades")) <= 0:
            return False
        baseline_wide = _as_int(baseline.get("wide_stop_trades"))
        candidate_wide = _as_int(candidate.get("wide_stop_trades"))
        baseline_stop = _as_float(baseline.get("average_initial_stop_distance_pct"))
        candidate_stop = _as_float(candidate.get("average_initial_stop_distance_pct"))
        narrower = (
            baseline_stop is not None
            and candidate_stop is not None
            and candidate_stop < baseline_stop
        )
        return candidate_wide < baseline_wide or narrower
    return False


def _stock_policy_evidence(
    stock: dict[str, Any],
    policy_id: str,
) -> dict[str, Any] | None:
    comparison = stock.get("risk_policy_comparison") or {}
    scenarios = _scenario_map(comparison)
    baseline = scenarios.get(POLICY_CURRENT)
    candidate = scenarios.get(policy_id)
    if baseline is None or candidate is None:
        return None

    baseline_metrics = baseline.get("metrics") or {}
    candidate_metrics = candidate.get("metrics") or {}
    baseline_trades = _as_int(baseline_metrics.get("trades"))
    expectancy_delta = _as_float((candidate.get("delta") or {}).get("expectancy_pctp"))
    mdd_delta = _as_float((candidate.get("delta") or {}).get("max_drawdown_pctp"))
    retention = _trade_retention(candidate, baseline)
    changed = _changed_count(policy_id, candidate)
    triggered = changed > 0
    solved = triggered and _problem_solved(policy_id, baseline=baseline, candidate=candidate)

    # "균형 개선" deliberately means both key outcomes did not worsen. We avoid
    # inventing a tiny tolerance just to make a candidate look better.
    balanced = bool(
        solved
        and expectancy_delta is not None
        and mdd_delta is not None
        and expectancy_delta >= 0
        and mdd_delta >= 0
    )
    harmed = bool(
        triggered
        and expectancy_delta is not None
        and mdd_delta is not None
        and expectancy_delta < 0
        and mdd_delta < 0
    )
    overfiltered = bool(triggered and retention is not None and retention < MIN_TRADE_RETENTION_RATIO)

    if baseline_trades <= 0:
        status = "NO_BASELINE_TRADES"
    elif not triggered:
        status = "NOT_TRIGGERED"
    elif overfiltered:
        status = "OVERFILTERED"
    elif balanced:
        status = "BALANCED_IMPROVEMENT"
    elif solved and (mdd_delta or 0) > 0:
        status = "RISK_TRADEOFF"
    elif solved:
        status = "PROBLEM_ONLY"
    elif harmed:
        status = "HARMED"
    else:
        status = "MIXED"

    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "size_band": stock.get("size_band"),
        "baseline_trades": baseline_trades,
        "candidate_trades": _as_int(candidate_metrics.get("trades")),
        "changed_trades": changed,
        "triggered": triggered,
        "problem_solved": solved,
        "balanced_improvement": balanced,
        "harmed": harmed,
        "overfiltered": overfiltered,
        "trade_retention_pct": None if retention is None else round(retention * 100.0, 1),
        "expectancy_delta_pctp": expectancy_delta,
        "max_drawdown_delta_pctp": mdd_delta,
        "baseline_expectancy_pct": _as_float(baseline_metrics.get("expectancy_pct")),
        "candidate_expectancy_pct": _as_float(candidate_metrics.get("expectancy_pct")),
        "baseline_max_drawdown_pct": _as_float(baseline_metrics.get("max_drawdown_pct")),
        "candidate_max_drawdown_pct": _as_float(candidate_metrics.get("max_drawdown_pct")),
        "status": status,
    }


def _policy_verdict(summary: dict[str, Any]) -> dict[str, str]:
    tested = _as_int(summary.get("tested_stocks"))
    triggered = _as_int(summary.get("triggered_stocks"))
    solved = _as_int(summary.get("problem_solved_stocks"))
    balanced = _as_int(summary.get("balanced_improvement_stocks"))
    harmed = _as_int(summary.get("harmed_stocks"))
    overfiltered = _as_int(summary.get("overfiltered_stocks"))

    if tested < MIN_TESTED_STOCKS:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "label": "표본 부족",
            "reason": f"실제 거래가 있었던 종목이 {tested}개라 여러 종목에서 반복되는지 판단하기 어렵습니다.",
        }
    if triggered < MIN_TRIGGERED_STOCKS:
        return {
            "status": "NOT_REPEATED",
            "label": "반복되지 않음",
            "reason": f"이 정책이 실제 결과를 바꾼 종목이 {triggered}개뿐이라 공통 문제로 보기 어렵습니다.",
        }

    majority = max(2, math.ceil(triggered / 2))
    if overfiltered >= majority:
        return {
            "status": "TOO_AGGRESSIVE",
            "label": "너무 강한 필터",
            "reason": f"적용된 {triggered}개 종목 중 {overfiltered}개에서 기존 거래의 절반 이상이 사라졌습니다.",
        }
    if balanced >= majority and solved >= majority and harmed < majority:
        return {
            "status": "CROSS_VALIDATION_SUPPORT",
            "label": "반복 개선 확인",
            "reason": f"정책이 작동한 {triggered}개 종목 중 {solved}개에서 목표 문제를 줄였고, {balanced}개에서는 거래당 평균과 최대 낙폭이 함께 악화되지 않았습니다.",
        }
    if solved >= majority and harmed < majority:
        return {
            "status": "RISK_ONLY_SUPPORT",
            "label": "위험 개선·대가 있음",
            "reason": f"{solved}개 종목에서 목표 위험은 줄었지만, 성과나 거래 기회 측면의 대가가 반복돼 실제 적용 근거로는 아직 부족합니다.",
        }
    if harmed >= majority:
        return {
            "status": "REJECT",
            "label": "개선 근거 없음",
            "reason": f"정책이 작동한 종목 중 {harmed}개에서 거래당 평균과 최대 낙폭이 함께 나빠졌습니다.",
        }
    return {
        "status": "MIXED",
        "label": "결과 혼재",
        "reason": "종목마다 효과 방향이 달라 하나의 공통 Risk 정책으로 채택하기 어렵습니다.",
    }


def build_cross_stock_policy_decision(
    stocks: list[dict[str, Any]],
    *,
    target_code: str,
    market: str,
    period: dict[str, str],
    selection: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate v0.19.5 policy experiments across automatically selected peers.

    This is a *research decision layer*. It never changes the production Risk Engine.
    Candidate selection rewards repeatable problem reduction and penalizes broad
    filtering; it intentionally does not rank by the highest raw return.
    """

    policy_rows: list[dict[str, Any]] = []
    for policy_id in POLICY_ORDER:
        evidence = [
            item
            for stock in stocks
            if (item := _stock_policy_evidence(stock, policy_id)) is not None
        ]
        tested = [item for item in evidence if item["baseline_trades"] > 0]
        triggered = [item for item in tested if item["triggered"]]
        solved = [item for item in triggered if item["problem_solved"]]
        balanced = [item for item in triggered if item["balanced_improvement"]]
        harmed = [item for item in triggered if item["harmed"]]
        overfiltered = [item for item in triggered if item["overfiltered"]]

        retention_values = [
            float(item["trade_retention_pct"])
            for item in triggered
            if item["trade_retention_pct"] is not None
        ]
        expectancy_deltas = [
            float(item["expectancy_delta_pctp"])
            for item in triggered
            if item["expectancy_delta_pctp"] is not None
        ]
        mdd_deltas = [
            float(item["max_drawdown_delta_pctp"])
            for item in triggered
            if item["max_drawdown_delta_pctp"] is not None
        ]
        definition = POLICY_DEFINITIONS.get(policy_id, {})
        summary = {
            "policy_id": policy_id,
            "label": definition.get("label", policy_id),
            "problem_target": definition.get("problem_target", ""),
            "tested_stocks": len(tested),
            "triggered_stocks": len(triggered),
            "problem_solved_stocks": len(solved),
            "balanced_improvement_stocks": len(balanced),
            "harmed_stocks": len(harmed),
            "overfiltered_stocks": len(overfiltered),
            "average_trade_retention_pct": _mean(retention_values),
            "average_expectancy_delta_pctp": _mean(expectancy_deltas),
            "average_max_drawdown_delta_pctp": _mean(mdd_deltas),
            "stock_evidence": evidence,
        }
        summary["verdict"] = _policy_verdict(summary)
        policy_rows.append(summary)

    supported = [
        row
        for row in policy_rows
        if (row.get("verdict") or {}).get("status") == "CROSS_VALIDATION_SUPPORT"
    ]
    # Prefer the policy supported by more stocks. Only after repeatability ties do we
    # use risk improvement and then the narrower-policy order as tie breakers.
    order_index = {policy_id: index for index, policy_id in enumerate(POLICY_ORDER)}
    supported.sort(
        key=lambda row: (
            -_as_int(row.get("balanced_improvement_stocks")),
            -_as_int(row.get("problem_solved_stocks")),
            -(_as_float(row.get("average_max_drawdown_delta_pctp")) or 0.0),
            order_index.get(str(row.get("policy_id")), 99),
        )
    )

    target = next((stock for stock in stocks if stock.get("code") == target_code), None)
    target_candidate = (
        ((target or {}).get("risk_policy_comparison") or {}).get("next_validation_candidate")
        if target
        else None
    )
    recommended = supported[0] if supported else None

    valid_stocks = sum(
        1
        for stock in stocks
        if _as_int((((_scenario_map(stock.get("risk_policy_comparison") or {}).get(POLICY_CURRENT) or {}).get("metrics") or {}).get("trades"))) > 0
    )

    if recommended is not None:
        recommended_id = str(recommended.get("policy_id"))
        matched_target = bool(target_candidate and target_candidate.get("policy_id") == recommended_id)
        headline = f"정책 ‘{recommended['label']}’이 여러 종목에서도 가장 반복적으로 문제를 줄였습니다."
        reason = str((recommended.get("verdict") or {}).get("reason") or "")
        if matched_target:
            reason += " 기준 종목에서 찾은 후보와 여러 종목 교차검증 결과도 일치했습니다."
        elif target_candidate:
            reason += " 다만 기준 종목에서 처음 나온 후보와는 달라, 한 종목만 보고 결정하면 안 된다는 점도 확인됐습니다."
        decision = {
            "status": "PROMOTION_CANDIDATE",
            "label": "정책 승격 검토 후보",
            "headline": headline,
            "reason": reason,
            "recommended_policy_id": recommended_id,
            "recommended_policy_label": recommended.get("label"),
            "next_step": "실제 Risk Gate에 적용하기 전, 다른 기간 또는 다른 시장에서도 같은 개선이 반복되는지 한 번 더 검증합니다.",
        }
    else:
        risk_only = [
            row
            for row in policy_rows
            if (row.get("verdict") or {}).get("status") == "RISK_ONLY_SUPPORT"
        ]
        if risk_only:
            risk_only.sort(
                key=lambda row: (
                    -_as_int(row.get("problem_solved_stocks")),
                    _as_int(row.get("harmed_stocks")),
                    order_index.get(str(row.get("policy_id")), 99),
                )
            )
            next_research = risk_only[0]
            decision = {
                "status": "MORE_VALIDATION",
                "label": "실제 적용 보류",
                "headline": "위험은 줄었지만 부작용 없이 반복된 정책은 아직 없습니다.",
                "reason": f"‘{next_research['label']}’이 위험 문제는 가장 자주 줄였지만 성과 또는 거래 기회 측면의 대가가 남았습니다.",
                "recommended_policy_id": None,
                "recommended_policy_label": None,
                "next_step": "정책을 실제 규칙에 넣지 않고 다른 기간에서 같은 대가가 반복되는지 추가 검증합니다.",
            }
        else:
            decision = {
                "status": "INSUFFICIENT_EVIDENCE",
                "label": "정책 변경 보류",
                "headline": "여러 종목에서도 반복되는 해결책을 아직 찾지 못했습니다.",
                "reason": "정책이 작동한 종목 수가 적거나 종목마다 결과 방향이 달랐습니다. 수익률이 높은 한 사례만으로 Risk 규칙을 바꾸지 않습니다.",
                "recommended_policy_id": None,
                "recommended_policy_label": None,
                "next_step": "현재 Risk 정책을 유지하고, 표본 기간이나 검증 범위를 넓힐 필요가 있습니다.",
            }

    return {
        "version": "0.19.6",
        "status": "CROSS_STOCK_RESEARCH",
        "market": market,
        "period": period,
        "target_code": target_code,
        "selection": selection,
        "tested_stock_count": len(stocks),
        "valid_trade_stock_count": valid_stocks,
        "stocks": stocks,
        "policies": policy_rows,
        "decision": decision,
        "guardrail": "이 결과는 동일 시장의 여러 종목에서 Risk 정책의 반복성을 확인하는 연구 단계입니다. 실제 Risk Engine이나 진입 규칙은 자동 변경하지 않습니다.",
        "limitation": "대표 종목은 검증 시작일 이전의 KRX 시가총액 순위를 기준으로 자동 선택합니다. 같은 시장의 종목들은 시장환경을 공유하므로 완전히 독립된 표본은 아닙니다.",
    }


class RiskPolicyValidationService:
    SAMPLE_STOCKS = 6  # target + five automatically selected peers
    SNAPSHOT_LOOKBACK_DAYS = 15
    PEER_QUANTILES = (0.03, 0.18, 0.38, 0.62, 0.82)

    def __init__(
        self,
        krx: KrxProvider,
        *,
        backtest_service: BacktestService | None = None,
    ) -> None:
        self.krx = krx
        self.backtest_service = backtest_service or BacktestService(krx)

    @staticmethod
    def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
        if callback is not None:
            callback(payload)

    async def _market_snapshot(self, market: str, as_of: date) -> tuple[str, list[dict[str, Any]]]:
        await self.krx.open_session()
        try:
            for offset in range(self.SNAPSHOT_LOOKBACK_DAYS):
                candidate = as_of - timedelta(days=offset)
                if candidate.weekday() >= 5:
                    continue
                result = await self.krx.stock_daily(market, candidate)
                if result.get("count"):
                    return str(result.get("date") or candidate.strftime("%Y%m%d")), list(result.get("rows") or [])
        finally:
            await self.krx.close_session()
        raise ProviderError("검증 시작일 이전의 KRX 시장 표본을 찾지 못했습니다.")

    @staticmethod
    def _eligible_universe(rows: list[dict[str, Any]], target_code: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        eligible: list[dict[str, Any]] = []
        for row in rows:
            code = str(row.get("code") or "").strip()
            if len(code) != 6 or not code.isdigit() or code in seen or code == target_code:
                continue
            market_cap = _as_float(row.get("market_cap"))
            close = _as_float(row.get("close"))
            volume = _as_float(row.get("volume"))
            name = str(row.get("name") or "").strip()
            if not name or market_cap is None or market_cap <= 0 or close is None or close <= 0:
                continue
            compact_name = name.replace(" ", "")
            if "스팩" in compact_name:
                continue
            # Preferred shares often have a materially different liquidity/price structure
            # from the common stock. Exclude the common Korean suffix patterns from the
            # automatic peer sample so one special security type does not dominate a band.
            if compact_name.endswith(("우", "우B", "우C")):
                continue
            # Avoid selecting a security that did not trade on the snapshot date.
            if volume is not None and volume <= 0:
                continue
            seen.add(code)
            eligible.append(row)
        eligible.sort(key=lambda row: float(row.get("market_cap") or 0), reverse=True)
        return eligible

    @classmethod
    def _select_peer_rows(cls, rows: list[dict[str, Any]], target_code: str) -> list[dict[str, Any]]:
        eligible = cls._eligible_universe(rows, target_code)
        if not eligible:
            return []
        selected: list[dict[str, Any]] = []
        used: set[str] = set()
        last_index = len(eligible) - 1
        for quantile in cls.PEER_QUANTILES:
            ideal = round(last_index * quantile)
            candidates = sorted(range(len(eligible)), key=lambda idx: (abs(idx - ideal), idx))
            for idx in candidates:
                row = eligible[idx]
                code = str(row.get("code") or "")
                if code in used:
                    continue
                used.add(code)
                percentile = (idx + 1) / max(len(eligible), 1)
                if percentile <= 0.10:
                    band = "시총 상위권"
                elif percentile <= 0.30:
                    band = "시총 중상위권"
                elif percentile <= 0.55:
                    band = "시총 중간권"
                elif percentile <= 0.75:
                    band = "시총 중하위권"
                else:
                    band = "시총 하위권"
                selected.append({**row, "size_band": band, "universe_rank": idx + 1})
                break
        return selected

    async def run(
        self,
        config: BacktestConfig,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        target_code = normalize_stock_code(config.code)
        market = config.market.upper().strip()
        start = date.fromisoformat(config.start_date)

        self._emit(
            progress,
            stage="cross_validation_select",
            message="같은 시장의 대표 종목을 자동 선택 중",
            current=0,
            total=1,
            details={"market": market},
        )
        snapshot_date, universe_rows = await self._market_snapshot(market, start)
        target_row = next((row for row in universe_rows if str(row.get("code") or "") == target_code), None)
        peer_rows = self._select_peer_rows(universe_rows, target_code)

        selected: list[dict[str, Any]] = [
            {
                "code": target_code,
                "name": str((target_row or {}).get("name") or target_code),
                "market_cap": _as_float((target_row or {}).get("market_cap")),
                "size_band": "기준 종목",
                "role": "TARGET",
            }
        ]
        for row in peer_rows[: self.SAMPLE_STOCKS - 1]:
            selected.append({
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or row.get("code") or ""),
                "market_cap": _as_float(row.get("market_cap")),
                "size_band": str(row.get("size_band") or "시장 표본"),
                "role": "PEER",
                "universe_rank": _as_int(row.get("universe_rank")),
            })

        selection = {
            "method": "START_DATE_MARKET_CAP_STRATIFIED",
            "label": "검증 시작일 기준 동일 시장 시가총액 구간별 자동 표본",
            "snapshot_date": snapshot_date,
            "market": market,
            "requested_stock_count": self.SAMPLE_STOCKS,
            "selected_stock_count": len(selected),
            "description": "기준 종목과 같은 시장에서 검증 시작일 이전에 실제 거래된 종목을 시가총액 순서로 나누고 상위·중간·하위 구간에서 자동 선택합니다. 사용자가 유리한 종목을 골라 결과를 맞추는 것을 줄이기 위한 방식입니다.",
        }

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        total = max(len(selected), 1)
        for index, stock in enumerate(selected, start=1):
            stock_name = str(stock.get("name") or stock.get("code") or "")
            self._emit(
                progress,
                stage="cross_validation",
                message=f"대표 종목 교차검증 · {stock_name}",
                current=index - 1,
                total=total,
                details={
                    "stock_index": index,
                    "stock_total": total,
                    "stock_code": stock.get("code"),
                    "stock_name": stock_name,
                    "inner_percent": 0.0,
                },
            )

            def child_progress(payload: dict[str, Any]) -> None:
                inner_total = max(_as_int(payload.get("total")), 1)
                inner_current = max(0, _as_int(payload.get("current")))
                inner_percent = min(100.0, inner_current / inner_total * 100.0)
                self._emit(
                    progress,
                    stage="cross_validation",
                    message=f"{stock_name} · {payload.get('message') or '검증 중'}",
                    current=index - 1,
                    total=total,
                    details={
                        "stock_index": index,
                        "stock_total": total,
                        "stock_code": stock.get("code"),
                        "stock_name": stock_name,
                        "inner_percent": round(inner_percent, 1),
                        "inner_stage": payload.get("stage"),
                    },
                )

            child_config = replace(config, code=str(stock.get("code") or target_code), market=market)
            try:
                result = await self.backtest_service.run_pullback(child_config, progress=child_progress)
            except (ProviderError, ValueError) as exc:
                errors.append({"code": str(stock.get("code") or ""), "name": stock_name, "error": str(exc)})
                continue

            results.append({
                **stock,
                "summary": result.get("summary") or {},
                "risk_policy_comparison": result.get("risk_policy_comparison") or {},
                "accuracy_audit": result.get("accuracy_audit") or {},
            })
            self._emit(
                progress,
                stage="cross_validation",
                message=f"대표 종목 교차검증 · {stock_name} 완료",
                current=index,
                total=total,
                details={
                    "stock_index": index,
                    "stock_total": total,
                    "stock_code": stock.get("code"),
                    "stock_name": stock_name,
                    "inner_percent": 100.0,
                },
            )

        decision = build_cross_stock_policy_decision(
            results,
            target_code=target_code,
            market=market,
            period={"start": config.start_date, "end": config.end_date},
            selection=selection,
        )
        decision["errors"] = errors
        self._emit(
            progress,
            stage="cross_validation_completed",
            message="여러 종목 Risk 정책 교차검증 완료",
            current=total,
            total=total,
            details={
                "tested_stocks": len(results),
                "recommended_policy": (decision.get("decision") or {}).get("recommended_policy_id"),
            },
        )
        return decision
