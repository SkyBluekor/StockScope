import { useEffect, useMemo, useState } from "react";
import {
  closeHoldingRecovery,
  getHoldingRecovery,
  recordHoldingRecoveryAssessment,
  startHoldingRecovery,
  HoldingsApiError,
  type HoldingPosition,
  type HoldingRecoveryAction,
  type HoldingRecoveryContext,
  type HoldingRecoveryThesisState,
} from "../services/holdingsApi";

type Props = {
  positions: HoldingPosition[];
  sourceKey: string;
};

const thesisOptions: Array<{
  value: HoldingRecoveryThesisState;
  label: string;
  detail: string;
}> = [
  { value: "INTACT", label: "기존 투자 이유가 아직 유효함", detail: "핵심 전제가 유지된다고 봅니다." },
  { value: "WEAKENED", label: "일부 전제가 약해짐", detail: "논리는 남아 있지만 위험 요인이 커졌습니다." },
  { value: "BROKEN", label: "핵심 전제가 무너짐", detail: "처음 보유한 이유를 더 이상 유지하기 어렵습니다." },
  { value: "UNKNOWN", label: "현재 자료로 판단하기 어려움", detail: "확인되지 않은 부분을 억지로 결론내리지 않습니다." },
];

const actionOptions: Array<{
  value: HoldingRecoveryAction;
  label: string;
  detail: string;
}> = [
  { value: "UNDECIDED", label: "아직 결정하지 않음", detail: "추가 근거를 확인한 뒤 방향을 정합니다." },
  { value: "HOLD", label: "현재 계획 유지 검토", detail: "기존 관리 계획을 그대로 둘지 검토합니다." },
  { value: "REDUCE", label: "일부 축소 검토", detail: "비중을 줄이는 선택지를 검토합니다." },
  { value: "EXIT", label: "전량 정리 검토", detail: "포지션 종료 선택지를 검토합니다." },
  { value: "ADD_REVIEW", label: "조건부 추가매수 검토", detail: "검토 의도만 기록하며 매수 신호·수량은 만들지 않습니다." },
];

