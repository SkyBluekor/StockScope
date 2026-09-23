from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

HOLDINGS_API = BACKEND / "app" / "api" / "holdings.py"
FRESHNESS = BACKEND / "app" / "holdings" / "freshness.py"
FRESHNESS_TEST = BACKEND / "tests" / "test_holdings_freshness_hold1g3.py"
CHART_TEST = BACKEND / "tests" / "test_holdings_chart_hold1g.py"
API_TEST = BACKEND / "tests" / "test_holdings_api_hold1f.py"
HISTORY_TEST = BACKEND / "tests" / "test_holdings_analysis_history_hold1e.py"

PRICE_CHART = FRONTEND / "src" / "components" / "HoldingsPriceChart.tsx"
WORKSPACE = FRONTEND / "src" / "components" / "HoldingsWorkspace.tsx"
HOLDINGS_SERVICE = FRONTEND / "src" / "services" / "holdingsApi.ts"
HOLDINGS_CSS = FRONTEND / "src" / "holdings.css"
PACKAGE_JSON = FRONTEND / "package.json"

FRESHNESS_CONTENT = 'from __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom pathlib import Path\nfrom typing import Any, Callable\n\nfrom app.backtest.market_store import HistoricalMarketStore\nfrom app.backtest.scanner import StockScannerService\nfrom app.core.config import PROJECT_ROOT\nfrom app.market.providers import KrxProvider\n\n\nDEFAULT_MARKET_STORE_DB = (\n    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"\n)\n\n\nclass HoldingsMarketFreshnessError(RuntimeError):\n    def __init__(self, code: str, message: str) -> None:\n        super().__init__(message)\n        self.code = code\n        self.message = message\n\n\n@dataclass(frozen=True, slots=True)\nclass HoldingsMarketFreshnessResult:\n    status: str\n    market: str\n    requested_date: str | None\n    latest_confirmed_date: str | None\n    resolved_as_of_date: str\n    known_data_date: str | None\n    market_data_updated: bool\n    date_changed: bool\n    network_requests: int\n    message: str\n\n    def to_dict(self) -> dict[str, Any]:\n        return {\n            "status": self.status,\n            "market": self.market,\n            "requested_date": self.requested_date,\n            "latest_confirmed_date": self.latest_confirmed_date,\n            "resolved_as_of_date": self.resolved_as_of_date,\n            "known_data_date": self.known_data_date,\n            "market_data_updated": self.market_data_updated,\n            "date_changed": self.date_changed,\n            "network_requests": self.network_requests,\n            "message": self.message,\n        }\n\n\nclass HoldingsMarketFreshnessService:\n    """Prepare the selected market\'s latest confirmed EOD data without running Scanner ranking."""\n\n    def __init__(\n        self,\n        *,\n        krx_api_key: str | None,\n        market_store_db: Path | None = None,\n        scanner_factory: Callable[[Any, HistoricalMarketStore], Any] | None = None,\n    ) -> None:\n        self.krx_api_key = krx_api_key\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n        self.scanner_factory = scanner_factory\n\n    async def prepare(\n        self,\n        *,\n        market: str,\n        known_data_date: str | None,\n    ) -> HoldingsMarketFreshnessResult:\n        clean_market = (market or "").strip().upper()\n        if clean_market not in {"KOSPI", "KOSDAQ"}:\n            raise HoldingsMarketFreshnessError(\n                "HOLD_MARKET_FRESHNESS_MARKET_INVALID",\n                "최신 시세 확인 대상 시장이 올바르지 않습니다.",\n            )\n\n        store = HistoricalMarketStore(self.market_store_db)\n        provider = KrxProvider(self.krx_api_key)\n        scanner = (\n            self.scanner_factory(provider, store)\n            if self.scanner_factory is not None\n            else StockScannerService(provider, market_store=store)\n        )\n\n        payload = await scanner.prepare_latest_confirmed_data(\n            market_scope=clean_market,\n            known_data_date=known_data_date,\n        )\n        status = str(payload.get("status") or "")\n        resolved = str(payload.get("resolved_as_of_date") or "").strip()\n        if status not in {"READY", "UPDATED"} or not resolved:\n            raise HoldingsMarketFreshnessError(\n                "HOLD_MARKET_FRESHNESS_UPDATE_FAILED",\n                str(payload.get("message") or "최신 확정 시세를 확인하지 못했습니다."),\n            )\n\n        diagnostics = payload.get("diagnostics") or {}\n        return HoldingsMarketFreshnessResult(\n            status=status,\n            market=clean_market,\n            requested_date=payload.get("requested_date"),\n            latest_confirmed_date=payload.get("latest_confirmed_date"),\n            resolved_as_of_date=resolved,\n            known_data_date=payload.get("known_data_date"),\n            market_data_updated=bool(payload.get("market_data_updated")),\n            date_changed=bool(payload.get("date_changed")),\n            network_requests=int(diagnostics.get("network_requests") or 0),\n            message=str(payload.get("message") or f"{resolved} 확정 일봉 기준으로 분석할 수 있습니다."),\n        )\n'
FRESHNESS_TEST_CONTENT = 'from __future__ import annotations\n\nimport asyncio\nimport sys\nfrom pathlib import Path\n\nimport pytest\nfrom fastapi import FastAPI\nfrom fastapi.testclient import TestClient\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\nfrom app.api import holdings as holdings_api\nfrom app.holdings.freshness import (\n    HoldingsMarketFreshnessError,\n    HoldingsMarketFreshnessResult,\n    HoldingsMarketFreshnessService,\n)\n\n\nclass _FakeScanner:\n    def __init__(self, payload: dict):\n        self.payload = payload\n        self.calls: list[dict] = []\n\n    async def prepare_latest_confirmed_data(self, **kwargs):\n        self.calls.append(kwargs)\n        return dict(self.payload)\n\n\ndef test_freshness_prepares_only_selected_market_and_never_runs_scanner(tmp_path: Path) -> None:\n    holder: dict[str, object] = {}\n    fake = _FakeScanner(\n        {\n            "status": "UPDATED",\n            "requested_date": "2026-09-22",\n            "latest_confirmed_date": "2026-09-22",\n            "resolved_as_of_date": "2026-09-22",\n            "known_data_date": "2026-09-21",\n            "market_data_updated": True,\n            "date_changed": True,\n            "diagnostics": {"network_requests": 2},\n            "message": "새로운 확정 시세를 확인했습니다.",\n        }\n    )\n\n    def factory(provider, store):\n        holder["store_path"] = store.db_path\n        return fake\n\n    service = HoldingsMarketFreshnessService(\n        krx_api_key="test",\n        market_store_db=tmp_path / "market.db",\n        scanner_factory=factory,\n    )\n    result = asyncio.run(service.prepare(market="KOSPI", known_data_date="2026-09-21"))\n\n    assert result.status == "UPDATED"\n    assert result.resolved_as_of_date == "2026-09-22"\n    assert result.network_requests == 2\n    assert fake.calls == [{"market_scope": "KOSPI", "known_data_date": "2026-09-21"}]\n    assert holder["store_path"] == tmp_path / "market.db"\n\n\ndef test_freshness_failure_does_not_accept_older_fallback(tmp_path: Path) -> None:\n    fake = _FakeScanner(\n        {\n            "status": "UPDATE_FAILED",\n            "resolved_as_of_date": "2026-09-21",\n            "known_data_date": "2026-09-21",\n            "message": "새로운 확정 시세를 가져오지 못했습니다. 현재 분석은 유지합니다.",\n            "diagnostics": {"network_requests": 1},\n        }\n    )\n    service = HoldingsMarketFreshnessService(\n        krx_api_key="test",\n        market_store_db=tmp_path / "market.db",\n        scanner_factory=lambda provider, store: fake,\n    )\n    with pytest.raises(HoldingsMarketFreshnessError) as exc:\n        asyncio.run(service.prepare(market="KOSPI", known_data_date="2026-09-21"))\n\n    assert exc.value.code == "HOLD_MARKET_FRESHNESS_UPDATE_FAILED"\n\n\ndef test_refresh_endpoint_uses_freshness_date_before_analysis(tmp_path: Path, monkeypatch) -> None:\n    holdings_db = tmp_path / "holdings.db"\n    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))\n\n    app = FastAPI()\n    app.include_router(holdings_api.router, prefix="/api")\n    client = TestClient(app)\n\n    watched = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    )\n    assert watched.status_code == 200, watched.text\n    stock_id = watched.json()["stock"]["stock_id"]\n\n    freshness_calls: list[dict] = []\n    analysis_calls: list[dict] = []\n\n    class FakeFreshnessService:\n        async def prepare(self, **kwargs):\n            freshness_calls.append(kwargs)\n            return HoldingsMarketFreshnessResult(\n                status="UPDATED",\n                market="KOSPI",\n                requested_date="2026-09-22",\n                latest_confirmed_date="2026-09-22",\n                resolved_as_of_date="2026-09-22",\n                known_data_date="2026-09-21",\n                market_data_updated=True,\n                date_changed=True,\n                network_requests=2,\n                message="새로운 확정 시세를 확인했습니다.",\n            )\n\n    class FakeHistoryService:\n        def analyze_and_record(self, **kwargs):\n            analysis_calls.append(kwargs)\n            return object()\n\n    monkeypatch.setattr(holdings_api, "_freshness_service", lambda: FakeFreshnessService())\n    monkeypatch.setattr(holdings_api, "_history_service", lambda catalog: FakeHistoryService())\n    monkeypatch.setattr(\n        holdings_api,\n        "_current_analysis_payload",\n        lambda catalog, sid: {"market_date": "2026-09-21"},\n    )\n    monkeypatch.setattr(\n        holdings_api,\n        "_stored_analysis_payload",\n        lambda catalog, stored: {\n            "market_date": "2026-09-22",\n            "revision_id": "revision-1",\n            "revision_no": 1,\n            "created_revision": True,\n            "promoted_current": True,\n        },\n    )\n\n    response = client.post(f"/api/holdings/stocks/{stock_id}/analysis/refresh")\n    assert response.status_code == 200, response.text\n    body = response.json()\n    assert freshness_calls == [{"market": "KOSPI", "known_data_date": "2026-09-21"}]\n    assert analysis_calls == [\n        {"monitored_stock_id": stock_id, "market_date": "2026-09-22"}\n    ]\n    assert body["market_date"] == "2026-09-22"\n    assert body["previous_analysis_date"] == "2026-09-21"\n    assert body["data_freshness"]["status"] == "UPDATED"\n\n\ndef test_freshness_source_never_runs_market_wide_scanner() -> None:\n    source = Path("backend/app/holdings/freshness.py").read_text(encoding="utf-8")\n    assert "prepare_latest_confirmed_data" in source\n    assert ".run(" not in source\n'
PRICE_CHART_CONTENT = 'import { useEffect, useMemo, useState, type PointerEvent } from "react";\nimport {\n  getHoldingChart,\n  type HoldingAnalysis,\n  type HoldingChartBar,\n  type HoldingChartRange,\n  type HoldingChartResponse,\n} from "../services/holdingsApi";\n\nconst RANGE_OPTIONS: Array<{ key: HoldingChartRange; label: string }> = [\n  { key: "1m", label: "1개월" },\n  { key: "3m", label: "3개월" },\n  { key: "6m", label: "6개월" },\n  { key: "1y", label: "1년" },\n];\n\nconst W = 920;\nconst H = 292;\nconst LEFT = 58;\nconst RIGHT = 74;\nconst TOP = 18;\nconst PRICE_BOTTOM = 210;\nconst VOLUME_TOP = 229;\nconst VOLUME_BOTTOM = 272;\n\nfunction number(value: string | null | undefined) {\n  if (value == null || value === "") return null;\n  const parsed = Number(value);\n  return Number.isFinite(parsed) ? parsed : null;\n}\n\nfunction formatPrice(value: number) {\n  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);\n}\n\nfunction formatVolume(value: number) {\n  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(value);\n}\n\nfunction shortDate(value: string) {\n  return value.length >= 10 ? `${value.slice(5, 7)}.${value.slice(8, 10)}` : value;\n}\n\nfunction mergeBars(history: HoldingChartBar[], liveBar: HoldingChartBar | null) {\n  if (!liveBar) return history;\n  if (history.length === 0) return [liveBar];\n  const last = history[history.length - 1];\n  if (last.date === liveBar.date) return [...history.slice(0, -1), liveBar];\n  return [...history, liveBar];\n}\n\ntype Props = {\n  stockId: string;\n  analysis: HoldingAnalysis | null;\n  liveBar?: HoldingChartBar | null;\n  refreshKey?: number;\n};\n\nexport default function HoldingsPriceChart({\n  stockId,\n  analysis,\n  liveBar = null,\n  refreshKey = 0,\n}: Props) {\n  const [range, setRange] = useState<HoldingChartRange>("1m");\n  const [chart, setChart] = useState<HoldingChartResponse | null>(null);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState<string | null>(null);\n  const [hoverIndex, setHoverIndex] = useState<number | null>(null);\n\n  useEffect(() => {\n    let cancelled = false;\n    setLoading(true);\n    setError(null);\n    setHoverIndex(null);\n    void getHoldingChart(stockId, range)\n      .then((result) => {\n        if (!cancelled) setChart(result);\n      })\n      .catch((loadError) => {\n        if (cancelled) return;\n        setChart(null);\n        setError(loadError instanceof Error ? loadError.message : "차트 데이터를 불러오지 못했습니다.");\n      })\n      .finally(() => {\n        if (!cancelled) setLoading(false);\n      });\n    return () => {\n      cancelled = true;\n    };\n  }, [stockId, range, refreshKey]);\n\n  const bars = useMemo(() => mergeBars(chart?.bars ?? [], liveBar), [chart, liveBar]);\n\n  const model = useMemo(() => {\n    const numeric = bars\n      .map((bar) => ({\n        ...bar,\n        o: number(bar.open),\n        h: number(bar.high),\n        l: number(bar.low),\n        c: number(bar.close),\n        v: number(bar.volume),\n      }))\n      .filter((bar) => bar.o != null && bar.h != null && bar.l != null && bar.c != null && bar.v != null);\n\n    if (numeric.length === 0) return null;\n\n    const levels = [\n      { key: "reference", label: "기준가", value: number(analysis?.reference_price) },\n      { key: "stop", label: "손절", value: number(analysis?.stop_price) },\n      { key: "target1", label: "1차 목표", value: number(analysis?.target1_price) },\n      { key: "target2", label: "2차 목표", value: number(analysis?.target2_price) },\n    ].filter((item): item is { key: string; label: string; value: number } => item.value != null);\n\n    const lowest = Math.min(...numeric.map((bar) => bar.l!));\n    const highest = Math.max(...numeric.map((bar) => bar.h!));\n    const visibleRange = Math.max(highest - lowest, highest * 0.015, 1);\n    const minPrice = lowest - visibleRange * 0.08;\n    const maxPrice = highest + visibleRange * 0.08;\n    const priceRange = maxPrice - minPrice || 1;\n    const maxVolume = Math.max(...numeric.map((bar) => bar.v!), 1);\n    const plotWidth = W - LEFT - RIGHT;\n    const step = plotWidth / numeric.length;\n    const candleWidth = Math.max(1.2, Math.min(8.5, step * 0.56));\n\n    const yPrice = (value: number) => TOP + ((maxPrice - value) / priceRange) * (PRICE_BOTTOM - TOP);\n    const xAt = (index: number) => LEFT + step * (index + 0.5);\n    const volumeY = (value: number) => VOLUME_BOTTOM - (value / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);\n\n    const tickIndexes = Array.from(new Set([\n      0,\n      Math.floor((numeric.length - 1) * 0.25),\n      Math.floor((numeric.length - 1) * 0.5),\n      Math.floor((numeric.length - 1) * 0.75),\n      numeric.length - 1,\n    ])).sort((a, b) => a - b);\n\n    const yTicks = Array.from({ length: 5 }, (_, index) => {\n      const ratio = index / 4;\n      const value = maxPrice - (maxPrice - minPrice) * ratio;\n      return { value, y: TOP + (PRICE_BOTTOM - TOP) * ratio };\n    });\n\n    const analysisIndex = analysis\n      ? numeric.findIndex((bar) => bar.date === analysis.market_date)\n      : -1;\n\n    const plottedLevels = levels.map((level) => ({\n      ...level,\n      position: level.value > maxPrice ? "above" : level.value < minPrice ? "below" : "inside",\n    }));\n\n    return {\n      numeric,\n      levels: plottedLevels,\n      xAt,\n      yPrice,\n      volumeY,\n      candleWidth,\n      tickIndexes,\n      yTicks,\n      analysisIndex,\n      plotWidth,\n      step,\n    };\n  }, [bars, analysis]);\n\n  function handlePointerMove(event: PointerEvent<SVGRectElement>) {\n    if (!model) return;\n    const rect = event.currentTarget.getBoundingClientRect();\n    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));\n    const chartX = ratio * W;\n    const raw = Math.floor((chartX - LEFT) / model.step);\n    const index = Math.max(0, Math.min(model.numeric.length - 1, raw));\n    setHoverIndex(index);\n  }\n\n  const hovered = model && hoverIndex != null ? model.numeric[hoverIndex] : null;\n  const chartDate = chart?.to_date ?? null;\n  const analysisDate = analysis?.market_date ?? null;\n  const analysisBehindChart = Boolean(chartDate && analysisDate && analysisDate < chartDate);\n\n  return (\n    <section className="holdings-chart-panel">\n      <div className="holdings-chart-head">\n        <div>\n          <h3>확정 일봉</h3>\n          <span>{chartDate ? `${chartDate.replace(/-/g, ".")}까지` : "저장된 확정 데이터 기준"}</span>\n        </div>\n        <div className="holdings-chart-ranges" aria-label="차트 기간">\n          {RANGE_OPTIONS.map((option) => (\n            <button\n              key={option.key}\n              type="button"\n              className={range === option.key ? "active" : ""}\n              onClick={() => setRange(option.key)}\n            >\n              {option.label}\n            </button>\n          ))}\n        </div>\n      </div>\n\n      {model && (\n        <div className="holdings-chart-levels" aria-label="분석 가격 기준">\n          {model.levels.map((level) => (\n            <span key={level.key} className={`holdings-chart-level ${level.key}`}>\n              <i aria-hidden="true" />\n              <b>{level.position === "above" ? "↑ " : level.position === "below" ? "↓ " : ""}{level.label}</b>\n              <strong>{formatPrice(level.value)}</strong>\n            </span>\n          ))}\n        </div>\n      )}\n\n      {loading && !chart ? (\n        <div className="holdings-chart-state">확정 일봉을 불러오는 중입니다.</div>\n      ) : error ? (\n        <div className="holdings-chart-state error">{error}</div>\n      ) : !model ? (\n        <div className="holdings-chart-state">표시할 확정 일봉이 없습니다.</div>\n      ) : (\n        <div className="holdings-chart-canvas">\n          <svg\n            viewBox={`0 0 ${W} ${H}`}\n            role="img"\n            aria-label={`${range} 확정 일봉 캔들 차트`}\n            onPointerLeave={() => setHoverIndex(null)}\n          >\n            <g className="holdings-chart-grid">\n              {model.yTicks.map((tick) => (\n                <g key={tick.y}>\n                  <line x1={LEFT} x2={W - RIGHT} y1={tick.y} y2={tick.y} />\n                  <text x={W - RIGHT + 8} y={tick.y + 4}>{formatPrice(tick.value)}</text>\n                </g>\n              ))}\n              <line x1={LEFT} x2={W - RIGHT} y1={VOLUME_TOP - 8} y2={VOLUME_TOP - 8} />\n            </g>\n\n            {model.levels\n              .filter((level) => level.position === "inside")\n              .map((level) => {\n                const y = model.yPrice(level.value);\n                return (\n                  <line\n                    key={level.key}\n                    className={`holdings-level-line ${level.key}`}\n                    x1={LEFT}\n                    x2={W - RIGHT}\n                    y1={y}\n                    y2={y}\n                  />\n                );\n              })}\n\n            {model.analysisIndex >= 0 && (\n              <line\n                className="holdings-analysis-marker"\n                x1={model.xAt(model.analysisIndex)}\n                x2={model.xAt(model.analysisIndex)}\n                y1={TOP}\n                y2={VOLUME_BOTTOM}\n              />\n            )}\n\n            <g className="holdings-candles">\n              {model.numeric.map((bar, index) => {\n                const x = model.xAt(index);\n                const openY = model.yPrice(bar.o!);\n                const closeY = model.yPrice(bar.c!);\n                const highY = model.yPrice(bar.h!);\n                const lowY = model.yPrice(bar.l!);\n                const bodyY = Math.min(openY, closeY);\n                const bodyHeight = Math.max(1.2, Math.abs(closeY - openY));\n                const direction = bar.c! > bar.o! ? "up" : bar.c! < bar.o! ? "down" : "flat";\n                const volumeY = model.volumeY(bar.v!);\n                return (\n                  <g key={`${bar.date}-${index}`} className={`holdings-candle ${direction}`}>\n                    <line x1={x} x2={x} y1={highY} y2={lowY} />\n                    <rect\n                      x={x - model.candleWidth / 2}\n                      y={bodyY}\n                      width={model.candleWidth}\n                      height={bodyHeight}\n                    />\n                    <rect\n                      className="volume"\n                      x={x - model.candleWidth / 2}\n                      y={volumeY}\n                      width={model.candleWidth}\n                      height={Math.max(1, VOLUME_BOTTOM - volumeY)}\n                    />\n                  </g>\n                );\n              })}\n            </g>\n\n            <g className="holdings-chart-dates">\n              {model.tickIndexes.map((index) => (\n                <text key={index} x={model.xAt(index)} y={H - 5}>{shortDate(model.numeric[index].date)}</text>\n              ))}\n            </g>\n\n            {hoverIndex != null && (\n              <line\n                className="holdings-chart-hover-line"\n                x1={model.xAt(hoverIndex)}\n                x2={model.xAt(hoverIndex)}\n                y1={TOP}\n                y2={VOLUME_BOTTOM}\n              />\n            )}\n\n            <rect\n              className="holdings-chart-hit"\n              x={LEFT}\n              y={TOP}\n              width={model.plotWidth}\n              height={VOLUME_BOTTOM - TOP}\n              onPointerMove={handlePointerMove}\n            />\n          </svg>\n\n          {hovered && (\n            <div className="holdings-chart-tooltip">\n              <strong>{hovered.date.replace(/-/g, ".")}</strong>\n              <span>시가 <b>{formatPrice(hovered.o!)}</b></span>\n              <span>고가 <b>{formatPrice(hovered.h!)}</b></span>\n              <span>저가 <b>{formatPrice(hovered.l!)}</b></span>\n              <span>종가 <b>{formatPrice(hovered.c!)}</b></span>\n              <span>거래량 <b>{formatVolume(hovered.v!)}</b></span>\n            </div>\n          )}\n        </div>\n      )}\n\n      <div className="holdings-chart-foot">\n        <span>{chartDate ? `차트 최신일 ${chartDate.replace(/-/g, ".")}` : "저장된 확정 일봉을 사용합니다."}</span>\n        {analysisDate && (\n          <span className={analysisBehindChart ? "stale" : ""}>\n            분석 기준일 {analysisDate.replace(/-/g, ".")}\n            {analysisBehindChart ? " · 새로고침 필요" : ""}\n          </span>\n        )}\n      </div>\n    </section>\n  );\n}\n'
CSS_TAIL = '/* HOLD.1-G.1/G.2/G.3 — list removal + readable confirmed EOD chart */\n.holdings-text-action,\n.holdings-remove-button,\n.holdings-remove-confirm {\n  font: inherit;\n  font-weight: 800;\n}\n.holdings-text-action {\n  border: 0;\n  background: transparent;\n  color: var(--accent-primary);\n  padding: 8px 4px;\n}\n.holdings-remove-button {\n  border: 1px solid var(--border-default);\n  background: transparent;\n  color: var(--text-secondary);\n  padding: 9px 11px;\n}\n.holdings-remove-button:hover {\n  border-color: var(--status-negative);\n  color: var(--status-negative);\n  background: var(--status-negative-bg);\n}\n.holdings-remove-confirm {\n  border: 1px solid var(--status-negative);\n  background: var(--status-negative-bg);\n  color: var(--status-negative);\n  padding: 9px 13px;\n}\n.holdings-remove-copy {\n  padding: 14px 0;\n  color: var(--text-secondary);\n  font-size: var(--font-body-small);\n  line-height: var(--line-body);\n}\n.holdings-remove-dialog { width: min(500px, 100%); }\n\n.holdings-chart-panel {\n  margin-top: 18px;\n  padding: 16px 0 10px;\n  border-top: 1px solid var(--border-default);\n  border-bottom: 1px solid var(--border-default);\n}\n.holdings-chart-head,\n.holdings-chart-foot {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  gap: 16px;\n}\n.holdings-chart-head h3 {\n  margin: 0;\n  color: var(--text-primary);\n  font-size: var(--font-card-title);\n}\n.holdings-chart-head span,\n.holdings-chart-foot {\n  color: var(--text-muted);\n  font-size: var(--font-meta);\n}\n.holdings-chart-ranges {\n  display: flex;\n  border-bottom: 1px solid var(--border-default);\n}\n.holdings-chart-ranges button {\n  border: 0;\n  border-bottom: 2px solid transparent;\n  background: transparent;\n  color: var(--text-secondary);\n  padding: 6px 9px;\n  font: inherit;\n  font-size: var(--font-meta);\n  font-weight: 800;\n}\n.holdings-chart-ranges button.active {\n  border-bottom-color: var(--accent-primary);\n  color: var(--text-primary);\n}\n\n.holdings-chart-levels {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 7px 16px;\n  margin-top: 10px;\n  padding: 8px 0;\n  border-top: 1px solid var(--border-subtle);\n  border-bottom: 1px solid var(--border-subtle);\n}\n.holdings-chart-level {\n  display: inline-flex;\n  align-items: center;\n  gap: 6px;\n  min-width: 0;\n  color: var(--text-secondary);\n  font-size: var(--font-meta);\n}\n.holdings-chart-level i {\n  display: inline-block;\n  width: 18px;\n  height: 0;\n  border-top: 2px dashed currentColor;\n}\n.holdings-chart-level b { font-weight: 800; }\n.holdings-chart-level strong {\n  color: var(--text-primary);\n  font-weight: 800;\n}\n.holdings-chart-level.reference { color: var(--status-info); }\n.holdings-chart-level.stop { color: var(--status-negative); }\n.holdings-chart-level.target1,\n.holdings-chart-level.target2 { color: var(--status-positive); }\n\n.holdings-chart-canvas {\n  position: relative;\n  margin-top: 8px;\n  min-height: 250px;\n}\n.holdings-chart-canvas svg {\n  display: block;\n  width: 100%;\n  height: auto;\n  min-height: 250px;\n  overflow: visible;\n}\n.holdings-chart-grid line {\n  stroke: var(--border-subtle);\n  stroke-width: 1;\n  vector-effect: non-scaling-stroke;\n}\n.holdings-chart-grid text,\n.holdings-chart-dates text {\n  fill: var(--text-muted);\n  font-size: 11px;\n}\n.holdings-chart-dates text { text-anchor: middle; }\n\n.holdings-candle line {\n  stroke-width: 1.25;\n  vector-effect: non-scaling-stroke;\n}\n.holdings-candle rect { stroke-width: 0; }\n.holdings-candle.up line,\n.holdings-candle.up rect {\n  stroke: var(--status-positive);\n  fill: var(--status-positive);\n}\n.holdings-candle.down line,\n.holdings-candle.down rect {\n  stroke: var(--status-negative);\n  fill: var(--status-negative);\n}\n.holdings-candle.flat line,\n.holdings-candle.flat rect {\n  stroke: var(--text-muted);\n  fill: var(--text-muted);\n}\n.holdings-candle .volume { opacity: .28; }\n\n.holdings-level-line {\n  stroke-width: 1;\n  stroke-dasharray: 5 4;\n  vector-effect: non-scaling-stroke;\n}\n.holdings-level-line.reference { stroke: var(--status-info); }\n.holdings-level-line.stop { stroke: var(--status-negative); }\n.holdings-level-line.target1,\n.holdings-level-line.target2 { stroke: var(--status-positive); }\n\n.holdings-analysis-marker {\n  stroke: var(--accent-primary);\n  stroke-width: 1;\n  stroke-dasharray: 3 5;\n  opacity: .72;\n  vector-effect: non-scaling-stroke;\n}\n.holdings-chart-hover-line {\n  stroke: var(--text-muted);\n  stroke-width: 1;\n  stroke-dasharray: 2 3;\n  opacity: .55;\n  pointer-events: none;\n  vector-effect: non-scaling-stroke;\n}\n.holdings-chart-hit {\n  fill: transparent;\n  cursor: crosshair;\n}\n.holdings-chart-tooltip {\n  position: absolute;\n  right: 12px;\n  top: 10px;\n  display: grid;\n  grid-template-columns: auto auto;\n  gap: 3px 12px;\n  min-width: 150px;\n  padding: 9px 10px;\n  border: 1px solid var(--border-strong);\n  background: var(--bg-surface-raised);\n  color: var(--text-secondary);\n  font-size: 11px;\n  box-shadow: var(--shadow);\n  pointer-events: none;\n}\n.holdings-chart-tooltip > strong {\n  grid-column: 1 / -1;\n  color: var(--text-primary);\n  margin-bottom: 2px;\n}\n.holdings-chart-tooltip span { display: contents; }\n.holdings-chart-tooltip b {\n  color: var(--text-primary);\n  text-align: right;\n}\n.holdings-chart-state {\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  min-height: 250px;\n  color: var(--text-secondary);\n  font-size: var(--font-body-small);\n}\n.holdings-chart-state.error { color: var(--status-negative); }\n.holdings-chart-foot {\n  margin-top: 5px;\n  padding-top: 8px;\n  border-top: 1px solid var(--border-subtle);\n}\n.holdings-chart-foot .stale {\n  color: var(--status-warning);\n  font-weight: 800;\n}\n\n@media (max-width: 700px) {\n  .holdings-chart-head,\n  .holdings-chart-foot {\n    align-items: flex-start;\n    flex-direction: column;\n  }\n  .holdings-chart-ranges {\n    width: 100%;\n    overflow-x: auto;\n  }\n  .holdings-chart-levels { gap: 7px 12px; }\n  .holdings-chart-canvas { overflow-x: auto; }\n  .holdings-chart-canvas svg { min-width: 720px; }\n  .holdings-chart-tooltip {\n    position: sticky;\n    left: 10px;\n    right: auto;\n    width: 160px;\n  }\n}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


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


