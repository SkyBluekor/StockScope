from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.backtest.exit_policy_selection import EXIT_POLICY_SELECTION_VERSION

VALIDATION_RUNNER_VERSION = "0.21.4-B.1.1"
CHECKPOINT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExitPolicyValidationRunnerConfig:
    start_date: str
    end_date: str
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    max_stocks: int = 20
    minimum_coverage_pct: float = 90.0
    initial_capital: float = 10_000_000
    max_holding_days: int = 20
    round_trip_cost_pct: float = 0.0
    minimum_stock_count: int = 3
    minimum_total_trades: int = 30
    post_target2_research_days: int = 60

    def validate(self) -> None:
        if not self.markets or any(market not in {"KOSPI", "KOSDAQ"} for market in self.markets):
            raise ValueError("검증 시장은 KOSPI/KOSDAQ 중 하나 이상이어야 합니다.")
        if self.max_stocks < 2 or self.max_stocks > 30:
            raise ValueError("Exit 정책 검증 종목 수는 2~30개 범위여야 합니다.")
        if self.minimum_coverage_pct < 50 or self.minimum_coverage_pct > 100:
            raise ValueError("로컬 데이터 최소 커버리지는 50~100% 범위여야 합니다.")
        if self.initial_capital <= 0:
            raise ValueError("초기 자본은 0보다 커야 합니다.")
        if self.max_holding_days < 1 or self.max_holding_days > 120:
            raise ValueError("최대 보유기간은 1~120 거래일 범위여야 합니다.")
        if self.round_trip_cost_pct < 0 or self.round_trip_cost_pct > 5:
            raise ValueError("왕복 비용률은 0~5% 범위여야 합니다.")
        if self.minimum_stock_count < 2 or self.minimum_stock_count > 30:
            raise ValueError("정책 선택 최소 종목 수는 2~30 범위여야 합니다.")
        if self.minimum_total_trades < 10 or self.minimum_total_trades > 10000:
            raise ValueError("정책 선택 최소 거래 수는 10~10000 범위여야 합니다.")
        if self.post_target2_research_days < 1 or self.post_target2_research_days > 240:
            raise ValueError("Target2 이후 연구 보유기간은 1~240 거래일 범위여야 합니다.")

    def signature_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["markets"] = list(self.markets)
        payload["runner_version"] = VALIDATION_RUNNER_VERSION
        payload["selection_version"] = EXIT_POLICY_SELECTION_VERSION
        return payload

    def signature(self) -> str:
        raw = json.dumps(self.signature_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class ExitPolicyValidationCheckpoint:
    def __init__(self, runtime_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or (Path(__file__).resolve().parents[2] / "runtime" / "research")

    def checkpoint_path(self, signature: str) -> Path:
        return self.runtime_dir / f"exit_policy_validation_checkpoint_{signature}.json"

    def report_path(self) -> Path:
        return self.runtime_dir / "exit_policy_validation_report.json"

    def load(self, signature: str) -> dict[str, Any] | None:
        path = self.checkpoint_path(signature)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION or payload.get("signature") != signature:
            return None
        return payload

    def save(self, signature: str, config: ExitPolicyValidationRunnerConfig, audits: list[dict[str, Any]]) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_path(signature)
        payload = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "runner_version": VALIDATION_RUNNER_VERSION,
            "selection_version": EXIT_POLICY_SELECTION_VERSION,
            "signature": signature,
            "config": config.signature_payload(),
            "completed_codes": [f"{row.get('market')}:{row.get('code')}" for row in audits],
            "audits": audits,
        }
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def clear(self, signature: str) -> None:
        path = self.checkpoint_path(signature)
        if path.exists():
            path.unlink()

    def save_report(self, report: dict[str, Any]) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_path()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def load_report(self) -> dict[str, Any] | None:
        path = self.report_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None



def validation_sample_signature(
    config: ExitPolicyValidationRunnerConfig,
    candidates: list[dict[str, Any]],
) -> str:
    sample = [f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').upper()}" for row in candidates]
    raw = config.signature() + "|" + ";".join(sample)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

def interleave_market_candidates(
    by_market: dict[str, list[dict[str, Any]]],
    markets: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    """Select local candidates without letting one market consume the whole sample."""
    queues = {market: list(by_market.get(market, [])) for market in markets}
    selected: list[dict[str, Any]] = []
    while len(selected) < limit:
        progressed = False
        for market in markets:
            queue = queues.get(market) or []
            if not queue:
                continue
            selected.append(queue.pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected
