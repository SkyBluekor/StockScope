from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

DECISION = BACKEND / "app" / "holdings" / "decision_context.py"
DECISION_TEST = BACKEND / "tests" / "test_holdings_decision_context_hold1g4.py"
HOLDINGS_API = BACKEND / "app" / "api" / "holdings.py"
ANALYSIS = BACKEND / "app" / "holdings" / "analysis.py"
ANALYSIS_HISTORY = BACKEND / "app" / "holdings" / "analysis_history.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
SERVICE = FRONTEND / "src" / "services" / "holdingsApi.ts"
WORKSPACE = FRONTEND / "src" / "components" / "HoldingsWorkspace.tsx"
CHART = FRONTEND / "src" / "components" / "HoldingsPriceChart.tsx"
CSS = FRONTEND / "src" / "holdings.css"
PACKAGE = FRONTEND / "package.json"

DECISION_CONTENT = 'from __future__ import annotations\n\nfrom decimal import Decimal\nfrom typing import Any\n\nfrom .catalog import HoldingsCatalog\n\n\nENTRY_LABELS = {\n    "READY": "진입 후보",\n    "WATCH": "조건 형성 중",\n    "NOT_READY": "조건 부족",\n    "BLOCKED": "위험 때문에 보류",\n    "CAUTION": "위험 주의",\n    "NO_TRADE": "신규 진입 제외",\n    "UNKNOWN": "판단 정보 없음",\n}\n\nPLAN_LABELS = {\n    "NO_PREVIOUS_PLAN": "비교할 이전 계획 없음",\n    "WITHIN_PLAN": "이전 계획 범위 내",\n    "STOP_BREACHED": "이전 계획 손절 기준 이탈",\n    "TARGET1_REACHED": "이전 계획 1차 목표 이상",\n    "TARGET2_REACHED": "이전 계획 2차 목표 이상",\n}\n\n\ndef _decimal_text(value: Decimal | None) -> str | None:\n    return None if value is None else format(value, "f")\n\n\ndef _safe_int(value: Any) -> int | None:\n    try:\n        return int(value)\n    except (TypeError, ValueError):\n        return None\n\n\nclass HoldingDecisionContextService:\n    """Project richer HOLD decision context from immutable analysis history.\n\n    No provider calls, no Market Store writes, and no new strategy/risk thresholds.\n    The entry state comes from the existing readiness snapshot. Price-plan state\n    compares the current confirmed EOD close with the previous market day\'s current\n    revision only.\n    """\n\n    def __init__(self, catalog: HoldingsCatalog) -> None:\n        self.catalog = catalog\n\n    def build(self, monitored_stock_id: str) -> dict[str, Any] | None:\n        with self.catalog.connection() as conn:\n            rows = conn.execute(\n                """\n                SELECT d.market_date,r.*\n                FROM stock_analysis_day d\n                JOIN stock_analysis_revision r ON r.id=d.current_revision_id\n                WHERE d.monitored_stock_id=?\n                ORDER BY d.market_date DESC\n                LIMIT 2\n                """,\n                (monitored_stock_id,),\n            ).fetchall()\n\n        if not rows:\n            return None\n\n        current_row = rows[0]\n        previous_row = rows[1] if len(rows) > 1 else None\n        current = self.catalog._revision_from_row(current_row)  # noqa: SLF001\n        previous = (\n            self.catalog._revision_from_row(previous_row)  # noqa: SLF001\n            if previous_row is not None\n            else None\n        )\n\n        snapshot = current.snapshot if isinstance(current.snapshot, dict) else {}\n        readiness = snapshot.get("readiness_state")\n        readiness = readiness if isinstance(readiness, dict) else {}\n\n        raw_entry_state = str(\n            readiness.get("status")\n            or snapshot.get("candidate_state")\n            or current.action_state\n            or "UNKNOWN"\n        ).strip().upper()\n        if raw_entry_state == "VALIDATION":\n            raw_entry_state = "WATCH"\n        if raw_entry_state not in ENTRY_LABELS:\n            raw_entry_state = "UNKNOWN"\n\n        warnings = readiness.get("warnings")\n        warnings = (\n            [str(item) for item in warnings if str(item).strip()]\n            if isinstance(warnings, list)\n            else []\n        )\n\n        entry = {\n            "state": raw_entry_state,\n            "label": ENTRY_LABELS[raw_entry_state],\n            "summary": (\n                str(readiness.get("summary")).strip()\n                if readiness.get("summary") not in (None, "")\n                else None\n            ),\n            "decision_reason": (\n                str(readiness.get("decision_reason")).strip()\n                if readiness.get("decision_reason") not in (None, "")\n                else None\n            ),\n            "missing": _safe_int(readiness.get("missing")),\n            "total": _safe_int(readiness.get("total")),\n            "warnings": warnings,\n        }\n\n        current_strategy = current.strategy_key\n        previous_strategy = previous.strategy_key if previous is not None else None\n        if previous is None:\n            strategy_state = "INITIAL"\n        elif previous_strategy == current_strategy:\n            strategy_state = "UNCHANGED"\n        else:\n            strategy_state = "CHANGED"\n\n        strategy = {\n            "state": strategy_state,\n            "current": current_strategy,\n            "previous": previous_strategy,\n            "previous_market_date": (\n                str(previous_row["market_date"]) if previous_row is not None else None\n            ),\n        }\n\n        previous_stop = previous.stop_price if previous is not None else None\n        previous_target1 = previous.target1_price if previous is not None else None\n        previous_target2 = previous.target2_price if previous is not None else None\n        current_close = current.reference_price\n        has_previous_plan = previous is not None and any(\n            value is not None\n            for value in (previous_stop, previous_target1, previous_target2)\n        )\n\n        if not has_previous_plan or current_close is None:\n            plan_state = "NO_PREVIOUS_PLAN"\n        elif previous_stop is not None and current_close <= previous_stop:\n            plan_state = "STOP_BREACHED"\n        elif previous_target2 is not None and current_close >= previous_target2:\n            plan_state = "TARGET2_REACHED"\n        elif previous_target1 is not None and current_close >= previous_target1:\n            plan_state = "TARGET1_REACHED"\n        else:\n            plan_state = "WITHIN_PLAN"\n\n        previous_plan = {\n            "state": plan_state,\n            "label": PLAN_LABELS[plan_state],\n            "previous_market_date": (\n                str(previous_row["market_date"]) if previous_row is not None else None\n            ),\n            "previous_stop_price": _decimal_text(previous_stop),\n            "previous_target1_price": _decimal_text(previous_target1),\n            "previous_target2_price": _decimal_text(previous_target2),\n            "current_close": _decimal_text(current_close),\n        }\n\n        return {\n            "entry": entry,\n            "strategy": strategy,\n            "previous_plan": previous_plan,\n        }\n'
DECISION_TEST_CONTENT = 'from __future__ import annotations\n\nfrom pathlib import Path\n\nimport pytest\n\nfrom app.holdings.catalog import HoldingsCatalog\nfrom app.holdings.decision_context import HoldingDecisionContextService\n\n\ndef _catalog(tmp_path: Path):\n    catalog = HoldingsCatalog(tmp_path / "holdings.db")\n    catalog.initialize()\n    stock = catalog.create_monitored_stock(\n        market="KOSPI",\n        ticker="005930",\n        name="삼성전자",\n        watch_enabled=True,\n    )\n    return catalog, stock\n\n\ndef _store(\n    catalog: HoldingsCatalog,\n    stock_id: str,\n    *,\n    market_date: str,\n    fingerprint: str,\n    strategy: str = "momentum_continuation",\n    action: str = "WATCH",\n    readiness: str = "WATCH",\n    reference: str = "100",\n    stop: str | None = "90",\n    target1: str | None = "110",\n    target2: str | None = "120",\n    summary: str | None = None,\n):\n    day = catalog.get_or_create_analysis_day(\n        monitored_stock_id=stock_id,\n        market_date=market_date,\n    )\n    revision = catalog.append_analysis_revision(\n        analysis_day_id=day.id,\n        input_fingerprint=fingerprint,\n        strategy_key=strategy,\n        action_state=action,\n        risk_state="READY",\n        reference_price=reference,\n        stop_price=stop,\n        target1_price=target1,\n        target2_price=target2,\n        scanner_version="0.21.3.7",\n        analysis_engine_version="HOLD_SINGLE_STOCK_V1",\n        policy_version="P1",\n        source_versions={"fixture": fingerprint},\n        snapshot={\n            "candidate_state": action,\n            "readiness_state": {\n                "status": readiness,\n                "summary": summary,\n                "decision_reason": "ENTRY_CONDITIONS_MISSING",\n                "missing": 2,\n                "total": 8,\n                "warnings": [],\n            },\n        },\n        revision_reason="INITIAL",\n        computed_at=f"{market_date}T08:00:00+00:00",\n    )\n    catalog.promote_current_revision(\n        analysis_day_id=day.id,\n        revision_id=revision.id,\n    )\n    return revision\n\n\n@pytest.mark.parametrize(\n    ("state", "label"),\n    [\n        ("READY", "진입 후보"),\n        ("WATCH", "조건 형성 중"),\n        ("NOT_READY", "조건 부족"),\n        ("BLOCKED", "위험 때문에 보류"),\n        ("CAUTION", "위험 주의"),\n    ],\n)\ndef test_entry_state_preserves_readiness_variation(tmp_path: Path, state: str, label: str):\n    catalog, stock = _catalog(tmp_path)\n    _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-22",\n        fingerprint=f"fp-{state}",\n        readiness=state,\n        action="WATCH",\n        summary="기존 readiness 설명",\n    )\n\n    context = HoldingDecisionContextService(catalog).build(stock.id)\n\n    assert context is not None\n    assert context["entry"]["state"] == state\n    assert context["entry"]["label"] == label\n    assert context["entry"]["summary"] == "기존 readiness 설명"\n\n\ndef test_previous_plan_stop_breach_and_same_day_revision_is_not_previous_plan(tmp_path: Path):\n    catalog, stock = _catalog(tmp_path)\n    _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-21",\n        fingerprint="prev",\n        strategy="pullback",\n        reference="105",\n        stop="100",\n        target1="110",\n        target2="120",\n    )\n    first_today = _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-22",\n        fingerprint="today-1",\n        strategy="trend_recovery",\n        reference="99",\n        stop="95",\n        target1="115",\n        target2="125",\n    )\n    day = catalog.get_or_create_analysis_day(\n        monitored_stock_id=stock.id,\n        market_date="2026-09-22",\n    )\n    same_day_second = catalog.append_analysis_revision(\n        analysis_day_id=day.id,\n        input_fingerprint="today-2",\n        strategy_key="momentum_continuation",\n        action_state="WATCH",\n        risk_state="READY",\n        reference_price="95",\n        stop_price="90",\n        target1_price="112",\n        target2_price="130",\n        scanner_version="0.21.3.7",\n        analysis_engine_version="HOLD_SINGLE_STOCK_V1",\n        policy_version="P1",\n        source_versions={"fixture": "today-2"},\n        snapshot={"readiness_state": {"status": "NOT_READY"}},\n        revision_reason="INPUT_CHANGED",\n        computed_at="2026-09-22T09:00:00+00:00",\n    )\n    catalog.promote_current_revision(\n        analysis_day_id=day.id,\n        revision_id=same_day_second.id,\n    )\n\n    context = HoldingDecisionContextService(catalog).build(stock.id)\n\n    assert context["previous_plan"]["state"] == "STOP_BREACHED"\n    assert context["previous_plan"]["previous_market_date"] == "2026-09-21"\n    assert context["previous_plan"]["previous_stop_price"] == "100"\n    assert context["previous_plan"]["current_close"] == "95"\n    assert context["strategy"]["state"] == "CHANGED"\n    assert context["strategy"]["previous"] == "pullback"\n    assert context["strategy"]["current"] == "momentum_continuation"\n    assert first_today.id != same_day_second.id\n\n\n@pytest.mark.parametrize(\n    ("current_close", "expected"),\n    [\n        ("105", "WITHIN_PLAN"),\n        ("115", "TARGET1_REACHED"),\n        ("125", "TARGET2_REACHED"),\n    ],\n)\ndef test_previous_plan_price_states(tmp_path: Path, current_close: str, expected: str):\n    catalog, stock = _catalog(tmp_path)\n    _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-21",\n        fingerprint="prev",\n        reference="100",\n        stop="90",\n        target1="110",\n        target2="120",\n    )\n    _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-22",\n        fingerprint="current",\n        reference=current_close,\n    )\n\n    context = HoldingDecisionContextService(catalog).build(stock.id)\n    assert context["previous_plan"]["state"] == expected\n\n\ndef test_first_analysis_has_initial_strategy_and_no_previous_plan(tmp_path: Path):\n    catalog, stock = _catalog(tmp_path)\n    _store(\n        catalog,\n        stock.id,\n        market_date="2026-09-22",\n        fingerprint="first",\n        strategy="ma20_rebound",\n        readiness="READY",\n    )\n\n    context = HoldingDecisionContextService(catalog).build(stock.id)\n\n    assert context["strategy"] == {\n        "state": "INITIAL",\n        "current": "ma20_rebound",\n        "previous": None,\n        "previous_market_date": None,\n    }\n    assert context["previous_plan"]["state"] == "NO_PREVIOUS_PLAN"\n\n\ndef test_decision_context_is_database_only() -> None:\n    source = Path("backend/app/holdings/decision_context.py").read_text(encoding="utf-8")\n    assert "KrxProvider" not in source\n    assert "StockScannerService" not in source\n    assert "requests." not in source\n    assert "httpx." not in source\n    assert "sqlite3.connect" not in source\n'
CHART_CONTENT = 'import { useEffect, useMemo, useState, type PointerEvent } from "react";\nimport {\n  getHoldingChart,\n  type HoldingAnalysis,\n  type HoldingDecisionContext,\n  type HoldingChartBar,\n  type HoldingChartRange,\n  type HoldingChartResponse,\n} from "../services/holdingsApi";\n\nconst RANGE_OPTIONS: Array<{ key: HoldingChartRange; label: string }> = [\n  { key: "1m", label: "1개월" },\n  { key: "3m", label: "3개월" },\n  { key: "6m", label: "6개월" },\n  { key: "1y", label: "1년" },\n];\n\nconst W = 920;\nconst H = 292;\nconst LEFT = 58;\nconst RIGHT = 74;\nconst TOP = 18;\nconst PRICE_BOTTOM = 210;\nconst VOLUME_TOP = 229;\nconst VOLUME_BOTTOM = 272;\n\nfunction number(value: string | null | undefined) {\n  if (value == null || value === "") return null;\n  const parsed = Number(value);\n  return Number.isFinite(parsed) ? parsed : null;\n}\n\nfunction formatPrice(value: number) {\n  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);\n}\n\nfunction formatVolume(value: number) {\n  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(value);\n}\n\nfunction shortDate(value: string) {\n  return value.length >= 10 ? `${value.slice(5, 7)}.${value.slice(8, 10)}` : value;\n}\n\nfunction mergeBars(history: HoldingChartBar[], liveBar: HoldingChartBar | null) {\n  if (!liveBar) return history;\n  if (history.length === 0) return [liveBar];\n  const last = history[history.length - 1];\n  if (last.date === liveBar.date) return [...history.slice(0, -1), liveBar];\n  return [...history, liveBar];\n}\n\ntype Props = {\n  stockId: string;\n  analysis: HoldingAnalysis | null;\n  liveBar?: HoldingChartBar | null;\n  refreshKey?: number;\n  decisionContext?: HoldingDecisionContext | null;\n};\n\nexport default function HoldingsPriceChart({\n  stockId,\n  analysis,\n  liveBar = null,\n  refreshKey = 0,\n  decisionContext = null,\n}: Props) {\n  const [range, setRange] = useState<HoldingChartRange>("1m");\n  const [chart, setChart] = useState<HoldingChartResponse | null>(null);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState<string | null>(null);\n  const [hoverIndex, setHoverIndex] = useState<number | null>(null);\n\n  useEffect(() => {\n    let cancelled = false;\n    setLoading(true);\n    setError(null);\n    setHoverIndex(null);\n    void getHoldingChart(stockId, range)\n      .then((result) => {\n        if (!cancelled) setChart(result);\n      })\n      .catch((loadError) => {\n        if (cancelled) return;\n        setChart(null);\n        setError(loadError instanceof Error ? loadError.message : "차트 데이터를 불러오지 못했습니다.");\n      })\n      .finally(() => {\n        if (!cancelled) setLoading(false);\n      });\n    return () => {\n      cancelled = true;\n    };\n  }, [stockId, range, refreshKey]);\n\n  const bars = useMemo(() => mergeBars(chart?.bars ?? [], liveBar), [chart, liveBar]);\n\n  const model = useMemo(() => {\n    const numeric = bars\n      .map((bar) => ({\n        ...bar,\n        o: number(bar.open),\n        h: number(bar.high),\n        l: number(bar.low),\n        c: number(bar.close),\n        v: number(bar.volume),\n      }))\n      .filter((bar) => bar.o != null && bar.h != null && bar.l != null && bar.c != null && bar.v != null);\n\n    if (numeric.length === 0) return null;\n\n    const levels = [\n      { key: "reference", label: "기준가", value: number(analysis?.reference_price) },\n      { key: "stop", label: "손절", value: number(analysis?.stop_price) },\n      { key: "target1", label: "1차 목표", value: number(analysis?.target1_price) },\n      { key: "target2", label: "2차 목표", value: number(analysis?.target2_price) },\n    ].filter((item): item is { key: string; label: string; value: number } => item.value != null);\n\n    const lowest = Math.min(...numeric.map((bar) => bar.l!));\n    const highest = Math.max(...numeric.map((bar) => bar.h!));\n    const visibleRange = Math.max(highest - lowest, highest * 0.015, 1);\n    const minPrice = lowest - visibleRange * 0.08;\n    const maxPrice = highest + visibleRange * 0.08;\n    const priceRange = maxPrice - minPrice || 1;\n    const maxVolume = Math.max(...numeric.map((bar) => bar.v!), 1);\n    const plotWidth = W - LEFT - RIGHT;\n    const step = plotWidth / numeric.length;\n    const candleWidth = Math.max(1.2, Math.min(8.5, step * 0.56));\n\n    const yPrice = (value: number) => TOP + ((maxPrice - value) / priceRange) * (PRICE_BOTTOM - TOP);\n    const xAt = (index: number) => LEFT + step * (index + 0.5);\n    const volumeY = (value: number) => VOLUME_BOTTOM - (value / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);\n\n    const tickIndexes = Array.from(new Set([\n      0,\n      Math.floor((numeric.length - 1) * 0.25),\n      Math.floor((numeric.length - 1) * 0.5),\n      Math.floor((numeric.length - 1) * 0.75),\n      numeric.length - 1,\n    ])).sort((a, b) => a - b);\n\n    const yTicks = Array.from({ length: 5 }, (_, index) => {\n      const ratio = index / 4;\n      const value = maxPrice - (maxPrice - minPrice) * ratio;\n      return { value, y: TOP + (PRICE_BOTTOM - TOP) * ratio };\n    });\n\n    const analysisIndex = analysis\n      ? numeric.findIndex((bar) => bar.date === analysis.market_date)\n      : -1;\n\n    const plottedLevels = levels.map((level) => ({\n      ...level,\n      position: level.value > maxPrice ? "above" : level.value < minPrice ? "below" : "inside",\n    }));\n\n    return {\n      numeric,\n      levels: plottedLevels,\n      xAt,\n      yPrice,\n      volumeY,\n      candleWidth,\n      tickIndexes,\n      yTicks,\n      analysisIndex,\n      plotWidth,\n      step,\n    };\n  }, [bars, analysis]);\n\n  function handlePointerMove(event: PointerEvent<SVGRectElement>) {\n    if (!model) return;\n    const rect = event.currentTarget.getBoundingClientRect();\n    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));\n    const chartX = ratio * W;\n    const raw = Math.floor((chartX - LEFT) / model.step);\n    const index = Math.max(0, Math.min(model.numeric.length - 1, raw));\n    setHoverIndex(index);\n  }\n\n  const hovered = model && hoverIndex != null ? model.numeric[hoverIndex] : null;\n  const chartDate = chart?.to_date ?? null;\n  const analysisDate = analysis?.market_date ?? null;\n  const analysisBehindChart = Boolean(chartDate && analysisDate && analysisDate < chartDate);\n\n  return (\n    <section className="holdings-chart-panel">\n      <div className="holdings-chart-head">\n        <div>\n          <h3>확정 일봉</h3>\n          <span>{chartDate ? `${chartDate.replace(/-/g, ".")}까지` : "저장된 확정 데이터 기준"}</span>\n        </div>\n        <div className="holdings-chart-ranges" aria-label="차트 기간">\n          {RANGE_OPTIONS.map((option) => (\n            <button\n              key={option.key}\n              type="button"\n              className={range === option.key ? "active" : ""}\n              onClick={() => setRange(option.key)}\n            >\n              {option.label}\n            </button>\n          ))}\n        </div>\n      </div>\n\n      {decisionContext && ["STOP_BREACHED", "TARGET1_REACHED", "TARGET2_REACHED"].includes(\n        decisionContext.previous_plan.state,\n      ) && (\n        <div className={`holdings-chart-plan-event ${decisionContext.previous_plan.state.toLowerCase()}`}>\n          <span>이전 계획</span>\n          <strong>{decisionContext.previous_plan.label}</strong>\n          {decisionContext.previous_plan.previous_market_date && (\n            <small>{decisionContext.previous_plan.previous_market_date.replace(/-/g, ".")} 기준</small>\n          )}\n        </div>\n      )}\n\n      {model && (\n        <div className="holdings-chart-levels" aria-label="분석 가격 기준">\n          {model.levels.map((level) => (\n            <span key={level.key} className={`holdings-chart-level ${level.key}`}>\n              <i aria-hidden="true" />\n              <b>{level.position === "above" ? "↑ " : level.position === "below" ? "↓ " : ""}{level.label}</b>\n              <strong>{formatPrice(level.value)}</strong>\n            </span>\n          ))}\n        </div>\n      )}\n\n      {loading && !chart ? (\n        <div className="holdings-chart-state">확정 일봉을 불러오는 중입니다.</div>\n      ) : error ? (\n        <div className="holdings-chart-state error">{error}</div>\n      ) : !model ? (\n        <div className="holdings-chart-state">표시할 확정 일봉이 없습니다.</div>\n      ) : (\n        <div className="holdings-chart-canvas">\n          <svg\n            viewBox={`0 0 ${W} ${H}`}\n            role="img"\n            aria-label={`${range} 확정 일봉 캔들 차트`}\n            onPointerLeave={() => setHoverIndex(null)}\n          >\n            <g className="holdings-chart-grid">\n              {model.yTicks.map((tick) => (\n                <g key={tick.y}>\n                  <line x1={LEFT} x2={W - RIGHT} y1={tick.y} y2={tick.y} />\n                  <text x={W - RIGHT + 8} y={tick.y + 4}>{formatPrice(tick.value)}</text>\n                </g>\n              ))}\n              <line x1={LEFT} x2={W - RIGHT} y1={VOLUME_TOP - 8} y2={VOLUME_TOP - 8} />\n            </g>\n\n            {model.levels\n              .filter((level) => level.position === "inside")\n              .map((level) => {\n                const y = model.yPrice(level.value);\n                return (\n                  <line\n                    key={level.key}\n                    className={`holdings-level-line ${level.key}`}\n                    x1={LEFT}\n                    x2={W - RIGHT}\n                    y1={y}\n                    y2={y}\n                  />\n                );\n              })}\n\n            {model.analysisIndex >= 0 && (\n              <line\n                className="holdings-analysis-marker"\n                x1={model.xAt(model.analysisIndex)}\n                x2={model.xAt(model.analysisIndex)}\n                y1={TOP}\n                y2={VOLUME_BOTTOM}\n              />\n            )}\n\n            <g className="holdings-candles">\n              {model.numeric.map((bar, index) => {\n                const x = model.xAt(index);\n                const openY = model.yPrice(bar.o!);\n                const closeY = model.yPrice(bar.c!);\n                const highY = model.yPrice(bar.h!);\n                const lowY = model.yPrice(bar.l!);\n                const bodyY = Math.min(openY, closeY);\n                const bodyHeight = Math.max(1.2, Math.abs(closeY - openY));\n                const direction = bar.c! > bar.o! ? "up" : bar.c! < bar.o! ? "down" : "flat";\n                const volumeY = model.volumeY(bar.v!);\n                return (\n                  <g key={`${bar.date}-${index}`} className={`holdings-candle ${direction}`}>\n                    <line x1={x} x2={x} y1={highY} y2={lowY} />\n                    <rect\n                      x={x - model.candleWidth / 2}\n                      y={bodyY}\n                      width={model.candleWidth}\n                      height={bodyHeight}\n                    />\n                    <rect\n                      className="volume"\n                      x={x - model.candleWidth / 2}\n                      y={volumeY}\n                      width={model.candleWidth}\n                      height={Math.max(1, VOLUME_BOTTOM - volumeY)}\n                    />\n                  </g>\n                );\n              })}\n            </g>\n\n            <g className="holdings-chart-dates">\n              {model.tickIndexes.map((index) => (\n                <text key={index} x={model.xAt(index)} y={H - 5}>{shortDate(model.numeric[index].date)}</text>\n              ))}\n            </g>\n\n            {hoverIndex != null && (\n              <line\n                className="holdings-chart-hover-line"\n                x1={model.xAt(hoverIndex)}\n                x2={model.xAt(hoverIndex)}\n                y1={TOP}\n                y2={VOLUME_BOTTOM}\n              />\n            )}\n\n            <rect\n              className="holdings-chart-hit"\n              x={LEFT}\n              y={TOP}\n              width={model.plotWidth}\n              height={VOLUME_BOTTOM - TOP}\n              onPointerMove={handlePointerMove}\n            />\n          </svg>\n\n          {hovered && (\n            <div className="holdings-chart-tooltip">\n              <strong>{hovered.date.replace(/-/g, ".")}</strong>\n              <span>시가 <b>{formatPrice(hovered.o!)}</b></span>\n              <span>고가 <b>{formatPrice(hovered.h!)}</b></span>\n              <span>저가 <b>{formatPrice(hovered.l!)}</b></span>\n              <span>종가 <b>{formatPrice(hovered.c!)}</b></span>\n              <span>거래량 <b>{formatVolume(hovered.v!)}</b></span>\n            </div>\n          )}\n        </div>\n      )}\n\n      <div className="holdings-chart-foot">\n        <span>{chartDate ? `차트 최신일 ${chartDate.replace(/-/g, ".")}` : "저장된 확정 일봉을 사용합니다."}</span>\n        {analysisDate && (\n          <span className={analysisBehindChart ? "stale" : ""}>\n            분석 기준일 {analysisDate.replace(/-/g, ".")}\n            {analysisBehindChart ? " · 새로고침 필요" : ""}\n          </span>\n        )}\n      </div>\n    </section>\n  );\n}\n'
CSS_APPEND = '/* HOLD.1-G.4 — richer decision context without new strategy/risk thresholds */\n.holdings-decision-cell strong,\n.holdings-decision-cell small { display:block; }\n.holdings-decision-cell strong { color:var(--text-primary); font-weight:800; }\n.holdings-decision-cell small {\n  margin-top:3px;\n  color:var(--status-warning);\n  font-size:var(--font-badge);\n  font-weight:750;\n}\n.holdings-decision-summary {\n  margin:10px 0 0;\n  padding-top:9px;\n  border-top:1px solid var(--border-subtle);\n  color:var(--text-secondary);\n  font-size:var(--font-meta);\n  line-height:var(--line-body);\n}\n.holdings-plan-text.alert { color:var(--status-negative); font-weight:850; }\n.holdings-plan-text.target { color:var(--status-positive); font-weight:850; }\n.holdings-chart-plan-event {\n  display:flex;\n  align-items:baseline;\n  gap:8px;\n  margin-top:9px;\n  padding:7px 0 7px 10px;\n  border-left:2px solid var(--status-warning);\n  color:var(--text-secondary);\n  font-size:var(--font-meta);\n}\n.holdings-chart-plan-event span,\n.holdings-chart-plan-event small { color:var(--text-muted); }\n.holdings-chart-plan-event strong { color:var(--text-primary); }\n.holdings-chart-plan-event.stop_breached { border-left-color:var(--status-negative); }\n.holdings-chart-plan-event.target1_reached,\n.holdings-chart-plan-event.target2_reached { border-left-color:var(--status-positive); }\n'

