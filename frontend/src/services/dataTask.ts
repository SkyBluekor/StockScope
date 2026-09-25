export const ACTIVE_DATA_TASK_KEY = "stockscope-active-data-task";
export const DATA_TASK_EVENT = "stockscope:data-task";

export type DataTaskSnapshot = {
  kind: "scanner";
  jobId: string;
  scope: "ALL" | "KOSPI" | "KOSDAQ";
  allowLargeSync: boolean;
  status: string;
  stage: string;
  message: string;
  current: number | null;
  total: number | null;
  percent: number | null;
  updatedAt: string | null;
  startedAt: number;
};

export function readActiveDataTask(): DataTaskSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_DATA_TASK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DataTaskSnapshot>;
    if (parsed.kind !== "scanner" || typeof parsed.jobId !== "string" || !parsed.jobId) return null;
    const scope = parsed.scope === "KOSPI" || parsed.scope === "KOSDAQ" ? parsed.scope : "ALL";
    return {
      kind: "scanner",
      jobId: parsed.jobId,
      scope,
      allowLargeSync: parsed.allowLargeSync === true,
      status: typeof parsed.status === "string" ? parsed.status : "queued",
      stage: typeof parsed.stage === "string" ? parsed.stage : "queued",
      message: typeof parsed.message === "string" ? parsed.message : "작업 상태 확인 중",
      current: typeof parsed.current === "number" && Number.isFinite(parsed.current) ? parsed.current : null,
      total: typeof parsed.total === "number" && Number.isFinite(parsed.total) ? parsed.total : null,
      percent: typeof parsed.percent === "number" && Number.isFinite(parsed.percent) ? parsed.percent : null,
      updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : null,
      startedAt: typeof parsed.startedAt === "number" && Number.isFinite(parsed.startedAt) ? parsed.startedAt : Date.now(),
    };
  } catch {
    return null;
  }
}

export function writeActiveDataTask(snapshot: DataTaskSnapshot) {
  try {
    window.sessionStorage.setItem(ACTIVE_DATA_TASK_KEY, JSON.stringify(snapshot));
  } catch {
    // The running job still works when sessionStorage is unavailable.
  }
  window.dispatchEvent(new CustomEvent<DataTaskSnapshot>(DATA_TASK_EVENT, { detail: snapshot }));
}

export function clearActiveDataTask() {
  try {
    window.sessionStorage.removeItem(ACTIVE_DATA_TASK_KEY);
  } catch {
    // Nothing else to do.
  }
  window.dispatchEvent(new CustomEvent(DATA_TASK_EVENT));
}

export function dataTaskIsRunning(snapshot: DataTaskSnapshot | null) {
  return Boolean(snapshot && !["completed", "failed", "cancelled", "unknown"].includes(snapshot.status));
}
