import type { HoldingStock, HoldingWorkspaceContext } from "../services/holdingsApi";
import { holdingProtectionSummary } from "./holdingProtectionSummary";
import { holdingsWatchPolicyText } from "./holdingsWatchPolicyText";

type Props = { stock: HoldingStock; context: HoldingWorkspaceContext | null; loading: boolean };

export default function HoldingProtectionOverview({ stock, context, loading }: Props) {
  const info = holdingProtectionSummary(stock, context, loading);
  const blockedPosition = info.watch.state === "POLICY_UNVERIFIED"
    ? context?.positions.find(row => row.watch && !row.watch.policy_enabled)
    : null;
  const watchPolicyCopy = blockedPosition
    ? holdingsWatchPolicyText(blockedPosition.watch)
    : null;
  return (
    <section className={"holdings-protection-overview state-" + info.state.toLowerCase()}
      aria-label="보유 현황 및 위험 관리 확인" role="status">
      <div className="holdings-protection-top">
        <div>
          <span className="holdings-protection-eyebrow">보유 관리 핵심 상태</span>
          <h3>{info.headline}</h3>
        </div>
        <small>{info.sourceDate ? info.sourceDate + " 확정 EOD 참고" : "확정 데이터 시점 확인 필요"}</small>
      </div>
      <div className="holdings-protection-facts">
        <div><span>보유 기록</span><strong>{info.positionCountDescription}</strong></div>
        <div><span>적용 관리 계획</span><strong>{info.plan.label}</strong></div>
        <div><span>보유 판단</span><strong>{info.decision.label}</strong></div>
        <div><span>실시간 Watch</span><strong>{info.watch.label}</strong></div>
      </div>
      {watchPolicyCopy && <p className="holdings-protection-policy-reason">{watchPolicyCopy.explanation}</p>}
      <p className="holdings-protection-next">{info.nextAction}</p>
      <div className="holdings-protection-links">
        <a className="holdings-protection-primary-link" href="#holdings-decision-panel">
          {info.decision.state === "NOT_CREATED" || info.decision.state === "RECHECK"
            ? "보유 판단 업데이트 위치로 이동 ↓" : "보유 판단 확인 ↓"}
        </a>
        {context?.management && <a href="#holdings-management-block">관리 계획 상세 ↓</a>}
        <a href="#holding-watch-summary">Watch 상태 상세 ↓</a>
      </div>
      <small>StockScope 기록만 요약합니다. 증권사 실잔고·실제 주문 체결·실시간 감시 가동은 검증하지 않았습니다.</small>
    </section>
  );
}
