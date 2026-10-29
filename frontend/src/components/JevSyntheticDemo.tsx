import { useEffect, useState } from "react";
import {
  getJevSyntheticDemoStatus,
  startJevSyntheticDemo,
  type JevSyntheticDemoStatus,
} from "../services/jevApi";

/** Only shown when the backend explicitly enables the localhost-only demo.
 * It never takes the selected ticker or Scanner capture as input. */
export default function JevSyntheticDemo() {
  const [session, setSession] = useState<JevSyntheticDemoStatus | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void getJevSyntheticDemoStatus()
      .then(value => { if (mounted) setSession(value); })
      .catch(() => { /* Ordinary Scanner remains usable without this demo. */ });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (session?.status !== "QUEUED" && session?.status !== "RUNNING") return;
    let mounted = true;
    const timer = window.setInterval(() => {
      void getJevSyntheticDemoStatus()
        .then(value => { if (mounted) setSession(value); })
        .catch(() => { if (mounted) setError("합성 작업 상태를 조회할 수 없습니다."); });
    }, 800);
    return () => { mounted = false; window.clearInterval(timer); };
  }, [session?.status]);

  if (!session?.enabled) return null;
  const finished = session.status === "VALID" || session.status === "ERROR"
    || session.status === "INTERRUPTED";
  const summary: Record<string, string> = {
    NOT_REQUESTED: "아직 실행하지 않음",
    QUEUED: "합성 검토 대기 중",
    RUNNING: "Mock V4 검토 실행 중",
    VALID: "합성 결과 검증·저장 완료",
    ERROR: "합성 검토 실패",
    INTERRUPTED: "서버 재시작으로 검토 중단 · 자동 재시도 없음",
  };
  const disposition: Record<string, string> = {
    PASS_THROUGH: "기존 판단 유지",
    REVIEW_REQUIRED: "추가 확인 필요",
    ABSTAIN: "판단 유보",
  };
  const run = async () => {
    if (!confirmed || working) return;
    setWorking(true);
    setError(null);
    try {
      setSession(await startJevSyntheticDemo());
    } catch {
      setError("합성 검토 실행을 시작하지 못했습니다. 로컬 개발 모드와 이전 기록을 확인하세요.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <details className="scanner-jev-motion-details" data-jev-synthetic-only="true">
      <summary>개발용 합성 JEV 테스트 기록 · 실제 종목과 무관</summary>
    <section className="scanner-jev-local-readiness" aria-label="개발 전용 JEV 합성 수동 검토">
      <strong>JEV 수동 검토 체험 · 순수 합성 데이터 (개발 전용)</strong>
      <p><b>{summary[session.status] ?? session.status}</b></p>
      <p>가상 종목 999991만 검토합니다. 현재 선택한 실제 종목과 무관하며, TypeSafe 외부 전송·과금은 0회입니다.</p>
      {session.status === "NOT_REQUESTED" && (
        <>
          <label style={{ display: "block" }}>
            <input type="checkbox" checked={confirmed}
              onChange={event => setConfirmed(event.target.checked)} />
            {" "}실제 종목이 아닌 합성 Mock 검토 1회임을 확인했습니다.
          </label>
          <button type="button" disabled={!confirmed || working} onClick={() => void run()}>
            {working ? "요청 중…" : "합성 JEV 검토 요청"}
          </button>
        </>
      )}
      {finished && (
        <>
          <p>검토 결과: <b>{session.result?.disposition
            ? disposition[session.result.disposition] ?? session.result.disposition
            : "유효한 판정 없음"}</b></p>
          <p>Mock 모델: {session.result?.model_returned ?? "확인 불가"} · 검증: {session.result?.model_identity_status ?? "미확인"}</p>
          <p>실제 API 사용량 0 · 합성 Mock 호출 {session.mock_provider_requests ?? 0}회
            {" "}· 비용 {session.result?.cost_unknown
              ? "청구액 미확정" : "$" + (session.result?.cost_usd ?? 0).toFixed(4)} (Mock)</p>
          {session.result?.failure_code && <p>상태 코드: {session.result.failure_code}</p>}
          <small>검토 ID: {session.result?.review_id ?? "없음"} · 저장 후 다시 조회해도 결과 유지</small>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <small>이 체험은 한 번만 실행되며 새로고침·중복 클릭·서버 재시작으로 추가 요청되지 않습니다.</small>
    </section>
    </details>
  );
}
