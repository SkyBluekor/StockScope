from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.jev.models import digest_json
from app.jev.protocol_canonical import (
    JEV_PROTOCOL_CANONICALIZATION_VERSION,
    ProtocolCanonicalError,
    canonical_protocol_bytes_v2,
    canonical_protocol_json_v2,
    digest_protocol_json_v2,
    normalize_protocol_json_v2,
    validate_protocol_identity_v2,
)
from app.jev.typesafe_canary_v3 import (
    CANARY_V3_PROTOCOL_PATH,
    build_canary_v3_protocol_artifact,
)


def test_v2_canonicalizer_normalizes_integral_float_and_negative_zero() -> None:
    assert normalize_protocol_json_v2(10) == 10
    assert normalize_protocol_json_v2(10.0) == 10
    assert normalize_protocol_json_v2(0.0) == 0
    assert normalize_protocol_json_v2(-0.0) == 0
    assert canonical_protocol_json_v2({"n": 10.0}) == '{"n":10}'


def test_v2_canonicalizer_preserves_non_integral_numbers() -> None:
    value = {"a": 0.5, "b": 0.7, "c": 0.9, "d": 0.25}
    assert normalize_protocol_json_v2(value) == value
    assert canonical_protocol_json_v2(value) == '{"a":0.5,"b":0.7,"c":0.9,"d":0.25}'


def test_v2_canonicalizer_normalizes_nested_values() -> None:
    left = {"outer": [{"x": 10}, {"x": 2.0, "inner": [3.0, 4.5]}]}
    right = {"outer": [{"x": 10.0}, {"x": 2, "inner": [3, 4.5]}]}
    assert canonical_protocol_bytes_v2(left) == canonical_protocol_bytes_v2(right)
    assert digest_protocol_json_v2(left) == digest_protocol_json_v2(right)


def test_v2_canonicalizer_sorts_object_keys_but_preserves_array_order() -> None:
    assert canonical_protocol_json_v2({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert digest_protocol_json_v2({"b": 2, "a": 1}) == digest_protocol_json_v2(
        {"a": 1, "b": 2}
    )
    assert digest_protocol_json_v2([1, 2]) != digest_protocol_json_v2([2, 1])


def test_v2_canonicalizer_preserves_unicode_bool_and_none() -> None:
    text = canonical_protocol_json_v2(
        {"한글": "유지", "truth": True, "missing": None}
    )
    assert "한글" in text
    assert "유지" in text
    assert normalize_protocol_json_v2(True) is True
    assert normalize_protocol_json_v2(None) is None
    assert digest_protocol_json_v2(True) != digest_protocol_json_v2(1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_v2_canonicalizer_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ProtocolCanonicalError) as exc_info:
        canonical_protocol_json_v2({"value": value})
    assert exc_info.value.code == "PROTOCOL_CANONICAL_NUMBER_INVALID"


@pytest.mark.parametrize("value", [(1, 2), {1: "not-a-string-key"}, object()])
def test_v2_canonicalizer_rejects_unsupported_json_domain(value: object) -> None:
    with pytest.raises(ProtocolCanonicalError):
        canonical_protocol_json_v2(value)


def test_v2_canonicalizer_digest_is_deterministic_and_value_sensitive() -> None:
    value = {"a": 10.0, "b": ["x", 0.5]}
    assert digest_protocol_json_v2(value) == digest_protocol_json_v2(value)
    assert digest_protocol_json_v2(10) == digest_protocol_json_v2(10.0)
    assert digest_protocol_json_v2(10) != digest_protocol_json_v2(10.5)


def test_v2_protocol_identity_validator_accepts_normalized_numeric_equivalence() -> None:
    stored_spec = {"deadline_seconds": 10}
    runtime_spec = {"deadline_seconds": 10.0}
    protocol_hash = digest_protocol_json_v2(stored_spec)

    result = validate_protocol_identity_v2(
        stored_artifact={"protocol_hash": protocol_hash, "spec": stored_spec},
        runtime_artifact={"protocol_hash": protocol_hash, "spec": runtime_spec},
    )

    assert result["canonicalization_version"] == JEV_PROTOCOL_CANONICALIZATION_VERSION
    assert result["protocol_hash"] == protocol_hash


def test_v2_protocol_identity_validator_rejects_real_drift() -> None:
    stored_spec = {"deadline_seconds": 10}
    runtime_spec = {"deadline_seconds": 10.5}
    protocol_hash = digest_protocol_json_v2(stored_spec)

    with pytest.raises(ProtocolCanonicalError) as exc_info:
        validate_protocol_identity_v2(
            stored_artifact={"protocol_hash": protocol_hash, "spec": stored_spec},
            runtime_artifact={
                "protocol_hash": digest_protocol_json_v2(runtime_spec),
                "spec": runtime_spec,
            },
        )
    assert exc_info.value.code == "PROTOCOL_CANONICAL_DRIFT"


def test_v2_canonicalizer_closes_v3_int_float_equality_hole() -> None:
    stored = json.loads(
        Path(CANARY_V3_PROTOCOL_PATH).read_text(encoding="utf-8")
    )
    runtime = build_canary_v3_protocol_artifact()

    assert stored["spec"] == runtime["spec"]
    assert type(stored["spec"]["deadline_seconds"]) is int
    assert type(runtime["spec"]["deadline_seconds"]) is float

    assert stored["protocol_hash"] == (
        "3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356"
    )
    assert digest_json(stored["spec"]) == (
        "eb1ba813b9d2c803d0edf2c824ffaa233ae7bbcc0b2c2a9263e1cb0f07bb9e23"
    )
    assert digest_json(runtime["spec"]) == stored["protocol_hash"]

    assert canonical_protocol_bytes_v2(stored["spec"]) == canonical_protocol_bytes_v2(
        runtime["spec"]
    )
    assert digest_protocol_json_v2(stored["spec"]) == digest_protocol_json_v2(
        runtime["spec"]
    )
