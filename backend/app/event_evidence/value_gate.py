from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.evaluation import HistoricalEventEvaluator


INCREMENTAL_VALUE_GATE_CONTRACT_VERSION = "VN_P6_S1_INCREMENTAL_VALUE_GATE_V1"
VALUE_GATE_PROTOCOL_CONTRACT_VERSION = "VN_P6_S1_VALUE_GATE_PROTOCOL_V1"
VALUE_GATE_DECISION_CONTRACT_VERSION = "VN_P6_S1_VALUE_GATE_DECISION_V1"


class ValueGateKind(str, Enum):
    OBSERVATIONAL_INCREMENTAL_VALUE = "OBSERVATIONAL_INCREMENTAL_VALUE"
    PREDICTION_VALUE = "PREDICTION_VALUE"


class ValueGateDecision(str, Enum):
    PASS = "PASS"
    HOLD = "HOLD"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class ValueGateProtocolStatus(str, Enum):
    UNAPPROVED = "UNAPPROVED"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class EvidencePopulation(str, Enum):
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    REAL_CORPUS = "REAL_CORPUS"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class ProductScope(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    REFERENCE_CONTEXT = "REFERENCE_CONTEXT"
    PREDICTION = "PREDICTION"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EventEvidenceContractError(
            "EVENT_VALUE_GATE_JSON_INVALID",
            "Incremental Value Gate payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IncrementalValueGateProtocol:
    protocol_id: str
    status: ValueGateProtocolStatus = ValueGateProtocolStatus.UNAPPROVED
    gate_kind: ValueGateKind = ValueGateKind.OBSERVATIONAL_INCREMENTAL_VALUE
    criteria_precommitted: bool = False
    sample_rule_approved: bool = False
    uncertainty_rule_approved: bool = False
    multiple_testing_policy_approved: bool = False
    control_rule_approved: bool = False
    required_horizons: tuple[int, ...] = ()
    minimum_sample_count: int | None = None
    minimum_clean_control_count: int | None = None
    minimum_observed_difference_pct_points: float | None = None
    contract_version: str = VALUE_GATE_PROTOCOL_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not str(self.protocol_id or "").strip():
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_PROTOCOL_ID_REQUIRED",
                "Value Gate protocol_id가 필요합니다.",
            )
        if self.contract_version != VALUE_GATE_PROTOCOL_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_PROTOCOL_CONTRACT_MISMATCH",
                "Value Gate Protocol contract version이 현재 코드와 다릅니다.",
            )
        try:
            status = (
                self.status
                if isinstance(self.status, ValueGateProtocolStatus)
                else ValueGateProtocolStatus(str(self.status))
            )
            gate_kind = (
                self.gate_kind
                if isinstance(self.gate_kind, ValueGateKind)
                else ValueGateKind(str(self.gate_kind))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_PROTOCOL_VALUE_INVALID",
                "알 수 없는 Value Gate protocol status/kind입니다.",
            ) from exc
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "gate_kind", gate_kind)

        horizons = tuple(int(value) for value in self.required_horizons)
        if any(value not in (1, 5, 20) for value in horizons):
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_HORIZON_INVALID",
                "Value Gate horizon은 1/5/20 거래일 중에서만 지정할 수 있습니다.",
            )
        object.__setattr__(self, "required_horizons", horizons)

        if gate_kind is ValueGateKind.PREDICTION_VALUE:
            raise EventEvidenceContractError(
                "PREDICTION_VALUE_GATE_NOT_IMPLEMENTED",
                "P6-S1-F V1은 prediction value gate를 구현하지 않습니다.",
            )

        numeric_criteria = (
            self.minimum_sample_count,
            self.minimum_clean_control_count,
            self.minimum_observed_difference_pct_points,
        )
        if status is ValueGateProtocolStatus.UNAPPROVED:
            if any(value is not None for value in numeric_criteria) or horizons:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_UNAPPROVED_CRITERIA_FORBIDDEN",
                    "UNAPPROVED Production protocol에는 임의 숫자/horizon 기준을 넣을 수 없습니다.",
                )
            if any(
                (
                    self.criteria_precommitted,
                    self.sample_rule_approved,
                    self.uncertainty_rule_approved,
                    self.multiple_testing_policy_approved,
                    self.control_rule_approved,
                )
            ):
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_UNAPPROVED_FLAGS_FORBIDDEN",
                    "UNAPPROVED protocol을 승인된 것처럼 표시할 수 없습니다.",
                )

        if status is ValueGateProtocolStatus.SYNTHETIC_TEST_ONLY:
            if not (
                self.criteria_precommitted
                and self.sample_rule_approved
                and self.uncertainty_rule_approved
                and self.multiple_testing_policy_approved
                and self.control_rule_approved
            ):
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_TEST_PROTOCOL_INCOMPLETE",
                    "Synthetic test protocol은 테스트용 gate 조건을 모두 명시해야 합니다.",
                )
            if not horizons:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_TEST_HORIZONS_REQUIRED",
                    "Synthetic test protocol은 required_horizons가 필요합니다.",
                )
            if self.minimum_sample_count is None or self.minimum_sample_count < 1:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_TEST_SAMPLE_RULE_REQUIRED",
                    "Synthetic test protocol은 양의 minimum_sample_count가 필요합니다.",
                )
            if (
                self.minimum_clean_control_count is None
                or self.minimum_clean_control_count < 1
            ):
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_TEST_CONTROL_RULE_REQUIRED",
                    "Synthetic test protocol은 양의 minimum_clean_control_count가 필요합니다.",
                )
            if self.minimum_observed_difference_pct_points is None:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_TEST_DIFFERENCE_RULE_REQUIRED",
                    "Synthetic test protocol은 테스트용 observed difference 기준이 필요합니다.",
                )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["gate_kind"] = self.gate_kind.value
        payload["required_horizons"] = list(self.required_horizons)
        return payload


