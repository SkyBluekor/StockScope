from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.holdings.catalog import HoldingsCatalog
from app.quotes.models import QuoteSnapshot

from .coordinator import WatchDemand
from .models import WatchObservation, WatchRuleRuntimeState, WatchRuleSpec
from .policy import WatchPolicy, production_watch_policy
from .state_machine import advance_watch_rule
from .storage import require_watch_schema


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


class WatchService:
    """
    Durable lifecycle for VN-P4-S1 Watch.

    The service owns only Watch state. It never inserts Holdings BUY/SELL events
    and never applies or mutates a management plan.
    """

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        policy_provider: Callable[[], WatchPolicy] = production_watch_policy,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.catalog = catalog
        self.policy_provider = policy_provider
        self.clock = clock

    def _policy(self, policy: WatchPolicy | None = None) -> WatchPolicy:
        selected = policy or self.policy_provider()
        selected.require_enabled()
        return selected

    @staticmethod
    def _rule_rows_for_demand(
        demand: WatchDemand,
    ) -> list[tuple[str, str, Decimal]]:
        rows: list[tuple[str, str, Decimal]] = [
            ("STOP", "BELOW_OR_EQUAL", demand.stop_price),
        ]
        if demand.target1_price is not None:
            rows.append(
                ("TARGET1", "ABOVE_OR_EQUAL", demand.target1_price)
            )
        if demand.target2_price is not None:
            rows.append(
                ("TARGET2", "ABOVE_OR_EQUAL", demand.target2_price)
            )
        return rows

    @staticmethod
    def _disable_setting(
        conn: sqlite3.Connection,
        setting_id: str,
        *,
        reason: str,
        at: str,
    ) -> None:
        conn.execute(
            """
            UPDATE holding_watch_setting
            SET enabled=0,status='DISABLED',disabled_reason=?,updated_at=?
            WHERE id=? AND status='ACTIVE'
            """,
            (reason, at, setting_id),
        )
        conn.execute(
            """
            UPDATE holding_watch_rule
            SET state='DISABLED',status='CLOSED',closed_at=?,updated_at=?,
                confirmation_count=0,rearm_count=0
            WHERE setting_id=? AND status='ACTIVE'
            """,
            (at, at, setting_id),
        )
        conn.execute(
            """
            UPDATE holding_watch_episode
            SET status='INVALIDATED',resolved_at=?,
                resolution_reason=?,updated_at=?
            WHERE setting_id=? AND status='OPEN'
            """,
            (at, reason, at, setting_id),
        )
        conn.execute(
            """
            UPDATE holding_watch_coverage_gap
            SET status='CLOSED',ended_at=?,updated_at=?
            WHERE setting_id=? AND status='OPEN'
            """,
            (at, at, setting_id),
        )

    def _ensure_setting(
        self,
        conn: sqlite3.Connection,
        demand: WatchDemand,
        policy: WatchPolicy,
        *,
        at: str,
    ) -> sqlite3.Row:
        active = conn.execute(
            """
            SELECT * FROM holding_watch_setting
            WHERE position_id=? AND status='ACTIVE'
            LIMIT 1
            """,
            (demand.position_id,),
        ).fetchone()

        if active is not None:
            compatible = (
                str(active["plan_id"]) == demand.plan_id
                and int(active["plan_version"]) == demand.plan_version
                and str(active["policy_version"]) == policy.policy_version
                and str(active["policy_contract_version"]) == policy.contract_version
            )
            if compatible:
                return active
            self._disable_setting(
                conn,
                str(active["id"]),
                reason="PLAN_OR_POLICY_CHANGED",
                at=at,
            )

        setting_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO holding_watch_setting(
                id,position_id,plan_id,plan_version,enabled,
                policy_version,policy_contract_version,status,
                disabled_reason,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                setting_id,
                demand.position_id,
                demand.plan_id,
                demand.plan_version,
                1,
                policy.policy_version,
                policy.contract_version,
                "ACTIVE",
                None,
                at,
                at,
            ),
        )

        for rule_kind, direction, threshold in self._rule_rows_for_demand(demand):
            conn.execute(
                """
                INSERT INTO holding_watch_rule(
                    id,setting_id,position_id,plan_id,plan_version,
                    rule_kind,direction,threshold_price,policy_version,
                    confirmation_observations,rearm_observations,
                    rearm_distance_bps,max_quote_age_seconds,
                    state,confirmation_count,rearm_count,
                    last_observed_at,last_price,status,closed_at,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid4()),
                    setting_id,
                    demand.position_id,
                    demand.plan_id,
                    demand.plan_version,
                    rule_kind,
                    direction,
                    _decimal_text(threshold),
                    policy.policy_version,
                    int(policy.confirmation_observations or 0),
                    int(policy.rearm_observations or 0),
                    int(policy.rearm_distance_bps or 0),
                    float(policy.max_quote_age_seconds or 0),
                    "ARMED",
                    0,
                    0,
                    None,
                    None,
                    "ACTIVE",
                    None,
                    at,
                    at,
                ),
            )

        return conn.execute(
            "SELECT * FROM holding_watch_setting WHERE id=?",
            (setting_id,),
        ).fetchone()

    def reconcile(
        self,
        demands: Iterable[WatchDemand],
        policy: WatchPolicy | None = None,
    ) -> dict[str, int | bool | str | None]:
        selected = policy or self.policy_provider()
        if not selected.enabled:
            return {
                "enabled": False,
                "blocked_reason": selected.blocked_reason,
                "active_settings": 0,
                "created_or_kept": 0,
                "disabled": 0,
            }
        selected.require_enabled()
        demand_list = list(demands)
        by_position = {item.position_id: item for item in demand_list}
        now_text = _dt_text(self.clock())

        with self.catalog.connection() as conn:
            require_watch_schema(conn)
            before_active = {
                str(row["id"]): row
                for row in conn.execute(
                    """
                    SELECT * FROM holding_watch_setting
                    WHERE status='ACTIVE'
                    """
                ).fetchall()
            }

            for setting_id, row in before_active.items():
                demand = by_position.get(str(row["position_id"]))
                if demand is None:
                    self._disable_setting(
                        conn,
                        setting_id,
                        reason="POSITION_OR_PLAN_NOT_ACTIVE",
                        at=now_text,
                    )

            ensured = 0
            for demand in demand_list:
                self._ensure_setting(
                    conn,
                    demand,
                    selected,
                    at=now_text,
                )
                ensured += 1

            active_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM holding_watch_setting
                    WHERE status='ACTIVE'
                    """
                ).fetchone()[0]
            )
            disabled_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM holding_watch_setting
                    WHERE status='DISABLED'
                    """
                ).fetchone()[0]
            )

        return {
            "enabled": True,
            "blocked_reason": None,
            "active_settings": active_count,
            "created_or_kept": ensured,
            "disabled": disabled_count,
        }

    @staticmethod
    def _runtime_from_row(row: sqlite3.Row) -> WatchRuleRuntimeState:
        return WatchRuleRuntimeState(
            state=str(row["state"]),  # type: ignore[arg-type]
            confirmation_count=int(row["confirmation_count"]),
            rearm_count=int(row["rearm_count"]),
            last_observed_at=_parse_dt(row["last_observed_at"]),
            last_price=(
                Decimal(str(row["last_price"]))
                if row["last_price"] is not None
                else None
            ),
        )

    @staticmethod
    def _spec_from_row(row: sqlite3.Row) -> WatchRuleSpec:
        return WatchRuleSpec(
            rule_kind=str(row["rule_kind"]),  # type: ignore[arg-type]
            direction=str(row["direction"]),  # type: ignore[arg-type]
            threshold_price=Decimal(str(row["threshold_price"])),
        )

    @staticmethod
    def _persist_runtime(
        conn: sqlite3.Connection,
        rule_id: str,
        runtime: WatchRuleRuntimeState,
        *,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            UPDATE holding_watch_rule
            SET state=?,confirmation_count=?,rearm_count=?,
                last_observed_at=?,last_price=?,updated_at=?
            WHERE id=? AND status='ACTIVE'
            """,
            (
                runtime.state,
                runtime.confirmation_count,
                runtime.rearm_count,
                (
                    _dt_text(runtime.last_observed_at)
                    if runtime.last_observed_at is not None
                    else None
                ),
                _decimal_text(runtime.last_price),
                updated_at,
                rule_id,
            ),
        )

    @staticmethod
    def _open_episode(
        conn: sqlite3.Connection,
        *,
        rule: sqlite3.Row,
        observed_at: str,
        trigger_price: Decimal,
        updated_at: str,
    ) -> sqlite3.Row:
        current = conn.execute(
            """
            SELECT * FROM holding_watch_episode
            WHERE rule_id=? AND status='OPEN'
            LIMIT 1
            """,
            (str(rule["id"]),),
        ).fetchone()
        if current is not None:
            return current

        episode_no = int(
            conn.execute(
                """
                SELECT COALESCE(MAX(episode_no),0)+1
                FROM holding_watch_episode
                WHERE rule_id=?
                """,
                (str(rule["id"]),),
            ).fetchone()[0]
        )
        episode_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO holding_watch_episode(
                id,rule_id,setting_id,position_id,plan_id,plan_version,
                episode_no,status,opened_at,confirmed_at,resolved_at,
                resolution_reason,trigger_price,confirmed_price,
                created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                episode_id,
                str(rule["id"]),
                str(rule["setting_id"]),
                str(rule["position_id"]),
                str(rule["plan_id"]),
                int(rule["plan_version"]),
                episode_no,
                "OPEN",
                observed_at,
                None,
                None,
                None,
                _decimal_text(trigger_price),
                None,
                updated_at,
                updated_at,
            ),
        )
        return conn.execute(
            "SELECT * FROM holding_watch_episode WHERE id=?",
            (episode_id,),
        ).fetchone()

    @staticmethod
    def _notification_id(episode_id: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"stockscope:watch:{episode_id}:WATCH_RULE_CONFIRMED",
            )
        )

    def _confirm_episode(
        self,
        conn: sqlite3.Connection,
        *,
        rule: sqlite3.Row,
        episode: sqlite3.Row,
        confirmed_at: str,
        confirmed_price: Decimal,
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            UPDATE holding_watch_episode
            SET confirmed_at=COALESCE(confirmed_at,?),
                confirmed_price=COALESCE(confirmed_price,?),
                updated_at=?
            WHERE id=? AND status='OPEN'
            """,
            (
                confirmed_at,
                _decimal_text(confirmed_price),
                updated_at,
                str(episode["id"]),
            ),
        )

        notification_id = self._notification_id(str(episode["id"]))
        payload = {
            "position_id": str(rule["position_id"]),
            "plan_id": str(rule["plan_id"]),
            "plan_version": int(rule["plan_version"]),
            "rule_id": str(rule["id"]),
            "rule_kind": str(rule["rule_kind"]),
            "threshold_price": str(rule["threshold_price"]),
            "confirmed_price": _decimal_text(confirmed_price),
            "confirmed_at": confirmed_at,
            "policy_version": str(rule["policy_version"]),
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO holding_watch_notification_outbox(
                id,episode_id,rule_id,setting_id,position_id,plan_id,
                notification_type,delivery_status,payload_json,
                created_at,delivered_at,read_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                notification_id,
                str(episode["id"]),
                str(rule["id"]),
                str(rule["setting_id"]),
                str(rule["position_id"]),
                str(rule["plan_id"]),
                "WATCH_RULE_CONFIRMED",
                "PENDING",
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                updated_at,
                None,
                None,
            ),
        )

    @staticmethod
    def _finish_open_episode(
        conn: sqlite3.Connection,
        *,
        rule_id: str,
        status: str,
        reason: str,
        at: str,
        only_unconfirmed: bool = False,
    ) -> None:
        extra = " AND confirmed_at IS NULL" if only_unconfirmed else ""
        conn.execute(
            f"""
            UPDATE holding_watch_episode
            SET status=?,resolved_at=?,resolution_reason=?,updated_at=?
            WHERE rule_id=? AND status='OPEN'{extra}
            """,
            (status, at, reason, at, rule_id),
        )

    @staticmethod
    def _record_gap_tx(
        conn: sqlite3.Connection,
        *,
        setting_id: str,
        position_id: str,
        reason: str,
        at: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        existing = conn.execute(
            """
            SELECT id FROM holding_watch_coverage_gap
            WHERE setting_id=? AND reason_code=? AND status='OPEN'
            LIMIT 1
            """,
            (setting_id, reason),
        ).fetchone()
        if existing is not None:
            conn.execute(
                """
                UPDATE holding_watch_coverage_gap
                SET updated_at=?
                WHERE id=?
                """,
                (at, str(existing["id"])),
            )
            return

        conn.execute(
            """
            INSERT INTO holding_watch_coverage_gap(
                id,setting_id,position_id,reason_code,status,
                started_at,ended_at,detail_json,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid4()),
                setting_id,
                position_id,
                reason,
                "OPEN",
                at,
                None,
                json.dumps(
                    detail or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                at,
                at,
            ),
        )

    @staticmethod
    def _reset_unfinished_confirmation(
        conn: sqlite3.Connection,
        *,
        setting_id: str,
        reason: str,
        at: str,
    ) -> None:
        pending = conn.execute(
            """
            SELECT id FROM holding_watch_rule
            WHERE setting_id=? AND status='ACTIVE'
              AND state='PENDING_CONFIRMATION'
            """,
            (setting_id,),
        ).fetchall()
        for row in pending:
            rule_id = str(row["id"])
            conn.execute(
                """
                UPDATE holding_watch_rule
                SET state='ARMED',confirmation_count=0,rearm_count=0,
                    updated_at=?
                WHERE id=?
                """,
                (at, rule_id),
            )
            WatchService._finish_open_episode(
                conn,
                rule_id=rule_id,
                status="INVALIDATED",
                reason=f"COVERAGE_GAP:{reason}",
                at=at,
                only_unconfirmed=True,
            )

    def record_coverage_issue(
        self,
        demand: WatchDemand,
        reason: str,
        *,
        detail: dict[str, object] | None = None,
        policy: WatchPolicy | None = None,
    ) -> dict[str, object]:
        selected = self._policy(policy)
        now_text = _dt_text(self.clock())
        with self.catalog.connection() as conn:
            require_watch_schema(conn)
            setting = self._ensure_setting(
                conn,
                demand,
                selected,
                at=now_text,
            )
            setting_id = str(setting["id"])
            self._record_gap_tx(
                conn,
                setting_id=setting_id,
                position_id=demand.position_id,
                reason=reason,
                at=now_text,
                detail=detail,
            )
            self._reset_unfinished_confirmation(
                conn,
                setting_id=setting_id,
                reason=reason,
                at=now_text,
            )
        return {
            "position_id": demand.position_id,
            "setting_id": setting_id,
            "reason": reason,
        }

    def process_quote(
        self,
        demand: WatchDemand,
        snapshot: QuoteSnapshot,
        policy: WatchPolicy | None = None,
    ) -> dict[str, object]:
        selected = self._policy(policy)
        now = self.clock()
        now_text = _dt_text(now)
        age_seconds = max(
            0.0,
            (now.astimezone(timezone.utc) - snapshot.received_at.astimezone(timezone.utc))
            .total_seconds(),
        )

        if age_seconds > float(selected.max_quote_age_seconds or 0):
            return {
                "coverage": self.record_coverage_issue(
                    demand,
                    "STALE_QUOTE",
                    detail={"age_seconds": age_seconds},
                    policy=selected,
                ),
                "transitions": [],
            }

        observed_at = _dt_text(snapshot.received_at)
        transitions: list[dict[str, object]] = []

        with self.catalog.connection() as conn:
            require_watch_schema(conn)
            setting = self._ensure_setting(
                conn,
                demand,
                selected,
                at=now_text,
            )
            setting_id = str(setting["id"])

            conn.execute(
                """
                UPDATE holding_watch_coverage_gap
                SET status='CLOSED',ended_at=?,updated_at=?
                WHERE setting_id=? AND status='OPEN'
                """,
                (observed_at, now_text, setting_id),
            )

            rules = conn.execute(
                """
                SELECT * FROM holding_watch_rule
                WHERE setting_id=? AND status='ACTIVE'
                ORDER BY CASE rule_kind
                    WHEN 'STOP' THEN 1
                    WHEN 'TARGET1' THEN 2
                    ELSE 3 END
                """,
                (setting_id,),
            ).fetchall()

            for rule in rules:
                runtime = self._runtime_from_row(rule)
                transition = advance_watch_rule(
                    self._spec_from_row(rule),
                    runtime,
                    WatchObservation(
                        price=snapshot.current_price,
                        observed_at=snapshot.received_at,
                        age_seconds=age_seconds,
                    ),
                    selected,
                )
                if not transition.accepted:
                    continue

                self._persist_runtime(
                    conn,
                    str(rule["id"]),
                    transition.current,
                    updated_at=now_text,
                )

                if transition.event == "CONDITION_ENTERED":
                    self._open_episode(
                        conn,
                        rule=rule,
                        observed_at=observed_at,
                        trigger_price=snapshot.current_price,
                        updated_at=now_text,
                    )

                elif transition.event == "CONFIRMED":
                    episode = self._open_episode(
                        conn,
                        rule=rule,
                        observed_at=observed_at,
                        trigger_price=snapshot.current_price,
                        updated_at=now_text,
                    )
                    self._confirm_episode(
                        conn,
                        rule=rule,
                        episode=episode,
                        confirmed_at=observed_at,
                        confirmed_price=snapshot.current_price,
                        updated_at=now_text,
                    )

                elif transition.event == "CONFIRMATION_RESET":
                    self._finish_open_episode(
                        conn,
                        rule_id=str(rule["id"]),
                        status="INVALIDATED",
                        reason="CONFIRMATION_RESET",
                        at=observed_at,
                        only_unconfirmed=True,
                    )

                elif transition.event == "RESOLVED":
                    self._finish_open_episode(
                        conn,
                        rule_id=str(rule["id"]),
                        status="RESOLVED",
                        reason="CONDITION_CLEARED",
                        at=observed_at,
                    )

                transitions.append(
                    {
                        "rule_id": str(rule["id"]),
                        "rule_kind": str(rule["rule_kind"]),
                        "event": transition.event,
                        "state": transition.current.state,
                    }
                )

        return {
            "position_id": demand.position_id,
            "plan_id": demand.plan_id,
            "plan_version": demand.plan_version,
            "setting_id": setting_id,
            "transitions": transitions,
            "coverage": None,
        }
