import { useEffect, useMemo, useState } from "react";

import type {
  BacktestJob,
  ScannerResponse,
} from "../services/api";

type Props = {
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  job: BacktestJob<ScannerResponse> | null;
  result: ScannerResponse | null;
};

type StepState = "done" | "active" | "waiting" | "blocked";

type Step = {
  id: string;
  label: string;
  detail: string;
  state: StepState;
};

function isPreparationStage(stage: string) {
  return stage === "queued"
    || stage.startsWith("scanner_prepare")
    || stage === "scanner_history_prepare"
    || stage === "scanner_plan"
    || stage === "scanner_data_prepare"
    || stage === "scanner_fast_budget"
    || stage === "scanner_universe";
}

function isStrategyStage(stage: string) {
  return stage === "scanner_quick_filter"
    || stage === "scanner_deep_analysis"
    || stage === "scanner_finalize"
    || stage === "scanner_historical_evidence"
    || stage === "scanner_priority_rank";
}

export default function AiReviewProgress({
  enabled,
  available,
  featureStatus,
  job,
  result,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const busy = job?.status === "queued" || job?.status === "running";
  const stage = String(job?.stage || "");
  const progress = result?.ai_review_progress ?? null;

  useEffect(() => {
    if (busy) setExpanded(true);
  }, [busy]);

  useEffect(() => {
    if (result?.generated_at) setExpanded(true);
  }, [result?.generated_at]);

  const steps = useMemo<Step[]>(() => {
    const hasResult = Boolean(result) && !busy;
    const preparation = isPreparationStage(stage);
    const strategy = isStrategyStage(stage);

    const dataState: StepState = hasResult || strategy
      ? "done"
      : busy && preparation
        ? "active"
        : "waiting";
    const strategyState: StepState = hasResult
      ? "done"
      : busy && strategy
        ? "active"
        : "waiting";
    const semanticState: StepState = hasResult && progress ? "done" : "waiting";

    let aiState: StepState = "waiting";
    let aiDetail = "기본 분석 후 필요한 후보만 확인";
    if (hasResult && progress) {
      if (!available) {
        aiState = "blocked";
        aiDetail = "기능 검증 대기";
      } else if (progress.provider_required === 0) {
        aiState = "done";
        aiDetail = "별도 AI 호출 불필요";
      } else if (progress.provider_completed >= progress.provider_required) {
        aiState = "done";
        aiDetail = String(progress.provider_completed) + "/" + String(progress.provider_required) + " 확인";
      } else {
        aiState = "waiting";
        aiDetail = String(progress.provider_required) + "개 후보 추가 확인 준비";
      }
    }

    const completeState: StepState = hasResult
      && progress
      && available
      && (
        progress.provider_required === 0
        || progress.provider_completed >= progress.provider_required
      )
      ? "done"
      : "waiting";

    return [
      {
        id: "data",
        label: "데이터 확인",
        detail: dataState === "done" ? "완료" : dataState === "active" ? "확정 데이터 확인 중" : "대기",
        state: dataState,
      },
      {
        id: "strategy",
        label: "전략 판정",
        detail: strategyState === "done" ? "완료" : strategyState === "active" ? "후보 조건 계산 중" : "대기",
        state: strategyState,
      },
      {
        id: "semantic",
        label: "의미 관계 확인",
        detail: semanticState === "done"
          ? String(progress?.local_checked ?? 0) + "/" + String(progress?.total_candidates ?? 0) + " 확인"
          : "대기",
        state: semanticState,
      },
      {
        id: "ai",
        label: "AI 보조 검토",
        detail: aiDetail,
        state: aiState,
      },
      {
        id: "complete",
        label: "결과 정리",
        detail: completeState === "done" ? "완료" : "대기",
        state: completeState,
      },
    ];
  }, [available, busy, progress, result, stage]);

  if (!enabled || (!job && !result)) return null;

  const current = steps.find((step) => step.state === "active")
    ?? steps.find((step) => step.state === "blocked")
    ?? steps.find((step) => step.state === "waiting")
    ?? steps[steps.length - 1];

  let summary = current.detail;
  if (result && progress) {
    if (available) {
      summary = progress.provider_required > 0
        ? "의미 관계 " + String(progress.local_checked) + "개 확인 · AI 추가 확인 후보 " + String(progress.provider_required) + "개"
        : "의미 관계 " + String(progress.local_checked) + "개 확인 · 별도 AI 호출이 필요한 후보 없음";
    } else {
      summary = "의미 관계 " + String(progress.local_checked) + "개 확인 · 실제 AI 검토는 기능 검증 완료 후 적용";
    }
  } else if (result && !progress) {
    summary = "이전 분석 결과입니다. 새 분석부터 AI 의미 관계 진행 상태를 함께 표시합니다.";
  }

  return (
    <section className="ai-review-flow" aria-live="polite">
      <header className="ai-review-flow-head">
        <div>
          <span className="ai-review-flow-kicker">AI 보조 검토 ON</span>
          <strong>{busy ? "분석 엔진이 후보를 단계별로 확인하고 있습니다." : "AI 보조 검토 경로"}</strong>
          <p>{summary}</p>
        </div>
        <div className="ai-review-flow-actions">
          <span className={"ai-review-feature-chip " + (available ? "ready" : "pending")}>
            {available ? "AI 사용 가능" : featureStatus === "DISABLED_VALIDATION_PENDING" ? "AI 검증 대기" : "AI 상태 확인 중"}
          </span>
          {!busy && result && (
            <button type="button" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "과정 접기" : "과정 보기"}
            </button>
          )}
        </div>
      </header>

      {expanded && (
        <div className="ai-review-flow-rail">
          {steps.map((step, index) => (
            <div className={"ai-review-flow-step " + step.state} key={step.id}>
              <div className="ai-review-flow-track">
                <span className="ai-review-flow-dot" aria-hidden="true">
                  {step.state === "done" ? "✓" : step.state === "blocked" ? "!" : ""}
                </span>
                {index < steps.length - 1 && <span className="ai-review-flow-line" aria-hidden="true" />}
              </div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
