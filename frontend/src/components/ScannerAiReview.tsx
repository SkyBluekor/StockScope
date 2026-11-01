import { useState } from "react";
import ScannerOwnedReviewB, { ownedReviewStatus } from "./ScannerOwnedReviewB";
import type { OwnedJevResult } from "../services/jevApi";
import type { ScannerCandidate, ScannerResponse } from "../services/api";
import type { JevMonitorItem } from "../services/jevApi";
import { scannerAiReviewStatus } from "./scannerAiReviewStatus";

type Props = {
  candidate: ScannerCandidate;
  sampleIndex: number;
  result: ScannerResponse;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  review: JevMonitorItem | null;
  loading: boolean;
  loadError: string | null;
  onRefresh: () => void;
};

function ScannerAiDiagnostics({
  candidate, result, enabled, available, featureStatus,
  review, loading, loadError, onRefresh,
}: Props) {
  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const items = review?.reason_codes.slice(0, 3) ?? [];
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;
  const verifiedModel = state.source === "STORED_JEV";
  const modelRunning = state.state === "RUNNING"
    && review?.operational_status === "RUNNING" && Boolean(review?.review_id);
  const tone = verifiedModel ? "verified" : modelRunning ? "working"
    : state.state === "FAILED" || state.state === "FEATURE_ERROR" ? "error"
      : state.state === "INPUT_MISSING" || state.state === "ABSTAIN" ? "review" : "idle";
  const sourceSummary = verifiedModel ? "저장된 실제 AI 검토"
    : modelRunning ? "실제 AI 검토 실행 중"
      : candidate.ai_review_presentation?.state === "LOCAL_COMPLETE"
        ? "기본 근거 확인 완료 · AI 모델 미실행"
        : "기본 분석과 별개의 AI 검토";
  return (
    <section className="scanner-jev-review" aria-label="JEV 상세 검토 기록">
      <div className={"scanner-jev-motion-status " + tone + (modelRunning ? " is-running" : "")} data-review-state={state.state} role="status">
        <span className="scanner-jev-motion-icon" aria-hidden="true">{verifiedModel ? "✓" : modelRunning ? "·" : "i"}</span>
        <div>
          <small>{sourceSummary}</small>
          <strong>{loading ? "저장된 검토 확인 중" : loadError ? "AI 검토 기록 확인 실패" : state.label}</strong>
          <p>{loading ? "종목과 분석 시점에 연결된 검토 기록을 확인하고 있어요." : loadError ?? state.detail}</p>
        </div>
      </div>
      <details className="scanner-jev-motion-details">
        <summary>검토 출처와 근거 자세히 보기</summary>
        <dl>
        <div><dt>검토 결과</dt><dd>{loading || loadError ? "확인할 수 없음" : state.outcome}</dd></div>
        <div><dt>검토 출처</dt><dd>{!loading && !loadError && state.source === "STORED_JEV" ? "검증된 Jev 저장 결과" : state.source === "LOCAL" ? "로컬 의미 점검 · 모델 미실행" : "유효한 모델 결과 없음"}</dd></div>
        <div><dt>기본 분석</dt><dd>유지 · Scanner 순위와 Risk 계산은 변경하지 않음</dd></div>
        <div><dt>분석 기준</dt><dd>{candidate.data_date || "확인 필요"} · {candidate.market} {candidate.code}</dd></div>
        {!loading && !loadError && review?.completed_at && state.source === "STORED_JEV" && (
          <div><dt>검토 저장 시점</dt><dd>{review.completed_at}</dd></div>
        )}
        </dl>
      </details>
      {!loading && !loadError && state.source === "STORED_JEV" && (
        <>
          <strong>추가 확인 항목 · 최대 3개</strong>
          {items.length > 0 ? <ul>{items.map(code => <li key={code}>{code}</li>)}</ul>
            : <p>저장된 검토에 별도의 추가 확인 코드가 없어요.</p>}
          <small>검토 코드는 응답에 저장된 값이며, 코드에 없는 원인을 추측하지 않아요.</small>
          <p>연결 근거: 분석 캡처 {captureId} · 검토 기록 {review?.review_id}</p>
        </>
      )}
      {state.source !== "STORED_JEV" && candidate.ai_review_presentation && (
        <details>
          <summary>로컬 의미 점검 보기 (Jev 호출 아님)</summary>
          <p>{candidate.ai_review_presentation.summary}</p>
          {[...candidate.ai_review_presentation.strengths, ...candidate.ai_review_presentation.review_points].slice(0, 3).map((text, index) => <p key={index}>{text}</p>)}
        </details>
      )}
      <p className="scanner-jev-next">{loadError ? "저장된 검토 조회 상태를 확인한 후 다시 시도하세요." : state.next}</p>
      {available && enabled && featureStatus === "ACTIVE" && (
        <button type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "기록 확인 중…" : "저장된 검토 다시 확인"}
        </button>
      )}
      <small>새로운 Jev 모델 호출은 실행하지 않습니다.</small>
    </section>
  );
}

