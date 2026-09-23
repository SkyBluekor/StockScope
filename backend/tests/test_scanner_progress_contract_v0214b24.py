from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "backend/app/backtest/scanner.py"
API = ROOT / "backend/app/api/backtest.py"
PANEL = ROOT / "frontend/src/components/ScannerPanel.tsx"
PROGRESS = ROOT / "frontend/src/components/scannerProgress.ts"
PROGRESS_CSS = ROOT / "frontend/src/components/scannerProgress.css"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_prepare_latest_confirmed_data_has_real_progress_and_heartbeat() -> None:
    source = _source(SCANNER)
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "prepare_latest_confirmed_data"
    )
    assert "progress" in [arg.arg for arg in method.args.args + method.args.kwonlyargs]
    for stage in (
        "scanner_prepare_local",
        "scanner_prepare_probe",
        "scanner_prepare_kospi_stock",
        "scanner_prepare_kospi_index",
        "scanner_prepare_kosdaq_stock",
        "scanner_prepare_kosdaq_index",
        "scanner_prepare_store",
    ):
        # Dynamic per-market stage names are represented by the prefix in source.
        if "{market.lower()}" in stage:
            continue
    assert '"scanner_prepare_local"' in source
    assert '"scanner_prepare_probe"' in source
    assert 'f"scanner_prepare_{market.lower()}_stock"' in source
    assert 'f"scanner_prepare_{market.lower()}_index"' in source
    assert '"scanner_prepare_store"' in source
    assert "asyncio.wait_for(asyncio.shield(task), timeout=2.0)" in source
    assert '"completed_stages"' in source
    assert '"reused_stages"' in source


def test_scanner_job_owns_freshness_then_analysis_without_decision_version_bump() -> None:
    scanner_source = _source(SCANNER)
    api_source = _source(API)
    assert re.search(r'VERSION\s*=\s*"0\.21\.3\.7"', scanner_source)
    assert "known_data_date: str | None = None" in api_source
    job_start = api_source.index("async def _run_scanner_job")
    job_end = api_source.index('@router.post("/scanner/freshness")', job_start)
    job_source = api_source[job_start:job_end]
    assert job_source.index("prepare_latest_confirmed_data") < job_source.index("service.run(")
    assert '"freshness_failure"' in job_source
    assert '"resolved_as_of_date"' in job_source
    assert '"completed_stages"' in job_source


def test_frontend_uses_stage_truth_not_fake_percent() -> None:
    panel = _source(PANEL)
    helper = _source(PROGRESS)
    css = _source(PROGRESS_CSS)
    assert "scannerProgressView" in panel
    assert "known_data_date" in panel
    assert "prepareScannerLatestData" not in panel
    assert "scanner-progress-track" not in panel
    assert "overallPercent" not in panel
    assert "준비 단계" in panel and "분석 단계" in panel
    assert "저장 데이터 재사용" in panel
    assert "진행 상세" in panel
    assert "PREPARATION_STAGES" in helper
    assert "ANALYSIS_STAGES" in helper
    assert 'marketScope === "KOSPI"' in helper
    assert 'marketScope === "KOSDAQ"' in helper
    assert "var(--bg" in css or "var(--text" in css
    assert "#FFFFFF" not in css.upper()


def test_progress_is_not_persisted_into_scanner_session_schema() -> None:
    panel = _source(PANEL)
    session = _source(ROOT / "frontend/src/components/scannerSession.ts")
    assert "progress:" not in session
    assert "progressStages" not in session
    assert "writeScannerSession({" in panel
