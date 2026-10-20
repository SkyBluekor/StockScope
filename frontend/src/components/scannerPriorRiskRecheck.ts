import type { ScannerCandidate } from "../services/api";
import {
  quoteMatchesCandidate,
  quoteTimeText,
  type ScannerQuoteSnapshot,
} from "./scannerQuoteTruth.ts";

/**
 * S31-K. Reusable, display-only comparison for ANY Scanner candidate.
 * A KIS snapshot is never a validated new Scanner/Risk decision, executable
 * entry or current position. Neither stale/mismatched quotes nor missing data
 * may silently make an old READY safe.
 */
export type PriorRiskRecheckState =
  | "NOT_CHECKED" | "CHECKING" | "QUOTE_ERROR" | "QUOTE_UNVERIFIED"
  | "QUOTE_NOT_AFTER_ANALYSIS" | "REFERENCE_UNAVAILABLE"
  | "OLD_REFERENCE_BREACHED" | "OLD_REFERENCE_NOT_BREACHED";

export type PriorRiskRecheck = {
  state: PriorRiskRecheckState;
  label: string;
  explanation: string;
  nextStep: string;
  analysisDate: string | null;
  quoteProvidedAt: string | null;
  quotePrice: number | null;
  originalInvalidationReference: number | null;
  oldReferenceComparison: "AT_OR_BELOW" | "ABOVE" | "NOT_COMPARABLE";
  quoteSourceLabel: string;
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

function dateKey(value: string | null | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const day = new Date(value + "T00:00:00+09:00");
  if (!Number.isFinite(day.getTime()) || Number.isNaN(day.getTime())) return null;
  return seoulDateKey(day) === value ? value : null;
}

function seoulDateKey(value: Date): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value);
  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return pick("year") + "-" + pick("month") + "-" + pick("day");
}

export function scannerPriorRiskRecheck(
  candidate: ScannerCandidate,
  snapshot: ScannerQuoteSnapshot,
): PriorRiskRecheck {
  const referenceRisk = candidate.entry_risk_guide?.risk;
  const ref = positive(referenceRisk?.invalidation_price);
  const refEntry = positive(referenceRisk?.entry_reference_price);
  const validRef = referenceRisk?.available !== false && ref != null
    && refEntry != null && ref < refEntry ? ref : null;
  const analysis = dateKey(candidate.data_date);
  const status = candidate.risk?.status ?? null;

  const base = {
    analysisDate: analysis,
    originalInvalidationReference: validRef,
    originalRiskStatus: status,
    quoteProvidedAt: null,
    quotePrice: null,
    oldReferenceComparison: "NOT_COMPARABLE" as const,
    quoteSourceLabel: "새 시세 미확인",
    riskRevalidated: false as const,
    scannerVerdictChanged: false as const,
    executionPermission: false as const,
  };
  const commonNext = "최신 시장·종목 데이터를 확인한 뒤 Scanner와 Risk를 다시 실행해야 신규 진입을 검토할 수 있어요.";
  const result = (
    state: PriorRiskRecheckState, label: string, explanation: string,
    nextStep = commonNext,
    context: Partial<PriorRiskRecheck> = {},
  ): PriorRiskRecheck => ({
    ...base, state, label, explanation, nextStep, ...context,
  });

  if (snapshot.loading) return result(
    "CHECKING", "시세 확인 중", "조회 중에는 이전의 판단과 가격만 참고하세요.",
  );
  if (snapshot.error) return result(
    "QUOTE_ERROR", "새 시세 확인 실패", "조회가 실패해 이전 Risk 참고선을 새 가격과 비교할 수 없어요.",
    "전략·가격 탭에서 시세를 다시 확인하세요.",
  );
  if (!snapshot.quote) return result(
    "NOT_CHECKED",
    status === "READY" ? "이전 READY 재확인 필요" : "분석일 Risk 상태 재확인 필요",
    status === "READY"
      ? "분석 당시 READY는 지금의 매수 허가가 아니에요. 새 가격도 아직 확인하지 않았어요."
      : "분석일 Risk 판단을 지금의 매수 허가로 볼 수 없어요. 새 가격도 아직 확인하지 않았어요.",
    "전략·가격 탭에서 선택한 종목의 새 시세를 수동 확인하세요.",
  );
  const quote = snapshot.quote;
  if (!quoteMatchesCandidate(quote, candidate)) return result(
    "QUOTE_UNVERIFIED", "시세 종목 불일치", "다른 종목·시장·제공자 시세는 비교하지 않아요.",
    "전략·가격 탭에서 해당 종목의 시세를 다시 확인하세요.",
  );
  const amount = positive(quote.current_price);
  const providerTime = Date.parse(quote.provider_timestamp ?? "");
  const receivedTime = Date.parse(quote.received_at ?? "");
  if (amount == null || !Number.isFinite(providerTime) || !Number.isFinite(receivedTime)
      || providerTime > receivedTime || !analysis) {
    return result(
      "QUOTE_UNVERIFIED", "가격·시각 확인 불가",
      "가격 또는 제공 시각이 불완전해 기존 Risk 참고선과 신뢰할 만한 비교를 할 수 없어요.",
      "가격과 제공 시각이 명확한 새 시세를 확인하세요.",
    );
  }
  const observedDay = seoulDateKey(new Date(providerTime));
  const provenance = quote.delivery?.source === "CACHE"
    ? "보관된 KIS 시세" : "조회 당시 KIS 시세";
  const context = {
    quoteProvidedAt: quoteTimeText(quote.provider_timestamp),
    quotePrice: amount,
    quoteSourceLabel: provenance,
  };
  if (observedDay <= analysis) return result(
    "QUOTE_NOT_AFTER_ANALYSIS", "분석일 이후 시세 미확인",
    "조회한 가격의 제공일이 분석일보다 늦지 않아요. 이전 READY를 재검증할 증거가 아니에요.",
    "분석일 이후 제공된 종목 시세를 확인하세요.", context,
  );
  if (validRef == null) return result(
    "REFERENCE_UNAVAILABLE", "기존 위험선 검증 불가",
    "분석 당시 무효화 참고가격이 없거나 Risk 가격 구조가 유효하지 않아요.",
    "현재 데이터로 Risk를 다시 계산해 확인하세요.", context,
  );
  if (amount <= validRef) return result(
    "OLD_REFERENCE_BREACHED", "조회 가격이 기존 위험선 이하",
    "조회 시점 가격이 분석 당시 무효화 참고가격 이하예요. 이전 Risk 판단을 신규 진입 근거로 사용하면 안 돼요.",
    "현재 가격과 시장 상황을 다시 분석하세요. 실제 보유·손절 주문 여부는 이 화면에서 알 수 없어요.",
    { ...context, oldReferenceComparison: "AT_OR_BELOW" },
  );
  return result(
    "OLD_REFERENCE_NOT_BREACHED", "기존 위험선 위 · 재검증 필요",
    "조회 가격이 옛 무효화 참고가격보다 높지만, 전략·위험이 현재도 유효하다는 뜻은 아니에요.",
    commonNext, { ...context, oldReferenceComparison: "ABOVE" },
  );
}
