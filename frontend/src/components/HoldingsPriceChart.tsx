import { useEffect, useMemo, useState, type PointerEvent } from "react";
import {
  getHoldingChart,
  type HoldingAnalysis,
  type HoldingChartBar,
  type HoldingChartRange,
  type HoldingChartResponse,
} from "../services/holdingsApi";

const RANGE_OPTIONS: Array<{ key: HoldingChartRange; label: string }> = [
  { key: "1m", label: "1개월" },
  { key: "3m", label: "3개월" },
  { key: "6m", label: "6개월" },
  { key: "1y", label: "1년" },
];

const W = 920;
const H = 292;
const LEFT = 58;
const RIGHT = 96;
const TOP = 18;
const PRICE_BOTTOM = 210;
const VOLUME_TOP = 229;
const VOLUME_BOTTOM = 272;

function number(value: string | null | undefined) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatPrice(value: number) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);
}

function formatVolume(value: number) {
  return new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function shortDate(value: string) {
  return value.length >= 10 ? `${value.slice(5, 7)}.${value.slice(8, 10)}` : value;
}

function mergeBars(history: HoldingChartBar[], liveBar: HoldingChartBar | null) {
  if (!liveBar) return history;
  if (history.length === 0) return [liveBar];
  const last = history[history.length - 1];
  if (last.date === liveBar.date) return [...history.slice(0, -1), liveBar];
  return [...history, liveBar];
}

type Props = {
  stockId: string;
  analysis: HoldingAnalysis | null;
  liveBar?: HoldingChartBar | null;
};

export default function HoldingsPriceChart({ stockId, analysis, liveBar = null }: Props) {
  const [range, setRange] = useState<HoldingChartRange>("1m");
  const [chart, setChart] = useState<HoldingChartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setChart(null);
    setHoverIndex(null);
    void getHoldingChart(stockId, range)
      .then((result) => {
        if (!cancelled) setChart(result);
      })
      .catch((loadError) => {
        if (cancelled) return;
        setChart(null);
        setError(loadError instanceof Error ? loadError.message : "차트 데이터를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stockId, range]);

  const bars = useMemo(() => mergeBars(chart?.bars ?? [], liveBar), [chart, liveBar]);

  const model = useMemo(() => {
    const numeric = bars
      .map((bar) => ({
        ...bar,
        o: number(bar.open),
        h: number(bar.high),
        l: number(bar.low),
        c: number(bar.close),
        v: number(bar.volume),
      }))
      .filter((bar) => bar.o != null && bar.h != null && bar.l != null && bar.c != null && bar.v != null);

    if (numeric.length === 0) return null;

    const levels = [
      { key: "reference", label: "기준가", value: number(analysis?.reference_price) },
      { key: "stop", label: "손절 기준", value: number(analysis?.stop_price) },
      { key: "target1", label: "1차 목표", value: number(analysis?.target1_price) },
      { key: "target2", label: "2차 목표", value: number(analysis?.target2_price) },
    ].filter((item): item is { key: string; label: string; value: number } => item.value != null);

    const priceValues = numeric.flatMap((bar) => [bar.h!, bar.l!]).concat(levels.map((item) => item.value));
    let minPrice = Math.min(...priceValues);
    let maxPrice = Math.max(...priceValues);
    const rawRange = Math.max(maxPrice - minPrice, maxPrice * 0.015, 1);
    minPrice -= rawRange * 0.08;
    maxPrice += rawRange * 0.08;
    const priceRange = maxPrice - minPrice || 1;
    const maxVolume = Math.max(...numeric.map((bar) => bar.v!), 1);
    const plotWidth = W - LEFT - RIGHT;
    const step = plotWidth / numeric.length;
    const candleWidth = Math.max(1.2, Math.min(8.5, step * 0.56));

    const yPrice = (value: number) => TOP + ((maxPrice - value) / priceRange) * (PRICE_BOTTOM - TOP);
    const xAt = (index: number) => LEFT + step * (index + 0.5);
    const volumeY = (value: number) => VOLUME_BOTTOM - (value / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);

    const tickIndexes = Array.from(new Set([
      0,
      Math.floor((numeric.length - 1) * 0.25),
      Math.floor((numeric.length - 1) * 0.5),
      Math.floor((numeric.length - 1) * 0.75),
      numeric.length - 1,
    ])).sort((a, b) => a - b);

    const yTicks = Array.from({ length: 5 }, (_, index) => {
      const ratio = index / 4;
      const value = maxPrice - (maxPrice - minPrice) * ratio;
      return { value, y: TOP + (PRICE_BOTTOM - TOP) * ratio };
    });

    const analysisIndex = analysis
      ? numeric.findIndex((bar) => bar.date === analysis.market_date)
      : -1;

    return {
      numeric,
      levels,
      xAt,
      yPrice,
      volumeY,
      candleWidth,
      tickIndexes,
      yTicks,
      analysisIndex,
      plotWidth,
      step,
    };
  }, [bars, analysis]);

  function handlePointerMove(event: PointerEvent<SVGRectElement>) {
    if (!model) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const chartX = ratio * W;
    const raw = Math.floor((chartX - LEFT) / model.step);
    const index = Math.max(0, Math.min(model.numeric.length - 1, raw));
    setHoverIndex(index);
  }

  const hovered = model && hoverIndex != null ? model.numeric[hoverIndex] : null;

  return (
    <section className="holdings-chart-panel">
      <div className="holdings-chart-head">
        <div>
          <h3>확정 일봉</h3>
          <span>
            {liveBar ? "오늘 캔들 실시간 반영" : chart?.to_date ? `${chart.to_date.replace(/-/g, ".")}까지` : "Market Store 기준"}
          </span>
        </div>
        <div className="holdings-chart-ranges" aria-label="차트 기간">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={range === option.key ? "active" : ""}
              onClick={() => setRange(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {loading && !chart ? (
        <div className="holdings-chart-state">확정 일봉을 불러오는 중입니다.</div>
      ) : error ? (
        <div className="holdings-chart-state error">{error}</div>
      ) : !model ? (
        <div className="holdings-chart-state">표시할 확정 일봉이 없습니다.</div>
      ) : (
        <div className="holdings-chart-canvas">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={`${range} 확정 일봉 캔들 차트`}
            onPointerLeave={() => setHoverIndex(null)}
          >
            <g className="holdings-chart-grid">
              {model.yTicks.map((tick) => (
                <g key={tick.y}>
                  <line x1={LEFT} x2={W - RIGHT} y1={tick.y} y2={tick.y} />
                  <text x={W - RIGHT + 8} y={tick.y + 4}>{formatPrice(tick.value)}</text>
                </g>
              ))}
              <line x1={LEFT} x2={W - RIGHT} y1={VOLUME_TOP - 8} y2={VOLUME_TOP - 8} />
            </g>

            {model.levels.map((level) => {
              const y = model.yPrice(level.value);
              return (
                <g key={level.key} className={`holdings-level ${level.key}`}>
                  <line className="holdings-level-line" x1={LEFT} x2={W - RIGHT} y1={y} y2={y} />
                  <text className="holdings-level-label" x={W - RIGHT + 8} y={y - 4}>{level.label}</text>
                </g>
              );
            })}

            {model.analysisIndex >= 0 && (
              <g className="holdings-analysis-marker">
                <line
                  x1={model.xAt(model.analysisIndex)}
                  x2={model.xAt(model.analysisIndex)}
                  y1={TOP}
                  y2={VOLUME_BOTTOM}
                />
                <text x={model.xAt(model.analysisIndex)} y={TOP + 12}>분석 기준일</text>
              </g>
            )}

            <g className="holdings-candles">
              {model.numeric.map((bar, index) => {
                const x = model.xAt(index);
                const openY = model.yPrice(bar.o!);
                const closeY = model.yPrice(bar.c!);
                const highY = model.yPrice(bar.h!);
                const lowY = model.yPrice(bar.l!);
                const bodyY = Math.min(openY, closeY);
                const bodyHeight = Math.max(1.2, Math.abs(closeY - openY));
                const direction = bar.c! > bar.o! ? "up" : bar.c! < bar.o! ? "down" : "flat";
                const volumeY = model.volumeY(bar.v!);
                return (
                  <g key={`${bar.date}-${index}`} className={`holdings-candle ${direction}`}>
                    <line x1={x} x2={x} y1={highY} y2={lowY} />
                    <rect
                      x={x - model.candleWidth / 2}
                      y={bodyY}
                      width={model.candleWidth}
                      height={bodyHeight}
                    />
                    <rect
                      className="volume"
                      x={x - model.candleWidth / 2}
                      y={volumeY}
                      width={model.candleWidth}
                      height={Math.max(1, VOLUME_BOTTOM - volumeY)}
                    />
                  </g>
                );
              })}
            </g>

            <g className="holdings-chart-dates">
              {model.tickIndexes.map((index) => (
                <text key={index} x={model.xAt(index)} y={H - 5}>{shortDate(model.numeric[index].date)}</text>
              ))}
            </g>

            {hoverIndex != null && (
              <line
                className="holdings-chart-hover-line"
                x1={model.xAt(hoverIndex)}
                x2={model.xAt(hoverIndex)}
                y1={TOP}
                y2={VOLUME_BOTTOM}
              />
            )}

            <rect
              className="holdings-chart-hit"
              x={LEFT}
              y={TOP}
              width={model.plotWidth}
              height={VOLUME_BOTTOM - TOP}
              onPointerMove={handlePointerMove}
            />
          </svg>

          {hovered && (
            <div className="holdings-chart-tooltip">
              <strong>{hovered.date.replace(/-/g, ".")}</strong>
              <span>시가 <b>{formatPrice(hovered.o!)}</b></span>
              <span>고가 <b>{formatPrice(hovered.h!)}</b></span>
              <span>저가 <b>{formatPrice(hovered.l!)}</b></span>
              <span>종가 <b>{formatPrice(hovered.c!)}</b></span>
              <span>거래량 <b>{formatVolume(hovered.v!)}</b></span>
            </div>
          )}
        </div>
      )}

      <div className="holdings-chart-foot">
        <span>과거 구간은 로컬 Market Store의 확정 일봉만 사용합니다.</span>
        {analysis && <span>분석 기준일 {analysis.market_date.replace(/-/g, ".")}</span>}
      </div>
    </section>
  );
}
