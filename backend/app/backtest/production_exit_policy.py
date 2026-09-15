from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.backtest.exit_policy_catalog import (
    POLICY_TARGET1_FULL_EXIT,
    PROFIT_PROTECTION_POLICY_IDS,
    policy_by_id,
)
from app.backtest.exit_policy_simulator import ExitPolicySimulator
from app.backtest.models import BacktestConfig, BacktestTrade
from app.strategy.models import StrategyName


PRODUCTION_EXIT_POLICY_VERSION = "EXIT_PRODUCTION_V2"
PRODUCTION_POLICY_SCHEMA_VERSION = 1
DEFAULT_POST_TARGET2_HORIZON_DAYS = 60
HOLDING_HARD_MAX = "HARD_MAX_HOLD"
HOLDING_TRAILING_HORIZON = "TRAILING_HORIZON_AFTER_TARGET2"


@dataclass(frozen=True, slots=True)
class ProductionExitPolicyResolution:
    strategy: str
    policy_id: str = POLICY_TARGET1_FULL_EXIT.id
    policy_version: str = PRODUCTION_EXIT_POLICY_VERSION
    holding_policy: str = "NOT_APPLICABLE"
    post_target2_horizon_days: int = DEFAULT_POST_TARGET2_HORIZON_DAYS
    policy_source: str = "SAFE_BASELINE_FALLBACK"
    research_status: str | None = None
    research_reason: str | None = None
    fallback_used: bool = True
    fallback_reason: str | None = "NO_VALIDATED_PRODUCTION_MAPPING"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductionExitPolicyRegistry:
    """Frozen production policy mapping generated from a completed B.1.1 report.

    Research reruns never mutate an existing production mapping. A missing mapping may
    be bootstrapped once from the latest completed validation report; after that only
    the explicit activate_from_latest_validation(force=True) path replaces it.
    """

    def __init__(self, runtime_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or (Path(__file__).resolve().parents[2] / "runtime" / "research")
        self.mapping_path = self.runtime_dir / "exit_policy_production.json"
        self.validation_report_path = self.runtime_dir / "exit_policy_validation_report.json"

    @staticmethod
    def _safe_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def load_mapping(self) -> dict[str, Any] | None:
        payload = self._safe_json(self.mapping_path)
        if payload is None:
            return None
        if payload.get("schema_version") != PRODUCTION_POLICY_SCHEMA_VERSION:
            return None
        if payload.get("policy_version") != PRODUCTION_EXIT_POLICY_VERSION:
            return None
        if not isinstance(payload.get("strategies"), dict):
            return None
        return payload

    def _build_mapping(self, report: dict[str, Any]) -> dict[str, Any]:
        if str(report.get("status") or "") != "COMPLETED":
            raise ValueError("완료된 Exit 정책 검증 리포트가 필요합니다.")
        validation_config = dict(report.get("validation_config") or {})
        horizon = int(validation_config.get("post_target2_research_days") or DEFAULT_POST_TARGET2_HORIZON_DAYS)
        horizon = max(1, min(240, horizon))
        strategies: dict[str, Any] = {}
        for row in report.get("strategies") or []:
            strategy = str(row.get("strategy") or "").strip()
            if not strategy:
                continue
            research_status = str(row.get("status") or "UNRESOLVED")
            selected_policy = str(row.get("selected_policy_id") or POLICY_TARGET1_FULL_EXIT.id)
            use_selected = research_status == "SELECTED" and selected_policy in PROFIT_PROTECTION_POLICY_IDS
            policy_id = selected_policy if use_selected else POLICY_TARGET1_FULL_EXIT.id
            hold_validation = dict(row.get("max_hold_validation") or {})
            if policy_id == POLICY_TARGET1_FULL_EXIT.id:
                holding_policy = "NOT_APPLICABLE"
            elif hold_validation.get("status") == "SELECTED" and hold_validation.get("selected") in {
                HOLDING_HARD_MAX,
                HOLDING_TRAILING_HORIZON,
            }:
                holding_policy = str(hold_validation["selected"])
            else:
                # Unresolved holding horizon stays conservative until separately proven.
                holding_policy = HOLDING_HARD_MAX
            strategies[strategy] = {
                "policy_id": policy_id,
                "holding_policy": holding_policy,
                "post_target2_horizon_days": horizon,
                "research_status": research_status,
                "research_reason": row.get("reason"),
                "fallback_used": policy_id == POLICY_TARGET1_FULL_EXIT.id and research_status != "BASELINE_BETTER",
                "fallback_reason": None if use_selected else (
                    "BASELINE_VALIDATED_BETTER" if research_status == "BASELINE_BETTER" else f"RESEARCH_{research_status}_FALLBACK"
                ),
            }
        return {
            "schema_version": PRODUCTION_POLICY_SCHEMA_VERSION,
            "policy_version": PRODUCTION_EXIT_POLICY_VERSION,
            "activation_source": "EXIT_POLICY_VALIDATION_REPORT",
            "validation_signature": report.get("signature"),
            "runner_version": report.get("runner_version"),
            "selection_version": report.get("version"),
            "validation_period": report.get("period"),
            "validation_config": validation_config,
            "production_policy_changed": any(
                row.get("policy_id") != POLICY_TARGET1_FULL_EXIT.id for row in strategies.values()
            ),
            "strategies": strategies,
        }

    def activate_from_latest_validation(self, *, force: bool = False) -> dict[str, Any]:
        existing = self.load_mapping()
        if existing is not None and not force:
            return existing
        report = self._safe_json(self.validation_report_path)
        if report is None:
            raise ValueError("Exit 정책 검증 리포트가 없습니다. B.1.1 검증을 먼저 실행하세요.")
        mapping = self._build_mapping(report)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temp = self.mapping_path.with_suffix(".tmp")
        temp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.mapping_path)
        return mapping

    def ensure_mapping(self) -> dict[str, Any] | None:
        existing = self.load_mapping()
        if existing is not None:
            return existing
        # B.2.1 itself is the explicit product-level approval. Freeze the first
        # completed B.1.1 result once, then never follow later research automatically.
        if self.validation_report_path.exists():
            try:
                return self.activate_from_latest_validation(force=False)
            except ValueError:
                return None
        return None

    def resolve(self, strategy: StrategyName | str) -> ProductionExitPolicyResolution:
        strategy_value = strategy.value if isinstance(strategy, StrategyName) else str(strategy)
        mapping = self.ensure_mapping()
        if mapping is None:
            return ProductionExitPolicyResolution(strategy=strategy_value)
        raw = (mapping.get("strategies") or {}).get(strategy_value)
        if not isinstance(raw, dict):
            return ProductionExitPolicyResolution(
                strategy=strategy_value,
                policy_source="PRODUCTION_MAPPING",
                fallback_reason="STRATEGY_NOT_IN_MAPPING",
            )
        policy_id = str(raw.get("policy_id") or POLICY_TARGET1_FULL_EXIT.id)
        if policy_id != POLICY_TARGET1_FULL_EXIT.id and policy_id not in PROFIT_PROTECTION_POLICY_IDS:
            policy_id = POLICY_TARGET1_FULL_EXIT.id
            invalid_fallback = True
        else:
            invalid_fallback = False
        holding = str(raw.get("holding_policy") or "NOT_APPLICABLE")
        if policy_id != POLICY_TARGET1_FULL_EXIT.id and holding not in {HOLDING_HARD_MAX, HOLDING_TRAILING_HORIZON}:
            holding = HOLDING_HARD_MAX
            invalid_fallback = True
        return ProductionExitPolicyResolution(
            strategy=strategy_value,
            policy_id=policy_id,
            holding_policy=holding,
            post_target2_horizon_days=max(1, min(240, int(raw.get("post_target2_horizon_days") or DEFAULT_POST_TARGET2_HORIZON_DAYS))),
            policy_source="VALIDATED_PRODUCTION_MAPPING",
            research_status=raw.get("research_status"),
            research_reason=raw.get("research_reason"),
            fallback_used=bool(raw.get("fallback_used")) or invalid_fallback,
            fallback_reason=("INVALID_POLICY_MAPPING" if invalid_fallback else raw.get("fallback_reason")),
        )

    def status(self) -> dict[str, Any]:
        mapping = self.ensure_mapping()
        return {
            "available": mapping is not None,
            "policy_version": PRODUCTION_EXIT_POLICY_VERSION,
            "mapping": mapping,
            "cache_token": self.cache_token(),
        }

    def cache_token(self) -> str:
        mapping = self.ensure_mapping()
        if mapping is None:
            return f"{PRODUCTION_EXIT_POLICY_VERSION}-baseline"
        raw = json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{PRODUCTION_EXIT_POLICY_VERSION}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


