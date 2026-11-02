import { useEffect, useRef, useState } from "react";
import {
  executeOwnedJevReview, getOwnedJevLatest, previewOwnedJevReview,
  type OwnedJevInput, type OwnedJevPreview, type OwnedJevResult,
} from "../services/jevApi";

type Props = {
  captureId: string | null;
  sampleIndex: number;
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  onStoredReview: (record: OwnedJevResult | null) => void;
};

export function ownedReviewStatus(review: OwnedJevResult | null) {
  if (!review) return null;
  if (review.status === "PENDING_OR_INTERRUPTED") return "호출 상태 미확인 · 자동 재시도 안 함";
  if (review.status === "ERROR") return "실제 JEV 요청 실패";
  if (review.status !== "VALID") return "검토 요청 중";
  if (review.disposition === "REVIEW_REQUIRED") return "사용자 작성 내용: 의미 충돌 확인 필요";
  if (review.disposition === "PASS_THROUGH") return "사용자 작성 내용: 명시적 충돌 낮음";
  return "사용자 작성 내용: 판단 보류";
}

/** No automatic model requests. User supplies both text fields and approves one paid call. */
export default function ScannerOwnedReviewB({
  captureId, sampleIndex, market, ticker, onStoredReview,
}: Props) {
  const [requiredCondition, setRequiredCondition] = useState("");
  const [observedMeaning, setObservedMeaning] = useState("");
  const [attested, setAttested] = useState(false);
  const [preview, setPreview] = useState<OwnedJevPreview | null>(null);
  const [stored, setStored] = useState<OwnedJevResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const onResultRef = useRef(onStoredReview);
  onResultRef.current = onStoredReview;

  useEffect(() => {
    let active = true;
    setRequiredCondition("");
    setObservedMeaning("");
    setAttested(false);
    setPreview(null);
    setStored(null);
    setBusy(false);
    setError(null);
    onResultRef.current(null);
    if (captureId && sampleIndex >= 0) {
      void getOwnedJevLatest({
        capture_id: captureId, sample_index: sampleIndex, market, ticker,
      }).then(reply => {
        if (active) {
          setStored(reply.review);
          onResultRef.current(reply.review);
        }
      }).catch(() => {
        if (active) setError("이 종목의 이전 JEV 기록을 확인할 수 없습니다.");
      });
    }
    return () => { active = false; };
  }, [captureId, sampleIndex, market, ticker]);

  const input: OwnedJevInput | null = captureId && sampleIndex >= 0
    ? {
      capture_id: captureId, sample_index: sampleIndex, market, ticker,
      required_condition: requiredCondition, observed_meaning: observedMeaning,
    } : null;

  const change = (value: string, kind: "condition" | "observation") => {
    if (kind === "condition") setRequiredCondition(value);
    else setObservedMeaning(value);
    setPreview(null);
    setError(null);
  };
  const prepare = async () => {
    if (!input || busy) return;
    setBusy(true);
    setPreview(null);
    setError(null);
    try {
      const result = await previewOwnedJevReview(input);
      setPreview(result);
      if (result.existing) {
        setStored(result.existing);
        onResultRef.current(result.existing);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "JEV 입력 확인 실패");
    } finally {
      setBusy(false);
    }
  };
  const execute = async () => {
    if (!input || !preview?.ready || !attested || busy || preview.existing) return;
    const accepted = window.confirm(
      "TypeSafe JEV에 아래 직접 작성한 두 문장을 전송하여 유료 API를 정확히 한 번 호출합니다.\n" +
      "모델: " + preview.model_requested + "\n" +
      "입력 해시: " + preview.input_sha256.slice(0, 16) + "…\n" +
      "정확한 요금은 호출 전에 확인할 수 없습니다.\n" +
      "시세·공시·뉴스·Scanner 원본은 전송하지 않습니다.\n\n" +
      "정말 실행하시겠습니까?",
    );
    if (!accepted) return;
    setBusy(true);
    setError(null);
    try {
      const reply = await executeOwnedJevReview(input, preview);
      setStored(reply);
      onResultRef.current(reply);
      setPreview(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "JEV 요청 실패 · 재시도 전에 저장 결과 확인 필요");
      // Do not retry automatically: provider billing may already have occurred.
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="scanner-jev-b-details" data-jev-owned-b="true">
      <summary>내가 작성한 조건으로 JEV 제2 의견 받기</summary>
      <div className="scanner-jev-b-body">
        <p className="scanner-jev-compact-note">
          선택 종목에 연결된 <b>내 문장 2개의 의미 충돌만</b> 확인합니다.
          실제 종목의 시세·공시·전망을 JEV가 확인하는 기능은 아닙니다.
        </p>
        {!captureId || sampleIndex < 0 ? (
          <p>저장된 Scanner 정본 캡처가 없어 이 종목에 검토 결과를 연결할 수 없습니다.</p>
        ) : (
          <>
            <label>
              반드시 지켜야 할 투자 조건 (직접 작성)
              <textarea rows={2} maxLength={500} value={requiredCondition}
                onChange={e => change(e.target.value, "condition")}
                placeholder="예: 내가 세운 조건은 손절 기준을 명확히 정한 뒤에만 진입하는 것이다." />
            </label>
            <label>
              내가 직접 관찰하거나 판단한 상황
              <textarea rows={2} maxLength={500} value={observedMeaning}
                onChange={e => change(e.target.value, "observation")}
                placeholder="예: 아직 손절할 가격을 정하지 않았지만 지금 진입하려고 한다." />
            </label>
            <small className="scanner-jev-compact-note">
              뉴스·공시·외부 자료의 원문이나 가격 데이터는 붙여 넣지 마세요.
              실제 호출 금액은 확인 전이므로 비용을 사전 확정할 수 없습니다.
            </small>
            <button type="button" onClick={() => void prepare()}
              disabled={busy || requiredCondition.trim().length < 16 ||
                observedMeaning.trim().length < 16}>
              {busy ? "확인 중…" : "전송 내용 미리 확인 (무료)"}
            </button>
            {preview && (
              <div className="scanner-jev-b-preview" data-jev-owned-preview="true">
                <p>검토 입력: 직접 작성한 두 문장만 / 모델 {preview.model_requested}</p>
                <small>입력 해시 {preview.input_sha256.slice(0, 16)}… · 호출 비용 미확정</small>
                {preview.existing ? (
                  <p>이미 검토한 요청입니다. 재호출하지 않습니다.</p>
                ) : preview.ready ? (
                  <>
                    <label className="scanner-jev-b-check">
                      <input type="checkbox" checked={attested}
                        onChange={e => setAttested(e.target.checked)} />
                      두 문장은 내가 직접 작성했으며, 외부 원천 자료를 포함하지 않고 유료 1회 전송에 동의합니다.
                    </label>
                    <button type="button" onClick={() => void execute()}
                      disabled={!attested || busy}>
                      {busy ? "JEV 검토 요청 중…" : "유료 JEV 1회 승인 및 실행"}
                    </button>
                  </>
                ) : (
                  <p>서버에서 실제 JEV 실행이 준비되지 않았습니다. ({preview.reason})</p>
                )}
              </div>
            )}
          </>
        )}
        {stored && (
          <p data-jev-owned-result="true">
            {ownedReviewStatus(stored)} · {stored.model_returned || "모델 결과 미확인"}
            {stored.completed_at ? " · " + stored.completed_at : ""}
            {stored.cost_usd != null ? " · $" + stored.cost_usd : " · 비용 미확정"}
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </div>
    </details>
  );
}
