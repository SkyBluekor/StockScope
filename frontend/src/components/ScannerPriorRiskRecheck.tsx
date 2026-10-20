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
export default function ScannerPriorRiskRecheck({
  candidate, snapshot, onOpenPriceTab,
}: Props) {
  const check = scannerPriorRiskRecheck(candidate, snapshot);
  const warning = check.state === "OLD_REFERENCE_BREACHED";
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
        <strong>기존 READY 유효성 · {check.label}</strong>
        <small>분석일 {check.analysisDate ?? "미확인"} · Risk {check.originalRiskStatus ?? "미확인"}</small>
      </div>
      <p>{check.explanation}</p>
      <div className="scanner-prior-risk-facts">
        <span>기존 무효화 참고선 · {wonText(check.originalInvalidationReference)}</span>
        <span>{detail}</span>
      </div>
      {check.quoteProvidedAt && (
        <small>시세 근거: {check.quoteSourceLabel} · 제공 {check.quoteProvidedAt}</small>
      )}
      <p className="scanner-prior-risk-next">{check.nextStep}</p>
      {onOpenPriceTab && (
        <button type="button" onClick={onOpenPriceTab}>전략·가격에서 시세 확인 →</button>
      )}
      <small>실시간 위험 경고·손절 체결·보유 상태를 확인한 결과가 아니며, 기존 후보 순위도 변경하지 않아요.</small>
    </section>
  );
}