def patch_holdings_api(source: str) -> str:
    if "HoldingsMarketFreshnessService" in source:
        fail("backend/app/api/holdings.py already appears to contain G.3 freshness changes.")

    import_anchor = 'from pydantic import BaseModel, Field\n'
    if source.count(import_anchor) != 1:
        fail("holdings.py pydantic import anchor changed.")
    source = source.replace(
        import_anchor,
        import_anchor + '\nfrom app.core.config import get_settings\n',
        1,
    )

    chart_import = 'from app.holdings.chart import HoldingsChartError, HoldingsChartService\n'
    if source.count(chart_import) != 1:
        fail("holdings.py chart import anchor changed.")
    source = source.replace(
        chart_import,
        chart_import
        + 'from app.holdings.freshness import (\n'
        + '    HoldingsMarketFreshnessError,\n'
        + '    HoldingsMarketFreshnessService,\n'
        + ')\n',
        1,
    )

    helper_anchor = '''def _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:
    return HoldingAnalysisHistoryService(catalog)


def _chart_service() -> HoldingsChartService:
    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
    return HoldingsChartService(Path(raw) if raw else None)


def _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:
'''
    helper_replacement = '''def _market_store_path() -> Path | None:
    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")
    return Path(raw) if raw else None


def _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:
    return HoldingAnalysisHistoryService(
        catalog,
        market_store_db=_market_store_path(),
    )


def _chart_service() -> HoldingsChartService:
    return HoldingsChartService(_market_store_path())


def _freshness_service() -> HoldingsMarketFreshnessService:
    settings = get_settings()
    return HoldingsMarketFreshnessService(
        krx_api_key=settings.krx_api_key,
        market_store_db=_market_store_path(),
    )


def _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:
'''
    if source.count(helper_anchor) != 1:
        fail("holdings.py service helper structure changed.")
    source = source.replace(helper_anchor, helper_replacement, 1)

    status_anchor = '''    if code in {
        "HOLD_KIS_SYNC_BALANCE_FAILED",
    }:
        return 502
'''
    status_replacement = '''    if code in {
        "HOLD_KIS_SYNC_BALANCE_FAILED",
        "HOLD_MARKET_FRESHNESS_UPDATE_FAILED",
    }:
        return 502
'''
    if source.count(status_anchor) != 1:
        fail("holdings.py HTTP status mapping changed.")
    source = source.replace(status_anchor, status_replacement, 1)

    refresh_anchor = '''@router.post("/stocks/{stock_id}/analysis/refresh")
def refresh_analysis(stock_id: str) -> dict[str, Any]:
    catalog = _catalog()
    try:
        stored = _history_service(catalog).analyze_latest_confirmed(
            monitored_stock_id=stock_id,
        )
        return _stored_analysis_payload(catalog, stored)
    except (HoldingsCatalogError, HoldingsAnalysisHistoryError) as error:
        _raise_holdings_error(error)
'''
    refresh_replacement = '''@router.post("/stocks/{stock_id}/analysis/refresh")
async def refresh_analysis(stock_id: str) -> dict[str, Any]:
    catalog = _catalog()
    try:
        stock = catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "HOLD_STOCK_NOT_FOUND",
                    "message": "등록된 종목을 찾을 수 없습니다.",
                },
            )

        current = _current_analysis_payload(catalog, stock_id)
        known_data_date = current.get("market_date") if current else None
        freshness = await _freshness_service().prepare(
            market=stock.market,
            known_data_date=known_data_date,
        )

        stored = _history_service(catalog).analyze_and_record(
            monitored_stock_id=stock_id,
            market_date=freshness.resolved_as_of_date,
        )
        payload = _stored_analysis_payload(catalog, stored)
        payload["previous_analysis_date"] = known_data_date
        payload["data_freshness"] = freshness.to_dict()
        return payload
    except (
        HoldingsCatalogError,
        HoldingsAnalysisHistoryError,
        HoldingsMarketFreshnessError,
    ) as error:
        _raise_holdings_error(error)
'''
    if source.count(refresh_anchor) != 1:
        fail("holdings.py refresh_analysis route changed.")
    return source.replace(refresh_anchor, refresh_replacement, 1)


