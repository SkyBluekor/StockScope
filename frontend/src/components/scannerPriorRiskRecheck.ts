import type { ScannerCandidate } from "../services/api";
import {
  quoteMatchesCandidate,
  quoteTimeText,
  type ScannerQuoteSnapshot,
} from "./scannerQuoteTruth.ts";

/**
 * S31-L: S31-K's generic, display-only check with explicit KIS time provenance.
 *
 * KIS REST legitimately has provider_timestamp=null; received_at means the
 * server received a price, NOT the time of the underlying market price.
 * Never equate the two. A received-only comparison is *indicative* and never
 * a verified historical breach, latest risk result, order or trade clearance.
 *
 * 15 minutes is a local UX freshness budget for displaying this snapshot,
 * NOT a Scanner/Risk policy threshold, market-halt signal or provider SLA.
 */
export const QUOTE_DISPLAY_MAX_AGE_MS = 15 * 60 * 1000;
const CLOCK_SKEW_TOLERANCE_MS = 5 * 60 * 1000;

export type PriorRiskRecheckState =
  | "NOT_CHECKED" | "CHECKING" | "QUOTE_ERROR" | "QUOTE_UNVERIFIED"
  | "QUOTE_NOT_AFTER_ANALYSIS" | "QUOTE_TOO_OLD"
  | "REFERENCE_UNAVAILABLE" | "RECEIVED_TIME_ONLY"
  | "OLD_REFERENCE_BREACHED" | "OLD_REFERENCE_NOT_BREACHED";

export type PriorRiskReferenceSide = "AT_OR_BELOW" | "ABOVE" | "NOT_COMPARABLE";

export type PriorRiskRecheck = {
  state: PriorRiskRecheckState;
  label: string;
  explanation: string;
  nextStep: string;
  analysisDate: string | null;
  quoteProvidedAt: string | null;
  quoteReceivedAt: string | null;
  quotePrice: number | null;
  originalInvalidationReference: number | null;
  // Only verified provider-time snapshots can use this field.
  oldReferenceComparison: PriorRiskReferenceSide;
  // KIS REST has no official trade time: an explicitly tentative comparison.
  indicativeOldReferenceComparison: PriorRiskReferenceSide;
  quoteTimeBasis: "PROVIDER_TIME" | "SERVER_RECEIVED_ONLY" | "UNVERIFIED";
  quoteSourceLabel: string;
  marketSessionLabel: string;
  originalRiskStatus: string | null;
  riskRevalidated: false;
  scannerVerdictChanged: false;
  executionPermission: false;
};

function positive(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function seoulDateKey(value: Date): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value);
  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return pick("year") + "-" + pick("month") + "-" + pick("day");
}

function dateKey(value: string | null | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const day = new Date(value + "T00:00:00+09:00");
  return Number.isFinite(day.getTime()) && seoulDateKey(day) === value ? value : null;
}

