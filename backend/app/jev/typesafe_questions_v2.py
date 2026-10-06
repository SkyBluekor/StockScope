from __future__ import annotations

import json
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_models import JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2


STRATEGY_CONTEXT_CONFLICT = "strategy_context_conflict"
ENTRY_CONTEXT_CONFLICT = "entry_context_conflict"
OVERALL_SEMANTIC_REVIEW_INSUFFICIENT = "overall_semantic_review_insufficient"

JEV_TYPESAFE_QUESTION_IDS_V2 = (
    STRATEGY_CONTEXT_CONFLICT,
    ENTRY_CONTEXT_CONFLICT,
    OVERALL_SEMANTIC_REVIEW_INSUFFICIENT,
)

JEV_TYPESAFE_QUESTIONS_V2: dict[str, dict[str, Any]] = {
    STRATEGY_CONTEXT_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Using only the supplied strategy_context and condition_context, judge "
            "whether the meaning of the already-passed condition context has an "
            "explicit, material conflict with the stated strategy description that "
            "deserves a user re-check. Do not recalculate numeric pass/fail. Do not "
            "invent missing intent, definitions, market context, news, company "
            "identity, or future returns. Entry-role comparison belongs to the "
            "entry-context question."
        ),
        "criteria": {
            "true": (
                "The supplied condition meaning contradicts or excludes the intent "
                "stated in the strategy description."
            ),
            "false": (
                "The supplied meaning is consistent or explicitly allowed, or a "
                "required intent/definition is missing so an explicit conflict "
                "cannot be established from the supplied evidence alone. Ordinary "
                "future uncertainty is not a conflict."
            ),
        },
    },
    ENTRY_CONTEXT_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Compare the confirmation-versus-execution meaning of the same price "
            "rule as stated in strategy_context.strategy_description with the "
            "meaning represented by entry_context.price_rule. Judge only whether "
            "those supplied meanings materially conflict. baseline only establishes "
            "that this is an ENTRY_CANDIDATE; it does not itself declare an order "
            "or executable range. Do not invent UI wording, user confusion, missing "
            "rule links, prices, stops, targets, risk/reward, or future returns."
        ),
        "criteria": {
            "true": (
                "Both sides identify the same rule and their supplied meanings are "
                "opposed, such as a confirmation-only rule being represented as an "
                "executable entry range."
            ),
            "false": (
                "The supplied meanings agree, or a required same-rule link or other "
                "meaning is missing so an explicit conflict cannot be established. "
                "RANGE, SEPARATED, NEAR, overlap, or ENTRY_CANDIDATE alone is not "
                "positive evidence."
            ),
        },
    },
    OVERALL_SEMANTIC_REVIEW_INSUFFICIENT: {
        "type": "noul",
        "instructions": (
            "Using only the supplied state, judge whether no explicit material "
            "conflict can be established for either limited review proposition and "
            "at least one proposition still lacks an essential intent, term, or "
            "rule link, so the overall semantic review cannot be completed without "
            "inventing missing meaning. A clear conflict supported by the supplied "
            "evidence makes this proposition false even if the other comparison is "
            "incomplete. Do not treat ordinary future uncertainty or deliberately "
            "excluded news, identity, account, portfolio, or detailed price data as "
            "insufficient evidence."
        ),
        "criteria": {
            "true": (
                "No evidence-supported conflict is established, and an essential "
                "meaning or same-rule relationship is missing such that different "
                "reasonable completions could change at least one comparison."
            ),
            "false": (
                "At least one evidence-supported conflict is already established, "
                "or the supplied meaning is sufficient to complete both limited "
                "comparisons. False does not certify that every omitted detail is "
                "known."
            ),
        },
    },
}

JEV_TYPESAFE_QUESTION_SET_HASH_V2 = digest_json(
    {
        "contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        "questions": JEV_TYPESAFE_QUESTIONS_V2,
    }
)


def build_typesafe_questions_v2() -> dict[str, dict[str, Any]]:
    return json.loads(canonical_json(JEV_TYPESAFE_QUESTIONS_V2))
