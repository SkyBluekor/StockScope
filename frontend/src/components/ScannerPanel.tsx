import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearScannerSession,
  latestScannerDataDate,
  resolveScannerDataDate,
  localDateKey,
  readScannerSession,
  useScannerSession,
  writeScannerSession,
} from "./scannerSession";
import {
  cancelBacktestJob,
  createScannerJob,
  fetchBacktestJob,
  type BacktestJob,
  type ScannerCandidate,
  type ScannerFreshnessResponse,
  type ScannerResponse,
  type StockSearchItem,
} from "../services/api";
import {
  ANALYSIS_STAGES,
  progressStatusMark,
  scannerProgressView,
} from "./scannerProgress";
import "./scannerProgress.css";

type MarketScope = "ALL" | "KOSPI" | "KOSDAQ";

type Props = {
  onAnalyzeStock: (item: StockSearchItem) => void;
};

const regimeLabel: Record<string, string> = {
  TREND_UP: "상승장",
  RANGE: "횡보장",
  TREND_DOWN: "하락장",
  HIGH_VOLATILITY: "고변동성",
  PANIC: "패닉",
  UNKNOWN: "판단 보류",
};

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const compact = value.replace(/-/g, "");
  if (compact.length !== 8) return value;
  return `${compact.slice(0, 4)}.${compact.slice(4, 6)}.${compact.slice(6, 8)}`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);
}

function formatSignedPct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatElapsed(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  if (safe < 60) return `${safe}초`;
  const minutes = Math.floor(safe / 60);
  const remain = safe % 60;
  return `${minutes}분 ${remain}초`;
}

