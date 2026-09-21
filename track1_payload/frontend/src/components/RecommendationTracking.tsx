import { useEffect, useMemo, useState } from "react";
import { readScannerSession } from "./scannerSession";
import {
  addTrackedRecommendation,
  closeTrackedRecommendation,
  listTrackedRecommendations,
  TrackingApiError,
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
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(n)}원` : "-";
}
function dateText(value: string | null | undefined) { return value ? value.replace(/-/g, ".") : "-"; }

export default function RecommendationTracking() {
  const [rows, setRows] = useState<TrackedRecommendation[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const scannerSession = useMemo(() => readScannerSession(), []);
  const result = asRecord(scannerSession?.result);
  const scannerDate = text(result.requested_as_of);
  const candidates = Array.isArray(result.candidates) ? result.candidates.map(asRecord) : [];

  async function refresh() {
    try { setRows(await listTrackedRecommendations()); }
    catch (error) { setMessage(error instanceof Error ? error.message : "추천 추적 목록을 불러오지 못했습니다."); }
  }

  useEffect(() => { void refresh(); }, []);

  const trackedKeys = useMemo(
    () => new Set(rows.map((row) => `${row.market}:${row.ticker}:${row.recommendation_date}`)),
    [rows],
  );

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
      setMessage(response.created ? `${name} ${ticker} 추천을 추적하기 시작했습니다.` : `${name} ${ticker}은 이미 추적 중입니다.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof TrackingApiError ? error.message : error instanceof Error ? error.message : "추적 추가에 실패했습니다.");
    } finally { setBusyKey(null); }
  }

  async function close(id: string) {
    setBusyKey(id); setMessage(null);
    try { await closeTrackedRecommendation(id); await refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "추적 종료에 실패했습니다."); }
    finally { setBusyKey(null); }
  }

  return (
    <section className="tracking-workspace">
      <header className="tracking-head">
        <div><span>추천 성과 기록</span><h1>추천 추적</h1><p>종목 찾기에서 나온 추천을 저장하고 이후 실제 움직임을 누적하기 위한 공간입니다.</p></div>
        <div className="tracking-count"><strong>{rows.filter((row) => row.status === "ACTIVE").length}</strong><span>추적 중</span></div>
      </header>

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
        <div className="tracking-section-head"><div><span>저장된 추천</span><h2>추적 목록</h2></div><small>추천 당시 Snapshot과 확정 종가를 보존합니다.</small></div>
        {rows.length === 0 ? <p className="tracking-empty">아직 추적 중인 추천이 없습니다.</p> : (
          <div className="tracking-table-wrap"><table className="tracking-table"><thead><tr><th>종목</th><th>추천일</th><th>추천 기준가</th><th>판단</th><th>전략</th><th>상태</th><th /></tr></thead><tbody>
            {rows.map((row) => <tr key={row.id}><td><strong>{row.name} <small>{row.ticker}</small></strong></td><td>{dateText(row.recommendation_date)}</td><td>{krw(row.reference_price)}</td><td>{row.decision_status ?? "-"}</td><td>{row.strategy ?? "-"}</td><td>{row.status === "ACTIVE" ? "추적 중" : "종료"}</td><td>{row.status === "ACTIVE" && <button className="tracking-text-button" disabled={busyKey === row.id} onClick={() => void close(row.id)}>추적 종료</button>}</td></tr>)}
          </tbody></table></div>
        )}
      </section>
    </section>
  );
}
