"""S7.4 P0/P1: offline rights inventory and field-by-field Scanner lineage.

This is a diagnostic, not a rights authority or provider request adapter.
Expected upstream paths are based on reviewed source code, NOT certified
provenance of any particular legacy database row or a legal grant.
Do not import provider clients or access credential stores here.
"""
from __future__ import annotations

from copy import deepcopy
import re
from pathlib import Path
from typing import Any

from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.scanner_shadow_s7 import load_frozen_candidates
from app.jev.scanner_shadow_s7_3 import (
    PACKET_VERSION, QUESTION_HASH, prepare_shadow_candidate,
)
from app.prospective.models import digest_json

VERSION = "JEV_ACT2_S7_4_P0_P1_LINEAGE_V1"
CONTRACT_REF = "docs/설계/JEV-ACT2-S7.4_데이터_출처_권한_및_시점_분류_기준.md"
# These paths are the inspected default Scanner endpoints, not evidence that
# any particular historical row was downloaded through this endpoint.
DEFAULT_SOURCE_PRODUCTS = (
    ("KRX_KOSPI_STOCK_DAILY", "sto/stk_bydd_trd", "KOSPI 일별 주식"),
    ("KRX_KOSDAQ_STOCK_DAILY", "sto/ksq_bydd_trd", "KOSDAQ 일별 주식"),
    ("KRX_KOSPI_INDEX_DAILY", "idx/kospi_dd_trd", "KOSPI 일별 지수"),
    ("KRX_KOSDAQ_INDEX_DAILY", "idx/kosdaq_dd_trd", "KOSDAQ 일별 지수"),
)
# Per-field rule: (origin type, expected parent kinds, time evidence quality).
MARKET = ("KRX_STOCK_DAILY", "KRX_INDEX_DAILY")
POLICY = ("INTERNAL_POLICY", (), "NOT_MARKET_TIMESTAMP")
META = ("PROVENANCE_METADATA", (), "CAPTURE_RECORD_ONLY")
MARKET_DECISION = ("INTERNAL_DECISION", MARKET, "DATE_ONLY")
MARKET_DERIVED = ("EXTERNAL_DERIVED", MARKET, "DATE_ONLY")
ORIGIN_UNKNOWN = "UNKNOWN_ORIGIN"

FIELDS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "version": POLICY,
    "review_scope": POLICY,
    "question_hash": META,
    "input_hash": ("PROVENANCE_METADATA", ("ENTIRE_PACKET",), "CAPTURE_RECORD_ONLY"),
    "source.capture_id": META,
    "source.sample_index": META,
    "source.snapshot_hash": ("PROVENANCE_METADATA", ("FROZEN_SNAPSHOT",), "CAPTURE_RECORD_ONLY"),
    "source.scanner_version": POLICY,
    "source.signal_date": ("PROVENANCE_METADATA", ("KRX_STOCK_DAILY",), "DATE_ONLY"),
    "source.known_to_system_at": META,
    "source.source_available_at": ("PROVENANCE_METADATA", MARKET, "UNKNOWN"),
    "source.source_time_proof": META,
    "baseline.strategy": MARKET_DECISION,
    "baseline.entry_action": MARKET_DECISION,
    "baseline.rank": ("INTERNAL_DECISION", (*MARKET, "SCANNER_COMPARISON_COHORT"), "DATE_ONLY"),
    "baseline.conditions.passed": MARKET_DECISION,
    "baseline.conditions.total": MARKET_DECISION,
    "baseline.conditions.missing": MARKET_DECISION,
    "baseline.risk.status": MARKET_DECISION,
    "baseline.risk.warning": MARKET_DECISION,
    "baseline.strategy_identity.origin": META,
    "baseline.strategy_identity.original_version": POLICY,
    "baseline.strategy_identity.original_definition_hash": POLICY,
    "baseline.strategy_identity.derived_version": ("PROVENANCE_METADATA", ("SCANNER_ENGINE_PASS",), "CAPTURE_RECORD_ONLY"),
    "baseline.strategy_identity.derived_definition_hash": ("PROVENANCE_METADATA", ("SCANNER_ENGINE_PASS",), "CAPTURE_RECORD_ONLY"),
    "baseline.strategy_identity.derived_evidence_source": META,
    "baseline.policy_id": POLICY,
    "baseline.policy_hash": POLICY,
    "baseline.horizon_intent": POLICY,
    "baseline.horizon_policy_version": POLICY,
    "evidence[].id": META,
    "evidence[].source": META,
    "evidence[].statement": MARKET_DERIVED,
    "evidence[].source_available_at": ("PROVENANCE_METADATA", MARKET, "UNKNOWN"),
    "evidence[].source_release_proof": META,
    "evidence[].external_transmission_rights": META,
    "limitations[]": META,
}
MARKET_DEPENDENT = set(MARKET) | {"SCANNER_COMPARISON_COHORT", "FROZEN_SNAPSHOT", "SCANNER_ENGINE_PASS", "ENTIRE_PACKET"}
REASONS_KO = {
    "SOURCE_ORIGIN_UNVERIFIED": "개별 시장 자료의 제공처·제품·수집 증거가 연결되지 않았습니다.",
    "SOURCE_RIGHTS_UNVERIFIED": "파생정보를 외부 AI로 전송할 권한이 검증되지 않았습니다.",
    "SOURCE_RELEASE_TIME_UNVERIFIED": "해당 원천의 실제 공개·최초 확보 시각 증거가 없습니다.",
    "UNKNOWN_OUTBOUND_FIELD": "기존 분류표에 없는 필드가 발견됐습니다.",
    "PACKET_HASH_MISMATCH": "로컬 패킷 무결성 검증에 실패했습니다.",
    "LOCAL_INTEGRITY_NOT_VERIFIED": "기존 후보 정합성 검증이 완료되지 않았습니다.",
    "LINEAGE_PARENT_UNVERIFIED": "필드와 원천 행/revision을 연결하는 증거가 없습니다.",
}


