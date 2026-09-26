import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchStockQuote,
  type DomesticMarketSessionResponse,
  type StockQuoteResponse,
  type StockQuoteVenue,
} from "../services/api";
import { marketSessionAllowsAutoQuote, marketSessionIsPaused } from "../services/marketSession";
import { shouldApplyQuote } from "../services/quote";
import {
  openStockQuoteStream,
  type StockQuoteStreamState,
} from "../services/quoteStream";
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
  const [streamState, setStreamState] = useState<StockQuoteStreamState>("IDLE");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const failuresRef = useRef(0);
  const quoteRef = useRef<StockQuoteResponse | null>(null);
  const streamStateRef = useRef<StockQuoteStreamState>("IDLE");
  const sessionRef = useRef<DomesticMarketSessionResponse | null>(marketSession);
  const runNowRef = useRef<((manual?: boolean) => void) | null>(null);
  const connectStreamRef = useRef<(() => void) | null>(null);
  sessionRef.current = marketSession;

  const refresh = useCallback(() => {
    runNowRef.current?.(true);
  }, []);

  useEffect(() => {
    const resourceKey = `${market}:${normalizedCode}`;
    const generation = ++generationRef.current;

    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    failuresRef.current = 0;
    quoteRef.current = null;
    streamStateRef.current = "IDLE";
    setQuote(null);
    setError(null);
    setRefreshing(false);
    setState("IDLE");
    setStreamState("IDLE");

    if (!validIdentity) {
      runNowRef.current = null;
      connectStreamRef.current = null;
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
    const closeStream = () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
    const setStream = (next: StockQuoteStreamState) => {
      if (!isCurrent()) return;
      streamStateRef.current = next;
      setStreamState(next);
    };
    const canNetwork = () => {
      if (document.visibilityState === "hidden") return false;
      return typeof navigator === "undefined" || navigator.onLine !== false;
    };
    const canAutoQuote = () =>
      canNetwork() && marketSessionAllowsAutoQuote(sessionRef.current);
    const matchesIdentity = (incoming: StockQuoteResponse) =>
      incoming.resource_key === resourceKey
      && incoming.market === market
      && incoming.ticker === normalizedCode
      && incoming.venue === venue;

    const applyQuote = (incoming: StockQuoteResponse) => {
      if (!isCurrent() || !matchesIdentity(incoming)) return false;
      if (!shouldApplyQuote(quoteRef.current, incoming)) return false;
      quoteRef.current = incoming;
      setQuote(incoming);
      setState("FRESH");
      setError(null);
      return true;
    };

    const schedule = (delayMs: number) => {
      clearTimer();
      if (
        !isCurrent()
        || permanentlyPaused
        || !canAutoQuote()
        || streamStateRef.current === "LIVE"
      ) return;
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
        if (!matchesIdentity(result)) {
          throw new Error("현재가 응답의 종목 정보가 현재 선택과 일치하지 않습니다.");
        }

        applyQuote(result);
        setState("FRESH");
        setError(null);
        failuresRef.current = 0;
        nextDelay = Math.max(1_000, pollIntervalMs);
      } catch (reason) {
        if (isAbortError(reason) || controller.signal.aborted || !isCurrent()) return;

        const apiError = reason instanceof ApiError ? reason : null;
        if (apiError?.status === 409 || apiError?.code === "KIS_QUOTE_NOT_CONFIGURED") {
          permanentlyPaused = true;
          clearTimer();
          closeStream();
          setStream("UNAVAILABLE");
          setState("NOT_CONFIGURED");
          setError(apiError.message);
          failuresRef.current = 0;
        } else if (apiError?.status === 422) {
          permanentlyPaused = true;
          clearTimer();
          closeStream();
          setStream("UNAVAILABLE");
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
          && streamStateRef.current !== "LIVE"
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

    const ensureFallback = () => {
      if (
        !isCurrent()
        || permanentlyPaused
        || !canAutoQuote()
        || streamStateRef.current === "LIVE"
        || abortRef.current != null
        || timerRef.current != null
      ) return;
      void run(false);
    };

    const connectStream = () => {
      if (!isCurrent() || permanentlyPaused || !canAutoQuote()) return;
      if (
        eventSourceRef.current
        && eventSourceRef.current.readyState !== EventSource.CLOSED
      ) return;

      closeStream();
      setStream("CONNECTING");

      let source: EventSource;
      source = openStockQuoteStream(
        normalizedCode,
        market,
        venue,
        {
          onOpen: () => {
            if (!isCurrent() || eventSourceRef.current !== source) return;
            if (streamStateRef.current !== "LIVE") setStream("CONNECTING");
          },
          onStatus: (status) => {
            if (
              !isCurrent()
              || eventSourceRef.current !== source
              || status.resource_key !== resourceKey
              || status.market !== market
              || status.ticker !== normalizedCode
              || status.venue !== venue
            ) return;

            if (status.state === "LIVE") {
              setStream("LIVE");
              clearTimer();
              failuresRef.current = 0;
              return;
            }

            if (status.state === "DEGRADED") {
              setStream("DEGRADED");
              ensureFallback();
              return;
            }

            if (status.state === "UNAVAILABLE") {
              setStream("UNAVAILABLE");
              ensureFallback();
              return;
            }

            setStream("CONNECTING");
          },
          onQuote: (incoming) => {
            if (!isCurrent() || eventSourceRef.current !== source) return;
            applyQuote(incoming);
          },
          onError: () => {
            if (!isCurrent() || eventSourceRef.current !== source) return;
            if (!canNetwork()) return;
            if (streamStateRef.current !== "UNAVAILABLE") {
              setStream("DEGRADED");
            }
            ensureFallback();
          },
        },
      );
      eventSourceRef.current = source;
    };
    connectStreamRef.current = connectStream;

    const handleVisibility = () => {
      if (!isCurrent() || document.visibilityState !== "hidden") return;
      clearTimer();
      abortRef.current?.abort();
      abortRef.current = null;
      closeStream();
      setStream("IDLE");
      setRefreshing(false);
    };
    const handleOffline = () => {
      if (!isCurrent() || permanentlyPaused) return;
      clearTimer();
      abortRef.current?.abort();
      abortRef.current = null;
      closeStream();
      setStream("DEGRADED");
      setRefreshing(false);
      setState(quoteRef.current ? "DELAYED" : "ERROR");
      setError("네트워크 연결을 확인해주세요.");
    };
    const handleOnline = () => {
      if (!isCurrent()) return;
      setError(null);
      // useDomesticMarketSession refreshes first; its checked_at update resumes quote + stream.
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
      connectStream();
    }

    return () => {
      disposed = true;
      if (runNowRef.current === runNow) runNowRef.current = null;
      if (connectStreamRef.current === connectStream) connectStreamRef.current = null;
      clearTimer();
      abortRef.current?.abort();
      abortRef.current = null;
      closeStream();
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
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      streamStateRef.current = "IDLE";
      setStreamState("IDLE");
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
      connectStreamRef.current?.();
    }
  }, [validIdentity, marketSession?.checked_at, marketSession?.phase]);

  return {
    quote,
    state,
    streamState,
    loading: state === "LOADING",
    refreshing,
    error,
    refresh,
    marketSession,
    marketSessionLoading,
    marketSessionError,
  };
}
