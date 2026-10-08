import type { ScannerCandidate, ScannerResponse } from "../services/api";
import type { JevMonitorItem } from "../services/jevApi";

export type AiReviewState =
  | "OFF" | "FEATURE_PENDING" | "NOT_REQUESTED" | "INPUT_MISSING"
  | "QUEUED" | "RUNNING" | "COMPLETE" | "NEEDS_REVIEW" | "ABSTAIN"
  | "FAILED" | "UNKNOWN";

export type AiReviewDisplay = {
  state: AiReviewState;
  label: string;
  detail: string;
  outcome: string;
  next: string;
  source: "NONE" | "LOCAL" | "STORED_JEV";
};

type Args = {
  candidate: ScannerCandidate;
  result: ScannerResponse;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  review?: JevMonitorItem | null;
};

export function matchStoredJevReview(
  record: JevMonitorItem,
  candidate: ScannerCandidate,
  captureId: string | null,
  sampleIndex: number,
): boolean {
  return Boolean(captureId)
    && record.capture_id === captureId
    && record.sample_index === sampleIndex
    && record.market === candidate.market
    && record.ticker === candidate.code;
}

export function scannerAiReviewStatus({
  candidate, result, enabled, available, featureStatus, review,
}: Args): AiReviewDisplay {
  // A saved review is authoritative only for the exact capture + stock,
  // and only after the server's integrity and model-identity checks agree.
  if (review?.operational_status === "VALID") {
    if (review.review_id && review.completed_at
      && review.integrity_status === "MATCHED"
      && review.model_identity_status === "MATCHED") {
      if (review.disposition === "PASS_THROUGH") {
        return { state: "COMPLETE", label: "AI 검토 완료", detail: "저장된 검토에서 추가 주의사항이 발견되지 않았어요.", outcome: "기존 판단 유지", next: "검토한 근거와 시점을 확인하세요.", source: "STORED_JEV" };
      }
      if (review.disposition === "REVIEW_REQUIRED") {
        return { state: "NEEDS_REVIEW", label: "AI 검토 완료 · 추가 확인 필요", detail: "저장된 검토에 추가 확인 항목이 있어요.", outcome: "추가 주의사항 있음", next: "검토 결과에 연결된 확인 코드를 살펴보세요.", source: "STORED_JEV" };
      }
      if (review.disposition === "ABSTAIN") {
        return { state: "ABSTAIN", label: "AI 검토 완료 · 판단 보류", detail: "검토 결과만으로 의미를 확정하지 않았어요.", outcome: "판단 보류", next: "불확실성 사유와 입력 근거를 확인하세요.", source: "STORED_JEV" };
      }
    }
    return { state: "UNKNOWN", label: "AI 검토 결과 확인 필요", detail: "저장 결과의 일치성 또는 무결성을 확인할 수 없어요.", outcome: "판단 보류", next: "검토 근거가 일치하는지 확인하세요.", source: "NONE" };
  }
  if (review?.operational_status === "ERROR" || review?.operational_status === "LATE" || review?.operational_status === "INTERRUPTED") {
    return { state: "FAILED", label: "AI 검토 실패 · 결과 확인 필요", detail: "요청 기록이 있지만 유효한 검토 결과는 없어요.", outcome: "판단 보류", next: "기능 제공 상태를 확인한 후 다시 검토하세요.", source: "NONE" };
  }
  if (review?.operational_status === "PENDING" && review.review_id) {
    return { state: "QUEUED", label: "AI 검토 대기 중", detail: "실제 검토 요청이 대기 중이에요.", outcome: "결과 없음", next: "검토 처리가 끝난 뒤 다시 확인하세요.", source: "NONE" };
  }

  if (!enabled) {
    return { state: "OFF", label: "AI 검토 꺼짐", detail: "기본 Scanner 분석만 사용하고 있어요.", outcome: "AI 판단 없음", next: "AI 검토와 별개로 기본 분석 결과를 확인하세요.", source: "NONE" };
  }
  if (!available || featureStatus !== "ACTIVE") {
    return { state: "FEATURE_PENDING", label: "AI 검토 기능 준비 중", detail: "설정이 켜져 있어도 실제 Jev 검토 기능은 아직 제공되지 않아요.", outcome: "AI 판단 없음", next: "현재는 기본 분석과 로컬 의미 점검만 확인할 수 있어요.", source: "LOCAL" };
  }
  if (review?.operational_status === "RUNNING" || candidate.ai_review_presentation?.provider_status === "RUNNING") {
    return { state: "RUNNING", label: "AI 검토 중", detail: "실제 검토 요청을 처리하고 있어요.", outcome: "결과 없음", next: "검토 완료 후 결과를 확인하세요.", source: "NONE" };
  }
  if (candidate.ai_review_presentation?.state === "NOT_READY") {
    return { state: "INPUT_MISSING", label: "AI 검토 불가 · 입력 정보 부족", detail: candidate.ai_review_presentation.summary, outcome: "판단 보류", next: "의미 정보가 준비된 다음 검토할 수 있어요.", source: "LOCAL" };
  }
  if (result.execution_mode === "BASELINE_ONLY"
    || result.jev_review?.status === "NOT_REQUESTED"
    || candidate.ai_review_presentation?.provider_status === "NOT_REQUESTED"
    || !review || review.operational_status === "PENDING" || review.operational_status === "SKIPPED") {
    return { state: "NOT_REQUESTED", label: "AI 검토 미실행", detail: "로컬 의미 점검은 AI 모델 호출이나 완료 증거가 아니에요.", outcome: "AI 판단 없음", next: "기능이 제공되면 별도로 검토해야 해요.", source: "LOCAL" };
  }
  return { state: "UNKNOWN", label: "AI 검토 상태 확인 필요", detail: "현재 유효한 검토 결과를 확인하지 못했어요.", outcome: "판단 보류", next: "검토 기록을 다시 확인하세요.", source: "NONE" };
}

export function historicalReviewStatus(candidate: ScannerCandidate): string {
  const evidence = candidate.historical_evidence;
  if (evidence?.verified) return "과거 검증 완료 · 성과는 별도 참고";
  if (evidence?.unavailable_reason === "INSUFFICIENT_AVAILABLE_HISTORY" || evidence?.status === "DATA_UNAVAILABLE") {
    return "과거 검증 불가 · 데이터 부족";
  }
  return "과거 검증 미완료";
}
