import { useEffect, useRef, useState } from "react";
import type { ScannerResponse, ScannerCandidate } from "../services/api";
import { compareScannerCandidates, type ScannerCandidateComparison } from "../services/prospectiveApi";
import { simpleConditionStatus } from "./scannerDecisionPresentation";
import "./scannerRankComparison.css";

type Props = { result: ScannerResponse };
const errors: Record<string, string> = {
  NOT_AVAILABLE_LEGACY: "이전에 저장한 분석에는 순위 비교 자료가 없어요. 없는 자료로 추측하지 않을게요.",
  RANK_EVIDENCE_MIGRATION_REQUIRED: "비교에 필요한 자료 저장 기능을 먼저 준비해야 해요.",
  RANK_EVIDENCE_STORE_UNAVAILABLE: "저장된 비교 자료를 읽지 못했어요.",
  EVIDENCE_HASH_MISMATCH: "비교 자료의 저장 상태를 확인하지 못했어요.",
  EVIDENCE_CONTEXT_MISMATCH: "두 종목의 분석 조건이 서로 맞지 않아 비교할 수 없어요.",
  RANK_ORDER_INCONSISTENT: "기록된 순서와 판단 자료가 달라 비교할 수 없어요.",
  CAPTURE_NOT_FINALIZED: "아직 분석이 완료되지 않았어요.",
  CAPTURE_NOT_FOUND: "이전에 저장된 분석을 찾지 못했어요.",
  SAMPLE_NOT_FOUND: "선택한 종목의 비교 자료가 없어요.",
  INVALID_COMPARISON_PAIR: "서로 다른 종목 두 개를 선택해 주세요.",
};

function simpleDifference(
  comparison: ScannerCandidateComparison,
  candidates: ScannerCandidate[],
): string {
  const field = comparison.decisive_field;
  const winner = comparison.winner_sample_index;
  if (winner == null || !candidates[winner]) return "실제 분석 기록을 비교한 결과예요.";
  const top = candidates[winner];
  const loserIndex = comparison.left?.sample_index === winner
    ? comparison.right?.sample_index
    : comparison.left?.sample_index;
  const other = loserIndex == null ? null : candidates[loserIndex];
  const a = top.name;
  const b = other?.name ?? "다른 종목";
  if (field === "tier_order") {
    return a + "를 먼저 보여주는 건 투자 조건의 전체 상태가 더 우선하기 때문이에요. " +
      a + ": " + simpleConditionStatus(top) + " / " +
      b + ": " + (other ? simpleConditionStatus(other) : "추가 확인이 필요해요") + ".";
  }
  if (field === "missing") return a + "가 아직 충족하지 못한 투자 조건이 더 적어서 먼저 보여줘요.";
  if (field === "risk_quality") return a + "의 위험 경고 수준이 상대적으로 낮아서 먼저 보여줘요.";
  if (field === "entry_gap_missing") return a + "는 가격 기준과의 차이를 확인할 수 있지만 " + b + "는 관련 자료가 부족해요.";
  if (field === "entry_gap_pct") return a + "가 분석 당시의 전략 가격 기준에 더 가까워서 먼저 보여줘요.";
  if (field === "negative_strategy_fit") return a + "가 현재 투자 조건에 더 잘 맞는 점수를 받았어요. 다만 매수 권유는 아니에요.";
  if (field === "tie_focus_order") return a + "와 " + b + "의 기본 조건이 같아, 기록된 차트 목표 기준으로 순서를 정했어요.";
  if (field === "code") return "실제 비교 조건이 같아 종목코드 순서로 보여줬어요. 어느 종목이 더 좋다는 뜻이 아니에요.";
  return "저장된 분석의 순서를 확인했어요. 자세한 계산 자료는 아래에서 볼 수 있어요.";
}

function candidateName(candidate: ScannerCandidate, index: number) {
  return (index + 1) + "번째 · " + candidate.name;
}

