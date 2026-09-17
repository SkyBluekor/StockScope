export type EntryPriceRuleForPosition = {
  kind: string;
  label: string;
  range_low: number | null;
  range_high: number | null;
  trigger_price: number | null;
  reference_price: number | null;
};

export type EntryPricePosition = {
  state: "INSIDE" | "BELOW" | "ABOVE" | "AT" | "UNAVAILABLE";
  message: string;
};

function finite(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function won(value: number) {
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(Math.abs(value))}원`;
}

function pct(value: number) {
  const safe = Math.abs(value);
  if (safe < 0.05) return "0.0%";
  return `${safe.toFixed(1)}%`;
}

function relativePct(base: number, value: number) {
  if (!Number.isFinite(base) || base === 0 || !Number.isFinite(value)) return null;
  return Math.abs((value - base) / base * 100);
}

function isBreakoutLabel(label: string) {
  return label.includes("돌파") || label.includes("고점");
}

export function buildEntryPricePosition(
  currentPrice: number | null | undefined,
  rule: EntryPriceRuleForPosition,
): EntryPricePosition {
  if (!finite(currentPrice) || currentPrice <= 0 || rule.kind === "UNAVAILABLE") {
    return {
      state: "UNAVAILABLE",
      message: "현재 전략은 하나의 가격으로 진입 위치를 계산하지 않습니다.",
    };
  }

  if (rule.kind === "RANGE" && finite(rule.range_low) && finite(rule.range_high)) {
    if (currentPrice >= rule.range_low && currentPrice <= rule.range_high) {
      return { state: "INSIDE", message: "현재가가 전략 조건 가격대 안에 있습니다." };
    }
    if (currentPrice < rule.range_low) {
      const delta = rule.range_low - currentPrice;
      const gap = relativePct(currentPrice, rule.range_low);
      return {
        state: "BELOW",
        message: `전략 조건 가격대까지 ${won(delta)} 남았습니다.${gap == null ? "" : ` (+${pct(gap)})`}`,
      };
    }
    const delta = currentPrice - rule.range_high;
    const gap = relativePct(rule.range_high, currentPrice);
    return {
      state: "ABOVE",
      message: `전략 조건 가격대보다 ${won(delta)} 높습니다.${gap == null ? "" : ` (+${pct(gap)})`}`,
    };
  }

  if (rule.kind === "ABOVE" && finite(rule.trigger_price)) {
    const noun = isBreakoutLabel(rule.label) ? "돌파 기준" : "기준 가격";
    if (currentPrice === rule.trigger_price) {
      return { state: "AT", message: `${noun}과 같은 가격입니다.` };
    }
    if (currentPrice < rule.trigger_price) {
      const delta = rule.trigger_price - currentPrice;
      const gap = relativePct(currentPrice, rule.trigger_price);
      return {
        state: "BELOW",
        message: `${noun}까지 ${won(delta)} 남았습니다.${gap == null ? "" : ` (+${pct(gap)})`}`,
      };
    }
    const delta = currentPrice - rule.trigger_price;
    const gap = relativePct(rule.trigger_price, currentPrice);
    return {
      state: "ABOVE",
      message: `${noun}을 ${won(delta)} 넘었습니다.${gap == null ? "" : ` (+${pct(gap)})`}`,
    };
  }

  if (rule.kind === "AT_OR_BELOW" && finite(rule.trigger_price)) {
    if (currentPrice === rule.trigger_price) {
      return { state: "AT", message: "최대 참고가격과 같은 가격입니다." };
    }
    if (currentPrice < rule.trigger_price) {
      const delta = rule.trigger_price - currentPrice;
      const gap = relativePct(rule.trigger_price, currentPrice);
      return {
        state: "BELOW",
        message: `최대 참고가격보다 ${won(delta)} 낮습니다.${gap == null ? "" : ` (-${pct(gap)})`}`,
      };
    }
    const delta = currentPrice - rule.trigger_price;
    const gap = relativePct(rule.trigger_price, currentPrice);
    return {
      state: "ABOVE",
      message: `최대 참고가격보다 ${won(delta)} 높습니다.${gap == null ? "" : ` (+${pct(gap)})`}`,
    };
  }

  const reference = finite(rule.reference_price) ? rule.reference_price : null;
  if (reference != null) {
    if (currentPrice === reference) {
      return { state: "AT", message: "기준 가격과 같은 가격입니다." };
    }
    const delta = Math.abs(currentPrice - reference);
    const gap = relativePct(reference, currentPrice);
    return currentPrice > reference
      ? { state: "ABOVE", message: `기준 가격보다 ${won(delta)} 높습니다.${gap == null ? "" : ` (+${pct(gap)})`}` }
      : { state: "BELOW", message: `기준 가격보다 ${won(delta)} 낮습니다.${gap == null ? "" : ` (-${pct(gap)})`}` };
  }

  return {
    state: "UNAVAILABLE",
    message: "현재 전략은 하나의 가격으로 진입 위치를 계산하지 않습니다.",
  };
}
