from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT

from .evaluation_models import (
    JEV_EVALUATION_POLICY_ID,
    JEV_EVALUATION_REPORT_VERSION,
)
from .models import JEV_COMPARISON_POLICY, digest_json
from .trial import TRIAL_PROTOCOL_ID


EVALUATION_POLICY_PATH = (
    PROJECT_ROOT
    / "docs"
    / "contracts"
    / "JEV_REVIEWER_EVALUATION_POLICY_V1.json"
)
EVALUATION_POLICY_ARTIFACT_VERSION = (
    "JEV_REVIEWER_EVALUATION_POLICY_ARTIFACT_V1"
)


class JevEvaluationPolicyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_evaluation_policy(
    path: Path | None = None,
) -> dict[str, Any]:
    source = Path(path or EVALUATION_POLICY_PATH)
    if not source.is_file():
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_MISSING",
            f"JEV evaluation policy를 찾을 수 없습니다: {source}",
        )
    try:
        artifact = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_INVALID",
            "JEV evaluation policy를 읽거나 파싱할 수 없습니다.",
        ) from exc
    if not isinstance(artifact, dict):
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_INVALID",
            "JEV evaluation policy root는 object여야 합니다.",
        )
    if artifact.get("artifact_version") != EVALUATION_POLICY_ARTIFACT_VERSION:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_VERSION_MISMATCH",
            "지원하지 않는 JEV evaluation policy artifact입니다.",
        )
    if artifact.get("policy_id") != JEV_EVALUATION_POLICY_ID:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_ID_MISMATCH",
            "JEV evaluation policy identity가 일치하지 않습니다.",
        )
    if artifact.get("status") != "FROZEN":
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_NOT_FROZEN",
            "JEV evaluation policy가 FROZEN 상태가 아닙니다.",
        )

    spec = {
        key: value
        for key, value in artifact.items()
        if key not in {
            "artifact_version",
            "policy_id",
            "status",
            "policy_spec_hash",
        }
    }
    computed_hash = digest_json(spec)
    if computed_hash != str(artifact.get("policy_spec_hash") or ""):
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_POLICY_HASH_MISMATCH",
            "JEV evaluation policy hash가 일치하지 않습니다.",
        )
    if spec.get("trial_protocol_id") != TRIAL_PROTOCOL_ID:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_TRIAL_ID_MISMATCH",
            "JEV evaluation policy의 trial identity가 일치하지 않습니다.",
        )
    if spec.get("report_version") != JEV_EVALUATION_REPORT_VERSION:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_REPORT_VERSION_MISMATCH",
            "JEV evaluation report version이 일치하지 않습니다.",
        )
    if spec.get("comparison_policy") != JEV_COMPARISON_POLICY:
        raise JevEvaluationPolicyError(
            "JEV_EVALUATION_COMPARISON_POLICY_MISMATCH",
            "JEV comparison policy가 frozen trial과 일치하지 않습니다.",
        )
    return {
        **artifact,
        "spec": spec,
        "computed_policy_hash": computed_hash,
    }
