from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from app.backtest.exit_policy_catalog import POLICY_TARGET1_FULL_EXIT

EXIT_POLICY_SELECTION_VERSION = "0.21.4-B.1"
SELECTION_BASIS = "PARETO_NO_WEIGHTING"


@dataclass(frozen=True, slots=True)
class ExitPolicySelectionConfig:
    minimum_stock_count: int = 3
    minimum_total_trades: int = 30

    def validate(self) -> None:
        if self.minimum_stock_count < 2 or self.minimum_stock_count > 50:
            raise ValueError("정책 선택 최소 종목 수는 2~50 범위여야 합니다.")
        if self.minimum_total_trades < 10 or self.minimum_total_trades > 10000:
            raise ValueError("정책 선택 최소 거래 수는 10~10000 범위여야 합니다.")


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _weighted_average(pairs: Iterable[tuple[float | None, int]]) -> float | None:
    numerator = 0.0
    denominator = 0
    for value, weight in pairs:
        if value is None or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    return None if denominator == 0 else numerator / denominator


def _median(values: Iterable[float | None]) -> float | None:
    rows = [value for value in values if value is not None]
    return None if not rows else float(median(rows))


def _worst_mdd(values: Iterable[float | None]) -> float | None:
    rows = [value for value in values if value is not None]
    return None if not rows else min(rows)


def _safe_profit_factor(profit_sum: float, loss_abs_sum: float) -> float | None:
    if loss_abs_sum > 0:
        return profit_sum / loss_abs_sum
    if profit_sum > 0:
        return None  # infinite PF is intentionally represented as unavailable, not a huge invented number.
    return None


def _metric_vector(row: dict[str, Any], *, include_giveback: bool = False) -> dict[str, tuple[float | None, bool]]:
    metrics = row.get("aggregate_metrics") or {}
    result: dict[str, tuple[float | None, bool]] = {
        "average_net_return_pct": (_number(metrics.get("average_net_return_pct")), True),
        "profit_factor": (_number(metrics.get("profit_factor")), True),
        "median_max_drawdown_pct": (_number(metrics.get("median_max_drawdown_pct")), True),
    }
    if include_giveback:
        result["average_profit_giveback_pct_points"] = (
            _number(metrics.get("average_profit_giveback_pct_points")),
            False,
        )
    return result


def _dominates(left: dict[str, Any], right: dict[str, Any], *, include_giveback: bool = False) -> bool:
    """Return True only when left is no worse on every comparable metric and better on at least one.

    This avoids an invented weighted score. Missing metrics do not create an advantage; at least two
    comparable core metrics must exist before a dominance decision is allowed.
    """

    left_vector = _metric_vector(left, include_giveback=include_giveback)
    right_vector = _metric_vector(right, include_giveback=include_giveback)
    comparable = 0
    strictly_better = False
    for key, (left_value, higher_is_better) in left_vector.items():
        right_value = right_vector.get(key, (None, higher_is_better))[0]
        if left_value is None or right_value is None:
            continue
        comparable += 1
        if higher_is_better:
            if left_value < right_value:
                return False
            if left_value > right_value:
                strictly_better = True
        else:
            if left_value > right_value:
                return False
            if left_value < right_value:
                strictly_better = True
    return comparable >= 2 and strictly_better


def _extract_primitives(policy_row: dict[str, Any]) -> dict[str, float]:
    primitives = policy_row.get("aggregation_primitives") or {}
    trades = _int(primitives.get("trades") or (policy_row.get("metrics") or {}).get("trades"))
    metrics = policy_row.get("metrics") or {}
    research = policy_row.get("profit_protection_metrics") or {}

    # v0.21.4-B.1 research rows provide exact additive primitives. The fallbacks below
    # keep older v0.21.4-A audit snapshots readable without pretending PF aggregation is exact.
    avg_net = _number(metrics.get("average_net_return_pct"))
    win_rate = _number(metrics.get("win_rate_pct"))
    avg_hold = _number(metrics.get("average_holding_days"))
    avg_giveback = _number(research.get("average_profit_giveback_pct_points"))

    return {
        "trades": float(trades),
        "wins": float(primitives.get("wins", 0 if win_rate is None else round(trades * win_rate / 100.0))),
        "net_return_sum_pct": float(primitives.get("net_return_sum_pct", 0.0 if avg_net is None else avg_net * trades)),
        "positive_net_sum_pct": float(primitives.get("positive_net_sum_pct", 0.0)),
        "negative_net_abs_sum_pct": float(primitives.get("negative_net_abs_sum_pct", 0.0)),
        "holding_days_sum": float(primitives.get("holding_days_sum", 0.0 if avg_hold is None else avg_hold * trades)),
        "giveback_sum_pct_points": float(
            primitives.get("giveback_sum_pct_points", 0.0 if avg_giveback is None else avg_giveback * trades)
        ),
        "giveback_observations": float(primitives.get("giveback_observations", trades if avg_giveback is not None else 0)),
    }