API_IMPORT_OLD = 'from app.holdings.chart import HoldingsChartError, HoldingsChartService\n'
API_IMPORT_NEW = 'from app.holdings.chart import HoldingsChartError, HoldingsChartService\nfrom app.holdings.decision_context import HoldingDecisionContextService\n'
API_HELPER_OLD = 'def _chart_service() -> HoldingsChartService:\n    return HoldingsChartService(_market_store_path())\n\n\ndef _freshness_service() -> HoldingsMarketFreshnessService:\n'
API_HELPER_NEW = 'def _chart_service() -> HoldingsChartService:\n    return HoldingsChartService(_market_store_path())\n\n\ndef _decision_service(catalog: HoldingsCatalog) -> HoldingDecisionContextService:\n    return HoldingDecisionContextService(catalog)\n\n\ndef _freshness_service() -> HoldingsMarketFreshnessService:\n'
API_PAYLOAD_OLD = '        "positions": [_position_payload(catalog, item) for item in positions],\n        "current_analysis": _current_analysis_payload(catalog, stock.id),\n    }\n'
API_PAYLOAD_NEW = '        "positions": [_position_payload(catalog, item) for item in positions],\n        "current_analysis": _current_analysis_payload(catalog, stock.id),\n        "decision_context": _decision_service(catalog).build(stock.id),\n    }\n'

