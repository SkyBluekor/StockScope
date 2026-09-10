import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelBacktestJob,
  createPullbackBacktestJob,
  fetchBacktestJob,
  searchStocks,
  type BacktestGroupMetrics,
  type BacktestJob,
  type PullbackBacktestResponse,
  type StockSearchItem,
} from "../services/api";

type Market = "KOSPI" | "KOSDAQ";

type Props = {
  code: string;
  market: Market;
  stockName?: string;
  onSelectStock: (item: StockSearchItem) => void;
};


const regimeLabel: Record<string, string> = {
  TREND_UP: "상승장",
  RANGE: "횡보장",
  TREND_DOWN: "하락장",
  HIGH_VOLATILITY: "고변동성",
  PANIC: "패닉",
  UNKNOWN: "판단 보류",
};

const exitReasonLabel: Record<string, string> = {
  STOP: "손절 기준 도달",
  STOP_GAP: "갭 하락 손절",
  STOP_SAME_DAY_PRIORITY: "동일 일봉 충돌 · 손절 우선",
  TARGET_1: "1차 목표 도달",
  TARGET_1_GAP: "갭 상승 목표 도달",
  TIME_EXIT: "최대 보유기간 종료",
  END_OF_DATA: "백테스트 기간 종료",
};

const auditStatusLabel: Record<string, string> = {
  PASS: "정상",
  WARN: "확인 필요",
  FAIL: "오류",
  INFO: "참고",
};

const auditFlagLabel: Record<string, string> = {
  WIDE_STOP: "손절 폭 12% 이상",
  CAUTION_RISK_PLAN: "Risk Engine 경고 상태",
  UNFAVORABLE_RISK_STRUCTURE: "손익 구조 불리함",
  LARGE_NEXT_OPEN_GAP: "다음날 시가 갭 10% 이상",
};

const methodologyLabel: Record<string, string> = {
  future_data_leakage: "미래 데이터 누수",
  entry: "진입 가격",
  same_day_ambiguity: "동일 일봉 충돌",
  holding_period: "최대 보유기간",
  cost: "거래 비용",
  fundamental: "재무·공시",
  relative_strength: "상대강도",
  target: "목표가",
  drawdown: "최대 낙폭",
  score_note: "전략 점수",
  research_note: "진입 타이밍 연구",
  risk_policy_research: "Risk 정책 비교",
};

const holdingOptions = [
  { days: 5, label: "5일", description: "아주 짧은 반등만 봅니다. 회전은 빠르지만 늦게 나오는 상승을 놓치기 쉽습니다." },
  { days: 10, label: "10일", description: "단기 스윙 중심입니다. 빠른 눌림 회복을 검증하기 좋습니다." },
  { days: 20, label: "20일 · 추천", description: "약 1개월 거래기간입니다. 반등을 기다리면서 장기 보유로 변질되는 것을 줄이는 기본값입니다." },
  { days: 40, label: "40일", description: "중기 추세 회복까지 기다립니다. 큰 움직임을 잡을 수 있지만 자금이 오래 묶일 수 있습니다." },
];

function isoDate(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function defaultStartDate() {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return isoDate(date);
}

function yearsBefore(value: string, years: number) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  date.setFullYear(date.getFullYear() - years);
  return isoDate(date);
}

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(value);
}