def _aggregate_policy(stock_rows: list[dict[str, Any]], policy_id: str) -> dict[str, Any] | None:
    observations: list[dict[str, Any]] = []
    total = {
        "trades": 0.0,
        "wins": 0.0,
        "net_return_sum_pct": 0.0,
        "positive_net_sum_pct": 0.0,
        "negative_net_abs_sum_pct": 0.0,
        "holding_days_sum": 0.0,
        "giveback_sum_pct_points": 0.0,
        "giveback_observations": 0.0,
    }
    mdds: list[float | None] = []
    market_set: set[str] = set()

    for stock in stock_rows:
        policy = next((row for row in stock.get("policies", []) if row.get("policy_id") == policy_id), None)
        if policy is None:
            continue
        primitives = _extract_primitives(policy)
        trades = int(primitives["trades"])
        if trades <= 0:
            continue
        for key in total:
            total[key] += primitives[key]
        metrics = policy.get("metrics") or {}
        research = policy.get("profit_protection_metrics") or {}
        mdd = _number(metrics.get("max_drawdown_pct"))
        mdds.append(mdd)
        market = str(stock.get("market") or "").upper()
        if market:
            market_set.add(market)
        observations.append({
            "code": stock.get("code"),
            "market": market or None,
            "trades": trades,
            "average_net_return_pct": _number(metrics.get("average_net_return_pct")),
            "profit_factor": _number(metrics.get("profit_factor")),
            "max_drawdown_pct": mdd,
            "average_holding_days": _number(metrics.get("average_holding_days")),
            "average_profit_giveback_pct_points": _number(research.get("average_profit_giveback_pct_points")),
        })

    trades = int(total["trades"])
    if trades <= 0:
        return None
    pf = _safe_profit_factor(total["positive_net_sum_pct"], total["negative_net_abs_sum_pct"])
    median_mdd = _median(mdds)
    worst_mdd = _worst_mdd(mdds)
    return {
        "policy_id": policy_id,
        "stock_count": len(observations),
        "markets": sorted(market_set),
        "aggregate_metrics": {
            "trades": trades,
            "win_rate_pct": round(total["wins"] / trades * 100.0, 3),
            "average_net_return_pct": round(total["net_return_sum_pct"] / trades, 4),
            "profit_factor": None if pf is None else round(pf, 4),
            "median_max_drawdown_pct": None if median_mdd is None else round(median_mdd, 4),
            "worst_max_drawdown_pct": None if worst_mdd is None else round(worst_mdd, 4),
            "average_holding_days": round(total["holding_days_sum"] / trades, 3),
            "average_profit_giveback_pct_points": (
                None
                if total["giveback_observations"] <= 0
                else round(total["giveback_sum_pct_points"] / total["giveback_observations"], 4)
            ),
        },
        "stock_results": observations,
        "aggregation_basis": {
            "average_net_return_pct": "TRADE_WEIGHTED_EXACT_FROM_ADDITIVE_PRIMITIVES",
            "profit_factor": "SUM_POSITIVE_NET_RETURN_DIV_SUM_ABSOLUTE_NEGATIVE_NET_RETURN",
            "max_drawdown_pct": "STOCK_LEVEL_MEDIAN_AND_WORST_DAILY_CLOSE_MTM",
            "giveback": "TRADE_WEIGHTED",
        },
    }


