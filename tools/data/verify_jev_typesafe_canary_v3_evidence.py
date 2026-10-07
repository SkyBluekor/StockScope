from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_PROTOCOL_ID = "JEV-TYPESAFE-CANARY-V3"
EXPECTED_PROTOCOL_HASH = (
    "3d1b711535e56931d9ba3e4e8d8db184e94f54f1f826d34478ad4bba8a09f356"
)
EXPECTED_REPORT_VERSION = "JEV_TYPESAFE_CANARY_REPORT_V3"
EXPECTED_BINDING_VERSION = "JEV_TYPESAFE_MODEL_BINDING_ARTIFACT_V3"
EXPECTED_PROVIDER = "TYPESAFE_SYSTEM_ONE"
EXPECTED_REQUEST_MODEL = "jev-latest"
EXPECTED_RESPONSE_MODEL = "jev-1.13.0"

EXPECTED_INPUT_TOKENS = 44043
EXPECTED_OUTPUT_TOKENS = 1656

REPORT_RELATIVE_PATH = Path(
    "docs/validation/JEV_TYPESAFE_CANARY_V3_2026-10-07.json"
)
BINDING_RELATIVE_PATH = Path(
    "docs/contracts/JEV_TYPESAFE_MODEL_BINDING_V3.json"
)

