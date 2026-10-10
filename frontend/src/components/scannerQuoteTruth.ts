import type {
  DomesticMarketSessionResponse,
  ScannerCandidate,
  StockQuoteResponse,
} from "../services/api";
import { assessPriceRule, type PriceRuleAssessment, wonText } from "./scannerDecisionPresentation.ts";

/**
 * Snapshot quotes compare with the analysis-date price rule. They NEVER
 * recalculate Scanner ranking, Risk, or the entry decision.
 */
export type ScannerQuoteSnapshot = {
  quote: StockQuoteResponse | null;
  marketSession: DomesticMarketSessionResponse | null;
  loading: boolean;
  error: string | null;
};

export type ScannerQuoteTruth = {
  state: "NOT_CHECKED" | "CHECKING" | "ERROR" | "IN_RANGE" | "OUT_OF_RANGE" | "UNKNOWN";
  assessment: PriceRuleAssessment | null;
  priceLabel: string;
  stateLabel: string;
  nextStep: string;
  freshnessLabel: string;
  marketLabel: string;
  // No path in this feature performs latest strategy/Risk validation.
  strategyRevalidated: false;
};

export const EMPTY_SCANNER_QUOTE: ScannerQuoteSnapshot = {
  quote: null, marketSession: null, loading: false, error: null,
};

export function quoteMatchesCandidate(
  quote: StockQuoteResponse,
  candidate: Pick<ScannerCandidate, "market" | "code">,
): boolean {
  return quote.provider === "KIS" && quote.mode === "SNAPSHOT"
    && quote.market === candidate.market
    && quote.ticker.trim().toUpperCase() === candidate.code.trim().toUpperCase();
}

export function quoteTimeText(value: string | null | undefined): string {
  if (!value) return "시간 확인 불가";
  const time = new Date(value);
  return Number.isNaN(time.getTime())
    ? "시간 확인 불가"
    : new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(time);
}

export function scannerQuoteTruth(
  candidate: ScannerCandidate,
  snapshot: ScannerQuoteSnapshot,
): ScannerQuoteTruth {
  const basis = {
    strategyRevalidated: false as const,
    priceLabel: "조회 가격 없음",
    freshnessLabel: "시세 미조회",
    marketLabel: "장 운영 상태 미확인",
    assessment: null,
  };
  if (snapshot.loading) return {
    ...basis, state: "CHECKING", stateLabel: "새 시세 확인 중",
    nextStep: "조회가 끝날 때까지 분석일 판단만 참고하세요.",
  };
  if (snapshot.error) return {
    ...basis, state: "ERROR", stateLabel: "새 시세 확인 실패",
    nextStep: "다시 조회하거나 분석일 자료만 확인하세요.",
  };
  const quote = snapshot.quote;
  if (!quote) return {
    ...basis, state: "NOT_CHECKED", stateLabel: "새 시세 미확인",
    nextStep: "새 시세를 조회해 분석일 가격 조건과 별도로 비교하세요.",
  };
  // Guard the rendering boundary in addition to the network response check.
  if (!quoteMatchesCandidate(quote, candidate)) return {
    ...basis, state: "ERROR", stateLabel: "종목이 다른 시세 수신",
    nextStep: "해당 결과는 표시하지 않습니다. 다시 조회하세요.",
  };
  const numericPrice = Number(quote.current_price);
  const assessment = assessPriceRule(candidate.entry_risk_guide?.price_rule, numericPrice);
  const validPrice = Number.isFinite(numericPrice) && numericPrice > 0;
  const receivedValid = quoteTimeText(quote.received_at) !== "시간 확인 불가";
  const providerValid = quoteTimeText(quote.provider_timestamp) !== "시간 확인 불가";
  const freshnessLabel = [
    quote.delivery?.source === "CACHE" ? "보관된 시세" : "조회 당시 수신된 시세",
    receivedValid ? "수신 " + quoteTimeText(quote.received_at) : "수신 시각 확인 불가",
    providerValid ? "제공 " + quoteTimeText(quote.provider_timestamp) : "제공 시각 확인 불가",
    quote.environment === "virtual" ? "KIS 모의투자" : "KIS 실거래",
  ].join(" · ");
  const marketLabel = snapshot.marketSession?.market_active === false
    ? "장 종료·휴장 중 마지막 거래 가격일 수 있어요."
    : snapshot.marketSession?.market_active === true
      ? "장중 수신 가격이며 이후 변동할 수 있어요."
      : "장 운영 상태가 확인되지 않았어요.";
  const state = assessment.state;
  return {
    strategyRevalidated: false,
    assessment,
    state,
    priceLabel: validPrice ? wonText(numericPrice) : "가격 확인 불가",
    stateLabel: !validPrice ? "조회 가격 판단 불가"
      : state === "IN_RANGE" ? "조회 가격은 분석일 참고 범위 안"
        : state === "OUT_OF_RANGE" ? "조회 가격은 분석일 참고 범위 밖"
          : "조회 가격의 참고 조건 판단 불가",
    nextStep: state === "OUT_OF_RANGE"
      ? "가격 조건이 이탈했어요. 최신 전략·위험을 재검증하기 전에는 진입 여부가 확정되지 않아요."
      : state === "IN_RANGE"
        ? "가격만 기존 범위에 들어왔어요. 현재 전략·위험은 여전히 재검증 전이에요."
        : "참고 가격의 적용 여부를 판단할 수 없어요. 전략·위험을 별도로 확인하세요.",
    freshnessLabel,
    marketLabel,
  };
}

export function asOfPriorityLabel(candidate: ScannerCandidate): string {
  const tier = candidate.priority?.tier;
  if (tier === "READY") return "분석일 기준 진입 후보";
  if (tier === "NEAR_READY") return "분석일 기준 근접 후보";
  if (tier === "RISK_HOLD") return "분석일 기준 위험 보류";
  if (tier === "WAIT") return "분석일 기준 관망 후보";
  if (tier === "LOW_PRIORITY") return "분석일 기준 낮은 우선순위";
  return candidate.priority?.label ? "분석일 기준: " + candidate.priority.label : "분석일 판단 미확인";
}
