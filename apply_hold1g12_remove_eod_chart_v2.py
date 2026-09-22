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
CHART_SERVICE = BACKEND / "app" / "holdings" / "chart.py"
CHART_TEST = BACKEND / "tests" / "test_holdings_chart_hold1g.py"

HOLDINGS_SERVICE = FRONTEND / "src" / "services" / "holdingsApi.ts"
HOLDINGS_WORKSPACE = FRONTEND / "src" / "components" / "HoldingsWorkspace.tsx"
PRICE_CHART = FRONTEND / "src" / "components" / "HoldingsPriceChart.tsx"
HOLDINGS_CSS = FRONTEND / "src" / "holdings.css"
GLOBAL_STYLES = FRONTEND / "src" / "styles.css"
PACKAGE_JSON = FRONTEND / "package.json"

CHART_SERVICE_CONTENT = 'from __future__ import annotations\n\nimport json\nimport sqlite3\nfrom dataclasses import asdict, dataclass\nfrom decimal import Decimal, InvalidOperation\nfrom pathlib import Path\nfrom typing import Any, Literal\n\nfrom app.core.config import PROJECT_ROOT\n\n\nChartRange = Literal["1m", "3m", "6m", "1y"]\nRANGE_BARS: dict[str, int] = {\n    "1m": 22,\n    "3m": 66,\n    "6m": 132,\n    "1y": 252,\n}\nDEFAULT_MARKET_STORE_DB = (\n    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"\n)\n\n\nclass HoldingsChartError(RuntimeError):\n    def __init__(self, code: str, message: str):\n        super().__init__(message)\n        self.code = code\n        self.message = message\n\n\n@dataclass(frozen=True, slots=True)\nclass HoldingChartBar:\n    date: str\n    open: str\n    high: str\n    low: str\n    close: str\n    volume: str\n\n\n@dataclass(frozen=True, slots=True)\nclass HoldingChartSeries:\n    market: str\n    ticker: str\n    chart_range: str\n    source: str\n    from_date: str\n    to_date: str\n    requested_bars: int\n    count: int\n    bars: tuple[HoldingChartBar, ...]\n\n    def to_dict(self) -> dict[str, Any]:\n        payload = asdict(self)\n        payload["range"] = payload.pop("chart_range")\n        payload["bars"] = [asdict(bar) for bar in self.bars]\n        return payload\n\n\ndef _normalize_market(market: str) -> str:\n    value = (market or "").strip().upper()\n    if value not in {"KOSPI", "KOSDAQ"}:\n        raise HoldingsChartError(\n            "HOLD_CHART_MARKET_INVALID",\n            "market은 KOSPI 또는 KOSDAQ이어야 합니다.",\n        )\n    return value\n\n\ndef _normalize_ticker(ticker: str) -> str:\n    value = (ticker or "").strip()\n    if len(value) != 6 or not value.isdigit():\n        raise HoldingsChartError(\n            "HOLD_CHART_TICKER_INVALID",\n            "국내주식 종목코드는 6자리 숫자여야 합니다.",\n        )\n    return value\n\n\ndef _decimal_text(value: Any, *, field: str, allow_zero: bool = False) -> str:\n    if value in (None, ""):\n        raise HoldingsChartError(\n            "HOLD_CHART_DATA_INVALID",\n            f"Market Store 차트 데이터에 {field} 값이 없습니다.",\n        )\n    try:\n        number = Decimal(str(value))\n    except (InvalidOperation, ValueError) as exc:\n        raise HoldingsChartError(\n            "HOLD_CHART_DATA_INVALID",\n            f"Market Store 차트 데이터의 {field} 값이 숫자가 아닙니다.",\n        ) from exc\n    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):\n        raise HoldingsChartError(\n            "HOLD_CHART_DATA_INVALID",\n            f"Market Store 차트 데이터의 {field} 값이 올바르지 않습니다.",\n        )\n    return format(number, "f")\n\n\ndef _iso_date(raw: Any, bas_dd: str) -> str:\n    value = str(raw or "").strip()\n    if len(value) == 10 and value[4] == "-" and value[7] == "-":\n        return value\n    if len(bas_dd) == 8 and bas_dd.isdigit():\n        return f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"\n    raise HoldingsChartError(\n        "HOLD_CHART_DATA_INVALID",\n        "Market Store 차트 데이터의 날짜 형식이 올바르지 않습니다.",\n    )\n\n\nclass HoldingsChartService:\n    """Read-only confirmed-EOD OHLCV reader for the HOLD UI chart."""\n\n    def __init__(self, market_store_db: Path | None = None) -> None:\n        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)\n\n    def _connect(self) -> sqlite3.Connection:\n        if not self.market_store_db.is_file():\n            raise HoldingsChartError(\n                "HOLD_CHART_MARKET_STORE_NOT_FOUND",\n                f"Market Store를 찾을 수 없습니다: {self.market_store_db}",\n            )\n        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"\n        conn = sqlite3.connect(uri, uri=True, timeout=20.0)\n        conn.row_factory = sqlite3.Row\n        return conn\n\n    def load(\n        self,\n        *,\n        market: str,\n        ticker: str,\n        chart_range: ChartRange,\n    ) -> HoldingChartSeries:\n        clean_market = _normalize_market(market)\n        clean_ticker = _normalize_ticker(ticker)\n        if chart_range not in RANGE_BARS:\n            raise HoldingsChartError(\n                "HOLD_CHART_RANGE_INVALID",\n                "차트 기간은 1m, 3m, 6m, 1y 중 하나여야 합니다.",\n            )\n        limit = RANGE_BARS[chart_range]\n\n        with self._connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT s.bas_dd,s.row_json\n                FROM stock_daily s\n                JOIN day_status d\n                  ON d.market=s.market\n                 AND d.bas_dd=s.bas_dd\n                 AND d.kind=\'stock\'\n                 AND d.status=\'data\'\n                WHERE s.market=? AND s.stock_code=?\n                ORDER BY s.bas_dd DESC\n                LIMIT ?\n                """,\n                (clean_market, clean_ticker, limit),\n            ).fetchall()\n\n        if not rows:\n            raise HoldingsChartError(\n                "HOLD_CHART_STOCK_NOT_FOUND",\n                f"{clean_market}/{clean_ticker}의 확정 일봉 데이터를 찾을 수 없습니다.",\n            )\n\n        bars: list[HoldingChartBar] = []\n        for row in reversed(rows):\n            try:\n                payload = json.loads(str(row["row_json"]))\n            except json.JSONDecodeError as exc:\n                raise HoldingsChartError(\n                    "HOLD_CHART_DATA_INVALID",\n                    "Market Store 차트 데이터 JSON을 읽을 수 없습니다.",\n                ) from exc\n            if not isinstance(payload, dict):\n                raise HoldingsChartError(\n                    "HOLD_CHART_DATA_INVALID",\n                    "Market Store 차트 데이터 형식이 올바르지 않습니다.",\n                )\n\n            open_text = _decimal_text(payload.get("open"), field="시가")\n            high_text = _decimal_text(payload.get("high"), field="고가")\n            low_text = _decimal_text(payload.get("low"), field="저가")\n            close_text = _decimal_text(payload.get("close"), field="종가")\n            volume_text = _decimal_text(\n                payload.get("volume"),\n                field="거래량",\n                allow_zero=True,\n            )\n\n            open_value = Decimal(open_text)\n            high_value = Decimal(high_text)\n            low_value = Decimal(low_text)\n            close_value = Decimal(close_text)\n            if high_value < max(open_value, close_value) or low_value > min(open_value, close_value) or high_value < low_value:\n                raise HoldingsChartError(\n                    "HOLD_CHART_DATA_INVALID",\n                    "Market Store OHLC 가격 관계가 올바르지 않습니다.",\n                )\n\n            bars.append(\n                HoldingChartBar(\n                    date=_iso_date(payload.get("date"), str(row["bas_dd"])),\n                    open=open_text,\n                    high=high_text,\n                    low=low_text,\n                    close=close_text,\n                    volume=volume_text,\n                )\n            )\n\n        return HoldingChartSeries(\n            market=clean_market,\n            ticker=clean_ticker,\n            chart_range=chart_range,\n            source="MARKET_STORE_CONFIRMED_EOD",\n            from_date=bars[0].date,\n            to_date=bars[-1].date,\n            requested_bars=limit,\n            count=len(bars),\n            bars=tuple(bars),\n        )\n'
CHART_TEST_CONTENT = 'from __future__ import annotations\n\nimport hashlib\nimport json\nimport os\nimport sqlite3\nimport sys\nfrom datetime import date, timedelta\nfrom pathlib import Path\n\nfrom fastapi import FastAPI\nfrom fastapi.testclient import TestClient\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\nfrom app.api import holdings as holdings_api\nfrom app.holdings.chart import HoldingsChartService, RANGE_BARS\n\n\ndef _row(index: int, bas_dd: str) -> dict[str, object]:\n    close = 70000 + index * 100\n    return {\n        "date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}",\n        "code": "005930",\n        "name": "삼성전자",\n        "open": close - 50,\n        "high": close + 250,\n        "low": close - 200,\n        "close": close,\n        "volume": 1_000_000 + index * 10_000,\n    }\n\n\ndef _build_market_store(path: Path, count: int = 280) -> None:\n    with sqlite3.connect(path) as conn:\n        conn.executescript(\n            """\n            CREATE TABLE stock_daily(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                stock_code TEXT NOT NULL,\n                row_json TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,stock_code)\n            );\n            CREATE TABLE day_status(\n                market TEXT NOT NULL,\n                bas_dd TEXT NOT NULL,\n                kind TEXT NOT NULL,\n                status TEXT NOT NULL,\n                PRIMARY KEY(market,bas_dd,kind)\n            );\n            """\n        )\n        start = date(2025, 1, 1)\n        for index in range(count):\n            bas_dd = (start + timedelta(days=index)).strftime("%Y%m%d")\n            conn.execute(\n                "INSERT INTO stock_daily VALUES(?,?,?,?)",\n                ("KOSPI", bas_dd, "005930", json.dumps(_row(index, bas_dd), ensure_ascii=False)),\n            )\n            conn.execute(\n                "INSERT INTO day_status VALUES(?,?,?,?)",\n                ("KOSPI", bas_dd, "stock", "data"),\n            )\n        conn.execute(\n            "UPDATE day_status SET status=\'empty\' WHERE bas_dd=(SELECT MAX(bas_dd) FROM day_status)"\n        )\n\n\ndef _sha(path: Path) -> str:\n    return hashlib.sha256(path.read_bytes()).hexdigest()\n\n\ndef test_chart_service_ranges_confirmed_only_and_read_only(tmp_path: Path) -> None:\n    store = tmp_path / "market.db"\n    _build_market_store(store)\n    before = _sha(store)\n    service = HoldingsChartService(store)\n\n    for chart_range, expected in RANGE_BARS.items():\n        result = service.load(market="KOSPI", ticker="005930", chart_range=chart_range)  # type: ignore[arg-type]\n        assert result.source == "MARKET_STORE_CONFIRMED_EOD"\n        assert result.count == expected\n        assert len(result.bars) == expected\n        assert list(result.bars) == sorted(result.bars, key=lambda bar: bar.date)\n        assert result.bars[-1].date == (date(2025, 1, 1) + timedelta(days=278)).isoformat()\n        assert DecimalLike(result.bars[0].low) <= DecimalLike(result.bars[0].open) <= DecimalLike(result.bars[0].high)\n        assert DecimalLike(result.bars[0].low) <= DecimalLike(result.bars[0].close) <= DecimalLike(result.bars[0].high)\n\n    assert _sha(store) == before\n\n\ndef DecimalLike(value: str) -> float:\n    return float(value)\n\n\ndef test_chart_endpoint_uses_monitored_stock_and_validates_range(tmp_path: Path, monkeypatch) -> None:\n    holdings_db = tmp_path / "holdings.db"\n    market_db = tmp_path / "market.db"\n    _build_market_store(market_db)\n    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))\n    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))\n\n    app = FastAPI()\n    app.include_router(holdings_api.router, prefix="/api")\n    client = TestClient(app)\n\n    watched = client.post(\n        "/api/holdings/watch",\n        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},\n    )\n    assert watched.status_code == 200, watched.text\n    stock_id = watched.json()["stock"]["stock_id"]\n\n    response = client.get(f"/api/holdings/stocks/{stock_id}/chart?range=1m")\n    assert response.status_code == 200, response.text\n    body = response.json()\n    assert body["ticker"] == "005930"\n    assert body["range"] == "1m"\n    assert body["source"] == "MARKET_STORE_CONFIRMED_EOD"\n    assert body["count"] == 22\n    assert set(body["bars"][0]) == {"date", "open", "high", "low", "close", "volume"}\n\n    invalid = client.get(f"/api/holdings/stocks/{stock_id}/chart?range=2m")\n    assert invalid.status_code == 422\n\n    missing = client.get("/api/holdings/stocks/not-found/chart?range=1m")\n    assert missing.status_code == 404\n\n\ndef test_chart_implementation_has_no_network_or_paid_chart_dependency() -> None:\n    chart_source = Path("backend/app/holdings/chart.py").read_text(encoding="utf-8")\n    lowered = chart_source.lower()\n    assert "requests" not in lowered\n    assert "httpx" not in lowered\n    assert "websocket" not in lowered\n    assert "kis" not in lowered\n    assert "mode=ro" in chart_source\n\n    package = Path("frontend/package.json").read_text(encoding="utf-8")\n    for dependency in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly"):\n        assert dependency not in package.lower()\n'
PRICE_CHART_CONTENT = 'import { useEffect, useMemo, useState, type PointerEvent } from "react";\nimport {\n  getHoldingChart,\n  type HoldingAnalysis,\n  type HoldingChartBar,\n  type HoldingChartRange,\n  type HoldingChartResponse,\n} from "../services/holdingsApi";\n\nconst RANGE_OPTIONS: Array<{ key: HoldingChartRange; label: string }> = [\n  { key: "1m", label: "1개월" },\n  { key: "3m", label: "3개월" },\n  { key: "6m", label: "6개월" },\n  { key: "1y", label: "1년" },\n];\n\nconst W = 920;\nconst H = 292;\nconst LEFT = 58;\nconst RIGHT = 96;\nconst TOP = 18;\nconst PRICE_BOTTOM = 210;\nconst VOLUME_TOP = 229;\nconst VOLUME_BOTTOM = 272;\n\nfunction number(value: string | null | undefined) {\n  if (value == null || value === "") return null;\n  const parsed = Number(value);\n  return Number.isFinite(parsed) ? parsed : null;\n}\n\nfunction formatPrice(value: number) {\n  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);\n}\n\nfunction formatVolume(value: number) {\n  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(value);\n}\n\nfunction shortDate(value: string) {\n  return value.length >= 10 ? `${value.slice(5, 7)}.${value.slice(8, 10)}` : value;\n}\n\nfunction mergeBars(history: HoldingChartBar[], liveBar: HoldingChartBar | null) {\n  if (!liveBar) return history;\n  if (history.length === 0) return [liveBar];\n  const last = history[history.length - 1];\n  if (last.date === liveBar.date) return [...history.slice(0, -1), liveBar];\n  return [...history, liveBar];\n}\n\ntype Props = {\n  stockId: string;\n  analysis: HoldingAnalysis | null;\n  liveBar?: HoldingChartBar | null;\n};\n\nexport default function HoldingsPriceChart({ stockId, analysis, liveBar = null }: Props) {\n  const [range, setRange] = useState<HoldingChartRange>("1m");\n  const [chart, setChart] = useState<HoldingChartResponse | null>(null);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState<string | null>(null);\n  const [hoverIndex, setHoverIndex] = useState<number | null>(null);\n\n  useEffect(() => {\n    let cancelled = false;\n    setLoading(true);\n    setError(null);\n    setChart(null);\n    setHoverIndex(null);\n    void getHoldingChart(stockId, range)\n      .then((result) => {\n        if (!cancelled) setChart(result);\n      })\n      .catch((loadError) => {\n        if (cancelled) return;\n        setChart(null);\n        setError(loadError instanceof Error ? loadError.message : "차트 데이터를 불러오지 못했습니다.");\n      })\n      .finally(() => {\n        if (!cancelled) setLoading(false);\n      });\n    return () => {\n      cancelled = true;\n    };\n  }, [stockId, range]);\n\n  const bars = useMemo(() => mergeBars(chart?.bars ?? [], liveBar), [chart, liveBar]);\n\n  const model = useMemo(() => {\n    const numeric = bars\n      .map((bar) => ({\n        ...bar,\n        o: number(bar.open),\n        h: number(bar.high),\n        l: number(bar.low),\n        c: number(bar.close),\n        v: number(bar.volume),\n      }))\n      .filter((bar) => bar.o != null && bar.h != null && bar.l != null && bar.c != null && bar.v != null);\n\n    if (numeric.length === 0) return null;\n\n    const levels = [\n      { key: "reference", label: "기준가", value: number(analysis?.reference_price) },\n      { key: "stop", label: "손절 기준", value: number(analysis?.stop_price) },\n      { key: "target1", label: "1차 목표", value: number(analysis?.target1_price) },\n      { key: "target2", label: "2차 목표", value: number(analysis?.target2_price) },\n    ].filter((item): item is { key: string; label: string; value: number } => item.value != null);\n\n    const priceValues = numeric.flatMap((bar) => [bar.h!, bar.l!]).concat(levels.map((item) => item.value));\n    let minPrice = Math.min(...priceValues);\n    let maxPrice = Math.max(...priceValues);\n    const rawRange = Math.max(maxPrice - minPrice, maxPrice * 0.015, 1);\n    minPrice -= rawRange * 0.08;\n    maxPrice += rawRange * 0.08;\n    const priceRange = maxPrice - minPrice || 1;\n    const maxVolume = Math.max(...numeric.map((bar) => bar.v!), 1);\n    const plotWidth = W - LEFT - RIGHT;\n    const step = plotWidth / numeric.length;\n    const candleWidth = Math.max(1.2, Math.min(8.5, step * 0.56));\n\n    const yPrice = (value: number) => TOP + ((maxPrice - value) / priceRange) * (PRICE_BOTTOM - TOP);\n    const xAt = (index: number) => LEFT + step * (index + 0.5);\n    const volumeY = (value: number) => VOLUME_BOTTOM - (value / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);\n\n    const tickIndexes = Array.from(new Set([\n      0,\n      Math.floor((numeric.length - 1) * 0.25),\n      Math.floor((numeric.length - 1) * 0.5),\n      Math.floor((numeric.length - 1) * 0.75),\n      numeric.length - 1,\n    ])).sort((a, b) => a - b);\n\n    const yTicks = Array.from({ length: 5 }, (_, index) => {\n      const ratio = index / 4;\n      const value = maxPrice - (maxPrice - minPrice) * ratio;\n      return { value, y: TOP + (PRICE_BOTTOM - TOP) * ratio };\n    });\n\n    const analysisIndex = analysis\n      ? numeric.findIndex((bar) => bar.date === analysis.market_date)\n      : -1;\n\n    return {\n      numeric,\n      levels,\n      xAt,\n      yPrice,\n      volumeY,\n      candleWidth,\n      tickIndexes,\n      yTicks,\n      analysisIndex,\n      plotWidth,\n      step,\n    };\n  }, [bars, analysis]);\n\n  function handlePointerMove(event: PointerEvent<SVGRectElement>) {\n    if (!model) return;\n    const rect = event.currentTarget.getBoundingClientRect();\n    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));\n    const chartX = ratio * W;\n    const raw = Math.floor((chartX - LEFT) / model.step);\n    const index = Math.max(0, Math.min(model.numeric.length - 1, raw));\n    setHoverIndex(index);\n  }\n\n  const hovered = model && hoverIndex != null ? model.numeric[hoverIndex] : null;\n\n  return (\n    <section className="holdings-chart-panel">\n      <div className="holdings-chart-head">\n        <div>\n          <h3>확정 일봉</h3>\n          <span>\n            {liveBar ? "오늘 캔들 실시간 반영" : chart?.to_date ? `${chart.to_date.replace(/-/g, ".")}까지` : "Market Store 기준"}\n          </span>\n        </div>\n        <div className="holdings-chart-ranges" aria-label="차트 기간">\n          {RANGE_OPTIONS.map((option) => (\n            <button\n              key={option.key}\n              type="button"\n              className={range === option.key ? "active" : ""}\n              onClick={() => setRange(option.key)}\n            >\n              {option.label}\n            </button>\n          ))}\n        </div>\n      </div>\n\n      {loading && !chart ? (\n        <div className="holdings-chart-state">확정 일봉을 불러오는 중입니다.</div>\n      ) : error ? (\n        <div className="holdings-chart-state error">{error}</div>\n      ) : !model ? (\n        <div className="holdings-chart-state">표시할 확정 일봉이 없습니다.</div>\n      ) : (\n        <div className="holdings-chart-canvas">\n          <svg\n            viewBox={`0 0 ${W} ${H}`}\n            role="img"\n            aria-label={`${range} 확정 일봉 캔들 차트`}\n            onPointerLeave={() => setHoverIndex(null)}\n          >\n            <g className="holdings-chart-grid">\n              {model.yTicks.map((tick) => (\n                <g key={tick.y}>\n                  <line x1={LEFT} x2={W - RIGHT} y1={tick.y} y2={tick.y} />\n                  <text x={W - RIGHT + 8} y={tick.y + 4}>{formatPrice(tick.value)}</text>\n                </g>\n              ))}\n              <line x1={LEFT} x2={W - RIGHT} y1={VOLUME_TOP - 8} y2={VOLUME_TOP - 8} />\n            </g>\n\n            {model.levels.map((level) => {\n              const y = model.yPrice(level.value);\n              return (\n                <g key={level.key} className={`holdings-level ${level.key}`}>\n                  <line className="holdings-level-line" x1={LEFT} x2={W - RIGHT} y1={y} y2={y} />\n                  <text className="holdings-level-label" x={W - RIGHT + 8} y={y - 4}>{level.label}</text>\n                </g>\n              );\n            })}\n\n            {model.analysisIndex >= 0 && (\n              <g className="holdings-analysis-marker">\n                <line\n                  x1={model.xAt(model.analysisIndex)}\n                  x2={model.xAt(model.analysisIndex)}\n                  y1={TOP}\n                  y2={VOLUME_BOTTOM}\n                />\n                <text x={model.xAt(model.analysisIndex)} y={TOP + 12}>분석 기준일</text>\n              </g>\n            )}\n\n            <g className="holdings-candles">\n              {model.numeric.map((bar, index) => {\n                const x = model.xAt(index);\n                const openY = model.yPrice(bar.o!);\n                const closeY = model.yPrice(bar.c!);\n                const highY = model.yPrice(bar.h!);\n                const lowY = model.yPrice(bar.l!);\n                const bodyY = Math.min(openY, closeY);\n                const bodyHeight = Math.max(1.2, Math.abs(closeY - openY));\n                const direction = bar.c! > bar.o! ? "up" : bar.c! < bar.o! ? "down" : "flat";\n                const volumeY = model.volumeY(bar.v!);\n                return (\n                  <g key={`${bar.date}-${index}`} className={`holdings-candle ${direction}`}>\n                    <line x1={x} x2={x} y1={highY} y2={lowY} />\n                    <rect\n                      x={x - model.candleWidth / 2}\n                      y={bodyY}\n                      width={model.candleWidth}\n                      height={bodyHeight}\n                    />\n                    <rect\n                      className="volume"\n                      x={x - model.candleWidth / 2}\n                      y={volumeY}\n                      width={model.candleWidth}\n                      height={Math.max(1, VOLUME_BOTTOM - volumeY)}\n                    />\n                  </g>\n                );\n              })}\n            </g>\n\n            <g className="holdings-chart-dates">\n              {model.tickIndexes.map((index) => (\n                <text key={index} x={model.xAt(index)} y={H - 5}>{shortDate(model.numeric[index].date)}</text>\n              ))}\n            </g>\n\n            {hoverIndex != null && (\n              <line\n                className="holdings-chart-hover-line"\n                x1={model.xAt(hoverIndex)}\n                x2={model.xAt(hoverIndex)}\n                y1={TOP}\n                y2={VOLUME_BOTTOM}\n              />\n            )}\n\n            <rect\n              className="holdings-chart-hit"\n              x={LEFT}\n              y={TOP}\n              width={model.plotWidth}\n              height={VOLUME_BOTTOM - TOP}\n              onPointerMove={handlePointerMove}\n            />\n          </svg>\n\n          {hovered && (\n            <div className="holdings-chart-tooltip">\n              <strong>{hovered.date.replace(/-/g, ".")}</strong>\n              <span>시가 <b>{formatPrice(hovered.o!)}</b></span>\n              <span>고가 <b>{formatPrice(hovered.h!)}</b></span>\n              <span>저가 <b>{formatPrice(hovered.l!)}</b></span>\n              <span>종가 <b>{formatPrice(hovered.c!)}</b></span>\n              <span>거래량 <b>{formatVolume(hovered.v!)}</b></span>\n            </div>\n          )}\n        </div>\n      )}\n\n      <div className="holdings-chart-foot">\n        <span>과거 구간은 로컬 Market Store의 확정 일봉만 사용합니다.</span>\n        {analysis && <span>분석 기준일 {analysis.market_date.replace(/-/g, ".")}</span>}\n      </div>\n    </section>\n  );\n}\n'
CSS_APPEND = '\n\n/* HOLD.1-G.1/G.2 — list removal + confirmed EOD chart */\n.holdings-text-action,.holdings-remove-button,.holdings-remove-confirm{font:inherit;font-weight:800}\n.holdings-text-action{border:0;background:transparent;color:var(--accent-primary);padding:8px 4px}\n.holdings-remove-button{border:1px solid var(--border-default);background:transparent;color:var(--text-secondary);padding:9px 11px}\n.holdings-remove-button:hover{border-color:var(--status-negative);color:var(--status-negative);background:var(--status-negative-bg)}\n.holdings-remove-confirm{border:1px solid var(--status-negative);background:var(--status-negative-bg);color:var(--status-negative);padding:9px 13px}\n.holdings-remove-copy{padding:14px 0;color:var(--text-secondary);font-size:var(--font-body-small);line-height:var(--line-body)}\n.holdings-remove-dialog{width:min(500px,100%)}\n.holdings-chart-panel{margin-top:18px;padding:16px 0 10px;border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default)}\n.holdings-chart-head,.holdings-chart-foot{display:flex;align-items:center;justify-content:space-between;gap:16px}\n.holdings-chart-head h3{margin:0;color:var(--text-primary);font-size:var(--font-card-title)}\n.holdings-chart-head span,.holdings-chart-foot{color:var(--text-muted);font-size:var(--font-meta)}\n.holdings-chart-ranges{display:flex;border-bottom:1px solid var(--border-default)}\n.holdings-chart-ranges button{border:0;border-bottom:2px solid transparent;background:transparent;color:var(--text-secondary);padding:6px 9px;font:inherit;font-size:var(--font-meta);font-weight:800}\n.holdings-chart-ranges button.active{border-bottom-color:var(--accent-primary);color:var(--text-primary)}\n.holdings-chart-canvas{position:relative;margin-top:10px;min-height:250px}\n.holdings-chart-canvas svg{display:block;width:100%;height:auto;min-height:250px;overflow:visible}\n.holdings-chart-grid line{stroke:var(--border-subtle);stroke-width:1;vector-effect:non-scaling-stroke}\n.holdings-chart-grid text,.holdings-chart-dates text{fill:var(--text-muted);font-size:11px}\n.holdings-chart-dates text{text-anchor:middle}\n.holdings-candle line{stroke-width:1.25;vector-effect:non-scaling-stroke}\n.holdings-candle rect{stroke-width:0}\n.holdings-candle.up line,.holdings-candle.up rect{stroke:var(--status-positive);fill:var(--status-positive)}\n.holdings-candle.down line,.holdings-candle.down rect{stroke:var(--status-negative);fill:var(--status-negative)}\n.holdings-candle.flat line,.holdings-candle.flat rect{stroke:var(--text-muted);fill:var(--text-muted)}\n.holdings-candle .volume{opacity:.28}\n.holdings-level-line{stroke-width:1;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}\n.holdings-level-label{font-size:10px;font-weight:800}\n.holdings-level.reference .holdings-level-line{stroke:var(--status-info)}\n.holdings-level.reference .holdings-level-label{fill:var(--status-info)}\n.holdings-level.stop .holdings-level-line{stroke:var(--status-negative)}\n.holdings-level.stop .holdings-level-label{fill:var(--status-negative)}\n.holdings-level.target1 .holdings-level-line,.holdings-level.target2 .holdings-level-line{stroke:var(--status-positive)}\n.holdings-level.target1 .holdings-level-label,.holdings-level.target2 .holdings-level-label{fill:var(--status-positive)}\n.holdings-analysis-marker line{stroke:var(--accent-primary);stroke-width:1;stroke-dasharray:3 5;opacity:.7;vector-effect:non-scaling-stroke}\n.holdings-analysis-marker text{fill:var(--accent-primary);font-size:10px;text-anchor:middle;font-weight:800}\n.holdings-chart-hover-line{stroke:var(--text-muted);stroke-width:1;stroke-dasharray:2 3;opacity:.55;pointer-events:none;vector-effect:non-scaling-stroke}\n.holdings-chart-hit{fill:transparent;cursor:crosshair}\n.holdings-chart-tooltip{position:absolute;right:12px;top:10px;display:grid;grid-template-columns:auto auto;gap:3px 12px;min-width:150px;padding:9px 10px;border:1px solid var(--border-strong);background:var(--bg-surface-raised);color:var(--text-secondary);font-size:11px;box-shadow:var(--shadow);pointer-events:none}\n.holdings-chart-tooltip>strong{grid-column:1/-1;color:var(--text-primary);margin-bottom:2px}\n.holdings-chart-tooltip span{display:contents}\n.holdings-chart-tooltip b{color:var(--text-primary);text-align:right}\n.holdings-chart-state{display:flex;align-items:center;justify-content:center;min-height:250px;color:var(--text-secondary);font-size:var(--font-body-small)}\n.holdings-chart-state.error{color:var(--status-negative)}\n.holdings-chart-foot{margin-top:5px;padding-top:8px;border-top:1px solid var(--border-subtle)}\n@media(max-width:700px){.holdings-chart-head,.holdings-chart-foot{align-items:flex-start;flex-direction:column}.holdings-chart-ranges{width:100%;overflow-x:auto}.holdings-chart-canvas{overflow-x:auto}.holdings-chart-canvas svg{min-width:720px}.holdings-chart-tooltip{position:sticky;left:10px;right:auto;width:160px}}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


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


