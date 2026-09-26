import type { ReactNode } from "react";
import type { StockContext, StockSearchItem, StrategyAnalysis } from "../services/api";
import StockAnalysisPriceChart from "./StockAnalysisPriceChart";
import StockNewsPanel from "./StockNewsPanel";
import StockTrackingActions from "./StockTrackingActions";
import "../stock-analysis.css";

type Props = {
  stockQuery: string;
  stockSearchBusy: boolean;
  stockSearchOpen: boolean;
  stockSearchResults: StockSearchItem[];
  selectedStockName: string;
  stockCode: string;
  stockMarket: "KOSPI" | "KOSDAQ";
  stockBusy: boolean;
  stockMessage: string;
  stock: StockContext | null;
  strategyAnalysis: StrategyAnalysis | null;
  strategyBusy: boolean;
  analysisOutdated: boolean;
  onQueryChange: (value: string) => void;
  onSearchFocus: () => void;
  onChooseStock: (item: StockSearchItem) => void;
  onRetryContext: () => void;
  onRunAnalysis: () => void;
  strategyMessage: string;
  scannerOrigin: boolean;
  onBackToScanner: () => void;
  onOpenHoldings: (target: { market: "KOSPI" | "KOSDAQ"; ticker: string; name: string }) => void;
  children?: ReactNode;
};

const strategyLabel: Record<string, string> = {
  trend_following: "추세추종",
  pullback: "눌림 후 반등",
  breakout: "돌파",
  support_bounce: "지지선 반등",
  oversold_bounce: "과매도 반등",
  range_trading: "박스권",
  momentum_continuation: "모멘텀 지속",
  volatility_squeeze: "변동성 압축",
  ma20_rebound: "20일선 반등",
  trend_recovery: "추세 회복",
  no_trade: "관망",
};