SERVICE_ANCHOR = 'export type HoldingStock = {\n'
SERVICE_TYPES = 'export type HoldingDecisionEntry = {\n  state: "READY" | "WATCH" | "NOT_READY" | "BLOCKED" | "CAUTION" | "NO_TRADE" | "UNKNOWN" | string;\n  label: string;\n  summary: string | null;\n  decision_reason: string | null;\n  missing: number | null;\n  total: number | null;\n  warnings: string[];\n};\n\nexport type HoldingStrategyContext = {\n  state: "INITIAL" | "UNCHANGED" | "CHANGED" | string;\n  current: string | null;\n  previous: string | null;\n  previous_market_date: string | null;\n};\n\nexport type HoldingPreviousPlanContext = {\n  state: "NO_PREVIOUS_PLAN" | "WITHIN_PLAN" | "STOP_BREACHED" | "TARGET1_REACHED" | "TARGET2_REACHED" | string;\n  label: string;\n  previous_market_date: string | null;\n  previous_stop_price: string | null;\n  previous_target1_price: string | null;\n  previous_target2_price: string | null;\n  current_close: string | null;\n};\n\nexport type HoldingDecisionContext = {\n  entry: HoldingDecisionEntry;\n  strategy: HoldingStrategyContext;\n  previous_plan: HoldingPreviousPlanContext;\n};\n\n'
SERVICE_FIELDS_OLD = '  positions: HoldingPosition[];\n  current_analysis: HoldingAnalysis | null;\n  latest_position_event?: HoldingPositionEvent | null;\n'
SERVICE_FIELDS_NEW = '  positions: HoldingPosition[];\n  current_analysis: HoldingAnalysis | null;\n  decision_context: HoldingDecisionContext | null;\n  latest_position_event?: HoldingPositionEvent | null;\n'

