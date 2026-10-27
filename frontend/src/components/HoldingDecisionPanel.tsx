import { useMemo, useState } from "react";
import {
  applyHoldingDecisionPlan,
  evaluateHoldingDecision,
  resolveHoldingDecision,
  type HoldingDecisionAction,
  type HoldingDecisionRecord,
  type HoldingDecisionSupportResponse,
  type HoldingPosition,
  type HoldingManagementResponse,
  type HoldingWorkspaceSourceStatus,
} from "../services/holdingsApi";
import { holdingPlanReview, type HoldingPlanReview } from "./holdingPlanReview";

type Props = {
  positions: HoldingPosition[];
  data: HoldingDecisionSupportResponse | null;
  management: HoldingManagementResponse | null;
  status?: HoldingWorkspaceSourceStatus;
  loading?: boolean;
  onContextChanged?: () => Promise<void> | void;
  onPlanChanged?: () => Promise<void> | void;
};

const actionLabel: Record<string, string> = {
  HOLD: "현재 계획 유지",
  ADD: "추가매수",
  REDUCE: "일부 축소",
  TAKE_PROFIT: "이익 실현",
  STOP: "손절 기준 대응",
  EXIT: "전량 종료 검토",
};

function dateText(value: string | null | undefined) {
  if (!value) return "-";
  return value.slice(0, 10).replace(/-/g, ".");
}

