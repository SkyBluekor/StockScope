import { useEffect, useSyncExternalStore } from "react";
import {
  cancelBacktestJob,
  createScannerJob,
  fetchBacktestJob,
  type BacktestJob,
  type ScannerFreshnessResponse,
  type ScannerResponse,
} from "../services/api";
import {
  commitScannerSession,
  latestScannerDataDate,
  useScannerSession,
} from "./scannerSession";
import {
  progressStatusMark,
  scannerProgressView,
} from "./scannerProgress";

type MarketScope = "ALL" | "KOSPI" | "KOSDAQ";
type UnknownRecord = Record<string, unknown>;

type RunnerState = {
  scope: MarketScope;
  job: BacktestJob<ScannerResponse> | null;
  error: string | null;
  freshnessFailure: ScannerFreshnessResponse | null;
  startedAt: number | null;
};

const runnerListeners = new Set<() => void>();
let runnerState: RunnerState = {
  scope: "ALL",
  job: null,
  error: null,
  freshnessFailure: null,
  startedAt: null,
};
let runToken = 0;

function emitRunner() {
  runnerListeners.forEach((listener) => listener());
}

function setRunnerState(next: Partial<RunnerState>) {
  runnerState = { ...runnerState, ...next };
  emitRunner();
}

function subscribeRunner(listener: () => void) {
  runnerListeners.add(listener);
  return () => runnerListeners.delete(listener);
}