def patch_holdings_service(source: str) -> str:
    if "HoldingDataFreshness" in source:
        fail("frontend holdingsApi.ts already appears to contain G.3 types.")

    type_anchor = '''export type HoldingChartResponse = {
  market: string;
  ticker: string;
  range: HoldingChartRange;
  source: "MARKET_STORE_CONFIRMED_EOD" | string;
  from_date: string;
  to_date: string;
  requested_bars: number;
  count: number;
  bars: HoldingChartBar[];
};
'''
    type_append = type_anchor + '''
export type HoldingDataFreshness = {
  status: "READY" | "UPDATED" | string;
  market: string;
  requested_date: string | null;
  latest_confirmed_date: string | null;
  resolved_as_of_date: string;
  known_data_date: string | null;
  market_data_updated: boolean;
  date_changed: boolean;
  network_requests: number;
  message: string;
};

export type HoldingAnalysisRefreshResponse = HoldingAnalysis & {
  created_revision: boolean;
  promoted_current: boolean;
  previous_analysis_date: string | null;
  data_freshness: HoldingDataFreshness;
};
'''
    if source.count(type_anchor) != 1:
        fail("holdingsApi.ts chart response type anchor changed.")
    source = source.replace(type_anchor, type_append, 1)

    fn_anchor = '''export function refreshHoldingAnalysis(stockId: string): Promise<unknown> {
  return requestJson(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/refresh`,
    jsonInit("POST"),
  );
}
'''
    fn_replacement = '''export function refreshHoldingAnalysis(
  stockId: string,
): Promise<HoldingAnalysisRefreshResponse> {
  return requestJson<HoldingAnalysisRefreshResponse>(
    `/api/holdings/stocks/${encodeURIComponent(stockId)}/analysis/refresh`,
    jsonInit("POST"),
  );
}
'''
    if source.count(fn_anchor) != 1:
        fail("holdingsApi.ts refresh function anchor changed.")
    return source.replace(fn_anchor, fn_replacement, 1)


