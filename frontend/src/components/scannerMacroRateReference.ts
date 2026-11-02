import type { ScannerMacroRateReference } from "../services/api";

export type ScannerMacroRateView = {
  headline: string;
  detail: string;
  available: boolean;
};

/** Descriptive reference only: never infer a historical Scanner decision or causality. */
export function scannerMacroRatePresentation(
  reference: ScannerMacroRateReference | null,
  scannerDataDate: string,
): ScannerMacroRateView {
  const empty = {
    headline: "미국 10년물 국채금리 자료를 확인할 수 없어요.",
    detail: "기존 종목 전략 및 시장 위험 판단은 그대로 유지돼요.",
    available: false,
  };
  if (!reference || !["AVAILABLE", "PARTIAL"].includes(reference.status)
    || reference.source !== "FRED_DGS10_LOCAL"
    || reference.source_unit !== "PERCENT"
    || reference.production_decision_approved !== false
    || reference.scanner_input_approved !== false
    || reference.risk_gate_input_approved !== false
    || !reference.value_pct?.trim()
    || !reference.observation_date
    || !reference.available_at
    || !reference.decision_cutoff) return empty;

  const rate = Number(reference.value_pct);
  const available = Date.parse(reference.available_at);
  const cutoff = Date.parse(reference.decision_cutoff);
  if (!Number.isFinite(rate) || !Number.isFinite(available)
    || !Number.isFinite(cutoff) || available > cutoff) return empty;

  // An observation's available_at is NOT the observation's date.
  // A delayed first-seen timestamp can never make an old rate current.
  const observationDay = /^\d{4}-\d{2}-\d{2}$/.test(reference.observation_date)
    ? Date.parse(reference.observation_date + "T00:00:00Z")
    : NaN;
  if (!Number.isFinite(observationDay) || observationDay > cutoff) return empty;
  const analysisEnd = /^\d{4}-\d{2}-\d{2}$/.test(scannerDataDate)
    ? Date.parse(scannerDataDate + "T23:59:59+09:00")
    : NaN;
  // Display-only recency guard. Seven calendar days tolerate weekends/holidays;
  // it is NOT a market-risk or trading-policy threshold.
  const referenceAgeDays = Math.floor((cutoff - observationDay) / 86_400_000);
  const staleReference = referenceAgeDays > 7;
  const later = (!Number.isNaN(analysisEnd) && available > analysisEnd)
    || reference.observation_date > scannerDataDate;
  const timeNote = reference.time_quality === "EXACT"
    || reference.time_quality === "PROVIDER_TIME"
    ? "자료 이용 가능 시각 기록 있음"
    : "원천 발표 시각 검증이 충분하지 않음";
  const snapshotNote = later
    ? "이 분석일 이후에 이용 가능해진 자료로, 당시 판단 근거가 아니에요."
    : "당시 분석에 사용된 입력이 아니라 현재 조회 기준 참고자료예요.";
  const publication = reference.source_published_at
    ? "원천 발표 기록 있음"
    : "원천 발표 시각 확인 불가";
  const referenceSummary = "FRED DGS10 · 관측일 " + reference.observation_date
    + " · 자료 이용 가능 기록일 " + reference.available_at.slice(0, 10)
    + " · " + publication + ". ";
  if (staleReference) {
    return {
      headline: "미국 10년물 금리 · 오래된 저장자료 (최신 금리 확인 필요)",
      detail: referenceSummary
        + "마지막 저장 관측은 조회 기준 " + referenceAgeDays + "일 전의 "
        + rate.toFixed(2) + "%입니다. 현재 금리나 분석일의 최신 금리로 해석할 수 없어요. "
        + snapshotNote + " 국내 시장 하락의 원인으로 단정하지 않아요. "
        + "전략 점수와 신규 진입 차단은 변경하지 않았어요.",
      available: true,
    };
  }
  return {
    headline: "미국 10년물 국채금리 " + rate.toFixed(2) + "% · 관측 " + reference.observation_date,
    detail: referenceSummary + timeNote + ". " + snapshotNote
      + " 국내 지수 하락의 원인으로 단정하지 않아요. 전략 점수와 신규 진입 차단은 변경하지 않았어요.",
    available: true,
  };
}
