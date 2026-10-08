import type { ScannerCandidate } from "../services/api";
import { beginnerCandidatePresentation } from "./scannerDecisionPresentation";

type Props = { candidate: ScannerCandidate };

export default function ScannerDecisionSummary({ candidate }: Props) {
  const view = beginnerCandidatePresentation(candidate);
  return (
    <section className="scanner-ux-decision scanner-ux2-decision" aria-label="선택한 종목의 쉬운 판단">
      <span className="scanner-ux-eyebrow">분석일 기준 판단 · 최신 전략 확인 전</span>
      <h4>{view.headline}</h4>
      <p className="scanner-ux2-decision-why">
        <strong>조건 현황</strong>
        <span>{view.why}</span>
      </p>
      {view.missingCount > 0 && (
        <div className="scanner-ux4-missing" aria-label="미충족 전략 조건">
          <strong>{view.missingConditions.length < view.missingCount ? "대표 미충족 조건" : "미충족 조건"} · {view.missingCount}개</strong>
          {view.missingConditions.length ? (
            <ul>
              {view.missingConditions.map((condition, index) => (
                <li key={condition.label + index}>
                  <b>{condition.label}</b>
                  {(condition.current || condition.required) && (
                    <span>
                      {condition.current && <small>현재: {condition.current}</small>}
                      {condition.required && <small>필요: {condition.required}</small>}
                    </span>
                  )}
                  {condition.detail && <p>{condition.detail}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <p>부족한 조건 {view.missingCount}개는 확인됐지만 상세 항목이 제공되지 않았어요. 전략·가격 탭에서 근거를 확인하세요.</p>
          )}
          {view.missingConditions.length > 0 && view.missingConditions.length < view.missingCount && (
            <small>전체 미충족 조건 중 제공된 대표 항목만 표시했어요.</small>
          )}
        </div>
      )}
      {(candidate.risk.warning || view.asOfPrice.state === "OUT_OF_RANGE") && (
        <p className="scanner-ux5-caution"><strong>주의</strong> {view.caution}</p>
      )}
      <p className="scanner-ux5-next"><strong>다음 확인</strong> {view.next}</p>
    </section>
  );
}
