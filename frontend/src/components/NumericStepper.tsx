import { useEffect, useRef } from "react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react";

type NumericStepperProps = {
  value: string;
  onChange: (value: string) => void;
  unit: string;
  mode?: "price" | "quantity" | "volume";
  placeholder?: string;
  seedValue?: number | null;
  baseValue?: number | null;
  baseLabel?: string;
  quickPercentages?: number[];
  ariaLabel?: string;
};

export function parseFormattedNumber(value: string): number | null {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatIntegerInput(value: string): string {
  const digits = value.replace(/[^0-9]/g, "");
  if (!digits) return "";
  const normalized = digits.replace(/^0+(?=\d)/, "");
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return "";
  return Math.trunc(parsed).toLocaleString("ko-KR");
}

export function krxTickSize(price: number): number {
  const safePrice = Math.max(0, price);
  if (safePrice < 2_000) return 1;
  if (safePrice < 5_000) return 5;
  if (safePrice < 20_000) return 10;
  if (safePrice < 50_000) return 50;
  if (safePrice < 200_000) return 100;
  if (safePrice < 500_000) return 500;
  return 1_000;
}

function formatNumber(value: number): string {
  return Math.max(0, Math.round(value)).toLocaleString("ko-KR");
}

function snapPrice(value: number): number {
  const safe = Math.max(1, value);
  const tick = krxTickSize(safe);
  return Math.max(tick, Math.round(safe / tick) * tick);
}

function dailyButtonLimits(baseValue: number) {
  const lowerRaw = baseValue * 0.7;
  const upperRaw = baseValue * 1.3;
  const lowerTick = krxTickSize(lowerRaw);
  const upperTick = krxTickSize(upperRaw);
  return {
    lower: Math.max(lowerTick, Math.ceil(lowerRaw / lowerTick) * lowerTick),
    upper: Math.max(upperTick, Math.floor(upperRaw / upperTick) * upperTick),
  };
}

function snapPriceWithinLimits(value: number, baseValue?: number | null): number {
  if (baseValue == null || baseValue <= 0) return snapPrice(value);
  const { lower, upper } = dailyButtonLimits(baseValue);
  const clamped = Math.min(upper, Math.max(lower, value));
  const tick = krxTickSize(clamped);
  let snapped = Math.round(clamped / tick) * tick;
  if (snapped < lower) snapped = Math.ceil(lower / tick) * tick;
  if (snapped > upper) snapped = Math.floor(upper / tick) * tick;
  return Math.min(upper, Math.max(lower, snapped));
}

function volumeStep(value: number): number {
  const safe = Math.max(0, value);
  if (safe < 10_000) return 100;
  if (safe < 100_000) return 1_000;
  if (safe < 1_000_000) return 10_000;
  if (safe < 10_000_000) return 100_000;
  return 1_000_000;
}

export default function NumericStepper({
  value,
  onChange,
  unit,
  mode = "price",
  placeholder,
  seedValue,
  baseValue,
  baseLabel,
  quickPercentages = [],
  ariaLabel,
}: NumericStepperProps) {
  const current = parseFormattedNumber(value);
  const currentRef = useRef<number | null>(current);
  const holdDelayRef = useRef<number | null>(null);
  const holdRepeatRef = useRef<number | null>(null);
  const holdStartedAtRef = useRef(0);
  const quickAnchorRef = useRef<{ value: number; percent: number } | null>(null);

  currentRef.current = current;

  const clearHold = () => {
    if (holdDelayRef.current != null) {
      window.clearTimeout(holdDelayRef.current);
      holdDelayRef.current = null;
    }
    if (holdRepeatRef.current != null) {
      window.clearTimeout(holdRepeatRef.current);
      holdRepeatRef.current = null;
    }
  };

  useEffect(() => {
    quickAnchorRef.current = null;
  }, [baseValue]);

  useEffect(() => clearHold, []);

  const commit = (next: number) => {
    currentRef.current = next;
    onChange(formatNumber(next));
  };

  const adjust = (direction: -1 | 1) => {
    quickAnchorRef.current = null;
    const liveCurrent = currentRef.current;

    if (liveCurrent == null) {
      if (seedValue != null && seedValue > 0) {
        const seeded = mode === "price"
          ? snapPriceWithinLimits(seedValue, baseValue)
          : Math.max(mode === "volume" ? 0 : 1, Math.round(seedValue));
        commit(seeded);
        return;
      }
      if (direction > 0) commit(mode === "volume" ? 1_000 : 1);
      return;
    }

    if (mode === "quantity") {
      commit(Math.max(1, Math.round(liveCurrent + direction)));
      return;
    }

    if (mode === "volume") {
      const step = volumeStep(liveCurrent);
      commit(Math.max(0, Math.round(liveCurrent + direction * step)));
      return;
    }

    const tick = krxTickSize(liveCurrent);
    const next = snapPriceWithinLimits(liveCurrent + direction * tick, baseValue);
    commit(next);
  };

  const beginHold = (direction: -1 | 1, event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    event.preventDefault();
    clearHold();

    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Some browsers can reject pointer capture; repeating still works.
    }

    adjust(direction);
    holdStartedAtRef.current = Date.now();

    const repeat = () => {
      adjust(direction);
      const elapsed = Date.now() - holdStartedAtRef.current;
      const delay = elapsed >= 1_600 ? 55 : elapsed >= 850 ? 90 : 135;
      holdRepeatRef.current = window.setTimeout(repeat, delay);
    };

    holdDelayRef.current = window.setTimeout(() => {
      holdDelayRef.current = null;
      repeat();
    }, 320);
  };

  const keyboardClick = (direction: -1 | 1, event: ReactMouseEvent<HTMLButtonElement>) => {
    // Pointer interaction is handled by onPointerDown so it does not double-step.
    // Keyboard-generated clicks have detail === 0.
    if (event.detail === 0) adjust(direction);
  };

  const applyBase = () => {
    if (baseValue == null || baseValue <= 0) return;
    const next = mode === "price" ? snapPriceWithinLimits(baseValue, baseValue) : Math.round(baseValue);
    quickAnchorRef.current = { value: next, percent: 0 };
    commit(next);
  };

  const applyPercent = (deltaPercent: number) => {
    if (baseValue == null || baseValue <= 0) return;

    const liveCurrent = currentRef.current;
    const anchored = quickAnchorRef.current;
    let currentPercent = 0;

    if (anchored && liveCurrent === anchored.value) {
      currentPercent = anchored.percent;
    } else if (liveCurrent != null) {
      currentPercent = ((liveCurrent / baseValue) - 1) * 100;
    }

    const targetPercent = Math.min(30, Math.max(-30, currentPercent + deltaPercent));
    const targetPrice = baseValue * (1 + targetPercent / 100);
    const next = mode === "price"
      ? snapPriceWithinLimits(targetPrice, baseValue)
      : Math.max(1, Math.round(targetPrice));

    quickAnchorRef.current = { value: next, percent: targetPercent };
    commit(next);
  };

  const relativePercent = (
    mode === "price" &&
    baseValue != null &&
    baseValue > 0 &&
    current != null
  )
    ? ((current / baseValue) - 1) * 100
    : null;

  const limits = mode === "price" && baseValue != null && baseValue > 0
    ? dailyButtonLimits(baseValue)
    : null;
  const atLowerLimit = current != null && limits != null && current <= limits.lower;
  const atUpperLimit = current != null && limits != null && current >= limits.upper;

  const handleDirectInput = (nextValue: string) => {
    quickAnchorRef.current = null;
    onChange(formatIntegerInput(nextValue));
  };

  return (
    <div className="numeric-stepper">
      {relativePercent != null && (
        <div className="numeric-stepper-status">
          <span>{baseLabel ?? "기준가"} 대비</span>
          <strong className={relativePercent > 0 ? "positive" : relativePercent < 0 ? "negative" : "neutral"}>
            {relativePercent > 0 ? "+" : ""}{relativePercent.toFixed(2)}%
          </strong>
          <em>버튼 조정 범위 -30% ~ +30%</em>
        </div>
      )}

      <div className="numeric-stepper-main">
        <button
          type="button"
          className="numeric-step-button"
          onPointerDown={(event) => beginHold(-1, event)}
          onPointerUp={clearHold}
          onPointerCancel={clearHold}
          onLostPointerCapture={clearHold}
          onClick={(event) => keyboardClick(-1, event)}
          onContextMenu={(event) => event.preventDefault()}
          disabled={atLowerLimit}
          aria-label={`${ariaLabel ?? "값"} 감소`}
          title="짧게 누르면 1단계, 꾹 누르면 연속 감소"
        >
          −
        </button>
        <div className="numeric-step-input">
          <input
            value={value}
            onChange={(event) => handleDirectInput(event.target.value)}
            placeholder={placeholder}
            inputMode="numeric"
            aria-label={ariaLabel}
          />
          <i>{unit}</i>
        </div>
        <button
          type="button"
          className="numeric-step-button"
          onPointerDown={(event) => beginHold(1, event)}
          onPointerUp={clearHold}
          onPointerCancel={clearHold}
          onLostPointerCapture={clearHold}
          onClick={(event) => keyboardClick(1, event)}
          onContextMenu={(event) => event.preventDefault()}
          disabled={atUpperLimit}
          aria-label={`${ariaLabel ?? "값"} 증가`}
          title="짧게 누르면 1단계, 꾹 누르면 연속 증가"
        >
          +
        </button>
      </div>

      {(mode === "price" || mode === "volume") && (
        <div className="numeric-stepper-hold-hint">
          <span>{mode === "price" ? "− / + 짧게: 1호가" : "− / + 짧게: 1단계"}</span>
          <span>꾹 누르기: 연속 조정</span>
        </div>
      )}

      {(baseLabel && baseValue != null && baseValue > 0) || quickPercentages.length > 0 ? (
        <div className="numeric-stepper-quick">
          {quickPercentages
            .filter((percent) => percent < 0)
            .map((percent) => (
              <button type="button" key={percent} onClick={() => applyPercent(percent)} disabled={!baseValue || atLowerLimit}>
                {percent}%
              </button>
            ))}
          {baseLabel && baseValue != null && baseValue > 0 && (
            <button type="button" className="base" onClick={applyBase}>
              {baseLabel}
            </button>
          )}
          {quickPercentages
            .filter((percent) => percent > 0)
            .map((percent) => (
              <button type="button" key={percent} onClick={() => applyPercent(percent)} disabled={!baseValue || atUpperLimit}>
                +{percent}%
              </button>
            ))}
        </div>
      ) : null}
    </div>
  );
}
