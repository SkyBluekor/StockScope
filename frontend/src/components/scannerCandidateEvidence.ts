import type { ScannerCandidate } from "../services/api";

// S29: presentation-only, no new scores or production rank changes.
export type CandidateEvidenceView = {
  orderLabel: string;
  tieExplanation: string | null;
  sameRunRankChangeLabel: string | null;
  historicalLabel: string;
  target1R: number | null;
  structuralR: number | null;
  riskStatus: "CHECKED" | "MISSING_REFERENCE" | "INVALID_REFERENCE" | "ENGINE_DISAGREEMENT";
  riskLabel: string;
  structuralLabel: string;
  isForecastOrProvenProfit: false;
};

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function rText(value: number | null): string {
  return value == null ? "계산할 근거 없음" : value.toFixed(2) + "R";
}

function historyText(candidate: ScannerCandidate): string {
  const status = candidate.priority?.historical_status
    ?? candidate.historical_evidence?.status
    ?? candidate.historical_fit?.status;
  if (status === "DATA_UNAVAILABLE") return "3년 과거 검증 데이터 부족";
  if (status === "NOT_RUN") return "3년 과거 검증 전";
  if (status === "INSUFFICIENT") return "과거 유사 사례 표본 부족";
  if (status === "NO_CASES") return "과거 유사 사례 없음";
  if (status === "WEAK") return "과거 검증 근거 약함";
  if (status === "FAIR") return "과거 검증 근거 보통 (미래 수익 보장 아님)";
  if (status === "GOOD") return "과거 검증 근거 양호 (미래 수익 보장 아님)";
  return "과거 검증 상태 확인 필요";
}

export function scannerCandidateEvidence(candidate: ScannerCandidate, displayIndex: number): CandidateEvidenceView {
  const p = candidate.priority;
  const rank = displayIndex + 1;
  const tied = Number.isInteger(p?.tie_size) && (p?.tie_size ?? 0) > 1
    && p?.strict_rank === false;
  const orderLabel = tied
    ? `동률 ${p!.tie_size}개 · 표시 ${rank}번`
    : `표시 ${rank}번 · 수익률 순위 아님`;
  const tieExplanation = tied
    ? p?.tie_breaker === "STRUCTURAL_TARGET_NEAREST_PROMOTE"
      ? "현재 조건·위험·진입 거리·전략 적합도가 같아 구조 목표가 가까운 한 종목을 먼저 표시하고 나머지는 종목코드로 나열했어요."
      : "동률 후보를 구분할 충분한 근거가 없어 표시 순서만 정했어요."
    : null;
  const sameRunRankChangeLabel = p && Number.isInteger(p.previous_rank)
    && Number.isInteger(p.rank_change)
    ? "이전 순위는 어제가 아니라 이번 분석 내 정렬 전 순서예요."
    : null;

  const risk = candidate.entry_risk_guide?.risk;
  const entry = finite(risk?.entry_reference_price);
  const stop = finite(risk?.invalidation_price);
  const target = finite(risk?.target1_price);
  const structural = finite(risk?.structural_target1_price);
  let riskStatus: CandidateEvidenceView["riskStatus"] = "MISSING_REFERENCE";
  let target1R: number | null = null;
  let structuralR: number | null = null;
  if (entry != null && entry > 0 && stop != null && target != null) {
    if (stop <= 0 || stop >= entry || target <= entry) {
      riskStatus = "INVALID_REFERENCE";
    } else {
      target1R = (target - entry) / (entry - stop);
      structuralR = structural != null && structural > entry
        ? (structural - entry) / (entry - stop) : null;
      riskStatus = "CHECKED";
      const engineR = finite(risk?.rr1);
      if (engineR != null && Math.abs(engineR - target1R) > 0.025) {
        riskStatus = "ENGINE_DISAGREEMENT";
      }
    }
  }
  if (target1R != null) target1R = Math.round(target1R * 100) / 100;
  if (structuralR != null) structuralR = Math.round(structuralR * 100) / 100;
  const riskLabel = riskStatus === "ENGINE_DISAGREEMENT"
    ? "참고 손익비 재검토 필요 (엔진 값과 다름)"
    : riskStatus === "INVALID_REFERENCE"
      ? "진입·무효화·목표가 순서 확인 필요"
      : riskStatus === "MISSING_REFERENCE"
        ? "참고 손익비 계산 근거 부족"
        : "1차 목표 참고 손익비 " + rText(target1R);
  const structuralLabel = structuralR == null
    ? "구조 저항 기준 손익비 확인 불가"
    : "구조 저항 기준 " + rText(structuralR);
  return {
    orderLabel, tieExplanation, sameRunRankChangeLabel,
    historicalLabel: historyText(candidate),
    target1R, structuralR, riskStatus, riskLabel, structuralLabel,
    isForecastOrProvenProfit: false,
  };
}

export function scannerTieSummary(candidates: ScannerCandidate[]): string {
  const first = candidates[0]?.priority;
  if (!first || !Number.isInteger(first.tie_size) || (first.tie_size ?? 0) <= 1
      || first.strict_rank !== false) {
    return "표시 번호는 분석일 검토 순서이며 예상 수익률 순위가 아니에요.";
  }
  const count = candidates.filter(c => c.priority?.tie_group === first.tie_group
    && c.priority?.strict_rank === false).length;
  return `맨 앞 ${first.tie_size}개 후보는 조건상 동률이에요${count < (first.tie_size ?? 0) ? " (일부만 표시됨)" : ""}. 번호는 투자 성과의 우열을 뜻하지 않아요.`;
}
