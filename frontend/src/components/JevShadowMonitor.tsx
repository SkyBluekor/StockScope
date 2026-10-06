import { useEffect, useMemo, useState } from "react";

import type { ScannerCandidate } from "../services/api";
import {
  getJevReviews,
  getJevStatus,
  type JevMonitorItem,
  type JevReviewResponse,
  type JevStatus,
} from "../services/jevApi";


type Props = {
  captureId: string | null | undefined;
  selectedCandidate: ScannerCandidate | null;
};

const REASON_TEXT: Record<string, string> = {
  STRATEGY_CONTEXT_CONFLICT:
    "전략 맥락과 조건 조합을 한 번 더 확인할 필요가 있습니다.",
  ENTRY_CONTEXT_CONFLICT:
    "진입 설명 맥락을 한 번 더 확인할 필요가 있습니다.",
  NO_ADDITIONAL_CONTEXT_CONFLICT:
    "추가로 확인할 의미상 충돌이 없습니다.",
};

function statusLabel(item: JevMonitorItem | null) {
  if (!item) return "검토 기록 없음";
  if (item.operational_status === "PENDING") return "검토 중";
  if (item.operational_status === "SKIPPED") return "검토 안 함";
  if (item.operational_status === "LATE") return "시간 초과";
  if (item.operational_status === "ERROR") return "검토 오류";
  if (item.operational_status === "INTERRUPTED") return "중단됨";
  if (
    item.operational_status === "VALID"
    && item.disposition === "REVIEW_REQUIRED"
  ) {
    return "추가 확인 필요";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "ABSTAIN"
  ) {
    return "판단 유보";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "PASS_THROUGH"
  ) {
    return "추가 확인 없음";
  }
  return "상태 확인";
}

function statusTone(item: JevMonitorItem | null) {
  if (!item) return "muted";
  if (
    item.operational_status === "ERROR"
    || item.operational_status === "LATE"
    || item.operational_status === "INTERRUPTED"
  ) {
    return "warning";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "REVIEW_REQUIRED"
  ) {
    return "review";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "PASS_THROUGH"
  ) {
    return "ok";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "ABSTAIN"
  ) {
    return "muted";
  }
  if (item.operational_status === "PENDING") return "pending";
  return "muted";
}

function selectedMessage(item: JevMonitorItem | null) {
  if (!item) {
    return "이 후보의 TypeSafe Jev 보조 검토 기록이 아직 없습니다.";
  }
  if (item.operational_status === "PENDING") {
    return "StockScope 결과는 이미 사용할 수 있고, Jev 보조 검토만 진행 중입니다.";
  }
  if (item.operational_status === "SKIPPED") {
    return "이 후보는 현재 TypeSafe Jev 검토 호출 대상이 아닙니다.";
  }
  if (item.operational_status === "LATE") {
    return "응답 시간이 기준을 넘어서 보조 판단으로 사용하지 않습니다.";
  }
  if (item.operational_status === "ERROR") {
    return "Jev 보조 검토에서 오류가 발생했지만 StockScope 결과에는 영향이 없습니다.";
  }
  if (item.operational_status === "INTERRUPTED") {
    return "서버 재시작 등으로 보조 검토가 중단됐습니다.";
  }
  if (
    item.operational_status === "VALID"
    && item.disposition === "ABSTAIN"
  ) {
    if (item.uncertainty_reason === "EVIDENCE_INSUFFICIENT") {
      return "현재 전달된 맥락만으로는 보조 검토 근거가 충분하지 않습니다.";
    }
    return "의미상 판단이 경계 구간에 있어 보조 검토가 판단을 유보했습니다.";
  }

  const mapped = item.reason_codes
    .map((code) => REASON_TEXT[code])
    .filter((value): value is string => Boolean(value));
  if (mapped.length > 0) {
    return mapped.slice(0, 2).join(" ");
  }
  if (item.disposition === "REVIEW_REQUIRED") {
    return "의미상 충돌 신호가 있어 한 번 더 확인하는 편이 좋습니다.";
  }
  return "추가로 확인할 의미상 충돌이 없습니다.";
}

