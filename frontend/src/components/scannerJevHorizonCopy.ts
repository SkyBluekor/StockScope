/** S31-Q. Only the original, server-verified capture can declare its period.
 * These strings are provenance labels, not a prompt to silently backfill a
 * LEGACY capture or override an unapproved horizon policy.
 */
export function scannerJevCapturedHorizonLabel(
  horizon: string | null | undefined,
): string {
  switch (horizon) {
    case "SHORT": return "단기 (SHORT)";
    case "MEDIUM": return "중기 (MEDIUM)";
    case "LONG": return "장기 (LONG · 로컬 V4 검사 대상 아님)";
    case "LEGACY_UNSPECIFIED": return "기간 미지정 (LEGACY_UNSPECIFIED)";
    default: return "원본 투자 기간 확인 불가";
  }
}

export function scannerJevDiagnosticStageLabel(
  stage: string | null | undefined,
): string {
  switch (stage) {
    case "HORIZON_SCOPE": return "캡처 투자 기간 검사";
    case "ACTION_SCOPE": return "원본 진입 후보 유형 검사";
    case "SEMANTIC_INPUT": return "전략·조건 의미 근거 검사";
    case "CAPTURE_INTEGRITY": return "원본 캡처 해시 검증";
    case "CAPTURE_LOOKUP": return "캡처 조회";
    case "COMPLETE": return "로컬 의미검사 완료";
    default: return "요청 근거 확인";
  }
}
