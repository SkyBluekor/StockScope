import {
  deriveProtectionDisplayState,
  isTrackingProductionPolicy,
  productionPolicyLabel,
  target2RoleLabel,
} from "../src/components/profitProtection";
import type { ProductionExitPolicyMetadata } from "../src/services/api";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const baseline: ProductionExitPolicyMetadata = {
  policy_id: "TARGET1_FULL_EXIT",
  label: "legacy",
  target1_is_exit: true,
  target2_included: false,
  target2_label: "2차 목표가",
  profit_protection: {
    enabled: false,
    activation: null,
    state: "NOT_APPLICABLE",
    current_protection_price: null,
  },
};
assert(productionPolicyLabel(baseline) === "1차 목표가 도달 시 전량 매도", "baseline label");
assert(isTrackingProductionPolicy(baseline) === false, "baseline must not be tracking");
assert(target2RoleLabel(baseline) === "참고 가격", "baseline target2 role");
assert(deriveProtectionDisplayState(baseline, 100, 120) === "NOT_APPLICABLE", "baseline protection state");

const atr: ProductionExitPolicyMetadata = {
  ...baseline,
  policy_id: "ATR_TRAIL_2_0",
  target1_is_exit: false,
  target2_included: true,
  profit_protection: {
    enabled: true,
    activation: "AFTER_TARGET2",
    state: "POSITION_CONTEXT_REQUIRED",
    current_protection_price: null,
  },
};
assert(productionPolicyLabel(atr) === "ATR 2.0배 기준 수익 보호", "ATR label");
assert(isTrackingProductionPolicy(atr) === true, "ATR must be tracking");
assert(target2RoleLabel(atr) === "수익 보호 시작 기준", "tracking target2 role");
assert(deriveProtectionDisplayState(atr, 110, 120) === "WAITING_FOR_TARGET2", "before target2 state");
assert(deriveProtectionDisplayState(atr, 121, 120) === "TARGET2_LEVEL_REACHED", "target2 level reached but not active");

const active: ProductionExitPolicyMetadata = {
  ...atr,
  profit_protection: {
    enabled: true,
    activation: "AFTER_TARGET2",
    state: "PROTECTION_ACTIVE",
    current_protection_price: 118,
  },
};
assert(deriveProtectionDisplayState(active, 123, 120) === "PROTECTION_ACTIVE", "active protection state");

const ma20 = { ...atr, policy_id: "MA20_TRAIL" };
const swing = { ...atr, policy_id: "CONFIRMED_SWING_LOW_TRAIL" };
assert(productionPolicyLabel(ma20) === "20일 이동평균선 기준 수익 보호", "MA20 label");
assert(productionPolicyLabel(swing) === "최근 확정 저점 기준 수익 보호", "swing label");

console.log("profitProtection v0.21.4-B.2.2: PASS");
