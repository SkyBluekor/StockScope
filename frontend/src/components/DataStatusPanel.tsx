import type { ProviderStatus } from "../services/api";
import type { DataTaskSnapshot } from "../services/dataTask";
import { dataTaskIsRunning } from "../services/dataTask";

type Props = {
  open: boolean;
  apiStatus: string;
  providers: ProviderStatus | null;
  task: DataTaskSnapshot | null;
  refreshing: boolean;
  onClose: () => void;
  onRefresh: () => void;
  onOpenTask: () => void;
};

type StatusTone = "ok" | "warn" | "idle";

type CapabilityState = {
  label: string;
  tone: StatusTone;
  description: string;
};

function configuredState(
  configured: boolean | null,
  description: string,
  missingLabel = "설정 필요",
): CapabilityState {
  if (configured == null) {
    return { label: "확인되지 않음", tone: "idle", description };
  }
  if (configured) {
    return { label: "설정됨 · 연결 확인 전", tone: "ok", description };
  }
  return { label: missingLabel, tone: "warn", description };
}

function taskLabel(task: DataTaskSnapshot) {
  if (task.status === "completed") return "작업 완료";
  if (task.status === "failed") return "작업 실패";
  if (task.status === "cancelled") return "작업 취소됨";
  if (task.status === "unknown") return "상태 확인 필요";
  return task.allowLargeSync ? "시장 데이터 준비 중" : "종목 후보 찾기 진행 중";
}

export function dataStatusSummary(apiStatus: string, providers: ProviderStatus | null) {
  if (apiStatus !== "정상") return { label: "데이터 상태 확인 필요", tone: "warn" as const };
  if (!providers) return { label: "데이터 설정 확인 중", tone: "idle" as const };
  if (!providers.krx.configured) return { label: "시장 데이터 설정 필요", tone: "warn" as const };
  if (!providers.dart.configured || !providers.naver_news.configured) {
    return { label: "일부 기능 설정 필요", tone: "warn" as const };
  }
  return { label: "기본 데이터 설정됨", tone: "ok" as const };
}

export default function DataStatusPanel({
  open,
  apiStatus,
  providers,
  task,
  refreshing,
  onClose,
  onRefresh,
  onOpenTask,
}: Props) {
  if (!open) return null;

  const summary = dataStatusSummary(apiStatus, providers);
  const krx = configuredState(
    providers ? providers.krx.configured : null,
    "종목 분석·후보 찾기·과거 성과의 시장 가격과 지수 데이터에 사용합니다.",
  );
  const dart = configuredState(
    providers ? providers.dart.configured : null,
    providers?.dart.configured
      ? "기업 기본정보와 공시·재무 정보에 사용합니다."
      : "기업·공시 정보만 제한됩니다. 가격과 전략 분석은 계속 사용할 수 있습니다.",
    "사용 제한",
  );
  const news = configuredState(
    providers ? providers.naver_news.configured : null,
    providers?.naver_news.configured
      ? "종목별 최근 뉴스 검색 결과에 사용합니다."
      : "최근 뉴스만 제한됩니다. 종목 분석과 전략 계산에는 영향을 주지 않습니다.",
    "사용 제한",
  );
  const kis: CapabilityState = providers == null
    ? { label: "확인되지 않음", tone: "idle", description: "선택적 증권사 연동 상태를 확인합니다." }
    : providers.kis.enabled
      ? {
          label: "설정됨 · 연결 확인 전",
          tone: "ok",
          description: "실계좌 잔고·현재가·실시간 시세를 사용하는 선택 기능입니다.",
        }
      : {
          label: "사용 안 함",
          tone: "idle",
          description: "선택 기능입니다. 직접 등록한 관심·보유 종목은 계속 사용할 수 있습니다.",
        };
  const running = dataTaskIsRunning(task);

  return (
    <div className="data-status-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="data-status-panel"
        role="dialog"
        aria-modal="true"
        aria-label="데이터 상태"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="data-status-head">
          <div>
            <h2>데이터 상태</h2>
            <p>현재 기능에 영향을 주는 설정과 데이터 작업 상태를 확인합니다.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="데이터 상태 닫기">×</button>
        </header>

        <section className={`data-status-summary tone-${summary.tone}`}>
          <span>현재 상태</span>
          <strong>{summary.label}</strong>
          <small>
            {apiStatus === "정상"
              ? "현재 API가 확인하는 것은 설정 여부입니다. 실제 제공처 연결 성공과 데이터 최신성은 이 상태만으로 판단하지 않습니다."
              : "백엔드 API 상태부터 확인해야 데이터 설정 정보를 읽을 수 있습니다."}
          </small>
        </section>

        {task && (
          <section className={`data-status-task ${running ? "running" : task.status}`} aria-live="polite">
            <div>
              <span>{taskLabel(task)}</span>
              <strong>{task.message}</strong>
              <small>
                {task.current != null && task.total != null && task.total > 0
                  ? `${task.current.toLocaleString()} / ${task.total.toLocaleString()}`
                  : task.current != null
                    ? `${task.current.toLocaleString()}건 처리`
                    : "진행 정보 확인 중"}
              </small>
            </div>
            <button type="button" onClick={onOpenTask}>
              {running ? "진행 보기" : "결과 보기"}
            </button>
          </section>
        )}

        <section className="data-status-capabilities" aria-label="기능별 데이터 설정">
          <h3>기능별 상태</h3>
          <div className="data-status-capability-row">
            <div>
              <span>시장 가격·지수</span>
              <small>{krx.description}</small>
            </div>
            <strong className={`tone-${krx.tone}`}>{krx.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <div>
              <span>기업·공시 정보</span>
              <small>{dart.description}</small>
            </div>
            <strong className={`tone-${dart.tone}`}>{dart.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <div>
              <span>최근 뉴스</span>
              <small>{news.description}</small>
            </div>
            <strong className={`tone-${news.tone}`}>{news.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <div>
              <span>증권사 연동</span>
              <small>{kis.description}</small>
            </div>
            <strong className={`tone-${kis.tone}`}>{kis.label}</strong>
          </div>
        </section>

        <details className="data-status-providers">
          <summary>기술 정보 보기</summary>
          <dl>
            <div>
              <dt>KRX</dt>
              <dd>
                <strong className={`tone-${krx.tone}`}>{providers == null ? "확인되지 않음" : providers.krx.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.krx.role ?? "시장/일별 시세/지수"}</span>
              </dd>
            </div>
            <div>
              <dt>DART</dt>
              <dd>
                <strong className={`tone-${dart.tone}`}>{providers == null ? "확인되지 않음" : providers.dart.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.dart.role ?? "기업/공시/재무"}</span>
              </dd>
            </div>
            <div>
              <dt>NAVER NEWS</dt>
              <dd>
                <strong className={`tone-${news.tone}`}>{providers == null ? "확인되지 않음" : providers.naver_news.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.naver_news.role ?? "종목 최근 뉴스"}</span>
              </dd>
            </div>
            <div>
              <dt>KIS</dt>
              <dd>
                <strong className={`tone-${kis.tone}`}>{providers == null ? "확인되지 않음" : providers.kis.enabled ? "설정됨" : "사용 안 함"}</strong>
                <span>{providers?.kis.role ?? "선택적 증권사 연동"}</span>
              </dd>
            </div>
          </dl>
        </details>

        <footer className="data-status-actions">
          <button type="button" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "설정 확인 중..." : "설정 상태 다시 확인"}
          </button>
          <button type="button" className="secondary" onClick={onClose}>닫기</button>
        </footer>
      </aside>
    </div>
  );
}
