import type { ScannerCandidate } from "../services/api";
import { assessPriceRule, priceReferenceText, wonText } from "./scannerDecisionPresentation";
import {
  quoteMatchesCandidate,
  scannerQuoteTruth,
  type ScannerQuoteSnapshot,
} from "./scannerQuoteTruth";

type Props = {
  candidate: ScannerCandidate;
  snapshot: ScannerQuoteSnapshot;
  onCheckPrice: () => void;
};

/**
 * Price view only: the quote is held by CandidateDetail across tab switches.
 * No quote can mutate candidate priority, Scanner verdict, or Risk.
 */
export default function ScannerPriceStatus({ candidate, snapshot, onCheckPrice }: Props) {
  const priceRule = candidate.entry_risk_guide?.price_rule;
  const baseline = assessPriceRule(priceRule, candidate.current_price);
  const truth = scannerQuoteTruth(candidate, snapshot);
  const quote = snapshot.quote && quoteMatchesCandidate(snapshot.quote, candidate)
    ? snapshot.quote : null;

  return (
    <section className="scanner-ux-price" aria-label="가격과 판단 근거 시점">
      <header className="scanner-ux-section-heading">
        <div>
          <span className="scanner-ux-eyebrow">가격 확인 · 판단 시점 구분</span>
          <h4>분석일 가격과 새 시세</h4>
        </div>
      </header>
      <div className="scanner-ux-price-grid">
        <div>
          <small>분석 당시 종가 · {candidate.data_date || "기준일 확인 필요"}</small>
          <strong>{wonText(candidate.current_price)}</strong>
          <p>{baseline.label} · 분석일 기준</p>
        </div>
        <div>
          <small>분석일 전략 참고 가격</small>
          <strong>{priceReferenceText(priceRule)}</strong>
          <p>당시 전략의 가격 기준이며 새 시세에 맞춰 재계산한 가격은 아니에요.</p>
        </div>
      </div>
      <div className="scanner-ux-price-live">
        <div>
          <strong>새로운 시세 확인</strong>
          <p>선택한 종목만 수동 조회합니다. 조회 후에도 현재 전략과 위험은 재검증 전이에요.</p>
        </div>
        <button type="button" onClick={onCheckPrice} disabled={snapshot.loading}>
          {snapshot.loading ? "시세 확인 중…" : quote ? "시세 다시 확인" : "새 시세 확인"}
        </button>
      </div>
      {snapshot.error && <p role="alert" className="scanner-ux-price-warning">{snapshot.error}</p>}
      {truth.state === "ERROR" && !snapshot.error && (
        <p role="alert" className="scanner-ux-price-warning">{truth.stateLabel}</p>
      )}
      {quote && !snapshot.loading && !snapshot.error && (
        <div className="scanner-ux-quote-result" role="status">
          <div className="scanner-ux-quote-head">
            <span>조회 당시 시세</span>
            <strong>{truth.priceLabel}</strong>
          </div>
          <p>{truth.marketLabel}</p>
          <small>{truth.freshnessLabel}</small>
          <p className="scanner-ux-price-assessment">
            {truth.assessment?.message ?? "조회 가격으로는 참고 조건을 확인할 수 없어요."}
          </p>
          <p className="scanner-ux-disclaimer">
            현재 전략·위험: 재검증 전. 가격만 분석 당시 기준과 비교했으며 실제 매수 가능 상태가 아니에요.
          </p>
        </div>
      )}
      {!quote && !snapshot.loading && !snapshot.error && (
        <p className="scanner-ux-price-empty">새 시세 미확인 · 현재 진입 여부는 결정되지 않았어요.</p>
      )}
    </section>
  );
}
