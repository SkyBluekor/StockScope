import { useEffect, useMemo, useState } from "react";
import {
  createProspectiveProtocol,
  createProspectiveRun,
  executeProspectiveRun,
  getProspectiveRun,
  getProspectiveStatus,
  listProspectiveCaptures,
  listProspectiveProtocols,
  listProspectiveRuns,
  type ProspectiveCapture,
  type ProspectiveEvaluationDetail,
  type ProspectiveProtocol,
  type ProspectiveRun,
  type ProspectiveStatus,
} from "../services/prospectiveApi";
import { SimulationApiError } from "../services/simulationApi";
import {
  createStrategyEvidenceArtifact,
  getStrategyEvidenceEligibility,
  StrategyGovernanceApiError,
  type StrategyEvidenceEligibility,
  type StrategyEvidenceEligibilityRow,
} from "../services/strategyGovernanceApi";

function count(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString("ko-KR");
}

function pct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function dateText(value: string | null | undefined) {
  return value ? value.replace(/-/g, ".") : "-";
}

function errorText(error: unknown) {
  if (error instanceof SimulationApiError) return error.message;
  if (error instanceof StrategyGovernanceApiError) return error.message;
  return error instanceof Error ? error.message : "추천 평가 정보를 불러오지 못했습니다.";
}

function evidenceLabel(value: string | null | undefined) {
  if (value === "SAMPLE_SIZE_POLICY_UNDEFINED") return "데이터는 있으나 표본 기준 미정";
  if (value === "INSUFFICIENT_EVIDENCE") return "아직 판단할 근거 부족";
  return value || "아직 평가 결과 없음";
}

function strategyIdentityLabel(value: string | null | undefined) {
  if (value === "EXACT") return "버전 확인됨";
  if (value === "STRATEGY_IDENTITY_UNPROVEN") return "버전 근거 없음";
  if (value === "MIXED_STRATEGY_VERSION") return "여러 버전 혼합";
  if (value === "STRATEGY_DEFINITION_MISMATCH") return "정의 불일치";
  if (value === "STRATEGY_VERSION_NOT_FOUND") return "등록 버전 없음";
  if (value === "SOURCE_SAMPLE_MISMATCH") return "원본 표본 불일치";
  if (value === "NO_TRADE_NOT_STRATEGY") return "전략 대상 아님";
  return value || "확인 불가";
}

