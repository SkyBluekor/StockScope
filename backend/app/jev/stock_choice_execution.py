"""JEV-B3: verified-input, one-candidate Choice execution boundary.

No server-configured trusted evidence resolver exists in production yet: a
client rights checkbox, token or note cannot turn this into a live provider.
This service can execute with a separately verified server-side resolver,
an explicit signed one-use preview approval and an initialized Choice table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from .models import digest_json
from .scanner_shadow_s7 import load_frozen_candidates
from .decision_reviewer_offline import DecisionReviewContractError
from .stock_choice_catalog import StockChoiceCatalog, StockChoiceStorageError
from .stock_review_contract_v1 import (
    DEFAULT_MODEL, QUESTION_HASH, VERSION, QUESTION_SET, MAX_WIRE_BYTES,
    StockReviewContractError, validate_choice_response,
)
from .typesafe_provider import (
    TYPESAFE_SYSTEM_ONE_URL, TypeSafeJevProviderError, load_typesafe_jev_api_key,
)


_SECRET = secrets.token_bytes(32)  # restart revokes outstanding approvals
_ALLOWED = frozenset({"strategy_intent", "review_notes",
                      "internal_risk_rule_description", "horizon_intent"})
_SENSITIVE = ("bearer ", "authorization:", "jev_api_key", "krx_api_key",
              "dart_api_key", "naver_client_secret", "kis_app_secret")


class StockChoiceExecutionError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TrustedChoiceInput:
    """Created ONLY by a vetted server-side resolver, never from HTTP JSON.

    source_policy_ref denotes a reviewed field-level AI outbound permission.
    A string supplied by a browser is never sufficient evidence of rights.
    """
    scope: str
    source_policy_ref: str
    observed_at_utc: str
    authored_for_capture: str
    authored_for_sample: int
    authored_for_snapshot: str
    fields: Mapping[str, str]


TrustedResolver = Callable[[dict[str, Any], dict[str, Any]], TrustedChoiceInput | None]


def unavailable_resolver(_capture: dict[str, Any],
                         _sample: dict[str, Any]) -> None:
    """No rights or time attestation exists for production market data yet."""
    return None


def _utc(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise StockChoiceExecutionError("CHOICE_TIME_INVALID") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise StockChoiceExecutionError("CHOICE_TIME_INVALID")
    if value.utcoffset().total_seconds() != 0:
        raise StockChoiceExecutionError("CHOICE_TIME_INVALID")
    return value.astimezone(timezone.utc)


def _token(identity: str, body_hash: str, deadline: int) -> str:
    material = json.dumps([identity, body_hash, deadline], separators=(",", ":")).encode()
    digest = hmac.new(_SECRET, material, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(material).decode().rstrip("=") + "." + digest


def _verify_token(value: str, identity: str, body_hash: str) -> None:
    if not isinstance(value, str) or len(value) > 750 or "." not in value:
        raise StockChoiceExecutionError("CHOICE_APPROVAL_REQUIRED")
    try:
        encoded, supplied = value.split(".", 1)
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        values = json.loads(raw)
        actual_identity, actual_hash, expiry = values
        expected = _token(actual_identity, actual_hash, expiry)
        valid = (type(expiry) is int and expiry >= int(datetime.now(timezone.utc).timestamp())
                 and expiry <= int(datetime.now(timezone.utc).timestamp()) + 300
                 and actual_identity == identity and actual_hash == body_hash
                 and hmac.compare_digest(expected, value))
    except (ValueError, TypeError, UnicodeError, OverflowError, binascii.Error):
        valid = False
    if not valid:
        raise StockChoiceExecutionError("CHOICE_APPROVAL_INVALID_OR_EXPIRED")


def _prepare_request(identity: dict[str, Any], evidence: TrustedChoiceInput,
                     *, model_id: str) -> dict[str, Any]:
    if not isinstance(evidence, TrustedChoiceInput) or evidence.scope != "VERIFIED_STOCK_CHOICE_AI_TRANSFER_V1":
        raise StockChoiceExecutionError("CHOICE_SOURCE_RIGHTS_UNVERIFIED")
    if (not isinstance(evidence.source_policy_ref, str)
            or len(evidence.source_policy_ref) < 12
            or evidence.source_policy_ref.startswith("CLIENT_")):
        raise StockChoiceExecutionError("CHOICE_SOURCE_RIGHTS_UNVERIFIED")
    if (evidence.authored_for_capture != identity["capture_id"]
            or evidence.authored_for_sample != identity["sample_index"]
            or evidence.authored_for_snapshot != identity["snapshot_hash"]):
        raise StockChoiceExecutionError("CHOICE_SOURCE_BINDING_MISMATCH")
    observed = _utc(evidence.observed_at_utc)
    if observed > datetime.now(timezone.utc):
        raise StockChoiceExecutionError("CHOICE_FUTURE_EVIDENCE")
    # This is a current review, not an attempt to recreate a past decision.
    fields = evidence.fields
    if not isinstance(fields, Mapping) or set(fields) != _ALLOWED:
        raise StockChoiceExecutionError("CHOICE_FIELD_NOT_ALLOWLISTED")
    if (not isinstance(model_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", model_id)):
        raise StockChoiceExecutionError("CHOICE_MODEL_INVALID")
    state = {"review_scope": "AUTHORIZED_CURRENT_REVIEW_PRIORITY_V1"}
    for key in sorted(_ALLOWED):
        text = fields.get(key)
        if (not isinstance(text, str) or not text.strip() or len(text) > 640
                or any(fragment in text.lower() for fragment in _SENSITIVE)):
            raise StockChoiceExecutionError("CHOICE_TEXT_NOT_ELIGIBLE")
        state[key] = text
    if fields["horizon_intent"] not in {"SHORT", "MEDIUM", "LONG"}:
        raise StockChoiceExecutionError("CHOICE_HORIZON_INVALID")
    if fields["horizon_intent"] != identity["horizon_intent"]:
        raise StockChoiceExecutionError("CHOICE_HORIZON_BINDING_MISMATCH")
    body = {"state": state, "questions": QUESTION_SET, "model": model_id}
    wire = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL, json=body).content
    if len(wire) > MAX_WIRE_BYTES:
        raise StockChoiceExecutionError("CHOICE_WIRE_TOO_LARGE")
    body_hash = hashlib.sha256(wire).hexdigest()
    input_hash = digest_json({
        "state": state,
        "source_policy_ref": evidence.source_policy_ref,
        "source_observed_at_utc": evidence.observed_at_utc,
    })
    review_identity = digest_json({
        "contract_version": VERSION, "candidate": identity, "input_hash": input_hash,
        "question_hash": QUESTION_HASH, "model": model_id,
    })
    return {
        "request_body": body, "request_body_sha256": body_hash,
        "input_hash": input_hash, "review_identity": review_identity,
        "source_policy_ref_hash": hashlib.sha256(
            evidence.source_policy_ref.encode("utf-8")).hexdigest(),
    }


async def _post_choice(body: dict[str, Any], *, model_id: str,
                       transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    key = load_typesafe_jev_api_key()
    if not key:
        raise TypeSafeJevProviderError("JEV_API_KEY_MISSING")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0), transport=transport,
    ) as client:
        try:
            response = await client.post(
                TYPESAFE_SYSTEM_ONE_URL,
                json=body,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_NETWORK_ERROR") from exc
    if response.status_code == 401:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_AUTH_ERROR")
    if response.status_code == 402:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_INSUFFICIENT_CREDITS")
    if response.status_code == 422:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_REQUEST_REJECTED")
    if response.status_code == 429:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_RATE_LIMIT")
    if response.status_code >= 500:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_UNAVAILABLE")
    if response.status_code >= 400:
        raise TypeSafeJevProviderError("TYPESAFE_PROVIDER_REQUEST_REJECTED")
    try:
        payload = response.json()
    except ValueError as exc:
        raise TypeSafeJevProviderError("TYPESAFE_RESPONSE_INVALID_JSON") from exc
    return validate_choice_response(payload, expected_model=model_id)


class StockChoiceService:
    def __init__(self, db_path: Path, *, resolver: TrustedResolver = unavailable_resolver,
                 model_id: str = DEFAULT_MODEL,
                 transport: httpx.AsyncBaseTransport | None = None,
                 cost_policy: Any | None = None):
        self.db_path = Path(db_path)
        self.catalog = StockChoiceCatalog(self.db_path)
        self.resolver = resolver  # server trusted code dependency, never HTTP param
        self.model_id = model_id
        self.transport = transport
        self.cost_policy = cost_policy  # No implicit live privileges in B3 fixtures.

    def _candidate(self, capture_id: str, sample_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if (not isinstance(capture_id, str) or not 1 <= len(capture_id) <= 200
                or type(sample_index) is not int or not 0 <= sample_index <= 499):
            raise StockChoiceExecutionError("CHOICE_IDENTITY_INVALID")
        try:
            pairs = load_frozen_candidates(self.db_path, capture_id=capture_id, limit=500)
        except DecisionReviewContractError as exc:
            raise StockChoiceExecutionError(exc.code) from exc
        for capture, sample in pairs:
            if sample["sample_index"] == sample_index:
                return capture, sample
        raise StockChoiceExecutionError("CHOICE_SAMPLE_NOT_FOUND")

    @staticmethod
    def _identity(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
        return {
            "capture_id": capture["id"],
            "sample_index": sample["sample_index"],
            "market": sample["market"],
            "ticker": sample["ticker"],
            "snapshot_hash": sample["snapshot_hash"],
            "horizon_intent": capture["horizon_intent"],
        }

    def preflight(self, capture_id: str, sample_index: int) -> dict[str, Any]:
        capture, sample = self._candidate(capture_id, sample_index)
        identity = self._identity(capture, sample)
        base = {
            "version": VERSION, "candidate": identity, "status": "NOT_READY",
            "reason_code": "CHOICE_SOURCE_RIGHTS_UNVERIFIED",
            "approved_for_paid_call": False, "approved_for_market_decision": False,
            "model_requested": self.model_id,
            "question_scope": "ONE_FOLLOWUP_CHECK_ONLY",
            "real_model_calls": 0,
            "latest_review": None, "preview": None, "approval_token": None,
        }
        try:
            rows = self.catalog.get_for_candidate(
                capture_id=identity["capture_id"], sample_index=sample_index,
                snapshot_hash=identity["snapshot_hash"],
                market=identity["market"], ticker=identity["ticker"],
            )
            base["latest_review"] = rows[0] if rows else None
        except StockChoiceStorageError as exc:
            base["reason_code"] = exc.code
            return base
        try:
            evidence = self.resolver(capture, sample)
            if evidence is None:
                if self.cost_policy is not None:
                    base["reason_code"] = "B4_NOTE_NOT_REGISTERED"
                return base
            prepared = _prepare_request(identity, evidence, model_id=self.model_id)
            price_preview = (self.cost_policy.check(prepared, model=self.model_id)
                             if self.cost_policy is not None else None)
        except (StockChoiceExecutionError, StockChoiceStorageError) as exc:
            base["reason_code"] = exc.code
            return base
        deadline = int(datetime.now(timezone.utc).timestamp()) + 180
        base.update({
            "status": "PREVIEW_READY",
            "reason_code": "AWAITING_EXPLICIT_APPROVAL",
            "preview": {
                "state": prepared["request_body"]["state"],
                "request_body_sha256": prepared["request_body_sha256"],
                "review_identity": prepared["review_identity"],
                "question_hash": QUESTION_HASH,
                "input_hash": prepared["input_hash"],
                "model": self.model_id,
                "cost_status": "ESTIMATED" if price_preview is not None else "UNKNOWN",
                "cost_policy": price_preview,
                "expires_at_utc": datetime.fromtimestamp(
                    deadline, timezone.utc).isoformat(),
            },
            "approval_token": _token(prepared["review_identity"],
                                      prepared["request_body_sha256"], deadline),
        })
        return base

    async def execute_once(self, *, capture_id: str, sample_index: int,
                           approval_token: str, request_body_sha256: str,
                           explicit_approval: bool) -> dict[str, Any]:
        if explicit_approval is not True:
            raise StockChoiceExecutionError("CHOICE_EXPLICIT_APPROVAL_REQUIRED")
        capture, sample = self._candidate(capture_id, sample_index)
        identity = self._identity(capture, sample)
        evidence = self.resolver(capture, sample)
        if evidence is None:
            raise StockChoiceExecutionError("CHOICE_SOURCE_RIGHTS_UNVERIFIED")
        prepared = _prepare_request(identity, evidence, model_id=self.model_id)
        if self.cost_policy is not None:
            self.cost_policy.check(prepared, model=self.model_id)
        if not hmac.compare_digest(str(request_body_sha256), prepared["request_body_sha256"]):
            raise StockChoiceExecutionError("CHOICE_BODY_CHANGED_SINCE_PREVIEW")
        _verify_token(approval_token, prepared["review_identity"],
                      prepared["request_body_sha256"])
        saved, fresh = self.catalog.reserve(
            review_identity=prepared["review_identity"],
            candidate=identity,
            input_hash=prepared["input_hash"], question_hash=QUESTION_HASH,
            model_requested=self.model_id,
            request_body_sha256=prepared["request_body_sha256"],
            approval_digest=hashlib.sha256(approval_token.encode()).hexdigest(),
        )
        if not fresh:
            return {"status": saved["status"], "reused": True, "review": saved}
        # Reservation committed before network. No automatic retry even for
        # transport failures: a remote charge may already have happened.
        try:
            wire = httpx.Request("POST", TYPESAFE_SYSTEM_ONE_URL,
                                 json=prepared["request_body"]).content
            if hashlib.sha256(wire).hexdigest() != prepared["request_body_sha256"]:
                raise StockChoiceExecutionError("CHOICE_BODY_CHANGED_SINCE_PREVIEW")
            normalized = await _post_choice(
                prepared["request_body"], model_id=self.model_id,
                transport=self.transport,
            )
            estimated_cost, pricing_ref = (
                self.cost_policy.after_response(normalized["usage"]["input_tokens"])
                if self.cost_policy is not None else (None, None)
            )
        except (StockChoiceExecutionError, TypeSafeJevProviderError, StockReviewContractError) as exc:
            saved = self.catalog.finish(
                review_identity=prepared["review_identity"],
                result=None, error_code=exc.code,
            )
            return {"status": saved["status"], "reused": False, "review": saved}
        saved = self.catalog.finish(
            review_identity=prepared["review_identity"], result=normalized,
            cost_estimate_usd=estimated_cost, cost_basis_ref=pricing_ref,
        )
        return {"status": saved["status"], "reused": False, "review": saved}
