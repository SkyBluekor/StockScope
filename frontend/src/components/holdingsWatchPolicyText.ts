/**
 * S31-O: explains only evidence actually returned by Holdings Watch.
 * A policy flag or stored Watch setting NEVER proves a live heartbeat.
 * This is presentation-only; production_watch_policy() remains disabled.
 */
export type WatchPolicyEvidence = {
  policy_enabled: boolean;
  migration_required: boolean;
  blocked_reason: string | null;
  available?: boolean;
};

export type WatchPolicyCopy = {
  title: string;
  explanation: string;
  approved: boolean;
  runtimeConfirmed: false;
};

export function holdingsWatchPolicyText(
  evidence: WatchPolicyEvidence | null | undefined,
): WatchPolicyCopy {
  if (!evidence || evidence.available === false) return {
    title: "Watch 정책 상태 확인 불가",
    explanation: "정책과 실제 감시 상태를 확인할 근거가 없습니다. 감시가 켜져 있다고 가정하지 마세요.",
    approved: false, runtimeConfirmed: false,
  };
  if (evidence.migration_required) return {
    title: "Watch 저장 구조 준비 필요",
    explanation: "Watch 저장 구조가 준비되지 않았습니다. 보유 판단과 관리 계획은 별도로 확인하세요.",
    approved: false, runtimeConfirmed: false,
  };
  if (!evidence.policy_enabled) return {
    title: "Watch 운영 정책 비활성",
    explanation: evidence.blocked_reason === "OPERATING_THRESHOLDS_UNAPPROVED"
      ? "위험 확정 관측 횟수, 해제 후 재감시 기준, 시세 유효시간이 아직 승인되지 않아 운영 감시를 켤 수 없습니다."
      : "운영 정책이 활성화되지 않았습니다. 보유중이거나 Watch 설정 기록이 있어도 자동 감시가 작동한다는 뜻은 아닙니다.",
    approved: false, runtimeConfirmed: false,
  };
  return {
    title: "Watch 운영 정책 활성 · 실제 가동 별도 확인",
    explanation: "정책이 활성화되어 있어도 연결 상태, 실행 세션, heartbeat, 감시 공백을 확인하기 전에는 실시간 보호 중이라고 판단할 수 없습니다.",
    approved: true, runtimeConfirmed: false,
  };
}
