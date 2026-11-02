import type { ScannerDjiLocalReference } from "../services/api";

export type ScannerDjiView = {
  headline: string;
  detail: string;
  available: boolean;
};

/** No predictive inference, historical decision attribution or implied US close. */
export function scannerDjiLocalPresentation(
  reference: ScannerDjiLocalReference | null,
  scannerDataDate: string,
  nowMs: number = Date.now(),
): ScannerDjiView {
  const unavailable = (message: string): ScannerDjiView => ({
    headline: message, detail: "", available: false,
  });
  if (!reference) return unavailable("미국 다우존스 참고 정보를 확인할 수 없어요.");
  if (reference.status === "UNAVAILABLE") {
    if (reference.reason === "PERSONAL_LOCAL_OPT_IN_REQUIRED") {
      return unavailable("미국 다우존스 · 개인 로컬 이용 확인 전 (비활성)");
    }
    if (reference.reason === "LOCAL_ACCESS_ONLY") {
      return unavailable("미국 다우존스 · 로컬 PC에서만 확인 가능");
    }
    return unavailable("미국 다우존스 참고 정보 이용 불가 · 기존 분석은 유지돼요.");
  }
  if (
    reference.status !== "PARTIAL"
    || reference.source !== "KIS_OVERSEAS_INDEX_LOCAL"
    || reference.index_code !== ".DJI"
    || reference.index_name !== "다우존스 산업평균지수"
    || !["OFFICIAL_KIS_REQUEST_CODE", "PROVIDER_RESPONSE"].includes(reference.index_name_source)
    || reference.usage_scope !== "PERSONAL_LOCAL_REFERENCE_ONLY"
    || reference.source_time_quality !== "DATE_ONLY"
    || reference.session_close_verified !== false
    || reference.scanner_input_approved !== false
    || reference.risk_gate_input_approved !== false
    || reference.production_decision_approved !== false
    || reference.ai_transfer_approved !== false
    || reference.retention_rights_approved !== false
    || !reference.index_value || !reference.previous_index_value
    || !reference.daily_change_pct
    || !reference.observation_date || !reference.previous_observation_date
    || !reference.fetched_at_utc
  ) return unavailable("미국 다우존스 · 신뢰 가능한 참고 값 없음");

  const current = Number(reference.index_value);
  const previous = Number(reference.previous_index_value);
  const reported = Number(reference.daily_change_pct);
  const fetched = Date.parse(reference.fetched_at_utc);
  const dateStamp = /^\d{4}-\d{2}-\d{2}$/;
  const observed = dateStamp.test(reference.observation_date)
    ? Date.parse(reference.observation_date + "T00:00:00Z") : NaN;
  const prevDate = dateStamp.test(reference.previous_observation_date)
    ? Date.parse(reference.previous_observation_date + "T00:00:00Z") : NaN;
  const kstDay = Number.isFinite(fetched)
    ? new Date(fetched + 9 * 60 * 60 * 1000).toISOString().slice(0, 10) : "";
  if (!Number.isFinite(current) || current <= 0
    || !Number.isFinite(previous) || previous <= 0
    || !Number.isFinite(reported) || Math.abs(reported) > 100
    || !Number.isFinite(fetched) || fetched > nowMs + 300_000
    || !Number.isFinite(observed) || !Number.isFinite(prevDate)
    || prevDate >= observed || reference.observation_date > kstDay
    || (Date.parse(kstDay + "T00:00:00Z") - observed) / 86_400_000 > 7
    || Math.abs((current / previous - 1) * 100 - reported) > 0.015
  ) return unavailable("미국 다우존스 · 날짜 또는 지수값 검증 실패");

  const change = (reported >= 0 ? "+" : "") + reported.toFixed(2) + "%";
  const afterAnalysis = dateStamp.test(scannerDataDate)
    && (reference.observation_date > scannerDataDate
      || fetched > Date.parse(scannerDataDate + "T23:59:59+09:00"));
  return {
    headline: "미국 다우존스 " + current.toLocaleString("ko-KR", {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }) + " · 일간 값 변화 " + change + " · 관측 " + reference.observation_date,
    detail: "KIS 일별 조회값 · 수집 " + reference.fetched_at_utc.slice(0, 10)
      + " · 원천 발표·확정 종가 시각 미확인 · "
      + (afterAnalysis
        ? "분석일 이후 조회한 자료로 당시 판단 근거가 아니에요."
        : "현재 조회 참고이며 당시 Scanner 결정 입력은 아니에요.")
      + " 국내 지수 변화의 원인이나 매매 신호로 해석하지 않아요.",
    available: true,
  };
}
