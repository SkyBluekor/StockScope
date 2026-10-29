import { useEffect, useState } from "react";
import type { ScannerCandidate, ScannerResponse } from "../services/api";
import { getJevLocalReadiness, type JevLocalReadiness, type JevMonitorItem } from "../services/jevApi";
import { scannerAiReviewStatus } from "./scannerAiReviewStatus";

type Props = {
  candidate: ScannerCandidate;
  result: ScannerResponse;
  sampleIndex: number;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  review: JevMonitorItem | null;
  loading: boolean;
  loadError: string | null;
  onRefresh: () => void;
};

export default function ScannerAiReview({
  candidate, result, sampleIndex, enabled, available, featureStatus,
  review, loading, loadError, onRefresh,
}: Props) {
  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const items = review?.reason_codes.slice(0, 3) ?? [];
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;
  const [readiness, setReadiness] = useState<JevLocalReadiness | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setReadiness(null);
    setReadinessError(null);
    if (!captureId || sampleIndex < 1) {
      setReadinessLoading(false);
      return () => { active = false; };
    }
    setReadinessLoading(true);
    void getJevLocalReadiness(captureId, sampleIndex)
      .then(value => {
        if (!active) return;
        if (value.capture_id !== captureId || value.sample_index !== sampleIndex
            || value.identity.market !== candidate.market
            || value.identity.ticker !== candidate.code) {
          setReadinessError("저장 캡처와 선택 종목의 식별 정보가 다릅니다. 다른 후보 결과를 표시하지 않습니다.");
          return;
        }
        setReadiness(value);
      })
      .catch(() => { if (active) setReadinessError("로컬 준비도를 확인하지 못했습니다. 저장 캡처와 DB 상태를 확인하세요."); })
      .finally(() => { if (active) setReadinessLoading(false); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const readinessLabel: Record<string, string> = {
    LOCAL_READY: "로컬 V4 입력 준비",
    LOCAL_ONLY: "로컬 검토만 가능",
    NEEDS_EVIDENCE: "입력 근거 확인 필요",
    SOURCE_RIGHTS_HOLD: "외부 전송 권한 확인 전까지 보류",
    NOT_ENTRY_CANDIDATE: "진입 후보가 아닌 참고 항목",
  };
  const reasonLabel: Record<string, string> = {
    SOURCE_RIGHTS_UNVERIFIED: "실제 데이터 외부 제공 권한이 확인되지 않았습니다.",
    SOURCE_RELEASE_TIME_UNVERIFIED: "원천 데이터의 최초 공개 시점이 검증되지 않았습니다.",
    SOURCE_ORIGIN_UNVERIFIED: "실제 데이터 원천을 확정하지 못했습니다.",
    REVISION_ASOF_UNPROVEN: "당시 사용한 원천 데이터 버전을 입증하지 못했습니다.",
    TYPESAFE_ACCOUNT_POLICY_UNVERIFIED: "수신자 계정의 처리·보관 조건이 확인되지 않았습니다.",
    OUTBOUND_BODY_NOT_APPROVED: "전송할 실제 요청 본문은 승인되지 않았습니다.",
    NOT_ENTRY_CANDIDATE: "기존 Scanner의 진입 후보가 아닙니다.",
    S7_4_LINEAGE_NOT_COMPLETE: "기초 데이터의 출처 연결이 충분하지 않습니다.",
  };
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
      <div className="scanner-jev-local-readiness" role="status" data-local-readiness={readiness?.status ?? "UNAVAILABLE"}>
        <strong>이 후보의 JEV 실행 준비도 · 로컬 읽기 전용</strong>
        {!captureId ? <p>확정된 COMPLETE 저장 캡처가 없어 후보별 준비도를 확인할 수 없습니다.</p>
          : readinessLoading ? <p>저장된 후보의 근거와 권한 상태를 확인 중입니다.</p>
            : readinessError ? <p>{readinessError}</p>
              : readiness ? (
                <>
                  <p><b>{readinessLabel[readiness.status] ?? readiness.status}</b> · {readinessLabel[readiness.local_readiness] ?? readiness.local_readiness}</p>
                  <p>실제 TypeSafe 전송: 금지 ({readiness.transmission_decision}) · 이 조회에서 모델 요청 0회</p>
                  <details>
                    <summary>미실행 사유와 검사 근거</summary>
                    <p>V4 상태: {readiness.local_v4_status} · 출처 연결: {readiness.lineage_analysis_status}</p>
                    <p>원천 공개 시각: {readiness.publication_time_status} · 사용 권한: {readiness.rights_status}</p>
                    {readiness.reason_codes.length > 0
                      ? <ul>{readiness.reason_codes.slice(0, 8).map(code => <li key={code}>{reasonLabel[code] ?? code} ({code})</li>)}</ul>
                      : <p>추가 사유 코드가 없습니다.</p>}
                    <small>캡처 해시: {readiness.identity.snapshot_hash}</small>
                  </details>
                </>
              ) : <p>로컬 준비도 결과 없음</p>}
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
