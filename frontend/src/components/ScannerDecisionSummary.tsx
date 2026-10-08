import type { ScannerCandidate } from "../services/api";
import { beginnerCandidatePresentation } from "./scannerDecisionPresentation";

type Props = { candidate: ScannerCandidate };

export default function ScannerDecisionSummary({ candidate }: Props) {
  const view = beginnerCandidatePresentation(candidate);
  return (
    <section className="scanner-ux-decision scanner-ux2-decision" aria-label="선택한 종목의 쉬운 판단">
      <span className="scanner-ux-eyebrow">한눈에 보는 판단 · 분석일 기준</span>
      <h4>{view.headline}</h4>
      <p className="scanner-ux2-decision-why">
        <strong>왜 찾았나요?</strong>
        <span>{view.why}</span>
      </p>
      <div className="scanner-ux-decision-facts scanner-ux2-facts">
        <div>
          <strong>무엇을 조심해야 하나요?</strong>
          <p>{view.caution}</p>
        </div>
        <div>
          <strong>다음에는 뭘 확인할까요?</strong>
          <p>{view.next}</p>
        </div>
      </div>
      <p className="scanner-ux-disclaimer">
        분석일 기준의 검토 순서이며, 지금 매수하라는 뜻은 아니에요.
      </p>
    </section>
  );
}
