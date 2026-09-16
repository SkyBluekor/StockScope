import json
from pathlib import Path

from app.backtest.exit_policy_validation_runner import ExitPolicyValidationCheckpoint


def _report(signature: str, stocks: int, *, expanded: bool = False):
    payload = {
        "signature": signature,
        "status": "COMPLETED",
        "period": {"start": "2023-09-16", "end": "2026-09-16"},
        "validation_config": {"max_holding_days": 20},
        "validated_stocks": [{"code": f"{i:06d}", "market": "KOSPI"} for i in range(stocks)],
        "summary": {"selected": 0, "baseline_better": 5, "unresolved": 5, "insufficient_sample": 0},
    }
    if expanded:
        payload["expanded_revalidation"] = {"base_signature": "a" * 20, "base_stock_count": 20}
    return payload


def test_history_metadata_is_lightweight_and_deduplicated(tmp_path: Path):
    store = ExitPolicyValidationCheckpoint(tmp_path)
    base = _report("a" * 20, 20)
    expanded = _report("b" * 20, 40, expanded=True)
    store.save_report(base)
    store.save_report(expanded)

    rows = store.list_reports(10)
    signatures = [row["signature"] for row in rows]
    assert signatures.count("b" * 20) == 1
    assert "a" * 20 in signatures
    latest = rows[0]
    assert latest["stock_count"] == 40
    assert latest["is_expanded"] is True
    assert latest["base_signature"] == "a" * 20
    assert latest["summary"]["baseline_better"] == 5
    assert "strategies" not in latest


def test_history_limit_is_respected(tmp_path: Path):
    store = ExitPolicyValidationCheckpoint(tmp_path)
    for idx in range(3):
        sig = f"{idx + 1:020x}"
        store.save_report(_report(sig, 20 + idx))
    rows = store.list_reports(2)
    assert len(rows) == 2
