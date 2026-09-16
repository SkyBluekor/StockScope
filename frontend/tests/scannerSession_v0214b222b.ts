import {
  clearScannerSession,
  latestScannerDataDate,
  resolveScannerDataDate,
  readScannerSession,
  SCANNER_SESSION_SCHEMA_VERSION,
  SCANNER_SESSION_STORAGE_KEY,
  writeScannerSession,
} from "../src/components/scannerSession";
import type { ScannerResponse } from "../src/services/api";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string) { return this.data.get(key) ?? null; }
  setItem(key: string, value: string) { this.data.set(key, value); }
  removeItem(key: string) { this.data.delete(key); }
}

const result = {
  version: "v0.21.3",
  scanner_cache_hit: false,
  generated_at: "2026-09-15T14:30:00+09:00",
  requested_as_of: "2026-09-15",
  market_scope: "ALL",
  data_dates: { KOSPI: "2026-09-14", KOSDAQ: "2026-09-12" },
  market_summary: [],
  summary: { universe_total: 10, special_excluded: 0, liquidity_filtered: 0, quick_analyzed: 10, data_insufficient: 0, deep_analyzed: 5, candidate_count: 2, shown_count: 2, excluded_after_analysis: 0 },
  candidates: [],
  more_candidates: [],
  empty_message: null,
  exclusion_policy: { default: [], liquidity: "" },
  methodology: { meaning: "", pipeline: [], guardrail: "" },
  diagnostics: { market_store_reused_items: 0, estimated_network_requests: 0, network_requests: 0, raw_cache_hits: 0, retries: 0, budget_used: 0, budget_limit: 1000, budget_remaining: 1000 },
} as ScannerResponse;

const storage = new MemoryStorage();
writeScannerSession({ scope: "ALL", result, completedAt: 1000, scrollY: 777, showMore: true, expandedEvidenceIds: ["KOSPI-005930"] }, storage);
const restored = readScannerSession(storage);
assert(restored !== null, "saved Scanner session should restore");
assert(restored.scope === "ALL", "scope should restore");
assert(restored.scrollY === 777, "scroll position should restore");
assert(restored.showMore === true, "show-more state should restore");
assert(restored.expandedEvidenceIds.includes("KOSPI-005930"), "expanded evidence should restore");
assert(latestScannerDataDate(restored.result) === null, "mixed market dates must not be presented as one analysis date");
assert(resolveScannerDataDate(restored.result).aligned === false, "mixed market dates must be marked inconsistent");
const alignedResult = {
  ...restored.result,
  requested_as_of: "2026-09-15",
  data_dates: { KOSPI: "2026-09-15", KOSDAQ: "2026-09-15" },
} as ScannerResponse;
assert(latestScannerDataDate(alignedResult) === "2026-09-15", "aligned market dates should expose the common analysis date");
assert(resolveScannerDataDate(alignedResult).aligned === true, "aligned market dates should be accepted");

const raw = JSON.parse(storage.getItem(SCANNER_SESSION_STORAGE_KEY) || "{}");
raw.schemaVersion = SCANNER_SESSION_SCHEMA_VERSION + 1;
storage.setItem(SCANNER_SESSION_STORAGE_KEY, JSON.stringify(raw));
assert(readScannerSession(storage) === null, "schema mismatch must invalidate cache");

writeScannerSession({ scope: "ALL", result, completedAt: 1000, scrollY: 0, showMore: false, expandedEvidenceIds: [] }, storage);
const mismatch = JSON.parse(storage.getItem(SCANNER_SESSION_STORAGE_KEY) || "{}");
mismatch.scope = "KOSPI";
storage.setItem(SCANNER_SESSION_STORAGE_KEY, JSON.stringify(mismatch));
assert(readScannerSession(storage) === null, "scope/result mismatch must invalidate cache");

writeScannerSession({ scope: "ALL", result, completedAt: 2000, scrollY: 321, showMore: false, expandedEvidenceIds: [] }, storage);
const blockedStorage = {
  getItem() { throw new Error("blocked"); },
  setItem() { throw new Error("blocked"); },
  removeItem() { throw new Error("blocked"); },
};
const memoryFallback = readScannerSession(blockedStorage);
assert(memoryFallback?.scrollY === 321, "in-memory fallback should preserve SPA navigation when sessionStorage is blocked");

clearScannerSession(storage);
assert(storage.getItem(SCANNER_SESSION_STORAGE_KEY) === null, "clear should remove Scanner session");
console.log("scannerSession/date consistency v0.21.4-B.2.2.2b tests: PASS");
