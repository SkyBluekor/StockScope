import type { DomesticMarketSessionResponse, StockQuoteResponse } from "../services/api";
import type { StockQuotePollingState } from "../hooks/useStockQuote";
import {
  quoteChangeRateText,
  quoteChangeTone,
  quotePriceText,
  quoteStatusMessage,
} from "../services/quote";
import { marketSessionIsPaused, quoteSessionMessage } from "../services/marketSession";
import "../quote.css";

type Props = {
  quote: StockQuoteResponse | null;
  state: StockQuotePollingState;
  refreshing: boolean;
  error: string | null;
  marketSession: DomesticMarketSessionResponse | null;
  marketSessionLoading: boolean;
  onRefresh: () => void;
};

export default function StockQuoteStrip({
  quote,
  state,
  refreshing,
  error,
  marketSession,
  marketSessionLoading,
  onRefresh,
}: Props) {
  const hasQuote = quote !== null;
  const pausedByMarket = marketSessionIsPaused(marketSession?.phase);
  const statusMessage = marketSessionLoading && !marketSession
    ? "시장 운영 상태 확인 중"
    : state === "FRESH" && marketSession
      ? quoteSessionMessage(marketSession, quote)
      : pausedByMarket && marketSession
        ? quoteSessionMessage(marketSession, quote)
        : quoteStatusMessage(state, quote);
  const changeTone = quoteChangeTone(quote?.change_rate);
  const priceLabel = pausedByMarket ? "마지막 시세" : "현재가";

  return (
    <section className={`quote-strip state-${state.toLowerCase()}`} aria-label="KIS 현재가 스냅샷">
      <div className="quote-strip-main">
        <span>{priceLabel}</span>
        <strong>{hasQuote ? quotePriceText(quote.current_price) : state === "NOT_CONFIGURED" ? "시세 미설정" : "-"}</strong>
        {hasQuote && (
          <b className={`quote-strip-change ${changeTone}`}>
            {quoteChangeRateText(quote.change_rate)}
          </b>
        )}
      </div>
      <div className="quote-strip-meta">
        <span role="status" aria-live="polite">
          {refreshing && hasQuote
            ? `현재가 갱신 중 · ${statusMessage}`
            : statusMessage}
        </span>
        {state === "ERROR" && error && <small>{error}</small>}
      </div>
      <button
        type="button"
        className="quote-strip-refresh"
        onClick={onRefresh}
        disabled={refreshing || state === "LOADING" || state === "NOT_CONFIGURED"}
      >
        {refreshing || state === "LOADING" ? "확인 중" : "새로고침"}
      </button>
    </section>
  );
}
