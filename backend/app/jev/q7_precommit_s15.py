"""S15 Q7 research-only precommit, independent from production approval.

The user supplies the evaluation cutoffs; no sample threshold, regime
criterion, promotion decision or retrospective strategy identity is invented.
Local write-once files provide *application-level* immutability, NOT trusted
timestamp notarization or authorization to activate the production policy.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app.simulation.strategy_governance import StrategyGovernanceError, strategy_definition
from app.strategy.models import StrategyName


VERSION = "Q7_RESEARCH_PRECOMMIT_S15_V1"
STATUS = "RESEARCH_ONLY_NOT_Q7_APPROVED"
KST = ZoneInfo("Asia/Seoul")
_STUDY = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "q7_precommit"
_DIMS = ("round_trip_cost_pct", "fee_pct", "tax_pct", "slippage_pct")


class Q7PrecommitError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _expect_keys(obj: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise Q7PrecommitError(code)
    return obj


def _string(obj: Any, code: str, *, minimum: int = 3, maximum: int = 500) -> str:
    if type(obj) is not str or not minimum <= len(obj.strip()) <= maximum or obj != obj.strip():
        raise Q7PrecommitError(code)
    return obj


def _number(value: Any, code: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise Q7PrecommitError(code)
    return float(value)


def _integer(value: Any, code: str, minimum: int = 1, maximum: int = 100000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise Q7PrecommitError(code)
    return value


def _date(value: Any, code: str) -> date:
    if type(value) is not str:
        raise Q7PrecommitError(code)
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError as exc:
        raise Q7PrecommitError(code) from exc


def _clock(now: datetime | None = None) -> datetime:
    current = now or datetime.now(KST)
    if current.tzinfo is None or current.utcoffset() is None:
        raise Q7PrecommitError("Q7_CLOCK_TIMEZONE_REQUIRED")
    return current.astimezone(KST)


def _definition(strategy_key: str) -> dict[str, str]:
    try:
        selected = StrategyName(strategy_key)
        definition = strategy_definition(selected)
    except (ValueError, KeyError, StrategyGovernanceError) as exc:
        raise Q7PrecommitError("Q7_STRATEGY_NOT_SUPPORTED") from exc
    return {
        "strategy_key": definition.strategy_key,
        "strategy_version_id": definition.strategy_version_id,
        "definition_hash": definition.definition_hash,
    }


def template(strategy_key: str) -> dict[str, Any]:
    """All undecided numbers are null; no accidental policy defaults."""
    return {
        "contract_version": VERSION,
        "study_id": None,
        "operator": None,
        "strategy": _definition(strategy_key),
        "market_scope": None,
        "time_split": {
            "development_start": None, "development_end": None,
            "holdout_start": None, "holdout_end": None,
            "purge_trading_days": None,
        },
        "population": {
            "universe_rule": None,
            "regime_rule": None,
            "minimum_independent_samples_total": None,
            "minimum_independent_samples_per_regime": None,
            "independence_key": "SIGNAL_DATE_MARKET_TICKER_STRATEGY",
            "maturity_trading_days": None,
        },
        "comparison": {
            "baseline": "CURRENT_SCANNER_MATCHED_COHORT",
            "return_basis": "OBSERVATION_ONLY_NOT_REAL_TRADES",
            "round_trip_cost_pct": None,
            "fee_pct": None,
            "tax_pct": None,
            "slippage_pct": None,
            "min_outperformance_pct": None,
            "max_drawdown_pct": None,
            "confidence_level_pct": None,
            "multiple_testing_rule": None,
        },
        "decision": {
            "promotion_rule": None,
            "abstain_rule": None,
            "demotion_rule": None,
            "rollback_rule": None,
        },
        "evidence": {
            "original_strategy_identity_required": True,
            "verified_source_time_required": True,
            "development_holdout_separate": True,
            "result_backfill_forbidden": True,
        },
    }


def validate_spec(
    spec: Any, *, now: datetime | None = None,
    require_current_identity: bool = True,
) -> dict[str, Any]:
    """Validate prospective split, completeness, and optional current engine binding.

    An archived artifact's historical hash must remain verifiable even when
    the engine definition changes later. New freezes always require the actual
    current engine identity.
    """
    today = _clock(now).date()
    t = template("pullback")
    _expect_keys(spec, set(t), "Q7_SPEC_FIELDS_INVALID")
    if spec["contract_version"] != VERSION:
        raise Q7PrecommitError("Q7_SPEC_VERSION_INVALID")
    study_id = _string(spec["study_id"], "Q7_STUDY_ID_INVALID", maximum=64)
    if not _STUDY.fullmatch(study_id):
        raise Q7PrecommitError("Q7_STUDY_ID_INVALID")
    _string(spec["operator"], "Q7_OPERATOR_REQUIRED", maximum=100)
    identity = _expect_keys(spec["strategy"], set(t["strategy"]), "Q7_IDENTITY_FIELDS_INVALID")
    _string(identity.get("strategy_key"), "Q7_STRATEGY_KEY_INVALID")
    _string(identity.get("strategy_version_id"), "Q7_STRATEGY_VERSION_INVALID")
    definition_hash = _string(identity.get("definition_hash"), "Q7_STRATEGY_HASH_INVALID", minimum=64, maximum=64)
    if not _HEX.fullmatch(definition_hash):
        raise Q7PrecommitError("Q7_STRATEGY_HASH_INVALID")
    if require_current_identity and identity != _definition(identity["strategy_key"]):
        raise Q7PrecommitError("Q7_STRATEGY_IDENTITY_NOT_CURRENT")
    if spec["market_scope"] not in ("ALL", "KOSPI", "KOSDAQ"):
        raise Q7PrecommitError("Q7_MARKET_SCOPE_INVALID")

    split = _expect_keys(spec["time_split"], set(t["time_split"]), "Q7_SPLIT_FIELDS_INVALID")
    d0, d1, h0, h1 = (_date(split[k], "Q7_SPLIT_DATE_INVALID") for k in (
        "development_start", "development_end", "holdout_start", "holdout_end"
    ))
    if not (d0 <= d1 <= today < h0 <= h1):
        raise Q7PrecommitError("Q7_HOLDOUT_NOT_PROSPECTIVE")
    purge = _integer(split["purge_trading_days"], "Q7_PURGE_INVALID", maximum=252)

    pop = _expect_keys(spec["population"], set(t["population"]), "Q7_POPULATION_FIELDS_INVALID")
    _string(pop["universe_rule"], "Q7_UNIVERSE_RULE_REQUIRED", minimum=20)
    _string(pop["regime_rule"], "Q7_REGIME_RULE_REQUIRED", minimum=20)
    total = _integer(pop["minimum_independent_samples_total"], "Q7_MIN_SAMPLE_REQUIRED")
    per = _integer(pop["minimum_independent_samples_per_regime"], "Q7_REGIME_MIN_SAMPLE_REQUIRED")
    if per > total:
        raise Q7PrecommitError("Q7_REGIME_SAMPLE_EXCEEDS_TOTAL")
    if pop["independence_key"] != "SIGNAL_DATE_MARKET_TICKER_STRATEGY":
        raise Q7PrecommitError("Q7_INDEPENDENCE_KEY_UNSUPPORTED")
    maturity = _integer(pop["maturity_trading_days"], "Q7_MATURITY_INVALID", maximum=252)
    if purge < maturity:
        raise Q7PrecommitError("Q7_PURGE_SHORTER_THAN_MATURITY")

    comp = _expect_keys(spec["comparison"], set(t["comparison"]), "Q7_COMPARISON_FIELDS_INVALID")
    if (comp["baseline"] != "CURRENT_SCANNER_MATCHED_COHORT"
            or comp["return_basis"] != "OBSERVATION_ONLY_NOT_REAL_TRADES"):
        raise Q7PrecommitError("Q7_UNSUPPORTED_COMPARISON")
    for k in _DIMS:
        _number(comp[k], "Q7_COST_REQUIRED", 0, 5)
    _number(comp["min_outperformance_pct"], "Q7_IMPROVEMENT_THRESHOLD_REQUIRED", 0, 100)
    _number(comp["max_drawdown_pct"], "Q7_DRAWDOWN_THRESHOLD_REQUIRED", 0, 100)
    _number(comp["confidence_level_pct"], "Q7_CONFIDENCE_REQUIRED", 50, 99.99)
    _string(comp["multiple_testing_rule"], "Q7_MULTIPLE_TESTING_RULE_REQUIRED", minimum=20)

    decision = _expect_keys(spec["decision"], set(t["decision"]), "Q7_DECISION_FIELDS_INVALID")
    for key, value in decision.items():
        _string(value, f"Q7_{key.upper()}_RULE_REQUIRED", minimum=20)

    evidence = _expect_keys(spec["evidence"], set(t["evidence"]), "Q7_EVIDENCE_FIELDS_INVALID")
    if evidence != t["evidence"]:
        raise Q7PrecommitError("Q7_EVIDENCE_SAFETY_INVALID")
    return spec


def _artifact_id(study_id: str) -> str:
    return "Q7-S15-" + study_id


def verify_artifact(value: Any, *, expected_study_id: str | None = None) -> dict[str, Any]:
    record = _expect_keys(
        value, {"schema", "artifact_id", "spec", "spec_hash", "frozen_at",
                "record_hash", "authority", "trusted_time_attested"},
        "Q7_ARTIFACT_FIELDS_INVALID",
    )
    if record["schema"] != VERSION or record["authority"] != STATUS or record["trusted_time_attested"] is not False:
        raise Q7PrecommitError("Q7_ARTIFACT_AUTHORITY_INVALID")
    if not isinstance(record["spec"], dict):
        raise Q7PrecommitError("Q7_ARTIFACT_SPEC_INVALID")
    study_id = record["spec"].get("study_id")
    if type(study_id) is not str or not _STUDY.fullmatch(study_id):
        raise Q7PrecommitError("Q7_ARTIFACT_STUDY_ID_MISMATCH")
    if study_id != expected_study_id and expected_study_id is not None:
        raise Q7PrecommitError("Q7_ARTIFACT_STUDY_ID_MISMATCH")
    if record["artifact_id"] != _artifact_id(study_id):
        raise Q7PrecommitError("Q7_ARTIFACT_ID_MISMATCH")
    if type(record["frozen_at"]) is not str:
        raise Q7PrecommitError("Q7_ARTIFACT_TIME_INVALID")
    try:
        when = datetime.fromisoformat(record["frozen_at"])
    except ValueError as exc:
        raise Q7PrecommitError("Q7_ARTIFACT_TIME_INVALID") from exc
    if when.tzinfo is None:
        raise Q7PrecommitError("Q7_ARTIFACT_TIME_INVALID")
    validate_spec(record["spec"], now=when, require_current_identity=False)
    if record["spec_hash"] != _hash(record["spec"]):
        raise Q7PrecommitError("Q7_ARTIFACT_SPEC_HASH_MISMATCH")
    body = dict(record)
    supplied = body.pop("record_hash")
    if type(supplied) is not str or not _HEX.fullmatch(supplied) or supplied != _hash(body):
        raise Q7PrecommitError("Q7_ARTIFACT_HASH_MISMATCH")
    return {
        "status": "VALID_LOCAL_RECORD_NOT_TRUSTED_ATTESTATION",
        "artifact_id": record["artifact_id"],
        "spec_hash": record["spec_hash"],
        "frozen_at": record["frozen_at"],
        "production_activation_allowed": False,
        "q7_approval_eligible": False,
    }


def freeze(
    spec: dict[str, Any], *,
    root: Path = _DEFAULT_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    clock = _clock(now)
    if not isinstance(spec, dict) or type(spec.get("study_id")) is not str or not _STUDY.fullmatch(spec["study_id"]):
        raise Q7PrecommitError("Q7_STUDY_ID_INVALID")
    root = Path(root).resolve()
    study_id = spec["study_id"]
    path = root / (study_id + ".json")
    # Idempotent retries stay readable even after the future holdout begins.
    if path.exists():
        existing = load(study_id, root=root)
        if existing["spec_hash"] != _hash(spec):
            raise Q7PrecommitError("Q7_STUDY_ALREADY_FROZEN_DIFFERENT_SPEC")
        return {**verify_artifact(existing, expected_study_id=study_id),
                "created": False, "path": str(path)}
    validate_spec(spec, now=clock)
    body = {
        "schema": VERSION,
        "artifact_id": _artifact_id(study_id),
        "spec": spec,
        "spec_hash": _hash(spec),
        "frozen_at": clock.isoformat(),
        "authority": STATUS,
        "trusted_time_attested": False,
    }
    record = {**body, "record_hash": _hash(body)}
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # Same study id cannot be changed or silently replaced. Even an
        # identical retry is read-only and verifies existing local record.
        existing = load(study_id, root=root)
        if existing["spec_hash"] != record["spec_hash"]:
            raise Q7PrecommitError("Q7_STUDY_ALREADY_FROZEN_DIFFERENT_SPEC")
        return {**verify_artifact(existing, expected_study_id=study_id),
                "created": False, "path": str(path)}
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        # A failed atomic create is not a usable precommit; do not allow a
        # truncated artifact to later masquerade as a valid result.
        path.unlink(missing_ok=True)
        raise
    return {**verify_artifact(record, expected_study_id=study_id),
            "created": True, "path": str(path)}


def load(study_id: str, *, root: Path = _DEFAULT_ROOT) -> dict[str, Any]:
    if type(study_id) is not str or not _STUDY.fullmatch(study_id):
        raise Q7PrecommitError("Q7_STUDY_ID_INVALID")
    path = Path(root).resolve() / (study_id + ".json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Q7PrecommitError("Q7_ARTIFACT_READ_UNAVAILABLE") from exc
    verify_artifact(value, expected_study_id=study_id)
    return value


def inventory(simulation_db: Path) -> dict[str, Any]:
    """Descriptive, read-only raw cohort. No independence/returns claim."""
    db = Path(simulation_db).resolve()
    if not db.is_file():
        return {"status": "NO_SIMULATION_DB", "production_activation_allowed": False}
    try:
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            required = {
                "prospective_capture_run", "prospective_recommendation_sample",
                "prospective_evaluation_report",
            }
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                return {"status": "SCHEMA_NOT_READY", "production_activation_allowed": False}
            counts = conn.execute(
                "SELECT COUNT(DISTINCT r.id) AS captures,COUNT(s.sample_index) AS samples,"
                "COUNT(CASE WHEN s.action='ENTRY_CANDIDATE' THEN 1 END) AS entries,"
                "MIN(s.signal_date) AS first_signal,MAX(s.signal_date) AS latest_signal "
                "FROM prospective_capture_run r LEFT JOIN prospective_recommendation_sample s "
                "ON s.capture_run_id=r.id WHERE r.status='COMPLETE'"
            ).fetchone()
            strategies = [dict(x) for x in conn.execute(
                "SELECT s.strategy,COUNT(*) AS raw_entries,"
                "COUNT(DISTINCT s.signal_date || ':' || s.market || ':' || s.ticker || ':' || s.strategy) AS distinct_keys "
                "FROM prospective_recommendation_sample s JOIN prospective_capture_run r "
                "ON r.id=s.capture_run_id WHERE r.status='COMPLETE' AND s.action='ENTRY_CANDIDATE' "
                "GROUP BY s.strategy ORDER BY raw_entries DESC,s.strategy"
            )]
            reports = conn.execute("SELECT COUNT(*) FROM prospective_evaluation_report").fetchone()[0]
    except sqlite3.Error:
        return {"status": "SIMULATION_READ_UNAVAILABLE", "production_activation_allowed": False}
    return {
        "status": "DESCRIPTIVE_ONLY",
        "raw_complete_captures": counts["captures"],
        "raw_samples": counts["samples"],
        "raw_entry_samples": counts["entries"],
        "first_signal_date": counts["first_signal"],
        "latest_signal_date": counts["latest_signal"],
        "evaluation_reports": reports,
        "strategies": strategies,
        "independent_mature_verified_count": None,
        "raw_distinct_keys_are_independent_samples": False,
        "promotion_allowed": False,
        "production_activation_allowed": False,
        "runtime_db_writes": 0,
    }
