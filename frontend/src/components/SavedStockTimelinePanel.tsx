import { useEffect, useRef, useState } from "react";
import {
  getSavedStockTimeline, type SavedStockTimelineEntry, type SavedStockTimeline,
  type SavedCaptureWindow,
} from "../services/api";

export type SelectedScannerStock = {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  name: string;
};

function observationLabel(window: SavedCaptureWindow | undefined): string {
  if (!window) return "자료 없음";
  const change = window.signal_close_change_pct;
  if (window.status === "OBSERVED" && typeof change === "number") {
    return (change > 0 ? "+" : "") + change.toFixed(2) + "%";
  }
  switch (window.status) {
    case "AWAITING_FUTURE_DAYS": return "관찰 대기";
    case "NOT_ENTRY_CANDIDATE": return "참조 기록";
    case "INTEGRITY_NOT_VERIFIED": return "원본 근거 부족";
    case "UNVERIFIED_CALENDAR_OR_DATA_GAP": return "시장 데이터 공백";
    case "PRICE_MISSING": return "가격 없음";
    case "MARKET_EVIDENCE_UNAVAILABLE": return "시장 근거 없음";
    default: return "확인 불가";
  }
}
function actionLabel(action: string | null): string {
  if (action === "ENTRY_CANDIDATE") return "진입 후보";
  if (action === "WAIT") return "대기";
  if (action === "NO_TRADE") return "관망";
  return action || "정보 없음";
}
function statusLabel(status: string) {
  if (status === "LOCAL_VALIDATED") return "원본 검증";
  if (status === "LEGACY_LIMITED") return "레거시 제한";
  if (status === "REFERENCE_ONLY") return "참조 기록";
  return "원본 근거 부족";
}
function dateTimeLabel(value: string | null) {
  if (!value) return "시각 미확인";
  const ts = new Date(value);
  return Number.isNaN(ts.valueOf())
    ? "시각 미확인"
    : ts.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "short" });
}