def patch_backend_api(source: str) -> str:
    if 'HoldingsChartService' in source or '/chart"' in source:
        fail("backend/app/api/holdings.py already appears to contain G.2 chart changes.")

    import_anchor = '''from app.holdings.catalog import (\n    DEFAULT_HOLDINGS_DB,\n    HoldingsCatalog,\n    HoldingsCatalogError,\n)\n'''
    if source.count(import_anchor) != 1:
        fail("Backend holdings import structure changed.")
    source = source.replace(
        import_anchor,
        import_anchor + 'from app.holdings.chart import HoldingsChartError, HoldingsChartService\n',
        1,
    )

    service_anchor = '''def _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:\n    return HoldingAnalysisHistoryService(catalog)\n\n\ndef _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:\n'''
    service_replacement = '''def _history_service(catalog: HoldingsCatalog) -> HoldingAnalysisHistoryService:\n    return HoldingAnalysisHistoryService(catalog)\n\n\ndef _chart_service() -> HoldingsChartService:\n    raw = os.getenv("STOCKSCOPE_MARKET_STORE_DB")\n    return HoldingsChartService(Path(raw) if raw else None)\n\n\ndef _lifecycle_service(catalog: HoldingsCatalog) -> PositionLifecycleService:\n'''
    if source.count(service_anchor) != 1:
        fail("Backend holdings service helper structure changed.")
    source = source.replace(service_anchor, service_replacement, 1)

    route_anchor = '''@router.get("/stocks/{stock_id}")\ndef stock_detail(stock_id: str) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stock = catalog.get_monitored_stock(stock_id)\n        return _stock_payload(catalog, stock, include_latest_event=True)\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n\n\n@router.post("/watch")\n'''
    route_replacement = '''@router.get("/stocks/{stock_id}")\ndef stock_detail(stock_id: str) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stock = catalog.get_monitored_stock(stock_id)\n        return _stock_payload(catalog, stock, include_latest_event=True)\n    except HoldingsCatalogError as error:\n        _raise_holdings_error(error)\n\n\n@router.get("/stocks/{stock_id}/chart")\ndef stock_chart(\n    stock_id: str,\n    chart_range: Literal["1m", "3m", "6m", "1y"] = Query(default="1m", alias="range"),\n) -> dict[str, Any]:\n    catalog = _catalog()\n    try:\n        stock = catalog.get_monitored_stock(stock_id)\n        if stock is None:\n            raise HTTPException(\n                status_code=404,\n                detail={\n                    "code": "HOLD_STOCK_NOT_FOUND",\n                    "message": "등록된 종목을 찾을 수 없습니다.",\n                },\n            )\n        result = _chart_service().load(\n            market=stock.market,\n            ticker=stock.ticker,\n            chart_range=chart_range,\n        )\n        return result.to_dict()\n    except (HoldingsCatalogError, HoldingsChartError) as error:\n        _raise_holdings_error(error)\n\n\n@router.post("/watch")\n'''
    if source.count(route_anchor) != 1:
        fail("Backend stock detail/watch route structure changed.")
    return source.replace(route_anchor, route_replacement, 1)