function money(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(number)}원`;
}

function hasLimitation(decision: HoldingDecisionRecord, code: string) {
  return decision.limitations.some((item) => item.code === code);
}

function decisionNeedText(decision: HoldingDecisionRecord) {
  if (hasLimitation(decision, "ANALYSIS_UNAVAILABLE")) {
    return {
      title: "최신 분석이 필요합니다.",
      summary: "확정 EOD 가격은 있지만 이 보유분에 연결할 최신 분석이 없습니다. 종목 분석을 갱신한 뒤 현재 판단을 다시 확인하세요.",
    };
  }
  if (hasLimitation(decision, "VALUATION_UNAVAILABLE")) {
    return {
      title: "확정 EOD 가격을 확인할 수 없습니다.",
      summary: "가격을 임의로 추정하지 않습니다. 확정 시장 데이터가 준비된 뒤 현재 판단을 다시 확인하세요.",
    };
  }
  if (
    decision.source_analysis_revision_id
    && decision.source_active_plan_id == null
    && decision.evidence.new_plan_horizon_activatable === false
  ) {
    return {
      title: "첫 관리 계획을 아직 적용할 수 없습니다.",
      summary: "최신 분석은 있지만 현재 Horizon 정책이 계획 적용 단계까지 승인되지 않았습니다. 기존 보유 원장은 그대로 유지됩니다.",
    };
  }
  if (
    decision.source_analysis_revision_id
    && decision.source_active_plan_id == null
  ) {
    return {
      title: "첫 관리 계획을 검토하세요.",
      summary: "최신 분석은 준비됐지만 아직 이 보유분에 적용한 손절·목표 계획이 없습니다. 계획을 적용하기 전까지 기존 원장은 바뀌지 않습니다.",
    };
  }
  return null;
}

function statusTitle(decision: HoldingDecisionRecord) {
  const effective = decision.effective_status ?? (decision.stale ? "STALE" : decision.status);
  if (effective === "STALE") return "보유 상태가 바뀌어 다시 판단해야 합니다.";
  const need = decisionNeedText(decision);
  if (need) return need.title;
  if (decision.status === "INSUFFICIENT_DATA") return "아직 판단할 자료가 충분하지 않습니다.";
  if (decision.status === "CONFLICT") return "새 분석과 현재 계획이 충돌합니다.";
  if (decision.status === "DEFERRED") return "현재 판단을 보류합니다.";
  if (decision.primary_action === "STOP") return "손절 기준을 확인할 시점입니다.";
  if (decision.primary_action === "TAKE_PROFIT") return "목표 구간에 도달해 이익 실현을 검토합니다.";
  if (decision.primary_action === "HOLD") return "현재 적용 계획을 유지할 수 있습니다.";
  return "보유 선택지를 검토하세요.";
}

function statusSummary(decision: HoldingDecisionRecord) {
  if (decision.stale) {
    if (decision.stale_reasons?.length === 1 && decision.stale_reasons[0] === "ACTIVE_PLAN_CHANGED") {
      return "이 판단이 참조한 활성 관리 계획이 현재 계획과 다릅니다. 기존 계획을 확인하고 판단만 다시 생성하세요.";
    }
    return "수량·평단·분석·적용 계획·확정 EOD 중 하나가 판단 생성 이후 바뀌었습니다.";
  }
  const need = decisionNeedText(decision);
  if (need) return need.summary;
  if (decision.status === "CONFLICT") {
    return "새 분석을 그대로 적용하면 기존 위험 기준을 느슨하게 만들 수 있어 자동 적용을 차단했습니다.";
  }
  if (decision.status === "INSUFFICIENT_DATA") {
    return "자료 부족을 HOLD로 바꾸지 않습니다. 최신 확정 EOD와 분석 근거를 확인한 뒤 다시 판단합니다.";
  }
  if (decision.primary_action === "STOP") {
    return "현재 확정 EOD가 이미 적용 중인 손절 가격 이하입니다. StockScope는 주문을 실행하지 않습니다.";
  }
  if (decision.primary_action === "TAKE_PROFIT") {
    return "현재 적용 계획의 목표 가격에 도달했습니다. 일부/전량 실현 여부는 사용자가 결정합니다.";
  }
  if (decision.primary_action === "HOLD") {
    return "현재 확정 EOD는 적용 중인 손절·목표 범위 안에 있습니다.";
  }
  return "보유 상태와 적용 계획을 기준으로 가능한 선택지를 정리했습니다.";
}

function optionTone(state: string) {
  if (state === "AVAILABLE") return "available";
  if (state === "BLOCKED") return "blocked";
  if (state === "REVIEW" || state === "MANUAL_REVIEW") return "review";
  return "muted";
}

function optionStateText(state: string) {
  if (state === "AVAILABLE") return "현재 검토 가능";
  if (state === "BLOCKED") return "정책상 차단";
  if (state === "REVIEW") return "사용자 검토";
  if (state === "MANUAL_REVIEW") return "직접 검토";
  if (state === "DEFERRED") return "판단 보류";
  return state;
}

export default function HoldingDecisionPanel({
  positions,
  data,
  management,
  status,
  loading = false,
  onContextChanged,
  onPlanChanged,
}: Props) {
  const [busyPositionId, setBusyPositionId] = useState<string | null>(null);
  const [pendingPlanReview, setPendingPlanReview] = useState<{ positionId: string; key: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const migrationRequired = status?.status === "MIGRATION_REQUIRED";

  const byPosition = useMemo(() => {
    const map = new Map<string, HoldingDecisionRecord | null>();
    for (const item of data?.positions ?? []) map.set(item.position_id, item.decision);
    return map;
  }, [data]);

  async function evaluate(positionId: string) {
    if (busyPositionId !== null) return;
    setPendingPlanReview(null);
    setBusyPositionId(positionId);
    setMessage(null);
    setError(null);
    try {
      const result = await evaluateHoldingDecision(positionId);
      setMessage(
        result.decision.reused
          ? "달라진 정보가 없어 현재 판단을 유지했습니다."
          : "현재 확정 EOD·최신 분석·적용 계획을 기준으로 판단을 업데이트했습니다.",
      );
      await onContextChanged?.();
    } catch (evaluateError) {
      setError(evaluateError instanceof Error ? evaluateError.message : "현재 판단을 만들지 못했습니다.");
    } finally {
      setBusyPositionId(null);
    }
  }

  async function acknowledge(decision: HoldingDecisionRecord) {
    if (busyPositionId !== null) return;
    setPendingPlanReview(null);
    setBusyPositionId(decision.position_id);
    setMessage(null);
    setError(null);
    try {
      await resolveHoldingDecision(decision.decision_id, {
        resolution_type: decision.primary_action === "HOLD"
          ? "KEEP_CURRENT_PLAN"
          : "ACKNOWLEDGED",
        selected_action: decision.primary_action,
      });
      setMessage(
        decision.primary_action === "HOLD"
          ? "현재 적용 계획을 유지하기로 기록했습니다."
          : "현재 판단을 확인한 것으로 기록했습니다.",
      );
      await onContextChanged?.();
    } catch (resolveError) {
      setError(resolveError instanceof Error ? resolveError.message : "판단 확인을 저장하지 못했습니다.");
    } finally {
      setBusyPositionId(null);
    }
  }

  async function applyPlan(decision: HoldingDecisionRecord, review: HoldingPlanReview) {
    if (busyPositionId !== null) return;
    // Confirmation is scoped to the displayed decision and exact price proposal.
    if (pendingPlanReview?.positionId !== decision.position_id || pendingPlanReview.key !== review.key) return;
    setPendingPlanReview(null);
    setBusyPositionId(decision.position_id);
    setMessage(null);
    setError(null);
    try {
      await applyHoldingDecisionPlan(decision.decision_id, {
        selected_action: decision.primary_action,
        note: "보유 판단 화면에서 변경 가격을 확인한 뒤 새 분석 계획 명시 적용",
      });
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : "새 관리 계획을 적용하지 못했습니다.");
      setBusyPositionId(null);
      return;
    }
    setMessage("새 분석의 관리 계획을 적용했습니다. 실제 매수·매도 거래는 발생하지 않았습니다.");
    try {
      await onPlanChanged?.();
      await onContextChanged?.();
    } catch {
      setError("계획 적용은 완료됐지만 화면을 새로고침하지 못했습니다. 최신 보유 정보를 다시 확인하세요.");
    } finally {
      setBusyPositionId(null);
    }
  }

  if (positions.length === 0) return null;

  if (migrationRequired) {
    return (
      <section id="holdings-decision-panel" className="holding-decision-panel migration-required" aria-label="보유 판단">
        <div className="holding-decision-heading">
          <div>
            <span>보유 판단</span>
            <h3>판단 기록 기능 준비가 필요합니다.</h3>
            <p>기존 보유 원장과 관리 계획은 그대로 유지됩니다. P3-S1 migration 이후부터 새 판단 기록을 사용합니다.</p>
          </div>
        </div>
        <details className="holding-decision-technical">
          <summary>개발 환경 준비 명령 보기</summary>
          <code>python tools/data/migrate_holdings_decision_vnp3s1.py</code>
        </details>
      </section>
    );
  }

  return (
    <section id="holdings-decision-panel" className="holding-decision-panel" aria-label="보유 판단">
      <div className="holding-decision-heading">
        <div>
          <span>보유 판단</span>
          <h3>현재 계획을 기준으로 지금 확인할 선택지를 정리합니다.</h3>
          <p>확정 EOD·최신 분석·현재 적용 계획만 사용합니다. 이 화면은 실제 주문을 실행하지 않습니다.</p>
        </div>
      </div>

      {loading && <div className="holding-decision-loading">저장된 판단을 확인하는 중입니다.</div>}
      {message && <div className="holding-decision-message">{message}</div>}
      {error && <div className="holding-decision-error">{error}</div>}

      {!loading && positions.map((position) => {
        const decision = byPosition.get(position.position_id) ?? null;
        const busy = busyPositionId !== null;
        const thisPositionBusy = busyPositionId === position.position_id;
        const visibleOptions = decision?.alternatives.filter(
          (item) => item.state !== "NOT_TRIGGERED",
        ) ?? [];
        const hasApplicableAnalysis = Boolean(
          decision?.source_analysis_revision_id
          && (
            decision.source_active_plan_id == null
            || decision.evidence.latest_analysis_differs_from_active_plan
          ),
        );
        const positionManagement = management?.positions.find(
          (item) => item.position_id === position.position_id,
        ) ?? null;
        const review = holdingPlanReview(decision, positionManagement);
        const isReviewConfirmed = Boolean(
          review
          && pendingPlanReview?.positionId === position.position_id
          && pendingPlanReview.key === review.key,
        );

        return (
          <article className="holding-decision-position" key={position.position_id}>
            <div className="holding-decision-position-head">
              <div>
                <span>{position.account_name || (position.provider === "KIS" ? "한국투자증권" : "보유 기록")}</span>
                {decision ? (
                  <>
                    <strong>{statusTitle(decision)}</strong>
                    <p>{statusSummary(decision)}</p>
                  </>
                ) : (
                  <>
                    <strong>아직 저장된 보유 판단이 없습니다.</strong>
                    <p>버튼을 눌렀을 때만 현재 저장 데이터로 판단을 생성합니다.</p>
                  </>
                )}
              </div>
              <button
                type="button"
                className="holdings-secondary-button"
                disabled={busy}
                onClick={() => void evaluate(position.position_id)}
              >
                {thisPositionBusy ? "확인 중…" : decision?.stale ? "최신 판단 다시 만들기" : "현재 판단 업데이트"}
              </button>
            </div>

            {decision && (
              <>
                <div className="holding-decision-basis">
                  <span>판단 기준</span>
                  <strong>{dateText(decision.valuation_market_date)} 확정 EOD · {money(decision.valuation_price)}</strong>
                  {decision.source_active_plan_version != null
                    ? <small>적용 계획 v{decision.source_active_plan_version}</small>
                    : <small>현재 적용 계획 없음</small>}
                </div>

                {visibleOptions.length > 0 && (
                  <div className="holding-decision-options" aria-label="검토 가능한 선택지">
                    {visibleOptions.map((option) => (
                      <div
                        className={`holding-decision-option ${optionTone(option.state)}`}
                        key={option.action}
                      >
                        <div>
                          <strong>{actionLabel[option.action] ?? option.action}</strong>
                          <span>{optionStateText(option.state)}</span>
                        </div>
                        <p>{option.reason}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div className="holding-decision-actions">
                  {!decision.stale && decision.status !== "INSUFFICIENT_DATA" && (
                    <button
                      type="button"
                      className="holdings-secondary-button"
                      disabled={busy}
                      onClick={() => void acknowledge(decision)}
                    >
                      {decision.primary_action === "HOLD" ? "현재 계획 유지 기록" : "이 판단 확인"}
                    </button>
                  )}
                  {review && !isReviewConfirmed && (
                    <button
                      type="button"
                      className="holdings-primary-button"
                      disabled={busy}
                      onClick={() => {
                        setPendingPlanReview({ positionId: position.position_id, key: review.key });
                        setMessage(null);
                        setError(null);
                      }}
                    >
                      새 분석 계획 비교
                    </button>
                  )}
                  {hasApplicableAnalysis && !review && !decision.stale && (
                    <small>{positionManagement?.proposal?.reason ?? "분석과 관리 계획 정보가 일치하지 않아 적용할 수 없습니다. 최신 보유 정보를 확인하세요."}</small>
                  )}
                  {review && (
                    <small>가격 변경을 확인한 다음에만 관리 계획을 적용합니다. 매수·매도 원장은 변경하지 않습니다.</small>
                  )}
                </div>

                {review && isReviewConfirmed && (
                  <div className="holding-decision-plan-review" role="group" aria-label="새 관리 계획 적용 확인">
                    <strong>적용할 손절·목표 가격을 확인하세요.</strong>
                    <p>분석 기준일 {dateText(review.proposalDate)} · {review.previousVersion == null
                      ? "첫 관리 계획 적용"
                      : `기존 계획 v${review.previousVersion} → 새 계획`}</p>
                    <div className="holding-decision-detail-grid">
                      <div><span>손절 기준</span><strong>{money(review.previousStop)} → {money(review.nextStop)}</strong></div>
                      <div><span>1차 목표</span><strong>{money(review.previousTarget1)} → {money(review.nextTarget1)}</strong></div>
                      <div><span>2차 목표</span><strong>{money(review.previousTarget2)} → {money(review.nextTarget2)}</strong></div>
                    </div>
                    <p>확정해도 실제 주문은 발생하지 않습니다. 기존 계획의 기준 가격이 교체됩니다.</p>
                    <div className="holding-decision-actions">
                      <button
                        type="button"
                        className="holdings-secondary-button"
                        disabled={busy}
                        onClick={() => setPendingPlanReview(null)}
                      >취소</button>
                      <button
                        type="button"
                        className="holdings-primary-button"
                        disabled={busy}
                        onClick={() => void applyPlan(decision, review)}
                      >이 가격으로 관리 계획 적용</button>
                    </div>
                  </div>
                )}

                <details className="holding-decision-technical">
                  <summary>판단 근거 · 제한사항</summary>
                  <div className="holding-decision-detail-grid">
                    <div><span>상태</span><strong>{decision.effective_status ?? decision.status}</strong></div>
                    <div><span>분석 revision</span><strong>{decision.source_analysis_revision_id ? "연결됨" : "없음"}</strong></div>
                    <div><span>Horizon</span><strong>{decision.horizon_intent ?? "미지정"}</strong></div>
                    <div><span>판단 시각</span><strong>{dateText(decision.created_at)}</strong></div>
                  </div>
                  {decision.limitations.length > 0 && (
                    <ul>
                      {decision.limitations.map((item) => (
                        <li key={item.code}>{item.message}</li>
                      ))}
                    </ul>
                  )}
                  {decision.stale_reasons && decision.stale_reasons.length > 0 && (
                    <p>다시 판단이 필요한 이유: {decision.stale_reasons.join(", ")}</p>
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
