import type { StrategyGovernanceOverview } from "../services/strategyGovernanceApi";

function productionSourceLabel(source: string) {
  if (source === "ACTIVE_SELECTION_POLICY") return "승인된 운영 정책";
  if (source === "ROLLBACK_FALLBACK") return "롤백 정책";
  return "기본 10 전략";
}

function evidenceLabel(overview: StrategyGovernanceOverview) {
  if (overview.evidence.stale_or_missing_count > 0) {
    return String(overview.evidence.stale_or_missing_count) + "개 확인 필요";
  }
  if (overview.evidence.artifact_count === 0) return "근거 없음";
  return String(overview.evidence.current_count) + "개 최신";
}

function proposalLabel(overview: StrategyGovernanceOverview) {
  if (!overview.proposal.latest_id) return "변경안 없음";
  if (overview.proposal.verification_status === "CURRENT") return "검토 가능한 변경안";
  return "변경안 재확인 필요";
}

export default function StrategyOperationsPanel({
  overview,
  loading,
  error,
}: {
  overview: StrategyGovernanceOverview | null;
  loading: boolean;
  error: string | null;
}) {
  const blocked =
    overview?.approval.blocked_reason === "Q7_APPROVAL_PROTOCOL_UNAPPROVED";

  return (
    <section className="sim-strategy-ops" aria-label="전략 운영">
      <div className="sim-strategy-ops-head">
        <div>
          <span className="sim-section-kicker">Strategy Operations</span>
          <h2>전략 운영</h2>
          <p>
            검증 근거와 Production 적용 상태를 분리해서 보여줍니다.
            최근 검증 결과가 자동으로 운영 전략을 바꾸지는 않습니다.
          </p>
        </div>
        <strong className={blocked ? "locked" : undefined}>
          {loading
            ? "상태 확인 중"
            : blocked
              ? "운영 변경 잠금"
              : overview
                ? "운영 상태 확인됨"
                : "확인 필요"}
        </strong>
      </div>

      {error && !overview ? (
        <p className="sim-strategy-ops-warning">
          전략 운영 저장소 준비 상태를 확인해야 합니다. {error}
        </p>
      ) : overview ? (
        <>
          <div className="sim-strategy-ops-strip">
            <div>
              <span>운영 전략</span>
              <strong>{overview.registry.operating_count}개</strong>
              <small>
                후보 {overview.registry.candidate_count} · 보류 {overview.registry.on_hold_count} · 강등 {overview.registry.demoted_count}
              </small>
            </div>
            <div>
              <span>검증 근거</span>
              <strong>{evidenceLabel(overview)}</strong>
              <small>저장된 근거 {overview.evidence.artifact_count}개</small>
            </div>
            <div>
              <span>변경안</span>
              <strong>{proposalLabel(overview)}</strong>
              <small>{overview.proposal.gate_state ?? "현재 제안 없음"}</small>
            </div>
            <div>
              <span>Production</span>
              <strong>
                {productionSourceLabel(overview.production_policy.policy_source)}
              </strong>
              <small>
                {overview.production_policy.rollback_available
                  ? "롤백 가능"
                  : "롤백 대기 없음"}
              </small>
            </div>
          </div>

          {blocked && (
            <p className="sim-strategy-ops-lock">
              승격·강등 수치 기준(Q7)이 아직 사전 승인되지 않아 운영 전략 변경은 잠겨 있습니다.
              검증과 근거 축적은 계속할 수 있습니다.
            </p>
          )}

          <details className="sim-strategy-ops-details">
            <summary>기술 정보 보기</summary>
            <dl>
              <div>
                <dt>Scanner</dt>
                <dd>{overview.scanner_baseline.scanner_version}</dd>
              </div>
              <div>
                <dt>Baseline</dt>
                <dd>{overview.scanner_baseline.baseline_id}</dd>
              </div>
              <div>
                <dt>Selection Policy</dt>
                <dd>{overview.production_policy.policy_id}</dd>
              </div>
              <div>
                <dt>Policy source</dt>
                <dd>{overview.production_policy.policy_source}</dd>
              </div>
              <div>
                <dt>Fallback</dt>
                <dd>
                  {overview.production_policy.fallback_used
                    ? overview.production_policy.fallback_reason ?? "사용 중"
                    : "사용 안 함"}
                </dd>
              </div>
              <div>
                <dt>Generation</dt>
                <dd>{overview.production_policy.generation ?? "-"}</dd>
              </div>
            </dl>
          </details>
        </>
      ) : (
        <p className="sim-strategy-ops-loading">
          전략 운영 상태를 불러오는 중입니다.
        </p>
      )}
    </section>
  );
}
