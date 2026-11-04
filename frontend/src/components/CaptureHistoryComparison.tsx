import { useEffect, useMemo, useState } from "react";
import type { SelectedScannerStock } from "./SavedStockTimelinePanel";
import {
  compareSavedCaptureHistory,
  type SavedCaptureComparison,
  type SavedCaptureDiffItem,
  type SavedCaptureJournalDetail,
  type SavedCaptureJournalItem,
} from "../services/api";

function labelDate(date: string | null | undefined) {
  return date || "기준일 불명";
}
function reasonLabel(code: string) {
  switch (code) {
    case "MARKET_SCOPE_CHANGED": return "시장 범위가 다릅니다";
    case "SCANNER_VERSION_CHANGED": return "Scanner 버전이 다릅니다";
    case "SCANNER_BASELINE_CHANGED": return "Scanner 기준선이 다릅니다";
    case "CANDIDATE_LIMIT_CHANGED": return "후보 수집 제한이 다릅니다";
    case "SELECTION_POLICY_CHANGED": return "전략 선택 정책이 다릅니다";
    case "SELECTION_POLICY_UNVERIFIED": return "선택 정책의 원본 근거가 부족합니다";
    default: return "비교 조건 확인 필요";
  }
}
function movement(item: SavedCaptureDiffItem) {
  switch (item.rank_movement) {
    case "UP": return "▲ " + item.rank_delta + "계단";
    case "DOWN": return "▼ " + Math.abs(item.rank_delta || 0) + "계단";
    case "SAME": return "변동 없음";
    case "NOT_COMPARABLE": return "순위 비교 불가";
    default: return "–";
  }
}
function actionLabel(action: string | null | undefined) {
  if (action === "ENTRY_CANDIDATE") return "진입 후보";
  if (action === "WAIT") return "대기";
  if (action === "NO_TRADE") return "관망";
  return action || "미확인";
}