class EventIncrementalValueGate:
    """Immutable P6-S1-F observational incremental-value decision gate.

    V1 never authorizes prediction, Strategy/Scanner changes, or production
    activation. Production criteria remain unapproved until separately defined.
    """

    def __init__(
        self,
        simulation_db: Path,
        market_store_db: Path,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.market_store_db = Path(market_store_db)
        self.clock = clock or _now
        self.evaluator = HistoricalEventEvaluator(
            self.simulation_db,
            self.market_store_db,
            clock=self.clock,
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STORE_NOT_FOUND",
                f"Simulation DB를 찾을 수 없습니다: {self.simulation_db}",
            )
        conn = sqlite3.connect(self.simulation_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _require_ready(self, conn: sqlite3.Connection) -> None:
        required = {
            "event_evidence_value_gate_protocol",
            "event_evidence_value_gate_decision",
            "event_evidence_evaluation_report",
            "event_evidence_outcome_observation",
            "event_evidence_quality_assessment",
            "event_evidence_record_source",
            "event_evidence_source_ref",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_MIGRATION_REQUIRED",
                "P6 Incremental Value Gate schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    def register_protocol(
        self,
        protocol: IncrementalValueGateProtocol,
    ) -> dict[str, Any]:
        payload = protocol.to_dict()
        protocol_json = _canonical_json(payload)
        protocol_hash = _digest(payload)
        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT protocol_json,protocol_hash
                FROM event_evidence_value_gate_protocol
                WHERE protocol_id=?
                """,
                (protocol.protocol_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["protocol_json"]) == protocol_json
                    and str(existing["protocol_hash"]) == protocol_hash
                ):
                    conn.commit()
                    return self.get_protocol(protocol.protocol_id)
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_PROTOCOL_CONFLICT",
                    "같은 Value Gate protocol_id가 다른 내용으로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_value_gate_protocol(
                    protocol_id,protocol_contract_version,status,gate_kind,
                    criteria_precommitted,sample_rule_approved,
                    uncertainty_rule_approved,multiple_testing_policy_approved,
                    control_rule_approved,required_horizons_json,
                    minimum_sample_count,minimum_clean_control_count,
                    minimum_observed_difference_pct_points,
                    protocol_json,protocol_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    protocol.protocol_id,
                    protocol.contract_version,
                    protocol.status.value,
                    protocol.gate_kind.value,
                    int(protocol.criteria_precommitted),
                    int(protocol.sample_rule_approved),
                    int(protocol.uncertainty_rule_approved),
                    int(protocol.multiple_testing_policy_approved),
                    int(protocol.control_rule_approved),
                    _canonical_json(list(protocol.required_horizons)),
                    protocol.minimum_sample_count,
                    protocol.minimum_clean_control_count,
                    protocol.minimum_observed_difference_pct_points,
                    protocol_json,
                    protocol_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_protocol(protocol.protocol_id)

    def get_protocol(self, protocol_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_value_gate_protocol
                WHERE protocol_id=?
                """,
                (protocol_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_PROTOCOL_NOT_FOUND",
                    "Incremental Value Gate Protocol을 찾을 수 없습니다.",
                )
            return {
                "protocol_id": str(row["protocol_id"]),
                "status": str(row["status"]),
                "gate_kind": str(row["gate_kind"]),
                "criteria_precommitted": bool(row["criteria_precommitted"]),
                "sample_rule_approved": bool(row["sample_rule_approved"]),
                "uncertainty_rule_approved": bool(row["uncertainty_rule_approved"]),
                "multiple_testing_policy_approved": bool(
                    row["multiple_testing_policy_approved"]
                ),
                "control_rule_approved": bool(row["control_rule_approved"]),
                "required_horizons": json.loads(
                    str(row["required_horizons_json"])
                ),
                "minimum_sample_count": row["minimum_sample_count"],
                "minimum_clean_control_count": row[
                    "minimum_clean_control_count"
                ],
                "minimum_observed_difference_pct_points": row[
                    "minimum_observed_difference_pct_points"
                ],
                "protocol_hash": str(row["protocol_hash"]),
                "protocol": json.loads(str(row["protocol_json"])),
                "created_at": str(row["created_at"]),
            }

    def _population_for_report(self, report: dict[str, Any]) -> EvidencePopulation:
        source_kinds: set[str] = set()
        with self._connect() as conn:
            self._require_ready(conn)
            for pin in report["observation_bundle"]:
                row = conn.execute(
                    """
                    SELECT DISTINCT sr.source_kind
                    FROM event_evidence_outcome_observation o
                    JOIN event_evidence_quality_assessment q
                      ON q.assessment_id=o.quality_assessment_id
                    JOIN event_evidence_record_source rs
                      ON rs.event_id=q.event_id
                     AND rs.event_version=q.event_version
                    JOIN event_evidence_source_ref sr
                      ON sr.source_ref_id=rs.source_ref_id
                    WHERE o.observation_id=?
                    """,
                    (pin["observation_id"],),
                ).fetchall()
                source_kinds.update(str(item["source_kind"]) for item in row)
        if not source_kinds:
            return EvidencePopulation.UNKNOWN
        synthetic = {item for item in source_kinds if item == "TEST_SYNTHETIC"}
        if synthetic == source_kinds:
            return EvidencePopulation.SYNTHETIC_ONLY
        if synthetic:
            return EvidencePopulation.MIXED
        return EvidencePopulation.REAL_CORPUS

    def _raw_report(self, report_id: str) -> dict[str, Any]:
        return self.evaluator.get_report(report_id)

    def evaluate_report(
        self,
        *,
        evaluation_report_id: str,
        gate_protocol_id: str,
    ) -> dict[str, Any]:
        protocol = self.get_protocol(gate_protocol_id)
        report = self._raw_report(evaluation_report_id)

        integrity_state = "MATCH"
        blocked: list[str] = []
        reasons: list[str] = []
        try:
            verified = self.evaluator.verify_report(evaluation_report_id)
            if verified["report_hash"] != report["report_hash"]:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_REPORT_HASH_MISMATCH",
                    "Gate가 읽은 Report hash와 검증 결과가 다릅니다.",
                )
        except EventEvidenceContractError:
            integrity_state = "MISMATCH"
            blocked.append("REPORT_INTEGRITY_FAILED")

        population = self._population_for_report(report)

        decision = ValueGateDecision.HOLD
        product_scope = ProductScope.RESEARCH_ONLY
        horizon_results: dict[str, Any] = {}

        if blocked:
            decision = ValueGateDecision.BLOCKED
        elif protocol["gate_kind"] != ValueGateKind.OBSERVATIONAL_INCREMENTAL_VALUE.value:
            decision = ValueGateDecision.BLOCKED
            blocked.append("PREDICTION_GATE_NOT_EVALUATED")
        elif protocol["status"] == ValueGateProtocolStatus.UNAPPROVED.value:
            reasons.extend(
                [
                    "GATE_CRITERIA_UNAPPROVED",
                    "SAMPLE_SUFFICIENCY_UNDECIDED",
                    "HORIZON_CRITERIA_UNAPPROVED",
                    "UNCERTAINTY_RULE_UNAPPROVED",
                    "MULTIPLE_TESTING_POLICY_UNAPPROVED",
                ]
            )
            if report["report"]["control_summary"]["approved"]:
                if (
                    int(report["report"]["control_summary"]["clean_match_count"])
                    <= 0
                ):
                    reasons.append("CONTROL_EVIDENCE_INSUFFICIENT")
            else:
                reasons.append("CONTROL_COMPARISON_NOT_AVAILABLE")
            if population is EvidencePopulation.SYNTHETIC_ONLY:
                reasons.append("SYNTHETIC_ONLY")
            elif population is EvidencePopulation.UNKNOWN:
                reasons.append("REAL_CORPUS_NOT_AVAILABLE")
        elif protocol["status"] == ValueGateProtocolStatus.SYNTHETIC_TEST_ONLY.value:
            if population is not EvidencePopulation.SYNTHETIC_ONLY:
                decision = ValueGateDecision.BLOCKED
                blocked.append("TEST_PROTOCOL_REAL_DATA_FORBIDDEN")
            else:
                minimum_samples = int(protocol["minimum_sample_count"])
                minimum_controls = int(protocol["minimum_clean_control_count"])
                min_difference = float(
                    protocol["minimum_observed_difference_pct_points"]
                )
                sample_ok = int(report["sample_count"]) >= minimum_samples
                control_summary = report["report"]["control_summary"]
                control_ok = (
                    bool(control_summary["approved"])
                    and int(control_summary["clean_match_count"])
                    >= minimum_controls
                )
                all_horizons_ok = True
                for horizon in protocol["required_horizons"]:
                    key = str(horizon)
                    metrics = report["report"]["horizons"].get(key) or {}
                    event_metric = metrics.get("market_adjusted_return") or {}
                    control_metric = (
                        metrics.get("control_market_adjusted_return") or {}
                    )
                    difference = metrics.get(
                        "observed_event_minus_control_pct_points"
                    )
                    mature_sample_count = int(
                        event_metric.get("sample_count") or 0
                    )
                    control_sample_count = int(
                        control_metric.get("sample_count") or 0
                    )
                    horizon_ok = (
                        mature_sample_count >= minimum_samples
                        and control_sample_count >= minimum_controls
                        and difference is not None
                        and float(difference) >= min_difference
                    )
                    horizon_results[key] = {
                        "status": "PASS" if horizon_ok else "FAIL",
                        "event_sample_count": mature_sample_count,
                        "control_sample_count": control_sample_count,
                        "event_market_adjusted_average_pct": event_metric.get(
                            "average_pct"
                        ),
                        "control_market_adjusted_average_pct": control_metric.get(
                            "average_pct"
                        ),
                        "observed_difference_pct_points": difference,
                        "test_threshold_pct_points": min_difference,
                    }
                    all_horizons_ok = all_horizons_ok and horizon_ok

                if not sample_ok:
                    reasons.append("SAMPLE_EVIDENCE_INSUFFICIENT")
                if not control_ok:
                    reasons.append("CONTROL_EVIDENCE_INSUFFICIENT")

                if sample_ok and control_ok:
                    if all_horizons_ok:
                        decision = ValueGateDecision.PASS
                        product_scope = ProductScope.REFERENCE_CONTEXT
                        reasons.append("INCREMENTAL_VALUE_CRITERIA_MET")
                    else:
                        decision = ValueGateDecision.FAIL
                        reasons.append("INCREMENTAL_VALUE_NOT_DEMONSTRATED")
                else:
                    decision = ValueGateDecision.HOLD
        else:
            decision = ValueGateDecision.BLOCKED
            blocked.append("VALUE_GATE_PROTOCOL_STATUS_INVALID")

        final_reasons = sorted(set(blocked + reasons))
        decision_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-value-gate:"
                    f"{VALUE_GATE_DECISION_CONTRACT_VERSION}:"
                    f"{protocol['protocol_hash']}:"
                    f"{report['report_id']}:{report['report_hash']}"
                ),
            )
        )
        decision_payload = {
            "gate_contract_version": INCREMENTAL_VALUE_GATE_CONTRACT_VERSION,
            "decision_contract_version": VALUE_GATE_DECISION_CONTRACT_VERSION,
            "decision_id": decision_id,
            "gate_protocol_id": protocol["protocol_id"],
            "gate_protocol_hash": protocol["protocol_hash"],
            "evaluation_report_id": report["report_id"],
            "evaluation_report_hash": report["report_hash"],
            "evidence_population": population.value,
            "integrity_state": integrity_state,
            "decision": decision.value,
            "decision_reasons": final_reasons,
            "sample_sufficiency": report["sample_sufficiency"],
            "control_status": report["report"]["control_summary"],
            "uncertainty_status": report["statistical_test_status"],
            "multiple_testing_status": (
                "APPROVED_FOR_SYNTHETIC_TEST"
                if protocol["multiple_testing_policy_approved"]
                else "NOT_CONFIGURED"
            ),
            "horizon_results": horizon_results,
            "product_scope": product_scope.value,
            "prediction_eligible": False,
            "guardrails": [
                "PASS는 observational incremental value gate의 test/protocol 결과이며 인과 효과를 뜻하지 않습니다.",
                "P6-S1-F V1은 주가 방향 예측, 확률, Strategy/Scanner 변경을 승인하지 않습니다.",
            ],
        }
        decision_json = _canonical_json(decision_payload)
        decision_hash = _digest(decision_payload)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT decision_json,decision_hash
                FROM event_evidence_value_gate_decision
                WHERE decision_id=?
                """,
                (decision_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["decision_json"]) == decision_json
                    and str(existing["decision_hash"]) == decision_hash
                ):
                    conn.commit()
                    return self.get_decision(decision_id)
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_IDENTITY_CONFLICT",
                    "같은 Value Gate Decision identity가 다른 결과로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_value_gate_decision(
                    decision_id,decision_contract_version,
                    gate_protocol_id,gate_protocol_hash,
                    evaluation_report_id,evaluation_report_hash,
                    evidence_population,integrity_state,
                    decision,decision_reasons_json,
                    sample_sufficiency,control_status_json,
                    uncertainty_status,multiple_testing_status,
                    horizon_results_json,product_scope,prediction_eligible,
                    decision_json,decision_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    decision_id,
                    VALUE_GATE_DECISION_CONTRACT_VERSION,
                    protocol["protocol_id"],
                    protocol["protocol_hash"],
                    report["report_id"],
                    report["report_hash"],
                    population.value,
                    integrity_state,
                    decision.value,
                    _canonical_json(final_reasons),
                    report["sample_sufficiency"],
                    _canonical_json(report["report"]["control_summary"]),
                    report["statistical_test_status"],
                    decision_payload["multiple_testing_status"],
                    _canonical_json(horizon_results),
                    product_scope.value,
                    0,
                    decision_json,
                    decision_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_decision(decision_id)

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_value_gate_decision
                WHERE decision_id=?
                """,
                (decision_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_VALUE_GATE_DECISION_NOT_FOUND",
                    "Incremental Value Gate Decision을 찾을 수 없습니다.",
                )
            return {
                "decision_id": str(row["decision_id"]),
                "gate_protocol_id": str(row["gate_protocol_id"]),
                "gate_protocol_hash": str(row["gate_protocol_hash"]),
                "evaluation_report_id": str(row["evaluation_report_id"]),
                "evaluation_report_hash": str(row["evaluation_report_hash"]),
                "evidence_population": str(row["evidence_population"]),
                "integrity_state": str(row["integrity_state"]),
                "decision": str(row["decision"]),
                "decision_reasons": json.loads(
                    str(row["decision_reasons_json"])
                ),
                "sample_sufficiency": str(row["sample_sufficiency"]),
                "control_status": json.loads(str(row["control_status_json"])),
                "uncertainty_status": str(row["uncertainty_status"]),
                "multiple_testing_status": str(
                    row["multiple_testing_status"]
                ),
                "horizon_results": json.loads(str(row["horizon_results_json"])),
                "product_scope": str(row["product_scope"]),
                "prediction_eligible": bool(row["prediction_eligible"]),
                "decision_hash": str(row["decision_hash"]),
                "decision": str(row["decision"]),
                "artifact": json.loads(str(row["decision_json"])),
                "created_at": str(row["created_at"]),
            }

    def verify_decision(self, decision_id: str) -> dict[str, Any]:
        decision = self.get_decision(decision_id)
        artifact = decision["artifact"]
        if _digest(artifact) != decision["decision_hash"]:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_DECISION_INTEGRITY_MISMATCH",
                "Value Gate Decision hash가 저장 내용과 일치하지 않습니다.",
            )
        protocol = self.get_protocol(decision["gate_protocol_id"])
        if protocol["protocol_hash"] != decision["gate_protocol_hash"]:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_PROTOCOL_HASH_MISMATCH",
                "Decision이 pin한 Value Gate Protocol hash가 다릅니다.",
            )
        report = self.evaluator.get_report(decision["evaluation_report_id"])
        if report["report_hash"] != decision["evaluation_report_hash"]:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_REPORT_HASH_MISMATCH",
                "Decision이 pin한 Evaluation Report hash가 다릅니다.",
            )
        self.evaluator.verify_report(report["report_id"])
        if decision["prediction_eligible"]:
            raise EventEvidenceContractError(
                "EVENT_VALUE_GATE_PREDICTION_GUARDRAIL_BROKEN",
                "P6-S1-F V1 Decision은 prediction_eligible=True일 수 없습니다.",
            )
        return {
            "status": "MATCH",
            "decision_id": decision_id,
            "decision_hash": decision["decision_hash"],
            "decision": decision["decision"],
        }
