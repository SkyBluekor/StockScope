import { useEffect, useMemo, useState } from "react";
import {
  createFeedbackCohort,
  createFeedbackReport,
  getFeedbackCohort,
  getFeedbackReport,
  listFeedbackCohorts,
  type FeedbackCohort,
  type FeedbackCohortListItem,
  type FeedbackReport,
  type FeedbackSelector,
  type FeedbackSourceType,
} from "../services/feedbackApi";
import { SimulationApiError } from "../services/simulationApi";

type Props = {
  selectedValidationId?: string | null;
};

function feedbackError(error: unknown) {
  if (error instanceof SimulationApiError) return error.message;
  return error instanceof Error ? error.message : "Feedback 정보를 처리하지 못했습니다.";
}

function count(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString("ko-KR");
}

function pct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function sourceLabel(value: FeedbackSourceType) {
  if (value === "TRACKING") return "Tracking 관찰";
  if (value === "VALIDATION") return "VAL.1 관찰";
  if (value === "EXECUTION") return "VAL.2 가상 실행";
  return "Backtest";
}

function evidenceStateLabel(value: string) {
  if (value === "INSUFFICIENT_EVIDENCE") return "비교할 근거 부족";
  if (value === "SAMPLE_SIZE_POLICY_UNDEFINED") return "표본 기준 미정 · 성능 결론 보류";
  return value;
}

function dimensionText(value: unknown) {
  if (value == null || value === "") return "미지정";
  return String(value);
}