def _producer_reference(path: str, *, is_risk: bool) -> tuple[str, str | None]:
    """Reviewed code producer and immutable snapshot field *path*, not data."""
    if path.startswith("evidence["):
        match = re.match(r"^evidence\[(\d+)\]", path)
        if is_risk:
            return (
                "backend/app/jev/scanner_shadow_s7_3.py::_local_packet;"
                "backend/app/risk/engine.py::RiskEngine.build_plan",
                "snapshot.risk",
            )
        return (
            "backend/app/strategy/semantic_source_v2.py::build_semantic_source_v2;"
            "backend/app/jev/scanner_shadow_s7_3.py::_local_packet",
            f"snapshot.semantic_source_v2.conditions.items[{match.group(1)}]"
            if match else None,
        )
    if path.startswith("baseline.conditions."):
        return (
            "backend/app/backtest/selector.py::build_condition_state;"
            "backend/app/jev/scanner_shadow_s7_3.py::_local_packet",
            "snapshot.conditions." + path.rsplit(".", 1)[-1],
        )
    if path.startswith("baseline.risk."):
        return (
            "backend/app/risk/engine.py::RiskEngine.build_plan;"
            "backend/app/backtest/selector.py::current_readiness",
            "snapshot.risk." + path.rsplit(".", 1)[-1],
        )
    if path == "baseline.rank":
        return (
            "backend/app/backtest/candidate_priority.py::rank_candidates",
            "snapshot.priority.rank",
        )
    if path.startswith("baseline.strategy_identity.") or path in (
        "baseline.policy_id", "baseline.policy_hash"
    ):
        return (
            "backend/app/strategy/semantic_identity_bridge.py::semantic_projection_candidate;"
            "backend/app/jev/scanner_shadow_s7_3.py::_local_packet",
            "snapshot.semantic_strategy_identity or snapshot.semantic_policy_provenance",
        )
    if path.startswith("source."):
        return (
            "backend/app/prospective/catalog.py::finalize_capture;"
            "backend/app/jev/scanner_shadow_s7_3.py::_local_packet",
            "prospective_capture_run / prospective_recommendation_sample",
        )
    if path.startswith("baseline."):
        return "backend/app/jev/scanner_shadow_s7_3.py::_local_packet", None
    return "backend/app/jev/scanner_shadow_s7_3.py::_local_packet", None


