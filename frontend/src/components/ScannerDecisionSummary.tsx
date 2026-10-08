import type { ScannerCandidate } from "../services/api";
import { beginnerCandidatePresentation } from "./scannerDecisionPresentation";

type Props = { candidate: ScannerCandidate };

export default function ScannerDecisionSummary({ candidate }: Props) {
  const view = beginnerCandidatePresentation(candidate);
  return (
    <section className="scanner-ux-decision" aria-label="선택한 종목의 쉬운 판단">
      <span className="scanner-ux-eyebrow">한눈에 보는 현재 판단 · 분석일 기준</span>
      <h4>{view.headline}</h4>
      <div className="scanner-ux-decision-facts">
        <div>
          <strong>왜 찾았나요?</strong>
          <p>{view.why}</p>
        </div>
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
        이 결과는 확정된 거래일의 분석입니다. 검토 순서가 높아도 매수하라는 뜻은 아니에요.
      </p>
    </section>
  );
}