def patch_workspace(source: str) -> str:
    if "chartRefreshKey" in source:
        fail("HoldingsWorkspace.tsx already appears to contain G.3 chart refresh wiring.")

    state_anchor = '''  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
  const [syncingKis, setSyncingKis] = useState(false);
'''
    state_replacement = '''  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
  const [chartRefreshKey, setChartRefreshKey] = useState(0);
  const [syncingKis, setSyncingKis] = useState(false);
'''
    if source.count(state_anchor) != 1:
        fail("HoldingsWorkspace state anchor changed.")
    source = source.replace(state_anchor, state_replacement, 1)

    refresh_anchor = '''  async function refreshSelected() {
    if (!selectedStockId) return;
    setRefreshingAnalysis(true);
    setError(null);
    setMessage(null);
    try {
      await refreshHoldingAnalysis(selectedStockId);
      await Promise.all([reloadStocks(selectedStockId), loadSelected(selectedStockId)]);
      setMessage("최신 확정 일봉 기준으로 분석을 새로 확인했습니다.");
    } catch (refreshError) {
      setError(readableError(refreshError, "분석을 새로 확인하지 못했습니다."));
    } finally {
      setRefreshingAnalysis(false);
    }
  }
'''
    refresh_replacement = '''  async function refreshSelected() {
    if (!selectedStockId) return;
    setRefreshingAnalysis(true);
    setError(null);
    setMessage(null);
    try {
      const result = await refreshHoldingAnalysis(selectedStockId);
      await Promise.all([reloadStocks(selectedStockId), loadSelected(selectedStockId)]);
      setChartRefreshKey((value) => value + 1);
      const dateLabel = compactDate(result.market_date);
      setMessage(
        result.data_freshness.status === "UPDATED"
          ? `새로운 확정 시세를 반영해 ${dateLabel} 기준으로 분석했습니다.`
          : `${dateLabel} 최신 확정 일봉 기준으로 분석했습니다.`,
      );
    } catch (refreshError) {
      setError(readableError(refreshError, "최신 확정 데이터를 확인하거나 분석하지 못했습니다."));
    } finally {
      setRefreshingAnalysis(false);
    }
  }
'''
    if source.count(refresh_anchor) != 1:
        fail("HoldingsWorkspace refreshSelected anchor changed.")
    source = source.replace(refresh_anchor, refresh_replacement, 1)

    chart_anchor = '''              <HoldingsPriceChart stockId={detail.stock_id} analysis={selectedAnalysis} />'''
    chart_replacement = '''              <HoldingsPriceChart
                stockId={detail.stock_id}
                analysis={selectedAnalysis}
                refreshKey={chartRefreshKey}
              />'''
    if source.count(chart_anchor) != 1:
        fail("HoldingsWorkspace chart component anchor changed.")
    return source.replace(chart_anchor, chart_replacement, 1)