WORKSPACE_IMPORT_OLD = '  type HoldingAccount,\n  type HoldingPosition,\n'
WORKSPACE_IMPORT_NEW = '  type HoldingAccount,\n  type HoldingDecisionContext,\n  type HoldingPosition,\n'
WORKSPACE_RISK_ANCHOR = 'const riskLabel: Record<string, string> = {\n  READY: "계산 완료",\n  CAUTION: "주의 조건 있음",\n  HOLD: "계산 보류",\n  BLOCKED: "계산 제한",\n  UNAVAILABLE: "계산 불가",\n};\n'
WORKSPACE_HELPERS = 'const riskLabel: Record<string, string> = {\n  READY: "계산 완료",\n  CAUTION: "주의 조건 있음",\n  HOLD: "계산 보류",\n  BLOCKED: "계산 제한",\n  UNAVAILABLE: "계산 불가",\n};\n\n\nfunction strategyChangeText(context: HoldingDecisionContext | null | undefined) {\n  if (!context) return "-";\n  if (context.strategy.state === "INITIAL") return "첫 분석";\n  if (context.strategy.state === "UNCHANGED") return "유지";\n  const previous = context.strategy.previous\n    ? strategyLabel[context.strategy.previous] ?? context.strategy.previous\n    : "이전 전략 없음";\n  const current = context.strategy.current\n    ? strategyLabel[context.strategy.current] ?? context.strategy.current\n    : "현재 전략 없음";\n  return `${previous} → ${current}`;\n}\n\nfunction planStateClass(context: HoldingDecisionContext | null | undefined) {\n  const state = context?.previous_plan.state;\n  if (state === "STOP_BREACHED") return "alert";\n  if (state === "TARGET1_REACHED" || state === "TARGET2_REACHED") return "target";\n  return "";\n}\n\nfunction isPlanEvent(context: HoldingDecisionContext | null | undefined) {\n  return ["STOP_BREACHED", "TARGET1_REACHED", "TARGET2_REACHED"].includes(\n    context?.previous_plan.state ?? "",\n  );\n}\n\nfunction holdingManagementText(context: HoldingDecisionContext | null | undefined) {\n  switch (context?.previous_plan.state) {\n    case "STOP_BREACHED":\n      return "확인이 필요한 가격 구간";\n    case "TARGET1_REACHED":\n    case "TARGET2_REACHED":\n      return "목표 가격 도달 구간";\n    case "WITHIN_PLAN":\n      return "이전 계획 범위 내";\n    default:\n      return "비교할 이전 계획 없음";\n  }\n}\n'
WORKSPACE_LIST_OLD = '                      <td>{stock.current_analysis ? actionLabel[stock.current_analysis.action_state] ?? stock.current_analysis.action_state : "분석 필요"}</td>\n'
WORKSPACE_LIST_NEW = '                      <td className="holdings-decision-cell">\n                        <strong>\n                          {stock.current_analysis\n                            ? stock.decision_context?.entry.label\n                              ?? actionLabel[stock.current_analysis.action_state]\n                              ?? stock.current_analysis.action_state\n                            : "분석 필요"}\n                        </strong>\n                        {stock.decision_context && isPlanEvent(stock.decision_context) && (\n                          <small>{stock.decision_context.previous_plan.label}</small>\n                        )}\n                      </td>\n'
WORKSPACE_CHART_OLD = '              <HoldingsPriceChart\n                stockId={detail.stock_id}\n                analysis={selectedAnalysis}\n                refreshKey={chartRefreshKey}\n              />\n'
WORKSPACE_CHART_NEW = '              <HoldingsPriceChart\n                stockId={detail.stock_id}\n                analysis={selectedAnalysis}\n                refreshKey={chartRefreshKey}\n                decisionContext={detail.decision_context}\n              />\n'
WORKSPACE_ANALYSIS_OLD = '                    <dl className="holdings-key-values">\n                      <div><dt>현재 판단</dt><dd>{actionLabel[selectedAnalysis.action_state] ?? selectedAnalysis.action_state}</dd></div>\n                      <div><dt>전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>\n                      <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>\n                      <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>\n                    </dl>\n'
WORKSPACE_ANALYSIS_NEW = '                    <>\n                      <dl className="holdings-key-values">\n                        <div>\n                          <dt>진입 상태</dt>\n                          <dd>\n                            {detail.decision_context?.entry.label\n                              ?? actionLabel[selectedAnalysis.action_state]\n                              ?? selectedAnalysis.action_state}\n                          </dd>\n                        </div>\n                        <div><dt>현재 전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>\n                        <div><dt>전략 변화</dt><dd>{strategyChangeText(detail.decision_context)}</dd></div>\n                        <div>\n                          <dt>가격 계획</dt>\n                          <dd className={`holdings-plan-text ${planStateClass(detail.decision_context)}`}>\n                            {detail.decision_context?.previous_plan.label ?? "비교할 이전 계획 없음"}\n                          </dd>\n                        </div>\n                        {detail.is_held && (\n                          <div><dt>보유 관리</dt><dd>{holdingManagementText(detail.decision_context)}</dd></div>\n                        )}\n                        <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>\n                        <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>\n                      </dl>\n                      {detail.decision_context?.entry.summary && (\n                        <p className="holdings-decision-summary">{detail.decision_context.entry.summary}</p>\n                      )}\n                    </>\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        p for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_api(source: str) -> str:
    if "HoldingDecisionContextService" in source:
        fail("holdings.py already appears to contain G.4.")
    source = replace_once(source, API_IMPORT_OLD, API_IMPORT_NEW, "holdings.py import")
    source = replace_once(source, API_HELPER_OLD, API_HELPER_NEW, "holdings.py helper")
    source = replace_once(source, API_PAYLOAD_OLD, API_PAYLOAD_NEW, "holdings.py payload")
    return source


