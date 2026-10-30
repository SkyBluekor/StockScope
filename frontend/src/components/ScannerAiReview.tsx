import { useEffect, useState } from "react";
import type { ScannerCandidate, ScannerResponse } from "../services/api";
import { getJevEntryRouting, getJevIndependentEventReference, getJevIndependentEventAssessment, getJevLocalReadiness, getJevOutboundPreflight, type JevEntryRouting, type JevIndependentEventReference, type JevIndependentEventAssessment, type JevLocalReadiness, type JevOutboundPreflight, type JevMonitorItem } from "../services/jevApi";
import { scannerAiReviewStatus } from "./scannerAiReviewStatus";
import JevSyntheticDemo from "./JevSyntheticDemo";
import JevEventV5Demo from "./JevEventV5Demo";
import ScannerDartDisclosure from "./ScannerDartDisclosure";
import { getJevEventV5Routing, type JevEventV5Routing, getJevRealEventAudit, type JevRealEventAudit } from "../services/jevApi";

type Props = {
  candidate: ScannerCandidate;
  result: ScannerResponse;
  sampleIndex: number;
  enabled: boolean;
  available: boolean;
  featureStatus: string | null;
  review: JevMonitorItem | null;
  loading: boolean;
  loadError: string | null;
  onRefresh: () => void;
};

