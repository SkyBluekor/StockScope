import { useEffect, useMemo, useState } from "react";
import { searchStocks, type StockSearchItem } from "../services/api";
import HoldingsPriceChart from "./HoldingsPriceChart";
import {
  addWatchStock,
  getHoldingStock,
  getHoldingTimeline,
  listHoldingAccounts,
  listHoldingStocks,
  recordManualBuy,
  recordManualCorrection,
  recordManualSell,
  refreshHoldingAnalysis,
  setWatchEnabled,
  syncKisHoldings,
  type HoldingAccount,
  type HoldingDecisionContext,
  type HoldingPosition,
  type HoldingStock,
  type HoldingTimelineItem,
} from "../services/holdingsApi";
import "../holdings.css";

type StockFilter = "all" | "watch" | "held";
type TimelineFilter = "all" | "analysis" | "position";
type ManualMode = "buy" | "sell" | "correction";

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
      return "이전 계획 범위 내";
    case "FIRST_PLAN":
      return "첫 계획 기준 저장됨";
    case "PREVIOUS_PLAN_UNAVAILABLE":
      return "이전 계획 정보 확인 필요";
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
      return `${previousDate ?? "이전"} 계획의 손절 기준 ${money(plan.previous_stop_price)}보다 현재 확정 종가 ${money(plan.current_close)}가 낮거나 같습니다.`;
    case "TARGET2_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 계획의 2차 목표 ${money(plan.previous_target2_price)} 이상입니다.`;
    case "TARGET1_REACHED":
      return `현재 확정 종가 ${money(plan.current_close)}가 ${previousDate ?? "이전"} 계획의 1차 목표 ${money(plan.previous_target1_price)} 이상입니다.`;
    case "WITHIN_PLAN":
      return `${previousDate ?? "이전"} 계획과 현재 확정 종가를 비교했으며 현재는 이전 계획 범위 안에 있습니다.`;
    default:
      return null;
  }
}

function previousPlanActionLabel(context: HoldingDecisionContext | null | undefined) {
  const plan = context?.previous_plan;
  if (!plan || plan.state === "FIRST_PLAN" || !plan.previous_market_date) return null;
  return plan.state === "PREVIOUS_PLAN_UNAVAILABLE" ? "과거 분석 보기" : "이전 계획 보기";
}