export default function CaptureHistoryComparison({
  currentId,
  captures,
  detail,
  revision,
  onSelectStock,
}: {
  currentId: string | null;
  captures: SavedCaptureJournalItem[];
  detail: SavedCaptureJournalDetail | null;
  revision: number;
  onSelectStock: (stock: SelectedScannerStock) => void;
}) {
  const eligible = useMemo(() => {
    const current = captures.find(c => c.id === currentId);
    const currentDataDate = current?.actual_data_date;
    if (!currentDataDate) return [];
    return captures
      .filter(c => c.id !== currentId && c.actual_data_date &&
        c.actual_data_date < currentDataDate)
      .sort((a, b) => (b.actual_data_date || "").localeCompare(a.actual_data_date || "")
        || (b.created_at || "").localeCompare(a.created_at || ""));
  }, [captures, currentId]);
  const [previousId, setPreviousId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<SavedCaptureComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosenPrevious = eligible.some(c => c.id === previousId)
    ? previousId : eligible[0]?.id || null;

  useEffect(() => {
    if (!currentId || !chosenPrevious) {
      setComparison(null);
      setError(null);
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setComparison(null);
    setError(null);
    void compareSavedCaptureHistory(currentId, chosenPrevious)
      .then(result => {
        if (!active) return;
        if (result.status !== "READY") {
          setError("두 기록을 비교할 수 없습니다. (" + result.status + ")");
          return;
        }
        setComparison(result);
      })
      .catch(() => {
        if (active) setError("기록 비교 정보를 읽어오지 못했습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [currentId, chosenPrevious, revision]);

  const latest = new Map(
    (detail?.candidates || []).map(c => [c.market + ":" + c.ticker, c]),
  );

  return (
    <section className="scanner-capture-diff" aria-label="날짜별 후보 변경 비교">
      <h4>이전 수집과 비교</h4>
      <p className="scanner-capture-journal-note">
        두 시점의 Scanner 반환 후보 목록을 비교합니다. 목록에서 사라진 종목은 매도·탈락을 뜻하지 않습니다.
      </p>
      {eligible.length === 0 ? (
        <p className="scanner-capture-journal-meta">
          선택한 기록보다 이전 기준일에 저장한 COMPLETE 수집 기록이 없습니다. 서로 다른 날짜의 기록이 필요합니다.
        </p>
      ) : (
        <>
          <div className="scanner-capture-journal-toolbar">
            <label>
              비교할 이전 수집 기록
              <select
                aria-label="비교할 이전 수집일 선택"
                value={chosenPrevious || ""}
                onChange={event => setPreviousId(event.currentTarget.value || null)}
              >
                {eligible.map(c => (
                  <option key={c.id} value={c.id}>
                    {labelDate(c.actual_data_date)} · {c.market_scope} · {c.returned_candidate_count}건
                  </option>
                ))}
              </select>
            </label>
            <span className="scanner-capture-journal-meta">
              현재 기준일 {labelDate(captures.find(c => c.id === currentId)?.actual_data_date)}
            </span>
          </div>
          {loading && <p role="status">저장된 두 기록을 비교하고 있어요.</p>}
          {error && <p role="alert" className="scanner-capture-journal-error">{error}</p>}
          {comparison?.summary && (
            <>
              <div className="scanner-capture-diff-stats" aria-label="두 시점 후보 변화 요약">
                <div><small>신규 등장</small><strong>{comparison.summary.new}개</strong></div>
                <div><small>연속 등장</small><strong>{comparison.summary.retained}개</strong></div>
                <div><small>목록 제외</small><strong>{comparison.summary.removed_from_returned_list}개</strong></div>
                <div><small>순위 상승 / 하락</small><strong>
                  {comparison.comparability?.rank_comparable
                    ? comparison.summary.rank_up + " / " + comparison.summary.rank_down
                    : "비교 제한"}
                </strong></div>
              </div>
              {(comparison.comparability?.warnings.length || 0) > 0 && (
                <p className="scanner-capture-journal-warning" role="status">
                  비교 조건이 다릅니다: {comparison.comparability?.warnings.map(reasonLabel).join(" · ")}.
                  목록 출현 여부만 참고하고, 순위 변동은 비교하지 않습니다.
                </p>
              )}
              <div className="scanner-capture-journal-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">종목</th>
                      <th scope="col">등장 여부</th>
                      <th scope="col">이전 순위</th>
                      <th scope="col">현재 순위</th>
                      <th scope="col">순위 변화</th>
                      <th scope="col">전략 / 상태 변화</th>
                      <th scope="col">현재 관찰</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(comparison.items || []).map(item => {
                      const current = latest.get(item.market + ":" + item.ticker);
                      const changes = [
                        item.strategy_changed ? "전략 변경" : null,
                        item.action_changed ? actionLabel(item.previous?.action) + " → " + actionLabel(item.current?.action) : null,
                        item.state_changed ? "후보 상태 변경" : null,
                      ].filter(Boolean);
                      return (
                        <tr key={item.market + ":" + item.ticker}>
                          <th scope="row">
                            <button
                              type="button"
                              className="scanner-capture-stock-link"
                              onClick={() => {
                                if (item.market === "KOSPI" || item.market === "KOSDAQ") {
                                  onSelectStock({ market: item.market, ticker: item.ticker, name: item.name });
                                }
                              }}
                              disabled={item.market !== "KOSPI" && item.market !== "KOSDAQ"}
                              aria-label={item.name + " 추천 이력 열기"}
                            >{item.name}</button>
                            <small>{item.market} · {item.ticker}</small>
                          </th>
                          <td>
                            {item.presence === "NEW" ? "신규" :
                              item.presence === "RETAINED" ? "연속" : "목록 제외"}
                          </td>
                          <td>{item.previous?.rank ?? "–"}</td>
                          <td>{item.current?.rank ?? "–"}</td>
                          <td>{movement(item)}</td>
                          <td>
                            {changes.length ? changes.join(" · ") : "변경 없음"}
                            {item.strategy_changed && (
                              <small>{item.previous?.strategy || "미확인"} → {item.current?.strategy || "미확인"}</small>
                            )}
                          </td>
                          <td>
                            {current ? (
                              <a href={"#scanner-capture-observation-" + current.sample_index}>
                                5·10·20일 관찰 보기
                              </a>
                            ) : "이전 기록에서 확인"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="scanner-capture-journal-note">
                기록 간 차이는 Scanner 반환 목록에 한정되며 시장 전체 종목의 진입·청산이나 실제 투자 수익률을 의미하지 않습니다.
                상세한 5·10·20거래일 종가 변화는 선택한 현재 기록의 관찰표에서 확인합니다.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
