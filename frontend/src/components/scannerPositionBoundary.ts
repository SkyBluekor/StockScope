import type { ScannerCandidate, ScannerResponse } from "../services/api";
import type { HoldingStock } from "../services/holdingsApi";

/**
 * Scanner S31-M: explain data ownership and time-boundary.
 *
 * Scanner candidate Risk is an entry research reference. A locally registered
 * position requires separate Holdings applied-plan/decision/watch evidence.
 * listHoldingStocks() is only a local inventory snapshot: it cannot prove
 * that an external broker still holds the stock or that Watch is active.
 *
 * Pure, read-only display logic; no new market/provider or Holdings calls.
 */
export type ScannerPositionBoundaryState =
  | "RECORDS_LOADING" | "RECORDS_UNAVAILABLE"
  | "LOCAL_POSITION_RECORDED" | "LOCAL_RECORD_CONFLICT"
  | "LOCAL_WATCH_ONLY" | "LOCAL_RECORD_NO_OPEN_POSITION"
  | "NOT_IN_LOCAL_LIST";

export type ScannerPositionBoundary = {
  state: ScannerPositionBoundaryState;
  headline: string;
  explanation: string;
  nextAction: string;
  openPositionCount: number | null;
  positionAccounts: string[];
  watchRegistered: boolean | null;
  brokerHoldingsVerified: false;
  activeStopOrWatchVerified: false;
  scannerReferenceIsAppliedHoldingStop: false;
  marketContext: {
    state: "AS_OF_ONLY" | "DATE_MISMATCH" | "UNAVAILABLE";
    analysisDate: string;
    regime: string | null;
    label: string;
    caution: string;
  };
};

const regimes: Record<string, string> = {
  TREND_UP: "상승장", RANGE: "횡보장",
  TREND_DOWN: "하락장", HIGH_VOLATILITY: "변동성 큰 시장",
  PANIC: "급변동 시장", UNKNOWN: "분류 보류",
};

function marketContext(
  candidate: ScannerCandidate,
  result: Pick<ScannerResponse, "market_summary">,
): ScannerPositionBoundary["marketContext"] {
  const rows = (result.market_summary ?? [])
    .filter((row) => row.market === candidate.market);
  if (rows.length !== 1) return {
    state: "UNAVAILABLE", analysisDate: candidate.data_date,
    regime: null, label: "해당 시장 분류 확인 불가",
    caution: "시장 상태를 확인할 수 없어요. 분석일 READY를 현재 진입 판단에 사용하지 마세요.",
  };
  const row = rows[0];
  if (row.data_date !== candidate.data_date) return {
    state: "DATE_MISMATCH", analysisDate: candidate.data_date,
    regime: null, label: "시장과 종목의 기준일 불일치",
    caution: "종목과 시장 자료의 날짜가 달라 당시 위험 환경을 대조할 수 없어요.",
  };
  const regime = row.regime;
  const label = regimes[regime] ?? "분류 확인 필요";
  const caution = ["TREND_DOWN", "HIGH_VOLATILITY", "PANIC"].includes(regime)
    ? "분석일에 위험 시장으로 분류됐어요. 신규 진입 여부와 보유종목 대응은 별도로 확인하세요."
    : regime === "TREND_UP" || regime === "RANGE"
      ? "당시 시장 분류일 뿐, 이후 급락이나 현재 시장의 안전을 보증하지 않아요."
      : "시장 분류가 불확실해 안전하다고 판단할 수 없어요.";
  return {
    state: "AS_OF_ONLY", analysisDate: row.data_date,
    regime, label: "분석일 KOSPI/KOSDAQ · " + label,
    caution,
  };
}

