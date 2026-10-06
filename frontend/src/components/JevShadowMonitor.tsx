import { useEffect, useMemo, useState } from "react";

import type { ScannerCandidate } from "../services/api";
import {
  getJevShadowReviews,
  getJevShadowStatus,
  type JevShadowMonitorItem,
  type JevShadowReviewResponse,
  type JevShadowStatus,
} from "../services/jevShadowApi";


type Props = {
  captureId: string | null | undefined;
  selectedCandidate: ScannerCandidate | null;
};

const REASON_TEXT: Record<string, string> = {
  CONDITION_ALIGNMENT: "기존 판단과 큰 이견이 없습니다.",
  CONDITION_CONFLICT: "조건 판단을 한 번 더 확인할 필요가 있습니다.",
  ENTRY_CONTEXT_CONFLICT: "현재 진입 위치를 추가 확인할 필요가 있습니다.",
  RISK_CAUTION: "위험 구조를 한 번 더 확인할 필요가 있습니다.",
  EVIDENCE_LIMITATION: "판단 근거가 충분하지 않습니다.",
};

function statusLabel(item: JevShadowMonitorItem | null) {
  if (!item) return "검토 기록 없음";
  if (item.status === "PENDING") return "검토 중";
  if (item.status === "SKIPPED") return "검토 안 함";
  if (item.status === "LATE") return "시간 초과";
  if (item.status === "ERROR") return "검토 오류";
  if (item.status === "INTERRUPTED") return "중단됨";
  if (item.status === "VALID" && item.decision === "REVIEW_REQUIRED") {
    return "재검토 필요";
  }
  if (item.status === "VALID" && item.decision === "ABSTAIN") {
    return "판단 유보";
  }
  if (item.status === "VALID" && item.decision === "PASS_THROUGH") {
    return "검토 완료";
  }
  return "상태 확인";
}

function statusTone(item: JevShadowMonitorItem | null) {
  if (!item) return "muted";
  if (
    item.status === "ERROR"
    || item.status === "LATE"
    || item.status === "INTERRUPTED"
  ) {
    return "warning";
  }
  if (
    item.status === "VALID"
    && item.decision === "REVIEW_REQUIRED"
  ) {
    return "review";
  }
  if (
    item.status === "VALID"
    && item.decision === "PASS_THROUGH"
  ) {
    return "ok";
  }
  if (
    item.status === "VALID"
    && item.decision === "ABSTAIN"
  ) {
    return "muted";
  }
  if (item.status === "PENDING") return "pending";
  return "muted";
}

function selectedMessage(item: JevShadowMonitorItem | null) {
  if (!item) {
    return "이 후보의 보조 검토 기록이 아직 없습니다.";
  }
  if (item.status === "PENDING") {
    return "StockScope 결과는 이미 사용할 수 있고, AI 보조 검토만 진행 중입니다.";
  }
  if (item.status === "SKIPPED") {
    return "이 후보는 현재 Shadow 검토 대상이 아닙니다.";
  }
  if (item.status === "LATE") {
    return "응답 시간이 기준을 넘어서 보조 판단으로 사용하지 않습니다.";
  }
  if (item.status === "ERROR") {
    return "AI 보조 검토에서 오류가 발생했지만 StockScope 결과에는 영향이 없습니다.";
  }
  if (item.status === "INTERRUPTED") {
    return "서버 재시작 등으로 보조 검토가 중단됐습니다.";
  }
  if (item.status === "VALID" && item.decision === "ABSTAIN") {
    return "근거가 충분하지 않아 AI 보조 검토가 판단을 유보했습니다.";
  }
  const mapped = item.reason_codes
    .map((code) => REASON_TEXT[code])
    .filter((value): value is string => Boolean(value));
  if (mapped.length > 0) {
    return mapped.slice(0, 2).join(" ");
  }
  if (item.decision === "REVIEW_REQUIRED") {
    return "추가로 확인할 요소가 있어 한 번 더 검토하는 편이 좋습니다.";
  }
  return "기존 판단과 큰 이견이 없습니다.";
}

function overallLabel(
  status: JevShadowStatus | null,
  reviews: JevShadowReviewResponse | null,
) {
  if (status && !status.available) return "준비되지 않음";
  if (status && !status.enabled) return "사용 안 함";
  if (!reviews) return "상태 확인 중";
  if (!reviews.available) return "준비되지 않음";
  if (reviews.summary.pending > 0) return "검토 중";
  if (reviews.summary.review_required > 0) return "재검토 후보 있음";
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
  const [status, setStatus] = useState<JevShadowStatus | null>(null);
  const [reviews, setReviews] = useState<JevShadowReviewResponse | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getJevShadowStatus()
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
        const value = await getJevShadowReviews(captureId);
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
        <small>Shadow · 읽기 전용</small>
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
            <small>재검토</small>
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
            <span>
              처리 {latencyText(selectedReview.latency_ms)}
            </span>
          )}
        </div>
      )}

      {pollTimedOut && (
        <p className="jev-shadow-poll-note">
          검토가 계속 진행 중입니다. 다음 조회에서 결과를 확인할 수 있습니다.
        </p>
      )}

      <p className="jev-shadow-guardrail">
        StockScope의 기존 후보·순위·진입·Risk 판단에는 반영되지 않는 보조 검토입니다.
      </p>
    </section>
  );
}
