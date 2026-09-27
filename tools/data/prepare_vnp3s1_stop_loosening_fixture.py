from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from tools.data.backup_runtime import create_backup
from tools.data.common import (
    DEFAULT_BACKUP_ROOT,
    DataToolError,
    holdings_db_path,
    iso_now,
    utc_stamp,
    validate_holdings_db,
)


UAT_MARKER = "VN-P3-S1-UAT.4-STOP-LOOSENING"


def _decimal(value: object, *, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DataToolError(f"{label} 값을 숫자로 해석할 수 없습니다: {value!r}") from exc
    if not parsed.is_finite():
        raise DataToolError(f"{label} 값이 유효하지 않습니다: {value!r}")
    return parsed


def _json_object(raw: object) -> dict[str, object]:
    if raw in (None, ""):
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {"original_raw": str(raw)}
    if isinstance(parsed, dict):
        return dict(parsed)
    return {"original_value": parsed}


def _suggest_stop(active_stop: Decimal) -> Decimal:
    if active_stop <= 0:
        raise DataToolError("현재 Active Plan의 손절 가격이 0 이하라 fixture를 만들 수 없습니다.")
    one_percent = (active_stop * Decimal("0.01")).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    delta = max(Decimal("1"), one_percent)
    candidate = active_stop - delta
    if candidate <= 0:
        candidate = active_stop / Decimal("2")
    if candidate <= 0 or candidate >= active_stop:
        raise DataToolError("현재 손절 가격보다 낮은 안전한 UAT 손절 가격을 계산하지 못했습니다.")
    return candidate


def _resolve_target(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    market: str | None,
    position_id: str | None,
) -> dict[str, sqlite3.Row]:
    stock_sql = "SELECT * FROM monitored_stock WHERE ticker=?"
    stock_params: list[object] = [ticker]
    if market:
        stock_sql += " AND market=?"
        stock_params.append(market)
    stocks = conn.execute(stock_sql, stock_params).fetchall()
    if not stocks:
        raise DataToolError("해당 ticker의 등록 종목을 찾지 못했습니다.")
    if len(stocks) != 1:
        raise DataToolError("동일 ticker 등록 종목이 여러 개입니다. --market을 지정하세요.")
    stock = stocks[0]

    position_sql = """
        SELECT p.*,mp.id AS active_plan_id,mp.plan_version AS active_plan_version,
               mp.source_analysis_revision_id AS active_source_revision_id,
               mp.reference_price AS active_reference_price,
               mp.stop_price AS active_stop_price,
               mp.target1_price AS active_target1_price,
               mp.target2_price AS active_target2_price
        FROM holding_position p
        JOIN holding_management_plan mp
          ON mp.position_id=p.id AND mp.status='ACTIVE'
        WHERE p.monitored_stock_id=? AND p.status='OPEN'
    """
    params: list[object] = [stock["id"]]
    if position_id:
        position_sql += " AND p.id=?"
        params.append(position_id)
    positions = conn.execute(position_sql, params).fetchall()
    if not positions:
        raise DataToolError("OPEN Position + ACTIVE Plan 조합을 찾지 못했습니다.")
    if len(positions) != 1:
        raise DataToolError("대상 Position이 여러 개입니다. --position-id를 지정하세요.")
    position = positions[0]

    latest = conn.execute(
        """
        SELECT d.id AS analysis_day_id,d.market_date,d.current_revision_id,r.*
        FROM stock_analysis_day d
        JOIN stock_analysis_revision r ON r.id=d.current_revision_id
        WHERE d.monitored_stock_id=?
        ORDER BY d.market_date DESC
        LIMIT 1
        """,
        (stock["id"],),
    ).fetchone()
    if latest is None:
        raise DataToolError("현재 Analysis Revision을 찾지 못했습니다.")

    if str(latest["id"]) != str(position["active_source_revision_id"]):
        raise DataToolError(
            "현재 최신 Analysis가 Active Plan의 source revision과 다릅니다. "
            "기존 미적용 분석을 보존하기 위해 fixture 생성을 중단합니다."
        )

    return {"stock": stock, "position": position, "latest": latest}


def inspect_target(
    *,
    holdings_db: Path,
    ticker: str,
    market: str | None = None,
    position_id: str | None = None,
    stop_price: Decimal | None = None,
) -> dict[str, object]:
    validate_holdings_db(holdings_db)
    uri = holdings_db.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        target = _resolve_target(
            conn,
            ticker=ticker,
            market=market,
            position_id=position_id,
        )
        position = target["position"]
        latest = target["latest"]
        active_stop = _decimal(position["active_stop_price"], label="Active Plan stop")
        fixture_stop = stop_price if stop_price is not None else _suggest_stop(active_stop)
        if fixture_stop <= 0 or fixture_stop >= active_stop:
            raise DataToolError(
                f"fixture stop은 0보다 크고 Active Plan stop({active_stop})보다 낮아야 합니다."
            )
        return {
            "stock_id": str(target["stock"]["id"]),
            "market": str(target["stock"]["market"]),
            "ticker": str(target["stock"]["ticker"]),
            "name": str(target["stock"]["name"]),
            "position_id": str(position["id"]),
            "position_quantity": str(position["current_quantity"]),
            "position_average_price": str(position["current_average_price"]),
            "active_plan_id": str(position["active_plan_id"]),
            "active_plan_version": int(position["active_plan_version"]),
            "active_plan_stop": str(active_stop),
            "source_revision_id": str(latest["id"]),
            "analysis_day_id": str(latest["analysis_day_id"]),
            "market_date": str(latest["market_date"]),
            "fixture_stop": str(fixture_stop),
        }


def prepare_stop_loosening_fixture(
    *,
    holdings_db: Path,
    ticker: str,
    market: str | None = None,
    position_id: str | None = None,
    stop_price: Decimal | None = None,
    backup_root: Path | None = None,
) -> dict[str, object]:
    preview = inspect_target(
        holdings_db=holdings_db,
        ticker=ticker,
        market=market,
        position_id=position_id,
        stop_price=stop_price,
    )
    fixture_stop = _decimal(preview["fixture_stop"], label="fixture stop")

    destination = Path(backup_root or DEFAULT_BACKUP_ROOT) / (
        f"StockScope_{UAT_MARKER}_{utc_stamp()}"
    )
    backup_dir = create_backup(
        destination=destination,
        holdings_db=holdings_db,
        include_market=False,
        include_simulation=False,
        include_tracking=False,
    )

    conn = sqlite3.connect(holdings_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        target = _resolve_target(
            conn,
            ticker=ticker,
            market=market,
            position_id=position_id,
        )
        position = target["position"]
        latest = target["latest"]
        active_stop = _decimal(position["active_stop_price"], label="Active Plan stop")
        if (
            str(position["id"]) != str(preview["position_id"])
            or str(position["active_plan_id"]) != str(preview["active_plan_id"])
            or int(position["active_plan_version"]) != int(preview["active_plan_version"])
            or str(position["current_quantity"]) != str(preview["position_quantity"])
            or str(position["current_average_price"]) != str(preview["position_average_price"])
            or str(latest["id"]) != str(preview["source_revision_id"])
            or str(active_stop) != str(preview["active_plan_stop"])
        ):
            raise DataToolError(
                "백업 이후 Position/Plan/Analysis 상태가 바뀌었습니다. "
                "동시 변경을 덮어쓰지 않기 위해 fixture 생성을 중단합니다."
            )
        if fixture_stop <= 0 or fixture_stop >= active_stop:
            raise DataToolError(
                "백업 이후 대상 상태가 바뀌어 fixture stop이 더 이상 유효하지 않습니다."
            )

        next_revision_no = int(
            conn.execute(
                """
                SELECT COALESCE(MAX(revision_no),0)+1
                FROM stock_analysis_revision
                WHERE analysis_day_id=?
                """,
                (latest["analysis_day_id"],),
            ).fetchone()[0]
        )
        revision_id = str(uuid4())
        fingerprint_seed = (
            f'{latest["input_fingerprint"]}|{UAT_MARKER}|{fixture_stop}|{revision_id}'
        )
        input_fingerprint = hashlib.sha256(
            fingerprint_seed.encode("utf-8")
        ).hexdigest()

        source_versions = _json_object(latest["source_versions_json"])
        source_versions["uat_fixture"] = {
            "marker": UAT_MARKER,
            "source_revision_id": str(latest["id"]),
        }
        snapshot = _json_object(latest["snapshot_json"])
        risk = snapshot.get("risk")
        if not isinstance(risk, dict):
            risk = {}
        else:
            risk = dict(risk)
        risk["invalidation_price"] = float(fixture_stop)
        snapshot["risk"] = risk
        snapshot["uat_fixture"] = {
            "marker": UAT_MARKER,
            "source_revision_id": str(latest["id"]),
            "active_plan_id": str(position["active_plan_id"]),
            "active_stop": str(active_stop),
            "fixture_stop": str(fixture_stop),
        }

        now = iso_now()
        conn.execute(
            """
            INSERT INTO stock_analysis_revision(
                id,analysis_day_id,revision_no,input_fingerprint,
                strategy_key,action_state,risk_state,
                reference_price,stop_price,target1_price,target2_price,
                scanner_version,analysis_engine_version,policy_version,
                source_versions_json,snapshot_json,revision_reason,
                computed_at,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                revision_id,
                latest["analysis_day_id"],
                next_revision_no,
                input_fingerprint,
                latest["strategy_key"],
                latest["action_state"],
                latest["risk_state"],
                latest["reference_price"],
                str(fixture_stop),
                latest["target1_price"],
                latest["target2_price"],
                latest["scanner_version"],
                latest["analysis_engine_version"],
                latest["policy_version"],
                json.dumps(source_versions, ensure_ascii=False, sort_keys=True),
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                f"{UAT_MARKER}: lower stop fixture",
                now,
                now,
            ),
        )

        horizon_table = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='analysis_horizon_context'
            """
        ).fetchone()
        if horizon_table is not None:
            source_horizon = conn.execute(
                """
                SELECT intent,policy_version,support_status
                FROM analysis_horizon_context
                WHERE revision_id=?
                LIMIT 1
                """,
                (latest["id"],),
            ).fetchone()
            if source_horizon is not None:
                conn.execute(
                    """
                    INSERT INTO analysis_horizon_context(
                        revision_id,intent,policy_version,support_status,created_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        revision_id,
                        source_horizon["intent"],
                        source_horizon["policy_version"],
                        source_horizon["support_status"],
                        now,
                    ),
                )

        cursor = conn.execute(
            """
            UPDATE stock_analysis_day
            SET current_revision_id=?,updated_at=?
            WHERE id=? AND current_revision_id=?
            """,
            (
                revision_id,
                now,
                latest["analysis_day_id"],
                latest["id"],
            ),
        )
        if cursor.rowcount != 1:
            raise DataToolError(
                "Analysis current revision이 동시에 변경되어 fixture 적용을 중단했습니다."
            )

        active_after = conn.execute(
            """
            SELECT id,plan_version,status,stop_price
            FROM holding_management_plan
            WHERE position_id=? AND status='ACTIVE'
            LIMIT 1
            """,
            (position["id"],),
        ).fetchone()
        stored_position = conn.execute(
            "SELECT current_quantity,current_average_price FROM holding_position WHERE id=?",
            (position["id"],),
        ).fetchone()
        if active_after is None or str(active_after["id"]) != str(position["active_plan_id"]):
            raise DataToolError("fixture 생성 중 Active Plan이 변경되었습니다.")
        if (
            str(stored_position["current_quantity"]) != str(position["current_quantity"])
            or str(stored_position["current_average_price"]) != str(position["current_average_price"])
        ):
            raise DataToolError("fixture 생성 중 Position 원장이 변경되었습니다.")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        **preview,
        "fixture_revision_id": revision_id,
        "fixture_revision_no": next_revision_no,
        "backup_dir": str(backup_dir),
        "restore_command": (
            f'.\\.venv\\Scripts\\python.exe .\\tools\\data\\restore_runtime.py '
            f'"{backup_dir}"'
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VN-P3-S1-UAT.4 전용: 현재 Active Plan보다 낮은 stop을 가진 "
            "새 Analysis Revision을 append하여 stop-loosening 보호를 검증합니다."
        )
    )
    parser.add_argument("--ticker", required=True, help="대상 종목 ticker")
    parser.add_argument("--market", help="KOSPI/KOSDAQ. 동일 ticker가 여러 개면 필수")
    parser.add_argument("--position-id", help="대상 OPEN Position ID. 여러 Position이면 필수")
    parser.add_argument(
        "--stop-price",
        type=Decimal,
        help="fixture stop. 생략하면 Active Plan stop보다 약 1% 낮게 계산합니다.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="백업 후 실제 UAT Analysis Revision을 생성합니다. 생략하면 preview만 출력합니다.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = holdings_db_path()
    try:
        preview = inspect_target(
            holdings_db=db_path,
            ticker=args.ticker.strip().upper(),
            market=args.market.strip().upper() if args.market else None,
            position_id=args.position_id,
            stop_price=args.stop_price,
        )
        print("=" * 78)
        print("VN-P3-S1-UAT.4 STOP-LOOSENING FIXTURE")
        print("=" * 78)
        print("Mode            ", "APPLY" if args.apply else "PREVIEW")
        print("Stock           ", f'{preview["name"]} {preview["ticker"]} · {preview["market"]}')
        print("Position        ", preview["position_id"])
        print("Quantity        ", preview["position_quantity"])
        print("Average price   ", preview["position_average_price"])
        print("Active Plan     ", f'v{preview["active_plan_version"]} · {preview["active_plan_id"]}')
        print("Active stop     ", preview["active_plan_stop"])
        print("Source revision ", preview["source_revision_id"])
        print("Fixture stop    ", preview["fixture_stop"])
        print("")
        if not args.apply:
            print("NO CHANGES MADE")
            print("확인 후 같은 명령에 --apply를 추가하세요.")
            return 0

        result = prepare_stop_loosening_fixture(
            holdings_db=db_path,
            ticker=args.ticker.strip().upper(),
            market=args.market.strip().upper() if args.market else None,
            position_id=args.position_id,
            stop_price=args.stop_price,
        )
        print("Backup          ", result["backup_dir"])
        print("Fixture revision", result["fixture_revision_id"])
        print("Revision no     ", result["fixture_revision_no"])
        print("Active Plan     ", "UNCHANGED")
        print("Position        ", "UNCHANGED")
        print("BUY/SELL        ", "UNCHANGED")
        print("")
        print("Browser next    최신 판단 다시 만들기 → CONFLICT 확인")
        print("Restore command ")
        print(result["restore_command"])
        return 0
    except DataToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