/**
 * Plan A: show the actual Scanner verdict and JEV state without technical
 * reports by default. The existing detailed review stays intact behind a
 * disclosure and is mounted only when explicitly opened by the user.
 *
 * No model request or change to the original Scanner decision is made here.
 */
export default function ScannerAiReview(props: Props) {
  const { candidate, result, enabled, available, featureStatus, review,
    loading, loadError, onRefresh, sampleIndex } = props;
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [ownedReview, setOwnedReview] = useState<OwnedJevResult | null>(null);
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;
  const linkedOwned = ownedReview
    && ownedReview.selected_stock.ticker === candidate.code
    && ownedReview.selected_stock.market === candidate.market
    && ownedReview.selected_stock.sample_index === sampleIndex
    && ownedReview.selected_stock.capture_id === captureId
    ? ownedReview : null;
  const manualStatus = ownedReviewStatus(linkedOwned);

  const state = scannerAiReviewStatus({
    candidate, result, enabled, available, featureStatus, review,
  });
  const verified = !loading && !loadError && state.source === "STORED_JEV";
  const active = verified || state.state === "RUNNING" || state.state === "QUEUED";
  const status = manualStatus || (loading ? "검토 기록 확인 중"
    : loadError ? "검토 기록 조회 실패"
    : verified ? (
      state.state === "NEEDS_REVIEW" ? "추가 확인 필요"
      : state.state === "ABSTAIN" ? "판단 보류"
      : "검토 완료"
    )
    : state.state === "RUNNING" ? "검토 진행 중"
    : state.state === "QUEUED" ? "검토 대기 중"
    : state.state === "FEATURE_PENDING" ? "현재 사용 불가"
    : state.state === "FEATURE_LOADING" ? "서버 상태 확인 중"
    : state.state === "FEATURE_ERROR" ? "서버 상태 확인 실패"
    : state.state === "OFF" ? "사용 안 함"
    : state.state === "FAILED" ? "검토 실패"
    : state.state === "INPUT_MISSING" ? "검토 입력 부족"
    : state.state === "UNKNOWN" ? "결과 확인 필요"
    : "아직 실행되지 않음");
  return (
    <section className="scanner-jev-review scanner-jev-compact" aria-label="선택 종목 AI 검토 근거"
      data-jev-primary-summary="true">
      <strong className="scanner-jev-compact-name">
        {candidate.name || candidate.code} ({candidate.code})
      </strong>
      <dl className="scanner-jev-compact-facts">
        <div><dt>Scanner 판단</dt><dd>{candidate.action_label || candidate.action}</dd></div>
        <div><dt>JEV 검토</dt><dd data-jev-primary-status={state.state}>{status}</dd></div>
        {verified && review?.completed_at && (
          <div><dt>검토 시각</dt><dd>{review.completed_at}</dd></div>
        )}
      </dl>
      {verified && review?.reason_codes && review.reason_codes.length > 0 && (
        <p className="scanner-jev-compact-note">
          확인 항목: {review.reason_codes.slice(0, 3).join(", ")}
        </p>
      )}
      {candidate.market === "KOSPI" || candidate.market === "KOSDAQ" ? (
        <ScannerOwnedReviewB
          key={[captureId, sampleIndex, candidate.market, candidate.code].join(":")}
          captureId={captureId}
          sampleIndex={sampleIndex}
          market={candidate.market}
          ticker={candidate.code}
          onStoredReview={setOwnedReview}
        />
      ) : (
        <p>해당 시장의 실제 종목 식별을 확인할 수 없습니다.</p>
      )}
      {verified && available && enabled && featureStatus === "ACTIVE" && (
        <button type="button" onClick={onRefresh} disabled={loading}>
          저장된 결과 새로고침
        </button>
      )}
      {!linkedOwned && !active && (
        <small className="scanner-jev-compact-note">
          기존 V4 자동 검토는 비활성 상태입니다. 위 수동 검토는 직접 작성한 문장만 사용합니다.
        </small>
      )}
      <details className="scanner-jev-compact-details"
        onToggle={event => { if (event.target === event.currentTarget) setDetailsOpen(event.currentTarget.open); }}>
        <summary>검토 근거·개발자 진단</summary>
        {detailsOpen && <ScannerAiDiagnostics {...props} />}
      </details>
    </section>
  );
}
