import type { ProductionExitPolicyMetadata } from "../services/api";

const BASELINE_POLICY_IDS = new Set(["TARGET1_FULL_EXIT", "TARGET1_FULL_EXIT_V1"]);

export function productionPolicyLabel(policy: ProductionExitPolicyMetadata | null | undefined) {
  const id = policy?.policy_id ?? "TARGET1_FULL_EXIT";
  const labels: Record<string, string> = {
    TARGET1_FULL_EXIT: "1차 목표가 도달 시 전량 매도",
    TARGET1_FULL_EXIT_V1: "1차 목표가 도달 시 전량 매도",
    ATR_TRAIL_1_5: "ATR 1.5배 기준 수익 보호",
    ATR_TRAIL_2_0: "ATR 2.0배 기준 수익 보호",
    ATR_TRAIL_2_5: "ATR 2.5배 기준 수익 보호",
    MA20_TRAIL: "20일 이동평균선 기준 수익 보호",
    SWING_LOW_TRAIL: "최근 확정 저점 기준 수익 보호",
    CONFIRMED_SWING_LOW_TRAIL: "최근 확정 저점 기준 수익 보호",
  };
  return labels[id] ?? policy?.label ?? "1차 목표가 도달 시 전량 매도";
}

export function isTrackingProductionPolicy(policy: ProductionExitPolicyMetadata | null | undefined) {
  const id = policy?.policy_id ?? "TARGET1_FULL_EXIT";
  return !BASELINE_POLICY_IDS.has(id) && Boolean(policy?.target2_included);
}

export function productionPolicyExplanation(policyId: string) {
  if (policyId.startsWith("ATR_TRAIL_")) {
    return "최근 가격 변동폭을 이용해 수익 보호 기준을 계산하는 방식입니다.";
  }
  if (policyId === "MA20_TRAIL") {
    return "최근 20거래일 평균 가격 흐름을 따라 수익 보호 기준을 조정하는 방식입니다.";
  }
  if (policyId === "CONFIRMED_SWING_LOW_TRAIL" || policyId === "SWING_LOW_TRAIL") {
    return "상승 과정에서 확인된 최근 저점을 기준으로 수익 보호 기준을 조정하는 방식입니다.";
  }
  return "2차 목표가 이후 가격 흐름을 따라 수익 보호 기준을 조정하는 방식입니다.";
}

export function target2RoleLabel(policy: ProductionExitPolicyMetadata | null | undefined) {
  return isTrackingProductionPolicy(policy) ? "수익 보호 시작 기준" : "참고 가격";
}

export type ProtectionDisplayState =
  | "NOT_APPLICABLE"
  | "WAITING_FOR_TARGET2"
  | "TARGET2_LEVEL_REACHED"
  | "PROTECTION_ACTIVE";

export function deriveProtectionDisplayState(
  policy: ProductionExitPolicyMetadata | null | undefined,
  currentPrice: number | null | undefined,
  target2Price: number | null | undefined,
): ProtectionDisplayState {
  if (!isTrackingProductionPolicy(policy)) return "NOT_APPLICABLE";
  const backendState = policy?.profit_protection?.state;
  const protectionPrice = policy?.profit_protection?.current_protection_price;
  if (backendState === "PROTECTION_ACTIVE" && protectionPrice != null && Number.isFinite(protectionPrice)) {
    return "PROTECTION_ACTIVE";
  }
  if (
    currentPrice != null && Number.isFinite(currentPrice) &&
    target2Price != null && Number.isFinite(target2Price) &&
    currentPrice < target2Price
  ) {
    return "WAITING_FOR_TARGET2";
  }
  return "TARGET2_LEVEL_REACHED";
}
