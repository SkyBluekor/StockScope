from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.calibration_candidate import RATE_SPIKE_FEATURE_IDS
from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.eligibility_reconstruction import validate_eligibility_reconstruction
from app.macro.identity import content_hash
from app.macro.reference_adequacy_protocol import (
    BLOCKERS as ADEQUACY_BLOCKERS,
    FORWARD_RULE,
    REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION,
    validate_reference_adequacy_protocol,
)
from app.macro.reference_stability import (
    MAD_METHOD,
    TAIL_METHOD,
    validate_reference_stability_evidence,
)

REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_V1"
)
REFERENCE_ADEQUACY_FAMILY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_FAMILY_V1"
)
REFERENCE_MODE = "EXPANDING_STRICTLY_PRIOR"


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Reference adequacy evidence requires finite values.")
    return result


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _research_rows(
    research: dict[str, Any],
    feature_id: str,
) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in research["feature_results"][feature_id]["expanding"]["rows"]
    ]
    rows.sort(key=lambda item: int(item["prior_count"]))
    actual = [int(row["prior_count"]) for row in rows]
    if actual != list(range(len(rows))):
        raise ValueError("Reference adequacy evidence requires contiguous prior counts.")
    return rows


def _family(
    stability: dict[str, Any],
    *,
    feature_id: str,
    method: str,
) -> dict[str, Any]:
    for family in stability["families"]:
        if family["feature_id"] == feature_id and family["method"] == method:
            return family
    raise ValueError("Reference stability family is missing.")


def _reference_hash_index(
    stability_family: dict[str, Any],
) -> dict[int, str]:
    result: dict[int, str] = {}
    for transition in stability_family["transitions"]:
        before = int(transition["prior_count_before"])
        after = int(transition["prior_count_after"])
        result[before] = str(transition["reference_hash_before"])
        result[after] = str(transition["reference_hash_after"])
    return result


def _common_support_points(stability: dict[str, Any]) -> list[int]:
    values = [
        int(point["minimum_prior_observations"])
        for point in stability["common_support_review_points"]
    ]
    if values != sorted(set(values)):
        raise ValueError("Common support review points must be sorted and unique.")
    return values


def _build_max_hull(lines: list[tuple[int, int]]) -> list[tuple[int, int]]:
    compact: list[tuple[int, int]] = []
    for slope, intercept in lines:
        if compact and compact[-1][0] == slope:
            if intercept > compact[-1][1]:
                compact[-1] = (slope, intercept)
            continue
        compact.append((slope, intercept))

    hull: list[tuple[int, int]] = []
    for line in compact:
        while len(hull) >= 2:
            m1, b1 = hull[-2]
            m2, b2 = hull[-1]
            m3, b3 = line
            if (b1 - b2) * (m3 - m2) >= (b2 - b3) * (m2 - m1):
                hull.pop()
            else:
                break
        hull.append(line)
    return hull


def _query_max_hull(hull: list[tuple[int, int]], x: int) -> int:
    if not hull:
        return 0

    def value(index: int) -> int:
        slope, intercept = hull[index]
        return slope * x + intercept

    lo = 0
    hi = len(hull) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if value(mid) <= value(mid + 1):
            lo = mid + 1
        else:
            hi = mid
    return value(lo)


