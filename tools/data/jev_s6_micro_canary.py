"""JEV-ACT2-S6 consent-gated synthetic Micro-Canary command.

Default is offline status; dry-run and report never read API credentials.
check-account performs an authenticated GET only after an explicit opt-in.
run-approved requires one explicit trial-specific consent, a model listed
by the account and a small reserved budget. Published standard pricing is
an ESTIMATE, not independently verified account billing.
Tests inject MockTransport; CI never makes real calls.
No StockScope Scanner, portfolio, validation, or production DB is used.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
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
from app.prospective.models import digest_json
from app.jev.decision_reviewer_micro_canary import (
    ActualTrialApproval, FrozenMicroProtocol, MicroCanaryRunner,
    MicroJournal, SystemOneMicroProvider, CASE_SET_HASH, QUESTION_HASH,
    synthetic_case_ids, synthetic_projection, micro_packet,
)
from app.jev.typesafe_provider import (
    TypeSafeJevProviderError, discover_typesafe_models,
    load_typesafe_jev_api_key,
)

VERSION = "JEV_ACT2_S6_2_MICRO_EXECUTION_V1"
# Stored only in gitignored data/, never any existing runtime, simulation or
# Prospective DB. CLI accepts no --db override for a live run.
RESEARCH_DB = ROOT / "data" / "jev_research" / "s6_micro_canary.sqlite3"
OUTPUT_TOKEN_RESERVATION = 8192
# Publicly advertised TypeSafe Jev standard rate. These are NOT validated
# against individual billing agreements; recorded costs are only estimates.
PUBLIC_INPUT_USD_PER_MILLION = "0.042"
PUBLIC_OUTPUT_USD_PER_MILLION = "0"


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
        verified_input_usd_per_million=PUBLIC_INPUT_USD_PER_MILLION,
        verified_output_usd_per_million=PUBLIC_OUTPUT_USD_PER_MILLION,
        pricing_basis="PUBLIC_STANDARD_UNVERIFIED",
        deadline_seconds=args.deadline_seconds,
    )
    proto.validate()
    return proto


def _upper_bound_check(protocol: FrozenMicroProtocol, cases: tuple[str, ...]) -> dict[str, Any]:
    """Conservative local planning only; provider cannot promise token maxima."""
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
        "pricing_basis": "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED",
        "public_input_usd_per_million": PUBLIC_INPUT_USD_PER_MILLION,
        "public_output_usd_per_million": PUBLIC_OUTPUT_USD_PER_MILLION,
    }


def _prompt_exact(input_fn: Callable[[str], str], message: str, phrase: str) -> None:
    try:
        supplied = input_fn(message)
    except (KeyboardInterrupt, EOFError) as exc:
        raise DecisionReviewContractError("S6_CONSENT_INTERACTIVE_REQUIRED") from exc
    if supplied != phrase:
        raise DecisionReviewContractError("S6_CONSENT_PHRASE_MISMATCH")


def _approved(
    proto: FrozenMicroProtocol, args: argparse.Namespace,
    input_fn: Callable[[str], str],
) -> ActualTrialApproval:
    # A single human-entered phrase binds model, protocol and maximum reserve.
    # There is no "approved=True" CLI flag or automatic approval. This
    # additionally acknowledges jev-latest may silently change revision.
    phrase = (
        f"RUN JEV MICRO {proto.identity_hash[:12]} "
        f"{proto.max_attempts} USD {proto.total_budget_usd}"
    )
    _prompt_exact(
        input_fn,
        "\nTypeSafe 합성 데이터 실험 (최대 "
        + str(proto.max_attempts) + "회, 예약 총액 $"
        + proto.total_budget_usd + ")\n"
        "모델: " + proto.model_requested
        + " (jev-latest는 변경 가능한 별칭이며 내부 버전 변경을 모두 감지할 수 없음)\n"
        "공개 입력 요금: $0.042/100만 토큰, 출력 무료 "
        "(실제 계정 청구액 보증 아님).\n"
        "실제 시장·종목 정보는 전송하지 않습니다.\n"
        "유료 실행과 별칭 위험을 승인하면 다음 문구를 정확히 입력하세요:\n"
        + phrase + "\n> ",
        phrase,
    )
    return ActualTrialApproval(
        approved_protocol_hash=proto.identity_hash,
        approved_case_set_hash=CASE_SET_HASH,
        approved_model=proto.model_returned,
        approved_budget_usd=proto.total_budget_usd,
        owner_approved=True,
        provider_terms_confirmed=True,  # owner accepts trial terms in prompt
        account_pricing_confirmed=True,  # public-rate estimate acknowledged, NOT verified
        model_catalog_confirmed=True,    # network catalog verified after consent
        explicit_trial_scope="S5_APPROVED_SYNTHETIC_MICRO_CANARY",
    )


def _record_owner_attestation(
    conn: sqlite3.Connection, proto: FrozenMicroProtocol,
    cases: tuple[str, ...], args: argparse.Namespace,
) -> None:
    """One immutable trial acknowledgement; retains legacy S6 tables unchanged.

    It does NOT assert this user's billing price was independently verified.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS jev_s6_2_run_consent (
        protocol_hash TEXT PRIMARY KEY,
        model_requested TEXT NOT NULL,
        case_ids_json TEXT NOT NULL,
        max_attempts INTEGER NOT NULL,
        reservation_budget_usd TEXT NOT NULL,
        pricing_basis TEXT NOT NULL
          CHECK(pricing_basis='PUBLIC_STANDARD_UNVERIFIED'),
        input_price_usd_per_million TEXT NOT NULL,
        output_price_usd_per_million TEXT NOT NULL,
        owner_acknowledged_at TEXT NOT NULL
    );
    CREATE TRIGGER IF NOT EXISTS jev_s6_2_consent_no_delete
    BEFORE DELETE ON jev_s6_2_run_consent
    BEGIN SELECT RAISE(ABORT,'S6.2 consent immutable'); END;
    CREATE TRIGGER IF NOT EXISTS jev_s6_2_consent_no_update
    BEFORE UPDATE ON jev_s6_2_run_consent
    BEGIN SELECT RAISE(ABORT,'S6.2 consent immutable'); END;
    """)
    values = (
        proto.identity_hash, proto.model_requested,
        json.dumps(cases, ensure_ascii=False),
        proto.max_attempts, proto.total_budget_usd,
        proto.pricing_basis, proto.verified_input_usd_per_million,
        proto.verified_output_usd_per_million,
    )
    existing = conn.execute(
        """SELECT model_requested,case_ids_json,max_attempts,
           reservation_budget_usd,pricing_basis,input_price_usd_per_million,
           output_price_usd_per_million
           FROM jev_s6_2_run_consent WHERE protocol_hash=?""",
        (proto.identity_hash,),
    ).fetchone()
    if existing:
        if tuple(existing) != values[1:]:
            raise DecisionReviewContractError("S6_CONSENT_SCOPE_DRIFT")
        return
    conn.execute(
        """INSERT INTO jev_s6_2_run_consent(
          protocol_hash,model_requested,case_ids_json,max_attempts,
          reservation_budget_usd,pricing_basis,input_price_usd_per_million,
          output_price_usd_per_million,owner_acknowledged_at
        ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (*values, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _catalog_summary(models: list[dict[str, str]]) -> dict[str, Any]:
    """Provider catalog metadata is NOT a signed immutable model revision."""
    safe = sorted(
        [
            {key: record[key] for key in ("name", "description", "release_date")}
            for record in models
        ],
        key=lambda record: record["name"],
    )
    if len({m["name"] for m in safe}) != len(safe):
        raise DecisionReviewContractError("S6_MODEL_CATALOG_DUPLICATE")
    return {
        "snapshot_hash": digest_json(safe),
        "catalog": safe,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "revision_proven": False,
    }


def _record_model_catalog(
    conn: sqlite3.Connection, proto: FrozenMicroProtocol,
    catalog: dict[str, Any],
) -> None:
    """Immutable first-known snapshot; visible drift => hard hold before POST."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS jev_s6_model_catalog_snapshot (
        protocol_hash TEXT PRIMARY KEY,
        requested_model TEXT NOT NULL,
        catalog_json TEXT NOT NULL,
        catalog_hash TEXT NOT NULL,
        queried_at TEXT NOT NULL,
        alias_policy TEXT NOT NULL,
        revision_status TEXT NOT NULL CHECK(revision_status='REVISION_UNVERIFIED')
    );
    CREATE TRIGGER IF NOT EXISTS jev_s6_catalog_no_update
    BEFORE UPDATE ON jev_s6_model_catalog_snapshot BEGIN
        SELECT RAISE(ABORT,'S6 provider catalog immutable');
    END;
    CREATE TRIGGER IF NOT EXISTS jev_s6_catalog_no_delete
    BEFORE DELETE ON jev_s6_model_catalog_snapshot BEGIN
        SELECT RAISE(ABORT,'S6 provider catalog immutable');
    END;
    """)
    existing = conn.execute(
        "SELECT catalog_hash,requested_model,alias_policy FROM "
        "jev_s6_model_catalog_snapshot WHERE protocol_hash=?",
        (proto.identity_hash,),
    ).fetchone()
    expected = (
        catalog["snapshot_hash"], proto.model_requested,
        proto.alias_identity_policy,
    )
    if existing is not None:
        if tuple(existing) != expected:
            raise DecisionReviewContractError("S6_CATALOG_CHANGED_NEW_PROTOCOL_REQUIRED")
        return
    conn.execute(
        """INSERT INTO jev_s6_model_catalog_snapshot(
            protocol_hash,requested_model,catalog_json,catalog_hash,
            queried_at,alias_policy,revision_status
        ) VALUES(?,?,?,?,?,?,?)""",
        (
            proto.identity_hash, proto.model_requested,
            json.dumps(catalog["catalog"], ensure_ascii=False, sort_keys=True),
            catalog["snapshot_hash"], catalog["checked_at"],
            proto.alias_identity_policy, "REVISION_UNVERIFIED",
        ),
    )
    conn.commit()


def _catalog_snapshots_readonly(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='jev_s6_model_catalog_snapshot'"
    ).fetchone()
    if not exists:
        return []
    return [
        {
            "protocol_hash": row["protocol_hash"],
            "requested_model": row["requested_model"],
            "catalog_hash": row["catalog_hash"],
            "catalog_checked_at": row["queried_at"],
            "identity_policy": row["alias_policy"],
            "model_revision_status": row["revision_status"],
            "models_at_check": json.loads(row["catalog_json"]),
        }
        for row in conn.execute(
            "SELECT * FROM jev_s6_model_catalog_snapshot ORDER BY queried_at"
        )
    ]


_CASE_KOREAN = {
    "s5-consistent": "정상 전략",
    "s5-condition-contradiction": "전략 조건 충돌",
    "s5-risk-contradiction": "위험 판단 충돌",
    "s5-insufficient-evidence": "근거 부족",
    "s5-unresolved-ambiguity": "해결되지 않는 모순",
}
_DECISION_KOREAN = {
    "PASS_THROUGH": "문제 없음",
    "REVIEW_REQUIRED": "재검토 필요",
    "ABSTAIN": "판단 보류",
}


def _display_report(report: dict[str, Any]) -> None:
    """Plain-language output; raw journal remains accessible with --json."""
    actual = report["by_origin"]["ACTUAL_PROVIDER"]
    mock = report["by_origin"]["MOCK_TEST"]
    print("=" * 63)
    print("StockScope Jev · 합성 실험 결과")
    print("=" * 63)
    print(
        f"실제 Jev 호출: {actual['attempts']}건 | 정상 응답 {actual['valid']}건"
        f" | 오류 {actual['errors']}건 | 중단 {actual['interrupted']}건"
    )
    print(
        f"합성 정답 일치: {actual['correct']}건 / {actual['valid']}건"
        f" | 불일치 {actual['incorrect']}건"
    )
    print(
        f"정상 사례 오탐: {actual['normal_false_reviews']}건"
        f" | 조건 충돌 미탐: {actual['contradiction_misses']}건"
        f" | 적절한 판단 보류: {actual['proper_abstentions']}건"
    )
    mean = actual["average_latency_ms"]
    print(f"평균 응답 지연: {mean if mean is not None else '측정 안 됨'} ms")
    print(
        f"API 비용 추정: ${actual['known_estimated_cost_usd']}"
        f" (공개 표준 요금 기준, 계정 청구액 아님)"
    )
    if actual["unknown_cost_attempts"]:
        print(f"청구액 확인 불가 요청: {actual['unknown_cost_attempts']}건")
    if actual["records"]:
        print("-" * 63)
        for record in actual["records"]:
            gold = _DECISION_KOREAN.get(record["gold"], record["gold"])
            got = _DECISION_KOREAN.get(record["choice"], record["choice"] or "응답 없음")
            verdict = (
                "일치" if record["state"] == "VALID" and record["choice"] == record["gold"]
                else "불일치" if record["state"] == "VALID"
                else f"응답 오류 ({record['reason'] or record['state']})"
            )
            print(
                f"{_CASE_KOREAN.get(record['case'], record['case'])}: "
                f"기대 {gold} → 실제 {got} · {verdict}"
            )
    else:
        print("아직 실제 Jev 실험 결과가 없습니다.")
    print(
        f"Mock 테스트 기록: {mock['attempts']}건"
        " (실제 모델 성능 집계에서 제외)"
    )
    print("※ 합성 판단 테스트이며 실전 투자 수익·손실 개선을 증명하지 않습니다.")


def _display(value: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if "by_origin" in value:
        _display_report(value)
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
                    "requested_model": (
                        r["typed_response"].get("requested_model")
                        if r["typed_response"] else r["model_id"]
                    ),
                    "reported_model": (
                        r["typed_response"].get("model")
                        if r["typed_response"] else None
                    ),
                    "revision_status": (
                        r["typed_response"].get("model_identity_status")
                        if r["typed_response"] else "UNKNOWN"
                    ),
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
        result = _aggregate(journal.list_records())
        result["model_catalog_snapshots"] = _catalog_snapshots_readonly(connection)
        return result
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
            "model_catalog_snapshot": _catalog_summary(models),
            "price_verified": False, "account_terms_verified": False,
            "micro_canary_calls": 0,
        }
        if args.model:
            fixed = _fixed_model(args.model)
            result["requested_model"] = fixed
            result["available"] = fixed in {m["name"] for m in models}
            result["model_kind"] = (
                "MOVING_ALIAS_SYNTHETIC_ONLY" if fixed == "jev-latest"
                else "NAMED_MODEL"
            )
            result["model_revision_status"] = "REVISION_UNVERIFIED"
        return result
    if mode not in ("dry-run", "run-approved"):
        raise DecisionReviewContractError("S6_MODE_INVALID")
    proto, cases, report = _manifest(args)
    report["worst_case_reservation"] = _upper_bound_check(proto, cases)
    report["account_price_state"] = "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    if mode == "dry-run":
        return report
    # The one run-specific human approval also authorizes the necessary
    # read-only GET /v1/models, followed by at most 5 synthetic model POSTs.
    approval = _approved(proto, args, input_fn)
    approval.validate(proto)
    # No credential is inspected before the two interactive approvals.
    api_key = load_typesafe_jev_api_key()
    if not api_key:
        raise DecisionReviewContractError("S6_API_KEY_MISSING")
    models = await _lookup_models(transport=transport)
    _check_model(models, proto.model_requested)
    catalog = _catalog_summary(models)
    # Make sure test approval cannot be mislabeled ACTUAL_PROVIDER. The normal
    # CLI has no transport injection, so only a real network path can get tag.
    origin = "MOCK_TEST" if transport is not None else "ACTUAL_PROVIDER"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(journal_path) as conn:
        journal = MicroJournal(conn)
        journal.initialize()
        journal.interrupt_pending()  # Never silently re-send a crashed request.
        _record_owner_attestation(conn, proto, cases, args)
        _record_model_catalog(conn, proto, catalog)
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
    result["owner_attestation"] = "ONE_EXPLICIT_RUN_CONSENT"
    result["pricing_basis"] = "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    result["model_catalog_snapshot_hash"] = catalog["snapshot_hash"]
    result["model_catalog_checked_at"] = catalog["checked_at"]
    result["model_revision_proven"] = False
    result["account_pricing_state"] = "USER_ATTESTED_NOT_INDEPENDENTLY_VERIFIED"
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
    p.add_argument("--model", default=None, help="Named model or jev-latest (synthetic-only unpinned alias); preview denied")
    p.add_argument("--case", action="append", default=None, help="Registered synthetic case; repeat to select")
    p.add_argument("--max-calls", type=int, default=5)
    p.add_argument("--budget-usd", default="0.05")
    p.add_argument("--reserve-usd", default="0.01")
    # Public standard rates are fixed in this isolated research CLI. Never
    # accept arbitrary zero-price overrides or claimed account billing rates.
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
