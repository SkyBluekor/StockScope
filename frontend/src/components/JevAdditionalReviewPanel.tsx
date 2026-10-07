import { useEffect, useMemo, useState } from "react";

import {
  getJevReviewFeature,
  requestJevReview,
  type JevManualReviewResult,
  type JevReviewFeature,
} from "../services/jevApi";


type Props = {
  captureId: string | null | undefined;
  sampleIndex: number | null;
  candidateName: string;
};

type ReviewView = {
  label: string;
  message: string;
  tone: "muted" | "pending" | "ok" | "review" | "warning";
};

const FEATURE_DISABLED_MESSAGE =
  "현재 추가 검토 기능을 검증 중입니다. 기본 분석 결과는 정상적으로 사용할 수 있습니다.";

function reviewView(result: JevManualReviewResult | null): ReviewView {
  if (!result) {
    return {
      label: "아직 추가 검토하지 않음",
      message:
        "필요한 경우에만 전략 조건의 의미가 서로 어긋나는 부분이 있는지 한 번 더 확인합니다.",
      tone: "muted",
    };
  }

  if (result.status === "QUEUED") {
    return {
      label: "추가 검토 대기 중",
      message: "기본 분석은 그대로 유지되며 Jev 추가 검토만 대기 중입니다.",
      tone: "pending",
    };
  }
  if (result.status === "RUNNING") {
    return {
      label: "추가 검토 중",
      message: "기본 분석 결과를 바꾸지 않고 의미 관계만 추가로 확인하고 있습니다.",
      tone: "pending",
    };
  }
  if (result.status === "PASS_THROUGH") {
    return {
      label: "추가로 확인할 의미 충돌 없음",
      message: "추가 검토에서 별도의 의미 충돌은 발견되지 않았습니다.",
      tone: "ok",
    };
  }
  if (result.status === "REVIEW_REQUIRED") {
    return {
      label: "한 번 더 확인할 부분 있음",
      message:
        "전략 조건의 의미 조합에서 다시 확인할 부분이 발견되었습니다. 기본 분석 결과를 변경하는 것은 아닙니다.",
      tone: "review",
    };
  }
  if (result.status === "SKIPPED") {
    if (result.reason === "NO_RESIDUAL_SEMANTIC_REVIEW") {
      return {
        label: "별도 검토가 필요하지 않음",
        message:
          "StockScope 기본 분석에서 충분히 판단할 수 있어 별도 Jev 검토가 필요하지 않습니다.",
        tone: "ok",
      };
    }
    if (result.reason === "LOCAL_CONFLICT_ALREADY_DETERMINED") {
      return {
        label: "기본 분석에서 이미 확인됨",
        message:
          "StockScope가 의미상 확인할 부분을 이미 판단했기 때문에 Jev를 다시 호출하지 않았습니다.",
        tone: "review",
      };
    }
    return {
      label: "별도 검토를 진행하지 않음",
      message: "현재 분석 상태에서는 Jev 추가 검토를 호출하지 않았습니다.",
      tone: "muted",
    };
  }
  if (result.status === "NOT_READY") {
    return {
      label: "이 분석은 추가 검토 준비가 되지 않음",
      message:
        "저장된 분석 상태만으로 추가 검토를 진행할 준비가 되지 않았습니다. 기본 분석 결과에는 영향이 없습니다.",
      tone: "muted",
    };
  }
  if (result.status === "UNAVAILABLE") {
    return {
      label: "현재 추가 검토를 사용할 수 없음",
      message: FEATURE_DISABLED_MESSAGE,
      tone: "muted",
    };
  }
  if (result.status === "ERROR") {
    return {
      label: "추가 검토 중 오류 발생",
      message:
        "Jev 추가 검토를 완료하지 못했습니다. StockScope 기본 분석 결과에는 영향이 없습니다.",
      tone: "warning",
    };
  }

  return {
    label: "추가 검토 상태 확인 필요",
    message: "기본 분석 결과에는 영향이 없습니다.",
    tone: "muted",
  };
}

