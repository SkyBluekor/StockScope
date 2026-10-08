import { useEffect, useState } from "react";
import type { ScannerCandidate, ScannerResponse } from "../services/api";
import { getJevReviews, type JevMonitorItem } from "../services/jevApi";
import {
  matchStoredJevReview, scannerAiReviewStatus,
} from "./scannerAiReviewStatus";

type Props = {
  candidate: ScannerCandidate;
  result: ScannerResponse;
  sampleIndex: number;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
};

export default function ScannerAiReview({
  candidate, result, sampleIndex, enabled, available, featureStatus,
}: Props) {
  const [review, setReview] = useState<JevMonitorItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;

  useEffect(() => {
    let active = true;
    setReview(null);
    setLoadError(null);
    if (!enabled || !available || featureStatus !== "ACTIVE" || !captureId) {
      setLoading(false);
      return () => { active = false; };
    }
    setLoading(true);
    void getJevReviews(captureId)
      .then((response) => {
        if (!active) return;
        if (!response.available || response.capture_id !== captureId) {
          setLoadError("저장된 검토 자료를 확인할 수 없어요.");
          return;
        }
        const matched = response.items.filter(item =>
          matchStoredJevReview(item, candidate, captureId, sampleIndex),
        );
        const valid = matched.find(item => item.operational_status === "VALID") ?? matched[0] ?? null;
        setReview(valid);
      })
      .catch(() => {
        if (active) setLoadError("저장된 AI 검토 결과를 읽지 못했어요.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [captureId, candidate.code, candidate.market, sampleIndex, enabled, available, featureStatus, refresh]);

  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const items = review?.reason_codes.slice(0, 3) ?? [];
  return (
    <section className="scanner-jev-review" aria-label="선택 종목 AI 검토 근거">
      <header>
        <small>기본 분석과 별개의 AI 검토</small>
        <strong>{loading ? "저장된 AI 검토 확인 중" : state.label}</strong>
      </header>
      <p>{loading ? "이 종목과 분석 시점에 연결된 저장 기록만 확인하고 있어요." : state.detail}</p>
      <dl>
        <div><dt>검토 결과</dt><dd>{loading ? "확인 중" : state.outcome}</dd></div>
        <div><dt>검토 출처</dt><dd>{state.source === "STORED_JEV" ? "검증된 Jev 저장 결과" : state.source === "LOCAL" ? "로컬 의미 점검 · 모델 미실행" : "유효한 모델 결과 없음"}</dd></div>
        <div><dt>기본 분석</dt><dd>유지 · Scanner 순위와 Risk 계산은 변경하지 않음</dd></div>
        <div><dt>분석 기준</dt><dd>{candidate.data_date || "확인 필요"} · {candidate.market} {candidate.code}</dd></div>
        {review?.completed_at && state.source === "STORED_JEV" && (
          <div><dt>검토 저장 시점</dt><dd>{review.completed_at}</dd></div>
        )}
      </dl>
      {state.source === "STORED_JEV" && (
        <>
          <strong>추가 확인 항목</strong>
          {items.length > 0
            ? <ul>{items.map(code => <li key={code}>{code}</li>)}</ul>
            : <p>저장된 결과에 별도 확인 항목 코드가 없어요.</p>}
          <small>확인 코드는 저장된 결과를 그대로 보여줍니다. 코드에 없는 이유를 만들어 설명하지 않아요.</small>
          <p>연결 근거: 분석 캡처 {captureId} · 검토 기록 {review?.review_id}</p>
        </>
      )}
      {state.source !== "STORED_JEV" && candidate.ai_review_presentation && (
        <details>
          <summary>로컬 의미 점검 결과 보기 (Jev 호출 아님)</summary>
          <p>{candidate.ai_review_presentation.summary}</p>
          {[...candidate.ai_review_presentation.strengths, ...candidate.ai_review_presentation.review_points].slice(0, 3).map((text, index) => <p key={index}>{text}</p>)}
        </details>
      )}
      <p className="scanner-jev-next">{loadError || state.next}</p>
      {available && enabled && featureStatus === "ACTIVE" && (
        <button type="button" onClick={() => setRefresh(x => x + 1)} disabled={loading}>
          {loading ? "기록 확인 중…" : "저장된 검토 다시 확인"}
        </button>
      )}
      <small>이 화면은 기존 저장 결과만 조회하며 새로운 Jev 모델 호출을 실행하지 않습니다.</small>
    </section>
  );
}
