"""JEV-ACT2-S5: consent-gated, SYNTHETIC-ONLY TypeSafe System One micro Canary.

TypeSafe System One returns typed probabilities/choices, NOT free-text evidence
citations. Never interpret those outputs as independently grounded explanations.
No credentials or networking on import; no Scanner, KRX, KIS, or actual capture
can enter this module. Approved real execution is deliberately NOT wired to UI.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import time
import sqlite3
from typing import Any

import httpx

from app.prospective.models import digest_json, canonical_json
from .decision_reviewer_offline import (
    INPUT_VERSION, OUTPUT_VERSION, DecisionReviewContractError,
    validate_decision_review_response,
)
from .typesafe_provider import (
    TYPESAFE_SYSTEM_ONE_URL, load_typesafe_jev_api_key,
)

MICRO_VERSION = "JEV_ACT2_S5_SYNTHETIC_MICRO_V1"
QUESTION_VERSION = "JEV_S5_TYPED_DECISION_CHOICE_V1"
CHOICE_NAME = "review_decision"
CHOICES = ("PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN")
PROVIDER_ID = "TYPESAFE_SYSTEM_ONE"
SYNTHETIC_SCOPE = "SYNTHETIC_ONLY"
# Provisional synthetic examples, never an assertion of profitability or a
# source for live stock prices. Gold labels are not transmitted to the model.
CASES = (
    {
        "id": "s5-consistent",
        "intent": "A momentum setup requires intact upward structure and participation.",
        "evidence": [
            ("condition-a", "Trend structure is intact and upward."),
            ("condition-b", "Participation supports the upward setup."),
            ("risk-a", "The synthetic risk gate reports READY without warnings."),
        ],
        "gold": "PASS_THROUGH",
    },
    {
        "id": "s5-condition-contradiction",
        "intent": "A breakout needs price strength and supportive participation.",
        "evidence": [
            ("condition-a", "The setup claims a breakout."),
            ("condition-b", "The synthetic participation indicator is explicitly falling."),
            ("risk-a", "The synthetic risk gate reports READY."),
        ],
        "gold": "REVIEW_REQUIRED",
    },
    {
        "id": "s5-risk-contradiction",
        "intent": "An entry setup must respect its risk restrictions.",
        "evidence": [
            ("condition-a", "Entry candidate is proposed."),
            ("risk-a", "Risk text states unresolved concentration conflict."),
            ("risk-b", "Risk metadata also says READY. The two statements conflict."),
        ],
        "gold": "REVIEW_REQUIRED",
    },
    {
        "id": "s5-insufficient-evidence",
        "intent": "A trend setup needs structure and participation confirmation.",
        "evidence": [
            ("condition-a", "Participation evidence is unavailable."),
            ("risk-a", "The risk gate reports READY but its basis is missing."),
        ],
        "gold": "ABSTAIN",
    },
    {
        "id": "s5-unresolved-ambiguity",
        "intent": "A range strategy requires a nontrending price structure.",
        "evidence": [
            ("condition-a", "One independent synthetic reading reports a stable range."),
            ("condition-b", "Another independent synthetic reading reports a trend break."),
            ("risk-a", "Neither reading has established precedence."),
        ],
        "gold": "ABSTAIN",
    },
)
_CASE_INDEX = {item["id"]: item for item in CASES}
CASE_SET_HASH = digest_json(CASES)
CHOICE_INSTRUCTION = (
    "Given only the synthetic strategy intent and evidence, choose one: "
    "PASS_THROUGH if supplied signals are coherent, REVIEW_REQUIRED if a "
    "material conflict appears, or ABSTAIN if relevant facts are insufficient "
    "or conflicting evidence cannot be resolved. Do not infer real-world data."
)
CHOICE_QUESTION = {
    "type": "choice",
    "instructions": CHOICE_INSTRUCTION,
    "criteria": {
        "PASS_THROUGH": "Evidence coherently supports the strategy and has no material conflict.",
        "REVIEW_REQUIRED": "Explicitly supplied material contradiction needs human recheck.",
        "ABSTAIN": "Necessary evidence is missing or contradictory claims cannot be resolved.",
    },
}
QUESTION_HASH = digest_json({"version": QUESTION_VERSION, "question": CHOICE_QUESTION})


def synthetic_case_ids() -> tuple[str, ...]:
    return tuple(sorted(_CASE_INDEX))


def synthetic_projection(case_id: str) -> dict[str, Any]:
    """Only immutable, internally authored fixtures; caller never supplies data."""
    case = _CASE_INDEX.get(case_id)
    if case is None:
        raise DecisionReviewContractError("S5_SYNTHETIC_CASE_NOT_REGISTERED")
    facts = [
        {
            "evidence_id": evidence_id,
            "owner": "SYNTHETIC_FIXTURE",
            "value": sentence,
            "source_ref": f"{MICRO_VERSION}:{case_id}",
        }
        for evidence_id, sentence in case["evidence"]
    ]
    body = {
        "schema_version": INPUT_VERSION,
        "source_kind": "SYNTHETIC_AUTHORED",
        "synthetic_contract": MICRO_VERSION,
        "synthetic_case_set_hash": CASE_SET_HASH,
        "case_id": case_id,
        "candidate_ref": {"synthetic_case_id": case_id},
        "baseline_decision": {"action": "ENTRY_CANDIDATE", "strategy_intent": case["intent"]},
        "evidence_items": facts,
        "limitations": ["SYNTHETIC_ONLY", "NO_MARKET_DATA", "NO_INVESTMENT_OUTCOME"],
        "allowed_decisions": list(CHOICES),
    }
    return {
        "status": "SYNTHETIC_ONLY",
        "input": {**body, "input_hash": digest_json(body)},
        "input_hash": digest_json(body),
        "real_market_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class FrozenMicroProtocol:
    """Cannot be activated with an alias or unknown price/account terms."""
    protocol_id: str
    model_requested: str
    model_returned: str
    max_attempts: int = 5
    per_attempt_reservation_usd: str = "0.01"
    total_budget_usd: str = "0.05"
    verified_input_usd_per_million: str | None = None
    verified_output_usd_per_million: str | None = None
    deadline_seconds: float = 5.0
    protocol_case_set_hash: str = CASE_SET_HASH
    question_hash: str = QUESTION_HASH
    retry_count: int = 0
    concurrency_cap: int = 1

    def validate(self) -> None:
        try:
            single = Decimal(self.per_attempt_reservation_usd)
            total = Decimal(self.total_budget_usd)
        except (ValueError, ArithmeticError) as exc:
            raise DecisionReviewContractError("S5_PROTOCOL_LIMIT_INVALID") from exc
        if not single.is_finite() or not total.is_finite():
            raise DecisionReviewContractError("S5_PROTOCOL_LIMIT_INVALID")
        if (
            not self.protocol_id.strip()
            or not self.model_requested.strip()
            or not self.model_returned.strip()
            or self.model_returned.upper() in {"UNFROZEN", "JEV-LATEST"}
            or not (1 <= self.max_attempts <= 10)
            or not (Decimal("0") < single <= Decimal("0.05"))
            or not (Decimal("0") < total <= Decimal("0.50"))
            or single * self.max_attempts > total
            or not (0.1 <= self.deadline_seconds <= 10)
            or self.retry_count != 0 or self.concurrency_cap != 1
            or self.protocol_case_set_hash != CASE_SET_HASH
            or self.question_hash != QUESTION_HASH
        ):
            raise DecisionReviewContractError("S5_PROTOCOL_LIMIT_INVALID")

    @property
    def identity_hash(self) -> str:
        self.validate()
        return digest_json(asdict(self))


@dataclass(frozen=True, slots=True)
class ActualTrialApproval:
    """External owner acknowledgement, never fabricated by this module."""
    approved_protocol_hash: str
    approved_case_set_hash: str
    approved_model: str
    approved_budget_usd: str
    owner_approved: bool = False
    provider_terms_confirmed: bool = False
    account_pricing_confirmed: bool = False
    model_catalog_confirmed: bool = False
    synthetic_only: bool = True
    explicit_trial_scope: str = ""

    def validate(self, protocol: FrozenMicroProtocol) -> None:
        protocol.validate()
        if (
            not self.owner_approved or not self.provider_terms_confirmed
            or not self.account_pricing_confirmed or not self.model_catalog_confirmed
            or not self.synthetic_only
            or self.explicit_trial_scope != "S5_APPROVED_SYNTHETIC_MICRO_CANARY"
            or self.approved_protocol_hash != protocol.identity_hash
            or self.approved_case_set_hash != CASE_SET_HASH
            or self.approved_model != protocol.model_returned
            or self.approved_budget_usd != protocol.total_budget_usd
        ):
            raise DecisionReviewContractError("S5_ACTUAL_TRIAL_NOT_APPROVED")
        for value in (
            protocol.verified_input_usd_per_million,
            protocol.verified_output_usd_per_million,
        ):
            try:
                price = Decimal(value) if value is not None else Decimal("-1")
                if not price.is_finite() or price < 0:
                    raise ValueError()
            except (ValueError, ArithmeticError) as exc:
                raise DecisionReviewContractError("S5_ACCOUNT_PRICE_UNVERIFIED") from exc


def _clean_choice_response(raw: dict[str, Any], protocol: FrozenMicroProtocol) -> dict[str, Any]:
    """Uses the vendor's actual typed CHOICE schema, not free-text JSON."""
    if not isinstance(raw, dict) or raw.get("model") != protocol.model_returned:
        raise DecisionReviewContractError("S5_RETURNED_MODEL_MISMATCH")
    answers = raw.get("answers")
    if not isinstance(answers, dict) or set(answers) != {CHOICE_NAME}:
        raise DecisionReviewContractError("S5_ANSWER_SET_INVALID")
    answer = answers[CHOICE_NAME]
    if not isinstance(answer, dict) or set(answer) != {"type", "choice", "confidence", "probabilities"}:
        raise DecisionReviewContractError("S5_CHOICE_SHAPE_INVALID")
    if answer["type"] != "choice" or answer["choice"] not in CHOICES:
        raise DecisionReviewContractError("S5_CHOICE_INVALID")
    probs = answer["probabilities"]
    if not isinstance(probs, dict) or set(probs) != set(CHOICES):
        raise DecisionReviewContractError("S5_CHOICE_PROBABILITIES_INVALID")
    values = list(probs.values())
    conf = answer["confidence"]
    if (
        any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values)
        or type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1
        or not 0.98 <= sum(values) <= 1.02
        or probs[answer["choice"]] != max(values)
    ):
        raise DecisionReviewContractError("S5_CHOICE_PROBABILITIES_INVALID")
    usage = raw.get("usage")
    if (
        not isinstance(usage, dict)
        or set(usage) != {"input_tokens", "output_tokens"}
        or any(type(v) is not int or v < 0 for v in usage.values())
    ):
        raise DecisionReviewContractError("S5_USAGE_INVALID")
    return {
        "decision": answer["choice"],
        "model": raw["model"],
        "confidence": float(conf),
        "probabilities": {k: float(v) for k, v in sorted(probs.items())},
        "usage": dict(usage),
    }


