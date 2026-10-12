"""JEV-ACT2-S6 consent-gated synthetic Micro-Canary command.

Default is offline status; dry-run and report never read API credentials.
check-account performs an authenticated GET only after an explicit opt-in.
run-approved additionally requires interactive, run-specific consent, current
account terms/pricing evidence supplied by the owner, and a pinned model
listed by the account. Tests inject MockTransport; CI never makes real calls.
No StockScope Scanner, portfolio, validation, or production DB is used.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.parse import urlsplit
import re
import sqlite3
import sys
from typing import Any, Callable

# Standalone PowerShell entry from repository root; no backend import via cwd.
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import httpx
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.decision_reviewer_micro_canary import (
    ActualTrialApproval, FrozenMicroProtocol, MicroCanaryRunner,
    MicroJournal, SystemOneMicroProvider, CASE_SET_HASH, QUESTION_HASH,
    synthetic_case_ids, synthetic_projection, micro_packet,
)
from app.jev.typesafe_provider import (
    TypeSafeJevProviderError, discover_typesafe_models,
    load_typesafe_jev_api_key,
)

VERSION = "JEV_ACT2_S6_MICRO_EXECUTION_V1"
# Stored only in gitignored data/, never any existing runtime, simulation or
# Prospective DB. CLI accepts no --db override for a live run.
RESEARCH_DB = ROOT / "data" / "jev_research" / "s6_micro_canary.sqlite3"
MAX_INPUT_TOKEN_UPPER_BYTES = True
OUTPUT_TOKEN_RESERVATION = 8192


def _decimal(value: str, code: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DecisionReviewContractError(code) from exc
    if not result.is_finite() or result < 0:
        raise DecisionReviewContractError(code)
    return result


def _fixed_model(model: str | None) -> str:
    value = (model or "").strip()
    if not value or "unfrozen" in value.lower():
        raise DecisionReviewContractError("S6_PINNED_MODEL_REQUIRED")
    if value == "jev-preview":
        raise DecisionReviewContractError("S6_PREVIEW_NOT_APPROVED")
    if "latest" in value.lower() and value != "jev-latest":
        raise DecisionReviewContractError("S6_ALIAS_NOT_APPROVED")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,100}", value):
        raise DecisionReviewContractError("S6_MODEL_ID_INVALID")
    return value


def _cases(selected: list[str] | None) -> tuple[str, ...]:
    available = set(synthetic_case_ids())
    values = selected or list(synthetic_case_ids())
    if len(set(values)) != len(values) or not set(values) <= available:
        raise DecisionReviewContractError("S6_CASE_SCOPE_INVALID")
    return tuple(values)


def _protocol(args: argparse.Namespace, cases: tuple[str, ...]) -> FrozenMicroProtocol:
    model = _fixed_model(args.model)
    if args.max_calls != len(cases):
        raise DecisionReviewContractError("S6_MAX_CALLS_MUST_EQUAL_CASES")
    proto = FrozenMicroProtocol(
        protocol_id="JEV-ACT2-S6-SYNTHETIC-" + ",".join(cases),
        model_requested=model,
        model_returned=model,
        alias_identity_policy=(
            "SYNTHETIC_JEV_LATEST_V1" if model == "jev-latest"
            else "FIXED_MODEL"
        ),
        max_attempts=args.max_calls,
        per_attempt_reservation_usd=args.reserve_usd,
        total_budget_usd=args.budget_usd,
        verified_input_usd_per_million=args.input_price,
        verified_output_usd_per_million=args.output_price,
        deadline_seconds=args.deadline_seconds,
    )
    proto.validate()
    return proto


def _upper_bound_check(protocol: FrozenMicroProtocol, cases: tuple[str, ...]) -> dict[str, Any]:
    """Conservative local planning only; provider cannot promise token maxima."""
    if (protocol.verified_input_usd_per_million is None or
        protocol.verified_output_usd_per_million is None):
        return {
            "status": "PRICE_UNKNOWN",
            "upper_bound_cost_usd": None,
            "note": "가격이 입력되지 않아 비용을 추정할 수 없습니다. 실제 실행은 금지됩니다.",
        }
    input_rate = _decimal(protocol.verified_input_usd_per_million, "S6_ACCOUNT_PRICE_REQUIRED")
    output_rate = _decimal(protocol.verified_output_usd_per_million, "S6_ACCOUNT_PRICE_REQUIRED")
    max_request_bytes = max(
        len(json.dumps(
            micro_packet(synthetic_projection(case), protocol),
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        for case in cases
    )
    bound = (
        Decimal(max_request_bytes) * input_rate
        + Decimal(OUTPUT_TOKEN_RESERVATION) * output_rate
    ) / Decimal(1_000_000)
    if bound > _decimal(protocol.per_attempt_reservation_usd, "S6_BUDGET_INVALID"):
        raise DecisionReviewContractError("S6_PESSIMISTIC_RESERVATION_EXCEEDS_LIMIT")
    return {
        "max_synthetic_request_bytes": max_request_bytes,
        "planning_output_tokens": OUTPUT_TOKEN_RESERVATION,
        "upper_bound_cost_usd": str(bound),
        "note": "보수적인 사전 추정치. 공급자 청구액의 절대 상한 보증이 아닙니다.",
    }


def _manifest(args: argparse.Namespace) -> tuple[FrozenMicroProtocol, tuple[str, ...], dict[str, Any]]:
    cases = _cases(args.case)
    proto = _protocol(args, cases)
    return proto, cases, {
        "version": VERSION,
        "scope": "SYNTHETIC_ONLY",
        "status": "AWAITING_SEPARATE_EXECUTION_CONSENT",
        "protocol_hash": proto.identity_hash,
        "model_requested": proto.model_requested,
        "model_identity_policy": proto.alias_identity_policy,
        "model_revision_status": (
            "REVISION_UNVERIFIED"
            if proto.alias_identity_policy == "SYNTHETIC_JEV_LATEST_V1"
            else "PINNED_NAME_NOT_PROVEN_IMMUTABLE"
        ),
        "case_set_hash": CASE_SET_HASH,
        "question_hash": QUESTION_HASH,
        "selected_cases": list(cases),
        "attempt_cap": proto.max_attempts,
        "budget_usd": proto.total_budget_usd,
        "reservation_per_call_usd": proto.per_attempt_reservation_usd,
        "retry_count": 0,
        "max_concurrency": 1,
        "actual_requests_executed_by_dry_run": 0,
        "market_data_included": False,
    }


def _prompt_exact(input_fn: Callable[[str], str], message: str, phrase: str) -> None:
    try:
        supplied = input_fn(message)
    except (KeyboardInterrupt, EOFError) as exc:
        raise DecisionReviewContractError("S6_CONSENT_INTERACTIVE_REQUIRED") from exc
    if supplied != phrase:
        raise DecisionReviewContractError("S6_CONSENT_PHRASE_MISMATCH")


def _attestations(args: argparse.Namespace) -> None:
    # A public home page is not evidence of this account's billing rate.
    # These remain *owner-reviewed statements*, never vendor-verified proof.
    for name in ("account_terms_ref", "account_price_ref"):
        value = getattr(args, name) or ""
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not (
                parsed.hostname == "typesafe.ai"
                or parsed.hostname.endswith(".typesafe.ai")
            )
            or parsed.path in ("", "/")
            or parsed.query or parsed.fragment or parsed.username or parsed.password
        ):
            raise DecisionReviewContractError("S6_ACCOUNT_EVIDENCE_REF_REQUIRED")
    if args.account_price_source != "ACCOUNT_BILLING_USER_ATTESTED":
        raise DecisionReviewContractError("S6_ACCOUNT_PRICING_UNVERIFIED")
    try:
        observed = date.fromisoformat(args.account_billing_checked_date or "")
    except ValueError as exc:
        raise DecisionReviewContractError("S6_ACCOUNT_PRICING_UNVERIFIED") from exc
    today = datetime.now(timezone.utc).date()
    if not (today - timedelta(days=7) <= observed <= today):
        raise DecisionReviewContractError("S6_ACCOUNT_PRICING_UNVERIFIED")
    for key in (args.input_price, args.output_price):
        _decimal(key, "S6_ACCOUNT_PRICE_REQUIRED")


def _approved(
    proto: FrozenMicroProtocol, args: argparse.Namespace,
    input_fn: Callable[[str], str],
) -> ActualTrialApproval:
    _attestations(args)
    text = f"RUN S6 {proto.identity_hash[:12]} {proto.max_attempts} USD {proto.total_budget_usd}"
    _prompt_exact(
        input_fn,
        "\n실제 계정에서 합성 데이터만 전송합니다. 모델, 요청 수, 최대 예약액을 검토했으면 아래 문장을 그대로 입력하세요:\n"
        + text + "\n> ",
        text,
    )
    _prompt_exact(
        input_fn,
        "계정 청구 화면과 이용 조건을 직접 확인했음을 확인하면 입력하세요:\n"
        "I CONFIRM ACCOUNT TERMS AND PRICING\n> ",
        "I CONFIRM ACCOUNT TERMS AND PRICING",
    )
    if proto.alias_identity_policy == "SYNTHETIC_JEV_LATEST_V1":
        # Must be attached to the exact trial fingerprint. A plain extra flag
        # or old consent cannot silently authorize a moving alias.
        phrase = f"I ACCEPT MOVING ALIAS {proto.identity_hash[:12]}"
        _prompt_exact(
            input_fn,
            "jev-latest는 실제 고정 모델 버전이 아닙니다. "
            "동일 alias가 내부적으로 바뀌어도 감지할 수 없음을 확인하면 입력하세요:\n"
            + phrase + "\n> ",
            phrase,
        )
    return ActualTrialApproval(
        approved_protocol_hash=proto.identity_hash,
        approved_case_set_hash=CASE_SET_HASH,
        approved_model=proto.model_returned,
        approved_budget_usd=proto.total_budget_usd,
        owner_approved=True,
        provider_terms_confirmed=True,
        account_pricing_confirmed=True,
        model_catalog_confirmed=True,
        explicit_trial_scope="S5_APPROVED_SYNTHETIC_MICRO_CANARY",
    )


def _record_owner_attestation(
    conn: sqlite3.Connection, proto: FrozenMicroProtocol,
    cases: tuple[str, ...], args: argparse.Namespace,
) -> None:
    """Immutable owner-entered evidence; NOT third-party price verification."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS jev_s6_owner_attestation (
        protocol_hash TEXT PRIMARY KEY,
        case_ids_json TEXT NOT NULL,
        model_id TEXT NOT NULL,
        max_attempts INTEGER NOT NULL,
        total_budget_usd TEXT NOT NULL,
        input_price TEXT NOT NULL,
        output_price TEXT NOT NULL,
        account_terms_ref TEXT NOT NULL,
        account_price_ref TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK(source_type='USER_ATTESTED'),
        account_price_source TEXT NOT NULL,
        account_billing_checked_date TEXT NOT NULL,
        model_identity_policy TEXT NOT NULL,
        approved_at TEXT NOT NULL
    );
    CREATE TRIGGER IF NOT EXISTS jev_s6_approval_no_delete
    BEFORE DELETE ON jev_s6_owner_attestation BEGIN
        SELECT RAISE(ABORT,'S6 approval immutable');
    END;
    CREATE TRIGGER IF NOT EXISTS jev_s6_approval_no_update
    BEFORE UPDATE ON jev_s6_owner_attestation BEGIN
        SELECT RAISE(ABORT,'S6 approval immutable');
    END;
    """)
    values = (
        proto.identity_hash, json.dumps(cases, ensure_ascii=False),
        proto.model_returned, proto.max_attempts, proto.total_budget_usd,
        proto.verified_input_usd_per_million,
        proto.verified_output_usd_per_million,
        args.account_terms_ref, args.account_price_ref, "USER_ATTESTED",
        args.account_price_source, args.account_billing_checked_date,
        proto.alias_identity_policy,
    )
    existing = conn.execute(
        "SELECT case_ids_json,model_id,max_attempts,total_budget_usd,"
        "input_price,output_price,account_terms_ref,account_price_ref,source_type,"
        "account_price_source,account_billing_checked_date,model_identity_policy "
        "FROM jev_s6_owner_attestation WHERE protocol_hash=?",
        (proto.identity_hash,),
    ).fetchone()
    if existing:
        if tuple(existing) != values[1:]:
            raise DecisionReviewContractError("S6_ATTESTATION_DRIFT")
        return
    conn.execute(
        """INSERT INTO jev_s6_owner_attestation(
            protocol_hash,case_ids_json,model_id,max_attempts,total_budget_usd,
            input_price,output_price,account_terms_ref,account_price_ref,
            source_type,account_price_source,account_billing_checked_date,
            model_identity_policy,approved_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (*values, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _display(value: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    print("=" * 65)
    print("StockScope JEV S6 · 합성 Micro-Canary 연구 전용")
    print("=" * 65)
    for key, value_ in value.items():
        if isinstance(value_, (list, dict)):
            print(f"{key}: {json.dumps(value_, ensure_ascii=False)}")
        else:
            print(f"{key}: {value_}")


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sources = ("ACTUAL_PROVIDER", "MOCK_TEST", "UNVERIFIED")
    groups: dict[str, Any] = {}
    for origin in sources:
        subset = [
            r for r in rows
            if (r.get("execution_origin") or "UNVERIFIED") == origin
        ]
        valid = [r for r in subset if r["state"] == "VALID"]
        # Gold is local-only. Wrong model decisions include every synthetic
        # case, and do not constitute an investment-performance comparison.
        misses = [r for r in valid if r["decision"] != r["expected_gold"]]
        normal_false_reviews = sum(
            r["expected_gold"] == "PASS_THROUGH" and r["decision"] == "REVIEW_REQUIRED"
            for r in valid
        )
        contradiction_misses = sum(
            r["expected_gold"] == "REVIEW_REQUIRED" and r["decision"] != "REVIEW_REQUIRED"
            for r in valid
        )
        avoidable_abstains = sum(
            r["expected_gold"] != "ABSTAIN" and r["decision"] == "ABSTAIN"
            for r in valid
        )
        proper_abstains = sum(
            r["expected_gold"] == "ABSTAIN" and r["decision"] == "ABSTAIN"
            for r in valid
        )
        cost_known = sum(
            (_decimal(r["computed_cost_usd"], "S6_STORED_COST_INVALID")
             for r in subset if r["computed_cost_usd"] is not None),
            Decimal("0"),
        )
        durations = [
            float(r["duration_ms"]) for r in subset
            if r.get("duration_ms") is not None
        ]
        groups[origin] = {
            "attempts": len(subset),
            "valid": len(valid),
            "incorrect": len(misses),
            "correct": len(valid) - len(misses),
            "normal_false_reviews": normal_false_reviews,
            "contradiction_misses": contradiction_misses,
            "proper_abstentions": proper_abstains,
            "avoidable_abstentions": avoidable_abstains,
            "errors": sum(r["state"] == "ERROR" for r in subset),
            "interrupted": sum(r["state"] == "INTERRUPTED" for r in subset),
            "known_estimated_cost_usd": str(cost_known),
            "unknown_cost_attempts": sum(r["cost_status"] == "UNKNOWN" for r in subset),
            "average_latency_ms": round(sum(durations)/len(durations), 2)
            if durations else None,
            "records": [
                {
                    "case": r["case_id"], "gold": r["expected_gold"],
                    "choice": r["decision"], "state": r["state"],
                    "probabilities": (
                        r["typed_response"]["probabilities"]
                        if r["typed_response"] else None
                    ),
                    "reason": r["reason_code"],
                    "estimated_cost_usd": r["computed_cost_usd"],
                    "cost_status": r["cost_status"],
                    "latency_ms": r.get("duration_ms"),
                }
                for r in subset
            ],
        }
    return {
        "version": VERSION,
        "status": "SYNTHETIC_DIAGNOSTIC_ONLY",
        "by_origin": groups,
        "total_records": len(rows),
        "investment_outcomes": "NOT_EVALUATED",
        "scanner_uplift_proven": False,
        "message": "합성 사례 정답 비교일 뿐 실제 투자 수익·손실 개선을 의미하지 않습니다.",
    }


def _read_report(db: Path) -> dict[str, Any]:
    if not db.is_file():
        return _aggregate([])
    connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        journal = MicroJournal(connection)
        return _aggregate(journal.list_records())
    finally:
        connection.close()


async def _lookup_models(*, transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, str]]:
    return await discover_typesafe_models(
        deadline_seconds=10.0, transport=transport,
    )


def _check_model(models: list[dict[str, str]], name: str) -> None:
    if name not in {m["name"] for m in models}:
        raise DecisionReviewContractError("S6_PINNED_MODEL_NOT_AVAILABLE_TO_ACCOUNT")


async def execute(
    args: argparse.Namespace, *,
    input_fn: Callable[[str], str] = input,
    transport: httpx.AsyncBaseTransport | None = None,
    journal_path: Path = RESEARCH_DB,
) -> dict[str, Any]:
    """Tests may inject MockTransport and temp DB; CLI never accepts those args."""
    mode = args.mode
    if mode == "status":
        return {
            "version": VERSION, "scope": "SYNTHETIC_ONLY",
            "status": "HOLD_UNTIL_SEPARATE_AUTHORIZATION",
            "available_modes": ["status", "dry-run", "check-account", "run-approved", "report"],
            "provider_calls": 0, "db_writes": 0,
            "real_stock_eligible": False,
        }
    if mode == "report":
        return _read_report(journal_path)
    if mode == "check-account":
        if not args.authorize_model_lookup:
            raise DecisionReviewContractError("S6_MODEL_LOOKUP_NOT_AUTHORIZED")
        _prompt_exact(input_fn, "인증된 계정 모델 목록을 외부 조회하려면 TYPE S6 MODEL LOOKUP 입력: ",
                      "TYPE S6 MODEL LOOKUP")
        models = await _lookup_models(transport=transport)
        result: dict[str, Any] = {
            "version": VERSION, "status": "MODEL_CATALOG_READ_ONLY",
            "models": models, "model_lookup_requests": 1,
            "price_verified": False, "account_terms_verified": False,
            "micro_canary_calls": 0,
        }
        if args.model:
            fixed = _fixed_model(args.model)
            result["requested_model"] = fixed
            result["available"] = fixed in {m["name"] for m in models}
        return result
    if mode not in ("dry-run", "run-approved"):
        raise DecisionReviewContractError("S6_MODE_INVALID")
    proto, cases, report = _manifest(args)
    report["worst_case_reservation"] = _upper_bound_check(proto, cases)
    if mode == "dry-run":
        return report
    if not args.authorize_model_lookup:
        raise DecisionReviewContractError("S6_MODEL_LOOKUP_NOT_AUTHORIZED")
    # Real user must retype this run's exact protocol fingerprint, count and
    # maximum reserved budget; flags or a reusable JSON boolean are insufficient.
    approval = _approved(proto, args, input_fn)
    approval.validate(proto)
    # No credential is inspected before the two interactive approvals.
    api_key = load_typesafe_jev_api_key()
    if not api_key:
        raise DecisionReviewContractError("S6_API_KEY_MISSING")
    models = await _lookup_models(transport=transport)
    _check_model(models, proto.model_requested)
    # Make sure test approval cannot be mislabeled ACTUAL_PROVIDER. The normal
    # CLI has no transport injection, so only a real network path can get tag.
    origin = "MOCK_TEST" if transport is not None else "ACTUAL_PROVIDER"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(journal_path) as conn:
        journal = MicroJournal(conn)
        journal.initialize()
        journal.interrupt_pending()  # Never silently re-send a crashed request.
        _record_owner_attestation(conn, proto, cases, args)
        provider = SystemOneMicroProvider(transport=transport)
        runner = MicroCanaryRunner(journal, provider, execution_origin=origin)
        for case in cases:
            row = await runner.run_case(case, proto, approval, api_key=api_key)
            if row["state"] != "VALID":
                break  # First provider failure stops remaining billable attempts.
            estimated = row["computed_cost_usd"]
            if (estimated is None or
                _decimal(estimated, "S6_STORED_COST_INVALID") >
                _decimal(proto.per_attempt_reservation_usd, "S6_BUDGET_INVALID")):
                break  # Reservation budget is NOT a billing guarantee.
    result = _read_report(journal_path)
    result["protocol_hash"] = proto.identity_hash
    result["account_model_lookup_requests"] = 1
    result["owner_attestation"] = "USER_ATTESTED_NOT_PROVIDER_INDEPENDENTLY_VERIFIED"
    result["pricing_reference"] = args.account_price_ref
    result["terms_reference"] = args.account_terms_ref
    result["status"] = "EXPERIMENT_RECORDED_NOT_INVESTMENT_VALIDATED"
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="StockScope JEV S6 synthetic-only micro Canary. Default is offline status."
    )
    p.add_argument(
        "mode", nargs="?", default="status",
        choices=("status", "dry-run", "check-account", "run-approved", "report"),
    )
    p.add_argument("--model", default=None, help="Explicit pinned model, not latest alias")
    p.add_argument("--case", action="append", default=None, help="Registered synthetic case; repeat to select")
    p.add_argument("--max-calls", type=int, default=5)
    p.add_argument("--budget-usd", default="0.05")
    p.add_argument("--reserve-usd", default="0.01")
    p.add_argument("--input-price", default=None, help="USER-confirmed USD per million input tokens")
    p.add_argument("--output-price", default=None, help="USER-confirmed USD per million output tokens")
    p.add_argument("--account-terms-ref", default=None, help="Owner-reviewed HTTPS terms evidence")
    p.add_argument("--account-price-ref", default=None, help="Owner-reviewed HTTPS account billing evidence (not homepage)")
    p.add_argument("--account-price-source", default=None, choices=["ACCOUNT_BILLING_USER_ATTESTED"])
    p.add_argument("--account-billing-checked-date", default=None, help="Recent YYYY-MM-DD date owner viewed billing rate")
    p.add_argument("--deadline-seconds", type=float, default=5.0)
    p.add_argument("--authorize-model-lookup", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(execute(args))
    except (DecisionReviewContractError, TypeSafeJevProviderError) as exc:
        # Do not print sensitive upstream HTTP details, API keys or payload.
        print(f"JEV S6 HOLD: {exc.code}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError):
        print("JEV S6 HOLD: LOCAL_RESEARCH_STORE_UNAVAILABLE", file=sys.stderr)
        return 2
    _display(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