function money(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(number)}원`;
}

function pct(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function currentAssessment(context: HoldingRecoveryContext) {
  const reviewId = context.open_review?.review_id;
  if (!reviewId) return null;
  const history = context.review_history.find((item) => item.review.review_id === reviewId);
  if (!history || history.assessments.length === 0) return null;
  return history.assessments[history.assessments.length - 1];
}

function scrollToDecision() {
  document.querySelector<HTMLElement>(".holding-decision-panel")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

export default function HoldingRecoveryPanel({ positions, sourceKey }: Props) {
  const openPositions = useMemo(
    () => positions.filter((position) => position.status === "OPEN"),
    [positions],
  );
  const [contexts, setContexts] = useState<Record<string, HoldingRecoveryContext>>({});
  const [migrationRequired, setMigrationRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyPositionId, setBusyPositionId] = useState<string | null>(null);
  const [thesisByPosition, setThesisByPosition] = useState<Record<string, HoldingRecoveryThesisState>>({});
  const [actionByPosition, setActionByPosition] = useState<Record<string, HoldingRecoveryAction>>({});
  const [reasonByPosition, setReasonByPosition] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(signal?: AbortSignal) {
    if (openPositions.length === 0) {
      setContexts({});
      setLoading(false);
      return;
    }
    setError(null);
    try {
      const rows = await Promise.all(
        openPositions.map(async (position) => {
          const context = await getHoldingRecovery(position.position_id, { signal });
          return [position.position_id, context] as const;
        }),
      );
      const next = Object.fromEntries(rows);
      setContexts(next);
      setMigrationRequired(false);

      const thesis: Record<string, HoldingRecoveryThesisState> = {};
      const actions: Record<string, HoldingRecoveryAction> = {};
      const reasons: Record<string, string> = {};
      for (const [positionId, context] of rows) {
        const latest = currentAssessment(context);
        thesis[positionId] = latest?.thesis_state ?? "UNKNOWN";
        actions[positionId] = latest?.review_action ?? "UNDECIDED";
        reasons[positionId] = latest?.reason_note ?? "";
      }
      setThesisByPosition(thesis);
      setActionByPosition(actions);
      setReasonByPosition(reasons);
    } catch (loadError) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      if (
        loadError instanceof HoldingsApiError
        && loadError.code === "HOLD_RECOVERY_MIGRATION_REQUIRED"
      ) {
        setMigrationRequired(true);
        setContexts({});
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Recovery 검토 정보를 불러오지 못했습니다.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setMessage(null);
    setMigrationRequired(false);
    void load(controller.signal);
    return () => controller.abort();
  }, [sourceKey, openPositions.map((item) => item.position_id).join("|")]);

  async function start(positionId: string) {
    setBusyPositionId(positionId);
    setMessage(null);
    setError(null);
    try {
      const result = await startHoldingRecovery(
        positionId,
        "보유 이유와 현재 위험을 별도 Recovery 문맥에서 재검토",
      );
      setContexts((current) => ({ ...current, [positionId]: result.context }));
      setThesisByPosition((current) => ({ ...current, [positionId]: "UNKNOWN" }));
      setActionByPosition((current) => ({ ...current, [positionId]: "UNDECIDED" }));
      setReasonByPosition((current) => ({ ...current, [positionId]: "" }));
      setMessage(
        result.created
          ? "Recovery 검토를 시작했습니다. Position·관리 계획·거래 원장은 변경하지 않았습니다."
          : "이미 진행 중인 Recovery 검토를 계속합니다.",
      );
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Recovery 검토를 시작하지 못했습니다.");
    } finally {
      setBusyPositionId(null);
    }
  }

  async function save(positionId: string) {
    const context = contexts[positionId];
    const review = context?.open_review;
    if (!context || !review) return;
    setBusyPositionId(positionId);
    setMessage(null);
    setError(null);
    try {
      const result = await recordHoldingRecoveryAssessment(review.review_id, {
        thesis_state: thesisByPosition[positionId] ?? "UNKNOWN",
        review_action: actionByPosition[positionId] ?? "UNDECIDED",
        reason_note: reasonByPosition[positionId]?.trim() || null,
        linked_decision_id: context.current.latest_decision?.decision_id ?? null,
      });
      setContexts((current) => ({ ...current, [positionId]: result.context }));
      setThesisByPosition((current) => ({
        ...current,
        [positionId]: result.assessment.thesis_state,
      }));
      setActionByPosition((current) => ({
        ...current,
        [positionId]: result.assessment.review_action,
      }));
      setReasonByPosition((current) => ({
        ...current,
        [positionId]: result.assessment.reason_note ?? "",
      }));
      setMessage("현재 근거와 선택 이유를 Recovery 기록에 남겼습니다. 실제 주문이나 계획 변경은 발생하지 않았습니다.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Recovery 검토 내용을 저장하지 못했습니다.");
    } finally {
      setBusyPositionId(null);
    }
  }

  async function close(positionId: string) {
    const context = contexts[positionId];
    const review = context?.open_review;
    if (!review) return;
    setBusyPositionId(positionId);
    setMessage(null);
    setError(null);
    try {
      const result = await closeHoldingRecovery(review.review_id, {
        reason: "MANUAL_REVIEW_COMPLETED",
        note: "사용자가 Recovery 검토를 명시적으로 종료",
      });
      setContexts((current) => ({ ...current, [positionId]: result.context }));
      setMessage("Recovery 검토를 종료했습니다. 가격 변화만으로 자동 종료되지는 않습니다.");
    } catch (closeError) {
      setError(closeError instanceof Error ? closeError.message : "Recovery 검토를 종료하지 못했습니다.");
    } finally {
      setBusyPositionId(null);
    }
  }

  if (openPositions.length === 0) return null;

  if (migrationRequired) {
    return (
      <section className="holding-recovery-panel migration-required" aria-label="손실 포지션 재검토">
        <div className="holding-recovery-heading">
          <span>RECOVERY REVIEW</span>
          <h3>Recovery 기록 저장소 준비가 필요합니다.</h3>
          <p>기존 Position과 관리 계획은 그대로 유지됩니다. P3-S2 migration 이후부터 수동 재검토 기록을 사용할 수 있습니다.</p>
        </div>
        <code>python tools/data/migrate_holdings_recovery_vnp3s2.py</code>
      </section>
    );
  }

  return (
    <section className="holding-recovery-panel" aria-label="손실 포지션 재검토">
      <div className="holding-recovery-heading">
        <span>RECOVERY REVIEW</span>
        <h3>손실이 커졌을 때, 본전이 아니라 보유 이유와 위험을 다시 봅니다.</h3>
        <p>자동 물타기·자동 손절·회복 확률을 만들지 않습니다. 사용자가 명시적으로 시작하고 종료하는 검토 기록입니다.</p>
      </div>

      {loading && <div className="holding-recovery-message">Recovery 기록을 확인하는 중입니다.</div>}
      {message && <div className="holding-recovery-message success">{message}</div>}
      {error && <div className="holding-recovery-message error">{error}</div>}

      {!loading && openPositions.map((position) => {
        const context = contexts[position.position_id];
        if (!context) return null;
        const busy = busyPositionId === position.position_id;
        const review = context.open_review;
        const performance = context.current.performance;
        const currentPlan = context.current.active_plan;
        const latest = currentAssessment(context);

        return (
          <article className="holding-recovery-position" key={position.position_id}>
            <div className="holding-recovery-summary">
              <div>
                <span>{position.account_name || position.provider || "보유 기록"}</span>
                <strong>{performance?.unrealized_return_pct != null ? pct(performance.unrealized_return_pct) : "손익 계산 확인 필요"}</strong>
                <small>{performance?.unrealized_pnl != null ? `평가손익 ${money(performance.unrealized_pnl)}` : "확정 EOD 평가손익을 확인할 수 없습니다."}</small>
              </div>
              <div>
                <span>현재 관리 기준</span>
                <strong>{currentPlan ? `Plan v${currentPlan.version}` : "적용 계획 없음"}</strong>
                <small>{context.current.valuation.market_date ? `${context.current.valuation.market_date.replace(/-/g, ".")} 확정 EOD` : "평가 기준일 없음"}</small>
              </div>
            </div>

            {!review ? (
              <div className="holding-recovery-start">
                <div>
                  <strong>별도 재검토 기록은 아직 시작하지 않았습니다.</strong>
                  <p>손실률 임계값으로 자동 시작하지 않습니다. 필요하다고 판단할 때 직접 시작하세요.</p>
                </div>
                <button
                  type="button"
                  className="holdings-secondary-button"
                  disabled={busy}
                  onClick={() => void start(position.position_id)}
                >
                  {busy ? "시작 중…" : "손실 포지션 재검토"}
                </button>
              </div>
            ) : (
              <>
                <div className="holding-recovery-status">
                  <span>재검토 진행 중 · {review.opened_at.slice(0, 10).replace(/-/g, ".")} 시작</span>
                  {latest && <small>최근 기록 {latest.created_at.slice(0, 10).replace(/-/g, ".")}</small>}
                </div>

                <fieldset className="holding-recovery-fieldset">
                  <legend>투자 논리</legend>
                  {thesisOptions.map((option) => (
                    <label key={option.value} className="holding-recovery-choice">
                      <input
                        type="radio"
                        name={`recovery-thesis-${position.position_id}`}
                        value={option.value}
                        checked={(thesisByPosition[position.position_id] ?? "UNKNOWN") === option.value}
                        onChange={() => setThesisByPosition((current) => ({ ...current, [position.position_id]: option.value }))}
                      />
                      <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                    </label>
                  ))}
                </fieldset>

                <fieldset className="holding-recovery-fieldset">
                  <legend>현재 검토 방향</legend>
                  {actionOptions.map((option) => (
                    <label key={option.value} className="holding-recovery-choice">
                      <input
                        type="radio"
                        name={`recovery-action-${position.position_id}`}
                        value={option.value}
                        checked={(actionByPosition[position.position_id] ?? "UNDECIDED") === option.value}
                        onChange={() => setActionByPosition((current) => ({ ...current, [position.position_id]: option.value }))}
                      />
                      <span><strong>{option.label}</strong><small>{option.detail}</small></span>
                    </label>
                  ))}
                </fieldset>

                {(actionByPosition[position.position_id] ?? "UNDECIDED") === "ADD_REVIEW" && (
                  <div className="holding-recovery-warning">
                    추가매수 정책은 아직 검증되지 않았습니다. 이 선택은 검토 의도만 기록하며 매수 신호·금액·수량을 만들지 않습니다.
                  </div>
                )}

                <label className="holding-recovery-reason">
                  <span>선택 이유</span>
                  <textarea
                    rows={3}
                    maxLength={2000}
                    value={reasonByPosition[position.position_id] ?? ""}
                    placeholder="지금 이 방향을 검토하는 핵심 이유를 짧게 남겨두세요."
                    onChange={(event) => setReasonByPosition((current) => ({ ...current, [position.position_id]: event.target.value }))}
                  />
                </label>

                <div className="holding-recovery-actions">
                  <button
                    type="button"
                    className="holdings-primary-button"
                    disabled={busy}
                    onClick={() => void save(position.position_id)}
                  >
                    {busy ? "저장 중…" : "검토 내용 기록"}
                  </button>
                  <button type="button" className="holdings-secondary-button" onClick={scrollToDecision}>
                    현재 보유 판단 보기
                  </button>
                  <button
                    type="button"
                    className="holdings-secondary-button"
                    disabled={busy}
                    onClick={() => void close(position.position_id)}
                  >
                    Recovery 검토 종료
                  </button>
                </div>

                {context.review_history.some((item) => item.assessments.length > 0) && (
                  <details className="holding-recovery-details">
                    <summary>이전 Recovery 기록</summary>
                    <div className="holding-recovery-history">
                      {context.review_history.flatMap((item) =>
                        item.assessments.map((assessment) => (
                          <div className="holding-recovery-history-row" key={assessment.assessment_id}>
                            <span>{assessment.created_at.slice(0, 10).replace(/-/g, ".")}</span>
                            <strong>
                              {thesisOptions.find((option) => option.value === assessment.thesis_state)?.label
                                ?? assessment.thesis_state}
                            </strong>
                            <span>
                              {actionOptions.find((option) => option.value === assessment.review_action)?.label
                                ?? assessment.review_action}
                            </span>
                            <p>{assessment.reason_note || "이유 기록 없음"}</p>
                          </div>
                        )),
                      )}
                    </div>
                  </details>
                )}

                <details className="holding-recovery-details">
                  <summary>현재 근거 · 제한사항</summary>
                  <div className="holding-recovery-evidence">
                    <span>Analysis</span><strong>{context.current.analysis ? `revision ${context.current.analysis.revision_no}` : "없음"}</strong>
                    <span>최근 보유 판단</span><strong>{context.current.latest_decision ? (context.current.latest_decision.stale ? "STALE" : context.current.latest_decision.status) : "없음"}</strong>
                    <span>전체 자산 비중</span><strong>확정하지 않음</strong>
                    <span>기업·공시 근거</span><strong>자동 충분성 판정 안 함</strong>
                  </div>
                  {context.current.limitations.length > 0 && (
                    <ul>
                      {context.current.limitations.map((item) => {
                        const text = ({
                          VALUATION_NOT_AVAILABLE: "확정 EOD 평가가격을 사용할 수 없습니다.",
                          ANALYSIS_NOT_AVAILABLE: "최신 분석이 없습니다.",
                          ACTIVE_PLAN_NOT_AVAILABLE: "현재 적용 중인 관리 계획이 없습니다.",
                          HOLDING_DECISION_NOT_AVAILABLE: "저장된 최신 보유 판단이 없습니다.",
                          HOLDING_DECISION_STALE: "최근 보유 판단이 현재 상태와 달라 다시 판단해야 합니다.",
                          POSITION_PNL_NOT_AVAILABLE: "현재 평가손익을 계산할 수 없습니다.",
                          ACCOUNT_TOTAL_EXPOSURE_NOT_PROVEN: "전체 현금·계좌·자산 범위를 알 수 없어 전체 자산 대비 비중을 확정하지 않습니다.",
                          COMPANY_EVIDENCE_NOT_CONNECTED: "기업·공시 근거는 아직 Recovery 판단 근거로 연결하지 않았습니다.",
                        } as Record<string, string>)[item] ?? item;
                        return <li key={item}>{text}</li>;
                      })}
                    </ul>
                  )}
                </details>
              </>
            )}
          </article>
        );
      })}
    </section>
  );
}
