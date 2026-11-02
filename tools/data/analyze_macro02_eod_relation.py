"""MACRO-02: one-shot, local-only retrospective DGS10/KRX comparison.

This script reads existing databases with SQLite mode=ro. It never fetches,
modifies Scanner/Strategy/Risk state or writes research artifacts. An observation
date precedes a KRX trading date only for DESCRIPTION; it does not prove the
information was available before Korean market close (PIT).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from bisect import bisect_left
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.macro import LocalMacroReader
from app.macro.impact import LocalMarketImpactReader
from tools.data.common import macro_db_path, market_db_path

SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
MARKETS = ("KOSPI", "KOSDAQ")
MAX_LAG_DAYS = 7  # Only a matching-window limit, never a trading-risk threshold.


def numeric(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def parsed_day(value: Any) -> date | None:
    value = str(value or "").replace("-", "")
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
    except ValueError:
        return None


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"기존 DB가 없습니다: {path}")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def market_days(db_path: Path, *, end: date, limit: int) -> list[dict[str, Any]]:
    """Require BOTH stock and index 'data' markers and genuine KRX index rows."""
    with closing(_connect_ro(db_path)) as conn:
        keys = [
            str(row["bas_dd"])
            for row in conn.execute(
                """
                SELECT bas_dd FROM day_status
                WHERE market IN ('KOSPI','KOSDAQ')
                  AND kind IN ('stock','index') AND status='data'
                  AND bas_dd<=?
                GROUP BY bas_dd
                HAVING COUNT(DISTINCT market || ':' || kind)=4
                ORDER BY bas_dd DESC
                LIMIT ?
                """,
                (end.strftime("%Y%m%d"), limit),
            )
        ]
        output = []
        for key in reversed(keys):
            result = {"day": key}
            for market in MARKETS:
                row = conn.execute(
                    "SELECT row_json FROM main_index_daily WHERE market=? AND bas_dd=?",
                    (market, key),
                ).fetchone()
                if not row:
                    break
                try:
                    raw = json.loads(row["row_json"])
                except (ValueError, TypeError):
                    break
                if not isinstance(raw, dict) or parsed_day(raw.get("date")) != parsed_day(key):
                    break
                rate = numeric(raw.get("change_rate"))
                close = numeric(raw.get("close"))
                if rate is None or close is None or close <= 0:
                    break
                result[market] = rate
            else:
                output.append(result)
        return output


def _macro_obs(rows: list[dict[str, Any]], *, cutoff: datetime) -> list[dict[str, Any]]:
    """One latest, published/readable revision per observation DATE."""
    chosen: dict[date, dict[str, Any]] = {}
    for raw in rows:
        day = parsed_day(raw.get("observation_date"))
        value = numeric(raw.get("normalized_value"))
        if day is None or value is None or str(raw.get("source_unit")) != "PERCENT":
            continue
        try:
            available = datetime.fromisoformat(str(raw["available_at"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if available.tzinfo is None or available > cutoff:
            continue
        item = {"day": day, "value": value, "available": available,
                "quality": raw.get("time_quality"),
                "published_at": raw.get("source_published_at")}
        older = chosen.get(day)
        if older is None or available > older["available"]:
            chosen[day] = item
    return [chosen[day] for day in sorted(chosen)]


def pair_retro(
    domestic: list[dict[str, Any]],
    macro: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pair prior US observation DATE with next KRX day (retrospective only)."""
    macro_days = [row["day"] for row in macro]
    reasons = {"NO_PRIOR_US_OBSERVATION": 0, "US_OBSERVATION_TOO_OLD": 0,
               "US_BASELINE_MISSING_OR_TOO_OLD": 0, "US_DAY_REUSED": 0}
    used: set[date] = set()
    paired: list[dict[str, Any]] = []
    for day_row in domestic:
        local_day = parsed_day(day_row["day"])
        if local_day is None:
            continue
        index = bisect_left(macro_days, local_day) - 1
        if index < 0:
            reasons["NO_PRIOR_US_OBSERVATION"] += 1
            continue
        current = macro[index]
        if (local_day - current["day"]).days > MAX_LAG_DAYS:
            reasons["US_OBSERVATION_TOO_OLD"] += 1
            continue
        if index == 0 or (current["day"] - macro[index - 1]["day"]).days > MAX_LAG_DAYS:
            reasons["US_BASELINE_MISSING_OR_TOO_OLD"] += 1
            continue
        if current["day"] in used:
            reasons["US_DAY_REUSED"] += 1
            continue
        used.add(current["day"])
        previous = macro[index - 1]
        delta_bp = (current["value"] - previous["value"]) * Decimal("100")
        local_close = datetime.combine(
            local_day, time(15, 30), tzinfo=timezone(timedelta(hours=9))
        )
        historically_verified = all(
            v["quality"] in {"EXACT", "PROVIDER_TIME"}
            and v["published_at"]
            and v["available"] <= local_close
            for v in (previous, current)
        )
        paired.append({
            "krx_date": local_day.isoformat(),
            "us_observation_date": current["day"].isoformat(),
            "lag_calendar_days": (local_day - current["day"]).days,
            "dgs10_change_bp": delta_bp,
            "KOSPI": day_row["KOSPI"],
            "KOSDAQ": day_row["KOSDAQ"],
            "pit_verified": bool(historically_verified),
            "time_quality": current["quality"],
        })
    groups: dict[str, dict[str, Any]] = {}
    for key, group in (
        ("rate_up", [x for x in paired if x["dgs10_change_bp"] > 0]),
        ("rate_down", [x for x in paired if x["dgs10_change_bp"] < 0]),
        ("rate_unchanged", [x for x in paired if x["dgs10_change_bp"] == 0]),
    ):
        groups[key] = {
            "count": len(group),
            "kospi_mean_pct": round(float(sum((x["KOSPI"] for x in group), Decimal(0)) / len(group)), 3) if group else None,
            "kosdaq_mean_pct": round(float(sum((x["KOSDAQ"] for x in group), Decimal(0)) / len(group)), 3) if group else None,
        }
    last = paired[-1] if paired else None
    return {
        "mode": "RETROSPECTIVE_DESCRIPTIVE_ONLY",
        "relation_status": "RELATION_UNVERIFIED",
        "policy_input_approved": False,
        "local_market_sessions": len(domestic),
        "us_observations_loaded": len(macro),
        "paired_sessions": len(paired),
        "pit_verified_pairs": sum(int(x["pit_verified"]) for x in paired),
        "alignment": "MOST_RECENT_US_OBSERVATION_DATE_STRICTLY_BEFORE_KRX_DATE",
        "alignment_is_not_publication_time_evidence": True,
        "excluded": reasons,
        "groups": groups,
        "last_pair": ({
            **{k: v for k, v in last.items() if k != "pit_verified" and k != "time_quality"},
            "dgs10_change_bp": float(last["dgs10_change_bp"]),
            "KOSPI": float(last["KOSPI"]),
            "KOSDAQ": float(last["KOSDAQ"]),
            "pit_verified": last["pit_verified"],
            "time_quality": last["time_quality"],
        } if last else None),
    }


