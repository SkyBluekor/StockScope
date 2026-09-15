import type { ScannerResponse } from "../services/api";

export const SCANNER_SESSION_STORAGE_KEY = "stockscope.scanner.session.v0.21.4-A.3";
export const SCANNER_SESSION_SCHEMA_VERSION = 1;

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

export function latestScannerDataDate(result: ScannerResponse | null | undefined) {
  if (!result) return null;
  const values = Object.values(result.data_dates ?? {}).filter((value): value is string => Boolean(value));
  if (values.length === 0) return result.requested_as_of || null;
  values.sort();
  return values[values.length - 1] ?? result.requested_as_of ?? null;
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
