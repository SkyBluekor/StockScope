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

export type BeginnerCandidatePresentation = {
  status: string;
  headline: string;
  why: string;
  caution: string;
  next: string;
  asOfPrice: PriceRuleAssessment;
};

export function beginnerCandidatePresentation(candidate: ScannerCandidate): BeginnerCandidatePresentation {
  const status = simpleConditionStatus(candidate);
  const passed = candidate.conditions?.passed ?? 0;
  const total = candidate.conditions?.total ?? 0;
  const missing = candidate.conditions?.missing ?? Math.max(0, total - passed);
  const risk = candidate.risk?.warning === true
    || candidate.priority?.tier === "RISK_HOLD"
    || candidate.entry_risk_guide?.action.status === "RISK_BLOCKED";
  const price = assessPriceRule(candidate.entry_risk_guide?.price_rule, candidate.current_price);
  const why = total > 0
    ? "분석 당시 설정된 투자 조건 " + passed + "개 중 " + total + "개를 확인했어요."
    : "현재 투자 조건이 충분히 계산되지 않았어요.";
  const caution = risk
    ? "현재 분석에서 위험 경고가 있어요. 가격이 맞더라도 이 경고를 먼저 확인해야 해요."
    : missing > 0
      ? "아직 " + missing + "개의 투자 조건이 충족되지 않았어요."
      : price.state === "OUT_OF_RANGE"
        ? "분석 당시 종가는 전략의 참고 가격 조건에서 벗어나 있었어요."
        : price.state === "UNKNOWN"
          ? "현재 자료만으로는 가격 조건을 확인하기 어려워요."
          : "투자 조건과 가격이 맞아도 지금 매수하라는 뜻은 아니에요.";
  const next = risk
    ? "위험 경고가 사라졌는지 다시 분석한 뒤 확인하세요."
    : missing > 0
      ? "남은 투자 조건 " + missing + "개가 충족되는지 확인하세요."
      : price.state === "OUT_OF_RANGE"
        ? "새로운 가격을 확인하고, 전략 조건이 여전히 유효한지 다시 살펴보세요."
        : "새 시세와 분석 기준일을 확인하고 실제 가격·위험 조건을 다시 살펴보세요.";

  const headline = risk
    ? "위험 신호가 있어 지금은 신중하게 살펴봐야 해요."
    : missing > 0
      ? "관심을 둘 만하지만 아직 기다려야 할 조건이 있어요."
      : price.state === "OUT_OF_RANGE"
        ? "투자 조건은 맞지만 분석 당시 가격은 참고 범위 밖이었어요."
        : "투자 조건은 충족했지만 지금 매수해도 된다는 뜻은 아니에요.";
  return { status, headline, why, caution, next, asOfPrice: price };
}
