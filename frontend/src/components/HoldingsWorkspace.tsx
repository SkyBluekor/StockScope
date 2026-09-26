import { useEffect, useMemo, useRef, useState } from "react";
import { searchStocks, type StockSearchItem } from "../services/api";
import { readHoldingsViewContext, writeHoldingsViewContext } from "../services/uiSession";
import HoldingsPriceChart from "./HoldingsPriceChart";
import StockNewsPanel from "./StockNewsPanel";
import {
  addWatchStock,
  getHoldingStock,
  getHoldingPerformance,
  getHoldingManagement,
  applyHoldingManagementPlan,
  getHoldingChart,
  getHoldingTimeline,
  listHoldingAccounts,
  listHoldingStocks,
  recordManualBuy,
  recordManualCorrection,
  registerHeldStock,
  recordManualSell,
  refreshHoldingAnalysis,
  prepareHoldingAnalysisWithProgress,
  setWatchEnabled,
  syncKisHoldings,
  HoldingsApiError,
  type HoldingAnalysisPrepareProgress,
  type HoldingAccount,
  type HoldingDecisionContext,
  type HoldingPosition,
  type HoldingPerformanceResponse,
  type HoldingManagementResponse,
  type HoldingStock,
  type HoldingTimelineItem,
} from "../services/holdingsApi";
import "../holdings.css";

type Props = {
  onAnalyzeStock?: (item: StockSearchItem) => void;
};

type HoldingsNavigationTarget = {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  name?: string;
};

type StockFilter = "all" | "watch" | "held";
type TimelineFilter = "all" | "analysis" | "position";
type ManualMode = "buy" | "sell" | "correction";
type HistoryRecoveryState = {
  stockId: string;
  currentRows: number | null;
  requiredRows: number | null;
  exhausted: boolean;
};

function readHoldingsNavigationTarget(): HoldingsNavigationTarget | null {
  try {
    const raw = window.sessionStorage.getItem("stockscope-holdings-target");
    if (!raw) return null;
    window.sessionStorage.removeItem("stockscope-holdings-target");
    const parsed = JSON.parse(raw) as Partial<HoldingsNavigationTarget>;
    const market = parsed.market === "KOSPI" || parsed.market === "KOSDAQ" ? parsed.market : null;
    const ticker = typeof parsed.ticker === "string" ? parsed.ticker.trim().toUpperCase() : "";
    if (!market || !ticker) return null;
    return {
      market,
      ticker,
      name: typeof parsed.name === "string" ? parsed.name : undefined,
    };
  } catch {
    return null;
  }
}

const strategyLabel: Record<string, string> = {
  trend_following: "상승 흐름 유지",
  pullback: "눌림 후 반등 흐름",
  breakout: "강한 돌파 흐름",
  support_bounce: "지지 가격에서 반등",
  oversold_bounce: "많이 떨어진 뒤 반등",
  range_trading: "일정 가격 사이 움직임",
  momentum_continuation: "강한 상승 지속",
  volatility_squeeze: "조용한 움직임 뒤 방향 대기",
  ma20_rebound: "최근 평균 가격에서 반등",
  trend_recovery: "다시 상승 흐름",
  no_trade: "지금은 관망",
};

const actionLabel: Record<string, string> = {
  READY: "진입 후보",
  WATCH: "관심 유지",
  NO_TRADE: "신규 진입 제외",
  NOT_READY: "현재 우선순위 낮음",
  CAUTION: "주의하며 관찰",
  BLOCKED: "위험 때문에 보류",
};

const riskLabel: Record<string, string> = {
  READY: "계산 완료",
  CAUTION: "주의 조건 있음",
  HOLD: "계산 보류",
  BLOCKED: "계산 제한",
  UNAVAILABLE: "계산 불가",
};


function strategyChangeText(context: HoldingDecisionContext | null | undefined) {
  if (!context) return "-";
  if (context.strategy.state === "INITIAL") return "첫 분석";
  if (context.strategy.state === "UNCHANGED") return "유지";
  const previous = context.strategy.previous
    ? strategyLabel[context.strategy.previous] ?? context.strategy.previous
    : "이전 전략 없음";
  const current = context.strategy.current
    ? strategyLabel[context.strategy.current] ?? context.strategy.current
    : "현재 전략 없음";
  return `${previous} → ${current}`;
}

function planStateClass(context: HoldingDecisionContext | null | undefined) {
  const state = context?.previous_plan.state;
  if (state === "STOP_BREACHED") return "alert";
  if (state === "TARGET1_REACHED" || state === "TARGET2_REACHED") return "target";
  return "";
}

function isPlanEvent(context: HoldingDecisionContext | null | undefined) {
  return ["STOP_BREACHED", "TARGET1_REACHED", "TARGET2_REACHED"].includes(
    context?.previous_plan.state ?? "",
  );
}

function holdingManagementText(context: HoldingDecisionContext | null | undefined) {
  switch (context?.previous_plan.state) {
    case "STOP_BREACHED":
      return "확인이 필요한 가격 구간";
    case "TARGET1_REACHED":
    case "TARGET2_REACHED":
      return "목표 가격 도달 구간";
    case "WITHIN_PLAN":
      return "이전 분석 범위 내";
    case "FIRST_PLAN":
      return "첫 계획 기준 저장됨";
    case "PREVIOUS_PLAN_UNAVAILABLE":
      return "이전 분석 정보 확인 필요";
    default:
      return "가격 계획 확인 필요";
  }
}

function conditionCountText(context: HoldingDecisionContext | null | undefined) {
  const total = context?.entry.total;
  const missing = context?.entry.missing;
  if (total == null || missing == null) return null;
  return `현재 전략 조건 ${total}개 중 ${missing}개가 부족합니다.`;
}

function entryGuidanceText(context: HoldingDecisionContext | null | undefined) {
  if (!context) return "현재 판단 근거를 확인할 수 없습니다.";
  const count = conditionCountText(context);
  switch (context.entry.state) {
    case "READY":
      return "현재 전략 조건과 손절·목표 위험 기준이 진입 후보로 다시 검토할 수 있는 수준입니다.";
    case "WATCH":
      return `${count ? `${count} ` : ""}일부 조건은 부족하지만 현재 전략 흐름은 남아 있어 다음 확정 일봉에서 계속 확인합니다.`;
    case "NOT_READY":
      return `${count ? `${count} ` : ""}현재는 신규 진입 관점에서 우선순위가 낮아 적극적으로 볼 단계는 아닙니다.`;
    case "BLOCKED":
      return "전략 조건은 갖춰졌지만 현재 위험 구조 때문에 신규 진입 후보로 보기 어렵습니다.";
    case "CAUTION":
      return "조건은 갖춰졌지만 손절 폭이나 목표 여유에 주의가 필요해 관찰이 필요합니다.";
    case "NO_TRADE":
      return "현재는 신규 진입 후보로 보기 어렵습니다. 다음 확정 일봉에서 조건 변화를 다시 확인합니다.";
    default:
      return context.entry.summary ?? "현재 판단 근거를 확인할 수 없습니다.";
  }
}

function planGuidanceText(
  context: HoldingDecisionContext | null | undefined,
  marketDate: string | null | undefined,
) {
  if (!context) return null;
  const plan = context.previous_plan;
  const previousDate = plan.previous_market_date ? compactDate(plan.previous_market_date) : null;
  switch (plan.state) {
    case "FIRST_PLAN":
      return `${compactDate(marketDate)}의 기준가·손절·목표 가격을 첫 비교 계획으로 저장했습니다. 다음 확정 일봉 분석부터 이 계획과 비교합니다.`;
    case "PREVIOUS_PLAN_UNAVAILABLE":
      return previousDate
        ? `${previousDate} 분석은 있지만 비교 가능한 손절·목표 가격 정보가 충분하지 않습니다.`
        : "이전 분석의 가격 계획 정보를 확인할 수 없습니다.";
    case "STOP_BREACHED":
      return `${previousDate ?? "이전"} 분석의 손절 기준 ${money(plan.previous_stop_price)}보다 현재 확정 종가 ${money(plan.current_close)}가 낮거나 같습니다.`;
    case "TARGET2_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 분석의 2차 목표 ${money(plan.previous_target2_price)} 이상입니다.`;
    case "TARGET1_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 분석의 1차 목표 ${money(plan.previous_target1_price)} 이상입니다.`;
    case "WITHIN_PLAN":
      return `${previousDate ?? "이전"} 분석과 현재 확정 종가를 비교했으며 현재는 이전 분석의 가격 범위 안에 있습니다.`;
    default:
      return null;
  }
}

function previousPlanActionLabel(context: HoldingDecisionContext | null | undefined) {
  const plan = context?.previous_plan;
  if (!plan || plan.state === "FIRST_PLAN" || !plan.previous_market_date) return null;
  return plan.state === "PREVIOUS_PLAN_UNAVAILABLE" ? "과거 분석 보기" : "이전 분석과 비교";
}