class _SuffixEnvelope:
    """Exact suffix-range additions plus global max/min line queries.

    Each support point j represents:
        g_m(j) = N * B_m(j) - m * A_N(j)

    A_N(j) is fixed for one anchor and becomes the line slope. Each appended
    observation adds N to B_m(j) for the suffix at/above its support rank.
    Querying at x=-m therefore yields the exact KS numerator without scanning
    every support point for every later t.
    """

    def __init__(self, slopes: list[int], block_size: int | None = None) -> None:
        self.slopes = slopes
        self.size = len(slopes)
        self.block_size = block_size or max(1, int(self.size ** 0.5) + 1)
        self.block_count = (self.size + self.block_size - 1) // self.block_size
        self.base = [0] * self.size
        self.lazy = [0] * self.block_count
        self.max_hulls: list[list[tuple[int, int]]] = [[] for _ in range(self.block_count)]
        self.min_hulls: list[list[tuple[int, int]]] = [[] for _ in range(self.block_count)]
        for block in range(self.block_count):
            self._rebuild(block)

    def _bounds(self, block: int) -> tuple[int, int]:
        left = block * self.block_size
        return left, min(self.size, left + self.block_size)

    def _rebuild(self, block: int) -> None:
        left, right = self._bounds(block)
        lines = [(self.slopes[i], self.base[i]) for i in range(left, right)]
        self.max_hulls[block] = _build_max_hull(lines)
        self.min_hulls[block] = _build_max_hull(
            sorted((-slope, -intercept) for slope, intercept in lines)
        )

    def add_suffix(self, start: int, amount: int) -> None:
        if start < 0 or start >= self.size:
            raise ValueError("Suffix update support rank is out of range.")
        first_block = start // self.block_size
        _, right = self._bounds(first_block)
        for i in range(start, right):
            self.base[i] += amount
        self._rebuild(first_block)
        for block in range(first_block + 1, self.block_count):
            self.lazy[block] += amount

    def max_abs_at(self, x: int) -> int:
        maximum: int | None = None
        minimum: int | None = None
        for block in range(self.block_count):
            lazy = self.lazy[block]
            block_max = _query_max_hull(self.max_hulls[block], x) + lazy
            block_min = -_query_max_hull(self.min_hulls[block], x) + lazy
            maximum = block_max if maximum is None else max(maximum, block_max)
            minimum = block_min if minimum is None else min(minimum, block_min)
        if maximum is None or minimum is None:
            return 0
        return max(abs(maximum), abs(minimum))


def _anchor_cumulative_counts(
    values: list[Decimal],
    *,
    support: list[Decimal],
    positions: dict[Decimal, int],
    anchor_n: int,
) -> list[int]:
    exact = [0] * len(support)
    for value in values[:anchor_n]:
        exact[positions[value]] += 1
    running = 0
    cumulative: list[int] = []
    for count in exact:
        running += count
        cumulative.append(running)
    return cumulative


def _max_with_arg(
    values: list[str | None],
    *,
    first_later_n: int,
) -> tuple[str | None, int | None]:
    best_value: Decimal | None = None
    best_n: int | None = None
    for offset, value in enumerate(values):
        if value is None:
            continue
        parsed = _decimal(value)
        if best_value is None or parsed > best_value:
            best_value = parsed
            best_n = first_later_n + offset
    return _decimal_text(best_value), best_n


