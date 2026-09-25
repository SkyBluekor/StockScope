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

function availability(ok: boolean, optional = false) {
  if (ok) return { label: "사용 가능", tone: "ok" };
  if (optional) return { label: "사용 안 함", tone: "idle" };
  return { label: "설정 확인 필요", tone: "warn" };
}

function taskLabel(task: DataTaskSnapshot) {
  if (task.status === "completed") return "작업 완료";
  if (task.status === "failed") return "작업 실패";
  if (task.status === "cancelled") return "작업 취소됨";
  if (task.status === "unknown") return "상태 확인 필요";
  return task.allowLargeSync ? "시장 데이터 준비 중" : "종목 후보 찾기 진행 중";
}

export function dataStatusSummary(apiStatus: string, providers: ProviderStatus | null) {
  if (apiStatus !== "정상") return { label: "데이터 상태 확인 필요", tone: "warn" };
  if (!providers) return { label: "데이터 상태 확인 중", tone: "idle" };
  const requiredReady = providers.krx.configured && providers.dart.configured;
  if (!requiredReady) return { label: "데이터 설정 확인 필요", tone: "warn" };
  return { label: "데이터 상태 정상", tone: "ok" };
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
  const krx = availability(Boolean(providers?.krx.configured));
  const dart = availability(Boolean(providers?.dart.configured));
  const news = availability(Boolean(providers?.naver_news.configured));
  const kis = availability(Boolean(providers?.kis.enabled), true);
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
            <span>DATA STATUS</span>
            <h2>데이터 상태</h2>
            <p>기능에 영향을 주는 데이터 연결 상태를 확인합니다.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="데이터 상태 닫기">×</button>
        </header>

        <section className={`data-status-summary tone-${summary.tone}`}>
          <span>현재 상태</span>
          <strong>{summary.label}</strong>
          <small>
            {apiStatus === "정상"
              ? "설정 여부를 기준으로 표시합니다. 실제 최신 데이터 시각이나 마지막 연결 성공 시각은 현재 API가 제공하지 않습니다."
              : "백엔드 API 연결부터 확인해야 합니다."}
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

        <section className="data-status-capabilities">
          <h3>현재 사용할 수 있는 기능</h3>
          <div className="data-status-capability-row">
            <span>시장 가격·지수</span>
            <strong className={`tone-${krx.tone}`}>{krx.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <span>기업·공시 정보</span>
            <strong className={`tone-${dart.tone}`}>{dart.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <span>최근 뉴스</span>
            <strong className={`tone-${news.tone}`}>{news.label}</strong>
          </div>
          <div className="data-status-capability-row">
            <span>증권사 연동</span>
            <strong className={`tone-${kis.tone}`}>{kis.label}</strong>
          </div>
        </section>

        <section className="data-status-providers">
          <h3>상세 연결</h3>
          <dl>
            <div>
              <dt>KRX</dt>
              <dd>
                <strong className={`tone-${krx.tone}`}>{providers?.krx.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.krx.role ?? "시장/일별 시세/지수"}</span>
              </dd>
            </div>
            <div>
              <dt>DART</dt>
              <dd>
                <strong className={`tone-${dart.tone}`}>{providers?.dart.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.dart.role ?? "기업/공시/재무"}</span>
              </dd>
            </div>
            <div>
              <dt>NAVER NEWS</dt>
              <dd>
                <strong className={`tone-${news.tone}`}>{providers?.naver_news.configured ? "설정됨" : "설정 필요"}</strong>
                <span>{providers?.naver_news.role ?? "종목 최근 뉴스"}</span>
              </dd>
            </div>
            <div>
              <dt>KIS</dt>
              <dd>
                <strong className={`tone-${kis.tone}`}>{providers?.kis.enabled ? "활성" : "사용 안 함"}</strong>
                <span>{providers?.kis.role ?? "선택적 증권사 연동"}</span>
              </dd>
            </div>
          </dl>
        </section>

        <footer className="data-status-actions">
          <button type="button" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "확인 중..." : "상태 다시 확인"}
          </button>
          <button type="button" className="secondary" onClick={onClose}>닫기</button>
        </footer>
      </aside>
    </div>
  );
}
