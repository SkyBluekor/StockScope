import useMacroEventReference from "../hooks/useMacroEventReference";
import type {
  MacroEventReferenceItem,
  MacroEventReferenceResponse,
} from "../services/macroEventReferenceApi";

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
    EARNINGS: "실적",
    LITIGATION: "소송",
    TREASURY: "자사주",
    DIVIDEND: "배당",
  };
  return labels[value] ?? "이벤트 근거";
}

function latestEvent(items: MacroEventReferenceItem[]) {
  return items.reduce<MacroEventReferenceItem | null>((latest, item) => {
    if (!latest) return item;
    const currentTime = Date.parse(item.assessment_as_of);
    const latestTime = Date.parse(latest.assessment_as_of);
    if (Number.isNaN(currentTime)) return latest;
    if (Number.isNaN(latestTime) || currentTime > latestTime) return item;
    return latest;
  }, null);
}

function eventSummary(reference: MacroEventReferenceResponse) {
  if (reference.event_source.reader_status === "UNAVAILABLE") {
    return "이벤트 근거 상태를 현재 확인하지 못했습니다.";
  }

  const event = reference.event_reference;
  if (event.status === "EVIDENCE_BLOCKED") {
    return "무결성을 확인하지 못한 이벤트 근거는 참고에서 제외했습니다.";
  }

  if (event.status === "REFERENCE_LIMITED") {
    return event.eligible_reference_count > 0
      ? `제한된 이벤트 참고 ${event.eligible_reference_count}건`
      : "조회 시점까지 확인된 이벤트 근거 없음";
  }

  if (
    event.status === "REFERENCE_AVAILABLE" &&
    event.eligible_reference_count > 0
  ) {
    const latest = latestEvent(event.items);
    return latest
      ? `이벤트 근거 ${event.eligible_reference_count}건 · 최근 확인: ${eventTypeLabel(latest.event_type)}`
      : `이벤트 근거 ${event.eligible_reference_count}건`;
  }

  return "조회 시점까지 확인된 이벤트 근거 없음";
}

export default function MacroEventReferenceInline({
  market,
  ticker,
  endDate,
}: Props) {
  const { reference, loading, error } = useMacroEventReference({
    market,
    ticker,
    endDate,
    enabled: Boolean(ticker && endDate),
  });

  const impact = reference?.impact ?? null;
  const impactUnavailable =
    impact?.status === "UNAVAILABLE" || reference?.status === "UNAVAILABLE";
  const insufficient =
    impact?.reason === "INSUFFICIENT_COMMON_SESSIONS";
  const sectorBlocked =
    reference?.sector.historical_sector_status === "BLOCKED_EXTERNAL_SOURCE";

  return (
    <section
      className="macro-event-reference-inline"
      aria-label="시장·이벤트 참고"
    >
      <div className="macro-event-reference-head">
        <div>
          <span>REFERENCE</span>
          <strong>시장 움직임과 확인된 근거</strong>
        </div>
        {impact?.window.start_date && impact?.window.end_date && (
          <small>
            {formatDate(impact.window.start_date)}
            {" → "}
            {formatDate(impact.window.end_date)}
          </small>
        )}
      </div>

      {loading ? (
        <p className="macro-event-reference-state">
          시장·이벤트 참고 데이터를 확인하는 중입니다.
        </p>
      ) : error ? (
        <p className="macro-event-reference-state">
          시장·이벤트 참고 데이터를 현재 확인하지 못했습니다.
        </p>
      ) : reference ? (
        <>
          {impactUnavailable ? (
            <p className="macro-event-reference-state">
              {insufficient
                ? "동일한 두 확정 거래일 데이터가 부족해 시장 대비 비교를 만들 수 없습니다."
                : "시장 대비 비교 데이터가 아직 준비되지 않았습니다."}
            </p>
          ) : impact ? (
            <div className="macro-event-reference-values">
              <div>
                <span>시장 변동</span>
                <strong>{signedValue(impact.market_return_pct, "%")}</strong>
              </div>
              <div>
                <span>종목 변동</span>
                <strong>{signedValue(impact.stock_return_pct, "%")}</strong>
              </div>
              <div>
                <span>시장 대비 차이</span>
                <strong>
                  {signedValue(impact.stock_vs_market_pctp, "%p")}
                </strong>
              </div>
            </div>
          ) : null}

          <p className="macro-event-reference-event">
            {eventSummary(reference)}
          </p>

          {sectorBlocked && (
            <p className="macro-event-reference-sector-note">
              과거 업종 소속의 시점 근거가 확보되지 않아 업종 비교는 현재
              제외됩니다.
            </p>
          )}

          <p className="macro-event-reference-note">
            시장 비교는 같은 두 확정 거래일의 단순 수익률 차이입니다.
            이벤트는 조회 시점까지 확인된 참고 근거이며, 방향 예측이나
            매수·매도 신호로 사용하지 않습니다.
          </p>
        </>
      ) : null}
    </section>
  );
}
