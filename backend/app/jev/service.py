from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .catalog import JevCatalog, JevCatalogError
from .models import (
    JEV_ADAPTER_VERSION,
    JEV_COMPARISON_POLICY,
    JEV_DECISIONS,
    JEV_INPUT_CONTRACT_VERSION,
    JEV_MODEL_ABSTAIN_REASONS,
    JEV_OUTPUT_CONTRACT_VERSION,
    JEV_REASON_CODES,
    digest_json,
)
from .provider import JevProvider, JevProviderError, provider_from_protocol


_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _simple_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            _simple_value(item)
            for item in value
            if isinstance(item, (str, int, float, bool))
        ]
    return None


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    result: dict[str, Any] = {}
    for key in keys:
        if key not in source:
            continue
        value = _simple_value(source.get(key))
        if value is not None or source.get(key) is None:
            result[key] = value
    return result


class JevOutputValidationError(RuntimeError):
    pass


class JevShadowService:
    def __init__(
        self,
        simulation_db: Path,
        *,
        provider_override: JevProvider | None = None,
    ) -> None:
        self.catalog = JevCatalog(simulation_db)
        self.provider_override = provider_override

    @staticmethod
    def _candidate_ref(sample: dict[str, Any]) -> str:
        return (
            f"{sample['capture_run_id']}:{int(sample['sample_index'])}:"
            f"{sample.get('market') or ''}:{sample.get('ticker') or ''}"
        )

    @staticmethod
    def _analysis_unit_key(payload: dict[str, Any]) -> tuple[str, ...]:
        baseline = payload.get("baseline_decision")
        identity = payload.get("baseline_identity")
        as_of = payload.get("as_of")
        candidate_ref = str(payload.get("candidate_ref") or "")
        parts = candidate_ref.split(":")
        market = parts[-2] if len(parts) >= 2 else ""
        ticker = parts[-1] if len(parts) >= 1 else ""
        return (
            market,
            ticker,
            str(as_of.get("signal_date") or "") if isinstance(as_of, dict) else "",
            str(baseline.get("strategy_version_id") or "")
            if isinstance(baseline, dict)
            else "",
            str(identity.get("horizon_intent") or "")
            if isinstance(identity, dict)
            else "",
        )

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _scope_reason(
        sample: dict[str, Any],
        spec: dict[str, Any],
    ) -> str | None:
        if str(sample.get("capture_status") or "") != "COMPLETE":
            return "CAPTURE_NOT_COMPLETE"
        if str(sample.get("action") or "") != "ENTRY_CANDIDATE":
            return "OUT_OF_SCOPE_ACTION"
        market_scope = str(spec.get("market_scope") or "ALL").upper()
        if (
            market_scope != "ALL"
            and str(sample.get("market") or "").upper() != market_scope
        ):
            return "OUT_OF_SCOPE_MARKET"
        strategy = str(spec.get("strategy") or "").strip()
        if strategy and str(sample.get("strategy") or "") != strategy:
            return "OUT_OF_SCOPE_STRATEGY"
        horizons = {
            str(item)
            for item in (spec.get("horizon_intents") or [])
            if str(item)
        }
        if horizons and str(sample.get("horizon_intent") or "") not in horizons:
            return "OUT_OF_SCOPE_HORIZON"
        return None

    @staticmethod
    def _entry_guide(snapshot: dict[str, Any]) -> dict[str, Any]:
        guide = snapshot.get("entry_risk_guide")
        if not isinstance(guide, dict):
            return {}
        return {
            "current_price": _simple_value(guide.get("current_price")),
            "price_rule": _pick(
                guide.get("price_rule"),
                (
                    "kind",
                    "status",
                    "range_low",
                    "range_high",
                    "trigger_price",
                    "reference_price",
                    "gap_pct",
                    "semantic_role",
                ),
            ),
            "risk": _pick(
                guide.get("risk"),
                (
                    "available",
                    "status",
                    "reference_only",
                    "entry_reference_price",
                    "structural_anchor",
                    "invalidation_price",
                    "stop_zone_low",
                    "stop_zone_high",
                    "target1_price",
                    "target2_price",
                    "risk_pct",
                    "reward1_pct",
                    "reward2_pct",
                    "rr1",
                    "rr2",
                    "structure_rating",
                    "needs_recheck",
                ),
            ),
            "action": _pick(guide.get("action"), ("status",)),
        }

    def _projection(
        self,
        sample: dict[str, Any],
        protocol: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        scope_reason = self._scope_reason(sample, protocol["spec"])
        if scope_reason:
            return None, scope_reason

        snapshot = dict(sample.get("snapshot") or {})
        conditions = _pick(
            snapshot.get("conditions"),
            ("passed", "total", "missing", "top_missing"),
        )
        risk = _pick(
            snapshot.get("risk"),
            ("status", "warning", "warnings"),
        )
        essential_missing: list[str] = []
        if not sample.get("scanner_version"):
            essential_missing.append("scanner_version")
        if not sample.get("input_fingerprint"):
            essential_missing.append("input_fingerprint")
        if not sample.get("signal_date"):
            essential_missing.append("signal_date")
        if not risk.get("status"):
            essential_missing.append("risk.status")
        if not conditions:
            essential_missing.append("conditions")
        if essential_missing:
            return None, "INSUFFICIENT_BASELINE_IDENTITY"

        capture_request = dict(sample.get("capture_request") or {})
        missing_evidence: list[str] = []
        for field_name, value in (
            ("strategy_version_id", snapshot.get("strategy_version_id")),
            ("strategy_definition_hash", snapshot.get("strategy_definition_hash")),
            ("selection_policy_id", capture_request.get("selection_policy_id")),
            ("selection_policy_hash", capture_request.get("selection_policy_hash")),
        ):
            if value in (None, ""):
                missing_evidence.append(field_name)

        candidate_ref = self._candidate_ref(sample)
        request_id = digest_json(
            {
                "candidate_ref": candidate_ref,
                "snapshot_hash": sample.get("snapshot_hash"),
                "protocol_id": protocol["id"],
                "protocol_hash": protocol["spec_hash"],
                "adapter_version": JEV_ADAPTER_VERSION,
            }
        )[:32]

        guide = self._entry_guide(snapshot)
        baseline_decision = {
            "action": str(sample.get("action") or ""),
            "candidate_state": sample.get("candidate_state"),
            "decision_status": sample.get("decision_status"),
            "rank": sample.get("rank"),
            "bucket": snapshot.get("bucket"),
            "strategy": sample.get("strategy"),
            "strategy_version_id": snapshot.get("strategy_version_id"),
            "strategy_definition_hash": snapshot.get("strategy_definition_hash"),
            "conditions": conditions,
            "risk": risk,
            "entry_risk_guide": guide,
        }

        available_at = sample.get("created_at") or sample.get("completed_at")
        evidence_specs = [
            (
                "E-CURRENT-PRICE",
                "Scanner",
                "entry_risk_guide.current_price",
                guide.get("current_price"),
            ),
            ("E-CONDITIONS", "Strategy", "conditions", conditions),
            ("E-RISK", "Risk", "risk", risk),
            (
                "E-ENTRY-RULE",
                "Strategy",
                "entry_risk_guide.price_rule",
                guide.get("price_rule"),
            ),
            (
                "E-RISK-GUIDE",
                "Risk",
                "entry_risk_guide.risk",
                guide.get("risk"),
            ),
        ]
        evidence_items = [
            {
                "evidence_id": evidence_id,
                "owner": owner,
                "field_path": field_path,
                "value": value,
                "source_ref": candidate_ref,
                "source_hash": sample.get("snapshot_hash"),
                "available_at": available_at,
                "limitations": [],
                "source_policy_ref": sample.get("scanner_baseline")
                or sample.get("scanner_version"),
            }
            for evidence_id, owner, field_path, value in evidence_specs
            if value not in (None, {}, [])
        ]

        base = {
            "schema_version": JEV_INPUT_CONTRACT_VERSION,
            "request_id": request_id,
            "evaluation_protocol_id": protocol["id"],
            "evaluation_protocol_hash": protocol["spec_hash"],
            "source_kind": "PROSPECTIVE_CAPTURE",
            "source_ref": str(sample["capture_run_id"]),
            "candidate_ref": candidate_ref,
            "as_of": {
                "signal_date": sample.get("signal_date"),
                "source_available_at": available_at,
                "cutoff": sample.get("signal_date"),
                "eod": True,
                "time_proof_status": "CAPTURED_SOURCE_IDENTITY",
            },
            "baseline_identity": {
                "scanner_version": sample.get("scanner_version"),
                "scanner_baseline": sample.get("scanner_baseline"),
                "input_fingerprint": sample.get("input_fingerprint"),
                "source_execution_key": sample.get("source_execution_key"),
                "source_snapshot_hash": sample.get("source_snapshot_hash"),
                "strategy_version_id": snapshot.get("strategy_version_id"),
                "strategy_definition_hash": snapshot.get(
                    "strategy_definition_hash"
                ),
                "selection_policy_id": capture_request.get("selection_policy_id"),
                "selection_policy_hash": capture_request.get(
                    "selection_policy_hash"
                ),
                "horizon_intent": sample.get("horizon_intent"),
                "horizon_policy_version": sample.get("horizon_policy_version"),
            },
            "baseline_decision": baseline_decision,
            "evidence_items": evidence_items,
            "allowed_decisions": [
                "PASS_THROUGH",
                "REVIEW_REQUIRED",
                "ABSTAIN",
            ],
            "missing_evidence": missing_evidence,
            "limitations": [
                "QUANT_ONLY_PHASE_1",
                "NO_NEWS",
                "NO_EVENT_EVIDENCE",
                "NO_MACRO_REFERENCE",
                "NO_HOLDINGS_OR_ACCOUNT",
                "NO_FUTURE_OUTCOME",
                "SHADOW_ONLY_NO_BASELINE_MUTATION",
            ],
            "adapter_version": JEV_ADAPTER_VERSION,
        }
        payload = {**base, "input_hash": digest_json(base)}
        return payload, None

    @staticmethod
    def _validate_reason(
        reason: Any,
        *,
        evidence_ids: set[str],
    ) -> dict[str, Any]:
        if not isinstance(reason, dict):
            raise JevOutputValidationError("reason must be an object")
        if set(reason) != {"code", "evidence_refs", "explanation"}:
            raise JevOutputValidationError("reason fields are invalid")
        code = str(reason.get("code") or "")
        if code not in JEV_REASON_CODES:
            raise JevOutputValidationError("reason code is invalid")
        refs = reason.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise JevOutputValidationError("reason evidence_refs are required")
        clean_refs = [str(item) for item in refs]
        if any(item not in evidence_ids for item in clean_refs):
            raise JevOutputValidationError("reason references unknown evidence")
        explanation = str(reason.get("explanation") or "").strip()
        if not explanation or len(explanation) > 600:
            raise JevOutputValidationError("reason explanation is invalid")
        return {
            "code": code,
            "evidence_refs": clean_refs,
            "explanation": explanation,
        }

    @classmethod
    def validate_output(
        cls,
        input_payload: dict[str, Any],
        raw: Any,
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise JevOutputValidationError("model output must be an object")
        required = {
            "decision",
            "abstain_reason",
            "supporting_reasons",
            "opposing_reasons",
        }
        if set(raw) != required:
            raise JevOutputValidationError("model output fields are invalid")
        decision = str(raw.get("decision") or "")
        if decision not in JEV_DECISIONS:
            raise JevOutputValidationError("decision is invalid")
        abstain_reason = raw.get("abstain_reason")
        if decision == "ABSTAIN":
            if str(abstain_reason or "") not in JEV_MODEL_ABSTAIN_REASONS:
                raise JevOutputValidationError("abstain_reason is invalid")
            abstain_reason = str(abstain_reason)
        elif abstain_reason is not None:
            raise JevOutputValidationError(
                "abstain_reason must be null for non-ABSTAIN decisions"
            )

        evidence_ids = {
            str(item.get("evidence_id"))
            for item in (input_payload.get("evidence_items") or [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        supporting_raw = raw.get("supporting_reasons")
        opposing_raw = raw.get("opposing_reasons")
        if not isinstance(supporting_raw, list) or not isinstance(opposing_raw, list):
            raise JevOutputValidationError("reason lists are required")
        supporting = [
            cls._validate_reason(item, evidence_ids=evidence_ids)
            for item in supporting_raw
        ]
        opposing = [
            cls._validate_reason(item, evidence_ids=evidence_ids)
            for item in opposing_raw
        ]
        if decision == "PASS_THROUGH" and not supporting:
            raise JevOutputValidationError(
                "PASS_THROUGH requires a supporting reason"
            )
        if decision == "REVIEW_REQUIRED" and not opposing:
            raise JevOutputValidationError(
                "REVIEW_REQUIRED requires an opposing reason"
            )
        return {
            "decision": decision,
            "abstain_reason": abstain_reason,
            "supporting_reasons": supporting,
            "opposing_reasons": opposing,
        }

    def enqueue_capture(self, capture_id: str) -> list[dict[str, Any]]:
        active = self.catalog.active_protocol()
        if active is None:
            return []
        protocol, activation = active
        rows = self.catalog.load_capture_candidates(capture_id)
        created: list[dict[str, Any]] = []
        spec = dict(protocol["spec"])
        deadline_seconds = max(
            0.1,
            float(spec.get("deadline_seconds") or 8.0),
        )
        existing_reviews = self.catalog.list_reviews(
            protocol_id=protocol["id"],
        )
        occupied_units = {
            self._analysis_unit_key(row["input"])
            for row in existing_reviews
            if row.get("status") != "SKIPPED"
        }
        recruited_count = sum(
            1
            for row in existing_reviews
            if row.get("status") != "SKIPPED"
        )
        spent_usd = sum(
            float(row.get("cost_usd") or 0.0)
            for row in existing_reviews
        )
        activation_at = self._parse_iso(
            activation.get("updated_at")
        )
        recruitment_days = int(
            spec.get("recruitment_duration_calendar_days") or 0
        )
        recruitment_end = (
            activation_at + timedelta(days=recruitment_days)
            if activation_at is not None and recruitment_days > 0
            else None
        )
        max_recruited = int(
            spec.get("max_recruited_candidates") or 0
        )
        budget_limit = float(
            spec.get("budget_limit_usd") or 0.0
        )

        for sample in rows:
            existing_same = next(
                (
                    row
                    for row in existing_reviews
                    if row.get("capture_run_id") == sample.get("capture_run_id")
                    and int(row.get("sample_index") or 0)
                    == int(sample.get("sample_index") or 0)
                ),
                None,
            )
            if existing_same is not None:
                created.append(existing_same)
                continue

            payload, skip_reason = self._projection(sample, protocol)
            candidate_ref = self._candidate_ref(sample)
            if payload is not None and str(
                spec.get("recruitment_mode") or ""
            ).upper() == "ACTIVATION_FORWARD":
                capture_time = self._parse_iso(
                    sample.get("completed_at") or sample.get("created_at")
                )
                if (
                    activation_at is not None
                    and capture_time is not None
                    and capture_time < activation_at
                ):
                    skip_reason = "PRE_ACTIVATION_CAPTURE"
                    payload = None
                elif (
                    recruitment_end is not None
                    and _now() > recruitment_end
                ):
                    skip_reason = "RECRUITMENT_WINDOW_CLOSED"
                    payload = None
            if payload is not None and max_recruited > 0:
                if recruited_count >= max_recruited:
                    skip_reason = "RECRUITMENT_CAP_REACHED"
                    payload = None
            if payload is not None and budget_limit > 0:
                if spent_usd >= budget_limit:
                    skip_reason = "TRIAL_BUDGET_EXHAUSTED"
                    payload = None
            if payload is not None:
                analysis_unit = self._analysis_unit_key(payload)
                if analysis_unit in occupied_units:
                    skip_reason = "DUPLICATE_OBSERVATION"
                    payload = None
            if payload is None:
                minimal = {
                    "schema_version": JEV_INPUT_CONTRACT_VERSION,
                    "request_id": digest_json(
                        {
                            "candidate_ref": candidate_ref,
                            "protocol": protocol["spec_hash"],
                            "skip_reason": skip_reason,
                        }
                    )[:32],
                    "evaluation_protocol_id": protocol["id"],
                    "evaluation_protocol_hash": protocol["spec_hash"],
                    "source_kind": "PROSPECTIVE_CAPTURE",
                    "source_ref": str(sample["capture_run_id"]),
                    "candidate_ref": candidate_ref,
                    "skip_reason": skip_reason,
                    "adapter_version": JEV_ADAPTER_VERSION,
                }
                minimal["input_hash"] = digest_json(minimal)
                idem = digest_json(
                    {
                        "capture_run_id": sample["capture_run_id"],
                        "sample_index": sample["sample_index"],
                        "snapshot_hash": sample["snapshot_hash"],
                        "protocol_hash": protocol["spec_hash"],
                        "input_hash": minimal["input_hash"],
                        "status": "SKIPPED",
                    }
                )
                created.append(
                    self.catalog.enqueue_review(
                        request_id=minimal["request_id"],
                        protocol=protocol,
                        capture_run_id=str(sample["capture_run_id"]),
                        sample_index=int(sample["sample_index"]),
                        candidate_ref=candidate_ref,
                        candidate_snapshot_hash=str(sample["snapshot_hash"]),
                        idempotency_key=idem,
                        input_payload=minimal,
                        deadline_at=None,
                        status="SKIPPED",
                        failure_code=skip_reason,
                    )
                )
                continue

            if (
                str(spec.get("provider_id") or "").upper() != "FAKE"
                and not bool(activation.get("allow_network"))
            ):
                skip_reason = "JEV_NETWORK_NOT_AUTHORIZED"
                idem = digest_json(
                    {
                        "capture_run_id": sample["capture_run_id"],
                        "sample_index": sample["sample_index"],
                        "snapshot_hash": sample["snapshot_hash"],
                        "protocol_hash": protocol["spec_hash"],
                        "input_hash": payload["input_hash"],
                        "status": "NETWORK_SKIPPED",
                    }
                )
                created.append(
                    self.catalog.enqueue_review(
                        request_id=str(payload["request_id"]),
                        protocol=protocol,
                        capture_run_id=str(sample["capture_run_id"]),
                        sample_index=int(sample["sample_index"]),
                        candidate_ref=candidate_ref,
                        candidate_snapshot_hash=str(sample["snapshot_hash"]),
                        idempotency_key=idem,
                        input_payload=payload,
                        deadline_at=None,
                        status="SKIPPED",
                        failure_code=skip_reason,
                    )
                )
                continue

            identity = {
                "capture_run_id": sample["capture_run_id"],
                "sample_index": sample["sample_index"],
                "snapshot_hash": sample["snapshot_hash"],
                "protocol_hash": protocol["spec_hash"],
                "input_hash": payload["input_hash"],
                "provider_id": spec.get("provider_id"),
                "model_id": spec.get("model_id"),
                "model_revision": spec.get("model_revision"),
                "prompt_version": spec.get("prompt_version"),
                "prompt_hash": spec.get("prompt_hash"),
                "output_contract": JEV_OUTPUT_CONTRACT_VERSION,
                "adapter_version": JEV_ADAPTER_VERSION,
                "comparison_policy": JEV_COMPARISON_POLICY,
            }
            requested = _now()
            review = self.catalog.enqueue_review(
                request_id=str(payload["request_id"]),
                protocol=protocol,
                capture_run_id=str(sample["capture_run_id"]),
                sample_index=int(sample["sample_index"]),
                candidate_ref=candidate_ref,
                candidate_snapshot_hash=str(sample["snapshot_hash"]),
                idempotency_key=digest_json(identity),
                input_payload=payload,
                deadline_at=_iso(
                    requested + timedelta(seconds=deadline_seconds)
                ),
                status="PENDING",
                requested_at=_iso(requested),
            )
            created.append(review)
            if review.get("status") != "SKIPPED":
                recruited_count += 1
                occupied_units.add(
                    self._analysis_unit_key(payload)
                )
        return created

    async def run_review(self, review_id: str) -> dict[str, Any]:
        review = self.catalog.get_review(review_id)
        if review is None:
            raise JevCatalogError(
                "JEV_REVIEW_NOT_FOUND",
                "JEV shadow review를 찾을 수 없습니다.",
            )
        if review["status"] != "PENDING":
            return review
        protocol = self.catalog.get_protocol(review["protocol_id"])
        active = self.catalog.active_protocol()
        if (
            protocol is None
            or active is None
            or active[0]["id"] != protocol["id"]
        ):
            return self._fail_review(
                review_id,
                "JEV_PROTOCOL_NOT_ACTIVE",
                0,
            )

        spec = dict(protocol["spec"])
        activation = active[1]
        if (
            str(spec.get("provider_id") or "").upper() != "FAKE"
            and protocol["status"] != "FROZEN"
        ):
            return self._fail_review(
                review_id,
                "JEV_PROTOCOL_UNFROZEN",
                0,
            )

        provider = self.provider_override
        if provider is None:
            try:
                provider = provider_from_protocol(
                    spec,
                    allow_network=bool(activation.get("allow_network")),
                )
            except JevProviderError as exc:
                return self._fail_review(review_id, exc.code, 0)

        deadline = max(
            0.1,
            float(spec.get("deadline_seconds") or 8.0),
        )
        started = perf_counter()
        try:
            provider_result = await asyncio.wait_for(
                provider.review(
                    review["input"],
                    deadline_seconds=deadline,
                ),
                timeout=deadline + 1.0,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            normalized = self.validate_output(
                review["input"],
                provider_result.raw_response,
            )
            status = (
                "LATE"
                if elapsed_ms > int(deadline * 1000)
                else "VALID"
            )
            return self.catalog.complete_review(
                review_id,
                status=status,
                decision=str(normalized["decision"]),
                abstain_reason=normalized["abstain_reason"],
                failure_code=(
                    "DEADLINE_EXCEEDED"
                    if status == "LATE"
                    else None
                ),
                normalized_response=normalized,
                raw_response_hash=digest_json(
                    provider_result.raw_response
                ),
                latency_ms=elapsed_ms,
                usage=provider_result.usage,
                cost_usd=provider_result.cost_usd,
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((perf_counter() - started) * 1000)
            failure_code = "PROVIDER_TIMEOUT"
        except JevOutputValidationError:
            elapsed_ms = int((perf_counter() - started) * 1000)
            failure_code = "OUTPUT_VALIDATION_ERROR"
        except JevProviderError as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            failure_code = exc.code
        except Exception:
            elapsed_ms = int((perf_counter() - started) * 1000)
            failure_code = "PROVIDER_FAILURE"

        return self._fail_review(
            review_id,
            failure_code,
            elapsed_ms,
        )

    def _fail_review(
        self,
        review_id: str,
        failure_code: str,
        latency_ms: int,
    ) -> dict[str, Any]:
        return self.catalog.complete_review(
            review_id,
            status="ERROR",
            decision="ABSTAIN",
            abstain_reason="MODEL_ERROR",
            failure_code=failure_code,
            normalized_response={
                "decision": "ABSTAIN",
                "abstain_reason": "MODEL_ERROR",
                "supporting_reasons": [],
                "opposing_reasons": [],
            },
            raw_response_hash=None,
            latency_ms=latency_ms,
            usage=None,
            cost_usd=None,
        )

    async def process_capture(
        self,
        capture_id: str,
    ) -> list[dict[str, Any]]:
        records = self.enqueue_capture(capture_id)
        result: list[dict[str, Any]] = []
        for row in records:
            if row["status"] == "PENDING":
                result.append(await self.run_review(row["id"]))
            else:
                result.append(row)
        return result

    def try_schedule_capture(self, capture_id: str) -> dict[str, Any]:
        try:
            active = self.catalog.active_protocol()
            if active is None:
                return {
                    "status": "DISABLED",
                    "capture_id": capture_id,
                    "message": (
                        "JEV Shadow는 명시적으로 활성화된 "
                        "trial protocol이 없습니다."
                    ),
                }
            records = self.enqueue_capture(capture_id)
            pending = [
                row
                for row in records
                if row["status"] == "PENDING"
            ]
            for row in pending:
                task = asyncio.create_task(
                    self.run_review(row["id"])
                )
                _BACKGROUND_TASKS.add(task)
                task.add_done_callback(_BACKGROUND_TASKS.discard)
            return {
                "status": (
                    "SCHEDULED"
                    if pending
                    else "NO_CALL"
                ),
                "capture_id": capture_id,
                "review_count": len(records),
                "pending_count": len(pending),
                "skipped_count": sum(
                    1
                    for row in records
                    if row["status"] == "SKIPPED"
                ),
                "baseline_mutated": False,
            }
        except JevCatalogError as exc:
            if exc.code in {
                "JEV_MIGRATION_REQUIRED",
                "JEV_SCHEMA_UNSUPPORTED",
            }:
                return {
                    "status": "NOT_READY",
                    "capture_id": capture_id,
                    "code": exc.code,
                }
            return {
                "status": "ERROR",
                "capture_id": capture_id,
                "code": exc.code,
                "baseline_mutated": False,
            }
        except Exception:
            return {
                "status": "ERROR",
                "capture_id": capture_id,
                "code": "JEV_SHADOW_SCHEDULE_FAILED",
                "baseline_mutated": False,
            }
