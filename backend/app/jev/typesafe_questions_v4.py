from __future__ import annotations

import json
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_models import JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4


STRATEGY_RELATION_CONFLICT = "strategy_relation_conflict"

JEV_TYPESAFE_QUESTION_IDS_V4 = (STRATEGY_RELATION_CONFLICT,)

JEV_TYPESAFE_QUESTIONS_V4: dict[str, dict[str, Any]] = {
    STRATEGY_RELATION_CONFLICT: {
        "type": "noul",
        "instructions": (
            "Using only strategy_intent, term_definitions, authored_relations, and "
            "passed_condition_meanings, judge whether the supplied meanings contain "
            "an explicit, material semantic conflict with the authored strategy "
            "relations that deserves a user re-check. StockScope has already handled "
            "deterministic matches, conflicts, missing information, and internally "
            "ambiguous states before this question. Do not recalculate thresholds, "
            "infer prices, invent missing definitions or relations, use outside market "
            "information, or infer a local verdict that is not present in the wire."
        ),
        "criteria": {
            "true": (
                "The supplied meanings, interpreted with the authored definitions and "
                "relations, materially contradict or violate the authored strategy "
                "semantics and deserve a user re-check."
            ),
            "false": (
                "The supplied meanings remain compatible with the authored strategy "
                "semantics, including explicitly allowed relationships and exceptions."
            ),
        },
    },
}

JEV_TYPESAFE_QUESTION_SET_HASH_V4 = digest_json(
    {
        "contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
        "questions": JEV_TYPESAFE_QUESTIONS_V4,
    }
)


def build_typesafe_questions_v4() -> dict[str, dict[str, Any]]:
    return json.loads(canonical_json(JEV_TYPESAFE_QUESTIONS_V4))
