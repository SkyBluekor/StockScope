import type {
  StockQuoteResponse,
  StockQuoteVenue,
} from "./api";

export type StockQuoteStreamState =
  | "IDLE"
  | "CONNECTING"
  | "LIVE"
  | "DEGRADED"
  | "UNAVAILABLE";

export type StockQuoteStreamStatus = {
  resource_key: string;
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  venue: StockQuoteVenue;
  state: Exclude<StockQuoteStreamState, "IDLE">;
  transport_state: string;
  subscription_state: string | null;
  reason_code: string | null;
  checked_at: string;
};

type StreamHandlers = {
  onOpen?: () => void;
  onStatus: (status: StockQuoteStreamStatus) => void;
  onQuote: (quote: StockQuoteResponse) => void;
  onError: () => void;
};

export function stockQuoteStreamUrl(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  venue: StockQuoteVenue,
) {
  const query = new URLSearchParams({ market, venue });
  return "/api/quotes/stocks/"
    + encodeURIComponent(code.trim().toUpperCase())
    + "/stream?"
    + query.toString();
}

export function parseStockQuoteStreamStatus(value: string): StockQuoteStreamStatus {
  return JSON.parse(value) as StockQuoteStreamStatus;
}

export function parseStockQuoteStreamQuote(value: string): StockQuoteResponse {
  return JSON.parse(value) as StockQuoteResponse;
}

export function openStockQuoteStream(
  code: string,
  market: "KOSPI" | "KOSDAQ",
  venue: StockQuoteVenue,
  handlers: StreamHandlers,
) {
  const source = new EventSource(stockQuoteStreamUrl(code, market, venue));

  source.onopen = () => handlers.onOpen?.();
  source.onerror = () => handlers.onError();

  source.addEventListener("status", (event) => {
    try {
      handlers.onStatus(parseStockQuoteStreamStatus((event as MessageEvent<string>).data));
    } catch {
      handlers.onError();
    }
  });

  source.addEventListener("quote", (event) => {
    try {
      handlers.onQuote(parseStockQuoteStreamQuote((event as MessageEvent<string>).data));
    } catch {
      handlers.onError();
    }
  });

  return source;
}
