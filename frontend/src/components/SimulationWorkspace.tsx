import { useEffect, useMemo, useState } from "react";
import {
  cancelValidationReplay,
  createValidationDraft,
  deleteLegacyValidation,
  deleteValidationDraft,
  getValidationDraft,
  getValidationOutcomeBreakdown,
  getValidationOutcomeSummary,
  listLegacyValidations,
  listValidationDrafts,
  previewValidationPeriod,
  refreshValidationOutcomes,
  runValidationReplay,
  SimulationApiError,
  type HistoricalValidationDraft,
  type HistoricalValidationOutcomeBreakdown,
  type HistoricalValidationOutcomeSummary,
  type ValidationOutcomeBreakdownRow,
  type LegacyValidation,
  type ValidationPeriodPreview,
} from "../services/simulationApi";
import "../simulation.css";

type Mode = "new" | "saved";
type Preset = "6m" | "1y" | "2y" | "custom";

const PRODUCTION_SCANNER_VERSION = "0.21.3.7";

function dateText(value: string | null | undefined) { return value ? value.replace(/-/g, ".") : "-"; }
function money(value: string | null | undefined) {
  const n = Number(value);
  return Number.isFinite(n) ? `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(n)}원` : "-";
}
function errorText(error: unknown) {
  if (error instanceof SimulationApiError) return error.message;
  return error instanceof Error ? error.message : "검증 정보를 처리하지 못했습니다.";
}
function marketLabel(value: string) { return value === "ALL" ? "전체" : value; }
function statusLabel(value: string) {
  if (value === "DRAFT") return "준비";
  if (value === "RUNNING") return "실행 중";
  if (value === "COMPLETED") return "완료";
  if (value === "FAILED") return "실패";
  if (value === "CANCELLED") return "중지됨";
  return value;
}
function replayPercent(row: HistoricalValidationDraft) {
  if (row.trading_day_count <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((row.processed_day_count / row.trading_day_count) * 100)));
}
function replayStatusLabel(row: HistoricalValidationDraft) {
  if (row.status === "RUNNING" && row.runtime_active === false) return "실행 중단됨";
  return statusLabel(row.status);
}

