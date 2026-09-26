import type { StockQuoteResponse } from "../services/api";
import type { StockQuotePollingState } from "../hooks/useStockQuote";
import {
  quoteChangeRateText,
  quoteChangeTone,
  quotePriceText,
  quoteStatusMessage,
} from "../services/quote";
import "../quote.css";

type Props = {
  quote: StockQuoteResponse | null;
  state: StockQuotePollingState;
  refreshing: boolean;
  error: string | null;
  onRefresh: () => void;
};

export default function StockQuoteStrip({
  quote,
  state,
  refreshing,
  error,
  onRefresh,
}: Props) {
  const hasQuote = quote !== null;
  const statusMessage = quoteStatusMessage(state, quote);
  const changeTone = quoteChangeTone(quote?.change_rate);

  return (
    <section className={`quote-strip state-${state.toLowerCase()}`} aria-label="KIS 현재가 스냅샷">
      <div className="quote-strip-main">
        <span>현재가</span>
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
