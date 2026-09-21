import { useSyncExternalStore } from "react";
import type { ScannerResponse } from "../services/api";

export const SCANNER_SESSION_SCHEMA_VERSION = 1;
const STORAGE_KEY = "stockscope.scanner.session.v0.21.4-A.3";

type MarketScope = "ALL" | "KOSPI" | "KOSDAQ";

export type ScannerSessionSnapshot = {
  schemaVersion: number;
  scope: MarketScope;
  result: ScannerResponse;
  completedAt: number;
  scrollY: number;
  showMore: boolean;
  expandedEvidenceIds: string[];
  selectedCandidateKey: string | null;
};

export type ScannerSessionInput = Omit<ScannerSessionSnapshot, "schemaVersion">;

type UnknownRecord = Record<string, unknown>;

const listeners = new Set<() => void>();
let memorySnapshot: ScannerSessionSnapshot | null = null;
let hydrated = false;

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function normalizeScope(value: unknown): MarketScope {
  return value === "KOSPI" || value === "KOSDAQ" ? value : "ALL";
}

function finiteNumber(value: unknown, fallback: number) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeSnapshot(value: unknown): ScannerSessionSnapshot | null {
  const raw = asRecord(value);
  const result = raw.result;
  if (!result || typeof result !== "object") return null;

  // Legacy payloads used Scanner algorithm version as a storage compatibility
  // gate. We intentionally ignore that field: algorithm version belongs to the
  // saved result, while browser persistence compatibility is schema-versioned.
  const expanded = Array.isArray(raw.expandedEvidenceIds)
    ? raw.expandedEvidenceIds.filter((item): item is string => typeof item === "string")
    : [];

  return {
    schemaVersion: SCANNER_SESSION_SCHEMA_VERSION,
    scope: normalizeScope(raw.scope),
    result: result as ScannerResponse,
    completedAt: finiteNumber(raw.completedAt, Date.now()),
    scrollY: Math.max(0, finiteNumber(raw.scrollY, 0)),
    showMore: raw.showMore === true,
    expandedEvidenceIds: expanded,
    selectedCandidateKey: typeof raw.selectedCandidateKey === "string" ? raw.selectedCandidateKey : null,
  };
}

function loadStorage(): ScannerSessionSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const normalized = normalizeSnapshot(JSON.parse(raw));
    if (!normalized) window.sessionStorage.removeItem(STORAGE_KEY);
    return normalized;
  } catch {
    return null;
  }
}

function persist(snapshot: ScannerSessionSnapshot | null) {
  if (typeof window === "undefined") return;
  try {
    if (snapshot) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // sessionStorage is recovery persistence only. The in-memory SPA snapshot
    // remains valid even when storage is blocked/quota-limited.
  }
}

function emit() {
  listeners.forEach((listener) => listener());
}

function hydrateOnce() {
  if (hydrated) return;
  hydrated = true;
  memorySnapshot = loadStorage();
}

export function getScannerSessionSnapshot(): ScannerSessionSnapshot | null {
  hydrateOnce();
  return memorySnapshot;
}

export function subscribeScannerSession(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function commitScannerSession(input: ScannerSessionInput | ScannerSessionSnapshot) {
  const normalized = normalizeSnapshot({ ...input, schemaVersion: SCANNER_SESSION_SCHEMA_VERSION });
  if (!normalized) return;
  hydrated = true;
  memorySnapshot = normalized;
  persist(normalized);
  emit();
}

// Backward-compatible names used by ScannerPanel and existing callers.
export function writeScannerSession(input: ScannerSessionInput | ScannerSessionSnapshot) {
  commitScannerSession(input);
}

export function readScannerSession() {
  return getScannerSessionSnapshot();
}

export function clearScannerSession() {
  hydrated = true;
  memorySnapshot = null;
  persist(null);
  emit();
}

export function useScannerSession() {
  return useSyncExternalStore(
    subscribeScannerSession,
    getScannerSessionSnapshot,
    () => null,
  );
}

function normalizeDate(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const compact = value.trim().replace(/\./g, "-");
  if (/^\d{8}$/.test(compact)) return `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(compact)) return compact;
  return null;
}

function resultDates(result: ScannerResponse | null | undefined) {
  if (!result) return [] as string[];
  const dates: string[] = [];
  const record = result as unknown as UnknownRecord;
  const requested = normalizeDate(record.requested_as_of);
  if (requested) dates.push(requested);
  const candidates = [
    ...(Array.isArray(record.candidates) ? record.candidates : []),
    ...(Array.isArray(record.more_candidates) ? record.more_candidates : []),
  ];
  for (const raw of candidates) {
    const day = normalizeDate(asRecord(raw).data_date);
    if (day) dates.push(day);
  }
  const summaries = Array.isArray(record.market_summary) ? record.market_summary : [];
  for (const raw of summaries) {
    const row = asRecord(raw);
    const day = normalizeDate(row.data_date ?? row.as_of_date ?? row.latest_complete_date);
    if (day) dates.push(day);
  }
  return dates;
}

export function latestScannerDataDate(result: ScannerResponse | null | undefined): string | null {
  const dates = resultDates(result);
  if (!dates.length) return null;
  const ordered = [...dates].sort();
  return ordered[ordered.length - 1] ?? null;
}

export function resolveScannerDataDate(result: ScannerResponse | null | undefined) {
  if (!result) return { date: null as string | null, aligned: true };
  const record = result as unknown as UnknownRecord;
  const requested = normalizeDate(record.requested_as_of);
  const candidateDates = [
    ...(Array.isArray(record.candidates) ? record.candidates : []),
    ...(Array.isArray(record.more_candidates) ? record.more_candidates : []),
  ].map((item) => normalizeDate(asRecord(item).data_date)).filter((item): item is string => Boolean(item));
  const unique = [...new Set(candidateDates)];
  const date = unique[0] ?? requested ?? latestScannerDataDate(result);
  const aligned = unique.length <= 1 && (!requested || !date || requested === date);
  return { date, aligned };
}

export function localDateKey(timestamp: number = Date.now()) {
  const day = new Date(timestamp);
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.storageArea !== window.sessionStorage || event.key !== STORAGE_KEY) return;
    hydrated = true;
    memorySnapshot = loadStorage();
    emit();
  });
}
