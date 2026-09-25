import { useEffect, useRef, useState } from "react";
import { ApiError, fetchStockNews, type StockNewsResponse } from "../services/api";
import "../stock-analysis.css";

type Props = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  companyLabel?: string;
  variant?: "full" | "compact";
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

function errorMessage(code: string | null, message: string) {
  switch (code) {
    case "NEWS_NOT_CONFIGURED":
      return "뉴스 API 설정을 확인해주세요.";
    case "NEWS_AUTH_FAILED":
      return "뉴스 API 인증 정보를 확인해주세요.";
    case "NEWS_RATE_LIMITED":
      return "뉴스 API 호출 한도에 도달했습니다. 잠시 후 다시 확인해주세요.";
    case "NEWS_TIMEOUT":
      return "뉴스 서비스 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.";
    default:
      return message;
  }
}

export default function StockNewsPanel({ code, market, companyLabel, variant = "full" }: Props) {
  const [news, setNews] = useState<StockNewsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code: string | null } | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const requestIdRef = useRef(0);
  const compact = variant === "compact";
  const requestLimit = compact ? 5 : 10;
  const collapsedLimit = compact ? 3 : 5;
  const expandedLimit = compact ? 5 : 10;

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

    void fetchStockNews(code, market, { limit: requestLimit, signal: controller.signal })
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
  }, [code, market, refreshToken, requestLimit]);

  const visibleItems = news?.items.slice(0, expanded ? expandedLimit : collapsedLimit) ?? [];
  const title = news?.company_name || companyLabel || code;

  return (
    <section className={`stock-news-panel ${compact ? "compact" : "full"}`} aria-label="최근 뉴스">
      <div className="stock-news-head">
        <div>
          <h3>최근 뉴스</h3>
          <p>{compact
            ? `${title} 이름으로 조회한 최근 기사입니다.`
            : `${title} 이름으로 조회한 최근 네이버 뉴스 검색 결과입니다.`}</p>
        </div>
        <div>
          {news?.fetched_at && <small>마지막 확인 {formatTimestamp(news.fetched_at)}</small>}
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)} disabled={loading}>
            {loading ? "불러오는 중" : "새로고침"}
          </button>
        </div>
      </div>

      {loading && !news ? (
        <div className="stock-news-state">최근 뉴스를 불러오는 중입니다...</div>
      ) : error ? (
        <div className="stock-news-state error">
          <strong>최근 뉴스를 불러오지 못했습니다.</strong>
          <span>{errorMessage(error.code, error.message)}</span>
        </div>
      ) : news && news.count === 0 ? (
        <div className="stock-news-state">
          <strong>현재 조회된 최근 뉴스가 없습니다.</strong>
          <span>검색 결과 없음은 뉴스 서비스 오류와 별개의 상태입니다.</span>
        </div>
      ) : (
        <>
          <div className="stock-news-list">
            {visibleItems.map((item) => (
              <article key={item.id} className="stock-news-item">
                <div className="stock-news-item-copy">
                  <div className="stock-news-meta">
                    <time dateTime={item.published_at ?? undefined}>{formatTimestamp(item.published_at)}</time>
                    <span>{sourceLabel(item.source_name, item.source_domain)}</span>
                  </div>
                  <h4>
                    <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                  </h4>
                  {item.description && <p>{item.description}</p>}
                </div>
                <a className="stock-news-origin" href={item.url} target="_blank" rel="noopener noreferrer" aria-label={`${item.title} 원문 새 탭에서 열기`}>원문 ↗</a>
              </article>
            ))}
          </div>

          {(news?.count ?? 0) > collapsedLimit && (
            <button type="button" className="stock-news-more" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "간단히 보기" : "최근 뉴스 더 보기 (" + Math.min(news?.count ?? 0, expandedLimit) + "건)"}
            </button>
          )}

          {news && (
            <>
              <p className="stock-news-footnote">
                뉴스 검색 결과는 참고 정보이며 StockScope의 Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다.
                현재 뉴스 목록은 기사 검색 결과이며 호재·악재 또는 주가 방향을 판정하지 않습니다.
              </p>
              {!compact && (
                <details className="stock-news-scope-details">
                  <summary>뉴스 분석 범위 보기</summary>
                  <div>
                    <strong>현재 제공 범위</strong>
                    <p>기업명 기반 최근 기사 검색 결과만 제공합니다.</p>
                    <p>업종·정책·국제 이슈와 종목의 영향 연결, 주가 방향 예측은 현재 이 화면에서는 제공하지 않습니다. 관련성과 영향 방향을 검증할 수 있는 별도 데이터가 마련된 경우에만 별도 분석으로 표시합니다.</p>
                  </div>
                </details>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
