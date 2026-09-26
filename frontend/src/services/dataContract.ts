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
    return "저장된 분석 결과는 현재 기준으로 갱신이 필요합니다.";
  }
  if (resource.status === "UNVERIFIED") {
    return "저장 결과 있음 · 현재 입력 기준과 완전 일치 여부는 확인하지 않았습니다.";
  }
  return "저장된 분석 결과의 현재 기준이 확인됐습니다.";
}
