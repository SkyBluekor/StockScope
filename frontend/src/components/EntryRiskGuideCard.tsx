import type { ConcreteEntryRiskGuide } from "../services/api";
import { buildEntryPricePosition } from "./entryPricePosition";

type Props = {
  guide: ConcreteEntryRiskGuide;
  compact?: boolean;
};

function price(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value)}원`;
}

function displayPrice(raw: number | null | undefined, display: number | null | undefined) {
  const value = display ?? raw;
  if (value == null || !Number.isFinite(value)) return "-";
  const changed = raw != null && Number.isFinite(raw) && Math.round(raw) !== Math.round(value);
  return `${changed ? "약 " : ""}${price(value)}`;
}

function rawPriceNote(raw: number | null | undefined, display: number | null | undefined) {
  if (raw == null || display == null || !Number.isFinite(raw) || !Number.isFinite(display)) return null;
  if (Math.round(raw) === Math.round(display)) return null;
  return `계산 기준 ${price(raw)}`;
}

function pct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function ratio(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value.toFixed(2)}배`;
}

function currentRelativePct(current: number | null | undefined, target: number | null | undefined) {
  if (current == null || target == null || !Number.isFinite(current) || !Number.isFinite(target) || current === 0) return null;
  return (target - current) / current * 100;
}

function goalPositionText(current: number | null | undefined, target: number | null | undefined, label: string) {
  if (current == null || target == null || !Number.isFinite(current) || !Number.isFinite(target) || current <= 0) return `${label} 계산 불가`;
  if (current > target) return `${label}${label === "2차 확장 목표" ? "도" : "를"} 이미 넘어섰습니다.`;
  if (current === target) return `${label}에 도달했습니다.`;
  const gap = (target - current) / current * 100;
  return `현재가 대비 +${gap.toFixed(1)}%`;
}

function priceRuleText(guide: ConcreteEntryRiskGuide) {
  const rule = guide.price_rule;
  if (rule.kind === "RANGE" && rule.range_low != null && rule.range_high != null) {
    return `${displayPrice(rule.range_low, rule.display_range_low)} ~ ${displayPrice(rule.range_high, rule.display_range_high)}`;
  }
  if (rule.kind === "ABOVE" && rule.trigger_price != null) return `${displayPrice(rule.trigger_price, rule.display_trigger_price)} 초과`;
  if (rule.kind === "AT_OR_BELOW" && rule.trigger_price != null) return `${displayPrice(rule.trigger_price, rule.display_trigger_price)} 이하`;
  if (rule.reference_price != null) return displayPrice(rule.reference_price, rule.display_reference_price);
  return "가격 기준 계산 불가";
}

function volumeRuleText(guide: ConcreteEntryRiskGuide) {
  const rule = guide.volume_rule;
  if (!rule.available || rule.required_ratio == null) return "별도 배수 기준 없음";
  if (rule.comparator === "AT_MOST") return `${ratio(rule.required_ratio)} 이하`;
  return `${ratio(rule.required_ratio)} 이상`;
}

function compactPricePlan(guide: ConcreteEntryRiskGuide) {
  const risk = guide.risk;
  const position = buildEntryPricePosition(guide.current_price, guide.price_rule);
  const stopPct = currentRelativePct(guide.current_price, risk.invalidation_price);
  const policy = guide.historical_policy;

  return (
    <section className="concrete-guide-card compact scanner-price-plan">
      <div className="scanner-price-plan-head">
        <div>
          <span>가격 계획</span>
          <strong>{displayPrice(guide.current_price, guide.display_current_price)}</strong>
          <small>현재 확정 종가</small>
        </div>
        <div className={`scanner-price-position state-${position.state.toLowerCase()}`}>
          <small>현재 가격 위치</small>
          <strong>{position.message}</strong>
        </div>
      </div>

      <div className="scanner-price-plan-grid">
        <article>
          <small>진입 참고</small>
          <strong>{priceRuleText(guide)}</strong>
          <span>{guide.price_rule.label}</span>
        </article>

        <article className="price-plan-stop">
          <small>손절 참고</small>
          <strong>{displayPrice(risk.invalidation_price, risk.display_invalidation_price)}</strong>
          <span>{stopPct == null ? "현재 Risk Engine 기준" : `현재가 대비 ${pct(stopPct)}`}</span>
          {rawPriceNote(risk.invalidation_price, risk.display_invalidation_price) && <b>{rawPriceNote(risk.invalidation_price, risk.display_invalidation_price)}</b>}
        </article>

        <article className="price-plan-target">
          <small>1차 목표</small>
          <strong>{displayPrice(risk.target1_price, risk.display_target1_price)}</strong>
          <span>{goalPositionText(guide.current_price, risk.target1_price, "1차 목표")}</span>
          {risk.rr1 != null && <b>손익비 1 : {risk.rr1.toFixed(2)}</b>}
        </article>

        <article className="price-plan-target2">
          <small>{policy?.target2_label ?? "2차 확장 목표"}</small>
          <strong>{displayPrice(risk.target2_price, risk.display_target2_price)}</strong>
          <span>{goalPositionText(guide.current_price, risk.target2_price, policy?.target2_label ?? "2차 확장 목표")}</span>
          {risk.rr2 != null && <b>손익비 1 : {risk.rr2.toFixed(2)}</b>}
        </article>
      </div>

      <div className="scanner-price-plan-policy">
        <strong>과거 검증 기준</strong>
        <span>{policy?.label ?? "1차 목표 도달 시 전량 종료"}</span>
        {policy && !policy.target2_included && <small>2차 확장 목표는 현재 과거 성과 계산에는 포함되지 않습니다.</small>}
      </div>
    </section>
  );
}

