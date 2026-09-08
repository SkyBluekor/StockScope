import { useEffect, useState } from "react";
import {
  ProviderStatus,
  StockContext,
  fetchHealth,
  fetchProviderStatus,
  fetchStockContext,
} from "./services/api";

function number(value: number | null | undefined, suffix = "") {
  return value == null ? "-" : `${new Intl.NumberFormat("ko-KR").format(value)}${suffix}`;
}

function formatKrxDate(value: string | null | undefined) {
  if (!value || value.length !== 8) return value ?? "-";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

export default function App() {
  const [apiStatus, setApiStatus] = useState("확인 중");
  const [providers, setProviders] = useState<ProviderStatus | null>(null);
  const [stockCode, setStockCode] = useState("005930");
  const [market, setMarket] = useState<"KOSPI" | "KOSDAQ">("KOSPI");
  const [context, setContext] = useState<StockContext | null>(null);
  const [message, setMessage] = useState("KRX + OpenDART 통합 데이터 조회 준비 완료");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then((data) => setApiStatus(data.status === "ok" ? "정상" : "오류"))
      .catch(() => setApiStatus("연결 실패"));
    fetchProviderStatus().then(setProviders).catch(() => setProviders(null));
  }, []);

  async function analyze() {
    setBusy(true);
    setMessage("최근 거래일 탐색 + KRX/OpenDART 통합 조회 중...");
    try {
      const result = await fetchStockContext(stockCode, market);
      setContext(result);
      const fallback = result.fallback_used ? ` · 최근 거래일 ${formatKrxDate(result.data_date)} 자동 적용` : "";
      setMessage(`통합 조회 성공 · ${result.company.corp_name ?? result.stock.name ?? stockCode}${fallback}`);
    } catch (error) {
      setContext(null);
      setMessage(error instanceof Error ? error.message : "통합 조회 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">StockScope</div>
        <div className="top-statuses">
          <span className="status">API {apiStatus}</span>
          <span className={`status ${providers?.krx.configured ? "connected" : ""}`}>
            KRX {providers?.krx.configured ? "설정됨" : "미설정"}
          </span>
          <span className={`status ${providers?.dart.configured ? "connected" : ""}`}>
            DART {providers?.dart.configured ? "설정됨" : "미설정"}
          </span>
        </div>
      </header>

      <section className="workspace">
        <div className="page-heading">
          <p className="eyebrow">MARKET DATA FOUNDATION · v0.4</p>
          <h1>종목코드 하나로 KRX + OpenDART 통합 조회</h1>
          <p>
            사용자가 날짜나 DART 고유번호를 직접 찾지 않아도 됩니다. StockScope가 최근 사용 가능한 KRX 거래일과
            DART corp_code를 자동으로 찾아 통합합니다.
          </p>
        </div>

        <div className="danger-banner">
          <strong>실제 매매 기능 없음</strong>
          <span>조회·분석·백테스트·시뮬레이션 전용입니다. 증권사 주문 API는 구현하지 않습니다.</span>
        </div>

        <section className="panel">
          <div className="panel-title">
            <div><span className="step">01</span><h2>통합 종목 조회</h2></div>
            <span className="read-only">KRX + OpenDART</span>
          </div>
          <div className="form compact">
            <label>시장
              <select value={market} onChange={(e) => setMarket(e.target.value as "KOSPI" | "KOSDAQ") }>
                <option value="KOSPI">KOSPI</option>
                <option value="KOSDAQ">KOSDAQ</option>
              </select>
            </label>
            <label>종목코드
              <input value={stockCode} onChange={(e) => setStockCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </label>
            <button className="primary" disabled={busy || stockCode.length !== 6} onClick={analyze}>
              {busy ? "조회 중..." : "통합 조회"}
            </button>
          </div>
          <p className="hint">당일 KRX 데이터가 아직 없거나 휴장일이면 최근 거래일을 자동으로 찾아 사용합니다.</p>
        </section>

        <div className="message">{message}</div>

        {context && (
          <>
            <section className="panel quote-panel">
              <div className="quote-head">
                <div>
                  <span className="eyebrow">KRX DAILY · {formatKrxDate(context.data_date)}</span>
                  <h2>{context.stock.name ?? context.company.corp_name} <small>{context.code}</small></h2>
                </div>
                <div className="price">
                  {number(context.stock.close, "원")}
                  <small>{context.stock.change_rate == null ? "" : `${context.stock.change_rate >= 0 ? "+" : ""}${context.stock.change_rate}%`}</small>
                </div>
              </div>
              {context.fallback_used && (
                <div className="sample-note">당일 데이터가 없어 최근 사용 가능한 거래일 {formatKrxDate(context.data_date)} 기준으로 자동 보정했습니다.</div>
              )}
              <div className="metrics six">
                <div><span>시가</span><strong>{number(context.stock.open)}</strong></div>
                <div><span>고가</span><strong>{number(context.stock.high)}</strong></div>
                <div><span>저가</span><strong>{number(context.stock.low)}</strong></div>
                <div><span>거래량</span><strong>{number(context.stock.volume)}</strong></div>
                <div><span>거래대금</span><strong>{number(context.stock.trade_value)}</strong></div>
                <div><span>시가총액</span><strong>{number(context.stock.market_cap)}</strong></div>
              </div>
            </section>

            <section className="grid two result-grid">
              <article className="panel">
                <div className="panel-title"><div><span className="step">02</span><h2>시장 지수</h2></div><span className="read-only">KRX</span></div>
                <dl className="detail-list">
                  <div><dt>지수</dt><dd>{context.market_index?.name ?? context.market}</dd></div>
                  <div><dt>종가</dt><dd>{number(context.market_index?.close)}</dd></div>
                  <div><dt>등락률</dt><dd>{context.market_index?.change_rate == null ? "-" : `${context.market_index.change_rate}%`}</dd></div>
                  <div><dt>기준일</dt><dd>{formatKrxDate(context.market_index?.date)}</dd></div>
                </dl>
              </article>

              <article className="panel">
                <div className="panel-title"><div><span className="step">03</span><h2>기업 개황</h2></div><span className="read-only">OpenDART</span></div>
                <dl className="detail-list">
                  <div><dt>회사명</dt><dd>{context.company.corp_name ?? "-"}</dd></div>
                  <div><dt>DART 코드</dt><dd>{context.company.corp_code ?? "-"}</dd></div>
                  <div><dt>대표자</dt><dd>{context.company.ceo ?? "-"}</dd></div>
                  <div><dt>설립일</dt><dd>{context.company.established_date ?? "-"}</dd></div>
                  <div><dt>결산월</dt><dd>{context.company.fiscal_month ?? "-"}</dd></div>
                </dl>
              </article>
            </section>

            <section className="panel">
              <div className="panel-title">
                <div><span className="step">04</span><h2>최근 공시</h2></div>
                <span className="read-only">{context.disclosures.count}건</span>
              </div>
              <div className="disclosure-list">
                {context.disclosures.rows.slice(0, 8).map((row, index) => (
                  <div className="disclosure" key={`${row.receipt_no ?? index}`}>
                    <span>{row.receipt_date ?? "-"}</span>
                    <strong>{row.report_name ?? "-"}</strong>
                  </div>
                ))}
                {context.disclosures.count === 0 && <p className="hint">최근 조회 기간에 공시가 없습니다.</p>}
              </div>
            </section>
          </>
        )}
      </section>
    </main>
  );
}
