import { useEffect, useMemo, useRef, useState } from "react";
import EntryRiskGuideCard from "./EntryRiskGuideCard";
import {
  cancelBacktestJob,
  createExitPolicyValidationJob,
  createExpandedExitPolicyValidationJob,
  createExpandedSamplePreparationJob,
  createMultiStrategyBacktestJob,
  fetchBacktestJob,
  fetchExitPolicyProductionStatus,
  fetchExitPolicyValidationReport,
  fetchExitPolicyValidationHistory,
  fetchLatestExitPolicyValidationAudit,
  fetchLatestExitPolicyValidationReport,
  prepareScannerLatestData,
  planExpandedExitPolicyValidation,
  runExitPolicyValidationAudit,
  searchStocks,
  type BacktestJob,
  type ExitPolicyResearchAuditReport,
  type ExpandedSamplePlan,
  type ExpandedSamplePreparationResult,
  type ExitPolicyValidationPolicy,
  type ExitPolicyValidationReport,
  type ExitPolicyValidationStrategy,
  type ExitPolicyValidationHistoryItem,
  type MultiStrategyBacktestResponse,
  type MultiStrategyConditionDetail,
  type MultiStrategyRow,
  type ProductionExitPolicyStatus,
  type StockSearchItem,
} from "../services/api";

type Market = "KOSPI" | "KOSDAQ";
type ResearchSection = "SUMMARY" | "RUN" | "RESULTS" | "RELIABILITY" | "EXPANDED" | "HISTORY";
type ResearchReportSource = "CURRENT_RUN" | "PREVIOUS_RUN" | null;

type Props = {
  code: string;
  market: Market;
  stockName?: string;
  onSelectStock: (item: StockSearchItem) => void;
};

const strategyGuides = [
  { professional: "추세 추종", easy: "상승 흐름 따라가기" },
  { professional: "눌림목", easy: "쉬어간 뒤 다시 오를 때 노리기" },
  { professional: "돌파", easy: "막힌 가격 돌파 노리기" },
  { professional: "지지 반등", easy: "지지 가격에서 반등 노리기" },
  { professional: "과매도 반등", easy: "과도한 하락 뒤 반등 노리기" },
  { professional: "박스권 매매", easy: "일정 가격 범위에서 노리기" },
  { professional: "모멘텀 지속", easy: "강한 상승 이어가기" },
  { professional: "변동성 수축", easy: "큰 움직임 전 조용한 구간 찾기" },
  { professional: "20일선 반등", easy: "20일선 반등 노리기" },
  { professional: "추세 회복", easy: "상승 흐름 회복 노리기" },
];

const regimeLabel: Record<string, string> = {
  TREND_UP: "상승장",
  RANGE: "횡보장",
  TREND_DOWN: "하락장",
  HIGH_VOLATILITY: "고변동성",
  PANIC: "패닉",
  UNKNOWN: "판단 보류",
};

const holdingOptions = [
  { days: 5, label: "5일", description: "아주 짧은 움직임만 봅니다." },
  { days: 10, label: "10일", description: "단기 스윙 기준입니다." },
  { days: 20, label: "20일 · 추천", description: "약 한 달 동안 전략이 이어지는지 확인하는 기본값입니다." },
  { days: 40, label: "40일", description: "중기 움직임까지 기다립니다." },
];

function isoDate(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function defaultStartDate() {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 3);
  return isoDate(date);
}

function formatPct(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(value);
}

