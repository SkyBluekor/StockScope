from __future__ import annotations

from typing import Any, Iterable


STATUS_LABELS = {
    "PASS": "확인",
    "WARN": "대기",
    "FAIL": "실패",
    "UNKNOWN": "미확정",
}


def build_auto_check_summary(
    *,
    checks: Iterable[dict[str, Any]],
    basis: str,
    input_hints: list[dict[str, str]] | None = None,
    next_data_note: str | None = None,
) -> dict[str, Any]:
    """Create a reusable progress model for strategy auto-check UIs.

    This deliberately reports condition progress, not a probability of price movement.
    """

    rows = [dict(item) for item in checks]
    total = len(rows)
    passed_rows = [item for item in rows if item.get("status") == "PASS"]
    failed_rows = [item for item in rows if item.get("status") == "FAIL"]
    pending_rows = [item for item in rows if item.get("status") in {"WARN", "UNKNOWN"}]
    known_rows = [item for item in rows if item.get("status") != "UNKNOWN"]

    def compact(item: dict[str, Any]) -> dict[str, Any]:
        status = str(item.get("status") or "UNKNOWN")
        return {
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "status": status,
            "status_label": STATUS_LABELS.get(status, status),
            "value": str(item.get("value") or ""),
            "explanation": str(item.get("explanation") or ""),
            "source": str(item.get("source") or ""),
        }

    passed = len(passed_rows)
    failed = len(failed_rows)
    pending = len(pending_rows)
    progress_pct = 0 if total == 0 else round(passed / total * 100)

    if failed:
        progress_message = f"{failed}개 핵심 조건에서 실패가 확인됐습니다."
    elif pending:
        progress_message = f"{total}개 조건 중 {passed}개 확인, {pending}개는 아직 확인 중입니다."
    else:
        progress_message = f"{total}개 조건이 모두 확인됐습니다."

    return {
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "known": len(known_rows),
        "total": total,
        "progress_pct": progress_pct,
        "progress_label": f"{passed}/{total} 조건 확인",
        "progress_message": progress_message,
        "passed_checks": [compact(item) for item in passed_rows],
        "failed_checks": [compact(item) for item in failed_rows],
        "pending_checks": [compact(item) for item in pending_rows],
        "basis": basis,
        "basis_label": "KRX 확정 EOD" if basis == "CONFIRMED_EOD" else "장중 Preview",
        "is_confirmed_basis": basis == "CONFIRMED_EOD",
        "input_hints": input_hints or [],
        "next_data_note": next_data_note or "다음 분석 시 앱이 자동으로 다시 판정합니다.",
        "policy": "이 진행도는 조건 확인 개수이며 상승확률이나 매매 성공확률이 아닙니다.",
    }
