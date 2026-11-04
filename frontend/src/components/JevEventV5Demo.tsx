import { useEffect, useState } from "react";
import {
  getJevEventV5DemoStatus, startJevEventV5Demo,
  type JevEventV5Demo as V5DemoStatus,
} from "../services/jevApi";

/** Explicit local, fake-only V5 demo. Never accepts the current Scanner ticker. */
export default function JevEventV5Demo() {
  const [session, setSession] = useState<V5DemoStatus | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getJevEventV5DemoStatus().then(value => {
      if (active) setSession(value);
    }).catch(() => { /* Live Scanner does not depend on synthetic demo. */ });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (session?.status !== "QUEUED" && session?.status !== "RUNNING") return;
    let active = true;
    const poll = window.setInterval(() => {
      void getJevEventV5DemoStatus().then(value => {
        if (active) setSession(value);
      }).catch(() => {
        if (active) setError("V5 합성 검토 상태 확인 실패");
      });
    }, 800);
    return () => { active = false; window.clearInterval(poll); };
  }, [session?.status]);

  if (!session?.enabled) return null;
  const statuses: Record<string, string> = {
    NOT_REQUESTED: "아직 실행하지 않음",
    QUEUED: "합성 검토 대기",
    RUNNING: "V5 Fake Provider 검토 중",
    VALID: "V5 합성 결과 검증·격리 저장 완료",
    ERROR: "V5 합성 검토 실패",
    INTERRUPTED: "서버 재시작으로 중단 · 자동 재실행 없음",
  };
  const verdicts: Record<string, string> = {
    REVIEW_REQUIRED: "추가 확인 필요",
    PASS_THROUGH: "추가 확인 필요성 낮음",
    ABSTAIN: "판정 보류",
  };
  const finished = ["VALID", "ERROR", "INTERRUPTED"].includes(session.status);
  const start = async () => {
    if (!confirmed || working) return;
    setWorking(true);
    setError(null);
    try {
      setSession(await startJevEventV5Demo());
    } catch {
      setError("합성 V5 실행 요청 실패. 로컬 옵션과 이전 기록을 확인하세요.");
    } finally {
      setWorking(false);
    }
  };
  return (
    <details className="scanner-jev-motion-details" data-jev-v5-synthetic="true">
      <summary>V5 독립 이벤트 Mock 검토 · 개발 전용</summary>
      <section className="scanner-jev-local-readiness">
        <strong>독립 이벤트 JEV V5 · 합성 경로</strong>
        <p>{statuses[session.status] ?? session.status}</p>
        <p>가상 사례 999992만 사용합니다. 선택한 실제 종목, KRX, 뉴스·공시 DB와 무관하며 외부 유료 호출 0회입니다.</p>
        {session.status === "NOT_REQUESTED" && (
          <>
            <label style={{ display: "block" }}>
              <input type="checkbox" checked={confirmed}
                onChange={e => setConfirmed(e.target.checked)} />
              {" "}가상 이벤트 1회의 Fake Provider 검토임을 확인했습니다.
            </label>
            <button type="button" disabled={!confirmed || working} onClick={() => void start()}>
              {working ? "요청 중…" : "합성 V5 검토 실행"}
            </button>
          </>
        )}
        {finished && (
          <>
            <p>결과: <b>{session.result?.disposition
              ? verdicts[session.result.disposition] ?? session.result.disposition
              : "유효한 판정 없음"}</b></p>
            <p>Mock 모델: {session.result?.model_returned ?? "없음"} · 실제 API 호출 0회
              {" "}· Fake 호출 {session.mock_provider_calls ?? 0}회</p>
            {session.result?.failure_code && <p>상태: {session.result.failure_code}</p>}
            {session.result?.review_id && <small>격리 검토 ID: {session.result.review_id}</small>}
          </>
        )}
        {error && <p role="alert">{error}</p>}
        <small>기존 V4·실종목 판정과 완전히 분리되며 한 번 실행한 결과를 새로고침 후 재사용합니다.</small>
      </section>
    </details>
  );
}