export default function EntryRiskGuideCard({ guide, compact = false }: Props) {
  if (compact) return compactPricePlan(guide);

  const rule = guide.price_rule;
  const volume = guide.volume_rule;
  const risk = guide.risk;

  return (
    <section className="concrete-guide-card">
      <div className="concrete-guide-head">
        <div>
          <span>구체적인 타이밍·위험 기준</span>
          <strong>{guide.action.title}</strong>
          <p>{guide.action.detail}</p>
        </div>
        <div className="concrete-guide-current">
          <small>현재 확정 종가</small>
          <b>{displayPrice(guide.current_price, guide.display_current_price)}</b>
        </div>
      </div>

      <div className="concrete-guide-grid">
        <article>
          <small>가격 타이밍</small>
          <strong>{priceRuleText(guide)}</strong>
          <span>{rule.label}</span>
          {rule.gap_pct != null && rule.gap_pct !== 0 && <b className="guide-gap">현재가 대비 {pct(rule.gap_pct)}</b>}
          {rule.gap_pct === 0 && <b className="guide-ok">현재 가격 조건 충족</b>}
        </article>

        <article>
          <small>거래량</small>
          <strong>{volumeRuleText(guide)}</strong>
          <span>현재 {ratio(volume.current_ratio)}</span>
          {volume.available && volume.gap_pct != null && volume.gap_pct > 0 && (
            <b className="guide-gap">{volume.comparator === "AT_MOST" ? `약 ${volume.gap_pct.toFixed(0)}% 감소 필요` : `약 ${volume.gap_pct.toFixed(0)}% 더 활발해야 함`}</b>
          )}
          {volume.available && volume.status === "PASS" && <b className="guide-ok">현재 거래량 조건 충족</b>}
        </article>

        <article>
          <small>손절 참고</small>
          <strong>{displayPrice(risk.invalidation_price, risk.display_invalidation_price)}</strong>
          <span>{[rawPriceNote(risk.invalidation_price, risk.display_invalidation_price), risk.risk_pct != null ? `참고 진입가 대비 -${Math.abs(risk.risk_pct).toFixed(1)}%` : "현재 Risk Engine 기준"].filter(Boolean).join(" · ")}</span>
          <b>{risk.structural_anchor_label || "전략 무효 기준"}</b>
        </article>

        <article>
          <small>1차 목표</small>
          <strong>{displayPrice(risk.target1_price, risk.display_target1_price)}</strong>
          <span>{[rawPriceNote(risk.target1_price, risk.display_target1_price), risk.reward1_pct != null ? `참고 진입가 대비 ${pct(risk.reward1_pct)}` : "계산 가능한 목표가 없음"].filter(Boolean).join(" · ")}</span>
          {risk.rr1 != null && <b>손익비 1 : {risk.rr1.toFixed(2)}</b>}
        </article>

        <article>
          <small>{guide.historical_policy?.target2_label ?? "2차 확장 목표"}</small>
          <strong>{displayPrice(risk.target2_price, risk.display_target2_price)}</strong>
          <span>{[rawPriceNote(risk.target2_price, risk.display_target2_price), risk.reward2_pct != null ? `참고 진입가 대비 ${pct(risk.reward2_pct)}` : "확장 목표 계산 불가"].filter(Boolean).join(" · ")}</span>
          {risk.rr2 != null && <b>손익비 1 : {risk.rr2.toFixed(2)}</b>}
        </article>

        <article>
          <small>상승 흐름 기준</small>
          <strong>{guide.trend_strength.available && guide.trend_strength.current_value != null ? pct(guide.trend_strength.current_value) : "직접 상승률 기준 없음"}</strong>
          <span>{guide.trend_strength.available ? `필요 ${guide.trend_strength.required_value || "전략 기준"}` : "단순 +x% 상승률을 새로 만들지 않습니다."}</span>
          <b>{guide.trend_strength.label}</b>
        </article>
      </div>

      <div className="concrete-guide-note">
        <div>
          <strong>전략이 틀렸다고 보는 가격</strong>
          <span>{risk.invalidation_price != null ? `${displayPrice(risk.invalidation_price, risk.display_invalidation_price)} 아래에서는 현재 전략의 전제가 깨진 것으로 봅니다.` : "현재 데이터만으로 전략 무효 가격을 계산하지 못했습니다."}</span>
        </div>
        {risk.needs_recheck && <p><b>다시 계산 필요</b> {risk.recheck_message}</p>}
        {guide.historical_policy && (
          <p className="historical-policy-note"><b>과거 검증 기준</b> {guide.historical_policy.label}. {guide.historical_policy.target2_included ? "2차 목표도 과거 성과 계산에 포함됩니다." : "2차 확장 목표는 현재 과거 성과 계산에는 포함되지 않습니다."}</p>
        )}
        <p>{guide.guardrail}</p>
      </div>
    </section>
  );
}
