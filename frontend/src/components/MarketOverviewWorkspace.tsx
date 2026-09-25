import type { IndexPoint, MarketDashboard } from "../services/api";

type Props = {
  dashboard: MarketDashboard | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
  onNavigate: (page: "analysis" | "scanner" | "holdings") => void;
};

function number(value: number | null | undefined, suffix = "") {
  if (value == null) return "-";
  return `${new Intl.NumberFormat("ko-KR").format(value)}${suffix}`;
}

function compactMoney(value: number | null | undefined) {
  if (value == null) return "-";
  if (Math.abs(value) >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(1)}조`;
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억`;
  if (Math.abs(value) >= 10_000) return `${(value / 10_000).toFixed(1)}만`;
  return number(value);
}

function signedRate(value: number | null | undefined) {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function rateClass(value: number | null | undefined) {
  if ((value ?? 0) > 0) return "positive";
  if ((value ?? 0) < 0) return "negative";
  return "neutral";
}

function Sparkline({ points }: { points: IndexPoint[] }) {
  const values = points.map((point) => point.close).filter((value): value is number => value != null);
  if (values.length < 2) return <div className="spark-empty">데이터 준비 중</div>;

  const width = 190;
  const height = 56;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} aria-label="최근 지수 흐름">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IndexCard({ name, point, history }: { name: string; point: IndexPoint; history: IndexPoint[] }) {
  return (
    <article className="summary-card index-card">
      <div>
        <span className="summary-label">{name}</span>
        <strong className="summary-value">{number(point.close)}</strong>
        <span className={`summary-change ${rateClass(point.change_rate)}`}>{signedRate(point.change_rate)}</span>
      </div>
      <Sparkline points={history} />
    </article>
  );
}

export default function MarketOverviewWorkspace({
  dashboard,
  loading,
  error,
  onReload,
  onNavigate,
}: Props) {
  const breadth = dashboard?.market.breadth;
  const upPercent = breadth?.total ? (breadth.up / breadth.total) * 100 : 0;
  const downPercent = breadth?.total ? (breadth.down / breadth.total) * 100 : 0;

  return (
    <section className="market-overview-workspace" aria-label="시장 현황">
      <section className="page-head market-overview-head">
        <div>
          <span className="eyebrow">MARKET OVERVIEW</span>
          <h1>시장 현황</h1>
          <p>최근 확정 KRX 거래일 기준으로 시장의 흐름과 주요 지표를 한눈에 확인합니다.</p>
        </div>
        <div className="date-box">
          <span>시장 요약 기준</span>
          <strong>{formatDate(dashboard?.data_date)}</strong>
          {dashboard?.fallback_used && <small>최근 확정 거래일 사용 중</small>}
        </div>
      </section>

      {dashboard?.data_freshness.status === "FALLBACK" && (
        <div className="freshness-notice">
          <div>
            <strong>최근 확정 거래일 사용 중</strong>
            <span>{dashboard.data_freshness.message}</span>
          </div>
          <small>{dashboard.data_freshness.retry_note}</small>
        </div>
      )}

      <div className="trade-lock">
        <strong>실제 매매 기능 없음</strong>
        <span>조회 · 분석 · 종목 과거 성과 · 시뮬레이션 전용이며 증권사 주문을 전송하지 않습니다.</span>
      </div>

      {loading && <div className="loading-card">KRX 시장 데이터를 불러오는 중입니다...</div>}
      {error && (
        <div className="error-card">
          <strong>시장 데이터 조회 실패</strong>
          <span>{error}</span>
          <button type="button" onClick={onReload}>다시 조회</button>
        </div>
      )}

      {dashboard && (
        <>
          <section className="summary-grid">
            <IndexCard name="KOSPI" point={dashboard.indices.kospi} history={dashboard.history.kospi} />
            <IndexCard name="KOSDAQ" point={dashboard.indices.kosdaq} history={dashboard.history.kosdaq} />
            <article className="summary-card">
              <span className="summary-label">시장 상태</span>
              <strong className="summary-value text-value">{dashboard.market.regime}</strong>
              <span className="summary-sub">상승 종목 비율 {(dashboard.market.breadth.up_ratio * 100).toFixed(1)}%</span>
            </article>
            <article className="summary-card">
              <span className="summary-label">변동성 프록시</span>
              <strong className="summary-value text-value">{dashboard.market.volatility_proxy}</strong>
              <span className="summary-sub">평균 절대 등락 {dashboard.market.breadth.avg_abs_change_rate.toFixed(2)}%</span>
            </article>
          </section>

          <section className="dashboard-grid">
            <article className="panel market-panel">
              <div className="panel-head">
                <div>
                  <span className="panel-kicker">MARKET BREADTH</span>
                  <h2>시장 폭</h2>
                </div>
                <span className="source-chip">KRX 공식 데이터</span>
              </div>
              <div className="breadth-stats">
                <div><strong className="positive">{number(breadth?.up)}</strong><span>상승</span></div>
                <div><strong>{number(breadth?.flat)}</strong><span>보합</span></div>
                <div><strong className="negative">{number(breadth?.down)}</strong><span>하락</span></div>
              </div>
              <div className="breadth-bar" aria-label="상승 하락 종목 비중">
                <div className="breadth-up" style={{ width: `${upPercent}%` }} />
                <div className="breadth-flat" style={{ width: `${Math.max(0, 100 - upPercent - downPercent)}%` }} />
                <div className="breadth-down" style={{ width: `${downPercent}%` }} />
              </div>
              <p className="muted">총 {number(breadth?.total)}개 종목의 당일 등락률을 집계한 값입니다.</p>
            </article>

            <article className="panel group-panel">
              <div className="panel-head">
                <div>
                  <span className="panel-kicker">RELATIVE STRENGTH</span>
                  <h2>강한 업종 / 지수</h2>
                </div>
              </div>
              <div className="group-list">
                {dashboard.strong_groups.map((group, index) => (
                  <div className="group-row" key={`${group.name}-${index}`}>
                    <span className="rank">{index + 1}</span>
                    <div><strong>{group.name ?? "-"}</strong><small>{group.kind} · {group.class ?? "KRX"}</small></div>
                    <b className="positive">{signedRate(group.change_rate)}</b>
                  </div>
                ))}
                {dashboard.strong_groups.length === 0 && <p className="muted">양(+)의 업종/지수 그룹이 없습니다.</p>}
              </div>
            </article>

            <article className="panel turnover-panel">
              <div className="panel-head">
                <div>
                  <span className="panel-kicker">TURNOVER</span>
                  <h2>거래대금 상위 종목</h2>
                </div>
                <span className="source-chip">KOSPI + KOSDAQ</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>순위</th><th>종목</th><th>시장</th><th>현재 기준가</th><th>등락률</th><th>거래대금</th></tr></thead>
                  <tbody>
                    {dashboard.top_turnover.map((row, index) => (
                      <tr key={`${row.code}-${index}`}>
                        <td>{index + 1}</td>
                        <td><strong>{row.name ?? row.code}</strong><small>{row.code}</small></td>
                        <td>{row.market ?? "-"}</td>
                        <td>{number(row.close, "원")}</td>
                        <td className={rateClass(row.change_rate)}>{signedRate(row.change_rate)}</td>
                        <td>{compactMoney(row.trade_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel summary-panel">
              <div className="panel-head">
                <div>
                  <span className="panel-kicker">RULE-BASED SUMMARY</span>
                  <h2>현재 상황 요약</h2>
                </div>
                <span className="source-chip purple">규칙 기반</span>
              </div>
              <div className="summary-copy">
                <strong>{dashboard.market.regime}</strong>
                <p>{dashboard.summary}</p>
              </div>
            </article>
          </section>

          <section className="market-overview-next" aria-label="다음 작업">
            <div>
              <span>다음으로 무엇을 볼까요?</span>
              <strong>시장 전체 흐름을 확인했으면 필요한 작업으로 바로 이동하세요.</strong>
            </div>
            <nav>
              <button type="button" onClick={() => onNavigate("scanner")}>종목 후보 찾기</button>
              <button type="button" onClick={() => onNavigate("analysis")}>종목 분석</button>
              <button type="button" onClick={() => onNavigate("holdings")}>내 종목 관리</button>
            </nav>
          </section>
        </>
      )}
    </section>
  );
}
