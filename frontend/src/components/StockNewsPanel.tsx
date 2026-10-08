import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchStockEventEvidence,
  fetchStockNews,
  type StockEventEvidenceItem,
  type StockEventEvidenceResponse,
  type StockNewsResponse,
} from "../services/api";
import "../stock-analysis.css";

type Props = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  companyLabel?: string;
  variant?: "full" | "compact" | "summary";
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

function eventTypeLabel(value: string) {
  const labels: Record<string, string> = {
    RIGHTS_ISSUE: "유상증자",
    CONVERTIBLE_BOND: "전환사채",
    BW: "신주인수권부사채",
    CAPITAL_REDUCTION: "감자",
    MERGER: "합병",
    SPLIT: "분할",
    DISTRESS: "재무 위험",
    MAJOR_SHAREHOLDER: "주요주주",
    LARGE_CONTRACT: "대규모 계약",
    EARNINGS_CHANGE: "실적 변동",
    LITIGATION: "소송",
    TREASURY: "자사주",
    DIVIDEND: "배당",
  };
  return labels[value] ?? "이벤트 근거";
}

function relationLabel(value: string) {
  const labels: Record<string, string> = {
    DIRECT_COMPANY: "직접 관련",
    SUBSIDIARY: "자회사 관계",
    CUSTOMER: "고객사 관계",
    SUPPLIER: "공급사 관계",
    COMPETITOR: "경쟁사 관계",
    INDUSTRY: "업종 관련",
    POLICY_EXPOSURE: "정책 노출",
    MACRO_EXPOSURE: "시장 환경 관련",
  };
  return labels[value] ?? "관계 확인";
}

function sourceKindLabel(value: string) {
  if (value === "OPENDART_DISCLOSURE") return "OpenDART";
  if (value.startsWith("NAVER")) return "네이버 뉴스";
  return value.replace(/_/g, " ");
}

function qualityLabel(value: StockEventEvidenceItem["quality_state"]) {
  return value === "USABLE" ? "참고 가능" : "제한된 참고";
}

function eventEvidenceSummary(
  evidence: StockEventEvidenceResponse | null,
  loading: boolean,
  error: string | null,
) {
  if (loading && !evidence) return "이벤트 근거 확인 중 · 방향 예측 미제공";
  if (error) return "이벤트 근거 상태를 현재 확인하지 못했습니다 · 방향 예측 미제공";
  if (!evidence) return "검증된 이벤트 근거 없음 · 방향 예측 미제공";
  if (evidence.event_evidence.status === "EVIDENCE_BLOCKED") {
    return "무결성을 확인하지 못한 이벤트 근거는 참고에서 제외 · 방향 예측 미제공";
  }
  if (evidence.event_evidence.reference_count > 0) {
    return `참고 가능한 이벤트 근거 ${evidence.event_evidence.reference_count}건 · 방향 예측은 아직 미검증`;
  }
  return "검증된 이벤트 근거 없음 · 방향 예측 미제공";
}

function eventEvidenceDetail(
  evidence: StockEventEvidenceResponse | null,
  loading: boolean,
  error: string | null,
) {
  if (loading && !evidence) return "검증된 이벤트 근거 상태를 확인하고 있습니다.";
  if (error) return "이벤트 근거 상태를 현재 확인하지 못했습니다. 최근 뉴스와 기존 종목 분석은 계속 이용할 수 있습니다.";
  if (!evidence || evidence.event_evidence.status === "NO_VALIDATED_EVIDENCE") {
    return "현재 이 종목에 연결된 검증 가능한 참고 근거가 없습니다.";
  }
  if (evidence.event_evidence.status === "EVIDENCE_BLOCKED") {
    return "무결성을 확인하지 못한 근거는 사용자 참고 정보에서 제외했습니다.";
  }
  if (evidence.event_evidence.status === "REFERENCE_LIMITED") {
    return "제한 조건이 있는 참고 근거만 확인됐습니다. 방향 판단이나 점수에는 사용하지 않습니다.";
  }
  return "검증된 범위에서 참고 가능한 이벤트 근거가 있습니다. Strategy·Scanner 점수에는 반영하지 않습니다.";
}

function valueValidationDetail(evidence: StockEventEvidenceResponse | null) {
  if (!evidence || evidence.value_validation.status === "NOT_EVALUATED") {
    return "이벤트 정보의 제품 증분 가치는 아직 실제 자료로 평가되지 않았습니다.";
  }
  switch (evidence.value_validation.status) {
    case "PASS":
      return "참고 정보로 연결할 수 있는 범위가 확인됐습니다. 주가 방향 예측 승인을 뜻하지 않습니다.";
    case "HOLD":
      return "현재 검증 기준에서는 연구·보류 상태입니다.";
    case "FAIL":
      return "현재 검증 범위에서는 추가적인 제품 가치를 확인하지 못했습니다.";
    case "BLOCKED":
      return "제품 가치 검증의 무결성 또는 입력 상태를 확인하지 못했습니다.";
    default:
      return "이벤트 정보의 제품 가치 상태를 확인할 수 없습니다.";
  }
}