def patch_service(source: str) -> str:
    if "export type HoldingDecisionContext" in source:
        fail("holdingsApi.ts already appears to contain G.4.")
    source = replace_once(source, SERVICE_ANCHOR, SERVICE_TYPES + SERVICE_ANCHOR, "holdingsApi.ts types")
    source = replace_once(source, SERVICE_FIELDS_OLD, SERVICE_FIELDS_NEW, "holdingsApi.ts stock fields")
    return source


def patch_workspace(source: str) -> str:
    if "strategyChangeText" in source:
        fail("HoldingsWorkspace.tsx already appears to contain G.4.")
    source = replace_once(source, WORKSPACE_IMPORT_OLD, WORKSPACE_IMPORT_NEW, "workspace imports")
    source = replace_once(source, WORKSPACE_RISK_ANCHOR, WORKSPACE_HELPERS, "workspace helpers")
    source = replace_once(source, WORKSPACE_LIST_OLD, WORKSPACE_LIST_NEW, "workspace list decision")
    source = replace_once(source, WORKSPACE_CHART_OLD, WORKSPACE_CHART_NEW, "workspace chart props")
    source = replace_once(source, WORKSPACE_ANALYSIS_OLD, WORKSPACE_ANALYSIS_NEW, "workspace detail decision")
    return source


