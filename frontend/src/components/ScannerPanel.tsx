import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelBacktestJob,
  createScannerJob,
  fetchBacktestJob,
  type BacktestJob,
  type ScannerCandidate,
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

function formatElapsed(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  if (safe < 60) return `${safe}초`;
  const minutes = Math.floor(safe / 60);
  const remain = safe % 60;
  return `${minutes}분 ${remain}초`;
}

const scannerStages = [
  { key: "scanner_plan", label: "필요 데이터 확인" },
  { key: "scanner_data_prepare", label: "최근 시장 데이터 준비" },
  { key: "scanner_quick_filter", label: "전체 종목 빠른 검사" },
  { key: "scanner_deep_analysis", label: "상위 후보 전략·위험 확인" },
  { key: "scanner_finalize", label: "후보 결과 정리" },
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

function CandidateCard({ candidate, rank, onAnalyze }: { candidate: ScannerCandidate; rank: number; onAnalyze: () => void }) {
  const tone = candidateTone(candidate);
  const topMissing = candidate.conditions.top_missing ?? [];
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
            <small>검증 수준</small>
            <strong>{candidate.historical_fit.verified === false ? "현재 조건 기준" : "현재 조건 + 과거 검증"}</strong>
            <p>{candidate.historical_fit.verified === false ? candidate.historical_fit.summary : `과거 사례 ${candidate.historical_fit.trades}건 · ${candidate.historical_fit.summary}`}</p>
          </section>
        </div>

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
  const [scope, setScope] = useState<MarketScope>("ALL");
  const [job, setJob] = useState<BacktestJob<ScannerResponse> | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const pollRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const lastProgressAtRef = useRef<number | null>(null);
  const lastProgressSignatureRef = useRef("");

  const busy = job?.status === "queued" || job?.status === "running";
  const progress = job?.progress;

  useEffect(() => () => {
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

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

  async function runScanner(forceRefresh = false, allowLargeSync = false) {
    if (busy) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    setError(null);
    setResult(null);
    setShowMore(false);
    const started = Date.now();
    startedAtRef.current = started;
    lastProgressAtRef.current = started;
    lastProgressSignatureRef.current = "";
    setClock(started);
    try {
      const created = await createScannerJob({
        market_scope: scope,
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

  return (
    <div className="scanner-workspace">
      <section className="scanner-hero">
        <div>
          <span className="eyebrow">STOCK SCANNER · v0.21.0.3</span>
          <h1>오늘 어떤 종목을 먼저 볼까요?</h1>
          <p>종목을 직접 고르기 전에 StockScope가 현재 조건, 10가지 전략, 위험, 과거 근거를 순서대로 확인해 먼저 볼 후보만 추립니다.</p>
        </div>
        <div className="scanner-flow" aria-label="종목 찾기 흐름">
          <span>1 · 시장 전체 빠른 검사</span><i>→</i><span>2 · 전략·위험 검증</span><i>→</i><span>3 · 후보 5개 안내</span>
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
            <button key={value} type="button" className={scope === value ? "active" : ""} onClick={() => setScope(value)} disabled={busy}>
              {value === "ALL" ? "전체" : value}
            </button>
          ))}
        </div>
        <div className="scanner-control-actions">
          <button type="button" className="scanner-run-button" onClick={() => void runScanner(false)} disabled={busy}>
            {busy ? "후보 찾는 중..." : "오늘의 후보 찾기"}
          </button>
          {busy && <button type="button" className="scanner-cancel-button" onClick={() => void cancel()}>중지</button>}
        </div>
      </section>

      {busy && progress && (
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
          <strong>종목 찾기를 완료하지 못했습니다.</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void runScanner(false)}>다시 시도</button>
        </section>
      )}

      {!result && !busy && !error && (
        <section className="scanner-empty-start">
          <strong>전략을 먼저 고를 필요가 없습니다.</strong>
          <p>버튼 한 번으로 시장 전체를 빠르게 거른 뒤, 조건이 좋은 종목만 10가지 전략과 Risk Engine으로 다시 확인합니다.</p>
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
            <div className="scanner-cache-note">
              {result.scanner_cache_hit ? "오늘 계산한 결과를 바로 재사용했습니다." : `KRX 신규 요청 ${result.diagnostics.network_requests}회 · 시장 저장 데이터 재사용 ${result.diagnostics.market_store_reused_items}건`}
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
              <p>순위는 상승 확률이 아니라 현재 준비도·위험·시장환경·과거 근거를 함께 본 확인 우선순위입니다.</p>
            </div>
            <button type="button" className="scanner-refresh-button" onClick={() => void runScanner(true)} disabled={busy}>최신 데이터로 다시 찾기</button>
          </section>

          {result.candidates.length === 0 ? (
            <section className="scanner-no-candidate">
              <strong>{noAnalyzedData ? "아직 시장 데이터 준비가 필요합니다." : "현재는 관망이 정상 결과입니다."}</strong>
              <p>{result.empty_message}</p>
            </section>
          ) : (
            <div className="scanner-candidate-list">
              {result.candidates.map((candidate, index) => (
                <CandidateCard key={`${candidate.market}-${candidate.code}`} candidate={candidate} rank={index + 1} onAnalyze={() => onAnalyzeStock(stockItem(candidate))} />
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
                    <CandidateCard key={`more-${candidate.market}-${candidate.code}`} candidate={candidate} rank={result.candidates.length + index + 1} onAnalyze={() => onAnalyzeStock(stockItem(candidate))} />
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
              <div><small>기존 KRX 캐시</small><strong>{formatNumber(result.diagnostics.raw_cache_hits)} hit</strong></div>
              <div><small>오늘 KRX(앱 기록)</small><strong>{formatNumber(result.diagnostics.budget_used)} / {formatNumber(result.diagnostics.budget_limit)}</strong></div>
              <div><small>Fast Scan 자동 상한</small><strong>{formatNumber(result.diagnostics.fast_request_limit ?? result.fast_request_limit)}회</strong></div>
              <div><small>과거 검증 완료</small><strong>{formatNumber(result.summary.historically_verified ?? 0)}개</strong></div>
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
