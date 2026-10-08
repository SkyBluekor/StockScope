import { useEffect, useMemo, useState } from "react";

import type {
  BacktestJob,
  ScannerResponse,
  ScannerCandidate,
} from "../services/api";
import type { JevMonitorItem } from "../services/jevApi";
import { scannerAiReviewStatus } from "./scannerAiReviewStatus";

type Props = {
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  job: BacktestJob<ScannerResponse> | null;
  result: ScannerResponse | null;
  selectedCandidate?: ScannerCandidate | null;
  review?: JevMonitorItem | null;
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
  selectedCandidate,
  review,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const busy = job?.status === "queued" || job?.status === "running";
  const stage = String(job?.stage || "");
  const progress = result?.ai_review_progress ?? null;
  const focus = selectedCandidate ?? result?.candidates[0] ?? null;
  const aiTruth = result && focus
    ? scannerAiReviewStatus({ candidate: focus, result, enabled, available, featureStatus, review })
    : null;

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
    const basicResultState: StepState = hasResult ? "done" : "waiting";
    const semanticState: StepState = hasResult && progress ? "done" : "waiting";

    // The aggregate scanner step must not reinterpret local work or zero
    // provider_required as a completed Jev call.
    const aiState: StepState =
      aiTruth?.state === "COMPLETE" || aiTruth?.state === "NEEDS_REVIEW" || aiTruth?.state === "ABSTAIN"
        ? "done"
        : aiTruth?.state === "FEATURE_PENDING" || aiTruth?.state === "INPUT_MISSING" || aiTruth?.state === "FAILED"
          ? "blocked" : "waiting";
    const aiDetail = aiTruth?.label ?? "AI 검토 미실행";

    let semanticDetail = "대기";
    if (hasResult && progress) {
      if (progress.total_candidates === 0) {
        semanticDetail = "확인 대상 없음";
      } else if (progress.not_ready > 0) {
        semanticDetail = String(progress.local_checked)
          + "개 확인 · "
          + String(progress.not_ready)
          + "개 준비 필요";
      } else {
        semanticDetail = String(progress.local_checked)
          + "/"
          + String(progress.total_candidates)
          + " 확인";
      }
    }

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
        id: "result",
        label: "기본 결과 표시",
        detail: basicResultState === "done" ? "완료" : "대기",
        state: basicResultState,
      },
      {
        id: "semantic",
        label: "의미 관계 확인",
        detail: semanticDetail,
        state: semanticState,
      },
      {
        id: "ai",
        label: "AI 보조 검토",
        detail: aiDetail,
        state: aiState,
      },
    ];
  }, [available, busy, progress, result, stage, aiTruth?.state, aiTruth?.label]);

  if (!enabled || (!job && !result)) return null;

  const current = steps.find((step) => step.state === "active")
    ?? steps.find((step) => step.state === "waiting")
    ?? steps.find((step) => step.state === "blocked")
    ?? steps[steps.length - 1];

  const summary = busy
    ? "기본 분석을 진행하고 있어요. 실제 AI 완료 여부는 별도로 확인해요."
    : result ? (aiTruth?.detail ?? "기본 분석은 완료됐지만 AI 검토 결과는 확인되지 않았어요.")
      : current.detail;

  return (
    <section className="ai-review-flow" aria-live="polite">
      <header className="ai-review-flow-head">
        <div>
          <span className="ai-review-flow-kicker">AI 보조 검토 ON</span>
          <strong>{busy ? "기본 분석 진행 중 · AI 완료 전" : "기본 분석 완료 · " + (aiTruth?.label ?? "AI 검토 미완료")}</strong>
          <p>{summary}</p>
        </div>
        <div className="ai-review-flow-actions">
          <span className={"ai-review-feature-chip " + (available ? "ready" : "pending")}>
            {aiTruth?.label ?? (available ? "AI 상태 확인 중" : "AI 검토 기능 준비 중")}
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
                  {step.state === "done" ? "✓" : step.state === "blocked" ? "Ⅱ" : ""}
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
