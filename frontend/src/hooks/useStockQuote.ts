import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchStockQuote,
  type StockQuoteResponse,
  type StockQuoteVenue,
} from "../services/api";

export type StockQuotePollingState =
  | "IDLE"
  | "LOADING"
  | "FRESH"
  | "DELAYED"
  | "NOT_CONFIGURED"
  | "ERROR";

type Options = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  venue?: StockQuoteVenue;
  enabled?: boolean;
  pollIntervalMs?: number;
};

const MAX_BACKOFF_MS = 30_000;

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function useStockQuote({
  code,
  market,
  venue = "INTEGRATED",
  enabled = true,
  pollIntervalMs = 5_000,
}: Options) {
  const [quote, setQuote] = useState<StockQuoteResponse | null>(null);
  const [state, setState] = useState<StockQuotePollingState>("IDLE");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const failuresRef = useRef(0);
  const quoteRef = useRef<StockQuoteResponse | null>(null);
  const runNowRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(() => {
    runNowRef.current?.();
  }, []);

  useEffect(() => {
    const normalizedCode = code.trim().toUpperCase();
    const valid = enabled && /^\d{6}$/.test(normalizedCode);
    const identity = `${market}:${normalizedCode}:${venue}`;
    const generation = ++generationRef.current;

    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    failuresRef.current = 0;
    quoteRef.current = null;
    setQuote(null);
    setError(null);
    setRefreshing(false);
    setState(valid ? "LOADING" : "IDLE");

    if (!valid) {
      runNowRef.current = null;
      return;
    }

    let disposed = false;
    let permanentlyPaused = false;

    const isCurrent = () => !disposed && generationRef.current === generation;

    const clearTimer = () => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const canPoll = () =>
      document.visibilityState !== "hidden"
      && (typeof navigator === "undefined" || navigator.onLine !== false);

    const schedule = (delayMs: number) => {
      clearTimer();
      if (!isCurrent() || !canPoll()) return;
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        void run();
      }, delayMs);
    };

    async function run() {
      if (!isCurrent() || !canPoll()) return;

      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;
      const hadQuote = quoteRef.current !== null;
      setRefreshing(hadQuote);
      if (!hadQuote) setState("LOADING");
      setError(null);

      let nextDelay: number | null = null;
      try {
        const result = await fetchStockQuote(normalizedCode, market, {
          venue,
          signal: controller.signal,
        });
        if (!isCurrent() || controller.signal.aborted) return;
        if (
          result.resource_key !== `${market}:${normalizedCode}`
          || result.market !== market
          || result.ticker !== normalizedCode
          || result.venue !== venue
        ) {
          throw new Error("현재가 응답의 종목 정보가 현재 선택과 일치하지 않습니다.");
        }

        quoteRef.current = result;
        setQuote(result);
        setState("FRESH");
        setError(null);
        failuresRef.current = 0;
        nextDelay = Math.max(1_000, pollIntervalMs);
      } catch (reason) {
        if (isAbortError(reason) || controller.signal.aborted || !isCurrent()) return;

        const apiError = reason instanceof ApiError ? reason : null;
        if (apiError?.status === 409 || apiError?.code === "KIS_QUOTE_NOT_CONFIGURED") {
          permanentlyPaused = true;
          setState("NOT_CONFIGURED");
          setError(apiError.message);
          failuresRef.current = 0;
          nextDelay = null;
        } else if (apiError?.status === 422) {
          permanentlyPaused = true;
          setState("ERROR");
          setError(apiError.message);
          nextDelay = null;
        } else {
          failuresRef.current += 1;
          const delay = Math.min(
            MAX_BACKOFF_MS,
            Math.max(1_000, pollIntervalMs) * (2 ** failuresRef.current),
          );
          setState(quoteRef.current ? "DELAYED" : "ERROR");
          setError(reason instanceof Error ? reason.message : "현재가를 확인하지 못했습니다.");
          nextDelay = delay;
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setRefreshing(false);
        }
        if (nextDelay != null && isCurrent() && canPoll()) {
          schedule(nextDelay);
        }
      }
    }

    const runNow = () => {
      if (!isCurrent() || permanentlyPaused) return;
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
        setRefreshing(false);
        return;
      }
      runNow();
    };

    const handleOffline = () => {
      if (!isCurrent() || permanentlyPaused) return;
      clearTimer();
      abortRef.current?.abort();
      setRefreshing(false);
      setState(quoteRef.current ? "DELAYED" : "ERROR");
      setError("네트워크 연결을 확인해주세요.");
    };

    const handleOnline = () => {
      if (!isCurrent()) return;
      runNow();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    if (canPoll()) runNow();

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
  }, [code, market, venue, enabled, pollIntervalMs]);

  return {
    quote,
    state,
    loading: state === "LOADING",
    refreshing,
    error,
    refresh,
  };
}