export default function ProspectiveEvaluationPanel() {
  const [status, setStatus] = useState<ProspectiveStatus | null>(null);
  const [captures, setCaptures] = useState<ProspectiveCapture[]>([]);
  const [protocols, setProtocols] = useState<ProspectiveProtocol[]>([]);
  const [runs, setRuns] = useState<ProspectiveRun[]>([]);
  const [latestDetail, setLatestDetail] = useState<ProspectiveEvaluationDetail | null>(null);
  const [migrationRequired, setMigrationRequired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [evidenceEligibility, setEvidenceEligibility] = useState<StrategyEvidenceEligibility | null>(null);
  const [evidenceBusy, setEvidenceBusy] = useState<string | null>(null);
  const [evidenceMessage, setEvidenceMessage] = useState<string | null>(null);

  const [name, setName] = useState("실제 추천 시간 분리 평가");
  const [marketScope, setMarketScope] = useState<"ALL" | "KOSPI" | "KOSDAQ">("ALL");
  const [developmentStart, setDevelopmentStart] = useState("");
  const [developmentEnd, setDevelopmentEnd] = useState("");
  const [holdoutStart, setHoldoutStart] = useState("");
  const [holdoutEnd, setHoldoutEnd] = useState("");
  const [executionMode, setExecutionMode] = useState<"PRODUCTION_POLICY" | "OBSERVATION_ONLY">("PRODUCTION_POLICY");
  const [selectedProtocolId, setSelectedProtocolId] = useState("");

  async function loadEvidenceEligibility(reportId: string) {
    try {
      const next = await getStrategyEvidenceEligibility(reportId);
      setEvidenceEligibility(next);
      setEvidenceMessage(null);
    } catch (error) {
      setEvidenceEligibility(null);
      setEvidenceMessage(errorText(error));
    }
  }

  async function load() {
    setMessage(null);
    try {
      const [nextStatus, nextCaptures, nextProtocols, nextRuns] = await Promise.all([
        getProspectiveStatus(),
        listProspectiveCaptures(),
        listProspectiveProtocols(),
        listProspectiveRuns(),
      ]);
      setStatus(nextStatus);
      setCaptures(nextCaptures);
      setProtocols(nextProtocols);
      setRuns(nextRuns);
      setMigrationRequired(false);
      setSelectedProtocolId((current) => current || nextProtocols[0]?.id || "");

      const completed = nextRuns.find((row) => row.status === "COMPLETED");
      if (completed) {
        const detail = await getProspectiveRun(completed.id);
        setLatestDetail(detail);
        if (detail.report?.id) {
          await loadEvidenceEligibility(detail.report.id);
        } else {
          setEvidenceEligibility(null);
          setEvidenceMessage(null);
        }
      } else {
        setLatestDetail(null);
        setEvidenceEligibility(null);
        setEvidenceMessage(null);
      }
    } catch (error) {
      if (
        error instanceof SimulationApiError
        && error.code === "PROSPECTIVE_MIGRATION_REQUIRED"
      ) {
        setMigrationRequired(true);
        setStatus(null);
        setCaptures([]);
        setProtocols([]);
        setRuns([]);
        setLatestDetail(null);
        return;
      }
      setMessage(errorText(error));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const captureFailures = useMemo(() => {
    const counts = status?.capture_counts ?? {};
    return Number(counts.FAILED ?? 0)
      + Number(counts.CANCELLED ?? 0)
      + Number(counts.INTERRUPTED ?? 0)
      + Number(counts.PARTIAL ?? 0);
  }, [status]);

  const latestReport = latestDetail?.report?.summary ?? null;
  const latestRun = latestDetail?.run ?? null;

  async function saveProtocol() {
    if (!developmentStart || !developmentEnd || !holdoutStart || !holdoutEnd) {
      setMessage("Development와 Holdout의 시작일·종료일을 모두 입력하세요.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const created = await createProspectiveProtocol({
        client_request_id: crypto.randomUUID(),
        name: name.trim() || "실제 추천 시간 분리 평가",
        market_scope: marketScope,
        development_start: developmentStart,
        development_end: developmentEnd,
        holdout_start: holdoutStart,
        holdout_end: holdoutEnd,
        execution_mode: executionMode,
        purge_trading_days: 20,
        max_holding_days: 20,
        round_trip_cost_pct: 0,
        fee_pct: 0,
        tax_pct: 0,
        slippage_pct: 0,
      });
      setSelectedProtocolId(created.id);
      setMessage("평가 기준을 고정했습니다. 결과를 본 뒤 조건을 바꾸면 새 기준으로 저장됩니다.");
      await load();
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  async function registerP5Evidence(row: StrategyEvidenceEligibilityRow) {
    if (!latestDetail?.report?.id || !row.strategy_version_id || !row.creation_allowed) return;
    setEvidenceBusy(row.strategy_key);
    setEvidenceMessage(null);
    try {
      await createStrategyEvidenceArtifact({
        source_kind: "PROSPECTIVE_REPORT",
        source_report_id: latestDetail.report.id,
        strategy_version_id: row.strategy_version_id,
      });
      await loadEvidenceEligibility(latestDetail.report.id);
      setEvidenceMessage("평가 결과를 P5 검토 근거로 보존했습니다. 전략 상태나 운영 정책은 자동 변경되지 않습니다.");
    } catch (error) {
      setEvidenceMessage(errorText(error));
    } finally {
      setEvidenceBusy(null);
    }
  }

  async function runEvaluation() {
    if (!selectedProtocolId) {
      setMessage("먼저 평가 기준을 저장하세요.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const created = await createProspectiveRun(selectedProtocolId);
      const result = await executeProspectiveRun(created.id);
      setLatestDetail(result);
      setMessage(
        result.run.status === "COMPLETED"
          ? "저장된 실제 추천 표본으로 평가를 완료했습니다."
          : `평가 상태: ${result.run.status}`,
      );
      await load();
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  if (migrationRequired) {
    return (
      <section className="sim-prospective">
        <header className="sim-prospective-head">
          <div>
            <span className="sim-section-kicker">실제 추천 기록</span>
            <h3>다음 Scanner 실행부터 추천을 자동 보존할 준비가 필요합니다.</h3>
            <p>기존 Tracking 기록은 바꾸지 않습니다. 이 기능은 사용자가 고르기 전 Scanner 추천 전체를 평가용으로 별도 보존합니다.</p>
          </div>
        </header>
        <div className="sim-prospective-migration">
          <strong>로컬 DB 준비 1회 필요</strong>
          <code>python tools/data/migrate_prospective_vnp2s2.py</code>
        </div>
      </section>
    );
  }

  return (
    <section className="sim-prospective">
      <header className="sim-prospective-head">
        <div>
          <span className="sim-section-kicker">실제 추천 기록</span>
          <h3>Scanner가 실제로 보여준 후보를 자동으로 쌓습니다.</h3>
          <p>Tracking에 넣은 종목만 골라 평가하지 않습니다. Scanner 완료 시점의 추천 집합을 그대로 보존해 사후 선택 편향을 줄입니다.</p>
        </div>
        <button className="sim-secondary" disabled={busy} onClick={() => void load()}>
          새로고침
        </button>
      </header>

      <div className="sim-prospective-status">
        <div>
          <span>기록된 추천</span>
          <strong>{count(status?.sample_count)}건</strong>
          <small>
            {status?.first_signal_date
              ? `${dateText(status.first_signal_date)}부터`
              : "다음 Scanner 완료부터 자동 기록"}
          </small>
        </div>
        <div>
          <span>정상 수집</span>
          <strong>{count(status?.capture_counts.COMPLETE)}회</strong>
          <small>같은 실행 재노출은 중복 집계하지 않음</small>
        </div>
        <div>
          <span>확인 필요한 수집</span>
          <strong>{count(captureFailures)}회</strong>
          <small>부분·실패·중지·재시작 포함</small>
        </div>
        <div>
          <span>전략 자동 변경</span>
          <strong>사용 안 함</strong>
          <small>평가 결과가 운영 정책을 자동 변경하지 않음</small>
        </div>
      </div>

      {message && <p className="sim-prospective-message">{message}</p>}

      <section className="sim-prospective-result">
        <div className="sim-prospective-result-head">
          <div>
            <span>현재 평가 상태</span>
            <h4>{evidenceLabel(latestReport?.evidence_state)}</h4>
          </div>
          <p>
            최소 표본·승격/강등 기준은 아직 정해지지 않았습니다.
            이 화면은 전략 우수 판정이나 자동 교체를 하지 않습니다.
          </p>
        </div>

        {latestReport && latestRun ? (
          <>
            <dl className="sim-prospective-facts">
              <div><dt>평가 표본</dt><dd>{count(latestRun.source_sample_count)}건</dd></div>
              <div><dt>결과 성숙</dt><dd>{count(latestRun.mature_count)}건</dd></div>
              <div><dt>관찰 중</dt><dd>{count(latestRun.immature_count)}건</dd></div>
              <div><dt>경계 제외</dt><dd>{count(latestRun.purged_count + latestRun.excluded_count)}건</dd></div>
            </dl>
            <div className="sim-prospective-metrics">
              {[5, 10, 20].map((day) => {
                const metric = latestReport.candidate_observation[`${day}d`];
                return (
                  <div key={day}>
                    <span>{day}일 관찰</span>
                    <strong>{pct(metric?.average_pct)}</strong>
                    <small>{count(metric?.sample_count)}건</small>
                  </div>
                );
              })}
              <div>
                <span>가상 실행 실현</span>
                <strong>{pct(latestReport.virtual_execution.realized_net_return.average_pct)}</strong>
                <small>{count(latestReport.virtual_execution.realized_net_return.sample_count)}건</small>
              </div>
            </div>
            <p className="sim-prospective-note">
              CENSORED {count(latestReport.virtual_execution.censored_mark_return.sample_count)}건은 실현수익이나 0%로 계산하지 않습니다.
            </p>
          </>
        ) : (
          <div className="sim-prospective-empty">
            <strong>아직 시간 분리 평가 결과가 없습니다.</strong>
            <p>추천은 먼저 쌓아둘 수 있습니다. 실제 미래 데이터가 충분해진 뒤 고정된 평가 기준으로 결과를 확인합니다.</p>
          </div>
        )}
      </section>

      <section className="sim-prospective-p5">
          <div className="sim-prospective-p5-head">
            <div>
              <span>P5 평가 근거</span>
              <strong>완료된 Prospective Report를 전략별 검토 근거로 보존합니다.</strong>
            </div>
            <p>근거 등록은 승격·강등·Proposal·Production Policy를 자동 실행하지 않습니다.</p>
          </div>

          {latestDetail?.report && evidenceMessage && <p className="sim-prospective-message">{evidenceMessage}</p>}

          {latestDetail?.report && evidenceEligibility ? (
            <div className="sim-prospective-p5-table-wrap">
              <table className="sim-prospective-p5-table">
                <thead>
                  <tr>
                    <th>전략</th>
                    <th>표본</th>
                    <th>성숙</th>
                    <th>Strategy identity</th>
                    <th>P5 상태</th>
                    <th>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceEligibility.strategies.map((row) => (
                    <tr key={`${row.strategy_key}:${row.strategy_version_id ?? row.identity_status}`}>
                      <td><strong>{row.strategy_key}</strong></td>
                      <td>{count(row.sample_count)}건</td>
                      <td>{count(row.mature_count)}건</td>
                      <td>{strategyIdentityLabel(row.identity_status)}</td>
                      <td>
                        {row.existing_artifact_id
                          ? "근거 등록됨"
                          : row.creation_allowed
                            ? evidenceLabel(row.evidence_state)
                            : "등록 차단"}
                      </td>
                      <td>
                        {row.existing_artifact_id ? (
                          <span className="sim-prospective-p5-done">보존됨</span>
                        ) : row.creation_allowed && row.strategy_version_id ? (
                          <button
                            className="sim-secondary"
                            disabled={evidenceBusy != null}
                            onClick={() => void registerP5Evidence(row)}
                          >
                            {evidenceBusy === row.strategy_key ? "등록 중…" : "P5 근거로 등록"}
                          </button>
                        ) : (
                          <span className="sim-prospective-p5-blocked">
                            {row.block_reason ? strategyIdentityLabel(row.block_reason) : "등록 불가"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            latestDetail?.report && !evidenceMessage
              ? <p className="sim-prospective-note">P5 근거 등록 가능 여부를 확인하고 있습니다.</p>
              : null
          )}
          {latestDetail?.report && (
            <p className="sim-prospective-note">
              최소 표본 기준은 아직 정의되지 않았습니다. Artifact는 평가 근거를 보존할 뿐 전략 우수성을 확정하지 않습니다.
            </p>
          )}
        {!latestDetail?.report && (
          <div className="sim-prospective-empty">
            <strong>아직 등록할 평가 근거가 없습니다.</strong>
            <p>
              현재 상태 · 평가 Report 없음 · 추천 기록 {count(status?.sample_count)}건 · 정상 수집 {count(status?.capture_counts.COMPLETE)}회 · 확인 필요 {count(captureFailures)}회
            </p>
            <p>
              Prospective 평가가 완료되면 Strategy Version을 확인한 뒤 P5 검토 근거로 등록할 수 있습니다.
            </p>
          </div>
        )}
      </section>

      <details className="sim-prospective-protocol">
        <summary>평가 기준 설정 · 상세</summary>
        <p>
          결과를 보기 전에 Development와 Holdout 기간을 고정합니다.
          결과를 본 뒤 조건을 바꾸면 기존 기준을 수정하지 않고 새 기준을 만듭니다.
        </p>
        <div className="sim-prospective-form">
          <label>
            <span>평가 이름</span>
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>시장</span>
            <select value={marketScope} onChange={(event) => setMarketScope(event.target.value as "ALL" | "KOSPI" | "KOSDAQ")}>
              <option value="ALL">KOSPI + KOSDAQ</option>
              <option value="KOSPI">KOSPI</option>
              <option value="KOSDAQ">KOSDAQ</option>
            </select>
          </label>
          <label>
            <span>Development 시작</span>
            <input type="date" value={developmentStart} onChange={(event) => setDevelopmentStart(event.target.value)} />
          </label>
          <label>
            <span>Development 종료</span>
            <input type="date" value={developmentEnd} onChange={(event) => setDevelopmentEnd(event.target.value)} />
          </label>
          <label>
            <span>Holdout 시작</span>
            <input type="date" value={holdoutStart} onChange={(event) => setHoldoutStart(event.target.value)} />
          </label>
          <label>
            <span>Holdout 종료</span>
            <input type="date" value={holdoutEnd} onChange={(event) => setHoldoutEnd(event.target.value)} />
          </label>
          <label>
            <span>실행 비교</span>
            <select value={executionMode} onChange={(event) => setExecutionMode(event.target.value as "PRODUCTION_POLICY" | "OBSERVATION_ONLY")}>
              <option value="PRODUCTION_POLICY">현재 Production 가상 실행 정책</option>
              <option value="OBSERVATION_ONLY">가격 관찰만</option>
            </select>
          </label>
        </div>
        <div className="sim-prospective-actions">
          <button className="sim-secondary" disabled={busy} onClick={() => void saveProtocol()}>
            평가 기준 저장
          </button>
          <select
            aria-label="저장된 평가 기준"
            value={selectedProtocolId}
            onChange={(event) => setSelectedProtocolId(event.target.value)}
          >
            <option value="">저장된 기준 선택</option>
            {protocols.map((row) => (
              <option key={row.id} value={row.id}>{row.name} · {row.spec.market_scope}</option>
            ))}
          </select>
          <button className="sim-primary" disabled={busy || !selectedProtocolId} onClick={() => void runEvaluation()}>
            {busy ? "처리 중…" : "성과 평가 실행"}
          </button>
        </div>
      </details>

      <details className="sim-prospective-history">
        <summary>수집 상태 상세</summary>
        {captures.length === 0 ? (
          <p>아직 Scanner prospective 기록이 없습니다.</p>
        ) : (
          <div className="sim-prospective-capture-list">
            {captures.slice(0, 10).map((row) => (
              <div key={row.id}>
                <span>{dateText(row.actual_data_date)}</span>
                <strong>{row.status}</strong>
                <span>{count(row.returned_candidate_count)}건</span>
                {row.error_message && <small>{row.error_message}</small>}
              </div>
            ))}
          </div>
        )}
      </details>
    </section>
  );
}
