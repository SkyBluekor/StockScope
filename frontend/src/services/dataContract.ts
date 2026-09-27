import type {
  DataContractAction,
  DataContractResourceStatus,
  StockDataContract,
} from "./api";

export type DataContractTone = "ok" | "muted" | "warn" | "idle";

export function dataContractStatusLabel(status: DataContractResourceStatus) {
  switch (status) {
    case "VALID": return "현재 기준 확인됨";
    case "UNVERIFIED": return "현재성 확인 제한";
    case "INVALID": return "갱신 필요";
    case "ABSENT": return "준비되지 않음";
  }
}

export function dataContractTone(status: DataContractResourceStatus): DataContractTone {
  switch (status) {
    case "VALID": return "ok";
    case "INVALID": return "warn";
    case "UNVERIFIED": return "muted";
    case "ABSENT": return "idle";
  }
}

export function contractAction(
  contract: StockDataContract | null,
  id: DataContractAction["id"],
) {
  return contract?.actions.find((action) => action.id === id && action.enabled) ?? null;
}

export function analysisContractMessage(contract: StockDataContract | null) {
  const resource = contract?.resources.analysis_result;
  if (!resource) return null;
  if (resource.status === "ABSENT") return "저장된 분석 결과가 없습니다.";
  if (resource.status === "INVALID") {
    if (resource.reason_code === "ANALYSIS_BASIS_STALE") {
      return "저장된 분석은 이전 확정 일봉 기준입니다.";
    }
    if (resource.reason_code === "CURRENT_INPUT_IDENTITY_MISMATCH") {
      return "저장된 분석과 현재 입력이 일치하지 않습니다. 분석을 새로 확인하세요.";
    }
    if (resource.reason_code === "CURRENT_INPUT_CHANGED_SINCE_PROOF") {
      return "입력 검증 이후 관련 시장 데이터가 변경되었습니다. 다시 검증하거나 분석을 갱신하세요.";
    }
    return "저장된 분석 결과는 현재 기준으로 갱신이 필요합니다.";
  }
  if (resource.status === "UNVERIFIED") {
    if (resource.reason_code === "CURRENT_INPUT_IDENTITY_NOT_PROVEN") {
      return "저장 결과는 있지만 현재 입력과 같은 조건인지 아직 증명되지 않았습니다.";
    }
    return "저장 결과 있음 · 현재 입력 기준과 완전 일치 여부는 확인하지 않았습니다.";
  }
  return "저장된 분석 결과의 현재 기준이 확인됐습니다.";
}