function formatNumber(value: number | null | undefined, suffix = "") {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}${suffix}`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function signedRate(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function trendLabel(analysis: StrategyAnalysis) {
  const slope = analysis.technical.ma20_slope_pct;
  if (slope == null) return "확인 필요";
  if (slope > 0.5) return "상승 흐름";
  if (slope < -0.5) return "하락 흐름";
  return "횡보";
}

function momentumLabel(analysis: StrategyAnalysis) {
  const rsi = analysis.technical.rsi14;
  if (rsi == null) return "확인 필요";
  if (rsi >= 70) return "과열 주의";
  if (rsi >= 55) return "강함";
  if (rsi >= 45) return "보통";
  if (rsi >= 30) return "약함";
  return "과매도 구간";
}

function volumeLabel(analysis: StrategyAnalysis) {
  const ratio = analysis.technical.volume_ratio_20;
  if (ratio == null) return "확인 필요";
  if (ratio >= 1.5) return "크게 증가";
  if (ratio >= 1.05) return "개선";
  if (ratio >= 0.8) return "보통";
  return "감소";
}

function volatilityLabel(analysis: StrategyAnalysis) {
  const atr = analysis.technical.atr_pct;
  if (atr == null) return "확인 필요";
  if (atr >= 5) return "높음";
  if (atr >= 3) return "주의";
  return "보통";
}

export default function StockAnalysisWorkspace({
  stockQuery,
  stockSearchBusy,
  stockSearchOpen,
  stockSearchResults,
  selectedStockName,
  stockCode,
  stockMarket,
  stockBusy,
  stockMessage,
  stock,
  strategyAnalysis,
  strategyBusy,
  analysisOutdated,
  onQueryChange,
  onSearchFocus,
  onChooseStock,
  onRetryContext,
  onRunAnalysis,
  strategyMessage,
  scannerOrigin,
  onBackToScanner,
  onOpenHoldings,
  children,
}: Props) {
  const selectedStrategy = strategyAnalysis?.top_strategy ?? strategyAnalysis?.best_regular_strategy ?? null;
  const plan = strategyAnalysis?.risk_analysis.selected_plan ?? null;
  const summary = strategyAnalysis?.analysis_summary ?? null;
  const positiveSignals = summary
    ? [...summary.priority_signals, ...summary.other_signals].filter((item) => item.status === "POSITIVE").slice(0, 4)
    : [];
  const cautionSignals = summary
    ? [...summary.priority_signals, ...summary.other_signals].filter((item) => item.status === "NEGATIVE" || item.status === "CAUTION").slice(0, 4)
    : [];
  const styleContext = summary?.entry_timing.style_context ?? null;
  const strategyBasisDate = strategyAnalysis?.data_freshness.eod_date ?? strategyAnalysis?.data_date ?? null;

  return (
    <section className="stock-analysis-workspace">
      <header className="stock-analysis-page-head">
        <div>
          <span className="eyebrow">STOCK ANALYSIS</span>
          <h1>종목 분석</h1>
          <p>종목의 현재 상태와 전략 근거를 최신 확정 일봉 기준으로 확인합니다.</p>
        </div>
      </header>

      {scannerOrigin && (
        <div className="stock-analysis-origin" role="status">
          <span>종목 후보 찾기에서 선택한 종목입니다.</span>
          <button type="button" onClick={onBackToScanner}>후보 목록으로 돌아가기</button>
        </div>
      )}

      <section className="stock-analysis-search" aria-label="분석 종목 검색">
        <div className="stock-search-box">
          <input
            value={stockQuery}
            onChange={(event) => onQueryChange(event.target.value)}
            onFocus={onSearchFocus}
            onKeyDown={(event) => {
              if (event.key === "Enter" && stockSearchResults[0]) {
                event.preventDefault();
                onChooseStock(stockSearchResults[0]);
              }
            }}
            placeholder="종목명 또는 6자리 코드 검색 · 예: 삼성전자, 005930"
            autoComplete="off"
          />
          {stockSearchBusy && <span className="search-spinner">검색 중</span>}
          {stockSearchOpen && stockQuery.trim().length >= 2 && (
            <div className="stock-suggestions">
              {stockSearchResults.map((item) => (
                <button type="button" key={`${item.market}-${item.code}`} onMouseDown={() => onChooseStock(item)}>
                  <span className={`market-badge ${item.market.toLowerCase()}`}>{item.market}</span>
                  <div>
                    <strong>{item.name}</strong>
                    <small>{item.code} · {item.stock_type || item.security_group || "주식"}</small>
                  </div>
                  <em>선택</em>
                </button>
              ))}
              {!stockSearchBusy && stockSearchResults.length === 0 && (
                <div className="search-empty">검색 결과가 없습니다.</div>
              )}
            </div>
          )}
        </div>
        <div className="stock-analysis-search-state">
          <span>
            {selectedStockName
              ? stockBusy
                ? `${stockMarket} · ${stockCode} · 기본 정보 확인 중`
                : `${stockMarket} · ${stockCode}`
              : "분석할 종목을 검색하세요"}
          </span>
        </div>
      </section>

      {!stock ? (
        <>
          <div className="stock-analysis-empty">
            <strong>
              {selectedStockName
                ? stockBusy
                  ? "종목 기본 정보를 확인하고 있습니다."
                  : stockMessage
                : "분석할 종목을 선택하세요."}
            </strong>
            <p>
              {selectedStockName
                ? "종목을 선택하면 최근 확정 종가와 기업 기본정보를 자동으로 확인합니다."
                : "종목을 선택하면 최근 확정 종가와 기업 기본정보를 먼저 확인합니다."}
            </p>
            {selectedStockName && !stockBusy && (
              <button type="button" className="stock-analysis-context-retry" onClick={onRetryContext}>
                다시 확인
              </button>
            )}
          </div>
          {selectedStockName && stockCode && (
            <StockNewsPanel code={stockCode} market={stockMarket} companyLabel={selectedStockName} />
          )}
        </>
      ) : (
        <>
          <section className="stock-analysis-stock-head">
            <div>
              <div className="stock-analysis-identity">
                <h2>{stock.company.corp_name ?? stock.stock.name ?? selectedStockName}</h2>
                <span>{stock.code} · {stock.market}</span>
              </div>
              <div className="stock-analysis-price-line">
                <div>
                  <span>최근 확정 종가</span>
                  <strong>{formatNumber(stock.stock.close, "원")}</strong>
                </div>
                <div>
                  <span>전일 대비</span>
                  <strong className={(stock.stock.change_rate ?? 0) >= 0 ? "positive" : "negative"}>
                    {signedRate(stock.stock.change_rate)}
                  </strong>
                </div>
                <div>
                  <span>분석 기준</span>
                  <strong>{formatDate(stock.data_date)}</strong>
                </div>
              </div>
            </div>
            <div className="stock-analysis-head-actions">
              <small>기본 정보와 차트는 조회 즉시 표시됩니다.</small>
              <small>전략 계산은 아래에서 필요할 때 직접 실행합니다.</small>
            </div>
          </section>

          <StockTrackingActions
            code={stock.code}
            market={stock.market}
            name={stock.company.corp_name ?? stock.stock.name ?? selectedStockName}
            referencePrice={stock.stock.close}
            onOpenHoldings={onOpenHoldings}
          />

          <section className="stock-analysis-chart-stage">
            <StockAnalysisPriceChart code={stock.code} market={stock.market} analysis={strategyAnalysis} />
          </section>

          <section className={`stock-analysis-execution ${analysisOutdated ? "outdated" : strategyAnalysis ? "has-result" : "not-run"}`}>
            <div>
              <span>STOCKSCOPE STRATEGY</span>
              <h3>전략 분석</h3>
              {!strategyAnalysis ? (
                <p>{strategyBusy ? "확정 일봉 기준 전략 분석을 계산하고 있습니다." : strategyMessage}</p>
              ) : analysisOutdated ? (
                <p>입력값이 변경되었습니다. 아래 결과는 이전 입력 기준이며, 변경한 조건은 아직 반영되지 않았습니다.</p>
              ) : strategyBusy ? (
                <p>새 분석을 계산 중입니다. 현재 표시 중인 이전 완료 결과는 그대로 유지합니다.</p>
              ) : (
                <p>
                  현재 세션의 분석 결과를 표시 중입니다.
                  {strategyBasisDate ? ` · 기준 ${formatDate(strategyBasisDate)} 확정 일봉` : ""}
                </p>
              )}
            </div>

            {!strategyAnalysis ? (
              <button type="button" className="stock-analysis-run" onClick={onRunAnalysis} disabled={strategyBusy}>
                {strategyBusy ? "전략 분석 중..." : "전략 분석 실행"}
              </button>
            ) : analysisOutdated ? (
              <button type="button" className="stock-analysis-run" onClick={onRunAnalysis} disabled={strategyBusy}>
                {strategyBusy ? "전략 분석 중..." : "변경값으로 다시 분석"}
              </button>
            ) : (
              <details className="stock-analysis-run-options">
                <summary>분석 실행 옵션</summary>
                <div>
                  <strong>같은 조건으로 다시 분석</strong>
                  <p>현재 입력 조건으로 Strategy 분석을 새로 실행합니다. 기존 결과는 새 분석이 성공할 때까지 유지합니다.</p>
                  <button type="button" onClick={onRunAnalysis} disabled={strategyBusy}>
                    {strategyBusy ? "새 분석 계산 중..." : "같은 조건으로 다시 분석"}
                  </button>
                </div>
              </details>
            )}
          </section>

          {strategyAnalysis && summary && (
            <>
              <section className="stock-analysis-verdict" aria-label="현재 분석 요약">
                <div className="stock-analysis-verdict-main">
                  <span>신규 진입 판단</span>
                  <strong>{summary.action_plan.label || summary.verdict_label}</strong>
                  <h3>{summary.action_plan.headline}</h3>
                  <p>{summary.action_plan.summary || summary.summary}</p>
                </div>
                <div className="stock-analysis-strategy">
                  <span>현재 전략</span>
                  <strong>{selectedStrategy ? strategyLabel[selectedStrategy.strategy] ?? selectedStrategy.strategy : "뚜렷한 우선 전략 없음"}</strong>
                  <small>{summary.top_strategy.score == null ? "전략 적합도 계산 결과를 확인하세요." : `전략 형태 적합도 ${summary.top_strategy.score} / 100 · 진입 확률 점수가 아닙니다.`}</small>
                </div>
                <div className="stock-analysis-risk-summary">
                  <span>위험 수준</span>
                  <strong>{summary.risk_level}</strong>
                  <small>{summary.perspective}</small>
                </div>
              </section>

              <section className="stock-analysis-plan-section">
                <div className="stock-analysis-plan">
                  <div className="stock-analysis-section-title">
                    <div>
                      <span>PRICE PLAN</span>
                      <h3>가격 계획</h3>
                    </div>
                    <small>공식 확정 EOD 기준</small>
                  </div>
                  <dl>
                    <div><dt>기준가</dt><dd>{formatNumber(plan?.entry_price ?? strategyAnalysis.data_freshness.eod_close, "원")}</dd></div>
                    <div><dt>손절 기준</dt><dd>{formatNumber(plan?.invalidation_price, "원")}</dd></div>
                    <div><dt>1차 목표</dt><dd>{formatNumber(plan?.target1_price, "원")}</dd></div>
                    <div><dt>2차 목표</dt><dd>{formatNumber(plan?.target2_price, "원")}</dd></div>
                  </dl>
                  <p className="stock-analysis-plan-note">
                    참고가격 시나리오를 입력해도 이 영역의 공식 기준은 확정 일봉 분석입니다.
                  </p>
                </div>
              </section>

              <section className="stock-analysis-evidence">
                <div className="stock-analysis-section-heading">
                  <span>판단 근거</span>
                  <h3>왜 이런 판단인가</h3>
                  <p>현재 결론에 직접 영향을 주는 조건만 먼저 보여줍니다.</p>
                </div>
                <div className="stock-analysis-evidence-columns">
                  <article className="positive">
                    <div><span>긍정적인 조건</span><strong>{positiveSignals.length}개</strong></div>
                    {positiveSignals.length > 0 ? (
                      <ul>{positiveSignals.map((item) => <li key={item.key}><b>✓ {item.label}</b><span>{item.action_hint || item.detail}</span></li>)}</ul>
                    ) : <p>현재 우선순위 신호 중 뚜렷한 긍정 조건이 없습니다.</p>}
                  </article>
                  <article className="caution">
                    <div><span>아직 부족하거나 주의할 조건</span><strong>{cautionSignals.length}개</strong></div>
                    {cautionSignals.length > 0 ? (
                      <ul>{cautionSignals.map((item) => <li key={item.key}><b>△ {item.label}</b><span>{item.action_hint || item.detail}</span></li>)}</ul>
                    ) : <p>현재 우선순위 신호에서 큰 주의 조건이 확인되지 않았습니다.</p>}
                  </article>
                </div>
                {(summary.key_reasons.length > 0 || summary.change_conditions.length > 0) && (
                  <details className="stock-analysis-evidence-more">
                    <summary>전체 판단 근거와 변경 조건 보기</summary>
                    <div>
                      <article><strong>핵심 근거</strong><ul>{summary.key_reasons.map((item) => <li key={item}>{item}</li>)}</ul></article>
                      <article><strong>판단이 바뀌는 조건</strong><ul>{summary.change_conditions.map((item) => <li key={item}>{item}</li>)}</ul></article>
                    </div>
                  </details>
                )}
              </section>

              <section className="stock-analysis-health-grid">
                <article className="stock-analysis-technical-summary">
                  <div className="stock-analysis-section-heading">
                    <span>TECHNICAL</span>
                    <h3>기술적 상태</h3>
                  </div>
                  <dl>
                    <div><dt>추세</dt><dd>{trendLabel(strategyAnalysis)}</dd></div>
                    <div><dt>모멘텀</dt><dd>{momentumLabel(strategyAnalysis)}</dd></div>
                    <div><dt>거래량</dt><dd>{volumeLabel(strategyAnalysis)}</dd></div>
                    <div><dt>변동성</dt><dd>{volatilityLabel(strategyAnalysis)}</dd></div>
                    <div><dt>시장 대비</dt><dd>{strategyAnalysis.relative_strength.available ? strategyAnalysis.relative_strength.label : "데이터 없음"}</dd></div>
                    <div><dt>업종 대비</dt><dd>{strategyAnalysis.sector_relative_strength.available ? strategyAnalysis.sector_relative_strength.label : "데이터 없음"}</dd></div>
                  </dl>
                  <details>
                    <summary>상세 기술지표 보기</summary>
                    <div className="stock-analysis-technical-detail">
                      <span>MA5 <b>{formatNumber(strategyAnalysis.technical.ma5, "원")}</b></span>
                      <span>MA20 <b>{formatNumber(strategyAnalysis.technical.ma20, "원")}</b></span>
                      <span>MA60 <b>{formatNumber(strategyAnalysis.technical.ma60, "원")}</b></span>
                      <span>MA120 <b>{formatNumber(strategyAnalysis.technical.ma120, "원")}</b></span>
                      <span>RSI14 <b>{strategyAnalysis.technical.rsi14?.toFixed(1) ?? "-"}</b></span>
                      <span>ATR <b>{strategyAnalysis.technical.atr_pct == null ? "-" : `${strategyAnalysis.technical.atr_pct.toFixed(2)}%`}</b></span>
                      <span>거래량비 <b>{strategyAnalysis.technical.volume_ratio_20 == null ? "-" : `${strategyAnalysis.technical.volume_ratio_20.toFixed(2)}배`}</b></span>
                      <span>지지 <b>{formatNumber(strategyAnalysis.technical.support, "원")}</b></span>
                      <span>저항 <b>{formatNumber(strategyAnalysis.technical.resistance, "원")}</b></span>
                    </div>
                  </details>
                </article>

                <article className="stock-analysis-company-summary">
                  <div className="stock-analysis-section-heading">
                    <span>COMPANY</span>
                    <h3>기업 분석</h3>
                  </div>
                  {strategyAnalysis.fundamental.available ? (
                    <dl>
                      <div><dt>최근 매출 성장</dt><dd>{strategyAnalysis.fundamental.recent_performance?.revenue_yoy_pct == null ? "확인 필요" : signedRate(strategyAnalysis.fundamental.recent_performance.revenue_yoy_pct)}</dd></div>
                      <div><dt>영업이익 성장</dt><dd>{strategyAnalysis.fundamental.recent_performance?.operating_profit_yoy_pct == null ? "확인 필요" : signedRate(strategyAnalysis.fundamental.recent_performance.operating_profit_yoy_pct)}</dd></div>
                      <div><dt>부채비율</dt><dd>{strategyAnalysis.fundamental.recent_performance?.debt_ratio_pct == null ? "확인 필요" : `${strategyAnalysis.fundamental.recent_performance.debt_ratio_pct.toFixed(1)}%`}</dd></div>
                      <div><dt>현금흐름</dt><dd>{strategyAnalysis.fundamental.recent_performance?.operating_cash_flow == null ? "확인 필요" : "데이터 확인됨"}</dd></div>
                    </dl>
                  ) : <p>현재 기업 재무 분석 데이터가 없습니다.</p>}
                  <small>세부 재무·공시 분석은 아래 전문 분석에서 확인합니다.</small>
                </article>

              </section>
            </>
          )}

          <StockNewsPanel
            code={stock.code}
            market={stock.market}
            companyLabel={stock.company.corp_name ?? stock.stock.name ?? selectedStockName}
          />

          {strategyAnalysis && (
            <section className="stock-analysis-style-summary stock-analysis-style-section">
              <div className="stock-analysis-section-heading">
                <span>INVESTOR STYLE</span>
                <h3>투자 관점별 분석</h3>
              </div>
              {styleContext?.label ? (
                <>
                  <strong>{styleContext.label}</strong>
                  <p>{styleContext.summary}</p>
                  <span>{styleContext.fit_label}{styleContext.score == null ? "" : ` · 조건 충족도 ${Math.round(styleContext.score)} / 100`}</span>
                </>
              ) : <p>투자 스타일 적합도는 상세 분석에서 확인할 수 있습니다.</p>}
              <small>조건 충족도는 해당 스타일 규칙과의 적합도이며 매수 확률이 아닙니다.</small>
            </section>
          )}

          {children && (
            <details className="stock-analysis-expert-details">
              <summary>
                <span>
                  <small>ADVANCED</small>
                  <strong>전문 분석·세부 설정</strong>
                  <em>참고가격·보유 시나리오와 기존 전문 분석은 필요할 때만 펼쳐봅니다.</em>
                </span>
                <b>펼치기</b>
              </summary>
              <div className="stock-analysis-body">
                {children}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