function awareTime(value: string | null | undefined): number | null {
  // A naive ISO datetime is browser-local and has no trustworthy market time.
  if (!value || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Clock dependency is injectable for deterministic tests. No automatic
 * polling, quote fetch or mutation is performed.
 */
export function scannerPriorRiskRecheck(
  candidate: ScannerCandidate,
  snapshot: ScannerQuoteSnapshot,
  nowMs: number = Date.now(),
): PriorRiskRecheck {
  const referenceRisk = candidate.entry_risk_guide?.risk;
  const ref = positive(referenceRisk?.invalidation_price);
  const refEntry = positive(referenceRisk?.entry_reference_price);
  const validRef = referenceRisk?.available !== false && ref != null
    && refEntry != null && ref < refEntry ? ref : null;
  const analysis = dateKey(candidate.data_date);
  const status = candidate.risk?.status ?? null;

  const marketSessionLabel = snapshot.marketSession?.market_active === true
    ? "장중 확인값일 수 있으나 실시간 지속 업데이트는 아닙니다."
    : snapshot.marketSession?.market_active === false
      ? "장 종료·휴장 중 수신한 가격은 마지막 거래 가격일 수 있습니다."
      : "장 운영 상태 미확인: 현재 거래 가격인지 단정할 수 없습니다.";

  const base = {
    analysisDate: analysis,
    originalInvalidationReference: validRef,
    originalRiskStatus: status,
    quoteProvidedAt: null,
    quoteReceivedAt: null,
    quotePrice: null,
    oldReferenceComparison: "NOT_COMPARABLE" as const,
    indicativeOldReferenceComparison: "NOT_COMPARABLE" as const,
    quoteTimeBasis: "UNVERIFIED" as const,
    quoteSourceLabel: "새 시세 미확인",
    marketSessionLabel,
    riskRevalidated: false as const,
    scannerVerdictChanged: false as const,
    executionPermission: false as const,
  };
  const commonNext = "최신 시장·종목 데이터로 Scanner와 Risk를 다시 실행한 뒤 신규 진입을 검토하세요.";
  const result = (
    state: PriorRiskRecheckState, label: string, explanation: string,
    nextStep = commonNext,
    context: Partial<PriorRiskRecheck> = {},
  ): PriorRiskRecheck => ({
    ...base, state, label, explanation, nextStep, ...context,
  });

  if (snapshot.loading) return result(
    "CHECKING", "시세 확인 중", "조회 중에는 분석일 기준 정보만 참고하세요.",
  );
  if (snapshot.error) return result(
    "QUOTE_ERROR", "새 시세 확인 실패", "새 시세를 받지 못해 기존 Risk 참고선과 비교할 수 없어요.",
    "전략·가격 탭에서 수동으로 다시 확인하세요.",
  );
  if (!snapshot.quote) return result(
    "NOT_CHECKED",
    status === "READY" ? "이전 READY 재확인 필요" : "분석일 Risk 상태 재확인 필요",
    status === "READY"
      ? "분석 당시 READY는 지금의 매수 허가가 아니에요. 새 시세도 아직 확인하지 않았어요."
      : "과거 Risk 판단은 현재의 매수 허가가 아니에요. 새 시세도 아직 확인하지 않았어요.",
    "전략·가격 탭에서 선택한 종목의 새 시세를 수동 확인하세요.",
  );
  const quote = snapshot.quote;
  if (!quoteMatchesCandidate(quote, candidate)) return result(
    "QUOTE_UNVERIFIED", "시세 종목 불일치", "다른 종목·시장·제공자 시세는 비교하지 않아요.",
    "전략·가격 탭에서 해당 종목의 시세를 다시 확인하세요.",
  );

  const amount = positive(quote.current_price);
  const receivedTime = awareTime(quote.received_at);
  const providerTime = quote.provider_timestamp == null
    ? null : awareTime(quote.provider_timestamp);
  if (amount == null || receivedTime == null || !analysis || !Number.isFinite(nowMs)
    || (quote.provider_timestamp != null && providerTime == null)
    || (providerTime != null && providerTime > receivedTime)
    || receivedTime > nowMs + CLOCK_SKEW_TOLERANCE_MS
    || (providerTime != null && providerTime > nowMs + CLOCK_SKEW_TOLERANCE_MS)) {
    return result(
      "QUOTE_UNVERIFIED", "가격·시각 확인 불가",
      "가격 또는 시각이 불완전하거나 서로 맞지 않아 기존 위험 참고선과 비교할 수 없어요.",
      "조회한 종목과 가격·시각 근거를 다시 확인하세요.",
    );
  }

  const observedDay = seoulDateKey(new Date(providerTime ?? receivedTime));
  const provenance = quote.delivery?.source === "CACHE"
    ? "보관된 KIS 시세" : quote.delivery?.source === "WEBSOCKET"
      ? "KIS 실시간 체결 스냅샷" : "KIS 수동 조회 스냅샷";
  const context = {
    quoteProvidedAt: providerTime == null ? null : quoteTimeText(quote.provider_timestamp),
    quoteReceivedAt: quoteTimeText(quote.received_at),
    quotePrice: amount,
    quoteSourceLabel: provenance,
  };
  if (observedDay <= analysis) return result(
    "QUOTE_NOT_AFTER_ANALYSIS", "분석일 이후 시세 미확인",
    "확인된 시점이 분석일 이후가 아니므로 과거 Risk 참고선을 다시 판단할 근거가 아니에요.",
    "분석일 이후의 가격과 실제 제공 시점을 확인하세요.", context,
  );
  const age = nowMs - receivedTime;
  const providerAge = providerTime == null ? 0 : nowMs - providerTime;
  const reportedCacheAge = quote.delivery?.cache_age_ms;
  if (age > QUOTE_DISPLAY_MAX_AGE_MS || providerAge > QUOTE_DISPLAY_MAX_AGE_MS
    || (typeof reportedCacheAge === "number" && (
      !Number.isFinite(reportedCacheAge) || reportedCacheAge < 0
      || reportedCacheAge > QUOTE_DISPLAY_MAX_AGE_MS
    ))) {
    return result(
      "QUOTE_TOO_OLD", "수신 후 시간이 지난 시세",
      "마지막 조회 또는 제공 시각이 오래돼 현재 위험을 판단할 수 없어요. 과거 가격으로만 참고하세요.",
      "전략·가격 탭에서 시세를 다시 수동 확인하세요.", context,
    );
  }
  if (validRef == null) return result(
    "REFERENCE_UNAVAILABLE", "기존 위험선 검증 불가",
    "분석 당시 Risk 무효화 참고가격이 없거나 정상적인 가격 구조가 아니에요.",
    "현재 시점 Risk 참고가격을 다시 계산해 확인하세요.", context,
  );
  const side = amount <= validRef ? "AT_OR_BELOW" as const : "ABOVE" as const;
  if (providerTime == null) {
    return result(
      "RECEIVED_TIME_ONLY",
      side === "AT_OR_BELOW" ? "수신 가격이 기존 위험선 이하 · 시점 미검증"
        : "수신 가격이 기존 위험선 위 · 시점 미검증",
      side === "AT_OR_BELOW"
        ? "KIS REST는 실제 가격 제공 시각을 주지 않았어요. 서버에 수신된 가격은 옛 위험선 이하이지만, 현재 위험선 이탈로 확정할 수는 없어요."
        : "KIS REST는 실제 가격 제공 시각을 주지 않았어요. 서버에 수신된 가격이 옛 위험선 위라도 현재 안전하다는 뜻은 아니에요.",
      "제공 시각이 확인되는 자료와 현재 전략·위험을 별도로 확인하세요.",
      {
        ...context, quoteTimeBasis: "SERVER_RECEIVED_ONLY",
        indicativeOldReferenceComparison: side,
      },
    );
  }
  if (side === "AT_OR_BELOW") return result(
    "OLD_REFERENCE_BREACHED", "제공 시각 확인 · 조회 가격이 기존 위험선 이하",
    "확인된 시점의 가격이 분석일 Risk 무효화 참고선 이하예요. 실제 손절이나 현재 보유 손익을 뜻하지 않아요.",
    commonNext, {
      ...context, quoteTimeBasis: "PROVIDER_TIME",
      oldReferenceComparison: side,
    },
  );
  return result(
    "OLD_REFERENCE_NOT_BREACHED", "제공 시각 확인 · 기존 위험선 위",
    "확인된 시점의 가격은 옛 참고선 위지만, 현재도 전략·Risk가 유효하다는 뜻은 아니에요.",
    commonNext, {
      ...context, quoteTimeBasis: "PROVIDER_TIME",
      oldReferenceComparison: side,
    },
  );
}