def _model_to_review(projection: dict[str, Any], choice: str) -> dict[str, Any]:
    # The vendor DOES NOT return citations or explanations. We attach a
    # deterministic explanation of the mapping, not falsely attribute it.
    refs = [e["evidence_id"] for e in projection["input"]["evidence_items"]]
    reason = {
        "code": "CONDITION_ALIGNMENT" if choice == "PASS_THROUGH" else "CONDITION_CONFLICT",
        "evidence_refs": refs,
        "explanation": "모델은 합성 근거 전체를 바탕으로 분류했으며 개별 근거를 인용하지 않았습니다.",
    }
    output = {
        "decision": choice,
        "abstain_reason": "CONFLICT_UNRESOLVED" if choice == "ABSTAIN" else None,
        "supporting_reasons": [reason] if choice == "PASS_THROUGH" else [],
        "opposing_reasons": [reason] if choice == "REVIEW_REQUIRED" else [],
    }
    return validate_decision_review_response(projection["input"], output)


def micro_packet(projection: dict[str, Any], protocol: FrozenMicroProtocol) -> dict[str, Any]:
    protocol.validate()
    if projection.get("status") != "SYNTHETIC_ONLY":
        raise DecisionReviewContractError("S5_REAL_MARKET_INPUT_FORBIDDEN")
    source = projection.get("input")
    if not isinstance(source, dict):
        raise DecisionReviewContractError("S5_INPUT_INVALID")
    case_id = source.get("case_id")
    expected = synthetic_projection(str(case_id))
    if projection != expected:
        raise DecisionReviewContractError("S5_SYNTHETIC_PROJECTION_FORGED")
    state = {
        "synthetic_only": True,
        "strategy_intent": source["baseline_decision"]["strategy_intent"],
        "evidence": [
            {"id": e["evidence_id"], "statement": e["value"]}
            for e in source["evidence_items"]
        ],
    }
    return {
        "state": state,
        "questions": {CHOICE_NAME: CHOICE_QUESTION},
        "model": protocol.model_requested,
    }


