import type { StockQuoteResponse } from "./api";
import type { StockQuotePollingState } from "../hooks/useStockQuote";

const wonFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

export function quoteNumber(value: string | null | undefined) {
  if (value == null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function quotePriceText(value: string | null | undefined) {
  const parsed = quoteNumber(value);
  return parsed == null ? "-" : `${wonFormatter.format(parsed)}원`;
}

export function quoteChangeRateText(value: string | null | undefined) {
  const parsed = quoteNumber(value);
  if (parsed == null) return "-";
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${parsed.toFixed(2)}%`;
}

export function quoteChangeTone(value: string | null | undefined) {
  const parsed = quoteNumber(value);
  if (parsed == null || parsed === 0) return "neutral";
  return parsed > 0 ? "positive" : "negative";
}

export function quoteReceivedTime(value: string | null | undefined) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(parsed);
}

export function quoteStatusMessage(
  state: StockQuotePollingState,
  quote: StockQuoteResponse | null,
) {
  const received = quoteReceivedTime(quote?.received_at);
  if (state === "NOT_CONFIGURED") return "KIS 시세 미설정";
  if (state === "LOADING") return "현재가 확인 중";
  if (state === "DELAYED") {
    return received ? `시세 갱신 지연 · 마지막 수신 ${received}` : "시세 갱신 지연";
  }
  if (state === "ERROR") return "현재가를 확인하지 못했습니다.";
  if (state === "FRESH" && quote) {
    return `KIS 통합 시세${received ? ` · ${received} 수신` : ""} · 스냅샷`;
  }
  return "현재가 대기";
}


function quoteTimestamp(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isWebSocketQuote(quote: StockQuoteResponse) {
  return quote.delivery.source === "WEBSOCKET";
}

export function shouldApplyQuote(
  current: StockQuoteResponse | null,
  incoming: StockQuoteResponse,
) {
  if (!current) return true;

  const currentProviderTime = quoteTimestamp(current.provider_timestamp);
  const incomingProviderTime = quoteTimestamp(incoming.provider_timestamp);

  if (currentProviderTime != null && incomingProviderTime != null) {
    if (incomingProviderTime < currentProviderTime) return false;
    if (incomingProviderTime === currentProviderTime) {
      if (isWebSocketQuote(current) && !isWebSocketQuote(incoming)) return false;
      if (!isWebSocketQuote(current) && isWebSocketQuote(incoming)) return true;
    }
  }

  if (
    isWebSocketQuote(current)
    && !isWebSocketQuote(incoming)
    && incomingProviderTime == null
  ) {
    return false;
  }

  if (!isWebSocketQuote(current) && isWebSocketQuote(incoming)) {
    return true;
  }

  const currentReceivedAt = quoteTimestamp(current.received_at);
  const incomingReceivedAt = quoteTimestamp(incoming.received_at);
  if (currentReceivedAt != null && incomingReceivedAt != null) {
    return incomingReceivedAt >= currentReceivedAt;
  }

  return true;
}
