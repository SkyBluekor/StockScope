import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchMarketStockImpact,
  type MarketStockImpactResponse,
} from "../services/marketImpactApi";

type Options = {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  endDate: string | null | undefined;
  enabled?: boolean;
};

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function useMarketStockImpact({
  market,
  ticker,
  endDate,
  enabled = true,
}: Options) {
  const [impact, setImpact] = useState<MarketStockImpactResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    const normalizedTicker = ticker.trim().toUpperCase();
    const normalizedEndDate = endDate?.trim() ?? "";

    if (
      !enabled ||
      !/^\d{6}$/.test(normalizedTicker) ||
      !/^\d{4}-?\d{2}-?\d{2}$/.test(normalizedEndDate)
    ) {
      generationRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      setImpact(null);
      setLoading(false);
      setError(null);
      return null;
    }

    const generation = ++generationRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const result = await fetchMarketStockImpact(
        market,
        normalizedTicker,
        normalizedEndDate,
        { signal: controller.signal },
      );
      if (generation !== generationRef.current || controller.signal.aborted) {
        return null;
      }
      setImpact(result);
      return result;
    } catch (reason) {
      if (isAbortError(reason) || generation !== generationRef.current) {
        return null;
      }
      setImpact(null);
      setError(
        reason instanceof Error
          ? reason.message
          : "시장 대비 비교 데이터를 확인하지 못했습니다.",
      );
      return null;
    } finally {
      if (generation === generationRef.current) {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setLoading(false);
      }
    }
  }, [market, ticker, endDate, enabled]);

  useEffect(() => {
    void refresh();
    return () => {
      generationRef.current += 1;
      abortRef.current?.abort();
    };
  }, [refresh]);

  return { impact, loading, error, refresh };
}
