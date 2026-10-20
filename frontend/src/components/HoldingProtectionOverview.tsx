import type { HoldingStock, HoldingWorkspaceContext } from "../services/holdingsApi";
import { holdingProtectionSummary } from "./holdingProtectionSummary";

type Props = { stock: HoldingStock; context: HoldingWorkspaceContext | null; loading: boolean };

export default function HoldingProtectionOverview({ stock, context, loading }: Props) {
  const info = holdingProtectionSummary(stock, context, loading);
  return (
    <section className={"holdings-protection-overview state-" + info.state.toLowerCase()}
      aria-label="보유 현황 및 위험 관리 확인" role="status">
      <div className="holdings-protection-top">
        <div>
          <span className="holdings-protection-eyebrow">보유 관리 핵심 상태</span>
          <h3>{info.headline}</h3>
          <p>{info.explanation}</p>
        </div>
        <small>{info.sourceDate ? info.sourceDate + " 확정 EOD 참고" : "확정 데이터 시점 확인 필요"}</small>
      </div>
      <div className="holdings-protection-facts">
        <div><span>보유 기록</span><strong>{info.positionCountDescription}</strong></div>
        <div><span>적용 관리 계획</span><strong>{info.plan.label}</strong></div>
        <div><span>보유 판단</span><strong>{info.decision.label}</strong></div>
        <div><span>실시간 Watch</span><strong>{info.watch.label}</strong></div>
      </div>
      <p className="holdings-protection-next">{info.nextAction}</p>
      <div className="holdings-protection-links">
        <a href="#holdings-decision-panel">보유 판단 살펴보기 ↓</a>
        <a href="#holding-watch-summary">Watch 확인 ↓</a>
        {context?.management && <a href="#holdings-management-block">관리 계획 확인 ↓</a>}
      </div>
      <small>보유 기록과 Scanner 신규 진입 READY는 별개입니다. 이 요약은 주문·자동손절·실시간 위험 알림을 실행하지 않습니다.</small>
    </section>
  );
}
