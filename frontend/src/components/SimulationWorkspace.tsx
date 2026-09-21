import { useEffect, useMemo, useState } from "react";
import {
  createValidationDraft,
  deleteLegacyValidation,
  deleteValidationDraft,
  listLegacyValidations,
  listValidationDrafts,
  previewValidationPeriod,
  SimulationApiError,
  type HistoricalValidationDraft,
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
  return value;
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
      await createValidationDraft(preset === "custom"
        ? { name: draftName.trim(), start_month: startMonth, end_month: endMonth, market_scope: marketScope }
        : { name: draftName.trim(), preset, market_scope: marketScope });
      setMessage(`'${draftName.trim()}' 검증 설정을 저장했습니다.`);
      setMode("saved");
    } catch (error) {
      setMessage(errorText(error));
    } finally { setBusy(false); }
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
        <div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>Scanner 전략을 과거 시장에 적용해 전체 성과를 검증합니다.</p></div>
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

        <section className="sim-validation-block sim-execution-pending">
          <div><span className="sim-section-kicker">실행 정책</span><h2>실제 검증 실행은 다음 단계에서 연결합니다.</h2><p>D 신호 → D+1 체결, Gap·Slippage·수수료·Stop/Target 우선순위를 고정한 실행 정책이 완성되기 전에는 기존 수동 체결을 새 전략 검증처럼 실행하지 않습니다.</p></div>
          <button className="sim-primary" disabled>검증 실행 · 준비 중</button>
        </section>
      </> : <section className="sim-validation-block">
        <div className="sim-section-head"><div><span className="sim-section-kicker">보존 데이터</span><h2>저장된 검증</h2></div><button className="sim-secondary" onClick={startNew}>+ 새 검증</button></div>
        <p className="sim-legacy-note">새 검증 설정과 기존 수동 Simulation을 구분해 보관합니다. 어떤 전략·시장·기간을 대상으로 했는지 확인한 뒤 열거나 삭제할 수 있습니다.</p>

        {savedBusy ? <div className="sim-empty">불러오는 중…</div> : <>
          <div className="sim-saved-group">
            <div className="sim-saved-group-head"><strong>새 Historical Validation</strong><span>{drafts.length}개</span></div>
            {drafts.length === 0 ? <div className="sim-empty"><strong>저장된 새 검증이 없습니다.</strong><span>+ 새 검증에서 설정을 저장하면 여기에 나타납니다.</span></div> : <div className="sim-table-wrap"><table className="sim-table sim-saved-table"><thead><tr><th>이름</th><th>대상</th><th>시장</th><th>기간</th><th>거래일</th><th>상태</th><th>관리</th></tr></thead><tbody>{drafts.map((row) => <tr key={row.id} className={selectedDraft?.id === row.id ? "selected" : undefined}><td><strong>{row.name}</strong><small>Scanner {row.scanner_version}</small></td><td>Production Scanner</td><td>{marketLabel(row.market_scope)}</td><td>{row.requested_start_month} ~ {row.requested_end_month}</td><td>{row.trading_day_count}</td><td>{statusLabel(row.status)}</td><td><button className="sim-text-button" onClick={() => { setSelectedDraft(row); setSelectedLegacy(null); }}>열기</button><button className="sim-text-button danger" onClick={() => void removeDraft(row)}>삭제</button></td></tr>)}</tbody></table></div>}
          </div>

          {selectedDraft && <div className="sim-saved-detail"><div className="sim-saved-detail-head"><div><span>저장된 검증</span><h3>{selectedDraft.name}</h3></div><strong>{statusLabel(selectedDraft.status)}</strong></div><dl><dt>검증 대상</dt><dd>Production Scanner {selectedDraft.scanner_version}</dd><dt>시장</dt><dd>{marketLabel(selectedDraft.market_scope)}</dd><dt>요청 기간</dt><dd>{selectedDraft.requested_start_month} ~ {selectedDraft.requested_end_month}</dd><dt>실제 기간</dt><dd>{dateText(selectedDraft.resolved_start_date)} ~ {dateText(selectedDraft.resolved_end_date)}</dd><dt>검증 대상</dt><dd>{selectedDraft.trading_day_count} 거래일</dd><dt>생성일</dt><dd>{dateText(selectedDraft.created_at.slice(0, 10))}</dd></dl></div>}

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
