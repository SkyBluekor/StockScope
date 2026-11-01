"""Stage B: one real, manually approved System One semantic check of user-owned text.

NOT a market-data/Scanner review. The stock and frozen Scanner snapshot bind
only the local persisted result; the TypeSafe wire holds just two user-authored
text fields and one fixed meaning question. No DART, Naver, KRX, quotes, scores,
or Scanner strategy snapshots are transmitted.

No network request is made without a dedicated execute POST and explicit
approval; one immutable result file is claimed before the paid request.
After a crash a pending claim remains non-retryable (unknown billing).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any

from app.prospective.catalog import ProspectiveCatalog, ProspectiveCatalogError
from .typesafe_provider import (
    TypeSafeSystemOneProvider, TypeSafeJevProviderError,
    load_typesafe_jev_api_key, validate_system_one_response,
)

VERSION = "JEV_USER_AUTHORED_MANUAL_B_V1"
QUESTION = "user_condition_conflict"
MODEL_ALIAS = "jev-latest"
CONFIRM_PHRASE = "유료 JEV 1회 실행"
QUESTIONS = {
    QUESTION: {
        "type": "noul",
        "instructions": (
            "Evaluate ONLY whether the user's own written observation explicitly "
            "contradicts the user's own stated mandatory condition. This is a "
            "semantic text consistency check, not a real-world stock assessment. "
            "Do not infer any market data, news, prices, company facts, future returns, "
            "investment suitability, or missing evidence. Do not make trading advice."
        ),
        "criteria": {
            "true": "The authored observation explicitly violates the authored mandatory condition and needs a human re-check.",
            "false": "The authored observation is consistent with, or does not explicitly violate, the authored mandatory condition.",
        },
    },
}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _time() -> str:
    return datetime.now(timezone.utc).isoformat()


class OwnedReviewError(ValueError):
    def __init__(self, code: str, *, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def _authored(value: str, kind: str) -> str:
    if not isinstance(value, str):
        raise OwnedReviewError("JEV_B_" + kind + "_REQUIRED")
    text = value.strip()
    if not 16 <= len(text) <= 500 or len(text.encode("utf-8")) > 1200:
        raise OwnedReviewError("JEV_B_" + kind + "_LENGTH_INVALID")
    if any(ord(c) < 32 and c not in "\n\t" for c in text) or (
        re.search(r"https?://|www\.|<script|api[_ -]?key|bearer\s+", text, re.I)
    ):
        raise OwnedReviewError("JEV_B_" + kind + "_UNSUPPORTED_INPUT")
    return text


def _capture_binding(
    db: Path, *, capture_id: str, sample_index: int, market: str, ticker: str,
) -> dict[str, Any]:
    if not db.is_file():
        raise OwnedReviewError("JEV_B_EXISTING_SCANNER_DB_REQUIRED")
    try:
        catalog = ProspectiveCatalog(db)
        capture = catalog.get_capture(capture_id)
        if not capture or capture.get("status") not in {"COMPLETE", "DUPLICATE"}:
            raise OwnedReviewError("JEV_B_CANONICAL_CAPTURE_REQUIRED")
        effective = capture["canonical_capture_id"] if capture["status"] == "DUPLICATE" else capture["id"]
        samples = catalog.list_samples(capture_run_id=effective)
    except ProspectiveCatalogError as exc:
        raise OwnedReviewError("JEV_B_SCANNER_DB_NOT_READY") from exc
    match = next((s for s in samples if s["sample_index"] == sample_index), None)
    if match is None or match["market"] != market or match["ticker"] != ticker:
        raise OwnedReviewError("JEV_B_SELECTED_STOCK_MISMATCH")
    snapshot_hash = str(match.get("snapshot_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash):
        raise OwnedReviewError("JEV_B_SNAPSHOT_INTEGRITY_UNVERIFIED")
    # Do not copy any sample market-data fields into the remote request.
    return {
        "capture_id": str(effective),
        "sample_index": int(sample_index),
        "snapshot_hash": snapshot_hash,
        "market": market, "ticker": ticker,
        "stock_name": str(match.get("name") or ticker),
    }


class OwnedReviewService:
    def __init__(self, db: Path, *, store_dir: Path | None = None,
                 provider_factory=None) -> None:
        self.db = Path(db)
        self.store_dir = Path(store_dir) if store_dir else self.db.parent / "jev_owned_review_b"
        self.provider_factory = provider_factory or (lambda model: TypeSafeSystemOneProvider(model_id=model))

    @staticmethod
    def ready() -> tuple[bool, str]:
        if os.getenv("STOCKSCOPE_JEV_B_ENABLE", "").strip() != "1":
            return False, "JEV_B_NOT_ENABLED"
        if not load_typesafe_jev_api_key():
            return False, "JEV_API_KEY_MISSING"
        return True, "READY"

    def prepare(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            index = data["sample_index"]
            if type(index) is not int or not 0 <= index <= 100:
                raise ValueError
            market = data["market"]
            ticker = data["ticker"]
            cap = data["capture_id"]
            if (not isinstance(cap, str) or len(cap) > 200 or
                    market not in {"KOSPI", "KOSDAQ"} or
                    not isinstance(ticker, str) or not re.fullmatch(r"\d{6}", ticker)):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise OwnedReviewError("JEV_B_REQUEST_IDENTITY_INVALID") from exc
        binding = _capture_binding(
            self.db, capture_id=cap, sample_index=index, market=market, ticker=ticker,
        )
        rule = _authored(data.get("required_condition"), "CONDITION")
        observation = _authored(data.get("observed_meaning"), "OBSERVATION")
        remote = {
            "state": {
                "authored_required_condition": rule,
                "authored_observation": observation,
            },
            "questions": QUESTIONS,
            "model": MODEL_ALIAS,
        }
        wire_hash = _hash(remote)
        source_hash = _hash({"required_condition": rule, "observed_meaning": observation})
        # Claim identity is PER STOCK PER CANONICAL CAPTURE, not per text.
        # Changing a sentence must never silently create a second paid call.
        claim_id = _hash({"version": VERSION, "binding": binding})
        prior = self.lookup(claim_id)
        if prior and (prior.get("wire_sha256") != wire_hash
                      or prior.get("input_sha256") != source_hash):
            raise OwnedReviewError("JEV_B_ONE_REVIEW_PER_STOCK_INPUT_LOCKED", http_status=409)
        allowed, reason = self.ready()
        return {
            "version": VERSION,
            "review_id": claim_id,
            "wire_sha256": wire_hash,
            "input_sha256": source_hash,
            "question_sha256": _hash(QUESTIONS),
            "model_requested": MODEL_ALIAS,
            "selected_stock": binding,
            "remote_input_scope": "USER_AUTHORED_TEXT_ONLY",
            "market_data_sent": False,
            "third_party_content_sent": False,
            "estimated_cost_usd": None,
            "cost_unknown": True,
            "ready": allowed,
            "reason": reason,
            "existing": prior,
            "_request": remote,  # INTERNAL: never return this field via HTTP
        }

    def _path(self, review_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", review_id):
            raise OwnedReviewError("JEV_B_REVIEW_ID_INVALID")
        return self.store_dir / (review_id + ".json")

    def lookup(self, review_id: str) -> dict[str, Any] | None:
        p = self._path(review_id)
        if not p.is_file():
            return None
        try:
            body = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise OwnedReviewError("JEV_B_STORED_RESULT_INVALID") from exc
        if (not isinstance(body, dict) or body.get("review_id") != review_id or
                body.get("version") != VERSION):
            raise OwnedReviewError("JEV_B_STORED_RESULT_INVALID")
        if body["status"] == "PENDING":
            return {**body, "status": "PENDING_OR_INTERRUPTED",
                    "reason": "JEV_B_BILLING_UNKNOWN_NO_AUTORETRY"}
        return body

    def latest(self, capture_id: str, sample_index: int, market: str, ticker: str) -> dict[str, Any] | None:
        binding = _capture_binding(
            self.db, capture_id=capture_id, sample_index=sample_index,
            market=market, ticker=ticker,
        )
        if not self.store_dir.is_dir():
            return None
        # Restricted to one local manually authorized review; bounded scan.
        records: list[dict[str, Any]] = []
        for p in list(self.store_dir.glob("*.json"))[:200]:
            if not re.fullmatch(r"[0-9a-f]{64}\.json", p.name):
                continue
            record = self.lookup(p.stem)
            if record and record.get("selected_stock") == binding:
                records.append(record)
        return max(records, key=lambda x: str(x.get("started_at") or "")) if records else None

    def _replace(self, review_id: str, value: dict[str, Any]) -> None:
        p = self._path(review_id)
        temp = p.with_name(p.name + "." + secrets.token_hex(8) + ".tmp")
        with temp.open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(p)

    async def execute(self, data: dict[str, Any], *,
                      preflight_sha256: str, explicit_confirm: str,
                      original_authored_attested: bool) -> dict[str, Any]:
        preview = self.prepare(data)
        if (not preview["ready"] or explicit_confirm != CONFIRM_PHRASE or
                original_authored_attested is not True or
                preflight_sha256 != preview["wire_sha256"]):
            raise OwnedReviewError("JEV_B_EXPLICIT_APPROVAL_OR_READINESS_REQUIRED", http_status=403)
        review_id = preview["review_id"]
        earlier = preview["existing"]
        if earlier is not None:
            return {**earlier, "reused": True}
        # The original capture was read before claiming; the network wire
        # includes NO snapshot, ticker, strategy price, news or fundamentals.
        self.store_dir.mkdir(parents=True, exist_ok=True)
        started = {
            "version": VERSION, "review_id": review_id,
            "selected_stock": preview["selected_stock"],
            "wire_sha256": preview["wire_sha256"],
            "input_sha256": preview["input_sha256"],
            "question_sha256": preview["question_sha256"],
            "model_requested": preview["model_requested"],
            "status": "PENDING", "started_at": _time(),
            "cost_usd": None, "cost_unknown": True,
            "real_provider_call_attempted": True,
        }
        try:
            with self._path(review_id).open("x", encoding="utf-8") as f:
                json.dump(started, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            return {**self.lookup(review_id), "reused": True}
        try:
            provider = self.provider_factory(MODEL_ALIAS)
            if type(provider) is not TypeSafeSystemOneProvider:
                raise OwnedReviewError("JEV_B_REAL_PROVIDER_REQUIRED")
            response = await provider.review(preview["_request"], deadline_seconds=12.0)
            checked = validate_system_one_response(
                response.raw_response, expected_question_ids=(QUESTION,),
            )
            concrete = checked["model"]
            if not (re.fullmatch(r"jev-[a-zA-Z0-9._-]{1,80}", concrete)
                    and "fake" not in concrete.lower()):
                raise OwnedReviewError("JEV_B_RETURNED_MODEL_INVALID")
            probability = checked["probabilities"][QUESTION]
            disposition = ("REVIEW_REQUIRED" if probability >= 0.7
                           else "PASS_THROUGH" if probability <= 0.3
                           else "ABSTAIN")
            final = {
                **started, "status": "VALID", "completed_at": _time(),
                "disposition": disposition,
                "model_returned": concrete,
                "answer_noul": probability,
                "response_sha256": _hash({
                    "model": checked["model"], "answers": checked["answers"],
                }),
                "usage": checked["usage"],
                "cost_usd": response.cost_usd,
                "cost_unknown": response.cost_unknown,
                "reused": False,
            }
        except (TypeSafeJevProviderError, OwnedReviewError, ValueError) as exc:
            final = {**started, "status": "ERROR", "completed_at": _time(),
                     "reason": getattr(exc, "code", "JEV_B_PROVIDER_VALIDATION_FAILED"),
                     "reused": False}
        self._replace(review_id, final)
        return final
