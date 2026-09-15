import { buildEntryPricePosition } from "../src/components/entryPricePosition";

function equal(actual: unknown, expected: unknown, label: string) {
  if (actual !== expected) throw new Error(`${label}: expected ${String(expected)}, got ${String(actual)}`);
}

const range = { kind: "RANGE", label: "20일 평균 가격 근처 구간", range_low: 95, range_high: 105, trigger_price: null, reference_price: 100 };
equal(buildEntryPricePosition(100, range).message, "현재가가 관심 구간 안에 있습니다.", "range inside");
equal(buildEntryPricePosition(90, range).message, "관심 구간까지 5원 남았습니다. (+5.6%)", "range below");
equal(buildEntryPricePosition(110, range).message, "관심 구간보다 5원 높습니다. (+4.8%)", "range above");

const breakout = { kind: "ABOVE", label: "20일 고점 돌파 확인 가격", range_low: null, range_high: null, trigger_price: 100, reference_price: 100 };
equal(buildEntryPricePosition(98, breakout).message, "돌파 기준까지 2원 남았습니다. (+2.0%)", "breakout below");
equal(buildEntryPricePosition(103, breakout).message, "돌파 기준을 3원 넘었습니다. (+3.0%)", "breakout above");

const maxPrice = { kind: "AT_OR_BELOW", label: "목표 여유를 남길 수 있는 최대 참고가격", range_low: null, range_high: null, trigger_price: 100, reference_price: 110 };
equal(buildEntryPricePosition(97, maxPrice).message, "최대 참고가격보다 3원 낮습니다. (-3.0%)", "max below");
equal(buildEntryPricePosition(104, maxPrice).message, "최대 참고가격보다 4원 높습니다. (+4.0%)", "max above");

const unavailable = { kind: "UNAVAILABLE", label: "가격 기준 계산 불가", range_low: null, range_high: null, trigger_price: null, reference_price: null };
equal(buildEntryPricePosition(100, unavailable).state, "UNAVAILABLE", "unavailable");

console.log("entryPricePosition v0.21.4-A.4: OK");
