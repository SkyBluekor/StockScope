from __future__ import annotations

import math
from typing import Any

from .protocol_canonical import digest_protocol_json_v2


JEV_REVIEW_IDENTITY_VERSION = "JEV_REVIEW_IDENTITY_V1"


def build_review_identity(
    *,
    semantic_source_snapshot_hash: str,
    relation_contract_hash: str,
    question_set_hash: str,
    disposition_policy_hash: str,
    threshold_strategy: float,
    requested_model_channel: str,
    review_epoch: int,
) -> dict[str, Any]:
    source_hash = str(semantic_source_snapshot_hash or "").strip()
    relation_hash = str(relation_contract_hash or "").strip()
    question_hash = str(question_set_hash or "").strip()
    policy_hash = str(disposition_policy_hash or "").strip()
    model_channel = str(requested_model_channel or "").strip()

    if not source_hash:
        raise ValueError("JEV_REVIEW_SOURCE_HASH_REQUIRED")
    if not relation_hash:
        raise ValueError("JEV_REVIEW_RELATION_HASH_REQUIRED")
    if not question_hash:
        raise ValueError("JEV_REVIEW_QUESTION_HASH_REQUIRED")
    if not policy_hash:
        raise ValueError("JEV_REVIEW_POLICY_HASH_REQUIRED")
    if not model_channel:
        raise ValueError("JEV_REVIEW_MODEL_CHANNEL_REQUIRED")
    if isinstance(threshold_strategy, bool) or not isinstance(
        threshold_strategy, (int, float)
    ):
        raise ValueError("JEV_REVIEW_THRESHOLD_INVALID")
    threshold = float(threshold_strategy)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("JEV_REVIEW_THRESHOLD_INVALID")
    if isinstance(review_epoch, bool) or not isinstance(review_epoch, int):
        raise ValueError("JEV_REVIEW_EPOCH_INVALID")
    if review_epoch < 0:
        raise ValueError("JEV_REVIEW_EPOCH_INVALID")

    payload = {
        "identity_version": JEV_REVIEW_IDENTITY_VERSION,
        "semantic_source_snapshot_hash": source_hash,
        "relation_contract_hash": relation_hash,
        "question_set_hash": question_hash,
        "disposition_policy_hash": policy_hash,
        "threshold_strategy": threshold,
        "requested_model_channel": model_channel,
        "review_epoch": review_epoch,
    }
    return {
        "identity_version": JEV_REVIEW_IDENTITY_VERSION,
        "review_identity": digest_protocol_json_v2(payload),
        "identity_payload": payload,
    }
