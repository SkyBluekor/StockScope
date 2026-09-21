import { Fragment, useEffect, useMemo, useState } from "react";
import { searchStocks, type StockSearchItem } from "../services/api";
import { useScannerSession } from "./scannerSession";
import EmbeddedScanner from "./EmbeddedScanner";
import {
  addManualTrackedItem,
  addScannerTrackedItem,
  closeTrackedRecommendation,
  deleteTrackedRecommendation,
  listTrackedRecommendations,
  previewManualTrackedItem,
  refreshActiveTrackedRecommendations,
  refreshTrackedRecommendation,
  TrackingApiError,
  type ManualTrackPreview,
  type RecommendationPerformance,
  type TrackedRecommendation,
} from "../services/trackingApi";
import "../tracking.css";

type UnknownRecord = Record<string, unknown>;
type SourceFilter = "ALL" | "SCANNER" | "MANUAL";
type StatusFilter = "ALL" | "ACTIVE" | "CLOSED";

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}
function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
function numberValue(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function priceValue(value: unknown): string | number | null {
  return typeof value === "string" || typeof value === "number" ? value : null;
}
function krw(value: string | number | null | undefined) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  return Number.isFinite(n) ? `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(n)}원` : "-";
}
function dateText(value: string | null | undefined) { return value ? value.replace(/-/g, ".") : "-"; }
function pct(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function pctTone(value: string | null | undefined) {
  const n = Number(value);
  return !Number.isFinite(n) || n === 0 ? "neutral" : n > 0 ? "positive" : "negative";
}
function touchLabel(enabled: boolean, day: string | null) {
  return enabled ? `도달${day ? ` · ${dateText(day)}` : ""}` : "미도달";
}
function hasScannerSource(row: TrackedRecommendation) { return row.has_scanner_source || row.source === "SCANNER"; }
function hasManualSource(row: TrackedRecommendation) { return row.has_manual_source || row.source === "MANUAL"; }
function sourceLabel(row: TrackedRecommendation) {
  if (hasScannerSource(row) && hasManualSource(row)) return "추천 · 직접";
  return hasManualSource(row) ? "직접" : "추천";
}
function sourceDetailLabel(row: TrackedRecommendation) {
  if (hasScannerSource(row) && hasManualSource(row)) return "Scanner 추천 · 직접 추가";
  return hasManualSource(row) ? "직접 추가" : "Scanner 추천";
}
function upsertTrackedRow(current: TrackedRecommendation[], row: TrackedRecommendation) {
  const rest = current.filter((item) => item.id !== row.id);
  return [row, ...rest];
}
function trackingStateLabel(status: string) {
  return status === "ACTIVE" ? "추적 중" : "종료";
}
function entryRuleAvailable(row: TrackedRecommendation) {
  const sourceSnapshot = Object.keys(row.scanner_snapshot ?? {}).length ? row.scanner_snapshot : row.snapshot;
  const candidate = asRecord(sourceSnapshot.candidate);
  const guide = asRecord(candidate.entry_risk_guide);
  const rule = asRecord(guide.price_rule);
  return ["RANGE", "ABOVE", "AT_OR_BELOW"].includes(String(rule.kind ?? "").toUpperCase());
}
function entryLabel(row: TrackedRecommendation) {
  if (!hasScannerSource(row) || !row.entry_price) return "-";
  if (!entryRuleAvailable(row)) return "판정 불가";
  return touchLabel(Boolean(row.performance?.entry_touched), row.performance?.entry_touch_date ?? null);
}
function candidatePricePlan(candidate: UnknownRecord) {
  const guide = asRecord(candidate.entry_risk_guide);
  const rule = asRecord(guide.price_rule);
  const risk = asRecord(guide.risk);
  const entry = priceValue(rule.display_trigger_price) ?? priceValue(rule.trigger_price) ?? priceValue(rule.display_reference_price)
    ?? priceValue(rule.reference_price) ?? priceValue(candidate.entry) ?? priceValue(candidate.entry_price);
  const stop = priceValue(risk.display_stop_zone_high) ?? priceValue(risk.stop_zone_high) ?? priceValue(risk.stop_price)
    ?? priceValue(candidate.stop) ?? priceValue(candidate.stop_price);
  const target1 = priceValue(risk.display_target1_price) ?? priceValue(risk.target1_price)
    ?? priceValue(candidate.target1) ?? priceValue(candidate.target1_price);
  const target2 = priceValue(risk.display_target2_price) ?? priceValue(risk.target2_price)
    ?? priceValue(candidate.target2) ?? priceValue(candidate.target2_price);
  return { entry, stop, target1, target2 };
}

function PerformanceCells({ performance }: { performance: RecommendationPerformance | null }) {
  if (!performance || !performance.latest_close) {
    return <><td>-</td><td className="tracking-muted">가격 대기</td><td>-</td><td>-</td><td>{performance?.trading_days ?? 0}D</td></>;
  }
  return <>
    <td>{krw(performance.latest_close)}{performance.price_status === "STALE" && <small className="tracking-stale">지연</small>}</td>
    <td className={`tracking-return ${pctTone(performance.current_return_pct)}`}>{pct(performance.current_return_pct)}</td>
    <td className={`tracking-return ${pctTone(performance.mfe_pct)}`}>{pct(performance.mfe_pct)}</td>
    <td className={`tracking-return ${pctTone(performance.mae_pct)}`}>{pct(performance.mae_pct)}</td>
    <td>{performance.trading_days}D</td>
  </>;
}

export default function RecommendationTracking() {
  const scannerSession = useScannerSession();
  const result = asRecord(scannerSession?.result);
  const scannerDate = text(result.requested_as_of);
  const candidates = [
    ...(Array.isArray(result.candidates) ? result.candidates : []),
    ...(Array.isArray(result.more_candidates) ? result.more_candidates : []),
  ].map(asRecord);

  const [rows, setRows] = useState<TrackedRecommendation[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lastMarketDate, setLastMarketDate] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("ALL");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [manualQuery, setManualQuery] = useState("");
  const [manualBusy, setManualBusy] = useState(false);
  const [manualRows, setManualRows] = useState<StockSearchItem[]>([]);
  const [manualSelected, setManualSelected] = useState<StockSearchItem | null>(null);
  const [manualPreview, setManualPreview] = useState<ManualTrackPreview | null>(null);

  async function loadRows() {
    try {
      const next = await listTrackedRecommendations();
      setRows(next);
      const dates = next.map((row) => row.performance?.market_date).filter((value): value is string => Boolean(value));
      if (dates.length) { dates.sort(); setLastMarketDate(dates[dates.length - 1] ?? null); }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "종목 성과 추적 목록을 불러오지 못했습니다.");
    }
  }

  useEffect(() => { void loadRows(); }, []);

  const scannerTrackingStatus = useMemo(
    () => new Map(rows.filter(hasScannerSource).map((row) => [`${row.market}:${row.ticker}:${row.recommendation_date}`, row.status])),
    [rows],
  );
  const manualActiveKeys = useMemo(
    () => new Set(rows.filter((row) => hasManualSource(row) && row.status === "ACTIVE").map((row) => `${row.market}:${row.ticker}`)),
    [rows],
  );
  const selectedManualKey = manualSelected ? `${manualSelected.market}:${manualSelected.code}` : null;
  const selectedManualActive = selectedManualKey ? manualActiveKeys.has(selectedManualKey) : false;
  const selectedManualSameDayClosed = Boolean(
    manualSelected && manualPreview && rows.some((row) =>
      hasManualSource(row)
      && row.status === "CLOSED"
      && row.market === manualSelected.market
      && row.ticker === manualSelected.code
      && row.recommendation_date === manualPreview.reference_date,
    ),
  );
  const activeCount = rows.filter((row) => row.status === "ACTIVE").length;
  const sourceCounts = {
    ALL: rows.length,
    SCANNER: rows.filter(hasScannerSource).length,
    MANUAL: rows.filter(hasManualSource).length,
  };
  const statusCounts = {
    ALL: rows.length,
    ACTIVE: activeCount,
    CLOSED: rows.filter((row) => row.status === "CLOSED").length,
  };
  const sortedRows = [...rows].sort((a, b) => {
    if (a.status !== b.status) return a.status === "ACTIVE" ? -1 : 1;
    const dateOrder = b.recommendation_date.localeCompare(a.recommendation_date);
    return dateOrder || a.ticker.localeCompare(b.ticker);
  });
  const visibleRows = sortedRows.filter((row) =>
    (sourceFilter === "ALL" || (sourceFilter === "SCANNER" ? hasScannerSource(row) : hasManualSource(row)))
    && (statusFilter === "ALL" || row.status === statusFilter),
  );

  async function addScanner(candidate: UnknownRecord) {
    const ticker = text(candidate.code);
    const name = text(candidate.name);
    const market = text(candidate.market);
    const recommendationDate = text(candidate.data_date) ?? scannerDate;
    if (!ticker || !name || !market || !recommendationDate) {
      setMessage("이 추천은 기준일 또는 종목 정보가 부족해 추적할 수 없습니다.");
      return;
    }
    const key = `${market}:${ticker}:${recommendationDate}`;
    const plan = candidatePricePlan(candidate);
    setBusyKey(key); setMessage(null);
    try {
      const response = await addScannerTrackedItem({
        ticker, name, market, recommendation_date: recommendationDate,
        scanner_version: text(result.scanner_version) ?? text(result.version),
        scanner_baseline: text(result.scanner_baseline) ?? text(result.baseline_id),
        strategy: text(candidate.strategy) ?? text(candidate.strategy_easy_name),
        decision_status: text(candidate.decision_status) ?? text(candidate.status) ?? text(candidate.action_label),
        rank: numberValue(candidate.rank),
        entry_price: plan.entry, stop_price: plan.stop, target1_price: plan.target1, target2_price: plan.target2,
        snapshot: { scanner_result_date: scannerDate, candidate },
      });
      setRows((current) => upsertTrackedRow(current, response.item));
      const merged = !response.created && response.item.has_manual_source && response.item.has_scanner_source;
      setMessage(response.created ? `${name} ${ticker} 추천을 추적하기 시작했습니다.` : merged ? `${name} ${ticker} 기존 추적에 Scanner 추천 정보를 합쳤습니다.` : `${name} ${ticker} 추천은 이미 저장되어 있습니다.`);
      void loadRows();
    } catch (error) {
      setMessage(error instanceof TrackingApiError ? error.message : error instanceof Error ? error.message : "추천 추적 추가에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function runManualSearch() {
    const query = manualQuery.trim();
    if (!query) return setMessage("종목명이나 종목코드를 입력해주세요.");
    setManualBusy(true); setMessage(null); setManualSelected(null); setManualPreview(null);
    try {
      const response = await searchStocks(query);
      setManualRows(response.rows);
      if (!response.rows.length) setMessage("검색 결과가 없습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "종목 검색에 실패했습니다.");
    } finally { setManualBusy(false); }
  }

  async function selectManual(item: StockSearchItem) {
    setManualSelected(item); setManualPreview(null); setManualBusy(true); setMessage(null);
    try {
      setManualPreview(await previewManualTrackedItem({ ticker: item.code, name: item.name, market: item.market }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "최신 확정 종가를 확인하지 못했습니다.");
    } finally { setManualBusy(false); }
  }

  async function addManual() {
    if (!manualSelected) return;
    setManualBusy(true); setMessage(null);
    try {
      const response = await addManualTrackedItem({ ticker: manualSelected.code, name: manualSelected.name, market: manualSelected.market });
      setRows((current) => upsertTrackedRow(current, response.item));
      const merged = !response.created && response.item.has_manual_source && response.item.has_scanner_source;
      setMessage(response.created ? `${manualSelected.name} ${manualSelected.code} 직접 추적을 시작했습니다.` : merged ? `${manualSelected.name} ${manualSelected.code} 기존 추천 추적에 직접 출처를 합쳤습니다.` : `${manualSelected.name} ${manualSelected.code}은 이미 직접 추적 중입니다.`);
      void loadRows();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "직접 추적 추가에 실패했습니다.");
    } finally { setManualBusy(false); }
  }

  async function close(id: string) {
    const row = rows.find((item) => item.id === id);
    if (!row) return;
    if (!window.confirm(`${row.name} ${row.ticker} 추적을 종료하시겠습니까?\n현재 확보된 거래일까지의 성과가 고정됩니다.`)) return;
    setBusyKey(id); setMessage(null);
    try {
      const updated = await closeTrackedRecommendation(id);
      setRows((current) => upsertTrackedRow(current, updated));
      setMessage(`${updated.name} ${updated.ticker} 추적을 종료했습니다.`);
      void loadRows();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "추적 종료에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function remove(row: TrackedRecommendation) {
    if (row.status !== "CLOSED") {
      setMessage("추적 중인 기록은 먼저 종료한 뒤 삭제할 수 있습니다.");
      return;
    }
    const scannerWarning = hasScannerSource(row)
      ? "\n이 기록은 Scanner 추천 성과 분석 자료에 사용될 수 있습니다."
      : "";
    if (!window.confirm(`${row.name} ${row.ticker} 추적 기록을 삭제하시겠습니까?${scannerWarning}\n추천 당시 정보와 누적 성과도 함께 삭제되며 되돌릴 수 없습니다.`)) return;
    setBusyKey(row.id); setMessage(null);
    try {
      await deleteTrackedRecommendation(row.id);
      setExpandedId((current) => current === row.id ? null : current);
      await loadRows();
      setMessage(`${row.name} ${row.ticker} 추적 기록을 삭제했습니다.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "추적 기록 삭제에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function refreshOne(id: string) {
    const before = rows.find((row) => row.id === id)?.performance ?? null;
    setBusyKey(id); setMessage(null);
    try {
      const updated = await refreshTrackedRecommendation(id);
      setRows((current) => current.map((row) => row.id === id ? updated : row));
      if (updated.performance?.market_date) setLastMarketDate(updated.performance.market_date);
      const after = updated.performance;
      const changed = Boolean(after) && (
        before?.market_date !== after?.market_date
        || before?.latest_date !== after?.latest_date
        || before?.latest_close !== after?.latest_close
        || before?.trading_days !== after?.trading_days
        || before?.current_return_pct !== after?.current_return_pct
      );
      setMessage(changed
        ? `${updated.name} ${updated.ticker} · ${dateText(after?.market_date)}까지 최신 데이터를 반영했습니다.`
        : "새로운 확정 거래일이 없습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "성과 갱신에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function refreshAll() {
    setBulkBusy(true); setMessage(null);
    try {
      const summary = await refreshActiveTrackedRecommendations();
      setLastMarketDate(summary.latest_market_date);
      await loadRows();
      const base = `성과 갱신 완료 · 변경 ${summary.updated} · 동일 ${summary.unchanged}`;
      if (summary.failed) setMessage(`${base} · 실패 ${summary.failed}`);
      else if (summary.updated === 0) setMessage("새로운 확정 거래일이 없습니다.");
      else setMessage(base);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "최신 데이터 반영에 실패했습니다.");
    } finally { setBulkBusy(false); }
  }

  return (
    <section className="tracking-workspace tracking-unified">
      <header className="tracking-head">
        <div><span>성과 데이터 축적</span><h1>종목 성과 추적</h1><p>이 화면에서 Scanner 종목 찾기를 직접 실행하거나 원하는 종목을 직접 추가해 이후 가격 움직임과 성과를 기록합니다. 쌓인 데이터는 Scanner가 어떤 조건에서 잘 작동했는지 분석하고 개선하는 데 사용됩니다.</p></div>
        <div className="tracking-summary"><div><strong>{activeCount}</strong><span>추적 중</span></div><button disabled={bulkBusy || activeCount === 0} onClick={() => void refreshAll()}>{bulkBusy ? "반영 중…" : "최신 데이터 반영"}</button></div>
      </header>

      <p className="feature-flow-line">종목 추가 → 이후 움직임 기록 → 성과 축적 → Scanner 개선 자료</p>
      <div className="tracking-meta-line"><span>최근 반영 {dateText(lastMarketDate)}</span><span>시작일 다음 거래일부터 성과 계산</span></div>
      {message && <div className="tracking-notice">{message}</div>}

      <EmbeddedScanner />

      <section className="tracking-source tracking-scanner-source">
        <div className="tracking-section-head"><div><span>Scanner 결과</span><h2>최근 추천 후보</h2></div><small>{scannerSession ? `기준일 ${dateText(scannerDate)} · ${candidates.length}종목` : "최근 Scanner 결과 없음"}</small></div>
        {!scannerSession ? <div className="tracking-empty tracking-empty-action"><strong>위 종목 찾기를 실행하면 추천 후보가 여기에 표시됩니다.</strong><span>메인 종목 찾기에서 실행한 결과도 같은 Scanner 상태를 사용합니다.</span></div> : candidates.length === 0 ? <p className="tracking-empty">이번 Scanner 실행에는 추천 후보가 없습니다.</p> : (
          <div className="tracking-candidates tracking-candidates-all">
            {candidates.map((candidate, index) => {
              const ticker = text(candidate.code) ?? "-";
              const name = text(candidate.name) ?? "종목";
              const market = text(candidate.market) ?? "KRX";
              const day = text(candidate.data_date) ?? scannerDate ?? "";
              const key = `${market}:${ticker}:${day}`;
              const trackedStatus = scannerTrackingStatus.get(key);
              const rank = numberValue(candidate.rank) ?? (index + 1);
              const buttonLabel = trackedStatus === "ACTIVE" ? "추적 중" : trackedStatus === "CLOSED" ? "추적 종료됨" : busyKey === key ? "추가 중…" : "추적 시작";
              return <div className="tracking-candidate" key={`${key}:${index}`}>
                <div><strong>{name} <small>{ticker}</small></strong><span>{rank ? `Rank ${rank} · ` : ""}{text(candidate.action_label) ?? text(candidate.strategy_easy_name) ?? "추천 후보"}</span></div>
                <button disabled={Boolean(trackedStatus) || busyKey === key} onClick={() => void addScanner(candidate)}>{buttonLabel}</button>
              </div>;
            })}
          </div>
        )}
      </section>

      <section className="tracking-source tracking-search-primary">
        <div className="tracking-section-head"><div><span>직접 추가</span><h2>원하는 종목 직접 찾기</h2></div><small>종목명 또는 코드만 입력 · 기준일과 기준가는 자동</small></div>
        <p className="feature-section-help">Scanner 추천이 아니어도 관심 있는 종목을 직접 추가해 같은 기준으로 관찰할 수 있습니다.</p>
        <div className="tracking-manual-search"><input value={manualQuery} onChange={(e) => setManualQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void runManualSearch(); }} placeholder="예: 삼성전자 또는 005930" /><button disabled={manualBusy} onClick={() => void runManualSearch()}>{manualBusy ? "검색 중…" : "검색"}</button></div>
        {manualRows.length > 0 && <div className="tracking-search-results">{manualRows.map((item) => {
          const key = `${item.market}:${item.code}`;
          const tracked = manualActiveKeys.has(key);
          return <button key={key} disabled={tracked} className={manualSelected?.code === item.code && manualSelected.market === item.market ? "selected" : ""} onClick={() => void selectManual(item)}><strong>{item.name} <small>{item.code}</small></strong><span>{tracked ? "추적 중" : item.market}</span></button>;
        })}</div>}
        {manualSelected && <div className="tracking-manual-preview-wrap"><div className="tracking-manual-preview"><div><span>선택 종목</span><strong>{manualSelected.name} <small>{manualSelected.code}</small></strong></div><div><span>추적 기준</span><strong>{manualPreview ? `${dateText(manualPreview.reference_date)} 확정 종가 · ${krw(manualPreview.reference_price)}` : "확정 종가 확인 중"}</strong></div><button disabled={!manualPreview || manualBusy || selectedManualActive || selectedManualSameDayClosed} onClick={() => void addManual()}>{manualBusy ? "처리 중…" : selectedManualActive ? "추적 중" : selectedManualSameDayClosed ? "다음 거래일부터 가능" : "추적 시작"}</button></div>{selectedManualSameDayClosed && <p className="tracking-manual-policy-note">이 종목은 같은 확정 거래일에 직접 추적을 종료했습니다. 새로운 확정 거래일이 생긴 뒤 다시 추적할 수 있습니다.</p>}</div>}
      </section>


      <section className="tracking-list tracking-list-always">
        <div className="tracking-section-head"><div><span>저장된 기록</span><h2>추적 중인 종목과 기록</h2></div><small>종목 · 출처 · 시작 기준 · 현재 상태를 한 화면에서 확인</small></div>
        <div className="feature-definition-line"><span><strong>추천</strong> Scanner가 찾은 종목</span><span><strong>직접</strong> 사용자가 추가한 종목</span><span><strong>추천 · 직접</strong> 같은 기준일·가격에서 두 조건이 모두 해당</span></div>
        <div className="tracking-list-filters"><div>{(["ALL", "SCANNER", "MANUAL"] as SourceFilter[]).map((value) => <button key={value} className={sourceFilter === value ? "active" : ""} onClick={() => setSourceFilter(value)}>{value === "ALL" ? "전체" : value === "SCANNER" ? "추천" : "직접"} <small>{sourceCounts[value]}</small></button>)}</div><div>{(["ALL", "ACTIVE", "CLOSED"] as StatusFilter[]).map((value) => <button key={value} className={statusFilter === value ? "active" : ""} onClick={() => setStatusFilter(value)}>{value === "ALL" ? "전체 상태" : value === "ACTIVE" ? "추적 중" : "종료"} <small>{statusCounts[value]}</small></button>)}</div></div>
        {visibleRows.length === 0 ? <div className="tracking-empty tracking-empty-action"><strong>{rows.length === 0 ? "아직 추적 중인 종목이 없습니다." : "현재 필터에 맞는 추적 기록이 없습니다."}</strong><span>{rows.length === 0 ? "위 종목 찾기에서 추천 후보를 선택하거나 원하는 종목을 직접 추가해 추적을 시작할 수 있습니다." : "다른 출처 또는 상태 필터를 선택해보세요."}</span></div> : (
          <div className="tracking-table-wrap"><table className="tracking-table"><thead><tr><th>종목</th><th>출처</th><th>시작일</th><th title="추적을 시작한 거래일의 확정 종가">기준가</th><th title="가장 최근 반영된 확정 종가">현재가</th><th title="기준가 대비 최신 성과">현재</th><th title="추적 시작 이후 가장 많이 상승했던 폭">최대 상승</th><th title="추적 시작 이후 가장 많이 하락했던 폭">최대 하락</th><th>경과</th><th>상태</th><th>관리</th></tr></thead><tbody>
            {visibleRows.map((row) => <Fragment key={row.id}>
              <tr className={expandedId === row.id ? "selected" : undefined}>
                <td><button className="tracking-row-button" onClick={() => setExpandedId((current) => current === row.id ? null : row.id)}><strong>{row.name} <small>{row.ticker}</small></strong></button></td>
                <td><span className="tracking-source-text">{sourceLabel(row)}</span></td><td>{dateText(row.recommendation_date)}</td><td>{krw(row.reference_price)}</td><PerformanceCells performance={row.performance} /><td>{trackingStateLabel(row.status)}{row.status === "CLOSED" && row.closed_market_date ? ` · ${dateText(row.closed_market_date)}` : ""}</td>
                <td>{row.status === "ACTIVE" ? <><button className="tracking-text-button" disabled={busyKey === row.id} onClick={() => void refreshOne(row.id)}>최신 반영</button><button className="tracking-text-button tracking-stop" disabled={busyKey === row.id} onClick={() => void close(row.id)}>추적 종료</button></> : <button className="tracking-text-button tracking-delete" disabled={busyKey === row.id} onClick={() => void remove(row)}>기록 삭제</button>}</td>
              </tr>
              {expandedId === row.id && <tr className="tracking-detail-row"><td colSpan={11}><div className="tracking-detail"><div className="tracking-detail-title"><div><strong>{row.name} {row.ticker}</strong><span>{sourceDetailLabel(row)} · 기준 {dateText(row.recommendation_date)} {krw(row.reference_price)}</span></div><span>{hasScannerSource(row) ? `${row.decision_status ?? "추천"}${row.rank ? ` · Rank ${row.rank}` : ""}` : "확정 종가 기준 추적"}</span></div>{(!row.performance || !row.performance.latest_close) && <p className="tracking-waiting-note">다음 거래일부터 성과가 계산됩니다.</p>}<div className="tracking-detail-grid"><dl><dt>현재가</dt><dd>{krw(row.performance?.latest_close)}</dd><dt>현재 성과</dt><dd className={`tracking-return ${pctTone(row.performance?.current_return_pct)}`}>{pct(row.performance?.current_return_pct)}</dd><dt>최대 상승</dt><dd>{pct(row.performance?.mfe_pct)}</dd><dt>최대 하락</dt><dd>{pct(row.performance?.mae_pct)}</dd></dl><dl><dt>5D</dt><dd>{pct(row.performance?.return_5d)}</dd><dt>10D</dt><dd>{pct(row.performance?.return_10d)}</dd><dt>20D</dt><dd>{pct(row.performance?.return_20d)}</dd></dl>{hasScannerSource(row) ? <dl><dt>Scanner</dt><dd>{row.scanner_version ?? "-"}</dd><dt>전략</dt><dd>{row.strategy ?? "-"}</dd><dt>진입 참고</dt><dd>{entryLabel(row)}</dd><dt>손절 참고</dt><dd>{row.stop_price ? touchLabel(Boolean(row.performance?.stop_touched), row.performance?.stop_touch_date ?? null) : "-"}</dd><dt>1차 목표</dt><dd>{row.target1_price ? touchLabel(Boolean(row.performance?.target1_touched), row.performance?.target1_touch_date ?? null) : "-"}</dd><dt>2차 목표</dt><dd>{row.target2_price ? touchLabel(Boolean(row.performance?.target2_touched), row.performance?.target2_touch_date ?? null) : "-"}</dd></dl> : <dl><dt>추적 출처</dt><dd>직접 추가</dd><dt>기준</dt><dd>확정 종가</dd><dt>추적 상태</dt><dd>{trackingStateLabel(row.status)}</dd></dl>}</div></div></td></tr>}
            </Fragment>)}
          </tbody></table></div>
        )}
      </section>
    </section>
  );
}
