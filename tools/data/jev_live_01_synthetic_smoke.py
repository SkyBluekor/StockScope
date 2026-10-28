"""JEV-LIVE-01 developer-only synthetic V4 -> TypeSafe -> review catalog.

Default: zero network, zero paid calls. --mode mock uses HTTP MockTransport.
--mode live is exactly ONE billable attempt and requires explicit, separate
approval plus provider evidence. NEVER run this against market capture DB.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

from app.jev.synthetic_live_01 import (
    execute_synthetic_service, prepare_synthetic_service,
)
from app.jev.typesafe_provider import load_typesafe_jev_api_key
from app.jev.typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT

LIVE_APPROVAL = "EXECUTE ONE BILLABLE SYNTHETIC JEV REVIEW"


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if set(body) != {"state", "model", "questions"}:
            return httpx.Response(422)
        return httpx.Response(200, json={
            "model": "jev-mock-returned",
            "answers": {
                key: {"type": "noul", "noul": 0.82 if key == STRATEGY_RELATION_CONFLICT else 0.05}
                for key in body["questions"]
            },
            "usage": {"input_tokens": 120, "output_tokens": 10},
        })
    return httpx.MockTransport(handler)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["preflight", "mock", "live"], default="preflight")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--expected-returned-model", default="")
    parser.add_argument("--budget-usd", type=float, default=1.0)
    parser.add_argument("--reservation-usd", type=float, default=0.10)
    parser.add_argument("--provider-policy-checked-at", default="")
    parser.add_argument("--retention-status", default="")
    parser.add_argument("--model-discovery-ref", default="")
    parser.add_argument("--model-discovery-hash", default="")
    parser.add_argument("--confirm", default="")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.mode == "live":
        if os.getenv("CI"):
            raise ValueError("JEV_LIVE01_PAID_CALL_FORBIDDEN_IN_CI")
        if args.confirm != LIVE_APPROVAL:
            raise ValueError("JEV_LIVE01_EXPLICIT_BILLABLE_APPROVAL_REQUIRED")
        if not args.expected_returned_model or args.expected_returned_model.upper() == "UNFROZEN":
            raise ValueError("JEV_LIVE01_RETURNED_MODEL_PIN_REQUIRED")
        if not load_typesafe_jev_api_key():
            raise ValueError("JEV_API_KEY_MISSING")
        evidence = {
            "provider_policy_checked_at": args.provider_policy_checked_at,
            "retention_status": args.retention_status,
            "model_discovery_ref": args.model_discovery_ref,
            "model_discovery_hash": args.model_discovery_hash,
        }
    else:
        evidence = dict.fromkeys((
            "provider_policy_checked_at", "retention_status",
            "model_discovery_ref", "model_discovery_hash"
        ), "MOCK_OR_PREFLIGHT_ONLY")
    output_dir = Path(tempfile.mkdtemp(prefix="stockscope-jev-live01-synthetic-"))
    db = output_dir / "synthetic_review.db"
    service, preview = prepare_synthetic_service(
        db, model_requested=args.model,
        expected_model_returned=(
            args.expected_returned_model if args.mode == "live" else "jev-mock-returned"
        ), evidence=evidence,
        budget_usd=args.budget_usd, reservation_usd=args.reservation_usd,
    )
    print(json.dumps({
        "mode": args.mode,
        "database": str(db),
        "preview": preview,
        "billable_provider_requests": 0 if args.mode != "live" else "AT_MOST_ONE_WHEN_EXECUTED",
        "reservation_is_not_actual_billing_cap": True,
    }, ensure_ascii=False, indent=2))
    if args.mode == "preflight":
        return 0

    original_key = os.environ.get("JEV_API_KEY")
    if args.mode == "mock":
        # MockTransport can never make a real HTTP request. Never expose actual key.
        os.environ["JEV_API_KEY"] = "local-http-mock-only"
    try:
        result = await execute_synthetic_service(
            service, preview,
            transport=_mock_transport() if args.mode == "mock" else None,
        )
    finally:
        if args.mode == "mock":
            if original_key is None:
                os.environ.pop("JEV_API_KEY", None)
            else:
                os.environ["JEV_API_KEY"] = original_key
    print(json.dumps({
        "mode": args.mode,
        "database": str(db),
        "verification": result,
        "billable_provider_requests": 0 if args.mode == "mock" else 1,
    }, ensure_ascii=False, indent=2))
    return 0 if result["stored_status"] == "VALID" else 2


def main() -> int:
    args = _parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except (ValueError, OSError) as exc:
        # Error codes only; never echo provider payload or secrets.
        print(f"JEV-LIVE-01 STOP: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
