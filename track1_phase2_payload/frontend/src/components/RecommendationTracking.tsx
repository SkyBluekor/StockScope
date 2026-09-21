import { Fragment, useEffect, useMemo, useState } from "react";
import { readScannerSession } from "./scannerSession";
import {
  addTrackedRecommendation,
  closeTrackedRecommendation,
  listTrackedRecommendations,
  refreshActiveTrackedRecommendations,
  refreshTrackedRecommendation,
  TrackingApiError,
  type RecommendationPerformance,
  type TrackedRecommendation,
} from "../services/trackingApi";
import "../tracking.css";

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" ? value as UnknownRecord : {};
}
function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
function numberValue(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function price(value: unknown): string | number | null {
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
  const [rows, setRows] = useState<TrackedRecommendation[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lastMarketDate, setLastMarketDate] = useState<string | null>(null);
  const scannerSession = useMemo(() => readScannerSession(), []);
  const result = asRecord(scannerSession?.result);
  const scannerDate = text(result.requested_as_of);
  const candidates = Array.isArray(result.candidates) ? result.candidates.map(asRecord) : [];

  async function loadRows() {
    try {
      const next = await listTrackedRecommendations();
      setRows(next);
      const dates = next.map((row) => row.performance?.market_date).filter((value): value is string => Boolean(value));
      if (dates.length) { dates.sort(); setLastMarketDate(dates[dates.length - 1] ?? null); }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "추천 추적 목록을 불러오지 못했습니다.");
    }
  }

  useEffect(() => { void loadRows(); }, []);

  const trackedKeys = useMemo(
    () => new Set(rows.map((row) => `${row.market}:${row.ticker}:${row.recommendation_date}`)),
    [rows],
  );
  const activeCount = rows.filter((row) => row.status === "ACTIVE").length;

  async function add(candidate: UnknownRecord) {
    const ticker = text(candidate.code);
    const name = text(candidate.name);
    const market = text(candidate.market);
    const recommendationDate = text(candidate.data_date) ?? scannerDate;
    if (!ticker || !name || !market || !recommendationDate) {
      setMessage("이 추천은 날짜 또는 종목 정보가 부족해 추적할 수 없습니다.");
      return;
    }
    const key = `${market}:${ticker}:${recommendationDate}`;
    setBusyKey(key); setMessage(null);
    try {
      const response = await addTrackedRecommendation({
        ticker, name, market, recommendation_date: recommendationDate, source: "SCANNER",
        scanner_version: text(result.scanner_version) ?? text(result.version),
        scanner_baseline: text(result.scanner_baseline) ?? text(result.baseline_id),
        strategy: text(candidate.strategy) ?? text(candidate.strategy_easy_name),
        decision_status: text(candidate.decision_status) ?? text(candidate.status) ?? text(candidate.action_label),
        rank: numberValue(candidate.rank),
        entry_price: price(candidate.entry) ?? price(candidate.entry_price),
        stop_price: price(candidate.stop) ?? price(candidate.stop_price),
        target1_price: price(candidate.target1) ?? price(candidate.target1_price),
        target2_price: price(candidate.target2) ?? price(candidate.target2_price),
        snapshot: { scanner_result_date: scannerDate, candidate },
      });
      setMessage(response.created ? `${name} ${ticker} 추천을 추적하기 시작했습니다.` : `${name} ${ticker}은 이미 저장되어 있습니다.`);
      await loadRows();
    } catch (error) {
      setMessage(error instanceof TrackingApiError ? error.message : error instanceof Error ? error.message : "추적 추가에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function close(id: string) {
    setBusyKey(id); setMessage(null);
    try { await closeTrackedRecommendation(id); await loadRows(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "추적 종료에 실패했습니다."); }
    finally { setBusyKey(null); }
  }

  async function refreshOne(id: string) {
    setBusyKey(id); setMessage(null);
    try {
      const updated = await refreshTrackedRecommendation(id);
      setRows((current) => current.map((row) => row.id === id ? updated : row));
      if (updated.performance?.market_date) setLastMarketDate(updated.performance.market_date);
      setMessage(`${updated.name} ${updated.ticker} 성과를 최신 데이터로 반영했습니다.`);
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
      setMessage(summary.failed ? `${base} · 실패 ${summary.failed}` : base);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "최신 데이터 반영에 실패했습니다.");
    } finally { setBulkBusy(false); }
  }

  return (
    <section className="tracking-workspace">
      <header className="tracking-head">
        <div><span>추천 성과 기록</span><h1>추천 추적</h1><p>추천 당시 판단을 고정하고, 이후 확정 일봉에서 실제 가격 움직임을 계속 기록합니다.</p></div>
        <div className="tracking-summary"><div><strong>{activeCount}</strong><span>추적 중</span></div><button disabled={bulkBusy || activeCount === 0} onClick={() => void refreshAll()}>{bulkBusy ? "반영 중…" : "최신 데이터 반영"}</button></div>
      </header>

      <div className="tracking-meta-line"><span>최근 반영 {dateText(lastMarketDate)}</span><span>성과는 추천일 다음 거래일부터 계산</span></div>
      {message && <div className="tracking-notice">{message}</div>}

      <section className="tracking-source">
        <div className="tracking-section-head"><div><span>최근 종목 찾기</span><h2>추천에서 바로 추가</h2></div><small>기준일 {dateText(scannerDate)}</small></div>
        {!scannerSession ? <p className="tracking-empty">저장된 종목 찾기 결과가 없습니다. 먼저 종목 찾기를 실행해주세요.</p> : candidates.length === 0 ? <p className="tracking-empty">추가할 추천 후보가 없습니다.</p> : (
          <div className="tracking-candidates">
            {candidates.slice(0, 10).map((candidate, index) => {
              const ticker = text(candidate.code) ?? "-";
              const name = text(candidate.name) ?? "종목";
              const market = text(candidate.market) ?? "KRX";
              const day = text(candidate.data_date) ?? scannerDate ?? "";
              const key = `${market}:${ticker}:${day}`;
              const tracked = trackedKeys.has(key);
              return <div className="tracking-candidate" key={`${key}:${index}`}>
                <div><strong>{name} <small>{ticker}</small></strong><span>{text(candidate.action_label) ?? text(candidate.strategy_easy_name) ?? "추천 후보"}</span></div>
                <button disabled={tracked || busyKey === key} onClick={() => void add(candidate)}>{tracked ? "추적 중" : busyKey === key ? "추가 중…" : "추적 추가"}</button>
              </div>;
            })}
          </div>
        )}
      </section>

      <section className="tracking-list">
        <div className="tracking-section-head"><div><span>저장된 추천</span><h2>추적 목록</h2></div><small>추천 Snapshot은 그대로 두고 성과 데이터만 갱신합니다.</small></div>
        {rows.length === 0 ? <div className="tracking-empty tracking-empty-action"><strong>아직 추적 중인 추천이 없습니다.</strong><span>종목 찾기에서 추천 후보를 추가하면 이후 실제 가격 움직임을 기록합니다.</span></div> : (
          <div className="tracking-table-wrap"><table className="tracking-table"><thead><tr><th>종목</th><th>추천일</th><th>추천가</th><th>현재가</th><th>현재</th><th>최대 상승</th><th>최대 하락</th><th>경과</th><th>상태</th><th /></tr></thead><tbody>
            {rows.map((row) => <Fragment key={row.id}>
              <tr key={row.id} className={expandedId === row.id ? "selected" : undefined}>
                <td><button className="tracking-row-button" onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}><strong>{row.name} <small>{row.ticker}</small></strong></button></td>
                <td>{dateText(row.recommendation_date)}</td><td>{krw(row.reference_price)}</td>
                <PerformanceCells performance={row.performance} />
                <td>{row.status === "ACTIVE" ? "추적 중" : "종료"}</td>
                <td>{row.status === "ACTIVE" ? <button className="tracking-text-button" disabled={busyKey === row.id} onClick={() => void refreshOne(row.id)}>갱신</button> : <span className="tracking-muted">-</span>}</td>
              </tr>
              {expandedId === row.id && <tr key={`${row.id}:detail`} className="tracking-detail-row"><td colSpan={10}><RecommendationDetail row={row} busy={busyKey === row.id} onClose={() => void close(row.id)} /></td></tr>}
            </Fragment>)}
          </tbody></table></div>
        )}
      </section>
    </section>
  );
}