function formatLocalTime(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function evidenceKey(candidate: ScannerCandidate) {
  return `${candidate.market}-${candidate.code}`;
}

function candidateTone(candidate: ScannerCandidate) {
  if (candidate.candidate_state === "READY") return "ready";
  if (candidate.candidate_state === "WATCH") return "watch";
  if (candidate.candidate_state === "VALIDATION") return "validation";
  return "muted";
}

function conditionStatusLabel(candidate: ScannerCandidate) {
  const { passed, total, missing } = candidate.conditions;
  return `${passed}/${total} 충족 · 부족 ${missing}개`;
}

function candidateKey(candidate: ScannerCandidate) {
  return evidenceKey(candidate);
}

function priceText(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "-" : `${formatNumber(value)}원`;
}

function priceRangeText(low: number | null | undefined, high: number | null | undefined) {
  if (low == null && high == null) return "-";
  if (low != null && high != null) {
    if (Math.abs(low - high) < 0.000001) return priceText(low);
    return `${formatNumber(low)}~${formatNumber(high)}원`;
  }
  return priceText(low ?? high);
}

function interestPriceText(candidate: ScannerCandidate) {
  const rule = candidate.entry_risk_guide?.price_rule;
  if (!rule) return "-";
  if (rule.kind === "RANGE") {
    return priceRangeText(rule.display_range_low ?? rule.range_low, rule.display_range_high ?? rule.range_high);
  }
  const trigger = rule.display_trigger_price ?? rule.trigger_price;
  const reference = rule.display_reference_price ?? rule.reference_price;
  if (rule.kind === "ABOVE" && trigger != null) return `${formatNumber(trigger)}원 이상`;
  if (rule.kind === "AT_OR_BELOW" && trigger != null) return `${formatNumber(trigger)}원 이하`;
  return priceText(trigger ?? reference);
}


function strategyPriceLabel(candidate: ScannerCandidate) {
  const rule = candidate.entry_risk_guide?.price_rule;
  if (!rule) return "전략 가격";
  if (rule.user_label) return rule.user_label;
  if (rule.kind === "RANGE") return "전략 조건 가격대";
  return "전략 조건 기준가";
}

function stopPriceText(candidate: ScannerCandidate) {
  const risk = candidate.entry_risk_guide?.risk;
  return risk ? priceRangeText(risk.display_stop_zone_low ?? risk.stop_zone_low, risk.display_stop_zone_high ?? risk.stop_zone_high) : "-";
}

function targetPriceText(candidate: ScannerCandidate, level: 1 | 2) {
  const risk = candidate.entry_risk_guide?.risk;
  if (!risk) return "-";
  const value = level === 1
    ? (risk.display_target1_price ?? risk.target1_price)
    : (risk.display_target2_price ?? risk.target2_price);
  return priceText(value);
}

function targetBasisLabel(candidate: ScannerCandidate) {
  const risk = candidate.entry_risk_guide?.risk;
  const audit = risk?.target1_audit;
  if (risk?.target1_cap_applied === true || audit?.target1_cap_applied === true) return "1.5R";
  const raw = String(audit?.target1_basis ?? risk?.target1_basis ?? "");
  if (raw.includes("저항")) return "최근 저항";
  if (raw.includes("20일") && raw.includes("고점")) return "20일 고점";
  if (raw.includes("1.5R")) return "1.5R";
  return raw || "근거 확인";
}

function targetGainPct(candidate: ScannerCandidate) {
  const risk = candidate.entry_risk_guide?.risk;
  const audited = risk?.target1_audit?.target1_gain_pct;
  if (audited != null && Number.isFinite(audited)) return audited;
  const target = risk?.target1_price;
  const current = candidate.current_price;
  if (target == null || current == null || !Number.isFinite(target) || !Number.isFinite(current) || current <= 0) return null;
  return (target / current - 1) * 100;
}

function targetRMultiple(candidate: ScannerCandidate) {
  const risk = candidate.entry_risk_guide?.risk;
  const value = risk?.target1_audit?.target1_r_multiple ?? risk?.rr1;
  return value != null && Number.isFinite(value) ? value : null;
}

function targetCapExplanation(candidate: ScannerCandidate) {
  const risk = candidate.entry_risk_guide?.risk;
  const audit = risk?.target1_audit;
  const capApplied = risk?.target1_cap_applied === true || audit?.target1_cap_applied === true;
  const structuralRaw = risk?.structural_target1_price ?? audit?.structural_target1_price;
  if (!capApplied || structuralRaw == null) return null;

  const structuralPrice = risk?.display_structural_target1_price ?? structuralRaw;
  const structuralBasis = String(risk?.structural_target1_basis ?? audit?.structural_target1_basis ?? "").trim();
  return {
    capLabel: "1.5R 현실성 상한 적용",
    structuralLabel: `구조 목표 ${priceText(structuralPrice)}${structuralBasis ? ` · ${structuralBasis}` : ""}`,
  };
}

function evidenceCompactText(candidate: ScannerCandidate) {
  const evidence = candidate.historical_evidence;
  if (!evidence?.verified) return evidence?.label ?? candidate.historical_fit.label;
  const average = formatSignedPct(evidence.average_net_return_pct);
  return `최근 3년 · ${evidence.sample_count}회 · 평균 ${average}`;
}

function emptyCandidateMessage(result: ScannerResponse, noAnalyzedData: boolean) {
  if (noAnalyzedData) {
    return "최근 기술지표 계산에 필요한 시장 데이터가 아직 충분하지 않습니다. 위의 ‘시장 데이터 준비’를 실행한 뒤 다시 확인하세요.";
  }
  const raw = String(result.empty_message ?? "").trim();
  if (!raw || /\bNO[_ -]?TRADE\b/i.test(raw)) {
    return "현재 확정 일봉 기준으로 10개 전략의 진입 조건을 충분히 만족한 종목이 없습니다. 조건을 억지로 완화하지 않고 다음 확정 일봉에서 다시 확인합니다.";
  }
  return raw;
}

function CandidateCompareRow({
  candidate,
  rank,
  selected,
  onSelect,
}: {
  candidate: ScannerCandidate;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const tone = candidateTone(candidate);
  return (
    <button
      type="button"
      className={`scanner-compare-row tone-${tone} ${selected ? "selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="scanner-compare-rank" aria-label={`후보 우선순위 ${rank}`}>{rank}</span>
      <span className="scanner-compare-stock">
        <strong>{candidate.name}</strong>
        <small>{candidate.market} · {candidate.strategy_easy_name}</small>
      </span>
      <span className="scanner-compare-judgement">
        <strong>{candidate.action_label}</strong>
        <small>{candidate.candidate_label} · {conditionStatusLabel(candidate)}</small>
      </span>
      <span className="scanner-compare-metrics">
        <span className="scanner-compare-metric current">
          <small>현재가</small>
          <strong>{priceText(candidate.current_price)}</strong>
        </span>
        <span className="scanner-compare-metric entry">
          <small>{strategyPriceLabel(candidate)}</small>
          <strong>{interestPriceText(candidate)}</strong>
        </span>
        <span className="scanner-compare-metric stop">
          <small>손절 참고구간</small>
          <strong>{stopPriceText(candidate)}</strong>
        </span>
        <span className="scanner-compare-metric target scanner-target-cell">
          <small>1차 목표</small>
          <strong>{targetPriceText(candidate, 1)}</strong>
          <em>{targetGainPct(candidate) == null ? "-" : `현재가 대비 ${formatSignedPct(targetGainPct(candidate))}`}</em>
        </span>
      </span>
      <span className="scanner-compare-arrow" aria-hidden="true">›</span>
    </button>
  );
}

function CandidateDetail({
  candidate,
  rank,
  onAnalyze,
  evidenceOpen,
  onEvidenceToggle,
}: {
  candidate: ScannerCandidate;
  rank: number;
  onAnalyze: () => void;
  evidenceOpen: boolean;
  onEvidenceToggle: (open: boolean) => void;
}) {
  const tone = candidateTone(candidate);
  const topMissing = candidate.conditions.top_missing ?? [];
  const evidence = candidate.historical_evidence;
  const evidenceLabel = evidence?.label ?? (candidate.historical_fit.verified === false ? "과거 검증 전" : candidate.historical_fit.label);
  const evidenceSummary = evidence?.summary ?? candidate.historical_fit.summary;
  const targetCap = targetCapExplanation(candidate);
  const changeSummary = candidate.user_action.next_transition
    || (topMissing.length > 0 ? topMissing.slice(0, 2).map((item) => item.label).join(" · ") : "현재 조건이 유지되는지 확인하세요.");

  return (
    <article className={`scanner-selected-detail tone-${tone}`}>
      <header className="scanner-selected-head">
        <div>
          <span className="scanner-selected-kicker">선택한 후보 · 우선순위 {rank}</span>
          <div className="scanner-stock-line">
            <h3>{candidate.name}</h3>
            <span>{candidate.market} · {candidate.code}</span>
          </div>
          <div className="scanner-selected-tags">
            <span className={`scanner-state-badge ${tone}`}>{candidate.candidate_label}</span>
            <span>{candidate.strategy_easy_name}</span>
            <span>{evidenceCompactText(candidate)}</span>
          </div>
        </div>
        <div className="scanner-selected-price">
          <small>기준 종가</small>
          <strong>{priceText(candidate.current_price)}</strong>
          <span>{formatDate(candidate.data_date)} 확정 일봉</span>
        </div>
      </header>

      <section className="scanner-detail-summary-grid">
        <div>
          <small>현재 판단</small>
          <strong>{candidate.action_label}</strong>
          <p>{candidate.headline}</p>
        </div>
        <div>
          <small>왜 후보인가</small>
          <strong>{candidate.priority?.label ?? candidate.strategy_easy_name}</strong>
          <p>{candidate.priority?.reason ?? candidate.reason}</p>
        </div>
        <div>
          <small>판단이 바뀌는 조건</small>
          <strong>{conditionStatusLabel(candidate)}</strong>
          <p>{changeSummary}</p>
        </div>
      </section>

      <section className="scanner-decision-price-band" aria-label="핵심 가격 기준">
        <div><small>현재가</small><strong>{priceText(candidate.current_price)}</strong></div>
        <div><small>{strategyPriceLabel(candidate)}</small><strong>{interestPriceText(candidate)}</strong></div>
        <div className="stop"><small>손절 참고구간</small><strong>{stopPriceText(candidate)}</strong></div>
        <div className="target">
          <small>1차 목표 · {targetBasisLabel(candidate)}</small>
          <strong>{targetPriceText(candidate, 1)}</strong>
          <span>
            {targetGainPct(candidate) == null ? "거리 계산 불가" : `현재가 대비 ${formatSignedPct(targetGainPct(candidate))}`}
            {targetRMultiple(candidate) == null ? "" : ` · ${targetRMultiple(candidate)!.toFixed(2)}R`}
          </span>
          {targetCap && (
            <>
              <span>{targetCap.capLabel}</span>
              <span>{targetCap.structuralLabel}</span>
            </>
          )}
        </div>
        <div><small>2차 목표</small><strong>{targetPriceText(candidate, 2)}</strong></div>
      </section>

      {candidate.entry_risk_guide?.price_consistency && candidate.entry_risk_guide.price_consistency.status !== "NOT_APPLICABLE" && (() => {
        const consistency = candidate.entry_risk_guide!.price_consistency!;
        const semanticContext = consistency.classification === "STRATEGY_CONDITION_BAND_OVERLAP" || consistency.classification === "DISPLAY_ROUNDING_TOUCH";
        const tone = consistency.status === "INVALID" ? "invalid" : consistency.status === "WARNING" ? "warning" : semanticContext ? "context" : "ok";
        const title = consistency.status === "INVALID" || consistency.status === "WARNING" ? "가격 계획 확인" : semanticContext ? "가격 기준 구분" : "가격 관계";
        return (
        <section className={`scanner-price-consistency ${tone}`}>
          <div>
            <strong>{title}</strong>
            <span>{consistency.status === "OK"
              ? (consistency.relation_message ?? consistency.message)
              : consistency.message}</span>
          </div>
          <div className="scanner-price-invalidation-inline">
            <small>전략 무효화 기준</small>
            <strong>{priceText(candidate.entry_risk_guide.risk.display_invalidation_price ?? candidate.entry_risk_guide.risk.invalidation_price)}</strong>
            <span>손절 참고구간과 별개의 전략 전제 기준</span>
          </div>
        </section>
        );
      })()}

      <section className="scanner-selected-strategy">
        <div>
          <small>현재 가장 맞는 방법</small>
          <strong>{candidate.strategy_easy_name}</strong>
          <span>전문 용어 · {candidate.strategy_name}</span>
        </div>
        <p>{candidate.strategy_description}</p>
      </section>

      {candidate.priority && (
        <section className={`scanner-priority-card priority-${candidate.priority.tier.toLowerCase()}`}>
          <div className="scanner-priority-head">
            <div>
              <small>후보 우선순위 근거</small>
              <strong>{candidate.priority.label}</strong>
              <p>{candidate.priority.reason}</p>
            </div>
          </div>
          <div className="scanner-priority-factors">
            {candidate.priority.strengths.map((item) => <span className="positive" key={`strength-${item}`}>✓ {item}</span>)}
            {candidate.priority.facts
              .filter((item) => !/\b거리\s+[0-9.]+%/.test(item))
              .map((item) => <span className="neutral" key={`fact-${item}`}>· {item}</span>)}
            {candidate.priority.penalties.map((item) => <span className="negative" key={`penalty-${item}`}>△ {item}</span>)}
          </div>
          <small className="scanner-priority-rule">순위 기준 · {candidate.priority.ranking_rule}</small>
        </section>
      )}

      <section className={`scanner-evidence-compact ${evidence?.status ? `evidence-${evidence.status.toLowerCase()}` : ""}`}>
        <div className="scanner-evidence-compact-head">
          <div>
            <small>같은 전략의 최근 3년 과거 근거</small>
            <strong>{evidenceLabel}</strong>
            <span>{evidenceSummary}</span>
          </div>
          {evidence?.verified && (
            <div className="scanner-evidence-compact-metrics">
              <span><small>유사 거래</small><b>{evidence.sample_count}회</b></span>
              <span><small>평균 순수익</small><b>{formatSignedPct(evidence.average_net_return_pct)}</b></span>
              <span><small>최대 낙폭</small><b>{formatSignedPct(evidence.max_drawdown_pct)}</b></span>
            </div>
          )}
        </div>
        {evidence && (
          <details
            className="scanner-evidence-details"
            open={evidenceOpen}
            onToggle={(event) => onEvidenceToggle(event.currentTarget.open)}
          >
            <summary>과거 근거 자세히 보기</summary>
            {evidence.verified ? (
              <>
                <div className="scanner-evidence-detail-grid">
                  <div><small>Profit Factor</small><strong>{evidence.profit_factor == null ? "-" : evidence.profit_factor.toFixed(2)}</strong></div>
                  <div><small>수익 거래</small><strong>{evidence.wins} / {evidence.sample_count}</strong></div>
                  <div><small>손절 종료</small><strong>{evidence.exit_counts.stop}회</strong></div>
                  <div><small>1차 목표 종료</small><strong>{evidence.exit_counts.target1}회</strong></div>
                </div>
                {evidence.target1_audit?.available && (
                  <div className="scanner-target1-audit">
                    <div><small>1차 목표 평균 거리</small><strong>{formatSignedPct(evidence.target1_audit.average_target_distance_pct)}</strong></div>
                    <div><small>평균 Risk 배수</small><strong>{evidence.target1_audit.average_target_r_multiple == null ? "-" : `${evidence.target1_audit.average_target_r_multiple.toFixed(2)}R`}</strong></div>
                    <div><small>20거래일 내 Target1 도달</small><strong>{evidence.target1_audit.target_hit_days?.within_20_days ?? 0} / {evidence.target1_audit.sample_count}</strong></div>
                    <div><small>Target1 도달 평균일</small><strong>{evidence.target1_audit.average_target_hit_days == null ? "-" : `${evidence.target1_audit.average_target_hit_days.toFixed(1)}일`}</strong></div>
                    <p>과거 동일 진입점 기준 Target1 기록입니다. 미래 성공 확률을 뜻하지 않습니다.</p>
                  </div>
                )}
                {evidence.market_regime_summary.length > 0 && (
                  <div className="scanner-regime-evidence">
                    {evidence.market_regime_summary.map((row) => (
                      <span key={row.regime}><b>{regimeLabel[row.regime] ?? row.regime}</b> · {row.trades}회 · 평균 {formatSignedPct(row.average_net_return_pct)}</span>
                    ))}
                  </div>
                )}
                {evidence.warnings.length > 0 && <div className="scanner-evidence-warnings">{evidence.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
                <p className="scanner-evidence-guardrail">{evidence.guardrail}</p>
              </>
            ) : (
              <div className="scanner-evidence-unavailable">
                <strong>{evidence.label}</strong>
                <p>{evidence.summary}</p>
                {evidence.warnings.length > 0 && <small>{evidence.warnings.join(" · ")}</small>}
              </div>
            )}
          </details>
        )}
      </section>

      {topMissing.length > 0 && (
        <details className="scanner-selected-secondary">
          <summary>판단 변경 조건 자세히 보기 <b>{topMissing.length}개</b></summary>
          <div className="scanner-missing-grid">
            {topMissing.map((condition, index) => (
              <div className="scanner-missing-item" key={`${condition.condition_id ?? condition.raw}-${index}`}>
                <strong>{condition.label}</strong>
                <p>{condition.detail}</p>
                {(condition.current_value || condition.required_value) && (
                  <div className="scanner-condition-values">
                    {condition.current_value && <span><small>현재</small><b>{condition.current_value}</b></span>}
                    {condition.required_value && <span><small>필요</small><b>{condition.required_value}</b></span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      <footer className="scanner-selected-action">
        <div>
          <small>지금 행동</small>
          <strong>{candidate.user_action.title || "현재 판단을 유지하세요."}</strong>
          <p>{candidate.user_action.detail}</p>
        </div>
        <button type="button" className="scanner-detail-button" onClick={onAnalyze}>이 종목 자세히 분석</button>
      </footer>

      {candidate.risk.warning && candidate.risk.warnings.length > 0 && (
        <div className="scanner-risk-note">
          <strong>추가 주의</strong>
          <span>{candidate.risk.warnings.join(" · ")}</span>
        </div>
      )}
    </article>
  );
}

export default function ScannerPanel({ onAnalyzeStock }: Props) {
  const initialSession = useMemo(() => readScannerSession(), []);
  const sharedSession = useScannerSession();
  const [scope, setScope] = useState<MarketScope>(initialSession?.scope ?? "ALL");
  const [job, setJob] = useState<BacktestJob<ScannerResponse> | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(initialSession?.result ?? null);
  const [selectedCandidateKey, setSelectedCandidateKey] = useState<string | null>(
    initialSession?.selectedCandidateKey
      ?? (initialSession?.result?.candidates?.[0] ? candidateKey(initialSession.result.candidates[0]) : null),
  );
  const [error, setError] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(initialSession?.showMore ?? false);
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<string[]>(initialSession?.expandedEvidenceIds ?? []);
  const [completedAt, setCompletedAt] = useState<number | null>(initialSession?.completedAt ?? null);
  const [restoredFromSession, setRestoredFromSession] = useState(Boolean(initialSession));
  const [clock, setClock] = useState(Date.now());
  const [freshnessFailure, setFreshnessFailure] = useState<ScannerFreshnessResponse | null>(null);
  const [dateNotice, setDateNotice] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const lastProgressAtRef = useRef<number | null>(null);
  const lastProgressSignatureRef = useRef("");
  const savedScrollRef = useRef(initialSession?.scrollY ?? 0);
  const didRestoreScrollRef = useRef(false);

  const jobBusy = job?.status === "queued" || job?.status === "running";
  const busy = jobBusy;
  const progress = job?.progress;

  useEffect(() => {
    // TRACK.1.10.1: accept Scanner results completed from another entry point
    // (for example Stock Tracking) without requiring a page round-trip.
    if (!sharedSession?.result || jobBusy || sharedSession.result === result) return;
    setScope(sharedSession.scope);
    setResult(sharedSession.result);
    setSelectedCandidateKey(
      sharedSession.selectedCandidateKey
        ?? (sharedSession.result.candidates?.[0] ? candidateKey(sharedSession.result.candidates[0]) : null),
    );
    setShowMore(sharedSession.showMore);
    setExpandedEvidenceIds(sharedSession.expandedEvidenceIds);
    setCompletedAt(sharedSession.completedAt);
    setRestoredFromSession(true);
    savedScrollRef.current = sharedSession.scrollY;
  }, [sharedSession, jobBusy, result]);

  useEffect(() => {
    const onScroll = () => {
      savedScrollRef.current = window.scrollY;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!result) return;
    writeScannerSession({
      scope,
      result,
      completedAt: completedAt ?? Date.now(),
      scrollY: savedScrollRef.current,
      showMore,
      expandedEvidenceIds,
      selectedCandidateKey,
    });
  }, [scope, result, completedAt, showMore, expandedEvidenceIds, selectedCandidateKey]);

  useEffect(() => {
    if (!initialSession || !result || didRestoreScrollRef.current) return;
    didRestoreScrollRef.current = true;
    const target = Math.max(0, initialSession.scrollY);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.scrollTo({ top: target, behavior: "auto" }));
    });
  }, [initialSession, result]);

  useEffect(() => () => {
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    if (!dateNotice) return undefined;
    const timer = window.setTimeout(() => setDateNotice(null), 4500);
    return () => window.clearTimeout(timer);
  }, [dateNotice]);

  function stockItem(candidate: ScannerCandidate): StockSearchItem {
    return {
      code: candidate.code,
      standard_code: candidate.code,
      name: candidate.name,
      full_name: candidate.name,
      english_name: "",
      market: candidate.market,
      market_name: candidate.market,
      security_group: "주식",
      section: "",
      stock_type: "보통주",
      listed_date: "",
      listed_shares: null,
      analysis_as_of_date: candidate.data_date || null,
    };
  }

  async function poll(jobId: string) {
    try {
      const latest = await fetchBacktestJob<ScannerResponse>(jobId);
      const signature = JSON.stringify({
        stage: latest.stage,
        current: latest.progress?.current,
        percent: latest.progress?.percent,
        details: latest.progress?.details,
      });
      if (signature !== lastProgressSignatureRef.current) {
        lastProgressSignatureRef.current = signature;
        lastProgressAtRef.current = Date.now();
      }
      setJob(latest);
      const latestDetails = latest.progress?.details ?? {};
      const resolvedProgressDate = typeof latestDetails.resolved_as_of_date === "string"
        ? latestDetails.resolved_as_of_date
        : null;
      if (latestDetails.date_changed === true && resolvedProgressDate) {
        setDateNotice(resolvedProgressDate);
      }
      if (latest.status === "completed" && latest.result) {
        const completedAtValue = Date.now();
        // TRACK.1.9: commit completed Scanner result synchronously so Tracking
        // sees the same result even if the user navigates before React effects run.
        writeScannerSession({
          scope,
          result: latest.result,
          completedAt: completedAtValue,
          scrollY: window.scrollY,
          showMore: false,
          expandedEvidenceIds: [],
          selectedCandidateKey: latest.result.candidates[0] ? candidateKey(latest.result.candidates[0]) : null,
        });
        setResult(latest.result);
        setSelectedCandidateKey(latest.result.candidates[0] ? candidateKey(latest.result.candidates[0]) : null);
        setShowMore(false);
        setExpandedEvidenceIds([]);
        setCompletedAt(completedAtValue);
        setRestoredFromSession(false);
        savedScrollRef.current = window.scrollY;
        return;
      }
      if (latest.status === "failed") {
        const freshnessValue: unknown = latestDetails.freshness_failure;
        const freshness = (
          freshnessValue !== null
          && typeof freshnessValue === "object"
          && !Array.isArray(freshnessValue)
        )
          ? freshnessValue as ScannerFreshnessResponse
          : undefined;
        if (freshness) {
          setFreshnessFailure(freshness);
          setError(null);
        } else {
          setError(latest.error || "종목 찾기 중 오류가 발생했습니다.");
        }
        return;
      }
      if (latest.status === "cancelled") return;
      pollRef.current = window.setTimeout(() => void poll(jobId), 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목 찾기 상태를 확인하지 못했습니다.");
    }
  }

  async function runScanner(
    forceRefresh = false,
    allowLargeSync = false,
    pinnedAsOfDate: string | null = null,
  ) {
    if (busy) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    setError(null);
    setFreshnessFailure(null);
    if (!result) {
      setShowMore(false);
      setExpandedEvidenceIds([]);
    }
    const started = Date.now();
    startedAtRef.current = started;
    lastProgressAtRef.current = started;
    lastProgressSignatureRef.current = "";
    setClock(started);

    try {
      const request = {
        market_scope: scope,
        as_of_date: pinnedAsOfDate ?? undefined,
        // The scanner job now owns freshness preparation so the same cancellable
        // progress stream covers latest-EOD verification and candidate analysis.
        known_data_date: pinnedAsOfDate
          ? undefined
          : (result?.requested_as_of ?? latestScannerDataDate(result)),
        candidate_limit: 5,
        force_refresh: forceRefresh,
        allow_large_sync: allowLargeSync,
      } as Parameters<typeof createScannerJob>[0] & { known_data_date?: string | null };
      const created = await createScannerJob(request);
      setJob(created);
      void poll(created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목 찾기를 시작하지 못했습니다.");
    }
  }

  function persistBeforeNavigation() {
    if (!result) return;
    const scrollY = window.scrollY;
    savedScrollRef.current = scrollY;
    writeScannerSession({
      scope,
      result,
      completedAt: completedAt ?? Date.now(),
      scrollY,
      showMore,
      expandedEvidenceIds,
      selectedCandidateKey,
    });
  }

  function analyzeCandidate(candidate: ScannerCandidate) {
    persistBeforeNavigation();
    try {
      window.sessionStorage.setItem("stockscope-scanner-analysis-context", JSON.stringify({
        code: candidate.code,
        market: candidate.market,
        data_date: candidate.data_date,
        strategy: candidate.strategy,
        strategy_easy_name: candidate.strategy_easy_name,
        strategy_name: candidate.strategy_name,
        action: candidate.action,
        action_label: candidate.action_label,
        passed: candidate.conditions.passed,
        total: candidate.conditions.total,
        risk_status: candidate.risk.status,
        saved_at: Date.now(),
      }));
    } catch {
      // Navigation still works even when sessionStorage is unavailable.
    }
    onAnalyzeStock(stockItem(candidate));
  }

  function changeScope(value: MarketScope) {
    if (busy || value === scope) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    clearScannerSession();
    setScope(value);
    setJob(null);
    setResult(null);
    setSelectedCandidateKey(null);
    setError(null);
    setShowMore(false);
    setExpandedEvidenceIds([]);
    setCompletedAt(null);
    setRestoredFromSession(false);
    setFreshnessFailure(null);
    setDateNotice(null);
    savedScrollRef.current = 0;
    didRestoreScrollRef.current = true;
  }

  function toggleEvidence(candidate: ScannerCandidate, open: boolean) {
    const key = evidenceKey(candidate);
    setExpandedEvidenceIds((current) => {
      if (open) return current.includes(key) ? current : [...current, key];
      return current.filter((item) => item !== key);
    });
  }

  function toggleMoreCandidates() {
    const next = !showMore;
    if (!next && result && selectedCandidateKey && result.more_candidates.some((candidate) => candidateKey(candidate) === selectedCandidateKey)) {
      setSelectedCandidateKey(result.candidates[0] ? candidateKey(result.candidates[0]) : null);
    }
    setShowMore(next);
  }

  async function cancel() {
    if (!job?.job_id || !busy) return;
    if (pollRef.current != null) window.clearTimeout(pollRef.current);
    try {
      const cancelled = await cancelBacktestJob<ScannerResponse>(job.job_id);
      setJob(cancelled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 취소에 실패했습니다.");
    }
  }

  const marketText = useMemo(() => {
    if (!result?.market_summary?.length) return "아직 시장 상태를 계산하지 않았습니다.";
    return result.market_summary.map((item) => `${item.market} ${regimeLabel[item.regime] ?? item.regime}`).join(" · ");
  }, [result]);

  const progressDetails = (progress?.details ?? {}) as Record<string, unknown>;
  const elapsedSeconds = startedAtRef.current == null ? 0 : Math.max(0, (clock - startedAtRef.current) / 1000);
  const staleSeconds = lastProgressAtRef.current == null ? 0 : Math.max(0, (clock - lastProgressAtRef.current) / 1000);
  const progressView = scannerProgressView(job?.stage, progressDetails);
  const activeRows = progressView.analysisStarted ? progressView.analysisRows : progressView.prepRows;
  const activeStage = activeRows.find((item) => item.status === "active" || item.status === "failed");
  const stageCountText = progressView.analysisStarted
    ? `분석 단계 ${progressView.analysisDone} / ${ANALYSIS_STAGES.length}`
    : `준비 단계 ${progressView.prepDone} / ${progressView.prepRows.length}`;
  const preparationItems = result?.preparation_required ?? [];
  const preparationRequests = preparationItems.reduce((sum, item) => sum + Number(item.estimated_network_requests || 0), 0);
  const noAnalyzedData = Boolean(result && result.summary.universe_total === 0 && preparationItems.length > 0);
  const analysisDateResolution = resolveScannerDataDate(result);
  const analysisDataDate = analysisDateResolution.date;
  const analysisDateMismatch = Boolean(result && !analysisDateResolution.aligned);
  const restoredOnDifferentDay = Boolean(initialSession && restoredFromSession && localDateKey(initialSession.completedAt) !== localDateKey());
  const allCandidates = useMemo(
    () => result ? [...result.candidates, ...result.more_candidates] : [],
    [result],
  );
  const selectedCandidate = useMemo(
    () => allCandidates.find((candidate) => candidateKey(candidate) === selectedCandidateKey) ?? result?.candidates[0] ?? null,
    [allCandidates, selectedCandidateKey, result],
  );
  const selectedRank = selectedCandidate
    ? Math.max(1, allCandidates.findIndex((candidate) => candidateKey(candidate) === candidateKey(selectedCandidate)) + 1)
    : 0;

  useEffect(() => {
    if (!result) {
      if (selectedCandidateKey != null) setSelectedCandidateKey(null);
      return;
    }
    if (allCandidates.length === 0) {
      if (selectedCandidateKey != null) setSelectedCandidateKey(null);
      return;
    }
    if (!selectedCandidateKey || !allCandidates.some((candidate) => candidateKey(candidate) === selectedCandidateKey)) {
      setSelectedCandidateKey(candidateKey(allCandidates[0]));
    }
  }, [result, allCandidates, selectedCandidateKey]);

  return (
    <div className="scanner-workspace">
      <section className="scanner-hero ux13-scanner-header">
        <div>
          <h1>종목 후보 찾기</h1>
          <p>현재 시장 조건에 맞는 후보를 찾습니다.</p>
        </div>
      </section>

      <section className="scanner-control-card">
        <div>
          <strong>시장 선택</strong>
          <p>일반 상장주 중심 · ETF·ETN·SPAC 등은 기본 후보에서 제외합니다.</p>
        </div>
        <div className="scanner-market-tabs" role="group" aria-label="검색 시장 선택">
          {(["ALL", "KOSPI", "KOSDAQ"] as MarketScope[]).map((value) => (
            <button key={value} type="button" className={scope === value ? "active" : ""} onClick={() => changeScope(value)} disabled={busy}>
              {value === "ALL" ? "전체" : value}
            </button>
          ))}
        </div>
        <div className="scanner-control-actions">
          {result && !busy ? (
            <div className="scanner-result-held">
              <strong>✓ 분석 결과 유지 중</strong>
              <span>같은 설정에서는 다시 찾지 않습니다.</span>
            </div>
          ) : (
            <button type="button" className="scanner-run-button" onClick={() => void runScanner(false)} disabled={busy}>
              {jobBusy && String(job?.stage || "").startsWith("scanner_prepare") ? "최신 시세 확인 중..." : jobBusy ? "후보 찾는 중..." : "후보 찾기"}
            </button>
          )}
          {jobBusy && <button type="button" className="scanner-cancel-button" onClick={() => void cancel()}>중지</button>}
        </div>
      </section>

      {dateNotice && (
        <aside className="scanner-date-toast" role="status" aria-live="polite">
          <div>
            <strong>✓ 새로운 확정 시세를 반영했습니다.</strong>
            <span>{formatDate(dateNotice)} 기준으로 분석합니다.</span>
          </div>
          <button type="button" aria-label="안내 닫기" onClick={() => setDateNotice(null)}>×</button>
        </aside>
      )}

      {freshnessFailure && (
        <section className={`scanner-freshness-failure ${freshnessFailure.current_date_valid ? "warning" : ""}`}>
          <div>
            <strong>{freshnessFailure.current_date_valid ? "새로운 확정 시세를 확인하지 못했습니다." : "현재 분석 기준 데이터를 다시 확인해야 합니다."}</strong>
            <p>{freshnessFailure.message}</p>
            {freshnessFailure.available_data_date && (
              <span>현재 사용할 수 있는 확정 일봉 · {formatDate(freshnessFailure.available_data_date)}</span>
            )}
            {freshnessFailure.failure_reason && (
              <small className="scanner-freshness-detail">확인 내용 · {freshnessFailure.failure_reason}</small>
            )}
          </div>
          <div className="scanner-freshness-actions">
            <button type="button" onClick={() => void runScanner(Boolean(result))}>다시 시도</button>
            {freshnessFailure.fallback_allowed && freshnessFailure.available_data_date && (
              <button
                type="button"
                className="secondary"
                onClick={() => void runScanner(Boolean(result), false, freshnessFailure.available_data_date)}
              >
                {formatDate(freshnessFailure.available_data_date)} 기준으로 분석
              </button>
            )}
          </div>
        </section>
      )}

      {jobBusy && progress && (
        <section className="scanner-progress-card progress-v24" aria-live="polite">
          <div className="scanner-progress-head">
            <div>
              <span>종목 찾기 진행 중</span>
              <strong>{progress.message || "시장 데이터를 확인하고 있습니다."}</strong>
            </div>
            <span className="scanner-progress-stage-count">{stageCountText}</span>
          </div>

          <div className="scanner-progress-current">
            <span>현재 작업</span>
            <strong>{activeStage?.label || progress.message || "작업 상태 확인 중"}</strong>
            {progressDetails.current_item != null
              ? <small>{String(progressDetails.current_item)}</small>
              : null}
          </div>

          <div className="scanner-progress-stages">
            {progressView.analysisStarted && (
              <div className="scanner-progress-prepared-summary">
                <i>✓</i><span>최신 확정 시세 준비 완료</span>
              </div>
            )}
            {activeRows.map((item) => (
              <div key={item.id} className={`scanner-progress-row ${item.status}`}>
                <i>{progressStatusMark(item.status)}</i>
                <span>{item.label}</span>
                {item.status === "reused" && <small>저장 데이터 재사용</small>}
                {item.status === "active" && progressDetails.items_done != null && progressDetails.items_total != null && (
                  <small>{formatNumber(Number(progressDetails.items_done))} / {formatNumber(Number(progressDetails.items_total))}</small>
                )}
              </div>
            ))}
          </div>

          <div className="scanner-progress-meta">
            <span>경과 <b>{formatElapsed(elapsedSeconds)}</b></span>
            {progressDetails.shortlisted != null && <span>현재 후보 <b>{String(progressDetails.shortlisted)}개</b></span>}
            {progressDetails.eta_seconds != null && Number(progressDetails.eta_seconds) >= 0 && (
              <span>예상 남은 시간 <b>약 {formatElapsed(Number(progressDetails.eta_seconds))}</b></span>
            )}
          </div>

          {staleSeconds >= 8 && staleSeconds < 45 && (
            <p className="scanner-progress-connection">데이터 제공처 응답을 기다리고 있습니다 · 연결 상태를 계속 확인 중입니다.</p>
          )}
          {staleSeconds >= 45 && staleSeconds < 120 && (
            <div className="scanner-progress-warning">
              <strong>응답이 평소보다 오래 걸리고 있습니다.</strong>
              <span>작업은 계속 진행 중입니다. 중지해도 이미 정상 저장된 시장 데이터는 유지됩니다.</span>
            </div>
          )}
          {staleSeconds >= 120 && (
            <div className="scanner-progress-warning danger">
              <strong>진행 상태 갱신이 오래 지연되고 있습니다.</strong>
              <span>계속 기다리거나 위의 중지 버튼으로 안전하게 취소할 수 있습니다.</span>
            </div>
          )}

          <details className="scanner-progress-diagnostics">
            <summary>진행 상세</summary>
            <div>
              {progressDetails.estimated_network_requests != null && <span>예상 KRX 신규 요청 {String(progressDetails.estimated_network_requests)}회</span>}
              {progressDetails.network_requests_so_far != null && <span>실제 KRX 요청 {String(progressDetails.network_requests_so_far)}회</span>}
              {progressDetails.processing_rate != null && <span>처리 속도 {Number(progressDetails.processing_rate).toFixed(1)}건/초</span>}
              {progressDetails.active_requests != null && progressDetails.concurrency_limit != null && (
                <span>동시 처리 {String(progressDetails.active_requests)} / {String(progressDetails.concurrency_limit)}</span>
              )}
              {progressDetails.retry_count != null && Number(progressDetails.retry_count) > 0 && <span>재시도 {String(progressDetails.retry_count)}회</span>}
            </div>
          </details>
        </section>
      )}

      {error && (
        <section className="scanner-error-card">
          <strong>{result ? "새 분석을 완료하지 못했습니다. 기존 결과를 유지합니다." : "종목 찾기를 완료하지 못했습니다."}</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void runScanner(Boolean(result))}>다시 시도</button>
        </section>
      )}

      {!result && !busy && !error && !freshnessFailure && (
        <section className="scanner-empty-start ux13-scanner-empty">
          <strong>후보 결과</strong>
          <p>아직 후보가 없습니다.</p>
        </section>
      )}

      {result && (
        <>
          <section className="scanner-result-summary">
            <div>
              <span>현재 시장</span>
              <strong>{marketText}</strong>
              <p>{result.methodology.meaning}</p>
            </div>
            <div className="scanner-summary-numbers">
              <span><small>전체 확인</small><b>{formatNumber(result.summary.universe_total)}개</b></span>
              <span><small>상세 검증</small><b>{formatNumber(result.summary.deep_analyzed)}개</b></span>
              <span><small>관심 후보</small><b>{formatNumber(result.summary.candidate_count)}개</b></span>
              <span><small>먼저 표시</small><b>{formatNumber(result.summary.shown_count)}개</b></span>
            </div>
            <div className="scanner-analysis-date">
              <span>분석 기준일</span>
              <strong>{analysisDataDate ? `${formatDate(analysisDataDate)} 확정 일봉` : "확정 일봉 확인 필요"}</strong>
              {analysisDateMismatch && <small>저장된 시장별 날짜가 달라 다시 분석해야 합니다.</small>}
            </div>
            <div className="scanner-cache-note">
              {result.scanner_cache_hit ? "오늘 계산한 결과를 바로 재사용했습니다." : `KRX 신규 요청 ${result.diagnostics.network_requests}회 · 시장 저장 데이터 재사용 ${result.diagnostics.market_store_reused_items}건`}
            </div>
            <div className={`scanner-session-note ${restoredFromSession ? "restored" : "current"}`}>
              <div>
                <small>{analysisDataDate ? `${formatDate(analysisDataDate)} 확정 일봉 기준` : "확정 일봉 기준"}</small>
                <strong>{restoredFromSession ? "이전 분석 결과를 그대로 불러왔습니다." : "현재 세션에서 이 결과를 유지합니다."}</strong>
                <span>마지막 분석 {formatLocalTime(completedAt)}</span>
              </div>
              <p>
                {restoredOnDifferentDay
                  ? "브라우저 날짜가 바뀌었습니다. 새 확정 일봉이 생겼다면 ‘다시 분석’으로 갱신하세요."
                  : "상세 분석 후 종목 찾기로 돌아와도 같은 결과를 다시 계산하지 않습니다."}
              </p>
            </div>
          </section>

          {preparationItems.length > 0 && (
            <section className="scanner-preparation-card">
              <div>
                <span>빠른 검색 범위 제한</span>
                <strong>대량 다운로드 없이 저장된 데이터로 먼저 찾았습니다.</strong>
                <p>최근 기술지표 계산에 필요한 데이터가 부족해 자동 다운로드 상한 {formatNumber(result.fast_request_limit ?? 60)}회를 넘겼습니다. 현재 후보는 사용 가능한 데이터 범위에서 만든 결과입니다.</p>
                <div className="scanner-preparation-markets">
                  {preparationItems.map((item) => (
                    <span key={item.market}><b>{item.market}</b> 예상 {formatNumber(item.estimated_network_requests)}회</span>
                  ))}
                </div>
              </div>
              <button type="button" onClick={() => void runScanner(true, true)} disabled={busy}>시장 데이터 준비 시작 · 약 {formatNumber(preparationRequests)}회</button>
            </section>
          )}

          <section className="scanner-section-head">
            <div>
              <span>후보 결과</span>
              <h2>{result.candidates.length > 0 ? `${result.candidates.length}개를 먼저 확인하세요.` : noAnalyzedData ? "아직 후보를 판단하지 못했습니다." : "현재 조건에 맞는 후보가 없습니다."}</h2>
              <p>순위는 상승 확률이 아닙니다. 현재 조건을 먼저 보고 Risk, 실제 진입 기준까지의 거리, 같은 전략의 3년 과거 근거 순으로 비교해 먼저 확인할 순서를 정합니다.</p>
            </div>
            <button type="button" className="scanner-refresh-button" onClick={() => void runScanner(true)} disabled={busy}>다시 분석</button>
          </section>

          {result.candidates.length === 0 ? (
            <section className="scanner-no-candidate" role="status" aria-live="polite">
              <strong>{noAnalyzedData ? "아직 시장 데이터 준비가 필요합니다." : "현재는 관망이 정상 결과입니다."}</strong>
              <p>{emptyCandidateMessage(result, noAnalyzedData)}</p>
              {!noAnalyzedData && <small>후보가 없는 것도 정상적인 분석 결과입니다. 현재 조건을 완화해서 종목을 억지로 만들지 않습니다.</small>}
            </section>
          ) : (
            <div className="scanner-decision-workspace">
              <section className="scanner-compare-panel">
                <header className="scanner-compare-head">
                  <div>
                    <span>후보 빠른 비교</span>
                    <strong>핵심 가격과 현재 판단만 먼저 비교하세요.</strong>
                  </div>
                  <small>행을 선택하면 아래 상세 판단만 바뀝니다.</small>
                </header>

                <div className="scanner-compare-labels" aria-hidden="true">
                  <span>순서</span><span>종목 / 전략</span><span>현재 판단</span><span>핵심 가격</span><span />
                </div>
                <div className="scanner-compare-list">
                  {result.candidates.map((candidate, index) => (
                    <CandidateCompareRow
                      key={candidateKey(candidate)}
                      candidate={candidate}
                      rank={index + 1}
                      selected={selectedCandidate ? candidateKey(selectedCandidate) === candidateKey(candidate) : false}
                      onSelect={() => setSelectedCandidateKey(candidateKey(candidate))}
                    />
                  ))}
                </div>

                {result.more_candidates.length > 0 && (
                  <div className="scanner-compare-more">
                    <button type="button" onClick={toggleMoreCandidates}>
                      {showMore ? "다른 후보 숨기기 ▲" : `다른 후보 ${result.more_candidates.length}개 보기 ▼`}
                    </button>
                    {showMore && (
                      <div className="scanner-compare-list more">
                        {result.more_candidates.map((candidate, index) => (
                          <CandidateCompareRow
                            key={`more-${candidateKey(candidate)}`}
                            candidate={candidate}
                            rank={result.candidates.length + index + 1}
                            selected={selectedCandidate ? candidateKey(selectedCandidate) === candidateKey(candidate) : false}
                            onSelect={() => setSelectedCandidateKey(candidateKey(candidate))}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </section>

              {selectedCandidate && (
                <CandidateDetail
                  candidate={selectedCandidate}
                  rank={selectedRank}
                  onAnalyze={() => analyzeCandidate(selectedCandidate)}
                  evidenceOpen={expandedEvidenceIds.includes(evidenceKey(selectedCandidate))}
                  onEvidenceToggle={(open) => toggleEvidence(selectedCandidate, open)}
                />
              )}
            </div>
          )}

          <details className="scanner-details">
            <summary>어떤 종목을 제외했나요? <b>펼치기 ▼</b></summary>
            <div className="scanner-details-grid">
              <div><small>기본 제외</small><strong>{result.exclusion_policy.default.join(" · ")}</strong></div>
              <div><small>유동성 기준</small><strong>{result.exclusion_policy.liquidity}</strong></div>
              <div><small>특수/거래 제외</small><strong>{formatNumber(result.summary.special_excluded)}개</strong></div>
              <div><small>유동성 빠른 제외</small><strong>{formatNumber(result.summary.liquidity_filtered)}개</strong></div>
            </div>
          </details>

          <details className="scanner-details">
            <summary>개발 확인용 · Scanner 실행 진단 <b>펼치기 ▼</b></summary>
            <div className="scanner-details-grid diagnostics">
              <div><small>예상 KRX 요청</small><strong>{formatNumber(result.diagnostics.estimated_network_requests)}회</strong></div>
              <div><small>실제 KRX 요청</small><strong>{formatNumber(result.diagnostics.network_requests)}회</strong></div>
              <div><small>초기 데이터 처리속도</small><strong>{Number(result.diagnostics.bootstrap_request_rate ?? 0).toFixed(1)}건/초</strong></div>
              <div><small>최대 동시 처리</small><strong>{formatNumber(result.diagnostics.bootstrap_peak_concurrency ?? 0)}개</strong></div>
              <div><small>초기 준비 오류</small><strong>{formatNumber(result.diagnostics.bootstrap_errors ?? 0)}건</strong></div>
              <div><small>시장 저장소 재사용</small><strong>{formatNumber(result.diagnostics.market_store_reused_items)}건</strong></div>
              <div><small>기존 KRX 캐시</small><strong>{formatNumber(result.diagnostics.raw_cache_hits)} hit</strong></div>
              <div><small>오늘 KRX(앱 기록)</small><strong>{formatNumber(result.diagnostics.budget_used)} / {formatNumber(result.diagnostics.budget_limit)}</strong></div>
              <div><small>Fast Scan 자동 상한</small><strong>{formatNumber(result.diagnostics.fast_request_limit ?? result.fast_request_limit)}회</strong></div>
              <div><small>3년 과거 근거 완료</small><strong>{formatNumber(result.summary.three_year_evidence_verified ?? 0)}개</strong></div>
              <div><small>현재 조건만</small><strong>{formatNumber(result.summary.current_only ?? 0)}개</strong></div>
              <div><small>데이터 준비</small><strong>{Number(result.diagnostics.data_prepare_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>빠른 검사</small><strong>{Number(result.diagnostics.quick_filter_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>상위 후보 분석</small><strong>{Number(result.diagnostics.deep_analysis_seconds ?? 0).toFixed(2)}초</strong></div>
              <div><small>전체 실행</small><strong>{Number(result.diagnostics.total_seconds ?? 0).toFixed(2)}초</strong></div>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
