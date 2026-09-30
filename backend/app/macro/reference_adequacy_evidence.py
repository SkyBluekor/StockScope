from __future__ import annotations

import base64
import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator

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

REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_V1 = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_V1"
)
REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_V2"
)
REFERENCE_ADEQUACY_FAMILY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_FAMILY_V2"
)
REFERENCE_MODE = "EXPANDING_STRICTLY_PRIOR"
COMPACT_ENCODING = "VARINT_BASE64_GZIP_JSON_V2"
TAIL_PATH_ENCODING = "EXACT_KS_NUMERATOR_UNSIGNED_VARINT_V1"
MAD_PATH_ENCODING = "SCALED_NONNEGATIVE_NULLABLE_VARINT_V1"
LOGICAL_HASH_CONTRACT = "R21_LOGICAL_EVIDENCE_V1"

_FEATURE_ORDER = {
    feature_id: index for index, feature_id in enumerate(RATE_SPIKE_FEATURE_IDS)
}
_METHOD_ORDER = {TAIL_METHOD: 0, MAD_METHOD: 1}


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


def _encode_unsigned_varints(values: Iterable[int]) -> tuple[str, str, int]:
    payload = bytearray()
    count = 0
    for original in values:
        value = int(original)
        if value < 0:
            raise ValueError("Unsigned varint cannot encode a negative value.")
        count += 1
        while value >= 0x80:
            payload.append((value & 0x7F) | 0x80)
            value >>= 7
        payload.append(value)
    raw = bytes(payload)
    return (
        base64.b64encode(raw).decode("ascii"),
        hashlib.sha256(raw).hexdigest(),
        count,
    )


def _decode_unsigned_varints(encoded: str) -> Iterator[int]:
    raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    value = 0
    shift = 0
    for byte in raw:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift > 70:
                raise ValueError("Invalid oversized varint.")
            continue
        yield value
        value = 0
        shift = 0
    if shift:
        raise ValueError("Truncated varint payload.")


def _encode_nullable_nonnegative(
    values: Iterable[int | None],
) -> tuple[str, str, int]:
    return _encode_unsigned_varints(
        0 if value is None else int(value) + 1
        for value in values
    )


def _decode_nullable_nonnegative(encoded: str) -> Iterator[int | None]:
    for value in _decode_unsigned_varints(encoded):
        yield None if value == 0 else value - 1


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
    def __init__(self, slopes: list[int], block_size: int | None = None) -> None:
        self.slopes = slopes
        self.size = len(slopes)
        self.block_size = block_size or max(1, int(self.size ** 0.5) + 1)
        self.block_count = (self.size + self.block_size - 1) // self.block_size
        self.base = [0] * self.size
        self.lazy = [0] * self.block_count
        self.max_hulls: list[list[tuple[int, int]]] = [
            [] for _ in range(self.block_count)
        ]
        self.min_hulls: list[list[tuple[int, int]]] = [
            [] for _ in range(self.block_count)
        ]
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
        for index in range(start, right):
            self.base[index] += amount
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


def _decimal_scale_exponent(values: Iterable[Decimal | None]) -> int:
    exponent = 0
    for value in values:
        if value is None:
            continue
        current = -value.as_tuple().exponent
        if current > exponent:
            exponent = current
    return exponent


def _scaled_int(value: Decimal | None, scale: int) -> int | None:
    if value is None:
        return None
    scaled = value * scale
    if scaled != scaled.to_integral_value():
        raise ValueError("Decimal scale does not preserve an exact integer.")
    return int(scaled)


