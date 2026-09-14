import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelBacktestJob,
  createMultiStrategyBacktestJob,
  fetchBacktestJob,
  searchStocks,
  type BacktestJob,
  type MultiStrategyBacktestResponse,
  type MultiStrategyConditionDetail,
  type MultiStrategyRow,
  type StockSearchItem,
} from "../services/api";

type Market = "KOSPI" | "KOSDAQ";

type Props = {
  code: string;
  market: Market;
  stockName?: string;
  onSelectStock: (item: StockSearchItem) => void;
};

const strategyGuides = [
  { professional: "추세 추종", easy: "상승 흐름 따라가기" },
  { professional: "눌림목", easy: "쉬어간 뒤 다시 오를 때 노리기" },
  { professional: "돌파", easy: "막힌 가격 돌파 노리기" },
  { professional: "지지 반등", easy: "지지 가격에서 반등 노리기" },
  { professional: "과매도 반등", easy: "과도한 하락 뒤 반등 노리기" },
  { professional: "박스권 매매", easy: "일정 가격 범위에서 노리기" },
  { professional: "모멘텀 지속", easy: "강한 상승 이어가기" },
  { professional: "변동성 수축", easy: "큰 움직임 전 조용한 구간 찾기" },
  { professional: "20일선 반등", easy: "20일선 반등 노리기" },
  { professional: "추세 회복", easy: "상승 흐름 회복 노리기" },
];

const regimeLabel: Record<string, string> = {
  TREND_UP: "상승장",
  RANGE: "횡보장",
  TREND_DOWN: "하락장",
  HIGH_VOLATILITY: "고변동성",
  PANIC: "패닉",
  UNKNOWN: "판단 보류",
};

const holdingOptions = [
  { days: 5, label: "5일", description: "아주 짧은 움직임만 봅니다." },
  { days: 10, label: "10일", description: "단기 스윙 기준입니다." },
  { days: 20, label: "20일 · 추천", description: "약 한 달 동안 전략이 이어지는지 확인하는 기본값입니다." },
  { days: 40, label: "40일", description: "중기 움직임까지 기다립니다." },
];

function isoDate(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function defaultStartDate() {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 3);
  return isoDate(date);
}

function formatPct(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(value);
}

