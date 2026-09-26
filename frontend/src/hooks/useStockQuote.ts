import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchStockQuote,
  type DomesticMarketSessionResponse,
  type StockQuoteResponse,
  type StockQuoteVenue,
} from "../services/api";
import { marketSessionAllowsAutoQuote, marketSessionIsPaused } from "../services/marketSession";
import useDomesticMarketSession from "./useDomesticMarketSession";

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
  const normalizedCode = code.trim().toUpperCase();
  const validIdentity = enabled && /^\d{6}$/.test(normalizedCode);
  const {
    session: marketSession,
    loading: marketSessionLoading,
    error: marketSessionError,
  } = useDomesticMarketSession({ enabled: validIdentity && venue === "INTEGRATED" });

  const [quote, setQuote] = useState<StockQuoteResponse | null>(null);
  const [state, setState] = useState<StockQuotePollingState>("IDLE");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const failuresRef = useRef(0);
  const quoteRef = useRef<StockQuoteResponse | null>(null);
  const sessionRef = useRef<DomesticMarketSessionResponse | null>(marketSession);
  const runNowRef = useRef<((manual?: boolean) => void) | null>(null);
  sessionRef.current = marketSession;

  const refresh = useCallback(() => {
    runNowRef.current?.(true);
  }, []);

  useEffect(() => {
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
    setState("IDLE");

    if (!validIdentity) {
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
    const canNetwork = () => {
      if (document.visibilityState === "hidden") return false;
      return typeof navigator === "undefined" || navigator.onLine !== false;
    };
    const canAutoPoll = () =>
      canNetwork() && marketSessionAllowsAutoQuote(sessionRef.current);

    const schedule = (delayMs: number) => {
      clearTimer();
      if (!isCurrent() || permanentlyPaused || !canAutoPoll()) return;
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        void run(false);
      }, delayMs);
    };

    async function run(manual: boolean) {
      if (!isCurrent() || permanentlyPaused || !canNetwork()) return;
      if (!manual && !marketSessionAllowsAutoQuote(sessionRef.current)) return;

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
          result.resource_key !== identity
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
        } else if (apiError?.status === 422) {
          permanentlyPaused = true;
          setState("ERROR");
          setError(apiError.message);
        } else {
          failuresRef.current += 1;
          nextDelay = Math.min(
            MAX_BACKOFF_MS,
            Math.max(1_000, pollIntervalMs) * (2 ** failuresRef.current),
          );
          setState(quoteRef.current ? "DELAYED" : "ERROR");
          setError(reason instanceof Error ? reason.message : "현재가를 확인하지 못했습니다.");
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setRefreshing(false);
        }
        if (
          nextDelay != null
          && isCurrent()
          && !permanentlyPaused
          && marketSessionAllowsAutoQuote(sessionRef.current)
        ) {
          schedule(nextDelay);
        }
      }
    }

    const runNow = (manual = false) => {
      if (!isCurrent() || permanentlyPaused) return;
      clearTimer();
      abortRef.current?.abort();
      void run(manual);
    };
    runNowRef.current = runNow;

    const handleVisibility = () => {
      if (!isCurrent() || document.visibilityState !== "hidden") return;
      clearTimer();
      abortRef.current?.abort();
      setRefreshing(false);
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
      // useDomesticMarketSession refreshes first; its checked_at update resumes quote polling.
      setError(null);
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    if (
      canNetwork()
      && sessionRef.current !== null
      && marketSessionAllowsAutoQuote(sessionRef.current)
    ) {
      runNow(false);
    }

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
  }, [normalizedCode, market, venue, validIdentity, pollIntervalMs]);

  useEffect(() => {
    if (!validIdentity || !marketSession || !runNowRef.current) return;

    if (marketSessionIsPaused(marketSession.phase)) {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      abortRef.current?.abort();
      abortRef.current = null;
      setRefreshing(false);
      setState(quoteRef.current ? "FRESH" : "IDLE");
      return;
    }

    if (
      marketSessionAllowsAutoQuote(marketSession)
      && document.visibilityState !== "hidden"
      && (typeof navigator === "undefined" || navigator.onLine !== false)
    ) {
      runNowRef.current(false);
    }
  }, [validIdentity, marketSession?.checked_at, marketSession?.phase]);

  return {
    quote,
    state,
    loading: state === "LOADING",
    refreshing,
    error,
    refresh,
    marketSession,
    marketSessionLoading,
    marketSessionError,
  };
}
