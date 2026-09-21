import { useEffect, useMemo, useState } from "react";
import {
  buySimulationPosition,
  createSimulationPortfolio,
  createSimulationSession,
  getSimulationMarks,
  getSimulationPortfolio,
  getSimulationPositions,
  getSimulationQuote,
  getSimulationSession,
  nextSimulationDay,
  sellSimulationPosition,
  SimulationApiError,
  type PositionMark,
  type SimulationPortfolio,
  type SimulationPosition,
  type SimulationSession,
} from "../services/simulationApi";
import { searchStocks, type ScannerCandidate, type StockSearchItem } from "../services/api";
import { readScannerSession } from "./scannerSession";
import "../simulation.css";

const STORAGE_KEY = "stockscope-simulation-portfolio";

type BuyChoice = {
  code: string;
  name: string;
  market: "KOSPI" | "KOSDAQ";
  origin: "SCANNER" | "SEARCH";
};

function numeric(value: string | number | null | undefined) {
  const parsed = typeof value === "number" ? value : Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function krw(value: string | number | null | undefined) {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(numeric(value))}원`;
}

function percent(value: string | number | null | undefined) {
  const number = numeric(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function signedMoney(value: string | number | null | undefined) {
  const number = numeric(value);
  return `${number > 0 ? "+" : number < 0 ? "-" : ""}${krw(Math.abs(number))}`;
}

function tone(value: string | number | null | undefined) {
  const number = numeric(value);
  return number > 0 ? "sim-positive" : number < 0 ? "sim-negative" : "";
}

function dateText(value: string | null | undefined) {
  if (!value) return "-";
  return value.replace(/-/g, ".");
}

function errorText(error: unknown) {
  if (!(error instanceof SimulationApiError)) return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
  const known: Record<string, string> = {
    SIM_INSUFFICIENT_CASH: "가상계좌의 현금이 부족합니다.",
    SIM_INSUFFICIENT_QUANTITY: "보유 수량보다 많이 매도할 수 없습니다.",
    SIM_POSITION_CLOSED: "이미 종료된 포지션입니다.",
    SIM_INVALID_TRADING_DATE: "해당 날짜에는 사용할 수 있는 확정 시장 데이터가 없습니다.",
    SIM_END_OF_RANGE: "설정한 시뮬레이션 마지막 날짜입니다.",
    SIM_END_OF_MARKET_DATA: "저장된 시장 데이터의 마지막 날짜입니다.",
    SIM_SESSION_NOT_FOUND: "먼저 시뮬레이션 기간을 설정해주세요.",
    SIM_MARKET_DATA_MISSING: "현재 시뮬레이션 날짜에 이 종목의 저장된 가격이 없습니다.",
  };
  return (error.code && known[error.code]) || error.message;
}

function scannerToChoice(candidate: ScannerCandidate): BuyChoice {
  return { code: candidate.code, name: candidate.name, market: candidate.market, origin: "SCANNER" };
}

function searchToChoice(item: StockSearchItem): BuyChoice {
  return { code: item.code, name: item.name, market: item.market, origin: "SEARCH" };
}

export default function SimulationWorkspace() {
  const [portfolioId, setPortfolioId] = useState(() => window.localStorage.getItem(STORAGE_KEY) ?? "");
  const [portfolio, setPortfolio] = useState<SimulationPortfolio | null>(null);
  const [positions, setPositions] = useState<SimulationPosition[]>([]);
  const [marks, setMarks] = useState<Record<string, PositionMark>>({});
  const [session, setSession] = useState<SimulationSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [portfolioName, setPortfolioName] = useState("기본 시뮬레이션");
  const [initialCash, setInitialCash] = useState("10000000");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [buyOpen, setBuyOpen] = useState(false);
  const [buyMode, setBuyMode] = useState<"recommend" | "search">("recommend");
  const [buyChoice, setBuyChoice] = useState<BuyChoice | null>(null);
  const [buyQuantity, setBuyQuantity] = useState("1");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyQuoteDate, setBuyQuoteDate] = useState("");
  const [buyError, setBuyError] = useState<string | null>(null);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [stockQuery, setStockQuery] = useState("");
  const [stockSearchBusy, setStockSearchBusy] = useState(false);
  const [stockSearchRows, setStockSearchRows] = useState<StockSearchItem[]>([]);

  const [sellTarget, setSellTarget] = useState<SimulationPosition | null>(null);
  const [sellQuantity, setSellQuantity] = useState("1");
  const [sellPrice, setSellPrice] = useState("");

  const scannerSnapshot = useMemo(() => readScannerSession(), []);
  const scannerDate = scannerSnapshot?.result?.requested_as_of ?? null;
  const scannerCandidates = useMemo(
    () => scannerSnapshot?.result?.candidates ?? [],
    [scannerSnapshot],
  );
  const alignedScannerCandidates = useMemo(
    () => session ? scannerCandidates.filter((candidate) => candidate.data_date === session.current_date) : [],
    [scannerCandidates, session],
  );

  const buyPreview = numeric(buyQuantity) * numeric(buyPrice);
  const sellPreview = sellTarget ? numeric(sellQuantity) * numeric(sellPrice) : 0;
  const sellPnlPreview = sellTarget
    ? (numeric(sellPrice) - numeric(sellTarget.average_entry_price)) * numeric(sellQuantity)
    : 0;
  const markMap = useMemo(() => marks, [marks]);

  async function refresh(id = portfolioId) {
    if (!id) return;
    const [summary, openPositions, markRows] = await Promise.all([
      getSimulationPortfolio(id),
      getSimulationPositions(id),
      getSimulationMarks(id),
    ]);
    setPortfolio(summary);
    setPositions(openPositions);
    setMarks(Object.fromEntries(markRows.map((row) => [row.position_id, row])));
    try {
      setSession(await getSimulationSession(id));
    } catch (error) {
      if (error instanceof SimulationApiError && error.code === "SIM_SESSION_NOT_FOUND") setSession(null);
      else throw error;
    }
  }

  useEffect(() => {
    if (!portfolioId) return;
    setBusy(true);
    void refresh(portfolioId)
      .catch((error) => {
        if (error instanceof SimulationApiError && error.status === 404) {
          window.localStorage.removeItem(STORAGE_KEY);
          setPortfolioId("");
          setPortfolio(null);
          return;
        }
        setMessage(errorText(error));
      })
      .finally(() => setBusy(false));
  }, [portfolioId]);

  async function createPortfolio() {
    if (numeric(initialCash) <= 0) return setMessage("초기 투자금은 0보다 커야 합니다.");
    setBusy(true); setMessage(null);
    try {
      const created = await createSimulationPortfolio(portfolioName.trim() || "기본 시뮬레이션", initialCash);
      window.localStorage.setItem(STORAGE_KEY, created.id);
      setPortfolioId(created.id);
      await refresh(created.id);
    } catch (error) { setMessage(errorText(error)); }
    finally { setBusy(false); }
  }

  async function createSession() {
    if (!portfolioId || !startDate) return setMessage("시작 거래일을 입력해주세요.");
    setBusy(true); setMessage(null);
    try {
      setSession(await createSimulationSession(portfolioId, startDate, endDate || undefined));
      await refresh(portfolioId);
    } catch (error) { setMessage(errorText(error)); }
    finally { setBusy(false); }
  }

  function resetBuyDialog() {
    setBuyChoice(null);
    setBuyQuantity("1");
    setBuyPrice("");
    setBuyQuoteDate("");
    setBuyError(null);
    setStockQuery("");
    setStockSearchRows([]);
  }

  function openBuyDialog(mode: "recommend" | "search" = "recommend") {
    if (!session) {
      setMessage("먼저 시뮬레이션 기간을 설정해주세요. 거래일을 정하면 종목 가격을 자동으로 불러옵니다.");
      return;
    }
    resetBuyDialog();
    setBuyMode(mode);
    setBuyOpen(true);
  }

  async function selectBuyStock(choice: BuyChoice) {
    if (!portfolioId || !session) return;
    setBuyChoice(choice);
    setBuyPrice("");
    setBuyQuoteDate("");
    setBuyError(null);
    setQuoteBusy(true);
    try {
      const quote = await getSimulationQuote(portfolioId, choice.code, choice.market);
      setBuyPrice(quote.close);
      setBuyQuoteDate(quote.trading_date);
    } catch (error) {
      setBuyError(errorText(error));
    } finally {
      setQuoteBusy(false);
    }
  }

  function openRecommended(candidate: ScannerCandidate) {
    openBuyDialog("recommend");
    void selectBuyStock(scannerToChoice(candidate));
  }

  async function runStockSearch() {
    const query = stockQuery.trim();
    if (!query) return setBuyError("종목명이나 종목코드를 입력해주세요.");
    setStockSearchBusy(true); setBuyError(null);
    try {
      const result = await searchStocks(query);
      setStockSearchRows(result.rows);
      if (result.rows.length === 0) setBuyError("검색 결과가 없습니다.");
    } catch (error) {
      setBuyError(error instanceof Error ? error.message : "종목 검색에 실패했습니다.");
    } finally {
      setStockSearchBusy(false);
    }
  }

  async function buy() {
    if (!portfolioId || !buyChoice || numeric(buyQuantity) <= 0 || numeric(buyPrice) <= 0) {
      return setBuyError("종목과 수량을 확인해주세요.");
    }
    setBusy(true); setBuyError(null); setMessage(null);
    try {
      await buySimulationPosition(portfolioId, {
        stock_code: buyChoice.code,
        stock_name: buyChoice.name,
        market: buyChoice.market,
        quantity: Math.trunc(numeric(buyQuantity)),
        execution_price: buyPrice,
      });
      setBuyOpen(false);
      resetBuyDialog();
      await refresh(portfolioId);
    } catch (error) { setBuyError(errorText(error)); }
    finally { setBusy(false); }
  }

  async function sell() {
    if (!portfolioId || !sellTarget || numeric(sellQuantity) <= 0 || numeric(sellPrice) <= 0) return setMessage("매도 수량과 가격을 확인해주세요.");
    setBusy(true); setMessage(null);
    try {
      await sellSimulationPosition(portfolioId, {
        position_id: sellTarget.id,
        quantity: Math.trunc(numeric(sellQuantity)),
        execution_price: sellPrice,
      });
      setSellTarget(null);
      await refresh(portfolioId);
    } catch (error) { setMessage(errorText(error)); }
    finally { setBusy(false); }
  }

  async function nextDay() {
    if (!portfolioId) return;
    setBusy(true); setMessage(null);
    try {
      const result = await nextSimulationDay(portfolioId);
      setMessage(`${dateText(result.previous_date)} → ${dateText(result.current_date)} 가격을 반영했습니다.`);
      await refresh(portfolioId);
    } catch (error) { setMessage(errorText(error)); }
    finally { setBusy(false); }
  }

  function goToScanner() {
    window.history.pushState({}, "", "/scanner");
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  if (!portfolioId || !portfolio) {
    return (
      <section className="simulation-workspace simulation-setup">
        <span className="sim-eyebrow">과거 시뮬레이션</span>
        <h1>과거 전략 검증 시작</h1>
        <p>Scanner 전략을 과거 시장에서 재현·검증하는 연구용 도구입니다. 일반 추천 추적과는 별개로 동작합니다.</p>
        {message && <div className="sim-notice error">{message}</div>}
        <div className="sim-form-grid compact">
          <label>이름<input value={portfolioName} onChange={(e: { target: { value: string } }) => setPortfolioName(e.target.value)} /></label>
          <label>초기 투자금<input inputMode="decimal" value={initialCash} onChange={(e: { target: { value: string } }) => setInitialCash(e.target.value.replace(/[^0-9.]/g, ""))} /></label>
        </div>
        <button className="sim-primary" disabled={busy} onClick={() => void createPortfolio()}>{busy ? "생성 중…" : "가상 포트폴리오 만들기"}</button>
      </section>
    );
  }

  const scannerDateAligned = Boolean(session && scannerDate && scannerDate === session.current_date);

  return (
    <section className="simulation-workspace">
      <header className="sim-page-head">
        <div>
          <span className="sim-eyebrow">과거 시뮬레이션</span>
          <h1>과거 전략 검증</h1>
          <p>{portfolio.name} · 실제 주문 없이 로컬 확정 일봉 데이터로 진행</p>
        </div>
        <div className="sim-date-block">
          <span>현재 거래일</span>
          <strong>{dateText(session?.current_date)}</strong>
          <small>{session ? "진행 중" : "시작 전"}</small>
        </div>
      </header>

      {message && <div className={`sim-notice ${message.includes("못") || message.includes("없") || message.includes("부족") ? "error" : ""}`}>{message}</div>}

      {!session && (
        <section className="sim-session-setup">
          <div><span className="sim-section-kicker">기간 설정</span><h2>시뮬레이션 기간 설정</h2><p>확정 시장 데이터가 존재하는 거래일을 입력합니다.</p></div>
          <div className="sim-form-grid">
            <label>시작 거래일<input type="date" value={startDate} onChange={(e: { target: { value: string } }) => setStartDate(e.target.value)} /></label>
            <label>종료 거래일 <small>선택</small><input type="date" value={endDate} onChange={(e: { target: { value: string } }) => setEndDate(e.target.value)} /></label>
            <button className="sim-primary" disabled={busy || !startDate} onClick={() => void createSession()}>시작</button>
          </div>
        </section>
      )}

      <div className="sim-summary-strip">
        <div><span>총 자산</span><strong>{krw(portfolio.total_equity)}</strong><small className={tone(portfolio.total_return_pct)}>{percent(portfolio.total_return_pct)}</small></div>
        <div><span>현금</span><strong>{krw(portfolio.cash_balance)}</strong></div>
        <div><span>평가손익</span><strong className={tone(portfolio.unrealized_pnl)}>{signedMoney(portfolio.unrealized_pnl)}</strong></div>
        <div><span>실현손익</span><strong className={tone(portfolio.realized_pnl)}>{signedMoney(portfolio.realized_pnl)}</strong></div>
      </div>

      <section className="sim-positions-section">
        <div className="sim-section-head">
          <div><span className="sim-section-kicker">보유 현황</span><h2>보유 종목</h2></div>
          <button className="sim-secondary" disabled={!session} onClick={() => openBuyDialog()}>+ 종목 추가</button>
        </div>
        {positions.length === 0 ? (
          <div className="sim-empty"><strong>현재 보유 중인 종목이 없습니다.</strong><span>{session ? "추천 종목을 고르거나 직접 찾아서 추가할 수 있습니다." : "먼저 시뮬레이션 기간을 설정해주세요."}</span></div>
        ) : (
          <div className="sim-table-wrap">
            <table className="sim-table">
              <thead><tr><th>종목</th><th>수량</th><th>평균매수가</th><th>현재가</th><th>평가금액</th><th>평가손익</th><th>수익률</th><th>가격 상태</th><th /></tr></thead>
              <tbody>{positions.map((position) => {
                const mark = markMap[position.id];
                const stale = Boolean(mark?.valuation_stale);
                return <tr key={position.id}>
                  <td><div className="sim-stock-identity"><strong>{position.stock_name}</strong><small>{position.stock_code}</small></div></td>
                  <td>{position.quantity}주</td>
                  <td>{krw(position.average_entry_price)}</td>
                  <td>{krw(position.current_price)}</td>
                  <td>{krw(position.market_value)}</td>
                  <td className={tone(position.unrealized_pnl)}>{signedMoney(position.unrealized_pnl)}</td>
                  <td className={tone(position.unrealized_pnl_pct)}>{percent(position.unrealized_pnl_pct)}</td>
                  <td><span className={`sim-price-state ${stale ? "stale" : ""}`}>{stale ? "이전 거래일 가격" : mark?.price_status === "FRESH" ? `${dateText(mark.source_bar_date)} 종가` : "매수가 기준"}</span></td>
                  <td><button className="sim-text-button" onClick={() => { setSellTarget(position); setSellQuantity(String(position.quantity)); setSellPrice(position.current_price); }}>매도</button></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        )}

        {session && (
          <div className="sim-scanner-add">
            <div className="sim-scanner-add-head">
              <div><strong>종목 찾기 추천에서 추가</strong><span>현재 거래일과 같은 날짜의 추천만 사용합니다.</span></div>
              {scannerSnapshot ? <small>종목 찾기 기준일 {dateText(scannerDate)}</small> : <button className="sim-text-button" onClick={goToScanner}>종목 찾기로 이동</button>}
            </div>
            {!scannerSnapshot ? (
              <p>아직 저장된 종목 찾기 결과가 없습니다.</p>
            ) : !scannerDateAligned ? (
              <div className="sim-inline-warning">현재 시뮬레이션 거래일은 {dateText(session.current_date)}이고 종목 찾기 결과는 {dateText(scannerDate)}입니다. 미래 정보를 섞지 않도록 바로 추가를 막았습니다. 같은 날짜로 종목 찾기를 실행해주세요.</div>
            ) : alignedScannerCandidates.length === 0 ? (
              <p>이 날짜에는 바로 추가할 추천 종목이 없습니다.</p>
            ) : (
              <div className="sim-recommend-row">
                {alignedScannerCandidates.slice(0, 5).map((candidate) => (
                  <button key={`${candidate.market}-${candidate.code}`} onClick={() => openRecommended(candidate)}>
                    <span><strong>{candidate.name}</strong><small>{candidate.code}</small></span>
                    <em>{candidate.action_label}</em>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="sim-timeline">
        <div><span className="sim-section-kicker">날짜 진행</span><h2>{session ? dateText(session.current_date) : "기간을 먼저 설정하세요"}</h2><p>다음 거래일의 확정 종가로 열린 보유 종목을 다시 평가합니다.</p></div>
        <button className="sim-primary" disabled={busy || !session} onClick={() => void nextDay()}>{busy ? "업데이트 중…" : "다음 거래일 →"}</button>
      </section>

      {buyOpen && <div className="sim-dialog-backdrop" onMouseDown={() => !busy && setBuyOpen(false)}><div className="sim-dialog sim-buy-dialog" onMouseDown={(e: { stopPropagation(): void }) => e.stopPropagation()}>
        <div className="sim-dialog-head"><div><span className="sim-section-kicker">종목 추가</span><h2>가상 매수</h2><p>종목은 한 번만 선택하면 이름·코드·해당 거래일 가격을 자동으로 채웁니다.</p></div><button onClick={() => setBuyOpen(false)}>×</button></div>

        <div className="sim-buy-tabs">
          <button className={buyMode === "recommend" ? "active" : ""} onClick={() => { setBuyMode("recommend"); setBuyChoice(null); setBuyPrice(""); setBuyError(null); }}>추천 종목</button>
          <button className={buyMode === "search" ? "active" : ""} onClick={() => { setBuyMode("search"); setBuyChoice(null); setBuyPrice(""); setBuyError(null); }}>직접 찾기</button>
        </div>

        {buyMode === "recommend" ? (
          <div className="sim-buy-source">
            {!scannerSnapshot ? (
              <div className="sim-buy-empty"><strong>저장된 추천 결과가 없습니다.</strong><button className="sim-secondary" onClick={goToScanner}>종목 찾기로 이동</button></div>
            ) : !scannerDateAligned ? (
              <div className="sim-inline-warning">종목 찾기 기준일 {dateText(scannerDate)}과 현재 거래일 {dateText(session?.current_date)}이 달라 추천을 사용할 수 없습니다.</div>
            ) : (
              <div className="sim-picker-list">
                {alignedScannerCandidates.map((candidate) => (
                  <button className={buyChoice?.code === candidate.code ? "selected" : ""} key={`${candidate.market}-${candidate.code}`} onClick={() => void selectBuyStock(scannerToChoice(candidate))}>
                    <span className="sim-picker-stock"><strong>{candidate.name}</strong><small>{candidate.code}</small></span>
                    <span className="sim-picker-reason"><b>{candidate.action_label}</b><small>{candidate.strategy_easy_name}</small></span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="sim-buy-source">
            <div className="sim-stock-search">
              <input value={stockQuery} onChange={(e: { target: { value: string } }) => setStockQuery(e.target.value)} onKeyDown={(e: { key: string; preventDefault(): void }) => { if (e.key === "Enter") { e.preventDefault(); void runStockSearch(); } }} placeholder="종목명 또는 종목코드" />
              <button className="sim-secondary" disabled={stockSearchBusy} onClick={() => void runStockSearch()}>{stockSearchBusy ? "찾는 중…" : "검색"}</button>
            </div>
            {stockSearchRows.length > 0 && <div className="sim-picker-list search-results">{stockSearchRows.map((item) => (
              <button className={buyChoice?.code === item.code ? "selected" : ""} key={`${item.market}-${item.code}`} onClick={() => void selectBuyStock(searchToChoice(item))}>
                <span className="sim-picker-stock"><strong>{item.name}</strong><small>{item.code}</small></span>
                <span className="sim-picker-reason"><small>{item.market_name}</small></span>
              </button>
            ))}</div>}
          </div>
        )}

        {buyError && <div className="sim-notice error">{buyError}</div>}

        {buyChoice && (
          <div className="sim-buy-selected">
            <div className="sim-selected-stock-line"><span><strong>{buyChoice.name}</strong><small>{buyChoice.code}</small></span><b>{quoteBusy ? "가격 확인 중…" : buyPrice ? `${dateText(buyQuoteDate)} 종가 ${krw(buyPrice)}` : "가격 없음"}</b></div>
            <label className="sim-quantity-field">수량<input inputMode="numeric" value={buyQuantity} onChange={(e: { target: { value: string } }) => setBuyQuantity(e.target.value.replace(/\D/g, ""))} /></label>
            <div className="sim-preview"><span>예상 매수금액</span><strong>{krw(buyPreview)}</strong><span>매수 후 예상 현금</span><strong>{krw(numeric(portfolio.cash_balance) - buyPreview)}</strong></div>
            <details className="sim-price-adjust"><summary>체결가격 직접 수정</summary><label>체결가격<input inputMode="decimal" value={buyPrice} onChange={(e: { target: { value: string } }) => setBuyPrice(e.target.value.replace(/[^0-9.]/g, ""))} /></label></details>
            <button className="sim-primary full" disabled={busy || quoteBusy || !buyPrice || numeric(buyQuantity) <= 0} onClick={() => void buy()}>{busy ? "처리 중…" : "매수"}</button>
          </div>
        )}
      </div></div>}

      {sellTarget && <div className="sim-dialog-backdrop" onMouseDown={() => !busy && setSellTarget(null)}><div className="sim-dialog" onMouseDown={(e: { stopPropagation(): void }) => e.stopPropagation()}>
        <div className="sim-dialog-head"><div><span className="sim-section-kicker">매도</span><h2><span className="sim-title-code">{sellTarget.stock_name} <small>{sellTarget.stock_code}</small></span></h2><p>보유 {sellTarget.quantity}주 · 평균매수가 {krw(sellTarget.average_entry_price)}</p></div><button onClick={() => setSellTarget(null)}>×</button></div>
        <div className="sim-quick-qty"><button onClick={() => setSellQuantity(String(Math.max(1, Math.floor(sellTarget.quantity * .25))))}>25%</button><button onClick={() => setSellQuantity(String(Math.max(1, Math.floor(sellTarget.quantity * .5))))}>50%</button><button onClick={() => setSellQuantity(String(sellTarget.quantity))}>전량</button></div>
        <div className="sim-form-grid"><label>매도 수량<input inputMode="numeric" value={sellQuantity} onChange={(e: { target: { value: string } }) => setSellQuantity(e.target.value.replace(/\D/g, ""))} /></label><label>매도 가격<input inputMode="decimal" value={sellPrice} onChange={(e: { target: { value: string } }) => setSellPrice(e.target.value.replace(/[^0-9.]/g, ""))} /></label></div>
        <div className="sim-preview"><span>예상 매도금액</span><strong>{krw(sellPreview)}</strong><span>예상 실현손익</span><strong className={tone(sellPnlPreview)}>{signedMoney(sellPnlPreview)}</strong><span>매도 후 수량</span><strong>{Math.max(0, sellTarget.quantity - Math.trunc(numeric(sellQuantity)))}주</strong></div>
        <button className="sim-primary full" disabled={busy || numeric(sellQuantity) > sellTarget.quantity} onClick={() => void sell()}>매도</button>
      </div></div>}
    </section>
  );
}
