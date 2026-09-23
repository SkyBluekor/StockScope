from __future__ import annotations

from decimal import Decimal
from typing import Any

from .catalog import HoldingsCatalog


ENTRY_LABELS = {
    "READY": "진입 후보",
    "WATCH": "관심 유지",
    "NOT_READY": "현재 우선순위 낮음",
    "BLOCKED": "위험 때문에 보류",
    "CAUTION": "주의하며 관찰",
    "NO_TRADE": "신규 진입 제외",
    "UNKNOWN": "판단 정보 없음",
}

PLAN_LABELS = {
    "FIRST_PLAN": "첫 계획 설정됨",
    "PREVIOUS_PLAN_UNAVAILABLE": "이전 가격 계획 정보 없음",
    "WITHIN_PLAN": "이전 계획 범위 내",
    "STOP_BREACHED": "이전 계획 손절 기준 이탈",
    "TARGET1_REACHED": "이전 계획 1차 목표 이상",
    "TARGET2_REACHED": "이전 계획 2차 목표 이상",
}


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class HoldingDecisionContextService:
    """Project richer HOLD decision context from immutable analysis history.

    No provider calls, no Market Store writes, and no new strategy/risk thresholds.
    The entry state comes from the existing readiness snapshot. Price-plan state
    compares the current confirmed EOD close with the previous market day's current
    revision only.
    """

    def __init__(self, catalog: HoldingsCatalog) -> None:
        self.catalog = catalog

    def build(self, monitored_stock_id: str) -> dict[str, Any] | None:
        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.market_date,r.*
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.monitored_stock_id=?
                ORDER BY d.market_date DESC
                LIMIT 2
                """,
                (monitored_stock_id,),
            ).fetchall()

        if not rows:
            return None

        current_row = rows[0]
        previous_row = rows[1] if len(rows) > 1 else None
        current = self.catalog._revision_from_row(current_row)  # noqa: SLF001
        previous = (
            self.catalog._revision_from_row(previous_row)  # noqa: SLF001
            if previous_row is not None
            else None
        )

        snapshot = current.snapshot if isinstance(current.snapshot, dict) else {}
        readiness = snapshot.get("readiness_state")
        readiness = readiness if isinstance(readiness, dict) else {}
        condition_state = snapshot.get("condition_state")
        condition_state = condition_state if isinstance(condition_state, dict) else {}

        raw_entry_state = str(
            readiness.get("status")
            or snapshot.get("candidate_state")
            or current.action_state
            or "UNKNOWN"
        ).strip().upper()
        if raw_entry_state == "VALIDATION":
            raw_entry_state = "WATCH"
        if raw_entry_state not in ENTRY_LABELS:
            raw_entry_state = "UNKNOWN"

        warnings = readiness.get("warnings")
        warnings = (
            [str(item) for item in warnings if str(item).strip()]
            if isinstance(warnings, list)
            else []
        )

        raw_missing_details = condition_state.get("missing_details")
        missing_details: list[dict[str, str | None]] = []
        if isinstance(raw_missing_details, list):
            for item in raw_missing_details:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("raw") or "").strip()
                if not label:
                    continue
                missing_details.append(
                    {
                        "label": label,
                        "detail": (
                            str(item.get("detail")).strip()
                            if item.get("detail") not in (None, "")
                            else None
                        ),
                        "current_value": (
                            str(item.get("current_value")).strip()
                            if item.get("current_value") not in (None, "")
                            else None
                        ),
                        "required_value": (
                            str(item.get("required_value")).strip()
                            if item.get("required_value") not in (None, "")
                            else None
                        ),
                        "raw": (
                            str(item.get("raw")).strip()
                            if item.get("raw") not in (None, "")
                            else None
                        ),
                    }
                )

        passed = _safe_int(condition_state.get("passed"))
        if passed is None:
            passed = _safe_int(readiness.get("passed"))
        missing = _safe_int(condition_state.get("missing"))
        if missing is None:
            missing = _safe_int(readiness.get("missing"))
        total = _safe_int(condition_state.get("total"))
        if total is None:
            total = _safe_int(readiness.get("total"))
        if missing_details:
            missing = len(missing_details)
            if total is not None and passed is None:
                passed = max(0, total - missing)

        entry = {
            "state": raw_entry_state,
            "label": ENTRY_LABELS[raw_entry_state],
            "summary": (
                str(readiness.get("summary")).strip()
                if readiness.get("summary") not in (None, "")
                else None
            ),
            "decision_reason": (
                str(readiness.get("decision_reason")).strip()
                if readiness.get("decision_reason") not in (None, "")
                else None
            ),
            "passed": passed,
            "missing": missing,
            "total": total,
            "warnings": warnings,
            "missing_details": missing_details,
        }

        current_strategy = current.strategy_key
        previous_strategy = previous.strategy_key if previous is not None else None
        if previous is None:
            strategy_state = "INITIAL"
        elif previous_strategy == current_strategy:
            strategy_state = "UNCHANGED"
        else:
            strategy_state = "CHANGED"

        strategy = {
            "state": strategy_state,
            "current": current_strategy,
            "previous": previous_strategy,
            "previous_market_date": (
                str(previous_row["market_date"]) if previous_row is not None else None
            ),
        }

        previous_reference = previous.reference_price if previous is not None else None
        previous_stop = previous.stop_price if previous is not None else None
        previous_target1 = previous.target1_price if previous is not None else None
        previous_target2 = previous.target2_price if previous is not None else None
        current_close = current.reference_price

        if previous is None:
            plan_state = "FIRST_PLAN"
        elif (
            current_close is None
            or all(
                value is None
                for value in (previous_stop, previous_target1, previous_target2)
            )
        ):
            plan_state = "PREVIOUS_PLAN_UNAVAILABLE"
        elif previous_stop is not None and current_close <= previous_stop:
            plan_state = "STOP_BREACHED"
        elif previous_target2 is not None and current_close >= previous_target2:
            plan_state = "TARGET2_REACHED"
        elif previous_target1 is not None and current_close >= previous_target1:
            plan_state = "TARGET1_REACHED"
        else:
            plan_state = "WITHIN_PLAN"

        previous_plan = {
            "state": plan_state,
            "label": PLAN_LABELS[plan_state],
            "previous_market_date": (
                str(previous_row["market_date"]) if previous_row is not None else None
            ),
            "previous_reference_price": _decimal_text(previous_reference),
            "previous_stop_price": _decimal_text(previous_stop),
            "previous_target1_price": _decimal_text(previous_target1),
            "previous_target2_price": _decimal_text(previous_target2),
            "current_close": _decimal_text(current_close),
        }

        return {
            "entry": entry,
            "strategy": strategy,
            "previous_plan": previous_plan,
        }
