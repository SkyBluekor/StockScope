import useMarketStockImpact from "../hooks/useMarketStockImpact";

type Props = {
  market: "KOSPI" | "KOSDAQ";
  ticker: string;
  endDate: string | null | undefined;
};

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function signedValue(
  value: string | null | undefined,
  suffix: "%" | "%p",
) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${parsed.toFixed(2)}${suffix}`;
}

export default function MarketStockImpactInline({
  market,
  ticker,
  endDate,
}: Props) {
  const { impact, loading, error } = useMarketStockImpact({
    market,
    ticker,
    endDate,
    enabled: Boolean(ticker && endDate),
  });

  const projection = impact?.impact ?? null;
  const unavailable =
    projection?.status === "UNAVAILABLE" ||
    impact?.status === "UNAVAILABLE";
  const insufficient =
    projection?.reason === "INSUFFICIENT_COMMON_SESSIONS";
  const sectorBlocked =
    impact?.sector_route.historical_sector_status ===
    "BLOCKED_EXTERNAL_SOURCE";

  return (
    <section
      className="market-stock-impact-inline"
      aria-label="시장 대비 최근 움직임"
    >
      <div className="market-stock-impact-head">
        <div>
          <span>시장 비교</span>
          <strong>시장 대비 최근 움직임</strong>
        </div>
        {projection?.window.start_date && projection?.window.end_date && (
          <small>
            {formatDate(projection.window.start_date)}
            {" → "}
            {formatDate(projection.window.end_date)}
          </small>
        )}
      </div>

      {loading ? (
        <p className="market-stock-impact-state">
          시장 대비 비교 데이터를 확인하는 중입니다.
        </p>
      ) : error ? (
        <p className="market-stock-impact-state">
          시장 대비 비교 데이터가 아직 준비되지 않았습니다.
        </p>
      ) : unavailable ? (
        <p className="market-stock-impact-state">
          {insufficient
            ? "동일한 두 확정 거래일 데이터가 부족해 시장 대비 비교를 만들 수 없습니다."
            : "시장 대비 비교 데이터가 아직 준비되지 않았습니다."}
        </p>
      ) : projection ? (
        <>
          <div className="market-stock-impact-values">
            <div>
              <span>시장 변동</span>
              <strong>
                {signedValue(projection.market.return_pct, "%")}
              </strong>
            </div>
            <div>
              <span>종목 변동</span>
              <strong>
                {signedValue(projection.stock.return_pct, "%")}
              </strong>
            </div>
            <div>
              <span>시장 대비 차이</span>
              <strong>
                {signedValue(
                  projection.relative.stock_vs_market_pctp,
                  "%p",
                )}
              </strong>
            </div>
          </div>
          <p className="market-stock-impact-note">
            같은 두 확정 거래일의 단순 수익률 차이입니다. 원인 분석이나
            매수·매도 판단을 의미하지 않습니다.
          </p>
        </>
      ) : null}

      {sectorBlocked && (
        <p className="market-stock-impact-sector-note">
          과거 업종 소속의 시점 근거가 확보되지 않아 업종 비교는 현재
          제외됩니다.
        </p>
      )}
    </section>
  );
}