def _mad_states(
    rows: list[dict[str, Any]],
    max_prior: int,
) -> dict[int, dict[str, Decimal | None]]:
    result: dict[int, dict[str, Decimal | None]] = {}
    for row in rows:
        prior_count = int(row["prior_count"])
        if prior_count <= 0 or prior_count > max_prior:
            continue
        result[prior_count] = {
            "median": _decimal_or_none(row.get("prior_median")),
            "mad": _decimal_or_none(row.get("prior_mad")),
        }
    return result


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
        numerators: list[int] = []
        best_num: int | None = None
        best_later: int | None = None

        for later_n in range(first_later_n, max_prior + 1):
            appended_value = values[later_n - 1]
            envelope.add_suffix(positions[appended_value], anchor_n)
            added_count = later_n - anchor_n
            numerator = envelope.max_abs_at(-added_count)
            numerators.append(numerator)
            if best_num is None or (
                numerator * best_later > best_num * later_n
                if best_later is not None
                else True
            ):
                best_num = numerator
                best_later = later_n

        encoded, encoded_sha, count = _encode_unsigned_varints(numerators)
        comparison_count += count
        maximum = (
            _decimal_text(
                Decimal(best_num) / Decimal(anchor_n * best_later)
            )
            if best_num is not None and best_later is not None
            else None
        )
        anchors.append(
            {
                "anchor_n": anchor_n,
                "anchor_reference_hash": reference_hashes.get(anchor_n),
                "first_later_n": first_later_n,
                "suffix_transition_count": count,
                "distance_encoding": TAIL_PATH_ENCODING,
                "numerator_varints_b64": encoded,
                "encoded_path_sha256": encoded_sha,
                "max_ecdf_sup_distance": maximum,
                "argmax_prior_count": best_later,
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
        "path_encoding": TAIL_PATH_ENCODING,
        "observed_support_value_count": len(observed_support),
        "max_prior_count": max_prior,
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
    scale_exponent = _decimal_scale_exponent(
        value
        for state in states.values()
        for value in (state["median"], state["mad"])
    )
    scale = 10 ** scale_exponent

    anchors: list[dict[str, Any]] = []
    comparison_count = 0
    for anchor_n in support_points:
        if anchor_n <= 0 or anchor_n >= max_prior:
            continue
        anchor = states.get(anchor_n) or {"median": None, "mad": None}
        anchor_median = anchor["median"]
        anchor_mad = anchor["mad"]
        anchor_median_units = _scaled_int(anchor_median, scale)
        anchor_mad_units = _scaled_int(anchor_mad, scale)
        first_later_n = anchor_n + 1

        median_units: list[int | None] = []
        mad_units: list[int | None] = []
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
            median_units.append(_scaled_int(median_shift, scale))
            mad_units.append(_scaled_int(mad_shift, scale))

        median_encoded, median_sha, median_count = _encode_nullable_nonnegative(
            median_units
        )
        mad_encoded, mad_sha, mad_count = _encode_nullable_nonnegative(mad_units)
        if median_count != mad_count:
            raise ValueError("MAD compact path lengths diverged.")
        comparison_count += median_count

        def max_units(values: list[int | None]) -> tuple[int | None, int | None]:
            best_value: int | None = None
            best_n: int | None = None
            for offset, value in enumerate(values):
                if value is None:
                    continue
                if best_value is None or value > best_value:
                    best_value = value
                    best_n = first_later_n + offset
            return best_value, best_n

        median_max_units, median_argmax = max_units(median_units)
        mad_max_units, mad_argmax = max_units(mad_units)
        relative_status = (
            "NON_COMPUTABLE_ZERO_SCALE"
            if anchor_mad_units == 0
            else "AVAILABLE"
            if anchor_mad_units is not None
            else "UNAVAILABLE"
        )
        relative_max = (
            _decimal_text(
                Decimal(mad_max_units) / Decimal(abs(anchor_mad_units))
            )
            if (
                mad_max_units is not None
                and anchor_mad_units not in {None, 0}
            )
            else None
        )
        relative_argmax = (
            mad_argmax if relative_status == "AVAILABLE" else None
        )

        anchors.append(
            {
                "anchor_n": anchor_n,
                "anchor_reference_hash": reference_hashes.get(anchor_n),
                "anchor_median_units": anchor_median_units,
                "anchor_mad_units": anchor_mad_units,
                "first_later_n": first_later_n,
                "suffix_transition_count": median_count,
                "path_encoding": MAD_PATH_ENCODING,
                "absolute_median_shift_varints_b64": median_encoded,
                "absolute_median_shift_encoded_sha256": median_sha,
                "absolute_mad_shift_varints_b64": mad_encoded,
                "absolute_mad_shift_encoded_sha256": mad_sha,
                "relative_mad_shift_derivation": (
                    "ABSOLUTE_MAD_SHIFT_DIVIDED_BY_ABS_ANCHOR_MAD"
                ),
                "relative_mad_shift_status": relative_status,
                "max_absolute_median_shift": (
                    _decimal_text(Decimal(median_max_units) / Decimal(scale))
                    if median_max_units is not None
                    else None
                ),
                "argmax_absolute_median_shift_prior_count": median_argmax,
                "max_absolute_mad_shift": (
                    _decimal_text(Decimal(mad_max_units) / Decimal(scale))
                    if mad_max_units is not None
                    else None
                ),
                "argmax_absolute_mad_shift_prior_count": mad_argmax,
                "max_relative_mad_shift": relative_max,
                "argmax_relative_mad_shift_prior_count": relative_argmax,
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
        "path_encoding": MAD_PATH_ENCODING,
        "scale_exponent": scale_exponent,
        "zero_scale_rule": "NON_COMPUTABLE_ZERO_SCALE",
        "null_to_zero_forbidden": True,
        "max_prior_count": max_prior,
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


def _logical_digest_token(digest: Any, value: Any) -> None:
    if value is None:
        encoded = b"<NULL>"
    else:
        encoded = str(value).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def _sorted_families(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        families,
        key=lambda family: (
            _FEATURE_ORDER[str(family["feature_id"])],
            _METHOD_ORDER[str(family["method"])],
        ),
    )


def _logical_hash_v2(artifact: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    _logical_digest_token(digest, LOGICAL_HASH_CONTRACT)
    for support in artifact["support_points"]:
        _logical_digest_token(digest, int(support))

    for family in _sorted_families(list(artifact["families"])):
        method = str(family["method"])
        _logical_digest_token(digest, family["feature_id"])
        _logical_digest_token(digest, method)
        scale = 10 ** int(family.get("scale_exponent") or 0)

        for anchor in family["anchors"]:
            anchor_n = int(anchor["anchor_n"])
            first_later_n = int(anchor["first_later_n"])
            count = int(anchor["suffix_transition_count"])
            _logical_digest_token(digest, anchor_n)
            _logical_digest_token(digest, anchor.get("anchor_reference_hash"))
            _logical_digest_token(digest, count)

            if method == TAIL_METHOD:
                numerators = _decode_unsigned_varints(
                    anchor["numerator_varints_b64"]
                )
                actual = 0
                for offset, numerator in enumerate(numerators):
                    later_n = first_later_n + offset
                    value = _decimal_text(
                        Decimal(numerator) / Decimal(anchor_n * later_n)
                    )
                    _logical_digest_token(digest, value)
                    actual += 1
                if actual != count:
                    raise ValueError("TAIL decoded path length mismatch.")
            else:
                medians = _decode_nullable_nonnegative(
                    anchor["absolute_median_shift_varints_b64"]
                )
                mads = _decode_nullable_nonnegative(
                    anchor["absolute_mad_shift_varints_b64"]
                )
                anchor_mad_units = anchor.get("anchor_mad_units")
                actual = 0
                for median_units, mad_units in zip(medians, mads, strict=True):
                    median_value = (
                        _decimal_text(Decimal(median_units) / Decimal(scale))
                        if median_units is not None
                        else None
                    )
                    mad_value = (
                        _decimal_text(Decimal(mad_units) / Decimal(scale))
                        if mad_units is not None
                        else None
                    )
                    relative_value = (
                        _decimal_text(
                            Decimal(mad_units)
                            / Decimal(abs(int(anchor_mad_units)))
                        )
                        if (
                            mad_units is not None
                            and anchor_mad_units not in {None, 0}
                        )
                        else None
                    )
                    _logical_digest_token(digest, median_value)
                    _logical_digest_token(digest, mad_value)
                    _logical_digest_token(digest, relative_value)
                    actual += 1
                if actual != count:
                    raise ValueError("MAD decoded path length mismatch.")
    return digest.hexdigest()


def _logical_hash_v1(artifact: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    _logical_digest_token(digest, LOGICAL_HASH_CONTRACT)
    for support in artifact["support_points"]:
        _logical_digest_token(digest, int(support))

    for family in _sorted_families(list(artifact["families"])):
        method = str(family["method"])
        _logical_digest_token(digest, family["feature_id"])
        _logical_digest_token(digest, method)
        for anchor in family["anchors"]:
            _logical_digest_token(digest, int(anchor["anchor_n"]))
            _logical_digest_token(digest, anchor.get("anchor_reference_hash"))
            _logical_digest_token(
                digest, int(anchor["suffix_transition_count"])
            )
            if method == TAIL_METHOD:
                for value in anchor["ecdf_sup_distances"]:
                    _logical_digest_token(
                        digest,
                        _decimal_text(_decimal(value)),
                    )
            else:
                medians = anchor["absolute_median_shifts"]
                mads = anchor["absolute_mad_shifts"]
                relatives = anchor["relative_mad_shifts"]
                if not (len(medians) == len(mads) == len(relatives)):
                    raise ValueError("Legacy MAD path lengths diverged.")
                for median_value, mad_value, relative_value in zip(
                    medians, mads, relatives, strict=True
                ):
                    _logical_digest_token(
                        digest,
                        _decimal_text(_decimal_or_none(median_value)),
                    )
                    _logical_digest_token(
                        digest,
                        _decimal_text(_decimal_or_none(mad_value)),
                    )
                    _logical_digest_token(
                        digest,
                        _decimal_text(_decimal_or_none(relative_value)),
                    )
    return digest.hexdigest()


def logical_evidence_hash(artifact: dict[str, Any]) -> str:
    version = artifact.get("contract_version")
    if version == REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION:
        return _logical_hash_v2(artifact)
    if version == REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_V1:
        return _logical_hash_v1(artifact)
    raise ValueError("Unsupported reference adequacy evidence contract.")


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

    if (
        adequacy_protocol["contract_version"]
        != REFERENCE_ADEQUACY_PROTOCOL_CONTRACT_VERSION
    ):
        raise ValueError("R2.1 requires the current reference adequacy protocol.")
    if adequacy_state["ready_for_evidence_generation"] is not True:
        raise ValueError(
            "Reference adequacy protocol is not ready for evidence generation."
        )

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
            raise ValueError(
                f"Reference adequacy protocol lineage mismatch: {key}"
            )

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
                    stability,
                    feature_id=feature_id,
                    method=TAIL_METHOD,
                ),
            )
        )
        families.append(
            _mad_family_evidence(
                feature_id=feature_id,
                rows=rows,
                support_points=support_points,
                stability_family=_family(
                    stability,
                    feature_id=feature_id,
                    method=MAD_METHOD,
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

    logical_shell = {
        "support_points": support_points,
        "families": families,
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION,
    }
    logical_hash = _logical_hash_v2(logical_shell)

    identity_payload = {
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION,
        "source": source_payload,
        "encoding": {
            "representation": COMPACT_ENCODING,
            "container": "GZIP_JSON",
            "canonical_json": True,
            "gzip_mtime": 0,
            "tail_path_encoding": TAIL_PATH_ENCODING,
            "mad_path_encoding": MAD_PATH_ENCODING,
            "logical_hash_contract": LOGICAL_HASH_CONTRACT,
        },
        "evidence_contract": {
            "reference_mode": REFERENCE_MODE,
            "forward_rule": FORWARD_RULE,
            "candidate_support_universe": (
                "REFERENCE_STABILITY_COMMON_REVIEW_POINTS"
            ),
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
        "logical_evidence_hash": logical_hash,
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


def _identity_payload_v1(artifact: dict[str, Any]) -> dict[str, Any]:
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


def _identity_payload_v2(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in (
            "contract_version",
            "source",
            "encoding",
            "evidence_contract",
            "unresolved_policy_classes",
            "counts",
            "support_points",
            "family_payload_hash",
            "logical_evidence_hash",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }


def validate_reference_adequacy_evidence_v1(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") != REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_V1:
        raise ValueError("Unsupported legacy reference adequacy evidence contract.")
    if artifact.get("analysis_status") != "COMPLETE":
        raise ValueError("Legacy reference adequacy evidence must be COMPLETE.")
    if artifact.get("holdout_locked") is not True:
        raise ValueError("Legacy evidence must keep Holdout locked.")
    if artifact.get("holdout_accessed") is not False:
        raise ValueError("Legacy evidence must not access Holdout.")
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("Legacy evidence must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("Legacy evidence must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError("Legacy evidence must have no Production impact.")
    if artifact.get("family_payload_hash") != content_hash(artifact["families"]):
        raise ValueError("Legacy evidence family payload hash mismatch.")
    evidence_hash = content_hash(_identity_payload_v1(artifact))
    if artifact.get("evidence_hash") != evidence_hash:
        raise ValueError("Legacy evidence hash mismatch.")
    if artifact.get("evidence_id") != f"RATEADEQEVID-{evidence_hash[:16]}":
        raise ValueError("Legacy evidence id mismatch.")
    return {
        "evidence_id": artifact["evidence_id"],
        "evidence_hash": evidence_hash,
        "common_support_point_count": int(
            artifact["counts"]["common_support_point_count"]
        ),
        "forward_comparison_count": int(
            artifact["counts"]["forward_comparison_count"]
        ),
        "ready_for_b2": False,
        "ready_for_holdout": False,
    }


def validate_reference_adequacy_evidence(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") == REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_V1:
        return validate_reference_adequacy_evidence_v1(artifact)
    if (
        artifact.get("contract_version")
        != REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported reference adequacy evidence contract.")
    if artifact.get("analysis_status") != "COMPLETE":
        raise ValueError("Reference adequacy evidence must be COMPLETE.")
    if (
        artifact.get("holdout_locked") is not True
        or artifact.get("holdout_accessed") is not False
    ):
        raise ValueError(
            "Reference adequacy evidence must keep Holdout locked and unread."
        )
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("Reference adequacy evidence must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("Reference adequacy evidence must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError(
            "Reference adequacy evidence must have no Production impact."
        )

    encoding = artifact.get("encoding") or {}
    if encoding.get("representation") != COMPACT_ENCODING:
        raise ValueError("Reference adequacy compact encoding mismatch.")
    if encoding.get("container") != "GZIP_JSON":
        raise ValueError("Reference adequacy container must be gzip JSON.")
    if encoding.get("gzip_mtime") != 0:
        raise ValueError("Reference adequacy gzip mtime must be deterministic.")

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

    support_points = [int(value) for value in artifact.get("support_points") or []]
    if support_points != sorted(set(support_points)):
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

        method = family["method"]
        max_prior = int(family["max_prior_count"])
        expected_anchors = [
            n for n in support_points if 0 < n < max_prior
        ]
        anchors = list(family.get("anchors") or [])
        if [int(item["anchor_n"]) for item in anchors] != expected_anchors:
            raise ValueError("R2.1 family anchor universe mismatch.")

        scale = 10 ** int(family.get("scale_exponent") or 0)
        for anchor in anchors:
            anchor_n = int(anchor["anchor_n"])
            first_later_n = int(anchor["first_later_n"])
            expected_count = max_prior - anchor_n
            if first_later_n != anchor_n + 1:
                raise ValueError("R2.1 first later support mismatch.")
            if int(anchor["suffix_transition_count"]) != expected_count:
                raise ValueError("R2.1 suffix transition count mismatch.")

            if method == TAIL_METHOD:
                if family.get("path_encoding") != TAIL_PATH_ENCODING:
                    raise ValueError("TAIL path encoding mismatch.")
                raw = base64.b64decode(
                    anchor["numerator_varints_b64"].encode("ascii"),
                    validate=True,
                )
                if hashlib.sha256(raw).hexdigest() != anchor[
                    "encoded_path_sha256"
                ]:
                    raise ValueError("TAIL encoded path hash mismatch.")
                values = list(
                    _decode_unsigned_varints(anchor["numerator_varints_b64"])
                )
                if len(values) != expected_count:
                    raise ValueError("TAIL decoded path length mismatch.")
                best_num: int | None = None
                best_later: int | None = None
                for offset, numerator in enumerate(values):
                    later_n = first_later_n + offset
                    if best_num is None or (
                        numerator * best_later > best_num * later_n
                        if best_later is not None
                        else True
                    ):
                        best_num = numerator
                        best_later = later_n
                expected_max = (
                    _decimal_text(
                        Decimal(best_num) / Decimal(anchor_n * best_later)
                    )
                    if best_num is not None and best_later is not None
                    else None
                )
                if anchor.get("max_ecdf_sup_distance") != expected_max:
                    raise ValueError("TAIL max envelope summary mismatch.")
                if anchor.get("argmax_prior_count") != best_later:
                    raise ValueError("TAIL argmax summary mismatch.")
            else:
                if family.get("path_encoding") != MAD_PATH_ENCODING:
                    raise ValueError("MAD path encoding mismatch.")
                median_raw = base64.b64decode(
                    anchor["absolute_median_shift_varints_b64"].encode("ascii"),
                    validate=True,
                )
                mad_raw = base64.b64decode(
                    anchor["absolute_mad_shift_varints_b64"].encode("ascii"),
                    validate=True,
                )
                if hashlib.sha256(median_raw).hexdigest() != anchor[
                    "absolute_median_shift_encoded_sha256"
                ]:
                    raise ValueError("MAD median encoded path hash mismatch.")
                if hashlib.sha256(mad_raw).hexdigest() != anchor[
                    "absolute_mad_shift_encoded_sha256"
                ]:
                    raise ValueError("MAD scale encoded path hash mismatch.")

                median_values = list(
                    _decode_nullable_nonnegative(
                        anchor["absolute_median_shift_varints_b64"]
                    )
                )
                mad_values = list(
                    _decode_nullable_nonnegative(
                        anchor["absolute_mad_shift_varints_b64"]
                    )
                )
                if (
                    len(median_values) != expected_count
                    or len(mad_values) != expected_count
                ):
                    raise ValueError("MAD decoded path length mismatch.")

                def max_units(
                    values: list[int | None],
                ) -> tuple[int | None, int | None]:
                    best_value: int | None = None
                    best_n: int | None = None
                    for offset, value in enumerate(values):
                        if value is None:
                            continue
                        if best_value is None or value > best_value:
                            best_value = value
                            best_n = first_later_n + offset
                    return best_value, best_n

                median_max, median_argmax = max_units(median_values)
                mad_max, mad_argmax = max_units(mad_values)
                expected_median_max = (
                    _decimal_text(Decimal(median_max) / Decimal(scale))
                    if median_max is not None
                    else None
                )
                expected_mad_max = (
                    _decimal_text(Decimal(mad_max) / Decimal(scale))
                    if mad_max is not None
                    else None
                )
                if anchor.get("max_absolute_median_shift") != expected_median_max:
                    raise ValueError("MAD median max summary mismatch.")
                if anchor.get("max_absolute_mad_shift") != expected_mad_max:
                    raise ValueError("MAD scale max summary mismatch.")
                if (
                    anchor.get("argmax_absolute_median_shift_prior_count")
                    != median_argmax
                ):
                    raise ValueError("MAD median argmax mismatch.")
                if (
                    anchor.get("argmax_absolute_mad_shift_prior_count")
                    != mad_argmax
                ):
                    raise ValueError("MAD scale argmax mismatch.")

                anchor_mad_units = anchor.get("anchor_mad_units")
                status = anchor.get("relative_mad_shift_status")
                if anchor_mad_units == 0:
                    if status != "NON_COMPUTABLE_ZERO_SCALE":
                        raise ValueError("MAD zero-scale status mismatch.")
                    expected_relative_max = None
                    expected_relative_argmax = None
                elif anchor_mad_units is None:
                    if status != "UNAVAILABLE":
                        raise ValueError("MAD unavailable scale status mismatch.")
                    expected_relative_max = None
                    expected_relative_argmax = None
                else:
                    if status != "AVAILABLE":
                        raise ValueError("MAD relative status mismatch.")
                    expected_relative_max = (
                        _decimal_text(
                            Decimal(mad_max)
                            / Decimal(abs(int(anchor_mad_units)))
                        )
                        if mad_max is not None
                        else None
                    )
                    expected_relative_argmax = mad_argmax
                if anchor.get("max_relative_mad_shift") != expected_relative_max:
                    raise ValueError("MAD relative max summary mismatch.")
                if (
                    anchor.get("argmax_relative_mad_shift_prior_count")
                    != expected_relative_argmax
                ):
                    raise ValueError("MAD relative argmax mismatch.")

            if anchor.get("selection_status") != "NOT_SELECTED":
                raise ValueError("R2.1 anchor cannot select support.")
            forward_count += expected_count

    if int(artifact["counts"]["forward_comparison_count"]) != forward_count:
        raise ValueError("R2.1 forward comparison count mismatch.")
    if artifact.get("family_payload_hash") != content_hash(families):
        raise ValueError("R2.1 family payload hash mismatch.")

    actual_logical_hash = _logical_hash_v2(artifact)
    if artifact.get("logical_evidence_hash") != actual_logical_hash:
        raise ValueError("R2.1 logical evidence hash mismatch.")

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

    evidence_hash = content_hash(_identity_payload_v2(artifact))
    if artifact.get("evidence_hash") != evidence_hash:
        raise ValueError("R2.1 evidence hash mismatch.")
    if artifact.get("evidence_id") != f"RATEADEQEVID-{evidence_hash[:16]}":
        raise ValueError("R2.1 evidence id mismatch.")

    return {
        "evidence_id": artifact["evidence_id"],
        "evidence_hash": evidence_hash,
        "logical_evidence_hash": actual_logical_hash,
        "common_support_point_count": len(support_points),
        "reference_family_count": len(families),
        "forward_comparison_count": forward_count,
        "encoding": COMPACT_ENCODING,
        "ready_for_b2": False,
        "ready_for_holdout": False,
    }


def compare_legacy_v1_to_compact_v2(
    legacy: dict[str, Any],
    compact: dict[str, Any],
) -> dict[str, Any]:
    legacy_state = validate_reference_adequacy_evidence_v1(legacy)
    compact_state = validate_reference_adequacy_evidence(compact)
    if legacy["source"]["adequacy_protocol_hash"] != compact["source"][
        "adequacy_protocol_hash"
    ]:
        raise ValueError("V1/V2 adequacy protocol lineage mismatch.")
    if legacy["support_points"] != compact["support_points"]:
        raise ValueError("V1/V2 support-point universe mismatch.")
    if int(legacy_state["forward_comparison_count"]) != int(
        compact_state["forward_comparison_count"]
    ):
        raise ValueError("V1/V2 forward comparison count mismatch.")

    legacy_logical = _logical_hash_v1(legacy)
    compact_logical = compact_state["logical_evidence_hash"]
    if legacy_logical != compact_logical:
        raise ValueError("V1/V2 logical evidence mismatch.")
    return {
        "status": "PASS",
        "logical_evidence_hash": compact_logical,
        "forward_comparison_count": compact_state["forward_comparison_count"],
    }


def load_reference_adequacy_evidence_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fp:
            payload = json.load(fp)
    else:
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def canonical_compact_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def deterministic_gzip_bytes(payload: dict[str, Any]) -> bytes:
    raw = canonical_compact_json_bytes(payload)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def render_reference_adequacy_evidence_text(artifact: dict[str, Any]) -> str:
    state = validate_reference_adequacy_evidence(artifact)
    policy = artifact["policy_state"]
    return "\n".join(
        [
            (
                "NEXT-6B-S4.2-B.1.6-R2.1 "
                "BOUNDARY-ANCHORED REFERENCE ADEQUACY EVIDENCE V2"
            ),
            "",
            f"Common support points : {state['common_support_point_count']}",
            f"Families              : {state['reference_family_count']}",
            f"Forward comparisons   : {state['forward_comparison_count']}",
            f"Encoding              : {state['encoding']}",
            f"Logical evidence hash : {state['logical_evidence_hash']}",
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
