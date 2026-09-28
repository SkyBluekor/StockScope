export type WatchRuleStatus = {
  rule_id: string;
  rule_kind: "STOP" | "TARGET1" | "TARGET2" | string;
  threshold_price: string;
  state: "ARMED" | "PENDING_CONFIRMATION" | "CONFIRMED" | "RESOLVED" | "DISABLED" | string;
  status: "ACTIVE" | "CLOSED" | string;
  last_observed_at: string | null;
  last_price: string | null;
};

export type WatchGapStatus = {
  gap_id: string;
  reason_code: string;
  started_at: string;
};

export type WatchNotificationSummary = {
  notification_id: string;
  payload: {
    rule_kind?: string;
    threshold_price?: string;
    confirmed_price?: string;
    confirmed_at?: string;
    plan_version?: number;
    [key: string]: unknown;
  };
  created_at: string;
  read_at: string | null;
};

export type WatchPositionStatus = {
  available: boolean;
  migration_required: boolean;
  position_id: string;
  policy_enabled: boolean;
  blocked_reason: string | null;
  setting: null | {
    setting_id: string;
    plan_id: string;
    plan_version: number;
    status: string;
    policy_version: string;
  };
  rules: WatchRuleStatus[];
  open_gaps: WatchGapStatus[];
  latest_notification: WatchNotificationSummary | null;
};

export type WatchNotification = {
  notification_id: string;
  position_id: string;
  plan_id: string;
  market: string;
  ticker: string;
  name: string;
  notification_type: string;
  delivery_status: string;
  payload: Record<string, unknown>;
  created_at: string;
  delivered_at: string | null;
  read_at: string | null;
};

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (response.ok) return response.json() as Promise<T>;

  let message = `Watch 요청 실패 (${response.status})`;
  try {
    const body = await response.json() as {
      detail?: string | { message?: string };
    };
    if (typeof body.detail === "string") message = body.detail;
    else if (body.detail?.message) message = body.detail.message;
  } catch {
    // Keep the stable fallback message.
  }
  throw new Error(message);
}

export function getWatchPosition(
  positionId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WatchPositionStatus> {
  return requestJson<WatchPositionStatus>(
    `/api/watch/positions/${encodeURIComponent(positionId)}`,
    { signal: options.signal },
  );
}

export async function getWatchNotifications(
  options: { signal?: AbortSignal; unreadOnly?: boolean; limit?: number } = {},
): Promise<WatchNotification[]> {
  const query = new URLSearchParams({
    limit: String(options.limit ?? 50),
    unread_only: String(options.unreadOnly ?? false),
  });
  const result = await requestJson<{ items: WatchNotification[] }>(
    `/api/watch/notifications?${query.toString()}`,
    { signal: options.signal },
  );
  return result.items;
}

export function markWatchNotificationRead(
  notificationId: string,
): Promise<{
  notification_id: string;
  delivery_status: string;
  delivered_at: string | null;
  read_at: string | null;
}> {
  return requestJson(
    `/api/watch/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: "POST" },
  );
}
