from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT

from .catalog import JevCatalog, JevCatalogError
from .models import JEV_ADAPTER_VERSION, JevTrialProtocolSpec, digest_json
from .prompt import (
    JEV_OUTPUT_SCHEMA_HASH,
    JEV_PROMPT_HASH,
    JEV_PROMPT_VERSION,
)
from .provider import (
    OPENAI_RESPONSES_PROVIDER_ID,
    OPENAI_TERRA_MODEL_ID,
)


TRIAL_ARTIFACT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "contracts"
    / "JEV_REVIEWER_TRIAL_PROTOCOL_V1.json"
)
TRIAL_PROTOCOL_ID = "JEV-REVIEWER-TRIAL-V1"
TRIAL_ARTIFACT_VERSION = "JEV_REVIEWER_TRIAL_PROTOCOL_ARTIFACT_V1"


class JevTrialError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_trial_artifact(
    path: Path | None = None,
) -> dict[str, Any]:
    source = Path(path or TRIAL_ARTIFACT_PATH)
    if not source.is_file():
        raise JevTrialError(
            "JEV_TRIAL_ARTIFACT_MISSING",
            f"JEV trial artifact를 찾을 수 없습니다: {source}",
        )
    try:
        artifact = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JevTrialError(
            "JEV_TRIAL_ARTIFACT_INVALID",
            "JEV trial artifact를 읽거나 파싱할 수 없습니다.",
        ) from exc

    if not isinstance(artifact, dict):
        raise JevTrialError(
            "JEV_TRIAL_ARTIFACT_INVALID",
            "JEV trial artifact root는 object여야 합니다.",
        )
    if artifact.get("artifact_version") != TRIAL_ARTIFACT_VERSION:
        raise JevTrialError(
            "JEV_TRIAL_ARTIFACT_VERSION_MISMATCH",
            "지원하지 않는 JEV trial artifact version입니다.",
        )
    if artifact.get("protocol_id") != TRIAL_PROTOCOL_ID:
        raise JevTrialError(
            "JEV_TRIAL_PROTOCOL_ID_MISMATCH",
            "JEV trial protocol identity가 일치하지 않습니다.",
        )
    if artifact.get("status") != "FROZEN_READY_FOR_ACTIVATION":
        raise JevTrialError(
            "JEV_TRIAL_NOT_FROZEN",
            "JEV trial artifact가 activation-ready 상태가 아닙니다.",
        )

    spec_raw = artifact.get("spec")
    if not isinstance(spec_raw, dict):
        raise JevTrialError(
            "JEV_TRIAL_SPEC_INVALID",
            "JEV trial spec가 없습니다.",
        )
    actual_hash = digest_json(spec_raw)
    if actual_hash != str(artifact.get("spec_hash") or ""):
        raise JevTrialError(
            "JEV_TRIAL_SPEC_HASH_MISMATCH",
            "JEV trial spec hash가 일치하지 않습니다.",
        )

    expected = {
        "provider_id": OPENAI_RESPONSES_PROVIDER_ID,
        "model_id": OPENAI_TERRA_MODEL_ID,
        "prompt_version": JEV_PROMPT_VERSION,
        "prompt_hash": JEV_PROMPT_HASH,
        "adapter_version": JEV_ADAPTER_VERSION,
    }
    for field, value in expected.items():
        if str(spec_raw.get(field) or "") != value:
            raise JevTrialError(
                "JEV_TRIAL_IDENTITY_MISMATCH",
                f"JEV trial identity 불일치: {field}",
            )

    settings = spec_raw.get("generation_settings")
    if not isinstance(settings, dict):
        raise JevTrialError(
            "JEV_TRIAL_GENERATION_SETTINGS_INVALID",
            "JEV generation settings가 없습니다.",
        )
    if settings.get("store") is not False:
        raise JevTrialError(
            "JEV_TRIAL_STORE_POLICY_INVALID",
            "JEV Responses API는 store=false로 고정되어야 합니다.",
        )
    if (
        str(settings.get("structured_output_schema_hash") or "")
        != JEV_OUTPUT_SCHEMA_HASH
    ):
        raise JevTrialError(
            "JEV_TRIAL_OUTPUT_SCHEMA_MISMATCH",
            "JEV output schema identity가 일치하지 않습니다.",
        )
    if not bool(spec_raw.get("source_transmission_approved")):
        raise JevTrialError(
            "JEV_SOURCE_TRANSMISSION_NOT_APPROVED",
            "JEV source transmission gate가 닫혀 있습니다.",
        )

    normalized = dict(spec_raw)
    normalized["horizon_intents"] = tuple(
        str(value)
        for value in (spec_raw.get("horizon_intents") or [])
    )
    try:
        spec = JevTrialProtocolSpec(**normalized)
    except TypeError as exc:
        raise JevTrialError(
            "JEV_TRIAL_SPEC_INVALID",
            "JEV trial spec field가 현재 코드와 일치하지 않습니다.",
        ) from exc
    gaps = spec.freeze_gaps()
    if gaps:
        raise JevTrialError(
            "JEV_TRIAL_FREEZE_INCOMPLETE",
            "JEV trial freeze 필드가 누락되었습니다: "
            + ", ".join(gaps),
        )

    return {
        **artifact,
        "spec_object": spec,
        "computed_spec_hash": actual_hash,
    }


def trial_readiness() -> dict[str, Any]:
    try:
        artifact = load_trial_artifact()
    except JevTrialError as exc:
        return {
            "ready": False,
            "status": "NOT_READY",
            "code": exc.code,
            "protocol_id": TRIAL_PROTOCOL_ID,
        }
    return {
        "ready": True,
        "status": "READY_FOR_ACTIVATION",
        "code": None,
        "protocol_id": TRIAL_PROTOCOL_ID,
        "spec_hash": artifact["computed_spec_hash"],
        "provider_id": artifact["spec"]["provider_id"],
        "model_id": artifact["spec"]["model_id"],
        "model_revision": artifact["spec"]["model_revision"],
        "prompt_version": artifact["spec"]["prompt_version"],
    }


def configure_trial_protocol(
    catalog: JevCatalog,
) -> dict[str, Any]:
    artifact = load_trial_artifact()
    spec = artifact["spec_object"]

    summary = catalog.status_summary()
    activation = summary.get("activation")
    if isinstance(activation, dict) and bool(activation.get("enabled")):
        raise JevTrialError(
            "JEV_TRIAL_ALREADY_ACTIVE",
            "활성 JEV trial이 있는 동안 configure 작업으로 상태를 바꾸지 않습니다.",
        )

    protocol = catalog.create_protocol(
        client_request_id=TRIAL_PROTOCOL_ID,
        spec=spec,
    )
    if protocol["spec_hash"] != artifact["computed_spec_hash"]:
        raise JevTrialError(
            "JEV_TRIAL_PROTOCOL_CONFLICT",
            "runtime JEV protocol과 frozen artifact의 hash가 다릅니다.",
        )
    if protocol["status"] != "FROZEN":
        raise JevTrialError(
            "JEV_TRIAL_PROTOCOL_NOT_FROZEN",
            "runtime JEV protocol이 FROZEN 상태가 아닙니다.",
        )

    catalog.set_activation(
        protocol["id"],
        enabled=False,
        allow_network=False,
    )
    return {
        "status": "READY_FOR_ACTIVATION",
        "protocol_id": protocol["id"],
        "protocol_spec_hash": protocol["spec_hash"],
        "network_enabled": False,
        "model_calls_executed": 0,
    }