def patch_frontend_service(source: str) -> str:
    if 'HoldingChartResponse' in source or 'getHoldingChart' in source:
        fail("frontend holdingsApi.ts already appears to contain G.2 chart changes.")

    type_anchor = '''export type KisSyncResponse = {\n  status: string;\n  sync_run_id: string;\n  account_id: string;\n  observed_at: string;\n  page_count: number;\n  holding_count: number;\n  created: number;\n  reconciled: number;\n  closed: number;\n  unchanged: number;\n};\n'''
    type_addition = type_anchor + '''\nexport type HoldingChartRange = "1m" | "3m" | "6m" | "1y";\n\nexport type HoldingChartBar = {\n  date: string;\n  open: string;\n  high: string;\n  low: string;\n  close: string;\n  volume: string;\n};\n\nexport type HoldingChartResponse = {\n  market: string;\n  ticker: string;\n  range: HoldingChartRange;\n  source: "MARKET_STORE_CONFIRMED_EOD" | string;\n  from_date: string;\n  to_date: string;\n  requested_bars: number;\n  count: number;\n  bars: HoldingChartBar[];\n};\n'''
    if source.count(type_anchor) != 1:
        fail("Frontend holdings API type structure changed.")
    source = source.replace(type_anchor, type_addition, 1)

    fn_anchor = '''export function syncKisHoldings(): Promise<KisSyncResponse> {\n  return requestJson<KisSyncResponse>("/api/holdings/kis/sync", jsonInit("POST"));\n}\n'''
    fn_replacement = '''export function getHoldingChart(\n  stockId: string,\n  range: HoldingChartRange,\n): Promise<HoldingChartResponse> {\n  const query = new URLSearchParams({ range });\n  return requestJson<HoldingChartResponse>(\n    `/api/holdings/stocks/${encodeURIComponent(stockId)}/chart?${query.toString()}`,\n  );\n}\n\nexport function syncKisHoldings(): Promise<KisSyncResponse> {\n  return requestJson<KisSyncResponse>("/api/holdings/kis/sync", jsonInit("POST"));\n}\n'''
    if source.count(fn_anchor) != 1:
        fail("Frontend holdings API function structure changed.")
    return source.replace(fn_anchor, fn_replacement, 1)