export function scannerPositionBoundary(
  candidate: ScannerCandidate,
  result: Pick<ScannerResponse, "market_summary">,
  managedStock: HoldingStock | null,
  holdingsLoading: boolean,
  holdingsReady: boolean,
): ScannerPositionBoundary {
  const market = marketContext(candidate, result);
  const defaults = {
    openPositionCount: null,
    positionAccounts: [] as string[],
    watchRegistered: null,
    brokerHoldingsVerified: false as const,
    activeStopOrWatchVerified: false as const,
    scannerReferenceIsAppliedHoldingStop: false as const,
    marketContext: market,
  };
  const build = (
    state: ScannerPositionBoundaryState, headline: string,
    explanation: string, nextAction: string,
    fields: Partial<ScannerPositionBoundary> = {},
  ): ScannerPositionBoundary => ({
    ...defaults, state, headline, explanation, nextAction, ...fields,
  });

  if (holdingsLoading) return build(
    "RECORDS_LOADING", "내 종목 기록 확인 중",
    "등록된 보유·관심 기록을 확인 중이에요. Scanner 후보라는 사실만으로 실제 보유를 판단하지 않아요.",
    "내 종목 기록이 확인된 뒤 보유 관리에서 적용 계획을 확인하세요.",
  );
  if (!holdingsReady) return build(
    "RECORDS_UNAVAILABLE", "보유 기록 확인 불가",
    "내 종목 데이터를 읽지 못했어요. 보유 여부가 없다고 판단하지 마세요.",
    "내 종목 등록 상태를 다시 조회하고 보유 관리 화면에서 확인하세요.",
  );
  if (!managedStock) return build(
    "NOT_IN_LOCAL_LIST", "로컬 내 종목 목록에 등록되지 않음",
    "StockScope에 저장된 목록에는 없지만 외부 증권계좌에 보유하지 않는다는 증거는 아니에요.",
    "실제 보유 여부는 증권계좌와 Holdings에서 별도로 확인하세요.",
    { openPositionCount: 0, watchRegistered: false },
  );
  if (managedStock.market !== candidate.market || managedStock.ticker !== candidate.code) {
    return build(
      "LOCAL_RECORD_CONFLICT", "보유 기록 종목 불일치",
      "내 종목 기록과 Scanner 종목코드·시장이 서로 다릅니다. 잘못된 종목의 판단을 표시할 수 없어요.",
      "종목과 계좌 기록이 일치하는지 Holdings에서 확인하세요.",
    );
  }
  const positions = Array.isArray(managedStock.positions) ? managedStock.positions : null;
  if (!positions) return build(
    "LOCAL_RECORD_CONFLICT", "보유 기록 자료 부족",
    "보유 등록 상태와 개별 포지션 기록을 함께 확인할 수 없어요.",
    "Holdings에서 실제 보유 기록과 계좌별 상태를 확인하세요.",
    { watchRegistered: managedStock.watch_enabled },
  );
  const open = positions.filter((p) => p.status === "OPEN");
  const isHeld = managedStock.is_held;
  const fields = {
    openPositionCount: open.length,
    positionAccounts: [...new Set(open.map((p) =>
      p.account_name || (p.provider === "KIS" ? "KIS 연결 기록" : "수동·기타 계좌 기록")))],
    watchRegistered: managedStock.watch_enabled,
  };
  if ((open.length > 0) !== isHeld) return build(
    "LOCAL_RECORD_CONFLICT", "보유 상태와 포지션 기록 불일치",
    "목록의 보유 표시와 개별 OPEN 포지션 개수가 맞지 않습니다. 어느 쪽도 현재 계좌의 진실로 간주하지 않아요.",
    "Holdings에서 데이터를 갱신하고 계좌별 OPEN 포지션을 확인하세요.",
    fields,
  );
  if (open.length > 0) return build(
    "LOCAL_POSITION_RECORDED", "로컬 보유 포지션 기록 있음",
    "StockScope에 OPEN 포지션이 등록돼 있어요. 하지만 실제 증권계좌 잔고·현재 적용 손절선·실시간 감시 상태는 여기서 검증하지 않았어요.",
    "신규 매수 기준이 아닌 Holdings의 계좌별 적용 계획·판단·Watch 상태를 확인하세요.",
    fields,
  );
  if (managedStock.watch_enabled) return build(
    "LOCAL_WATCH_ONLY", "관심종목으로 등록됨 · 보유 확인 안 됨",
    "관심종목 등록은 보유 포지션이나 Watch 실시간 감시가 시작됐다는 의미가 아니에요.",
    "보유한 종목이라면 Holdings에 실제 포지션과 계좌를 확인하세요.",
    fields,
  );
  return build(
    "LOCAL_RECORD_NO_OPEN_POSITION", "로컬 OPEN 포지션 없음",
    "내 종목에는 기록이 있지만 OPEN 포지션은 없어요. 외부 계좌에 보유하지 않는다고 단정할 수 없어요.",
    "신규 진입 검토와 실제 보유 판단을 구분하고 계좌를 별도 확인하세요.",
    fields,
  );
}
