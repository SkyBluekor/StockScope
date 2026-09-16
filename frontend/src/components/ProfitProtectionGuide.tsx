import type { ConcreteEntryRiskGuide } from "../services/api";
import { deriveProtectionDisplayState, isTrackingProductionPolicy, productionPolicyExplanation, productionPolicyLabel } from "./profitProtection";

type Props = {
  guide: ConcreteEntryRiskGuide;
  compact?: boolean;
};

function finite(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function price(value: number | null | undefined) {
  if (!finite(value)) return "-";
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}원`;
}

function percentGap(current: number | null | undefined, target: number | null | undefined) {
  if (!finite(current) || !finite(target) || current <= 0) return null;
  return (target - current) / current * 100;
}

function displayValue(raw: number | null | undefined, display: number | null | undefined) {
  return finite(display) ? display : finite(raw) ? raw : null;
}

function entryReference(guide: ConcreteEntryRiskGuide) {
  if (finite(guide.risk.entry_reference_price)) return guide.risk.entry_reference_price;
  const rule = guide.price_rule;
  const trigger = displayValue(rule.trigger_price, rule.display_trigger_price);
  if (finite(trigger)) return trigger;
  const reference = displayValue(rule.reference_price, rule.display_reference_price);
  if (finite(reference)) return reference;
  const low = displayValue(rule.range_low, rule.display_range_low);
  const high = displayValue(rule.range_high, rule.display_range_high);
  if (finite(low) && finite(high)) return (low + high) / 2;
  return low ?? high ?? null;
}

function PricePositionMap({ guide, tracking }: { guide: ConcreteEntryRiskGuide; tracking: boolean }) {
  const current = displayValue(guide.current_price, guide.display_current_price);
  const stop = displayValue(guide.risk.invalidation_price, guide.risk.display_invalidation_price);
  const entry = entryReference(guide);
  const target1 = displayValue(guide.risk.target1_price, guide.risk.display_target1_price);
  const target2 = displayValue(guide.risk.target2_price, guide.risk.display_target2_price);
  const values = [stop, entry, target1, target2, current].filter(finite);
  if (values.length < 2) return null;

  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min *= 0.98;
    max *= 1.02;
  }
  const pad = Math.max((max - min) * 0.06, Math.abs(max) * 0.005);
  min -= pad;
  max += pad;
  const pos = (value: number) => Math.max(1, Math.min(99, ((value - min) / (max - min)) * 100));

  const levels = [
    { key: "stop", label: "손절", value: stop, tone: "danger" },
    { key: "entry", label: "진입 참고", value: entry, tone: "neutral" },
    { key: "target1", label: "1차 목표", value: target1, tone: "success" },
    { key: "target2", label: "2차 목표", value: target2, tone: "primary" },
  ].filter((item): item is { key: string; label: string; value: number; tone: string } => finite(item.value));

  return (
    <div className="exit-price-map" aria-label="현재가와 주요 가격 기준 위치">
      <div className="exit-price-map-title">
        <strong>현재 가격 위치</strong>
        <span>가격 간 거리를 한눈에 보기 위한 참고 표시입니다.</span>
      </div>
      <div className="exit-price-track-wrap">
        <div className="exit-price-track" />
        {levels.map((item) => (
          <span
            key={item.key}
            className={`exit-price-marker tone-${item.tone}`}
            style={{ left: `${pos(item.value)}%` }}
            aria-label={`${item.label} ${price(item.value)}`}
          />
        ))}
        {finite(current) && (
          <div className="exit-price-current" style={{ left: `${pos(current)}%` }}>
            <b>현재가</b>
            <strong>{price(current)}</strong>
          </div>
        )}
      </div>
      <div className="exit-price-legend">
        {levels.map((item) => (
          <div key={item.key}>
            <span className={`exit-price-dot tone-${item.tone}`} />
            <small>{item.label}</small>
            <strong>{price(item.value)}</strong>
            {item.key === "target2" && <em>{tracking ? "수익 보호 시작 기준" : "참고 가격"}</em>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProfitProtectionGuide({ guide, compact = false }: Props) {
  const policy = guide.historical_policy;
  const policyId = policy?.policy_id ?? "TARGET1_FULL_EXIT";
  const tracking = isTrackingProductionPolicy(policy);
  const protection = policy?.profit_protection;
  const current = displayValue(guide.current_price, guide.display_current_price);
  const target2 = displayValue(guide.risk.target2_price, guide.risk.display_target2_price);
  const target2Gap = percentGap(current, target2);
  const displayState = deriveProtectionDisplayState(policy, current, target2);
  const activePrice = protection?.current_protection_price;
  const active = displayState === "PROTECTION_ACTIVE" && finite(activePrice);
  const activeGap = active ? percentGap(activePrice, current) : null;

  if (compact) {
    return (
      <div className={`profit-protection-compact ${tracking ? "tracking" : "baseline"}`}>
        <strong>현재 수익 실현 기준</strong>
        <span>{productionPolicyLabel(policy)}</span>
        <small>
          {!policy
            ? "현재 실제 정책 정보를 확인하지 못해 안전한 기본 기준으로 표시합니다."
            : tracking
              ? "2차 목표가 이후 수익 보호를 시작하는 기준입니다. 실제 보호선은 보유 이력이 있을 때 확정합니다."
              : "1차 목표가가 실제 수익 실현 기준이며 2차 목표가는 참고 가격입니다."}
        </small>
      </div>
    );
  }

  return (
    <section className={`profit-protection-guide ${tracking ? "tracking" : "baseline"}`}>
      <PricePositionMap guide={guide} tracking={tracking} />

      <div className="profit-protection-main">
        <div className="profit-protection-heading">
          <span>현재 수익 실현 기준</span>
          <strong>{productionPolicyLabel(policy)}</strong>
          <p>
            {tracking
              ? productionPolicyExplanation(policyId)
              : "현재 적용 기준에서는 1차 목표가에 도달하면 거래를 종료합니다."}
          </p>
        </div>

        {!tracking ? (
          <div className="profit-protection-summary baseline-summary">
            <div><small>1차 목표가</small><strong>실제 수익 실현 기준</strong></div>
            <div><small>2차 목표가</small><strong>참고 가격</strong></div>
            <p>현재 실제 적용 기준에는 추적형 수익 보호선이 없습니다.</p>
          </div>
        ) : (
          <div className="profit-protection-summary tracking-summary">
            <div className="profit-protection-status">
              <small>현재 상태</small>
              {active ? (
                <strong>수익 보호 진행 중</strong>
              ) : displayState === "WAITING_FOR_TARGET2" ? (
                <strong>수익 보호 대기 중</strong>
              ) : (
                <strong>보호 시작 가격 확인 구간</strong>
              )}
            </div>

            {active ? (
              <>
                <div><small>현재 보호 기준</small><strong>{price(activePrice)}</strong></div>
                <div><small>현재가와 보호 기준 차이</small><strong>{activeGap == null ? "-" : `${Math.abs(activeGap).toFixed(1)}%`}</strong></div>
                <p>보호 기준은 상승할 수 있지만 다시 낮아지지 않는 방식입니다.</p>
              </>
            ) : (
              <>
                <div><small>수익 보호 시작 기준</small><strong>{price(target2)}</strong></div>
                <div><small>현재 가격 위치</small><strong>{target2Gap == null ? "확인 필요" : target2Gap > 0 ? `2차 목표가까지 ${target2Gap.toFixed(1)}%` : "2차 목표가 이상"}</strong></div>
                <p>
                  현재 종목 분석에는 실제 보유 시작일·보호선 이력이 없으므로 보호선이 활성화됐다고 추측하지 않습니다. 실제 보호 기준은 포지션 이력이 있을 때만 표시합니다.
                </p>
              </>
            )}
          </div>
        )}

        {!policy ? (
          <p className="profit-protection-fallback">현재 실제 적용 기준을 확인하지 못해 안전한 기본 기준으로 표시하고 있습니다.</p>
        ) : policy.fallback_used ? (
          <p className="profit-protection-fallback">검증된 다른 기준이 실제 적용되지 않아 현재 기본 기준을 사용하고 있습니다.</p>
        ) : null}
      </div>
    </section>
  );
}
