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
  READY: "진입 조건 확인",
  WATCH: "지켜보기",
  NO_TRADE: "지금은 관망",
  NOT_READY: "조건 더 필요",
  CAUTION: "주의하며 관찰",
  BLOCKED: "지금은 관망",
};

const riskLabel: Record<string, string> = {
  READY: "계산 완료",
  CAUTION: "주의 조건 있음",
  HOLD: "계산 보류",
  BLOCKED: "계산 제한",
  UNAVAILABLE: "계산 불가",
};

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
  const [syncingKis, setSyncingKis] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
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

  async function refreshSelected() {
    if (!selectedStockId) return;
    setRefreshingAnalysis(true);
    setError(null);
    setMessage(null);
    try {
      await refreshHoldingAnalysis(selectedStockId);
      await Promise.all([reloadStocks(selectedStockId), loadSelected(selectedStockId)]);
      setMessage("최신 확정 일봉 기준으로 분석을 새로 확인했습니다.");
    } catch (refreshError) {
      setError(readableError(refreshError, "분석을 새로 확인하지 못했습니다."));
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

  async function setSelectedWatch(enabled: boolean, removedFromList = false) {
    if (!detail) return;
    setError(null);
    setMessage(null);
    try {
      await setWatchEnabled(detail.stock_id, enabled);
      setRemoveOpen(false);
      await reloadStocks(enabled || detail.is_held ? detail.stock_id : null);
      if (detail.is_held) await loadSelected(detail.stock_id);
      setMessage(
        enabled
          ? "관심 종목으로 등록했습니다."
          : removedFromList
            ? "내 종목 목록에서 제거했습니다. 저장된 분석 기록은 유지됩니다."
            : "관심 종목에서 해제했습니다.",
      );
    } catch (watchError) {
      setError(readableError(watchError, "관심 상태를 변경하지 못했습니다."));
    }
  }

  function requestWatchChange() {
    if (!detail) return;
    if (!detail.watch_enabled) {
      void setSelectedWatch(true);
      return;
    }
    if (detail.is_held) {
      void setSelectedWatch(false);
      return;
    }
    setRemoveOpen(true);
  }

  async function openManual(mode: ManualMode) {
    if (!detail) return;
    setManualMode(mode);
    setManualQuantity("");
    setManualPrice("");
    setManualNote("");
    setManualAt(localDateTimeValue());
    setError(null);
    try {
      const rows = await listHoldingAccounts();
      setAccounts(rows);
      const manualAccounts = rows.filter(
        (account) => account.account_kind === "MANUAL" || account.account_kind === "VIRTUAL",
      );
      setManualAccountId(manualAccounts[0]?.id ?? "");
      setManualPositionId(editablePositions[0]?.position_id ?? "");
      if (mode !== "buy" && editablePositions.length === 0) {
        setError("수동으로 수정할 수 있는 보유 기록이 없습니다.");
        return;
      }
      setManualOpen(true);
    } catch (accountError) {
      setError(readableError(accountError, "수동 기록 계좌를 확인하지 못했습니다."));
    }
  }

  async function saveManual() {
    if (!detail) return;
    if (!manualQuantity.trim()) {
      setError("수량을 입력해주세요.");
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
          ? "보유 기록을 추가했습니다."
          : manualMode === "sell"
            ? "보유 기록을 감소시켰습니다."
            : "보유 정보를 수정했습니다.",
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
                    <th>구분</th>
                    <th>현재 판단</th>
                    <th>분석일</th>
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
                      </td>
                      <td>
                        <span>{stock.is_held ? "보유" : stock.watch_enabled ? "관심" : "-"}</span>
                        {stock.is_held && stock.watch_enabled && <small>관심</small>}
                      </td>
                      <td>{stock.current_analysis ? actionLabel[stock.current_analysis.action_state] ?? stock.current_analysis.action_state : "분석 필요"}</td>
                      <td>{compactDate(stock.current_analysis?.market_date)}</td>
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
                  <button className="holdings-secondary" type="button" onClick={() => void openManual("buy")}>수동 기록</button>
                  <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>
                    {syncingKis ? "동기화 중" : "잔고 동기화"}
                  </button>
                  <button
                    className={detail.watch_enabled && !detail.is_held ? "holdings-remove-button" : "holdings-text-action"}
                    type="button"
                    onClick={requestWatchChange}
                  >
                    {!detail.watch_enabled ? "관심 등록" : detail.is_held ? "관심 해제" : "목록에서 제거"}
                  </button>
                </div>
              </div>

              <HoldingsPriceChart stockId={detail.stock_id} analysis={selectedAnalysis} />

              <div className="holdings-analysis-grid">
                <section className="holdings-analysis-block">
                  <div className="holdings-block-title">
                    <h3>현재 분석</h3>
                  </div>
                  {selectedAnalysis ? (
                    <dl className="holdings-key-values">
                      <div><dt>현재 판단</dt><dd>{actionLabel[selectedAnalysis.action_state] ?? selectedAnalysis.action_state}</dd></div>
                      <div><dt>전략</dt><dd>{strategyLabel[selectedAnalysis.strategy_key] ?? selectedAnalysis.strategy_key}</dd></div>
                      <div><dt>위험 계산</dt><dd>{riskLabel[selectedAnalysis.risk_state] ?? selectedAnalysis.risk_state}</dd></div>
                      <div><dt>분석 기준일</dt><dd>{compactDate(selectedAnalysis.market_date)}</dd></div>
                    </dl>
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
                    <span>계좌별로 따로 표시합니다.</span>
                  </div>
                  {editablePositions.length > 0 && (
                    <div className="holdings-inline-actions">
                      <button type="button" onClick={() => void openManual("sell")}>보유 감소</button>
                      <button type="button" onClick={() => void openManual("correction")}>정보 수정</button>
                    </div>
                  )}
                </div>
                {detail.positions.length === 0 ? (
                  <div className="holdings-inline-empty"><span>현재 열린 보유 기록이 없습니다.</span></div>
                ) : (
                  <div className="holdings-position-list">
                    {detail.positions.map((position) => (
                      <article key={position.position_id} className="holdings-position-row">
                        <div>
                          <strong>{position.account_name || (position.provider === "KIS" ? "한국투자증권" : "수동 기록")}</strong>
                          <small>{position.account_kind === "BROKER" ? "연동 계좌" : "StockScope 수동 기록"}</small>
                        </div>
                        <div><span>수량</span><strong>{quantity(position.quantity)}주</strong></div>
                        <div><span>평균단가</span><strong>{money(position.average_price)}</strong></div>
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

      {removeOpen && detail && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setRemoveOpen(false)}>
          <div className="holdings-dialog holdings-remove-dialog" role="dialog" aria-modal="true" aria-label="목록에서 제거" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>목록에서 제거</h2>
                <p>{detail.name}을(를) 내 종목 목록에서 제거할까요?</p>
              </div>
              <button type="button" onClick={() => setRemoveOpen(false)} aria-label="닫기">×</button>
            </div>
            <div className="holdings-remove-copy">저장된 분석 기록과 과거 변화 기록은 삭제되지 않습니다.</div>
            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setRemoveOpen(false)}>취소</button>
              <button type="button" className="holdings-remove-confirm" onClick={() => void setSelectedWatch(false, true)}>제거</button>
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
          <div className="holdings-dialog manual" role="dialog" aria-modal="true" aria-label="수동 보유 기록" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>수동 기록</h2>
                <p>{detail.name} · 실제 증권사 주문이 아닌 StockScope 내부 기록입니다.</p>
              </div>
              <button type="button" onClick={() => setManualOpen(false)} aria-label="닫기">×</button>
            </div>

            <div className="holdings-tabs manual-tabs">
              <button className={manualMode === "buy" ? "active" : ""} onClick={() => setManualMode("buy")}>보유 추가</button>
              <button className={manualMode === "sell" ? "active" : ""} disabled={editablePositions.length === 0} onClick={() => {
                setManualMode("sell");
                setManualPositionId(editablePositions[0]?.position_id ?? "");
              }}>보유 감소</button>
              <button className={manualMode === "correction" ? "active" : ""} disabled={editablePositions.length === 0} onClick={() => {
                setManualMode("correction");
                setManualPositionId(editablePositions[0]?.position_id ?? "");
              }}>정보 수정</button>
            </div>

            <div className="holdings-form">
              {manualMode === "buy" ? (
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
              ) : (
                <label>
                  <span>수정할 보유 기록</span>
                  <select value={manualPositionId} onChange={(event) => setManualPositionId(event.target.value)}>
                    {editablePositions.map((position) => (
                      <option key={position.position_id} value={position.position_id}>
                        {(position.account_name || position.provider)} · {quantity(position.quantity)}주
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                <span>수량</span>
                <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" placeholder="예: 5" />
              </label>
              <label>
                <span>{manualMode === "correction" ? "평균단가" : "가격"}</span>
                <input value={manualPrice} onChange={(event) => setManualPrice(event.target.value)} inputMode="decimal" placeholder="예: 265000" />
              </label>
              <label>
                <span>기록 시각</span>
                <input type="datetime-local" value={manualAt} onChange={(event) => setManualAt(event.target.value)} />
              </label>
              <label className="full">
                <span>{manualMode === "correction" ? "수정 사유" : "메모 (선택)"}</span>
                <input value={manualNote} onChange={(event) => setManualNote(event.target.value)} placeholder={manualMode === "correction" ? "수정 이유를 입력하세요." : "선택 입력"} />
              </label>
            </div>
            <div className="holdings-order-note">실제 매수·매도 주문은 실행되지 않습니다.</div>
            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setManualOpen(false)}>취소</button>
              <button type="button" className="holdings-primary" onClick={() => void saveManual()} disabled={manualBusy}>
                {manualBusy ? "저장 중" : "기록 저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