function formatCompactDate(value: string) {
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function userFacingResearchText(value: string | null | undefined) {
  if (!value) return value ?? "";
  const replacements: Array<[string, string]> = [
    ["Production Exit 정책", "현재 실제 매도 기준"],
    ["기존 Target1 전량 종료 정책", "기존 1차 목표가 전량 매도 기준"],
    ["기존 Target1 전량 종료", "기존 1차 목표가 전량 매도"],
    ["Target1 전량 종료 정책", "1차 목표가 전량 매도 기준"],
    ["Target1 전량 종료", "1차 목표가에서 전량 매도"],
    ["기존 Target1 정책", "기존 1차 목표가 기준"],
    ["기존 Target1 종료", "기존 1차 목표가 매도"],
    ["Target2 이후 최근 확정 Swing Low 추적", "2차 목표가 도달 후 최근 확정 저점 기준 수익 보호"],
    ["Target2 이후 MA20 추적", "2차 목표가 도달 후 20일 이동평균선 기준 수익 보호"],
    ["Target2 이후", "2차 목표가 도달 후"],
    ["Target2", "2차 목표가"],
    ["Swing Low", "최근 확정 저점"],
    ["MA20", "20일 이동평균선"],
    ["Exit 정책", "매도 기준"],
    ["Exit 방식", "수익 실현 방식"],
    ["Exit 후보", "새 매도 기준 후보"],
    ["Exit 계산", "매도 기준 비교 계산"],
    ["Production 정책", "현재 실제 적용 기준"],
    ["로컬 Market Store", "저장된 시세 데이터"],
    ["Market Store", "저장된 시세 데이터"],
    ["로컬 데이터", "저장된 시세 데이터"],
    ["로컬 종목", "저장 데이터가 충분한 종목"],
    ["로컬 커버리지", "데이터 보유율"],
    ["Risk Engine", "위험 관리 기준"],
    ["Profit Factor", "이익/손실 비율(PF)"],
    ["Giveback", "수익 반납폭"],
    ["Trailing horizon", "수익 보호 추적 기간"],
    ["Trailing", "수익 보호 추적"],
    ["Hard Max Hold", "기존 최대 보유기간"],
    ["Max Hold", "최대 보유기간"],
    ["trade-off", "상충 관계"],
    ["fallback으로 유지", "기존 기준으로 유지"],
    ["Pareto 우위 정책", "다른 핵심 지표를 악화시키지 않으면서 개선된 유일한 기준"],
    ["충분표본", "충분한 표본"],
    ["열위가 없습니다", "불리하지 않았습니다"],
    ["자동 확정하지 않습니다", "확정하지 않았습니다"],
    ["체크포인트", "중간 저장 결과"],
    ["네트워크 요청", "추가 시세 요청"],
    ["백테스트", "과거 성과 검증"],
    ["정책", "기준"],
  ];
  return replacements.reduce((text, [from, to]) => text.split(from).join(to), value);
}

function historicalEvidenceHint(row: MultiStrategyRow) {
  const status = row.historical_fit.status;
  if (status === "INSUFFICIENT") return "현재 비교 기준에서는 표본이 부족합니다.";
  if (status === "WEAK") return "표본은 있지만 평균 결과나 손실 구조가 충분히 안정적이지 않았습니다.";
  if (status === "FAIR") return "일부 긍정 근거가 있지만 결과가 혼재되어 있습니다.";
  if (status === "GOOD") return "현재 비교 기준에서 과거 근거가 상대적으로 양호했습니다.";
  return "표본 수와 평균 결과, 손익 구조, 최대 낙폭(MDD)을 함께 확인합니다.";
}

function exitLabel(value: string) {
  const labels: Record<string, string> = {
    STOP: "손절",
    STOP_GAP: "갭 손절",
    STOP_SAME_DAY_PRIORITY: "손절 우선",
    TARGET_1: "1차 목표가",
    TARGET_1_GAP: "갭으로 1차 목표가 도달",
    TIME_EXIT: "보유기간 종료",
    END_OF_DATA: "기간 종료",
  };
  return labels[value] ?? value;
}

function DetailToggleText({ closed = "펼치기 ▼", open = "숨기기 ▲" }: { closed?: string; open?: string }) {
  return (
    <b className="details-toggle-label" aria-hidden="true">
      <span className="when-closed">{closed}</span>
      <span className="when-open">{open}</span>
    </b>
  );
}

function ConditionMetricCard({ condition }: { condition: MultiStrategyConditionDetail }) {
  const status = condition.status ?? "UNKNOWN";
  const statusLabel = status === "PASS" ? "충족" : status === "FAIL" ? "아직 부족" : "확인 필요";
  return (
    <article className={`strategy-condition-metric status-${status.toLowerCase()}`}>
      <div className="strategy-condition-head">
        <strong>{condition.label}</strong>
        <b>{status === "PASS" ? "✓" : status === "FAIL" ? "✕" : "○"} {statusLabel}</b>
      </div>
      <p>{condition.detail}</p>
      {(condition.current_value || condition.required_value) && (
        <div className="strategy-condition-values">
          {condition.current_value && <span><small>현재</small><strong>{condition.current_value}</strong></span>}
          {condition.required_value && <span><small>필요</small><strong>{condition.required_value}</strong></span>}
        </div>
      )}
    </article>
  );
}

function StrategyConditionSummary({ row, action }: { row: MultiStrategyRow; action: string }) {
  const rawPassedDetails = row.current.reason_details ?? [];
  const rawMissingDetails = row.current.unmet_details ?? [];
  const total = Math.max(0, row.current.total ?? 0);
  const passed = Math.max(0, Math.min(total, row.current.passed ?? 0));
  const missing = Math.max(0, row.current.missing ?? (total - passed));
  const passedDetails = rawPassedDetails.slice(0, passed);
  const missingDetails = rawMissingDetails.slice(0, missing);
  const primaryMissing = missingDetails.slice(0, 3);
  const remainingMissing = missingDetails.slice(3);

  return (
    <section className="strategy-condition-summary">
      <div className="strategy-condition-summary-head">
        <div>
          <span>{action === "ENTRY_CANDIDATE" ? "현재 진입 준비" : "왜 아직 진입하지 않나요?"}</span>
          <strong>전체 {total}개 · 충족 {passed}개 · 부족 {missing}개</strong>
        </div>
        <b>{passed}/{total}</b>
      </div>

      {missing > 0 && (
        <>
          <div className="strategy-condition-section-title">
            <strong>가장 중요한 부족 조건</strong>
            <span>{missing > 3 ? "우선 3개만 보여드립니다." : "현재 부족한 조건입니다."}</span>
          </div>
          <div className="strategy-condition-grid">
            {primaryMissing.map((condition) => (
              <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
            ))}
          </div>
          {remainingMissing.length > 0 && (
            <details className="strategy-condition-more">
              <summary>
                <span>나머지 부족 조건 {remainingMissing.length}개</span>
                <DetailToggleText closed="보기 ▼" open="숨기기 ▲" />
              </summary>
              <div className="strategy-condition-grid">
                {remainingMissing.map((condition) => (
                  <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
                ))}
              </div>
            </details>
          )}
          {missingDetails.length < missing && (
            <p className="strategy-condition-empty">
              부족 조건은 총 {missing}개지만 상세 설명은 {missingDetails.length}개만 제공됐습니다. 전문 상세에서 원본 조건을 확인할 수 있습니다.
            </p>
          )}
        </>
      )}

      {passed > 0 && (
        <details className="strategy-condition-more passed">
          <summary>
            <span>이미 충족한 조건 {passed}개</span>
            <DetailToggleText closed="보기 ▼" open="숨기기 ▲" />
          </summary>
          {passedDetails.length > 0 ? (
            <>
              <div className="strategy-condition-grid">
                {passedDetails.map((condition) => (
                  <ConditionMetricCard key={`${condition.condition_id ?? condition.raw}-${condition.status}`} condition={condition} />
                ))}
              </div>
              {passedDetails.length < passed && (
                <p className="strategy-condition-empty">충족 조건은 총 {passed}개지만 상세 설명은 {passedDetails.length}개만 제공됐습니다.</p>
              )}
            </>
          ) : (
            <p className="strategy-condition-empty">충족 개수는 계산됐지만 상세 설명 데이터가 없습니다.</p>
          )}
        </details>
      )}

      {row.current.condition_consistency?.ok === false && (
        <div className="strategy-condition-consistency-error" role="alert">
          <strong>조건 집계가 서로 맞지 않습니다.</strong>
          <span>이 결과는 진입 판단에 사용하지 말고 최신 데이터로 다시 분석하세요.</span>
        </div>
      )}

      {total === 0 && (
        <p className="strategy-condition-empty">현재 전략 조건을 세부 항목으로 나눠 표시할 수 없습니다. 다음 분석에서 다시 계산합니다.</p>
      )}
    </section>
  );
}

function strategyDisplayLabel(strategy: string) {
  const labels: Record<string, string> = {
    TREND_FOLLOWING: "추세 추종",
    PULLBACK: "눌림목",
    BREAKOUT: "돌파",
    SUPPORT_BOUNCE: "지지 반등",
    OVERSOLD_BOUNCE: "과매도 반등",
    RANGE_TRADING: "박스권 매매",
    MOMENTUM_CONTINUATION: "모멘텀 지속",
    VOLATILITY_SQUEEZE: "변동성 수축",
    MA20_REBOUND: "20일선 반등",
    TREND_RECOVERY: "추세 회복",
  };
  return labels[strategy.trim().toUpperCase()] ?? strategy;
}

function exitPolicyStatusLabel(status: string) {
  const labels: Record<string, string> = {
    SELECTED: "새 기준 후보",
    BASELINE_BETTER: "기존 기준 유지",
    UNRESOLVED: "판단 보류",
    INSUFFICIENT_SAMPLE: "표본 부족",
  };
  return labels[status] ?? status;
}

function exitPolicyLabel(policyId: string | null | undefined) {
  const labels: Record<string, string> = {
    TARGET1_FULL_EXIT: "1차 목표가에서 전량 매도",
    TARGET1_FULL_EXIT_V1: "1차 목표가에서 전량 매도",
    ATR_TRAIL_1_5: "ATR 1.5배 기준 수익 보호",
    ATR_TRAIL_2_0: "ATR 2.0배 기준 수익 보호",
    ATR_TRAIL_2_5: "ATR 2.5배 기준 수익 보호",
    MA20_TRAIL: "20일 이동평균선 기준 수익 보호",
    SWING_LOW_TRAIL: "최근 확정 저점 기준 수익 보호",
    CONFIRMED_SWING_LOW_TRAIL: "최근 확정 저점 기준 수익 보호",
  };
  return policyId ? labels[policyId] ?? "매도 기준 확인 필요" : "-";
}

function policyMetrics(policy: ExitPolicyValidationPolicy | null | undefined) {
  return policy?.aggregate_metrics ?? null;
}

function metricChangeText(
  baselineValue: number | null | undefined,
  candidateValue: number | null | undefined,
  options: { digits?: number; unit?: string; higherIsBetter?: boolean; neutralOnly?: boolean } = {},
) {
  if (baselineValue == null || candidateValue == null || !Number.isFinite(baselineValue) || !Number.isFinite(candidateValue)) return "-";
  const digits = options.digits ?? 2;
  const unit = options.unit ?? "";
  const diff = candidateValue - baselineValue;
  const magnitude = `${diff > 0 ? "+" : ""}${diff.toFixed(digits)}${unit}`;
  if (options.neutralOnly) return magnitude;
  if (Math.abs(diff) < 10 ** -(digits + 1)) return `변화 거의 없음`;
  const improved = options.higherIsBetter === false ? diff < 0 : diff > 0;
  return `${magnitude} · ${improved ? "개선" : "악화"}`;
}

function finiteValues(values: Array<number | null | undefined>) {
  return values.filter((value): value is number => value != null && Number.isFinite(value));
}

function formatPctRange(values: Array<number | null | undefined>) {
  const rows = finiteValues(values);
  if (rows.length === 0) return "-";
  const min = Math.min(...rows);
  const max = Math.max(...rows);
  if (Math.abs(max - min) < 0.005) return formatPct(min);
  return `${formatPct(min)} ~ ${formatPct(max)}`;
}

function formatNumberRange(values: Array<number | null | undefined>, digits = 2, unit = "") {
  const rows = finiteValues(values);
  if (rows.length === 0) return "-";
  const min = Math.min(...rows);
  const max = Math.max(...rows);
  const fmt = (value: number) => `${formatNumber(value, digits)}${unit}`;
  if (Math.abs(max - min) < 10 ** -(digits + 1)) return fmt(min);
  return `${fmt(min)} ~ ${fmt(max)}`;
}

function compareAlternativeMetric(
  baselineValue: number | null | undefined,
  alternativeValues: Array<number | null | undefined>,
  higherIsBetter: boolean,
  positiveText: string,
  negativeText: string,
  mixedText: string,
) {
  if (typeof baselineValue !== "number" || !Number.isFinite(baselineValue)) return "비교할 현재 기준 수치가 없습니다.";
  const values = finiteValues(alternativeValues);
  if (values.length === 0) return "비교 가능한 새 방식 수치가 없습니다.";
  const epsilon = 0.005;
  const deltas = values.map((value) => (higherIsBetter ? value - baselineValue : baselineValue - value));
  if (deltas.every((delta) => delta > epsilon)) return positiveText;
  if (deltas.every((delta) => delta < -epsilon)) return negativeText;
  if (deltas.every((delta) => Math.abs(delta) <= epsilon)) return "현재 기준과 거의 같은 수준입니다.";
  return mixedText;
}

function validationComparisonSnapshot(row: ExitPolicyValidationStrategy) {
  const baseline = row.baseline ?? null;
  const baselineMetrics = policyMetrics(baseline);
  const alternatives = row.policies.filter((policy) => policy.policy_id !== baseline?.policy_id);
  const selectedPolicy = row.status === "SELECTED"
    ? row.policies.find((policy) => policy.policy_id === row.selected_policy_id) ?? null
    : null;
  const comparisonPolicies = selectedPolicy ? [selectedPolicy] : alternatives;
  const currentNet = baselineMetrics ? formatPct(baselineMetrics.average_net_return_pct) : "-";
  const currentDrawdown = baselineMetrics ? formatPct(baselineMetrics.median_max_drawdown_pct) : "-";
  const alternativeNet = comparisonPolicies.length > 0
    ? formatPctRange(comparisonPolicies.map((policy) => policy.aggregate_metrics.average_net_return_pct))
    : "-";
  const alternativeDrawdown = comparisonPolicies.length > 0
    ? formatPctRange(comparisonPolicies.map((policy) => policy.aggregate_metrics.median_max_drawdown_pct))
    : "-";
  const compared = selectedPolicy
    ? exitPolicyLabel(selectedPolicy.policy_id)
    : alternatives.length > 0 ? `${alternatives.length}개 새 방식 비교` : "비교 가능한 새 방식 없음";
  const subject = selectedPolicy ? "새 기준 후보" : "새 방식";
  const netInsight = compareAlternativeMetric(
    baselineMetrics?.average_net_return_pct,
    comparisonPolicies.map((policy) => policy.aggregate_metrics.average_net_return_pct),
    true,
    `${subject}의 평균 순수익이 현재 기준보다 높습니다.`,
    `${subject}의 평균 순수익이 현재 기준보다 낮습니다.`,
    "평균 순수익은 새 방식마다 결과가 엇갈립니다.",
  );
  const drawdownInsight = compareAlternativeMetric(
    baselineMetrics?.median_max_drawdown_pct,
    comparisonPolicies.map((policy) => policy.aggregate_metrics.median_max_drawdown_pct),
    true,
    `${subject}의 최대 낙폭이 현재 기준보다 작습니다.`,
    `${subject}의 최대 낙폭이 현재 기준보다 큽니다.`,
    "최대 낙폭은 새 방식마다 결과가 엇갈립니다.",
  );
  return { currentNet, currentDrawdown, alternativeNet, alternativeDrawdown, compared, alternatives, netInsight, drawdownInsight };
}

function validationConclusionHeadline(report: ExitPolicyValidationReport) {
  if (report.status !== "COMPLETED") return "추가 과거 시세 데이터가 필요합니다.";
  const selected = report.summary?.selected ?? 0;
  if (selected === 0) return "기존 1차 목표가 전량 매도 기준보다 명확하게 우수한 새 기준은 확인되지 않았습니다.";
  return `${selected}개 전략에서 기존 1차 목표가 전량 매도 기준보다 개선된 새 후보가 확인되었습니다. 실제 적용 여부는 현재 적용 기준과 별도로 확인합니다.`;
}

type LatestReanalysisSummary = {
  status: "UP_TO_DATE" | "UPDATED_CHANGED" | "UPDATED_SAME";
  previousAsOf: string;
  latestAsOf: string;
  changes: Array<{ label: string; before: string; after: string }>;
};

function formatWon(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function resultStrategyRow(result: MultiStrategyBacktestResponse | null | undefined) {
  if (!result) return null;
  if (result.recommendation.strategy) {
    return result.strategies.find((row) => row.strategy === result.recommendation.strategy) ?? result.strategies[0] ?? null;
  }
  return result.strategies[0] ?? null;
}

function buildLatestReanalysisChanges(
  before: MultiStrategyBacktestResponse,
  after: MultiStrategyBacktestResponse,
) {
  const changes: Array<{ label: string; before: string; after: string }> = [];
  const beforeRow = resultStrategyRow(before);
  const afterRow = resultStrategyRow(after);
  const beforeGuide = before.recommendation.entry_risk_guide;
  const afterGuide = after.recommendation.entry_risk_guide;
  const pairs: Array<[string, string, string]> = [
    ["현재 판단", before.recommendation.action_label, after.recommendation.action_label],
    ["가장 가까운 전략", before.recommendation.strategy_easy_name ?? before.recommendation.strategy_label ?? "-", after.recommendation.strategy_easy_name ?? after.recommendation.strategy_label ?? "-"],
    ["충족 조건", beforeRow ? `${beforeRow.current.passed}/${beforeRow.current.total}` : "-", afterRow ? `${afterRow.current.passed}/${afterRow.current.total}` : "-"],
    ["손절 참고가", formatWon(beforeGuide?.risk.display_invalidation_price ?? beforeGuide?.risk.invalidation_price), formatWon(afterGuide?.risk.display_invalidation_price ?? afterGuide?.risk.invalidation_price)],
    ["1차 목표가", formatWon(beforeGuide?.risk.display_target1_price ?? beforeGuide?.risk.target1_price), formatWon(afterGuide?.risk.display_target1_price ?? afterGuide?.risk.target1_price)],
    ["2차 목표가", formatWon(beforeGuide?.risk.display_target2_price ?? beforeGuide?.risk.target2_price), formatWon(afterGuide?.risk.display_target2_price ?? afterGuide?.risk.target2_price)],
  ];
  for (const [label, oldValue, newValue] of pairs) {
    if (oldValue !== newValue) changes.push({ label, before: oldValue, after: newValue });
  }
  return changes;
}

function expandedOutcomeText(report: ExitPolicyValidationReport["expanded_revalidation"]) {
  if (!report) return null;
  const expandedSelected = Number((report.expanded_summary as { selected?: number } | undefined)?.selected ?? 0);
  if (report.outcome === "NEW_CANDIDATE" || expandedSelected > 0) {
    return {
      title: "확대 표본에서 새 매도 기준 후보가 확인됐습니다.",
      detail: "바로 적용하지 않고 후보 전략의 신뢰성 검증을 먼저 확인하는 것이 좋습니다.",
      action: "후보 전략의 신뢰성 검증을 다시 확인합니다.",
    };
  }
  if (report.outcome === "BASELINE_STRENGTHENED") {
    return {
      title: "표본을 늘리면서 기존 기준 유지 쪽으로 결론이 더 명확해졌습니다.",
      detail: `현재 ${report.expanded_stock_count}종목에서도 새 기준 후보는 확인되지 않았습니다.`,
      action: "현재 1차 목표가 도달 시 전량 매도 기준을 유지합니다.",
    };
  }
  if (report.outcome === "NO_CANDIDATE_STABLE") {
    return {
      title: "표본을 늘려도 기존 연구 결론이 그대로 유지됐습니다.",
      detail: `현재 ${report.expanded_stock_count}종목에서도 명확하게 우수한 새 매도 기준은 확인되지 않았습니다.`,
      action: "현재 매도 기준을 유지하고 다음 기능 개선으로 넘어갈 수 있습니다.",
    };
  }
  return {
    title: "표본을 늘리자 일부 전략의 결론이 달라졌습니다.",
    detail: "종목 구성의 영향을 받고 있으므로 현재 단계에서 실제 매도 기준을 변경하지 않는 것이 안전합니다.",
    action: "변경된 전략과 신뢰성 검증 결과를 먼저 확인합니다.",
  };
}

function expandedOverallProgress(
  job: BacktestJob<ExitPolicyValidationReport> | null,
  target: number,
  baseCount: number,
) {
  if (!job) return null;
  const details = job.progress.details ?? {};
  const reused = Number(details.reused_stocks ?? details.cross_sample_reused_stocks ?? 0);
  const calculated = Number(details.calculated_stocks ?? 0);
  const processed = Number(details.processed_stocks ?? job.progress.current ?? 0);
  const total = Math.max(1, Number(details.validation_stock_total ?? job.progress.total ?? target));
  const completed = Math.max(0, Math.min(total, processed));
  return {
    percent: Math.max(0, Math.min(100, completed / total * 100)),
    completed,
    total,
    reused: Math.max(reused, Math.min(baseCount, completed)),
    calculated,
    currentCode: String(details.validation_code ?? details.code ?? ""),
    internalMessage: String(details.internal_message ?? ""),
    internalPercent: Number(details.internal_percent ?? 0),
  };
}

function isBaselineExitPolicy(policyId: string | null | undefined) {
  return !policyId || policyId === "TARGET1_FULL_EXIT" || policyId === "TARGET1_FULL_EXIT_V1";
}

function productionPolicyOverview(status: ProductionExitPolicyStatus | null) {
  if (!status) return { known: false, baselineOnly: false, changedRows: [] as Array<[string, string]> };
  const entries = Object.entries(status.mapping?.strategies ?? {});
  const changedRows = entries
    .filter(([, row]) => !isBaselineExitPolicy(row.policy_id))
    .map(([strategy, row]) => [strategyDisplayLabel(strategy), exitPolicyLabel(row.policy_id)] as [string, string]);
  return { known: true, baselineOnly: changedRows.length === 0, changedRows };
}

function validationDecisionSummary(row: ExitPolicyValidationStrategy) {
  if (row.status === "SELECTED") {
    return "기존 기준보다 핵심 수익·위험 지표에서 불리하지 않고 일부 지표가 개선되어 새 매도 기준 후보로 분류했습니다.";
  }
  if (row.status === "BASELINE_BETTER") {
    return "충분한 표본이 있는 새 방식들과 비교했을 때 기존 기준이 핵심 지표에서 더 불리하지 않아 유지합니다.";
  }
  if (row.status === "INSUFFICIENT_SAMPLE") {
    return "여러 종목과 거래 표본이 충분하지 않아 새 기준을 판단하지 않고 기존 기준을 유지합니다.";
  }
  if (row.stock_concentration?.single_stock_dominant) {
    return "개선 효과가 특정 종목에 지나치게 집중되어 전체 전략의 새 기준으로 보기 어려워 판단을 보류했습니다.";
  }
  return "일부 지표는 좋아졌지만 다른 핵심 지표와 상충해 한 가지 기준으로 확정하기 어려워 판단을 보류했습니다.";
}

function validationDecisionPolicy(row: ExitPolicyValidationStrategy) {
  if (row.status === "SELECTED") return exitPolicyLabel(row.selected_policy_id);
  if (row.status === "BASELINE_BETTER") return "기존 1차 목표가 전량 매도 유지";
  if (row.status === "INSUFFICIENT_SAMPLE") return "표본 보강 전 기존 기준 유지";
  return "새 매도 기준 확정 안 함";
}

const VALIDATION_STRATEGY_ORDER = [
  "TREND_FOLLOWING",
  "PULLBACK",
  "BREAKOUT",
  "SUPPORT_BOUNCE",
  "OVERSOLD_BOUNCE",
  "RANGE_TRADING",
  "MOMENTUM_CONTINUATION",
  "VOLATILITY_SQUEEZE",
  "MA20_REBOUND",
  "TREND_RECOVERY",
] as const;

function validationStrategyProgressRows(localCurrent: number, localTotal: number) {
  if (localTotal <= 0 || localTotal % VALIDATION_STRATEGY_ORDER.length !== 0) return [];
  const unitsPerStrategy = localTotal / VALIDATION_STRATEGY_ORDER.length;
  if (!Number.isInteger(unitsPerStrategy) || unitsPerStrategy <= 0) return [];
  return VALIDATION_STRATEGY_ORDER.map((strategy, index) => {
    const start = index * unitsPerStrategy;
    const completed = Math.max(0, Math.min(unitsPerStrategy, localCurrent - start));
    const percent = (completed / unitsPerStrategy) * 100;
    return { strategy, completed, total: unitsPerStrategy, percent };
  });
}

function validationProgressView(job: BacktestJob<ExitPolicyValidationReport>) {
  const details = job.progress.details ?? {};
  const stockIndexRaw = Number(details.validation_stock_index ?? 0);
  const stockTotalRaw = Number(details.validation_stock_total ?? job.progress.total ?? 0);
  const processedRaw = Number(details.processed_stocks ?? job.progress.current ?? 0);
  const total = Math.max(0, Number.isFinite(stockTotalRaw) ? stockTotalRaw : Number(job.progress.total || 0));
  const completed = Math.max(0, Math.min(total, Number.isFinite(processedRaw) ? processedRaw : Number(job.progress.current || 0)));
  const percent = total > 0 ? (completed / total) * 100 : Math.max(0, Math.min(100, job.progress.percent || 0));
  const currentStockIndex = Number.isFinite(stockIndexRaw) && stockIndexRaw > 0
    ? stockIndexRaw
    : Math.min(total, completed + (job.status === "running" ? 1 : 0));
  const currentCode = String(details.validation_code ?? details.code ?? "-");
  const strategy = typeof details.strategy === "string" ? strategyDisplayLabel(details.strategy) : null;
  const policy = typeof details.policy === "string" ? exitPolicyLabel(details.policy) : null;
  let currentTask = userFacingResearchText(job.progress.message);
  if (job.stage === "exit_policy_validation_stock_work") currentTask = "현재 종목의 매도 기준을 비교하고 있습니다.";
  else if (job.stage === "exit_policy_validation_checkpoint_hit") currentTask = "이전에 완료한 연구 결과를 재사용하고 있습니다.";
  else if (job.stage === "exit_policy_validation_stock_skipped") currentTask = "데이터가 부족한 종목을 제외하고 있습니다.";
  else if (job.stage === "exit_policy_validation_stock_completed") currentTask = "현재 종목의 매도 기준 비교를 완료했습니다.";
  else if (job.stage === "exit_policy_validation_sample") currentTask = "저장된 시세 데이터에서 검증 대상 종목을 확정했습니다.";
  return {
    completed,
    total,
    percent,
    currentStockIndex,
    currentCode,
    currentTask,
    strategy,
    policy,
    localCurrent: Math.max(0, Number(details.internal_current ?? 0)),
    localTotal: Math.max(0, Number(details.internal_total ?? 0)),
    localPercent: Math.max(0, Math.min(100, Number(details.internal_percent ?? 0))),
  };
}

function ExitPolicyStrategyReport({ row }: { row: ExitPolicyValidationStrategy }) {
  const baseline = row.baseline ?? null;
  const candidate = row.status === "SELECTED"
    ? (row.selected ?? row.policies.find((policy) => policy.policy_id === row.selected_policy_id) ?? null)
    : null;
  const baselineMetrics = policyMetrics(baseline);
  const candidateMetrics = policyMetrics(candidate);
  const hasDirectComparison = Boolean(baselineMetrics && candidateMetrics && baseline?.policy_id !== candidate?.policy_id);
  const alternativePolicies = row.policies.filter((policy) => policy.policy_id !== baseline?.policy_id);

  return (
    <article className={`exit-validation-strategy status-${row.status.toLowerCase()}`}>
      <div className="exit-validation-strategy-head">
        <div><span>{strategyDisplayLabel(row.strategy)}</span><strong>{exitPolicyStatusLabel(row.status)}</strong></div>
        <div className="exit-validation-strategy-decision"><small>결론</small><b>{validationDecisionPolicy(row)}</b></div>
      </div>
      <p className="exit-validation-strategy-summary">{validationDecisionSummary(row)}</p>

      <details className="exit-validation-strategy-details">
        <summary><span>자세한 비교 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
        <div className="exit-validation-strategy-details-body">
          <div className="exit-validation-reason"><b>판단 근거</b><span>{userFacingResearchText(row.reason)}</span></div>

          {hasDirectComparison && baselineMetrics && candidateMetrics && (
            <div className="exit-validation-direct-compare">
              <div className="exit-validation-direct-compare-head">
                <strong>기존 기준과 새 후보 비교</strong>
                <span>{exitPolicyLabel(baseline?.policy_id)} → {exitPolicyLabel(candidate?.policy_id)}</span>
              </div>
              <div className="exit-validation-policy-table-wrap">
                <table className="exit-validation-policy-table compact-comparison">
                  <thead><tr><th>항목</th><th>기존 기준</th><th>새 후보</th><th>변화</th></tr></thead>
                  <tbody>
                    <tr><td>평균 순수익</td><td>{formatPct(baselineMetrics.average_net_return_pct)}</td><td>{formatPct(candidateMetrics.average_net_return_pct)}</td><td>{metricChangeText(baselineMetrics.average_net_return_pct, candidateMetrics.average_net_return_pct, { unit: "%p" })}</td></tr>
                    <tr><td>이익/손실 비율</td><td>{formatNumber(baselineMetrics.profit_factor, 2)}</td><td>{formatNumber(candidateMetrics.profit_factor, 2)}</td><td>{metricChangeText(baselineMetrics.profit_factor, candidateMetrics.profit_factor, { digits: 2 })}</td></tr>
                    <tr><td>최대 낙폭</td><td>{formatPct(baselineMetrics.median_max_drawdown_pct)}</td><td>{formatPct(candidateMetrics.median_max_drawdown_pct)}</td><td>{metricChangeText(baselineMetrics.median_max_drawdown_pct, candidateMetrics.median_max_drawdown_pct, { unit: "%p" })}</td></tr>
                    <tr><td>수익 반납폭</td><td>{baselineMetrics.average_profit_giveback_pct_points == null ? "-" : `${formatNumber(baselineMetrics.average_profit_giveback_pct_points, 2)}%p`}</td><td>{candidateMetrics.average_profit_giveback_pct_points == null ? "-" : `${formatNumber(candidateMetrics.average_profit_giveback_pct_points, 2)}%p`}</td><td>{metricChangeText(baselineMetrics.average_profit_giveback_pct_points, candidateMetrics.average_profit_giveback_pct_points, { unit: "%p", higherIsBetter: false })}</td></tr>
                    <tr><td>평균 보유기간</td><td>{baselineMetrics.average_holding_days == null ? "-" : `${formatNumber(baselineMetrics.average_holding_days, 1)}일`}</td><td>{candidateMetrics.average_holding_days == null ? "-" : `${formatNumber(candidateMetrics.average_holding_days, 1)}일`}</td><td>{metricChangeText(baselineMetrics.average_holding_days, candidateMetrics.average_holding_days, { digits: 1, unit: "일", neutralOnly: true })}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!hasDirectComparison && baselineMetrics && alternativePolicies.length > 0 && (
            <div className="exit-validation-direct-compare range-comparison">
              <div className="exit-validation-direct-compare-head">
                <strong>기존 기준과 새 방식 전체 범위</strong>
                <span>{alternativePolicies.length}개 새 방식을 한 번에 비교한 범위입니다.</span>
              </div>
              <div className="exit-validation-policy-table-wrap">
                <table className="exit-validation-policy-table compact-comparison">
                  <thead><tr><th>항목</th><th>기존 기준</th><th>새 방식 범위</th></tr></thead>
                  <tbody>
                    <tr><td>평균 순수익</td><td>{formatPct(baselineMetrics.average_net_return_pct)}</td><td>{formatPctRange(alternativePolicies.map((policy) => policy.aggregate_metrics.average_net_return_pct))}</td></tr>
                    <tr><td>이익/손실 비율</td><td>{formatNumber(baselineMetrics.profit_factor, 2)}</td><td>{formatNumberRange(alternativePolicies.map((policy) => policy.aggregate_metrics.profit_factor), 2)}</td></tr>
                    <tr><td>최대 낙폭</td><td>{formatPct(baselineMetrics.median_max_drawdown_pct)}</td><td>{formatPctRange(alternativePolicies.map((policy) => policy.aggregate_metrics.median_max_drawdown_pct))}</td></tr>
                    <tr><td>수익 반납폭</td><td>{baselineMetrics.average_profit_giveback_pct_points == null ? "-" : `${formatNumber(baselineMetrics.average_profit_giveback_pct_points, 2)}%p`}</td><td>{formatNumberRange(alternativePolicies.map((policy) => policy.aggregate_metrics.average_profit_giveback_pct_points), 2, "%p")}</td></tr>
                    <tr><td>평균 보유기간</td><td>{baselineMetrics.average_holding_days == null ? "-" : `${formatNumber(baselineMetrics.average_holding_days, 1)}일`}</td><td>{formatNumberRange(alternativePolicies.map((policy) => policy.aggregate_metrics.average_holding_days), 1, "일")}</td></tr>
                  </tbody>
                </table>
              </div>
              <p className="exit-validation-range-note">범위는 여러 새 방식의 최소~최대 값이며, 이 화면이 임의로 ‘최고 방식’을 고른 결과가 아닙니다.</p>
            </div>
          )}

          {row.stock_concentration?.single_stock_dominant && (
            <div className="exit-validation-warning">특정 종목({String(row.stock_concentration.dominant_code ?? "-")})의 영향이 너무 커 전체 전략의 새 기준으로 자동 선택하지 않았습니다.</div>
          )}
          {row.max_hold_validation && (
            <div className="exit-validation-hold"><b>2차 목표가 도달 후 보유기간</b><span>{userFacingResearchText(row.max_hold_validation.reason)}</span></div>
          )}

          <details className="exit-validation-policy-details">
            <summary><span>매도 방식별 전체 수치</span><DetailToggleText /></summary>
            <div className="exit-validation-policy-table-wrap">
              <table className="exit-validation-policy-table">
                <thead><tr><th>방식</th><th>거래</th><th>평균 수익</th><th>이익/손실 비율</th><th>최대 낙폭</th><th>수익 반납</th><th>평균 보유</th></tr></thead>
                <tbody>{row.policies.map((policy) => <tr key={policy.policy_id}><td>{exitPolicyLabel(policy.policy_id)}</td><td>{policy.aggregate_metrics.trades}</td><td>{formatPct(policy.aggregate_metrics.average_net_return_pct)}</td><td>{formatNumber(policy.aggregate_metrics.profit_factor, 2)}</td><td>{formatPct(policy.aggregate_metrics.median_max_drawdown_pct)}</td><td>{policy.aggregate_metrics.average_profit_giveback_pct_points == null ? "-" : `${formatNumber(policy.aggregate_metrics.average_profit_giveback_pct_points, 2)}%p`}</td><td>{policy.aggregate_metrics.average_holding_days == null ? "-" : `${formatNumber(policy.aggregate_metrics.average_holding_days, 1)}일`}</td></tr>)}</tbody>
              </table>
            </div>
          </details>
          {row.regime_metrics && Object.keys(row.regime_metrics).length > 0 && (
            <details className="exit-validation-policy-details">
              <summary><span>시장 상태별 결과</span><DetailToggleText /></summary>
              <div className="exit-validation-regime-grid">
                {Object.entries(row.regime_metrics).map(([regime, metrics]) => (
                  <span key={regime}><small>{regimeLabel[regime] ?? regime}</small><b>{formatPct(metrics.average_net_return_pct)}</b><em>{metrics.trades}건 · 이익/손실 비율 {formatNumber(metrics.profit_factor, 2)}</em></span>
                ))}
              </div>
            </details>
          )}
        </div>
      </details>
    </article>
  );
}

function researchAuditCheckLabel(status: string | undefined) {
  if (status === "PASS") return "통과";
  if (status === "PASS_WITH_NOTES") return "확인 필요";
  if (status === "FAIL") return "불일치";
  if (status === "STABLE") return "안정적";
  if (status === "SENSITIVE") return "민감함";
  if (status === "POLICY_DEPENDENT") return "방식에 따라 달라짐";
  if (status === "NO_COUNT_DIVERGENCE_DETECTED") return "건수 차이 없음";
  if (status === "INFORMATIONAL") return "참고";
  return status || "-";
}

function StrategyMiniCard({ row }: { row: MultiStrategyRow }) {
  return (
    <article className={`multi-strategy-mini fit-${row.historical_fit.status.toLowerCase()}`}>
      <div className="multi-strategy-rank">{row.rank}위</div>
      <div>
        <strong>{row.guide.easy_name}</strong>
        <span>{row.guide.professional_name} 전략 · {row.historical_fit.label}</span>
      </div>
      <div className="multi-strategy-mini-current">
        <b>{row.current.label}</b>
        <small>과거 사례 {row.historical_metrics.trades}건</small>
      </div>
    </article>
  );
}

export default function BacktestPanel({ code, market, stockName, onSelectStock }: Props) {
  const [view, setView] = useState<"setup" | "result">("setup");
  const [stockQuery, setStockQuery] = useState(stockName ? `${stockName} (${code})` : code);
  const [stockSearchResults, setStockSearchResults] = useState<StockSearchItem[]>([]);
  const [stockSearchBusy, setStockSearchBusy] = useState(false);
  const [stockSearchOpen, setStockSearchOpen] = useState(false);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(() => isoDate(new Date()));
  const [initialCapital, setInitialCapital] = useState("10000000");
  const [maxHoldingDays, setMaxHoldingDays] = useState(20);
  const [customHolding, setCustomHolding] = useState("");
  const [costPct, setCostPct] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<BacktestJob<MultiStrategyBacktestResponse> | null>(null);
  const [result, setResult] = useState<MultiStrategyBacktestResponse | null>(null);
  const [validationBusy, setValidationBusy] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [validationJob, setValidationJob] = useState<BacktestJob<ExitPolicyValidationReport> | null>(null);
  const [validationReport, setValidationReport] = useState<ExitPolicyValidationReport | null>(null);
  const [expandedValidationReport, setExpandedValidationReport] = useState<ExitPolicyValidationReport | null>(null);
  const [validationAudit, setValidationAudit] = useState<ExitPolicyResearchAuditReport | null>(null);
  const [validationAuditBusy, setValidationAuditBusy] = useState(false);
  const [validationAuditError, setValidationAuditError] = useState<string | null>(null);
  const [expandedPlanOpen, setExpandedPlanOpen] = useState(false);
  const [expandedTarget, setExpandedTarget] = useState<20 | 40 | 60>(40);
  const [expandedPlan, setExpandedPlan] = useState<ExpandedSamplePlan | null>(null);
  const [expandedPlanBusy, setExpandedPlanBusy] = useState(false);
  const [expandedBusy, setExpandedBusy] = useState(false);
  const [expandedPrepareBusy, setExpandedPrepareBusy] = useState(false);
  const [expandedError, setExpandedError] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<BacktestJob<ExitPolicyValidationReport> | null>(null);
  const [expandedPrepareJob, setExpandedPrepareJob] = useState<BacktestJob<ExpandedSamplePreparationResult> | null>(null);
  const [productionStatus, setProductionStatus] = useState<ProductionExitPolicyStatus | null>(null);
  const [productionStatusError, setProductionStatusError] = useState(false);
  const [latestReanalysisBusy, setLatestReanalysisBusy] = useState(false);
  const [latestReanalysisSummary, setLatestReanalysisSummary] = useState<LatestReanalysisSummary | null>(null);
  const [validationSetupOpen, setValidationSetupOpen] = useState(true);
  const [validationPanelOpen, setValidationPanelOpen] = useState(false);
  const [mainSetupExpanded, setMainSetupExpanded] = useState(false);
  const [researchSection, setResearchSection] = useState<ResearchSection>("RUN");
  const [researchReportSource, setResearchReportSource] = useState<ResearchReportSource>(null);
  const [previousResearchMeta, setPreviousResearchMeta] = useState<ExitPolicyValidationHistoryItem | null>(null);
  const [researchHistory, setResearchHistory] = useState<ExitPolicyValidationHistoryItem[]>([]);
  const [researchHistoryBusy, setResearchHistoryBusy] = useState(false);
  const [researchHistoryError, setResearchHistoryError] = useState<string | null>(null);
  const [previousResearchBusy, setPreviousResearchBusy] = useState(false);
  const activeJobId = useRef<string | null>(null);
  const activeValidationJobId = useRef<string | null>(null);
  const activeExpandedJobId = useRef<string | null>(null);
  const activeExpandedPrepareJobId = useRef<string | null>(null);
  const workspaceTopRef = useRef<HTMLDivElement | null>(null);
  const validationReportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setStockQuery(stockName ? `${stockName} (${code})` : code);
  }, [code, stockName]);

  useEffect(() => {
    const query = stockQuery.trim();
    const selectedLabel = stockName ? `${stockName} (${code})` : "";
    if (query === selectedLabel || query.length < 2) {
      setStockSearchResults([]);
      setStockSearchBusy(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setStockSearchBusy(true);
      void searchStocks(query)
        .then((response) => {
          setStockSearchResults(response.rows);
          setStockSearchOpen(true);
        })
        .catch(() => {
          setStockSearchResults([]);
          setStockSearchOpen(true);
        })
        .finally(() => setStockSearchBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [stockQuery, code, stockName]);

  useEffect(() => {
    // A stored research report is data, not the current UI session.
    // On every fresh page mount we stay on the setup screen and only check lightweight metadata.
    void fetchExitPolicyValidationHistory(1)
      .then((response) => setPreviousResearchMeta(response.available ? response.rows[0] ?? null : null))
      .catch(() => setPreviousResearchMeta(null));
    void refreshProductionStatus(2);
  }, []);

  useEffect(() => {
    const reference = expandedValidationReport ?? validationReport;
    const count = reference?.validated_stocks?.length ?? reference?.selected_stocks?.length ?? 0;
    if (count >= 40) setExpandedTarget(60);
    else setExpandedTarget(40);
    setExpandedPlan(null);
    setExpandedError(null);
    setExpandedPlanOpen(false);
  }, [validationReport?.signature, expandedValidationReport?.signature]);

  useEffect(() => {
    return () => {
      const running = activeJobId.current;
      if (running) void cancelBacktestJob<MultiStrategyBacktestResponse>(running).catch(() => undefined);
      const validationRunning = activeValidationJobId.current;
      if (validationRunning) void cancelBacktestJob<ExitPolicyValidationReport>(validationRunning).catch(() => undefined);
      const expandedRunning = activeExpandedJobId.current;
      if (expandedRunning) void cancelBacktestJob<ExitPolicyValidationReport>(expandedRunning).catch(() => undefined);
      const prepareRunning = activeExpandedPrepareJobId.current;
      if (prepareRunning) void cancelBacktestJob<ExpandedSamplePreparationResult>(prepareRunning).catch(() => undefined);
    };
  }, []);

  useEffect(() => {
    const running = activeJobId.current;
    if (running) void cancelBacktestJob<MultiStrategyBacktestResponse>(running).catch(() => undefined);
    activeJobId.current = null;
    setBusy(false);
    setJob(null);
    setResult(null);
    setError(null);
    setView("setup");
  }, [code, market]);

  const selectedHolding = customHolding ? Number(customHolding) : maxHoldingDays;
  const selectedStockLabel = stockName ? `${stockName} (${code})` : "";
  const stockSelectionDirty = Boolean(stockQuery.trim() && stockQuery.trim() !== selectedStockLabel);
  const holdingDescription = useMemo(() => {
    if (customHolding) return "직접 입력한 거래일 수를 모든 전략에 동일하게 적용합니다.";
    return holdingOptions.find((item) => item.days === maxHoldingDays)?.description ?? "";
  }, [customHolding, maxHoldingDays]);

  function chooseStock(item: StockSearchItem) {
    onSelectStock(item);
    setStockQuery(`${item.name} (${item.code})`);
    setStockSearchResults([]);
    setStockSearchOpen(false);
    setView("setup");
  }

  function scrollTop() {
    window.requestAnimationFrame(() => workspaceTopRef.current?.scrollIntoView({ behavior: "auto", block: "start" }));
  }

  async function refreshProductionStatus(retries = 0) {
    setProductionStatusError(false);
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        const response = await fetchExitPolicyProductionStatus();
        setProductionStatus(response);
        setProductionStatusError(false);
        return;
      } catch {
        if (attempt >= retries) {
          setProductionStatusError(true);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 350 * (attempt + 1)));
      }
    }
  }

  async function refreshResearchHistory(limit = 20) {
    if (researchHistoryBusy) return;
    setResearchHistoryBusy(true);
    setResearchHistoryError(null);
    try {
      const response = await fetchExitPolicyValidationHistory(limit);
      setResearchHistory(response.rows ?? []);
      setPreviousResearchMeta(response.rows?.[0] ?? null);
    } catch (cause) {
      setResearchHistoryError(cause instanceof Error ? cause.message : "이전 연구 기록을 확인하지 못했습니다.");
    } finally {
      setResearchHistoryBusy(false);
    }
  }

  async function loadStoredResearch(signature?: string) {
    if (previousResearchBusy) return;
    setPreviousResearchBusy(true);
    setValidationError(null);
    setValidationAudit(null);
    setValidationAuditError(null);
    try {
      const response = signature
        ? await fetchExitPolicyValidationReport(signature)
        : await fetchLatestExitPolicyValidationReport();
      if (!response.available || !response.report) throw new Error("저장된 연구 결과를 찾지 못했습니다.");
      const stored = response.report;
      const baseSignature = stored.expanded_revalidation?.base_signature;
      if (baseSignature) {
        setExpandedValidationReport(stored);
        const base = await fetchExitPolicyValidationReport(baseSignature);
        setValidationReport(base.available && base.report ? base.report : stored);
      } else {
        setValidationReport(stored);
        setExpandedValidationReport(null);
      }
      setResearchReportSource("PREVIOUS_RUN");
      setValidationPanelOpen(true);
      setValidationSetupOpen(false);
      setMainSetupExpanded(false);
      setView("setup");
      setResearchSection("SUMMARY");
      scrollTop();
    } catch (cause) {
      setValidationError(cause instanceof Error ? cause.message : "이전 연구 결과를 불러오지 못했습니다.");
    } finally {
      setPreviousResearchBusy(false);
    }
  }

  async function openResearchSection(section: ResearchSection) {
    setValidationPanelOpen(true);
    setResearchSection(section);
    if (section === "HISTORY") await refreshResearchHistory(30);
    if (section === "RELIABILITY" && validationReport && !validationAudit && !validationAuditBusy) {
      const latestSignature = previousResearchMeta?.signature;
      const visibleSignature = (expandedValidationReport ?? validationReport).signature;
      if (!latestSignature || latestSignature === visibleSignature || researchReportSource === "CURRENT_RUN") {
        void fetchLatestExitPolicyValidationAudit()
          .then((response) => { if (response.available && response.report) setValidationAudit(response.report); })
          .catch(() => undefined);
      }
    }
  }

  async function runBacktest(
    endDateOverride?: string,
    options: { preserveResult?: boolean } = {},
  ): Promise<MultiStrategyBacktestResponse | null> {
    if (!code.trim() || stockSelectionDirty || busy) return null;
    const holding = Number(selectedHolding);
    if (!Number.isFinite(holding) || holding < 1 || holding > 120) {
      setError("최대 보유기간은 1~120 거래일로 입력해 주세요.");
      return null;
    }
    setBusy(true);
    setError(null);
    if (!options.preserveResult) setResult(null);
    setView("result");
    scrollTop();

    try {
      const created = await createMultiStrategyBacktestJob({
        code,
        market,
        start_date: startDate,
        end_date: endDateOverride ?? endDate,
        initial_capital: Number(initialCapital),
        max_holding_days: holding,
        round_trip_cost_pct: Number(costPct),
      });
      setJob(created);
      activeJobId.current = created.job_id;

      while (activeJobId.current === created.job_id) {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        const latest = await fetchBacktestJob<MultiStrategyBacktestResponse>(created.job_id);
        setJob(latest);
        if (latest.status === "completed" && latest.result) {
          setResult(latest.result);
          setBusy(false);
          activeJobId.current = null;
          scrollTop();
          return latest.result;
        }
        if (latest.status === "failed") {
          throw new Error(latest.error || "전체 전략 검증을 완료하지 못했습니다.");
        }
        if (latest.status === "cancelled") {
          setBusy(false);
          activeJobId.current = null;
          return null;
        }
      }
      return null;
    } catch (cause) {
      setBusy(false);
      activeJobId.current = null;
      setError(cause instanceof Error ? cause.message : "전체 전략 검증 중 오류가 발생했습니다.");
      return null;
    }
  }

  async function runExitPolicyValidation(forceRefresh = false) {
    if (validationBusy) return;
    const holding = Number(selectedHolding);
    if (!Number.isFinite(holding) || holding < 1 || holding > 120) {
      setValidationError("최대 보유기간은 1~120 거래일로 입력해 주세요.");
      return;
    }
    setValidationBusy(true);
    setValidationError(null);
    setValidationAudit(null);
    setValidationAuditError(null);
    setValidationPanelOpen(true);
    setValidationSetupOpen(true);
    setResearchSection("RUN");
    setResearchReportSource(null);
    try {
      const created = await createExitPolicyValidationJob({
        start_date: startDate,
        end_date: endDate,
        markets: ["KOSPI", "KOSDAQ"],
        max_stocks: 20,
        minimum_coverage_pct: 90,
        initial_capital: Number(initialCapital),
        max_holding_days: holding,
        round_trip_cost_pct: Number(costPct),
        minimum_stock_count: 3,
        minimum_total_trades: 30,
        post_target2_research_days: 60,
        force_refresh: forceRefresh,
      });
      setValidationJob(created);
      activeValidationJobId.current = created.job_id;
      while (activeValidationJobId.current === created.job_id) {
        await new Promise((resolve) => window.setTimeout(resolve, 800));
        const latest = await fetchBacktestJob<ExitPolicyValidationReport>(created.job_id);
        setValidationJob(latest);
        if (latest.status === "completed" && latest.result) {
          setValidationReport(latest.result);
          setExpandedValidationReport(null);
          setResearchReportSource("CURRENT_RUN");
          setResearchSection("SUMMARY");
          setValidationSetupOpen(false);
          setMainSetupExpanded(false);
          setValidationBusy(false);
          activeValidationJobId.current = null;
          void refreshResearchHistory(1);
          return;
        }
        if (latest.status === "failed") throw new Error(userFacingResearchText(latest.error || "매도 기준 비교 검증을 완료하지 못했습니다."));
        if (latest.status === "cancelled") {
          setValidationBusy(false);
          activeValidationJobId.current = null;
          return;
        }
      }
    } catch (cause) {
      setValidationBusy(false);
      activeValidationJobId.current = null;
      setValidationError(userFacingResearchText(cause instanceof Error ? cause.message : "매도 기준 비교 검증 중 오류가 발생했습니다."));
    }
  }

  async function cancelExitPolicyValidation() {
    const id = activeValidationJobId.current;
    if (!id) return;
    try {
      const cancelled = await cancelBacktestJob<ExitPolicyValidationReport>(id);
      setValidationJob(cancelled);
    } finally {
      activeValidationJobId.current = null;
      setValidationBusy(false);
    }
  }

  async function runValidationAudit() {
    const reportForAudit = expandedValidationReport ?? validationReport;
    if (validationAuditBusy || reportForAudit?.status !== "COMPLETED") return;
    setValidationAuditBusy(true);
    setValidationAuditError(null);
    try {
      const report = await runExitPolicyValidationAudit();
      if (!report.available) {
        setValidationAudit(null);
        setValidationAuditError(report.message || "연구 신뢰성 검증에 필요한 원자료가 없습니다.");
        return;
      }
      setValidationAudit(report);
    } catch (cause) {
      setValidationAuditError(cause instanceof Error ? cause.message : "연구 결과 신뢰성 검증 중 오류가 발생했습니다.");
    } finally {
      setValidationAuditBusy(false);
    }
  }

  async function loadExpandedPlan(target: 20 | 40 | 60 = expandedTarget) {
    const baseReport = expandedValidationReport ?? validationReport;
    if (!baseReport?.signature || expandedPlanBusy) return;
    setExpandedPlanOpen(true);
    setExpandedPlanBusy(true);
    setExpandedError(null);
    try {
      const plan = await planExpandedExitPolicyValidation({
        target_stocks: target,
        base_signature: baseReport.signature,
      });
      setExpandedPlan(plan);
    } catch (cause) {
      setExpandedPlan(null);
      setExpandedError(cause instanceof Error ? cause.message : "확대 표본 검증 준비 상태를 확인하지 못했습니다.");
    } finally {
      setExpandedPlanBusy(false);
    }
  }

  async function prepareExpandedData() {
    const baseReport = expandedValidationReport ?? validationReport;
    if (!baseReport?.signature || expandedPrepareBusy) return;
    setExpandedPrepareBusy(true);
    setExpandedError(null);
    try {
      const created = await createExpandedSamplePreparationJob({
        target_stocks: expandedTarget,
        base_signature: baseReport.signature,
      });
      setExpandedPrepareJob(created);
      activeExpandedPrepareJobId.current = created.job_id;
      while (activeExpandedPrepareJobId.current === created.job_id) {
        await new Promise((resolve) => window.setTimeout(resolve, 800));
        const latest = await fetchBacktestJob<ExpandedSamplePreparationResult>(created.job_id);
        setExpandedPrepareJob(latest);
        if (latest.status === "completed" && latest.result) {
          setExpandedPlan(latest.result.plan);
          activeExpandedPrepareJobId.current = null;
          setExpandedPrepareBusy(false);
          if (latest.result.status !== "READY") setExpandedError(latest.result.message);
          return;
        }
        if (latest.status === "failed") throw new Error(latest.error || "확대 표본 검증 데이터를 준비하지 못했습니다.");
        if (latest.status === "cancelled") {
          activeExpandedPrepareJobId.current = null;
          setExpandedPrepareBusy(false);
          return;
        }
      }
    } catch (cause) {
      activeExpandedPrepareJobId.current = null;
      setExpandedPrepareBusy(false);
      setExpandedError(cause instanceof Error ? cause.message : "확대 표본 검증 데이터 준비 중 오류가 발생했습니다.");
    }
  }

  async function runExpandedValidation() {
    const baseReport = expandedValidationReport ?? validationReport;
    if (!baseReport?.signature || expandedBusy || !expandedPlan?.ready_to_run) return;
    setExpandedBusy(true);
    setExpandedError(null);
    try {
      const created = await createExpandedExitPolicyValidationJob({
        target_stocks: expandedTarget,
        base_signature: baseReport.signature,
      });
      setExpandedJob(created);
      activeExpandedJobId.current = created.job_id;
      while (activeExpandedJobId.current === created.job_id) {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        const latest = await fetchBacktestJob<ExitPolicyValidationReport>(created.job_id);
        setExpandedJob(latest);
        if (latest.status === "completed" && latest.result) {
          setExpandedValidationReport(latest.result);
          setResearchReportSource("CURRENT_RUN");
          setResearchSection("EXPANDED");
          setValidationAudit(null);
          setValidationAuditError(null);
          setExpandedPlan(null);
          setExpandedPlanOpen(false);
          activeExpandedJobId.current = null;
          setExpandedBusy(false);
          void refreshProductionStatus(2);
          void refreshResearchHistory(1);
          return;
        }
        if (latest.status === "failed") throw new Error(latest.error || "확대 표본 재검증을 완료하지 못했습니다.");
        if (latest.status === "cancelled") {
          activeExpandedJobId.current = null;
          setExpandedBusy(false);
          return;
        }
      }
    } catch (cause) {
      activeExpandedJobId.current = null;
      setExpandedBusy(false);
      setExpandedError(cause instanceof Error ? cause.message : "확대 표본 재검증 중 오류가 발생했습니다.");
    }
  }

  async function rerunLatest() {
    if (busy || latestReanalysisBusy || !result) return;
    setLatestReanalysisBusy(true);
    setLatestReanalysisSummary(null);
    setError(null);
    try {
      const freshness = await prepareScannerLatestData({
        market_scope: market,
        known_data_date: result.as_of_date,
      });
      const resolved = freshness.resolved_as_of_date ?? freshness.latest_confirmed_date ?? result.as_of_date;
      if (!freshness.date_changed || resolved === result.as_of_date) {
        setLatestReanalysisSummary({
          status: "UP_TO_DATE",
          previousAsOf: result.as_of_date,
          latestAsOf: resolved,
          changes: [],
        });
        return;
      }

      const before = result;
      setEndDate(resolved);
      const after = await runBacktest(resolved, { preserveResult: true });
      if (!after) return;
      const changes = buildLatestReanalysisChanges(before, after);
      setLatestReanalysisSummary({
        status: changes.length > 0 ? "UPDATED_CHANGED" : "UPDATED_SAME",
        previousAsOf: before.as_of_date,
        latestAsOf: after.as_of_date,
        changes,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "최신 확정 데이터 확인 중 오류가 발생했습니다.");
    } finally {
      setLatestReanalysisBusy(false);
    }
  }

  async function cancelRunning() {
    const id = activeJobId.current;
    if (!id) return;
    try {
      const cancelled = await cancelBacktestJob<MultiStrategyBacktestResponse>(id);
      setJob(cancelled);
    } finally {
      activeJobId.current = null;
      setBusy(false);
    }
  }

  const topStrategy = result?.recommendation.strategy
    ? result.strategies.find((row) => row.strategy === result.recommendation.strategy) ?? result.strategies[0]
    : null;
  const topThree = result?.strategies.slice(0, 3) ?? [];
  const validationRows = validationReport?.strategies ?? [];
  const validationCandidates = validationRows.filter((row) => row.status === "SELECTED");
  const validationProgress = validationJob ? validationProgressView(validationJob) : null;
  const productionOverview = productionPolicyOverview(productionStatus);
  const operationalValidationReport = expandedValidationReport ?? validationReport;
  const selectedResearchIsLatest = Boolean(operationalValidationReport && (!previousResearchMeta || operationalValidationReport.signature === previousResearchMeta.signature || researchReportSource === "CURRENT_RUN"));
  const validationAuditCurrent = Boolean(validationAudit && operationalValidationReport && validationAudit.validation_signature === operationalValidationReport.signature);
  const currentValidationAudit = validationAuditCurrent ? validationAudit : null;
  const auditSensitiveRows = currentValidationAudit?.strategies?.filter((row) => row.leave_one_out?.status === "SENSITIVE") ?? [];
  const auditStableRows = currentValidationAudit?.strategies?.filter((row) => row.leave_one_out?.status !== "SENSITIVE") ?? [];
  const auditSensitiveCount = currentValidationAudit?.summary?.leave_one_out_sensitive_strategies ?? auditSensitiveRows.length;
  const auditStrategyCount = currentValidationAudit?.summary?.strategy_count ?? currentValidationAudit?.strategies?.length ?? 0;
  const auditStableCount = Math.max(0, auditStrategyCount - auditSensitiveCount);
  const auditCriticalCount = currentValidationAudit?.summary?.critical_issue_count ?? 0;
  const auditPolicyDependentCount = currentValidationAudit?.summary?.policy_dependent_entry_strategies ?? 0;
  const auditAggregateMismatch = currentValidationAudit?.checks?.aggregate_replay?.mismatch_count ?? 0;
  const auditDecisionMismatch = currentValidationAudit?.checks?.decision_replay?.mismatch_count ?? 0;
  const auditHasCalculationProblem = auditCriticalCount > 0 || auditAggregateMismatch > 0 || auditDecisionMismatch > 0 || currentValidationAudit?.status === "FAIL";
  const auditNeedsSourceData = currentValidationAudit?.status === "DATA_REQUIRED";
  const auditMainHeadline = !currentValidationAudit
    ? "이 연구 결과를 한 번 더 확인할 수 있습니다."
    : auditNeedsSourceData
      ? "신뢰성 검증을 완료하려면 연구 원자료가 더 필요합니다."
      : auditHasCalculationProblem
        ? "연구 결과 계산에서 다시 확인해야 할 문제가 발견됐습니다."
        : auditSensitiveCount > 0
          ? `계산에는 큰 이상이 없지만, ${auditSensitiveCount}개 전략은 종목 구성에 따라 결과가 달라졌습니다.`
          : "계산 결과가 일관되며 종목 구성 변경에도 연구 결론이 안정적으로 유지됐습니다.";
  const auditCurrentJudgment = !currentValidationAudit
    ? "신뢰성 검증을 실행하면 현재 연구 결과의 계산 일관성과 종목 구성 영향을 확인할 수 있습니다."
    : auditNeedsSourceData
      ? "현재 결과를 더 해석하기 전에 검증에 필요한 원자료를 먼저 준비해야 합니다."
      : auditHasCalculationProblem
        ? "현재 연구 결과를 그대로 기준 변경에 사용하지 않는 것이 좋습니다. 먼저 불일치 원인을 확인해야 합니다."
        : (operationalValidationReport?.summary?.selected ?? 0) === 0
          ? "현재 매도 기준을 바꿀 추가 근거는 확인되지 않았습니다."
          : auditSensitiveCount > 0
            ? "새 매도 기준 후보는 있지만, 실제 적용 전에 더 넓은 종목 표본에서 같은 결과가 유지되는지 확인할 필요가 있습니다."
            : "새 매도 기준 후보가 확인됐습니다. 실제 적용 여부는 현재 적용 기준과 별도로 검토해야 합니다.";
  const auditNextStep = !currentValidationAudit
    ? "현재 20종목 연구를 그대로 두고 신뢰성 검증만 실행합니다."
    : auditNeedsSourceData
      ? "연구 원자료를 준비한 뒤 신뢰성 검증을 다시 실행합니다."
      : auditHasCalculationProblem
        ? "계산 불일치 원인을 수정한 뒤 연구를 다시 실행하는 것이 우선입니다."
        : auditSensitiveCount > 0
          ? "더 많은 종목에서도 같은 결론이 유지되는지 재검증하는 것이 좋습니다."
          : "다른 종목 표본에서도 같은 결론이 반복되는지 확인하면 결과의 적용 범위를 더 분명히 할 수 있습니다.";
  const researchMaxHoldingDays = Number(validationReport?.validation_config?.max_holding_days ?? selectedHolding);
  const currentValidationStockCount = operationalValidationReport?.validated_stocks?.length ?? operationalValidationReport?.selected_stocks?.length ?? 0;
  const availableExpandedTargets = ([20, 40, 60] as const).filter((value) => value > currentValidationStockCount);
  const expandedComparison = expandedValidationReport?.expanded_revalidation ?? null;
  const expandedChangedRows = expandedComparison?.strategies?.filter((row) => !row.status_same) ?? [];
  const expandedSameRows = expandedComparison?.strategies?.filter((row) => row.status_same) ?? [];
  const expandedOutcome = expandedOutcomeText(expandedComparison ?? undefined);
  const expandedBaseSummary = (expandedComparison?.base_summary ?? {}) as Partial<NonNullable<ExitPolicyValidationReport["summary"]>>;
  const expandedAfterSummary = (expandedComparison?.expanded_summary ?? {}) as Partial<NonNullable<ExitPolicyValidationReport["summary"]>>;
  const expandedProgress = expandedOverallProgress(
    expandedJob,
    expandedTarget,
    expandedComparison?.base_stock_count ?? validationReport?.validated_stocks?.length ?? 0,
  );
  const completedValidation = validationReport?.status === "COMPLETED" && !validationBusy;
  const setupTabActive = view === "setup";
  const resultTabActive = view === "result";
  const zeroSummaryLabels = validationReport?.summary
    ? [
        validationReport.summary.selected === 0 ? "새 기준 후보" : "",
        validationReport.summary.baseline_better === 0 ? "기존 기준 유지" : "",
        validationReport.summary.unresolved === 0 ? "판단 보류" : "",
        validationReport.summary.insufficient_sample === 0 ? "표본 부족" : "",
      ].filter(Boolean)
    : [];
  const researchConclusionTitle = validationReport?.status === "COMPLETED"
    ? validationCandidates.length > 0 ? `새 매도 기준 후보 ${validationCandidates.length}개 확인` : "현재 매도 기준 유지"
    : "연구 결과 확인 필요";

  return (
    <section className="backtest-workspace multi-strategy-workspace" ref={workspaceTopRef}>
      <header className="multi-strategy-header">
        <div>
          <span>과거 성과 검증 · 10가지 전략 비교</span>
          <h1>10가지 투자 방법 자동 비교</h1>
          <p>종목 하나를 고르면 StockScope가 10가지 방법을 같은 과거 데이터로 비교합니다. 전문 용어를 몰라도 지금 어떤 방법이 맞는지와 사용자가 해야 할 일을 쉬운 말로 정리합니다.</p>
        </div>
        <div className="multi-strategy-flow" aria-label="전략 자동 검증 흐름">
          <span>1 · 종목 선택</span><i>→</i><span>2 · 10가지 방법 비교</span><i>→</i><span>3 · 지금 행동 안내</span>
        </div>
      </header>

      <nav className="backtest-subnav" aria-label="전략 검증 단계">
        <button type="button" className={setupTabActive ? "active" : ""} onClick={() => { setView("setup"); setMainSetupExpanded(true); scrollTop(); }}>1 · 설정</button>
        <button
          type="button"
          className={resultTabActive ? "active" : ""}
          disabled={!busy && !result && !error}
          onClick={() => { setView("result"); scrollTop(); }}
        >2 · 결과</button>
      </nav>

      {view === "setup" && (
        <div className="multi-strategy-setup">
          {completedValidation && (
            <button type="button" className="backtest-completed-setup-toggle" onClick={() => setMainSetupExpanded((open) => !open)}>
              <span><small>기본 검증 설정과 전략 설명</small><strong>{stockName || code || "선택 종목"} · {formatCompactDate(startDate)} ~ {formatCompactDate(endDate)} · 최대 {selectedHolding || "-"}거래일</strong></span>
              <b>{mainSetupExpanded ? "접기 ▲" : "설정 보기 ▼"}</b>
            </button>
          )}
          {(!completedValidation || mainSetupExpanded) && (
            <>
          <section className="multi-strategy-purpose">
            <div>
              <span>이 기능으로 무엇을 해결하나요?</span>
              <strong>“이 종목에서는 어떤 방법을 쓰는 게 맞지?”를 사용자가 직접 고르지 않게 합니다.</strong>
              <p>과거에 잘 맞았는지, 지금 시장과 맞는지, 현재 진입 조건이 준비됐는지를 StockScope가 계산한 뒤 쉬운 행동 안내로 정리합니다.</p>
            </div>
            <div className="multi-strategy-chip-list">
              {strategyGuides.map((guide) => (
                <span key={guide.professional}>
                  <b>{guide.easy}</b>
                  <small>{guide.professional} 전략</small>
                </span>
              ))}
            </div>
          </section>

          <section className="backtest-settings-card">
            <div className="backtest-section-title"><span>검증 설정</span><strong>10가지 방법은 StockScope가 자동으로 전부 비교합니다.</strong></div>
            <div className="backtest-stock-picker">
              <label htmlFor="backtest-stock-search">검증 종목</label>
              <div className="backtest-stock-search-box">
                <input
                  id="backtest-stock-search"
                  value={stockQuery}
                  placeholder="종목명 또는 종목코드 검색"
                  onFocus={() => stockSearchResults.length > 0 && setStockSearchOpen(true)}
                  onChange={(event) => { setStockQuery(event.target.value); setStockSearchOpen(true); }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && stockSearchResults[0]) {
                      event.preventDefault();
                      chooseStock(stockSearchResults[0]);
                    }
                  }}
                />
                <span>{stockSearchBusy ? "검색 중" : code ? `${market} · ${code}` : "종목을 선택하세요"}</span>
                {stockSearchOpen && stockQuery.trim().length >= 2 && stockQuery !== selectedStockLabel && (
                  <div className="backtest-stock-results">
                    {stockSearchResults.length > 0 ? stockSearchResults.map((item) => (
                      <button key={`${item.market}-${item.code}`} type="button" onClick={() => chooseStock(item)}>
                        <strong>{item.name}</strong><span>{item.market} · {item.code}</span>
                      </button>
                    )) : <p>{stockSearchBusy ? "종목을 찾는 중입니다..." : "검색 결과가 없습니다."}</p>}
                  </div>
                )}
              </div>
            </div>
            {stockSelectionDirty && <div className="backtest-selection-notice">검색 결과에서 종목을 선택해야 검증 대상이 변경됩니다.</div>}

            <div className="backtest-config-grid">
              <label><span>시작일</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
              <label><span>종료일</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
              <label><span>초기 자본 <small>성과 비교용</small></span><input type="number" min="1" step="100000" value={initialCapital} onChange={(event) => setInitialCapital(event.target.value)} /></label>
              <label><span>왕복 비용률 <small>모든 전략 동일</small></span><div className="backtest-input-suffix"><input type="number" min="0" max="5" step="0.01" value={costPct} onChange={(event) => setCostPct(event.target.value)} /><b>%</b></div></label>
            </div>

            <div className="holding-config">
              <div className="holding-title"><div><strong>최대 보유기간</strong><span>모든 전략에 동일한 보유기간을 적용해 비교 조건을 맞춥니다.</span></div><b>{selectedHolding || "-"} 거래일</b></div>
              <div className="holding-buttons">
                {holdingOptions.map((option) => (
                  <button key={option.days} type="button" className={!customHolding && maxHoldingDays === option.days ? "active" : ""} onClick={() => { setCustomHolding(""); setMaxHoldingDays(option.days); }}>{option.label}</button>
                ))}
                <label className={customHolding ? "active" : ""}><span>직접 입력</span><input type="number" min="1" max="120" placeholder="거래일" value={customHolding} onChange={(event) => setCustomHolding(event.target.value)} /></label>
              </div>
              <p className="holding-explanation">{holdingDescription}</p>
            </div>

            <details className="backtest-policy-details">
              <summary><span>공정하게 비교하기 위해 어떤 조건을 같게 하나요?</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>
              <div className="multi-strategy-method-brief">
                <p><b>과거 데이터</b> 10개 전략이 같은 KRX 데이터 한 벌을 사용합니다.</p>
                <p><b>진입 가격</b> 신호 다음 거래일 시가를 사용합니다.</p>
                <p><b>손절/매도</b> 같은 위험 관리 기준 + 1차 목표가 + 동일 보유기간을 사용합니다.</p>
                <p><b>추천 기준</b> 수익률 1등만 고르지 않고 표본·거래당 평균·이익/손실 비율·최대 낙폭·현재 상태를 함께 봅니다.</p>
              </div>
            </details>

            <div className="backtest-run-row multi-strategy-run-row">
              <div><strong>투자 방법을 직접 고를 필요가 없습니다.</strong><span>10가지 방법을 자동으로 비교하고 결과 화면에서 왜 이 방법이 맞는지와 지금 사용자가 해야 할 일을 보여줍니다.</span></div>
              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "10가지 방법 분석 중..." : "10가지 방법 자동 비교 시작"}</button>
            </div>
            {error && <div className="backtest-error"><strong>실행 실패</strong><span>{userFacingResearchText(error)}</span></div>}
          </section>
            </>
          )}
          {previousResearchMeta && !validationReport && (
            <section className="research-previous-banner">
              <div>
                <span>이전 연구 결과가 있습니다</span>
                <strong>{previousResearchMeta.stock_count}종목 · {formatCompactDate(previousResearchMeta.period.start)} ~ {formatCompactDate(previousResearchMeta.period.end)}</strong>
                <small>저장된 결과는 유지되지만 새 브라우저 세션에서는 자동으로 결과 화면을 열지 않습니다.</small>
              </div>
              <button type="button" disabled={previousResearchBusy} onClick={() => void loadStoredResearch(previousResearchMeta.signature)}>
                {previousResearchBusy ? "불러오는 중..." : "이전 결과 보기"}
              </button>
            </section>
          )}
          <details className="exit-validation-panel" open={validationPanelOpen} onToggle={(event) => setValidationPanelOpen(event.currentTarget.open)}>
            <summary><span>매도 기준 연구 작업공간</span><DetailToggleText closed="열기 ▼" open="접기 ▲" /></summary>
            <div className={`exit-validation-body research-workspace research-section-${researchSection.toLowerCase()}`}>
              <nav className="research-workspace-nav" aria-label="매도 기준 연구 화면">
                <button type="button" className={researchSection === "SUMMARY" ? "active" : ""} disabled={!validationReport} onClick={() => void openResearchSection("SUMMARY")}>요약</button>
                <button type="button" className={researchSection === "RUN" ? "active" : ""} onClick={() => void openResearchSection("RUN")}>연구 실행</button>
                <button type="button" className={researchSection === "RESULTS" ? "active" : ""} disabled={!validationReport} onClick={() => void openResearchSection("RESULTS")}>연구 결과</button>
                <button type="button" className={researchSection === "RELIABILITY" ? "active" : ""} disabled={!validationReport} onClick={() => void openResearchSection("RELIABILITY")}>신뢰성</button>
                <button type="button" className={researchSection === "EXPANDED" ? "active" : ""} disabled={!validationReport} onClick={() => { void openResearchSection("EXPANDED"); if (!expandedPlan && availableExpandedTargets.length > 0) void loadExpandedPlan(expandedTarget); }}>확대 검증</button>
                <button type="button" className={researchSection === "HISTORY" ? "active" : ""} onClick={() => void openResearchSection("HISTORY")}>연구 기록</button>
              </nav>
              {validationReport && researchSection !== "RUN" && researchSection !== "HISTORY" && (
                <div className="research-workspace-context">
                  <span>{researchReportSource === "PREVIOUS_RUN" ? "저장된 이전 연구 결과" : "현재 세션 연구 결과"}</span>
                  <strong>{(expandedValidationReport ?? validationReport).validated_stocks?.length ?? (expandedValidationReport ?? validationReport).selected_stocks?.length ?? 0}종목 · {formatCompactDate((expandedValidationReport ?? validationReport).period.start)} ~ {formatCompactDate((expandedValidationReport ?? validationReport).period.end)}</strong>
                </div>
              )}
              {!validationReport && researchSection !== "RUN" && researchSection !== "HISTORY" && (
                <section className="research-workspace-empty">
                  <strong>표시할 연구 결과가 없습니다.</strong>
                  <p>새 연구를 실행하거나 저장된 이전 연구 결과를 불러온 뒤 이 화면을 확인할 수 있습니다.</p>
                  {previousResearchMeta && <button type="button" disabled={previousResearchBusy} onClick={() => void loadStoredResearch(previousResearchMeta.signature)}>이전 결과 불러오기</button>}
                </section>
              )}
              {researchSection === "RUN" && (<>
              <details
                className="exit-validation-setup-collapse"
                open={validationSetupOpen}
                onToggle={(event) => setValidationSetupOpen(event.currentTarget.open)}
              >
                <summary>
                  <span>{validationReport?.status === "COMPLETED" && !validationBusy ? "연구 조건 및 다시 실행" : "연구 조건 설정"}</span>
                  <DetailToggleText closed="조건 보기 ▼" open="조건 숨기기 ▲" />
                </summary>
                <div className="exit-validation-setup-collapse-body">
                  <div className="exit-validation-intro">
                    <div><strong>2차 목표가 도달 후 어떤 수익 실현 방식이 더 나았는지 비교합니다.</strong><p>저장된 과거 시세가 충분한 종목만 비교에 사용합니다. 추가 시세 다운로드 없이 저장된 데이터만 사용하며, 이 결과가 현재 매도 기준을 자동으로 바꾸지는 않습니다.</p></div>
                    <span>연구용 비교 · 현재 매도 기준 변경 없음</span>
                  </div>
                  <div className="exit-validation-config-summary">
                    <span><b>기간</b>{formatCompactDate(startDate)} ~ {formatCompactDate(endDate)}</span>
                    <span><b>시장</b>KOSPI + KOSDAQ</span>
                    <span><b>최대 표본</b>20종목</span>
                    <span><b>최소 데이터 보유율</b>90%</span>
                  </div>
                  <div className="exit-validation-actions">
                    <button type="button" disabled={validationBusy} onClick={() => void runExitPolicyValidation(false)}>{validationBusy ? "매도 기준 비교 중..." : validationReport ? "같은 조건으로 검증/이어하기" : "매도 기준 비교 시작"}</button>
                    {validationReport && <button type="button" className="secondary" disabled={validationBusy} onClick={() => void runExitPolicyValidation(true)}>전체 연구 다시 계산</button>}
                    {validationBusy && <button type="button" className="secondary" onClick={() => void cancelExitPolicyValidation()}>검증 중단</button>}
                  </div>
                </div>
              </details>
              {validationBusy && validationJob && validationProgress && (
                <div className="exit-validation-progress-overview">
                  <div className="exit-validation-progress-head">
                    <div>
                      <span>전체 연구 진행률</span>
                      <strong>{validationProgress.percent.toFixed(1)}%</strong>
                      <p>{validationProgress.completed} / {validationProgress.total || "-"} 종목 처리 완료 · 완료 종목 기준</p>
                    </div>
                    <b>{validationJob.elapsed_seconds.toFixed(1)}초</b>
                  </div>
                  <progress max={100} value={validationProgress.percent} />
                  <div className="exit-validation-current-task">
                    <span><small>현재 작업</small><strong>{validationProgress.currentTask}</strong></span>
                    <span><small>현재 종목</small><strong>{validationProgress.currentCode}</strong></span>
                    <span><small>진행 위치</small><strong>{validationProgress.currentStockIndex || "-"} / {validationProgress.total || "-"}</strong></span>
                    <span><small>추가 시세 요청</small><strong>{Number(validationJob.progress.details.network_requests ?? 0)}회</strong></span>
                  </div>
                  <details className="exit-validation-progress-details">
                    <summary><span>세부 진행 상황 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
                    <div>
                      <span><b>현재 세부 단계</b>{userFacingResearchText(validationJob.progress.message)}</span>
                      <span><b>현재 종목 내부 진행</b>{validationProgress.localCurrent} / {validationProgress.localTotal || "-"} · {validationProgress.localPercent.toFixed(1)}%</span>
                      <span><b>현재 전략</b>{validationProgress.strategy ?? "-"}</span>
                      <span><b>비교 방식</b>{validationProgress.policy ?? "-"}</span>
                    </div>
                    {validationProgress.strategy && validationStrategyProgressRows(validationProgress.localCurrent, validationProgress.localTotal).length > 0 && (
                      <div className="exit-validation-strategy-progress-list">
                        {validationStrategyProgressRows(validationProgress.localCurrent, validationProgress.localTotal).map((row) => (
                          <span key={`progress-${row.strategy}`} className={row.percent >= 100 ? "done" : row.percent > 0 ? "active" : "waiting"}>
                            <b>{strategyDisplayLabel(row.strategy)}</b>
                            <small>{row.percent >= 100 ? "완료" : row.percent <= 0 ? "대기" : `${row.completed} / ${row.total} · ${row.percent.toFixed(0)}%`}</small>
                          </span>
                        ))}
                      </div>
                    )}
                  </details>
                </div>
              )}
              {validationError && <div className="backtest-error"><strong>매도 기준 비교 실패</strong><span>{userFacingResearchText(validationError)}</span></div>}
              </>)}
              {researchSection === "HISTORY" && (
                <section className="research-history-panel">
                  <div className="research-history-head">
                    <div><span>연구 기록</span><strong>이전에 저장한 연구를 선택해 다시 볼 수 있습니다.</strong></div>
                    <button type="button" className="secondary" disabled={researchHistoryBusy} onClick={() => void refreshResearchHistory(30)}>{researchHistoryBusy ? "불러오는 중..." : "기록 새로고침"}</button>
                  </div>
                  {researchHistoryError && <div className="backtest-error"><strong>기록 조회 실패</strong><span>{researchHistoryError}</span></div>}
                  {!researchHistoryBusy && researchHistory.length === 0 && !researchHistoryError && (
                    <div className="research-history-empty">저장된 연구 기록이 없습니다.</div>
                  )}
                  <div className="research-history-list">
                    {researchHistory.map((item) => (
                      <article key={`research-history-${item.signature}`} className={item.signature === (expandedValidationReport ?? validationReport)?.signature ? "active" : ""}>
                        <div>
                          <span>{item.is_expanded ? `확대 검증 · ${item.expanded_from ?? "-"} → ${item.stock_count}종목` : `기본 연구 · ${item.stock_count}종목`}</span>
                          <strong>{formatCompactDate(item.period.start)} ~ {formatCompactDate(item.period.end)} · 최대 {item.max_holding_days ?? "-"}거래일</strong>
                          <small>새 후보 {item.summary.selected} · 기존 유지 {item.summary.baseline_better} · 판단 보류 {item.summary.unresolved}</small>
                        </div>
                        <button type="button" disabled={previousResearchBusy} onClick={() => void loadStoredResearch(item.signature)}>결과 보기</button>
                      </article>
                    ))}
                  </div>
                </section>
              )}
              {validationReport && (
                <div className="exit-validation-report" ref={validationReportRef}>
                  <section className="exit-validation-result-hero">
                    <div className="exit-validation-result-hero-top">
                      <span>이번 연구의 결론</span>
                      <b>{validationReport.status === "COMPLETED" ? (validationCandidates.length > 0 ? `새 후보 ${validationCandidates.length}개` : "변경 근거 없음") : "데이터 확인 필요"}</b>
                    </div>
                    <h2>{researchConclusionTitle}</h2>
                    <p>{validationConclusionHeadline(validationReport)}</p>
                    <div className="exit-validation-hero-policy">
                      <span>현재 적용 기준</span>
                      <strong>{productionOverview.known ? (productionOverview.baselineOnly ? "1차 목표가 도달 시 전량 매도" : "전략별 매도 기준 적용 중") : "서버에서 현재 기준 확인 중"}</strong>
                      {productionOverview.known && <small>{productionOverview.baselineOnly ? "기존 기준 사용 중" : `${productionOverview.changedRows.length}개 전략에 별도 기준 적용`}</small>}
                    </div>
                    {validationReport.summary && (
                      <>
                        <div className="exit-validation-hero-summary">
                          {validationReport.summary.selected > 0 && <span className="candidate"><small>새 기준 후보</small><b>{validationReport.summary.selected}</b></span>}
                          {validationReport.summary.baseline_better > 0 && <span><small>기존 기준 유지</small><b>{validationReport.summary.baseline_better}</b></span>}
                          {validationReport.summary.unresolved > 0 && <span><small>판단 보류</small><b>{validationReport.summary.unresolved}</b></span>}
                          {validationReport.summary.insufficient_sample > 0 && <span><small>표본 부족</small><b>{validationReport.summary.insufficient_sample}</b></span>}
                        </div>
                        {zeroSummaryLabels.length > 0 && <small className="exit-validation-zero-summary">0건 · {zeroSummaryLabels.join(" · ")}</small>}
                      </>
                    )}
                    <small className="exit-validation-result-period">{formatCompactDate(validationReport.period.start)} ~ {formatCompactDate(validationReport.period.end)} · 저장된 시세 데이터 기준</small>
                  </section>

                  {researchSection === "EXPANDED" && expandedComparison && expandedOutcome && (
                    <section className={`exit-validation-expanded-result outcome-${String(expandedComparison.outcome ?? "mixed").toLowerCase()}`}>
                      <div className="exit-validation-section-title">
                        <span>확대 표본 검증 결론</span>
                        <strong>{expandedComparison.base_stock_count}종목 → {expandedComparison.expanded_stock_count}종목</strong>
                      </div>
                      <h3>{expandedOutcome.title}</h3>
                      <p>{expandedOutcome.detail}</p>

                      <div className="exit-validation-expanded-before-after">
                        <div>
                          <span>기존 연구 · {expandedComparison.base_stock_count}종목</span>
                          <b>새 후보 {expandedBaseSummary.selected ?? 0}</b>
                          <small>기존 유지 {expandedBaseSummary.baseline_better ?? 0} · 판단 보류 {expandedBaseSummary.unresolved ?? 0}</small>
                        </div>
                        <i>→</i>
                        <div>
                          <span>확대 연구 · {expandedComparison.expanded_stock_count}종목</span>
                          <b>새 후보 {expandedAfterSummary.selected ?? 0}</b>
                          <small>기존 유지 {expandedAfterSummary.baseline_better ?? 0} · 판단 보류 {expandedAfterSummary.unresolved ?? 0}</small>
                        </div>
                      </div>

                      <div className="exit-validation-expanded-result-summary">
                        <span><small>같은 결론 유지</small><b>{expandedComparison.same_status_count} / {expandedComparison.strategy_count}</b></span>
                        <span className={expandedComparison.changed_status_count > 0 ? "changed" : ""}><small>결론 변경</small><b>{expandedComparison.changed_status_count}개</b></span>
                        <span><small>이전 민감 전략 중 결론 유지</small><b>{expandedComparison.previously_sensitive_same_status ?? 0}개</b></span>
                      </div>

                      <div className="exit-validation-expanded-next-action">
                        <span>그래서 지금은?</span>
                        <strong>{expandedOutcome.action}</strong>
                      </div>

                      {expandedChangedRows.length > 0 && (
                        <div className="exit-validation-expanded-changes">
                          <strong>결론이 달라진 전략</strong>
                          <div>
                            {expandedChangedRows.map((row) => (
                              <span key={`expanded-change-${row.strategy}`}>
                                <b>{strategyDisplayLabel(row.strategy)}</b>
                                <small>{exitPolicyStatusLabel(row.before_status)} → {exitPolicyStatusLabel(row.after_status)}</small>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {expandedSameRows.length > 0 && (
                        <details className="exit-validation-expanded-same">
                          <summary><span>같은 결론을 유지한 전략 {expandedSameRows.length}개</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
                          <div>{expandedSameRows.map((row) => <span key={`expanded-same-${row.strategy}`}>{strategyDisplayLabel(row.strategy)}</span>)}</div>
                        </details>
                      )}
                    </section>
                  )}

                  {researchSection === "EXPANDED" && validationReport.status === "COMPLETED" && (
                    <section className="research-expanded-workspace">
                      <div className="research-expanded-workspace-head">
                        <div><span>확대 표본 검증</span><strong>기존 연구의 조건을 유지한 채 종목 수만 늘려 결론이 유지되는지 확인합니다.</strong></div>
                        <b>{currentValidationStockCount}종목 기준</b>
                      </div>
                      {availableExpandedTargets.length > 0 ? (
                        <>
                          <div className="exit-validation-expanded-targets">
                            {availableExpandedTargets.map((target) => (
                              <button key={`workspace-expanded-target-${target}`} type="button" className={expandedTarget === target ? "active" : ""} onClick={() => { setExpandedTarget(target); setExpandedPlan(null); setExpandedPlanOpen(true); void loadExpandedPlan(target); }}>
                                {target}종목{target === 40 && currentValidationStockCount < 40 ? " · 권장" : ""}
                              </button>
                            ))}
                          </div>
                          {!expandedPlan && !expandedPlanBusy && (
                            <button type="button" className="expanded-sample-open" onClick={() => { setExpandedPlanOpen(true); void loadExpandedPlan(expandedTarget); }}>확대 검증 준비 상태 확인</button>
                          )}
                          {expandedPlanBusy && <p className="exit-validation-expanded-message">저장된 시세 데이터에서 확대 검증 가능 여부를 확인하고 있습니다.</p>}
                          {expandedError && <div className="exit-validation-expanded-error">{expandedError}</div>}
                          {expandedPlan && !expandedPlanBusy && (
                            <>
                              <div className="exit-validation-expanded-plan-summary">
                                <span><small>현재 연구</small><b>{expandedPlan.base_stock_count}종목</b></span>
                                <span><small>확대 목표</small><b>{expandedPlan.target_stock_count}종목</b></span>
                                <span><small>바로 사용 가능</small><b>{expandedPlan.ready_stock_count}종목</b></span>
                                <span><small>시장 구성</small><b>{Object.entries(expandedPlan.target_market_counts).map(([name, count]) => `${name} ${count}`).join(" · ") || "-"}</b></span>
                              </div>
                              <p className="exit-validation-expanded-note">기존 {expandedPlan.base_stock_count}종목 결과는 가능한 한 재사용하고, 새로 추가되는 종목만 계산합니다. 기간·거래비용·최대 보유기간·전략·매도 후보는 기존 연구와 동일하게 유지합니다.</p>
                              {expandedPlan.ready_to_run ? (
                                <div className="exit-validation-expanded-actions ready">
                                  <div><b>추가 다운로드 없이 바로 재검증할 수 있습니다.</b><small>저장된 시세 데이터만 사용합니다.</small></div>
                                  <button type="button" disabled={expandedBusy} onClick={() => void runExpandedValidation()}>{expandedBusy ? "재검증 중..." : `${expandedPlan.target_stock_count}종목으로 다시 검증`}</button>
                                </div>
                              ) : expandedPlan.data_preparation.can_prepare ? (
                                <div className="exit-validation-expanded-actions prepare">
                                  <div><b>일부 과거 시세를 먼저 준비해야 합니다.</b><small>부족한 날짜 {expandedPlan.data_preparation.missing_history_items}개 · 예상 추가 KRX 요청 {expandedPlan.data_preparation.estimated_network_requests ?? "확인 중"}회</small></div>
                                  <button type="button" disabled={expandedPrepareBusy} onClick={() => void prepareExpandedData()}>{expandedPrepareBusy ? "데이터 준비 중..." : "검증 데이터 준비"}</button>
                                </div>
                              ) : (
                                <div className="exit-validation-expanded-actions unavailable"><b>현재 저장 데이터만으로 목표 표본을 만들 수 없습니다.</b><small>{expandedPlan.data_preparation.note}</small></div>
                              )}
                            </>
                          )}
                          {expandedPrepareBusy && expandedPrepareJob && (
                            <div className="exit-validation-expanded-progress workflow"><div className="expanded-progress-step"><span>2 / 5 · 필요한 시세 준비</span><b>{expandedPrepareJob.progress.percent.toFixed(1)}%</b></div><progress max="100" value={expandedPrepareJob.progress.percent} /><small>{expandedPrepareJob.progress.current.toLocaleString()} / {expandedPrepareJob.progress.total.toLocaleString()} 준비 완료 · 기존 저장 데이터는 다시 받지 않습니다.</small></div>
                          )}
                          {expandedBusy && expandedJob && expandedProgress && (
                            <div className="exit-validation-expanded-progress workflow overall">
                              <div className="expanded-progress-step"><span>3 / 5 · 종목별 연구 중</span><b>{expandedProgress.percent.toFixed(1)}%</b></div>
                              <strong className="expanded-progress-main">{expandedProgress.completed} / {expandedProgress.total}종목 완료</strong>
                              <progress max="100" value={expandedProgress.percent} />
                              <div className="expanded-progress-stats"><span><small>기존 결과 재사용</small><b>{expandedProgress.reused}종목</b></span><span><small>새 계산 완료</small><b>{expandedProgress.calculated}종목</b></span><span><small>현재 종목</small><b>{expandedProgress.currentCode || "-"}</b></span></div>
                              {(expandedProgress.internalMessage || expandedProgress.internalPercent > 0) && (<details className="expanded-progress-detail"><summary><span>세부 작업 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary><p>{expandedProgress.internalMessage || "현재 종목의 세부 매도 기준을 비교하고 있습니다."} {expandedProgress.internalPercent > 0 ? `· 종목 내부 ${expandedProgress.internalPercent.toFixed(0)}%` : ""}</p></details>)}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="research-expanded-complete">현재 결과가 이미 최대 60종목 표본입니다. 추가 확대 대상이 없습니다.</div>
                      )}
                    </section>
                  )}

                  {validationReport.status === "COMPLETED" && (
                    <section className="exit-validation-current-policy readable">
                      <div className="exit-validation-section-title">
                        <span>현재 기준 상세</span>
                        <strong>유지한다는 기준이 무엇인지 바로 확인할 수 있습니다.</strong>
                      </div>
                      {productionStatusError ? (
                        <div className="exit-validation-current-policy-error">
                          <span>현재 실제 적용 기준을 서버에서 확인하지 못했습니다. 연구 결과만으로 적용 상태를 추측하지 않습니다.</span>
                          <button type="button" onClick={() => void refreshProductionStatus(2)}>다시 확인</button>
                        </div>
                      ) : productionOverview.known ? (
                        <>
                          <div className="exit-validation-current-policy-list">
                            <div><span>수익 실현</span><strong>{productionOverview.baselineOnly ? "1차 목표가 도달 시 전량 매도" : "전략별 적용 기준 사용"}</strong></div>
                            <div><span>손절</span><strong>전략 분석에서 계산된 손절선에 먼저 도달하면 종료</strong></div>
                            <div><span>최대 보유</span><strong>이번 연구 {Number.isFinite(researchMaxHoldingDays) ? `${researchMaxHoldingDays}거래일` : "-"}</strong></div>
                            <div><span>2차 목표가</span><strong>{productionOverview.baselineOnly ? "현재는 참고 가격" : "수익 보호 기준이 적용된 전략에서 활용"}</strong></div>
                          </div>
                          {!productionOverview.baselineOnly && productionOverview.changedRows.length > 0 && (
                            <details className="exit-validation-current-policy-details">
                              <summary><span>전략별 실제 적용 기준 보기</span><DetailToggleText /></summary>
                              <div>
                                {productionOverview.changedRows.map(([strategy, policy]) => <span key={`production-${strategy}`}><b>{strategy}</b><small>{policy}</small></span>)}
                              </div>
                            </details>
                          )}
                          <p className="exit-validation-current-policy-note">연구 결과와 실제 적용 기준은 별도입니다. 연구에서 새 후보가 나와도 실제 적용 기준은 자동으로 바뀌지 않습니다.</p>
                        </>
                      ) : (
                        <p className="exit-validation-current-policy-note">현재 실제 적용 기준을 불러오는 중입니다.</p>
                      )}
                    </section>
                  )}

                  {validationReport.status === "COMPLETED" && validationReport.summary && (
                    <section className="exit-validation-why">
                      <div className="exit-validation-section-title">
                        <span>{validationReport.summary.selected === 0 ? "왜 현재 기준을 유지하나요?" : "왜 이런 결론이 나왔나요?"}</span>
                        <strong>상태 숫자보다 실제 판단 이유를 먼저 봅니다.</strong>
                      </div>
                      <div className="exit-validation-why-grid">
                        {validationReport.summary.selected > 0 && <span><b>새 기준 후보 {validationReport.summary.selected}개</b><small>기존 기준보다 핵심 수익·위험 지표에서 불리하지 않으면서 개선된 방식이 확인됐습니다.</small></span>}
                        {validationReport.summary.baseline_better > 0 && <span><b>기존 기준 유지 {validationReport.summary.baseline_better}개</b><small>비교한 새 방식들이 기존 기준보다 수익과 위험을 함께 개선하지 못했습니다.</small></span>}
                        {validationReport.summary.unresolved > 0 && <span><b>판단 보류 {validationReport.summary.unresolved}개</b><small>일부 지표는 좋아졌지만 다른 핵심 지표가 나빠 어느 방식이 더 낫다고 확정하기 어려웠습니다.</small></span>}
                        {validationReport.summary.insufficient_sample > 0 && <span><b>표본 부족 {validationReport.summary.insufficient_sample}개</b><small>종목 또는 거래 표본이 부족해 새 기준 판단을 보류하고 기존 기준을 유지했습니다.</small></span>}
                      </div>
                    </section>
                  )}

                  {researchSection === "SUMMARY" && validationReport.status === "COMPLETED" && (
                    <section className="research-summary-navigation">
                      <button type="button" onClick={() => void openResearchSection("RESULTS")}><span>전략별 연구 결과</span><strong>{validationRows.length}개 전략 비교 보기</strong></button>
                      <button type="button" onClick={() => void openResearchSection("RELIABILITY")}><span>신뢰성</span><strong>{currentValidationAudit ? `결론 유지 ${auditStableCount} · 민감 ${auditSensitiveCount}` : "결과를 얼마나 참고할지 확인"}</strong></button>
                      <button type="button" onClick={() => { void openResearchSection("EXPANDED"); if (!expandedPlan && availableExpandedTargets.length > 0) void loadExpandedPlan(expandedTarget); }}><span>확대 검증</span><strong>{expandedComparison ? `${expandedComparison.base_stock_count} → ${expandedComparison.expanded_stock_count}종목 결과 보기` : "더 넓은 표본에서 재확인"}</strong></button>
                    </section>
                  )}

                  {validationReport.status === "COMPLETED" && (
                    <section className={`exit-validation-reliability status-${(currentValidationAudit?.status ?? "unchecked").toLowerCase()}`}>
                      <div className="exit-validation-reliability-head">
                        <div>
                          <span>연구 결과 신뢰성</span>
                          <strong>{auditMainHeadline}</strong>
                          <p>검사 항목 자체보다, 이번 연구 결과를 어느 정도 참고할 수 있는지와 다음에 무엇을 확인해야 하는지를 먼저 보여드립니다.</p>
                        </div>
                        <button type="button" disabled={validationAuditBusy || !selectedResearchIsLatest} onClick={() => void runValidationAudit()}>
                          {validationAuditBusy ? "검증 중..." : !selectedResearchIsLatest ? "최신 연구에서 검증 가능" : currentValidationAudit ? "현재 연구 다시 검증" : "신뢰성 검증 실행"}
                        </button>
                      </div>

                      {validationAuditError && <div className="exit-validation-reliability-error">{validationAuditError}</div>}
                      {!selectedResearchIsLatest && <div className="exit-validation-reliability-error">선택한 과거 연구는 저장된 결과를 볼 수 있지만 신뢰성 재검증은 최신 연구에서만 실행할 수 있습니다.</div>}

                      {currentValidationAudit && (
                        <>
                          <section className={`exit-validation-reliability-summary-card ${auditHasCalculationProblem || auditNeedsSourceData ? "needs-attention" : ""}`}>
                            <div className="exit-validation-reliability-summary-copy">
                              <span>이 연구 결과를 어떻게 봐야 할까요?</span>
                              <strong>{auditMainHeadline}</strong>
                              <p>{auditHasCalculationProblem
                                ? "현재 연구 결과를 기준 변경에 사용하기 전에 계산 불일치 원인을 먼저 확인해야 합니다."
                                : auditNeedsSourceData
                                  ? "저장된 원자료가 부족해 지금은 연구 결과의 안정성을 충분히 확인하기 어렵습니다."
                                  : auditSensitiveCount > 0
                                    ? `이번 결과는 참고할 수 있지만, ${auditSensitiveCount}개 전략이 종목 구성에 민감해 새 기준 변경 근거로 보기에는 아직 부족합니다.`
                                    : "계산 결과와 종목 구성 변경에 대한 재검증에서도 결론이 안정적으로 유지됐습니다."}</p>
                            </div>
                            <div className="exit-validation-reliability-key-numbers">
                              <span><small>결론이 유지된 전략</small><b>{auditStableCount}개</b></span>
                              <span className={auditSensitiveCount > 0 ? "sensitive" : ""}><small>종목 구성에 민감</small><b>{auditSensitiveCount}개</b></span>
                            </div>
                          </section>

                          {auditSensitiveRows.length > 0 && (
                            <section className="exit-validation-reliability-sensitive-list">
                              <div>
                                <span>종목 구성의 영향을 받은 전략</span>
                                <strong>이 전략들은 종목 하나의 포함 여부에 따라 결론이 달라질 수 있습니다.</strong>
                              </div>
                              <div className="exit-validation-reliability-chips">
                                {auditSensitiveRows.map((row) => <b key={`sensitive-chip-${row.strategy}`}>{strategyDisplayLabel(row.strategy)}</b>)}
                              </div>
                            </section>
                          )}

                          {auditStableRows.length > 0 && (
                            <details className="exit-validation-reliability-details compact">
                              <summary><span>안정적으로 결론이 유지된 전략 {auditStableRows.length}개</span><DetailToggleText closed="전략 보기 ▼" open="숨기기 ▲" /></summary>
                              <div className="exit-validation-reliability-chips stable">
                                {auditStableRows.map((row) => <b key={`stable-chip-${row.strategy}`}>{strategyDisplayLabel(row.strategy)}</b>)}
                              </div>
                            </details>
                          )}

                          <section className={`exit-validation-reliability-judgment compact ${auditHasCalculationProblem || auditNeedsSourceData ? "needs-attention" : ""}`}>
                            <span>현재 판단에 미치는 영향</span>
                            <strong>{auditCurrentJudgment}</strong>
                            <p>현재 적용 기준: <b>{productionOverview.known ? (productionOverview.baselineOnly ? "1차 목표가 도달 시 전량 매도" : "전략별 매도 기준 적용 중") : "서버에서 확인 중"}</b></p>
                          </section>

                          <section className="exit-validation-reliability-next emphasized">
                            <span>다음 확인</span>
                            <strong>{auditNextStep}</strong>
                            {!auditHasCalculationProblem && !auditNeedsSourceData && auditSensitiveCount > 0 && (
                              <p>현재 {currentValidationStockCount}종목에서 민감했던 {auditSensitiveCount}개 전략이 더 넓은 종목 표본에서도 같은 결론을 보이는지 확인합니다.</p>
                            )}
                            {!auditHasCalculationProblem && !auditNeedsSourceData && <small>이 단계에서는 연구 결과나 현재 매도 기준을 자동으로 변경하지 않습니다.</small>}
                            {!auditHasCalculationProblem && !auditNeedsSourceData && availableExpandedTargets.length > 0 && (
                              <button type="button" className="expanded-sample-open" onClick={() => { void openResearchSection("EXPANDED"); setExpandedPlanOpen(true); void loadExpandedPlan(expandedTarget); }}>확대 검증으로 이동</button>
                            )}
                          </section>

                          <div className="exit-validation-reliability-limit-note">
                            <b>참고</b>
                            <span>{auditPolicyDependentCount > 0
                              ? "매도 방식에 따라 보유기간과 이후 진입 기회가 달라질 수 있어 모든 거래가 완전히 동일한 1:1 비교는 아닙니다."
                              : "저장된 표본에서는 매도 방식에 따른 후속 거래 건수 차이가 확인되지 않았습니다."}</span>
                          </div>

                          {auditPolicyDependentCount > 0 && (
                            <details className="exit-validation-reliability-details compact">
                              <summary><span>비교 방식 자세히 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
                              <div className="exit-validation-reliability-plain-detail">
                                한 매도 방식은 포지션을 일찍 종료하고 다른 방식은 더 오래 보유할 수 있습니다. 이 차이 때문에 같은 기간 중 다음 진입 신호를 받을 수 있는 기회도 달라질 수 있습니다. 따라서 이번 연구는 동일한 최초 조건에서 시작하지만 모든 후속 거래를 완전히 고정한 1:1 비교는 아닙니다.
                              </div>
                            </details>
                          )}

                          <details className="exit-validation-reliability-details user-facing">
                            <summary><span>전략별 안정성 자세히 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
                            <div className="exit-validation-reliability-detail-body">
                              <div className="exit-validation-reliability-strategies">
                                {currentValidationAudit.strategies?.map((row) => {
                                  const changedLabels = Array.from(new Set((row.leave_one_out?.unstable_removed_stocks ?? []).map((item) => item.status_label).filter(Boolean)));
                                  const sensitive = row.leave_one_out?.status === "SENSITIVE";
                                  return (
                                    <article key={`audit-${row.strategy}`} className={sensitive ? "sensitive" : "stable"}>
                                      <header><strong>{strategyDisplayLabel(row.strategy)}</strong><b>{sensitive ? "종목 구성에 민감" : "결론 유지"}</b></header>
                                      <p className="exit-validation-reliability-strategy-conclusion">원래 연구 결론: <b>{row.research_status_label}</b></p>
                                      <p>{sensitive
                                        ? `특정 종목을 제외하면 ${changedLabels.length > 0 ? changedLabels.join(" 또는 ") : "다른 결론"}으로 바뀌는 경우가 있어 현재 결론을 확정적으로 보기 어렵습니다.`
                                        : "어떤 종목 하나를 제외해도 같은 연구 결론이 유지됐습니다."}</p>
                                      <div>
                                        <span><small>거래 표본</small><b>{row.baseline_sample?.trades ?? 0}건</b></span>
                                        <span><small>거래 발생 종목</small><b>{row.baseline_sample?.participating_stocks ?? 0}개</b></span>
                                        <span><small>한 종목 최대 거래 비중</small><b>{row.baseline_sample?.largest_stock_trade_share_pct == null ? "-" : `${row.baseline_sample.largest_stock_trade_share_pct.toFixed(1)}%`}</b></span>
                                        <span><small>한 종목씩 제외 후 결론 유지</small><b>{row.leave_one_out?.runs ? `${row.leave_one_out.same_status ?? 0}/${row.leave_one_out.runs}` : "-"}</b></span>
                                      </div>
                                    </article>
                                  );
                                })}
                              </div>
                            </div>
                          </details>

                          <details className="exit-validation-reliability-details technical">
                            <summary><span>검증 상세 내용 보기</span><DetailToggleText closed="보기 ▼" open="숨기기 ▲" /></summary>
                            <div className="exit-validation-reliability-detail-body">
                              <div className="exit-validation-reliability-checks">
                                <span><small>데이터 커버리지</small><b>{researchAuditCheckLabel(currentValidationAudit.checks?.data_coverage?.status)}</b></span>
                                <span><small>집계 수치 재계산</small><b>{researchAuditCheckLabel(currentValidationAudit.checks?.aggregate_replay?.status)}</b></span>
                                <span><small>연구 판정 재현</small><b>{researchAuditCheckLabel(currentValidationAudit.checks?.decision_replay?.status)}</b></span>
                                <span><small>미래 데이터 처리 규칙</small><b>{researchAuditCheckLabel(currentValidationAudit.checks?.guardrails?.status)}</b></span>
                                <span><small>종목 하나 제거 검증</small><b>{researchAuditCheckLabel(currentValidationAudit.checks?.leave_one_out?.status)}</b></span>
                                <span><small>후속 진입 기회 영향</small><b>{auditPolicyDependentCount > 0 ? "방식에 따라 달라질 수 있음" : "확인된 건수 차이 없음"}</b></span>
                              </div>

                              <div className="exit-validation-reliability-data">
                                <div>
                                  <span>검증에 사용한 종목</span>
                                  <strong>{Object.entries(currentValidationAudit.checks?.data_coverage?.market_counts ?? {}).map(([name, count]) => `${name} ${count}개`).join(" · ") || "-"}</strong>
                                  <small>최소 데이터 보유율 {formatNumber(currentValidationAudit.checks?.data_coverage?.minimum_coverage_pct, 1)}%</small>
                                </div>
                                <div>
                                  <span>집계 재계산</span>
                                  <strong>{currentValidationAudit.checks?.aggregate_replay?.checked_policy_aggregates ?? 0}개 정책 집계 확인</strong>
                                  <small>불일치 {auditAggregateMismatch}건</small>
                                </div>
                                <div>
                                  <span>판정 재현</span>
                                  <strong>{auditDecisionMismatch}건 불일치</strong>
                                  <small>저장된 종목별 결과에서 전략 판정을 다시 계산했습니다.</small>
                                </div>
                              </div>

                              {(currentValidationAudit.summary?.notes?.length ?? 0) > 0 && (
                                <div className="exit-validation-reliability-notes">
                                  <strong>검증 과정에서 확인된 참고 사항</strong>
                                  {currentValidationAudit.summary?.notes?.map((note) => <p key={note}>{note}</p>)}
                                </div>
                              )}

                              {(currentValidationAudit.limitations?.length ?? 0) > 0 && (
                                <div className="exit-validation-reliability-limitations">
                                  <strong>이 검증이 확인하지 못하는 범위</strong>
                                  {currentValidationAudit.limitations?.map((item) => <p key={item}>{item}</p>)}
                                </div>
                              )}
                            </div>
                          </details>
                        </>
                      )}
                    </section>
                  )}

                  {validationReport.status === "COMPLETED" && validationCandidates.length > 0 && (
                    <section className="exit-validation-candidates">
                      <div className="exit-validation-candidates-head">
                        <div><span>새 매도 기준 후보</span><strong>실제 연구에서 새 후보로 분류된 전략입니다.</strong></div>
                        <b>{validationCandidates.length}개</b>
                      </div>
                      <div className="exit-validation-candidate-grid">
                        {validationCandidates.map((row) => (
                          <article key={`candidate-${row.strategy}`}>
                            <span>{strategyDisplayLabel(row.strategy)}</span>
                            <strong>{exitPolicyLabel(row.selected_policy_id)}</strong>
                            <p>{validationDecisionSummary(row)}</p>
                          </article>
                        ))}
                      </div>
                    </section>
                  )}

                  {validationReport.status === "COMPLETED" && validationRows.length > 0 && (
                    <section className="exit-validation-core-results readable">
                      <div className="exit-validation-section-title">
                        <span>전략별 핵심 비교</span>
                        <strong>결론 → 실제 수치 → 이유 순서로 읽습니다.</strong>
                      </div>
                      <div className="exit-validation-core-cards">
                        {validationRows.map((row) => {
                          const snapshot = validationComparisonSnapshot(row);
                          return (
                            <details className={`exit-validation-core-card compact status-${row.status.toLowerCase()}`} key={`core-${row.strategy}`}>
                              <summary>
                                <div><small>{snapshot.compared}</small><h3>{strategyDisplayLabel(row.strategy)}</h3><p>{userFacingResearchText(row.reason)}</p></div>
                                <span><b>{exitPolicyStatusLabel(row.status)}</b><DetailToggleText closed="수치 보기 ▼" open="닫기 ▲" /></span>
                              </summary>
                              <div className="exit-validation-core-card-body">
                                <div className="exit-validation-core-insights" aria-label="핵심 수치 해석">
                                  <span>{snapshot.netInsight}</span>
                                  <span>{snapshot.drawdownInsight}</span>
                                </div>
                                <div className="exit-validation-core-metrics">
                                  <div><small>현재 기준</small><span>평균 순수익 <b>{snapshot.currentNet}</b></span><span>최대 낙폭 <b>{snapshot.currentDrawdown}</b></span></div>
                                  <div><small>{row.status === "SELECTED" ? "새 기준 후보" : "새 방식 비교 범위"}</small><span>평균 순수익 <b>{snapshot.alternativeNet}</b></span><span>최대 낙폭 <b>{snapshot.alternativeDrawdown}</b></span></div>
                                </div>
                              </div>
                            </details>
                          );
                        })}
                      </div>
                      <p className="exit-validation-core-note">새 방식 비교 범위는 검증한 방식들의 최소~최대 값입니다. 화면이 임의로 최고 방식을 선정한 값이 아닙니다.</p>
                    </section>
                  )}

                  {validationReport.status !== "COMPLETED" && validationReport.message && (
                    <div className="exit-validation-warning">{userFacingResearchText(validationReport.message)}</div>
                  )}

                  {validationRows.length > 0 && (
                    <details className="exit-validation-all-results">
                      <summary><span>전체 전략 결과 보기</span><DetailToggleText closed={`${validationRows.length}개 전략 펼치기 ▼`} open="전체 전략 숨기기 ▲" /></summary>
                      <div className="exit-validation-strategies">
                        {validationRows.map((row) => <ExitPolicyStrategyReport key={row.strategy} row={row} />)}
                      </div>
                    </details>
                  )}

                  <details className="exit-validation-research-details">
                    <summary><span>연구 실행 정보와 원자료 보기</span><DetailToggleText /></summary>
                    <div className="exit-validation-research-details-body">
                      {validationReport.message && validationReport.status === "COMPLETED" && (
                        <div className="exit-validation-note">{userFacingResearchText(validationReport.message)}</div>
                      )}
                      <div className="exit-validation-meta">
                        <span><b>완료 종목</b>{validationReport.checkpoint?.completed_stocks ?? validationReport.sample?.stocks ?? 0}</span>
                        <span><b>이전 진행 결과 재사용</b>{validationReport.checkpoint?.reused_stocks ?? 0}</span>
                        <span><b>저장 시세 불러오기</b>{formatNumber(validationReport.performance.market_store_load_seconds, 2)}초</span>
                        <span><b>매도 기준 비교 계산</b>{formatNumber(validationReport.performance.exit_policy_calculation_seconds, 2)}초</span>
                        <span><b>전체 실행시간</b>{formatNumber(validationReport.performance.total_seconds, 2)}초</span>
                      </div>
                      {(validationReport.validated_stocks?.length || validationReport.excluded_stocks?.length) && (
                        <details className="exit-validation-sample-details">
                          <summary><span>검증에 사용한 종목과 제외 사유</span><DetailToggleText /></summary>
                          <div className="exit-validation-sample-grid">
                            {validationReport.validated_stocks?.map((stock) => <span key={`used-${stock.market}-${stock.code}`}><b>{stock.code}</b><small>{stock.market} · 검증 사용</small></span>)}
                            {validationReport.excluded_stocks?.map((stock) => <span className="excluded" key={`excluded-${stock.market}-${stock.code}`}><b>{stock.code}</b><small>{stock.market} · {userFacingResearchText(stock.reason)}</small></span>)}
                          </div>
                        </details>
                      )}
                    </div>
                  </details>
                </div>
              )}
            </div>
          </details>
        </div>
      )}

      {view === "result" && (
        <div className="backtest-result-view multi-strategy-result-view">
          <div className="backtest-result-toolbar">
            <div><span>검증 대상</span><strong>{stockName || code || "종목 미선택"} · 전체 전략</strong><small>{formatCompactDate(startDate)} ~ {formatCompactDate(endDate)}</small></div>
            <button type="button" disabled={busy} onClick={() => { setView("setup"); scrollTop(); }}>설정 변경</button>
          </div>

          {busy && job && (
            <div className="backtest-progress-card">
              <div className="backtest-progress-head"><div><strong>{userFacingResearchText(job.progress.message)}</strong><span>{job.progress.current.toLocaleString()} / {job.progress.total.toLocaleString()} · {job.progress.percent.toFixed(1)}%</span></div><b>{job.elapsed_seconds.toFixed(1)}초</b></div>
              <progress max={100} value={job.progress.percent} />
              <div className="backtest-progress-stats"><span><b>처리 방식</b>{job.progress.details.cold_start_fast_path ? "초기 데이터 빠른 처리" : job.progress.details.single_stock_fast_path ? "단일 종목 빠른 처리" : "기본 처리"}</span><span><b>저장 시세 재사용</b>{Number(job.progress.details.history_store_hits ?? 0).toLocaleString()}회</span><span><b>선택 종목 저장 데이터</b>{Number(job.progress.details.cached_symbol_fast_path_hits ?? 0).toLocaleString()}일</span><span><b>KRX 응답 재사용</b>{Number(job.progress.details.raw_cache_hits ?? 0).toLocaleString()}회</span><span><b>실제 요청</b>{Number(job.progress.details.network_requests ?? 0).toLocaleString()}회</span><span><b>동시 처리</b>{Number(job.progress.details.concurrency ?? 0).toLocaleString()}</span><span><b>재시도</b>{Number(job.progress.details.retries ?? 0).toLocaleString()}회</span><span><b>현재 전략</b>{job.progress.details.strategy ? strategyDisplayLabel(String(job.progress.details.strategy)) : "-"}</span></div>
              <button type="button" className="backtest-cancel-button" onClick={() => void cancelRunning()}>분석 취소</button>
            </div>
          )}
          {busy && !job && <div className="loading-card">10가지 방법 비교를 준비하고 있습니다...</div>}
          {error && <div className="backtest-error"><strong>실행 실패</strong><span>{error}</span><button type="button" onClick={() => { setView("setup"); scrollTop(); }}>설정으로 돌아가기</button></div>}

          {result && (
            <div className="multi-strategy-results">
              <section className={`strategy-selector-hero action-${result.recommendation.action.toLowerCase()}`}>
                <div className="strategy-selector-kicker">
                  <span>{formatCompactDate(result.as_of_date)} 확정 일봉 기준</span>
                  <b>{regimeLabel[result.market_regime] ?? result.market_regime}</b>
                </div>

                <div className="strategy-selector-main beginner">
                  <div>
                    <span>현재 10개 방법 중 조건에 가장 가까운 방법</span>
                    <h2>{result.recommendation.strategy_easy_name ?? "현재 추천 전략 없음"}</h2>
                    {result.recommendation.strategy_label && <small className="strategy-professional-name">전문 용어 · {result.recommendation.strategy_label} 전략</small>}
                    <small className="strategy-rank-guardrail">가장 높은 순위가 곧 진입 가능을 의미하지 않습니다.</small>
                  </div>
                  <div className="strategy-selector-decision">
                    <span>현재 판단</span>
                    <strong>{result.recommendation.action_label}</strong>
                    <p>{result.recommendation.headline}</p>
                  </div>
                </div>

                {result.recommendation.strategy_description && (
                  <div className="strategy-beginner-explanation">
                    <div>
                      <span>이게 무슨 방법인가요?</span>
                      <strong>{result.recommendation.strategy_description}</strong>
                    </div>
                    {result.recommendation.strategy_when_to_use && (
                      <p><b>주로 언제 쓰나요?</b> {result.recommendation.strategy_when_to_use}</p>
                    )}
                  </div>
                )}

                <div className="strategy-selector-reason">
                  <span>왜 지금 이렇게 판단했나요?</span>
                  <p>{result.recommendation.reason}</p>
                  {(result.recommendation.additional_warnings?.length ?? 0) > 0 && (
                    <div className="strategy-selector-secondary-warnings">
                      <b>추가 주의</b>
                      {result.recommendation.additional_warnings!.map((warning) => <small key={warning}>{warning}</small>)}
                    </div>
                  )}
                </div>

                {topStrategy && <StrategyConditionSummary row={topStrategy} action={result.recommendation.action} />}

                {result.recommendation.entry_risk_guide && (
                  <EntryRiskGuideCard guide={result.recommendation.entry_risk_guide} />
                )}

                <div className="strategy-user-action-card">
                  <div className="strategy-user-action-head">
                    <span>지금 행동</span>
                    <strong>{result.recommendation.user_action.user_task}</strong>
                  </div>
                  <div>
                    <b>{result.recommendation.user_action.title}</b>
                    <p>{result.recommendation.user_action.detail}</p>
                    {result.recommendation.action !== "ENTRY_CANDIDATE" && (
                      <p className="strategy-next-user-action"><strong>다음 행동</strong> 최신 확정 데이터가 나온 뒤 다시 분석하세요.</p>
                    )}
                  </div>
                </div>

                <div className="strategy-next-check-card">
                  <div className="strategy-next-check-copy">
                    <span>다음 분석에서는 무엇을 하나요?</span>
                    <strong>최신 확정 데이터로 부족했던 조건과 위험을 다시 계산합니다.</strong>
                    <small>{result.recommendation.recheck_label}</small>
                  </div>
                  <div className="strategy-next-conditions">
                    <span>다시 확인하는 항목</span>
                    <ul className="strategy-recheck-list">
                      <li>부족했던 전략 조건</li>
                      <li>현재 시장 상황</li>
                      <li>손절 위험</li>
                      <li>목표 가격까지의 여유</li>
                    </ul>
                  </div>
                </div>

                <div className="strategy-transition-card">
                  <div>
                    <span>조건이 충족되면?</span>
                    <strong>바로 매수 신호가 되지는 않습니다.</strong>
                    <small>StockScope가 전략 조건 + 시장 상황 + 손절·목표 위험을 다시 확인하고, 모두 적절하면 진입 후보로 변경합니다.</small>
                  </div>
                  <button type="button" className="secondary" disabled={busy || latestReanalysisBusy} onClick={() => void rerunLatest()}>
                    {latestReanalysisBusy ? "최신 데이터 확인 중..." : "최신 확정 데이터로 다시 분석"}
                  </button>
                </div>

                {latestReanalysisSummary && (
                  <section className={`latest-reanalysis-summary ${latestReanalysisSummary.status.toLowerCase()}`}>
                    <div className="latest-reanalysis-summary-head">
                      <span>최신 데이터 재분석 결과</span>
                      <strong>{latestReanalysisSummary.status === "UP_TO_DATE"
                        ? "이미 최신 확정 데이터입니다."
                        : latestReanalysisSummary.status === "UPDATED_CHANGED"
                          ? "최신 데이터를 반영하면서 일부 판단이 달라졌습니다."
                          : "최신 데이터를 반영했지만 현재 판단은 그대로입니다."}</strong>
                      <small>분석 기준일 {formatCompactDate(latestReanalysisSummary.previousAsOf)} → {formatCompactDate(latestReanalysisSummary.latestAsOf)}</small>
                    </div>
                    {latestReanalysisSummary.status === "UP_TO_DATE" ? (
                      <p>새로 반영할 확정 시세가 없어 불필요한 전체 재계산을 실행하지 않았습니다.</p>
                    ) : latestReanalysisSummary.changes.length > 0 ? (
                      <div className="latest-reanalysis-change-grid">
                        {latestReanalysisSummary.changes.map((change) => (
                          <div key={`latest-change-${change.label}`}>
                            <span>{change.label}</span>
                            <b>{change.before}</b><i>→</i><strong>{change.after}</strong>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p>분석 기준일은 최신화됐지만 전략 판단과 주요 가격 계획에는 의미 있는 변화가 없습니다.</p>
                    )}
                  </section>
                )}

                <div className="strategy-recheck-note">
                  <b>현재 버전은 상시 자동 감시가 아닙니다.</b>
                  <span>다음 거래일 데이터가 확정된 뒤 다시 분석하면 StockScope가 최신 데이터로 조건을 자동 재평가합니다. 사용자가 거래량·RSI·이동평균을 직접 계산할 필요는 없습니다.</span>
                </div>
                <small>{result.recommendation.guardrail}</small>
              </section>

              {result.historical_policy && (
                <section className="historical-policy-banner">
                  <div><span>현재 과거 성과 검증 매도 기준</span><strong>{exitPolicyLabel(result.historical_policy.policy_id)}</strong></div>
                  <p>{result.historical_policy.target2_included ? "2차 목표가까지 현재 과거 성과 계산에 반영됩니다." : "2차 목표가는 현재 위험 관리 계획의 참고가격이며, 현재 과거 성과 계산에는 아직 반영되지 않습니다."}</p>
                </section>
              )}

              {topStrategy && (
                <section className="strategy-selector-proof">
                  <article><span>과거에는 어땠나요?</span><strong>{topStrategy.historical_fit.label}</strong><p>{topStrategy.historical_fit.summary}</p></article>
                  <article><span>지금 조건은 어떤가요?</span><strong>{topStrategy.current.label}</strong><p>{topStrategy.current.summary}</p></article>
                  <article><span>과거 사례는 충분한가요?</span><strong>{topStrategy.historical_metrics.trades}건</strong><p>{historicalEvidenceHint(topStrategy)} 표본 수만이 아니라 평균 결과·손익 구조·최대 낙폭을 함께 평가합니다.</p></article>
                </section>
              )}

              <section className="strategy-selector-top3">
                <div className="backtest-section-title"><span>다른 방법과 비교하면?</span><strong>StockScope가 같은 기준으로 비교한 현재 상위 3개 방법입니다.</strong></div>
                <div className="multi-strategy-mini-grid">{topThree.map((row) => <StrategyMiniCard key={row.strategy} row={row} />)}</div>
              </section>

              {result.warnings.length > 0 && <div className="backtest-warning"><strong>데이터 확인사항</strong>{result.warnings.map((warning) => <span key={warning}>{userFacingResearchText(warning)}</span>)}</div>}

              <div className="multi-strategy-details-stack">
                <details>
                  <summary><span>10개 방법 전체 비교 · 전문 숫자 보기</span><DetailToggleText /></summary>
                  <div className="backtest-table-wrap">
                    <table className="backtest-table multi-strategy-table">
                      <thead><tr><th>순위</th><th>방법</th><th>전문 전략명</th><th>과거 판단</th><th>과거 사례</th><th>거래당 평균</th><th>가장 큰 손실 구간(MDD)</th><th>현재 상태</th></tr></thead>
                      <tbody>{result.strategies.map((row) => (
                        <tr key={row.strategy}>
                          <td><b>{row.rank}</b></td><td><strong>{row.guide.easy_name}</strong></td><td>{row.guide.professional_name}</td><td>{row.historical_fit.label}</td><td>{row.historical_metrics.trades}건</td><td>{formatPct(row.historical_metrics.expectancy_pct)}</td><td>{formatPct(row.historical_metrics.max_drawdown_pct)}</td><td>{row.current.label}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  <p className="backtest-detail-note">순위는 주가 상승 확률이 아닙니다. 같은 과거 데이터에서 각 방법이 얼마나 잘 맞았는지와 현재 조건을 함께 비교한 우선순위입니다.</p>
                </details>

                {topStrategy && (
                  <details>
                    <summary><span>왜 ‘{topStrategy.guide.easy_name}’가 현재 가장 가까운 전략인가?</span><DetailToggleText /></summary>
                    <div className="strategy-guide-detail">
                      <strong>{topStrategy.guide.easy_name}</strong>
                      <small>{topStrategy.guide.professional_name} 전략</small>
                      <p>{topStrategy.guide.description}</p>
                      <p><b>주로 언제 쓰나요?</b> {topStrategy.guide.when_to_use}</p>
                    </div>
                    <div className="multi-strategy-explanation-grid">
                      <article><span>과거 검증</span><strong>{topStrategy.historical_fit.label}</strong><p>{topStrategy.historical_fit.summary}</p></article>
                      <article><span>현재 조건</span><strong>{topStrategy.current.label}</strong><p>{topStrategy.current.summary}</p></article>
                    </div>
                    {(topStrategy.current.reason_details?.length ?? 0) > 0 && (
                      <div className="multi-strategy-reason-list">
                        <strong>현재 맞아 있는 조건</strong>
                        <div className="strategy-detail-condition-grid">{topStrategy.current.reason_details!.slice(0, 5).map((reason) => <ConditionMetricCard key={reason.condition_id ?? reason.raw} condition={reason} />)}</div>
                      </div>
                    )}
                    {(topStrategy.current.unmet_details?.length ?? 0) > 0 && (
                      <div className="multi-strategy-reason-list missing">
                        <strong>아직 부족한 조건</strong>
                        <div className="strategy-detail-condition-grid">{topStrategy.current.unmet_details!.slice(0, 5).map((reason) => <ConditionMetricCard key={reason.condition_id ?? reason.raw} condition={reason} />)}</div>
                      </div>
                    )}
                  </details>
                )}

                {topStrategy && (
                  <details>
                    <summary><span>‘{topStrategy.guide.easy_name}’의 과거 거래 숫자로 보기</span><DetailToggleText /></summary>
                    {topStrategy.recent_trades.length === 0 ? <p className="backtest-empty-row">표시할 과거 거래가 없습니다.</p> : (
                      <div className="backtest-table-wrap"><table className="backtest-table"><thead><tr><th>진입일</th><th>청산일</th><th>결과</th><th>종료 이유</th><th>보유</th></tr></thead><tbody>{topStrategy.recent_trades.map((trade) => <tr key={`${trade.entry_date}-${trade.exit_date}`}><td>{formatCompactDate(trade.entry_date)}</td><td>{formatCompactDate(trade.exit_date)}</td><td>{formatPct(trade.net_return_pct)}</td><td>{exitLabel(trade.exit_reason)}</td><td>{trade.holding_days}일</td></tr>)}</tbody></table></div>
                    )}
                  </details>
                )}

                <details>
                  <summary><span>전문가용 · 비교 방법과 한계</span><DetailToggleText /></summary>
                  <div className="multi-strategy-method-brief">
                    {Object.entries(result.methodology).map(([key, value]) => <p key={key}>{value}</p>)}
                  </div>
                </details>

                {result.performance && (
                  <details>
                    <summary><span>개발 확인용 · 실행 성능 진단</span><DetailToggleText /></summary>
                    <div className="backtest-progress-stats"><span><b>처리 방식</b>{result.performance.cold_start_fast_path ? "초기 데이터 빠른 처리" : result.performance.single_stock_fast_path ? "단일 종목 빠른 처리" : "기본 처리"}</span><span><b>데이터 준비</b>{formatNumber(result.performance.data_prepare_seconds, 2)}초</span><span><b>10가지 전략 계산</b>{formatNumber(result.performance.strategy_calculation_seconds, 2)}초</span><span><b>전체</b>{formatNumber(result.performance.total_seconds, 2)}초</span><span><b>선택 종목 저장 데이터</b>{Number(result.performance.cached_symbol_fast_path_hits ?? 0).toLocaleString()}일</span><span><b>KRX 요청</b>{result.performance.network_requests}회</span><span><b>재시도</b>{Number(result.performance.retries ?? 0).toLocaleString()}회</span>{result.performance.history_fill_ms !== undefined && <span><b>누락 데이터 채우기</b>{formatNumber(result.performance.history_fill_ms / 1000, 2)}초</span>}</div>
                  </details>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
