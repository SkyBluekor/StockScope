from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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
        if self.max_stocks < 2 or self.max_stocks > 60:
            raise ValueError("Exit 정책 검증 종목 수는 2~60개 범위여야 합니다.")
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

    def research_fingerprint_payload(self) -> dict[str, Any]:
        """Return research conditions that affect one stock's audit result.

        ``max_stocks`` is intentionally excluded so a 20-stock research run can be
        reused when the same conditions are expanded to 40/60 stocks.
        """
        payload = self.signature_payload()
        payload.pop("max_stocks", None)
        return payload

    def research_fingerprint(self) -> str:
        raw = json.dumps(self.research_fingerprint_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class ExitPolicyValidationCheckpoint:
    def __init__(self, runtime_dir: Path | None = None) -> None:
        self.runtime_dir = runtime_dir or (Path(__file__).resolve().parents[2] / "runtime" / "research")

    def checkpoint_path(self, signature: str) -> Path:
        return self.runtime_dir / f"exit_policy_validation_checkpoint_{signature}.json"

    def report_path(self) -> Path:
        return self.runtime_dir / "exit_policy_validation_report.json"

    def archived_report_path(self, signature: str) -> Path:
        return self.runtime_dir / f"exit_policy_validation_report_{signature}.json"

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

    @staticmethod
    def _fingerprint_from_saved_config(config: dict[str, Any]) -> str:
        payload = dict(config)
        payload.pop("max_stocks", None)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def load_reusable_audits(
        self,
        config: ExitPolicyValidationRunnerConfig,
        candidates: list[dict[str, Any]],
        *,
        exclude_signature: str | None = None,
    ) -> list[dict[str, Any]]:
        """Reuse stock audits from compatible sample checkpoints.

        Sample signatures include the whole selected stock list. Expanded validation
        therefore has a different checkpoint even when the research conditions are
        identical. This lookup reuses only per-stock audits whose conditions match
        exactly, so 20 -> 40 can calculate just the 20 newly added stocks.
        """
        wanted_order = [
            f"{str(row.get('market') or '').upper()}:{str(row.get('code') or '').upper()}"
            for row in candidates
        ]
        wanted = set(wanted_order)
        if not wanted:
            return []

        target_fingerprint = config.research_fingerprint()
        found: dict[str, dict[str, Any]] = {}
        paths = sorted(
            self.runtime_dir.glob("exit_policy_validation_checkpoint_*.json"),
            key=lambda item: item.stat().st_mtime if item.exists() else 0.0,
            reverse=True,
        )
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
                continue
            if exclude_signature and str(payload.get("signature") or "") == exclude_signature:
                continue
            saved_config = payload.get("config")
            if not isinstance(saved_config, dict):
                continue
            if self._fingerprint_from_saved_config(saved_config) != target_fingerprint:
                continue

            for audit in payload.get("audits") or []:
                if not isinstance(audit, dict):
                    continue
                key = f"{str(audit.get('market') or '').upper()}:{str(audit.get('code') or '').upper()}"
                if key in wanted and key not in found:
                    found[key] = audit
            if len(found) >= len(wanted):
                break

        return [found[key] for key in wanted_order if key in found]

    def clear(self, signature: str) -> None:
        path = self.checkpoint_path(signature)
        if path.exists():
            path.unlink()

    def archive_report(self, report: dict[str, Any]) -> Path | None:
        signature = str(report.get("signature") or "").strip()
        if not signature:
            return None
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        path = self.archived_report_path(signature)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def save_report(self, report: dict[str, Any]) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.archive_report(report)
        path = self.report_path()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    def load_report(self, signature: str | None = None) -> dict[str, Any] | None:
        path = self.archived_report_path(signature) if signature else self.report_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return lightweight metadata for archived research runs, newest first."""
        safe_limit = max(1, min(int(limit), 100))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        paths = sorted(
            self.runtime_dir.glob("exit_policy_validation_report_*.json"),
            key=lambda item: item.stat().st_mtime if item.exists() else 0.0,
            reverse=True,
        )
        latest_path = self.report_path()
        if latest_path.exists():
            paths.insert(0, latest_path)

        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                stat = path.stat()
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            signature = str(payload.get("signature") or "").strip()
            if not signature or signature in seen:
                continue
            seen.add(signature)
            validated = payload.get("validated_stocks") or payload.get("selected_stocks") or []
            sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
            expanded = payload.get("expanded_revalidation") if isinstance(payload.get("expanded_revalidation"), dict) else None
            count = len(validated) or int(sample.get("stocks") or 0)
            rows.append({
                "signature": signature,
                "status": str(payload.get("status") or ""),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "period": {
                    "start": str(period.get("start") or ""),
                    "end": str(period.get("end") or ""),
                },
                "stock_count": count,
                "max_holding_days": (payload.get("validation_config") or {}).get("max_holding_days") if isinstance(payload.get("validation_config"), dict) else None,
                "summary": {
                    "selected": int(summary.get("selected") or 0),
                    "baseline_better": int(summary.get("baseline_better") or 0),
                    "unresolved": int(summary.get("unresolved") or 0),
                    "insufficient_sample": int(summary.get("insufficient_sample") or 0),
                },
                "is_expanded": expanded is not None,
                "base_signature": str(expanded.get("base_signature") or "") if expanded else None,
                "expanded_from": int(expanded.get("base_stock_count") or 0) if expanded else None,
            })
            if len(rows) >= safe_limit:
                break
        return rows



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
