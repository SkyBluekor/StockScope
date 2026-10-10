import type { ScannerCandidate } from "../services/api";
import { beginnerCandidatePresentation } from "./scannerDecisionPresentation";
import { scannerQuoteTruth, type ScannerQuoteSnapshot } from "./scannerQuoteTruth";

type Props = {
  candidate: ScannerCandidate;
  quoteSnapshot: ScannerQuoteSnapshot;
  onOpenPriceTab: () => void;
};

export default function ScannerDecisionSummary({ candidate, quoteSnapshot, onOpenPriceTab }: Props) {
  const view = beginnerCandidatePresentation(candidate);
  const quote = scannerQuoteTruth(candidate, quoteSnapshot);
  const quoteAvailable = quoteSnapshot.quote !== null && !quoteSnapshot.loading
    && !quoteSnapshot.error && quote.state !== "ERROR";
  const keepAsOfNextStep = candidate.risk.warning
    || candidate.priority?.tier === "RISK_HOLD"
    || candidate.entry_risk_guide?.action.status === "RISK_BLOCKED"
    || candidate.action === "NO_TRADE"
    || candidate.priority?.tier === "LOW_PRIORITY"
    || candidate.conditions.missing > 0;
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
      <section className="scanner-ux6-quote" aria-label="분석일 판정과 새 시세">
        <div className="scanner-ux6-quote-top">
          <strong>새 시세와 기존 참고 조건</strong>
          <button type="button" onClick={onOpenPriceTab}>전략·가격에서 확인 →</button>
        </div>
        <div className="scanner-ux6-quote-values">
          <span>{quote.stateLabel}</span>
          <strong>{quoteAvailable ? quote.priceLabel : "새 가격 없음"}</strong>
        </div>
        {quoteAvailable && <small>{quote.freshnessLabel} · {quote.marketLabel}</small>}
        <p className="scanner-ux6-validation">현재 전략·위험: 재검증 전 · 분석일 후보 순위는 변경되지 않았어요.</p>
      </section>
      <p className="scanner-ux5-next">
        <strong>다음 확인</strong>
        {keepAsOfNextStep ? view.next
          : quote.state === "NOT_CHECKED" ? "전략·가격 탭에서 새 시세를 확인한 뒤 전략·위험을 재검증하세요."
          : quote.state === "CHECKING" ? "시세 확인 중입니다. 분석일 판단만 참고하세요."
            : quote.state === "ERROR" ? "새 시세를 다시 확인한 뒤 전략·위험을 검증하세요."
              : quote.nextStep}
      </p>
    </section>
  );
}
