import { useEffect, useRef, useState } from "react";
import type {
  DomesticMarketSessionResponse,
  ScannerCandidate,
  StockQuoteResponse,
} from "../services/api";
import { fetchDomesticMarketSession, fetchStockQuote } from "../services/api";
import { assessPriceRule, priceReferenceText, wonText } from "./scannerDecisionPresentation";

function timeText(value: string | null | undefined): string {
  if (!value) return "시간 확인 불가";
  const time = new Date(value);
  return Number.isNaN(time.getTime())
    ? "시간 확인 불가"
    : new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(time);
}

type Props = { candidate: ScannerCandidate };

export default function ScannerPriceStatus({ candidate }: Props) {
  const [quote, setQuote] = useState<StockQuoteResponse | null>(null);
  const [marketSession, setMarketSession] = useState<DomesticMarketSessionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const priceRule = candidate.entry_risk_guide?.price_rule;
  const baseline = assessPriceRule(priceRule, candidate.current_price);
  const marketPrice = quote ? Number(quote.current_price) : null;
  const marketAssessment = quote && marketPrice != null && Number.isFinite(marketPrice) && marketPrice > 0
    ? assessPriceRule(priceRule, marketPrice) : null;

  useEffect(() => () => {
    controllerRef.current?.abort();
  }, []);

  async function checkPrice() {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setQuote(null);
    setMarketSession(null);
    setLoading(true);
    setError(null);
    try {
      const [quoteResult, sessionResult] = await Promise.allSettled([
        fetchStockQuote(candidate.code, candidate.market, { signal: controller.signal }),
        fetchDomesticMarketSession({ signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      if (quoteResult.status === "fulfilled" && quoteResult.value) {
        setQuote(quoteResult.value);
      } else {
        throw new Error("새 시세를 확인하지 못했습니다. 분석 당시의 가격만 참고하세요.");
      }
      if (sessionResult.status === "fulfilled") setMarketSession(sessionResult.value);
    } catch (reason) {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : "시세를 확인하지 못했습니다.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <section className="scanner-ux-price" aria-label="가격과 판단 근거 시점">
      <header className="scanner-ux-section-heading">
        <div>
          <span className="scanner-ux-eyebrow">가격 확인</span>
          <h4>분석 당시의 가격과 새로 확인한 가격은 달라요.</h4>
        </div>
      </header>
      <div className="scanner-ux-price-grid">
        <div>
          <small>분석 당시 종가 · {candidate.data_date || "기준일 확인 필요"}</small>
          <strong>{wonText(candidate.current_price)}</strong>
          <p>{baseline.label}</p>
        </div>
        <div>
          <small>전략이 제시한 참고 가격</small>
          <strong>{priceReferenceText(priceRule)}</strong>
          <p>가격만 맞는다고 실제 매수 조건이 완성되는 건 아니에요.</p>
        </div>
      </div>
      <div className="scanner-ux-price-live">
        <div>
          <strong>새로운 시세 확인</strong>
          <p>필요할 때 선택한 종목만 조회합니다. 시세를 조회해도 투자 전략은 자동으로 다시 계산하지 않아요.</p>
        </div>
        <button type="button" onClick={() => void checkPrice()} disabled={loading}>
          {loading ? "시세 확인 중…" : quote ? "시세 다시 확인" : "새 시세 확인"}
        </button>
      </div>
      {error && <p role="alert" className="scanner-ux-price-warning">{error}</p>}
      {quote && (
        <div className="scanner-ux-quote-result" role="status">
          <div className="scanner-ux-quote-head">
            <span>조회된 시세</span>
            <strong>{marketPrice != null && Number.isFinite(marketPrice) && marketPrice > 0 ? wonText(marketPrice) : "가격 확인 불가"}</strong>
          </div>
          <p>
            {marketSession?.market_active === false
              ? "현재 장이 열려 있지 않아 마지막 거래 가격일 수 있어요."
              : marketSession?.market_active === true
                ? "장이 열려 있어도 조회 결과는 수신 당시의 가격이에요."
                : "장 운영 상태가 확인되지 않아 실시간 거래 가격이라고 단정할 수 없어요."}
          </p>
          <small>
            KIS {quote.environment === "virtual" ? "모의투자" : "실거래"} 환경
            {" · "}시세 수신 {timeText(quote.received_at)}
            {quote.delivery.source === "CACHE" ? " · 보관된 시세" : ""}
            {quote.provider_timestamp ? " · 제공 시각 " + timeText(quote.provider_timestamp) : ""}
          </small>
          <p className="scanner-ux-price-assessment">
            {marketAssessment?.message ?? "현재 받은 가격으로는 참고 조건을 확인할 수 없어요."}
          </p>
          <p className="scanner-ux-disclaimer">
            이 정보는 가격만 비교한 결과입니다. 분석일 이후 전략 조건과 위험은 다시 검증하지 않았어요.
          </p>
        </div>
      )}
    </section>
  );
}
