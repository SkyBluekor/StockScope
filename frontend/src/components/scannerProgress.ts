export type ScannerProgressStatus = "waiting" | "active" | "done" | "reused" | "failed";

export type ScannerProgressRow = {
  id: string;
  label: string;
  status: ScannerProgressStatus;
};

export const PREPARATION_STAGES = [
  { id: "scanner_prepare_local", label: "로컬 저장 데이터 확인" },
  { id: "scanner_prepare_probe", label: "최신 거래일 확인" },
  { id: "scanner_prepare_kospi_stock", label: "KOSPI 종목 데이터" },
  { id: "scanner_prepare_kospi_index", label: "KOSPI 지수" },
  { id: "scanner_prepare_kosdaq_stock", label: "KOSDAQ 종목 데이터" },
  { id: "scanner_prepare_kosdaq_index", label: "KOSDAQ 지수" },
  { id: "scanner_prepare_store", label: "저장 데이터 최종 검증" },
] as const;

export const ANALYSIS_STAGES = [
  { id: "scanner_history_prepare", label: "최근 시장 데이터 준비" },
  { id: "scanner_quick_filter", label: "전체 종목 빠른 검사" },
  { id: "scanner_deep_analysis", label: "상위 후보 전략·Risk 확인" },
  { id: "scanner_priority_rank", label: "최종 우선순위 정리" },
] as const;

const PREP_ALIAS = new Map<string, string>(PREPARATION_STAGES.map((item) => [item.id, item.id]));
const ANALYSIS_ALIAS: Record<string, string> = {
  scanner_plan: "scanner_history_prepare",
  scanner_data_prepare: "scanner_history_prepare",
  scanner_fast_budget: "scanner_history_prepare",
  scanner_universe: "scanner_history_prepare",
  scanner_quick_filter: "scanner_quick_filter",
  scanner_deep_analysis: "scanner_deep_analysis",
  scanner_finalize: "scanner_deep_analysis",
  scanner_historical_evidence: "scanner_deep_analysis",
  scanner_priority_rank: "scanner_priority_rank",
};

export function canonicalScannerStage(stage: string | undefined): string | null {
  if (!stage) return null;
  if (PREP_ALIAS.has(stage)) return stage;
  return ANALYSIS_ALIAS[stage] ?? (stage === "scanner_prepare_complete" ? "scanner_history_prepare" : null);
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function scannerProgressView(stage: string | undefined, details: Record<string, unknown>) {
  const completed = new Set(asStringList(details.completed_stages));
  const reused = new Set(asStringList(details.reused_stages));
  const failedStage = typeof details.failed_stage === "string" ? details.failed_stage : null;
  const canonical = canonicalScannerStage(stage);
  const analysisStarted = Boolean(canonical && ANALYSIS_STAGES.some((item) => item.id === canonical))
    || stage === "scanner_cache"
    || stage === "scanner_complete";
  const marketScope = typeof details.market_scope === "string" ? details.market_scope : "ALL";
  const applicablePreparation = PREPARATION_STAGES.filter((item) => {
    if (marketScope === "KOSPI") return !item.id.includes("kosdaq");
    if (marketScope === "KOSDAQ") return !item.id.includes("kospi");
    return true;
  });

  const prepRows: ScannerProgressRow[] = applicablePreparation.map((item, index) => {
    if (failedStage === item.id) return { ...item, status: "failed" };
    if (reused.has(item.id)) return { ...item, status: "reused" };
    if (completed.has(item.id) || analysisStarted) return { ...item, status: "done" };
    if (canonical === item.id) return { ...item, status: "active" };
    const activeIndex = applicablePreparation.findIndex((candidate) => candidate.id === canonical);
    return { ...item, status: activeIndex > index ? "done" : "waiting" };
  });

  const analysisRows: ScannerProgressRow[] = ANALYSIS_STAGES.map((item, index) => {
    if (stage === "scanner_cache" || stage === "scanner_complete") return { ...item, status: "done" };
    if (canonical === item.id) return { ...item, status: "active" };
    const activeIndex = ANALYSIS_STAGES.findIndex((candidate) => candidate.id === canonical);
    return { ...item, status: activeIndex > index ? "done" : "waiting" };
  });

  const prepDone = prepRows.filter((item) => item.status === "done" || item.status === "reused").length;
  const analysisDone = analysisRows.filter((item) => item.status === "done" || item.status === "reused").length;
  return { analysisStarted, prepRows, analysisRows, prepDone, analysisDone };
}

export function progressStatusMark(status: ScannerProgressStatus) {
  if (status === "done" || status === "reused") return "✓";
  if (status === "active") return "●";
  if (status === "failed") return "!";
  return "○";
}