def _aggregate_regimes(stock_rows: list[dict[str, Any]], policy_id: str) -> dict[str, Any]:
    combined: dict[str, dict[str, float]] = {}
    for stock in stock_rows:
        policy = next((row for row in stock.get("policies", []) if row.get("policy_id") == policy_id), None)
        if policy is None:
            continue
        for regime, primitive in (policy.get("regime_aggregation_primitives") or {}).items():
            target = combined.setdefault(regime, {
                "trades": 0.0,
                "wins": 0.0,
                "net_return_sum_pct": 0.0,
                "positive_net_sum_pct": 0.0,
                "negative_net_abs_sum_pct": 0.0,
            })
            for key in target:
                target[key] += float((primitive or {}).get(key, 0.0))

    result: dict[str, Any] = {}
    for regime, row in combined.items():
        trades = int(row["trades"])
        if trades <= 0:
            continue
        pf = _safe_profit_factor(row["positive_net_sum_pct"], row["negative_net_abs_sum_pct"])
        result[regime] = {
            "trades": trades,
            "win_rate_pct": round(row["wins"] / trades * 100.0, 3),
            "average_net_return_pct": round(row["net_return_sum_pct"] / trades, 4),
            "profit_factor": None if pf is None else round(pf, 4),
        }
    return result


def _stock_concentration(
    stock_rows: list[dict[str, Any]],
    candidate_policy_id: str,
    baseline_policy_id: str,
) -> dict[str, Any]:
    contributions: list[dict[str, Any]] = []
    for stock in stock_rows:
        candidate = next((row for row in stock.get("policies", []) if row.get("policy_id") == candidate_policy_id), None)
        baseline = next((row for row in stock.get("policies", []) if row.get("policy_id") == baseline_policy_id), None)
        if candidate is None or baseline is None:
            continue
        cand = _extract_primitives(candidate)
        base = _extract_primitives(baseline)
        delta = cand["net_return_sum_pct"] - base["net_return_sum_pct"]
        contributions.append({
            "code": stock.get("code"),
            "market": stock.get("market"),
            "net_return_sum_delta_pct_points": round(delta, 4),
        })
    positives = sorted(
        [row for row in contributions if row["net_return_sum_delta_pct_points"] > 0],
        key=lambda row: row["net_return_sum_delta_pct_points"],
        reverse=True,
    )
    dominant = False
    dominant_code = None
    if positives:
        first = float(positives[0]["net_return_sum_delta_pct_points"])
        rest = sum(float(row["net_return_sum_delta_pct_points"]) for row in positives[1:])
        dominant = first > rest
        if dominant:
            dominant_code = positives[0]["code"]
    return {
        "single_stock_dominant": dominant,
        "dominant_code": dominant_code,
        "definition": "한 종목의 양(+) 개선 기여가 나머지 모든 양(+) 개선 기여 합보다 큰 경우",
        "stock_contributions": contributions,
    }


def _holding_policy_result(
    stock_rows: list[dict[str, Any]],
    selected_policy_id: str | None,
) -> dict[str, Any]:
    if not selected_policy_id or selected_policy_id == POLICY_TARGET1_FULL_EXIT.id:
        return {
            "status": "NOT_APPLICABLE",
            "selected": None,
            "reason": "Target1 전량 종료 정책에는 Target2 이후 Max Hold 비교가 적용되지 않습니다.",
        }

    extended_rows: list[dict[str, Any]] = []
    hard_rows: list[dict[str, Any]] = []
    for stock in stock_rows:
        normal = next((row for row in stock.get("policies", []) if row.get("policy_id") == selected_policy_id), None)
        hard = next(
            (row for row in stock.get("holding_policy_variants", []) if row.get("policy_id") == selected_policy_id),
            None,
        )
        if normal is not None:
            extended_rows.append({"code": stock.get("code"), "market": stock.get("market"), "policies": [normal]})
        if hard is not None:
            hard_rows.append({"code": stock.get("code"), "market": stock.get("market"), "policies": [hard]})

    extended = _aggregate_policy(extended_rows, selected_policy_id)
    hard = _aggregate_policy(hard_rows, selected_policy_id)
    if extended is None or hard is None:
        return {
            "status": "UNRESOLVED",
            "selected": None,
            "reason": "Target2 이후 Max Hold 두 방식을 비교할 표본이 충분하지 않습니다.",
            "extended": extended,
            "hard_max_hold": hard,
        }
    if _dominates(extended, hard, include_giveback=True):
        status = "SELECTED"
        selected = "TRAILING_HORIZON_AFTER_TARGET2"
        reason = "Target2 이후 Trailing horizon 연장이 Hard Max Hold보다 핵심 지표에서 열위가 없고 일부 지표가 개선됐습니다."
    elif _dominates(hard, extended, include_giveback=True):
        status = "SELECTED"
        selected = "HARD_MAX_HOLD"
        reason = "기존 Max Hold 유지가 Trailing horizon 연장보다 핵심 지표에서 열위가 없고 일부 지표가 개선됐습니다."
    else:
        status = "UNRESOLVED"
        selected = None
        reason = "Max Hold 두 방식 사이에 수익/위험 trade-off가 있어 자동 확정하지 않습니다."
    return {
        "status": status,
        "selected": selected,
        "reason": reason,
        "extended": extended,
        "hard_max_hold": hard,
    }


