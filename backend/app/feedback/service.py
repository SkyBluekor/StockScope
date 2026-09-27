from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.backtest.jobs import BacktestJobManager

from .adapter import FeedbackAdapterError, FeedbackEvidenceAdapter
from .catalog import FeedbackCatalog, FeedbackCatalogError
from .models import EvidenceSelector, FeedbackEvidence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric(values: list[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "average_pct": round(sum(values) / len(values), 4) if values else None,
        "median_pct": round(float(statistics.median(values)), 4) if values else None,
    }


class FeedbackService:
    def __init__(
        self,
        simulation_db: Path,
        tracking_db: Path,
        *,
        job_manager: BacktestJobManager | None = None,
        clock=None,
    ) -> None:
        self.adapter = FeedbackEvidenceAdapter(
            simulation_db=simulation_db,
            tracking_db=tracking_db,
            job_manager=job_manager,
        )
        self.catalog = FeedbackCatalog(simulation_db)
        self.clock = clock or _now

    def evidence(self, selector: EvidenceSelector) -> dict[str, Any]:
        rows = self.adapter.resolve(selector)
        return {
            "selector": selector.normalized().to_dict(),
            "count": len(rows),
            "rows": [row.to_dict() for row in rows],
        }

    def create_cohort(
        self,
        *,
        client_request_id: str,
        name: str,
        selectors: list[EvidenceSelector],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not client_request_id.strip():
            raise FeedbackCatalogError(
                "FEEDBACK_IDEMPOTENCY_KEY_REQUIRED",
                "cohort 생성에는 client_request_id가 필요합니다.",
            )
        if not name.strip():
            raise FeedbackCatalogError(
                "FEEDBACK_COHORT_NAME_REQUIRED",
                "cohort 이름을 입력하세요.",
            )
        if not selectors:
            raise FeedbackCatalogError(
                "FEEDBACK_SOURCE_REQUIRED",
                "하나 이상의 평가 원본이 필요합니다.",
            )

        selector_results: list[dict[str, Any]] = []
        evidence: list[FeedbackEvidence] = []
        for selector in selectors:
            normalized = selector.normalized()
            try:
                resolved = self.adapter.resolve(normalized)
            except FeedbackAdapterError as exc:
                selector_results.append(
                    {
                        "source_type": normalized.source_type,
                        "source_id": normalized.source_id,
                        "selector": normalized.to_dict(),
                        "status": "ERROR",
                        "error_code": exc.code,
                        "error_message": exc.message,
                        "evidence_count": 0,
                    }
                )
                continue
            selector_results.append(
                {
                    "source_type": normalized.source_type,
                    "source_id": normalized.source_id,
                    "selector": normalized.to_dict(),
                    "status": "READY" if resolved else "EMPTY",
                    "error_code": None,
                    "error_message": None,
                    "evidence_count": len(resolved),
                }
            )
            evidence.extend(resolved)

        return self.catalog.create_cohort(
            client_request_id=client_request_id.strip(),
            name=name.strip(),
            filters=filters or {},
            selector_results=selector_results,
            evidence=evidence,
            created_at=self.clock(),
        )

    @staticmethod
    def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        evidence_rows = [item["evidence"] for item in rows]
        maturity = Counter(str(item["maturity_status"]) for item in evidence_rows)
        source_types = Counter(str(item["source_type"]) for item in evidence_rows)

        observation_5d = [
            float(item["metrics"]["return_5d"])
            for item in evidence_rows
            if item["metrics"].get("return_5d") is not None
        ]
        observation_10d = [
            float(item["metrics"]["return_10d"])
            for item in evidence_rows
            if item["metrics"].get("return_10d") is not None
        ]
        observation_20d = [
            float(item["metrics"]["return_20d"])
            for item in evidence_rows
            if item["metrics"].get("return_20d") is not None
        ]
        mfe = [
            float(item["metrics"]["mfe_pct"])
            for item in evidence_rows
            if item["metrics"].get("mfe_pct") is not None
            and item["maturity_status"] in {"MATURE", "MATURE_REALIZED"}
        ]
        mae = [
            float(item["metrics"]["mae_pct"])
            for item in evidence_rows
            if item["metrics"].get("mae_pct") is not None
            and item["maturity_status"] in {"MATURE", "MATURE_REALIZED"}
        ]
        realized_net = [
            float(item["metrics"]["net_return_pct"])
            for item in evidence_rows
            if item["maturity_status"] == "MATURE_REALIZED"
            and item["metrics"].get("net_return_pct") is not None
        ]
        realized_gross = [
            float(item["metrics"]["gross_return_pct"])
            for item in evidence_rows
            if item["maturity_status"] == "MATURE_REALIZED"
            and item["metrics"].get("gross_return_pct") is not None
        ]
        censored_mark = [
            float(item["metrics"]["mark_return_pct"])
            for item in evidence_rows
            if item["maturity_status"] == "CENSORED"
            and item["metrics"].get("mark_return_pct") is not None
        ]
        realized_count = len(realized_net)
        observation_samples = max(
            len(observation_5d),
            len(observation_10d),
            len(observation_20d),
        )
        metric_sample_count = max(realized_count, observation_samples)
        return {
            "comparison_key": rows[0]["comparison_key"],
            "comparison_dimensions": rows[0]["comparison_dimensions"],
            "member_count": len(rows),
            "source_types": dict(source_types),
            "maturity": dict(maturity),
            "metrics": {
                "return_5d": _metric(observation_5d),
                "return_10d": _metric(observation_10d),
                "return_20d": _metric(observation_20d),
                "mfe": _metric(mfe),
                "mae": _metric(mae),
                "realized_net_return": _metric(realized_net),
                "realized_gross_return": _metric(realized_gross),
                "censored_mark_return": _metric(censored_mark),
            },
            "metric_sample_count": metric_sample_count,
            "censored_is_realized_return": False,
        }

    def _summarize(self, cohort: dict[str, Any]) -> dict[str, Any]:
        members = cohort["members"]
        included = [
            item for item in members
            if item["inclusion_status"] == "INCLUDED"
        ]
        excluded = [
            item for item in members
            if item["inclusion_status"] != "INCLUDED"
        ]

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in included:
            groups[str(item["comparison_key"])].append(item)
        group_summaries = [
            self._group_summary(group_rows)
            for _, group_rows in sorted(groups.items(), key=lambda pair: pair[0])
        ]
        metric_samples = sum(
            int(group["metric_sample_count"])
            for group in group_summaries
        )

        maturity = Counter(
            str(item["evidence"]["maturity_status"])
            for item in included
        )
        source_types = Counter(
            str(item["source_type"])
            for item in members
        )
        exclusion_reasons = Counter(
            str(item["exclusion_reason"] or "UNSPECIFIED")
            for item in excluded
        )

        source_errors = [
            source for source in cohort["sources"]
            if source["status"] == "ERROR"
        ]
        if not included or metric_samples == 0:
            evidence_state = "INSUFFICIENT_EVIDENCE"
        else:
            evidence_state = "SAMPLE_SIZE_POLICY_UNDEFINED"

        return {
            "cohort_id": cohort["id"],
            "cohort_version": cohort["cohort_version"],
            "filters": cohort["filters"],
            "counts": {
                "source_selector_count": len(cohort["sources"]),
                "source_error_count": len(source_errors),
                "member_count": len(members),
                "included_count": len(included),
                "excluded_count": len(excluded),
                "comparison_group_count": len(group_summaries),
                "metric_sample_count": metric_samples,
            },
            "source_types": dict(source_types),
            "maturity": dict(maturity),
            "exclusion_reasons": dict(exclusion_reasons),
            "source_errors": source_errors,
            "comparison": {
                "groups": group_summaries,
                "cross_group_aggregation_allowed": False,
                "different_comparison_keys_are_not_merged": True,
            },
            "evidence_state": evidence_state,
            "minimum_sample_policy_defined": False,
            "performance_conclusion_allowed": False,
            "notes": [
                "Tracking 관찰, 가상 Execution, Backtest 결과는 계산 정의가 다르면 합산하지 않습니다.",
                "CENSORED는 실현손익 또는 0% 수익으로 계산하지 않습니다.",
                "Manual-only Tracking은 Scanner 성과 근거에서 제외됩니다.",
            ],
        }

    def verify_cohort_sources(self, cohort: dict[str, Any]) -> dict[str, Any]:
        states: list[dict[str, Any]] = []
        for ref in cohort["members"]:
            live = self.adapter.resolve_exact(
                source_type=ref["source_type"],
                source_id=ref["source_id"],
                source_item_id=ref["source_item_id"],
            )
            if live is None:
                state = "SOURCE_MISSING"
                current_hash = None
            elif live.source_hash != ref["source_hash"]:
                state = "SOURCE_CHANGED"
                current_hash = live.source_hash
            else:
                state = "MATCH"
                current_hash = live.source_hash
            states.append(
                {
                    "source_ref_id": ref["id"],
                    "source_type": ref["source_type"],
                    "source_id": ref["source_id"],
                    "source_item_id": ref["source_item_id"],
                    "stored_hash": ref["source_hash"],
                    "current_hash": current_hash,
                    "state": state,
                    "durability": ref["durability"],
                }
            )
        counts = Counter(item["state"] for item in states)
        return {
            "status": "MATCH" if not counts.get("SOURCE_MISSING") and not counts.get("SOURCE_CHANGED") else "SOURCE_INVALID",
            "counts": dict(counts),
            "sources": states,
        }

    def create_report(
        self,
        *,
        cohort_id: str,
        client_request_id: str,
    ) -> dict[str, Any]:
        if not client_request_id.strip():
            raise FeedbackCatalogError(
                "FEEDBACK_IDEMPOTENCY_KEY_REQUIRED",
                "report 생성에는 client_request_id가 필요합니다.",
            )
        cohort = self.catalog.get_cohort(cohort_id)
        verification = self.verify_cohort_sources(cohort)
        summary = self._summarize(cohort)
        summary["source_verification_at_creation"] = verification
        status = (
            "READY"
            if verification["status"] == "MATCH"
            else "SOURCE_INVALID"
        )
        report = self.catalog.create_report(
            cohort_id=cohort_id,
            client_request_id=client_request_id.strip(),
            summary=summary,
            source_set_hash=self.catalog.source_set_hash(cohort_id),
            status=status,
            created_at=self.clock(),
        )
        return self.get_report(report["id"])

    def get_report(self, report_id: str) -> dict[str, Any]:
        report = self.catalog.get_report(report_id)
        cohort = self.catalog.get_cohort(report["cohort_id"])
        current = self.verify_cohort_sources(cohort)
        payload = dict(report)
        payload["source_verification_current"] = current
        payload["effective_status"] = (
            report["status"]
            if current["status"] == "MATCH"
            else "SOURCE_INVALID"
        )
        payload["source_changed_or_missing"] = current["status"] != "MATCH"
        return payload

    def get_cohort(self, cohort_id: str) -> dict[str, Any]:
        cohort = self.catalog.get_cohort(cohort_id)
        cohort["source_verification"] = self.verify_cohort_sources(cohort)
        cohort["reports"] = self.catalog.list_reports(cohort_id)
        return cohort
