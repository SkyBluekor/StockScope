import type { ScannerCandidate } from "../services/api";
import type { ScannerQuoteSnapshot } from "./scannerQuoteTruth";
import { wonText } from "./scannerDecisionPresentation";
import { scannerPriorRiskRecheck } from "./scannerPriorRiskRecheck";

type Props = {
  candidate: ScannerCandidate;
  snapshot: ScannerQuoteSnapshot;
  onOpenPriceTab?: () => void;
};

/** Display-only: never promotes an old Scanner READY or initiates network calls. */
export default function ScannerPriorRiskCard({
  candidate, snapshot, onOpenPriceTab,
}: Props) {
  const check = scannerPriorRiskRecheck(candidate, snapshot);
  const warning = check.state === "OLD_REFERENCE_BREACHED"
    || check.indicativeOldReferenceComparison === "AT_OR_BELOW";
  const detail = check.quotePrice == null
    ? "조회 가격 없음"
    : "조회 가격 " + wonText(check.quotePrice);
  return (
    <section
      className={"scanner-prior-risk" + (warning ? " scanner-prior-risk-breach" : "")}
      aria-label="분석일 위험 참고선 재확인"
      role="status"
    >
      <div className="scanner-prior-risk-heading">
        <strong>분석일 Risk 참고선 · {check.label}</strong>
        <small>분석일 {check.analysisDate ?? "미확인"} · Risk {check.originalRiskStatus ?? "미확인"}</small>
      </div>
      <p>{check.explanation}</p>
      <div className="scanner-prior-risk-facts">
        <span>기존 무효화 참고선 · {wonText(check.originalInvalidationReference)}</span>
        <span>{detail}</span>
      </div>
      {check.quoteReceivedAt && (
        <small>
          시세 근거: {check.quoteSourceLabel} · 서버 수신 {check.quoteReceivedAt}
          {check.quoteProvidedAt
            ? " · 제공자 시각 " + check.quoteProvidedAt
            : " · 실제 가격 제공 시각 확인 불가"}
        </small>
      )}
      {check.quotePrice != null && (
        <small>{check.marketSessionLabel}</small>
      )}
      {check.state === "RECEIVED_TIME_ONLY" && (
        <small>수신 시각은 거래·체결 시각이 아닙니다. 현재가나 확정 위험 경보로 사용하지 마세요.</small>
      )}
      {check.state === "QUOTE_TOO_OLD" && (
        <small>이 결과는 오래된 가격입니다. 자동 갱신되지 않습니다.</small>
      )}
      <p className="scanner-prior-risk-next">{check.nextStep}</p>
      {onOpenPriceTab && (
        <button type="button" onClick={onOpenPriceTab}>전략·가격에서 시세 확인 →</button>
      )}
      <small>실시간 위험 경고·손절 체결·보유 상태를 확인한 결과가 아니며, 기존 후보 순위도 변경하지 않아요.</small>
    </section>
  );
}
