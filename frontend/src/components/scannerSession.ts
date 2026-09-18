import type { ScannerResponse } from "../services/api";

export const SCANNER_SESSION_STORAGE_KEY = "stockscope.scanner.session.v0.21.4-A.3";
export const SCANNER_SESSION_SCHEMA_VERSION = 2;
export const SCANNER_DECISION_VERSION = "0.21.3.4";

export type ScannerMarketScope = "ALL" | "KOSPI" | "KOSDAQ";

type StorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

export type ScannerSessionSnapshot = {
  schemaVersion: number;
  scope: ScannerMarketScope;
  result: ScannerResponse;
  completedAt: number;
  savedAt: number;
  savedLocalDate: string;
  scrollY: number;
  showMore: boolean;
  expandedEvidenceIds: string[];
  selectedCandidateKey?: string | null;
};

let memorySnapshot: ScannerSessionSnapshot | null = null;

function browserSessionStorage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

export function localDateKey(value: number | Date = Date.now()) {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export type ScannerDateResolution = {
  date: string | null;
  aligned: boolean;
  requestedDate: string | null;
  marketDates: Partial<Record<"KOSPI" | "KOSDAQ", string>>;
};

export function resolveScannerDataDate(result: ScannerResponse | null | undefined): ScannerDateResolution {
  if (!result) {
    return { date: null, aligned: false, requestedDate: null, marketDates: {} };
  }
  const requestedDate = result.requested_as_of || null;
  const markets: Array<"KOSPI" | "KOSDAQ"> = result.market_scope === "ALL"
    ? ["KOSPI", "KOSDAQ"]
    : [result.market_scope];
  const marketDates = result.data_dates ?? {};
  const values = markets.map((market) => marketDates[market]).filter((value): value is string => Boolean(value));
  if (values.length !== markets.length) {
    return { date: null, aligned: false, requestedDate, marketDates };
  }
  const unique = new Set(values);
  if (unique.size !== 1) {
    return { date: null, aligned: false, requestedDate, marketDates };
  }
  const commonDate = values[0] ?? null;
  if (requestedDate && commonDate !== requestedDate) {
    return { date: null, aligned: false, requestedDate, marketDates };
  }
  return { date: commonDate, aligned: Boolean(commonDate), requestedDate, marketDates };
}

export function latestScannerDataDate(result: ScannerResponse | null | undefined) {
  return resolveScannerDataDate(result).date;
}

export function readScannerSession(storage: StorageLike | null = browserSessionStorage()): ScannerSessionSnapshot | null {
  if (storage) {
    try {
      const raw = storage.getItem(SCANNER_SESSION_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<ScannerSessionSnapshot>;
        if (parsed.schemaVersion !== SCANNER_SESSION_SCHEMA_VERSION) return null;
        if (!parsed.result || !parsed.scope || !parsed.completedAt) return null;
        if (!(["ALL", "KOSPI", "KOSDAQ"] as string[]).includes(parsed.scope)) return null;
        if (parsed.result.market_scope !== parsed.scope) return null;
        if (parsed.result.version !== SCANNER_DECISION_VERSION) {
          try { storage.removeItem(SCANNER_SESSION_STORAGE_KEY); } catch { /* ignore */ }
          return null;
        }
        const restored: ScannerSessionSnapshot = {
          schemaVersion: SCANNER_SESSION_SCHEMA_VERSION,
          scope: parsed.scope,
          result: parsed.result,
          completedAt: Number(parsed.completedAt),
          savedAt: Number(parsed.savedAt ?? parsed.completedAt),
          savedLocalDate: String(parsed.savedLocalDate ?? localDateKey(Number(parsed.completedAt))),
          scrollY: Math.max(0, Number(parsed.scrollY ?? 0)),
          showMore: Boolean(parsed.showMore),
          expandedEvidenceIds: Array.isArray(parsed.expandedEvidenceIds)
            ? parsed.expandedEvidenceIds.filter((value): value is string => typeof value === "string")
            : [],
          selectedCandidateKey: typeof parsed.selectedCandidateKey === "string" ? parsed.selectedCandidateKey : null,
        };
        memorySnapshot = restored;
        return restored;
      }
    } catch {
      return memorySnapshot;
    }
  }
  return memorySnapshot;
}

export function writeScannerSession(snapshot: Omit<ScannerSessionSnapshot, "schemaVersion" | "savedAt" | "savedLocalDate">, storage: StorageLike | null = browserSessionStorage()) {
  if (!storage) return;
  const now = Date.now();
  const payload: ScannerSessionSnapshot = {
    ...snapshot,
    schemaVersion: SCANNER_SESSION_SCHEMA_VERSION,
    savedAt: now,
    savedLocalDate: localDateKey(now),
  };
  memorySnapshot = payload;
  try {
    storage.setItem(SCANNER_SESSION_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // sessionStorage quota/privacy failures should never break Scanner rendering.
  }
}

export function clearScannerSession(storage: StorageLike | null = browserSessionStorage()) {
  memorySnapshot = null;
  if (!storage) return;
  try {
    storage.removeItem(SCANNER_SESSION_STORAGE_KEY);
  } catch {
    // Ignore browser storage failures and fall back to in-memory state.
  }
}
