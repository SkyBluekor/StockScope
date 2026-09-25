import type { ReactNode } from "react";
import type { StockContext, StockSearchItem, StrategyAnalysis } from "../services/api";
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
  onLoadContext: () => void;
  onRunAnalysis: () => void;
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

function decisionLabel(analysis: StrategyAnalysis | null) {
  if (!analysis) return null;
  if (analysis.risk_gate.active || analysis.top_strategy?.strategy === "no_trade") return "신규 진입 제외";
  return analysis.top_strategy?.suitability || "분석 완료";
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
  onLoadContext,
  onRunAnalysis,
  children,
}: Props) {
  const selectedStrategy = strategyAnalysis?.top_strategy ?? strategyAnalysis?.best_regular_strategy ?? null;
  const plan = strategyAnalysis?.risk_analysis.selected_plan ?? null;
  const reasons = strategyAnalysis?.risk_gate.active
    ? strategyAnalysis.risk_gate.reasons
    : selectedStrategy?.reasons ?? [];

  return (
    <section className="stock-analysis-workspace">
      <header className="stock-analysis-page-head">
        <div>
          <span className="eyebrow">STOCK ANALYSIS</span>
          <h1>종목 분석</h1>
          <p>종목의 현재 상태와 전략 근거를 최신 확정 일봉 기준으로 확인합니다.</p>
        </div>
      </header>

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
          <span>{selectedStockName ? `${stockMarket} · ${stockCode}` : "분석할 종목을 검색하세요"}</span>
          {selectedStockName && !stock && (
            <button type="button" onClick={onLoadContext} disabled={stockBusy}>
              {stockBusy ? "불러오는 중" : "기본 정보 불러오기"}
            </button>
          )}
        </div>
      </section>

      {!stock ? (
        <div className="stock-analysis-empty">
          <strong>{selectedStockName ? stockMessage : "분석할 종목을 선택하세요."}</strong>
          <p>종목을 선택하면 최근 확정 종가와 기업 기본정보를 먼저 불러옵니다.</p>
        </div>
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
              <button type="button" className="stock-analysis-run" onClick={onRunAnalysis} disabled={strategyBusy}>
                {strategyBusy ? "분석 중..." : analysisOutdated ? "변경값 다시 분석" : strategyAnalysis ? "분석 다시 실행" : "분석 실행"}
              </button>
              <small>공식 분석은 최신 확정 일봉을 기준으로 합니다.</small>
            </div>
          </section>

          {strategyAnalysis && (
            <section className="stock-analysis-verdict" aria-label="현재 분석 요약">
              <div className="stock-analysis-verdict-main">
                <span>신규 진입 판단</span>
                <strong>{decisionLabel(strategyAnalysis)}</strong>
                <p>{strategyAnalysis.risk_gate.message || selectedStrategy?.note || strategyAnalysis.first_load_note}</p>
              </div>
              <div className="stock-analysis-strategy">
                <span>현재 전략</span>
                <strong>{selectedStrategy ? strategyLabel[selectedStrategy.strategy] ?? selectedStrategy.strategy : "-"}</strong>
                <small>{selectedStrategy?.note ?? "전략 결과를 확인하세요."}</small>
              </div>
              <div className="stock-analysis-reasons">
                <span>핵심 이유</span>
                {reasons.length > 0 ? (
                  <ul>{reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul>
                ) : (
                  <p>세부 분석에서 전략 조건과 위험 기준을 확인할 수 있습니다.</p>
                )}
              </div>
            </section>
          )}

          {strategyAnalysis && (
            <section className="stock-analysis-plan">
              <div className="stock-analysis-section-title">
                <div>
                  <span>PRICE PLAN</span>
                  <h3>가격 계획</h3>
                </div>
                <small>{strategyAnalysis.data_freshness.analysis_basis === "CONFIRMED_EOD" ? "확정 일봉 기준" : "참고가격 시나리오"}</small>
              </div>
              <dl>
                <div><dt>기준가</dt><dd>{formatNumber(plan?.entry_price ?? strategyAnalysis.effective.price, "원")}</dd></div>
                <div><dt>손절 기준</dt><dd>{formatNumber(plan?.invalidation_price, "원")}</dd></div>
                <div><dt>1차 목표</dt><dd>{formatNumber(plan?.target1_price, "원")}</dd></div>
                <div><dt>2차 목표</dt><dd>{formatNumber(plan?.target2_price, "원")}</dd></div>
              </dl>
            </section>
          )}

          <div className="stock-analysis-body">
            {children}
          </div>
        </>
      )}
    </section>
  );
}
