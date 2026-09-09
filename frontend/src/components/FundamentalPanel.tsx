import type { StrategyAnalysis } from "../services/api";
import { TermHelp } from "./BeginnerHelp";

function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000_000) return `${sign}${(abs / 1_000_000_000_000).toFixed(2)}조원`;
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(abs >= 1_000_000_000 ? 1 : 2)}억원`;
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString("ko-KR")}만원`;
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function percent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function ratio(value: number | null | undefined, suffix = "배") {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value.toFixed(2)}${suffix}`;
}

function axisClass(status: string) {
  if (status === "STRONG" || status === "GOOD") return "positive";
  if (status === "WEAK") return "negative";
  if (status === "CAUTION") return "caution";
  return "neutral";
}

function yoy(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "전년동기 비교 없음";
  return `전년동기 ${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function FundamentalPanel({ analysis }: { analysis: StrategyAnalysis }) {
  const data = analysis.fundamental;

  if (!data.available) {
    return (
      <section className="fundamental-panel unavailable">
        <div className="fundamental-head">
          <div>
            <span>FUNDAMENTAL ENGINE · v0.17.1</span>
            <h3>재무 체력 분석</h3>
            <p>{data.overall.summary}</p>
          </div>
          <div className="fundamental-overall"><span>현재 결과</span><strong>분석 불가</strong></div>
        </div>
        <div className="fundamental-unavailable">재무 분석이 없어도 기술·상대강도·리스크 분석은 계속 사용할 수 있습니다.</div>
      </section>
    );
  }

  const axes = ["profitability", "growth", "stability", "cashflow"]
    .map((key) => data.axes[key])
    .filter(Boolean);
  const valuation = data.valuation.preview ?? data.valuation.eod;
  const annualLatest = data.latest_metrics;
  const recent = data.recent_performance;
  const latestReport = data.latest_report;

  return (
    <section className={`fundamental-panel overall-${data.overall.status.toLowerCase()}`}>
      <div className="fundamental-head">
        <div>
          <span>FUNDAMENTAL ENGINE · v0.17.1</span>
          <div className="title-with-help">
            <h3>회사의 최신 재무 상태는 어떤가?</h3>
            <TermHelp term="fundamental_health" current={data.overall.summary} />
          </div>
          <p>{data.overall.headline}</p>
        </div>
        <div className="fundamental-overall">
          <span>{latestReport?.period_label ?? `${data.latest_year}년`} · {data.statement_basis_label ?? "연결"}</span>
          <strong>{data.overall.label}</strong>
          <em>{data.archetype.label}</em>
        </div>
      </div>

      {data.freshness && (
        <div className={`fundamental-freshness ${data.freshness.status.toLowerCase()}`}>
          <div>
            <span>최신 실적 기준</span>
            <strong>{data.freshness.label}</strong>
          </div>
          <p>{data.freshness.message}</p>
        </div>
      )}

      <div className="fundamental-result-hero">
        <span>프로그램 결론</span>
        <strong>{data.archetype.label}</strong>
        <p>{data.archetype.summary}</p>
      </div>

      {recent && (
        <div className="fundamental-recent-performance">
          <div className="fundamental-recent-head">
            <div>
              <span>가장 최근 공식 실적</span>
              <strong>{recent.period_label}</strong>
            </div>
            <small>
              {recent.compare_label
                ? `${recent.compare_label}와 같은 기간끼리 비교`
                : "전년 동일 기간 비교 데이터 없음"}
            </small>
          </div>
          <div className="fundamental-recent-grid">
            <article>
              <span className="term-inline">매출 <TermHelp term="revenue" /></span>
              <strong>{money(recent.revenue)}</strong>
              <b className={(recent.revenue_yoy_pct ?? 0) >= 0 ? "up" : "down"}>{yoy(recent.revenue_yoy_pct)}</b>
            </article>
            <article>
              <span className="term-inline">영업이익 <TermHelp term="operating_profit" /></span>
              <strong>{money(recent.operating_profit)}</strong>
              <b className={(recent.operating_profit_yoy_pct ?? 0) >= 0 ? "up" : "down"}>{yoy(recent.operating_profit_yoy_pct)}</b>
            </article>
            <article>
              <span className="term-inline">순이익 <TermHelp term="net_income" /></span>
              <strong>{money(recent.net_income)}</strong>
              <b className={(recent.net_income_yoy_pct ?? 0) >= 0 ? "up" : "down"}>{yoy(recent.net_income_yoy_pct)}</b>
            </article>
            <article>
              <span className="term-inline">영업현금 <TermHelp term="operating_cash_flow" /></span>
              <strong>{money(recent.operating_cash_flow)}</strong>
              <b className={(recent.operating_cash_flow_yoy_pct ?? 0) >= 0 ? "up" : "down"}>{yoy(recent.operating_cash_flow_yoy_pct)}</b>
            </article>
          </div>
          <p className="fundamental-period-policy">
            분기·반기 실적은 연간 실적과 직접 비교하지 않고 같은 기간의 전년 실적과만 비교합니다.
          </p>
        </div>
      )}

      <div className="fundamental-axis-grid">
        {axes.map((axis) => (
          <article className={axisClass(axis.status)} key={axis.code}>
            <span>{axis.label}</span>
            <strong>{axis.status_label}</strong>
            <p>{axis.headline}</p>
            {axis.evidence.length > 0 && <small>{axis.evidence.slice(0, 2).join(" · ")}</small>}
          </article>
        ))}
        <article className={data.valuation.status === "HIGH_MULTIPLE" ? "caution" : data.valuation.status === "LOW_MULTIPLE" ? "positive" : "neutral"}>
          <span className="term-inline">가격 배수 <TermHelp term="per" current={data.valuation.message} /></span>
          <strong>{data.valuation.label}</strong>
          <p>{data.valuation.message}</p>
          <small>PER {ratio(valuation.per)} · PBR {ratio(valuation.pbr)}</small>
        </article>
      </div>

      {(data.strengths.length > 0 || data.warnings.length > 0) && (
        <div className="fundamental-takeaways">
          <article>
            <strong>좋게 보는 이유</strong>
            {data.strengths.length > 0 ? <ul>{data.strengths.map((item) => <li key={item}>{item}</li>)}</ul> : <p>뚜렷한 재무 강점이 아직 부족합니다.</p>}
          </article>
          <article className="warning">
            <strong>주의해서 볼 부분</strong>
            {data.warnings.length > 0 ? <ul>{data.warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <p>현재 자동 분석에서 큰 재무 경고는 확인되지 않았습니다.</p>}
          </article>
        </div>
      )}

      {data.watch_points.length > 0 && (
        <div className="fundamental-watch">
          <strong>다음 정기실적에서 앱이 다시 볼 것</strong>
          <div>{data.watch_points.map((item) => <span key={item}>{item}</span>)}</div>
        </div>
      )}

      <details className="fundamental-details">
        <summary>
          <span>
            <strong>최근 실적과 연간 추세 자세히 보기</strong>
            <small>최신 정기보고서의 전년동기 비교 + 장기 사업보고서 추세</small>
          </span>
          <b>펼치기</b>
        </summary>

        {recent && data.prior_same_period && (
          <div className="fundamental-period-compare">
            <div className="fundamental-period-row header">
              <span>기간</span><span>매출</span><span>영업이익</span><span>순이익</span><span>영업현금</span>
            </div>
            <div className="fundamental-period-row">
              <strong>{recent.period_label}</strong>
              <span>{money(recent.revenue)}</span>
              <span>{money(recent.operating_profit)}</span>
              <span>{money(recent.net_income)}</span>
              <span>{money(recent.operating_cash_flow)}</span>
            </div>
            <div className="fundamental-period-row">
              <strong>{data.prior_same_period.period_label ?? data.prior_same_period.year}</strong>
              <span>{money(data.prior_same_period.revenue)}</span>
              <span>{money(data.prior_same_period.operating_profit)}</span>
              <span>{money(data.prior_same_period.net_income)}</span>
              <span>{money(data.prior_same_period.operating_cash_flow)}</span>
            </div>
          </div>
        )}

        <div className="fundamental-subsection-title">
          <strong>최근 연간 기준 보조지표</strong>
          <small>{data.annual_latest_year ?? data.latest_year} 사업보고서 기준 · ROE/PER 계산에는 연간값을 사용합니다.</small>
        </div>
        <div className="fundamental-latest-grid">
          <article><span className="term-inline">매출 <TermHelp term="revenue" /></span><strong>{money(annualLatest?.revenue)}</strong></article>
          <article><span className="term-inline">영업이익 <TermHelp term="operating_profit" /></span><strong>{money(annualLatest?.operating_profit)}</strong></article>
          <article><span className="term-inline">순이익 <TermHelp term="net_income" /></span><strong>{money(annualLatest?.net_income)}</strong></article>
          <article><span className="term-inline">영업이익률 <TermHelp term="operating_margin" /></span><strong>{percent(annualLatest?.operating_margin_pct)}</strong></article>
          <article><span className="term-inline">ROE <TermHelp term="roe" /></span><strong>{percent(annualLatest?.roe_pct)}</strong></article>
          <article><span className="term-inline">부채비율 <TermHelp term="debt_ratio" /></span><strong>{percent(annualLatest?.debt_ratio_pct)}</strong></article>
          <article><span className="term-inline">유동비율 <TermHelp term="current_ratio" /></span><strong>{percent(annualLatest?.current_ratio_pct)}</strong></article>
          <article><span className="term-inline">영업현금흐름 <TermHelp term="operating_cash_flow" /></span><strong>{money(annualLatest?.operating_cash_flow)}</strong></article>
        </div>

        <div className="fundamental-year-table">
          <div className="fundamental-year-row header">
            <span>연도</span><span>매출</span><span>영업이익</span><span>순이익</span><span>ROE</span><span>부채비율</span><span>영업현금</span>
          </div>
          {data.years.slice(0, 4).map((year) => (
            <div className="fundamental-year-row" key={year.year}>
              <strong>{year.year}</strong>
              <span>{money(year.revenue)}</span>
              <span>{money(year.operating_profit)}</span>
              <span>{money(year.net_income)}</span>
              <span>{percent(year.roe_pct)}</span>
              <span>{percent(year.debt_ratio_pct)}</span>
              <span>{money(year.operating_cash_flow)}</span>
            </div>
          ))}
        </div>
      </details>

      <details className="fundamental-details valuation-details">
        <summary>
          <span><strong>PER·PBR 계산 근거</strong><small>최신 연간 EPS/BPS + 확정 가격/현재 참고가격 Preview</small></span>
          <b>펼치기</b>
        </summary>
        <div className="fundamental-valuation-grid">
          <article><span className="term-inline">EPS <TermHelp term="eps" /></span><strong>{money(data.valuation.eps)}</strong></article>
          <article><span className="term-inline">BPS <TermHelp term="bps" /></span><strong>{money(data.valuation.bps)}</strong></article>
          <article><span>KRX EOD PER</span><strong>{ratio(data.valuation.eod.per)}</strong></article>
          <article><span>KRX EOD PBR</span><strong>{ratio(data.valuation.eod.pbr)}</strong></article>
          {data.valuation.preview && <article><span>현재가격 Preview PER</span><strong>{ratio(data.valuation.preview.per)}</strong></article>}
          {data.valuation.preview && <article><span>현재가격 Preview PBR</span><strong>{ratio(data.valuation.preview.pbr)}</strong></article>}
        </div>
        <p className="fundamental-valuation-policy">{data.valuation.policy}</p>
      </details>

      <div className="fundamental-basis">
        <strong>데이터 기준</strong>
        <span>{data.data_basis.financial}</span>
        <span>{data.data_basis.price}</span>
        <small>{data.data_basis.note}</small>
      </div>
    </section>
  );
}

