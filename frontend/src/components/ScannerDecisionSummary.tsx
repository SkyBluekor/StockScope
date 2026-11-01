import type { ScannerCandidate, ScannerResponse } from "../services/api";
import { beginnerCandidatePresentation, scannerEntryGuidance } from "./scannerDecisionPresentation";
import { scannerQuoteTruth, type ScannerQuoteSnapshot } from "./scannerQuoteTruth";

type Props = {
  candidate: ScannerCandidate;
  marketContext: ScannerResponse["market_summary"][number] | null;
  quoteSnapshot: ScannerQuoteSnapshot;
  onOpenPriceTab: () => void;
};

export default function ScannerDecisionSummary({ candidate, marketContext, quoteSnapshot, onOpenPriceTab }: Props) {
  const view = beginnerCandidatePresentation(candidate);
  const entry = scannerEntryGuidance(candidate, marketContext);
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
      <div className="scanner-entry-guidance" data-scanner-entry-guidance={entry.state} role="status">
        <span className="scanner-ux-eyebrow">신규 진입 판단 · 분석일 기준 (현재 매수 허가 아님)</span>
        <h4>{entry.headline}</h4>
        <p>{entry.explanation}</p>
      </div>
      <p className="scanner-ux2-decision-why">
        <strong>종목 전략 조건</strong>
        <span>{view.headline} {view.why}</span>
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
      <section aria-label="분석일 시장 위험" className="scanner-ux2-decision-why">
        <strong>시장 위험 · 분석일 기준</strong>
        {marketContext?.risk_reference_status === "DECLINE_RECHECK" ? (
          <span>
            {candidate.market === "KOSDAQ" ? "코스닥" : "코스피"} 지수가
            {" "}{marketContext.index_change_rate_pct?.toFixed(2)}% 하락·약세 신호를 보였습니다.
            종목 자체의 전략 조건과 별개로 진입 전 시장 상황을 다시 확인하세요.
            이 경고만으로 기존 Scanner의 진입 판정이나 순위를 바꾸지는 않았습니다.
            {" "}({marketContext.index_data_date ?? candidate.data_date} · KRX 확정 일별)
          </span>
        ) : marketContext?.risk_reference_status === "REFERENCE_ONLY" ? (
          <span>
            {candidate.market === "KOSDAQ" ? "코스닥" : "코스피"} 지수
            {" "}{marketContext.index_change_rate_pct != null ? marketContext.index_change_rate_pct.toFixed(2) + "%" : "변동률 확인 필요"}.
            기존 지수 규칙에서 하락 주의 신호는 없지만 다른 위험이 없다는 뜻은 아닙니다.
            {" "}({marketContext.index_data_date ?? candidate.data_date} · KRX 확정 일별)
          </span>
        ) : (
          <span>
            분석일과 일치하는 KRX 지수 변동률을 확인하지 못했습니다.
            시장이 안전하다는 뜻이 아니며, 현재 전략 판단과 별도로 확인해야 합니다.
          </span>
        )}
      </section>
      <p className="scanner-ux6-validation">
        미국 금리·국제 사건·공시 참고자료는 현재 Scanner의 전략 점수와 진입 차단에 자동 반영되지 않았습니다.
      </p>
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
        {entry.state === "MARKET_RECHECK"
          ? "시장 하락 위험과 최신 시세·전략을 재확인한 뒤 신규 진입을 판단하세요."
          : entry.state === "MARKET_UNKNOWN" && !keepAsOfNextStep
            ? "해당 분석일의 시장 근거와 최신 시세·위험을 확인하세요."
          : keepAsOfNextStep ? view.next
          : quote.state === "NOT_CHECKED" ? "전략·가격 탭에서 새 시세를 확인한 뒤 전략·위험을 재검증하세요."
          : quote.state === "CHECKING" ? "시세 확인 중입니다. 분석일 판단만 참고하세요."
            : quote.state === "ERROR" ? "새 시세를 다시 확인한 뒤 전략·위험을 검증하세요."
              : quote.nextStep}
      </p>
    </section>
  );
}