export default function JevAdditionalReviewPanel({
  captureId,
  sampleIndex,
  candidateName,
}: Props) {
  const [feature, setFeature] = useState<JevReviewFeature | null>(null);
  const [featureError, setFeatureError] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [reviewErrorKey, setReviewErrorKey] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, JevManualReviewResult>>({});

  const reviewKey = captureId && sampleIndex != null && sampleIndex >= 0
    ? `${captureId}:${sampleIndex}`
    : null;
  const result = reviewKey ? results[reviewKey] ?? null : null;

  useEffect(() => {
    let cancelled = false;
    setFeatureError(false);
    void getJevReviewFeature()
      .then((value) => {
        if (!cancelled) setFeature(value);
      })
      .catch(() => {
        if (!cancelled) {
          setFeature(null);
          setFeatureError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [captureId]);

  useEffect(() => {
    if (reviewKey !== reviewErrorKey) setReviewErrorKey(null);
  }, [reviewKey, reviewErrorKey]);

  const enabled = Boolean(
    reviewKey
    && feature?.available === true
    && feature.feature_status === "ACTIVE",
  );

  const view = useMemo(() => {
    if (reviewErrorKey === reviewKey && reviewKey) {
      return {
        label: "추가 검토 상태 확인 실패",
        message:
          "Jev 추가 검토 요청을 완료하지 못했습니다. StockScope 기본 분석 결과에는 영향이 없습니다.",
        tone: "warning" as const,
      };
    }
    return reviewView(result);
  }, [result, reviewErrorKey, reviewKey]);

  const featureLabel = featureError
    ? "상태 확인 실패"
    : feature == null
      ? "사용 가능 여부 확인 중"
      : enabled
        ? "선택적으로 사용 가능"
        : "검증 완료 후 사용 가능";

  async function runReview() {
    if (!enabled || !captureId || sampleIndex == null || !reviewKey) return;
    setBusyKey(reviewKey);
    setReviewErrorKey(null);
    try {
      const next = await requestJevReview({
        capture_id: captureId,
        sample_index: sampleIndex,
        review_epoch: 0,
      });
      setResults((current) => ({ ...current, [reviewKey]: next }));
    } catch {
      setReviewErrorKey(reviewKey);
    } finally {
      setBusyKey((current) => current === reviewKey ? null : current);
    }
  }

  const busy = busyKey === reviewKey;
  const noSnapshot = !captureId || sampleIndex == null || sampleIndex < 0;

  return (
    <section
      className={`jev-additional-review tone-${view.tone}`}
      aria-live="polite"
    >
      <div className="jev-additional-review-rail" aria-hidden="true" />
      <div className="jev-additional-review-body">
        <header className="jev-additional-review-head">
          <div>
            <span className="jev-additional-review-kicker">추가 검토</span>
            <h3>Jev 추가 검토</h3>
            <p>
              StockScope의 기본 분석은 그대로 두고, 전략 조건의 의미가 서로
              어긋나는 부분이 있는지만 선택적으로 확인합니다.
            </p>
          </div>
          <span className="jev-additional-review-state">{featureLabel}</span>
        </header>

        <div className="jev-additional-review-selected">
          <div>
            <small>선택 후보</small>
            <strong>{candidateName}</strong>
          </div>
          <div>
            <small>추가 검토 상태</small>
            <strong>{noSnapshot ? "이 분석은 추가 검토 준비가 되지 않음" : view.label}</strong>
          </div>
        </div>

        <p className="jev-additional-review-message">
          {noSnapshot
            ? "저장된 분석 snapshot을 확인할 수 없어 추가 검토를 요청할 수 없습니다. 기본 분석 결과에는 영향이 없습니다."
            : !enabled && feature?.reason === "FEATURE_NOT_ACTIVATED"
              ? FEATURE_DISABLED_MESSAGE
              : view.message}
        </p>

        {result?.reused && (
          <p className="jev-additional-review-reused">
            이 분석에 대한 기존 검토 결과를 사용했습니다.
          </p>
        )}

        <div className="jev-additional-review-actions">
          <button
            type="button"
            className="jev-additional-review-button"
            disabled={!enabled || noSnapshot || busy}
            onClick={() => void runReview()}
          >
            {busy
              ? "추가 검토 중..."
              : enabled
                ? result
                  ? "기존 검토 결과 확인"
                  : "Jev로 한 번 더 검토"
                : "검증 완료 후 사용 가능"}
          </button>
          <small>
            Jev 결과는 후보 순위·진입·손절·목표·Risk를 변경하지 않습니다.
          </small>
        </div>
      </div>
    </section>
  );
}
