import EntryRiskGuideCard from "./EntryRiskGuideCard";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearScannerSession,
  latestScannerDataDate,
  localDateKey,
  readScannerSession,
  writeScannerSession,
} from "./scannerSession";
import {
  cancelBacktestJob,
  createScannerJob,
  fetchBacktestJob,
  prepareScannerLatestData,
  type BacktestJob,
  type ScannerCandidate,
  type ScannerFreshnessResponse,
  type ScannerResponse,
  type StockSearchItem,
} from "../services/api";

type MarketScope = "ALL" | "KOSPI" | "KOSDAQ";

type Props = {
  onAnalyzeStock: (item: StockSearchItem) => void;
};

const regimeLabel: Record<string, string> = {
  TREND_UP: "상승장",
  RANGE: "횡보장",
  TREND_DOWN: "하락장",
  HIGH_VOLATILITY: "고변동성",
  PANIC: "패닉",
  UNKNOWN: "판단 보류",
};

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);
}

function formatSignedPct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatElapsed(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  if (safe < 60) return `${safe}초`;
  const minutes = Math.floor(safe / 60);
  const remain = safe % 60;
  return `${minutes}분 ${remain}초`;
}

function formatLocalTime(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function evidenceKey(candidate: ScannerCandidate) {
  return `${candidate.market}-${candidate.code}`;
}

const scannerStages = [
  { key: "scanner_plan", label: "필요 데이터 확인" },
  { key: "scanner_data_prepare", label: "최근 시장 데이터 준비" },
  { key: "scanner_quick_filter", label: "전체 종목 빠른 검사" },
  { key: "scanner_deep_analysis", label: "상위 후보 전략·위험 확인" },
  { key: "scanner_finalize", label: "후보 풀 확정" },
  { key: "scanner_historical_evidence", label: "후보 풀 3년 근거" },
  { key: "scanner_priority_rank", label: "최종 우선순위 설명" },
];

function stageIndex(stage: string | undefined) {
  if (!stage) return 0;
  if (stage === "scanner_cache" || stage === "scanner_complete") return scannerStages.length;
  if (stage === "scanner_fast_budget" || stage === "scanner_universe") return 1;
  return Math.max(0, scannerStages.findIndex((item) => item.key === stage));
}

function candidateTone(candidate: ScannerCandidate) {
  if (candidate.candidate_state === "READY") return "ready";
  if (candidate.candidate_state === "WATCH") return "watch";
  if (candidate.candidate_state === "VALIDATION") return "validation";
  return "muted";
}

function conditionStatusLabel(candidate: ScannerCandidate) {
  const { passed, total, missing } = candidate.conditions;
  return `${passed}/${total} 충족 · 부족 ${missing}개`;
}

function CandidateCard({
  candidate,
  rank,
  onAnalyze,
  evidenceOpen,
  onEvidenceToggle,
}: {
  candidate: ScannerCandidate;
  rank: number;
  onAnalyze: () => void;
  evidenceOpen: boolean;
  onEvidenceToggle: (open: boolean) => void;
}) {
  const tone = candidateTone(candidate);
  const topMissing = candidate.conditions.top_missing ?? [];
  const evidence = candidate.historical_evidence;
  const evidenceLabel = evidence?.label ?? (candidate.historical_fit.verified === false ? "과거 검증 전" : candidate.historical_fit.label);
  const evidenceSummary = evidence?.summary ?? candidate.historical_fit.summary;
  return (
    <article className={`scanner-candidate-card tone-${tone}`}>
      <div className="scanner-rank">{rank}위</div>
      <div className="scanner-candidate-main">
        <div className="scanner-candidate-head">
          <div>
            <div className="scanner-stock-line">
              <strong>{candidate.name}</strong>
              <span>{candidate.market} · {candidate.code}</span>
            </div>
            <span className={`scanner-state-badge ${tone}`}>{candidate.candidate_label}</span>
          </div>
          <div className="scanner-price-box">
            <small>기준 종가</small>
            <strong>{formatNumber(candidate.current_price)}원</strong>
            <span>{formatDate(candidate.data_date)} 기준</span>
          </div>
        </div>

        {candidate.priority && (
          <section className={`scanner-priority-card priority-${candidate.priority.tier.toLowerCase()}`}>
            <div className="scanner-priority-head">
              <div>
                <small>왜 {rank}위인가요?</small>
                <strong>{candidate.priority.label}</strong>
                <p>{candidate.priority.reason}</p>
              </div>
            </div>
            <div className="scanner-priority-factors">
              {candidate.priority.strengths.map((item) => <span className="positive" key={`strength-${item}`}>✓ {item}</span>)}
              {candidate.priority.facts
                .filter((item) => !/\b거리\s+[0-9.]+%/.test(item))
                .map((item) => <span className="neutral" key={`fact-${item}`}>· {item}</span>)}
              {candidate.priority.penalties.map((item) => <span className="negative" key={`penalty-${item}`}>△ {item}</span>)}
            </div>
            <small className="scanner-priority-rule">순위 기준 · {candidate.priority.ranking_rule}</small>
          </section>
        )}

        <div className="scanner-strategy-box">
          <small>현재 가장 맞는 방법</small>
          <strong>{candidate.strategy_easy_name}</strong>
          <span>전문 용어 · {candidate.strategy_name}</span>
          <p>{candidate.strategy_description}</p>
        </div>

        <div className="scanner-judgement-row">
          <section>
            <small>현재 판단</small>
            <strong>{candidate.action_label}</strong>
            <p>{candidate.headline}</p>
          </section>
          <section>
            <small>진입 준비</small>
            <strong>{conditionStatusLabel(candidate)}</strong>
            <p>{candidate.reason}</p>
          </section>
          <section>
            <small>3년 과거 근거</small>
            <strong>{evidenceLabel}</strong>
            <p>{evidenceSummary}</p>
          </section>
        </div>

        {candidate.entry_risk_guide && <EntryRiskGuideCard guide={candidate.entry_risk_guide} compact />}

        {evidence && (
          <section className={`scanner-evidence-card evidence-${evidence.status.toLowerCase()}`}>
            <div className="scanner-section-caption">
              <strong>같은 전략의 최근 3년 과거 근거</strong>
              <span>{formatDate(evidence.period.start)} ~ {formatDate(evidence.period.end)}</span>
            </div>
            {evidence.verified ? (
              <>
                <div className="scanner-evidence-grid">
                  <div><small>유사 거래</small><strong>{evidence.sample_count}회</strong><span>{evidence.sample_sufficient ? "평가 가능한 표본" : `최소 ${evidence.minimum_sample}회 필요`}</span></div>
                  <div><small>수익 거래</small><strong>{evidence.wins} / {evidence.sample_count}</strong><span>상승 확률이 아니라 과거 결과입니다.</span></div>
                  <div><small>평균 순수익</small><strong>{formatSignedPct(evidence.average_net_return_pct)}</strong><span>거래당 과거 평균</span></div>
                  <div><small>최대 낙폭</small><strong>{formatSignedPct(evidence.max_drawdown_pct)}</strong><span>과거 검증 구간 기준</span></div>
                </div>
                <details
                  className="scanner-evidence-details"
                  open={evidenceOpen}
                  onToggle={(event) => onEvidenceToggle(event.currentTarget.open)}
                >
                  <summary>과거 근거 자세히 보기</summary>
                  <div className="scanner-evidence-detail-grid">
                    <div><small>이익/손실 비율(PF)</small><strong>{evidence.profit_factor == null ? "-" : evidence.profit_factor.toFixed(2)}</strong></div>
                    <div><small>손절 종료</small><strong>{evidence.exit_counts.stop}회</strong></div>
                    <div><small>1차 목표가 도달 종료</small><strong>{evidence.exit_counts.target1}회</strong></div>
                    <div><small>시간 종료</small><strong>{evidence.exit_counts.time_exit}회</strong></div>
                  </div>
                  {evidence.market_regime_summary.length > 0 && (
                    <div className="scanner-regime-evidence">
                      {evidence.market_regime_summary.map((row) => (
                        <span key={row.regime}><b>{regimeLabel[row.regime] ?? row.regime}</b> · {row.trades}회 · 평균 {formatSignedPct(row.average_net_return_pct)}</span>
                      ))}
                    </div>
                  )}
                  {evidence.warnings.length > 0 && <div className="scanner-evidence-warnings">{evidence.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
                  <p className="scanner-evidence-guardrail">{evidence.guardrail}</p>
                </details>
              </>
            ) : (
              <div className="scanner-evidence-unavailable">
                <strong>{evidence.label}</strong>
                <p>{evidence.summary}</p>
                {evidence.warnings.length > 0 && <small>{evidence.warnings.join(" · ")}</small>}
              </div>
            )}
          </section>
        )}

        {topMissing.length > 0 && (
          <div className="scanner-missing-block">
            <div className="scanner-section-caption">
              <strong>지금 부족한 핵심 조건</strong>
              <span>사용자가 계산할 필요는 없습니다.</span>
            </div>
            <div className="scanner-missing-grid">
              {topMissing.map((condition, index) => (
                <div className="scanner-missing-item" key={`${condition.condition_id ?? condition.raw}-${index}`}>
                  <strong>{condition.label}</strong>
                  <p>{condition.detail}</p>
                  {(condition.current_value || condition.required_value) && (
                    <div className="scanner-condition-values">
                      {condition.current_value && <span><small>현재</small><b>{condition.current_value}</b></span>}
                      {condition.required_value && <span><small>필요</small><b>{condition.required_value}</b></span>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="scanner-action-row">
          <div>
            <small>지금 행동</small>
            <strong>{candidate.user_action.title || "현재 판단을 유지하세요."}</strong>
            <p>{candidate.user_action.detail}</p>
          </div>
          <button type="button" className="scanner-detail-button" onClick={onAnalyze}>이 종목 자세히 분석</button>
        </div>

        {candidate.risk.warning && candidate.risk.warnings.length > 0 && (
          <div className="scanner-risk-note">
            <strong>추가 주의</strong>
            <span>{candidate.risk.warnings.join(" · ")}</span>
          </div>
        )}
      </div>
    </article>
  );
}

export default function ScannerPanel({ onAnalyzeStock }: Props) {
  const initialSession = useMemo(() => readScannerSession(), []);
  const [scope, setScope] = useState<MarketScope>(initialSession?.scope ?? "ALL");
  const [job, setJob] = useState<BacktestJob<ScannerResponse> | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(initialSession?.result ?? null);
  const [error, setError] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(initialSession?.showMore ?? false);
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<string[]>(initialSession?.expandedEvidenceIds ?? []);
  const [completedAt, setCompletedAt] = useState<number | null>(initialSession?.completedAt ?? null);
  const [restoredFromSession, setRestoredFromSession] = useState(Boolean(initialSession));
  const [clock, setClock] = useState(Date.now());
  const [freshnessBusy, setFreshnessBusy] = useState(false);
  const [freshnessFailure, setFreshnessFailure] = useState<ScannerFreshnessResponse | null>(null);
  const [dateNotice, setDateNotice] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const lastProgressAtRef = useRef<number | null>(null);
  const lastProgressSignatureRef = useRef("");
  const savedScrollRef = useRef(initialSession?.scrollY ?? 0);
  const didRestoreScrollRef = useRef(false);

  const jobBusy = job?.status === "queued" || job?.status === "running";
  const busy = freshnessBusy || jobBusy;
  const progress = job?.progress;

  useEffect(() => {
    const onScroll = () => {
      savedScrollRef.current = window.scrollY;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!result) return;
    writeScannerSession({
      scope,
      result,
      completedAt: completedAt ?? Date.now(),
      scrollY: savedScrollRef.current,
      showMore,
      expandedEvidenceIds,
    });
  }, [scope, result, completedAt, showMore, expandedEvidenceIds]);

  useEffect(() => {
    if (!initialSession || !result || didRestoreScrollRef.current) return;
    didRestoreScrollRef.current = true;
    const target = Math.max(0, initialSession.scrollY);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.scrollTo({ top: target, behavior: "auto" }));
    });
  }, [initialSession, result]);

  useEffect(() => () => {
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    if (!dateNotice) return undefined;
    const timer = window.setTimeout(() => setDateNotice(null), 4500);
    return () => window.clearTimeout(timer);
  }, [dateNotice]);

  function stockItem(candidate: ScannerCandidate): StockSearchItem {
    return {
      code: candidate.code,
      standard_code: candidate.code,
      name: candidate.name,
      full_name: candidate.name,
      english_name: "",
      market: candidate.market,
      market_name: candidate.market,
      security_group: "주식",
      section: "",
      stock_type: "보통주",
      listed_date: "",
      listed_shares: null,
      analysis_as_of_date: candidate.data_date || null,
    };
  }

  async function poll(jobId: string) {
    try {
      const latest = await fetchBacktestJob<ScannerResponse>(jobId);
      const signature = JSON.stringify({
        stage: latest.stage,
        current: latest.progress?.current,
        percent: latest.progress?.percent,
        details: latest.progress?.details,
      });
      if (signature !== lastProgressSignatureRef.current) {
        lastProgressSignatureRef.current = signature;
        lastProgressAtRef.current = Date.now();
      }
      setJob(latest);
      if (latest.status === "completed" && latest.result) {
        setResult(latest.result);
        setShowMore(false);
        setExpandedEvidenceIds([]);
        setCompletedAt(Date.now());
        setRestoredFromSession(false);
        savedScrollRef.current = window.scrollY;
        return;
      }
      if (latest.status === "failed") {
        setError(latest.error || "종목 찾기 중 오류가 발생했습니다.");
        return;
      }
      if (latest.status === "cancelled") return;
      pollRef.current = window.setTimeout(() => void poll(jobId), 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목 찾기 상태를 확인하지 못했습니다.");
    }
  }

  async function runScanner(
    forceRefresh = false,
    allowLargeSync = false,
    pinnedAsOfDate: string | null = null,
  ) {
    if (busy) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    setError(null);
    setFreshnessFailure(null);
    if (!result) {
      setShowMore(false);
      setExpandedEvidenceIds([]);
    }
    const started = Date.now();
    startedAtRef.current = started;
    lastProgressAtRef.current = started;
    lastProgressSignatureRef.current = "";
    setClock(started);

    let resolvedAsOfDate = pinnedAsOfDate;
    if (!pinnedAsOfDate) {
      setFreshnessBusy(true);
      try {
        const freshness = await prepareScannerLatestData({
          market_scope: scope,
          known_data_date: latestScannerDataDate(result),
        });
        if (freshness.status === "UPDATE_FAILED" || !freshness.resolved_as_of_date) {
          setFreshnessFailure(freshness);
          return;
        }
        resolvedAsOfDate = freshness.resolved_as_of_date;
        if (freshness.date_changed) {
          setDateNotice(freshness.resolved_as_of_date);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "최신 확정 시세를 확인하지 못했습니다.");
        return;
      } finally {
        setFreshnessBusy(false);
      }
    }

    try {
      const created = await createScannerJob({
        market_scope: scope,
        as_of_date: resolvedAsOfDate ?? undefined,
        candidate_limit: 5,
        force_refresh: forceRefresh,
        allow_large_sync: allowLargeSync,
      });
      setJob(created);
      void poll(created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목 찾기를 시작하지 못했습니다.");
    }
  }

  function persistBeforeNavigation() {
    if (!result) return;
    const scrollY = window.scrollY;
    savedScrollRef.current = scrollY;
    writeScannerSession({
      scope,
      result,
      completedAt: completedAt ?? Date.now(),
      scrollY,
      showMore,
      expandedEvidenceIds,
    });
  }

  function analyzeCandidate(candidate: ScannerCandidate) {
    persistBeforeNavigation();
    onAnalyzeStock(stockItem(candidate));
  }

  function changeScope(value: MarketScope) {
    if (busy || value === scope) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    clearScannerSession();
    setScope(value);
    setJob(null);
    setResult(null);
    setError(null);
    setShowMore(false);
    setExpandedEvidenceIds([]);
    setCompletedAt(null);
    setRestoredFromSession(false);
    setFreshnessFailure(null);
    setDateNotice(null);
    savedScrollRef.current = 0;
    didRestoreScrollRef.current = true;
  }

  function toggleEvidence(candidate: ScannerCandidate, open: boolean) {
    const key = evidenceKey(candidate);
    setExpandedEvidenceIds((current) => {
      if (open) return current.includes(key) ? current : [...current, key];
      return current.filter((item) => item !== key);
    });
  }

  async function cancel() {
    if (!job?.job_id || !busy) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    try {
      const cancelled = await cancelBacktestJob<ScannerResponse>(job.job_id);
      setJob(cancelled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 취소에 실패했습니다.");
    }
  }

  const marketText = useMemo(() => {
    if (!result?.market_summary?.length) return "아직 시장 상태를 계산하지 않았습니다.";
    return result.market_summary.map((item) => `${item.market} ${regimeLabel[item.regime] ?? item.regime}`).join(" · ");
  }, [result]);

  const progressDetails = progress?.details ?? {};
  const overallPercentRaw = Number(progressDetails.overall_percent ?? progress?.percent ?? 0);
  const overallPercent = Number.isFinite(overallPercentRaw) ? Math.max(0, Math.min(100, overallPercentRaw)) : 0;
  const elapsedSeconds = startedAtRef.current == null ? 0 : Math.max(0, (clock - startedAtRef.current) / 1000);
  const staleSeconds = lastProgressAtRef.current == null ? 0 : Math.max(0, (clock - lastProgressAtRef.current) / 1000);
  const currentStageIndex = stageIndex(job?.stage);
  const preparationItems = result?.preparation_required ?? [];
  const preparationRequests = preparationItems.reduce((sum, item) => sum + Number(item.estimated_network_requests || 0), 0);
  const noAnalyzedData = Boolean(result && result.summary.universe_total === 0 && preparationItems.length > 0);
  const analysisDataDate = latestScannerDataDate(result);
  const restoredOnDifferentDay = Boolean(initialSession && restoredFromSession && localDateKey(initialSession.completedAt) !== localDateKey());

  return (
    <div className="scanner-workspace">
      <section className="scanner-hero">
        <div>
          <span className="eyebrow">STOCK SCANNER · v0.21.4-B.2.1.1</span>
          <h1>오늘 어떤 종목을 먼저 볼까요?</h1>
          <p>종목을 직접 고르기 전에 현재 조건을 먼저 보고, Risk·진입 기준까지의 거리·같은 전략의 3년 과거 근거를 순서대로 비교해 먼저 확인할 후보를 정합니다.</p>
        </div>
        <div className="scanner-flow" aria-label="종목 찾기 흐름">
          <span>1 · 시장 전체 빠른 검사</span><i>→</i><span>2 · 전략·Risk·3년 근거</span><i>→</i><span>3 · 후보 우선순위 설명</span>
        </div>
      </section>

      <section className="scanner-control-card">
        <div>
          <span>검색 시장</span>
          <strong>일반 주식 중심으로 찾습니다.</strong>
          <p>우선주·SPAC·ETF·ETN·거래정지·데이터 부족 종목은 기본 후보에서 제외합니다.</p>
        </div>
        <div className="scanner-market-tabs" role="group" aria-label="검색 시장 선택">
          {(["ALL", "KOSPI", "KOSDAQ"] as MarketScope[]).map((value) => (
            <button key={value} type="button" className={scope === value ? "active" : ""} onClick={() => changeScope(value)} disabled={busy}>
              {value === "ALL" ? "전체" : value}
            </button>
          ))}
        </div>
        <div className="scanner-control-actions">
          {result && !busy ? (
            <div className="scanner-result-held">
              <strong>✓ 분석 결과 유지 중</strong>
              <span>같은 설정에서는 다시 찾지 않습니다.</span>
            </div>
          ) : (
            <button type="button" className="scanner-run-button" onClick={() => void runScanner(false)} disabled={busy}>
              {freshnessBusy ? "최신 시세 확인 중..." : jobBusy ? "후보 찾는 중..." : "오늘의 후보 찾기"}
            </button>
          )}
          {jobBusy && <button type="button" className="scanner-cancel-button" onClick={() => void cancel()}>중지</button>}
        </div>
      </section>

      {dateNotice && (
        <aside className="scanner-date-toast" role="status" aria-live="polite">
          <div>
            <strong>✓ 새로운 확정 시세를 반영했습니다.</strong>
            <span>{formatDate(dateNotice)} 기준으로 분석합니다.</span>
          </div>
          <button type="button" aria-label="안내 닫기" onClick={() => setDateNotice(null)}>×</button>
        </aside>
      )}

      {freshnessFailure && (
        <section className="scanner-freshness-failure">
          <div>
            <strong>최신 시세를 가져오지 못했습니다.</strong>
            <p>{freshnessFailure.message}</p>
            {freshnessFailure.available_data_date && (
              <span>현재 사용할 수 있는 확정 일봉 · {formatDate(freshnessFailure.available_data_date)}</span>
            )}
          </div>
          <div className="scanner-freshness-actions">
            <button type="button" onClick={() => void runScanner(Boolean(result))}>다시 시도</button>
            {freshnessFailure.available_data_date && (
              <button
                type="button"
                className="secondary"
                onClick={() => void runScanner(Boolean(result), false, freshnessFailure.available_data_date)}
              >
                {formatDate(freshnessFailure.available_data_date)} 기준으로 분석
              </button>
            )}
          </div>
        </section>
      )}

      {jobBusy && progress && (
        <section className="scanner-progress-card">
          <div className="scanner-progress-head">
            <div>
              <span>StockScope가 자동으로 확인 중</span>
              <strong>{progress.message || "시장 데이터를 확인하고 있습니다."}</strong>
            </div>
            <b>{Math.round(overallPercent)}%</b>
          </div>
          <div className="scanner-progress-track"><i style={{ width: `${Math.max(2, overallPercent)}%` }} /></div>

          <div className="scanner-progress-stages">
            {scannerStages.map((item, index) => {
              const done = currentStageIndex > index || job?.stage === "scanner_complete" || job?.stage === "scanner_cache";
              const active = currentStageIndex === index && !done;
              return (
                <div key={item.key} className={done ? "done" : active ? "active" : "waiting"}>
                  <i>{done ? "✓" : active ? "●" : "○"}</i>
                  <span>{item.label}</span>
                </div>
              );
            })}
          </div>

          <div className="scanner-progress-meta">
            <span>경과 <b>{formatElapsed(elapsedSeconds)}</b></span>
            <span>마지막 진행 <b>{staleSeconds < 2 ? "방금" : `${Math.floor(staleSeconds)}초 전`}</b></span>
            {progressDetails.current_item && <span>현재 <b>{String(progressDetails.current_item)}</b></span>}
            {progressDetails.items_done != null && progressDetails.items_total != null && (
              <span>처리 <b>{formatNumber(Number(progressDetails.items_done))} / {formatNumber(Number(progressDetails.items_total))}</b></span>
            )}
            {progressDetails.shortlisted != null && <span>현재 후보 <b>{String(progressDetails.shortlisted)}개</b></span>}
            {progressDetails.estimated_network_requests != null && <span>예상 KRX 신규 요청 <b>{String(progressDetails.estimated_network_requests)}회</b></span>}
            {progressDetails.network_requests_so_far != null && <span>실제 KRX 요청 <b>{String(progressDetails.network_requests_so_far)}회</b></span>}
            {progressDetails.processing_rate != null && <span>처리 속도 <b>{Number(progressDetails.processing_rate).toFixed(1)}건/초</b></span>}
            {progressDetails.eta_seconds != null && Number(progressDetails.eta_seconds) >= 0 && <span>예상 남은 시간 <b>약 {formatElapsed(Number(progressDetails.eta_seconds))}</b></span>}
            {progressDetails.active_requests != null && progressDetails.concurrency_limit != null && (
              <span>동시 처리 <b>{String(progressDetails.active_requests)} / {String(progressDetails.concurrency_limit)}</b></span>
            )}
            {progressDetails.retry_count != null && Number(progressDetails.retry_count) > 0 && <span>재시도 <b>{String(progressDetails.retry_count)}회</b></span>}
          </div>

          {staleSeconds >= 30 && staleSeconds < 90 && (
            <div className="scanner-progress-warning">
              <strong>처리가 평소보다 오래 걸리고 있습니다.</strong>
              <span>마지막 진행이 {Math.floor(staleSeconds)}초 전입니다. 작업은 자동으로 계속 확인합니다.</span>
            </div>
          )}
          {staleSeconds >= 90 && (
            <div className="scanner-progress-warning danger">
              <strong>최근 진행 상태가 오래 갱신되지 않았습니다.</strong>
              <span>계속 기다리거나 위의 중지 버튼으로 안전하게 취소할 수 있습니다. 이미 저장된 시장 데이터는 유지됩니다.</span>
            </div>
          )}
        </section>
      )}

      {error && (
        <section className="scanner-error-card">
          <strong>{result ? "새 분석을 완료하지 못했습니다. 기존 결과를 유지합니다." : "종목 찾기를 완료하지 못했습니다."}</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void runScanner(Boolean(result))}>다시 시도</button>
        </section>
      )}

      {!result && !busy && !error && !freshnessFailure && (
        <section className="scanner-empty-start">
          <strong>전략을 먼저 고를 필요가 없습니다.</strong>
          <p>버튼 한 번으로 시장 전체를 빠르게 거른 뒤, 조건이 좋은 종목만 10가지 전략과 위험 관리 기준으로 다시 확인합니다.</p>
        </section>
      )}

      {result && (
        <>
          <section className="scanner-result-summary">
            <div>
              <span>현재 시장</span>
              <strong>{marketText}</strong>
              <p>{result.methodology.meaning}</p>
            </div>
            <div className="scanner-summary-numbers">
              <span><small>전체 확인</small><b>{formatNumber(result.summary.universe_total)}개</b></span>
              <span><small>상세 검증</small><b>{formatNumber(result.summary.deep_analyzed)}개</b></span>
              <span><small>관심 후보</small><b>{formatNumber(result.summary.candidate_count)}개</b></span>
              <span><small>먼저 표시</small><b>{formatNumber(result.summary.shown_count)}개</b></span>
            </div>
            <div className="scanner-analysis-date">
              <span>분석 기준일</span>
              <strong>{analysisDataDate ? `${formatDate(analysisDataDate)} 확정 일봉` : "확정 일봉 확인 필요"}</strong>
            </div>
            <div className="scanner-cache-note">
              {result.scanner_cache_hit ? "오늘 계산한 결과를 바로 재사용했습니다." : `KRX 신규 요청 ${result.diagnostics.network_requests}회 · 시장 저장 데이터 재사용 ${result.diagnostics.market_store_reused_items}건`}
            </div>
            <div className={`scanner-session-note ${restoredFromSession ? "restored" : "current"}`}>
              <div>
                <small>{analysisDataDate ? `${formatDate(analysisDataDate)} 확정 일봉 기준` : "확정 일봉 기준"}</small>
                <strong>{restoredFromSession ? "이전 분석 결과를 그대로 불러왔습니다." : "현재 세션에서 이 결과를 유지합니다."}</strong>
                <span>마지막 분석 {formatLocalTime(completedAt)}</span>
              </div>
              <p>
                {restoredOnDifferentDay
                  ? "브라우저 날짜가 바뀌었습니다. 새 확정 일봉이 생겼다면 ‘다시 분석’으로 갱신하세요."
                  : "상세 분석 후 종목 찾기로 돌아와도 같은 결과를 다시 계산하지 않습니다."}
              </p>
            </div>
          </section>

          {preparationItems.length > 0 && (
            <section className="scanner-preparation-card">
              <div>
                <span>빠른 검색 범위 제한</span>
                <strong>대량 다운로드 없이 저장된 데이터로 먼저 찾았습니다.</strong>
                <p>최근 기술지표 계산에 필요한 데이터가 부족해 자동 다운로드 상한 {formatNumber(result.fast_request_limit ?? 60)}회를 넘겼습니다. 현재 후보는 사용 가능한 데이터 범위에서 만든 결과입니다.</p>
                <div className="scanner-preparation-markets">
                  {preparationItems.map((item) => (
                    <span key={item.market}><b>{item.market}</b> 예상 {formatNumber(item.estimated_network_requests)}회</span>
                  ))}
                </div>
              </div>
              <button type="button" onClick={() => void runScanner(true, true)} disabled={busy}>시장 데이터 준비 시작 · 약 {formatNumber(preparationRequests)}회</button>
            </section>
          )}

          <section className="scanner-section-head">
            <div>
              <span>오늘 먼저 볼 후보</span>
              <h2>{result.candidates.length > 0 ? `${result.candidates.length}개를 먼저 확인하세요.` : noAnalyzedData ? "아직 후보를 판단하지 못했습니다." : "억지로 추천할 종목이 없습니다."}</h2>
              <p>순위는 상승 확률이 아닙니다. 현재 조건을 먼저 보고 Risk, 실제 진입 기준까지의 거리, 같은 전략의 3년 과거 근거 순으로 비교해 먼저 확인할 순서를 정합니다.</p>
            </div>
            <button type="button" className="scanner-refresh-button" onClick={() => void runScanner(true)} disabled={busy}>다시 분석</button>
          </section>

          {result.candidates.length === 0 ? (
            <section className="scanner-no-candidate">
              <strong>{noAnalyzedData ? "아직 시장 데이터 준비가 필요합니다." : "현재는 관망이 정상 결과입니다."}</strong>
              <p>{result.empty_message}</p>
            </section>
          ) : (
            <div className="scanner-candidate-list">
              {result.candidates.map((candidate, index) => (
                <CandidateCard
                  key={`${candidate.market}-${candidate.code}`}
                  candidate={candidate}
                  rank={index + 1}
                  onAnalyze={() => analyzeCandidate(candidate)}
                  evidenceOpen={expandedEvidenceIds.includes(evidenceKey(candidate))}
                  onEvidenceToggle={(open) => toggleEvidence(candidate, open)}
                />
              ))}
            </div>
          )}

          {result.more_candidates.length > 0 && (
            <section className="scanner-more-section">
              <button type="button" onClick={() => setShowMore((value) => !value)}>
                {showMore ? "다른 후보 숨기기 ▲" : `다른 후보 ${result.more_candidates.length}개 보기 ▼`}
              </button>
              {showMore && (
                <div className="scanner-candidate-list compact">
                  {result.more_candidates.map((candidate, index) => (
                    <CandidateCard
                      key={`more-${candidate.market}-${candidate.code}`}
                      candidate={candidate}
                      rank={result.candidates.length + index + 1}
                      onAnalyze={() => analyzeCandidate(candidate)}
                      evidenceOpen={expandedEvidenceIds.includes(evidenceKey(candidate))}
                      onEvidenceToggle={(open) => toggleEvidence(candidate, open)}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          <details className="scanner-details">
            <summary>어떤 종목을 제외했나요? <b>펼치기 ▼</b></summary>
            <div className="scanner-details-grid">
              <div><small>기본 제외</small><strong>{result.exclusion_policy.default.join(" · ")}</strong></div>
              <div><small>유동성 기준</small><strong>{result.exclusion_policy.liquidity}</strong></div>
              <div><small>특수/거래 제외</small><strong>{formatNumber(result.summary.special_excluded)}개</strong></div>
              <div><small>유동성 빠른 제외</small><strong>{formatNumber(result.summary.liquidity_filtered)}개</strong></div>
            </div>
          </details>

          <details className="scanner-details">
            <summary>개발 확인용 · Scanner 실행 진단 <b>펼치기 ▼</b></summary>
            <div className="scanner-details-grid diagnostics">
              <div><small>예상 KRX 요청</small><strong>{formatNumber(result.diagnostics.estimated_network_requests)}회</strong></div>
              <div><small>실제 KRX 요청</small><strong>{formatNumber(result.diagnostics.network_requests)}회</strong></div>
              <div><small>초기 데이터 처리속도</small><strong>{Number(result.diagnostics.bootstrap_request_rate ?? 0).toFixed(1)}건/초</strong></div>
              <div><small>최대 동시 처리</small><strong>{formatNumber(result.diagnostics.bootstrap_peak_concurrency ?? 0)}개</strong></div>
              <div><small>초기 준비 오류</small><strong>{formatNumber(result.diagnostics.bootstrap_errors ?? 0)}건</strong></div>
              <div><small>시장 저장소 재사용</small><strong>{formatNumber(result.diagnostics.market_store_reused_items)}건</strong></div>
              <div><small>KRX 응답 재사용</small><strong>{formatNumber(result.diagnostics.raw_cache_hits)}회</strong></div>
              <div><small>오늘 KRX(앱 기록)</small><strong>{formatNumber(result.diagnostics.budget_used)} / {formatNumber(result.diagnostics.budget_limit)}</strong></div>
              <div><small>Fast Scan 자동 상한</small><strong>{formatNumber(result.diagnostics.fast_request_limit ?? result.fast_request_limit)}회</strong></div>
              <div><small>3년 과거 근거 완료</small><strong>{formatNumber(result.summary.three_year_evidence_verified ?? 0)}개</strong></div>
              <div><small>현재 조건만</small><strong>{formatNumber(result.summary.current_only ?? 0)}개</strong></div>
              <div><small>데이터 준비</small><strong>{Number(result.diagnostics.data_prepare_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>빠른 검사</small><strong>{Number(result.diagnostics.quick_filter_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>상위 후보 분석</small><strong>{Number(result.diagnostics.deep_analysis_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>전체 실행</small><strong>{Number(result.diagnostics.total_seconds ?? 0).toFixed(2)}초</strong></div>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