class ProductionExitPolicyEngine:
    def __init__(self, base: Any, registry: ProductionExitPolicyRegistry | None = None) -> None:
        self.base = base
        self.registry = registry or ProductionExitPolicyRegistry()
        self.simulator = ExitPolicySimulator(base)

    @staticmethod
    def historical_policy_metadata(resolution: ProductionExitPolicyResolution) -> dict[str, Any]:
        baseline = resolution.policy_id == POLICY_TARGET1_FULL_EXIT.id
        spec = policy_by_id(resolution.policy_id)
        return {
            "policy_id": resolution.policy_id,
            "policy_version": resolution.policy_version,
            "label": "1차 목표 도달 시 전량 종료" if baseline else spec.label,
            "target1_is_exit": baseline,
            "target2_included": not baseline,
            "target2_label": "2차 확장 목표",
            "holding_policy": resolution.holding_policy,
            "policy_source": resolution.policy_source,
            "fallback_used": resolution.fallback_used,
            "fallback_reason": resolution.fallback_reason,
        }

    @staticmethod
    def _annotate_baseline_trade(trade: BacktestTrade, resolution: ProductionExitPolicyResolution) -> None:
        trade.metadata = {
            **dict(trade.metadata or {}),
            "exit_policy": {
                **resolution.to_dict(),
                "target1_reached": str(trade.exit_reason).startswith("TARGET_1"),
                "target2_reached": False,
                "trailing_activated": False,
                "final_protection_price": None,
            },
        }

    def simulate_trade(
        self,
        *,
        signal: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        config: BacktestConfig,
        strategy: StrategyName,
    ) -> tuple[BacktestTrade | None, int | None, ProductionExitPolicyResolution]:
        resolution = self.registry.resolve(strategy)
        if resolution.policy_id == POLICY_TARGET1_FULL_EXIT.id:
            trade, exit_index = self.base._simulate_trade(  # noqa: SLF001 - exact approved baseline path
                signal=signal,
                stock_rows=stock_rows,
                config=config,
                research_only=False,
                strategy=strategy,
            )
            if trade is not None:
                self._annotate_baseline_trade(trade, resolution)
            return trade, exit_index, resolution

        spec = policy_by_id(resolution.policy_id)
        extend = resolution.holding_policy == HOLDING_TRAILING_HORIZON
        trade, exit_index = self.simulator.simulate_profit_protection_trade(
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            strategy=strategy,
            policy=spec,
            post_target2_days=resolution.post_target2_horizon_days,
            extend_after_target2=extend,
            research_only=False,
            metadata_key="exit_policy",
            metadata_version=resolution.policy_version,
            horizon_exit_reason="PRODUCTION_HORIZON_EXIT",
        )
        if trade is not None:
            details = dict((trade.metadata or {}).get("exit_policy") or {})
            details.update(resolution.to_dict())
            trade.metadata["exit_policy"] = details
            return trade, exit_index, resolution

        # A validated trailing policy still needs Target2 geometry. If an individual
        # historical signal cannot build it, retain the exact old Target1 baseline for
        # that trade instead of silently dropping the trade from Historical Evidence.
        baseline_resolution = ProductionExitPolicyResolution(
            strategy=resolution.strategy,
            policy_source=resolution.policy_source,
            research_status=resolution.research_status,
            research_reason=resolution.research_reason,
            fallback_used=True,
            fallback_reason="SELECTED_POLICY_UNUSABLE_FOR_TRADE",
        )
        trade, exit_index = self.base._simulate_trade(  # noqa: SLF001
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            research_only=False,
            strategy=strategy,
        )
        if trade is not None:
            self._annotate_baseline_trade(trade, baseline_resolution)
        return trade, exit_index, baseline_resolution


def production_policy_cache_token() -> str:
    return ProductionExitPolicyRegistry().cache_token()