def _tail_family_evidence(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    support_points: list[int],
    stability_family: dict[str, Any],
) -> dict[str, Any]:
    max_prior = len(rows) - 1
    values = [_decimal(row["value"]) for row in rows]
    observed_support = sorted(set(values[:max_prior]))
    positions = {value: index for index, value in enumerate(observed_support)}
    reference_hashes = _reference_hash_index(stability_family)

    anchors: list[dict[str, Any]] = []
    comparison_count = 0
    for anchor_n in support_points:
        if anchor_n <= 0 or anchor_n >= max_prior:
            continue
        first_later_n = anchor_n + 1
        anchor_counts = _anchor_cumulative_counts(
            values,
            support=observed_support,
            positions=positions,
            anchor_n=anchor_n,
        )
        envelope = _SuffixEnvelope(anchor_counts)
        path: list[str] = []
        for later_n in range(first_later_n, max_prior + 1):
            appended_value = values[later_n - 1]
            envelope.add_suffix(positions[appended_value], anchor_n)
            added_count = later_n - anchor_n
            numerator = envelope.max_abs_at(-added_count)
            distance = Decimal(numerator) / Decimal(anchor_n * later_n)
            path.append(_decimal_text(distance) or "0")

        maximum, argmax = _max_with_arg(path, first_later_n=first_later_n)
        comparison_count += len(path)
        anchors.append(
            {
                "anchor_n": anchor_n,
                "anchor_reference_hash": reference_hashes.get(anchor_n),
                "first_later_n": first_later_n,
                "suffix_transition_count": len(path),
                "ecdf_sup_distances": path,
                "max_ecdf_sup_distance": maximum,
                "argmax_prior_count": argmax,
                "path_hash": content_hash(path),
                "selection_status": "NOT_SELECTED",
            }
        )

    payload = {
        "contract_version": REFERENCE_ADEQUACY_FAMILY_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": TAIL_METHOD,
        "reference_mode": REFERENCE_MODE,
        "forward_rule": FORWARD_RULE,
        "metric": "ECDF_SUP_DISTANCE",
        "evaluation_support": "OBSERVED_VALUES_UNION_ONLY",
        "invented_x_grid_points": 0,
        "algorithm": "EXACT_SUFFIX_ENVELOPE_SQRT_DECOMPOSITION_V1",
        "observed_support_value_count": len(observed_support),
        "max_prior_count": max_prior,
        "reference_state_index": [
            [prior_count, reference_hashes.get(prior_count)]
            for prior_count in range(1, max_prior + 1)
        ],
        "anchor_count": len(anchors),
        "forward_comparison_count": comparison_count,
        "anchors": anchors,
        "tolerance": None,
        "adequacy_pass": "UNRESOLVED",
        "selection_status": "NOT_SELECTED",
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATEADEQEVFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def _mad_states(rows: list[dict[str, Any]], max_prior: int) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        prior_count = int(row["prior_count"])
        if prior_count <= 0 or prior_count > max_prior:
            continue
        median = _decimal_or_none(row.get("prior_median"))
        mad = _decimal_or_none(row.get("prior_mad"))
        result[prior_count] = {
            "median": median,
            "mad": mad,
        }
    return result


def _mad_family_evidence(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    support_points: list[int],
    stability_family: dict[str, Any],
) -> dict[str, Any]:
    max_prior = len(rows) - 1
    states = _mad_states(rows, max_prior)
    reference_hashes = _reference_hash_index(stability_family)

    anchors: list[dict[str, Any]] = []
    comparison_count = 0
    for anchor_n in support_points:
        if anchor_n <= 0 or anchor_n >= max_prior:
            continue
        anchor = states.get(anchor_n) or {"median": None, "mad": None}
        anchor_median = anchor["median"]
        anchor_mad = anchor["mad"]
        first_later_n = anchor_n + 1

        median_path: list[str | None] = []
        mad_path: list[str | None] = []
        relative_path: list[str | None] = []
        relative_status = (
            "NON_COMPUTABLE_ZERO_SCALE"
            if anchor_mad == 0
            else "AVAILABLE"
            if anchor_mad is not None
            else "UNAVAILABLE"
        )

        for later_n in range(first_later_n, max_prior + 1):
            later = states.get(later_n) or {"median": None, "mad": None}
            later_median = later["median"]
            later_mad = later["mad"]

            median_shift = (
                abs(later_median - anchor_median)
                if anchor_median is not None and later_median is not None
                else None
            )
            mad_shift = (
                abs(later_mad - anchor_mad)
                if anchor_mad is not None and later_mad is not None
                else None
            )
            relative_shift = (
                mad_shift / abs(anchor_mad)
                if mad_shift is not None and anchor_mad not in {None, Decimal(0)}
                else None
            )
            median_path.append(_decimal_text(median_shift))
            mad_path.append(_decimal_text(mad_shift))
            relative_path.append(_decimal_text(relative_shift))

        median_max, median_argmax = _max_with_arg(
            median_path, first_later_n=first_later_n
        )
        mad_max, mad_argmax = _max_with_arg(
            mad_path, first_later_n=first_later_n
        )
        relative_max, relative_argmax = _max_with_arg(
            relative_path, first_later_n=first_later_n
        )
        comparison_count += len(median_path)
        path_payload = {
            "absolute_median_shifts": median_path,
            "absolute_mad_shifts": mad_path,
            "relative_mad_shifts": relative_path,
        }
        anchors.append(
            {
                "anchor_n": anchor_n,
                "anchor_reference_hash": reference_hashes.get(anchor_n),
                "anchor_median": _decimal_text(anchor_median),
                "anchor_mad": _decimal_text(anchor_mad),
                "first_later_n": first_later_n,
                "suffix_transition_count": len(median_path),
                **path_payload,
                "relative_mad_shift_status": relative_status,
                "max_absolute_median_shift": median_max,
                "argmax_absolute_median_shift_prior_count": median_argmax,
                "max_absolute_mad_shift": mad_max,
                "argmax_absolute_mad_shift_prior_count": mad_argmax,
                "max_relative_mad_shift": relative_max,
                "argmax_relative_mad_shift_prior_count": relative_argmax,
                "path_hash": content_hash(path_payload),
                "selection_status": "NOT_SELECTED",
            }
        )

    payload = {
        "contract_version": REFERENCE_ADEQUACY_FAMILY_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": MAD_METHOD,
        "reference_mode": REFERENCE_MODE,
        "forward_rule": FORWARD_RULE,
        "metrics": [
            "ABSOLUTE_MEDIAN_SHIFT",
            "ABSOLUTE_MAD_SHIFT",
            "RELATIVE_MAD_SHIFT",
        ],
        "combination_rule": "ALL_AND",
        "zero_scale_rule": "NON_COMPUTABLE_ZERO_SCALE",
        "null_to_zero_forbidden": True,
        "max_prior_count": max_prior,
        "reference_state_index": [
            [prior_count, reference_hashes.get(prior_count)]
            for prior_count in range(1, max_prior + 1)
        ],
        "anchor_count": len(anchors),
        "forward_comparison_count": comparison_count,
        "anchors": anchors,
        "tolerances": {
            "absolute_median_shift": None,
            "absolute_mad_shift": None,
            "relative_mad_shift": None,
        },
        "adequacy_pass": "UNRESOLVED",
        "selection_status": "NOT_SELECTED",
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATEADEQEVFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def build_reference_adequacy_evidence(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
    reconstruction: dict[str, Any],
    stability: dict[str, Any],
    adequacy_protocol: dict[str, Any],
    source_main_sha: str | None = None,
) -> dict[str, Any]:
    development_state = validate_development_artifact(development_dataset)
    protocol_state = validate_research_protocol(
        protocol,
        development_dataset_hash=development_state["dataset_hash"],
    )
    research_state = validate_distribution_research_artifact(
        research,
        development_dataset_hash=development_state["dataset_hash"],
        protocol_hash=protocol_state["protocol_hash"],
    )
    reconstruction_state = validate_eligibility_reconstruction(reconstruction)
    stability_state = validate_reference_stability_evidence(stability)
    adequacy_state = validate_reference_adequacy_protocol(adequacy_protocol)

    if adequacy_protocol["contract_version"] != REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION:
        raise ValueError("R2.1 requires the current reference adequacy protocol.")
    if adequacy_state["ready_for_evidence_generation"] is not True:
        raise ValueError("Reference adequacy protocol is not ready for evidence generation.")

    expected_lineage = {
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "reconstruction_hash": reconstruction["reconstruction_hash"],
        "reference_stability_hash": stability_state["stability_hash"],
    }
    source = adequacy_protocol["source"]
    for key, expected in expected_lineage.items():
        if source.get(key) != expected:
            raise ValueError(f"Reference adequacy protocol lineage mismatch: {key}")

    if int(reconstruction["counts"]["raw_candidate_count"]) != int(
        reconstruction_state["raw_candidate_count"]
    ):
        raise ValueError("R2.1 reconstruction raw candidate count mismatch.")

    support_points = _common_support_points(stability)
    families: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        rows = _research_rows(research, feature_id)
        families.append(
            _tail_family_evidence(
                feature_id=feature_id,
                rows=rows,
                support_points=support_points,
                stability_family=_family(
                    stability, feature_id=feature_id, method=TAIL_METHOD
                ),
            )
        )
        families.append(
            _mad_family_evidence(
                feature_id=feature_id,
                rows=rows,
                support_points=support_points,
                stability_family=_family(
                    stability, feature_id=feature_id, method=MAD_METHOD
                ),
            )
        )

    policy_state = {
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    source_payload = {
        **expected_lineage,
        "reconstruction_id": reconstruction["reconstruction_id"],
        "reference_stability_id": stability["stability_id"],
        "adequacy_protocol_id": adequacy_protocol["adequacy_protocol_id"],
        "adequacy_protocol_hash": adequacy_state["adequacy_protocol_hash"],
        "source_main_sha": source_main_sha or "UNSPECIFIED",
    }
    counts = {
        "common_support_point_count": len(support_points),
        "tail_family_count": 3,
        "mad_family_count": 3,
        "reference_family_count": 6,
        "forward_comparison_count": sum(
            int(family["forward_comparison_count"]) for family in families
        ),
    }
    identity_payload = {
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION,
        "source": source_payload,
        "evidence_contract": {
            "reference_mode": REFERENCE_MODE,
            "forward_rule": FORWARD_RULE,
            "candidate_support_universe": "REFERENCE_STABILITY_COMMON_REVIEW_POINTS",
            "candidate_support_points_hash": content_hash(support_points),
            "tail_metric": "ECDF_SUP_DISTANCE",
            "tail_evaluation_support": "OBSERVED_VALUES_UNION_ONLY",
            "tail_invented_x_grid_points": 0,
            "mad_metrics": [
                "ABSOLUTE_MEDIAN_SHIFT",
                "ABSOLUTE_MAD_SHIFT",
                "RELATIVE_MAD_SHIFT",
            ],
            "temporal_perturbation_role": "OPTIONAL_DIAGNOSTIC_ONLY",
            "local_transition_role": "DIAGNOSTIC_ONLY",
            "weighted_stability_score": None,
            "tolerance_selection_performed": False,
            "minimum_n_selection_performed": False,
            "validation_suffix_selection_performed": False,
        },
        "unresolved_policy_classes": list(ADEQUACY_BLOCKERS),
        "counts": counts,
        "support_points": support_points,
        "family_payload_hash": content_hash(families),
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    evidence_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "evidence_id": f"RATEADEQEVID-{evidence_hash[:16]}",
        "evidence_hash": evidence_hash,
        "analysis_status": "COMPLETE",
        "families": families,
    }


def _identity_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in (
            "contract_version",
            "source",
            "evidence_contract",
            "unresolved_policy_classes",
            "counts",
            "support_points",
            "family_payload_hash",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }


def validate_reference_adequacy_evidence(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("contract_version") != REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION:
        raise ValueError("Unsupported reference adequacy evidence contract.")
    if artifact.get("analysis_status") != "COMPLETE":
        raise ValueError("Reference adequacy evidence must be COMPLETE.")
    if artifact.get("holdout_locked") is not True or artifact.get("holdout_accessed") is not False:
        raise ValueError("Reference adequacy evidence must keep Holdout locked and unread.")
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("Reference adequacy evidence must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("Reference adequacy evidence must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError("Reference adequacy evidence must have no Production impact.")

    contract = artifact.get("evidence_contract") or {}
    if contract.get("forward_rule") != FORWARD_RULE:
        raise ValueError("Reference adequacy forward rule mismatch.")
    if contract.get("tail_invented_x_grid_points") != 0:
        raise ValueError("R2.1 cannot invent TAIL x-grid points.")
    if contract.get("weighted_stability_score") is not None:
        raise ValueError("R2.1 weighted stability score is forbidden.")
    for key in (
        "tolerance_selection_performed",
        "minimum_n_selection_performed",
        "validation_suffix_selection_performed",
    ):
        if contract.get(key) is not False:
            raise ValueError(f"R2.1 selection flag must remain false: {key}")

    support_points = list(artifact.get("support_points") or [])
    if support_points != sorted(set(int(value) for value in support_points)):
        raise ValueError("R2.1 support points must be sorted and unique.")

    families = list(artifact.get("families") or [])
    if len(families) != 6:
        raise ValueError("R2.1 requires six TAIL/MAD families.")
    forward_count = 0
    for family in families:
        if family.get("forward_rule") != FORWARD_RULE:
            raise ValueError("R2.1 family forward rule mismatch.")
        if family.get("selection_status") != "NOT_SELECTED":
            raise ValueError("R2.1 family cannot select support.")
        if family.get("adequacy_pass") != "UNRESOLVED":
            raise ValueError("R2.1 family cannot approve adequacy.")
        anchors = list(family.get("anchors") or [])
        if [int(item["anchor_n"]) for item in anchors] != [
            n for n in support_points if 0 < n < int(family["max_prior_count"])
        ]:
            raise ValueError("R2.1 family anchor universe mismatch.")
        for anchor in anchors:
            expected_count = int(family["max_prior_count"]) - int(anchor["anchor_n"])
            if int(anchor["suffix_transition_count"]) != expected_count:
                raise ValueError("R2.1 suffix transition count mismatch.")
            if anchor.get("selection_status") != "NOT_SELECTED":
                raise ValueError("R2.1 anchor cannot select support.")
            if family["method"] == TAIL_METHOD:
                if len(anchor["ecdf_sup_distances"]) != expected_count:
                    raise ValueError("TAIL forward path length mismatch.")
            else:
                for key in (
                    "absolute_median_shifts",
                    "absolute_mad_shifts",
                    "relative_mad_shifts",
                ):
                    if len(anchor[key]) != expected_count:
                        raise ValueError("MAD forward path length mismatch.")
                if anchor.get("anchor_mad") == "0":
                    if anchor.get("relative_mad_shift_status") != "NON_COMPUTABLE_ZERO_SCALE":
                        raise ValueError("MAD zero-scale status mismatch.")
                    if any(value is not None for value in anchor["relative_mad_shifts"]):
                        raise ValueError("MAD zero-scale relative shifts must remain null.")
            forward_count += expected_count

    if int(artifact["counts"]["forward_comparison_count"]) != forward_count:
        raise ValueError("R2.1 forward comparison count mismatch.")
    if artifact.get("family_payload_hash") != content_hash(families):
        raise ValueError("R2.1 family payload hash mismatch.")

    expected_policy = {
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if artifact.get("policy_state") != expected_policy:
        raise ValueError("R2.1 policy state changed.")

    evidence_hash = content_hash(_identity_payload(artifact))
    if artifact.get("evidence_hash") != evidence_hash:
        raise ValueError("R2.1 evidence hash mismatch.")
    if artifact.get("evidence_id") != f"RATEADEQEVID-{evidence_hash[:16]}":
        raise ValueError("R2.1 evidence id mismatch.")

    return {
        "evidence_id": artifact["evidence_id"],
        "evidence_hash": evidence_hash,
        "common_support_point_count": len(support_points),
        "forward_comparison_count": forward_count,
        "ready_for_b2": False,
        "ready_for_holdout": False,
    }


def render_reference_adequacy_evidence_text(artifact: dict[str, Any]) -> str:
    state = validate_reference_adequacy_evidence(artifact)
    policy = artifact["policy_state"]
    return "\n".join(
        [
            "NEXT-6B-S4.2-B.1.6-R2.1 BOUNDARY-ANCHORED REFERENCE ADEQUACY EVIDENCE",
            "",
            f"Common support points : {state['common_support_point_count']}",
            "TAIL families         : 3",
            "MAD families          : 3",
            "EPT reference gate    : EXCLUDED",
            f"Forward comparisons   : {state['forward_comparison_count']}",
            "Forward paths         : COMPLETE",
            "Tolerance selection   : NOT PERFORMED",
            "Minimum N selection   : NOT PERFORMED",
            "Validation suffix     : UNRESOLVED",
            "",
            f"Reference adequacy    : {policy['reference_adequacy']}",
            f"Minimum prior N       : {policy['minimum_prior_observations']}",
            f"Holdout accessed      : {artifact['holdout_accessed']}",
            f"Network requests      : {artifact['network_requests']}",
            f"Macro DB writes       : {artifact['macro_db_writes']}",
            f"Production            : {artifact['production_impact']}",
            "",
            "B.2 readiness         : BLOCKED",
            "Holdout readiness     : BLOCKED",
        ]
    )