def patch_workspace(source: str) -> str:
    if 'HoldingsPriceChart' in source or 'removeOpen' in source:
        fail("HoldingsWorkspace.tsx already appears to contain G.1/G.2 changes.")

    import_anchor = 'import { searchStocks, type StockSearchItem } from "../services/api";\n'
    if source.count(import_anchor) != 1:
        fail("HoldingsWorkspace import structure changed.")
    source = source.replace(import_anchor, import_anchor + 'import HoldingsPriceChart from "./HoldingsPriceChart";\n', 1)

    state_anchor = '  const [addOpen, setAddOpen] = useState(false);\n'
    if source.count(state_anchor) != 1:
        fail("HoldingsWorkspace dialog state structure changed.")
    source = source.replace(state_anchor, state_anchor + '  const [removeOpen, setRemoveOpen] = useState(false);\n', 1)

    watch_anchor = '''  async function toggleWatch() {\n    if (!detail) return;\n    setError(null);\n    try {\n      await setWatchEnabled(detail.stock_id, !detail.watch_enabled);\n      await reloadStocks(detail.stock_id);\n      if (detail.is_held || !detail.watch_enabled) {\n        await loadSelected(detail.stock_id);\n      }\n      setMessage(detail.watch_enabled ? "관심 종목에서 해제했습니다." : "관심 종목으로 등록했습니다.");\n    } catch (watchError) {\n      setError(readableError(watchError, "관심 상태를 변경하지 못했습니다."));\n    }\n  }\n'''
    watch_replacement = '''  async function setSelectedWatch(enabled: boolean, removedFromList = false) {\n    if (!detail) return;\n    setError(null);\n    setMessage(null);\n    try {\n      await setWatchEnabled(detail.stock_id, enabled);\n      setRemoveOpen(false);\n      await reloadStocks(enabled || detail.is_held ? detail.stock_id : null);\n      if (detail.is_held) await loadSelected(detail.stock_id);\n      setMessage(\n        enabled\n          ? "관심 종목으로 등록했습니다."\n          : removedFromList\n            ? "내 종목 목록에서 제거했습니다. 저장된 분석 기록은 유지됩니다."\n            : "관심 종목에서 해제했습니다.",\n      );\n    } catch (watchError) {\n      setError(readableError(watchError, "관심 상태를 변경하지 못했습니다."));\n    }\n  }\n\n  function requestWatchChange() {\n    if (!detail) return;\n    if (!detail.watch_enabled) {\n      void setSelectedWatch(true);\n      return;\n    }\n    if (detail.is_held) {\n      void setSelectedWatch(false);\n      return;\n    }\n    setRemoveOpen(true);\n  }\n'''
    if source.count(watch_anchor) != 1:
        fail("HoldingsWorkspace watch handler structure changed.")
    source = source.replace(watch_anchor, watch_replacement, 1)

    head_anchor = '''                  <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>\n                    {syncingKis ? "동기화 중" : "잔고 동기화"}\n                  </button>\n                </div>\n              </div>\n\n              <div className="holdings-analysis-grid">\n'''
    head_replacement = '''                  <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>\n                    {syncingKis ? "동기화 중" : "잔고 동기화"}\n                  </button>\n                  <button\n                    className={detail.watch_enabled && !detail.is_held ? "holdings-remove-button" : "holdings-text-action"}\n                    type="button"\n                    onClick={requestWatchChange}\n                  >\n                    {!detail.watch_enabled ? "관심 등록" : detail.is_held ? "관심 해제" : "목록에서 제거"}\n                  </button>\n                </div>\n              </div>\n\n              <HoldingsPriceChart stockId={detail.stock_id} analysis={selectedAnalysis} />\n\n              <div className="holdings-analysis-grid">\n'''
    if source.count(head_anchor) != 1:
        fail("HoldingsWorkspace detail header structure changed.")
    source = source.replace(head_anchor, head_replacement, 1)

    analysis_watch_anchor = '''                  <div className="holdings-block-title">\n                    <h3>현재 분석</h3>\n                    <button type="button" className="holdings-text-button" onClick={toggleWatch}>\n                      {detail.watch_enabled ? "관심 해제" : "관심 등록"}\n                    </button>\n                  </div>\n'''
    analysis_watch_replacement = '''                  <div className="holdings-block-title">\n                    <h3>현재 분석</h3>\n                  </div>\n'''
    if source.count(analysis_watch_anchor) != 1:
        fail("HoldingsWorkspace analysis watch button structure changed.")
    source = source.replace(analysis_watch_anchor, analysis_watch_replacement, 1)

    dialog_anchor = '''      {addOpen && (\n        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setAddOpen(false)}>\n'''
    dialog_replacement = '''      {removeOpen && detail && (\n        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setRemoveOpen(false)}>\n          <div className="holdings-dialog holdings-remove-dialog" role="dialog" aria-modal="true" aria-label="목록에서 제거" onMouseDown={(event) => event.stopPropagation()}>\n            <div className="holdings-dialog-head">\n              <div>\n                <h2>목록에서 제거</h2>\n                <p>{detail.name}을(를) 내 종목 목록에서 제거할까요?</p>\n              </div>\n              <button type="button" onClick={() => setRemoveOpen(false)} aria-label="닫기">×</button>\n            </div>\n            <div className="holdings-remove-copy">저장된 분석 기록과 과거 변화 기록은 삭제되지 않습니다.</div>\n            <div className="holdings-dialog-actions">\n              <button type="button" className="holdings-secondary" onClick={() => setRemoveOpen(false)}>취소</button>\n              <button type="button" className="holdings-remove-confirm" onClick={() => void setSelectedWatch(false, true)}>제거</button>\n            </div>\n          </div>\n        </div>\n      )}\n\n      {addOpen && (\n        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setAddOpen(false)}>\n'''
    if source.count(dialog_anchor) != 1:
        fail("HoldingsWorkspace add dialog structure changed.")
    return source.replace(dialog_anchor, dialog_replacement, 1)


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-G.1/G.2 — 목록 제거 UX + 확정 일봉 차트")
    print("Theme support: LIGHT + DARK")
    print("Chart data: LOCAL MARKET STORE ONLY")
    print("Paid API/service: NO")
    print("KIS/Realtime: NO")
    print("Actual DB stock delete: NO")

    required = (
        HOLDINGS_API,
        HOLDINGS_SERVICE,
        HOLDINGS_WORKSPACE,
        HOLDINGS_CSS,
        GLOBAL_STYLES,
        PACKAGE_JSON,
    )
    for path in required:
        if not path.is_file():
            fail(f"Required file missing: {path}")
    for path in (CHART_SERVICE, CHART_TEST, PRICE_CHART):
        if path.exists():
            fail(f"Target already exists: {path}")

    style_text = GLOBAL_STYLES.read_text(encoding="utf-8-sig")
    for marker in ('html[data-theme="dark"]', 'html[data-theme="light"]', '--bg-surface:', '--text-primary:'):
        if marker not in style_text:
            fail(f"Existing Light/Dark theme marker missing: {marker}")

    package_before = PACKAGE_JSON.read_text(encoding="utf-8-sig")
    for dependency in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly"):
        if dependency in package_before.lower():
            fail(f"Unexpected chart dependency already present: {dependency}")

    originals = {
        HOLDINGS_API: HOLDINGS_API.read_text(encoding="utf-8-sig"),
        HOLDINGS_SERVICE: HOLDINGS_SERVICE.read_text(encoding="utf-8-sig"),
        HOLDINGS_WORKSPACE: HOLDINGS_WORKSPACE.read_text(encoding="utf-8-sig"),
        HOLDINGS_CSS: HOLDINGS_CSS.read_text(encoding="utf-8-sig"),
    }
    patched = {
        HOLDINGS_API: patch_backend_api(originals[HOLDINGS_API]),
        HOLDINGS_SERVICE: patch_frontend_service(originals[HOLDINGS_SERVICE]),
        HOLDINGS_WORKSPACE: patch_workspace(originals[HOLDINGS_WORKSPACE]),
        HOLDINGS_CSS: originals[HOLDINGS_CSS] + CSS_APPEND,
    }

    protected = {
        ROOT / "backend" / "app" / "backtest" / "scanner.py": None,
        ROOT / "backend" / "app" / "backtest" / "production_exit_policy.py": None,
        ROOT / "backend" / "app" / "strategy": None,
        ROOT / "backend" / "app" / "integrations" / "kis": None,
        GLOBAL_STYLES: None,
        PACKAGE_JSON: None,
    }
    for path in list(protected):
        protected[path] = tree_hash(path)

    created: list[Path] = []
    modified: list[Path] = []
    try:
        CHART_SERVICE.write_text(CHART_SERVICE_CONTENT, encoding="utf-8", newline="\n")
        created.append(CHART_SERVICE)
        CHART_TEST.write_text(CHART_TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(CHART_TEST)
        PRICE_CHART.write_text(PRICE_CHART_CONTENT, encoding="utf-8", newline="\n")
        created.append(PRICE_CHART)
        for path, content in patched.items():
            path.write_text(content, encoding="utf-8", newline="\n")
            modified.append(path)

        print()
        print("=== HOLD.1-G.1/G.2 STATIC CONTRACT ===")
        backend_source = HOLDINGS_API.read_text(encoding="utf-8")
        chart_source = CHART_SERVICE.read_text(encoding="utf-8")
        frontend_source = HOLDINGS_WORKSPACE.read_text(encoding="utf-8")
        service_source = HOLDINGS_SERVICE.read_text(encoding="utf-8")
        chart_ui_source = PRICE_CHART.read_text(encoding="utf-8")
        css_source = HOLDINGS_CSS.read_text(encoding="utf-8")
        package_now = PACKAGE_JSON.read_text(encoding="utf-8-sig")

        checks = {
            "chart API route": '/stocks/{stock_id}/chart' in backend_source,
            "chart ranges": all(value in chart_source for value in ('"1m": 22', '"3m": 66', '"6m": 132', '"1y": 252')),
            "Market Store read-only": "mode=ro" in chart_source,
            "confirmed EOD gate": "d.status='data'" in chart_source and "d.kind='stock'" in chart_source,
            "network calls": all(token not in chart_source.lower() for token in ("requests", "httpx", "websocket")),
            "KIS chart calls": "kis" not in chart_source.lower() and "kis" not in chart_ui_source.lower(),
            "paid chart dependency": package_now == package_before,
            "SVG chart": "<svg" in chart_ui_source and "holdings-candle" in chart_ui_source,
            "live-ready prop": "liveBar" in chart_ui_source,
            "analysis overlays": all(label in chart_ui_source for label in ("기준가", "손절 기준", "1차 목표", "2차 목표", "분석 기준일")),
            "remove UI": "목록에서 제거" in frontend_source and "removeOpen" in frontend_source,
            "remove preserves history": "저장된 분석 기록과 과거 변화 기록은 삭제되지 않습니다." in frontend_source,
            "no DELETE API": 'method: "DELETE"' not in service_source and "deleteHolding" not in service_source,
            "watch-state removal": "setWatchEnabled(detail.stock_id, enabled)" in frontend_source,
            "Light/Dark tokens": "var(--bg-surface" in css_source and "var(--text-primary" in css_source,
            "no theme fork": 'html[data-theme=' not in CSS_APPEND and ':root' not in CSS_APPEND,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        run(
            [sys.executable, "-m", "pytest", "backend/tests/test_holdings_chart_hold1g.py", "backend/tests/test_holdings_api_hold1f.py", "-q"],
            ROOT,
            "Focused backend regression",
        )

        smoke = r'''import sys
sys.path.insert(0, "backend")
from app.holdings.chart import HoldingsChartService
result = HoldingsChartService().load(market="KOSPI", ticker="005930", chart_range="1m")
assert result.count > 0
assert result.count <= 22
assert result.source == "MARKET_STORE_CONFIRMED_EOD"
print("REAL MARKET STORE CHART: PASS")
print("RANGE:", result.from_date, "->", result.to_date)
print("BARS:", result.count)
print("NETWORK CALLS: 0")
print("KIS CALLS: 0")
print("MARKET STORE WRITE: 0 (SQLite mode=ro)")
'''
        run([sys.executable, "-c", smoke], ROOT, "Real Market Store read-only smoke")

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        for path, before_hash in protected.items():
            if tree_hash(path) != before_hash:
                fail(f"Protected source changed unexpectedly: {path}")

        print()
        print("HOLD.1-G.1/G.2 IMPLEMENTATION READY")
        print("Added:")
        print(" - backend/app/holdings/chart.py")
        print(" - backend/tests/test_holdings_chart_hold1g.py")
        print(" - frontend/src/components/HoldingsPriceChart.tsx")
        print("Modified:")
        print(" - backend/app/api/holdings.py (read-only chart route only)")
        print(" - frontend/src/services/holdingsApi.ts")
        print(" - frontend/src/components/HoldingsWorkspace.tsx")
        print(" - frontend/src/holdings.css")
        print("List removal UX: PASS")
        print("Physical monitored_stock delete: NO")
        print("1M/3M/6M/1Y confirmed EOD chart: PASS")
        print("OHLCV + volume: PASS")
        print("Analysis price overlays: PASS")
        print("Dark mode: existing tokens reused")
        print("Light mode: existing tokens reused")
        print("External API calls for chart: 0")
        print("KIS calls for chart: 0")
        print("Paid service/dependency: 0")
        print("Realtime overlay: NO (HOLD.1-H next)")
        print("Frontend build: PASS")
        print()
        print("NEXT: visual UAT — remove one watch-only stock, then check 1M/3M/6M/1Y chart in Dark + Light.")
        return 0

    except Exception:
        for path in reversed(modified):
            path.write_text(originals[path], encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — G.1/G.2 changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