function RecommendationDetail({ row, busy, onClose }: { row: TrackedRecommendation; busy: boolean; onClose: () => void }) {
  const p = row.performance;
  return <div className="tracking-detail">
    <div className="tracking-detail-title"><div><strong>{row.name} {row.ticker}</strong><span>{row.decision_status ?? "-"}{row.rank != null ? ` · Rank ${row.rank}` : ""}{row.strategy ? ` · ${row.strategy}` : ""}</span></div>{row.status === "ACTIVE" && <button className="tracking-text-button" disabled={busy} onClick={onClose}>추적 종료</button>}</div>
    <div className="tracking-detail-grid">
      <dl><dt>추천가</dt><dd>{krw(row.reference_price)}</dd><dt>현재가</dt><dd>{krw(p?.latest_close)}{p?.price_status === "STALE" ? " · 지연" : ""}</dd><dt>현재 성과</dt><dd className={`tracking-return ${pctTone(p?.current_return_pct)}`}>{pct(p?.current_return_pct)}</dd></dl>
      <dl><dt>5D</dt><dd className={`tracking-return ${pctTone(p?.return_5d)}`}>{pct(p?.return_5d)}</dd><dt>10D</dt><dd className={`tracking-return ${pctTone(p?.return_10d)}`}>{pct(p?.return_10d)}</dd><dt>20D</dt><dd className={`tracking-return ${pctTone(p?.return_20d)}`}>{pct(p?.return_20d)}</dd></dl>
      <dl><dt>진입 참고가</dt><dd>{row.entry_price ? `${krw(row.entry_price)} · ${touchLabel(Boolean(p?.entry_touched), p?.entry_touch_date ?? null)}` : "-"}</dd><dt>손절 참고가</dt><dd>{row.stop_price ? `${krw(row.stop_price)} · ${touchLabel(Boolean(p?.stop_touched), p?.stop_touch_date ?? null)}` : "-"}</dd></dl>
      <dl><dt>1차 목표</dt><dd>{row.target1_price ? `${krw(row.target1_price)} · ${touchLabel(Boolean(p?.target1_touched), p?.target1_touch_date ?? null)}` : "-"}</dd><dt>2차 목표</dt><dd>{row.target2_price ? `${krw(row.target2_price)} · ${touchLabel(Boolean(p?.target2_touched), p?.target2_touch_date ?? null)}` : "-"}</dd></dl>
    </div>
    <div className="tracking-events">
      <span>추천 {dateText(row.recommendation_date)}</span>
      {p?.entry_touch_date && <span>진입 참고가 {dateText(p.entry_touch_date)}</span>}
      {p?.stop_touch_date && <span>손절 참고가 {dateText(p.stop_touch_date)}</span>}
      {p?.target1_touch_date && <span>1차 목표 {dateText(p.target1_touch_date)}</span>}
      {p?.target2_touch_date && <span>2차 목표 {dateText(p.target2_touch_date)}</span>}
    </div>
  </div>;
}
