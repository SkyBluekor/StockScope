import type { ScannerCandidate, ScannerResponse } from "../services/api";
import type { HoldingStock } from "../services/holdingsApi";
import { scannerPositionBoundary } from "./scannerPositionBoundary";

type Props = {
  candidate: ScannerCandidate;
  result: Pick<ScannerResponse, "market_summary">;
  managedStock: HoldingStock | null;
  holdingsLoading: boolean;
  holdingsReady: boolean;
  onOpenHoldings?: () => void;
};

export default function ScannerPositionBoundaryCard(props: Props) {
  const view = scannerPositionBoundary(
    props.candidate, props.result, props.managedStock,
    props.holdingsLoading, props.holdingsReady,
  );
  const canNavigate = Boolean(props.onOpenHoldings)
    && (view.state === "LOCAL_POSITION_RECORDED" || view.state === "LOCAL_WATCH_ONLY");
  return (
    <section className="scanner-position-boundary" aria-label="신규 진입과 내 보유 기록 구분">
      <header className="scanner-position-boundary-head">
        <strong>신규 진입 후보 ≠ 보유종목 대응</strong>
        <span>{view.headline}</span>
      </header>
      <p>{view.explanation}</p>
      {view.state === "LOCAL_POSITION_RECORDED" && (
        <p>
          <strong>로컬 OPEN 기록 {view.openPositionCount}개</strong>
          {view.positionAccounts.length > 0 && " · " + view.positionAccounts.join(", ")}
          <small>증권사 실잔고·현재 체결 상태를 검증한 숫자는 아니에요.</small>
        </p>
      )}
      <p className="scanner-position-boundary-market">
        <strong>{view.marketContext.label}</strong>
        <span> · 기준일 {view.marketContext.analysisDate}</span>
      </p>
      <p>{view.marketContext.caution}</p>
      <p className="scanner-position-boundary-next">{view.nextAction}</p>
      {canNavigate && (
        <button type="button" onClick={props.onOpenHoldings}>
          Holdings에서 보유 판단 확인 →
        </button>
      )}
      <small>Scanner의 Risk 무효화 참고가격은 실제 보유 포지션에 적용된 손절 주문·계획 가격이 아닙니다.</small>
    </section>
  );
}
