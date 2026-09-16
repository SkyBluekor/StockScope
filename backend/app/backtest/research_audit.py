from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.backtest.exit_policy_catalog import POLICY_TARGET1_FULL_EXIT
from app.backtest.exit_policy_selection import (
    ExitPolicySelectionConfig,
    ExitPolicySelector,
    _aggregate_policy,
    _extract_primitives,
)
from app.backtest.exit_policy_validation_runner import ExitPolicyValidationCheckpoint

RESEARCH_AUDIT_VERSION = "0.21.4-B.2.1.6"
AUDIT_REPORT_FILENAME = "exit_policy_validation_audit.json"
_FLOAT_TOLERANCE = 1e-8


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _same_number(left: Any, right: Any, tolerance: float = _FLOAT_TOLERANCE) -> bool:
    a = _number(left)
    b = _number(right)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance


def _strategy_lookup(audit: dict[str, Any], strategy_name: str) -> dict[str, Any] | None:
    return next(
        (row for row in audit.get("strategies", []) if str(row.get("strategy") or "") == strategy_name),
        None,
    )


def _stock_rows_for_strategy(audits: list[dict[str, Any]], strategy_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for audit in audits:
        strategy = _strategy_lookup(audit, strategy_name)
        if strategy is None:
            continue
        result.append(
            {
                "code": audit.get("code"),
                "market": audit.get("market"),
                "policies": strategy.get("policies") or [],
                "holding_policy_variants": strategy.get("holding_policy_variants") or [],
            }
        )
    return result


def _policy_lookup(strategy: dict[str, Any], policy_id: str) -> dict[str, Any] | None:
    return next(
        (row for row in strategy.get("policies", []) if str(row.get("policy_id") or "") == policy_id),
        None,
    )


def _decision_reason_code(decision: dict[str, Any]) -> str:
    status = str(decision.get("status") or "UNKNOWN")
    if status == "INSUFFICIENT_SAMPLE":
        return "INSUFFICIENT_SAMPLE"
    if status == "BASELINE_BETTER":
        return "BASELINE_NO_WORSE_THAN_ALL_ELIGIBLE_CANDIDATES"
    if status == "SELECTED":
        return "UNIQUE_PARETO_IMPROVER"
    if status == "UNRESOLVED":
        concentration = decision.get("stock_concentration") or {}
        if concentration.get("single_stock_dominant"):
            return "SINGLE_STOCK_DOMINANCE"
        reason = str(decision.get("reason") or "")
        if "여러 개" in reason:
            return "MULTIPLE_PARETO_CANDIDATES"
        return "METRIC_TRADEOFF"
    return "UNKNOWN"


def _status_label(status: str) -> str:
    return {
        "SELECTED": "새 기준 후보",
        "BASELINE_BETTER": "기존 기준 유지",
        "UNRESOLVED": "판단 보류",
        "INSUFFICIENT_SAMPLE": "표본 부족",
    }.get(status, status)


def _market_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        market = str(row.get("market") or "UNKNOWN").upper()
        counts[market] = counts.get(market, 0) + 1
    return counts


class ExitPolicyResearchAuditStore:
    def __init__(self, runtime_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or (Path(__file__).resolve().parents[2] / "runtime" / "research")

    def path(self) -> Path:
        return self.runtime_dir / AUDIT_REPORT_FILENAME

    def save(self, report: dict[str, Any]) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        path = self.path()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def load(self) -> dict[str, Any] | None:
        path = self.path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None


class ExitPolicyResearchAuditor:
    """Independent, local-only integrity review for the latest B.1.1 validation report.

    This layer does not fetch KRX data and never changes research/production policy.
    It replays aggregation and selection from the saved per-stock checkpoint, checks
    data coverage metadata, quantifies stock concentration, and performs leave-one-stock-out
    stability analysis. Full trade IDs are not persisted by B.1.1, so matched-entry equality
    is reported as a methodology limitation rather than guessed as PASS.
    """

    def __init__(
        self,
        checkpoint_store: ExitPolicyValidationCheckpoint | None = None,
        audit_store: ExitPolicyResearchAuditStore | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store or ExitPolicyValidationCheckpoint()
        self.audit_store = audit_store or ExitPolicyResearchAuditStore(self.checkpoint_store.runtime_dir)

    @staticmethod
    def _selection_config(report: dict[str, Any]) -> ExitPolicySelectionConfig:
        raw = report.get("validation_config") or {}
        return ExitPolicySelectionConfig(
            minimum_stock_count=max(2, _integer(raw.get("minimum_stock_count") or 3)),
            minimum_total_trades=max(10, _integer(raw.get("minimum_total_trades") or 30)),
        )

    @staticmethod
    def _coverage_check(report: dict[str, Any], audits: list[dict[str, Any]]) -> dict[str, Any]:
        config = report.get("validation_config") or {}
        minimum = _number(config.get("minimum_coverage_pct")) or 90.0
        selected = list(report.get("selected_stocks") or [])
        validated = list(report.get("validated_stocks") or [])
        excluded = list(report.get("excluded_stocks") or [])
        validated_keys = {
            f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').upper()}"
            for row in validated
        }
        audit_keys = {
            f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').upper()}"
            for row in audits
        }
        stock_rows: list[dict[str, Any]] = []
        low_coverage: list[str] = []
        for stock in selected:
            code = str(stock.get("code") or "")
            market = str(stock.get("market") or "").upper()
            coverage = _number(stock.get("coverage_pct"))
            if coverage is not None and coverage + 1e-9 < minimum:
                low_coverage.append(f"{market}:{code}")
            stock_rows.append(
                {
                    "code": code,
                    "market": market,
                    "coverage_pct": coverage,
                    "row_count": _integer(stock.get("row_count")),
                    "trading_days": _integer(stock.get("trading_days")),
                    "first_date": stock.get("first_date"),
                    "last_date": stock.get("last_date"),
                    "validated": f"{market}:{code}" in audit_keys,
                }
            )

        market_availability = report.get("market_availability") or {}
        market_rows: list[dict[str, Any]] = []
        index_coverage_failures: list[str] = []
        for market, availability in market_availability.items():
            index_coverage = _number((availability or {}).get("index_coverage_pct"))
            if index_coverage is not None and index_coverage + 1e-9 < minimum:
                index_coverage_failures.append(str(market))
            market_rows.append(
                {
                    "market": str(market),
                    "trading_days": _integer((availability or {}).get("trading_days")),
                    "index_days": _integer((availability or {}).get("index_days")),
                    "index_coverage_pct": index_coverage,
                }
            )

        missing_audits = sorted(validated_keys - audit_keys)
        status = "PASS"
        if low_coverage or index_coverage_failures or missing_audits:
            status = "FAIL"
        elif excluded:
            status = "PASS_WITH_NOTES"
        return {
            "status": status,
            "minimum_coverage_pct": minimum,
            "selected_stocks": len(selected),
            "validated_stocks": len(audits),
            "excluded_stocks": len(excluded),
            "market_counts": _market_counts(audits),
            "low_coverage_stocks": low_coverage,
            "index_coverage_failures": index_coverage_failures,
            "missing_checkpoint_audits": missing_audits,
            "stocks": stock_rows,
            "markets": market_rows,
        }

    @staticmethod
    def _aggregate_replay(report: dict[str, Any], audits: list[dict[str, Any]]) -> dict[str, Any]:
        mismatches: list[dict[str, Any]] = []
        checked = 0
        fields = (
            "trades",
            "win_rate_pct",
            "average_net_return_pct",
            "profit_factor",
            "median_max_drawdown_pct",
            "worst_max_drawdown_pct",
            "average_holding_days",
            "average_profit_giveback_pct_points",
        )
        for strategy_result in report.get("strategies", []) or []:
            strategy_name = str(strategy_result.get("strategy") or "")
            stock_rows = _stock_rows_for_strategy(audits, strategy_name)
            for reported_policy in strategy_result.get("policies", []) or []:
                policy_id = str(reported_policy.get("policy_id") or "")
                replayed = _aggregate_policy(stock_rows, policy_id)
                checked += 1
                if replayed is None:
                    mismatches.append(
                        {"strategy": strategy_name, "policy_id": policy_id, "field": "policy", "reported": "present", "replayed": None}
                    )
                    continue
                if _integer(replayed.get("stock_count")) != _integer(reported_policy.get("stock_count")):
                    mismatches.append(
                        {
                            "strategy": strategy_name,
                            "policy_id": policy_id,
                            "field": "stock_count",
                            "reported": reported_policy.get("stock_count"),
                            "replayed": replayed.get("stock_count"),
                        }
                    )
                reported_metrics = reported_policy.get("aggregate_metrics") or {}
                replayed_metrics = replayed.get("aggregate_metrics") or {}
                for field in fields:
                    if not _same_number(reported_metrics.get(field), replayed_metrics.get(field)):
                        mismatches.append(
                            {
                                "strategy": strategy_name,
                                "policy_id": policy_id,
                                "field": field,
                                "reported": reported_metrics.get(field),
                                "replayed": replayed_metrics.get(field),
                            }
                        )
        return {
            "status": "PASS" if not mismatches else "FAIL",
            "checked_policy_aggregates": checked,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:100],
            "basis": "저장된 종목별 additive primitives에서 Net/PF/보유기간/Giveback과 종목별 MDD 집계를 다시 계산",
        }

    @staticmethod
    def _decision_replay(report: dict[str, Any], audits: list[dict[str, Any]], config: ExitPolicySelectionConfig) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        selector = ExitPolicySelector(config)
        replayed = selector.run(audits)
        replay_by_strategy = {str(row.get("strategy") or ""): row for row in replayed.get("strategies", []) or []}
        mismatches: list[dict[str, Any]] = []
        traces: dict[str, dict[str, Any]] = {}
        for original in report.get("strategies", []) or []:
            strategy = str(original.get("strategy") or "")
            rerun = replay_by_strategy.get(strategy)
            if rerun is None:
                mismatches.append({"strategy": strategy, "field": "strategy", "reported": "present", "replayed": None})
                continue
            original_status = str(original.get("status") or "")
            replay_status = str(rerun.get("status") or "")
            original_policy = str(original.get("selected_policy_id") or "")
            replay_policy = str(rerun.get("selected_policy_id") or "")
            traces[strategy] = {
                "reported_status": original_status,
                "replayed_status": replay_status,
                "reported_policy_id": original_policy,
                "replayed_policy_id": replay_policy,
                "reason_code": _decision_reason_code(rerun),
                "reason": rerun.get("reason"),
            }
            if original_status != replay_status:
                mismatches.append({"strategy": strategy, "field": "status", "reported": original_status, "replayed": replay_status})
            if original_policy != replay_policy:
                mismatches.append({"strategy": strategy, "field": "selected_policy_id", "reported": original_policy, "replayed": replay_policy})

        summary = report.get("summary") or {}
        reported_counts = {
            "SELECTED": _integer(summary.get("selected")),
            "BASELINE_BETTER": _integer(summary.get("baseline_better")),
            "UNRESOLVED": _integer(summary.get("unresolved")),
            "INSUFFICIENT_SAMPLE": _integer(summary.get("insufficient_sample")),
        }
        replayed_counts = {key: _integer((replayed.get("status_counts") or {}).get(key)) for key in reported_counts}
        if reported_counts != replayed_counts:
            mismatches.append({
                "strategy": "__SUMMARY__",
                "field": "status_counts",
                "reported": reported_counts,
                "replayed": replayed_counts,
            })
        return (
            {
                "status": "PASS" if not mismatches else "FAIL",
                "mismatch_count": len(mismatches),
                "mismatches": mismatches,
                "selection_basis": replayed.get("selection_basis"),
            },
            traces,
        )

    @staticmethod
    def _leave_one_out(report: dict[str, Any], audits: list[dict[str, Any]], config: ExitPolicySelectionConfig) -> dict[str, dict[str, Any]]:
        original_by_strategy = {
            str(row.get("strategy") or ""): row for row in report.get("strategies", []) or []
        }
        if len(audits) <= 2:
            return {
                strategy: {
                    "status": "UNAVAILABLE",
                    "runs": 0,
                    "same_status": 0,
                    "same_policy": 0,
                    "same_status_pct": None,
                    "status_counts": {},
                    "unstable_removed_stocks": [],
                    "note": "종목 하나를 제외하면 선택 검증 최소 종목 수를 보장할 수 없어 실행하지 않았습니다.",
                }
                for strategy in original_by_strategy
            }

        selector = ExitPolicySelector(config)
        accumulator: dict[str, dict[str, Any]] = {
            strategy: {
                "runs": 0,
                "same_status": 0,
                "same_policy": 0,
                "status_counts": {},
                "unstable_removed_stocks": [],
            }
            for strategy in original_by_strategy
        }
        for removed_index, removed in enumerate(audits):
            subset = audits[:removed_index] + audits[removed_index + 1 :]
            replayed = selector.run(subset)
            replay_by_strategy = {str(row.get("strategy") or ""): row for row in replayed.get("strategies", []) or []}
            removed_key = f"{str(removed.get('market') or '').upper()}:{str(removed.get('code') or '').upper()}"
            for strategy, original in original_by_strategy.items():
                row = replay_by_strategy.get(strategy)
                if row is None:
                    continue
                target = accumulator[strategy]
                target["runs"] += 1
                status = str(row.get("status") or "UNKNOWN")
                target["status_counts"][status] = target["status_counts"].get(status, 0) + 1
                same_status = status == str(original.get("status") or "")
                same_policy = str(row.get("selected_policy_id") or "") == str(original.get("selected_policy_id") or "")
                target["same_status"] += int(same_status)
                target["same_policy"] += int(same_policy)
                if not same_status or not same_policy:
                    target["unstable_removed_stocks"].append(
                        {
                            "removed": removed_key,
                            "status": status,
                            "status_label": _status_label(status),
                            "selected_policy_id": row.get("selected_policy_id"),
                        }
                    )

        result: dict[str, dict[str, Any]] = {}
        for strategy, row in accumulator.items():
            runs = _integer(row.get("runs"))
            same_status = _integer(row.get("same_status"))
            result[strategy] = {
                **row,
                "status": "STABLE" if runs > 0 and same_status == runs else "SENSITIVE",
                "same_status_pct": None if runs <= 0 else round(same_status / runs * 100.0, 1),
            }
        return result

    @staticmethod
    def _entry_set_check(audits: list[dict[str, Any]], strategy_name: str) -> dict[str, Any]:
        divergent: list[dict[str, Any]] = []
        recent_trade_samples_checked = 0
        recent_trade_entry_mismatches = 0
        for audit in audits:
            strategy = _strategy_lookup(audit, strategy_name)
            if strategy is None:
                continue
            policies = list(strategy.get("policies") or [])
            signal_counts = {str(row.get("policy_id") or ""): _integer(row.get("signal_count")) for row in policies}
            trade_counts = {
                str(row.get("policy_id") or ""): _integer((row.get("metrics") or {}).get("trades")) for row in policies
            }
            if len(set(signal_counts.values())) > 1 or len(set(trade_counts.values())) > 1:
                divergent.append(
                    {
                        "code": audit.get("code"),
                        "market": audit.get("market"),
                        "signal_counts": signal_counts,
                        "trade_counts": trade_counts,
                    }
                )

            baseline = next((row for row in policies if row.get("policy_id") == POLICY_TARGET1_FULL_EXIT.id), None)
            if baseline is not None:
                baseline_entries = {str(row.get("entry_date")) for row in baseline.get("recent_trades", []) or []}
                for candidate in policies:
                    if candidate is baseline:
                        continue
                    candidate_entries = {str(row.get("entry_date")) for row in candidate.get("recent_trades", []) or []}
                    if baseline_entries or candidate_entries:
                        recent_trade_samples_checked += 1
                        if baseline_entries != candidate_entries:
                            recent_trade_entry_mismatches += 1

        return {
            "status": "POLICY_DEPENDENT" if divergent else "NO_COUNT_DIVERGENCE_DETECTED",
            "divergent_stock_count": len(divergent),
            "divergent_stocks": divergent[:20],
            "recent_trade_samples_checked": recent_trade_samples_checked,
            "recent_trade_entry_mismatches": recent_trade_entry_mismatches,
            "matched_entry_equality_proven": False,
            "note": (
                "정책별 종료 시점이 달라지면 occupied 기간이 달라져 후속 진입 기회도 달라질 수 있습니다. "
                "현재 저장 결과는 모든 거래 ID를 보존하지 않으므로 완전한 1:1 동일 진입 집합을 증명하지 않습니다."
            ),
        }

    @staticmethod
    def _guardrail_check(audits: list[dict[str, Any]]) -> dict[str, Any]:
        expected = {
            "entry_price_policy": "NEXT_TRADING_DAY_OPEN",
            "same_day_stop_target2_policy": "STOP_FIRST_CONSERVATIVE",
            "trailing_exit_confirmation": "DAILY_CLOSE",
            "protection_update_policy": "AFTER_CLOSE_FOR_NEXT_TRADING_DAY_ONLY",
            "protection_direction": "NON_DECREASING",
        }
        mismatches: list[dict[str, Any]] = []
        recent_protection_rows = 0
        recent_non_decreasing_failures = 0
        same_day_stop_samples = 0
        for audit in audits:
            config = audit.get("config") or {}
            for key, expected_value in expected.items():
                if config.get(key) != expected_value:
                    mismatches.append(
                        {
                            "code": audit.get("code"),
                            "market": audit.get("market"),
                            "field": key,
                            "expected": expected_value,
                            "actual": config.get(key),
                        }
                    )
            for strategy in audit.get("strategies", []) or []:
                for policy in strategy.get("policies", []) or []:
                    for trade in policy.get("recent_trades", []) or []:
                        if trade.get("exit_reason") == "STOP_SAME_DAY_PRIORITY":
                            same_day_stop_samples += 1
                        research = (trade.get("metadata") or {}).get("exit_policy_research") or {}
                        if research.get("trailing_activated"):
                            recent_protection_rows += 1
                            if research.get("protection_never_decreases") is not True:
                                recent_non_decreasing_failures += 1
        status = "PASS" if not mismatches and recent_non_decreasing_failures == 0 else "FAIL"
        return {
            "status": status,
            "config_mismatch_count": len(mismatches),
            "config_mismatches": mismatches[:50],
            "recent_trailing_trade_samples": recent_protection_rows,
            "recent_non_decreasing_failures": recent_non_decreasing_failures,
            "recent_same_day_stop_priority_samples": same_day_stop_samples,
            "scope": "저장된 연구 설정 전체 + 각 정책 최근 거래 표본의 보호선 메타데이터",
            "limitation": "B.1.1 저장 결과는 모든 거래 상세를 보존하지 않아 과거 20종목의 모든 봉을 이 단계에서 재시뮬레이션하지 않습니다.",
        }

    @staticmethod
    def _strategy_diagnostics(
        report: dict[str, Any],
        audits: list[dict[str, Any]],
        decision_traces: dict[str, dict[str, Any]],
        leave_one_out: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for row in report.get("strategies", []) or []:
            strategy_name = str(row.get("strategy") or "")
            baseline_policy_id = POLICY_TARGET1_FULL_EXIT.id
            contributions: list[dict[str, Any]] = []
            market_trades: dict[str, int] = {}
            total_trades = 0
            for audit in audits:
                strategy = _strategy_lookup(audit, strategy_name)
                if strategy is None:
                    continue
                baseline = _policy_lookup(strategy, baseline_policy_id)
                if baseline is None:
                    continue
                primitives = _extract_primitives(baseline)
                trades = int(primitives["trades"])
                if trades <= 0:
                    continue
                market = str(audit.get("market") or "UNKNOWN").upper()
                total_trades += trades
                market_trades[market] = market_trades.get(market, 0) + trades
                contributions.append(
                    {
                        "code": audit.get("code"),
                        "market": market,
                        "trades": trades,
                        "net_return_sum_pct": round(float(primitives["net_return_sum_pct"]), 6),
                    }
                )
            contributions.sort(key=lambda item: abs(float(item["net_return_sum_pct"])), reverse=True)
            total_abs = sum(abs(float(item["net_return_sum_pct"])) for item in contributions)
            top1_abs_share = None if total_abs <= 0 else round(abs(float(contributions[0]["net_return_sum_pct"])) / total_abs * 100.0, 1)
            top3_abs = sum(abs(float(item["net_return_sum_pct"])) for item in contributions[:3])
            top3_abs_share = None if total_abs <= 0 else round(top3_abs / total_abs * 100.0, 1)
            max_trade_share = None
            if total_trades > 0 and contributions:
                max_trade_share = round(max(int(item["trades"]) for item in contributions) / total_trades * 100.0, 1)

            regime_metrics = row.get("regime_metrics") or {}
            regime_total = sum(_integer((metrics or {}).get("trades")) for metrics in regime_metrics.values())
            regimes = [
                {
                    "regime": regime,
                    "trades": _integer((metrics or {}).get("trades")),
                    "share_pct": None if regime_total <= 0 else round(_integer((metrics or {}).get("trades")) / regime_total * 100.0, 1),
                    "average_net_return_pct": _number((metrics or {}).get("average_net_return_pct")),
                    "profit_factor": _number((metrics or {}).get("profit_factor")),
                }
                for regime, metrics in regime_metrics.items()
            ]
            results.append(
                {
                    "strategy": strategy_name,
                    "research_status": row.get("status"),
                    "research_status_label": _status_label(str(row.get("status") or "")),
                    "selected_policy_id": row.get("selected_policy_id"),
                    "decision_trace": decision_traces.get(strategy_name) or {},
                    "baseline_sample": {
                        "trades": total_trades,
                        "participating_stocks": len(contributions),
                        "market_trades": market_trades,
                        "largest_stock_trade_share_pct": max_trade_share,
                        "top1_abs_net_contribution_share_pct": top1_abs_share,
                        "top3_abs_net_contribution_share_pct": top3_abs_share,
                        "largest_contributors": contributions[:5],
                    },
                    "entry_set": ExitPolicyResearchAuditor._entry_set_check(audits, strategy_name),
                    "leave_one_out": leave_one_out.get(strategy_name) or {},
                    "regimes": regimes,
                }
            )
        return results

    def run(self) -> dict[str, Any]:
        validation_report = self.checkpoint_store.load_report()
        if validation_report is None:
            return {
                "version": RESEARCH_AUDIT_VERSION,
                "available": False,
                "status": "DATA_REQUIRED",
                "message": "먼저 매도 기준 비교 검증 결과를 만들어야 합니다.",
            }
        if validation_report.get("status") != "COMPLETED":
            return {
                "version": RESEARCH_AUDIT_VERSION,
                "available": False,
                "status": "DATA_REQUIRED",
                "validation_signature": validation_report.get("signature"),
                "message": "완료된 매도 기준 비교 결과가 없어 신뢰성 검증을 실행할 수 없습니다.",
            }

        signature = str(validation_report.get("signature") or "")
        checkpoint = self.checkpoint_store.load(signature)
        audits = list((checkpoint or {}).get("audits") or [])
        if not checkpoint or not audits:
            return {
                "version": RESEARCH_AUDIT_VERSION,
                "available": False,
                "status": "DATA_REQUIRED",
                "validation_signature": signature,
                "message": "연구 원자료가 저장된 중간 결과를 찾지 못했습니다. 같은 조건으로 연구를 다시 실행해야 신뢰성 검증이 가능합니다.",
            }

        config = self._selection_config(validation_report)
        coverage = self._coverage_check(validation_report, audits)
        aggregate_replay = self._aggregate_replay(validation_report, audits)
        decision_replay, decision_traces = self._decision_replay(validation_report, audits, config)
        leave_one_out = self._leave_one_out(validation_report, audits, config)
        guardrails = self._guardrail_check(audits)
        strategies = self._strategy_diagnostics(
            validation_report,
            audits,
            decision_traces,
            leave_one_out,
        )

        sensitive_strategies = [row["strategy"] for row in strategies if (row.get("leave_one_out") or {}).get("status") == "SENSITIVE"]
        policy_dependent_entries = [row["strategy"] for row in strategies if (row.get("entry_set") or {}).get("status") == "POLICY_DEPENDENT"]
        high_concentration = [
            row["strategy"]
            for row in strategies
            if _number((row.get("baseline_sample") or {}).get("top1_abs_net_contribution_share_pct")) is not None
            and float((row.get("baseline_sample") or {}).get("top1_abs_net_contribution_share_pct")) >= 50.0
        ]

        critical_checks = {
            "data_coverage": coverage.get("status") != "FAIL",
            "aggregate_replay": aggregate_replay.get("status") == "PASS",
            "decision_replay": decision_replay.get("status") == "PASS",
            "guardrails": guardrails.get("status") == "PASS",
        }
        critical_issues = [key for key, ok in critical_checks.items() if not ok]
        notes: list[str] = []
        if sensitive_strategies:
            notes.append(f"종목 하나를 제외했을 때 결론이 바뀌는 전략이 {len(sensitive_strategies)}개 있습니다.")
        if policy_dependent_entries:
            notes.append("매도 방식에 따라 보유기간이 달라져 후속 진입 기회도 달라질 수 있습니다. 완전히 동일한 거래쌍 비교는 아닙니다.")
        if high_concentration:
            notes.append(f"기존 기준의 절대 순손익 기여가 한 종목에 50% 이상 집중된 전략이 {len(high_concentration)}개 있습니다.")
        if (validation_report.get("sample") or {}).get("market_diversity_warning"):
            notes.append("검증 표본이 한 시장에만 포함되어 있습니다.")

        overall_status = "FAIL" if critical_issues else ("PASS_WITH_NOTES" if notes else "PASS")
        report = {
            "version": RESEARCH_AUDIT_VERSION,
            "available": True,
            "status": overall_status,
            "validation_signature": signature,
            "validation_period": validation_report.get("period"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "research_only": True,
            "production_policy_changed": False,
            "summary": {
                "critical_issue_count": len(critical_issues),
                "critical_issues": critical_issues,
                "note_count": len(notes),
                "notes": notes,
                "validated_stocks": len(audits),
                "strategy_count": len(strategies),
                "leave_one_out_sensitive_strategies": len(sensitive_strategies),
                "policy_dependent_entry_strategies": len(policy_dependent_entries),
                "high_concentration_strategies": len(high_concentration),
            },
            "checks": {
                "data_coverage": coverage,
                "aggregate_replay": aggregate_replay,
                "decision_replay": decision_replay,
                "guardrails": guardrails,
                "leave_one_out": {
                    "status": "PASS" if not sensitive_strategies else "PASS_WITH_NOTES",
                    "sensitive_strategies": sensitive_strategies,
                    "strategy_count": len(strategies),
                },
                "entry_set": {
                    "status": "INFORMATIONAL",
                    "policy_dependent_strategies": policy_dependent_entries,
                    "matched_entry_equality_proven": False,
                },
            },
            "strategies": strategies,
            "limitations": [
                "B.1.1 checkpoint는 모든 거래 상세가 아니라 정책별 집계 primitive와 최근 거래 일부만 보존합니다.",
                "따라서 Net/PF/보유기간/Giveback 집계와 전략 판정은 재현하지만 모든 개별 거래의 진입일/종료일을 1:1 재검산하지는 않습니다.",
                "종목 하나 제거 검증은 저장된 종목별 연구 결과를 다시 집계하는 방식이며 KRX 네트워크 요청을 하지 않습니다.",
                "이 검증은 현재 연구 결과의 일관성을 확인할 뿐 미래 성과를 보장하지 않습니다.",
            ],
        }
        saved = self.audit_store.save(report)
        report["report"] = {
            "saved": True,
            "filename": saved.name,
            "runtime_area": "backend/runtime/research",
        }
        return report
