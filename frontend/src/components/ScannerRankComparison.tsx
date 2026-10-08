import { useEffect, useRef, useState } from "react";
import type { ScannerResponse, ScannerCandidate } from "../services/api";
import {
  compareScannerCandidates,
  type ScannerCandidateComparison,
} from "../services/prospectiveApi";
import "./scannerRankComparison.css";

type Props = { result: ScannerResponse };
const errors: Record<string, string> = {
  NOT_AVAILABLE_LEGACY: "이 분석에는 저장된 순위 근거가 없습니다. 과거 결과를 임의로 다시 계산하지 않습니다.",
  RANK_EVIDENCE_MIGRATION_REQUIRED: "순위 근거 저장 구조 준비가 필요합니다.",
  RANK_EVIDENCE_STORE_UNAVAILABLE: "저장된 순위 근거를 읽을 수 없습니다.",
  EVIDENCE_HASH_MISMATCH: "순위 근거 또는 후보 스냅샷의 무결성 검증에 실패했습니다.",
  EVIDENCE_CONTEXT_MISMATCH: "이 분석의 후보·정책·데이터 기준이 보존된 순위 근거와 일치하지 않습니다.",
  RANK_ORDER_INCONSISTENT: "순위와 정렬 근거가 일치하지 않아 비교할 수 없습니다.",
  CAPTURE_NOT_FINALIZED: "아직 확정되지 않은 Scanner 분석입니다.",
  CAPTURE_NOT_FOUND: "해당 Scanner 캡처가 현재 DB에 없습니다.",
  SAMPLE_NOT_FOUND: "해당 후보의 캡처 기록이 없습니다.",
  INVALID_COMPARISON_PAIR: "서로 다른 후보 두 개를 선택해 주세요.",
};

function candidateName(candidate: ScannerCandidate, index: number) {
  return (index + 1) + "위 · " + candidate.name + " (" + candidate.code + ")";
}

export default function ScannerRankComparison({ result }: Props) {
  const candidates = [...result.candidates, ...result.more_candidates];
  const [leftIndex, setLeftIndex] = useState(0);
  const [rightIndex, setRightIndex] = useState(1);
  const [state, setState] = useState<ScannerCandidateComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const requestSeq = useRef(0);
  const rawCapture = result.prospective_capture;
  const captureId = rawCapture?.canonical_capture_id || rawCapture?.capture_id || null;

  useEffect(() => {
    setLeftIndex(0);
    setRightIndex(1);
    setState(null);
    setError(null);
    setPending(false);
    requestSeq.current += 1;
  }, [result, captureId]);

  useEffect(() => {
    const token = ++requestSeq.current;
    setState(null);
    setError(null);
    if (!captureId || leftIndex === rightIndex || leftIndex >= candidates.length || rightIndex >= candidates.length) {
      setPending(false);
      return;
    }
    setPending(true);
    void compareScannerCandidates(captureId, leftIndex, rightIndex)
      .then((value) => {
        if (requestSeq.current !== token) return;
        setState(value);
      })
      .catch((e: unknown) => {
        if (requestSeq.current !== token) return;
        setError(e instanceof Error ? e.message : "비교 결과를 확인하지 못했습니다.");
      })
      .finally(() => {
        if (requestSeq.current === token) setPending(false);
      });
    return () => { requestSeq.current += 1; };
    // The immutable completed result is shared by the Scanner session.
  }, [captureId, leftIndex, rightIndex, result, candidates.length]);

  if (candidates.length < 2) return null;
  const unavailable = !captureId
    ? "이 Scanner 결과에는 저장된 캡처 ID가 없어 순위 근거를 비교할 수 없습니다."
    : leftIndex === rightIndex
      ? errors.INVALID_COMPARISON_PAIR
      : state && state.status !== "AVAILABLE"
        ? errors[state.status] ?? ("비교 근거가 준비되지 않았습니다 (" + state.status + ").")
        : null;

  return (
    <section className="scanner-rank-explain" aria-label="후보 순위 차이">
      <div className="scanner-rank-explain-heading">
        <div>
          <span className="scanner-rank-explain-kicker">순위가 갈린 이유</span>
          <h3>두 후보의 판단 기준 비교</h3>
        </div>
        <small>실제 Scanner 정렬 근거 · AI 호출 없음</small>
      </div>
      <div className="scanner-rank-explain-controls">
        <label>
          첫 번째 후보
          <select value={leftIndex} onChange={(e) => setLeftIndex(Number(e.target.value))}>
            {candidates.map((candidate, index) => (
              <option key={index + "-" + candidate.market + "-" + candidate.code} value={index}>
                {candidateName(candidate, index)}
              </option>
            ))}
          </select>
        </label>
        <label>
          두 번째 후보
          <select value={rightIndex} onChange={(e) => setRightIndex(Number(e.target.value))}>
            {candidates.map((candidate, index) => (
              <option key={index + "-" + candidate.market + "-" + candidate.code} value={index}>
                {candidateName(candidate, index)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="scanner-rank-explain-result" aria-live="polite">
        {pending ? <p role="status">저장된 판단 근거 확인 중…</p>
          : error ? <p role="alert">{error}</p>
            : unavailable ? <p className="scanner-rank-explain-unavailable">{unavailable}</p>
              : state?.status === "AVAILABLE" ? (
                <>
                  <p className="scanner-rank-explain-decisive">
                    <strong>{state.left?.final_rank}위와 {state.right?.final_rank}위의 결정적 차이</strong>
                    {state.decisive_reason}
                  </p>
                  <div className="scanner-rank-explain-table-wrap">
                    <table className="scanner-rank-explain-table">
                      <thead>
                        <tr>
                          <th scope="col">정렬 요소</th>
                          <th scope="col">{state.left?.name}</th>
                          <th scope="col">{state.right?.name}</th>
                          <th scope="col">해석</th>
                        </tr>
                      </thead>
                      <tbody>
                        {state.factors?.map((factor) => (
                          <tr key={factor.field} className={factor.decisive ? "decisive" : ""}>
                            <th scope="row">{factor.label}</th>
                            <td>{factor.left_value}</td>
                            <td>{factor.right_value}</td>
                            <td>{factor.decisive ? "순위 결정" : factor.used_for_decision ? "앞선 기준 동일" : "후속 참고"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {state.limitations?.map((notice) => <p key={notice} className="scanner-rank-explain-note">{notice}</p>)}
                </>
              ) : null}
      </div>
    </section>
  );
}