def stock_relative_example(
    db_path: Path, *, market: str, ticker: str, end: date
) -> dict[str, Any]:
    """Use the existing strictly read-only impact reader for a selected stock."""
    result = LocalMarketImpactReader(db_path).read_pair_as_of(
        market=market, ticker=ticker, end_date=end.isoformat()
    )
    stock = {
        parsed_day(row.get("date") or row.get("bas_dd")): numeric(row.get("close"))
        for row in result.get("stock_rows") or []
    }
    market_closes = {
        parsed_day(row.get("date") or row.get("bas_dd")): numeric(row.get("close"))
        for row in result.get("market_rows") or []
    }
    common = sorted(day for day in set(stock) & set(market_closes)
                    if day is not None and stock[day] is not None
                    and market_closes[day] is not None
                    and stock[day] > 0 and market_closes[day] > 0)
    if len(common) < 2 or common[-1] != end:
        return {"status": "UNAVAILABLE", "reason": "STOCK_AND_MARKET_COMMON_END_REQUIRED"}
    previous, last = common[-2:]
    stock_return = (stock[last] / stock[previous] - 1) * Decimal(100)
    market_return = (market_closes[last] / market_closes[previous] - 1) * Decimal(100)
    return {
        "status": "AVAILABLE", "market": market, "ticker": ticker,
        "start_date": previous.isoformat(), "end_date": last.isoformat(),
        "stock_return_pct": round(float(stock_return), 3),
        "market_return_pct": round(float(market_return), 3),
        "stock_vs_market_pctp": round(float(stock_return - market_return), 3),
        "interpretation": "DESCRIPTIVE_ONLY_NO_CAUSAL_OR_TRADING_INPUT",
    }


def analyze(*, macro_db: Path, market_db: Path, end: date, limit: int,
            market: str, ticker: str, cutoff: datetime) -> dict[str, Any]:
    if not 1 <= limit <= 260:
        raise ValueError("limit must be between 1 and 260.")
    domestic = market_days(market_db, end=end, limit=limit)
    reader = LocalMacroReader(macro_db)
    window = reader.read_series_window(
        SERIES, cutoff=cutoff.isoformat(), observation_limit=1000,
        historical_eligible_only=False,
    )
    observations = _macro_obs(window.get("observations") or [], cutoff=cutoff)
    comparison = pair_retro(domestic, observations)
    if window.get("status") != "COMPLETE" or not domestic:
        comparison["relation_status"] = "DATA_UNAVAILABLE"
    return {
        "task": "MACRO-02",
        "data_paths": {"macro_db": str(macro_db), "market_db": str(market_db)},
        "snapshot_cutoff_utc": cutoff.isoformat(),
        "research_end_date": end.isoformat(),
        "macro_reader_status": window.get("status"),
        "macro_reader_reason": window.get("reason"),
        "comparison": comparison,
        "selected_stock_example": stock_relative_example(
            market_db, market=market, ticker=ticker, end=end,
        ),
        "limitations": [
            "DATE_ONLY_DGS10_IMPORTED_AFTER_HISTORICAL_TRADING_DAY_NOT_PIT",
            "DATE_ORDER_IS_NOT_PROOF_OF_KOREAN_OPEN_OR_CLOSE_AVAILABILITY",
            "DESCRIPTIVE_GROUP_MEANS_ARE_NOT_CAUSATION_OR_PREDICTION",
            "NO_STRATEGY_RISK_SCANNER_HOLDINGS_OR_JEV_CHANGES",
            "NO_NETWORK_NO_DB_WRITE",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MACRO-02 historical comparison.")
    parser.add_argument("--end", default="2026-10-30")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--market", choices=MARKETS, default="KOSDAQ")
    parser.add_argument("--ticker", default="171090")
    args = parser.parse_args()
    try:
        end = date.fromisoformat(args.end)
        report = analyze(
            macro_db=macro_db_path(), market_db=market_db_path(),
            end=end, limit=args.days, market=args.market, ticker=args.ticker,
            cutoff=datetime.now(timezone.utc),
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print("MACRO-02 read-only analysis unavailable:", exc, file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
