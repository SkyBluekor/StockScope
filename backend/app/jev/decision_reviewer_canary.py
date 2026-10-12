"""ACT2-S4: closed-network Decision Reviewer Canary preparation.

Only an injected httpx.MockTransport is executable here. This module does
not import credentials, accept arbitrary URLs, access the network, or connect
its tables to production. An actual provider needs a separate approved step.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

import httpx

from app.horizon import resolve_horizon_context
from app.prospective.models import canonical_json, digest_json
from .decision_reviewer_offline import (
    INPUT_VERSION, OUTPUT_VERSION, DecisionReviewContractError,
    validate_decision_review_response,
)

CANARY_PREP_VERSION = "JEV_ACT2_S4_CANARY_PREP_V1"
MOCK_JOURNAL_VERSION = "JEV_ACT2_S4_MOCK_JOURNAL_V1"
MOCK_URL = "https://jev-mock.invalid/review"
PROMPT_VERSION = "JEV_SCANNER_DECISION_REVIEW_PROMPT_V1"
PROMPT_TEXT = (
    "Only interpret supplied Scanner evidence. Cite input evidence IDs. "
    "Reply with exactly decision, abstain_reason, supporting_reasons, "
    "opposing_reasons. Never create a trade instruction, price, probability, "
    "forecast, or evidence absent from this input. Abstain if unsupported."
)


@dataclass(frozen=True)
class TrialLimits:
    """Strict test-only ceiling; not authorization to pay or transmit."""
    protocol_id: str
    model_id: str = "MOCK-ACT2-S4"
    provider_id: str = "MOCK_HTTP"
    max_attempts: int = 2
    max_reserved_usd: float = 0.02
    per_attempt_reservation_usd: float = 0.01
    deadline_seconds: float = 2.0
    concurrency_cap: int = 1
    retry_count: int = 0
    allow_real_network: bool = False

    def validate(self) -> None:
        if (
            not self.protocol_id.strip()
            or self.model_id != "MOCK-ACT2-S4"
            or self.provider_id != "MOCK_HTTP"
            or self.allow_real_network
            or not (1 <= self.max_attempts <= 10)
            or not (0 < self.per_attempt_reservation_usd <= 0.01)
            or not (0 < self.max_reserved_usd <= 0.1)
            or self.max_attempts * self.per_attempt_reservation_usd > self.max_reserved_usd + 1e-9
            or not (0 < self.deadline_seconds <= 10)
            or self.concurrency_cap != 1
            or self.retry_count != 0
        ):
            raise DecisionReviewContractError("S4_MOCK_LIMITS_INVALID")

    @property
    def protocol_hash(self) -> str:
        from dataclasses import asdict
        return digest_json(asdict(self))


def _check(code: str, passed: bool, reason: str) -> dict[str, str]:
    return {"code": code, "status": "PASS" if passed else "HOLD", "reason": reason}


def assess_actual_canary_preflight(
    projection: dict[str, Any],
    *,
    model_identity_confirmed: bool = False,
    account_pricing_verified: bool = False,
    budget_approved: bool = False,
    source_transmission_approved: bool = False,
    explicit_user_execution_approved: bool = False,
) -> dict[str, Any]:
    """Read-only actual-market gate. Booleans alone never override source law."""
    review_input = projection.get("input")
    identity_ok = isinstance(review_input, dict) and isinstance(projection.get("input_hash"), str)
    if identity_ok:
        body = dict(review_input)
        supplied_hash = body.pop("input_hash", None)
        identity_ok = (
            supplied_hash == projection["input_hash"]
            and supplied_hash == digest_json(body)
            and review_input.get("schema_version") == INPUT_VERSION
        )
    horizon = (
        str(review_input.get("baseline_identity", {}).get("horizon_intent") or "")
        if identity_ok else ""
    )
    horizon_state = resolve_horizon_context(horizon)
    provenance = review_input.get("as_of", {}) if identity_ok else {}
    items = review_input.get("evidence_items", ()) if identity_ok else ()
    source_time_ok = (
        isinstance(provenance, dict)
        and provenance.get("time_proof") == "SOURCE_RELEASE_TIMESTAMP_VERIFIED"
        and isinstance(items, list)
        and bool(items)
        and all(isinstance(v, dict) and v.get("available_at") for v in items)
    )
    limitations = review_input.get("limitations", ()) if identity_ok else ()
    forbidden = (
        "NOT_AUTHORIZED_FOR_PROVIDER_TRANSMISSION" in limitations
        or "HORIZON_NUMERIC_POLICY_NOT_APPROVED" in limitations
    )
    checks = [
        _check("INPUT_HASH", identity_ok, "원본 projection 서명/버전 불일치"),
        _check("MARKET_SCOPE", identity_ok and projection.get("status") == "ACTUAL_CANARY_APPROVED_SOURCE",
               "S3는 OFFLINE_INSPECTABLE_ONLY이며 실제 후보 호출 승인이 아님"),
        _check("HORIZON_POLICY", horizon_state.is_activatable,
               horizon_state.reason_code or "미승인 기간 정책"),
        _check("SOURCE_AS_OF", source_time_ok, "EOD 날짜만으로 외부 공개 시각을 증명할 수 없음"),
        _check("SOURCE_RIGHTS", source_transmission_approved and not forbidden,
               "전송 승인 또는 입력 source 권한 증거 부족"),
        _check("PROVIDER_MODEL", model_identity_confirmed, "실제 공급자/모델 revision 미고정"),
        _check("PRICING", account_pricing_verified, "실계정 요금 미검증"),
        _check("BUDGET", budget_approved, "요청 및 프로젝트 비용 승인 없음"),
        _check("USER_EXECUTION", explicit_user_execution_approved, "해당 Canary 호출 별도 승인 없음"),
    ]
    # This diagnostic can never perform a call, even if the caller supplies
    # all True. Approval needs a separate executable implementation.
    return {
        "version": CANARY_PREP_VERSION,
        "status": "HOLD",
        "can_call_actual_provider": False,
        "checks": checks,
        "blocking_reasons": [c["code"] for c in checks if c["status"] != "PASS"],
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def build_mock_request(projection: dict[str, Any], limits: TrialLimits) -> dict[str, Any]:
    """Minimal provider-neutral packet; raw market payload never forwarded."""
    limits.validate()
    if projection.get("status") != "OFFLINE_INSPECTABLE_ONLY":
        raise DecisionReviewContractError("S4_NOT_MOCK_INSPECTABLE")
    review_input = projection.get("input")
    if not isinstance(review_input, dict):
        raise DecisionReviewContractError("S4_INPUT_INVALID")
    source = dict(review_input)
    expected_hash = source.pop("input_hash", None)
    if (
        expected_hash != projection.get("input_hash")
        or expected_hash != digest_json(source)
        or review_input.get("schema_version") != INPUT_VERSION
        or review_input.get("evaluation_protocol_id") != limits.protocol_id
    ):
        raise DecisionReviewContractError("S4_INPUT_IDENTITY_MISMATCH")
    evidence = review_input.get("evidence_items")
    if (
        not isinstance(evidence, list) or not evidence
        or any(not isinstance(x, dict)
               or x.get("owner") not in {"SCANNER_ENGINE", "SCANNER_RISK"}
               or not x.get("evidence_id") for x in evidence)
    ):
        raise DecisionReviewContractError("S4_SOURCE_ALLOWLIST_DENIED")
    baseline = review_input["baseline_decision"]
    if baseline.get("action") != "ENTRY_CANDIDATE":
        raise DecisionReviewContractError("S4_OUT_OF_SCOPE_ACTION")
    return {
        "transport": "MOCK_ONLY",
        "model": limits.model_id,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": digest_json({"prompt": PROMPT_TEXT, "version": PROMPT_VERSION}),
        "input_hash": expected_hash,
        "instruction": PROMPT_TEXT,
        "review": {
            "strategy": baseline["strategy"],
            "action": baseline["action"],
            "conditions": baseline["conditions"],
            "risk": baseline["risk"],
            "evidence_items": [
                {"evidence_id": x["evidence_id"], "owner": x["owner"], "value": x["value"]}
                for x in evidence
            ],
            "limitations": [
                "NO_EXACT_MARKET_SOURCE_RELEASE_TIME",
                "NO_PRICE_GUIDE_TRANSMISSION",
                "NO_REAL_MODEL_USE",
            ],
        },
    }


class MockHttpReviewer:
    """Only accepts a MockTransport; a regular http client cannot be supplied."""

    def __init__(self, transport: httpx.MockTransport):
        if not isinstance(transport, httpx.MockTransport):
            raise DecisionReviewContractError("S4_REAL_TRANSPORT_FORBIDDEN")
        self._transport = transport

    async def review(self, packet: dict[str, Any], *, deadline_seconds: float) -> dict[str, Any]:
        async with httpx.AsyncClient(transport=self._transport, timeout=deadline_seconds) as client:
            response = await client.post(MOCK_URL, json=packet)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise DecisionReviewContractError("S4_HTTP_RESPONSE_INVALID")
        return data


class MockShadowJournal:
    """Opt-in SQLite connection for isolated testing. No production migration."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def initialize_test_store(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS jev_s4_mock_trial (
            identity TEXT PRIMARY KEY,
            protocol_hash TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            source_ref_json TEXT NOT NULL,
            candidate_ref_json TEXT NOT NULL,
            baseline_action TEXT NOT NULL,
            provider_id TEXT NOT NULL CHECK(provider_id='MOCK_HTTP'),
            model_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('PENDING','VALID','ERROR','INTERRUPTED')),
            disposition TEXT,
            reason_code TEXT,
            output_json TEXT,
            reservation_usd REAL NOT NULL,
            observed_cost_usd REAL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TRIGGER IF NOT EXISTS jev_s4_mock_no_delete
        BEFORE DELETE ON jev_s4_mock_trial BEGIN
           SELECT RAISE(ABORT,'JEV mock review is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS jev_s4_mock_no_terminal_change
        BEFORE UPDATE ON jev_s4_mock_trial
        WHEN OLD.state <> 'PENDING' BEGIN
           SELECT RAISE(ABORT,'JEV completed mock review is immutable');
        END;
        """)

    def _ready(self) -> None:
        if not self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jev_s4_mock_trial'"
        ).fetchone():
            raise DecisionReviewContractError("S4_MOCK_TEST_STORE_NOT_INITIALIZED")

    def list_records(self) -> list[dict[str, Any]]:
        self._ready()
        rows = self.conn.execute(
            "SELECT * FROM jev_s4_mock_trial ORDER BY created_at,identity"
        ).fetchall()
        return [self._to_record(row) for row in rows]

    @staticmethod
    def _to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            **dict(row),
            "source_ref": json.loads(row["source_ref_json"]),
            "candidate_ref": json.loads(row["candidate_ref_json"]),
            "output": json.loads(row["output_json"]) if row["output_json"] else None,
            "fake_only": True,
            "actual_provider_calls": 0,
        }

    def reserve(
        self, projection: dict[str, Any], packet: dict[str, Any], limits: TrialLimits,
    ) -> tuple[dict[str, Any], bool]:
        self._ready()
        identity = digest_json({
            "source_ref": projection["input"]["source_ref"],
            "candidate_ref": projection["input"]["candidate_ref"],
            "protocol_hash": limits.protocol_hash,
            "input_hash": projection["input_hash"],
            "request_hash": digest_json(packet),
            "model_id": limits.model_id,
        })
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            prior = self.conn.execute(
                "SELECT * FROM jev_s4_mock_trial WHERE identity=?", (identity,)
            ).fetchone()
            if prior is not None:
                self.conn.commit()
                return self._to_record(prior), True
            row = self.conn.execute(
                "SELECT COUNT(*) AS attempts,COALESCE(SUM(reservation_usd),0) AS booked "
                "FROM jev_s4_mock_trial WHERE protocol_hash=?",
                (limits.protocol_hash,),
            ).fetchone()
            if (row["attempts"] >= limits.max_attempts
                or row["booked"] + limits.per_attempt_reservation_usd
                   > limits.max_reserved_usd + 1e-9):
                raise DecisionReviewContractError("S4_MOCK_BUDGET_OR_ATTEMPTS_EXCEEDED")
            self.conn.execute(
                """INSERT INTO jev_s4_mock_trial(
                identity,protocol_hash,input_hash,request_hash,source_ref_json,
                candidate_ref_json,baseline_action,provider_id,model_id,
                state,reservation_usd,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identity, limits.protocol_hash, projection["input_hash"],
                    digest_json(packet),
                    canonical_json(projection["input"]["source_ref"]),
                    canonical_json(projection["input"]["candidate_ref"]),
                    projection["input"]["baseline_decision"]["action"],
                    limits.provider_id, limits.model_id, "PENDING",
                    limits.per_attempt_reservation_usd, now,
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        row = self.conn.execute(
            "SELECT * FROM jev_s4_mock_trial WHERE identity=?", (identity,)
        ).fetchone()
        return self._to_record(row), False

    def finish(
        self, identity: str, *, output: dict[str, Any] | None,
        failure_code: str | None, reservation_usd: float,
    ) -> dict[str, Any]:
        self._ready()
        now = datetime.now(timezone.utc).isoformat()
        status = "VALID" if output is not None else "ERROR"
        cursor = self.conn.execute(
            """UPDATE jev_s4_mock_trial SET
                state=?,disposition=?,reason_code=?,output_json=?,
                observed_cost_usd=?,completed_at=?
                WHERE identity=? AND state='PENDING'""",
            (
                status, output["decision"] if output else "ABSTAIN",
                failure_code,
                canonical_json(output) if output else None,
                0.0, now, identity,
            ),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise DecisionReviewContractError("S4_MOCK_FINISH_NOT_PENDING")
        return self.get(identity)

    def interrupt_one(self, identity: str) -> dict[str, Any]:
        self._ready()
        self.conn.execute(
            """UPDATE jev_s4_mock_trial SET state='INTERRUPTED',
            reason_code='S4_PROCESS_INTERRUPTED',completed_at=?
            WHERE identity=? AND state='PENDING'""",
            (datetime.now(timezone.utc).isoformat(), identity),
        )
        self.conn.commit()
        return self.get(identity)

    def get(self, identity: str) -> dict[str, Any]:
        self._ready()
        row = self.conn.execute(
            "SELECT * FROM jev_s4_mock_trial WHERE identity=?", (identity,)
        ).fetchone()
        if row is None:
            raise DecisionReviewContractError("S4_MOCK_RECORD_NOT_FOUND")
        return self._to_record(row)

    def interrupt_pending(self) -> int:
        self._ready()
        cursor = self.conn.execute(
            """UPDATE jev_s4_mock_trial SET state='INTERRUPTED',
               reason_code='S4_PROCESS_INTERRUPTED',
               completed_at=?
               WHERE state='PENDING'""",
            (datetime.now(timezone.utc).isoformat(),),
        )
        self.conn.commit()
        return cursor.rowcount


class MockCanaryRunner:
    """Executes a bounded mock transport, never an actual provider."""

    def __init__(self, journal: MockShadowJournal, provider: MockHttpReviewer):
        self.journal = journal
        self.provider = provider
        self._lock = asyncio.Lock()

    async def run_once(self, projection: dict[str, Any], limits: TrialLimits) -> dict[str, Any]:
        packet = build_mock_request(projection, limits)
        async with self._lock:
            record, reused = self.journal.reserve(projection, packet, limits)
            if reused:
                return {**record, "reused": True}
            try:
                raw = await asyncio.wait_for(
                    self.provider.review(packet, deadline_seconds=limits.deadline_seconds),
                    timeout=limits.deadline_seconds,
                )
                # HTTP adapter has no right to trust a provider-provided model ID;
                # only the four output fields validated in S3 can be accepted.
                validated = validate_decision_review_response(projection["input"], raw)
                failure = None
            except asyncio.CancelledError:
                self.journal.interrupt_one(record["identity"])
                raise
            except Exception as exc:  # Mock errors must never become baseline decisions.
                validated = None
                failure = exc.code if isinstance(exc, DecisionReviewContractError) else (
                    "S4_MOCK_TIMEOUT" if isinstance(exc, asyncio.TimeoutError)
                    else "S4_MOCK_HTTP_OR_SCHEMA_ERROR"
                )
            result = self.journal.finish(
                record["identity"], output=validated, failure_code=failure,
                reservation_usd=limits.per_attempt_reservation_usd,
            )
            return {**result, "reused": False}
