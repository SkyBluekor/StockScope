from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import mean, median, pstdev
from typing import Any


MACRO_DISTRIBUTION_CONTRACT_VERSION = "VN_NEXT6B_S3_DISTRIBUTION_V1"
RESEARCH_FEATURE_IDS = (
    "rate_level_pct",
    "delta_bp_1obs",
    "delta_bp_5obs",
    "delta_bp_10obs",
)


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Distribution input must be numeric.") from exc
    if not result.is_finite():
        raise ValueError("Distribution input must be finite.")
    return result


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _fraction(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def median_absolute_deviation(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    center = median(values)
    return median([abs(value - center) for value in values])


def summarize_values(values: list[Decimal]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "population_stddev": None,
            "mad": None,
            "positive_count": 0,
            "zero_count": 0,
            "negative_count": 0,
        }
    med = median(values)
    mad = median_absolute_deviation(values)
    return {
        "count": len(values),
        "min": _decimal_text(min(values)),
        "max": _decimal_text(max(values)),
        "mean": _decimal_text(mean(values)),
        "median": _decimal_text(med),
        "population_stddev": _decimal_text(pstdev(values)),
        "mad": _decimal_text(mad),
        "positive_count": sum(value > 0 for value in values),
        "zero_count": sum(value == 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
    }


def empirical_cdf(values: list[Decimal]) -> list[dict[str, Any]]:
    if not values:
        return []
    counts: dict[Decimal, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    total = len(values)
    cumulative = 0
    result: list[dict[str, Any]] = []
    for value in sorted(counts):
        count = counts[value]
        cumulative += count
        result.append(
            {
                "value": _decimal_text(value),
                "count": count,
                "cumulative_count_le": cumulative,
                "fraction_le": _fraction(cumulative, total),
            }
        )
    return result


def tail_profile(values: list[Decimal]) -> dict[str, list[dict[str, Any]]]:
    if not values:
        return {"positive": [], "negative": [], "absolute": []}
    total = len(values)
    positive_values = sorted({value for value in values if value > 0})
    negative_values = sorted({value for value in values if value < 0})
    absolute_values = sorted({abs(value) for value in values if value != 0})

    positive = [
        {
            "value": _decimal_text(value),
            "count_ge": sum(item >= value for item in values),
            "fraction_ge": _fraction(sum(item >= value for item in values), total),
        }
        for value in positive_values
    ]
    negative = [
        {
            "value": _decimal_text(value),
            "count_le": sum(item <= value for item in values),
            "fraction_le": _fraction(sum(item <= value for item in values), total),
        }
        for value in negative_values
    ]
    absolute = [
        {
            "absolute_value": _decimal_text(value),
            "count_abs_ge": sum(abs(item) >= value for item in values),
            "fraction_abs_ge": _fraction(
                sum(abs(item) >= value for item in values),
                total,
            ),
        }
        for value in absolute_values
    ]
    return {
        "positive": positive,
        "negative": negative,
        "absolute": absolute,
    }


def _feature_from_row(row: dict[str, Any], feature_id: str) -> dict[str, Any] | None:
    for feature in row.get("features", []):
        if feature.get("feature_id") == feature_id:
            return feature
    return None


def extract_feature_series(
    rows: list[dict[str, Any]],
    feature_id: str,
) -> tuple[list[dict[str, Any]], int]:
    series: list[dict[str, Any]] = []
    unavailable = 0
    for row in rows:
        feature = _feature_from_row(row, feature_id)
        if (
            feature is None
            or feature.get("status") != "AVAILABLE"
            or feature.get("value") is None
        ):
            unavailable += 1
            continue
        series.append(
            {
                "observation_date": str(row["observation_date"]),
                "value": _decimal(feature["value"]),
                "row_hash": row["row_hash"],
            }
        )
    return series, unavailable


def build_expanding_analysis(
    series: list[dict[str, Any]],
) -> dict[str, Any]:
    prior: list[Decimal] = []
    rows: list[dict[str, Any]] = []
    percentile_available = 0
    robust_available = 0

    for item in series:
        value = item["value"]
        if not prior:
            rows.append(
                {
                    "observation_date": item["observation_date"],
                    "row_hash": item["row_hash"],
                    "value": _decimal_text(value),
                    "prior_count": 0,
                    "empirical_percentile_le": None,
                    "positive_tail_fraction_ge": None,
                    "prior_median": None,
                    "prior_mad": None,
                    "robust_deviation_mad": None,
                    "status": "INSUFFICIENT_HISTORY",
                    "reason": "NO_PRIOR_OBSERVATIONS",
                }
            )
            prior.append(value)
            continue

        prior_count = len(prior)
        count_le = sum(previous <= value for previous in prior)
        count_ge = sum(previous >= value for previous in prior)
        prior_median = median(prior)
        prior_mad = median_absolute_deviation(prior)
        robust = None
        reason = None
        status = "AVAILABLE"
        if prior_mad is None or prior_mad == 0:
            reason = "PRIOR_MAD_ZERO"
        else:
            robust = (value - prior_median) / prior_mad
            robust_available += 1

        percentile_available += 1
        rows.append(
            {
                "observation_date": item["observation_date"],
                "row_hash": item["row_hash"],
                "value": _decimal_text(value),
                "prior_count": prior_count,
                "empirical_percentile_le": _fraction(count_le, prior_count),
                "positive_tail_fraction_ge": _fraction(count_ge, prior_count),
                "prior_median": _decimal_text(prior_median),
                "prior_mad": _decimal_text(prior_mad),
                "robust_deviation_mad": _decimal_text(robust),
                "status": status,
                "reason": reason,
            }
        )
        prior.append(value)

    return {
        "rule": "STRICTLY_PRIOR_DEVELOPMENT_ROWS_ONLY",
        "lookback_mode": "EXPANDING",
        "minimum_sample_policy_defined": False,
        "selected_rolling_lookback": None,
        "row_count": len(rows),
        "percentile_available_count": percentile_available,
        "robust_deviation_available_count": robust_available,
        "rows": rows,
    }


def build_yearly_summary(
    series: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Decimal]] = defaultdict(list)
    for item in series:
        year = str(item["observation_date"])[:4]
        groups[year].append(item["value"])
    return {
        year: summarize_values(values)
        for year, values in sorted(groups.items())
    }


def analyze_feature_distribution(
    rows: list[dict[str, Any]],
    feature_id: str,
) -> dict[str, Any]:
    if feature_id not in RESEARCH_FEATURE_IDS:
        raise ValueError(f"Unsupported research feature: {feature_id}")
    series, unavailable = extract_feature_series(rows, feature_id)
    values = [item["value"] for item in series]
    return {
        "contract_version": MACRO_DISTRIBUTION_CONTRACT_VERSION,
        "feature_id": feature_id,
        "available_count": len(series),
        "unavailable_count": unavailable,
        "summary": summarize_values(values),
        "empirical_cdf": empirical_cdf(values),
        "tail_profile": tail_profile(values),
        "expanding": build_expanding_analysis(series),
        "yearly_summary": build_yearly_summary(series),
        "selected_threshold": None,
        "selected_minimum_sample": None,
        "selected_rolling_lookback": None,
    }
