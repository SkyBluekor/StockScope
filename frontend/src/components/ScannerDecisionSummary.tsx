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
        <strong>어디까지 충족했나요?</strong>
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
      <div className="scanner-ux-decision-facts scanner-ux2-facts">
        <div>
          <strong>위험·가격 확인</strong>
          <p>{view.caution}</p>
        </div>
        <div>
          <strong>지금 확인할 일</strong>
          <p>{view.next}</p>
        </div>
      </div>
    </section>
  );
}