function overallLabel(
  status: JevStatus | null,
  reviews: JevReviewResponse | null,
) {
  if (status && !status.available) return "준비되지 않음";
  if (status?.trial_status === "TRIAL_NOT_FROZEN") {
    return "코어 준비됨 · 시험 미시작";
  }
  if (
    status
    && !status.enabled
    && status.protocol_status === "FROZEN"
  ) {
    return "시험 준비됨 · 아직 시작하지 않음";
  }
  if (status && !status.enabled) return "사용 안 함";
  if (!reviews) return "상태 확인 중";
  if (!reviews.available) return "준비되지 않음";
  if (reviews.summary.pending > 0) return "검토 중";
  if (reviews.summary.review_required > 0) return "추가 확인 후보 있음";
  if (
    reviews.summary.error
    + reviews.summary.late
    + reviews.summary.interrupted
    > 0
  ) {
    return "일부 검토 확인 필요";
  }
  if (reviews.summary.complete > 0) return "검토 완료";
  if (
    reviews.summary.total > 0
    && reviews.summary.skipped === reviews.summary.total
  ) {
    return "검토 안 함";
  }
  return "아직 기록 없음";
}

function latencyText(latencyMs: number) {
  const safe = Math.max(0, latencyMs);
  if (safe < 1000) return safe + "ms";
  return (safe / 1000).toFixed(1) + "초";
}

export default function JevShadowMonitor({
  captureId,
  selectedCandidate,
}: Props) {
  const [status, setStatus] = useState<JevStatus | null>(null);
  const [reviews, setReviews] = useState<JevReviewResponse | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getJevStatus()
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [captureId]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const startedAt = Date.now();

    setReviews(null);
    setPollTimedOut(false);
    setLoadError(false);

    if (!captureId) {
      return () => {
        cancelled = true;
      };
    }

    const load = async () => {
      try {
        const value = await getJevReviews(captureId);
        if (cancelled) return;
        setReviews(value);
        const stillPending = value.summary.pending > 0;
        if (stillPending && Date.now() - startedAt < 30_000) {
          timer = window.setTimeout(() => {
            void load();
          }, 1500);
        } else if (stillPending) {
          setPollTimedOut(true);
        }
      } catch {
        if (!cancelled) setLoadError(true);
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [captureId]);

  const selectedReview = useMemo(() => {
    if (!selectedCandidate || !reviews) return null;
    return reviews.items.find(
      (item) => (
        item.market === selectedCandidate.market
        && item.ticker === selectedCandidate.code
      ),
    ) ?? null;
  }, [reviews, selectedCandidate]);

  const label = overallLabel(status, reviews);
  const selectedTone = statusTone(selectedReview);
  const errorCount = reviews
    ? reviews.summary.error
      + reviews.summary.late
      + reviews.summary.interrupted
    : 0;

  return (
    <section
      className={"jev-shadow-monitor tone-" + selectedTone}
      aria-live="polite"
    >
      <header className="jev-shadow-monitor-head">
        <div>
          <span>AI 보조 검토</span>
          <strong>{loadError ? "검토 상태 확인 실패" : label}</strong>
        </div>
        <small>TypeSafe Jev · Shadow</small>
      </header>

      {!captureId ? (
        <p className="jev-shadow-monitor-empty">
          이번 Scanner 결과에는 연결된 Shadow capture가 아직 없습니다.
        </p>
      ) : reviews ? (
        <div className="jev-shadow-monitor-stats">
          <span>
            <small>완료</small>
            <b>{reviews.summary.complete}</b>
          </span>
          <span>
            <small>추가 확인</small>
            <b>{reviews.summary.review_required}</b>
          </span>
          <span>
            <small>검토 중</small>
            <b>{reviews.summary.pending}</b>
          </span>
          <span>
            <small>유보</small>
            <b>{reviews.summary.abstain}</b>
          </span>
          <span>
            <small>오류/지연</small>
            <b>{errorCount}</b>
          </span>
        </div>
      ) : (
        <p className="jev-shadow-monitor-empty">
          {loadError
            ? "보조 검토 상태를 불러오지 못했습니다."
            : "보조 검토 상태를 확인하는 중입니다."}
        </p>
      )}

      {selectedCandidate && (
        <div className={"jev-shadow-selected tone-" + selectedTone}>
          <div>
            <small>선택 후보</small>
            <strong>
              {selectedCandidate.name}
              {" · "}
              {statusLabel(selectedReview)}
            </strong>
          </div>
          <p>{selectedMessage(selectedReview)}</p>
          {selectedReview?.latency_ms != null && (
            <span>처리 {latencyText(selectedReview.latency_ms)}</span>
          )}
        </div>
      )}

      {pollTimedOut && (
        <p className="jev-shadow-poll-note">
          검토가 계속 진행 중입니다. 다음 조회에서 결과를 확인할 수 있습니다.
        </p>
      )}

      <p className="jev-shadow-guardrail">
        Jev 보조 검토는 StockScope의 기존 후보·순위·진입·Risk 판단을 변경하지 않습니다.
      </p>
    </section>
  );
}
