from __future__ import annotations

import json
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_models import JEV_TYPESAFE_QUESTION_CONTRACT_VERSION


STRATEGY_CONTEXT_CONFLICT = "strategy_context_conflict"
ENTRY_CONTEXT_CONFLICT = "entry_context_conflict"
REVIEW_EVIDENCE_INSUFFICIENT = "review_evidence_insufficient"

JEV_TYPESAFE_QUESTION_IDS = (
    STRATEGY_CONTEXT_CONFLICT,
    ENTRY_CONTEXT_CONFLICT,
    REVIEW_EVIDENCE_INSUFFICIENT,
)

JEV_TYPESAFE_QUESTIONS: dict[str, dict[str, Any]] = {
    STRATEGY_CONTEXT_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Using only the supplied strategy_context and condition_context, judge "
            "whether the meaning of the already-passed condition context materially "
            "conflicts with the stated strategy description. Do not recalculate "
            "whether any numeric condition passes. Do not infer missing market data, "
            "news, company identity, or future returns. Do not judge whether the "
            "stock is attractive or recommend a trade. Answer only the proposition "
            "about semantic conflict."
        ),
        "criteria": {
            "true": (
                "The supplied passed-condition context contains a meaningful "
                "combination or qualification that is difficult to reconcile with "
                "the stated strategy description and therefore deserves a human "
                "re-check."
            ),
            "false": (
                "The supplied passed-condition context is semantically consistent "
                "with the stated strategy description; numeric eligibility remains "
                "owned by StockScope's deterministic rules."
            ),
        },
    },
    ENTRY_CONTEXT_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Using only entry_context and baseline, judge whether the semantic role "
            "of the strategy price rule materially conflicts with the "
            "ENTRY_CANDIDATE presentation. The local program has already validated "
            "arithmetic price relationships. Do not recompute prices, stops, "
            "targets, risk/reward, or eligibility. A strategy condition band or "
            "threshold is not an executable buy range unless the supplied state "
            "explicitly says so. Do not recommend a trade or predict returns. "
            "Answer only the proposition about semantic presentation conflict."
        ),
        "criteria": {
            "true": (
                "The supplied entry semantics could materially mislead a user about "
                "what the ENTRY_CANDIDATE state means, even though deterministic "
                "price validation itself has already passed."
            ),
            "false": (
                "The supplied entry semantics and ENTRY_CANDIDATE presentation are "
                "mutually consistent and do not add a material semantic warning."
            ),
        },
    },
    REVIEW_EVIDENCE_INSUFFICIENT: {
        "type": "noul",
        "instructions": (
            "Using only the supplied state, judge whether the semantic context is "
            "inherently insufficient to evaluate the two limited review propositions "
            "reliably. Do not treat ordinary uncertainty about future price movement "
            "as insufficient evidence. Do not request news, company identity, "
            "account data, holdings, or future outcomes. Judge only whether the "
            "provided semantic context is sufficient for the limited "
            "strategy-context and entry-context review."
        ),
        "criteria": {
            "true": (
                "The supplied semantic context is too incomplete or ambiguous to "
                "support the limited review without inventing missing meaning."
            ),
            "false": (
                "The supplied semantic context is adequate for the limited review, "
                "even if the result may still be uncertain."
            ),
        },
    },
}

JEV_TYPESAFE_QUESTION_SET_HASH = digest_json(
    {
        "contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION,
        "questions": JEV_TYPESAFE_QUESTIONS,
    }
)


def build_typesafe_questions() -> dict[str, dict[str, Any]]:
    return json.loads(canonical_json(JEV_TYPESAFE_QUESTIONS))
