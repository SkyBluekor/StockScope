import { useEffect, useRef, useState } from "react";
import type { ScannerCandidate, ScannerResponse } from "../services/api";
import { getJevCandidateLocalCheck, type JevCandidateLocalCheck } from "../services/jevApi";
import type { JevMonitorItem } from "../services/jevApi";
import { scannerAiReviewStatus } from "./scannerAiReviewStatus";
import { scannerJevCapturedHorizonLabel, scannerJevDiagnosticStageLabel } from "./scannerJevHorizonCopy";

type Props = {
  candidate: ScannerCandidate;
  result: ScannerResponse;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  review: JevMonitorItem | null;
  loading: boolean;
  loadError: string | null;
  onRefresh: () => void;
  sampleIndex: number;
};

export default function ScannerAiReview({
  candidate, result, enabled, available, featureStatus,
  review, loading, loadError, onRefresh, sampleIndex,
}: Props) {
  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const items = review?.reason_codes.slice(0, 3) ?? [];
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;
  const [localCheck, setLocalCheck] = useState<JevCandidateLocalCheck | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [localLoading, setLocalLoading] = useState(false);
  const checkSeq = useRef(0);
  useEffect(() => {
    // Old candidate or capture response must never appear on a new selection.
    checkSeq.current += 1;
    setLocalCheck(null);
    setLocalError(null);
    setLocalLoading(false);
  }, [captureId, sampleIndex, candidate.code, candidate.market]);

  async function checkLocalCandidate(): Promise<void> {
    if (!captureId || localLoading) return;
    const seq = ++checkSeq.current;
    setLocalLoading(true);
    setLocalError(null);
    setLocalCheck(null);
    try {
      const reply = await getJevCandidateLocalCheck({
        captureId, sampleIndex, market: candidate.market, ticker: candidate.code,
      });
      if (seq !== checkSeq.current) return;
      if (reply.market !== candidate.market || reply.ticker !== candidate.code
        || reply.sample_index !== sampleIndex || reply.capture_id !== captureId
        || reply.review_kind !== "LOCAL_SEMANTIC_CHECK_NOT_JEV_MODEL"
        || reply.model_result_available !== false || reply.jev_model_calls !== 0
        || reply.provider_call_authorized !== false) {
        setLocalError("요청한 캡처·종목과 로컬 검토 근거가 일치하지 않습니다.");
        return;
      }
      setLocalCheck(reply);
    } catch {
      if (seq === checkSeq.current)
        setLocalError("로컬 검토 결과를 불러오지 못했어요. 저장된 분석 캡처를 확인하세요.");
    } finally {
      if (seq === checkSeq.current) setLocalLoading(false);
    }
  }

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
    <section className="scanner-jev-review" aria-label="선택 종목 AI 검토 근거">
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
      <section className="scanner-jev-local-check" aria-label="실제 후보 JEV 로컬 의미검사">
        <strong>이 종목의 전략 근거 직접 점검</strong>
        <p>현재 저장된 Scanner 캡처의 전략·조건 사이에서 의미 충돌이 있는지 확인해요.
          외부 JEV 모델에 데이터를 보내거나 비용을 청구하는 검토는 아닙니다.</p>
        <button type="button" onClick={() => void checkLocalCandidate()}
          disabled={!captureId || localLoading}>
          {localLoading ? "로컬 근거 확인 중…" : "이 후보의 로컬 의미검사 실행"}
        </button>
        {!captureId && <p role="status">검증 가능한 Scanner 캡처 ID가 없어 검사를 실행할 수 없어요.</p>}
        {localError && <p role="alert">{localError}</p>}
        {localCheck && <div role="status" data-local-review-state={localCheck.status}>
          <strong>{localCheck.headline}</strong>
          <p>{localCheck.explanation}</p>
          <p>검사 단계: {scannerJevDiagnosticStageLabel(localCheck.check_stage)}</p>
          {localCheck.horizon_diagnostic_status !== "NOT_CHECKED" && (
            <div className="scanner-jev-local-horizon">
              <strong>캡처에 저장된 투자 기간: {scannerJevCapturedHorizonLabel(localCheck.capture_horizon_intent)}</strong>
              <small>로컬 V4 의미검사 지원 범위는 SHORT·MEDIUM입니다.
                지원 범위와 실제 모델 호출 허가는 별개이며, 원본 투자 기간을 변경하지 않았습니다.</small>
            </div>
          )}
          {localCheck.status === "HOLD" && (
            <p>검사 보류 사유: {localCheck.reason_code ?? "근거 미확인"}</p>
          )}
          <p className="scanner-jev-local-next">{localCheck.next_action}</p>
          {localCheck.status === "LOCAL_CHECK_COMPLETE" && (
            <p>로컬 분류: {localCheck.local_semantic_status} ·
              {localCheck.provider_review_suggested_by_local_state
                ? " 외부 모델 추가 검토 대상일 수 있으나 호출 권한 미확인"
                : " 외부 모델 검토 대상 아님"}
            </p>
          )}
          <small>검토 종류: 로컬 V4 의미검사 · 실제 JEV 모델 호출 0회 ·
            기존 Scanner·Risk 판단 변경 없음</small>
        </div>}
      </section>
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
