import type {
  DomesticMarketSessionPhase,
  DomesticMarketSessionResponse,
  StockQuoteResponse,
} from "./api";
import { quoteReceivedTime } from "./quote";

export function marketSessionAllowsAutoQuote(
  session: DomesticMarketSessionResponse | null,
) {
  if (!session) return false;
  return session.quote_polling_allowed || session.phase === "UNKNOWN";
}

export function marketSessionIsPaused(
  phase: DomesticMarketSessionPhase | null | undefined,
) {
  return phase === "CLOSED" || phase === "INTERMISSION";
}

export function quoteSessionMessage(
  session: DomesticMarketSessionResponse | null,
  quote: StockQuoteResponse | null,
) {
  const received = quoteReceivedTime(quote?.received_at);
  const suffix = received ? ` · 마지막 수신 ${received}` : "";

  switch (session?.phase) {
    case "PRE_MARKET":
      return `프리마켓 · KIS 통합 시세${received ? ` · ${received} 수신` : ""}`;
    case "REGULAR":
      return `장중 · KIS 통합 시세${received ? ` · ${received} 수신` : ""}`;
    case "AFTER_MARKET":
      return `애프터마켓 · KIS 통합 시세${received ? ` · ${received} 수신` : ""}`;
    case "INTERMISSION":
      return `시장 전환 구간${suffix}`;
    case "CLOSED":
      return `장 마감${suffix}`;
    case "UNKNOWN":
      return `시장 운영 상태 확인 불가 · KIS 시세${received ? ` · ${received} 수신` : ""}`;
    default:
      return "시장 운영 상태 확인 중";
  }
}