export default function SavedStockTimelinePanel({
  stock, onClose,
}: {
  stock: SelectedScannerStock | null;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<SavedStockTimelineEntry[]>([]);
  const [meta, setMeta] = useState<SavedStockTimeline | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [requestOffset, setRequestOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeButton = useRef<HTMLButtonElement | null>(null);
  const [loadKey, setLoadKey] = useState<string | null>(null);
  const key = stock ? stock.market + ":" + stock.ticker : null;

  // A new selection always opens at its most recent saved capture.
  useEffect(() => {
    setEntries([]);
    setMeta(null);
    setNext(null);
    setError(null);
    setRequestOffset(key ? 0 : null);
    setLoadKey(key);
  }, [key]);

  useEffect(() => {
    if (!stock || key !== loadKey || requestOffset === null) return;
    let active = true;
    setLoading(true);
    setError(null);
    void getSavedStockTimeline(stock.market, stock.ticker, requestOffset)
      .then(result => {
        if (!active) return;
        if (result.status !== "READY") {
          setError("저장된 종목 이력을 불러올 수 없습니다. (" + result.status + ")");
          return;
        }
        setMeta(result);
        setEntries(existing => requestOffset === 0
          ? result.entries || []
          : [...existing, ...(result.entries || [])]);
        setNext(result.next_offset ?? null);
      })
      .catch(() => {
        if (active) setError("종목 이력 서버에 연결하지 못했습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [stock, key, loadKey, requestOffset]);

  useEffect(() => {
    if (stock) closeButton.current?.focus();
  }, [key, stock]);

  if (!stock) return null;

  const groups = new Set(entries.map(item => item.signal_date));
  const duplicateSignals = entries.length - groups.size;

  return (
    <section className="scanner-stock-timeline" aria-label={stock.name + " 저장 Scanner 추천 이력"}>
      <div className="scanner-capture-journal-head">
        <div>
          <strong>{stock.name} · 추천 기록 타임라인</strong>
          <p>{stock.market} · {stock.ticker} · 저장된 Scanner 결과에만 포함된 기록</p>
        </div>
        <button type="button" ref={closeButton} onClick={onClose}>종목 이력 닫기</button>
      </div>
      {meta?.summary && (
        <div className="scanner-capture-diff-stats" aria-label="종목 이력 요약">
          <div><small>저장 캡처 등장</small><strong>{meta.summary.capture_appearances}회</strong></div>
          <div><small>서로 다른 기준 거래일</small><strong>{meta.summary.distinct_signal_days}일</strong></div>
          <div><small>최초 등장 기준일</small><strong>{meta.summary.first_signal_date || "미확인"}</strong></div>
          <div><small>마지막 등장 기준일</small><strong>{meta.summary.latest_signal_date || "미확인"}</strong></div>
        </div>
      )}
      {duplicateSignals > 0 && (
        <p className="scanner-capture-journal-warning">
          같은 기준일에 여러 번 수집된 기록이 {duplicateSignals}건 포함되어 있습니다. 각각의 실행은 보존하지만 별개 추천 거래일로 중복 계산하지 않습니다.
        </p>
      )}
      {loading && <p role="status">종목 추천 기록을 읽는 중...</p>}
      {error && <p role="alert" className="scanner-capture-journal-error">{error}</p>}
      {!loading && !error && meta?.summary?.capture_appearances === 0 &&
        <p>이 종목의 저장된 COMPLETE 추천 기록이 없습니다.</p>}
      {entries.length > 0 && (
        <>
          <p className="scanner-capture-journal-note">
            순위는 각 실행에서 저장한 값이며 서로 다른 Scanner 정책·후보 제한 간 상승·하락을 주장하지 않습니다.
            관찰 자료 확인 기준 {meta?.market_eod_cutoff_date || "미확인"} · 매매 수익률이 아닌 신호일 종가 대비 변화입니다.
          </p>
          <div className="scanner-capture-journal-table-wrap">
            <table>
              <thead><tr>
                <th scope="col">추천 기준일 / 수집 시각</th>
                <th scope="col">저장 순위</th>
                <th scope="col">전략</th>
                <th scope="col">당시 상태</th>
                <th scope="col">근거</th>
                <th scope="col">5거래일</th>
                <th scope="col">10거래일</th>
                <th scope="col">20거래일</th>
              </tr></thead>
              <tbody>
                {entries.map((entry, index) => (
                  <tr key={entry.capture_id + ":" + entry.sample_index}>
                    <th scope="row">
                      {entry.signal_date}
                      <small>{dateTimeLabel(entry.captured_at)}</small>
                      {index > 0 && entry.signal_date === entries[index - 1].signal_date &&
                        <small>동일 기준일 반복 수집</small>}
                    </th>
                    <td>{entry.rank ?? "미확인"}</td>
                    <td>{entry.strategy || "미확인"}</td>
                    <td>{actionLabel(entry.action)}
                      {entry.candidate_state && <small>{entry.candidate_state}</small>}
                    </td>
                    <td>{statusLabel(entry.integrity_category)}</td>
                    {(["5d", "10d", "20d"] as const).map(window => (
                      <td key={window} title={entry.windows[window]?.status}>
                        {observationLabel(entry.windows[window])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {next !== null && (
            <button type="button" disabled={loading}
              onClick={() => setRequestOffset(next)}>
              {loading ? "조회 중..." : "이전 기록 더 보기"}
            </button>
          )}
        </>
      )}
      <p className="scanner-capture-journal-note">
        기록이 없는 날짜는 이 종목이 실제로 Scanner 심사에서 탈락했다는 증거가 아닙니다.
        저장된 COMPLETE 목록에 들어온 기록만 표시합니다. 이 화면은 관심종목·보유종목을 자동 등록하지 않습니다.
      </p>
    </section>
  );
}