class SystemOneMicroProvider:
    """Real endpoint transport exists, but requires an explicit trial permit.

    Optional injected MockTransport is for CI. Without an actual approval,
    even mocked submissions fail before accessing credentials or HTTP.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def ask(
        self, packet: dict[str, Any], protocol: FrozenMicroProtocol,
        approval: ActualTrialApproval | None, *, api_key: str | None = None,
    ) -> dict[str, Any]:
        if approval is None:
            raise DecisionReviewContractError("S5_ACTUAL_TRIAL_NOT_APPROVED")
        approval.validate(protocol)
        # Reject raw/mutated/ad-hoc packets before any key or HTTP use.
        if (
            set(packet) != {"state", "questions", "model"}
            or packet["model"] != protocol.model_requested
            or packet["questions"] != {CHOICE_NAME: CHOICE_QUESTION}
            or not isinstance(packet["state"], dict)
            or packet["state"].get("synthetic_only") is not True
        ):
            raise DecisionReviewContractError("S5_REQUEST_INVALID")
        # A simple synthetic_only marker is insufficient: require the exact
        # frozen, code-authored fixture packet before any credentials or I/O.
        if not any(
            packet == micro_packet(synthetic_projection(case_id), protocol)
            for case_id in synthetic_case_ids()
        ):
            raise DecisionReviewContractError("S5_SYNTHETIC_PACKET_FORGED")
        key = api_key or load_typesafe_jev_api_key()
        if not key:
            raise DecisionReviewContractError("S5_API_KEY_MISSING")
        try:
            async with httpx.AsyncClient(
                timeout=protocol.deadline_seconds, transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    TYPESAFE_SYSTEM_ONE_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json=packet,
                )
            response.raise_for_status()
            raw = response.json()
        except httpx.HTTPError as exc:
            raise DecisionReviewContractError("S5_PROVIDER_HTTP_ERROR") from exc
        except (ValueError, TypeError) as exc:
            raise DecisionReviewContractError("S5_PROVIDER_RESPONSE_INVALID") from exc
        return _clean_choice_response(raw, protocol)


class MicroJournal:
    """Separate, explicitly initialized SQLite research DB; no operations DB."""
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection
        self.conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS jev_s5_synthetic (
            review_id TEXT PRIMARY KEY,
            protocol_hash TEXT NOT NULL,
            case_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            expected_gold TEXT NOT NULL,
            provider_id TEXT NOT NULL CHECK(provider_id='TYPESAFE_SYSTEM_ONE'),
            model_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('PENDING','VALID','ERROR','INTERRUPTED')),
            decision TEXT,
            output_json TEXT,
            typed_response_json TEXT,
            reason_code TEXT,
            reserved_usd TEXT NOT NULL,
            computed_cost_usd TEXT,
            cost_status TEXT NOT NULL,
            execution_origin TEXT NOT NULL DEFAULT 'MOCK_TEST'
              CHECK(execution_origin IN ('MOCK_TEST','ACTUAL_PROVIDER')),
            duration_ms REAL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TRIGGER IF NOT EXISTS jev_s5_no_delete
        BEFORE DELETE ON jev_s5_synthetic BEGIN
            SELECT RAISE(ABORT,'S5 trial record cannot be deleted');
        END;
        CREATE TRIGGER IF NOT EXISTS jev_s5_no_revise_terminal
        BEFORE UPDATE ON jev_s5_synthetic
        WHEN OLD.state <> 'PENDING' BEGIN
            SELECT RAISE(ABORT,'S5 terminal record cannot change');
        END;
        """)

    def _one(self, key: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM jev_s5_synthetic WHERE review_id=?", (key,)
        ).fetchone()
        if row is None:
            raise DecisionReviewContractError("S5_JOURNAL_RECORD_MISSING")
        result = dict(row)
        result["output"] = json.loads(row["output_json"]) if row["output_json"] else None
        result["typed_response"] = (
            json.loads(row["typed_response_json"]) if row["typed_response_json"] else None
        )
        result["investment_outcome"] = "NOT_EVALUATED"
        result["fake_case_gold_separate_from_wire"] = True
        return result

    def reserve(self, projection: dict[str, Any], packet: dict[str, Any],
                protocol: FrozenMicroProtocol, *, origin: str = "MOCK_TEST"
                ) -> tuple[dict[str, Any], bool]:
        if origin not in ("MOCK_TEST", "ACTUAL_PROVIDER"):
            raise DecisionReviewContractError("S6_ORIGIN_INVALID")
        key = digest_json({
            "protocol": protocol.identity_hash, "origin": origin,
            "case": projection["input"]["case_id"],
            "input_hash": projection["input_hash"], "request_hash": digest_json(packet),
        })
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT review_id FROM jev_s5_synthetic WHERE review_id=?", (key,)
            ).fetchone()
            if row:
                self.conn.commit()
                return self._one(key), True
            other = self.conn.execute(
                "SELECT reserved_usd FROM jev_s5_synthetic WHERE protocol_hash=?",
                (protocol.identity_hash,),
            ).fetchall()
            booked = sum((Decimal(r["reserved_usd"]) for r in other), Decimal("0"))
            if (
                len(other) >= protocol.max_attempts
                or booked + Decimal(protocol.per_attempt_reservation_usd)
                   > Decimal(protocol.total_budget_usd)
            ):
                raise DecisionReviewContractError("S5_TRIAL_BUDGET_EXHAUSTED")
            self.conn.execute(
                """INSERT INTO jev_s5_synthetic(
                  review_id,protocol_hash,case_id,input_hash,request_hash,expected_gold,
                  provider_id,model_id,state,reserved_usd,cost_status,
                  execution_origin,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    key,protocol.identity_hash,projection["input"]["case_id"],
                    projection["input_hash"],digest_json(packet),
                    _CASE_INDEX[projection["input"]["case_id"]]["gold"],
                    PROVIDER_ID,protocol.model_returned,"PENDING",
                    protocol.per_attempt_reservation_usd,"UNKNOWN",origin,now,
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self._one(key), False

    def finish(self, key: str, *, output: dict[str, Any] | None,
               typed: dict[str, Any] | None, error: str | None,
               protocol: FrozenMicroProtocol, duration_ms: float | None = None
               ) -> dict[str, Any]:
        if output is None:
            state, cost, cost_status = "ERROR", None, "UNKNOWN"
        else:
            state = "VALID"
            usage = typed["usage"] if typed else {}
            cost = str(
                (Decimal(usage["input_tokens"]) *
                 Decimal(protocol.verified_input_usd_per_million) +
                 Decimal(usage["output_tokens"]) *
                 Decimal(protocol.verified_output_usd_per_million)) /
                Decimal(1_000_000)
            )
            cost_status = "ESTIMATED_FROM_VERIFIED_ACCOUNT_RATE"
        cur = self.conn.execute(
            """UPDATE jev_s5_synthetic
               SET state=?,decision=?,output_json=?,typed_response_json=?,
                   reason_code=?,computed_cost_usd=?,cost_status=?,
                   duration_ms=?,completed_at=?
               WHERE review_id=? AND state='PENDING'""",
            (
                state, output["decision"] if output else "ABSTAIN",
                canonical_json(output) if output else None,
                canonical_json(typed) if typed else None,
                error,cost,cost_status,duration_ms,
                datetime.now(timezone.utc).isoformat(),key,
            ),
        )
        self.conn.commit()
        if cur.rowcount != 1:
            raise DecisionReviewContractError("S5_JOURNAL_NOT_PENDING")
        return self._one(key)

    def interrupt_pending(self) -> int:
        cur = self.conn.execute(
            """UPDATE jev_s5_synthetic
               SET state='INTERRUPTED',reason_code='S5_RESTART_INTERRUPTED',
               completed_at=? WHERE state='PENDING'""",
            (datetime.now(timezone.utc).isoformat(),),
        )
        self.conn.commit()
        return cur.rowcount

    def list_records(self) -> list[dict[str, Any]]:
        return [
            self._one(row["review_id"])
            for row in self.conn.execute(
                "SELECT review_id FROM jev_s5_synthetic ORDER BY created_at,review_id"
            )
        ]


class MicroCanaryRunner:
    """One-by-one, no retry, reserve BEFORE provider; error preserves baseline."""
    def __init__(
        self, journal: MicroJournal, provider: SystemOneMicroProvider,
        *, execution_origin: str = "MOCK_TEST",
    ):
        if execution_origin not in ("MOCK_TEST", "ACTUAL_PROVIDER"):
            raise DecisionReviewContractError("S6_ORIGIN_INVALID")
        if execution_origin == "ACTUAL_PROVIDER" and provider.transport is not None:
            raise DecisionReviewContractError("S6_ACTUAL_TRANSPORT_MUST_NOT_BE_MOCK")
        if execution_origin == "MOCK_TEST" and not isinstance(
            provider.transport, httpx.MockTransport
        ):
            raise DecisionReviewContractError("S6_TEST_TRANSPORT_MUST_BE_MOCK")
        self.journal = journal
        self.provider = provider
        self.execution_origin = execution_origin
        self.lock = asyncio.Lock()

    async def run_case(
        self, case_id: str, protocol: FrozenMicroProtocol,
        approval: ActualTrialApproval | None, *, api_key: str | None = None,
    ) -> dict[str, Any]:
        # The guard is before reservation, credentials and HTTP.
        if approval is None:
            raise DecisionReviewContractError("S5_ACTUAL_TRIAL_NOT_APPROVED")
        approval.validate(protocol)
        projection = synthetic_projection(case_id)
        packet = micro_packet(projection, protocol)
        async with self.lock:
            prior, reused = self.journal.reserve(
                projection, packet, protocol, origin=self.execution_origin,
            )
            if reused:
                return {**prior, "reused": True}
            started = time.monotonic()
            try:
                typed = await asyncio.wait_for(
                    self.provider.ask(
                        packet, protocol, approval, api_key=api_key,
                    ),
                    timeout=protocol.deadline_seconds,
                )
                output = _model_to_review(projection, typed["decision"])
                error = None
            except asyncio.CancelledError:
                self.journal.interrupt_pending()
                raise
            except Exception as exc:
                typed, output = None, None
                error = (
                    exc.code if isinstance(exc, DecisionReviewContractError)
                    else "S5_PROVIDER_OR_VALIDATION_ERROR"
                )
            result = self.journal.finish(
                prior["review_id"], output=output, typed=typed,
                error=error, protocol=protocol,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
            return {**result, "reused": False}


def summarize_micro_canary(journal: MicroJournal) -> dict[str, Any]:
    """Synthetic quality diagnostics only; never a live investment metric."""
    records = journal.list_records()
    valid = [r for r in records if r["state"] == "VALID"]
    wrong = sum(r["decision"] != r["expected_gold"] for r in valid)
    return {
        "version": MICRO_VERSION,
        "scope": SYNTHETIC_SCOPE,
        "attempts": len(records),
        "valid": len(valid),
        "errors": sum(r["state"] == "ERROR" for r in records),
        "abstained": sum(r["decision"] == "ABSTAIN" for r in valid),
        "incorrect_against_synthetic_gold": wrong,
        "correct_against_synthetic_gold": len(valid) - wrong,
        "unattempted_cases": sorted(set(synthetic_case_ids()) - {r["case_id"] for r in records}),
        "outcome": "NOT_EVALUATED",
        "investment_uplift_established": False,
    }