export default function FeedbackPanel({ selectedValidationId }: Props) {
  const [cohorts, setCohorts] = useState<FeedbackCohortListItem[]>([]);
  const [selected, setSelected] = useState<FeedbackCohort | null>(null);
  const [report, setReport] = useState<FeedbackReport | null>(null);
  const [selectors, setSelectors] = useState<FeedbackSelector[]>([]);
  const [sourceType, setSourceType] = useState<FeedbackSourceType>("VALIDATION");
  const [sourceId, setSourceId] = useState(selectedValidationId ?? "");
  const [name, setName] = useState("검증 근거 비교");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [migrationRequired, setMigrationRequired] = useState(false);

  useEffect(() => {
    if (selectedValidationId) {
      setSourceType("VALIDATION");
      setSourceId(selectedValidationId);
    }
  }, [selectedValidationId]);

  async function loadCohorts() {
    try {
      const rows = await listFeedbackCohorts();
      setCohorts(rows);
      setMigrationRequired(false);
    } catch (error) {
      if (error instanceof SimulationApiError && error.code === "FEEDBACK_MIGRATION_REQUIRED") {
        setMigrationRequired(true);
        setCohorts([]);
        return;
      }
      setMessage(feedbackError(error));
    }
  }

  useEffect(() => {
    void loadCohorts();
  }, []);

  const selectorKeySet = useMemo(
    () => new Set(selectors.map((item) => `${item.source_type}:${item.source_id}`)),
    [selectors],
  );

  function addSelector(next: FeedbackSelector) {
    const source = {
      ...next,
      source_id: next.source_id.trim(),
    };
    if (!source.source_id) return;
    const key = `${source.source_type}:${source.source_id}`;
    if (selectorKeySet.has(key)) return;
    setSelectors((rows) => [...rows, source]);
  }

  async function chooseCohort(cohortId: string) {
    setBusy(true);
    setMessage(null);
    try {
      const detail = await getFeedbackCohort(cohortId);
      setSelected(detail);
      const latest = detail.reports?.[0];
      setReport(latest ? await getFeedbackReport(latest.id) : null);
    } catch (error) {
      setMessage(feedbackError(error));
    } finally {
      setBusy(false);
    }
  }

  async function makeCohort() {
    if (selectors.length === 0) {
      setMessage("비교할 원본을 하나 이상 추가하세요.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const created = await createFeedbackCohort({
        client_request_id: crypto.randomUUID(),
        name: name.trim() || "검증 근거 비교",
        sources: selectors,
        filters: { purpose: "VN-P2-S1_FEEDBACK_COMPARISON" },
      });
      setSelected(created);
      setReport(null);
      setSelectors([]);
      await loadCohorts();
    } catch (error) {
      setMessage(feedbackError(error));
    } finally {
      setBusy(false);
    }
  }

  async function makeReport() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await createFeedbackReport(selected.id);
      setReport(created);
      setSelected(await getFeedbackCohort(selected.id));
    } catch (error) {
      setMessage(feedbackError(error));
    } finally {
      setBusy(false);
    }
  }

  if (migrationRequired) {
    return (
      <section className="sim-feedback">
        <div className="sim-feedback-head">
          <div>
            <span className="sim-section-kicker">Feedback / Validation</span>
            <h4>비교 근거 연결</h4>
          </div>
        </div>
        <div className="sim-feedback-blocked">
          <strong>Feedback 저장 구조 준비가 필요합니다.</strong>
          <p>조회 화면이 DB를 자동 변경하지 않도록 migration은 명시적으로 실행하게 되어 있습니다.</p>
          <code>python tools/data/migrate_feedback_vnp2s1.py</code>
        </div>
      </section>
    );
  }

  return (
    <section className="sim-feedback">
      <div className="sim-feedback-head">
        <div>
          <span className="sim-section-kicker">Feedback / Validation</span>
          <h4>기존 근거를 같은 기준끼리 비교</h4>
          <p>Tracking 관찰, VAL.1 가격 관찰, VAL.2 가상 실행, Backtest를 원본 의미를 유지한 채 연결합니다.</p>
        </div>
        <button className="sim-secondary" disabled={busy} onClick={() => void loadCohorts()}>
          목록 새로고침
        </button>
      </div>

      <div className="sim-feedback-builder">
        <div className="sim-feedback-quick">
          {selectedValidationId && (
            <button
              className="sim-secondary"
              disabled={selectorKeySet.has(`VALIDATION:${selectedValidationId}`)}
              onClick={() => addSelector({ source_type: "VALIDATION", source_id: selectedValidationId })}
            >
              현재 VAL.1 추가
            </button>
          )}
          <button
            className="sim-secondary"
            disabled={selectorKeySet.has("TRACKING:ALL")}
            onClick={() => addSelector({ source_type: "TRACKING", source_id: "ALL" })}
          >
            Scanner Tracking 전체 추가
          </button>
        </div>

        <div className="sim-feedback-source-form">
          <select value={sourceType} onChange={(event) => setSourceType(event.target.value as FeedbackSourceType)}>
            <option value="VALIDATION">VAL.1</option>
            <option value="EXECUTION">VAL.2</option>
            <option value="TRACKING">Tracking</option>
            <option value="BACKTEST">Backtest</option>
          </select>
          <input
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            placeholder={sourceType === "TRACKING" ? "ALL 또는 Tracking ID" : "원본 ID"}
          />
          <button className="sim-secondary" onClick={() => addSelector({ source_type: sourceType, source_id: sourceId })}>
            원본 추가
          </button>
        </div>

        {selectors.length > 0 && (
          <div className="sim-feedback-source-list">
            {selectors.map((item, index) => (
              <div key={`${item.source_type}:${item.source_id}`}>
                <span>{sourceLabel(item.source_type)}</span>
                <strong>{item.source_id}</strong>
                <button
                  className="sim-text-button"
                  onClick={() => setSelectors((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}
                >
                  제거
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="sim-feedback-create">
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={160} />
          <button className="sim-primary" disabled={busy || selectors.length === 0} onClick={() => void makeCohort()}>
            {busy ? "처리 중…" : "Cohort 만들기"}
          </button>
        </div>
      </div>

      {message && <p className="sim-feedback-message">{message}</p>}

      <div className="sim-feedback-layout">
        <aside className="sim-feedback-cohorts">
          <strong>저장된 cohort</strong>
          {cohorts.length === 0 ? (
            <p>아직 저장된 cohort가 없습니다.</p>
          ) : cohorts.map((item) => (
            <button
              key={item.id}
              className={selected?.id === item.id ? "selected" : undefined}
              onClick={() => void chooseCohort(item.id)}
            >
              <span>{item.name}</span>
              <small>{item.status} · 포함 {count(item.included_count)} / 전체 {count(item.member_count)}</small>
            </button>
          ))}
        </aside>

        <div className="sim-feedback-detail">
          {!selected ? (
            <div className="sim-empty">
              <strong>비교할 cohort를 선택하세요.</strong>
              <p>서로 다른 계산 기준은 같은 평균으로 합치지 않습니다.</p>
            </div>
          ) : (
            <>
              <div className="sim-feedback-selected-head">
                <div>
                  <span>{selected.cohort_version}</span>
                  <h5>{selected.name}</h5>
                </div>
                <strong>{selected.source_verification?.status ?? selected.status}</strong>
              </div>

              <dl className="sim-feedback-facts">
                <div><dt>원본</dt><dd>{count(selected.sources.length)}개</dd></div>
                <div><dt>근거 행</dt><dd>{count(selected.members.length)}건</dd></div>
                <div><dt>제외</dt><dd>{count(selected.members.filter((item) => item.inclusion_status !== "INCLUDED").length)}건</dd></div>
                <div><dt>원본 상태</dt><dd>{selected.source_verification?.status ?? "-"}</dd></div>
              </dl>

              {selected.sources.some((source) => source.status === "ERROR") && (
                <div className="sim-feedback-errors">
                  <strong>읽지 못한 원본</strong>
                  {selected.sources.filter((source) => source.status === "ERROR").map((source) => (
                    <p key={`${source.source_type}:${source.source_id}`}>
                      {sourceLabel(source.source_type)} · {source.source_id} · {source.error_message ?? source.error_code}
                    </p>
                  ))}
                </div>
              )}

              <div className="sim-feedback-report-action">
                <div>
                  <strong>비교 보고서</strong>
                  <small>현재 cohort snapshot으로 새 report version을 만듭니다. 기존 report는 덮어쓰지 않습니다.</small>
                </div>
                <button className="sim-primary" disabled={busy} onClick={() => void makeReport()}>
                  {busy ? "계산 중…" : "새 보고서 계산"}
                </button>
              </div>

              {report && (
                <div className="sim-feedback-report">
                  <div className="sim-feedback-report-summary">
                    <div>
                      <span>근거 상태</span>
                      <strong>{evidenceStateLabel(report.summary.evidence_state)}</strong>
                    </div>
                    <div>
                      <span>비교 그룹</span>
                      <strong>{count(report.summary.counts.comparison_group_count)}</strong>
                    </div>
                    <div>
                      <span>성과 표본</span>
                      <strong>{count(report.summary.counts.metric_sample_count)}</strong>
                    </div>
                    <div>
                      <span>원본 검증</span>
                      <strong>{report.effective_status ?? report.status}</strong>
                    </div>
                  </div>

                  <p className="sim-feedback-guardrail">
                    최소 표본 기준은 아직 정해지지 않았으므로 이 화면은 전략 우수·승격 결론을 내리지 않습니다.
                    CENSORED는 실현수익 0%로 계산하지 않습니다.
                  </p>

                  <div className="sim-breakdown-scroll">
                    <table className="sim-breakdown-table">
                      <thead>
                        <tr>
                          <th>근거 종류</th>
                          <th>시장</th>
                          <th>전략</th>
                          <th>Horizon</th>
                          <th>정책</th>
                          <th>행</th>
                          <th>20D 관찰</th>
                          <th>실현 가상수익</th>
                          <th>CENSORED</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.summary.comparison.groups.map((group) => {
                          const d = group.comparison_dimensions;
                          return (
                            <tr key={group.comparison_key}>
                              <td>{dimensionText(d.origin_kind)}</td>
                              <td>{dimensionText(d.market)}</td>
                              <td>{dimensionText(d.strategy)}</td>
                              <td>{dimensionText(d.horizon_intent)}</td>
                              <td>{dimensionText(d.exit_policy_token ?? d.execution_policy_version)}</td>
                              <td>{count(group.member_count)}</td>
                              <td>
                                {pct(group.metrics.return_20d.average_pct)}
                                <small> · {count(group.metrics.return_20d.sample_count)}건</small>
                              </td>
                              <td>
                                {pct(group.metrics.realized_net_return.average_pct)}
                                <small> · {count(group.metrics.realized_net_return.sample_count)}건</small>
                              </td>
                              <td>{count(group.maturity.CENSORED ?? 0)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {Object.keys(report.summary.exclusion_reasons).length > 0 && (
                    <p className="sim-feedback-note">
                      제외: {Object.entries(report.summary.exclusion_reasons).map(([key, value]) => `${key} ${count(value)}건`).join(" · ")}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