export default function ScannerRankComparison({ result }: Props) {
  const candidates = [...result.candidates, ...result.more_candidates];
  const [leftIndex, setLeftIndex] = useState(0);
  const [rightIndex, setRightIndex] = useState(1);
  const [opened, setOpened] = useState(false);
  const [state, setState] = useState<ScannerCandidateComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const requestSeq = useRef(0);
  const rawCapture = result.prospective_capture;
  const captureId = rawCapture?.canonical_capture_id || rawCapture?.capture_id || null;

  useEffect(() => {
    setLeftIndex(0);
    setRightIndex(1);
    setState(null);
    setError(null);
    setOpened(false);
    setPending(false);
    if (detailsRef.current) detailsRef.current.open = false;
    requestSeq.current += 1;
  }, [result, captureId]);

  useEffect(() => {
    const token = ++requestSeq.current;
    setState(null);
    setError(null);
    if (!opened || !captureId || leftIndex === rightIndex || leftIndex >= candidates.length || rightIndex >= candidates.length) {
      setPending(false);
      return;
    }
    setPending(true);
    void compareScannerCandidates(captureId, leftIndex, rightIndex)
      .then((value) => {
        if (requestSeq.current === token) setState(value);
      })
      .catch((reason: unknown) => {
        if (requestSeq.current === token) setError(reason instanceof Error ? reason.message : "비교 결과를 읽지 못했어요.");
      })
      .finally(() => {
        if (requestSeq.current === token) setPending(false);
      });
    return () => { requestSeq.current += 1; };
  }, [opened, captureId, leftIndex, rightIndex, result, candidates.length]);

  if (candidates.length < 2) return null;
  const unavailable = !captureId
    ? "이 분석에 저장된 비교 자료가 없어 순위 차이를 설명할 수 없어요."
    : leftIndex === rightIndex
      ? errors.INVALID_COMPARISON_PAIR
      : state && state.status !== "AVAILABLE"
        ? errors[state.status] ?? ("비교 자료를 확인할 수 없어요 (" + state.status + ").")
        : null;

  return (
    <details
      ref={detailsRef}
      className="scanner-rank-explain"
      onToggle={(event) => {
        if (event.currentTarget === event.target) setOpened(event.currentTarget.open);
      }}
    >
      <summary className="scanner-ux-rank-summary">
        두 종목이 왜 다른 순서로 나왔는지 비교해 보기
        <small>원하는 종목 두 개를 골라 이유를 알아볼 수 있어요.</small>
      </summary>
      {opened && (
        <>
          <div className="scanner-rank-explain-controls">
            <label>
              첫 번째 종목
              <select value={leftIndex} onChange={(event) => setLeftIndex(Number(event.target.value))}>
                {candidates.map((candidate, index) => (
                  <option key={index + "-" + candidate.market + "-" + candidate.code} value={index}>
                    {candidateName(candidate, index)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              두 번째 종목
              <select value={rightIndex} onChange={(event) => setRightIndex(Number(event.target.value))}>
                {candidates.map((candidate, index) => (
                  <option key={index + "-" + candidate.market + "-" + candidate.code} value={index}>
                    {candidateName(candidate, index)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="scanner-rank-explain-result" aria-live="polite">
            {pending ? <p role="status">두 종목의 분석 기록을 확인하고 있어요…</p>
              : error ? <p role="alert">{error}</p>
                : unavailable ? <p className="scanner-rank-explain-unavailable">{unavailable}</p>
                  : state?.status === "AVAILABLE" ? (
                    <>
                      <p className="scanner-rank-explain-decisive">
                        <strong>먼저 보여준 이유</strong>
                        {simpleDifference(state, candidates)}
                      </p>
                      <p className="scanner-rank-explain-note">종목을 살펴볼 순서의 차이이며, 지금 매수하거나 더 많이 오를 종목이라는 뜻은 아니에요.</p>
                      <details className="scanner-ux-rank-method">
                        <summary>비교한 계산 기준 자세히 보기</summary>
                        <div className="scanner-rank-explain-table-wrap">
                          <table className="scanner-rank-explain-table">
                            <thead>
                              <tr>
                                <th scope="col">분석 기준</th>
                                <th scope="col">{state.left?.name}</th>
                                <th scope="col">{state.right?.name}</th>
                                <th scope="col">설명</th>
                              </tr>
                            </thead>
                            <tbody>
                              {state.factors?.map((factor) => (
                                <tr key={factor.field} className={factor.decisive ? "decisive" : ""}>
                                  <th scope="row">{factor.label}</th>
                                  <td>{factor.left_value}</td>
                                  <td>{factor.right_value}</td>
                                  <td>{factor.decisive ? "순서가 갈린 기준" : factor.used_for_decision ? "같은 조건" : "참고 항목"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {state.limitations?.map((notice) => (
                          <p key={notice} className="scanner-rank-explain-note">{notice}</p>
                        ))}
                      </details>
                    </>
                  ) : null}
          </div>
        </>
      )}
    </details>
  );
}
