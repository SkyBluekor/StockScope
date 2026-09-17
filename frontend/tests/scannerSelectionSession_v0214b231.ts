import {
  readScannerSession,
  writeScannerSession,
  type ScannerSessionSnapshot,
} from "../src/components/scannerSession";

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
  market_scope: "ALL",
  requested_as_of: "2026-09-16",
  data_dates: { KOSPI: "2026-09-16", KOSDAQ: "2026-09-16" },
  candidates: [
    { market: "KOSPI", code: "489790", name: "한화비전" },
    { market: "KOSPI", code: "192820", name: "코스맥스" },
  ],
  more_candidates: [],
} as any;

const storage = new MemoryStorage();
writeScannerSession({
  scope: "ALL",
  result,
  completedAt: Date.now(),
  scrollY: 640,
  showMore: false,
  expandedEvidenceIds: [],
  selectedCandidateKey: "KOSPI-192820",
}, storage);

const restored: ScannerSessionSnapshot | null = readScannerSession(storage);
assert(restored !== null, "Scanner session should restore");
assert(restored.selectedCandidateKey === "KOSPI-192820", "selected candidate must survive F5/session restore");
assert(restored.scrollY === 640, "scroll position must remain intact with selected candidate persistence");
console.log("scannerSelectionSession v0.21.4-B.2.3.1: PASS");
