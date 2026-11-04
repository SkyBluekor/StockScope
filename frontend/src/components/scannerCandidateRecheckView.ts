import type { ScannerCandidate, ScannerCandidateRecheck, ScannerResponse } from "../services/api";

/** Only present the backend's actual filter reason; never infer a trading verdict. */
export function scannerRecheckFilterDescription(raw: string | null | undefined): string {
  if (!raw) return "필터 제외 세부 사유를 확인하지 못했습니다.";
  const labels: Record<string, string> = {
    LOW_LIQUIDITY: "최근 거래대금이 Scanner의 기본 유동성 기준보다 낮습니다.",
    SPAC: "스팩(SPAC) 종목으로 기본 Scanner 검색 대상에서 제외됐습니다.",
    "우선주": "우선주로 기본 Scanner 검색 대상에서 제외됐습니다.",
    "ETF/ETN": "ETF 또는 ETN으로 기본 Scanner 검색 대상에서 제외됐습니다.",
    "거래정지 또는 거래 없음": "해당 거래일의 거래량 또는 거래대금이 없거나 0입니다. 거래정지 여부 자체를 확정한 것은 아닙니다.",
    "가격 데이터 없음": "해당 거래일의 종가가 없거나 유효하지 않습니다.",
    "종목명 없음": "해당 거래일의 종목명이 없습니다.",
    "일반 6자리 주식코드 아님": "Scanner가 지원하는 일반적인 6자리 주식코드 형태가 아닙니다.",
  };
  return labels[raw] ?? "Scanner 필터 사유: " + raw;
}

export function scannerRecheckHeadline(result: ScannerCandidateRecheck): string {
  switch (result.status) {
    case "MATCHED_RETURNED_CANDIDATE": return "새 Scanner 후보 목록에서 확인";
    case "TARGETED_EVALUATED_OUTSIDE_RANKING": return "전체 순위 밖 · 종목별 전략·Risk 별도 계산";
    case "TARGET_OUTSIDE_SCANNER_FILTER": return "기본 필터 제외 · 전략·Risk 심층 계산 미실행";
    case "TARGET_STOCK_ROW_MISSING": return "새 날짜의 종목 행 없음 · 판단 보류";
    case "NOT_IN_RETURNED_POOL": return "새 Scanner 반환 목록 밖 · 종목 판단 미확정";
    default: return "새 기준일 또는 개별 입력 확인 필요";
  }
}

/** A removed historical candidate must not select an unrelated top-ranked stock. */
export function scannerSelectionAfterRecheck(
  result: Pick<ScannerResponse, "candidate_recheck" | "candidates" | "more_candidates">,
  preferredKey: string | null,
): string | null {
  const all: ScannerCandidate[] = [...(result.candidates ?? []), ...(result.more_candidates ?? [])];
  const key = (item: ScannerCandidate) => item.market + "-" + item.code;
  const recheck = result.candidate_recheck;
  if (recheck) {
    const target = all.find(item =>
      item.market === recheck.market && item.code === recheck.code
      && item.data_date === recheck.new_data_date,
    );
    return target && recheck.status === "MATCHED_RETURNED_CANDIDATE"
      ? key(target) : null;
  }
  return preferredKey && all.some(item => key(item) === preferredKey)
    ? preferredKey
    : (result.candidates?.[0] ? key(result.candidates[0]) : null);
}

export function scannerRecheckCaptureDescription(result: ScannerCandidateRecheck): string {
  const state = result.baseline_scanner_capture_status ?? "미확인";
  if (state === "COMPLETE" || state === "DUPLICATE") {
    return "전체 Scanner 후보 캡처 " + state + " · " +
      (result.baseline_scanner_capture_id || "ID 미확인");
  }
  return "전체 Scanner 후보 캡처 " + state + " · 저장 완료 확인 불가";
}
