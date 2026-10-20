import type {
  HoldingStock,
  HoldingWorkspaceContext,
} from "../services/holdingsApi";

/**
 * S31-N: pure read-only projection of existing Holdings workspace evidence.
 * Never treats an old Scanner stop as an applied Holding plan.
 * Watch position settings do not prove live runtime heartbeat or actual orders.
 */
export type ProtectionState =
  | "LOADING" | "SOURCE_UNVERIFIED" | "NONE" | "PARTIAL"
  | "APPLIED" | "REFERENCE_BREACHED";
export type DecisionState =
  | "LOADING" | "SOURCE_UNVERIFIED" | "NOT_CREATED" | "RECHECK"
  | "SAVED";
export type WatchState =
  | "LOADING" | "SOURCE_UNVERIFIED" | "POLICY_UNVERIFIED"
  | "GAP_REPORTED" | "SETTING_ABSENT" | "SETTING_PRESENT";

export type HoldingProtectionSummary = {
  state: "LOADING" | "SOURCE_UNVERIFIED" | "REVIEW_NEEDED" | "RECORDED_ONLY";
  headline: string;
  explanation: string;
  positionCount: number | null;
  positionCountDescription: string;
  plan: { state: ProtectionState; label: string; count: number | null };
  decision: { state: DecisionState; label: string };
  watch: { state: WatchState; label: string };
  nextAction: string;
  sourceDate: string | null;
  hasBrokerBalanceProof: false;
  hasLiveWatchProof: false;
  hasExecutedStopProof: false;
};

const unavailable = (state: "LOADING" | "SOURCE_UNVERIFIED"): HoldingProtectionSummary => ({
  state,
  headline: state === "LOADING" ? "보유 관리 상태 확인 중" : "보유 관리 근거 확인 불가",
  explanation: state === "LOADING"
    ? "보유 기록과 적용 계획을 불러오고 있어요. 이전 화면의 정보를 현재 판단으로 사용하지 마세요."
    : "보유 기록·적용 계획·Watch 상태를 같은 종목 기준으로 확인하지 못했습니다. 안전하거나 미적용이라고 추정하지 않아요.",
  positionCount: null,
  positionCountDescription: "로컬 OPEN 기록 확인 불가",
  plan: { state, label: state === "LOADING" ? "확인 중" : "확인 불가", count: null },
  decision: { state, label: state === "LOADING" ? "확인 중" : "확인 불가" },
  watch: { state, label: state === "LOADING" ? "확인 중" : "확인 불가" },
  nextAction: "데이터를 다시 불러온 뒤 보유 원장과 관리 계획을 확인하세요.",
  sourceDate: null,
  hasBrokerBalanceProof: false,
  hasLiveWatchProof: false,
  hasExecutedStopProof: false,
});

