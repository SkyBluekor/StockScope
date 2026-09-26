import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchDomesticMarketSession,
  type DomesticMarketSessionResponse,
} from "../services/api";

type Options = {
  enabled?: boolean;
  fallbackRecheckMs?: number;
};

const DEFAULT_RECHECK_MS = 30 * 60 * 1000;

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function unknownSession(reasonCode: string): DomesticMarketSessionResponse {
  const now = new Date();
  const localDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return {
    market: "DOMESTIC_EQUITY",
    venue: "INTEGRATED",
    timezone: "Asia/Seoul",
    checked_at: now.toISOString(),
    local_date: localDate,
    trading_day: null,
    phase: "UNKNOWN",
    quote_polling_allowed: true,
    market_active: null,
    next_transition_at: null,
    source: "UNKNOWN",
    reason_code: reasonCode,
  };
}

export default function useDomesticMarketSession({
  enabled = true,
  fallbackRecheckMs = DEFAULT_RECHECK_MS,
}: Options = {}) {
  const [session, setSession] = useState<DomesticMarketSessionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const runNowRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(() => {
    runNowRef.current?.();
  }, []);

  useEffect(() => {
    const generation = ++generationRef.current;
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;

    if (!enabled) {
      setSession(null);
      setLoading(false);
      setError(null);
      runNowRef.current = null;
      return;
    }

    let disposed = false;
    const isCurrent = () => !disposed && generationRef.current === generation;
    const canRequest = () =>
      document.visibilityState !== "hidden"
      && (typeof navigator === "undefined" || navigator.onLine !== false);

    const clearTimer = () => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const schedule = (result: DomesticMarketSessionResponse | null) => {
      clearTimer();
      if (!isCurrent() || !canRequest()) return;

      let delay = Math.max(60_000, fallbackRecheckMs);
      if (result?.next_transition_at) {
        const transition = new Date(result.next_transition_at).getTime();
        if (Number.isFinite(transition)) {
          delay = Math.max(1_000, transition - Date.now() + 250);
        }
      }
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        void run();
      }, delay);
    };

    async function run() {
      if (!isCurrent() || !canRequest()) return;
      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;
      setLoading(true);

      try {
        const result = await fetchDomesticMarketSession({
          venue: "INTEGRATED",
          signal: controller.signal,
        });
        if (!isCurrent() || controller.signal.aborted) return;
        setSession(result);
        setError(null);
        schedule(result);
      } catch (reason) {
        if (isAbortError(reason) || controller.signal.aborted || !isCurrent()) return;
        const fallback = unknownSession("MARKET_SESSION_REQUEST_FAILED");
        setSession(fallback);
        setError(reason instanceof Error ? reason.message : "시장 운영 상태를 확인하지 못했습니다.");
        schedule(fallback);
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        if (isCurrent()) setLoading(false);
      }
    }

    const runNow = () => {
      if (!isCurrent()) return;
      clearTimer();
      abortRef.current?.abort();
      void run();
    };
    runNowRef.current = runNow;

    const handleVisibility = () => {
      if (!isCurrent()) return;
      if (document.visibilityState === "hidden") {
        clearTimer();
        abortRef.current?.abort();
        setLoading(false);
        return;
      }
      runNow();
    };
    const handleOffline = () => {
      if (!isCurrent()) return;
      clearTimer();
      abortRef.current?.abort();
      setLoading(false);
    };
    const handleOnline = () => {
      if (!isCurrent()) return;
      runNow();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    if (canRequest()) runNow();

    return () => {
      disposed = true;
      if (runNowRef.current === runNow) runNowRef.current = null;
      clearTimer();
      abortRef.current?.abort();
      abortRef.current = null;
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, [enabled, fallbackRecheckMs]);

  return { session, loading, error, refresh };
}