function money(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(parsed)}원`;
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

function stockHoldingSummary(stock: HoldingStock) {
  const positions = stock.positions ?? [];
  if (positions.length === 0) return stock.watch_enabled ? "관심 종목" : "보유 기록 없음";
  if (positions.length === 1) {
    const position = positions[0];
    return `보유 ${quantity(position.quantity)}주 · 평균 ${money(position.average_price)}`;
  }
  const total = positions.reduce((sum, position) => sum + quantityNumber(position.quantity), 0);
  return `보유 ${positions.length}개 포지션 · 총 ${quantity(String(total))}주`;
}

function stockDecisionText(stock: HoldingStock) {
  if (!stock.current_analysis) return "분석 필요";
  return stock.decision_context?.entry.label
    ?? actionLabel[stock.current_analysis.action_state]
    ?? stock.current_analysis.action_state;
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

function readableError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function timelineLabel(item: HoldingTimelineItem) {
  if (item.kind === "ANALYSIS") return "분석 갱신";
  switch (item.event_type) {
    case "BUY":
      return "보유 추가";
    case "SELL":
      return "보유 감소";
    case "CORRECTION":
      return "수동 수정";
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
    case "BUY":
      return "StockScope 수동 보유 기록에 수량을 추가했습니다.";
    case "SELL":
      return "StockScope 수동 보유 기록에서 수량을 줄였습니다.";
    case "CORRECTION":
      return "수동 보유 정보의 수량 또는 평균단가를 수정했습니다.";
    case "BALANCE_OBSERVED":
      return "한국투자증권에서 확인한 잔고를 기록했습니다.";
    case "RECONCILED":
      return "한국투자증권 잔고와 StockScope 보유 정보를 동기화했습니다.";
    default:
      return "보유 정보가 변경되었습니다.";
  }
}

export default function HoldingsWorkspace() {
  const [stocks, setStocks] = useState<HoldingStock[]>([]);
  const [selectedStockId, setSelectedStockId] = useState<string | null>(null);
  const [detail, setDetail] = useState<HoldingStock | null>(null);
  const [timeline, setTimeline] = useState<HoldingTimelineItem[]>([]);
  const [stockFilter, setStockFilter] = useState<StockFilter>("all");
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>("all");
  const [query, setQuery] = useState("");
  const [loadingStocks, setLoadingStocks] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshingAnalysis, setRefreshingAnalysis] = useState(false);
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

  async function reloadStocks(preferredId?: string | null) {
    setLoadingStocks(true);
    try {
      const rows = await listHoldingStocks();
      setStocks(rows);
      const keep = preferredId && rows.some((row) => row.stock_id === preferredId)
        ? preferredId
        : selectedStockId && rows.some((row) => row.stock_id === selectedStockId)
          ? selectedStockId
          : rows[0]?.stock_id ?? null;
      setSelectedStockId(keep);
      if (!keep) {
        setDetail(null);
        setTimeline([]);
      }
    } catch (loadError) {
      setError(readableError(loadError, "내 종목 목록을 불러오지 못했습니다."));
    } finally {
      setLoadingStocks(false);
    }
  }

  async function loadSelected(stockId: string) {
    setLoadingDetail(true);
    try {
      const [stock, rows] = await Promise.all([
        getHoldingStock(stockId),
        getHoldingTimeline(stockId),
      ]);
      setDetail(stock);
      setTimeline(rows);
    } catch (loadError) {
      setError(readableError(loadError, "선택한 종목 정보를 불러오지 못했습니다."));
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => {
    void reloadStocks();
  }, []);

  useEffect(() => {
    setShowMissingConditions(false);
    setShowPreviousPlan(false);
    if (selectedStockId) void loadSelected(selectedStockId);
  }, [selectedStockId]);

  useEffect(() => {
    if (!addOpen) return;
    const text = addQuery.trim();
    if (text.length < 2) {
      setAddResults([]);
      setAddSearching(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setAddSearching(true);
      void searchStocks(text)
        .then((result) => setAddResults(result.rows))
        .catch(() => setAddResults([]))
        .finally(() => setAddSearching(false));
    }, 250);
    return () => window.clearTimeout(timer);
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

  const manualDialogTitle = manualMode === "buy"
    ? manualPosition ? "수량 추가" : "보유 등록"
    : manualMode === "sell"
      ? "수량 감소"
      : "정보 수정";

  const manualRemainingQuantity = manualMode === "sell" && manualPosition
    ? Math.max(0, quantityNumber(manualPosition.quantity) - quantityNumber(manualQuantity))
    : null;

  async function refreshSelected() {
    if (!selectedStockId) return;
    setRefreshingAnalysis(true);
    setError(null);
    setMessage(null);
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
      setError(readableError(refreshError, "최신 확정 데이터를 확인하거나 분석하지 못했습니다."));
    } finally {
      setRefreshingAnalysis(false);
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

  async function chooseAddStock(item: StockSearchItem) {
    setError(null);
    try {
      const result = await addWatchStock({
        market: item.market,
        ticker: item.code,
        name: item.name,
      });
      setAddOpen(false);
      setAddQuery("");
      setAddResults([]);
      await reloadStocks(result.stock.stock_id);
      setSelectedStockId(result.stock.stock_id);
      setMessage(result.created ? "관심 종목에 추가했습니다." : "이미 등록된 종목을 관심 상태로 변경했습니다.");
    } catch (addError) {
      setError(readableError(addError, "종목을 추가하지 못했습니다."));
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
    } else if (mode === "sell" && position) {
      setManualQuantity(quantityNumber(position.quantity) >= 1 ? "1" : position.quantity);
      setManualPrice("");
    } else {
      setManualQuantity("");
      setManualPrice("");
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
    const current = quantityNumber(manualQuantity);
    let next = Math.max(0, current + delta);
    if (manualMode === "sell" && manualPosition) {
      next = Math.min(next, quantityNumber(manualPosition.quantity));
    }
    setManualQuantity(String(next));
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
      setError(`감소 수량은 현재 보유 ${quantity(manualPosition.quantity)}주를 넘을 수 없습니다.`);
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
      setError("정보 수정에는 수정 사유가 필요합니다.");
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
          analysis_revision_id: detail.current_analysis?.revision_id ?? null,
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
      setMessage(
        manualMode === "buy"
          ? manualPosition
            ? `${manualQuantity}주를 추가했습니다. 보유 현황을 갱신했습니다.`
            : `${manualQuantity}주를 보유 종목으로 등록했습니다.`
          : manualMode === "sell"
            ? `${manualQuantity}주를 감소했습니다. 보유 현황을 갱신했습니다.`
            : "StockScope에 저장된 보유 정보를 수정했습니다.",
      );
    } catch (manualError) {
      setError(readableError(manualError, "수동 기록을 저장하지 못했습니다."));
    } finally {
      setManualBusy(false);
    }
  }

  const selectedAnalysis = detail?.current_analysis ?? null;

  return (
    <div className="holdings-workspace">
      <section className="holdings-page-head">
        <div>
          <span className="eyebrow">HOLDINGS · EOD ANALYSIS</span>
          <h1>내 종목 분석</h1>
          <p>관심 종목과 보유 종목을 한곳에서 확인합니다.</p>
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
              <table className="holdings-stock-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>현재 판단</th>
                    <th>분석일</th>
                    <th>관리</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStocks.map((stock) => (
                    <tr
                      key={stock.stock_id}
                      className={selectedStockId === stock.stock_id ? "selected" : ""}
                      onClick={() => setSelectedStockId(stock.stock_id)}
                    >
                      <td>
                        <strong>{stock.name}</strong>
                        <small>{stock.ticker} · {stock.market}</small>
                        <span className="holdings-list-position-summary">{stockHoldingSummary(stock)}</span>
                      </td>
                      <td className="holdings-decision-cell">
                        <strong>{stockDecisionText(stock)}</strong>
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
                    </tr>
                  ))}
                </tbody>
              </table>
              {visibleStocks.length === 0 && <div className="holdings-empty compact">조건에 맞는 종목이 없습니다.</div>}
            </div>
          )}
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
                  <button className="holdings-primary" type="button" onClick={refreshSelected} disabled={refreshingAnalysis}>
                    {refreshingAnalysis ? "분석 확인 중" : "분석 새로고침"}
                  </button>
                  <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>
                    {syncingKis ? "동기화 중" : "잔고 동기화"}
                  </button>
                </div>
              </div>

              <HoldingsPriceChart
                stockId={detail.stock_id}
                analysis={selectedAnalysis}
                refreshKey={chartRefreshKey}
                decisionContext={detail.decision_context}
              />

              <div className="holdings-analysis-grid">
                <section className="holdings-analysis-block">
                  <div className="holdings-block-title">
                    <h3>현재 분석</h3>
                  </div>
                  {selectedAnalysis ? (
                    <>
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
                                ? "이전 계획 닫기"
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
                              이전 계획 · {compactDate(detail.decision_context.previous_plan.previous_market_date)}
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
                  <h3>주요 가격</h3>
                  <dl className="holdings-price-list">
                    <div><dt>기준가</dt><dd>{money(selectedAnalysis?.reference_price)}</dd></div>
                    <div><dt>손절 기준</dt><dd>{money(selectedAnalysis?.stop_price)}</dd></div>
                    <div><dt>1차 목표</dt><dd>{money(selectedAnalysis?.target1_price)}</dd></div>
                    <div><dt>2차 목표</dt><dd>{money(selectedAnalysis?.target2_price)}</dd></div>
                  </dl>
                </section>
              </div>

              <div className="holdings-basis-note">
                실시간 판단이 아니라 최신 확정 일봉 기준 분석입니다.
              </div>

              <section className="holdings-positions">
                <div className="holdings-block-title">
                  <div>
                    <h3>보유 현황</h3>
                    <span>계좌별 보유 수량과 평균단가를 확인하고, 수동 기록은 여기에서 바로 변경합니다.</span>
                  </div>
                </div>

                {detail.positions.length === 0 ? (
                  <div className="holdings-inline-empty">
                    <span>현재 열린 보유 기록이 없습니다.</span>
                    <div className="holdings-position-empty-actions">
                      <button className="holdings-primary small" type="button" onClick={() => void openManual("buy")}>
                        보유 등록
                      </button>
                    </div>
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
                            <button className="primary" type="button" onClick={() => void openManual("buy", position)}>수량 추가</button>
                            <button type="button" onClick={() => void openManual("sell", position)}>수량 감소</button>
                            <button type="button" onClick={() => void openManual("correction", position)}>정보 수정</button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </section>

      <section className="holdings-timeline-pane">
        <div className="holdings-section-head">
          <div>
            <h2>최근 변화</h2>
            <span>선택한 종목의 분석과 보유 기록</span>
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
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setAddOpen(false)}>
          <div className="holdings-dialog" role="dialog" aria-modal="true" aria-label="종목 추가" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div><h2>종목 추가</h2><p>종목명이나 종목코드로 검색한 뒤 선택하세요.</p></div>
              <button type="button" onClick={() => setAddOpen(false)} aria-label="닫기">×</button>
            </div>
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
                  <button key={`${item.market}-${item.code}`} type="button" onClick={() => void chooseAddStock(item)}>
                    <span><strong>{item.name}</strong><small>{item.code}</small></span>
                    <b>{item.market}</b>
                  </button>
                ))
              )}
            </div>
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
                      ? "감소 수량"
                      : "보유 수량"}
                </span>
                {manualMode === "sell" ? (
                  <div className="holdings-quantity-stepper">
                    <button type="button" onClick={() => adjustManualQuantity(-1)} disabled={quantityNumber(manualQuantity) <= 0}>−</button>
                    <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" />
                    <button type="button" onClick={() => adjustManualQuantity(1)} disabled={!!manualPosition && quantityNumber(manualQuantity) >= quantityNumber(manualPosition.quantity)}>+</button>
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
                      ? "감소 가격 (기록용)"
                      : manualPosition ? "추가 매수가" : "평균 매수가"}
                </span>
                <input value={manualPrice} onChange={(event) => setManualPrice(event.target.value)} inputMode="decimal" placeholder="예: 265000" />
              </label>

              {manualMode === "sell" && manualPosition && (
                <div className="holdings-form-preview">
                  <span>감소 후 보유 수량</span>
                  <strong>{quantity(String(manualRemainingQuantity ?? 0))}주</strong>
                </div>
              )}

              {manualMode === "buy" && manualPosition && manualQuantity.trim() && (
                <div className="holdings-form-preview">
                  <span>추가 후 보유 수량</span>
                  <strong>{quantity(String(quantityNumber(manualPosition.quantity) + quantityNumber(manualQuantity)))}주</strong>
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
                ? "실제 주문 내역을 만드는 것이 아니라 StockScope에 저장된 보유 수량과 평균단가를 바로잡습니다."
                : manualMode === "sell"
                  ? "실제 매도 주문은 실행되지 않습니다. 선택한 내부 보유 기록의 수량만 감소시킵니다."
                  : "실제 매수 주문은 실행되지 않습니다. StockScope 내부 보유 기록만 추가합니다."}
            </div>

            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setManualOpen(false)}>취소</button>
              <button type="button" className="holdings-primary" onClick={() => void saveManual()} disabled={manualBusy}>
                {manualBusy
                  ? "저장 중"
                  : manualMode === "buy"
                    ? manualPosition ? "수량 추가" : "보유 등록"
                    : manualMode === "sell"
                      ? "감소 적용"
                      : "정보 수정"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