function formatPct(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatPctPoint(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%p`;
}

function formatWon(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}원`;
}

function formatCompactDate(value: string) {
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function metricTone(value: number | null | undefined) {
  if (value == null) return "neutral";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function MetricTable({
  rows,
  firstColumn,
  keyLabel = (key: string) => key,
}: {
  rows: BacktestGroupMetrics[];
  firstColumn: string;
  keyLabel?: (key: string) => string;
}) {
  if (!rows.length) return <p className="backtest-empty-row">표시할 거래 표본이 없습니다.</p>;
  return (
    <div className="backtest-table-wrap">
      <table className="backtest-table">
        <thead>
          <tr>
            <th>{firstColumn}</th>
            <th>거래</th>
            <th>승률</th>
            <th>비용 반영 평균</th>
            <th>거래당 평균</th>
            <th>수익/손실 비율</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td><strong>{keyLabel(row.key)}</strong></td>
              <td>{row.trades}</td>
              <td>{row.win_rate_pct == null ? "-" : `${formatNumber(row.win_rate_pct, 1)}%`}</td>
              <td className={metricTone(row.average_net_return_pct)}>{formatPct(row.average_net_return_pct)}</td>
              <td className={metricTone(row.expectancy_pct)}>{formatPct(row.expectancy_pct)}</td>
              <td>{formatNumber(row.profit_factor, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BacktestPanel({ code, market, stockName, onSelectStock }: Props) {
  const [view, setView] = useState<"setup" | "result">("setup");
  const [stockQuery, setStockQuery] = useState(stockName ? `${stockName} (${code})` : code);
  const [stockSearchResults, setStockSearchResults] = useState<StockSearchItem[]>([]);
  const [stockSearchBusy, setStockSearchBusy] = useState(false);
  const [stockSearchOpen, setStockSearchOpen] = useState(false);
  const workspaceTopRef = useRef<HTMLDivElement | null>(null);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(() => isoDate(new Date()));
  const [initialCapital, setInitialCapital] = useState("10000000");
  const [maxHoldingDays, setMaxHoldingDays] = useState(20);
  const [customHolding, setCustomHolding] = useState("");
  const [costPct, setCostPct] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PullbackBacktestResponse | null>(null);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [expandedTradeKey, setExpandedTradeKey] = useState<string | null>(null);
  const activeJobId = useRef<string | null>(null);

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

  function chooseBacktestStock(item: StockSearchItem) {
    onSelectStock(item);
    setStockQuery(`${item.name} (${item.code})`);
    setStockSearchResults([]);
    setStockSearchOpen(false);
    setView("setup");
  }

  function scrollWorkspaceTop() {
    window.requestAnimationFrame(() => {
      workspaceTopRef.current?.scrollIntoView({ behavior: "auto", block: "start" });
    });
  }

  useEffect(() => {
    const runningJob = activeJobId.current;
    if (runningJob) void cancelBacktestJob(runningJob).catch(() => undefined);
    activeJobId.current = null;
    setBusy(false);
    setJob(null);
    setResult(null);
    setExpandedTradeKey(null);
    setError(null);
    setView("setup");
  }, [code, market]);

  const selectedHolding = customHolding ? Number(customHolding) : maxHoldingDays;
  const selectedStockLabel = stockName ? `${stockName} (${code})` : "";
  const stockSelectionDirty = Boolean(stockQuery.trim() && stockQuery.trim() !== selectedStockLabel);
  const holdingDescription = useMemo(() => {
    if (customHolding) return "직접 지정한 거래일 수로 종료 시점을 검증합니다. 너무 짧거나 길면 눌림목 전략의 성격 자체가 달라질 수 있습니다.";
    return holdingOptions.find((item) => item.days === maxHoldingDays)?.description ?? "";
  }, [customHolding, maxHoldingDays]);

  async function runBacktest(overrides?: { startDate?: string }) {
    const capital = Number(initialCapital);
    const effectiveStartDate = overrides?.startDate ?? startDate;
    const cost = Number(costPct);
    const holding = Number(selectedHolding);
    if (stockSelectionDirty) {
      setError("검색어만 입력된 상태입니다. 검색 결과에서 실제 종목을 먼저 선택해주세요.");
      return;
    }
    if (!code.trim()) {
      setError("검증할 종목을 먼저 선택해주세요.");
      return;
    }
    if (!Number.isFinite(capital) || capital <= 0) {
      setError("초기 자본은 0보다 큰 숫자여야 합니다.");
      return;
    }
    if (!Number.isInteger(holding) || holding < 1 || holding > 120) {
      setError("최대 보유기간은 1~120 거래일 사이의 정수여야 합니다.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0 || cost > 5) {
      setError("왕복 비용률은 0~5% 범위로 입력해주세요.");
      return;
    }

    setView("result");
    scrollWorkspaceTop();
    setBusy(true);
    setError(null);
    setResult(null);
    setExpandedTradeKey(null);
    setJob(null);
    let createdJobId: string | null = null;
    try {
      let current = await createPullbackBacktestJob({
        code: code.trim().toUpperCase(),
        market,
        start_date: effectiveStartDate,
        end_date: endDate,
        initial_capital: capital,
        max_holding_days: holding,
        round_trip_cost_pct: cost,
      });
      createdJobId = current.job_id;
      activeJobId.current = current.job_id;
      setJob(current);

      while (activeJobId.current === current.job_id) {
        if (current.status === "completed") {
          if (!current.result) throw new Error("완료된 백테스트 결과가 비어 있습니다.");
          setResult(current.result);
          scrollWorkspaceTop();
          return;
        }
        if (current.status === "failed") throw new Error(current.error || "백테스트 실행에 실패했습니다.");
        if (current.status === "cancelled") return;
        await new Promise((resolve) => window.setTimeout(resolve, 600));
        if (activeJobId.current !== current.job_id) return;
        current = await fetchBacktestJob(current.job_id);
        setJob(current);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "백테스트 실행에 실패했습니다.");
    } finally {
      if (createdJobId && activeJobId.current === createdJobId) activeJobId.current = null;
      setBusy(false);
    }
  }

  async function rerunForYears(years: number) {
    const expandedStart = yearsBefore(endDate, years);
    setStartDate(expandedStart);
    setView("result");
    scrollWorkspaceTop();
    await runBacktest({ startDate: expandedStart });
  }

  function openResultSection(sectionId: string) {
    const element = document.getElementById(sectionId);
    if (element instanceof HTMLDetailsElement) element.open = true;
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSolverAction(action: { type: string; years?: number; section?: string }) {
    if (action.type === "RERUN_PERIOD" && action.years) {
      await rerunForYears(action.years);
      return;
    }
    if (action.type === "VIEW_SECTION" && action.section) openResultSection(action.section);
  }

  async function cancelRunningBacktest() {
    const jobId = activeJobId.current;
    if (!jobId) return;
    try {
      const cancelled = await cancelBacktestJob(jobId);
      setJob(cancelled);
      activeJobId.current = null;
      setBusy(false);
      setView("setup");
      scrollWorkspaceTop();
    } catch (err) {
      setError(err instanceof Error ? err.message : "백테스트 취소에 실패했습니다.");
    }
  }


  return (
    <section id="backtest-workspace" className="backtest-workspace">
      <div ref={workspaceTopRef} className="backtest-workspace-anchor" />

      <section className="backtest-page-head">
        <div>
          <span className="panel-kicker">BACKTEST WORKSPACE · v0.19.5</span>
          <h1>전략 백테스트</h1>
          <p>StockScope의 전략을 과거 데이터에 다시 적용해, 단순한 수익률이 아니라 <strong>어디서 실패했고 무엇을 다시 검증해야 하는지</strong> 찾습니다.</p>
        </div>
        <span className="source-chip">KRX EOD · 주문 없음</span>
      </section>

      <nav className="backtest-view-tabs" aria-label="백테스트 단계">
        <button type="button" className={view === "setup" ? "active" : ""} disabled={busy} onClick={() => { setView("setup"); scrollWorkspaceTop(); }}>1 · 설정</button>
        <button type="button" className={view === "result" ? "active" : ""} disabled={!result && !busy && !error} onClick={() => { setView("result"); scrollWorkspaceTop(); }}>2 · 결과</button>
      </nav>

      {view === "setup" && (
        <div className="backtest-setup-view">
          <section className="backtest-role-card">
            <div>
              <span>백테스트를 왜 하나요?</span>
              <strong>“이 전략이 좋아 보인다”를 믿기 전에, 과거에 실제로 어디서 통하고 어디서 실패했는지 확인합니다.</strong>
              <p>수익률 숫자만 보는 기능이 아닙니다. 진입이 너무 늦었는지, 특정 시장에서만 실패했는지, 손절 구조에 문제가 있었는지를 찾아 다음 검증 방향을 정합니다.</p>
            </div>
            <div className="backtest-role-flow">
              <span><b>전략 실행</b>과거 시점의 데이터만 사용</span><i>→</i>
              <span><b>문제 발견</b>손실이 생긴 조건 분리</span><i>→</i>
              <span><b>해결 검증</b>기간·진입·시장 조건 재검증</span>
            </div>
          </section>

          <section className="backtest-strategy-catalog">
            <div className="backtest-section-title"><span>검증할 전략</span><strong>현재는 눌림목 전략부터 검증합니다.</strong></div>
            <div className="backtest-strategy-options">
              <button type="button" className="active"><b>눌림목</b><span>상승 중 잠시 조정받은 뒤 재상승하는 구간</span></button>
              <button type="button" disabled><b>돌파</b><span>저항 가격을 강하게 넘어서는 구간 · 준비중</span></button>
              <button type="button" disabled><b>지지 반등</b><span>반복 지지 가격에서 반등하는 구간 · 준비중</span></button>
              <button type="button" disabled><b>추세 회복</b><span>약해진 추세가 다시 살아나는 구간 · 준비중</span></button>
            </div>
          </section>

          <section className="pullback-beginner-guide">
            <div className="pullback-guide-copy">
              <span>눌림목 전략이란?</span>
              <h2>오르는 주식을 아무 가격에서 따라 사지 않고, 잠시 쉬어간 뒤 다시 올라가는지 확인하는 방법입니다.</h2>
              <p>상승하던 주가도 계속 직선으로 오르지는 않습니다. 잠깐 가격이 내려오는 조정이 생겼을 때 <strong>상승 추세가 아직 살아 있고 지지 가격이 무너지지 않은 상태에서 다시 반등하는지</strong> 확인한 뒤 진입 후보로 봅니다.</p>
            </div>
            <div className="pullback-price-example" aria-label="눌림목 가격 예시">
              <div><small>① 상승</small><b>100,000원 → 120,000원</b><span>상승 추세가 만들어짐</span></div>
              <div><small>② 잠시 조정</small><b>113,000원</b><span>추세가 끝난 하락인지 잠시 쉬는지 확인</span></div>
              <div><small>③ 다시 반등</small><b>115,000원</b><span>지지가 살아 있으면 진입 후보 검토</span></div>
            </div>
            <div className="pullback-why-grid">
              <article><span>해결하려는 문제</span><strong>뒤늦은 추격 매수</strong><p>이미 많이 오른 가격을 따라 샀다가 바로 조정받는 위험을 줄이려는 전략입니다.</p></article>
              <article><span>StockScope가 확인</span><strong>추세 · 조정 · 지지 · 반등</strong><p>가격뿐 아니라 RSI와 거래량 회복까지 자동 확인해 “조정 중”과 “다시 올라가는 중”을 구분합니다.</p></article>
              <article><span>백테스트가 확인</span><strong>이 규칙이 실제로 통했나?</strong><p>과거에 같은 규칙을 반복 적용하고, 실패가 진입 시점·시장환경·손절 중 어디에서 발생했는지 찾습니다.</p></article>
            </div>
          </section>

          <section className="backtest-settings-card">
            <div className="backtest-section-title"><span>백테스트 설정</span><strong>종목과 검증 조건을 정한 뒤 실행합니다.</strong></div>
            <div className="backtest-stock-picker">
              <label htmlFor="backtest-stock-search">검증 종목</label>
              <div className="backtest-stock-search-box">
                <input id="backtest-stock-search" value={stockQuery} placeholder="종목명 또는 종목코드 검색" onFocus={() => stockSearchResults.length > 0 && setStockSearchOpen(true)} onChange={(event) => { setStockQuery(event.target.value); setStockSearchOpen(true); }} onKeyDown={(event) => { if (event.key === "Enter" && stockSearchResults[0]) { event.preventDefault(); chooseBacktestStock(stockSearchResults[0]); } }} />
                <span>{stockSearchBusy ? "검색 중" : code ? `${market} · ${code}` : "종목을 선택하세요"}</span>
                {stockSearchOpen && stockQuery.trim().length >= 2 && stockQuery !== selectedStockLabel && (
                  <div className="backtest-stock-results">
                    {stockSearchResults.length > 0 ? stockSearchResults.map((item) => (
                      <button key={`${item.market}-${item.code}`} type="button" onClick={() => chooseBacktestStock(item)}><strong>{item.name}</strong><span>{item.market} · {item.code}</span></button>
                    )) : <p>{stockSearchBusy ? "종목을 찾는 중입니다..." : "검색 결과가 없습니다."}</p>}
                  </div>
                )}
              </div>
              <p>빠른 조회와 종목 선택은 공유하지만, 백테스트 실행과 결과는 이 페이지에서 독립적으로 관리합니다.</p>
            </div>
            {stockSelectionDirty && <div className="backtest-selection-notice">검색 결과에서 종목을 선택해야 백테스트 대상이 변경됩니다.</div>}
            <div className="backtest-target compact">
              <div><span>현재 검증 대상</span><strong>{stockName || code || "종목 미선택"}</strong><small>{code ? `${market} · ${code}` : "위에서 종목을 선택하세요"}</small></div>
              <p>최신 재무·공시는 과거 시점의 미래정보가 섞일 수 있어 현재 백테스트 진입판정에서 제외합니다.</p>
            </div>
            <div className="backtest-config-grid">
              <label><span>시작일</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
              <label><span>종료일</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
              <label><span>초기 자본 <small>성과곡선 계산용</small></span><input type="number" min="1" step="100000" value={initialCapital} onChange={(event) => setInitialCapital(event.target.value)} /></label>
              <label><span>왕복 비용률 <small>수수료·세금·슬리피지 가정</small></span><div className="backtest-input-suffix"><input type="number" min="0" max="5" step="0.01" value={costPct} onChange={(event) => setCostPct(event.target.value)} /><b>%</b></div></label>
            </div>
            <div className="holding-config">
              <div className="holding-title"><div><strong>최대 보유기간</strong><span>손절·목표가가 먼저 발생하면 즉시 종료합니다. 이 값은 둘 다 발생하지 않았을 때 얼마나 기다릴지 정합니다.</span></div><b>{selectedHolding || "-"} 거래일</b></div>
              <div className="holding-buttons">
                {holdingOptions.map((option) => (<button key={option.days} type="button" className={!customHolding && maxHoldingDays === option.days ? "active" : ""} onClick={() => { setCustomHolding(""); setMaxHoldingDays(option.days); }}>{option.label}</button>))}
                <label className={customHolding ? "active" : ""}><span>직접 입력</span><input type="number" min="1" max="120" placeholder="거래일" value={customHolding} onChange={(event) => setCustomHolding(event.target.value)} /></label>
              </div>
              <p className="holding-explanation">{holdingDescription}</p>
            </div>
            <details className="backtest-policy-details">
              <summary>현재 백테스트 계산 기준 보기</summary>
              <div className="backtest-policy-strip"><span><b>진입</b> 반등 확인 후 다음 거래일 시가</span><span><b>동일 일봉 충돌</b> 손절 우선</span><span><b>중복 진입</b> 기존 거래 종료 전 금지</span><span><b>기본 청산</b> Risk Engine 1차 목표가</span></div>
            </details>
            <div className="backtest-run-row"><div><strong>실행하면 결과 화면으로 이동합니다.</strong><span>완료 후 결과 화면 맨 위에서 문제와 해결 방향부터 보여줍니다.</span></div><button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "백테스트 실행 중..." : "눌림목 전략 검증 시작"}</button></div>
            {error && <div className="backtest-error"><strong>실행 실패</strong><span>{error}</span></div>}
          </section>
        </div>
      )}

      {view === "result" && (
        <div className="backtest-result-view">
          <div className="backtest-result-toolbar">
            <div><span>검증 대상</span><strong>{stockName || code} · 눌림목 전략</strong><small>{formatCompactDate(startDate)} ~ {formatCompactDate(endDate)}</small></div>
            <button type="button" disabled={busy} onClick={() => { setView("setup"); scrollWorkspaceTop(); }}>설정 변경</button>
          </div>
          {busy && job && (
            <div className="backtest-progress-card">
              <div className="backtest-progress-head"><div><strong>{job.progress.message}</strong><span>{job.progress.current.toLocaleString()} / {job.progress.total.toLocaleString()} 항목 · {job.progress.percent.toFixed(1)}%</span></div><b>{job.elapsed_seconds.toFixed(1)}초 경과</b></div>
              <progress max={100} value={job.progress.percent} />
              <div className="backtest-progress-stats"><span><b>종목별 과거 저장소</b>{Number(job.progress.details.history_store_hits ?? 0).toLocaleString()} hit</span><span><b>기존 KRX 캐시</b>{Number(job.progress.details.raw_cache_hits ?? 0).toLocaleString()} hit</span><span><b>KRX 실제 요청</b>{Number(job.progress.details.network_requests ?? 0).toLocaleString()}회</span><span><b>재시도</b>{Number(job.progress.details.retries ?? 0).toLocaleString()}회</span></div>
              <button type="button" className="backtest-cancel-button" onClick={() => void cancelRunningBacktest()}>백테스트 취소</button>
            </div>
          )}
          {busy && !job && <div className="loading-card">백테스트 작업을 준비하고 있습니다...</div>}
          {error && <div className="backtest-error"><strong>실행 실패</strong><span>{error}</span><button type="button" onClick={() => { setView("setup"); scrollWorkspaceTop(); }}>설정으로 돌아가기</button></div>}
      {result && (
        <div className="backtest-results">
          <section className="backtest-result-purpose">
            <div>
              <span>이번 검증에서 StockScope가 답하는 질문</span>
              <strong>{stockName || code}에 눌림목 전략을 적용했을 때 어디가 문제였나요?</strong>
            </div>
            <ol>
              <li><b>전략 근거</b><span>이 종목·기간에서 실제로 성과가 있었는가</span></li>
              <li><b>실패 원인</b><span>진입 시점·시장 상황·손절 중 어디가 약했는가</span></li>
              <li><b>다음 해결</b><span>무엇을 더 검증해야 전략을 개선할 수 있는가</span></li>
            </ol>
          </section>
          {result.warnings.length > 0 && (
            <div className="backtest-warning">
              <strong>데이터 경고</strong>
              {result.warnings.map((warning) => <span key={warning}>{warning}</span>)}
            </div>
          )}

          {result.accuracy_audit && (
            <>
              <section className={`backtest-audit-summary audit-${result.accuracy_audit.status.toLowerCase()}`}>
                <div>
                  <span>이 결과를 믿어도 되나요?</span>
                  <strong>{result.accuracy_audit.label}</strong>
                  <h3>{result.accuracy_audit.headline}</h3>
                  <p>{result.accuracy_audit.summary}</p>
                </div>
                {result.accuracy_audit.flagged_trades.length > 0 && (
                  <button type="button" onClick={() => openResultSection("trade-detail-analysis")}>문제 거래 계산 근거 보기</button>
                )}
              </section>

              <details className="backtest-detail backtest-audit-detail">
                <summary><span><strong>백테스트 계산 정확성 점검</strong><small>미래 데이터·다음날 시가·손익 계산·Risk Engine 연결을 자동 검사했습니다.</small></span><b>펼치기</b></summary>
                <div className="backtest-audit-check-grid">
                  {result.accuracy_audit.checks.map((check) => (
                    <article key={check.id} className={`audit-check-${check.status.toLowerCase()}`}>
                      <span>{auditStatusLabel[check.status] ?? check.status}</span>
                      <strong>{check.title}</strong>
                      <p>{check.detail}</p>
                    </article>
                  ))}
                </div>
                {result.accuracy_audit.flagged_trades.length > 0 && (
                  <div className="backtest-audit-findings">
                    <strong>우선 확인할 거래</strong>
                    {result.accuracy_audit.flagged_trades.map((trade) => (
                      <article key={`${trade.signal_date}-${trade.entry_date}`}>
                        <b>{formatCompactDate(trade.signal_date ?? "")} 신호</b>
                        <span>진입 {formatWon(trade.entry_price)} → 손절 {formatWon(trade.stop_price)} · 손절 거리 {formatNumber(trade.stop_distance_pct, 2)}%</span>
                        <p>{trade.cause}</p>
                      </article>
                    ))}
                  </div>
                )}
                <div className="backtest-audit-policy-note">
                  <strong>현재 확인된 정책 연결</strong>
                  <p>{result.accuracy_audit.policy_observation}</p>
                  <p>{result.accuracy_audit.research_observation}</p>
                </div>
                <p className="backtest-solver-guardrail">{result.accuracy_audit.guardrail}</p>
              </details>
            </>
          )}

          {result.risk_policy_comparison && (
            <section id="risk-policy-analysis" className="backtest-risk-policy-solver">
              <div className="risk-policy-solver-head">
                <div>
                  <span>발견한 문제를 어떻게 줄일 수 있나요?</span>
                  <h3>{result.risk_policy_comparison.headline}</h3>
                  <p>{result.risk_policy_comparison.summary}</p>
                </div>
                <div className="risk-policy-problem-counts">
                  <span><b>{result.risk_policy_comparison.baseline_problem.caution_trades}건</b> CAUTION 포함</span>
                  <span><b>{result.risk_policy_comparison.baseline_problem.wide_stop_trades}건</b> {formatNumber(result.risk_policy_comparison.baseline_problem.wide_stop_threshold_pct, 0)}%+ 손절</span>
                </div>
              </div>

              {result.risk_policy_comparison.next_validation_candidate && (
                <div className="risk-policy-next-candidate">
                  <span>다음에 더 검증할 후보</span>
                  <strong>{result.risk_policy_comparison.next_validation_candidate.label}</strong>
                  <p>{result.risk_policy_comparison.next_validation_candidate.reason}</p>
                  <small>{result.risk_policy_comparison.next_validation_candidate.next_step}</small>
                </div>
              )}

              <div className="backtest-table-wrap">
                <table className="backtest-table risk-policy-table">
                  <thead>
                    <tr>
                      <th>비교 정책</th>
                      <th>해결하려는 문제</th>
                      <th>거래</th>
                      <th>거래당 평균</th>
                      <th>최대 낙폭</th>
                      <th>직접 바뀐 거래</th>
                      <th>StockScope 해석</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.risk_policy_comparison.scenarios.map((scenario) => {
                      const isCandidate = result.risk_policy_comparison?.next_validation_candidate?.policy_id === scenario.id;
                      const changed = scenario.id === "NEAREST_VALID_ANCHOR"
                        ? `${scenario.anchor_changed_trades}건 기준 변경`
                        : `${scenario.blocked_by_policy}건 진입 차단`;
                      return (
                        <tr key={scenario.id} className={isCandidate ? "risk-policy-candidate-row" : ""}>
                          <td>
                            <strong>{scenario.label}</strong>
                            <small>{scenario.short}</small>
                          </td>
                          <td>{scenario.problem_target}</td>
                          <td>{scenario.metrics.trades}건</td>
                          <td className={metricTone(scenario.metrics.expectancy_pct)}>
                            {formatPct(scenario.metrics.expectancy_pct)}
                            {scenario.id !== "CURRENT" && <small>현재 대비 {formatPctPoint(scenario.delta.expectancy_pctp)}</small>}
                          </td>
                          <td className={metricTone(scenario.delta.max_drawdown_pctp)}>
                            {formatPct(scenario.metrics.max_drawdown_pct)}
                            {scenario.id !== "CURRENT" && <small>현재 대비 {formatPctPoint(scenario.delta.max_drawdown_pctp)}</small>}
                          </td>
                          <td>{changed}</td>
                          <td>
                            <strong>{scenario.interpretation.headline}</strong>
                            <small>{scenario.interpretation.meaning}</small>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="risk-policy-decision">
                <strong>결론</strong>
                <p>{result.risk_policy_comparison.decision}</p>
                <small>{result.risk_policy_comparison.guardrail}</small>
              </div>
            </section>
          )}

          {result.problem_solver ? (
            <>
              <section className={`backtest-solver-verdict ${result.problem_solver.status.toLowerCase()}`}>
                <div>
                  <span>StockScope 문제 해결 판단</span>
                  <strong>{stockName || code} · {result.problem_solver.label}</strong>
                  <h3>{result.problem_solver.headline}</h3>
                  <p>{result.problem_solver.summary}</p>
                </div>
                <small>{formatCompactDate(result.period.start)} ~ {formatCompactDate(result.period.end)}</small>
              </section>

              <div className="backtest-solver-status-grid">
                <article className={`solver-tone ${result.problem_solver.performance.level.toLowerCase()}`}>
                  <span>현재 성과</span>
                  <strong>{result.problem_solver.performance.label}</strong>
                  <p>{result.problem_solver.performance.reason}</p>
                </article>
                <article className={`solver-tone ${result.problem_solver.risk.level.toLowerCase()}`}>
                  <span>위험 수준</span>
                  <strong>{result.problem_solver.risk.label}</strong>
                  <p>{result.problem_solver.risk.reason}</p>
                </article>
                <article className={`solver-tone ${result.problem_solver.confidence.level.toLowerCase()}`}>
                  <span>결과 신뢰도</span>
                  <strong>{result.problem_solver.confidence.label}</strong>
                  <p>{result.problem_solver.confidence.reason}</p>
                </article>
              </div>

              <section className="backtest-problem-section">
                <div className="backtest-section-heading">
                  <div>
                    <span>문제 → 원인 → 해결</span>
                    <h3>StockScope가 발견한 문제</h3>
                  </div>
                  <small>숫자를 직접 해석하지 않아도 되도록 우선순위대로 정리했습니다.</small>
                </div>
                {result.problem_solver.problems.length === 0 ? (
                  <div className="backtest-no-problem">
                    <strong>현재 데이터에서 뚜렷한 문제 패턴을 찾지 못했습니다.</strong>
                    <span>좋은 결과도 한 종목·한 기간만으로 채택하지 않고 다른 기간과 종목에서 재현되는지 확인해야 합니다.</span>
                  </div>
                ) : (
                  <div className="backtest-problem-list">
                    {result.problem_solver.problems.map((problem, index) => (
                      <article key={problem.id} className={`backtest-problem-card severity-${problem.severity.toLowerCase()}`}>
                        <div className="problem-index">{index + 1}</div>
                        <div className="problem-body">
                          <strong>{problem.title}</strong>
                          <dl>
                            <div><dt>근거</dt><dd>{problem.evidence}</dd></div>
                            <div><dt>왜 문제인가</dt><dd>{problem.meaning}</dd></div>
                            <div className="solution"><dt>해결 방법</dt><dd>{problem.solution}</dd></div>
                          </dl>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="backtest-next-actions">
                <div className="backtest-section-heading">
                  <div>
                    <span>다음 행동</span>
                    <h3>이 결과를 어떻게 활용할까요?</h3>
                  </div>
                  <small>앱이 할 수 있는 재검증은 버튼으로 바로 실행합니다.</small>
                </div>
                {result.problem_solver.next_actions.length > 0 ? (
                  <div className="backtest-action-grid">
                    {result.problem_solver.next_actions.map((action) => (
                      <article key={action.id}>
                        <strong>{action.label}</strong>
                        <p>{action.description}</p>
                        <button type="button" disabled={busy} onClick={() => void handleSolverAction(action)}>
                          {action.type === "RERUN_PERIOD" ? "바로 다시 검증" : "근거 보기"}
                        </button>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="backtest-no-problem">
                    <strong>다음 단계는 재현성 확인입니다.</strong>
                    <span>현재 종목·기간에서만 좋은 결과인지 다른 기간과 종목에서도 반복되는지 확인한 뒤 규칙 변경을 검토합니다.</span>
                  </div>
                )}
              </section>

              {result.problem_solver.strategy_candidate && (
                <section className="backtest-candidate-card">
                  <span>충분한 표본에서 발견된 개선 후보</span>
                  <strong>{result.problem_solver.strategy_candidate.title}</strong>
                  <p>{result.problem_solver.strategy_candidate.reason}</p>
                  <small>{result.problem_solver.strategy_candidate.next_validation}</small>
                </section>
              )}

              <p className="backtest-solver-guardrail">{result.problem_solver.guardrail}</p>
            </>
          ) : (
            <section className={`backtest-verdict ${result.assessment.status.toLowerCase()}`}>
              <div>
                <span>과거 검증 결과</span>
                <strong>{result.assessment.label}</strong>
                <p>{result.assessment.summary}</p>
              </div>
            </section>
          )}

          <details className="backtest-detail evidence-summary">
            <summary><span><strong>숫자 근거 자세히 보기</strong><small>현재 판단에 사용된 승률·손익·낙폭·자본 변화를 확인합니다.</small></span><b>펼치기</b></summary>
            <div className="backtest-summary-grid">
              <article>
                <span>실제 규칙 거래</span>
                <strong>{result.summary.trades}회</strong>
                <small>현재 반등 확인 규칙으로 실제 진입한 표본</small>
              </article>
              <article>
                <span>승률</span>
                <strong>{result.summary.win_rate_pct == null ? "-" : `${formatNumber(result.summary.win_rate_pct, 1)}%`}</strong>
                <small>승 {result.summary.wins} · 패 {result.summary.losses}</small>
              </article>
              <article className={metricTone(result.summary.average_net_return_pct)}>
                <span>비용 반영 평균 손익</span>
                <strong>{formatPct(result.summary.average_net_return_pct)}</strong>
                <small>비용 전 {formatPct(result.summary.average_gross_return_pct)}</small>
              </article>
              <article className={metricTone(result.summary.expectancy_pct)}>
                <span>거래 1회당 평균</span>
                <strong>{formatPct(result.summary.expectancy_pct)}</strong>
                <small>현재 표본의 평균 결과</small>
              </article>
              <article>
                <span>수익/손실 비율</span>
                <strong>{formatNumber(result.summary.profit_factor, 2)}</strong>
                <small>1보다 크면 총수익이 총손실보다 큼</small>
              </article>
              <article className={metricTone(result.summary.max_drawdown_pct)}>
                <span>최대 낙폭</span>
                <strong>{formatPct(result.summary.max_drawdown_pct)}</strong>
                <small>보유 중 평가손실까지 포함</small>
              </article>
            </div>
            <div className="backtest-capital-strip">
              <div><span>초기 자본</span><strong>{formatWon(result.summary.initial_capital)}</strong></div>
              <div><span>최종 가상 자본</span><strong>{formatWon(result.summary.final_capital)}</strong></div>
              <div><span>누적 비용 반영 손익</span><strong className={metricTone(result.summary.total_net_return_pct)}>{formatPct(result.summary.total_net_return_pct)}</strong></div>
              <div><span>평균 보유</span><strong>{result.summary.average_holding_days == null ? "-" : `${formatNumber(result.summary.average_holding_days, 1)}일`}</strong></div>
            </div>
          </details>

          <details id="entry-timing-analysis" className="backtest-detail">
            <summary><span><strong>진입 시점은 언제가 나았나요?</strong><small>7가지 확인 조건 중 몇 개가 충족됐을 때 결과가 달랐는지 비교합니다.</small></span><b>펼치기</b></summary>
            <div className="backtest-inline-explainer">
              <strong>3/7~7/7의 뜻</strong>
              <p>StockScope가 진입 전에 확인하는 7가지 조건 중 몇 개가 충족됐는지를 뜻합니다. 숫자가 높다고 무조건 더 좋은 신호는 아니며, 이 표는 현재 진입 규칙이 너무 이르거나 늦은지 찾기 위한 연구입니다.</p>
            </div>
            <MetricTable
              rows={result.entry_timing_research.map((row) => ({ ...row, key: row.entry_timing }))}
              firstColumn="확인된 조건"
            />
            <p className="backtest-note">좋아 보이는 구간이 있어도 한 종목의 결과만으로 진입 규칙을 자동 변경하지 않습니다. 충분한 표본에서 반복되는지 먼저 검증합니다.</p>
          </details>

          <details id="market-regime-analysis" className="backtest-detail">
            <summary><span><strong>어떤 시장에서 잘·못 작동했나요?</strong><small>눌림목 전략이 시장 상황에 따라 달라지는지 확인합니다.</small></span><b>펼치기</b></summary>
            <MetricTable
              rows={result.market_regime_performance}
              firstColumn="시장 상황"
              keyLabel={(key) => regimeLabel[key] ?? key}
            />
            <p className="backtest-note">시장별 차이가 반복되면 “모든 시장에서 사용”이 아니라 특정 시장에서만 켜는 전략 필터를 검증할 수 있습니다.</p>
          </details>

          <details className="backtest-detail">
            <summary><span><strong>전략 점수는 실제 성과와 연결됐나요?</strong><small>높은 적합도 점수가 실제 결과도 좋았는지 확인합니다.</small></span><b>펼치기</b></summary>
            <MetricTable rows={result.score_performance} firstColumn="전략 적합도" />
            <p className="backtest-note">전략 적합도는 상승확률이 아닙니다. 높은 점수 구간이 반복해서 더 좋은 결과를 내는지 검증하는 용도입니다.</p>
          </details>

          <details id="trade-detail-analysis" className="backtest-detail">
            <summary><span><strong>실제 거래에서 어디서 실패했나요?</strong><small>각 거래의 신호 → 다음날 시가 → 손절 계산 → 청산 경로까지 추적합니다.</small></span><b>펼치기</b></summary>
            {result.trades.length === 0 ? (
              <p className="backtest-empty-row">선택 기간에는 현재 기본 진입 규칙을 충족한 거래가 없습니다.</p>
            ) : (
              <div className="backtest-table-wrap">
                <table className="backtest-table trade-table audit-trade-table">
                  <thead><tr><th>신호</th><th>진입</th><th>손절 기준</th><th>1차 목표</th><th>청산</th><th>적합도</th><th>조건</th><th>손익</th><th>종료 이유</th><th>계산 근거</th></tr></thead>
                  <tbody>
                    {result.trades.map((trade) => {
                      const tradeKey = `${trade.signal_date}-${trade.entry_date}`;
                      const trace = trade.metadata.audit;
                      const stopDistance = trace?.risk?.initial_stop_distance_pct
                        ?? ((trade.entry_price - trade.stop_price) / trade.entry_price * 100);
                      const isWideStop = stopDistance >= 12;
                      const isExpanded = expandedTradeKey === tradeKey;
                      return (
                        <Fragment key={tradeKey}>
                          <tr>
                            <td>{formatCompactDate(trade.signal_date)}</td>
                            <td>{formatWon(trade.entry_price)}</td>
                            <td className={isWideStop ? "audit-warning-cell" : ""}>
                              {formatWon(trade.stop_price)}
                              <small>손절 거리 {formatNumber(stopDistance, 2)}%</small>
                            </td>
                            <td>{formatWon(trade.target1_price)}</td>
                            <td>{formatWon(trade.exit_price)}</td>
                            <td>{trade.strategy_score}</td>
                            <td>{trade.entry_timing_passed}/{trade.entry_timing_total}</td>
                            <td className={metricTone(trade.net_return_pct)}>{formatPct(trade.net_return_pct)}</td>
                            <td>{exitReasonLabel[trade.exit_reason] ?? trade.exit_reason}</td>
                            <td><button type="button" className="trade-audit-toggle" onClick={() => setExpandedTradeKey(isExpanded ? null : tradeKey)}>{isExpanded ? "닫기" : "근거 보기"}</button></td>
                          </tr>
                          {isExpanded && (
                            <tr className="trade-audit-row">
                              <td colSpan={10}>
                                {trace ? (
                                  <div className="trade-audit-panel">
                                    <div className="trade-audit-head">
                                      <div>
                                        <span>이 거래가 만들어진 계산 경로</span>
                                        <strong>{formatCompactDate(trade.signal_date)} 신호 → {formatCompactDate(trade.entry_date)} 진입 → {formatCompactDate(trade.exit_date)} 청산</strong>
                                      </div>
                                      {trace.flags && trace.flags.length > 0 && (
                                        <div className="trade-audit-flags">{trace.flags.map((flag) => <b key={flag}>{auditFlagLabel[flag] ?? flag}</b>)}</div>
                                      )}
                                    </div>

                                    <div className="trade-audit-grid">
                                      <article>
                                        <span>1 · 신호 계산</span>
                                        <strong>신호일까지만 사용</strong>
                                        <dl>
                                          <div><dt>종목 데이터 끝</dt><dd>{formatCompactDate(trace.signal_boundary?.stock_history_end_date ?? trade.signal_date)}</dd></div>
                                          <div><dt>시장 데이터 끝</dt><dd>{formatCompactDate(trace.signal_boundary?.index_history_end_date ?? trade.signal_date)}</dd></div>
                                          <div><dt>미래 데이터</dt><dd>{trace.signal_boundary?.future_data_used ? "사용됨 · 오류" : "사용 안 함"}</dd></div>
                                        </dl>
                                      </article>

                                      <article>
                                        <span>2 · 실제 가상 진입</span>
                                        <strong>다음 거래일 시가</strong>
                                        <dl>
                                          <div><dt>신호일 종가</dt><dd>{formatWon(trace.entry?.signal_close)}</dd></div>
                                          <div><dt>다음날 시가</dt><dd>{formatWon(trace.entry?.entry_open ?? trade.entry_price)}</dd></div>
                                          <div><dt>시가 갭</dt><dd>{formatPct(trace.entry?.gap_from_signal_close_pct)}</dd></div>
                                          <div><dt>규칙 확인</dt><dd>{trace.entry?.next_trading_day_open_verified ? "정상" : "확인 필요"}</dd></div>
                                        </dl>
                                      </article>

                                      <article className={isWideStop ? "trade-audit-risk-card warning" : "trade-audit-risk-card"}>
                                        <span>3 · 손절 기준 계산</span>
                                        <strong>{formatWon(trace.risk?.invalidation_price ?? trade.stop_price)}</strong>
                                        <dl>
                                          <div><dt>구조적 기준</dt><dd>{trace.risk?.structural_anchor_label ?? "-"} {formatWon(trace.risk?.structural_anchor)}</dd></div>
                                          <div><dt>진입→구조 기준</dt><dd>{formatNumber(trace.risk?.anchor_distance_from_entry_pct, 2)}%</dd></div>
                                          <div><dt>ATR</dt><dd>{formatNumber(trace.risk?.atr_pct, 2)}% · {formatWon(trace.risk?.atr_value_at_entry)}</dd></div>
                                          <div><dt>ATR 여유</dt><dd>{formatNumber(trace.risk?.buffer_factor, 2)}배 · 진입가 대비 {formatNumber(trace.risk?.atr_buffer_from_anchor_pct, 2)}%</dd></div>
                                          <div><dt>최종 손절 거리</dt><dd><b>{formatNumber(stopDistance, 2)}%</b></dd></div>
                                          <div><dt>Risk 판정</dt><dd>{trace.risk?.risk_plan_status ?? trade.risk_plan_status} · {trace.risk?.structure_rating ?? "-"}</dd></div>
                                        </dl>
                                        <p>{trace.risk?.formula}</p>
                                      </article>

                                      <article>
                                        <span>4 · 실제 청산</span>
                                        <strong>{exitReasonLabel[trade.exit_reason] ?? trade.exit_reason}</strong>
                                        <dl>
                                          <div><dt>청산일 시가</dt><dd>{formatWon(trace.execution?.exit_open)}</dd></div>
                                          <div><dt>고가 / 저가</dt><dd>{formatWon(trace.execution?.exit_high)} / {formatWon(trace.execution?.exit_low)}</dd></div>
                                          <div><dt>청산가</dt><dd>{formatWon(trade.exit_price)}</dd></div>
                                          <div><dt>Gross</dt><dd>{formatPct(trace.execution?.gross_return_pct ?? trade.gross_return_pct)}</dd></div>
                                          <div><dt>비용</dt><dd>-{formatNumber(trace.execution?.round_trip_cost_pct, 3)}%</dd></div>
                                          <div><dt>Net</dt><dd className={metricTone(trade.net_return_pct)}>{formatPct(trace.execution?.net_return_pct ?? trade.net_return_pct)}</dd></div>
                                        </dl>
                                      </article>
                                    </div>

                                    {trace.risk?.risk_plan_status === "CAUTION" && (
                                      <div className="trade-audit-policy-warning">
                                        <strong>왜 CAUTION인데 거래가 만들어졌나요?</strong>
                                        <p>현재 백테스트는 Risk Engine의 <b>reference_only</b>만 진입 금지로 사용합니다. CAUTION은 “구조가 불리하거나 손절 폭이 넓다”는 경고이지만 현재 정책상 거래 자체는 허용됩니다. v0.19.5에서도 현재 실제 규칙은 그대로 두고, 아래 Risk 정책 비교에서 어떤 차단 방식이 문제를 줄이는지 별도 연구합니다.</p>
                                      </div>
                                    )}
                                    {trace.risk?.warnings && trace.risk.warnings.length > 0 && (
                                      <div className="trade-audit-risk-warnings">
                                        <strong>당시 Risk Engine 경고</strong>
                                        {trace.risk.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <p className="backtest-empty-row">이 결과는 정확성 감사 이전 형식이라 거래 계산 추적 정보가 없습니다. 같은 조건으로 다시 실행하면 근거가 생성됩니다.</p>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </details>

          {result.performance && (
            <details className="backtest-detail performance">
              <summary><span><strong>실행 성능 진단</strong><small>데이터 준비와 전략 계산이 어디에서 시간을 사용했는지 확인합니다.</small></span><b>펼치기</b></summary>
              <div className="backtest-performance-grid">
                <span><b>전체</b>{formatNumber(result.performance.total_seconds, 2)}초</span>
                <span><b>데이터 준비</b>{formatNumber(result.performance.data_prepare_seconds, 2)}초</span>
                <span><b>전략 계산</b>{formatNumber(result.performance.strategy_calculation_seconds, 2)}초</span>
                <span><b>KRX 실제 요청</b>{result.performance.network_requests.toLocaleString()}회</span>
                <span><b>종목별 과거 저장소</b>{result.performance.history_store_hits.toLocaleString()} hit</span>
                <span><b>기존 KRX 캐시</b>{result.performance.raw_cache_hits.toLocaleString()} hit</span>
              </div>
            </details>
          )}

          <details className="backtest-detail methodology">
            <summary><span><strong>백테스트 방법론·한계</strong><small>미래 데이터 누수 방지와 계산 가정을 확인합니다.</small></span><b>펼치기</b></summary>
            <div className="backtest-methodology">
              {Object.entries(result.methodology).map(([key, value]) => (
                <p key={key}><strong>{methodologyLabel[key] ?? key.replace(/_/g, " ")}</strong><span>{value}</span></p>
              ))}
            </div>
          </details>
        </div>
      )}

        </div>
      )}
    </section>
  );
}