def patch_css(source: str) -> str:
    if "HOLD.1-G.4" in source:
        fail("holdings.css already appears to contain G.4.")
    return source.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-G.4 — 판단 상태 세분화 + 이전 분석 계획 추적")
    print("New decision thresholds: NO")
    print("Scanner/Strategy/Risk modification: NO")
    print("Market Store write: NO")
    print("KRX/KIS calls: NO")
    print("Theme support: LIGHT + DARK")

    required = [HOLDINGS_API, ANALYSIS, ANALYSIS_HISTORY, SCANNER, SERVICE, WORKSPACE, CHART, CSS, PACKAGE]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    if DECISION.exists() or DECISION_TEST.exists():
        fail("G.4 target file already exists; stop to avoid double apply.")

    api_before = HOLDINGS_API.read_text(encoding="utf-8-sig")
    workspace_before = WORKSPACE.read_text(encoding="utf-8-sig")
    chart_before = CHART.read_text(encoding="utf-8-sig")

    preflight = {
        "G.3 freshness": "prepare_latest: bool = Query(default=False)" in api_before,
        "G.3 chart refresh key": "refreshKey={chartRefreshKey}" in workspace_before,
        "G.3 chart readability": "holdings-chart-levels" in chart_before,
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("HOLD.1-G.3 is not in the expected state.")

    protected = {
        "analysis": sha256(ANALYSIS),
        "analysis_history": sha256(ANALYSIS_HISTORY),
        "scanner": sha256(SCANNER),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
        "market_store": tree_hash(BACKEND / "app" / "backtest" / "market_store.py"),
    }

    originals = {
        HOLDINGS_API: api_before,
        SERVICE: SERVICE.read_text(encoding="utf-8-sig"),
        WORKSPACE: workspace_before,
        CHART: chart_before,
        CSS: CSS.read_text(encoding="utf-8-sig"),
    }
    created: list[Path] = []

    try:
        HOLDINGS_API.write_text(patch_api(originals[HOLDINGS_API]), encoding="utf-8", newline="\n")
        SERVICE.write_text(patch_service(originals[SERVICE]), encoding="utf-8", newline="\n")
        WORKSPACE.write_text(patch_workspace(originals[WORKSPACE]), encoding="utf-8", newline="\n")
        CHART.write_text(CHART_CONTENT, encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(originals[CSS]), encoding="utf-8", newline="\n")

        DECISION.write_text(DECISION_CONTENT, encoding="utf-8", newline="\n")
        created.append(DECISION)
        DECISION_TEST.write_text(DECISION_TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(DECISION_TEST)

        print()
        print("=== HOLD.1-G.4 STATIC CONTRACT ===")
        api_now = HOLDINGS_API.read_text(encoding="utf-8")
        decision_now = DECISION.read_text(encoding="utf-8")
        service_now = SERVICE.read_text(encoding="utf-8")
        workspace_now = WORKSPACE.read_text(encoding="utf-8")
        chart_now = CHART.read_text(encoding="utf-8")
        css_now = CSS.read_text(encoding="utf-8")
        package_now = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "decision context API payload": '"decision_context": _decision_service(catalog).build(stock.id)' in api_now,
            "readiness variation preserved": all(state in decision_now for state in ("READY", "WATCH", "NOT_READY", "BLOCKED", "CAUTION")),
            "previous day current revision only": "r.id=d.current_revision_id" in decision_now and "ORDER BY d.market_date DESC" in decision_now and "LIMIT 2" in decision_now,
            "stop breach": "STOP_BREACHED" in decision_now and "current_close <= previous_stop" in decision_now,
            "target1 reached": "TARGET1_REACHED" in decision_now and "current_close >= previous_target1" in decision_now,
            "target2 priority": decision_now.index("current_close >= previous_target2") < decision_now.index("current_close >= previous_target1"),
            "strategy change": all(state in decision_now for state in ("INITIAL", "UNCHANGED", "CHANGED")),
            "no provider call": all(token not in decision_now for token in ("KrxProvider", "StockScannerService", "requests.", "httpx.")),
            "decision service read only": all(token not in decision_now for token in ("INSERT ", "UPDATE ", "DELETE ")),
            "frontend typed context": "export type HoldingDecisionContext" in service_now,
            "list uses rich entry state": "stock.decision_context?.entry.label" in workspace_now,
            "detail separates entry strategy plan": all(label in workspace_now for label in ("진입 상태", "현재 전략", "전략 변화", "가격 계획")),
            "held management descriptive": "확인이 필요한 가격 구간" in workspace_now,
            "no sell instruction": "매도" not in decision_now and "손절하세요" not in decision_now,
            "chart event summary": "holdings-chart-plan-event" in chart_now,
            "light dark tokens": "var(--text-primary)" in css_now and "var(--status-negative)" in css_now,
            "no theme fork": 'html[data-theme=' not in css_now and ":root" not in css_now,
            "no paid chart dependency": all(name not in package_now for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            fail(f"Project venv python not found: {python}")

        run(
            [
                str(python), "-m", "pytest",
                "backend/tests/test_holdings_decision_context_hold1g4.py",
                "backend/tests/test_holdings_api_hold1f.py",
                "backend/tests/test_holdings_analysis_history_hold1e.py",
                "backend/tests/test_holdings_freshness_hold1g3.py",
                "backend/tests/test_holdings_chart_hold1g.py",
                "-q",
            ],
            ROOT,
            "Focused backend regression",
        )

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        protected_after = {
            "analysis": sha256(ANALYSIS),
            "analysis_history": sha256(ANALYSIS_HISTORY),
            "scanner": sha256(SCANNER),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
            "market_store": tree_hash(BACKEND / "app" / "backtest" / "market_store.py"),
        }
        if protected_after != protected:
            fail("Protected Analysis/Scanner/Strategy/Risk/KIS/Market Store source changed.")

        print()
        print("HOLD.1-G.4 IMPLEMENTATION READY")
        print("Added:")
        print(" - backend/app/holdings/decision_context.py")
        print(" - backend/tests/test_holdings_decision_context_hold1g4.py")
        print("Modified:")
        print(" - backend/app/api/holdings.py")
        print(" - frontend/src/services/holdingsApi.ts")
        print(" - frontend/src/components/HoldingsWorkspace.tsx")
        print(" - frontend/src/components/HoldingsPriceChart.tsx")
        print(" - frontend/src/holdings.css")
        print("Entry states: READY/WATCH/NOT_READY/BLOCKED/CAUTION")
        print("Previous-day plan comparison: PASS")
        print("Same-day revision excluded: PASS")
        print("Strategy INITIAL/UNCHANGED/CHANGED: PASS")
        print("New strategy/risk thresholds: 0")
        print("Market Store write: 0")
        print("KRX/KIS calls: 0")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" - Check the three existing list judgment labels.")
        print(" - Check detail rows: 진입 상태 / 현재 전략 / 전략 변화 / 가격 계획.")
        print(" - Confirm any stop/target event is descriptive only.")
        print(" - Capture one Dark screenshot.")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — HOLD.1-G.4 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
