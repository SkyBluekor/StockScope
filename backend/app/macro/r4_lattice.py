from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Any

NEG_INF = {"kind": "NEG_INF"}
POS_INF = {"kind": "POS_INF"}


def _sorted(values: Iterable[Fraction]) -> list[Fraction]:
    out = sorted(values)
    if not out:
        raise ValueError("EMPTY_SAMPLE")
    return out


def _frac(value: Fraction) -> dict[str, int]:
    return {"num": value.numerator, "den": value.denominator}


def q_minus(values: Iterable[Fraction], p: Fraction) -> Fraction:
    xs = _sorted(values)
    if p <= 0 or p > 1:
        raise ValueError("Q_MINUS_PROBABILITY_OUT_OF_RANGE")
    n = len(xs)
    k = (p.numerator * n + p.denominator - 1) // p.denominator
    return xs[max(0, k - 1)]


def q_plus(values: Iterable[Fraction], p: Fraction) -> Fraction:
    xs = _sorted(values)
    if p < 0 or p >= 1:
        raise ValueError("Q_PLUS_PROBABILITY_OUT_OF_RANGE")
    n = len(xs)
    k = (p.numerator * n) // p.denominator + 1
    return xs[k - 1]


def median_set(values: Iterable[Fraction]) -> tuple[Fraction, Fraction]:
    xs = list(values)
    return q_minus(xs, Fraction(1, 2)), q_plus(xs, Fraction(1, 2))


def midpoint_median(values: Iterable[Fraction]) -> Fraction:
    lo, hi = median_set(values)
    return (lo + hi) / 2


def raw_mad(values: Iterable[Fraction]) -> Fraction:
    xs = list(values)
    m = midpoint_median(xs)
    return midpoint_median([abs(x - m) for x in xs])


def median_outer_interval(values: Iterable[Fraction], e: Fraction) -> tuple[Any, Any]:
    xs = list(values)
    if e < 0:
        raise ValueError("NEGATIVE_BAND_WIDTH")
    lo_p = Fraction(1, 2) - e
    hi_p = Fraction(1, 2) + e
    lo: Any = NEG_INF if lo_p <= 0 else _frac(q_minus(xs, lo_p))
    hi: Any = POS_INF if hi_p >= 1 else _frac(q_plus(xs, hi_p))
    return lo, hi


def _decode_endpoint(value: Any) -> Fraction | None:
    if isinstance(value, dict) and value.get("kind") in {"NEG_INF", "POS_INF"}:
        return None
    return Fraction(value["num"], value["den"])


def mad_outer_interval(values: Iterable[Fraction], e: Fraction) -> tuple[Any, Any]:
    xs = list(values)
    mhat = midpoint_median(xs)
    lo, hi = median_outer_interval(xs, e)
    lo_f, hi_f = _decode_endpoint(lo), _decode_endpoint(hi)
    if lo_f is None or hi_f is None:
        return _frac(Fraction(0)), POS_INF
    r_m = max(abs(lo_f - mhat), abs(hi_f - mhat))
    dev = [abs(x - mhat) for x in xs]
    lo_p = Fraction(1, 2) - 2 * e
    hi_p = Fraction(1, 2) + 2 * e
    a_d = Fraction(0) if lo_p <= 0 else q_minus(dev, lo_p)
    if hi_p >= 1:
        return _frac(max(Fraction(0), a_d - r_m)), POS_INF
    b_d = q_plus(dev, hi_p)
    return _frac(max(Fraction(0), a_d - r_m)), _frac(b_d + r_m)
