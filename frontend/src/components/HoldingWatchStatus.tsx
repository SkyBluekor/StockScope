import { useEffect, useMemo, useState } from "react";
import type { HoldingPosition } from "../services/holdingsApi";
import {
  getWatchPosition,
  type WatchPositionStatus,
} from "../services/watchApi";

type Props = {
  positions: HoldingPosition[];
  sourceKey: string;
};

function statusLabel(status: WatchPositionStatus) {
  if (status.migration_required) return "준비 필요";
  if (!status.policy_enabled) return "정책 검증 중";
  if (status.open_gaps.length > 0) return "감시 공백";
  if (status.rules.some((rule) => rule.state === "CONFIRMED")) return "기준 확인됨";
  if (status.setting) return "감시 중";
  return "미감시";
}

function statusDetail(status: WatchPositionStatus) {
  if (status.migration_required) {
    return "Watch 저장 구조가 아직 준비되지 않았습니다.";
  }
  if (!status.policy_enabled) {
    return "실시간 confirmation·재무장 기준을 검증하기 전이라 운영 감시는 켜지 않았습니다.";
  }
  if (status.open_gaps.length > 0) {
    return "시세 연속성이 끊긴 구간이 있습니다 · "
      + status.open_gaps.map((gap) => gap.reason_code).join(", ");
  }
  const confirmed = status.rules.find((rule) => rule.state === "CONFIRMED");
  if (confirmed) {
    return confirmed.rule_kind + " "
      + Number(confirmed.threshold_price).toLocaleString("ko-KR")
      + "원 기준이 확인되었습니다.";
  }
  if (status.setting) {
    return "현재 적용 Plan v" + status.setting.plan_version + " 기준으로 서버가 관찰합니다.";
  }
  return "현재 적용 계획에 연결된 Watch가 없습니다.";
}

export default function HoldingWatchStatus({ positions, sourceKey }: Props) {
  const openPositions = useMemo(
    () => positions.filter((position) => position.status === "OPEN"),
    [positions],
  );
  const [statuses, setStatuses] = useState<Record<string, WatchPositionStatus>>({});
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setError(false);

    if (openPositions.length === 0) {
      setStatuses({});
      return () => controller.abort();
    }

    void Promise.all(
      openPositions.map(async (position) => {
        const status = await getWatchPosition(
          position.position_id,
          { signal: controller.signal },
        );
        return [position.position_id, status] as const;
      }),
    ).then((rows) => {
      if (!controller.signal.aborted) {
        setStatuses(Object.fromEntries(rows));
      }
    }).catch((loadError) => {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      if (!controller.signal.aborted) setError(true);
    });

    return () => controller.abort();
  }, [sourceKey, openPositions.map((position) => position.position_id).join("|")]);

  if (openPositions.length === 0) return null;

  return (
    <div className="holding-watch-summary" aria-label="실시간 감시 상태">
      <span className="holding-watch-summary-label">실시간 감시</span>
      <div className="holding-watch-summary-list">
        {openPositions.map((position) => {
          const status = statuses[position.position_id];
          return (
            <div className="holding-watch-summary-row" key={position.position_id}>
              <strong>
                {error
                  ? "상태 확인 실패"
                  : status
                    ? statusLabel(status)
                    : "확인 중"}
              </strong>
              <span>
                {error
                  ? "기존 보유 판단과 관리 계획은 그대로 유지됩니다."
                  : status
                    ? statusDetail(status)
                    : "Watch 상태를 확인하고 있습니다."}
              </span>
              {openPositions.length > 1 && (
                <small>{position.account_name || position.provider || "보유 기록"}</small>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