export default function StockNewsPanel({ code, market, companyLabel, variant = "full" }: Props) {
  const [news, setNews] = useState<StockNewsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; code: string | null } | null>(null);
  const [evidence, setEvidence] = useState<StockEventEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const requestIdRef = useRef(0);
  const compact = variant !== "full";
  // Preserve the existing full/compact contracts; summary is a separate cap.
  const requestLimit = compact ? 5 : 10;
  const collapsedLimit = compact ? 3 : 5;
  const expandedLimit = compact ? 5 : 10;
  const summaryLimit = variant === "summary" ? 2 : requestLimit;

  useEffect(() => {
    if (!code) {
      setNews(null);
      setError(null);
      setLoading(false);
      setEvidence(null);
      setEvidenceError(null);
      setEvidenceLoading(false);
      return;
    }

    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    setNews(null);
    setError(null);
    setExpanded(false);
    setLoading(true);

    if (compact) {
      setEvidence(null);
      setEvidenceError(null);
      setEvidenceLoading(false);
    } else {
      setEvidence(null);
      setEvidenceError(null);
      setEvidenceLoading(true);
      void fetchStockEventEvidence(code, market, { signal: controller.signal })
        .then((result) => {
          if (requestId !== requestIdRef.current || controller.signal.aborted) return;
          setEvidence(result);
        })
        .catch((reason: unknown) => {
          if (controller.signal.aborted || requestId !== requestIdRef.current) return;
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          if (reason instanceof ApiError && reason.code === "EVENT_EVIDENCE_SCHEMA_NOT_READY") {
            setEvidenceError("이벤트 근거 기능 준비 중");
            return;
          }
          setEvidenceError("이벤트 근거 상태를 현재 확인하지 못했습니다.");
        })
        .finally(() => {
          if (requestId === requestIdRef.current && !controller.signal.aborted) {
            setEvidenceLoading(false);
          }
        });
    }

    const newsRequest = variant === "summary"
      ? fetchStockNews(code, market, { limit: summaryLimit, signal: controller.signal })
      : fetchStockNews(code, market, { limit: requestLimit, signal: controller.signal });
    void newsRequest
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
  }, [code, market, refreshToken, requestLimit, summaryLimit, compact, variant]);

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
          <strong>최근 뉴스만 불러오지 못했습니다.</strong>
          <span>{errorMessage(error.code, error.message)}</span>
          <small>종목 분석과 전략 계산 결과에는 영향을 주지 않습니다.</small>
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
                    {compact ? (
                      <>
                        <time className="stock-news-time" dateTime={item.published_at ?? undefined}>{formatTimestamp(item.published_at)}</time>
                        <span className="stock-news-source">{sourceLabel(item.source_name, item.source_domain)}</span>
                      </>
                    ) : (
                      <>
                        <span className="stock-news-source">{sourceLabel(item.source_name, item.source_domain)}</span>
                        <time className="stock-news-time" dateTime={item.published_at ?? undefined}>{formatTimestamp(item.published_at)}</time>
                      </>
                    )}
                  </div>
                  <h4>
                    <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                  </h4>
                  {item.description && <p>{item.description}</p>}
                </div>
                {compact && (
                  <a className="stock-news-origin" href={item.url} target="_blank" rel="noopener noreferrer" aria-label={`${item.title} 원문 새 탭에서 열기`}>원문 ↗</a>
                )}
              </article>
            ))}
          </div>

          {variant !== "summary" && (news?.count ?? 0) > collapsedLimit && (
            <button type="button" className="stock-news-more" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "간단히 보기" : "최근 뉴스 더 보기 (" + Math.min(news?.count ?? 0, expandedLimit) + "건)"}
            </button>
          )}

          {news && variant !== "summary" && (
            <p className="stock-news-footnote">
              뉴스 검색 결과는 참고 정보이며 StockScope의 Strategy·Scanner·Ranking·Risk 계산을 변경하지 않습니다.
              현재 뉴스 목록은 기사 검색 결과이며 호재·악재 또는 주가 방향을 판정하지 않습니다.
            </p>
          )}
        </>
      )}

      {!compact && (
        <>
          <p className={`stock-news-evidence-state ${evidenceError ? "error" : ""}`}>
            {eventEvidenceSummary(evidence, evidenceLoading, evidenceError)}
          </p>
          <details className="stock-news-scope-details">
            <summary>뉴스·이벤트 근거 범위 보기</summary>
            <div>
              <strong>최근 뉴스</strong>
              <p>기업명 기반 최근 검색 결과를 표시합니다. 기사 목록 자체는 Strategy·Scanner·Ranking·Risk 계산에 사용하지 않습니다.</p>
              <p>검증되지 않은 자동 영향 연결과 주가 방향 예측은 현재 이 화면에서는 제공하지 않습니다.</p>

              <strong>검증된 이벤트 근거</strong>
              <p>{eventEvidenceDetail(evidence, evidenceLoading, evidenceError)}</p>
              {evidence && evidence.event_evidence.items.length > 0 && (
                <ul className="stock-news-evidence-detail-list">
                  {evidence.event_evidence.items.map((item, index) => (
                    <li key={`${item.event_type}-${item.assessment_as_of}-${index}`}>
                      <b>{eventTypeLabel(item.event_type)} · {relationLabel(item.relation_type)}</b>
                      <span>
                        {item.source_kinds.map(sourceKindLabel).join(", ")}
                        {" · "}
                        확인 {formatTimestamp(item.evidence_as_of)}
                        {" · "}
                        {qualityLabel(item.quality_state)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <strong>제품 가치 검증</strong>
              <p>{valueValidationDetail(evidence)}</p>

              <strong>방향 예측</strong>
              <p>주가 방향 예측은 아직 검증되지 않아 제공하지 않습니다. 이벤트 근거가 있어도 예측·확률·Strategy 점수로 자동 변환하지 않습니다.</p>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