function formatCompactDate(value: string) {
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function exitLabel(value: string) {
  const labels: Record<string, string> = {
    STOP: "손절",
    STOP_GAP: "갭 손절",
    STOP_SAME_DAY_PRIORITY: "손절 우선",
    TARGET_1: "1차 목표",
    TARGET_1_GAP: "갭 목표",
    TIME_EXIT: "보유기간 종료",
    END_OF_DATA: "기간 종료",
  };
  return labels[value] ?? value;
}

function DetailToggleText({ closed = "펼치기 ▼", open = "숨기기 ▲" }: { closed?: string; open?: string }) {
  return (
    <b className="details-toggle-label" aria-hidden="true">
      <span className="when-closed">{closed}</span>
      <span className="when-open">{open}</span>
    </b>
  );
}

function ConditionMetricCard({ condition }: { condition: MultiStrategyConditionDetail }) {
  const status = condition.status ?? "UNKNOWN";
  const statusLabel = status === "PASS" ? "충족" : status === "FAIL" ? "아직 부족" : "확인 필요";
  return (
    <article className={`strategy-condition-metric status-${status.toLowerCase()}`}>
      <div className="strategy-condition-head">
        <strong>{condition.label}</strong>
        <b>{status === "PASS" ? "✓" : status === "FAIL" ? "✕" : "○"} {statusLabel}</b>
      </div>
      <p>{condition.detail}</p>
      {(condition.current_value || condition.required_value) && (
        <div className="strategy-condition-values">
          {condition.current_value && <span><small>현재</small><strong>{condition.current_value}</strong></span>}
          {condition.required_value && <span><small>필요</small><strong>{condition.required_value}</strong></span>}
        </div>
      )}
    </article>
  );
}

function StrategyConditionSummary({ row, action }: { row: MultiStrategyRow; action: string }) {
  const rawPassedDetails = row.current.reason_details ?? [];
  const rawMissingDetails = row.current.unmet_details ?? [];
  const total = Math.max(0, row.current.total ?? 0);
  const passed = Math.max(0, Math.min(total, row.current.passed ?? 0));
  const missing = Math.max(0, row.current.missing ?? (total - passed));
  const passedDetails = rawPassedDetails.slice(0, passed);
  const missingDetails = rawMissingDetails.slice(0, missing);
  const primaryMissing = missingDetails.slice(0, 3);
  const remainingMissing = missingDetails.slice(3);

  return (
    <section className="strategy-condition-summary">
      <div className="strategy-condition-summary-head">
        <div>
          <span>{action === "ENTRY_CANDIDATE" ? "현재 진입 준비" : "왜 아직 진입하지 않나요?"}</span>
          <strong>전체 {total}개 · 충족 {passed}개 · 부족 {missing}개</strong>
        </div>
        <b>{passed}/{total}</b>
      </div>

      {missing > 0 && (
        <>
          <div className="strategy-condition-section-title">
            <strong>가장 중요한 부족 조건</strong>
            <span>{missing > 3 ? "우선 3개만 보여드립니다." : "현재 부족한 조건입니다."}</span>
          </div>
          <div className="strategy-condition-grid">
            {primaryMissing.map((condition) => (
              <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
            ))}
          </div>
          {remainingMissing.length > 0 && (
            <details className="strategy-condition-more">
              <summary>
                <span>나머지 부족 조건 {remainingMissing.length}개</span>
                <DetailToggleText closed="보기 ▼" open="숨기기 ▲" />
              </summary>
              <div className="strategy-condition-grid">
                {remainingMissing.map((condition) => (
                  <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
                ))}
              </div>
            </details>
          )}
          {missingDetails.length < missing && (
            <p className="strategy-condition-empty">
              부족 조건은 총 {missing}개지만 상세 설명은 {missingDetails.length}개만 제공됐습니다. 전문 상세에서 원본 조건을 확인할 수 있습니다.
            </p>
          )}
        </>
      )}

      {passed > 0 && (
        <details className="strategy-condition-more passed">
          <summary>
            <span>이미 충족한 조건 {passed}개</span>
            <DetailToggleText closed="보기 ▼" open="숨기기 ▲" />
          </summary>
          {passedDetails.length > 0 ? (
            <>
              <div className="strategy-condition-grid">
                {passedDetails.map((condition) => (
                  <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
                ))}
              </div>
              {passedDetails.length < passed && (
                <p className="strategy-condition-empty">충족 조건은 총 {passed}개지만 상세 설명은 {passedDetails.length}개만 제공됐습니다.</p>
              )}
            </>
          ) : (
            <p className="strategy-condition-empty">충족 개수는 계산됐지만 상세 설명 데이터가 없습니다.</p>
          )}
        </details>
      )}

      {row.current.condition_consistency?.ok === false && (
        <div className="strategy-condition-consistency-error" role="alert">
          <strong>조건 집계가 서로 맞지 않습니다.</strong>
          <span>이 결과는 진입 판단에 사용하지 말고 최신 데이터로 다시 분석하세요.</span>
        </div>
      )}

      {total === 0 && (
        <p className="strategy-condition-empty">현재 전략 조건을 세부 항목으로 나눠 표시할 수 없습니다. 다음 분석에서 다시 계산합니다.</p>
      )}
    </section>
  );
}

function StrategyMiniCard({ row }: { row: MultiStrategyRow }) {
  return (
    <article className={`multi-strategy-mini fit-${row.historical_fit.status.toLowerCase()}`}>
      <div className="multi-strategy-rank">{row.rank}위</div>
      <div>
        <strong>{row.guide.easy_name}</strong>
        <span>{row.guide.professional_name} 전략 · {row.historical_fit.label}</span>
      </div>
      <div className="multi-strategy-mini-current">
        <b>{row.current.label}</b>
        <small>과거 사례 {row.historical_metrics.trades}건</small>
      </div>
    </article>
  );
}

export default function BacktestPanel({ code, market, stockName, onSelectStock }: Props) {
  const [view, setView] = useState<"setup" | "result">("setup");
  const [stockQuery, setStockQuery] = useState(stockName ? `${stockName} (${code})` : code);
  const [stockSearchResults, setStockSearchResults] = useState<StockSearchItem[]>([]);
  const [stockSearchBusy, setStockSearchBusy] = useState(false);
  const [stockSearchOpen, setStockSearchOpen] = useState(false);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(() => isoDate(new Date()));
  const [initialCapital, setInitialCapital] = useState("10000000");
  const [maxHoldingDays, setMaxHoldingDays] = useState(20);
  const [customHolding, setCustomHolding] = useState("");
  const [costPct, setCostPct] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<BacktestJob<MultiStrategyBacktestResponse> | null>(null);
  const [result, setResult] = useState<MultiStrategyBacktestResponse | null>(null);
  const activeJobId = useRef<string | null>(null);
  const workspaceTopRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setStockQuery(stockName ? `${stockName} (${code})` : code);
  }, [code, stockName]);

  useEffect(() => {
    const query = stockQuery.trim();
    const selectedLabel = stockName ? `${stockName} (${code})` : "";
    if (query === selectedLabel || query.length < 2) {
      setStockSearchResults([]);
      setStockSearchBusy(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setStockSearchBusy(true);
      void searchStocks(query)
        .then((response) => {
          setStockSearchResults(response.rows);
          setStockSearchOpen(true);
        })
        .catch(() => {
          setStockSearchResults([]);
          setStockSearchOpen(true);
        })
        .finally(() => setStockSearchBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [stockQuery, code, stockName]);

  useEffect(() => {
    return () => {
      const running = activeJobId.current;
      if (running) void cancelBacktestJob<MultiStrategyBacktestResponse>(running).catch(() => undefined);
    };
  }, []);

  useEffect(() => {
    const running = activeJobId.current;
    if (running) void cancelBacktestJob<MultiStrategyBacktestResponse>(running).catch(() => undefined);
    activeJobId.current = null;
    setBusy(false);
    setJob(null);
    setResult(null);
    setError(null);
    setView("setup");
  }, [code, market]);

  const selectedHolding = customHolding ? Number(customHolding) : maxHoldingDays;
  const selectedStockLabel = stockName ? `${stockName} (${code})` : "";
  const stockSelectionDirty = Boolean(stockQuery.trim() && stockQuery.trim() !== selectedStockLabel);
  const holdingDescription = useMemo(() => {
    if (customHolding) return "직접 입력한 거래일 수를 모든 전략에 동일하게 적용합니다.";
    return holdingOptions.find((item) => item.days === maxHoldingDays)?.description ?? "";
  }, [customHolding, maxHoldingDays]);

  function chooseStock(item: StockSearchItem) {
    onSelectStock(item);
    setStockQuery(`${item.name} (${item.code})`);
    setStockSearchResults([]);
    setStockSearchOpen(false);
    setView("setup");
  }

  function scrollTop() {
    window.requestAnimationFrame(() => workspaceTopRef.current?.scrollIntoView({ behavior: "auto", block: "start" }));
  }

  async function runBacktest(endDateOverride?: string) {
    if (!code.trim() || stockSelectionDirty || busy) return;
    const holding = Number(selectedHolding);
    if (!Number.isFinite(holding) || holding < 1 || holding > 120) {
      setError("최대 보유기간은 1~120 거래일로 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    setView("result");
    scrollTop();

    try {
      const created = await createMultiStrategyBacktestJob({
        code,
        market,
        start_date: startDate,
        end_date: endDateOverride ?? endDate,
        initial_capital: Number(initialCapital),
        max_holding_days: holding,
        round_trip_cost_pct: Number(costPct),
      });
      setJob(created);
      activeJobId.current = created.job_id;

      while (activeJobId.current === created.job_id) {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        const latest = await fetchBacktestJob<MultiStrategyBacktestResponse>(created.job_id);
        setJob(latest);
        if (latest.status === "completed" && latest.result) {
          setResult(latest.result);
          setBusy(false);
          activeJobId.current = null;
          scrollTop();
          return;
        }
        if (latest.status === "failed") {
          throw new Error(latest.error || "전체 전략 검증을 완료하지 못했습니다.");
        }
        if (latest.status === "cancelled") {
          setBusy(false);
          activeJobId.current = null;
          return;
        }
      }
    } catch (cause) {
      setBusy(false);
      activeJobId.current = null;
      setError(cause instanceof Error ? cause.message : "전체 전략 검증 중 오류가 발생했습니다.");
    }
  }

  function rerunLatest() {
    if (busy) return;
    const latest = isoDate(new Date());
    setEndDate(latest);
    void runBacktest(latest);
  }

  async function cancelRunning() {
    const id = activeJobId.current;
    if (!id) return;
    try {
      const cancelled = await cancelBacktestJob<MultiStrategyBacktestResponse>(id);
      setJob(cancelled);
    } finally {
      activeJobId.current = null;
      setBusy(false);
    }
  }

  const topStrategy = result?.recommendation.strategy
    ? result.strategies.find((row) => row.strategy === result.recommendation.strategy) ?? result.strategies[0]
    : null;
  const topThree = result?.strategies.slice(0, 3) ?? [];

  return (
    <section className="backtest-workspace multi-strategy-workspace" ref={workspaceTopRef}>
      <header className="multi-strategy-header">
        <div>
          <span>STRATEGY SELECTOR · v0.20.3</span>
          <h1>10가지 투자 방법 자동 비교</h1>
          <p>종목 하나를 고르면 StockScope가 10가지 방법을 같은 과거 데이터로 비교합니다. 전문 용어를 몰라도 지금 어떤 방법이 맞는지와 사용자가 해야 할 일을 쉬운 말로 정리합니다.</p>
        </div>
        <div className="multi-strategy-flow" aria-label="전략 자동 검증 흐름">
          <span>1 · 종목 선택</span><i>→</i><span>2 · 10가지 방법 비교</span><i>→</i><span>3 · 지금 행동 안내</span>
        </div>
      </header>

      <nav className="backtest-subnav" aria-label="전략 검증 단계">
        <button type="button" className={view === "setup" ? "active" : ""} onClick={() => { setView("setup"); scrollTop(); }}>1 · 설정</button>
        <button type="button" className={view === "result" ? "active" : ""} disabled={!busy && !result && !error} onClick={() => { setView("result"); scrollTop(); }}>2 · 결과</button>
      </nav>

      {view === "setup" && (
        <div className="multi-strategy-setup">
          <section className="multi-strategy-purpose">
            <div>
              <span>이 기능으로 무엇을 해결하나요?</span>
              <strong>“이 종목에서는 어떤 방법을 쓰는 게 맞지?”를 사용자가 직접 고르지 않게 합니다.</strong>
              <p>과거에 잘 맞았는지, 지금 시장과 맞는지, 현재 진입 조건이 준비됐는지를 StockScope가 계산한 뒤 쉬운 행동 안내로 정리합니다.</p>
            </div>
            <div className="multi-strategy-chip-list">
              {strategyGuides.map((guide) => (
                <span key={guide.professional}>
                  <b>{guide.easy}</b>
                  <small>{guide.professional} 전략</small>
                </span>
              ))}
            </div>
          </section>

          <section className="backtest-settings-card">
            <div className="backtest-section-title"><span>검증 설정</span><strong>10가지 방법은 StockScope가 자동으로 전부 비교합니다.</strong></div>
            <div className="backtest-stock-picker">
              <label htmlFor="backtest-stock-search">검증 종목</label>
              <div className="backtest-stock-search-box">
                <input
                  id="backtest-stock-search"
                  value={stockQuery}
                  placeholder="종목명 또는 종목코드 검색"
                  onFocus={() => stockSearchResults.length > 0 && setStockSearchOpen(true)}
                  onChange={(event) => { setStockQuery(event.target.value); setStockSearchOpen(true); }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && stockSearchResults[0]) {
                      event.preventDefault();
                      chooseStock(stockSearchResults[0]);
                    }
                  }}
                />
                <span>{stockSearchBusy ? "검색 중" : code ? `${market} · ${code}` : "종목을 선택하세요"}</span>
                {stockSearchOpen && stockQuery.trim().length >= 2 && stockQuery !== selectedStockLabel && (
                  <div className="backtest-stock-results">
                    {stockSearchResults.length > 0 ? stockSearchResults.map((item) => (
                      <button key={`${item.market}-${item.code}`} type="button" onClick={() => chooseStock(item)}>
                        <strong>{item.name}</strong><span>{item.market} · {item.code}</span>
                      </button>
                    )) : <p>{stockSearchBusy ? "종목을 찾는 중입니다..." : "검색 결과가 없습니다."}</p>}
                  </div>
                )}
              </div>
            </div>
            {stockSelectionDirty && <div className="backtest-selection-notice">검색 결과에서 종목을 선택해야 검증 대상이 변경됩니다.</div>}

            <div className="backtest-config-grid">
              <label><span>시작일</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
              <label><span>종료일</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
              <label><span>초기 자본 <small>성과 비교용</small></span><input type="number" min="1" step="100000" value={initialCapital} onChange={(event) => setInitialCapital(event.target.value)} /></label>
              <label><span>왕복 비용률 <small>모든 전략 동일</small></span><div className="backtest-input-suffix"><input type="number" min="0" max="5" step="0.01" value={costPct} onChange={(event) => setCostPct(event.target.value)} /><b>%</b></div></label>
            </div>

            <div className="holding-config">
              <div className="holding-title"><div><strong>최대 보유기간</strong><span>모든 전략에 동일한 보유기간을 적용해 비교 조건을 맞춥니다.</span></div><b>{selectedHolding || "-"} 거래일</b></div>
              <div className="holding-buttons">
                {holdingOptions.map((option) => (
                  <button key={option.days} type="button" className={!customHolding && maxHoldingDays === option.days ? "active" : ""} onClick={() => { setCustomHolding(""); setMaxHoldingDays(option.days); }}>{option.label}</button>
                ))}
                <label className={customHolding ? "active" : ""}><span>직접 입력</span><input type="number" min="1" max="120" placeholder="거래일" value={customHolding} onChange={(event) => setCustomHolding(event.target.value)} /></label>
              </div>
              <p className="holding-explanation">{holdingDescription}</p>
            </div>

            <details className="backtest-policy-details">
              <summary><span>공정하게 비교하기 위해 어떤 조건을 같게 하나요?</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>
              <div className="multi-strategy-method-brief">
                <p><b>과거 데이터</b> 10개 전략이 같은 KRX 데이터 한 벌을 사용합니다.</p>
                <p><b>진입 가격</b> 신호 다음 거래일 시가를 사용합니다.</p>
                <p><b>위험/청산</b> 기존 Risk Engine + 1차 목표가 + 동일 보유기간을 사용합니다.</p>
                <p><b>추천 기준</b> 수익률 1등만 고르지 않고 표본·거래당 평균·Profit Factor·MDD·현재 상태를 함께 봅니다.</p>
              </div>
            </details>

            <div className="backtest-run-row multi-strategy-run-row">
              <div><strong>투자 방법을 직접 고를 필요가 없습니다.</strong><span>10가지 방법을 자동으로 비교하고 결과 화면에서 왜 이 방법이 맞는지와 지금 사용자가 해야 할 일을 보여줍니다.</span></div>
              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "10가지 방법 분석 중..." : "10가지 방법 자동 비교 시작"}</button>
            </div>
            {error && <div className="backtest-error"><strong>실행 실패</strong><span>{error}</span></div>}
          </section>
        </div>
      )}

      {view === "result" && (
        <div className="backtest-result-view multi-strategy-result-view">
          <div className="backtest-result-toolbar">
            <div><span>검증 대상</span><strong>{stockName || code || "종목 미선택"} · 전체 전략</strong><small>{formatCompactDate(startDate)} ~ {formatCompactDate(endDate)}</small></div>
            <button type="button" disabled={busy} onClick={() => { setView("setup"); scrollTop(); }}>설정 변경</button>
          </div>

          {busy && job && (
            <div className="backtest-progress-card">
              <div className="backtest-progress-head"><div><strong>{job.progress.message}</strong><span>{job.progress.current.toLocaleString()} / {job.progress.total.toLocaleString()} · {job.progress.percent.toFixed(1)}%</span></div><b>{job.elapsed_seconds.toFixed(1)}초</b></div>
              <progress max={100} value={job.progress.percent} />
              <div className="backtest-progress-stats"><span><b>시장 저장소</b>{Number(job.progress.details.market_store_hits ?? job.progress.details.history_store_hits ?? 0).toLocaleString()} hit</span><span><b>기존 KRX 캐시</b>{Number(job.progress.details.raw_cache_hits ?? 0).toLocaleString()} hit</span><span><b>예상 신규 요청</b>{Number(job.progress.details.estimated_network_requests ?? 0).toLocaleString()}회</span><span><b>실제 요청</b>{Number(job.progress.details.network_requests ?? 0).toLocaleString()}회</span>{Number(job.progress.details.budget_limit ?? 0) > 0 && <span><b>오늘 KRX(앱 기록)</b>{Number(job.progress.details.budget_used ?? 0).toLocaleString()} / {Number(job.progress.details.budget_limit ?? 0).toLocaleString()}</span>}<span><b>현재 전략</b>{String(job.progress.details.strategy ?? "-")}</span></div>
              <button type="button" className="backtest-cancel-button" onClick={() => void cancelRunning()}>분석 취소</button>
            </div>
          )}
          {busy && !job && <div className="loading-card">10가지 방법 비교를 준비하고 있습니다...</div>}
          {error && <div className="backtest-error"><strong>실행 실패</strong><span>{error}</span><button type="button" onClick={() => { setView("setup"); scrollTop(); }}>설정으로 돌아가기</button></div>}

          {result && (
            <div className="multi-strategy-results">
              <section className={`strategy-selector-hero action-${result.recommendation.action.toLowerCase()}`}>
                <div className="strategy-selector-kicker">
                  <span>{formatCompactDate(result.as_of_date)} 기준</span>
                  <b>{regimeLabel[result.market_regime] ?? result.market_regime}</b>
                </div>

                <div className="strategy-selector-main beginner">
                  <div>
                    <span>현재 가장 적합한 방법</span>
                    <h2>{result.recommendation.strategy_easy_name ?? "현재 추천 전략 없음"}</h2>
                    {result.recommendation.strategy_label && <small className="strategy-professional-name">전문 용어 · {result.recommendation.strategy_label} 전략</small>}
                  </div>
                  <div className="strategy-selector-decision">
                    <span>현재 판단</span>
                    <strong>{result.recommendation.action_label}</strong>
                    <p>{result.recommendation.headline}</p>
                  </div>
                </div>

                {result.recommendation.strategy_description && (
                  <div className="strategy-beginner-explanation">
                    <div>
                      <span>이게 무슨 방법인가요?</span>
                      <strong>{result.recommendation.strategy_description}</strong>
                    </div>
                    {result.recommendation.strategy_when_to_use && (
                      <p><b>주로 언제 쓰나요?</b> {result.recommendation.strategy_when_to_use}</p>
                    )}
                  </div>
                )}

                <div className="strategy-selector-reason">
                  <span>왜 지금 이렇게 판단했나요?</span>
                  <p>{result.recommendation.reason}</p>
                  {(result.recommendation.additional_warnings?.length ?? 0) > 0 && (
                    <div className="strategy-selector-secondary-warnings">
                      <b>추가 주의</b>
                      {result.recommendation.additional_warnings!.map((warning) => <small key={warning}>{warning}</small>)}
                    </div>
                  )}
                </div>

                {topStrategy && <StrategyConditionSummary row={topStrategy} action={result.recommendation.action} />}

                <div className="strategy-user-action-card">
                  <div className="strategy-user-action-head">
                    <span>지금 행동</span>
                    <strong>{result.recommendation.user_action.user_task}</strong>
                  </div>
                  <div>
                    <b>{result.recommendation.user_action.title}</b>
                    <p>{result.recommendation.user_action.detail}</p>
                    {result.recommendation.action !== "ENTRY_CANDIDATE" && (
                      <p className="strategy-next-user-action"><strong>다음 행동</strong> 최신 확정 데이터가 나온 뒤 다시 분석하세요.</p>
                    )}
                  </div>
                </div>

                <div className="strategy-next-check-card">
                  <div className="strategy-next-check-copy">
                    <span>다음 분석에서는 무엇을 하나요?</span>
                    <strong>최신 확정 데이터로 부족했던 조건과 위험을 다시 계산합니다.</strong>
                    <small>{result.recommendation.recheck_label}</small>
                  </div>
                  <div className="strategy-next-conditions">
                    <span>다시 확인하는 항목</span>
                    <ul className="strategy-recheck-list">
                      <li>부족했던 전략 조건</li>
                      <li>현재 시장 상황</li>
                      <li>손절 위험</li>
                      <li>목표 가격까지의 여유</li>
                    </ul>
                  </div>
                </div>

                <div className="strategy-transition-card">
                  <div>
                    <span>조건이 충족되면?</span>
                    <strong>바로 매수 신호가 되지는 않습니다.</strong>
                    <small>StockScope가 전략 조건 + 시장 상황 + 손절·목표 위험을 다시 확인하고, 모두 적절하면 진입 후보로 변경합니다.</small>
                  </div>
                  <button type="button" className="secondary" disabled={busy} onClick={rerunLatest}>최신 확정 데이터로 다시 분석</button>
                </div>

                <div className="strategy-recheck-note">
                  <b>현재 버전은 상시 자동 감시가 아닙니다.</b>
                  <span>다음 거래일 데이터가 확정된 뒤 다시 분석하면 StockScope가 최신 데이터로 조건을 자동 재평가합니다. 사용자가 거래량·RSI·이동평균을 직접 계산할 필요는 없습니다.</span>
                </div>
                <small>{result.recommendation.guardrail}</small>
              </section>

              {topStrategy && (
                <section className="strategy-selector-proof">
                  <article><span>과거에는 어땠나요?</span><strong>{topStrategy.historical_fit.label}</strong><p>{topStrategy.historical_fit.summary}</p></article>
                  <article><span>지금 조건은 어떤가요?</span><strong>{topStrategy.current.label}</strong><p>{topStrategy.current.summary}</p></article>
                  <article><span>과거 사례는 충분한가요?</span><strong>{topStrategy.historical_metrics.trades}건</strong><p>과거 진입 사례가 5건 미만이면 결과가 좋아도 근거 부족으로 처리합니다. 자세한 숫자는 아래에서 확인할 수 있습니다.</p></article>
                </section>
              )}

              <section className="strategy-selector-top3">
                <div className="backtest-section-title"><span>다른 방법과 비교하면?</span><strong>StockScope가 같은 기준으로 비교한 현재 상위 3개 방법입니다.</strong></div>
                <div className="multi-strategy-mini-grid">{topThree.map((row) => <StrategyMiniCard key={row.strategy} row={row} />)}</div>
              </section>

              {result.warnings.length > 0 && <div className="backtest-warning"><strong>데이터 확인사항</strong>{result.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}

              <div className="multi-strategy-details-stack">
                <details>
                  <summary><span>10개 방법 전체 비교 · 전문 숫자 보기</span><DetailToggleText /></summary>
                  <div className="backtest-table-wrap">
                    <table className="backtest-table multi-strategy-table">
                      <thead><tr><th>순위</th><th>방법</th><th>전문 전략명</th><th>과거 판단</th><th>과거 사례</th><th>거래당 평균</th><th>가장 큰 손실 구간(MDD)</th><th>현재 상태</th></tr></thead>
                      <tbody>{result.strategies.map((row) => (
                        <tr key={row.strategy}>
                          <td><b>{row.rank}</b></td><td><strong>{row.guide.easy_name}</strong></td><td>{row.guide.professional_name}</td><td>{row.historical_fit.label}</td><td>{row.historical_metrics.trades}건</td><td>{formatPct(row.historical_metrics.expectancy_pct)}</td><td>{formatPct(row.historical_metrics.max_drawdown_pct)}</td><td>{row.current.label}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  <p className="backtest-detail-note">순위는 주가 상승 확률이 아닙니다. 같은 과거 데이터에서 각 방법이 얼마나 잘 맞았는지와 현재 조건을 함께 비교한 우선순위입니다.</p>
                </details>

                {topStrategy && (
                  <details>
                    <summary><span>왜 ‘{topStrategy.guide.easy_name}’가 1순위인가?</span><DetailToggleText /></summary>
                    <div className="strategy-guide-detail">
                      <strong>{topStrategy.guide.easy_name}</strong>
                      <small>{topStrategy.guide.professional_name} 전략</small>
                      <p>{topStrategy.guide.description}</p>
                      <p><b>주로 언제 쓰나요?</b> {topStrategy.guide.when_to_use}</p>
                    </div>
                    <div className="multi-strategy-explanation-grid">
                      <article><span>과거 검증</span><strong>{topStrategy.historical_fit.label}</strong><p>{topStrategy.historical_fit.summary}</p></article>
                      <article><span>현재 조건</span><strong>{topStrategy.current.label}</strong><p>{topStrategy.current.summary}</p></article>
                    </div>
                    {(topStrategy.current.reason_details?.length ?? 0) > 0 && (
                      <div className="multi-strategy-reason-list">
                        <strong>현재 맞아 있는 조건</strong>
                        <div className="strategy-detail-condition-grid">{topStrategy.current.reason_details!.slice(0, 5).map((reason) => <ConditionMetricCard key={reason.condition_id ?? reason.raw} condition={reason} />)}</div>
                      </div>
                    )}
                    {(topStrategy.current.unmet_details?.length ?? 0) > 0 && (
                      <div className="multi-strategy-reason-list missing">
                        <strong>아직 부족한 조건</strong>
                        <div className="strategy-detail-condition-grid">{topStrategy.current.unmet_details!.slice(0, 5).map((reason) => <ConditionMetricCard key={reason.condition_id ?? reason.raw} condition={reason} />)}</div>
                      </div>
                    )}
                  </details>
                )}

                {topStrategy && (
                  <details>
                    <summary><span>‘{topStrategy.guide.easy_name}’의 과거 거래 숫자로 보기</span><DetailToggleText /></summary>
                    {topStrategy.recent_trades.length === 0 ? <p className="backtest-empty-row">표시할 과거 거래가 없습니다.</p> : (
                      <div className="backtest-table-wrap"><table className="backtest-table"><thead><tr><th>진입일</th><th>청산일</th><th>결과</th><th>종료 이유</th><th>보유</th></tr></thead><tbody>{topStrategy.recent_trades.map((trade) => <tr key={`${trade.entry_date}-${trade.exit_date}`}><td>{formatCompactDate(trade.entry_date)}</td><td>{formatCompactDate(trade.exit_date)}</td><td>{formatPct(trade.net_return_pct)}</td><td>{exitLabel(trade.exit_reason)}</td><td>{trade.holding_days}일</td></tr>)}</tbody></table></div>
                    )}
                  </details>
                )}

                <details>
                  <summary><span>전문가용 · 비교 방법과 한계</span><DetailToggleText /></summary>
                  <div className="multi-strategy-method-brief">
                    {Object.entries(result.methodology).map(([key, value]) => <p key={key}>{value}</p>)}
                  </div>
                </details>

                {result.performance && (
                  <details>
                    <summary><span>개발 확인용 · 실행 성능 진단</span><DetailToggleText /></summary>
                    <div className="backtest-progress-stats"><span><b>데이터 준비</b>{formatNumber(result.performance.data_prepare_seconds, 2)}초</span><span><b>10전략 계산</b>{formatNumber(result.performance.strategy_calculation_seconds, 2)}초</span><span><b>전체</b>{formatNumber(result.performance.total_seconds, 2)}초</span><span><b>실제 KRX 요청</b>{result.performance.network_requests}회</span>{result.performance.estimated_network_requests !== undefined && <span><b>실행 전 예상</b>{result.performance.estimated_network_requests}회</span>}{result.performance.market_store_hits !== undefined && <span><b>시장 저장소 재사용</b>{result.performance.market_store_hits.toLocaleString()} hit</span>}{result.performance.raw_cache_hits !== undefined && <span><b>기존 KRX 캐시</b>{result.performance.raw_cache_hits.toLocaleString()} hit</span>}{result.performance.cache_reuse_pct !== undefined && <span><b>데이터 재사용</b>{formatNumber(result.performance.cache_reuse_pct, 1)}%</span>}{result.performance.budget_limit !== undefined && <span><b>오늘 KRX(앱 기록)</b>{Number(result.performance.budget_used ?? 0).toLocaleString()} / {result.performance.budget_limit.toLocaleString()}</span>}</div>
                  </details>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
