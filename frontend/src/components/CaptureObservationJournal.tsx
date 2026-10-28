import { useEffect, useState } from "react";
import {
  getSavedCaptureJournalDetail, listSavedCaptureJournal,
  type SavedCaptureJournalDetail, type SavedCaptureJournalItem,
  type SavedCaptureWindow,
} from "../services/api";
import "./captureObservationJournal.css";
import CaptureHistoryComparison from "./CaptureHistoryComparison";

function dateLabel(value: string | null | undefined) {
  if (!value) return "날짜 미확인";
  const day = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : "날짜 미확인";
}

function windowLabel(window: SavedCaptureWindow | undefined) {
  if (!window) return "확인 불가";
  if (window.status === "OBSERVED" && typeof window.signal_close_change_pct === "number") {
    const val = window.signal_close_change_pct;
    return (val > 0 ? "+" : "") + val.toFixed(2) + "%";
  }
  if (window.status === "AWAITING_FUTURE_DAYS") return "관찰 대기";
  if (window.status === "NOT_ENTRY_CANDIDATE") return "비교 대상 아님";
  if (window.status === "INTEGRITY_NOT_VERIFIED") return "원본 근거 부족";
  if (window.status === "UNVERIFIED_CALENDAR_OR_DATA_GAP") return "시장 데이터 공백";
  if (window.status === "PRICE_MISSING") return "가격 없음";
  if (window.status === "POST_AS_OF_DATA_REJECTED") return "미래 자료 제외";
  return "자료 확인 불가";
}

function timeLabel(value: string | null | undefined) {
  if (!value) return "";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function CaptureObservationJournal({
  currentCaptureId,
}: {
  currentCaptureId: string | null;
}) {
  const [opened, setOpened] = useState(false);
  const [captures, setCaptures] = useState<SavedCaptureJournalItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<SavedCaptureJournalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!opened) return;
    let alive = true;
    setBusy(true);
    setError(null);
    void listSavedCaptureJournal().then(reply => {
      if (!alive) return;
      if (reply.status !== "READY") {
        setCaptures([]);
        setError("저장된 후보 기록을 읽을 수 없어요.");
        return;
      }
      setCaptures(reply.captures);
      setSelected(previous => {
        const preferred = currentCaptureId && reply.captures.some(c => c.id === currentCaptureId)
          ? currentCaptureId : null;
        return previous && reply.captures.some(c => c.id === previous)
          ? previous : preferred || reply.captures[0]?.id || null;
      });
    }).catch(() => {
      if (alive) setError("수집 기록 연결을 확인해 주세요.");
    }).finally(() => {
      if (alive) setBusy(false);
    });
    return () => { alive = false; };
  }, [opened, revision, currentCaptureId]);

  useEffect(() => {
    if (!opened || !selected) {
      setDetail(null);
      return;
    }
    let alive = true;
    setBusy(true);
    setError(null);
    setDetail(null);
    void getSavedCaptureJournalDetail(selected).then(reply => {
      if (!alive) return;
      if (reply.status !== "READY") {
        setError("선택한 캡처의 관찰 정보를 확인할 수 없어요. (" + reply.status + ")");
        return;
      }
      setDetail(reply);
    }).catch(() => {
      if (alive) setError("저장 후보의 관찰 정보를 불러오지 못했어요.");
    }).finally(() => {
      if (alive) setBusy(false);
    });
    return () => { alive = false; };
  }, [opened, selected, revision]);

  return (
    <section className="scanner-capture-journal" aria-label="저장 후보 날짜별 관찰">
      <div className="scanner-capture-journal-head">
        <div>
          <strong>저장 후보 · 날짜별 관찰</strong>
          <p>전에 찾은 후보를 다시 볼 수 있어요. 이후 확정 일봉이 쌓이면 5·10·20거래일 종가 변화를 표시합니다.</p>
        </div>
        <button type="button" onClick={() => setOpened(was => !was)}>
          {opened ? "수집 기록 닫기" : "수집 기록 보기"}
        </button>
      </div>
      {opened && (
        <div className="scanner-capture-journal-content">
          <div className="scanner-capture-journal-toolbar">
            <label>
              분석 기록
              <select
                aria-label="저장된 수집일 선택"
                value={selected || ""}
                onChange={event => setSelected(event.currentTarget.value || null)}
                disabled={captures.length === 0}
              >
                {!selected && <option value="">수집 기록을 선택하세요</option>}
                {captures.map(capture => (
                  <option value={capture.id} key={capture.id}>
                    {dateLabel(capture.actual_data_date)} 기준 · {capture.market_scope} · {capture.returned_candidate_count}건 · {timeLabel(capture.created_at)}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" disabled={busy} onClick={() => setRevision(v => v + 1)}>
              {busy ? "확인 중..." : "최신 관찰 갱신"}
            </button>
          </div>
          {error && <p className="scanner-capture-journal-error" role="alert">{error}</p>}
          {!busy && captures.length === 0 && !error && <p>저장된 COMPLETE 후보 기록이 없습니다.</p>}
          {detail?.capture && (
            <>
              <p className="scanner-capture-journal-meta">
                {dateLabel(detail.capture.actual_data_date)} 확정 일봉 기준 · 저장 {detail.capture.sample_count}건
                · 관찰 자료 확인 상한 {detail.market_eod_cutoff_date || "미확인"}
                · 실제 진입·체결 수익률 아님
              </p>
              <div className="scanner-capture-journal-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">저장 후보</th>
                      <th scope="col">근거</th>
                      <th scope="col">5거래일</th>
                      <th scope="col">10거래일</th>
                      <th scope="col">20거래일</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.candidates.map(candidate => (
                      <tr key={candidate.sample_index}>
                        <th scope="row" id={"scanner-capture-observation-" + candidate.sample_index}>
                          {candidate.name || candidate.ticker}
                          <small>{candidate.market} · {candidate.ticker}
                            {candidate.rank != null ? " · 순위 " + candidate.rank : ""}
                          </small>
                        </th>
                        <td>
                          {candidate.action === "ENTRY_CANDIDATE"
                            ? candidate.integrity_category === "LOCAL_VALIDATED" ? "원본 검증"
                            : candidate.integrity_category === "LEGACY_LIMITED" ? "레거시 제한"
                            : "원본 근거 부족"
                            : "참조 기록"}
                        </td>
                        {(["5d", "10d", "20d"] as const).map(window => (
                          <td key={window} title={candidate.windows[window]?.status}>
                            {windowLabel(candidate.windows[window])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <CaptureHistoryComparison
                currentId={selected}
                captures={captures}
                detail={detail}
                revision={revision}
              />
              <p className="scanner-capture-journal-note">
                관찰 수치는 추천 당일 종가 대비 이후 확정 종가의 변화입니다.
                당일 이후에 생성된 기록은 장전 추천 성과로 인정하지 않으며, 누락된 거래일·시세는 수익률로 추정하지 않습니다.
                최신 관찰 갱신은 저장 DB 조회만 수행하고 후보 수집·거래·승인은 실행하지 않습니다.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
