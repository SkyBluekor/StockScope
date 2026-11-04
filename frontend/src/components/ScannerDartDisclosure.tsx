import { useEffect, useRef, useState } from "react";
import {
  fetchJevLiveDartDisclosures,
  type JevDartLiveResponse,
} from "../services/jevApi";

/** Actual OpenDART lookup is strictly user-initiated and never persisted. */
export default function ScannerDartDisclosure({ ticker, market }: { ticker: string; market: string }) {
  const [result, setResult] = useState<JevDartLiveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    request.current?.abort();
    setResult(null);
    setError(null);
    setLoading(false);
    return () => request.current?.abort();
  }, [ticker, market]);

  const lookUp = async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const value = await fetchJevLiveDartDisclosures(ticker, market, controller.signal);
      if (controller.signal.aborted) return;
      if (
        value.stock_code !== ticker ||
        value.event_evidence_storage !== "NOT_PERSISTED_RIGHTS_UNVERIFIED" ||
        value.external_ai_transfer !== "BLOCKED" ||
        value.model_calls !== 0 || value.db_writes !== 0
      ) {
        setError("OpenDART 종목 신원 또는 보관 정책 불일치");
      } else {
        setResult(value);
      }
    } catch (reason) {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : "OpenDART 공시 조회 실패");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  };
  return (
    <details data-jev-live-dart="p6e" className="scanner-jev-motion-details">
      <summary>실제 OpenDART 공시 조회 · 최근 30일</summary>
      <div className="scanner-jev-local-readiness">
        <p>선택 종목 {ticker}의 공시를 OpenDART에서 직접 조회합니다. 요청할 때만 API를 호출하며 별도 데이터 저장이나 JEV 전송은 하지 않습니다.</p>
        <button type="button" disabled={loading} onClick={() => void lookUp()}>
          {loading ? "공시 조회 중…" : "공시 새로 조회"}
        </button>
        {error && <p role="alert">{error}</p>}
        {result && (
          <>
            <p data-jev-live-dart-count="true">
              실제 조회 {result.count}건 · 전체 {result.total_count}건
              {result.truncated ? " · 상위 일부 페이지만 표시" : ""}
            </p>
            {result.p6f_ingest_preview && (
              <p data-jev-p6f-ingest-preview="true">
                EventEvidence 정규화 후보 {result.p6f_ingest_preview.validated_metadata_count}건
                {result.p6f_ingest_preview.invalid_metadata_count > 0
                  ? " · 검증 제외 " + result.p6f_ingest_preview.invalid_metadata_count + "건"
                  : ""}
                {" · "}실제 DB 저장 0건 (권한 미승인)
              </p>
            )}
            <small>종목·기업코드 출처 대조와 이벤트 정규화는 별개입니다. 거래소 시장 정보는 이 조회에서 독립 검증되지 않았습니다.</small>
            <small>기준: {result.begin_date}~{result.end_date} · 조회 {result.fetched_at} (UTC). 공시 접수일은 날짜만 제공되어 당시 게시 시각을 증명하지 않습니다.</small>
            {result.rows.length === 0 && <p>해당 기간 공시 없음</p>}
            {result.rows.length > 0 && (
              <ul>
                {result.rows.map(item => (
                  <li key={item.receipt_no}>
                    <a href={item.viewer_url} target="_blank" rel="noopener noreferrer">
                      {item.receipt_date} · {item.report_name || "공시"} (접수번호 {item.receipt_no})
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <small>EventEvidence 영구 저장: 미승인·미실행 / 외부 AI 전송: 차단. 이 목록은 P6 사건 검증이나 투자 판단에 자동 반영되지 않습니다.</small>
          </>
        )}
      </div>
    </details>
  );
}
