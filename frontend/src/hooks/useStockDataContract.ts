import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchStockDataContract,
  type StockDataContract,
  type StockDataContractRange,
} from "../services/api";

type Options = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  range?: StockDataContractRange;
  jobId?: string | null;
  enabled?: boolean;
};

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function useStockDataContract({
  code,
  market,
  range,
  jobId = null,
  enabled = true,
}: Options) {
  const [contract, setContract] = useState<StockDataContract | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    const normalizedCode = code.trim().toUpperCase();
    if (!enabled || !/^\d{6}$/.test(normalizedCode)) {
      generationRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      setContract(null);
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
      const result = await fetchStockDataContract(normalizedCode, market, {
        range,
        jobId: jobId ?? undefined,
        signal: controller.signal,
      });
      if (generation !== generationRef.current || controller.signal.aborted) return null;
      setContract(result);
      return result;
    } catch (reason) {
      if (isAbortError(reason) || generation !== generationRef.current) return null;
      setError(reason instanceof Error ? reason.message : "데이터 상태를 확인하지 못했습니다.");
      return null;
    } finally {
      if (generation === generationRef.current) {
        if (abortRef.current === controller) abortRef.current = null;
        setLoading(false);
      }
    }
  }, [code, market, range, jobId, enabled]);

  useEffect(() => {
    void refresh();
    return () => {
      generationRef.current += 1;
      abortRef.current?.abort();
    };
  }, [refresh]);

  return { contract, loading, error, refresh };
}