function getRunnerState() {
  return runnerState;
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function candidateKey(candidate: UnknownRecord) {
  return `${String(candidate.market ?? "KRX")}-${String(candidate.code ?? "")}`;
}

function currentResultCandidates(result: ScannerResponse | null | undefined) {
  if (!result) return [];
  const raw = result as unknown as UnknownRecord;
  return [
    ...(Array.isArray(raw.candidates) ? raw.candidates : []),
    ...(Array.isArray(raw.more_candidates) ? raw.more_candidates : []),
  ];
}

function resultDate(result: ScannerResponse | null | undefined) {
  if (!result) return null;
  const raw = result as unknown as UnknownRecord;
  return typeof raw.requested_as_of === "string" ? raw.requested_as_of : latestScannerDataDate(result);
}

function percentOf(job: BacktestJob<ScannerResponse> | null) {
  const details = asRecord(job?.progress?.details);
  const raw = Number(details.overall_percent ?? job?.progress?.percent ?? 0);
  if (!Number.isFinite(raw)) return 0;
  return Math.max(0, Math.min(100, raw));
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

async function pollRunner(jobId: string, scope: MarketScope, token: number): Promise<void> {
  while (token === runToken) {
    try {
      const latest = await fetchBacktestJob<ScannerResponse>(jobId);
      if (token !== runToken) return;
      setRunnerState({ job: latest });

      if (latest.status === "completed" && latest.result) {
        const candidates = currentResultCandidates(latest.result);
        const first = candidates.length ? asRecord(candidates[0]) : null;
        commitScannerSession({
          scope,
          result: latest.result,
          completedAt: Date.now(),
          scrollY: 0,
          showMore: false,
          expandedEvidenceIds: [],
          selectedCandidateKey: first ? candidateKey(first) : null,
        });
        setRunnerState({ error: null, freshnessFailure: null });
        return;
      }

      if (latest.status === "failed") {
        const details = asRecord(latest.progress?.details);
        const failureValue = details.freshness_failure;
        const freshnessFailure = failureValue && typeof failureValue === "object" && !Array.isArray(failureValue)
          ? failureValue as ScannerFreshnessResponse
          : null;
        setRunnerState({
          freshnessFailure,
          error: freshnessFailure ? null : (latest.error || "종목 찾기 중 오류가 발생했습니다."),
        });
        return;
      }

      if (latest.status === "cancelled") return;
      await sleep(700);
    } catch (error) {
      if (token !== runToken) return;
      setRunnerState({ error: error instanceof Error ? error.message : "종목 찾기 상태를 확인하지 못했습니다." });
      return;
    }
  }
}

async function startRunner(
  scope: MarketScope,
  currentResult: ScannerResponse | null,
  options: { forceRefresh?: boolean; pinnedAsOfDate?: string | null } = {},
) {
  const status = runnerState.job?.status;
  if (status === "queued" || status === "running") return;

  const token = ++runToken;
  setRunnerState({
    scope,
    job: null,
    error: null,
    freshnessFailure: null,
    startedAt: Date.now(),
  });

  try {
    const pinned = options.pinnedAsOfDate ?? null;
    const request = {
      market_scope: scope,
      as_of_date: pinned ?? undefined,
      known_data_date: pinned ? undefined : (currentResult?.requested_as_of ?? latestScannerDataDate(currentResult)),
      candidate_limit: 5,
      force_refresh: Boolean(options.forceRefresh),
      allow_large_sync: false,
    } as Parameters<typeof createScannerJob>[0] & { known_data_date?: string | null };
    const created = await createScannerJob(request);
    if (token !== runToken) return;
    setRunnerState({ job: created });
    void pollRunner(created.job_id, scope, token);
  } catch (error) {
    if (token !== runToken) return;
    setRunnerState({ error: error instanceof Error ? error.message : "종목 찾기를 시작하지 못했습니다." });
  }
}

async function cancelRunner() {
  const current = runnerState.job;
  if (!current?.job_id || !(current.status === "queued" || current.status === "running")) return;
  ++runToken;
  try {
    const cancelled = await cancelBacktestJob<ScannerResponse>(current.job_id);
    setRunnerState({ job: cancelled });
  } catch (error) {
    setRunnerState({ error: error instanceof Error ? error.message : "종목 찾기 작업을 중지하지 못했습니다." });
  }
}

function setScope(scope: MarketScope) {
  const status = runnerState.job?.status;
  if (status === "queued" || status === "running") return;
  setRunnerState({ scope, error: null, freshnessFailure: null });
}

function formatDate(value: string | null | undefined) {
  return value ? value.replace(/-/g, ".") : "-";
}

export default function EmbeddedScanner() {
  const session = useScannerSession();
  const runner = useSyncExternalStore(subscribeRunner, getRunnerState, getRunnerState);
  const busy = runner.job?.status === "queued" || runner.job?.status === "running";
  const currentResult = session?.result ?? null;
  const resultForScope = session?.scope === runner.scope ? currentResult : null;
  const currentCandidates = currentResultCandidates(currentResult);
  const progress = percentOf(runner.job);
  const details = asRecord(runner.job?.progress?.details);
  const progressView = scannerProgressView(runner.job?.stage, details);
  const currentStage = [...progressView.prepRows, ...progressView.analysisRows].find((item) => item.status === "active");

  useEffect(() => {
    if (busy || !session?.scope || session.scope === runner.scope) return;
    setScope(session.scope);
  }, [busy, runner.scope, session?.scope]);

  return (
    <section className="tracking-source tracking-embedded-scanner">
      <div className="tracking-section-head">
        <div>
          <span>종목 찾기</span>
          <h2>이 화면에서 바로 추천 후보 찾기</h2>
        </div>
        <small>기존 종목 찾기와 같은 Scanner · 같은 결과 공유</small>
      </div>

      <div className="tracking-scanner-controls">
        <div className="tracking-scanner-markets" role="group" aria-label="종목 찾기 시장 선택">
          {(["ALL", "KOSPI", "KOSDAQ"] as MarketScope[]).map((value) => (
            <button
              key={value}
              type="button"
              className={runner.scope === value ? "active" : ""}
              disabled={busy}
              onClick={() => setScope(value)}
            >
              {value === "ALL" ? "전체" : value}
            </button>
          ))}
        </div>
        <div className="tracking-scanner-actions">
          <button
            type="button"
            className="tracking-scanner-run"
            disabled={busy}
            onClick={() => void startRunner(runner.scope, resultForScope, { forceRefresh: Boolean(resultForScope) })}
          >
            {busy ? "후보 찾는 중…" : resultForScope ? "후보 다시 찾기" : "종목 찾기 실행"}
          </button>
          {busy && <button type="button" className="tracking-scanner-cancel" onClick={() => void cancelRunner()}>중지</button>}
        </div>
      </div>

      {busy && (
        <div className="tracking-scanner-progress" aria-live="polite">
          <div className="tracking-scanner-progress-head">
            <div>
              <strong>{currentStage?.label ?? "종목 찾기 진행 중"}</strong>
              <span>{progress.toFixed(0)}%</span>
            </div>
            <div className="tracking-scanner-progress-bar"><i style={{ width: `${progress}%` }} /></div>
          </div>
          <div className="tracking-scanner-stage-line">
            {[...progressView.prepRows, ...progressView.analysisRows].map((item) => (
              <span key={item.id} className={item.status}>
                <b>{progressStatusMark(item.status)}</b>{item.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {runner.error && <div className="tracking-scanner-error">{runner.error}</div>}

      {runner.freshnessFailure && (
        <div className="tracking-scanner-error">
          <strong>{runner.freshnessFailure.message || "최신 확정 시세를 확인하지 못했습니다."}</strong>
          {runner.freshnessFailure.available_data_date && <span>사용 가능한 확정 일봉 · {formatDate(runner.freshnessFailure.available_data_date)}</span>}
          {runner.freshnessFailure.fallback_allowed && runner.freshnessFailure.available_data_date && (
            <button
              type="button"
              onClick={() => void startRunner(runner.scope, resultForScope, { forceRefresh: Boolean(resultForScope), pinnedAsOfDate: runner.freshnessFailure?.available_data_date ?? null })}
            >
              {formatDate(runner.freshnessFailure.available_data_date)} 기준으로 찾기
            </button>
          )}
        </div>
      )}

      {!busy && currentResult && (
        <div className="tracking-scanner-result-line">
          <strong>최근 결과 · {currentCandidates.length}종목</strong>
          <span>기준일 {formatDate(resultDate(currentResult))} · 아래 추천 후보에서 바로 추적할 수 있습니다.</span>
        </div>
      )}

      {!busy && !currentResult && !runner.error && !runner.freshnessFailure && (
        <div className="tracking-scanner-empty">
          <strong>아직 종목 찾기 결과가 없습니다.</strong>
          <span>시장 전체 또는 KOSPI·KOSDAQ을 선택하고 이 화면에서 바로 실행하세요.</span>
        </div>
      )}
    </section>
  );
}
