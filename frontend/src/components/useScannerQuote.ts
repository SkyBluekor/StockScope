import { useEffect, useRef, useState } from "react";
import {
  fetchDomesticMarketSession,
  fetchStockQuote,
  type ScannerCandidate,
} from "../services/api";
import {
  EMPTY_SCANNER_QUOTE,
  quoteMatchesCandidate,
  type ScannerQuoteSnapshot,
} from "./scannerQuoteTruth";

/**
 * Hoisted to CandidateDetail, not the tab body: one explicit quote lookup
 * survives tab changes but never follows the next selected candidate.
 * CandidateDetail is keyed by candidate and analysis execution identity.
 */
export default function useScannerQuote(candidate: ScannerCandidate) {
  const [snapshot, setSnapshot] = useState<ScannerQuoteSnapshot>(EMPTY_SCANNER_QUOTE);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => {
    controllerRef.current?.abort();
  }, []);

  async function checkPrice() {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setSnapshot({ ...EMPTY_SCANNER_QUOTE, loading: true });
    try {
      const [quoteResult, sessionResult] = await Promise.allSettled([
        fetchStockQuote(candidate.code, candidate.market, { signal: controller.signal }),
        fetchDomesticMarketSession({ signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      if (quoteResult.status !== "fulfilled" || !quoteResult.value) {
        throw new Error("새 시세를 확인하지 못했습니다. 분석 당시의 가격만 참고하세요.");
      }
      if (!quoteMatchesCandidate(quoteResult.value, candidate)) {
        throw new Error("요청한 종목과 다른 시세가 도착했어요. 결과를 적용하지 않고 다시 조회해야 해요.");
      }
      setSnapshot({
        quote: quoteResult.value,
        marketSession: sessionResult.status === "fulfilled" ? sessionResult.value : null,
        loading: false,
        error: null,
      });
    } catch (reason) {
      if (controller.signal.aborted) return;
      setSnapshot({
        ...EMPTY_SCANNER_QUOTE,
        error: reason instanceof Error ? reason.message : "시세를 확인하지 못했습니다.",
      });
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }

  return { snapshot, checkPrice };
}