function money(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(parsed)}원`;
}

function historyRequirement(error: HoldingsApiError) {
  const directCurrent = error.detail?.current_rows;
  const directRequired = error.detail?.required_rows;
  if (typeof directCurrent === "number" && typeof directRequired === "number") {
    return { currentRows: directCurrent, requiredRows: directRequired };
  }
  const match = error.message.match(/(\d+)\s*\/\s*(\d+)/);
  return {
    currentRows: match ? Number(match[1]) : null,
    requiredRows: match ? Number(match[2]) : null,
  };
}

function quantity(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 6 }).format(parsed);
}

const HOLD_G5_POSITION_UX = true;

function quantityNumber(value: string | null | undefined) {
  const parsed = Number(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function signedMoney(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  const absolute = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(Math.abs(parsed));
  if (parsed > 0) return `+${absolute}원`;
  if (parsed < 0) return `-${absolute}원`;
  return "0원";
}

function signedPercent(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  const formatted = new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(parsed));
  if (parsed > 0) return `+${formatted}%`;
  if (parsed < 0) return `-${formatted}%`;
  return "0.00%";
}

function pnlSignClass(value: string | null | undefined) {
  const parsed = Number(value ?? "");
  if (!Number.isFinite(parsed) || parsed === 0) return "";
  return parsed > 0 ? "positive" : "negative";
}

function managementStateText(state: string) {
  switch (state) {
    case "NO_ACTIVE_PLAN": return "적용 중인 보유분 관리 기준 없음";
    case "WITHIN_PLAN": return "현재 계획 범위 안";
    case "STOP_BREACHED": return "손절 기준 확인 필요";
    case "TARGET1_REACHED": return "1차 목표 구간 도달";
    case "TARGET2_REACHED": return "2차 목표 구간 도달";
    case "DATA_UNAVAILABLE": return "현재 가격 확인 필요";
    default: return state;
  }
}

function proposalStateText(state: string) {
  switch (state) {
    case "NONE": return "새 제안 없음";
    case "SAME_AS_ACTIVE": return "현재 계획과 동일";
    case "NEW_REVISION": return "최신 분석의 새 계획";
    case "NOT_APPLICABLE": return "적용할 가격 계획 없음";
    default: return state;
  }
}

function performanceStatusText(status: string) {
  switch (status) {
    case "COMPLETE_SINCE_TRACKING_START":
      return "StockScope 추적 시작 이후 기록 기준";
    case "PARTIAL":
      return "일부 거래만 확인됨";
    case "VALUATION_ONLY":
      return "현재 보유 평가만 가능";
    case "UNAVAILABLE":
      return "손익 계산 정보 부족";
    default:
      return status;
  }
}

function stockDecisionText(stock: HoldingStock) {
  if (!stock.current_analysis) return "분석 필요";
  return stock.decision_context?.entry.label
    ?? actionLabel[stock.current_analysis.action_state]
    ?? stock.current_analysis.action_state;
}

function stockPositionListSummary(stock: HoldingStock) {
  const positions = stock.positions ?? [];
  if (positions.length === 0) return { quantity: "-", average: "-" };
  if (positions.length === 1) {
    return {
      quantity: `${quantity(positions[0].quantity)}주`,
      average: money(positions[0].average_price),
    };
  }
  const total = positions.reduce((sum, position) => sum + quantityNumber(position.quantity), 0);
  return {
    quantity: `총 ${quantity(String(total))}주`,
    average: `${positions.length}개 보유 기록`,
  };
}

function stockStateLabel(stock: HoldingStock) {
  if (stock.watch_enabled && stock.is_held) return "관심 · 보유";
  if (stock.is_held) return "보유";
  if (stock.watch_enabled) return "관심";
  return "등록 상태 없음";
}

function compactDate(value: string | null | undefined) {
  if (!value) return "-";
  const text = value.slice(0, 10);
  return text.replace(/-/g, ".");
}

function compactDateTime(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 16);
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function localDateTimeValue() {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function toIso(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

const HOLD_G52R_UAT_FIX_1 = true;

function analysisRevisionIdForTrade(
  analysis: HoldingStock["current_analysis"],
  effectiveAtLocal: string,
) {
  if (!analysis?.revision_id || !analysis.computed_at) return null;
  const effectiveAt = new Date(effectiveAtLocal).getTime();
  const computedAt = new Date(analysis.computed_at).getTime();
  if (!Number.isFinite(effectiveAt) || !Number.isFinite(computedAt)) return null;
  return computedAt <= effectiveAt ? analysis.revision_id : null;
}

function readableError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function timelineLabel(item: HoldingTimelineItem) {
  if (item.kind === "ANALYSIS") return "분석 갱신";
  switch (item.event_type) {
    case "OPENING_BALANCE":
      return "기존 보유 등록";
    case "BUY":
      return "추가 매수";
    case "SELL":
      return "매도";
    case "CORRECTION":
      return "보유 정보 수정";
    case "BALANCE_OBSERVED":
      return "잔고 확인";
    case "RECONCILED":
      return "잔고 동기화";
    default:
      return "보유 기록";
  }
}

function timelineDescription(item: HoldingTimelineItem) {
  if (item.kind === "ANALYSIS") {
    const strategy = typeof item.payload.strategy_key === "string"
      ? strategyLabel[item.payload.strategy_key] ?? item.payload.strategy_key
      : null;
    return strategy ? `최신 확정 데이터 기준 분석 · ${strategy}` : "최신 확정 데이터 기준 분석을 기록했습니다.";
  }
  const note = typeof item.payload.note === "string" ? item.payload.note : null;
  if (note) return note;
  switch (item.event_type) {
    case "OPENING_BALANCE":
      return "StockScope 추적을 시작할 당시의 기존 보유 상태를 등록했습니다.";
    case "BUY":
      return "실제 추가 매수 거래를 StockScope 보유 원장에 기록했습니다.";
    case "SELL":
      return "실제 매도 거래를 StockScope 보유 원장에 기록했습니다.";
    case "CORRECTION":
      return "거래가 아닌 보유 정보 정정으로 현재 수량 또는 평균단가를 바로잡았습니다.";
    case "BALANCE_OBSERVED":
      return "한국투자증권에서 확인한 잔고를 기록했습니다.";
    case "RECONCILED":
      return "한국투자증권 잔고와 StockScope 보유 정보를 동기화했습니다.";
    default:
      return "보유 정보가 변경되었습니다.";
  }
}

export default function HoldingsWorkspace({ onAnalyzeStock }: Props) {
  const [stocks, setStocks] = useState<HoldingStock[]>([]);
  const [navigationTarget] = useState<HoldingsNavigationTarget | null>(readHoldingsNavigationTarget);
  const [initialViewContext] = useState(() => readHoldingsViewContext());
  const navigationTargetConsumedRef = useRef(false);
  const [selectedStockId, setSelectedStockId] = useState<string | null>(
    navigationTarget ? null : initialViewContext?.selectedStockId ?? null,
  );
  const [detail, setDetail] = useState<HoldingStock | null>(null);
  const [timeline, setTimeline] = useState<HoldingTimelineItem[]>([]);
  const [performance, setPerformance] = useState<HoldingPerformanceResponse | null>(null);
  const [management, setManagement] = useState<HoldingManagementResponse | null>(null);
  const [applyingPlanId, setApplyingPlanId] = useState<string | null>(null);
  const [stockFilter, setStockFilter] = useState<StockFilter>(
    navigationTarget ? "all" : initialViewContext?.stockFilter ?? "all",
  );
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>(
    navigationTarget ? "all" : initialViewContext?.timelineFilter ?? "all",
  );
  const [query, setQuery] = useState(navigationTarget ? "" : initialViewContext?.query ?? "");
  const [loadingStocks, setLoadingStocks] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
  const [preparingHistory, setPreparingHistory] = useState(false);
  const [historyRecovery, setHistoryRecovery] = useState<HistoryRecoveryState | null>(null);
  const [historyProgress, setHistoryProgress] = useState<HoldingAnalysisPrepareProgress | null>(null);
  const [chartRefreshKey, setChartRefreshKey] = useState(0);
  const [syncingKis, setSyncingKis] = useState(false);
  const [showMissingConditions, setShowMissingConditions] = useState(false);
  const [showPreviousPlan, setShowPreviousPlan] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<HoldingStock | null>(null);
  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState<StockSearchItem[]>([]);
  const [addSearching, setAddSearching] = useState(false);
  const [addSelectedStock, setAddSelectedStock] = useState<StockSearchItem | null>(null);
  const [addMode, setAddMode] = useState<"held" | null>(null);
  const [addQuantity, setAddQuantity] = useState("1");
  const [addAveragePrice, setAddAveragePrice] = useState("");
  const [addReferencePrice, setAddReferencePrice] = useState("");
  const [addEffectiveAt, setAddEffectiveAt] = useState(localDateTimeValue());
  const [addBusy, setAddBusy] = useState(false);

  const [manualOpen, setManualOpen] = useState(false);
  const [manualMode, setManualMode] = useState<ManualMode>("buy");
  const [accounts, setAccounts] = useState<HoldingAccount[]>([]);
  const [manualPositionId, setManualPositionId] = useState("");
  const [manualAccountId, setManualAccountId] = useState("");
  const [manualQuantity, setManualQuantity] = useState("");
  const [manualPrice, setManualPrice] = useState("");
  const [manualAt, setManualAt] = useState(localDateTimeValue());
  const [manualNote, setManualNote] = useState("");
  const [manualBusy, setManualBusy] = useState(false);

  const [manualReferencePrice, setManualReferencePrice] = useState("");
  const [quickEditPositionId, setQuickEditPositionId] = useState<string | null>(null);
  const [quickEditField, setQuickEditField] = useState<"quantity" | "average_price" | null>(null);
  const [quickEditValue, setQuickEditValue] = useState("");
  const [quickEditBaseValue, setQuickEditBaseValue] = useState("");
  const [quickEditBusy, setQuickEditBusy] = useState(false);
  const [quickZeroConfirm, setQuickZeroConfirm] = useState(false);
  const holdDelayRef = useRef<number | null>(null);
  const holdIntervalRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const quickEditPanelRef = useRef<HTMLDivElement | null>(null);
  const quickEditInputRef = useRef<HTMLInputElement | null>(null);
  const holdingOverviewRef = useRef<HTMLDivElement | null>(null);
  const selectedStockIdRef = useRef<string | null>(selectedStockId);
  const detailRequestIdRef = useRef(0);
  const detailAbortRef = useRef<AbortController | null>(null);
  const addSearchRequestIdRef = useRef(0);

  selectedStockIdRef.current = selectedStockId;

  async function reloadStocks(preferredId?: string | null) {
    setLoadingStocks(true);
    try {
      const rows = await listHoldingStocks();
      setStocks(rows);
      const navigationTargetId = !navigationTargetConsumedRef.current && navigationTarget
        ? rows.find(
            (row) => row.market === navigationTarget.market
              && row.ticker.trim().toUpperCase() === navigationTarget.ticker,
          )?.stock_id ?? null
        : null;
      if (!navigationTargetConsumedRef.current) navigationTargetConsumedRef.current = true;

      const keep = navigationTargetId
        ?? (preferredId && rows.some((row) => row.stock_id === preferredId)
          ? preferredId
          : selectedStockId && rows.some((row) => row.stock_id === selectedStockId)
            ? selectedStockId
            : rows[0]?.stock_id ?? null);
      setSelectedStockId(keep);
      if (!keep) {
        setDetail(null);
        setTimeline([]);
        setPerformance(null);
        setManagement(null);
      }
    } catch (loadError) {
      setError(readableError(loadError, "내 종목 목록을 불러오지 못했습니다."));
    } finally {
      setLoadingStocks(false);
    }
  }

  async function loadSelected(stockId: string) {
    const requestId = ++detailRequestIdRef.current;
    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;

    setLoadingDetail(true);
    if (detail?.stock_id !== stockId) {
      setDetail(null);
      setTimeline([]);
      setPerformance(null);
      setManagement(null);
    }

    try {
      const [stock, rows, pnl, managementResult] = await Promise.all([
        getHoldingStock(stockId, { signal: controller.signal }),
        getHoldingTimeline(stockId, 100, { signal: controller.signal }),
        getHoldingPerformance(stockId, { signal: controller.signal }),
        getHoldingManagement(stockId, { signal: controller.signal }),
      ]);
      if (requestId !== detailRequestIdRef.current || selectedStockIdRef.current !== stockId) return;
      setDetail(stock);
      setTimeline(rows);
      setPerformance(pnl);
      setManagement(managementResult);
    } catch (loadError) {
      if (isAbortError(loadError)) return;
      if (requestId !== detailRequestIdRef.current || selectedStockIdRef.current !== stockId) return;
      setError(readableError(loadError, "선택한 종목 정보를 불러오지 못했습니다."));
    } finally {
      if (requestId === detailRequestIdRef.current) {
        if (detailAbortRef.current === controller) detailAbortRef.current = null;
        setLoadingDetail(false);
      }
    }
  }

  async function applyLatestManagementPlan(positionId: string, revisionId: string) {
    setApplyingPlanId(positionId);
    setError(null);
    try {
      await applyHoldingManagementPlan(positionId, revisionId);
      setMessage("최신 분석의 가격 계획을 현재 보유분 관리 기준으로 적용했습니다.");
      if (selectedStockId) await loadSelected(selectedStockId);
    } catch (applyError) {
      setError(readableError(applyError, "보유분 관리 기준을 적용하지 못했습니다."));
    } finally {
      setApplyingPlanId(null);
    }
  }

  useEffect(() => {
    void reloadStocks();
    return () => {
      detailRequestIdRef.current += 1;
      detailAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    writeHoldingsViewContext({
      stockFilter,
      timelineFilter,
      query,
      selectedStockId,
    });
  }, [stockFilter, timelineFilter, query, selectedStockId]);

  useEffect(() => {
    setShowMissingConditions(false);
    setShowPreviousPlan(false);
    setHistoryRecovery(null);
    setHistoryProgress(null);
    if (selectedStockId) {
      void loadSelected(selectedStockId);
      return;
    }
    detailRequestIdRef.current += 1;
    detailAbortRef.current?.abort();
    detailAbortRef.current = null;
    setLoadingDetail(false);
    setDetail(null);
    setTimeline([]);
    setPerformance(null);
    setManagement(null);
  }, [selectedStockId]);

  useEffect(() => {
    if (!addOpen) {
      addSearchRequestIdRef.current += 1;
      setAddSearching(false);
      return undefined;
    }
    const text = addQuery.trim();
    if (text.length < 2) {
      addSearchRequestIdRef.current += 1;
      setAddResults([]);
      setAddSearching(false);
      return undefined;
    }

    let controller: AbortController | null = null;
    const timer = window.setTimeout(() => {
      controller = new AbortController();
      const requestId = ++addSearchRequestIdRef.current;
      setAddSearching(true);
      void searchStocks(text, { signal: controller.signal })
        .then((result) => {
          if (requestId !== addSearchRequestIdRef.current || addQuery.trim() !== text) return;
          setAddResults(result.rows);
        })
        .catch((error) => {
          if (isAbortError(error) || requestId !== addSearchRequestIdRef.current) return;
          if (addQuery.trim() !== text) return;
          setAddResults([]);
        })
        .finally(() => {
          if (requestId === addSearchRequestIdRef.current) setAddSearching(false);
        });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, [addOpen, addQuery]);

  const summary = useMemo(() => {
    const analyzed = stocks.filter((stock) => stock.current_analysis != null);
    const analysisDates = analyzed
      .map((stock) => stock.current_analysis?.market_date ?? "")
      .filter(Boolean)
      .sort();
    const latest = analysisDates.length > 0 ? analysisDates[analysisDates.length - 1] : null;
    return {
      watched: stocks.filter((stock) => stock.watch_enabled).length,
      held: stocks.filter((stock) => stock.is_held).length,
      analyzed: analyzed.length,
      pending: stocks.length - analyzed.length,
      latest,
    };
  }, [stocks]);

  const visibleStocks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return stocks.filter((stock) => {
      if (stockFilter === "watch" && !stock.watch_enabled) return false;
      if (stockFilter === "held" && !stock.is_held) return false;
      if (!needle) return true;
      return stock.name.toLowerCase().includes(needle) || stock.ticker.includes(needle);
    });
  }, [stocks, stockFilter, query]);

  useEffect(() => {
    if (loadingStocks) return;
    if (visibleStocks.length === 0) {
      if (selectedStockId != null) setSelectedStockId(null);
      return;
    }
    if (!selectedStockId || !visibleStocks.some((stock) => stock.stock_id === selectedStockId)) {
      setSelectedStockId(visibleStocks[0].stock_id);
    }
  }, [loadingStocks, selectedStockId, visibleStocks]);

  const visibleTimeline = useMemo(() => {
    if (timelineFilter === "analysis") return timeline.filter((item) => item.kind === "ANALYSIS");
    if (timelineFilter === "position") return timeline.filter((item) => item.kind !== "ANALYSIS");
    return timeline;
  }, [timeline, timelineFilter]);

  const editablePositions = useMemo(
    () => (detail?.positions ?? []).filter(
      (position) => position.account_kind === "MANUAL" || position.account_kind === "VIRTUAL",
    ),
    [detail],
  );

  const manualPosition = useMemo(
    () => (detail?.positions ?? []).find((position) => position.position_id === manualPositionId) ?? null,
    [detail, manualPositionId],
  );

  const singlePosition = detail?.positions.length === 1 ? detail.positions[0] : null;
  const singleEditablePosition = singlePosition
    && (singlePosition.account_kind === "MANUAL" || singlePosition.account_kind === "VIRTUAL")
      ? singlePosition
      : null;
  const totalHeldQuantity = (detail?.positions ?? []).reduce(
    (sum, position) => sum + quantityNumber(position.quantity),
    0,
  );

  const manualDialogTitle = manualMode === "buy"
    ? "추가 매수 기록"
    : manualMode === "sell"
      ? "매도 기록"
      : "보유 정보 수정";

  const manualRemainingQuantity = manualMode === "sell" && manualPosition
    ? Math.max(0, quantityNumber(manualPosition.quantity) - quantityNumber(manualQuantity))
    : null;

  const manualSellRealizedPnl = manualMode === "sell"
    && manualPosition
    && manualPosition.average_price != null
    && quantityNumber(manualQuantity) > 0
    && quantityNumber(manualPrice) > 0
      ? quantityNumber(manualQuantity)
        * (quantityNumber(manualPrice) - quantityNumber(manualPosition.average_price))
      : null;

  const manualBuyProjectedAverage = manualMode === "buy"
    && manualPosition
    && manualPosition.average_price != null
    && quantityNumber(manualPosition.quantity) > 0
    && quantityNumber(manualQuantity) > 0
    && quantityNumber(manualPrice) > 0
      ? (
          quantityNumber(manualPosition.quantity) * quantityNumber(manualPosition.average_price)
          + quantityNumber(manualQuantity) * quantityNumber(manualPrice)
        ) / (
          quantityNumber(manualPosition.quantity) + quantityNumber(manualQuantity)
        )
      : null;

  async function refreshSelected() {
    if (!selectedStockId) return;
    setRefreshingAnalysis(true);
    setError(null);
    setMessage(null);
    setHistoryRecovery(null);
    try {
      const result = await refreshHoldingAnalysis(selectedStockId);
      await Promise.all([reloadStocks(selectedStockId), loadSelected(selectedStockId)]);
      setChartRefreshKey((value) => value + 1);
      const dateLabel = compactDate(result.market_date);
      setMessage(
        result.data_freshness.status === "UPDATED"
          ? `새로운 확정 시세를 반영해 ${dateLabel} 기준으로 분석했습니다.`
          : `${dateLabel} 최신 확정 일봉 기준으로 분석했습니다.`,
      );
    } catch (refreshError) {
      if (refreshError instanceof HoldingsApiError && refreshError.code === "HOLD_ANALYSIS_HISTORY_INSUFFICIENT") {
        const requirement = historyRequirement(refreshError);
        setHistoryRecovery({
          stockId: selectedStockId,
          currentRows: requirement.currentRows,
          requiredRows: requirement.requiredRows,
          exhausted: false,
        });
        return;
      }
      setError(readableError(refreshError, "최신 확정 데이터를 확인하거나 분석하지 못했습니다."));
    } finally {
      setRefreshingAnalysis(false);
    }
  }

  async function prepareHistoryAndAnalyze() {
    if (!selectedStockId) return;
    setPreparingHistory(true);
    setError(null);
    setMessage(null);
    setHistoryProgress({
      type: "progress",
      stage: "starting",
      message: "데이터 준비를 시작합니다.",
    });
    try {
      const result = await prepareHoldingAnalysisWithProgress(
        selectedStockId,
        (progress) => setHistoryProgress(progress),
      );
      setHistoryRecovery(null);
      setHistoryProgress({ type: "progress", stage: "refresh", message: "화면을 갱신하고 있습니다." });
      await Promise.all([reloadStocks(selectedStockId), loadSelected(selectedStockId)]);
      setChartRefreshKey((value) => value + 1);
      const prepared = result.history_prepare;
      const preparedText = prepared && prepared.prepared_rows > 0
        ? `과거 가격 ${prepared.prepared_rows}거래일을 추가로 준비하고 `
        : "과거 가격 데이터를 확인하고 ";
      setMessage(`${preparedText}${compactDate(result.market_date)} 기준 분석을 완료했습니다.`);
      setHistoryProgress(null);
    } catch (prepareError) {
      setHistoryProgress(null);
      if (prepareError instanceof HoldingsApiError && prepareError.code === "HOLD_ANALYSIS_HISTORY_INSUFFICIENT") {
        const requirement = historyRequirement(prepareError);
        setHistoryRecovery({
          stockId: selectedStockId,
          currentRows: requirement.currentRows,
          requiredRows: requirement.requiredRows,
          exhausted: true,
        });
        return;
      }
      setError(readableError(prepareError, "과거 가격 데이터를 준비하지 못했습니다."));
    } finally {
      setPreparingHistory(false);
    }
  }

  async function syncKis() {
    setSyncingKis(true);
    setError(null);
    setMessage(null);
    try {
      const result = await syncKisHoldings();
      await reloadStocks(selectedStockId);
      if (selectedStockId) await loadSelected(selectedStockId);
      setMessage(`잔고 동기화 완료 · 확인 ${result.holding_count}종목`);
    } catch (syncError) {
      setError(readableError(syncError, "한국투자증권 잔고 동기화에 실패했습니다."));
    } finally {
      setSyncingKis(false);
    }
  }

  function closeAddDialog() {
    if (addBusy) return;
    setAddOpen(false);
    setAddQuery("");
    setAddResults([]);
    setAddSelectedStock(null);
    setAddMode(null);
    setAddQuantity("1");
    setAddAveragePrice("");
    setAddReferencePrice("");
    setAddEffectiveAt(localDateTimeValue());
  }

  async function selectAddStock(item: StockSearchItem) {
    setAddSelectedStock(item);
    setAddMode(null);
    setAddQuantity("1");
    setAddEffectiveAt(localDateTimeValue());
    setAddQuery("");
    setAddResults([]);
    setError(null);

    const existing = stocks.find(
      (stock) => stock.market === item.market && stock.ticker === item.code,
    );
    let reference = existing?.current_analysis?.reference_price ?? "";
    if (!reference && existing) {
      try {
        const chart = await getHoldingChart(existing.stock_id, "1m");
        reference = chart.bars.length > 0 ? chart.bars[chart.bars.length - 1]?.close ?? "" : "";
      } catch {
        reference = "";
      }
    }
    setAddReferencePrice(reference);
    setAddAveragePrice(reference);
  }

  function openExistingHoldingRegistration() {
    if (!detail || detail.is_held) return;
    const market: "KOSPI" | "KOSDAQ" = detail.market === "KOSDAQ" ? "KOSDAQ" : "KOSPI";
    const referencePrice = detail.current_analysis?.reference_price ?? "";
    setAddSelectedStock({
      code: detail.ticker,
      standard_code: detail.ticker,
      name: detail.name,
      full_name: detail.name,
      english_name: "",
      market,
      market_name: market,
      security_group: "주식",
      section: "",
      stock_type: "보통주",
      listed_date: "",
      listed_shares: null,
      analysis_as_of_date: detail.current_analysis?.market_date ?? null,
    });
    setAddMode("held");
    setAddQuantity("1");
    setAddReferencePrice(referencePrice);
    setAddAveragePrice(referencePrice);
    setAddEffectiveAt(localDateTimeValue());
    setAddQuery("");
    setAddResults([]);
    setAddOpen(true);
    setError(null);
  }

  async function addSelectedAsWatch() {
    if (!addSelectedStock) return;
    setAddBusy(true);
    setError(null);
    try {
      const result = await addWatchStock({
        market: addSelectedStock.market,
        ticker: addSelectedStock.code,
        name: addSelectedStock.name,
      });
      const stockId = result.stock.stock_id;
      setAddOpen(false);
      setAddSelectedStock(null);
      setAddMode(null);
      setAddQuery("");
      setAddResults([]);
      await reloadStocks(stockId);
      setSelectedStockId(stockId);
      setMessage(result.created ? "관심 종목에 추가했습니다." : "이미 등록된 종목을 관심 상태로 변경했습니다.");
    } catch (addError) {
      setError(readableError(addError, "관심 종목을 추가하지 못했습니다."));
    } finally {
      setAddBusy(false);
    }
  }

  function adjustAddQuantity(delta: number) {
    setAddQuantity((value) => String(Math.max(1, quantityNumber(value) + delta)));
  }

  function setAddPriceByPercent(percent: number) {
    setAddAveragePrice((value) => {
      const current = quantityNumber(value) || quantityNumber(addReferencePrice);
      if (current <= 0) return value;
      return String(Math.max(1, Math.round(current * (1 + percent / 100))));
    });
  }

  async function addSelectedAsHeld() {
    if (!addSelectedStock) return;
    if (quantityNumber(addQuantity) <= 0) {
      setError("보유 수량은 0보다 커야 합니다.");
      return;
    }
    if (quantityNumber(addAveragePrice) <= 0) {
      setError("평균단가를 입력해주세요.");
      return;
    }

    setAddBusy(true);
    setError(null);
    try {
      const result = await registerHeldStock({
        market: addSelectedStock.market,
        ticker: addSelectedStock.code,
        name: addSelectedStock.name,
        quantity: addQuantity,
        average_price: addAveragePrice,
        effective_at: toIso(addEffectiveAt),
      });
      const stockId = result.stock.stock_id;
      setAddOpen(false);
      setAddSelectedStock(null);
      setAddMode(null);
      setAddQuery("");
      setAddResults([]);
      await reloadStocks(stockId);
      setSelectedStockId(stockId);
      setMessage(`${addSelectedStock.name}을(를) ${quantity(addQuantity)}주 기존 보유 상태로 등록했습니다.`);
    } catch (addError) {
      setError(readableError(addError, "기존 보유 상태를 등록하지 못했습니다."));
    } finally {
      setAddBusy(false);
    }
  }

  async function changeWatch(stock: HoldingStock, enabled: boolean, removedFromList = false) {
    setError(null);
    setMessage(null);
    try {
      await setWatchEnabled(stock.stock_id, enabled);
      setRemoveTarget(null);
      const preferred = enabled || stock.is_held ? stock.stock_id : null;
      await reloadStocks(preferred);
      if (stock.is_held && stock.stock_id === selectedStockId) {
        await loadSelected(stock.stock_id);
      }
      setMessage(
        enabled
          ? `${stock.name}을(를) 관심 종목으로 등록했습니다.`
          : removedFromList
            ? `${stock.name}을(를) 내 종목 목록에서 제거했습니다. 저장된 분석 기록은 유지됩니다.`
            : `${stock.name}의 관심 등록을 해제했습니다. 보유 기록은 그대로 유지됩니다.`,
      );
    } catch (watchError) {
      setError(readableError(watchError, "관심 상태를 변경하지 못했습니다."));
    }
  }

  function requestListWatchChange(stock: HoldingStock) {
    if (!stock.watch_enabled) {
      void changeWatch(stock, true);
      return;
    }
    if (stock.is_held) {
      void changeWatch(stock, false);
      return;
    }
    setRemoveTarget(stock);
  }

  async function resolveRegistrationReferencePrice() {
    if (!detail) return "";
    const analysisPrice = quantityNumber(detail.current_analysis?.reference_price ?? "");
    if (analysisPrice > 0) return String(Math.round(analysisPrice));

    try {
      const chart = await getHoldingChart(detail.stock_id, "1m");
      const latest = chart.bars.length > 0 ? chart.bars[chart.bars.length - 1] : undefined;
      const latestClose = quantityNumber(latest?.close ?? "");
      return latestClose > 0 ? String(Math.round(latestClose)) : "";
    } catch {
      return "";
    }
  }

  function setManualPriceByPercent(percent: number) {
    const base = quantityNumber(manualReferencePrice);
    if (base <= 0) return;
    setManualPrice(String(Math.max(1, Math.round(base * (1 + percent / 100)))));
  }

  function openQuickEdit(field: "quantity" | "average_price", position: HoldingPosition) {
    if (position.account_kind === "BROKER") {
      setError("증권사 연동 보유는 잔고 동기화로만 변경할 수 있습니다.");
      return;
    }
    const value = field === "quantity" ? position.quantity : position.average_price;
    setQuickEditPositionId(position.position_id);
    setQuickEditField(field);
    setQuickEditValue(value ?? "");
    setQuickEditBaseValue(value ?? "");
    setQuickZeroConfirm(false);
    setError(null);
    setMessage(null);
  }

  function closeQuickEdit() {
    if (quickEditBusy) return;
    setQuickEditPositionId(null);
    setQuickEditField(null);
    setQuickEditValue("");
    setQuickEditBaseValue("");
    setQuickZeroConfirm(false);
  }

  function adjustQuickQuantity(delta: number) {
    setQuickZeroConfirm(false);
    setQuickEditValue((value) => String(Math.max(0, quantityNumber(value) + delta)));
  }

  function adjustQuickPrice(percent: number) {
    setQuickEditValue((value) => {
      const current = quantityNumber(value) || quantityNumber(quickEditBaseValue);
      if (current <= 0) return value;
      return String(Math.max(1, Math.round(current * (1 + percent / 100))));
    });
  }

  function stopHoldRepeat(clearTriggered = false) {
    if (holdDelayRef.current != null) {
      window.clearTimeout(holdDelayRef.current);
      holdDelayRef.current = null;
    }
    if (holdIntervalRef.current != null) {
      window.clearInterval(holdIntervalRef.current);
      holdIntervalRef.current = null;
    }
    if (clearTriggered) holdTriggeredRef.current = false;
  }

  function startHoldRepeat(action: () => void) {
    stopHoldRepeat(true);
    holdDelayRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      action();
      holdIntervalRef.current = window.setInterval(action, 110);
    }, 350);
  }

  function runClickUnlessHeld(action: () => void) {
    if (holdTriggeredRef.current) {
      holdTriggeredRef.current = false;
      return;
    }
    action();
  }

  async function saveQuickEdit(confirmZero = false) {
    if (!detail || !quickEditPositionId || !quickEditField) return;
    const position = detail.positions.find((item) => item.position_id === quickEditPositionId);
    if (!position) {
      setError("수정할 보유 기록을 찾을 수 없습니다.");
      return;
    }
    if (position.account_kind === "BROKER") {
      setError("증권사 연동 보유는 잔고 동기화로만 변경할 수 있습니다.");
      return;
    }

    const next = quantityNumber(quickEditValue);
    if (quickEditField === "quantity" && next < 0) {
      setError("보유 수량은 0 이상이어야 합니다.");
      return;
    }
    if (quickEditField === "quantity" && next === 0 && !confirmZero) {
      setQuickZeroConfirm(true);
      return;
    }
    if (quickEditField === "average_price" && next <= 0) {
      setError("평균단가는 0보다 커야 합니다.");
      return;
    }

    setQuickEditBusy(true);
    setError(null);
    setMessage(null);
    try {
      await recordManualCorrection(position.position_id, {
        quantity: quickEditField === "quantity" ? quickEditValue : position.quantity,
        average_price: quickEditField === "average_price" ? quickEditValue : position.average_price,
        effective_at: toIso(localDateTimeValue()),
        note: quickEditField === "quantity" ? "보유 수량 직접 수정" : "평균단가 직접 수정",
      });
      const editedField = quickEditField;
      setQuickEditPositionId(null);
      setQuickEditField(null);
      setQuickEditValue("");
      setQuickEditBaseValue("");
      setQuickZeroConfirm(false);
      await Promise.all([reloadStocks(detail.stock_id), loadSelected(detail.stock_id)]);
      window.requestAnimationFrame(() => {
        holdingOverviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      setMessage(editedField === "quantity" ? "보유 수량을 수정했습니다." : "평균단가를 수정했습니다.");
    } catch (editError) {
      setError(readableError(editError, "보유 정보를 수정하지 못했습니다."));
    } finally {
      setQuickEditBusy(false);
    }
  }

  useEffect(() => () => stopHoldRepeat(true), []);

  useEffect(() => {
    if (!quickEditField || !quickEditPositionId) return;
    const frame = window.requestAnimationFrame(() => {
      quickEditPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      quickEditInputRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [quickEditField, quickEditPositionId]);

  async function openManual(mode: ManualMode, position?: HoldingPosition) {
    if (!detail) return;
    if (position?.account_kind === "BROKER") {
      setError("증권사 연동 보유는 잔고 동기화로만 변경할 수 있습니다.");
      return;
    }

    setManualMode(mode);
    setManualPositionId(position?.position_id ?? "");
    setManualAccountId(position?.account_id ?? "");
    setManualNote("");
    setManualAt(localDateTimeValue());
    setError(null);

    if (mode === "correction" && position) {
      setManualQuantity(position.quantity);
      setManualPrice(position.average_price ?? "");
      setManualReferencePrice(position.average_price ?? "");
    } else if (mode === "sell" && position) {
      setManualQuantity(quantityNumber(position.quantity) >= 1 ? "1" : position.quantity);
      setManualPrice("");
      setManualReferencePrice("");
    } else {
      const referencePrice = await resolveRegistrationReferencePrice();
      setManualQuantity("1");
      setManualPrice(referencePrice);
      setManualReferencePrice(referencePrice);
    }

    try {
      if (mode === "buy" && !position) {
        const rows = await listHoldingAccounts();
        setAccounts(rows);
        const manualAccounts = rows.filter(
          (account) => account.account_kind === "MANUAL" || account.account_kind === "VIRTUAL",
        );
        setManualAccountId(manualAccounts[0]?.id ?? "");
      } else {
        setAccounts([]);
      }
      setManualOpen(true);
    } catch (accountError) {
      setError(readableError(accountError, "보유 기록 계좌를 확인하지 못했습니다."));
    }
  }

  function adjustManualQuantity(delta: number) {
    setManualQuantity((value) => {
      const current = quantityNumber(value);
      let next = Math.max(0, current + delta);
      if (manualMode === "sell" && manualPosition) {
        next = Math.min(next, quantityNumber(manualPosition.quantity));
      }
      return String(next);
    });
  }

  function adjustManualPrice(percent: number) {
    setManualPrice((value) => {
      const current = quantityNumber(value) || quantityNumber(manualReferencePrice);
      if (current <= 0) return value;
      return String(Math.max(1, Math.round(current * (1 + percent / 100))));
    });
  }

  async function saveManual() {
    if (!detail) return;
    if (!manualQuantity.trim()) {
      setError("수량을 입력해주세요.");
      return;
    }
    if (manualMode !== "correction" && quantityNumber(manualQuantity) <= 0) {
      setError("수량은 0보다 크게 입력해주세요.");
      return;
    }
    if (manualMode === "sell" && manualPosition && quantityNumber(manualQuantity) > quantityNumber(manualPosition.quantity)) {
      setError(`매도 수량은 현재 보유 ${quantity(manualPosition.quantity)}주를 넘을 수 없습니다.`);
      return;
    }
    if (manualMode !== "correction" && !manualPrice.trim()) {
      setError("가격을 입력해주세요.");
      return;
    }
    if (manualMode === "correction" && !manualPrice.trim()) {
      setError("평균단가를 입력해주세요.");
      return;
    }
    if (manualMode === "correction" && !manualNote.trim()) {
      setError("보유 정보 수정에는 수정 사유가 필요합니다.");
      return;
    }

    setManualBusy(true);
    setError(null);
    try {
      if (manualMode === "buy") {
        await recordManualBuy({
          stock_id: detail.stock_id,
          account_id: manualAccountId || null,
          quantity: manualQuantity,
          unit_price: manualPrice,
          effective_at: toIso(manualAt),
          analysis_revision_id: analysisRevisionIdForTrade(detail.current_analysis, manualAt),
          note: manualNote.trim() || null,
        });
      } else if (manualMode === "sell") {
        await recordManualSell(manualPositionId, {
          quantity: manualQuantity,
          unit_price: manualPrice,
          effective_at: toIso(manualAt),
          note: manualNote.trim() || null,
        });
      } else {
        await recordManualCorrection(manualPositionId, {
          quantity: manualQuantity,
          average_price: manualPrice,
          effective_at: toIso(manualAt),
          note: manualNote.trim(),
        });
      }
      setManualOpen(false);
      await Promise.all([reloadStocks(detail.stock_id), loadSelected(detail.stock_id)]);
      window.requestAnimationFrame(() => {
        holdingOverviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      setMessage(
        manualMode === "buy"
          ? manualPosition
            ? `${manualQuantity}주를 추가했습니다. 보유 현황을 갱신했습니다.`
            : `${manualQuantity}주를 보유 종목으로 등록했습니다.`
          : manualMode === "sell"
            ? `${manualQuantity}주 매도를 기록했습니다. 보유 현황을 갱신했습니다.`
            : "StockScope에 저장된 보유 정보를 바로잡았습니다.",
      );
    } catch (manualError) {
      setError(readableError(manualError, "수동 기록을 저장하지 못했습니다."));
    } finally {
      setManualBusy(false);
    }
  }

  const selectedAnalysis = detail?.current_analysis ?? null;
  const detailPerspective: "watch" | "held" = stockFilter === "held"
    ? "held"
    : stockFilter === "watch"
      ? "watch"
      : detail?.is_held
        ? "held"
        : "watch";

  function openSelectedStockAnalysis() {
    if (!detail || !onAnalyzeStock) return;
    const market: "KOSPI" | "KOSDAQ" = detail.market === "KOSDAQ" ? "KOSDAQ" : "KOSPI";
    onAnalyzeStock({
      code: detail.ticker,
      standard_code: detail.ticker,
      name: detail.name,
      full_name: detail.name,
      english_name: "",
      market,
      market_name: market,
      security_group: "주식",
      section: "",
      stock_type: "보통주",
      listed_date: "",
      listed_shares: null,
      analysis_as_of_date: detail.current_analysis?.market_date ?? null,
    });
  }

  return (
    <div className="holdings-workspace">
      <section className="holdings-page-head">
        <div>
          <span className="eyebrow">HOLDINGS</span>
          <h1>내 종목 관리</h1>
          <p>관심 종목의 현재 판단과 실제 보유 상태, 손익과 보유분 관리 기준을 확인합니다.</p>
        </div>
        <button type="button" className="holdings-secondary" onClick={() => setAddOpen(true)}>
          + 종목 추가
        </button>
      </section>

      <section className="holdings-summary" aria-label="내 종목 요약">
        <div><span>관심 종목</span><strong>{summary.watched}</strong></div>
        <div><span>보유 종목</span><strong>{summary.held}</strong></div>
        <div><span>분석 완료</span><strong>{summary.analyzed}</strong></div>
        <div><span>분석 필요</span><strong>{summary.pending}</strong></div>
        <div><span>최근 분석일</span><strong className="date">{compactDate(summary.latest)}</strong></div>
      </section>

      {(message || error) && (
        <div className={`holdings-notice ${error ? "error" : ""}`} role="status">
          {error ?? message}
        </div>
      )}

      <section className="holdings-main-grid">
        <div className="holdings-left-column">
        <div className="holdings-list-pane">
          <div className="holdings-section-head">
            <div>
              <h2>내 종목 목록</h2>
              <span>{stocks.length}개 종목</span>
            </div>
          </div>

          <div className="holdings-filter-row">
            <div className="holdings-tabs" role="tablist" aria-label="종목 구분">
              <button className={stockFilter === "all" ? "active" : ""} onClick={() => setStockFilter("all")}>
                전체 {stocks.length}
              </button>
              <button className={stockFilter === "watch" ? "active" : ""} onClick={() => setStockFilter("watch")}>
                관심 {summary.watched}
              </button>
              <button className={stockFilter === "held" ? "active" : ""} onClick={() => setStockFilter("held")}>
                보유 {summary.held}
              </button>
            </div>
            <input
              className="holdings-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="종목명 또는 종목코드 검색"
              aria-label="내 종목 검색"
            />
          </div>

          {loadingStocks ? (
            <div className="holdings-empty">목록을 불러오는 중입니다.</div>
          ) : stocks.length === 0 ? (
            <div className="holdings-empty">
              <strong>아직 등록한 종목이 없습니다.</strong>
              <span>관심 있거나 보유한 종목을 추가해보세요.</span>
              <button className="holdings-primary" type="button" onClick={() => setAddOpen(true)}>종목 추가</button>
            </div>
          ) : (
            <div className="holdings-stock-table-wrap">
              <table className={`holdings-stock-table perspective-${stockFilter}`}>
                <thead>
                  {stockFilter === "watch" ? (
                    <tr>
                      <th>종목</th>
                      <th>분석 기준가</th>
                      <th>현재 판단</th>
                      <th>마지막 분석</th>
                      <th>상태</th>
                    </tr>
                  ) : stockFilter === "held" ? (
                    <tr>
                      <th>종목</th>
                      <th>보유 수량</th>
                      <th>평균단가</th>
                      <th>분석 기준가</th>
                      <th>관리 상태</th>
                    </tr>
                  ) : (
                    <tr>
                      <th>종목</th>
                      <th>상태</th>
                      <th>현재 판단</th>
                      <th>분석일</th>
                      <th>관리</th>
                    </tr>
                  )}
                </thead>
                <tbody>
                  {visibleStocks.map((stock) => {
                    const positionSummary = stockPositionListSummary(stock);
                    return (
                      <tr
                        key={stock.stock_id}
                        className={selectedStockId === stock.stock_id ? "selected" : ""}
                        onClick={() => setSelectedStockId(stock.stock_id)}
                      >
                        <td>
                          <strong>{stock.name}</strong>
                          <small>{stock.ticker} · {stock.market}</small>
                        </td>

                        {stockFilter === "watch" ? (
                          <>
                            <td className="holdings-price-cell">
                              <strong>{money(stock.current_analysis?.reference_price)}</strong>
                              <small>{compactDate(stock.current_analysis?.market_date)} 기준</small>
                            </td>
                            <td className="holdings-decision-cell">
                              <strong>{historyRecovery?.stockId === stock.stock_id ? "데이터 준비 필요" : stockDecisionText(stock)}</strong>
                              {stock.decision_context && isPlanEvent(stock.decision_context) && (
                                <small>{stock.decision_context.previous_plan.label}</small>
                              )}
                            </td>
                            <td>{compactDate(stock.current_analysis?.market_date)}</td>
                            <td className="holdings-state-cell">
                              <strong>{stock.is_held ? "관심 · 보유" : "관심"}</strong>
                              {stock.is_held ? (
                                <button
                                  type="button"
                                  className="holdings-list-action"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setSelectedStockId(stock.stock_id);
                                    setStockFilter("held");
                                  }}
                                >
                                  보유 관리
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="holdings-list-action remove"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    requestListWatchChange(stock);
                                  }}
                                >
                                  관심 해제
                                </button>
                              )}
                            </td>
                          </>
                        ) : stockFilter === "held" ? (
                          <>
                            <td className="holdings-holding-cell"><strong>{positionSummary.quantity}</strong></td>
                            <td className="holdings-holding-cell"><strong>{positionSummary.average}</strong></td>
                            <td className="holdings-price-cell">
                              <strong>{money(stock.current_analysis?.reference_price)}</strong>
                              <small>{compactDate(stock.current_analysis?.market_date)} 기준</small>
                            </td>
                            <td className="holdings-state-cell">
                              <strong>{stock.current_analysis ? "보유 관리 확인" : "분석 필요"}</strong>
                              <small>평가손익·적용 기준은 선택 후 확인</small>
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="holdings-state-cell"><strong>{stockStateLabel(stock)}</strong></td>
                            <td className="holdings-decision-cell">
                              <strong>{historyRecovery?.stockId === stock.stock_id ? "데이터 준비 필요" : stockDecisionText(stock)}</strong>
                              {stock.decision_context && isPlanEvent(stock.decision_context) && (
                                <small>{stock.decision_context.previous_plan.label}</small>
                              )}
                            </td>
                            <td>{compactDate(stock.current_analysis?.market_date)}</td>
                            <td>
                              <button
                                type="button"
                                className={`holdings-list-action ${stock.watch_enabled && !stock.is_held ? "remove" : ""}`}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  requestListWatchChange(stock);
                                }}
                              >
                                {!stock.watch_enabled ? "관심 등록" : stock.is_held ? "관심 해제" : "제거"}
                              </button>
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {visibleStocks.length === 0 && (
                <div className="holdings-empty compact holdings-perspective-empty">
                  <strong>
                    {stockFilter === "watch"
                      ? "관심 종목이 없습니다."
                      : stockFilter === "held"
                        ? "등록된 보유 종목이 없습니다."
                        : "조건에 맞는 종목이 없습니다."}
                  </strong>
                  <span>
                    {stockFilter === "watch"
                      ? "종목 후보 찾기에서 관심 종목을 추가하거나 직접 종목을 등록할 수 있습니다."
                      : stockFilter === "held"
                        ? "실제 보유 수량과 평균단가를 입력해 보유 관리를 시작할 수 있습니다."
                        : "검색어나 필터를 바꿔 다시 확인해주세요."}
                  </span>
                  {stockFilter !== "all" && (
                    <button className="holdings-secondary small" type="button" onClick={() => setAddOpen(true)}>
                      종목 추가
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
          
        </div>

        <div className="holdings-detail-pane">
          {!selectedStockId ? (
            <div className="holdings-empty detail">왼쪽에서 종목을 선택해주세요.</div>
          ) : loadingDetail && !detail ? (
            <div className="holdings-empty detail">종목 정보를 불러오는 중입니다.</div>
          ) : detail ? (
            <>
              <div className="holdings-detail-head">
                <div>
                  <div className="holdings-stock-title">
                    <h2>{detail.name}</h2>
                    <span>{detail.ticker} · {detail.market}</span>
                  </div>
                  <div className="holdings-type-line">
                    {detail.is_held && <span>보유 중</span>}
                    {detail.watch_enabled && <span>관심 종목</span>}
                  </div>
                </div>
                <div className="holdings-actions">
                  {onAnalyzeStock && (
                    <button className="holdings-secondary" type="button" onClick={openSelectedStockAnalysis}>
                      종목 분석 보기
                    </button>
                  )}
                  <button className="holdings-primary" type="button" onClick={refreshSelected} disabled={refreshingAnalysis}>
                    {refreshingAnalysis ? "분석 확인 중" : "분석 새로고침"}
                  </button>
                  {detailPerspective === "watch" ? (
                    <>
                      {detail.is_held ? (
                        <button className="holdings-secondary" type="button" onClick={() => setStockFilter("held")}>
                          보유 관리 보기
                        </button>
                      ) : (
                        <button className="holdings-secondary" type="button" onClick={openExistingHoldingRegistration}>
                          기존 보유 등록
                        </button>
                      )}
                      {detail.watch_enabled && (
                        <button className="holdings-text-button" type="button" onClick={() => requestListWatchChange(detail)}>
                          관심 해제
                        </button>
                      )}
                    </>
                  ) : (
                    <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>
                      {syncingKis ? "동기화 중" : "잔고 동기화"}
                    </button>
                  )}
                </div>
              </div>

              {historyRecovery?.stockId === detail.stock_id && (
                <div className={`holdings-history-recovery ${historyRecovery.exhausted ? "exhausted" : ""}`} role="status">
                  <div>
                    <strong>분석에 필요한 과거 가격 데이터가 부족합니다.</strong>
                    <p>
                      {historyRecovery.exhausted
                        ? "현재 준비 가능한 범위를 확인했지만 분석 기준에는 아직 부족합니다. 신규 상장 종목처럼 실제 거래 이력이 짧은 경우에는 더 많은 기간을 만들 수 없습니다."
                        : "이 종목에 필요한 과거 가격 데이터만 준비한 뒤 분석을 이어갈 수 있습니다."}
                    </p>
                    {historyRecovery.currentRows != null && historyRecovery.requiredRows != null && (
                      <small>확보 {historyRecovery.currentRows}거래일 · 필요 {historyRecovery.requiredRows}거래일</small>
                    )}
                  </div>
                  <div className="holdings-history-recovery-action">
                    {preparingHistory && historyProgress && (
                      <div className="holdings-history-progress" aria-live="polite">
                        <strong>{historyProgress.message}</strong>
                        {historyProgress.stock_required != null && (
                          <span>
                            종목 가격 {historyProgress.stock_current ?? 0}/{historyProgress.stock_required}거래일
                          </span>
                        )}
                        {historyProgress.index_required != null && (
                          <span>
                            시장지수 {historyProgress.index_current ?? 0}/{historyProgress.index_required}거래일
                          </span>
                        )}
                      </div>
                    )}
                    <button
                      className="holdings-primary small holdings-history-recovery-button"
                      type="button"
                      onClick={() => void prepareHistoryAndAnalyze()}
                      disabled={preparingHistory || refreshingAnalysis}
                    >
                      {preparingHistory
                        ? "준비 중..."
                        : historyRecovery.exhausted
                          ? "다시 확인"
                          : "데이터 준비 후 분석"}
                    </button>
                  </div>
                </div>
              )}

              {detailPerspective === "watch" && (
                <section className="holdings-watch-overview" aria-label="관심 종목 현재 판단">
                  <div className="holdings-watch-overview-head">
                    <div>
                      <span>현재 판단</span>
                      <strong>{detail.decision_context?.entry.label ?? stockDecisionText(detail)}</strong>
                      <p>{detail.decision_context?.entry.summary || detail.decision_context?.entry.decision_reason || "최신 분석에서 현재 조건을 확인하세요."}</p>
                    </div>
                    <div className="holdings-watch-date">
                      <span>분석 기준일</span>
                      <strong>{compactDate(selectedAnalysis?.market_date)}</strong>
                    </div>
                  </div>
                  <div className="holdings-watch-metrics">
                    <div><span>분석 기준가</span><strong>{money(selectedAnalysis?.reference_price)}</strong></div>
                    <div><span>전략</span><strong>{selectedAnalysis ? (strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key) : "분석 필요"}</strong></div>
                    <div><span>마지막 분석</span><strong>{compactDate(selectedAnalysis?.market_date)}</strong></div>
                  </div>
                  {detail.is_held && (
                    <div className="holdings-watch-held-bridge">
                      <span>이 종목은 현재 보유 중입니다. 관심 관점과 실제 보유 관리는 분리해서 확인합니다.</span>
                      <button type="button" className="holdings-text-button" onClick={() => setStockFilter("held")}>보유 관리 보기</button>
                    </div>
                  )}
                </section>
              )}

              {detailPerspective === "held" && (
                <div className="holdings-position-management" ref={holdingOverviewRef}>
                  <div className="holdings-position-quickbar" aria-label="보유 빠른 관리">
                    {detail.positions.length === 0 ? (
                      <>
                        <div className="holdings-position-quick-status">
                          <span>보유 상태</span>
                          <strong>미보유</strong>
                        </div>
                        <small className="holdings-quickbar-note">신규 종목은 ‘종목 추가’에서 관심/보유를 처음부터 선택할 수 있습니다.</small>
                      </>
                    ) : detail.positions.length === 1 && singlePosition ? (
                      <>
                        {singleEditablePosition ? (
                          <>
                            <button
                              type="button"
                              className={`holdings-direct-value ${quickEditField === "quantity" && quickEditPositionId === singleEditablePosition.position_id ? "active-edit" : ""}`}
                              aria-pressed={quickEditField === "quantity" && quickEditPositionId === singleEditablePosition.position_id}
                              onClick={() => openQuickEdit("quantity", singleEditablePosition)}
                            >
                              <span>보유 수량</span>
                              <strong>{quantity(singleEditablePosition.quantity)}주</strong>
                              <small>숫자를 눌러 바로 수정</small>
                            </button>
                            <button
                              type="button"
                              className={`holdings-direct-value ${quickEditField === "average_price" && quickEditPositionId === singleEditablePosition.position_id ? "active-edit" : ""}`}
                              aria-pressed={quickEditField === "average_price" && quickEditPositionId === singleEditablePosition.position_id}
                              onClick={() => openQuickEdit("average_price", singleEditablePosition)}
                            >
                              <span>평균단가</span>
                              <strong>{money(singleEditablePosition.average_price)}</strong>
                              <small>숫자를 눌러 바로 수정</small>
                            </button>
                          </>
                        ) : (
                          <>
                            <div className="holdings-direct-value readonly">
                              <span>보유 수량</span>
                              <strong>{quantity(singlePosition.quantity)}주</strong>
                            </div>
                            <div className="holdings-direct-value readonly">
                              <span>평균단가</span>
                              <strong>{money(singlePosition.average_price)}</strong>
                            </div>
                            <small className="holdings-quickbar-note">증권사 연동 보유는 잔고 동기화로 갱신됩니다.</small>
                          </>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="holdings-position-quick-status">
                          <span>총 보유</span>
                          <strong>{quantity(String(totalHeldQuantity))}주</strong>
                        </div>
                        <div className="holdings-position-quick-status">
                          <span>보유 기록</span>
                          <strong>{detail.positions.length}개</strong>
                        </div>
                        <button
                          type="button"
                          className="holdings-text-button holdings-nowrap-action"
                          onClick={() => document.getElementById("holdings-position-details")?.scrollIntoView({ behavior: "smooth", block: "start" })}
                        >
                          계좌별 보유 보기
                        </button>
                      </>
                    )}
                  </div>
  
                  {performance && performance.positions.length > 0 && (
                    <div className="holdings-pnl-block" aria-label="보유 손익">
                      <div className="holdings-pnl-head">
                        <div>
                          <strong>보유 손익</strong>
                          <span>비용 제외 · {performanceStatusText(performance.calculation_status)}</span>
                        </div>
                        <span>
                          {performance.valuation.available && performance.valuation.market_date
                            ? `${compactDate(performance.valuation.market_date)} 확정 종가 기준`
                            : "최신 확정 가격 없음"}
                        </span>
                      </div>
  
                      {performance.positions.length === 1 ? (() => {
                        const pnl = performance.positions[0];
                        return (
                          <>
                            <div className="holdings-pnl-metrics">
                              <div><span>잔여 원가</span><strong>{money(pnl.cost_basis)}</strong></div>
                              <div><span>평가 금액</span><strong>{money(pnl.market_value)}</strong></div>
                              <div className="holdings-pnl-focus">
                                <span>평가 손익</span>
                                <strong className={pnlSignClass(pnl.unrealized_pnl)}>
                                  {signedMoney(pnl.unrealized_pnl)}
                                  {pnl.unrealized_return_pct != null && <small>{signedPercent(pnl.unrealized_return_pct)}</small>}
                                </strong>
                              </div>
                              <div>
                                <span>확인된 실현손익</span>
                                <strong className={pnlSignClass(pnl.confirmed_realized_pnl)}>
                                  {pnl.confirmed_realized_pnl == null ? "미확인" : signedMoney(pnl.confirmed_realized_pnl)}
                                </strong>
                              </div>
                              <div>
                                <span>기록 기준 손익</span>
                                <strong className={pnlSignClass(pnl.tracked_pnl)}>
                                  {pnl.tracked_pnl == null ? "-" : signedMoney(pnl.tracked_pnl)}
                                </strong>
                              </div>
                            </div>
                            <div className="holdings-pnl-note">
                              <span>{pnl.calculation_message}</span>
                              {performance.valuation.available && performance.valuation.price && (
                                <span>평가가격 {money(performance.valuation.price)}</span>
                              )}
                            </div>
                          </>
                        );
                      })() : (
                        <div className="holdings-pnl-position-table-wrap">
                          <table className="holdings-pnl-position-table">
                            <thead><tr><th>계좌</th><th>수량</th><th>평가손익</th><th>실현손익</th><th>범위</th></tr></thead>
                            <tbody>
                              {performance.positions.map((pnl) => (
                                <tr key={pnl.position_id}>
                                  <td>{pnl.account_name || pnl.provider}</td>
                                  <td>{quantity(pnl.quantity)}주</td>
                                  <td className={pnlSignClass(pnl.unrealized_pnl)}>{signedMoney(pnl.unrealized_pnl)}</td>
                                  <td className={pnlSignClass(pnl.confirmed_realized_pnl)}>
                                    {pnl.confirmed_realized_pnl == null ? "미확인" : signedMoney(pnl.confirmed_realized_pnl)}
                                  </td>
                                  <td>{performanceStatusText(pnl.calculation_status)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {performance.aggregate.potential_overlap && (
                            <div className="holdings-pnl-warning">
                              수동 보유와 증권사 보유가 함께 있어 종목 합계를 실제 자산 합계로 단정하지 않습니다.
                            </div>
                          )}
                        </div>
                      )}
  
                      {!performance.valuation.available && (
                        <div className="holdings-pnl-warning">
                          평가손익을 0원으로 대체하지 않았습니다. {performance.valuation.message || "최신 확정 가격이 필요합니다."}
                        </div>
                      )}
                    </div>
                  )}


                {management && management.positions.length > 0 && (
                  <div className="holdings-management-block" aria-label="보유분 관리 기준">
                    <div className="holdings-management-head">
                      <div>
                        <strong>보유분 관리 기준</strong>
                        <span>
                          현재 보유분에 실제 적용 중인 손절·목표 가격
                          {management.valuation.market_date ? ` · ${compactDate(management.valuation.market_date)} 확정 종가 기준` : " · 현재 가격 데이터 확인 필요"}
                        </span>
                      </div>
                    </div>
                    {management.positions.map((item) => (
                      <div className="holdings-management-position" key={item.position_id}>
                        <div className="holdings-management-status">
                          <div><span>{item.account_name || item.provider || "보유 기록"}</span><strong>{managementStateText(item.management_state)}</strong></div>
                          {management.valuation.price && <span>기준 가격 {money(management.valuation.price)}</span>}
                        </div>
                        {item.active_plan ? (
                          <div className="holdings-management-plan-grid">
                            <div><span>적용 기준일</span><strong>{compactDate(item.active_plan.applied_at)}</strong></div>
                            <div><span>손절</span><strong>{money(item.active_plan.stop_price)}</strong></div>
                            <div><span>1차 목표</span><strong>{money(item.active_plan.target1_price)}</strong></div>
                            <div><span>2차 목표</span><strong>{money(item.active_plan.target2_price)}</strong></div>
                          </div>
                        ) : <div className="holdings-management-empty">현재 적용 중인 보유분 관리 기준이 없습니다. 최신 분석에 적용 가능한 제안이 있다면 아래에서 확인 후 직접 적용할 수 있습니다.</div>}
                        {item.active_plan && <small className="holdings-management-version">기술 정보 · 내부 기준 v{item.active_plan.version}</small>}
                        <div className="holdings-management-proposal">
                          <div>
                            <span className="holdings-management-proposal-kicker">최신 분석 제안</span>
                            <span>{proposalStateText(item.proposal.state)}</span>
                            {item.proposal.analysis_revision_id && <strong>손절 {money(item.proposal.stop_price)} · 1차 {money(item.proposal.target1_price)} · 2차 {money(item.proposal.target2_price)}</strong>}
                            {item.proposal.reason && <small>{item.proposal.reason}</small>}
                          </div>
                          {item.proposal.analysis_revision_id && item.proposal.state !== "SAME_AS_ACTIVE" && item.proposal.can_apply && (
                            <button type="button" className="holdings-secondary-button" disabled={applyingPlanId === item.position_id}
                              onClick={() => void applyLatestManagementPlan(item.position_id, item.proposal.analysis_revision_id as string)}>
                              {applyingPlanId === item.position_id ? "적용 중..." : "이 계획 적용"}
                            </button>
                          )}
                          {item.proposal.analysis_revision_id && item.proposal.state !== "SAME_AS_ACTIVE" && !item.proposal.can_apply && (
                            <span className="holdings-management-cannot-apply">현재 적용할 수 없는 제안입니다.</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="holdings-position-actions-primary" aria-label="보유 작업">
                  <span>보유 작업</span>
                  {detail.positions.length === 1 && singleEditablePosition ? (
                    <div>
                      <button type="button" className="holdings-action-button buy" onClick={() => void openManual("buy", singleEditablePosition)}>+ 추가 매수 기록</button>
                      <button type="button" className="holdings-action-button sell" onClick={() => void openManual("sell", singleEditablePosition)}>매도 기록</button>
                      <button type="button" className="holdings-action-button correction" onClick={() => void openManual("correction", singleEditablePosition)}>보유 정보 수정</button>
                    </div>
                  ) : detail.positions.length === 1 && singlePosition ? (
                    <div>
                      <button type="button" onClick={() => void syncKis()} disabled={syncingKis}>
                        {syncingKis ? "동기화 중" : "잔고 동기화"}
                      </button>
                      <small>증권사 연동 보유는 직접 수정하지 않습니다.</small>
                    </div>
                  ) : detail.positions.length > 1 ? (
                    <div>
                      <button type="button" onClick={() => document.getElementById("holdings-position-details")?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                        계좌별 보유 보기
                      </button>
                    </div>
                  ) : (
                    <small>현재 보유 기록이 없습니다.</small>
                  )}
                </div>

                {quickEditField && quickEditPositionId && singleEditablePosition?.position_id === quickEditPositionId && (
                  <div
                    ref={quickEditPanelRef}
                    className="holdings-inline-position-editor"
                    tabIndex={-1}
                    aria-label={quickEditField === "quantity" ? "보유 수량 바로 수정" : "평균단가 바로 수정"}
                  >
                    <div className="holdings-inline-editor-head">
                      <strong>{quickEditField === "quantity" ? "보유 수량 바로 수정" : "평균단가 바로 수정"}</strong>
                      <button type="button" className="holdings-inline-close" onClick={closeQuickEdit} disabled={quickEditBusy}>닫기</button>
                    </div>

                    {quickEditField === "quantity" ? (
                      <>
                        <div className="holdings-adjust-buttons" aria-label="보유 수량 빠른 조정">
                          {[-10, -5, -1, 1, 5, 10].map((delta) => (
                            <button
                              key={delta}
                              type="button"
                              onPointerDown={() => startHoldRepeat(() => adjustQuickQuantity(delta))}
                              onPointerUp={() => stopHoldRepeat(false)}
                              onPointerLeave={() => stopHoldRepeat(true)}
                              onPointerCancel={() => stopHoldRepeat(true)}
                              onClick={() => runClickUnlessHeld(() => adjustQuickQuantity(delta))}
                              onContextMenu={(event) => event.preventDefault()}
                              disabled={delta < 0 && quantityNumber(quickEditValue) <= 0}
                            >
                              {delta > 0 ? `+${delta}` : delta}
                            </button>
                          ))}
                        </div>
                        <div className="holdings-editable-number inline">
                          <input
                            ref={quickEditInputRef}
                            value={quickEditValue}
                            onChange={(event) => { setQuickEditValue(event.target.value); setQuickZeroConfirm(false); }}
                            inputMode="decimal"
                            aria-label="변경할 보유 수량"
                          />
                          <span>주</span>
                        </div>
                        <small className="holdings-hold-hint">버튼은 짧게 누르면 1회, 약 0.35초 이상 누르면 연속으로 증감합니다.</small>
                      </>
                    ) : (
                      <>
                        <div className="holdings-adjust-buttons price" aria-label="평균단가 빠른 조정">
                          {[-5, -1].map((percent) => (
                            <button
                              key={percent}
                              type="button"
                              onPointerDown={() => startHoldRepeat(() => adjustQuickPrice(percent))}
                              onPointerUp={() => stopHoldRepeat(false)}
                              onPointerLeave={() => stopHoldRepeat(true)}
                              onPointerCancel={() => stopHoldRepeat(true)}
                              onClick={() => runClickUnlessHeld(() => adjustQuickPrice(percent))}
                              onContextMenu={(event) => event.preventDefault()}
                            >
                              {percent}%
                            </button>
                          ))}
                          <button type="button" onClick={() => setQuickEditValue(quickEditBaseValue)}>현재값</button>
                          {[1, 5].map((percent) => (
                            <button
                              key={percent}
                              type="button"
                              onPointerDown={() => startHoldRepeat(() => adjustQuickPrice(percent))}
                              onPointerUp={() => stopHoldRepeat(false)}
                              onPointerLeave={() => stopHoldRepeat(true)}
                              onPointerCancel={() => stopHoldRepeat(true)}
                              onClick={() => runClickUnlessHeld(() => adjustQuickPrice(percent))}
                              onContextMenu={(event) => event.preventDefault()}
                            >
                              +{percent}%
                            </button>
                          ))}
                        </div>
                        <div className="holdings-editable-number inline">
                          <input ref={quickEditInputRef} value={quickEditValue} onChange={(event) => setQuickEditValue(event.target.value)} inputMode="decimal" aria-label="변경할 평균단가" />
                          <span>원</span>
                        </div>
                        <small className="holdings-hold-hint">평균단가 +/- 버튼도 약 0.35초 이상 누르면 현재 표시값 기준으로 계속 증감합니다.</small>
                      </>
                    )}

                    <small className="holdings-editor-meaning">
                      실제 매수·매도 기록이 아니라 StockScope의 현재 보유 정보를 바로잡습니다.
                    </small>

                    {quickZeroConfirm ? (
                      <div className="holdings-zero-confirm">
                        <span>0주로 변경하면 현재 수동 보유 기록이 종료됩니다.</span>
                        <div>
                          <button type="button" className="holdings-secondary small" onClick={() => setQuickZeroConfirm(false)}>계속 수정</button>
                          <button type="button" className="holdings-remove-confirm" onClick={() => void saveQuickEdit(true)} disabled={quickEditBusy}>0주로 변경</button>
                        </div>
                      </div>
                    ) : (
                      <div className="holdings-inline-editor-actions">
                        <button type="button" className="holdings-secondary small" onClick={closeQuickEdit} disabled={quickEditBusy}>취소</button>
                        <button type="button" className="holdings-primary small holdings-nowrap-action" onClick={() => void saveQuickEdit()} disabled={quickEditBusy}>
                          {quickEditBusy ? "적용 중" : "적용"}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              <section className={`holdings-positions ${detail.positions.length <= 1 ? "single-hidden" : ""}`} id="holdings-position-details">
                <div className="holdings-block-title">
                  <div>
                    <h3>계좌별 보유</h3>
                    <span>계좌별 보유 상태와 거래 기록을 구분해 관리합니다.</span>
                  </div>
                </div>

                {detail.positions.length === 0 ? (
                  <div className="holdings-inline-empty">
                    <span>현재 보유 기록이 없습니다. 위의 보유 등록에서 바로 추가할 수 있습니다.</span>
                  </div>
                ) : (
                  <div className="holdings-position-list">
                    {detail.positions.map((position) => (
                      <article key={position.position_id} className="holdings-position-row">
                        <div>
                          <strong>{position.account_name || (position.provider === "KIS" ? "한국투자증권" : "수동 기록")}</strong>
                          <small>{position.account_kind === "BROKER" ? "증권사 연동 보유" : "StockScope 내부 보유 기록"}</small>
                        </div>
                        <div><span>수량</span><strong>{quantity(position.quantity)}주</strong></div>
                        <div><span>평균단가</span><strong>{money(position.average_price)}</strong></div>
                        {position.account_kind === "BROKER" ? (
                          <span className="holdings-position-broker-note">잔고 동기화로 갱신됩니다.</span>
                        ) : (
                          <div className="holdings-position-actions">
                            <button type="button" onClick={() => void openManual("buy", position)}>추가 매수 기록</button>
                            <button type="button" onClick={() => void openManual("sell", position)}>매도 기록</button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>

  
                </div>
  
                )}

              <HoldingsPriceChart
                stockId={detail.stock_id}
                analysis={selectedAnalysis}
                refreshKey={chartRefreshKey}
                decisionContext={detail.decision_context}
              />

              <StockNewsPanel
                code={detail.ticker}
                market={detail.market === "KOSDAQ" ? "KOSDAQ" : "KOSPI"}
                companyLabel={detail.name}
                variant="compact"
              />

              <details
                className={`holdings-analysis-disclosure perspective-${detailPerspective}`}
                open={detailPerspective === "watch" ? true : undefined}
              >
                {detailPerspective === "held" && (
                  <summary>
                    <span>추가 매수·신규 진입 관점 보기</span>
                    <small>기존 보유분 관리와 분리된 보조 분석</small>
                  </summary>
                )}
                <div className="holdings-analysis-disclosure-body">
              <div className="holdings-analysis-grid">
                <section className="holdings-analysis-block">
                  <div className="holdings-block-title">
                    <h3>{detailPerspective === "held" ? "추가 매수·신규 진입 관점" : "현재 판단 상세"}</h3>
                  </div>
                  {selectedAnalysis ? (
                    <>
                      {detailPerspective === "held" && (
                        <div className="holdings-entry-guardrail">
                          현재 시점에 새 물량을 추가한다고 가정한 분석입니다. 기존 보유분의 매도 판단이나 적용 중인 관리 기준을 변경하지 않습니다.
                        </div>
                      )}
                      <dl className="holdings-key-values">
                        <div>
                          <dt>진입 상태</dt>
                          <dd>
                            {detail.decision_context?.entry.label
                              ?? actionLabel[selectedAnalysis.action_state]
                              ?? selectedAnalysis.action_state}
                          </dd>
                        </div>
                        <div><dt>현재 전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>
                        <div><dt>전략 변화</dt><dd>{strategyChangeText(detail.decision_context)}</dd></div>
                        <div>
                          <dt>가격 계획</dt>
                          <dd className={`holdings-plan-text ${planStateClass(detail.decision_context)}`}>
                            {detail.decision_context?.previous_plan.label ?? "가격 계획 확인 필요"}
                          </dd>
                        </div>
                        {detail.is_held && (
                          <div><dt>보유 관리</dt><dd>{holdingManagementText(detail.decision_context)}</dd></div>
                        )}
                        <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>
                        <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>
                      </dl>

                      <div className="holdings-decision-explain">
                        <p>{entryGuidanceText(detail.decision_context)}</p>
                        {planGuidanceText(detail.decision_context, selectedAnalysis.market_date) && (
                          <p className="holdings-plan-guidance">
                            {planGuidanceText(detail.decision_context, selectedAnalysis.market_date)}
                          </p>
                        )}

                        <div className="holdings-decision-actions">
                          {(detail.decision_context?.entry.missing_details.length ?? 0) > 0 && (
                            <button
                              type="button"
                              className="holdings-inline-toggle"
                              onClick={() => setShowMissingConditions((value) => !value)}
                            >
                              {showMissingConditions
                                ? "부족한 조건 닫기"
                                : `부족한 조건 ${detail.decision_context?.entry.missing_details.length ?? 0}개 보기`}
                            </button>
                          )}
                          {previousPlanActionLabel(detail.decision_context) && (
                            <button
                              type="button"
                              className="holdings-inline-toggle"
                              onClick={() => setShowPreviousPlan((value) => !value)}
                            >
                              {showPreviousPlan
                                ? "이전 분석 비교 닫기"
                                : previousPlanActionLabel(detail.decision_context)}
                            </button>
                          )}
                        </div>

                        {showMissingConditions && detail.decision_context && (
                          <div className="holdings-decision-expand">
                            <strong>부족한 조건</strong>
                            {detail.decision_context.entry.missing_details.map((condition, index) => (
                              <div className="holdings-condition-row" key={`${condition.raw ?? condition.label}-${index}`}>
                                <strong>{condition.label}</strong>
                                {(condition.current_value || condition.required_value) && (
                                  <span>
                                    {condition.current_value ? `현재 ${condition.current_value}` : ""}
                                    {condition.current_value && condition.required_value ? " · " : ""}
                                    {condition.required_value ? `필요 ${condition.required_value}` : ""}
                                  </span>
                                )}
                                {condition.detail && <small>{condition.detail}</small>}
                              </div>
                            ))}
                          </div>
                        )}

                        {showPreviousPlan && detail.decision_context?.previous_plan.previous_market_date && (
                          <div className="holdings-decision-expand">
                            <strong>
                              이전 분석 · {compactDate(detail.decision_context.previous_plan.previous_market_date)}
                            </strong>
                            <dl className="holdings-previous-plan">
                              <div><dt>기준가</dt><dd>{money(detail.decision_context.previous_plan.previous_reference_price)}</dd></div>
                              <div><dt>손절 기준</dt><dd>{money(detail.decision_context.previous_plan.previous_stop_price)}</dd></div>
                              <div><dt>1차 목표</dt><dd>{money(detail.decision_context.previous_plan.previous_target1_price)}</dd></div>
                              <div><dt>2차 목표</dt><dd>{money(detail.decision_context.previous_plan.previous_target2_price)}</dd></div>
                              <div><dt>현재 확정 종가</dt><dd>{money(detail.decision_context.previous_plan.current_close)}</dd></div>
                            </dl>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="holdings-inline-empty">
                      <span>아직 저장된 분석이 없습니다.</span>
                      <button className="holdings-primary small" type="button" onClick={refreshSelected}>분석 실행</button>
                    </div>
                  )}
                </section>

                <section className="holdings-analysis-block">
                  <h3>{detailPerspective === "held" ? "신규 진입 기준 가격" : "주요 가격"}</h3>
                  <dl className="holdings-price-list">
                    <div><dt>기준가</dt><dd>{money(selectedAnalysis?.reference_price)}</dd></div>
                    <div><dt>손절 기준</dt><dd>{money(selectedAnalysis?.stop_price)}</dd></div>
                    <div><dt>1차 목표</dt><dd>{money(selectedAnalysis?.target1_price)}</dd></div>
                    <div><dt>2차 목표</dt><dd>{money(selectedAnalysis?.target2_price)}</dd></div>
                  </dl>
                </section>
              </div>

              <div className="holdings-basis-note">
                {detailPerspective === "held"
                  ? "이 보조 분석의 가격은 신규 물량 기준입니다. 실제 적용 중인 보유분 관리 기준은 위의 ‘보유분 관리 기준’을 우선 확인하세요."
                  : "현재 판단은 최신 EOD 분석 기준이며 실제 매수 여부는 사용자가 별도로 결정합니다."}
              </div>
                </div>
              </details>

            </>
          ) : null}
        </div>
      </section>

      <section className="holdings-timeline-pane">
        <div className="holdings-section-head">
          <div>
            <h2>최근 변화</h2>
            <span>선택한 종목의 분석과 실제 보유 기록을 시간순으로 확인합니다.</span>
          </div>
          <div className="holdings-tabs compact" role="tablist" aria-label="최근 변화 필터">
            <button className={timelineFilter === "all" ? "active" : ""} onClick={() => setTimelineFilter("all")}>전체</button>
            <button className={timelineFilter === "analysis" ? "active" : ""} onClick={() => setTimelineFilter("analysis")}>분석</button>
            <button className={timelineFilter === "position" ? "active" : ""} onClick={() => setTimelineFilter("position")}>보유 기록</button>
          </div>
        </div>
        {selectedStockId && visibleTimeline.length > 0 ? (
          <div className="holdings-timeline-table-wrap">
            <table className="holdings-timeline-table">
              <thead><tr><th>일시</th><th>종류</th><th>내용</th><th>기준일</th></tr></thead>
              <tbody>
                {visibleTimeline.map((item, index) => (
                  <tr key={`${item.occurred_at}-${item.analysis_revision_id ?? item.position_id ?? index}`}>
                    <td>{compactDateTime(item.occurred_at)}</td>
                    <td>{timelineLabel(item)}</td>
                    <td>{timelineDescription(item)}</td>
                    <td>{compactDate(item.market_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="holdings-empty compact">
            {selectedStockId ? "아직 표시할 변화 기록이 없습니다." : "종목을 선택하면 변화 기록을 확인할 수 있습니다."}
          </div>
        )}
      </section>

      {removeTarget && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setRemoveTarget(null)}>
          <div className="holdings-dialog holdings-remove-dialog" role="dialog" aria-modal="true" aria-label="목록에서 제거" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>목록에서 제거</h2>
                <p>{removeTarget.name}을(를) 내 종목 목록에서 제거할까요?</p>
              </div>
              <button type="button" onClick={() => setRemoveTarget(null)} aria-label="닫기">×</button>
            </div>
            <div className="holdings-remove-copy">저장된 분석 기록과 과거 변화 기록은 삭제되지 않습니다.</div>
            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setRemoveTarget(null)}>취소</button>
              <button type="button" className="holdings-remove-confirm" onClick={() => void changeWatch(removeTarget, false, true)}>제거</button>
            </div>
          </div>
        </div>
      )}

      {addOpen && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={closeAddDialog}>
          <div className="holdings-dialog holdings-add-dialog" role="dialog" aria-modal="true" aria-label="종목 추가" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>종목 추가</h2>
                <p>{addSelectedStock ? (addMode === "held" ? "이미 보유 중인 상태를 StockScope의 시작 보유 상태로 등록합니다." : "관심종목인지 기존 보유 등록인지 선택하세요.") : "종목명이나 종목코드로 검색한 뒤 선택하세요."}</p>
              </div>
              <button type="button" onClick={closeAddDialog} aria-label="닫기" disabled={addBusy}>×</button>
            </div>

            {!addSelectedStock ? (
              <>
                <input
                  autoFocus
                  value={addQuery}
                  onChange={(event) => setAddQuery(event.target.value)}
                  placeholder="예: 삼성전자 또는 005930"
                />
                <div className="holdings-picker-list">
                  {addSearching ? (
                    <div className="holdings-empty compact">검색 중입니다.</div>
                  ) : addQuery.trim().length < 2 ? (
                    <div className="holdings-empty compact">두 글자 이상 입력해주세요.</div>
                  ) : addResults.length === 0 ? (
                    <div className="holdings-empty compact">검색 결과가 없습니다.</div>
                  ) : (
                    addResults.map((item) => (
                      <button key={`${item.market}-${item.code}`} type="button" onClick={() => void selectAddStock(item)}>
                        <span><strong>{item.name}</strong><small>{item.code}</small></span>
                        <b>{item.market}</b>
                      </button>
                    ))
                  )}
                </div>
              </>
            ) : (
              <div className="holdings-add-selected">
                <div className="holdings-add-stock-head">
                  <div>
                    <strong>{addSelectedStock.name}</strong>
                    <span>{addSelectedStock.code} · {addSelectedStock.market}</span>
                  </div>
                  <button type="button" className="holdings-inline-toggle" onClick={() => { setAddSelectedStock(null); setAddMode(null); setAddQuery(""); }} disabled={addBusy}>다른 종목 선택</button>
                </div>

                <div className="holdings-add-type">
                  <span>등록 유형</span>
                  <div>
                    <button type="button" className="holdings-secondary" onClick={() => void addSelectedAsWatch()} disabled={addBusy}>관심종목</button>
                    <button type="button" className={addMode === "held" ? "holdings-primary" : "holdings-secondary"} onClick={() => { setAddMode("held"); setAddEffectiveAt(localDateTimeValue()); }} disabled={addBusy}>기존 보유 등록</button>
                  </div>
                </div>

                {addMode === "held" && (
                  <div className="holdings-add-held-form">
                    <label>
                      <span>보유 수량</span>
                      <div className="holdings-adjust-buttons" aria-label="신규 보유 수량 빠른 조정">
                        {[-10, -5, -1, 1, 5, 10].map((delta) => (
                          <button
                            key={delta}
                            type="button"
                            onPointerDown={() => startHoldRepeat(() => adjustAddQuantity(delta))}
                            onPointerUp={() => stopHoldRepeat(false)}
                            onPointerLeave={() => stopHoldRepeat(true)}
                            onPointerCancel={() => stopHoldRepeat(true)}
                            onClick={() => runClickUnlessHeld(() => adjustAddQuantity(delta))}
                            onContextMenu={(event) => event.preventDefault()}
                            disabled={delta < 0 && quantityNumber(addQuantity) <= 1}
                          >
                            {delta > 0 ? `+${delta}` : delta}
                          </button>
                        ))}
                      </div>
                      <div className="holdings-editable-number inline">
                        <input value={addQuantity} onChange={(event) => setAddQuantity(event.target.value)} inputMode="decimal" aria-label="신규 보유 수량" />
                        <span>주</span>
                      </div>
                      <small className="holdings-hold-hint">+ / - 버튼을 길게 누르면 같은 단위로 계속 증감합니다.</small>
                    </label>

                    <label>
                      <span>평균단가</span>
                      {addReferencePrice && (
                        <div className="holdings-adjust-buttons price" aria-label="신규 평균단가 빠른 조정">
                          {[-5, -1].map((percent) => (
                            <button
                              key={percent}
                              type="button"
                              onPointerDown={() => startHoldRepeat(() => setAddPriceByPercent(percent))}
                              onPointerUp={() => stopHoldRepeat(false)}
                              onPointerLeave={() => stopHoldRepeat(true)}
                              onPointerCancel={() => stopHoldRepeat(true)}
                              onClick={() => runClickUnlessHeld(() => setAddPriceByPercent(percent))}
                              onContextMenu={(event) => event.preventDefault()}
                            >
                              {percent}%
                            </button>
                          ))}
                          <button type="button" onClick={() => setAddAveragePrice(addReferencePrice)}>기준가</button>
                          {[1, 5].map((percent) => (
                            <button
                              key={percent}
                              type="button"
                              onPointerDown={() => startHoldRepeat(() => setAddPriceByPercent(percent))}
                              onPointerUp={() => stopHoldRepeat(false)}
                              onPointerLeave={() => stopHoldRepeat(true)}
                              onPointerCancel={() => stopHoldRepeat(true)}
                              onClick={() => runClickUnlessHeld(() => setAddPriceByPercent(percent))}
                              onContextMenu={(event) => event.preventDefault()}
                            >
                              +{percent}%
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="holdings-editable-number inline">
                        <input value={addAveragePrice} onChange={(event) => setAddAveragePrice(event.target.value)} inputMode="decimal" aria-label="신규 평균단가" placeholder="내 실제 평균단가 입력" />
                        <span>원</span>
                      </div>
                      <small className="holdings-reference-price">
                        {addReferencePrice ? `기준 가격 ${money(addReferencePrice)} · 실제 평단과 다르면 직접 수정하세요.` : "실제 보유 평균단가를 입력하세요."}
                      </small>
                      <small className="holdings-hold-hint">평균단가 +/- 버튼도 약 0.35초 이상 누르면 현재 표시값 기준으로 계속 증감합니다.</small>
                    </label>

                    <label>
                      <span>보유 상태 기준 시각</span>
                      <input
                        type="datetime-local"
                        value={addEffectiveAt}
                        onChange={(event) => setAddEffectiveAt(event.target.value)}
                      />
                    </label>
                    <div className="holdings-opening-balance-note">
                      이미 보유 중이던 수량과 평균단가를 시작 상태로 등록합니다. 새로운 매수 기록(BUY)을 생성하는 기능이 아닙니다.
                    </div>
                    <div className="holdings-add-held-summary">
                      <span>등록 후</span>
                      <strong>{quantity(addQuantity)}주 · {money(addAveragePrice)}</strong>
                    </div>
                    <button type="button" className="holdings-primary holdings-nowrap-action" onClick={() => void addSelectedAsHeld()} disabled={addBusy || quantityNumber(addQuantity) <= 0 || quantityNumber(addAveragePrice) <= 0}>
                      {addBusy ? "등록 중" : "기존 보유 등록"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {manualOpen && detail && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setManualOpen(false)}>
          <div className="holdings-dialog manual" role="dialog" aria-modal="true" aria-label={manualDialogTitle} onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>{manualDialogTitle}</h2>
                <p>{detail.name} · 실제 증권사 주문이 아니라 StockScope 내부 보유 기록을 변경합니다.</p>
              </div>
              <button type="button" onClick={() => setManualOpen(false)} aria-label="닫기">×</button>
            </div>

            {manualPosition && (
              <div className="holdings-manual-summary">
                <div><span>대상</span><strong>{manualPosition.account_name || manualPosition.provider}</strong></div>
                <div><span>현재 수량</span><strong>{quantity(manualPosition.quantity)}주</strong></div>
                <div><span>현재 평균단가</span><strong>{money(manualPosition.average_price)}</strong></div>
              </div>
            )}

            <div className="holdings-form">
              {manualMode === "buy" && !manualPosition && (
                <label>
                  <span>기록 계좌</span>
                  <select value={manualAccountId} onChange={(event) => setManualAccountId(event.target.value)}>
                    <option value="">기본 수동 기록</option>
                    {accounts
                      .filter((account) => account.account_kind === "MANUAL" || account.account_kind === "VIRTUAL")
                      .map((account) => (
                        <option key={account.id} value={account.id}>{account.display_name || account.provider}</option>
                      ))}
                  </select>
                </label>
              )}

              {manualMode === "buy" && manualPosition && (
                <label>
                  <span>기록 계좌</span>
                  <div className="holdings-manual-account-fixed">{manualPosition.account_name || manualPosition.provider}</div>
                </label>
              )}

              <label>
                <span>
                  {manualMode === "buy"
                    ? manualPosition ? "추가 수량" : "보유 수량"
                    : manualMode === "sell"
                      ? "매도 수량"
                      : "보유 수량"}
                </span>
                {manualMode === "sell" ? (
                  <div className="holdings-quantity-stepper">
                    <button
                      type="button"
                      onPointerDown={() => startHoldRepeat(() => adjustManualQuantity(-1))}
                      onPointerUp={() => stopHoldRepeat(false)}
                      onPointerLeave={() => stopHoldRepeat(true)}
                      onPointerCancel={() => stopHoldRepeat(true)}
                      onClick={() => runClickUnlessHeld(() => adjustManualQuantity(-1))}
                      onContextMenu={(event) => event.preventDefault()}
                      disabled={quantityNumber(manualQuantity) <= 0}
                    >−</button>
                    <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" />
                    <button
                      type="button"
                      onPointerDown={() => startHoldRepeat(() => adjustManualQuantity(1))}
                      onPointerUp={() => stopHoldRepeat(false)}
                      onPointerLeave={() => stopHoldRepeat(true)}
                      onPointerCancel={() => stopHoldRepeat(true)}
                      onClick={() => runClickUnlessHeld(() => adjustManualQuantity(1))}
                      onContextMenu={(event) => event.preventDefault()}
                      disabled={!!manualPosition && quantityNumber(manualQuantity) >= quantityNumber(manualPosition.quantity)}
                    >+</button>
                  </div>
                ) : manualMode === "buy" ? (
                  <div className="holdings-direct-adjust">
                    <div className="holdings-adjust-buttons" aria-label="보유 수량 빠른 조정">
                      {[-10, -5, -1, 1, 5, 10].map((delta) => (
                        <button
                          key={delta}
                          type="button"
                          onPointerDown={() => startHoldRepeat(() => adjustManualQuantity(delta))}
                          onPointerUp={() => stopHoldRepeat(false)}
                          onPointerLeave={() => stopHoldRepeat(true)}
                          onPointerCancel={() => stopHoldRepeat(true)}
                          onClick={() => runClickUnlessHeld(() => adjustManualQuantity(delta))}
                          onContextMenu={(event) => event.preventDefault()}
                          disabled={quantityNumber(manualQuantity) + delta < 1}
                        >
                          {delta > 0 ? `+${delta}` : delta}
                        </button>
                      ))}
                    </div>
                    <div className="holdings-editable-number">
                      <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" aria-label="보유 수량 직접 입력" />
                      <span>주</span>
                    </div>
                    <small className="holdings-hold-hint">+ / - 버튼을 길게 누르면 같은 단위로 계속 증감합니다.</small>
                  </div>
                ) : (
                  <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" placeholder="예: 5" />
                )}
              </label>

              <label>
                <span>
                  {manualMode === "correction"
                    ? "평균단가"
                    : manualMode === "sell"
                      ? "매도가"
                      : manualPosition ? "추가 매수가" : "평균 매수가"}
                </span>
                {manualMode === "buy" ? (
                  <div className="holdings-direct-adjust">
                    <div className="holdings-adjust-buttons price" aria-label="가격 빠른 조정">
                      {[-5, -1].map((percent) => (
                        <button
                          key={percent}
                          type="button"
                          onPointerDown={() => startHoldRepeat(() => adjustManualPrice(percent))}
                          onPointerUp={() => stopHoldRepeat(false)}
                          onPointerLeave={() => stopHoldRepeat(true)}
                          onPointerCancel={() => stopHoldRepeat(true)}
                          onClick={() => runClickUnlessHeld(() => adjustManualPrice(percent))}
                          onContextMenu={(event) => event.preventDefault()}
                          disabled={!manualReferencePrice}
                        >
                          {percent}%
                        </button>
                      ))}
                      <button type="button" onClick={() => setManualPrice(manualReferencePrice)} disabled={!manualReferencePrice}>기준가</button>
                      {[1, 5].map((percent) => (
                        <button
                          key={percent}
                          type="button"
                          onPointerDown={() => startHoldRepeat(() => adjustManualPrice(percent))}
                          onPointerUp={() => stopHoldRepeat(false)}
                          onPointerLeave={() => stopHoldRepeat(true)}
                          onPointerCancel={() => stopHoldRepeat(true)}
                          onClick={() => runClickUnlessHeld(() => adjustManualPrice(percent))}
                          onContextMenu={(event) => event.preventDefault()}
                          disabled={!manualReferencePrice}
                        >
                          +{percent}%
                        </button>
                      ))}
                    </div>
                    <div className="holdings-editable-number">
                      <input value={manualPrice} onChange={(event) => setManualPrice(event.target.value)} inputMode="decimal" aria-label="가격 직접 입력" placeholder="가격 직접 입력" />
                      <span>원</span>
                    </div>
                    <small className="holdings-reference-price">
                      {manualReferencePrice ? `기준 가격 ${money(manualReferencePrice)}` : "기준 가격이 없어 직접 입력이 필요합니다."}
                    </small>
                  </div>
                ) : (
                  <input value={manualPrice} onChange={(event) => setManualPrice(event.target.value)} inputMode="decimal" placeholder="예: 265000" />
                )}
              </label>

              {manualMode === "buy" && !manualPosition && manualQuantity.trim() && manualPrice.trim() && (
                <div className="holdings-registration-preview">
                  <span>{quantity(manualQuantity)}주 × {money(manualPrice)}</span>
                  <strong>기록 금액 {money(String(quantityNumber(manualQuantity) * quantityNumber(manualPrice)))}</strong>
                </div>
              )}

              {manualMode === "sell" && manualPosition && (
                <div className="holdings-trade-preview">
                  <div><span>매도 후 보유</span><strong>{quantity(String(manualRemainingQuantity ?? 0))}주</strong></div>
                  <div>
                    <span>기록될 실현손익</span>
                    <strong className={pnlSignClass(manualSellRealizedPnl == null ? null : String(manualSellRealizedPnl))}>
                      {manualSellRealizedPnl == null ? "계산 불가" : signedMoney(String(manualSellRealizedPnl))}
                    </strong>
                  </div>
                  <small>매도 직전 평균단가 기준 · 비용 제외</small>
                </div>
              )}

              {manualMode === "buy" && manualPosition && manualQuantity.trim() && (
                <div className="holdings-trade-preview">
                  <div>
                    <span>추가 후 보유</span>
                    <strong>{quantity(String(quantityNumber(manualPosition.quantity) + quantityNumber(manualQuantity)))}주</strong>
                  </div>
                  <div>
                    <span>예상 평균단가</span>
                    <strong>{manualBuyProjectedAverage == null ? "계산 불가" : money(String(manualBuyProjectedAverage))}</strong>
                  </div>
                  <small>현재 평균단가와 입력한 추가 매수가 기준</small>
                </div>
              )}

              <label>
                <span>기록 시각</span>
                <input type="datetime-local" value={manualAt} onChange={(event) => setManualAt(event.target.value)} />
              </label>
              <label className="full">
                <span>{manualMode === "correction" ? "수정 사유" : "메모 (선택)"}</span>
                <input value={manualNote} onChange={(event) => setManualNote(event.target.value)} placeholder={manualMode === "correction" ? "수정 이유를 입력하세요." : "선택 입력"} />
              </label>
            </div>

            <div className="holdings-order-note">
              {manualMode === "correction"
                ? "실제 매수·매도 거래가 아니라 StockScope에 저장된 현재 수량과 평균단가를 바로잡습니다. 이전 실현손익은 다시 계산하지 않습니다."
                : manualMode === "sell"
                  ? "StockScope에 실제 매도 내역을 기록합니다. 증권사 주문은 실행되지 않습니다."
                  : "StockScope에 실제 추가 매수 내역을 기록합니다. 증권사 주문은 실행되지 않습니다."}
            </div>

            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setManualOpen(false)}>취소</button>
              <button type="button" className="holdings-primary" onClick={() => void saveManual()} disabled={manualBusy}>
                {manualBusy
                  ? "저장 중"
                  : manualMode === "buy"
                    ? manualPosition ? "추가 매수 기록" : "보유 등록"
                    : manualMode === "sell"
                      ? "매도 기록"
                      : "보유 정보 수정"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