export function holdingProtectionSummary(
  stock: HoldingStock,
  context: HoldingWorkspaceContext | null,
  loading: boolean,
): HoldingProtectionSummary {
  if (loading) return unavailable("LOADING");
  if (!context
    || stock.stock_id !== context.stock.stock_id
    || stock.stock_id !== context.context_identity.stock_id
    || stock.market !== context.stock.market
    || stock.ticker !== context.stock.ticker) {
    return unavailable("SOURCE_UNVERIFIED");
  }
  const open = stock.positions.filter(position => position.status === "OPEN");
  const ids = new Set(open.map(position => position.position_id));
  if (open.length === 0 || ids.size !== open.length || !stock.is_held
    || context.positions.length !== open.length
    || context.positions.some(row => !ids.has(row.position.position_id))
    || context.source_status.ledger?.status !== "VALID") {
    return unavailable("SOURCE_UNVERIFIED");
  }

  const status = context.source_status;
  let plan: HoldingProtectionSummary["plan"];
  if (status.management?.status !== "AVAILABLE" || !context.management
    || context.positions.some(row => row.management == null
      || row.management.position_id !== row.position.position_id)) {
    plan = { state: "SOURCE_UNVERIFIED", label: "적용 계획 확인 불가", count: null };
  } else {
    const active = context.positions.filter(row =>
      row.management?.active_plan?.status === "ACTIVE"
      && row.management.active_plan.position_id === row.position.position_id);
    const breached = context.positions.some(row =>
      row.management?.active_plan?.status === "ACTIVE"
      && row.management.active_plan.position_id === row.position.position_id
      && row.management.management_state === "STOP_BREACHED");
    plan = breached
      ? { state: "REFERENCE_BREACHED", label: "확정 종가 기준 손절선 확인 필요", count: active.length }
      : active.length === 0
        ? { state: "NONE", label: "현재 적용된 관리 계획 없음", count: 0 }
        : active.length === open.length
          ? { state: "APPLIED", label: `적용 계획 ${active.length}건 확인`, count: active.length }
          : { state: "PARTIAL", label: `일부만 적용 (${active.length}/${open.length})`, count: active.length };
  }

  let decision: HoldingProtectionSummary["decision"];
  if (status.decision?.status !== "AVAILABLE") {
    decision = { state: "SOURCE_UNVERIFIED", label: "보유 판단 확인 불가" };
  } else {
    const saved = context.positions.filter(row => row.decision != null);
    decision = saved.some(row => row.decision!.stale
      || row.decision!.effective_status === "STALE"
      || ["CONFLICT", "REVIEW_REQUIRED", "INSUFFICIENT_DATA"].includes(row.decision!.status))
      ? { state: "RECHECK", label: "보유 판단 다시 확인 필요" }
      : saved.length < open.length
        ? { state: "NOT_CREATED", label: "저장된 판단 없음/부족" }
        : { state: "SAVED", label: "저장된 판단 있음 · 현재 유효성 별도 확인" };
  }

  let watch: HoldingProtectionSummary["watch"];
  const watchRows = context.positions.map(row => row.watch);
  if (status.watch?.status !== "AVAILABLE"
    || watchRows.some(row => !row || !row.available)) {
    watch = { state: "SOURCE_UNVERIFIED", label: "Watch 상태 확인 불가" };
  } else if (watchRows.some(row => row.open_gaps.length > 0)) {
    watch = { state: "GAP_REPORTED", label: "감시 연속성 공백 기록 있음" };
  } else if (watchRows.some(row => !row.policy_enabled || row.migration_required)) {
    watch = { state: "POLICY_UNVERIFIED", label: "Watch 운영 정책 미활성/검증 중" };
  } else if (watchRows.some(row => !row.setting || row.setting.status !== "ACTIVE")) {
    watch = { state: "SETTING_ABSENT", label: "Watch 적용 설정 없음/미확인" };
  } else {
    watch = { state: "SETTING_PRESENT", label: "Watch 설정 기록 있음 · 실제 가동 미확인" };
  }

  const needsReview =
    ["NONE", "PARTIAL", "REFERENCE_BREACHED"].includes(plan.state)
    || ["NOT_CREATED", "RECHECK"].includes(decision.state)
    || ["POLICY_UNVERIFIED", "GAP_REPORTED", "SETTING_ABSENT"].includes(watch.state);
  const uncertain =
    plan.state === "SOURCE_UNVERIFIED"
    || decision.state === "SOURCE_UNVERIFIED"
    || watch.state === "SOURCE_UNVERIFIED";

  const state = uncertain ? "SOURCE_UNVERIFIED" as const
    : needsReview ? "REVIEW_NEEDED" as const
      : "RECORDED_ONLY" as const;
  const headline = state === "SOURCE_UNVERIFIED"
    ? "일부 관리 상태의 근거를 확인할 수 없어요"
    : plan.state === "REFERENCE_BREACHED"
      ? "확정 종가가 적용된 손절 참고선을 이탈했어요"
      : plan.state === "NONE"
        ? "보유 기록은 있지만 적용된 관리 계획이 없어요"
        : state === "REVIEW_NEEDED"
          ? "보유 관리에서 확인할 항목이 있어요"
          : "관리 정보가 저장돼 있어요 · 실시간 가동 별도 확인";
  const explanation =
    "이 화면은 StockScope에 기록된 보유·관리 상태를 설명합니다. 증권사 실잔고, 실제 손절 주문 및 자동 감시 가동을 증명하지 않습니다.";
  const nextAction = plan.state === "REFERENCE_BREACHED"
    ? "보유 판단에서 확정 EOD 근거를 확인하세요. 자동 손절이나 매도는 실행하지 않았습니다."
    : plan.state === "NONE" || plan.state === "PARTIAL"
      ? "보유 판단에서 최신 분석과 관리 계획 적용 가능 여부를 확인하세요. 적용은 사용자가 직접 결정합니다."
      : uncertain
        ? "확인 불가 항목을 원본 보유 판단·관리 계획·Watch 영역에서 다시 확인하세요."
        : "아래의 보유 판단·관리 계획·Watch 정보를 점검하세요.";
  return {
    state, headline, explanation,
    positionCount: open.length,
    positionCountDescription: `로컬 OPEN 포지션 ${open.length}개 · 실제 계좌 잔고 미검증`,
    plan, decision, watch, nextAction,
    sourceDate: context.context_identity.market_confirmed_date,
    hasBrokerBalanceProof: false,
    hasLiveWatchProof: false,
    hasExecutedStopProof: false,
  };
}