_SENSITIVE_KEYS = frozenset(
    {
        "jev_api_key",
        "api_key",
        "authorization",
        "authorization_header",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
    }
)
_ALLOWED_RECORD_KEYS = frozenset(
    {
        "fixture_id",
        "partition",
        "projected_state_hash",
        "repetition",
        "model_requested",
        "model_returned",
        "probability",
        "usage",
        "latency_ms",
    }
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+\S+")
_JEV_KEY_ASSIGNMENT_RE = re.compile(r"(?i)\bJEV_API_KEY\s*[:=]")


class EvidenceVerificationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EvidenceVerificationError(code)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceVerificationError("V3_EVIDENCE_FILE_MISSING")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceVerificationError("V3_EVIDENCE_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise EvidenceVerificationError("V3_EVIDENCE_JSON_INVALID")
    return value


def _scan_sensitive_material(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _SENSITIVE_KEYS:
                raise EvidenceVerificationError("V3_EVIDENCE_SECRET_MATERIAL_PRESENT")
            if normalized == "credential":
                if str(child).strip().upper() not in {"PRESENT", "ABSENT"}:
                    raise EvidenceVerificationError(
                        "V3_EVIDENCE_SECRET_MATERIAL_PRESENT"
                    )
            _scan_sensitive_material(child)
        return

    if isinstance(value, list):
        for child in value:
            _scan_sensitive_material(child)
        return

    if isinstance(value, str):
        if _BEARER_RE.search(value) or _JEV_KEY_ASSIGNMENT_RE.search(value):
            raise EvidenceVerificationError("V3_EVIDENCE_SECRET_MATERIAL_PRESENT")


def _verify_binding(binding: dict[str, Any]) -> None:
    _require(
        binding.get("artifact_version") == EXPECTED_BINDING_VERSION,
        "V3_EVIDENCE_BINDING_VERSION_MISMATCH",
    )
    _require(
        binding.get("status") == "OBSERVED_CANARY_BINDING",
        "V3_EVIDENCE_BINDING_STATUS_MISMATCH",
    )
    _require(
        binding.get("provider_id") == EXPECTED_PROVIDER,
        "V3_EVIDENCE_PROVIDER_MISMATCH",
    )
    _require(
        binding.get("selected_request_model") == EXPECTED_REQUEST_MODEL,
        "V3_EVIDENCE_REQUEST_MODEL_MISMATCH",
    )
    _require(
        binding.get("request_channel_class") == "STABLE_ALIAS",
        "V3_EVIDENCE_REQUEST_CHANNEL_MISMATCH",
    )
    _require(
        binding.get("observed_response_model") == EXPECTED_RESPONSE_MODEL,
        "V3_EVIDENCE_RESPONSE_MODEL_MISMATCH",
    )
    _require(
        binding.get("canary_protocol_hash") == EXPECTED_PROTOCOL_HASH,
        "V3_EVIDENCE_PROTOCOL_HASH_MISMATCH",
    )


def _verify_records(report: dict[str, Any]) -> None:
    records = report.get("records")
    _require(isinstance(records, dict), "V3_EVIDENCE_RECORDS_INVALID")

    combined: list[dict[str, Any]] = []
    for partition in ("selection", "validation"):
        rows = records.get(partition)
        _require(isinstance(rows, list), "V3_EVIDENCE_RECORDS_INVALID")
        _require(len(rows) == 36, "V3_EVIDENCE_RECORD_COUNT_MISMATCH")
        fixture_counts: Counter[str] = Counter()
        for row in rows:
            _require(isinstance(row, dict), "V3_EVIDENCE_RECORDS_INVALID")
            _require(
                set(row) <= _ALLOWED_RECORD_KEYS,
                "V3_EVIDENCE_RECORD_SHAPE_INVALID",
            )
            _require(
                row.get("partition") == partition,
                "V3_EVIDENCE_RECORD_PARTITION_MISMATCH",
            )
            fixture_id = str(row.get("fixture_id") or "")
            expected_prefix = "v3-s" if partition == "selection" else "v3-v"
            _require(
                fixture_id.startswith(expected_prefix),
                "V3_EVIDENCE_RECORD_FIXTURE_INVALID",
            )
            fixture_counts[fixture_id] += 1
            _require(
                row.get("model_requested") == EXPECTED_REQUEST_MODEL,
                "V3_EVIDENCE_RECORD_MODEL_MISMATCH",
            )
            _require(
                row.get("model_returned") == EXPECTED_RESPONSE_MODEL,
                "V3_EVIDENCE_RECORD_MODEL_MISMATCH",
            )
            probability = row.get("probability")
            _require(
                isinstance(probability, (int, float))
                and not isinstance(probability, bool)
                and math.isfinite(float(probability))
                and 0.0 <= float(probability) <= 1.0,
                "V3_EVIDENCE_RECORD_PROBABILITY_INVALID",
            )
            usage = row.get("usage")
            _require(isinstance(usage, dict), "V3_EVIDENCE_RECORD_USAGE_INVALID")
            _require(
                isinstance(usage.get("input_tokens"), int)
                and usage["input_tokens"] >= 0
                and isinstance(usage.get("output_tokens"), int)
                and usage["output_tokens"] >= 0,
                "V3_EVIDENCE_RECORD_USAGE_INVALID",
            )
            combined.append(row)

        _require(
            len(fixture_counts) == 12 and set(fixture_counts.values()) == {3},
            "V3_EVIDENCE_RECORD_REPETITION_MISMATCH",
        )

    input_tokens = sum(row["usage"]["input_tokens"] for row in combined)
    output_tokens = sum(row["usage"]["output_tokens"] for row in combined)
    _require(
        input_tokens == EXPECTED_INPUT_TOKENS,
        "V3_EVIDENCE_INPUT_USAGE_MISMATCH",
    )
    _require(
        output_tokens == EXPECTED_OUTPUT_TOKENS,
        "V3_EVIDENCE_OUTPUT_USAGE_MISMATCH",
    )


def verify_evidence(repo_root: Path) -> None:
    report = _load_json(repo_root / REPORT_RELATIVE_PATH)
    binding = _load_json(repo_root / BINDING_RELATIVE_PATH)

    _scan_sensitive_material(report)
    _scan_sensitive_material(binding)
    _verify_binding(binding)

    _require(
        report.get("report_version") == EXPECTED_REPORT_VERSION,
        "V3_EVIDENCE_REPORT_VERSION_MISMATCH",
    )
    _require(
        report.get("status") == "FAIL",
        "V3_EVIDENCE_STATUS_MISMATCH",
    )
    _require(
        report.get("canary_protocol_id") == EXPECTED_PROTOCOL_ID,
        "V3_EVIDENCE_PROTOCOL_ID_MISMATCH",
    )
    _require(
        report.get("canary_protocol_hash") == EXPECTED_PROTOCOL_HASH,
        "V3_EVIDENCE_PROTOCOL_HASH_MISMATCH",
    )
    _require(
        report.get("model_binding") == binding,
        "V3_EVIDENCE_BINDING_FILE_MISMATCH",
    )

    attempts = report.get("api_attempts")
    _require(
        attempts
        == {
            "model_discovery": 1,
            "systemone": 72,
            "total": 73,
            "hard_cap": 73,
        },
        "V3_EVIDENCE_ATTEMPT_COUNT_MISMATCH",
    )
    counts = report.get("systemone_counts")
    _require(
        counts
        == {
            "planned": 72,
            "attempted": 72,
            "completed": 72,
            "valid": 72,
            "failed": 0,
        },
        "V3_EVIDENCE_SYSTEMONE_COUNT_MISMATCH",
    )
    _require(
        report.get("selected_threshold") == {"threshold_strategy": 0.9},
        "V3_EVIDENCE_THRESHOLD_MISMATCH",
    )
    _require(
        report.get("errors") == ["CANARY_V3_VALIDATION_FAILED"],
        "V3_EVIDENCE_ERROR_MISMATCH",
    )
    _require(
        report.get("real_stock_data_sent") is False,
        "V3_EVIDENCE_REAL_STOCK_FLAG_INVALID",
    )
    _require(
        report.get("actual_trial_activation") is False,
        "V3_EVIDENCE_TRIAL_FLAG_INVALID",
    )
    _require(
        report.get("final_threshold_frozen") is False,
        "V3_EVIDENCE_FINAL_THRESHOLD_FLAG_INVALID",
    )
    _require(
        report.get("trial_freeze_readiness") == "BLOCKED_CANARY_FAILED",
        "V3_EVIDENCE_TRIAL_READINESS_MISMATCH",
    )
    _require(
        report.get("usage")
        == {
            "input_tokens": EXPECTED_INPUT_TOKENS,
            "output_tokens": EXPECTED_OUTPUT_TOKENS,
        },
        "V3_EVIDENCE_USAGE_MISMATCH",
    )

    selection = report.get("selection_analysis")
    validation = report.get("validation_analysis")
    _require(
        isinstance(selection, dict)
        and isinstance(selection.get("selected"), dict)
        and selection["selected"].get("threshold_strategy") == 0.9
        and selection["selected"].get("eligible") is True,
        "V3_EVIDENCE_SELECTION_ANALYSIS_MISMATCH",
    )
    _require(
        isinstance(validation, dict)
        and validation.get("threshold_strategy") == 0.9
        and validation.get("hard_proposition_checks") == 30
        and validation.get("hard_proposition_mismatches") == 12
        and validation.get("hard_false_reviews") == 0
        and validation.get("hard_missed_reviews") == 12
        and validation.get("hard_disposition_reason_errors") == 12
        and validation.get("review_required_count") == 0
        and validation.get("eligible") is False,
        "V3_EVIDENCE_VALIDATION_ANALYSIS_MISMATCH",
    )

    budget = report.get("budget")
    _require(isinstance(budget, dict), "V3_EVIDENCE_BUDGET_INVALID")
    _require(
        math.isclose(
            float(budget.get("per_call_reservation_usd")),
            0.001,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "V3_EVIDENCE_BUDGET_INVALID",
    )
    _require(
        math.isclose(
            float(budget.get("reserved_exposure_usd")),
            0.072,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "V3_EVIDENCE_BUDGET_INVALID",
    )
    _require(
        budget.get("actual_provider_cost_usd") is None
        and budget.get("actual_provider_cost_status") == "UNKNOWN",
        "V3_EVIDENCE_PROVIDER_COST_INVALID",
    )

    _verify_records(report)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        verify_evidence(repo_root)
    except EvidenceVerificationError as exc:
        print(f"TYPE-JEV CANARY V3 EVIDENCE VERIFY FAIL: {exc.code}")
        return 1

    print("TYPE-JEV CANARY V3 EVIDENCE VERIFY PASS")
    print("network_calls=0")
    print("env_access=0")
    print("secret_material=false")
    print("real_stock_data_sent=false")
    print("status=FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