def patch_css(source: str) -> str:
    marker = "/* HOLD.1-G.1/G.2 — list removal + confirmed EOD chart */"
    marker2 = "/* HOLD.1-G.1/G.2/G.3 — list removal + readable confirmed EOD chart */"
    if marker2 in source:
        fail("holdings.css already contains G.3 chart styles.")
    index = source.find(marker)
    if index < 0:
        fail("holdings.css G.1/G.2 marker not found.")
    return source[:index].rstrip() + "\n\n\n" + CSS_TAIL.strip() + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-G.3 — 차트 가독성 + 최신 확정 데이터 자동 준비")
    print("Refresh network trigger: USER CLICK ONLY")
    print("Scanner ranking run: NO")
    print("KIS: NO")
    print("Paid API/service: NO")
    print("Theme support: LIGHT + DARK")

    required = [
        HOLDINGS_API,
        CHART_TEST,
        API_TEST,
        HISTORY_TEST,
        PRICE_CHART,
        WORKSPACE,
        HOLDINGS_SERVICE,
        HOLDINGS_CSS,
        PACKAGE_JSON,
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    if FRESHNESS.exists() or FRESHNESS_TEST.exists():
        fail("G.3 target file already exists; stop to avoid double-apply.")

    protected = {
        "scanner": sha256(BACKEND / "app" / "backtest" / "scanner.py"),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
    }

    originals = {
        HOLDINGS_API: HOLDINGS_API.read_text(encoding="utf-8-sig"),
        PRICE_CHART: PRICE_CHART.read_text(encoding="utf-8-sig"),
        WORKSPACE: WORKSPACE.read_text(encoding="utf-8-sig"),
        HOLDINGS_SERVICE: HOLDINGS_SERVICE.read_text(encoding="utf-8-sig"),
        HOLDINGS_CSS: HOLDINGS_CSS.read_text(encoding="utf-8-sig"),
    }
    created: list[Path] = []

    try:
        HOLDINGS_API.write_text(
            patch_holdings_api(originals[HOLDINGS_API]),
            encoding="utf-8",
            newline="\n",
        )
        HOLDINGS_SERVICE.write_text(
            patch_holdings_service(originals[HOLDINGS_SERVICE]),
            encoding="utf-8",
            newline="\n",
        )
        WORKSPACE.write_text(
            patch_workspace(originals[WORKSPACE]),
            encoding="utf-8",
            newline="\n",
        )
        PRICE_CHART.write_text(PRICE_CHART_CONTENT, encoding="utf-8", newline="\n")
        HOLDINGS_CSS.write_text(
            patch_css(originals[HOLDINGS_CSS]),
            encoding="utf-8",
            newline="\n",
        )
        FRESHNESS.write_text(FRESHNESS_CONTENT, encoding="utf-8", newline="\n")
        created.append(FRESHNESS)
        FRESHNESS_TEST.write_text(FRESHNESS_TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(FRESHNESS_TEST)

        print()
        print("=== HOLD.1-G.3 STATIC CONTRACT ===")
        api_now = HOLDINGS_API.read_text(encoding="utf-8")
        fresh_now = FRESHNESS.read_text(encoding="utf-8")
        chart_now = PRICE_CHART.read_text(encoding="utf-8")
        workspace_now = WORKSPACE.read_text(encoding="utf-8")
        service_now = HOLDINGS_SERVICE.read_text(encoding="utf-8")
        css_now = HOLDINGS_CSS.read_text(encoding="utf-8")
        package_now = PACKAGE_JSON.read_text(encoding="utf-8").lower()

        checks = {
            "refresh is async": "async def refresh_analysis" in api_now,
            "freshness before analysis": "await _freshness_service().prepare" in api_now and "market_date=freshness.resolved_as_of_date" in api_now,
            "same Market Store path": "market_store_db=_market_store_path()" in api_now and "HoldingsChartService(_market_store_path())" in api_now,
            "selected market only": "market_scope=clean_market" in fresh_now,
            "prepare only": "prepare_latest_confirmed_data" in fresh_now and ".run(" not in fresh_now,
            "no KIS in freshness": "integrations.kis" not in fresh_now.lower(),
            "chart Y scale OHLC only": "concat(levels.map" not in chart_now and "const lowest = Math.min(...numeric.map((bar) => bar.l!))" in chart_now,
            "chart legend": "holdings-chart-levels" in chart_now,
            "out-of-range level markers": 'position: level.value > maxPrice ? "above"' in chart_now,
            "no SVG level labels": "holdings-level-label" not in chart_now,
            "analysis marker no SVG text": '<g className="holdings-analysis-marker">' not in chart_now,
            "chart refresh key": "refreshKey={chartRefreshKey}" in workspace_now and "[stockId, range, refreshKey]" in chart_now,
            "stale date hint": "새로고침 필요" in chart_now,
            "typed refresh response": "HoldingAnalysisRefreshResponse" in service_now,
            "light/dark tokens": "var(--text-primary)" in css_now and "var(--bg-surface-raised)" in css_now,
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
                str(python),
                "-m",
                "pytest",
                "backend/tests/test_holdings_freshness_hold1g3.py",
                "backend/tests/test_holdings_chart_hold1g.py",
                "backend/tests/test_holdings_api_hold1f.py",
                "backend/tests/test_holdings_analysis_history_hold1e.py",
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
            "scanner": sha256(BACKEND / "app" / "backtest" / "scanner.py"),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
        }
        if protected_after != protected:
            fail("Protected Scanner/Strategy/Risk/KIS source changed during G.3.")

        print()
        print("HOLD.1-G.3 IMPLEMENTATION READY")
        print("Added:")
        print(" - backend/app/holdings/freshness.py")
        print(" - backend/tests/test_holdings_freshness_hold1g3.py")
        print("Modified:")
        print(" - backend/app/api/holdings.py")
        print(" - frontend/src/components/HoldingsPriceChart.tsx")
        print(" - frontend/src/components/HoldingsWorkspace.tsx")
        print(" - frontend/src/services/holdingsApi.ts")
        print(" - frontend/src/holdings.css")
        print("Refresh prepares latest confirmed EOD first: PASS")
        print("Selected market only: PASS")
        print("Scanner ranking run: NO")
        print("Provider failure preserves existing analysis: PASS")
        print("Chart Y-axis ignores distant targets: PASS")
        print("Analysis labels moved outside plot: PASS")
        print("Chart refetch after analysis refresh: PASS")
        print("Dark/Light theme: PASS")
        print("Paid service/dependency: 0")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Do NOT run 종목 후보 찾기.")
        print(" 2) Open 내 종목 분석.")
        print(" 3) Click 분석 새로고침 on a 09.21 stock.")
        print(" 4) Confirm analysis + chart advance to 09.22.")
        print(" 5) Capture one Dark screenshot of the revised chart.")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — HOLD.1-G.3 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
