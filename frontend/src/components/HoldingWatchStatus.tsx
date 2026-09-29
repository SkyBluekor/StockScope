import { useEffect, useMemo, useState } from "react";
import type {
  HoldingPosition,
  HoldingWorkspaceSourceStatus,
} from "../services/holdingsApi";
import {
  getWatchNotifications,
  getWatchStatus,
  markWatchNotificationRead,
  type WatchNotification,
  type WatchPositionStatus,
  type WatchSystemStatus,
} from "../services/watchApi";

type Props = {
  positions: HoldingPosition[];
  statuses: Record<string, WatchPositionStatus>;
  status?: HoldingWorkspaceSourceStatus;
  loading?: boolean;
};

function transportLabel(value: string | null | undefined) {
  if (value === "CONNECTED") return "시세 연결 정상";
  if (value === "BACKOFF") return "재연결 중";
  if (value === "DEGRADED") return "시세 연결 문제";
  if (value === "CONNECTING") return "연결 중";
  if (value === "DISABLED") return "실시간 시세 비활성";
  if (value === "IDLE") return "대기 중";
  return "상태 확인 중";
}

function continuityLabel(status: WatchSystemStatus | null) {
  const session = status?.runtime?.session;
  if (!status?.runtime || status.runtime.migration_required) return "준비 필요";
  if (!session) return "기록 없음";
  if (session.continuity_state === "UNMONITORED") return "감시 연속성 미확인";
  if (session.status === "RUNNING") return "실행 중";
  if (session.status === "INTERRUPTED") return "이전 실행 중단";
  return "정상 종료";
}

function notificationText(item: WatchNotification) {
  const kind = String(item.payload.rule_kind ?? item.notification_type ?? "Watch");
  const threshold = item.payload.threshold_price
    ? Number(item.payload.threshold_price).toLocaleString("ko-KR") + "원"
    : "기준가";
  const confirmed = item.payload.confirmed_price
    ? " · 확인가 " + Number(item.payload.confirmed_price).toLocaleString("ko-KR") + "원"
    : "";
  return kind + " · " + threshold + confirmed;
}

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

export default function HoldingWatchStatus({
  positions,
  statuses,
  status,
  loading = false,
}: Props) {
  const [systemStatus, setSystemStatus] = useState<WatchSystemStatus | null>(null);
  const [notifications, setNotifications] = useState<WatchNotification[]>([]);
  const [watchError, setWatchError] = useState<string | null>(null);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [busyNotificationId, setBusyNotificationId] = useState<string | null>(null);

  async function loadWatchOverview(signal?: AbortSignal) {
    try {
      const [nextStatus, nextNotifications] = await Promise.all([
        getWatchStatus({ signal }),
        getWatchNotifications({ signal, limit: 20 }),
      ]);
      setSystemStatus(nextStatus);
      setNotifications(nextNotifications);
      setWatchError(null);
    } catch (loadError) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setWatchError(loadError instanceof Error ? loadError.message : "Watch 상태를 불러오지 못했습니다.");
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadWatchOverview(controller.signal);
    return () => controller.abort();
  }, [positions.map((position) => position.position_id).join("|")]);

  async function confirmNotification(notificationId: string) {
    setBusyNotificationId(notificationId);
    try {
      await markWatchNotificationRead(notificationId);
      await loadWatchOverview();
    } finally {
      setBusyNotificationId(null);
    }
  }

  const openPositions = useMemo(
    () => positions.filter((position) => position.status === "OPEN"),
    [positions],
  );
  const error = status?.status === "PARTIAL" || status?.status === "UNAVAILABLE";

  if (openPositions.length === 0) return null;

  return (
    <div className="holding-watch-summary" aria-label="실시간 감시 상태">
      <span className="holding-watch-summary-label">실시간 감시</span>

      <div className="holding-watch-health">
        <div>
          <span>Watch 정책</span>
          <strong>
            {systemStatus?.migration_required
              ? "준비 필요"
              : systemStatus?.policy_enabled
                ? "운영 감시"
                : "정책 검증 중"}
          </strong>
        </div>
        <div>
          <span>시세 연결</span>
          <strong>{transportLabel(systemStatus?.transport?.state)}</strong>
        </div>
        <div>
          <span>실행 연속성</span>
          <strong>{continuityLabel(systemStatus)}</strong>
        </div>
        <div>
          <span>미확인 알림</span>
          <strong>{systemStatus?.notifications?.unread ?? systemStatus?.pending_notifications ?? 0}건</strong>
        </div>
        <button
          type="button"
          className="holdings-text-button"
          onClick={() => setInboxOpen((value) => !value)}
        >
          {inboxOpen ? "알림 닫기" : "알림 보기"}
        </button>
      </div>

      {watchError && <p className="holding-watch-error">{watchError}</p>}

      {systemStatus?.runtime?.session?.continuity_state === "UNMONITORED" && (
        <p className="holding-watch-continuity">
          이전 실행의 마지막 heartbeat 이후 StockScope 실행 상태가 이어졌다고 확인할 수 없습니다.
          이 구간을 시장 데이터 장애라고 단정하지 않습니다.
        </p>
      )}

      {inboxOpen && (
        <div className="holding-watch-inbox" aria-label="Watch 알림함">
          {notifications.length === 0 ? (
            <p>저장된 Watch 알림이 없습니다.</p>
          ) : notifications.map((item) => (
            <div className="holding-watch-notification" key={item.notification_id}>
              <div>
                <strong>{item.name} · {item.ticker}</strong>
                <span>{notificationText(item)}</span>
                <small>{item.created_at} · {item.read_at ? "확인" : "미확인"}</small>
              </div>
              {!item.read_at && (
                <button
                  type="button"
                  className="holdings-text-button"
                  disabled={busyNotificationId === item.notification_id}
                  onClick={() => void confirmNotification(item.notification_id)}
                >
                  {busyNotificationId === item.notification_id ? "확인 중…" : "확인"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
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
                    : loading ? "확인 중" : "상태 없음"}
              </strong>
              <span>
                {error
                  ? "기존 보유 판단과 관리 계획은 그대로 유지됩니다."
                  : status
                    ? statusDetail(status)
                    : loading ? "Watch 상태를 확인하고 있습니다." : "저장된 Watch 상태가 없습니다."}
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