function ScannerAiDiagnostics({
  candidate, result, sampleIndex, enabled, available, featureStatus,
  review, loading, loadError, onRefresh,
}: Props) {
  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const items = review?.reason_codes.slice(0, 3) ?? [];
  const captureId = result.prospective_capture?.canonical_capture_id
    || result.prospective_capture?.capture_id || null;
  const [realAudit, setRealAudit] = useState<JevRealEventAudit | null>(null);
  const [realAuditError, setRealAuditError] = useState(false);
  useEffect(() => {
    let active = true;
    setRealAudit(null);
    setRealAuditError(false);
    if (!captureId) return () => { active = false; };
    void getJevRealEventAudit(captureId).then(value => {
      if (!active) return;
      if (value.capture_id !== captureId || value.read_only !== true
          || value.real_market_model_calls !== 0 || value.db_writes !== 0) {
        setRealAuditError(true);
        return;
      }
      setRealAudit(value);
    }).catch(() => { if (active) setRealAuditError(true); });
    return () => { active = false; };
  }, [captureId]);
  const realAuditSummary = !captureId ? "저장된 캡처 없음"
    : realAuditError ? "읽기 전용 DB 진단 실패 · DB 경로 확인 필요"
    : !realAudit ? "기존 EventEvidence DB 점검 중"
    : !realAudit.store.schema_ready ? "이벤트 저장 구조 미준비 (" + realAudit.store.status + ")"
    : realAudit.store.stored_counts_not_asof.source_refs === 0
      ? "저장된 원천 이벤트 자료 0건 · 데이터 수집 경로 점검 필요"
    : "저장된 원천 참조 " + realAudit.store.stored_counts_not_asof.source_refs
      + "건 · 캡처 후보의 시점 내 참고 근거 "
      + realAudit.rows.filter(item => item.reference_status === "EVIDENCE_UNCERTAIN").length
      + "/" + realAudit.entry_count + "건";
  const [batch, setBatch] = useState<JevEntryRouting | null>(null);
  const [batchError, setBatchError] = useState(false);
  useEffect(() => {
    let active = true;
    setBatch(null);
    setBatchError(false);
    if (!captureId) return () => { active = false; };
    void getJevEntryRouting(captureId).then(value => {
      if (!active) return;
      // Never display a different canonical snapshot as this selected result.
      if (value.canonical_capture_id !== captureId || !value.read_only
        || value.external_model_call_allowed !== false) {
        setBatchError(true);
        return;
      }
      setBatch(value);
    }).catch(() => { if (active) setBatchError(true); });
    return () => { active = false; };
  }, [captureId]);
  const matchedRouting = batch?.rows.find(item =>
    item.sample_index === sampleIndex
    && item.market === candidate.market
    && item.ticker === candidate.code
  ) ?? null;
  const [eventReference, setEventReference] = useState<JevIndependentEventReference | null>(null);
  const [eventError, setEventError] = useState(false);
  useEffect(() => {
    let active = true;
    setEventReference(null);
    setEventError(false);
    if (!captureId || sampleIndex < 0) return () => { active = false; };
    void getJevIndependentEventReference(captureId, sampleIndex)
      .then(value => {
        if (!active) return;
        if (value.capture_id !== captureId || value.sample_index !== sampleIndex
            || value.market !== candidate.market || value.ticker !== candidate.code
            || value.external_model_call_allowed !== false
            || value.model_review_executed !== false) {
          setEventError(true);
          return;
        }
        setEventReference(value);
      })
      .catch(() => { if (active) setEventError(true); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const eventIdentityValid = eventReference
    && (!matchedRouting || matchedRouting.snapshot_hash === eventReference.snapshot_hash);
  const eventSummary = !captureId ? "저장된 캡처가 없어 확인 불가"
    : eventError ? "독립 근거 조회 실패"
    : eventReference && !eventIdentityValid ? "이 후보의 원본 해시와 일치하지 않음"
    : !eventReference ? "독립 근거 확인 중"
    : eventReference.status === "NO_INDEPENDENT_EVIDENCE"
      ? "캡처 시점까지 확인된 독립 이벤트 근거 없음"
      : eventReference.status === "EVIDENCE_UNCERTAIN"
        ? "이벤트 참고 근거 " + eventReference.reference_count + "건 · 전략 충돌 여부 미판정"
        : "이벤트 근거 확인 불가 · 출처 또는 시점 점검 필요";
  const [assessment, setAssessment] = useState<JevIndependentEventAssessment | null>(null);
  const [assessmentError, setAssessmentError] = useState(false);
  useEffect(() => {
    let active = true;
    setAssessment(null);
    setAssessmentError(false);
    if (!captureId || sampleIndex < 0) return () => { active = false; };
    void getJevIndependentEventAssessment(captureId, sampleIndex)
      .then(value => {
        if (!active) return;
        if (value.capture_id !== captureId || value.sample_index !== sampleIndex
          || value.market !== candidate.market || value.ticker !== candidate.code
          || value.model_review_executed !== false
          || value.external_model_call_allowed !== false) {
          setAssessmentError(true);
          return;
        }
        setAssessment(value);
      })
      .catch(() => { if (active) setAssessmentError(true); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const assessmentMatches = assessment
    && (!matchedRouting || matchedRouting.snapshot_hash === assessment.snapshot_hash)
    && (!eventReference || eventReference.snapshot_hash === assessment.snapshot_hash);
  const assessmentSummary = !captureId ? "저장 캡처 없음"
    : assessmentError ? "검토 상태 조회 실패"
    : assessment && !assessmentMatches ? "후보 원본 해시 불일치 · 표시 차단"
    : !assessment ? "검토 상태 확인 중"
    : assessment.status === "EVIDENCE_CONFLICT"
      ? "로컬 검토된 충돌 주장 · 사용자 확인 필요"
    : assessment.status === "EVIDENCE_COMPATIBLE"
      ? "로컬 검토된 양립 주장 · 실제 모델 검토 아님"
    : assessment.status === "EVIDENCE_UNCERTAIN"
      ? "의미 관계 미확정 · " + (assessment.independent_review_candidate ? "추가 검토 후보" : "확인 가능한 검토 주장 없음")
    : assessment.status === "NO_INDEPENDENT_EVIDENCE"
      ? "확인된 이벤트 근거 없음"
    : "이벤트 판정 불가 · 신원·시점·이용권 점검 필요";
  const [eventV5, setEventV5] = useState<JevEventV5Routing | null>(null);
  const [eventV5Error, setEventV5Error] = useState(false);
  useEffect(() => {
    let active = true;
    setEventV5(null);
    setEventV5Error(false);
    if (!captureId || sampleIndex < 0) return () => { active = false; };
    void getJevEventV5Routing(captureId, sampleIndex).then(value => {
      if (!active) return;
      if (value.capture_id !== captureId || value.sample_index !== sampleIndex
        || value.market !== candidate.market || value.ticker !== candidate.code
        || value.external_model_call_allowed !== false
        || value.model_review_executed !== false || value.model_result !== null) {
        setEventV5Error(true);
        return;
      }
      setEventV5(value);
    }).catch(() => { if (active) setEventV5Error(true); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const eventV5IdentityValid = eventV5
    && (!matchedRouting || matchedRouting.snapshot_hash === eventV5.snapshot_hash)
    && (!assessment || assessment.snapshot_hash === eventV5.snapshot_hash);
  const eventV5Text: Record<string, string> = {
    SKIPPED_NO_EVIDENCE: "참고 이벤트 없음 · 추가 호출 생략",
    SKIPPED_LOCALLY_RESOLVED: "로컬에서 의미 확인 완료 · 추가 호출 생략",
    LOCAL_REVIEW_REQUIRED: "로컬 충돌 주장 · 사용자 재확인 우선",
    BLOCKED_EVIDENCE: "원본 이벤트 근거 부족 · 요청 차단",
    REVIEW_CANDIDATE_PROVIDER_HOLD: "추가 검토 후보 · 실제 외부 데이터 사용권 확인 전",
    BLOCKED_NOT_REVIEW_CANDIDATE: "승인된 미해결 주장 없음 · 검토 대상 아님",
  };
  const eventV5Summary = eventV5Error ? "V5 적격성 조회 실패"
    : eventV5 && !eventV5IdentityValid ? "원본 불일치 · V5 상태 표시 차단"
    : !eventV5 ? "V5 검토 상태 확인 중"
    : eventV5Text[eventV5.routing] ?? "V5 검토 상태 불명";
  const routeExplanation: Record<string, string> = {
    LOCAL_MATCH: "의미 조건 일치 · JEV 추가 검토 불필요",
    LOCAL_CONFLICT: "로컬 의미 충돌 · 조건 근거 확인",
    LOCAL_INCOMPLETE: "의미 증거 부족 · 모델 검토 보류",
    LOCAL_AMBIGUOUS: "의미 해석 불명확 · 모델 검토 보류",
    RESIDUAL_READY: "JEV 추가 판단 대상 · 실제 전송 권한 확인 전",
    RESIDUAL_BLOCKED: "JEV 추가 판단 대상이지만 입력 증거 부족",
    BLOCKED_EVIDENCE: "로컬 V4 또는 원본 무결성 증거 부족",
  };
  const [readiness, setReadiness] = useState<JevLocalReadiness | null>(null);
  const [outbound, setOutbound] = useState<JevOutboundPreflight | null>(null);
  const [outboundError, setOutboundError] = useState<string | null>(null);
  const [outboundLoading, setOutboundLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setOutbound(null);
    setOutboundError(null);
    if (!captureId || sampleIndex < 0) {
      setOutboundLoading(false);
      return () => { active = false; };
    }
    setOutboundLoading(true);
    void getJevOutboundPreflight(captureId, sampleIndex)
      .then(value => {
        if (!active) return;
        if (value.capture_id !== captureId || value.sample_index !== sampleIndex
          || value.market !== candidate.market || value.ticker !== candidate.code) {
          setOutboundError("외부 전송 검사 결과가 현재 후보와 일치하지 않아 표시하지 않습니다.");
        } else {
          setOutbound(value);
        }
      })
      .catch(() => { if (active) setOutboundError("외부 전송 근거를 조회할 수 없습니다."); })
      .finally(() => { if (active) setOutboundLoading(false); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setReadiness(null);
    setReadinessError(null);
    if (!captureId || sampleIndex < 0) {
      setReadinessLoading(false);
      return () => { active = false; };
    }
    setReadinessLoading(true);
    void getJevLocalReadiness(captureId, sampleIndex)
      .then(value => {
        if (!active) return;
        if (value.capture_id !== captureId || value.sample_index !== sampleIndex
            || value.identity.market !== candidate.market
            || value.identity.ticker !== candidate.code) {
          setReadinessError("저장 캡처와 선택 종목의 식별 정보가 다릅니다. 다른 후보 결과를 표시하지 않습니다.");
          return;
        }
        setReadiness(value);
      })
      .catch(() => { if (active) setReadinessError("로컬 준비도를 확인하지 못했습니다. 저장 캡처와 DB 상태를 확인하세요."); })
      .finally(() => { if (active) setReadinessLoading(false); });
    return () => { active = false; };
  }, [captureId, sampleIndex, candidate.market, candidate.code]);
  const readinessLabel: Record<string, string> = {
    LOCAL_READY: "로컬 V4 입력 준비",
    LOCAL_ONLY: "로컬 검토만 가능",
    NEEDS_EVIDENCE: "입력 근거 확인 필요",
    SOURCE_RIGHTS_HOLD: "외부 전송 권한 확인 전까지 보류",
    NOT_ENTRY_CANDIDATE: "진입 후보가 아닌 참고 항목",
  };
  const reasonLabel: Record<string, string> = {
    SOURCE_RIGHTS_UNVERIFIED: "실제 데이터 외부 제공 권한이 확인되지 않았습니다.",
    SOURCE_RELEASE_TIME_UNVERIFIED: "원천 데이터의 최초 공개 시점이 검증되지 않았습니다.",
    SOURCE_ORIGIN_UNVERIFIED: "실제 데이터 원천을 확정하지 못했습니다.",
    REVISION_ASOF_UNPROVEN: "당시 사용한 원천 데이터 버전을 입증하지 못했습니다.",
    TYPESAFE_ACCOUNT_POLICY_UNVERIFIED: "수신자 계정의 처리·보관 조건이 확인되지 않았습니다.",
    OUTBOUND_BODY_NOT_APPROVED: "전송할 실제 요청 본문은 승인되지 않았습니다.",
    NOT_ENTRY_CANDIDATE: "기존 Scanner의 진입 후보가 아닙니다.",
    S7_4_LINEAGE_NOT_COMPLETE: "기초 데이터의 출처 연결이 충분하지 않습니다.",
  };
  const contract = readiness?.input_contract;
  const localSummary = matchedRouting?.routing === "LOCAL_MATCH"
    ? "의미 분석 일치 · 모델 검토 불필요"
    : matchedRouting?.routing === "LOCAL_CONFLICT"
      ? "의미 조건 충돌 · 검토 근거 확인"
      : matchedRouting?.routing === "LOCAL_INCOMPLETE"
        ? "의미 증거 부족 · 로컬 검토 미완료"
        : matchedRouting?.routing === "LOCAL_AMBIGUOUS"
          ? "의미 판단 불명확 · 로컬 검토 미완료"
          : matchedRouting?.routing === "RESIDUAL_READY"
            ? "V4 구조 입력 준비 · 실제 시장 외부 검토는 보류"
            : matchedRouting?.routing === "RESIDUAL_BLOCKED"
              ? "추가 검토 필요 · V4 입력/무결성 증거 부족"
    : readinessError
    ? "후보 신원 검증 실패 · 결과 표시 차단"
    : readinessLoading ? "로컬 입력 확인 중"
    : !readiness ? "저장 캡처 확인 필요"
    : readiness.local_v4_status === "BLOCKED_HORIZON"
      ? "평가 기간 지정 없음 · 원본을 임의 수정하지 않음"
    : readiness.local_v4_status === "LOCAL_V4_PROJECTABLE"
      ? "V4 입력 형식 준비 · 외부 전송 승인과 별개"
    : readiness.local_v4_status === "SKIPPED_LOCAL"
      ? "로컬 의미 검토만 가능"
    : "V4 입력 근거 확인 필요";
  const strategySummary = contract?.original_strategy_identity === "CAPTURED_ORIGINAL"
    ? "원본 전략 신원 확인"
    : contract?.original_strategy_identity === "LEGACY_DERIVED_NOT_ORIGINAL"
      ? "레거시 유도 전략 · 원본 신원 아님"
      : "원본 전략 신원 미확인";
  const policySummary = contract?.horizon_support_status === "EVALUATION_PENDING"
    ? "기간 수치 정책 승인 전"
    : contract?.horizon_support_status === "LEGACY_UNSPECIFIED"
      ? "평가 기간 기록 없음"
      : contract?.horizon_support_status === "UNSUPPORTED"
        ? "평가 기간 정책 미지원"
        : contract?.horizon_support_status === "SUPPORTED"
          ? "평가 기간 정책 확인됨"
          : "평가 기간 상태 확인 필요";
  const outboundSummary = outboundError
    ? "전송 자격 조회 실패 · 요청 차단"
    : outboundLoading ? "외부 전송 자격 확인 중"
    : outbound?.decision === "HOLD" ? "외부 제공 권한 미확인 · 전송 보류"
    : outbound?.decision === "NOT_APPLICABLE" ? "검토 대상 아님"
    : outbound?.decision === "DENY" ? "외부 전송 금지"
    : "전송 승인 없음";
  const verifiedModel = state.source === "STORED_JEV";
  const modelRunning = state.state === "RUNNING"
    && review?.operational_status === "RUNNING" && Boolean(review?.review_id);
  const tone = verifiedModel ? "verified" : modelRunning ? "working"
    : state.state === "FAILED" || state.state === "FEATURE_ERROR" ? "error"
      : state.state === "INPUT_MISSING" || state.state === "ABSTAIN" ? "review" : "idle";
  const sourceSummary = verifiedModel ? "저장된 실제 AI 검토"
    : modelRunning ? "실제 AI 검토 실행 중"
      : candidate.ai_review_presentation?.state === "LOCAL_COMPLETE"
        ? "기본 근거 확인 완료 · AI 모델 미실행"
        : "기본 분석과 별개의 AI 검토";
  return (
    <section className="scanner-jev-review" aria-label="JEV 개발자 상세 진단">
      <div className={"scanner-jev-motion-status " + tone + (modelRunning ? " is-running" : "")} data-review-state={state.state} role="status">
        <span className="scanner-jev-motion-icon" aria-hidden="true">{verifiedModel ? "✓" : modelRunning ? "·" : "i"}</span>
        <div>
          <small>{sourceSummary}</small>
          <strong>{loading ? "저장된 검토 확인 중" : loadError ? "AI 검토 기록 확인 실패" : state.label}</strong>
          <p>{loading ? "종목과 분석 시점에 연결된 검토 기록을 확인하고 있어요." : loadError ?? state.detail}</p>
        </div>
      </div>
      <div className="scanner-jev-local-readiness" data-jev-real-summary="live-04r">
        <strong>선택 종목 · {candidate.name ?? candidate.code} ({candidate.code})</strong>
        <p>기존 Scanner 판단 유지 · AI 추가 검토는 별도 판단입니다.</p>
        <p><b>로컬 입력:</b> {localSummary}</p>
        {batch && (
          <p data-jev-entry-summary="p5">
            <b>이 분석의 진입 후보:</b> {batch.entry_count}개 · 의미 일치 {batch.counts.LOCAL_MATCH}개
            {" · "}충돌 {batch.counts.LOCAL_CONFLICT}개
            {" · "}모델 추가 판단 필요 {batch.counts.RESIDUAL_READY + batch.counts.RESIDUAL_BLOCKED}개
            {" · "}근거 부족 {batch.counts.LOCAL_INCOMPLETE + batch.counts.LOCAL_AMBIGUOUS + batch.counts.BLOCKED_EVIDENCE}개
          </p>
        )}
        {matchedRouting && (
          <p data-jev-entry-route={matchedRouting.routing}>
            <b>이 후보의 분기:</b> {routeExplanation[matchedRouting.routing] ?? "검토 상태 확인 필요"}
          </p>
        )}
        {batchError && <small>진입 후보 전체 분류를 불러오지 못했습니다. 기존 Scanner 판단은 그대로 유지됩니다.</small>}
        <p data-jev-real-event-inventory="p6d"><b>실제 이벤트 저장 현황:</b> {realAuditSummary}</p>
        <ScannerDartDisclosure key={candidate.market + ":" + candidate.code} ticker={candidate.code} market={candidate.market} />
        <p data-jev-independent-event="p6a"><b>독립 뉴스·공시 근거:</b> {eventSummary}</p>
        <p data-jev-event-assessment="p6b"><b>이벤트 의미 판정:</b> {assessmentSummary}</p>
        <p data-jev-event-v5="p6c"><b>JEV V5:</b> {eventV5Summary} · 모델 미실행</p>
        {assessmentMatches && assessment && assessment.approved_assertion_count > 0 && (
          <details>
            <summary>검토 주장·시점 보기</summary>
            <p>검토된 이벤트 {assessment.reviewed_event_count}건 · 사후 작성으로 제외 {assessment.retrospective_assertion_count}건</p>
            <p>판정: {assessment.assertion_status} · 사유: {assessment.reason_codes.slice(0, 5).join(", ") || "없음"}</p>
            {assessment.reviewed_assertion_refs.map(item => (
              <p key={item.assertion_hash}>
                사건 {item.event_id} · revision {item.event_version} · 개념 {item.claim_id} · {item.relation}
                {" · "}승인 {item.approved_at} · 출처 {item.source_ref_id}
                <small>품질 SHA-256: {item.quality_hash} · 출처 SHA-256: {item.source_ref_hash}</small>
              </p>
            ))}
            <small>운영자 로컬 검토 기록입니다. 제3자 검증이나 JEV 실행을 증명하지 않으며, 외부 전송은 보류 상태입니다.</small>
          </details>
        )}
        {eventIdentityValid && eventReference?.status === "EVIDENCE_UNCERTAIN" && (
          <small>캡처 생성 시각 기준 저장된 참고 자료입니다. 전략의 반대 근거나 실제 JEV 검토 결과로 확정하지 않습니다. 외부 AI 사용 권한은 미승인입니다.</small>
        )}
        <p><b>전략:</b> {strategySummary} · <b>기간:</b> {policySummary}</p>
        <p><b>외부 TypeSafe:</b> {outboundSummary}</p>
        <button type="button" disabled
          title={matchedRouting?.routing === "LOCAL_MATCH"
            ? "로컬 의미 조건이 일치하여 잔여 의미 검토 대상이 아닙니다."
            : "실제 시장 데이터의 외부 전송 이용권과 실행 승인이 확인되지 않았습니다."}>
          {matchedRouting?.routing === "LOCAL_MATCH"
            ? "로컬 검토 완료 · JEV 호출 불필요"
            : matchedRouting?.routing === "LOCAL_CONFLICT"
              ? "로컬 충돌 확인 · 조건 재검토 필요"
              : matchedRouting?.routing === "RESIDUAL_READY"
                ? "JEV 추가 판단 대상 · 외부 검토 보류"
                : matchedRouting?.routing === "LOCAL_INCOMPLETE" || matchedRouting?.routing === "LOCAL_AMBIGUOUS"
                  ? "추가 근거 확인 전 · 모델 검토 불가"
                  : "실제 종목 JEV 추가 검토 (현재 사용 불가)"}
        </button>
        <small>저장된 실모델 검토가 없는 경우 AI 의견은 생성되지 않았습니다. 이 조회는 추가 모델 요청을 하지 않습니다.</small>
      </div>
      <JevSyntheticDemo />
      <JevEventV5Demo />
      <details className="scanner-jev-motion-details">
        <summary>로컬 입력 준비도와 외부 전송 차단 근거 자세히 보기</summary>
      <div className="scanner-jev-local-readiness" role="status" data-local-readiness={readiness?.status ?? "UNAVAILABLE"}>
        <strong>이 후보의 JEV 실행 준비도 · 로컬 읽기 전용</strong>
        {!captureId ? <p>확정된 COMPLETE 저장 캡처가 없어 후보별 준비도를 확인할 수 없습니다.</p>
          : readinessLoading ? <p>저장된 후보의 근거와 권한 상태를 확인 중입니다.</p>
            : readinessError ? <p>{readinessError}</p>
              : readiness ? (
                <>
                  <p><b>{readinessLabel[readiness.status] ?? readiness.status}</b> · {readinessLabel[readiness.local_readiness] ?? readiness.local_readiness}</p>
                  <p>{readiness.transmission_decision === "NO_GO"
                    ? "실제 TypeSafe 전송: 금지 (SOURCE_RIGHTS_HOLD)"
                    : "이 후보는 현 단계에서 TypeSafe 호출 대상이 아닙니다."} · 이 조회에서 모델 요청 0회</p>
                  <p>원본 신원 확인 · 순위 {readiness.baseline_checks.rank.status} / 전략 {readiness.baseline_checks.strategy.status} / Risk {readiness.baseline_checks.risk.status} / 정책 {readiness.baseline_checks.policy.status}</p>
                  <details>
                    <summary>미실행 사유와 검사 근거</summary>
                    <p>V4 상태: {readiness.local_v4_status} · 출처 연결: {readiness.lineage_analysis_status}</p>
                    <p>원천 공개 시각: {readiness.publication_time_status} · 사용 권한: {readiness.rights_status}</p>
                    <p>Horizon 원본: {readiness.input_contract.horizon_intent ?? "미지정"} · 정책 버전: {readiness.input_contract.horizon_policy_version ?? "미확인"} · 상태: {readiness.input_contract.horizon_support_status}</p>
                    <p>전략 신원: {readiness.input_contract.original_strategy_identity} · 원천 공개 시각: 검증되지 않음</p>
                    <p>캡처 생성: {readiness.input_contract.capture_created_at ?? "미확인"} · 시작: {readiness.input_contract.capture_started_at ?? "미확인"} · 완료: {readiness.input_contract.capture_completed_at ?? "미확인"}</p>
                    <small>캡처 자체 시각은 원천 데이터 공개·최초 확보 시각을 증명하지 않습니다.</small>
                    {readiness.reason_codes.length > 0
                      ? <ul>{readiness.reason_codes.slice(0, 8).map(code => <li key={code}>{reasonLabel[code] ?? code} ({code})</li>)}</ul>
                      : <p>추가 사유 코드가 없습니다.</p>}
                    <small>캡처 해시: {readiness.identity.snapshot_hash}</small>
                  </details>
                </>
              ) : <p>로컬 준비도 결과 없음</p>}
      </div>
      <div className="scanner-jev-local-readiness" data-outbound-gate="live-03">
        <strong>실제 데이터의 외부 AI 전송 자격 · LIVE-03</strong>
        {!captureId ? <p>저장된 캡처가 없어 외부 전송 검사를 수행할 수 없습니다.</p>
          : outboundLoading ? <p>로컬 필드·권한·전송 본문 검사 중…</p>
            : outboundError ? <p role="alert">{outboundError}</p>
              : outbound ? (
                <>
                  <p><b>외부 전송 {outbound.decision === "HOLD" ? "보류" : outbound.decision === "NOT_APPLICABLE" ? "비대상" : "차단"}</b> · 실제 JEV 모델 호출 없음</p>
                  <p>{outbound.wire_ready
                    ? "V4 요청 형식·바이트 지문을 로컬에서 확인했습니다. 전송 권한을 의미하지 않습니다."
                    : "검토 입력 또는 권한 근거가 부족하여 요청 본문은 생성하지 않았습니다."}</p>
                  <details>
                    <summary>전송 권한·데이터 시점 근거</summary>
                    <p>실행 권한: {outbound.execution_status} · 공급자: {outbound.recipient}</p>
                    <p>원천 시각 진위: {outbound.time_authenticity} · 계정 권한 검증: {outbound.trusted_rights_resolver}</p>
                    {outbound.wire_audit && (
                      <p>전송 예정 필드 {outbound.wire_audit.field_count}개 · 본문 {outbound.wire_audit.http_body_bytes}바이트 · SHA-256 {outbound.wire_audit.http_body_sha256}</p>
                    )}
                    {outbound.reason_codes.length > 0 && (
                      <ul>{outbound.reason_codes.slice(0, 8).map(code => <li key={code}>{reasonLabel[code] ?? code}</li>)}</ul>
                    )}
                  </details>
                </>
              ) : <p>외부 전송 검사 미실행</p>}
      </div>
      </details>
      <details className="scanner-jev-motion-details">
        <summary>검토 출처와 근거 자세히 보기</summary>
        <dl>
        <div><dt>검토 결과</dt><dd>{loading || loadError ? "확인할 수 없음" : state.outcome}</dd></div>
        <div><dt>검토 출처</dt><dd>{!loading && !loadError && state.source === "STORED_JEV" ? "검증된 Jev 저장 결과" : state.source === "LOCAL" ? "로컬 의미 점검 · 모델 미실행" : "유효한 모델 결과 없음"}</dd></div>
        <div><dt>기본 분석</dt><dd>유지 · Scanner 순위와 Risk 계산은 변경하지 않음</dd></div>
        <div><dt>분석 기준</dt><dd>{candidate.data_date || "확인 필요"} · {candidate.market} {candidate.code}</dd></div>
        {!loading && !loadError && review?.completed_at && state.source === "STORED_JEV" && (
          <div><dt>검토 저장 시점</dt><dd>{review.completed_at}</dd></div>
        )}
        </dl>
      </details>
      {!loading && !loadError && state.source === "STORED_JEV" && (
        <>
          <strong>추가 확인 항목 · 최대 3개</strong>
          {items.length > 0 ? <ul>{items.map(code => <li key={code}>{code}</li>)}</ul>
            : <p>저장된 검토에 별도의 추가 확인 코드가 없어요.</p>}
          <small>검토 코드는 응답에 저장된 값이며, 코드에 없는 원인을 추측하지 않아요.</small>
          <p>연결 근거: 분석 캡처 {captureId} · 검토 기록 {review?.review_id}</p>
        </>
      )}
      {state.source !== "STORED_JEV" && candidate.ai_review_presentation && (
        <details>
          <summary>로컬 의미 점검 보기 (Jev 호출 아님)</summary>
          <p>{candidate.ai_review_presentation.summary}</p>
          {[...candidate.ai_review_presentation.strengths, ...candidate.ai_review_presentation.review_points].slice(0, 3).map((text, index) => <p key={index}>{text}</p>)}
        </details>
      )}
      <p className="scanner-jev-next">{loadError ? "저장된 검토 조회 상태를 확인한 후 다시 시도하세요." : state.next}</p>
      {available && enabled && featureStatus === "ACTIVE" && (
        <button type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "기록 확인 중…" : "저장된 검토 다시 확인"}
        </button>
      )}
      <small>새로운 Jev 모델 호출은 실행하지 않습니다.</small>
    </section>
  );
}
 
/** End-user AI review is intentionally concise. Existing diagnostics are kept
 * behind an explicit developer disclosure and only mount when opened, so
 * browsing Scanner candidates never triggers P5/P6 debug network requests. */
export default function ScannerAiReview(props: Props) {
  const { candidate, result, enabled, available, featureStatus, review, loading, loadError, onRefresh } = props;
  const [developerOpen, setDeveloperOpen] = useState(false);
  const state = scannerAiReviewStatus({ candidate, result, enabled, available, featureStatus, review });
  const hasVerifiedReview = !loading && !loadError && state.source === "STORED_JEV";
  const isRunning = state.state === "RUNNING" || state.state === "QUEUED";
  const isError = Boolean(loadError) || state.state === "FEATURE_ERROR" || state.state === "FAILED" || state.state === "UNKNOWN";
  const tone = hasVerifiedReview ? "verified" : isRunning ? "working" : isError ? "error" : "idle";
  const visibleStatus = loading ? "저장된 JEV 결과 확인 중"
    : loadError ? "저장된 JEV 결과를 확인하지 못했습니다."
    : hasVerifiedReview ? state.outcome
    : isRunning ? state.label
    : state.state === "OFF" ? "사용 안 함"
    : state.state === "FEATURE_PENDING" ? "현재 서버에서 JEV 사용 불가"
    : state.state === "FEATURE_LOADING" ? "JEV 제공 상태 확인 중"
    : isError ? "JEV 결과 확인 불가"
    : state.state === "INPUT_MISSING" ? "검토 입력 부족"
    : "실제 JEV 검토 미실행";
  // A-stage has no live executable review route. Do not advertise a working
  // button based on a local toggle or stored model result.
  const unavailableReason = !available || featureStatus !== "ACTIVE"
    ? "서버에서 실제 검토 기능이 활성화되지 않았습니다."
    : !enabled ? "JEV 사용 설정이 꺼져 있습니다."
    : "현재 실제 종목의 허용된 전송 입력과 실행 승인이 준비되지 않았습니다.";
  return (
    <section className="scanner-jev-review" aria-label="선택 종목 AI 검토 근거" data-jev-a-summary="true">
      <div className="scanner-jev-compact-summary" data-jev-primary-summary="true">
        <strong className="scanner-jev-compact-stock">{candidate.name || candidate.code} ({candidate.code})</strong>
        <dl>
          <div><dt>Scanner 판단</dt><dd>{candidate.action_label || candidate.action}</dd></div>
          <div><dt>JEV 검토</dt><dd data-jev-primary-status={state.state}>{visibleStatus}</dd></div>
          {hasVerifiedReview && review?.completed_at && (
            <div><dt>검토 시각</dt><dd>{review.completed_at}</dd></div>
          )}
        </dl>
        {hasVerifiedReview && review?.reason_codes.length > 0 && (
          <p className="scanner-jev-compact-note">추가 확인 코드: {review.reason_codes.slice(0, 3).join(", ")}</p>
        )}
        <button type="button" disabled title={unavailableReason}>JEV 검토 실행 (사용 불가)</button>
        {hasVerifiedReview && available && enabled && featureStatus === "ACTIVE" && (
          <button type="button" onClick={onRefresh} disabled={loading}>
            {loading ? "결과 확인 중…" : "저장된 결과 새로고침"}
          </button>
        )}
        {!hasVerifiedReview && (
          <small className="scanner-jev-compact-note" data-jev-unavailable-reason="true">
            {isError ? "검토 기록을 확인할 수 없습니다. Scanner 판단은 유지됩니다." : unavailableReason}
          </small>
        )}
      </div>
      <details className="scanner-jev-motion-details scanner-jev-developer-details"
        data-jev-developer-details="true"
        open={developerOpen}
        onToggle={event => setDeveloperOpen(event.currentTarget.open)}>
        <summary>개발자 진단 및 공시 조회</summary>
        {developerOpen && <ScannerAiDiagnostics {...props} />}
      </details>
    </section>
  );
}
