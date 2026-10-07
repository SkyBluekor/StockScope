from __future__ import annotations

from pathlib import Path
from typing import Any

from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
)

from .models import digest_json
from .review_identity import build_review_identity
from .review_models import (
    JEV_USER_FEATURE_ACTIVE,
    JEV_USER_FEATURE_DISABLED,
    REVIEW_ERROR,
    REVIEW_NOT_READY,
    REVIEW_PASS_THROUGH,
    REVIEW_QUEUED,
    REVIEW_REQUIRED,
    REVIEW_RUNNING,
    REVIEW_SKIPPED,
    REVIEW_UNAVAILABLE,
    JevManualReviewResult,
)
from .typesafe_catalog import TypeSafeJevCatalog, TypeSafeJevCatalogError
from .typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
)
from .typesafe_policy_v4 import JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4
from .typesafe_provider import TypeSafeJevProvider, TypeSafeJevProviderError
from .typesafe_questions_v4 import JEV_TYPESAFE_QUESTION_SET_HASH_V4
from .typesafe_service import build_system_one_request, review_once
from .typesafe_state import TypeSafeStateProjectionError
from .typesafe_state_v4 import route_typesafe_state_v4


class JevManualReviewService:
    """User-triggered V4 review boundary.

    Production remains disabled until a later validation/activation step.
    The only enabled path in this stage is dependency-injected fake-provider
    testing; no real provider is constructed here.
    """

    def __init__(
        self,
        simulation_db: Path,
        *,
        feature_status: str = JEV_USER_FEATURE_DISABLED,
        protocol: dict[str, Any] | None = None,
        provider_override: TypeSafeJevProvider | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.feature_status = str(feature_status or JEV_USER_FEATURE_DISABLED)
        self.protocol = dict(protocol) if isinstance(protocol, dict) else None
        self.provider_override = provider_override
        self.prospective = ProspectiveCatalog(self.simulation_db)
        self.typesafe = TypeSafeJevCatalog(self.simulation_db)

    @staticmethod
    def _baseline_reference(
        *,
        requested_capture_id: str,
        effective_capture_id: str | None,
        sample_index: int,
        snapshot_hash: str | None = None,
    ) -> dict[str, Any]:
        return {
            "requested_capture_id": requested_capture_id,
            "capture_id": effective_capture_id,
            "sample_index": int(sample_index),
            "snapshot_hash": snapshot_hash,
        }

    def _result(
        self,
        *,
        status: str,
        reason: str,
        baseline_reference: dict[str, Any],
        reused: bool = False,
        review_id: str | None = None,
        review_identity: str | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return JevManualReviewResult(
            status=status,
            reason=reason,
            reused=reused,
            baseline_reference=baseline_reference,
            review_id=review_id,
            review_identity=review_identity,
            feature_status=self.feature_status,
            reason_codes=reason_codes,
        ).to_dict()

    def _load_sample(
        self,
        capture_id: str,
        sample_index: int,
    ) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
        base = self._baseline_reference(
            requested_capture_id=capture_id,
            effective_capture_id=None,
            sample_index=sample_index,
        )
        try:
            capture = self.prospective.get_capture(capture_id)
        except ProspectiveCatalogError as exc:
            return None, base, exc.code
        if capture is None:
            return None, base, "CAPTURE_NOT_FOUND"

        status = str(capture.get("status") or "")
        effective_capture_id = (
            str(capture.get("canonical_capture_id") or "")
            if status == "DUPLICATE"
            else str(capture.get("id") or "")
        )
        if not effective_capture_id:
            return None, base, "CAPTURE_NOT_READY"
        base["capture_id"] = effective_capture_id

        if status not in {"COMPLETE", "DUPLICATE"}:
            return None, base, "CAPTURE_NOT_READY"

        try:
            samples = self.prospective.list_samples(
                capture_run_id=effective_capture_id
            )
        except ProspectiveCatalogError as exc:
            return None, base, exc.code

        sample = next(
            (
                item
                for item in samples
                if int(item.get("sample_index") or 0) == int(sample_index)
            ),
            None,
        )
        if sample is None:
            return None, base, "CAPTURE_SAMPLE_NOT_FOUND"

        base["snapshot_hash"] = str(sample.get("snapshot_hash") or "") or None
        return sample, base, None

    def _existing_result(
        self,
        *,
        recruitment: dict[str, Any],
        baseline_reference: dict[str, Any],
        review_identity: str,
    ) -> dict[str, Any]:
        review_id = str(recruitment.get("review_id") or "").strip() or None
        if review_id is None:
            return self._result(
                status=REVIEW_QUEUED,
                reason="DUPLICATE_REVIEW_REUSED",
                reused=True,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )

        review = self.typesafe.get_review(review_id)
        if review is None:
            return self._result(
                status=REVIEW_QUEUED,
                reason="DUPLICATE_REVIEW_REUSED",
                reused=True,
                baseline_reference=baseline_reference,
                review_id=review_id,
                review_identity=review_identity,
            )

        operational = str(review.get("status") or "")
        if operational == "PENDING":
            status = REVIEW_RUNNING
            reason = "DUPLICATE_REVIEW_REUSED"
        elif operational == "VALID":
            disposition = str(review.get("disposition") or "")
            status = (
                REVIEW_REQUIRED
                if disposition == REVIEW_REQUIRED
                else REVIEW_PASS_THROUGH
            )
            reason = "DUPLICATE_REVIEW_REUSED"
        elif operational == "SKIPPED":
            status = REVIEW_SKIPPED
            reason = str(review.get("failure_code") or "REVIEW_SKIPPED")
        else:
            status = REVIEW_ERROR
            reason = str(
                review.get("failure_code")
                or "PREVIOUS_REVIEW_NOT_REUSABLE"
            )

        return self._result(
            status=status,
            reason=reason,
            reused=True,
            baseline_reference=baseline_reference,
            review_id=review_id,
            review_identity=review_identity,
        )

    async def request_review(
        self,
        *,
        capture_id: str,
        sample_index: int = 0,
        review_epoch: int = 0,
    ) -> dict[str, Any]:
        clean_capture_id = str(capture_id or "").strip()
        if not clean_capture_id:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="CAPTURE_ID_REQUIRED",
                baseline_reference=self._baseline_reference(
                    requested_capture_id="",
                    effective_capture_id=None,
                    sample_index=sample_index,
                ),
            )
        if sample_index < 0 or review_epoch < 0:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="REVIEW_REQUEST_INVALID",
                baseline_reference=self._baseline_reference(
                    requested_capture_id=clean_capture_id,
                    effective_capture_id=None,
                    sample_index=sample_index,
                ),
            )

        baseline_reference = self._baseline_reference(
            requested_capture_id=clean_capture_id,
            effective_capture_id=None,
            sample_index=sample_index,
        )

        if self.feature_status != JEV_USER_FEATURE_ACTIVE:
            return self._result(
                status=REVIEW_UNAVAILABLE,
                reason="FEATURE_NOT_ACTIVATED",
                baseline_reference=baseline_reference,
            )

        sample, baseline_reference, load_error = self._load_sample(
            clean_capture_id,
            sample_index,
        )
        if sample is None:
            return self._result(
                status=REVIEW_NOT_READY,
                reason=load_error or "SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        snapshot = sample.get("snapshot")
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("semantic_source_v2"),
            dict,
        ):
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        try:
            route = route_typesafe_state_v4(sample)
        except TypeSafeStateProjectionError:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        if route.local_status == LOCAL_MATCH:
            return self._result(
                status=REVIEW_SKIPPED,
                reason="NO_RESIDUAL_SEMANTIC_REVIEW",
                baseline_reference=baseline_reference,
            )
        if route.local_status == LOCAL_CONFLICT:
            return self._result(
                status=REVIEW_SKIPPED,
                reason="LOCAL_CONFLICT_ALREADY_DETERMINED",
                baseline_reference=baseline_reference,
            )
        if route.local_status == LOCAL_INCOMPLETE:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )
        if route.local_status == LOCAL_AMBIGUOUS:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_AMBIGUOUS",
                baseline_reference=baseline_reference,
            )
        if route.local_status != RESIDUAL_SEMANTIC_REVIEW:
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        protocol = self.protocol
        if not isinstance(protocol, dict) or protocol.get("status") != "FROZEN":
            return self._result(
                status=REVIEW_UNAVAILABLE,
                reason="V4_PROTOCOL_NOT_READY",
                baseline_reference=baseline_reference,
            )
        spec = protocol.get("spec")
        if not isinstance(spec, dict):
            return self._result(
                status=REVIEW_UNAVAILABLE,
                reason="V4_PROTOCOL_NOT_READY",
                baseline_reference=baseline_reference,
            )
        if (
            spec.get("question_contract_version")
            != JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4
            or spec.get("disposition_policy_version")
            != JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4
        ):
            return self._result(
                status=REVIEW_UNAVAILABLE,
                reason="V4_PROTOCOL_NOT_READY",
                baseline_reference=baseline_reference,
            )
        if self.provider_override is None:
            return self._result(
                status=REVIEW_UNAVAILABLE,
                reason="PROVIDER_NOT_ACTIVATED",
                baseline_reference=baseline_reference,
            )

        source = snapshot["semantic_source_v2"]
        relations = source.get("relations")
        if not isinstance(relations, dict):
            return self._result(
                status=REVIEW_NOT_READY,
                reason="SEMANTIC_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        try:
            identity = build_review_identity(
                semantic_source_snapshot_hash=str(
                    source.get("source_snapshot_hash") or ""
                ),
                relation_contract_hash=str(
                    relations.get("relation_contract_hash") or ""
                ),
                question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH_V4,
                disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4,
                threshold_strategy=spec["threshold_strategy"],
                requested_model_channel=str(spec.get("model_requested") or ""),
                review_epoch=review_epoch,
            )
            request, projection = build_system_one_request(sample, spec)
        except (KeyError, TypeError, ValueError, TypeSafeStateProjectionError):
            return self._result(
                status=REVIEW_NOT_READY,
                reason="V4_PROTOCOL_OR_SOURCE_NOT_READY",
                baseline_reference=baseline_reference,
            )

        review_identity = str(identity["review_identity"])
        try:
            existing = self.typesafe.find_recruitment_by_analysis_unit_key(
                review_identity
            )
        except TypeSafeJevCatalogError as exc:
            return self._result(
                status=REVIEW_NOT_READY,
                reason=exc.code,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )
        if existing is not None:
            return self._existing_result(
                recruitment=existing,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )

        reservation = spec.get("per_call_reservation_usd")
        try:
            recruitment = self.typesafe.reserve_recruitment(
                protocol_id=str(protocol["id"]),
                capture_run_id=str(sample["capture_run_id"]),
                sample_index=int(sample["sample_index"]),
                analysis_unit_key=review_identity,
                candidate_snapshot_hash=str(sample.get("snapshot_hash") or ""),
                callable=True,
                reserved_cost_usd=float(reservation or 0.0),
            )
        except (KeyError, TypeError, ValueError, TypeSafeJevCatalogError) as exc:
            code = exc.code if isinstance(exc, TypeSafeJevCatalogError) else (
                "REVIEW_RESERVATION_FAILED"
            )
            return self._result(
                status=REVIEW_ERROR,
                reason=code,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )

        if recruitment.get("status") == "NOT_RECRUITED_LIMIT":
            return self._result(
                status=REVIEW_SKIPPED,
                reason="REVIEW_RECRUITMENT_LIMIT",
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )
        if not bool(recruitment.get("callable")):
            return self._result(
                status=REVIEW_SKIPPED,
                reason=str(recruitment.get("skip_reason") or "REVIEW_NOT_CALLABLE"),
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )
        if recruitment.get("review_id"):
            return self._existing_result(
                recruitment=recruitment,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )

        try:
            review_row = self.typesafe.begin_review(
                recruitment_id=str(recruitment["id"]),
                request_id=review_identity,
                state=projection.state,
                protocol=protocol,
                deadline_at=None,
            )
        except TypeSafeJevCatalogError as exc:
            return self._result(
                status=REVIEW_ERROR,
                reason=exc.code,
                baseline_reference=baseline_reference,
                review_identity=review_identity,
            )

        review_id = str(review_row["id"])
        try:
            reviewed = await review_once(
                sample,
                spec,
                self.provider_override,
            )
            normalized = reviewed.normalized_response
            completed = self.typesafe.complete_review(
                review_id,
                status="VALID",
                disposition=reviewed.disposition,
                uncertainty_reason=reviewed.uncertainty_reason,
                failure_code=None,
                model_returned=str(normalized.get("model") or ""),
                model_identity_status="MATCHED",
                typed_answers=dict(normalized.get("answers") or {}),
                raw_response_hash=digest_json(
                    {
                        "model": normalized.get("model"),
                        "answers": normalized.get("answers"),
                    }
                ),
                latency_ms=None,
                usage=dict(normalized.get("usage") or {}),
                cost_usd=reviewed.cost_usd,
                cost_unknown=reviewed.cost_unknown,
            )
        except (TypeSafeJevProviderError, ValueError) as exc:
            code = exc.code if isinstance(exc, TypeSafeJevProviderError) else (
                "JEV_V4_REVIEW_FAILED"
            )
            try:
                self.typesafe.complete_review(
                    review_id,
                    status="ERROR",
                    disposition=None,
                    uncertainty_reason=None,
                    failure_code=code,
                    model_returned=None,
                    model_identity_status="ERROR",
                    typed_answers=None,
                    raw_response_hash=None,
                    latency_ms=None,
                    usage=None,
                    cost_usd=None,
                    cost_unknown=True,
                )
            except TypeSafeJevCatalogError:
                pass
            return self._result(
                status=REVIEW_ERROR,
                reason=code,
                baseline_reference=baseline_reference,
                review_id=review_id,
                review_identity=review_identity,
            )

        final_status = (
            REVIEW_REQUIRED
            if str(completed.get("disposition") or "") == REVIEW_REQUIRED
            else REVIEW_PASS_THROUGH
        )
        return self._result(
            status=final_status,
            reason="JEV_ADDITIONAL_REVIEW_COMPLETE",
            reused=False,
            baseline_reference=baseline_reference,
            review_id=review_id,
            review_identity=review_identity,
            reason_codes=tuple(reviewed.reason_codes),
        )
