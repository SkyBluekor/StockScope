from __future__ import annotations

import hashlib
import json
import math
from typing import Any


JEV_PROTOCOL_CANONICALIZATION_VERSION = "JEV_PROTOCOL_CANONICAL_JSON_V2"
JEV_PROTOCOL_HASH_ALGORITHM = "SHA-256"


class ProtocolCanonicalError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_protocol_json_v2(value: Any) -> Any:
    """Normalize protocol data into the V2 canonical JSON value domain."""
    if value is None or isinstance(value, (str, bool)):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolCanonicalError("PROTOCOL_CANONICAL_NUMBER_INVALID")
        if value == 0.0 or value.is_integer():
            return int(value)
        return value

    if isinstance(value, list):
        return [normalize_protocol_json_v2(item) for item in value]

    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ProtocolCanonicalError("PROTOCOL_CANONICAL_KEY_INVALID")
        return {
            key: normalize_protocol_json_v2(value[key])
            for key in sorted(value)
        }

    raise ProtocolCanonicalError("PROTOCOL_CANONICAL_TYPE_UNSUPPORTED")


def canonical_protocol_json_v2(value: Any) -> str:
    normalized = normalize_protocol_json_v2(value)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolCanonicalError("PROTOCOL_CANONICAL_SERIALIZATION_FAILED") from exc


def canonical_protocol_bytes_v2(value: Any) -> bytes:
    return canonical_protocol_json_v2(value).encode("utf-8")


def digest_protocol_json_v2(value: Any) -> str:
    return hashlib.sha256(canonical_protocol_bytes_v2(value)).hexdigest()


def validate_protocol_identity_v2(
    *,
    stored_artifact: dict[str, Any],
    runtime_artifact: dict[str, Any],
) -> dict[str, str]:
    """Validate a V2-canonical frozen protocol artifact.

    This validator is for protocols whose protocol_hash was created with
    JEV_PROTOCOL_CANONICAL_JSON_V2. Historical V1/V2/V3 protocol hashes are
    intentionally not rewritten through this function.
    """
    if not isinstance(stored_artifact, dict) or not isinstance(runtime_artifact, dict):
        raise ProtocolCanonicalError("PROTOCOL_ARTIFACT_INVALID")

    stored_spec = stored_artifact.get("spec")
    runtime_spec = runtime_artifact.get("spec")
    if not isinstance(stored_spec, dict) or not isinstance(runtime_spec, dict):
        raise ProtocolCanonicalError("PROTOCOL_SPEC_INVALID")

    stored_bytes = canonical_protocol_bytes_v2(stored_spec)
    runtime_bytes = canonical_protocol_bytes_v2(runtime_spec)
    if stored_bytes != runtime_bytes:
        raise ProtocolCanonicalError("PROTOCOL_CANONICAL_DRIFT")

    stored_digest = hashlib.sha256(stored_bytes).hexdigest()
    runtime_digest = hashlib.sha256(runtime_bytes).hexdigest()
    stored_hash = str(stored_artifact.get("protocol_hash") or "")
    runtime_hash = str(runtime_artifact.get("protocol_hash") or "")

    if not stored_hash:
        raise ProtocolCanonicalError("PROTOCOL_HASH_MISSING")
    if stored_hash != stored_digest:
        raise ProtocolCanonicalError("STORED_PROTOCOL_HASH_INVALID")
    if runtime_hash and runtime_hash != runtime_digest:
        raise ProtocolCanonicalError("RUNTIME_PROTOCOL_HASH_INVALID")
    if stored_digest != runtime_digest:
        raise ProtocolCanonicalError("PROTOCOL_CANONICAL_DRIFT")

    return {
        "canonicalization_version": JEV_PROTOCOL_CANONICALIZATION_VERSION,
        "hash_algorithm": JEV_PROTOCOL_HASH_ALGORITHM,
        "protocol_hash": stored_digest,
        "stored_artifact_hash": digest_protocol_json_v2(stored_artifact),
        "runtime_artifact_hash": digest_protocol_json_v2(runtime_artifact),
    }
