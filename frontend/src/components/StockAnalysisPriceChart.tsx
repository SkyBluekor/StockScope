import { useEffect, useMemo, useState } from "react";
import {
  fetchStockChart,
  prepareStockChartWithProgress,
  type StockChartRange,
  type StockChartResponse,
  type StrategyAnalysis,
} from "../services/api";

const RANGE_OPTIONS: Array<{ key: StockChartRange; label: string }> = [
  { key: "1m", label: "1개월" },
  { key: "3m", label: "3개월" },
  { key: "6m", label: "6개월" },
  { key: "1y", label: "1년" },
];

const WIDTH = 840;
const HEIGHT = 300;
const LEFT = 54;
const RIGHT = 72;
const TOP = 20;
const PRICE_BOTTOM = 218;
const VOLUME_TOP = 238;
const VOLUME_BOTTOM = 280;

function num(value: string | number | null | undefined) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fmt(value: number) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);
}

type Props = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  analysis: StrategyAnalysis | null;
};

export default function StockAnalysisPriceChart({ code, market, analysis }: Props) {
  const [range, setRange] = useState<StockChartRange>("3m");
  const [chart, setChart] = useState<StockChartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [progress, setProgress] = useState<{ current: number; required: number; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setProgress(null);
    void fetchStockChart(code, market, range)
      .then((result) => {
        if (!cancelled) setChart(result);
      })
      .catch((reason) => {
        if (!cancelled) {
          setChart(null);
          setError(reason instanceof Error ? reason.message : "차트를 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [code, market, range]);

  const model = useMemo(() => {
    if (!chart?.bars.length) return null;
    const bars = chart.bars.map((bar) => ({
      ...bar,
      o: num(bar.open)!,
      h: num(bar.high)!,
      l: num(bar.low)!,
      c: num(bar.close)!,
      v: num(bar.volume) ?? 0,
    }));
    const plan = analysis?.risk_analysis.selected_plan ?? null;
    const levels = [
      { key: "entry", label: "기준가", value: plan?.entry_price ?? analysis?.data_freshness.eod_close ?? null },
      { key: "stop", label: "손절", value: plan?.invalidation_price ?? null },
      { key: "target1", label: "1차 목표", value: plan?.target1_price ?? null },
      { key: "target2", label: "2차 목표", value: plan?.target2_price ?? null },
    ].filter((item): item is { key: string; label: string; value: number } => item.value != null && Number.isFinite(item.value));

    const low = Math.min(...bars.map((bar) => bar.l));
    const high = Math.max(...bars.map((bar) => bar.h));
    const levelLow = levels.length ? Math.min(...levels.map((level) => level.value)) : low;
    const levelHigh = levels.length ? Math.max(...levels.map((level) => level.value)) : high;
    const rawMin = Math.min(low, levelLow);
    const rawMax = Math.max(high, levelHigh);
    const spread = Math.max(rawMax - rawMin, rawMax * .02, 1);
    const min = rawMin - spread * .08;
    const max = rawMax + spread * .08;
    const y = (price: number) => TOP + ((max - price) / (max - min)) * (PRICE_BOTTOM - TOP);
    const plotWidth = WIDTH - LEFT - RIGHT;
    const step = plotWidth / bars.length;
    const x = (index: number) => LEFT + step * (index + .5);
    const maxVolume = Math.max(...bars.map((bar) => bar.v), 1);
    const volumeY = (volume: number) => VOLUME_BOTTOM - (volume / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);
    const candleWidth = Math.max(1.2, Math.min(7.5, step * .55));
    const ticks = Array.from({ length: 5 }, (_, index) => {
      const ratio = index / 4;
      return { y: TOP + (PRICE_BOTTOM - TOP) * ratio, value: max - (max - min) * ratio };
    });
    return { bars, levels, y, x, volumeY, candleWidth, ticks, plotWidth };
  }, [chart, analysis]);

  async function prepareRange() {
    if (preparing) return;
    setPreparing(true);
    setError(null);
    try {
      await prepareStockChartWithProgress(code, market, range, (item) => {
        setProgress({ current: item.current ?? 0, required: item.required ?? 0, message: item.message });
      });
      setChart(await fetchStockChart(code, market, range));
      setProgress(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "차트 데이터를 준비하지 못했습니다.");
    } finally {
      setPreparing(false);
    }
  }

  const partial = Boolean(chart && chart.count < chart.requested_bars);

  return (
    <section className="stock-analysis-chart" aria-label="확정 일봉 차트">
      <div className="stock-analysis-chart-head">
        <div>
          <span>CONFIRMED EOD</span>
          <h3>확정 일봉</h3>
          <small>{chart?.to_date ? `${chart.to_date.replace(/-/g, ".")}까지` : "Market Store 기준"}</small>
        </div>
        <div className="stock-analysis-chart-ranges">
          {RANGE_OPTIONS.map((option) => (
            <button key={option.key} type="button" className={range === option.key ? "active" : ""} onClick={() => setRange(option.key)} disabled={preparing}>
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {model && (
        <div className="stock-analysis-chart-levels">
          {model.levels.map((level) => (
            <span key={level.key} className={level.key}><i /><b>{level.label}</b><strong>{fmt(level.value)}</strong></span>
          ))}
        </div>
      )}

      {partial && (
        <div className="stock-analysis-chart-coverage">
          <span>{preparing ? progress?.message ?? "과거 데이터를 준비하고 있습니다." : `현재 ${chart?.count ?? 0} / ${chart?.requested_bars ?? 0}거래일`}</span>
          {!preparing && <button type="button" onClick={() => void prepareRange()}>이 기간 데이터 준비</button>}
        </div>
      )}

      {loading && !chart ? (
        <div className="stock-analysis-chart-state">확정 일봉을 불러오는 중입니다.</div>
      ) : error && !model ? (
        <div className="stock-analysis-chart-state error">{error}</div>
      ) : !model ? (
        <div className="stock-analysis-chart-state">표시할 확정 일봉이 없습니다.</div>
      ) : (
        <div className="stock-analysis-chart-canvas">
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${range} 확정 일봉 캔들 차트`}>
            <g className="stock-chart-grid">
              {model.ticks.map((tick) => (
                <g key={tick.y}>
                  <line x1={LEFT} x2={WIDTH - RIGHT} y1={tick.y} y2={tick.y} />
                  <text x={WIDTH - RIGHT + 8} y={tick.y + 4}>{fmt(tick.value)}</text>
                </g>
              ))}
            </g>
            {model.levels.map((level) => (
              <line key={level.key} className={`stock-chart-level-line ${level.key}`} x1={LEFT} x2={WIDTH - RIGHT} y1={model.y(level.value)} y2={model.y(level.value)} />
            ))}
            <g className="stock-chart-candles">
              {model.bars.map((bar, index) => {
                const x = model.x(index);
                const openY = model.y(bar.o);
                const closeY = model.y(bar.c);
                const highY = model.y(bar.h);
                const lowY = model.y(bar.l);
                const direction = bar.c > bar.o ? "up" : bar.c < bar.o ? "down" : "flat";
                const volumeY = model.volumeY(bar.v);
                return (
                  <g className={direction} key={bar.date}>
                    <line x1={x} x2={x} y1={highY} y2={lowY} />
                    <rect x={x - model.candleWidth / 2} y={Math.min(openY, closeY)} width={model.candleWidth} height={Math.max(1.2, Math.abs(closeY - openY))} />
                    <rect className="volume" x={x - model.candleWidth / 2} y={volumeY} width={model.candleWidth} height={Math.max(1, VOLUME_BOTTOM - volumeY)} />
                  </g>
                );
              })}
            </g>
            <text className="stock-chart-date start" x={LEFT} y={HEIGHT - 5}>{model.bars[0]?.date.slice(5).replace("-", ".")}</text>
            <text className="stock-chart-date end" x={WIDTH - RIGHT} y={HEIGHT - 5}>{model.bars[model.bars.length - 1]?.date.slice(5).replace("-", ".")}</text>
          </svg>
        </div>
      )}

      {error && model && <div className="stock-analysis-chart-inline-error">{error}</div>}
    </section>
  );
}
