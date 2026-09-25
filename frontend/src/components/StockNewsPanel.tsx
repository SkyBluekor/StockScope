import { useEffect, useRef, useState } from "react";
import { ApiError, fetchStockNews, type StockNewsResponse } from "../services/api";

type Props = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  companyLabel?: string;
};

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "시각 정보 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "시각 정보 없음";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function sourceLabel(sourceName: string | null, sourceDomain: string | null) {
  return sourceName || sourceDomain || "출처 확인";
}

export default function StockNewsPanel({ code, market, companyLabel }: Props) {
  const [news, setNews] = useState<StockNewsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code: string | null } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!code) {
      setNews(null);
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    setNews(null);
    setError(null);
    setExpanded(false);
    setLoading(true);

    void fetchStockNews(code, market, { limit: 10, signal: controller.signal })
      .then((result) => {
        if (requestId !== requestIdRef.current || controller.signal.aborted) return;
        setNews(result);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return;
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (reason instanceof ApiError) {
          setError({ message: reason.message, code: reason.code });
          return;
        }
        setError({
          message: reason instanceof Error ? reason.message : "최근 뉴스를 불러오지 못했습니다.",
          code: null,
        });
      })
      .finally(() => {
        if (requestId === requestIdRef.current && !controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [code, market, refreshToken]);

  const visibleItems = news?.items.slice(0, expanded ? 10 : 5) ?? [];
  const title = news?.company_name || companyLabel || code;

  return (
    <section className="stock-news-panel" aria-label="최근 뉴스">
      <div className="stock-news-head">
        <div>
          <span>NEWS</span>
          <h3>최근 뉴스</h3>
          <p>{title}와 직접 관련된 네이버 검색 결과를 최신순으로 표시합니다.</p>
        </div>
        <div>
          {news?.fetched_at && <small>마지막 확인 {formatTimestamp(news.fetched_at)}</small>}
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)} disabled={loading}>
            {loading ? "불러오는 중" : "새로고침"}
          </button>
        </div>
      </div>

      {loading && !news ? (
        <div className="stock-news-state">최근 뉴스를 불러오는 중입니다.</div>
      ) : error ? (
        <div className="stock-news-state error">
          <strong>최근 뉴스를 불러오지 못했습니다.</strong>
          <span>{error.code === "NEWS_NOT_CONFIGURED" ? "뉴스 API 설정을 확인해주세요." : error.message}</span>
        </div>
      ) : news && news.count === 0 ? (
        <div className="stock-news-state">
          <strong>최근 검색 결과가 없습니다.</strong>
          <span>뉴스가 없다는 뜻과 뉴스 서비스 오류는 구분해서 표시합니다.</span>
        </div>
      ) : (
        <>
          <div className="stock-news-list">
            {visibleItems.map((item) => (
              <article key={item.id} className="stock-news-item">
                <div className="stock-news-meta">
                  <time dateTime={item.published_at ?? undefined}>{formatTimestamp(item.published_at)}</time>
                  <span>{sourceLabel(item.source_name, item.source_domain)}</span>
                </div>
                <h4>
                  <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                </h4>
                {item.description && <p>{item.description}</p>}
                <a className="stock-news-origin" href={item.url} target="_blank" rel="noopener noreferrer">원문 보기</a>
              </article>
            ))}
          </div>

          {(news?.count ?? 0) > 5 && (
            <button type="button" className="stock-news-more" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "간단히 보기" : "최근 뉴스 더 보기 (" + Math.min(news?.count ?? 0, 10) + "건)"}
            </button>
          )}

          {news && (
            <p className="stock-news-footnote">
              뉴스 검색 결과는 참고 정보이며 StockScope의 Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다.
            </p>
          )}
        </>
      )}
    </section>
  );
}