def source_audit() -> dict[str, Any]:
    """Reviewed static inventory only: no live license/account inspection."""
    return {
        "version": VERSION,
        "status": "SOURCE_AUDIT_PROVIDER_HOLD",
        "evidence_basis": "REVIEWED_CODE_AND_PUBLIC_TERMS_ONLY",
        "contract_ref": CONTRACT_REF,
        "products": [
            {
                "source_id": sid,
                "expected_endpoint": endpoint,
                "name": name,
                "connection": "DEFAULT_SCANNER_CODE_PATH",
                "actual_row_provenance": "UNVERIFIED",
                "raw_third_party_disclosure": "RESTRICTED_BY_KRX_OPEN_API_PUBLIC_TERMS",
                "derived_ai_transmission": "UNVERIFIED",
                "source_release_time": "UNVERIFIED",
                "account_grant": "UNVERIFIED",
            }
            for sid, endpoint, name in DEFAULT_SOURCE_PRODUCTS
        ],
        "other_paths": {
            "KIS": "SEPARATE_QUOTE_ACCOUNT_PATH_NOT_DEFAULT_SCANNER",
            "OpenDART": "SEPARATE_OR_OPTIONAL_PATH",
            "FRED": "SEPARATE_MACRO_RESEARCH_PATH",
            "NAVER": "SEPARATE_NEWS_PATH",
        },
        "verified_allowed_real_market_fields": 0,
        "next_evidence": [
            "적용 계정·제품의 원문 계약 또는 허가서",
            "조건 PASS·Risk·순위 파생정보의 TypeSafe AI 처리·보관 권한",
            "사용된 행·revision과 공개·최초 확보 시각의 신뢰 가능한 기록",
        ],
        "real_provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def _leaves(value: Any, path: str = "", *, depth: int = 0):
    """Enumerate every leaf, including empty containers, with bounded work."""
    if depth > 16:
        raise DecisionReviewContractError("S7_4_LINEAGE_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        if not value:
            yield path, value
        for key, child in value.items():
            if not isinstance(key, str):
                raise DecisionReviewContractError("S7_4_LINEAGE_NONSTRING_KEY")
            yield from _leaves(child, f"{path}.{key}" if path else key, depth=depth + 1)
    elif isinstance(value, list):
        if not value:
            yield path, value
        for index, child in enumerate(value):
            yield from _leaves(child, f"{path}[{index}]", depth=depth + 1)
    else:
        yield path, value


def _field_entry(path: str, *, is_risk: bool) -> dict[str, Any]:
    rule_path = re.sub(r"\[\d+\]", "[]", path)
    rule = FIELDS.get(rule_path)
    if rule is None:
        return {
            "path": path, "origin_type": ORIGIN_UNKNOWN,
            "expected_parents": [], "actual_source": "UNVERIFIED",
            "rights_status": "UNVERIFIED", "time_quality": "UNKNOWN",
            "producer_ref": None, "local_source_ref": None,
            "reason_codes": ["UNKNOWN_OUTBOUND_FIELD"],
        }
    origin, parents, quality = rule
    if rule_path == "evidence[].statement":
        parents = ("SCANNER_RISK_PLAN", *MARKET) if is_risk else ("SCANNER_ENGINE_PASS", *MARKET)
        origin = "INTERNAL_DECISION"
    # The SourceArtifact/acquisition manifest has not been persisted by current
    # KRX history paths. No per-row source or release time may be inferred.
    dependent = bool(set(parents) & MARKET_DEPENDENT)
    codes = ["SOURCE_RIGHTS_UNVERIFIED"]
    if dependent:
        codes += ["SOURCE_ORIGIN_UNVERIFIED", "LINEAGE_PARENT_UNVERIFIED"]
    if quality in ("DATE_ONLY", "UNKNOWN") or dependent:
        codes.append("SOURCE_RELEASE_TIME_UNVERIFIED")
    producer_ref, local_source_ref = _producer_reference(path, is_risk=is_risk)
    return {
        "path": path,
        "origin_type": origin,
        "expected_parents": list(parents),
        "producer_ref": producer_ref,
        "local_source_ref": local_source_ref,
        "expected_source": "KRX_OPEN_API_DEFAULT_PATH" if dependent else "STOCKSCOPE_INTERNAL",
        "actual_source": "UNVERIFIED" if dependent else "INTERNAL_CODE_ONLY",
        "rights_status": "UNVERIFIED",
        "time_quality": quality,
        "reason_codes": sorted(set(codes)),
    }


def diagnose_prepared(prepared: dict[str, Any]) -> dict[str, Any]:
    """Preserve upstream S7.1/S7.3 failures and diagnose only verified packets.

    COMPLETE means *field enumeration completed*, never that data origin,
    rights, time evidence or external TypeSafe eligibility was verified.
    """
    identity = deepcopy(prepared.get("identity") or {})
    category = prepared.get("category")
    upstream_codes = list(prepared.get("reason_codes") or [])
    codes: set[str] = set(upstream_codes)
    fields: list[dict[str, Any]] = []
    packet = prepared.get("packet")
    lineage_status = "NOT_RUN"
    if category == "REFERENCE_ONLY":
        # A reference-only record is not a failed entry candidate.
        lineage_status = "NOT_APPLICABLE"
    elif prepared.get("status") != "LOCAL_PACKET_READY" or not isinstance(packet, dict):
        codes.add("LOCAL_INTEGRITY_NOT_VERIFIED")
    else:
        unsigned = dict(packet)
        supplied = unsigned.pop("input_hash", None)
        if (
            supplied != digest_json(unsigned)
            or supplied != prepared.get("packet_hash")
            or packet.get("version") != PACKET_VERSION
            or packet.get("question_hash") != QUESTION_HASH
        ):
            codes.add("PACKET_HASH_MISMATCH")
        else:
            try:
                for path, _ in _leaves(packet):
                    if len(fields) >= 512:
                        raise DecisionReviewContractError("S7_4_LINEAGE_TOO_MANY_FIELDS")
                    is_risk = (
                        path.startswith("evidence[")
                        and isinstance(packet.get("evidence"), list)
                        and path.split("]", 1)[0].removeprefix("evidence[").isdigit()
                        and packet["evidence"][int(path.split("]", 1)[0][9:])].get("source")
                        == "SCANNER_RISK_DERIVED"
                    )
                    item = _field_entry(path, is_risk=is_risk)
                    fields.append(item)
                    codes.update(item["reason_codes"])
            except DecisionReviewContractError as exc:
                # A partially traversed packet must never look complete.
                fields.clear()
                codes.add(exc.code)
                lineage_status = "PARTIAL"
            except (TypeError, KeyError, IndexError, AttributeError):
                fields.clear()
                codes.add("S7_4_PACKET_SHAPE_INVALID")
                lineage_status = "PARTIAL"
            else:
                lineage_status = "COMPLETE"
    # Report only paths/categories, never raw statements, prices or keys.
    return {
        "version": VERSION,
        "status": "LINEAGE_DIAGNOSTIC_PROVIDER_HOLD",
        "identity": identity,
        "category": category,
        "integrity_status": prepared.get("status"),
        "integrity_reason_codes": upstream_codes,
        "lineage_analysis_status": lineage_status,
        "packet_hash": prepared.get("packet_hash"),
        "temporal_status": prepared.get("temporal_status"),
        "field_diagnostics": fields,
        "field_count": len(fields),
        "unclassified_fields": sum(
            "UNKNOWN_OUTBOUND_FIELD" in f["reason_codes"] for f in fields
        ),
        "reason_codes": sorted(codes),
        "real_provider_eligible": False,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }

def diagnose_capture(
    simulation_db: Path, *, capture_id: str | None, limit: int = 60,
    sample_index: int | None = None,
) -> dict[str, Any]:
    """Read-only canonical SQLite capture; no research or market DB writes."""
    if not capture_id:
        raise DecisionReviewContractError("S7_3_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("S7_3_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("S7_3_SAMPLE_NOT_FOUND")
    records = [diagnose_prepared(prepare_shadow_candidate(c, s)) for c, s in pairs]
    entry_records = [r for r in records if r["category"] != "REFERENCE_ONLY"]
    statuses = [r["lineage_analysis_status"] for r in entry_records]
    if not entry_records:
        lineage_status = "NOT_APPLICABLE"
    elif all(status == "COMPLETE" for status in statuses):
        lineage_status = "COMPLETE"
    elif any(status in ("COMPLETE", "PARTIAL") for status in statuses):
        lineage_status = "PARTIAL"
    else:
        lineage_status = "NOT_RUN"
    return {
        "version": VERSION,
        "status": "LINEAGE_DIAGNOSTIC_PROVIDER_HOLD",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "entry_candidates": sum(r["category"] != "REFERENCE_ONLY" for r in records),
        "local_packets_ready": sum(r["integrity_status"] == "LOCAL_PACKET_READY" for r in records),
        "unclassified_fields": sum(r["unclassified_fields"] for r in records),
        "lineage_analysis_status": lineage_status,
        "lineage_examined_count": sum(
            r["lineage_analysis_status"] == "COMPLETE" for r in records
        ),
        "lineage_not_run_count": sum(
            r["lineage_analysis_status"] == "NOT_RUN" for r in records
        ),
        "lineage_partial_count": sum(
            r["lineage_analysis_status"] == "PARTIAL" for r in records
        ),
        "reference_count": sum(
            r["lineage_analysis_status"] == "NOT_APPLICABLE" for r in records
        ),
        "invalid_count": sum(r["category"] == "INVALID" for r in records),
        "records": records,
        "real_provider_eligible": 0,
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
