import { useEffect, useMemo, useState } from "react";
import {
  buySimulationPosition,
  createSimulationPortfolio,
  createSimulationSession,
  getSimulationMarks,
  getSimulationPortfolio,
  getSimulationPositions,
  getSimulationSession,
  nextSimulationDay,
  sellSimulationPosition,
  SimulationApiError,
  type PositionMark,
  type SimulationPortfolio,
  type SimulationPosition,
  type SimulationSession,
} from "../services/simulationApi";
import "../simulation.css";

const STORAGE_KEY = "stockscope-simulation-portfolio";

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
    SIM_SESSION_NOT_FOUND: "아직 Historical Session이 없습니다.",
  };
  return (error.code && known[error.code]) || error.message;
}

export default function SimulationWorkspace() {
  const [portfolioId, setPortfolioId] = useState(() => window.localStorage.getItem(STORAGE_KEY) ?? "");
  const [portfolio, setPortfolio] = useState<SimulationPortfolio | null>(null);
  const [positions, setPositions] = useState<SimulationPosition[]>([]);
  const [marks, setMarks] = useState<Record<string, PositionMark>>({});
  const [session, setSession] = useState<SimulationSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [portfolioName, setPortfolioName] = useState("Main Simulation");
  const [initialCash, setInitialCash] = useState("10000000");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [buyOpen, setBuyOpen] = useState(false);
  const [buyCode, setBuyCode] = useState("005930");
  const [buyName, setBuyName] = useState("삼성전자");
  const [buyMarket, setBuyMarket] = useState("KRX");
  const [buyQuantity, setBuyQuantity] = useState("1");
  const [buyPrice, setBuyPrice] = useState("");

  const [sellTarget, setSellTarget] = useState<SimulationPosition | null>(null);
  const [sellQuantity, setSellQuantity] = useState("1");
  const [sellPrice, setSellPrice] = useState("");

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
      const created = await createSimulationPortfolio(portfolioName.trim() || "Main Simulation", initialCash);
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

  async function buy() {
    if (!portfolioId || numeric(buyQuantity) <= 0 || numeric(buyPrice) <= 0) return setMessage("수량과 체결가격을 확인해주세요.");
    setBusy(true); setMessage(null);
    try {
      await buySimulationPosition(portfolioId, {
        stock_code: buyCode.trim(), stock_name: buyName.trim(), market: buyMarket,
        quantity: Math.trunc(numeric(buyQuantity)), execution_price: buyPrice,
      });
      setBuyOpen(false);
      await refresh(portfolioId);
    } catch (error) { setMessage(errorText(error)); }
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

  if (!portfolioId || !portfolio) {
    return (
      <section className="simulation-workspace simulation-setup">
        <span className="sim-eyebrow">HISTORICAL SIMULATION</span>
        <h1>Simulation 시작하기</h1>
        <p>가상 자금으로 과거 시장을 한 거래일씩 진행하며 포지션과 손익을 확인합니다.</p>
        {message && <div className="sim-notice error">{message}</div>}
        <div className="sim-form-grid compact">
          <label>이름<input value={portfolioName} onChange={(e: { target: { value: string } }) => setPortfolioName(e.target.value)} /></label>
          <label>초기 투자금<input inputMode="decimal" value={initialCash} onChange={(e: { target: { value: string } }) => setInitialCash(e.target.value.replace(/[^0-9.]/g, ""))} /></label>
        </div>
        <button className="sim-primary" disabled={busy} onClick={() => void createPortfolio()}>{busy ? "생성 중…" : "가상 포트폴리오 만들기"}</button>
      </section>
    );
  }

  return (
    <section className="simulation-workspace">
      <header className="sim-page-head">
        <div>
          <span className="sim-eyebrow">HISTORICAL SIMULATION</span>
          <h1>Simulation</h1>
          <p>{portfolio.name} · 실제 주문 없이 로컬 Historical Market Store로 진행</p>
        </div>
        <div className="sim-date-block">
          <span>현재 거래일</span>
          <strong>{dateText(session?.current_date)}</strong>
          <small>{session ? "Historical Session 진행 중" : "Session 시작 전"}</small>
        </div>
      </header>

      {message && <div className={`sim-notice ${message.includes("못") || message.includes("없") || message.includes("부족") ? "error" : ""}`}>{message}</div>}

      {!session && (
        <section className="sim-session-setup">
          <div><span className="sim-section-kicker">TIMELINE</span><h2>시뮬레이션 기간 설정</h2><p>확정 시장 데이터가 존재하는 거래일을 입력합니다.</p></div>
          <div className="sim-form-grid">
            <label>시작 거래일<input type="date" value={startDate} onChange={(e: { target: { value: string } }) => setStartDate(e.target.value)} /></label>
            <label>종료 거래일 <small>선택</small><input type="date" value={endDate} onChange={(e: { target: { value: string } }) => setEndDate(e.target.value)} /></label>
            <button className="sim-primary" disabled={busy || !startDate} onClick={() => void createSession()}>Session 시작</button>
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
          <div><span className="sim-section-kicker">POSITIONS</span><h2>보유 종목</h2></div>
          <button className="sim-secondary" onClick={() => setBuyOpen(true)}>+ 종목 매수</button>
        </div>
        {positions.length === 0 ? (
          <div className="sim-empty"><strong>현재 보유 중인 종목이 없습니다.</strong><span>가상 매수 후 날짜를 진행하면 평가손익 변화를 확인할 수 있습니다.</span></div>
        ) : (
          <div className="sim-table-wrap">
            <table className="sim-table">
              <thead><tr><th>종목</th><th>수량</th><th>평균매수가</th><th>현재가</th><th>평가금액</th><th>평가손익</th><th>수익률</th><th>가격 상태</th><th /></tr></thead>
              <tbody>{positions.map((position) => {
                const mark = markMap[position.id];
                const stale = Boolean(mark?.valuation_stale);
                return <tr key={position.id}>
                  <td><strong>{position.stock_name}</strong><small>{position.stock_code} · {position.market}</small></td>
                  <td>{position.quantity}주</td>
                  <td>{krw(position.average_entry_price)}</td>
                  <td>{krw(position.current_price)}</td>
                  <td>{krw(position.market_value)}</td>
                  <td className={tone(position.unrealized_pnl)}>{signedMoney(position.unrealized_pnl)}</td>
                  <td className={tone(position.unrealized_pnl_pct)}>{percent(position.unrealized_pnl_pct)}</td>
                  <td><span className={`sim-price-state ${stale ? "stale" : ""}`}>{stale ? "이전 가격 사용" : mark?.price_status === "FRESH" ? `${dateText(mark.source_bar_date)} 종가` : "체결가 기준"}</span></td>
                  <td><button className="sim-text-button" onClick={() => { setSellTarget(position); setSellQuantity(String(position.quantity)); setSellPrice(position.current_price); }}>매도</button></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="sim-timeline">
        <div><span className="sim-section-kicker">TIMELINE</span><h2>{session ? dateText(session.current_date) : "Session을 먼저 시작하세요"}</h2><p>다음 거래일의 확정 종가로 열린 Position을 다시 평가합니다.</p></div>
        <button className="sim-primary" disabled={busy || !session} onClick={() => void nextDay()}>{busy ? "업데이트 중…" : "다음 거래일 →"}</button>
      </section>

      {buyOpen && <div className="sim-dialog-backdrop" onMouseDown={() => !busy && setBuyOpen(false)}><div className="sim-dialog" onMouseDown={(e: { stopPropagation(): void }) => e.stopPropagation()}>
        <div className="sim-dialog-head"><div><span className="sim-section-kicker">BUY</span><h2>가상 매수</h2></div><button onClick={() => setBuyOpen(false)}>×</button></div>
        <div className="sim-form-grid">
          <label>종목코드<input value={buyCode} onChange={(e: { target: { value: string } }) => setBuyCode(e.target.value)} /></label>
          <label>종목명<input value={buyName} onChange={(e: { target: { value: string } }) => setBuyName(e.target.value)} /></label>
          <label>시장<select value={buyMarket} onChange={(e: { target: { value: string } }) => setBuyMarket(e.target.value)}><option value="KRX">KRX 자동</option><option value="KOSPI">KOSPI</option><option value="KOSDAQ">KOSDAQ</option></select></label>
          <label>수량<input inputMode="numeric" value={buyQuantity} onChange={(e: { target: { value: string } }) => setBuyQuantity(e.target.value.replace(/\D/g, ""))} /></label>
          <label>체결가격<input inputMode="decimal" value={buyPrice} onChange={(e: { target: { value: string } }) => setBuyPrice(e.target.value.replace(/[^0-9.]/g, ""))} /></label>
        </div>
        <div className="sim-preview"><span>예상 매수금액</span><strong>{krw(buyPreview)}</strong><span>매수 후 예상 현금</span><strong>{krw(numeric(portfolio.cash_balance) - buyPreview)}</strong></div>
        <button className="sim-primary full" disabled={busy} onClick={() => void buy()}>매수</button>
      </div></div>}

      {sellTarget && <div className="sim-dialog-backdrop" onMouseDown={() => !busy && setSellTarget(null)}><div className="sim-dialog" onMouseDown={(e: { stopPropagation(): void }) => e.stopPropagation()}>
        <div className="sim-dialog-head"><div><span className="sim-section-kicker">SELL</span><h2>{sellTarget.stock_name} 매도</h2><p>보유 {sellTarget.quantity}주 · 평단 {krw(sellTarget.average_entry_price)}</p></div><button onClick={() => setSellTarget(null)}>×</button></div>
        <div className="sim-quick-qty"><button onClick={() => setSellQuantity(String(Math.max(1, Math.floor(sellTarget.quantity * .25))))}>25%</button><button onClick={() => setSellQuantity(String(Math.max(1, Math.floor(sellTarget.quantity * .5))))}>50%</button><button onClick={() => setSellQuantity(String(sellTarget.quantity))}>전량</button></div>
        <div className="sim-form-grid"><label>매도 수량<input inputMode="numeric" value={sellQuantity} onChange={(e: { target: { value: string } }) => setSellQuantity(e.target.value.replace(/\D/g, ""))} /></label><label>매도 가격<input inputMode="decimal" value={sellPrice} onChange={(e: { target: { value: string } }) => setSellPrice(e.target.value.replace(/[^0-9.]/g, ""))} /></label></div>
        <div className="sim-preview"><span>예상 매도금액</span><strong>{krw(sellPreview)}</strong><span>예상 실현손익</span><strong className={tone(sellPnlPreview)}>{signedMoney(sellPnlPreview)}</strong><span>매도 후 수량</span><strong>{Math.max(0, sellTarget.quantity - Math.trunc(numeric(sellQuantity)))}주</strong></div>
        <button className="sim-primary full" disabled={busy || numeric(sellQuantity) > sellTarget.quantity} onClick={() => void sell()}>매도</button>
      </div></div>}
    </section>
  );
}
