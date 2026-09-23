import { useEffect, useMemo, useState, type PointerEvent } from "react";
import {
  getHoldingChart,
  type HoldingAnalysis,
  type HoldingDecisionContext,
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
const RIGHT = 74;
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
  refreshKey?: number;
  decisionContext?: HoldingDecisionContext | null;
};

export default function HoldingsPriceChart({
  stockId,
  analysis,
  liveBar = null,
  refreshKey = 0,
  decisionContext = null,
}: Props) {
  const [range, setRange] = useState<HoldingChartRange>("1m");
  const [chart, setChart] = useState<HoldingChartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
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
  }, [stockId, range, refreshKey]);

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
      { key: "stop", label: "손절", value: number(analysis?.stop_price) },
      { key: "target1", label: "1차 목표", value: number(analysis?.target1_price) },
      { key: "target2", label: "2차 목표", value: number(analysis?.target2_price) },
    ].filter((item): item is { key: string; label: string; value: number } => item.value != null);

    const lowest = Math.min(...numeric.map((bar) => bar.l!));
    const highest = Math.max(...numeric.map((bar) => bar.h!));
    const visibleRange = Math.max(highest - lowest, highest * 0.015, 1);
    const minPrice = lowest - visibleRange * 0.08;
    const maxPrice = highest + visibleRange * 0.08;
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

    const plottedLevels = levels.map((level) => ({
      ...level,
      position: level.value > maxPrice ? "above" : level.value < minPrice ? "below" : "inside",
    }));

    return {
      numeric,
      levels: plottedLevels,
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
  const chartDate = chart?.to_date ?? null;
  const analysisDate = analysis?.market_date ?? null;
  const analysisBehindChart = Boolean(chartDate && analysisDate && analysisDate < chartDate);

  return (
    <section className="holdings-chart-panel">
      <div className="holdings-chart-head">
        <div>
          <h3>확정 일봉</h3>
          <span>{chartDate ? `${chartDate.replace(/-/g, ".")}까지` : "저장된 확정 데이터 기준"}</span>
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

      {decisionContext && ["STOP_BREACHED", "TARGET1_REACHED", "TARGET2_REACHED"].includes(
        decisionContext.previous_plan.state,
      ) && (
        <div className={`holdings-chart-plan-event ${decisionContext.previous_plan.state.toLowerCase()}`}>
          <span>이전 계획</span>
          <strong>{decisionContext.previous_plan.label}</strong>
          {decisionContext.previous_plan.previous_market_date && (
            <small>{decisionContext.previous_plan.previous_market_date.replace(/-/g, ".")} 기준</small>
          )}
        </div>
      )}

      {model && (
        <div className="holdings-chart-levels" aria-label="분석 가격 기준">
          {model.levels.map((level) => (
            <span key={level.key} className={`holdings-chart-level ${level.key}`}>
              <i aria-hidden="true" />
              <b>{level.position === "above" ? "↑ " : level.position === "below" ? "↓ " : ""}{level.label}</b>
              <strong>{formatPrice(level.value)}</strong>
            </span>
          ))}
        </div>
      )}

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

            {model.levels
              .filter((level) => level.position === "inside")
              .map((level) => {
                const y = model.yPrice(level.value);
                return (
                  <line
                    key={level.key}
                    className={`holdings-level-line ${level.key}`}
                    x1={LEFT}
                    x2={W - RIGHT}
                    y1={y}
                    y2={y}
                  />
                );
              })}

            {model.analysisIndex >= 0 && (
              <line
                className="holdings-analysis-marker"
                x1={model.xAt(model.analysisIndex)}
                x2={model.xAt(model.analysisIndex)}
                y1={TOP}
                y2={VOLUME_BOTTOM}
              />
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
        <span>{chartDate ? `차트 최신일 ${chartDate.replace(/-/g, ".")}` : "저장된 확정 일봉을 사용합니다."}</span>
        {analysisDate && (
          <span className={analysisBehindChart ? "stale" : ""}>
            분석 기준일 {analysisDate.replace(/-/g, ".")}
            {analysisBehindChart ? " · 새로고침 필요" : ""}
          </span>
        )}
      </div>
    </section>
  );
}
