import type { ConcreteEntryRiskGuide, ScannerCandidate } from "../services/api";

export type PriceRuleAssessment = {
  state: "IN_RANGE" | "OUT_OF_RANGE" | "UNKNOWN";
  label: string;
  message: string;
  reference: string;
};

const won = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

export function wonText(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) || value <= 0 ? "확인할 수 없음" : won.format(value) + "원";
}

export function simpleConditionStatus(candidate: ScannerCandidate): string {
  const tier = candidate.priority?.tier;
  if (tier === "RISK_HOLD" || candidate.entry_risk_guide?.action.status === "RISK_BLOCKED") {
    return "위험 때문에 추가 확인이 필요해요";
  }
  if (tier === "LOW_PRIORITY" || candidate.action === "NO_TRADE") {
    return "지금은 먼저 살펴볼 종목이 아니에요";
  }
  if (candidate.risk.warning) return "주의할 위험 요소가 있어요";
  if (tier === "READY") return "투자 조건을 충족했어요";
  if (tier === "NEAR_READY") return "투자 조건이 조금 부족해요";
  if (tier === "WAIT") return "아직 확인할 조건이 있어요";
  return "현재 조건을 더 확인해야 해요";
}

export function priceReferenceText(rule: ConcreteEntryRiskGuide["price_rule"] | null | undefined): string {
  if (!rule) return "매수 참고 가격 정보가 없어요";
  const trigger = rule.trigger_price;
  const low = rule.range_low;
  const high = rule.range_high;
  if (rule.kind === "AT_OR_BELOW" && trigger != null && Number.isFinite(trigger) && trigger > 0)
    return wonText(trigger) + " 이하";
  if (rule.kind === "ABOVE" && trigger != null && Number.isFinite(trigger) && trigger > 0)
    return wonText(trigger) + " 이상";
  if (rule.kind === "RANGE" && low != null && high != null && low > 0 && high >= low)
    return wonText(low) + " ~ " + wonText(high);
  if (rule.kind === "REFERENCE" && rule.reference_price != null && rule.reference_price > 0)
    return wonText(rule.reference_price) + " (참고 가격)";
  return "적용 가능한 가격 기준을 확인할 수 없어요";
}

export function assessPriceRule(
  rule: ConcreteEntryRiskGuide["price_rule"] | null | undefined,
  price: number | null | undefined,
): PriceRuleAssessment {
  const reference = priceReferenceText(rule);
  if (!rule || price == null || !Number.isFinite(price) || price <= 0) {
    return { state: "UNKNOWN", label: "가격 확인 필요", message: "가격 또는 판단 기준이 없어 비교할 수 없어요.", reference };
  }
  const trigger = rule.trigger_price;
  const low = rule.range_low;
  const high = rule.range_high;
  let within: boolean | null = null;
  if (rule.kind === "AT_OR_BELOW" && trigger != null && Number.isFinite(trigger) && trigger > 0) {
    within = price <= trigger;
  } else if (rule.kind === "ABOVE" && trigger != null && Number.isFinite(trigger) && trigger > 0) {
    within = price >= trigger;
  } else if (
    rule.kind === "RANGE" && low != null && high != null &&
    Number.isFinite(low) && Number.isFinite(high) && low > 0 && high >= low
  ) {
    within = price >= low && price <= high;
  }
  if (within == null) {
    return {
      state: "UNKNOWN", label: "가격 기준 확인 필요",
      message: "참고 가격만 있거나 적용할 수 있는 구체적인 가격 조건이 없어요.",
      reference,
    };
  }
  const usableEntry = rule.executable_entry_range === true;
  if (within) return {
    state: "IN_RANGE",
    label: "참고 가격 조건에 들어와 있어요",
    message: usableEntry
      ? "이 가격은 전략의 참고 범위에 있어요. 실제 매수 판단에는 다른 조건과 최신 분석도 필요해요."
      : "가격만 비교하면 조건에 맞아요. 실제 매수 신호인지 판단할 수는 없어요.",
    reference,
  };
  return {
    state: "OUT_OF_RANGE",
    label: "참고 가격 조건에서 벗어나 있어요",
    message: "이 가격은 전략의 참고 범위 밖이에요. 조건과 위험을 다시 확인하기 전에는 매수 여부를 판단할 수 없어요.",
    reference,
  };
}

export type MissingConditionView = {
  label: string;
  detail: string | null;
  current: string | null;
  required: string | null;
};

function nonempty(value: string | null | undefined): string | null {
  const trimmed = String(value ?? "").trim();
  return trimmed || null;
}

// top_missing is an ordered explanation subset, not a substitute for the
// authoritative missing count. Never invent a condition not present in data.
export function missingConditionDetails(candidate: ScannerCandidate): MissingConditionView[] {
  const count = Number(candidate.conditions?.missing ?? 0);
  if (!Number.isFinite(count) || count <= 0) return [];
  const raw = candidate.conditions?.top_missing ?? [];
  const seen = new Set<string>();
  const items: MissingConditionView[] = [];
  for (const item of raw) {
    const label = nonempty(item.label) ?? nonempty(item.raw);
    if (!label || seen.has(label)) continue;
    seen.add(label);
    items.push({
      label,
      detail: nonempty(item.detail),
      current: nonempty(item.current_value),
      required: nonempty(item.required_value),
    });
    if (items.length >= 3) break;
  }
  return items;
}

