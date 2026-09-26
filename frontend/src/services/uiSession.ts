export type AnalysisSelectionContext = {
  market: "KOSPI" | "KOSDAQ";
  code: string;
  name: string;
  scannerOrigin: boolean;
  savedAt: number;
};

export type HoldingsViewContext = {
  stockFilter: "all" | "watch" | "held";
  timelineFilter: "all" | "analysis" | "position";
  query: string;
  selectedStockId: string | null;
};

export type TrackingMode = "tracking" | "historical";

const ANALYSIS_KEY = "stockscope-analysis-context-v1";
const HOLDINGS_KEY = "stockscope-holdings-context-v1";
const TRACKING_KEY = "stockscope-tracking-mode-v1";

function readSessionJson(key: string): unknown {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSessionJson(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // UI context persistence is optional. Core workflows must keep working.
  }
}

export function readAnalysisSelectionContext(): AnalysisSelectionContext | null {
  const raw = readSessionJson(ANALYSIS_KEY);
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Partial<AnalysisSelectionContext>;
  const market = value.market === "KOSPI" || value.market === "KOSDAQ" ? value.market : null;
  const code = typeof value.code === "string" ? value.code.trim().toUpperCase() : "";
  const name = typeof value.name === "string" ? value.name.trim() : "";
  if (!market || !code || !name) return null;
  return {
    market,
    code,
    name,
    scannerOrigin: value.scannerOrigin === true,
    savedAt: typeof value.savedAt === "number" && Number.isFinite(value.savedAt) ? value.savedAt : 0,
  };
}

export function writeAnalysisSelectionContext(value: Omit<AnalysisSelectionContext, "savedAt">) {
  writeSessionJson(ANALYSIS_KEY, { ...value, savedAt: Date.now() });
}

export function readHoldingsViewContext(): HoldingsViewContext | null {
  const raw = readSessionJson(HOLDINGS_KEY);
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Partial<HoldingsViewContext>;
  const stockFilter = value.stockFilter === "watch" || value.stockFilter === "held" || value.stockFilter === "all"
    ? value.stockFilter
    : null;
  const timelineFilter = value.timelineFilter === "analysis" || value.timelineFilter === "position" || value.timelineFilter === "all"
    ? value.timelineFilter
    : null;
  if (!stockFilter || !timelineFilter) return null;
  return {
    stockFilter,
    timelineFilter,
    query: typeof value.query === "string" ? value.query : "",
    selectedStockId: typeof value.selectedStockId === "string" && value.selectedStockId.trim()
      ? value.selectedStockId
      : null,
  };
}

export function writeHoldingsViewContext(value: HoldingsViewContext) {
  writeSessionJson(HOLDINGS_KEY, value);
}

export function readTrackingMode(): TrackingMode {
  if (typeof window === "undefined") return "tracking";
  try {
    const value = window.sessionStorage.getItem(TRACKING_KEY);
    return value === "historical" ? "historical" : "tracking";
  } catch {
    return "tracking";
  }
}

export function writeTrackingMode(value: TrackingMode) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(TRACKING_KEY, value);
  } catch {
    // Optional UI persistence only.
  }
}
