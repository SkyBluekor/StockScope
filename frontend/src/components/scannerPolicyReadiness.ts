/** Read-only explanation of frozen Scanner selection-policy evidence.
 * Never infer an S7 verdict or activate a strategy selection policy. */
export type ScannerPolicySource = {
  policy_source?: string | null;
  fallback_used?: boolean;
  policy_id?: string | null;
  policy_hash?: string | null;
} | null | undefined;

export type CandidateIdentitySource = {
  action?: string | null;
  strategy_version_id?: string | null;
  strategy_definition_hash?: string | null;
};

export type ScannerPolicyReadiness =
  | "LEGACY_IDENTITY_LIMITED"
  | "PINNED_IDENTITY_PRESENT"
  | "PINNED_IDENTITY_INCOMPLETE"
  | "POLICY_UNKNOWN";

export function scannerPolicyReadiness(
  policy: ScannerPolicySource,
  candidates: readonly CandidateIdentitySource[],
  scannerCacheHit: boolean,
): {
  status: ScannerPolicyReadiness;
  label: string;
  message: string;
  candidateEntryCount: number;
  missingOriginalIdentityCount: number;
} {
  const entries = candidates.filter(c => c.action === "ENTRY_CANDIDATE");
  const missing = entries.filter(c =>
    typeof c.strategy_version_id !== "string" ||
    !c.strategy_version_id.trim() ||
    typeof c.strategy_definition_hash !== "string" ||
    !c.strategy_definition_hash.trim()
  ).length;
  const info = {
    candidateEntryCount: entries.length,
    missingOriginalIdentityCount: missing,
  };
  if (policy?.policy_source === "LEGACY_CURRENT_10_FALLBACK") {
    return {
      status: "LEGACY_IDENTITY_LIMITED",
      label: "기본 전략 · 원본 식별 근거 제한",
      message: "이번 Scanner는 Legacy Fallback 전략 정책으로 실행됐어요. 이 정책은 전략 버전·정의 해시가 비어 있어 진입 후보가 S7에서 LEGACY_LIMITED로 분류될 수 있습니다. 기존 기록은 수정하지 않으며, 승인된 전략 정책 없이 자동으로 LOCAL_VALIDATED로 바꾸지 않습니다.",
      ...info,
    };
  }
  if (policy?.policy_source === "ACTIVE_SELECTION_POLICY" ||
      policy?.policy_source === "ROLLBACK_FALLBACK") {
    if (missing > 0) {
      return {
        status: "PINNED_IDENTITY_INCOMPLETE",
        label: "전략 식별 정보 확인 필요",
        message: "승인 또는 롤백 정책으로 실행됐지만 일부 진입 후보의 원본 전략 버전·정의 해시가 없습니다. S7 검증이 필요하며, 누락된 원본 정보를 현재 시점 값으로 채워 넣지 않습니다.",
        ...info,
      };
    }
    return {
      status: "PINNED_IDENTITY_PRESENT",
      label: "전략 식별 정보 포함 · S7 별도 검증",
      message: scannerCacheHit
        ? "승인된 정책의 원본 식별 정보가 포함돼 있지만 캐시 결과예요. 재사용 데이터만으로 실제 엔진 통과 증거와 S7 LOCAL_VALIDATED를 보장할 수 없습니다."
        : "승인 또는 롤백 정책의 원본 전략 식별 정보가 포함돼 있습니다. 실제 엔진 통과 근거·순위·Risk·정책 일치 여부는 S7 검증을 거쳐야 하며 LOCAL_VALIDATED 또는 성과 검증을 보장하지 않습니다.",
      ...info,
    };
  }
  return {
    status: "POLICY_UNKNOWN",
    label: "전략 식별 근거 미확인",
    message: "이번 실행의 Selection Policy 연결 정보를 확인할 수 없습니다. 결과 표시만으로 S7 분류나 실제 성과를 확정할 수 없습니다.",
    ...info,
  };
}