export type BeginnerCandidatePresentation = {
  status: string;
  headline: string;
  why: string;
  caution: string;
  next: string;
  asOfPrice: PriceRuleAssessment;
  missingConditions: MissingConditionView[];
  missingCount: number;
  nextActionLabel: string;
  nextActionContext: string;
};

export function beginnerCandidatePresentation(candidate: ScannerCandidate): BeginnerCandidatePresentation {
  const passed = candidate.conditions?.passed ?? 0;
  const total = candidate.conditions?.total ?? 0;
  const missing = candidate.conditions?.missing ?? Math.max(0, total - passed);
  const hasConditionData = Number.isFinite(total) && total > 0
    && Number.isFinite(passed) && passed >= 0 && passed <= total
    && Number.isFinite(missing) && missing >= 0;
  const missingConditions = missingConditionDetails(candidate);
  const firstMissing = missingConditions[0];
  const blocked = candidate.risk?.warning === true
    || candidate.priority?.tier === "RISK_HOLD"
    || candidate.entry_risk_guide?.action.status === "RISK_BLOCKED";
  const lowPriority = candidate.priority?.tier === "LOW_PRIORITY" || candidate.action === "NO_TRADE";
  const price = assessPriceRule(candidate.entry_risk_guide?.price_rule, candidate.current_price);
  const status = simpleConditionStatus(candidate);
  const why = hasConditionData
    ? "전체 투자 조건 " + total + "개 중 " + passed + "개를 충족했어요."
    : "분석 당시 투자 조건의 전체 개수 또는 계산 결과를 확인할 수 없어요.";

  if (blocked) {
    return {
      status, why, asOfPrice: price, missingConditions, missingCount: missing,
      headline: "위험 신호가 있어 진입 판단을 보류해야 해요.",
      caution: candidate.risk?.warnings?.[0] ? "위험 경고: " + candidate.risk.warnings[0] : "현재 분석에서 위험 경고가 확인됐어요.",
      next: "위험 경고의 원인을 확인하고, 새 분석에서도 해소됐는지 확인하세요.",
      nextActionLabel: "위험 차단 이유 확인",
      nextActionContext: candidate.risk?.warnings?.[0] || "전략·위험 정보 확인",
    };
  }
  if (lowPriority || !hasConditionData) {
    return {
      status, why, asOfPrice: price, missingConditions, missingCount: missing,
      headline: lowPriority ? "현재 우선 검토할 진입 후보는 아니에요." : "판단에 필요한 조건 자료가 부족해요.",
      caution: lowPriority ? "기존 Scanner의 낮은 우선순위 판단을 유지합니다." : "확인되지 않은 조건을 충족으로 계산하지 않았어요.",
      next: "전략·가격 탭에서 계산 근거를 확인하세요.",
      nextActionLabel: "판단 근거 확인",
      nextActionContext: "분석일 기준 자료 확인",
    };
  }
  if (missing > 0) {
    const missingLabel = firstMissing?.label ?? "부족한 조건의 상세 정보 없음";
    return {
      status, why, asOfPrice: price, missingConditions, missingCount: missing,
      headline: "진입 조건이 " + missing + "개 부족해요. 충족될 때까지 기다려야 해요.",
      caution: firstMissing ? "먼저 확인할 조건: " + missingLabel : "부족한 조건 " + missing + "개가 있지만 상세 근거가 제공되지 않았어요.",
      next: firstMissing ? "‘" + missingLabel + "’ 조건이 충족되는지 확인하세요." : "전략·가격 탭에서 조건 근거를 확인하세요.",
      nextActionLabel: firstMissing ? "부족: " + missingLabel : "부족한 조건 상세 없음",
      nextActionContext: firstMissing
        ? [firstMissing.current && "현재 " + firstMissing.current, firstMissing.required && "필요 " + firstMissing.required].filter(Boolean).join(" · ") || "조건 설명 확인"
        : "조건 " + missing + "개 부족 · 근거 확인 필요",
    };
  }
  if (price.state === "OUT_OF_RANGE") {
    return {
      status, why, asOfPrice: price, missingConditions, missingCount: missing,
      headline: "분석일 진입 조건은 충족했지만 분석 당시 가격은 참고 범위 밖이에요.",
      caution: "분석 당시 가격이 전략 참고 가격에서 벗어나 있었어요.",
      next: "새 시세와 현재 전략 조건·위험을 다시 검증하세요.",
      nextActionLabel: "참고 가격 조건 확인",
      nextActionContext: price.label,
    };
  }
  return {
    status, why, asOfPrice: price, missingConditions, missingCount: missing,
    headline: "분석일 기준 진입 조건을 모두 충족했어요.",
    caution: price.state === "IN_RANGE"
      ? "분석 당시 참고 가격 조건도 충족했어요. 지금의 전략 유효성은 별개예요."
      : "분석 당시 참고 가격을 판단할 수 없어요. 가격 기준을 확인하세요.",
    next: "새 시세를 확인한 후 전략 조건과 위험이 지금도 유효한지 다시 검증하세요.",
    nextActionLabel: price.state === "UNKNOWN" ? "가격 기준 확인" : "새 시세·전략 확인",
    nextActionContext: price.label,
  };
}