function pctText(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
function countText(value: number | null | undefined) {
  return `${Number(value ?? 0).toLocaleString("ko-KR")}건`;
}
function touchText(value: { touched_count: number; comparable_count: number; touched_pct: number | null }) {
  if (value.comparable_count <= 0) return "비교 기준 없음";
  const rate = value.touched_pct == null ? "-" : `${value.touched_pct.toFixed(1)}%`;
  return `${value.touched_count.toLocaleString("ko-KR")} / ${value.comparable_count.toLocaleString("ko-KR")}건 · ${rate}`;
}
function averageMedianNote(average: number | null | undefined, median: number | null | undefined) {
  if (average == null || median == null || !Number.isFinite(average) || !Number.isFinite(median)) {
    return "평균과 중앙값은 확인 가능한 표본만 사용합니다.";
  }
  const gap = average - median;
  if (Math.abs(gap) < 0.005) {
    return "평균과 중앙값이 거의 같습니다. 두 값 모두 결과 분포를 이해할 때 함께 확인합니다.";
  }
  return `평균은 중앙값보다 ${Math.abs(gap).toFixed(2)}%p ${gap > 0 ? "높습니다" : "낮습니다"}. 큰 상승·하락 사례가 평균에 영향을 줄 수 있으므로 두 값을 함께 확인합니다.`;
}

const validationStrategyLabels: Record<string, string> = {
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
  UNKNOWN: "전략 정보 없음",
};
const validationDecisionLabels: Record<string, string> = {
  READY: "진입 후보",
  WATCH: "관심 유지",
  NOT_READY: "현재 우선순위 낮음",
  CAUTION: "주의하며 관찰",
  BLOCKED: "위험 때문에 보류",
  NO_TRADE: "신규 진입 제외",
  UNKNOWN: "판단 정보 없음",
};
function validationStrategyLabel(key: string) {
  return validationStrategyLabels[key] ?? key;
}
function validationDecisionLabel(key: string) {
  return validationDecisionLabels[key] ?? key;
}
function touchPctText(value: { comparable_count: number; touched_count: number; touched_pct: number | null }) {
  if (value.comparable_count <= 0 || value.touched_pct == null) return "-";
  return `${value.touched_pct.toFixed(1)}%`;
}

function ValidationBreakdownDetail({
  row,
  label,
}: {
  row: ValidationOutcomeBreakdownRow;
  label: string;
}) {
  return (
    <div className="sim-breakdown-detail">
      <strong>{label} 상세</strong>
      <div className="sim-breakdown-detail-grid">
        {(["5d", "10d", "20d"] as const).map((horizon) => {
          const metric = row.horizons[horizon];
          const title = horizon === "5d" ? "5거래일 뒤" : horizon === "10d" ? "10거래일 뒤" : "20거래일 뒤";
          return (
            <div key={horizon}>
              <span>{title}</span>
              <strong>{pctText(metric.average_pct)}</strong>
              <small>중앙값 {pctText(metric.median_pct)} · 표본 {countText(metric.sample_count)}</small>
            </div>
          );
        })}
      </div>
      <div className="sim-breakdown-detail-meta">
        <div>
          <span>20거래일 가격 움직임</span>
          <strong>최고 상승폭 {pctText(row.mfe_20d.average_pct)}</strong>
          <small>최대 하락폭 {pctText(row.mae_20d.average_pct)}</small>
        </div>
        <div>
          <span>20거래일 가격 기준 도달</span>
          <strong>1차 목표 {touchText(row.touches.target1)}</strong>
          <small>2차 목표 {touchText(row.touches.target2)} · 손절 기준 {touchText(row.touches.stop)}</small>
        </div>
      </div>
    </div>
  );
}

export default function SimulationWorkspace() {
  const [mode, setMode] = useState<Mode>("new");
  const [preset, setPreset] = useState<Preset>("1y");
  const [marketScope, setMarketScope] = useState<"ALL" | "KOSPI" | "KOSDAQ">("ALL");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [preview, setPreview] = useState<ValidationPeriodPreview | null>(null);
  const [draftName, setDraftName] = useState("Production Scanner · 최근 1년");
  const [drafts, setDrafts] = useState<HistoricalValidationDraft[]>([]);
  const [legacy, setLegacy] = useState<LegacyValidation[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<HistoricalValidationDraft | null>(null);
  const [selectedLegacy, setSelectedLegacy] = useState<LegacyValidation | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedBusy, setSavedBusy] = useState(false);
  const [replayBusy, setReplayBusy] = useState(false);
  const [outcomeBusy, setOutcomeBusy] = useState(false);
  const [outcomeSummary, setOutcomeSummary] = useState<HistoricalValidationOutcomeSummary | null>(null);
  const [outcomeBreakdown, setOutcomeBreakdown] = useState<HistoricalValidationOutcomeBreakdown | null>(null);
  const [expandedStrategyKey, setExpandedStrategyKey] = useState<string | null>(null);
  const [expandedDecisionKey, setExpandedDecisionKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function defaultName(nextPreset: Preset, nextMarket: "ALL" | "KOSPI" | "KOSDAQ", nextPreview?: ValidationPeriodPreview | null) {
    const market = nextMarket === "ALL" ? "전체시장" : nextMarket;
    const period = nextPreset === "6m" ? "최근 6개월" : nextPreset === "1y" ? "최근 1년" : nextPreset === "2y" ? "최근 2년" : nextPreview ? `${nextPreview.requested_start_month}~${nextPreview.requested_end_month}` : "직접 선택";
    return `${market} Scanner · ${period}`;
  }

  async function loadPreview(nextPreset = preset, nextMarket = marketScope, nextStart = startMonth, nextEnd = endMonth, refreshName = false) {
    if (nextPreset === "custom" && (!nextStart || !nextEnd)) {
      setPreview(null);
      return;
    }
    setBusy(true); setMessage(null);
    try {
      const result = await previewValidationPeriod(nextPreset === "custom"
        ? { start_month: nextStart, end_month: nextEnd, market_scope: nextMarket }
        : { preset: nextPreset, market_scope: nextMarket });
      setPreview(result);
      if (nextPreset !== "custom") {
        setStartMonth(result.requested_start_month);
        setEndMonth(result.requested_end_month);
      }
      if (refreshName) setDraftName(defaultName(nextPreset, nextMarket, result));
    } catch (error) {
      setPreview(null);
      setMessage(errorText(error));
    } finally { setBusy(false); }
  }

  async function loadSaved() {
    setSavedBusy(true);
    try {
      const [nextDrafts, nextLegacy] = await Promise.all([listValidationDrafts(), listLegacyValidations()]);
      setDrafts(nextDrafts);
      setLegacy(nextLegacy);
      if (selectedDraft) setSelectedDraft(nextDrafts.find((item) => item.id === selectedDraft.id) ?? null);
      if (selectedLegacy) setSelectedLegacy(nextLegacy.find((item) => item.portfolio_id === selectedLegacy.portfolio_id) ?? null);
    } catch (error) {
      setMessage(errorText(error));
    } finally { setSavedBusy(false); }
  }

  useEffect(() => { void loadPreview("1y", "ALL", "", "", true); }, []);
  useEffect(() => { if (mode === "saved") void loadSaved(); }, [mode]);

  useEffect(() => {
    setExpandedStrategyKey(null);
    setExpandedDecisionKey(null);
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "COMPLETED") {
      setOutcomeSummary(null);
      setOutcomeBreakdown(null);
      return;
    }
    let disposed = false;
    setOutcomeBusy(true);
    setOutcomeBreakdown(null);
    void getValidationOutcomeSummary(selectedDraft.id)
      .then(async (summary) => {
        if (disposed) return;
        setOutcomeSummary(summary);
        if (summary.status === "READY") {
          const breakdown = await getValidationOutcomeBreakdown(selectedDraft.id);
          if (!disposed) setOutcomeBreakdown(breakdown);
        }
      })
      .catch((error) => { if (!disposed) setMessage(errorText(error)); })
      .finally(() => { if (!disposed) setOutcomeBusy(false); });
    return () => { disposed = true; };
  }, [mode, selectedDraft?.id, selectedDraft?.status]);

  useEffect(() => {
    if (mode !== "saved" || !selectedDraft || selectedDraft.status !== "RUNNING") return;
    let disposed = false;
    const validationId = selectedDraft.id;

    async function pollReplay() {
      try {
        const next = await getValidationDraft(validationId);
        if (disposed) return;
        setSelectedDraft(next);
        setDrafts((rows) => rows.map((row) => row.id === next.id ? next : row));
        if (next.status !== "RUNNING") {
          if (next.status === "COMPLETED") setMessage(`'${next.name}' 과거 Scanner 재생이 완료되었습니다.`);
          else if (next.status === "CANCELLED") setMessage(`'${next.name}' 과거 Scanner 재생을 중지했습니다.`);
          else if (next.status === "FAILED") setMessage(next.error_message || `'${next.name}' 과거 Scanner 재생에 실패했습니다.`);
        }
      } catch (error) {
        if (!disposed) setMessage(errorText(error));
      }
    }

    void pollReplay();
    const timer = window.setInterval(() => void pollReplay(), 1500);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [mode, selectedDraft?.id, selectedDraft?.status]);

  const periodHint = useMemo(() => {
    if (!preview) return "Market Store의 확정 거래일을 기준으로 실제 범위를 계산합니다.";
    if (!preview.valid) return `현재 ${preview.trading_days} 거래일 · 최소 ${preview.minimum_trading_days} 거래일이 필요합니다.`;
    return `${dateText(preview.resolved_start_date)} ~ ${dateText(preview.resolved_end_date)} · ${preview.trading_days} 거래일`;
  }, [preview]);

  function choosePreset(value: Preset) {
    setPreset(value);
    if (value === "custom") {
      setDraftName(defaultName(value, marketScope, preview));
      return;
    }
    void loadPreview(value, marketScope, startMonth, endMonth, true);
  }

  function chooseMarket(value: "ALL" | "KOSPI" | "KOSDAQ") {
    setMarketScope(value);
    void loadPreview(preset, value, startMonth, endMonth, true);
  }

  async function saveDraft() {
    if (!preview?.valid || !draftName.trim()) return;
    setBusy(true); setMessage(null);
    try {
      const created = await createValidationDraft(preset === "custom"
        ? { name: draftName.trim(), start_month: startMonth, end_month: endMonth, market_scope: marketScope }
        : { name: draftName.trim(), preset, market_scope: marketScope });
      setSelectedDraft(created);
      setSelectedLegacy(null);
      setDrafts((rows) => [created, ...rows.filter((row) => row.id !== created.id)]);
      setMessage(`'${draftName.trim()}' 검증 설정을 저장했습니다.`);
      setMode("saved");
    } catch (error) {
      setMessage(errorText(error));
    } finally { setBusy(false); }
  }

  async function runReplay(row: HistoricalValidationDraft) {
    if (replayBusy || row.status === "COMPLETED") return;
    setReplayBusy(true); setMessage(null);
    try {
      await runValidationReplay(row.id);
      const next = await getValidationDraft(row.id);
      setSelectedDraft(next);
      setDrafts((rows) => rows.map((item) => item.id === next.id ? next : item));
      setMessage(row.status === "DRAFT"
        ? `'${row.name}' 과거 Scanner 재생을 시작했습니다.`
        : `'${row.name}' 과거 Scanner 재생을 이어서 시작했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
      try {
        const next = await getValidationDraft(row.id);
        setSelectedDraft(next);
        setDrafts((rows) => rows.map((item) => item.id === next.id ? next : item));
      } catch { /* request error already shown */ }
    } finally { setReplayBusy(false); }
  }

  async function cancelReplay(row: HistoricalValidationDraft) {
    if (replayBusy || row.status !== "RUNNING") return;
    setReplayBusy(true); setMessage(null);
    try {
      await cancelValidationReplay(row.id);
      const next = await getValidationDraft(row.id);
      setSelectedDraft(next);
      setDrafts((rows) => rows.map((item) => item.id === next.id ? next : item));
      setMessage(next.status === "CANCELLED"
        ? `'${row.name}' 과거 Scanner 재생을 중지했습니다.`
        : `'${row.name}' 중지를 요청했습니다. 현재 거래일 처리 후 멈춥니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally { setReplayBusy(false); }
  }

  async function calculateOutcomes(row: HistoricalValidationDraft) {
    if (outcomeBusy || row.status !== "COMPLETED") return;
    setOutcomeBusy(true); setMessage(null);
    try {
      const summary = await refreshValidationOutcomes(row.id);
      setOutcomeSummary(summary);
      const breakdown = summary.status === "READY"
        ? await getValidationOutcomeBreakdown(row.id)
        : null;
      setOutcomeBreakdown(breakdown);
      setExpandedStrategyKey(null);
      setExpandedDecisionKey(null);
      setMessage(`'${row.name}' 후보 ${summary.outcome_count}건의 D+1~D+20 성과를 계산했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function removeDraft(row: HistoricalValidationDraft) {
    if (!window.confirm(`'${row.name}' 검증 설정을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
    setSavedBusy(true); setMessage(null);
    try {
      await deleteValidationDraft(row.id);
      if (selectedDraft?.id === row.id) setSelectedDraft(null);
      await loadSaved();
      setMessage(`'${row.name}' 검증 설정을 삭제했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally { setSavedBusy(false); }
  }

  async function removeLegacy(row: LegacyValidation) {
    if (!window.confirm(`'${row.name}' 이전 Simulation 기록을 삭제하시겠습니까?\n연결된 거래 기록이 있으면 삭제가 차단됩니다.`)) return;
    setSavedBusy(true); setMessage(null);
    try {
      await deleteLegacyValidation(row.portfolio_id);
      if (selectedLegacy?.portfolio_id === row.portfolio_id) setSelectedLegacy(null);
      await loadSaved();
      setMessage(`'${row.name}' 이전 Simulation 기록을 삭제했습니다.`);
    } catch (error) {
      setMessage(errorText(error));
    } finally { setSavedBusy(false); }
  }

  function startNew() {
    setSelectedDraft(null); setSelectedLegacy(null); setMode("new");
  }

  return (
    <section className="simulation-workspace sim-validation-foundation">
      <header className="sim-page-head">
        <div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>과거 판단을 거래일별로 재현하고, 저장된 후보가 이후 실제로 어떻게 움직였는지 확인합니다.</p></div>
        {preview && <div className="sim-date-block"><span>Market Store 최신</span><strong>{dateText(preview.market_data_latest_date)}</strong><small>{preview.partial_end_month ? "현재 월은 확보된 거래일까지" : "확정 데이터 기준"}</small></div>}
      </header>

      <div className="sim-validation-tabs" role="tablist" aria-label="전략 성과 검증">
        <button className={mode === "new" ? "active" : ""} onClick={startNew}>새 검증</button>
        <button className={mode === "saved" ? "active" : ""} onClick={() => setMode("saved")}>저장된 검증 <small>{drafts.length + legacy.length || ""}</small></button>
      </div>

      {message && <div className="sim-notice">{message}</div>}

      {mode === "new" ? <>
        <section className="sim-validation-block">
          <div className="sim-section-head"><div><span className="sim-section-kicker">검증 설정</span><h2>무엇을, 어느 기간에 검증할지 저장합니다.</h2></div><small>최소 60 실제 거래일</small></div>

          <div className="sim-validation-row sim-validation-name-row">
            <span>검증 이름</span>
            <input className="sim-validation-name" value={draftName} maxLength={120} onChange={(e) => setDraftName(e.target.value)} placeholder="예: 9월 Scanner 1년 검증" />
          </div>

          <div className="sim-validation-overview">
            <div><span>검증 대상</span><strong>Production Scanner</strong></div>
            <div><span>Scanner 버전</span><strong>{PRODUCTION_SCANNER_VERSION}</strong></div>
            <div><span>시장</span><strong>{marketLabel(marketScope)}</strong></div>
            <div><span>상태</span><strong>설정 저장 전</strong></div>
          </div>

          <div className="sim-validation-row">
            <span>시장 범위</span>
            <div className="sim-inline-options">{(["ALL", "KOSPI", "KOSDAQ"] as const).map((value) => <button key={value} className={marketScope === value ? "active" : ""} onClick={() => chooseMarket(value)}>{value === "ALL" ? "전체" : value}</button>)}</div>
          </div>

          <div className="sim-validation-row">
            <span>검증 기간</span>
            <div className="sim-inline-options"><button className={preset === "6m" ? "active" : ""} onClick={() => choosePreset("6m")}>최근 6개월</button><button className={preset === "1y" ? "active" : ""} onClick={() => choosePreset("1y")}>최근 1년</button><button className={preset === "2y" ? "active" : ""} onClick={() => choosePreset("2y")}>최근 2년</button><button className={preset === "custom" ? "active" : ""} onClick={() => choosePreset("custom")}>직접 선택</button></div>
          </div>

          {preset === "custom" && <div className="sim-month-range"><label><span>시작 월</span><input type="month" value={startMonth} onChange={(e) => setStartMonth(e.target.value)} /></label><span>~</span><label><span>종료 월</span><input type="month" value={endMonth} onChange={(e) => setEndMonth(e.target.value)} /></label><button className="sim-secondary" disabled={busy || !startMonth || !endMonth} onClick={() => void loadPreview("custom", marketScope, startMonth, endMonth, false)}>기간 확인</button></div>}

          <div className={`sim-validation-preview ${preview && !preview.valid ? "invalid" : ""}`}>
            <div><span>요청 범위</span><strong>{startMonth || "-"} ~ {endMonth || "-"}</strong></div>
            <div><span>실제 거래일 범위</span><strong>{preview ? `${dateText(preview.resolved_start_date)} ~ ${dateText(preview.resolved_end_date)}` : "-"}</strong></div>
            <div><span>검증 대상</span><strong>{preview ? `${preview.trading_days} 거래일` : busy ? "계산 중…" : "-"}</strong></div>
            <div><span>최소 기준</span><strong>{preview ? `${preview.minimum_trading_days} 거래일` : "60 거래일"}</strong></div>
          </div>
          <p className="sim-validation-hint">{periodHint}</p>
        </section>

        <section className="sim-validation-block sim-draft-action">
          <div><span className="sim-section-kicker">저장</span><h2>설정을 먼저 보존합니다.</h2><p>저장된 설정은 검증 대상·Scanner 버전·시장·실제 거래일 범위를 함께 남깁니다. 실행 엔진은 다음 단계에서 이 설정을 읽어 사용합니다.</p></div>
          <button className="sim-primary" disabled={busy || !preview?.valid || !draftName.trim()} onClick={() => void saveDraft()}>{busy ? "처리 중…" : "설정 저장"}</button>
        </section>

        <section className="sim-validation-block sim-replay-intro">
          <div><span className="sim-section-kicker">과거 Scanner 재생</span><h2>저장 후 실제 거래일별 판단을 재현합니다.</h2><p>선택한 날짜 당시까지 Market Store에 저장된 데이터만 사용합니다. 거래 체결과 수익률 평가는 다음 검증 단계에서 수행합니다.</p></div>
        </section>
      </> : <section className="sim-validation-block">
        <div className="sim-section-head"><div><span className="sim-section-kicker">보존 데이터</span><h2>저장된 검증</h2></div><button className="sim-secondary" onClick={startNew}>+ 새 검증</button></div>
        <p className="sim-legacy-note">새 검증 설정과 기존 수동 Simulation을 구분해 보관합니다. 어떤 전략·시장·기간을 대상으로 했는지 확인한 뒤 열거나 삭제할 수 있습니다.</p>

        {savedBusy ? <div className="sim-empty">불러오는 중…</div> : <>
          <div className="sim-saved-group">
            <div className="sim-saved-group-head"><strong>새 Historical Validation</strong><span>{drafts.length}개</span></div>
            {drafts.length === 0 ? <div className="sim-empty"><strong>저장된 새 검증이 없습니다.</strong><span>+ 새 검증에서 설정을 저장하면 여기에 나타납니다.</span></div> : <div className="sim-table-wrap"><table className="sim-table sim-saved-table"><thead><tr><th>이름</th><th>대상</th><th>시장</th><th>기간</th><th>재현</th><th>상태</th><th>관리</th></tr></thead><tbody>{drafts.map((row) => <tr key={row.id} className={selectedDraft?.id === row.id ? "selected" : undefined}><td><strong>{row.name}</strong><small>Scanner {row.scanner_version}</small></td><td>Production Scanner</td><td>{marketLabel(row.market_scope)}</td><td>{row.requested_start_month} ~ {row.requested_end_month}</td><td>{row.processed_day_count ?? 0} / {row.trading_day_count}일</td><td>{replayStatusLabel(row)}</td><td><button className="sim-text-button" onClick={() => { setSelectedDraft(row); setSelectedLegacy(null); }}>열기</button><button className="sim-text-button danger" disabled={row.status === "RUNNING"} onClick={() => void removeDraft(row)}>삭제</button></td></tr>)}</tbody></table></div>}
          </div>

          {selectedDraft && <div className="sim-saved-detail sim-replay-detail">
            <div className="sim-saved-detail-head"><div><span>저장된 검증</span><h3>{selectedDraft.name}</h3></div><strong>{replayStatusLabel(selectedDraft)}</strong></div>
            <dl><dt>검증 대상</dt><dd>Production Scanner {selectedDraft.scanner_version}</dd><dt>시장</dt><dd>{marketLabel(selectedDraft.market_scope)}</dd><dt>실제 기간</dt><dd>{dateText(selectedDraft.resolved_start_date)} ~ {dateText(selectedDraft.resolved_end_date)}</dd><dt>생성일</dt><dd>{dateText(selectedDraft.created_at.slice(0, 10))}</dd></dl>

            <div className="sim-replay-status">
              <div className="sim-replay-progress-head"><span>과거 Scanner 재생</span><strong>{selectedDraft.processed_day_count ?? 0} / {selectedDraft.trading_day_count} 거래일 · {replayPercent(selectedDraft)}%</strong></div>
              <div className="sim-replay-progress" aria-label={`재생 진행률 ${replayPercent(selectedDraft)}%`}><span style={{ width: `${replayPercent(selectedDraft)}%` }} /></div>
              <div className="sim-replay-metrics">
                <div><span>최근 완료일</span><strong>{dateText(selectedDraft.last_completed_date)}</strong></div>
                <div><span>누적 후보</span><strong>{selectedDraft.candidate_count ?? 0}</strong></div>
                <div><span>실행 상태</span><strong>{replayStatusLabel(selectedDraft)}</strong></div>
              </div>

              {selectedDraft.status === "FAILED" && <div className="sim-replay-error"><strong>{selectedDraft.error_code || "VAL_REPLAY_FAILED"}</strong><span>{selectedDraft.error_message || "과거 Scanner 재생에 실패했습니다."}</span></div>}
              {selectedDraft.status === "RUNNING" && selectedDraft.runtime_active === false && <p className="sim-replay-note">이전 실행 프로세스가 종료되었습니다. 완료된 날짜는 보존되어 있으며 이어서 실행할 수 있습니다.</p>}
              {selectedDraft.status === "CANCELLED" && <p className="sim-replay-note">완료된 날짜까지 저장되었습니다. 이어 실행하면 다음 미완료 거래일부터 계속합니다.</p>}
              {selectedDraft.status === "COMPLETED" && <p className="sim-replay-note">모든 대상 거래일의 당시 Scanner 판단을 저장했습니다. 아래 성과 평가는 추천 당일을 제외하고 D+1부터 최대 20거래일까지 실제 확정 일봉을 관측합니다.</p>}

              <div className="sim-replay-actions">
                {selectedDraft.status === "DRAFT" && <button className="sim-primary" disabled={replayBusy} onClick={() => void runReplay(selectedDraft)}>{replayBusy ? "시작 중…" : "과거 Scanner 재생 시작"}</button>}
                {(selectedDraft.status === "FAILED" || selectedDraft.status === "CANCELLED" || (selectedDraft.status === "RUNNING" && selectedDraft.runtime_active === false)) && <button className="sim-primary" disabled={replayBusy} onClick={() => void runReplay(selectedDraft)}>{replayBusy ? "시작 중…" : "이어 실행"}</button>}
                {selectedDraft.status === "RUNNING" && selectedDraft.runtime_active !== false && <><span className="sim-replay-running">재생 중…</span><button className="sim-secondary" disabled={replayBusy || selectedDraft.cancel_requested} onClick={() => void cancelReplay(selectedDraft)}>{selectedDraft.cancel_requested ? "중지 요청됨" : replayBusy ? "처리 중…" : "중지"}</button></>}
              </div>
            </div>

            {selectedDraft.status === "COMPLETED" && <div className="sim-outcome-status">
              <div className="sim-outcome-head">
                <div>
                  <span className="sim-section-kicker">후보 실제 결과</span>
                  <h4>검증 결과</h4>
                  <p>과거에 저장한 Scanner 후보가 이후 확정 일봉에서 어떻게 움직였는지 확인합니다.</p>
                </div>
                <div className="sim-outcome-refresh">
                  <button className="sim-secondary" disabled={outcomeBusy} onClick={() => void calculateOutcomes(selectedDraft)}>
                    {outcomeBusy ? "계산 중…" : outcomeSummary?.status === "READY" ? "성과 갱신" : "성과 계산"}
                  </button>
                  <small>새 거래일이 추가되면 최근 후보의 결과만 다시 계산합니다. Scanner 판단은 바뀌지 않습니다.</small>
                </div>
              </div>

              {outcomeBusy && !outcomeSummary ? <div className="sim-empty">성과 정보를 확인하는 중…</div> :
              outcomeSummary?.status !== "READY" ? <section className="sim-outcome-section">
                <h5>아직 성과를 계산하지 않았습니다.</h5>
                <p>
                  과거 {selectedDraft.processed_day_count.toLocaleString("ko-KR")}거래일의 분석은 완료되었고,
                  당시 포착한 후보는 {selectedDraft.candidate_count.toLocaleString("ko-KR")}건입니다.
                  성과 계산을 누르면 각 후보의 다음 거래일부터 최대 20거래일까지 가격 변화를 확인합니다.
                </p>
                <p className="sim-outcome-note">실제 주문이나 체결을 가정하지 않고 Market Store의 확정 일봉만 사용합니다.</p>
              </section> : <>
                <section className="sim-outcome-section sim-outcome-overview">
                  <span className="sim-section-kicker">한눈에 보기</span>
                  <h5>검증 결과 요약</h5>
                  <p>
                    과거 {outcomeSummary.replay.processed_trading_days.toLocaleString("ko-KR")}거래일의 Scanner 판단을 다시 확인했고,
                    당시 포착한 후보는 총 <strong>{countText(outcomeSummary.total_candidates)}</strong>입니다.
                    그중 <strong>{countText(outcomeSummary.horizons["20d"].sample_count)}</strong>은
                    20거래일 뒤까지 결과를 확인할 수 있습니다.
                  </p>
                  <p>
                    20거래일 뒤 평균 가격 변화는 <strong>{pctText(outcomeSummary.horizons["20d"].average_pct)}</strong>,
                    중앙값은 <strong>{pctText(outcomeSummary.horizons["20d"].median_pct)}</strong>입니다.
                    {" "}{averageMedianNote(outcomeSummary.horizons["20d"].average_pct, outcomeSummary.horizons["20d"].median_pct)}
                  </p>
                  <p className="sim-outcome-note">
                    이 수치는 실제 매매 수익률이 아니라 후보 포착 당일 종가를 기준으로 이후 확정 일봉의 가격 변화를 측정한 값입니다.
                  </p>
                </section>

                <section className="sim-outcome-section">
                  <h5>과거 분석 범위</h5>
                  <dl className="sim-outcome-facts">
                    <div><dt>과거 분석</dt><dd>{outcomeSummary.replay.processed_trading_days.toLocaleString("ko-KR")}거래일 모두 확인</dd></div>
                    <div><dt>과거에 포착한 후보</dt><dd>{countText(outcomeSummary.total_candidates)}</dd></div>
                    <div><dt>20거래일 뒤까지 확인</dt><dd>{countText(outcomeSummary.horizons["20d"].sample_count)} / {countText(outcomeSummary.total_candidates)}</dd></div>
                  </dl>
                  <p className="sim-outcome-note">
                    같은 종목이 여러 거래일에 다시 포착된 경우 각각 한 건으로 계산합니다.
                    최근에 포착된 후보는 아직 20거래일이 지나지 않아 장기 결과 표본에서 제외될 수 있습니다.
                  </p>
                </section>

                <section className="sim-outcome-section">
                  <h5>이후 가격 변화</h5>
                  <table className="sim-outcome-table">
                    <thead>
                      <tr><th>확인 시점</th><th>평균 가격 변화</th><th>중앙값</th><th>확인 가능한 후보</th></tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>5거래일 뒤</td>
                        <td>{pctText(outcomeSummary.horizons["5d"].average_pct)}</td>
                        <td>{pctText(outcomeSummary.horizons["5d"].median_pct)}</td>
                        <td>{countText(outcomeSummary.horizons["5d"].sample_count)}</td>
                      </tr>
                      <tr>
                        <td>10거래일 뒤</td>
                        <td>{pctText(outcomeSummary.horizons["10d"].average_pct)}</td>
                        <td>{pctText(outcomeSummary.horizons["10d"].median_pct)}</td>
                        <td>{countText(outcomeSummary.horizons["10d"].sample_count)}</td>
                      </tr>
                      <tr>
                        <td>20거래일 뒤</td>
                        <td>{pctText(outcomeSummary.horizons["20d"].average_pct)}</td>
                        <td>{pctText(outcomeSummary.horizons["20d"].median_pct)}</td>
                        <td>{countText(outcomeSummary.horizons["20d"].sample_count)}</td>
                      </tr>
                    </tbody>
                  </table>
                  <div className="sim-outcome-explain">
                    <strong>평균과 중앙값은 왜 같이 보나요?</strong>
                    <p>평균은 모든 후보의 값을 합쳐 계산해 큰 상승·하락 사례의 영향을 받을 수 있습니다. 중앙값은 결과를 순서대로 놓았을 때 가운데에 있는 값입니다.</p>
                    <p>{averageMedianNote(outcomeSummary.horizons["20d"].average_pct, outcomeSummary.horizons["20d"].median_pct)}</p>
                  </div>
                </section>

                <section className="sim-outcome-section">
                  <h5>20거래일 동안의 가격 움직임</h5>
                  <dl className="sim-outcome-movement">
                    <div>
                      <dt>평균 최고 상승폭</dt>
                      <dd>{pctText(outcomeSummary.mfe_20d.average_pct)}</dd>
                      <small>각 후보가 기준가보다 가장 많이 올랐던 순간을 평균한 값</small>
                    </div>
                    <div>
                      <dt>평균 최대 하락폭</dt>
                      <dd>{pctText(outcomeSummary.mae_20d.average_pct)}</dd>
                      <small>각 후보가 기준가보다 가장 많이 내려갔던 순간을 평균한 값</small>
                    </div>
                  </dl>
                </section>

                <section className="sim-outcome-section">
                  <h5>20거래일 안에 가격 기준에 닿은 경우</h5>
                  <p className="sim-outcome-warning">
                    이 수치는 성공률이나 손실률이 아닙니다. 해당 기간에 그 가격에 한 번이라도 닿았는지를 센 값입니다.
                  </p>
                  <table className="sim-outcome-table sim-outcome-touch">
                    <thead><tr><th>가격 기준</th><th>도달한 후보 / 비교 가능한 후보</th></tr></thead>
                    <tbody>
                      <tr><td>진입 관찰 가격</td><td>{touchText(outcomeSummary.touches.entry)}</td></tr>
                      <tr><td>손절 기준 가격</td><td>{touchText(outcomeSummary.touches.stop)}</td></tr>
                      <tr><td>1차 목표 가격</td><td>{touchText(outcomeSummary.touches.target1)}</td></tr>
                      <tr><td>2차 목표 가격</td><td>{touchText(outcomeSummary.touches.target2)}</td></tr>
                    </tbody>
                  </table>
                  <div className="sim-outcome-explain">
                    <strong>진입 관찰 가격은 무엇인가요?</strong>
                    <p>Scanner가 당시 제시한 진입 가격 범위 또는 조건에 이후 20거래일 동안 실제 가격이 닿았는지를 뜻합니다. 실제 매수 체결을 의미하지 않습니다.</p>
                  </div>
                  <p className="sim-outcome-note">
                    같은 후보가 손절 기준과 목표 가격에 모두 포함될 수 있습니다.
                    같은 일봉에서 두 가격에 모두 닿았더라도 일봉 데이터만으로 어느 가격이 먼저였는지는 알 수 없으므로 순서를 추정하지 않습니다.
                  </p>
                </section>

                <section className="sim-outcome-section">
                  <span className="sim-section-kicker">그룹 비교</span>
                  <h5>전략별 결과</h5>
                  <p>같은 Scanner 후보라도 당시 적용된 전략에 따라 이후 가격 움직임이 어떻게 달랐는지 나눠 봅니다.</p>
                  <p className="sim-breakdown-note">표는 과거 후보 수가 많은 순으로 표시하며 성과 순위가 아닙니다. 후보 수가 적은 그룹은 수치가 크게 흔들릴 수 있으므로 표본 수를 함께 확인하세요.</p>
                  {outcomeBreakdown?.status === "READY" && outcomeBreakdown.strategy.length > 0 ? <>
                    <div className="sim-breakdown-scroll">
                      <table className="sim-breakdown-table">
                        <thead><tr><th>전략</th><th>과거 후보</th><th>20일 확인</th><th>20일 평균</th><th>중앙값</th><th>1차 목표</th><th>손절 기준</th><th>상세</th></tr></thead>
                        <tbody>
                          {outcomeBreakdown.strategy.map((row) => (
                            <tr key={row.key}>
                              <td>{validationStrategyLabel(row.key)}</td>
                              <td>{countText(row.candidate_count)}</td>
                              <td>{countText(row.horizons["20d"].sample_count)}</td>
                              <td>{pctText(row.horizons["20d"].average_pct)}</td>
                              <td>{pctText(row.horizons["20d"].median_pct)}</td>
                              <td>{touchPctText(row.touches.target1)}</td>
                              <td>{touchPctText(row.touches.stop)}</td>
                              <td><button type="button" className="sim-breakdown-action" onClick={() => setExpandedStrategyKey((current) => current === row.key ? null : row.key)}>{expandedStrategyKey === row.key ? "닫기" : "상세 보기"}</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {outcomeBreakdown.strategy.filter((row) => row.key === expandedStrategyKey).map((row) => (
                      <ValidationBreakdownDetail key={row.key} row={row} label={validationStrategyLabel(row.key)} />
                    ))}
                  </> : <p className="sim-outcome-note">성과 계산 후 전략별 결과를 확인할 수 있습니다.</p>}
                </section>

                <section className="sim-outcome-section">
                  <h5>당시 판단별 결과</h5>
                  <p>Scanner가 후보를 찾았을 때의 판단 상태에 따라 이후 가격 움직임을 나눠 봅니다. 현재 종목에 대한 매수·매도 지시가 아니라 과거 판단의 특성을 확인하기 위한 통계입니다.</p>
                  {outcomeBreakdown?.status === "READY" && outcomeBreakdown.decision_status.length > 0 ? <>
                    <div className="sim-breakdown-scroll">
                      <table className="sim-breakdown-table">
                        <thead><tr><th>당시 판단</th><th>과거 후보</th><th>20일 확인</th><th>20일 평균</th><th>중앙값</th><th>1차 목표</th><th>손절 기준</th><th>상세</th></tr></thead>
                        <tbody>
                          {outcomeBreakdown.decision_status.map((row) => (
                            <tr key={row.key}>
                              <td>{validationDecisionLabel(row.key)}</td>
                              <td>{countText(row.candidate_count)}</td>
                              <td>{countText(row.horizons["20d"].sample_count)}</td>
                              <td>{pctText(row.horizons["20d"].average_pct)}</td>
                              <td>{pctText(row.horizons["20d"].median_pct)}</td>
                              <td>{touchPctText(row.touches.target1)}</td>
                              <td>{touchPctText(row.touches.stop)}</td>
                              <td><button type="button" className="sim-breakdown-action" onClick={() => setExpandedDecisionKey((current) => current === row.key ? null : row.key)}>{expandedDecisionKey === row.key ? "닫기" : "상세 보기"}</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {outcomeBreakdown.decision_status.filter((row) => row.key === expandedDecisionKey).map((row) => (
                      <ValidationBreakdownDetail key={row.key} row={row} label={validationDecisionLabel(row.key)} />
                    ))}
                  </> : <p className="sim-outcome-note">성과 계산 후 당시 판단별 결과를 확인할 수 있습니다.</p>}
                </section>

                <details className="sim-outcome-method">
                  <summary>검증 방법 보기</summary>
                  <dl>
                    <div><dt>기준 가격</dt><dd>후보 포착 당일 종가</dd></div>
                    <div><dt>결과 관찰 시작</dt><dd>다음 거래일 (D+1)</dd></div>
                    <div><dt>관찰 기간</dt><dd>최대 20거래일</dd></div>
                    <div><dt>가격 데이터</dt><dd>Market Store 확정 일봉</dd></div>
                    <div><dt>실제 주문 가정</dt><dd>하지 않음</dd></div>
                    <div><dt>같은 일봉의 손절·목표 순서</dt><dd>추정하지 않음</dd></div>
                  </dl>
                </details>
              </>}
            </div>}
          </div>}

          <div className="sim-saved-group sim-legacy-group">
            <div className="sim-saved-group-head"><strong>이전 수동 Simulation</strong><span>{legacy.length}개</span></div>
            <p className="sim-legacy-note">새 전략 성과 검증과 구조가 다른 이전 데이터입니다. 전략 정보가 없으면 없는 그대로 표시합니다.</p>
            {legacy.length === 0 ? <div className="sim-empty"><strong>이전 Simulation 기록이 없습니다.</strong></div> : <div className="sim-table-wrap"><table className="sim-table sim-saved-table"><thead><tr><th>이름</th><th>전략</th><th>기간</th><th>포지션</th><th>거래</th><th>초기 자금</th><th>관리</th></tr></thead><tbody>{legacy.map((row) => <tr key={row.portfolio_id} className={selectedLegacy?.portfolio_id === row.portfolio_id ? "selected" : undefined}><td><strong>{row.name}</strong><small>Legacy · 자동 활성화 안 함</small></td><td>정보 없음</td><td>{row.start_date ? `${dateText(row.start_date)} ~ ${dateText(row.end_date ?? row.current_date)}` : "설정 기록 없음"}</td><td>{row.position_count}</td><td>{row.trade_count}</td><td>{money(row.initial_cash)}</td><td><button className="sim-text-button" onClick={() => { setSelectedLegacy(row); setSelectedDraft(null); }}>보기</button><button className="sim-text-button danger" onClick={() => void removeLegacy(row)}>삭제</button></td></tr>)}</tbody></table></div>}
          </div>

          {selectedLegacy && <div className="sim-saved-detail legacy"><div className="sim-saved-detail-head"><div><span>이전 수동 Simulation</span><h3>{selectedLegacy.name}</h3></div><strong>Legacy</strong></div><dl><dt>유형</dt><dd>이전 수동 Simulation</dd><dt>전략</dt><dd>정보 없음</dd><dt>기간</dt><dd>{selectedLegacy.start_date ? `${dateText(selectedLegacy.start_date)} ~ ${dateText(selectedLegacy.end_date ?? selectedLegacy.current_date)}` : "설정 기록 없음"}</dd><dt>포지션</dt><dd>{selectedLegacy.position_count}</dd><dt>거래</dt><dd>{selectedLegacy.trade_count}</dd><dt>초기 자금</dt><dd>{money(selectedLegacy.initial_cash)}</dd></dl><p>새 Historical Validation의 실행 의미와 다른 이전 데이터이므로 자동으로 현재 검증에 연결하지 않습니다.</p></div>}
        </>}
      </section>}
    </section>
  );
}