class ExitPolicySelector:
    def __init__(self, config: ExitPolicySelectionConfig | None = None) -> None:
        self.config = config or ExitPolicySelectionConfig()
        self.config.validate()

    def _strategy_stock_rows(self, audits: list[dict[str, Any]], strategy_name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for audit in audits:
            strategy = next((row for row in audit.get("strategies", []) if row.get("strategy") == strategy_name), None)
            if strategy is None:
                continue
            rows.append({
                "code": audit.get("code"),
                "market": audit.get("market"),
                "policies": strategy.get("policies") or [],
                "holding_policy_variants": strategy.get("holding_policy_variants") or [],
            })
        return rows

    def _decide(self, stock_rows: list[dict[str, Any]], policy_ids: list[str]) -> dict[str, Any]:
        baseline_id = POLICY_TARGET1_FULL_EXIT.id
        aggregated = [row for policy_id in policy_ids if (row := _aggregate_policy(stock_rows, policy_id)) is not None]
        by_id = {row["policy_id"]: row for row in aggregated}
        baseline = by_id.get(baseline_id)
        if baseline is None:
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "selected_policy_id": baseline_id,
                "reason": "기존 Target1 정책의 비교 표본이 없어 새 Exit 정책을 선택할 수 없습니다.",
                "baseline": None,
                "policies": aggregated,
            }

        sample_ok = (
            baseline["stock_count"] >= self.config.minimum_stock_count
            and _int((baseline.get("aggregate_metrics") or {}).get("trades")) >= self.config.minimum_total_trades
        )
        candidates = [
            row for row in aggregated
            if row["policy_id"] != baseline_id
            and row["stock_count"] >= self.config.minimum_stock_count
            and _int((row.get("aggregate_metrics") or {}).get("trades")) >= self.config.minimum_total_trades
        ]
        if not sample_ok or not candidates:
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "selected_policy_id": baseline_id,
                "reason": "여러 종목/거래 표본 기준을 충족하지 못해 기존 Target1 전량 종료를 fallback으로 유지합니다.",
                "baseline": baseline,
                "policies": aggregated,
            }

        baseline_improvers = [row for row in candidates if _dominates(row, baseline)]
        if not baseline_improvers:
            if candidates and all(_dominates(baseline, row) for row in candidates):
                return {
                    "status": "BASELINE_BETTER",
                    "selected_policy_id": baseline_id,
                    "reason": "기존 Target1 전량 종료가 모든 충분표본 후보보다 핵심 지표에서 열위가 없습니다.",
                    "baseline": baseline,
                    "policies": aggregated,
                }
            return {
                "status": "UNRESOLVED",
                "selected_policy_id": baseline_id,
                "reason": "새 Exit 후보가 일부 지표는 개선하지만 다른 핵심 지표가 악화되어 자동 확정하지 않습니다.",
                "baseline": baseline,
                "policies": aggregated,
            }

        frontier: list[dict[str, Any]] = []
        for candidate in baseline_improvers:
            dominated_by_other = any(
                other["policy_id"] != candidate["policy_id"] and _dominates(other, candidate, include_giveback=True)
                for other in baseline_improvers
            )
            if not dominated_by_other:
                frontier.append(candidate)

        if len(frontier) != 1:
            return {
                "status": "UNRESOLVED",
                "selected_policy_id": baseline_id,
                "reason": "기존 정책보다 나은 후보가 여러 개지만 서로 수익/위험/Giveback trade-off가 있어 한 정책으로 확정하지 않습니다.",
                "baseline": baseline,
                "policies": aggregated,
            }

        selected = frontier[0]
        concentration = _stock_concentration(stock_rows, selected["policy_id"], baseline_id)
        if concentration["single_stock_dominant"]:
            return {
                "status": "UNRESOLVED",
                "selected_policy_id": baseline_id,
                "reason": "개선 효과가 특정 한 종목에 과도하게 집중되어 새 정책을 자동 확정하지 않습니다.",
                "baseline": baseline,
                "policies": aggregated,
                "stock_concentration": concentration,
            }

        return {
            "status": "SELECTED",
            "selected_policy_id": selected["policy_id"],
            "reason": "기존 Target1 종료보다 핵심 지표에서 열위가 없고, 후보들 중 유일한 Pareto 우위 정책입니다.",
            "baseline": baseline,
            "selected": selected,
            "policies": aggregated,
            "stock_concentration": concentration,
        }

    def run(self, audits: list[dict[str, Any]]) -> dict[str, Any]:
        if len(audits) < 2:
            raise ValueError("Exit 정책 선택 검증에는 최소 2개 종목이 필요합니다.")
        strategy_names: list[str] = []
        policy_ids: list[str] = []
        for audit in audits:
            for strategy in audit.get("strategies", []):
                name = str(strategy.get("strategy") or "")
                if name and name not in strategy_names:
                    strategy_names.append(name)
                for policy in strategy.get("policies", []):
                    policy_id = str(policy.get("policy_id") or "")
                    if policy_id and policy_id not in policy_ids:
                        policy_ids.append(policy_id)

        strategy_results: list[dict[str, Any]] = []
        for strategy_name in strategy_names:
            stock_rows = self._strategy_stock_rows(audits, strategy_name)
            decision = self._decide(stock_rows, policy_ids)
            selected_policy_id = decision.get("selected_policy_id")
            if decision.get("status") != "SELECTED":
                selected_for_hold = None if selected_policy_id == POLICY_TARGET1_FULL_EXIT.id else selected_policy_id
            else:
                selected_for_hold = selected_policy_id
            decision["strategy"] = strategy_name
            decision["regime_metrics"] = (
                {} if not selected_policy_id else _aggregate_regimes(stock_rows, str(selected_policy_id))
            )
            decision["max_hold_validation"] = _holding_policy_result(stock_rows, selected_for_hold)
            strategy_results.append(decision)

        markets = sorted({str(audit.get("market") or "").upper() for audit in audits if audit.get("market")})
        statuses: dict[str, int] = {}
        for row in strategy_results:
            status = str(row.get("status") or "UNKNOWN")
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "version": EXIT_POLICY_SELECTION_VERSION,
            "research_only": True,
            "selection_basis": SELECTION_BASIS,
            "production_policy_changed": False,
            "sample": {
                "stocks": len(audits),
                "markets": markets,
                "minimum_stock_count": self.config.minimum_stock_count,
                "minimum_total_trades": self.config.minimum_total_trades,
                "market_diversity_warning": len(markets) < 2,
            },
            "strategies": strategy_results,
            "status_counts": statuses,
            "guardrails": {
                "no_weighted_score": True,
                "insufficient_sample_fallback": POLICY_TARGET1_FULL_EXIT.id,
                "tradeoff_policy": "UNRESOLVED",
                "single_stock_dominance_policy": "UNRESOLVED",
                "production_integration_deferred_to": "v0.21.4-B.2",
            },
        }


def save_selection_report(report: dict[str, Any], path: Path | None = None) -> Path:
    target = path or (Path(__file__).resolve().parents[2] / "runtime" / "research" / "exit_policy_selection.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
