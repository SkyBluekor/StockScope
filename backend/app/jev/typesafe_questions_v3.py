from __future__ import annotations

import json
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_models import JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3


STRATEGY_CONTEXT_CONFLICT = "strategy_context_conflict"

JEV_TYPESAFE_QUESTION_IDS_V3 = (STRATEGY_CONTEXT_CONFLICT,)

JEV_TYPESAFE_QUESTIONS_V3: dict[str, dict[str, Any]] = {
    STRATEGY_CONTEXT_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Using only strategy_intent, term_definitions, and "
            "passed_condition_meanings, judge whether the supplied meanings contain "
            "an explicit, material semantic conflict with the authored strategy "
            "intent that deserves a user re-check. The conditions have already been "
            "evaluated as passed by StockScope. Do not recalculate thresholds, infer "
            "prices, invent missing definitions, use outside market information, or "
            "treat ordinary future uncertainty as a conflict."
        ),
        "criteria": {
            "true": (
                "At least one supplied passed meaning, alone or in combination with "
                "the other supplied meanings and definitions, materially contradicts "
                "or excludes the authored strategy intent."
            ),
            "false": (
                "The supplied passed meanings are compatible with or explicitly "
                "allowed by the authored intent. Missing semantic dependencies are "
                "handled locally before this question and must not be guessed here."
            ),
        },
    },
}

JEV_TYPESAFE_QUESTION_SET_HASH_V3 = digest_json(
    {
        "contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
        "questions": JEV_TYPESAFE_QUESTIONS_V3,
    }
)


def build_typesafe_questions_v3() -> dict[str, dict[str, Any]]:
    return json.loads(canonical_json(JEV_TYPESAFE_QUESTIONS_V3))
