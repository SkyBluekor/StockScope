import { useState } from "react";
import {
  getJevSyntheticActualReceipts,
  type JevSyntheticActualReport,
} from "../services/jevApi";

const labels: Record<string, string> = {
  PASS_THROUGH: "문제 없음",
  REVIEW_REQUIRED: "재검토 필요",
  ABSTAIN: "판단 보류",
};

function validResponse(value: JevSyntheticActualReport): boolean {
  return value.scope === "SYNTHETIC_ONLY"
    && value.real_stock_models_reviewed === 0
    && value.scanner_uplift_proven === false
    && value.model_calls_on_request === 0
    && value.external_requests_on_request === 0
    && value.db_writes_on_request === 0
    && value.provider_provenance === "LOCAL_JOURNAL_ORIGIN_CLAIM_NOT_CRYPTOGRAPHICALLY_ATTESTED"
    && value.results.every(r =>
      ["s5-consistent","s5-condition-contradiction","s5-risk-contradiction",
        "s5-insufficient-evidence","s5-unresolved-ambiguity"].includes(r.case_id));
}

/** Actual model micro-canary history, wholly unrelated to the selected stock.
 * GET-only on explicit click. No provider call and no paid execution path.
 */
export default function JevSyntheticTrialHistory() {
  const [data, setData] = useState<JevSyntheticActualReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(): Promise<void> {
    if (loading) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const report = await getJevSyntheticActualReceipts();
      if (!validResponse(report)) {
        setError("합성 모델 실험과 실제 종목 데이터의 경계가 확인되지 않아 결과를 표시하지 않았어요.");
        return;
      }
      setData(report);
    } catch {
      setError("로컬 합성 JEV 실험 기록을 읽지 못했어요. 백엔드 연결과 연구 DB를 확인하세요.");
    } finally {
      setLoading(false);
    }
  }
  const hasRecords = data && data.actual_provider_attempts_recorded > 0;
  return (
    <details className="scanner-jev-synthetic-report" aria-label="별도 실제 JEV 모델 합성 실험 내역">
      <summary>실제 JEV 모델 실험 내역 보기 (합성 데이터 · 현재 종목과 별개)</summary>
      <p>
        이 영역은 기존 TypeSafe API를 호출한 합성 실험의 연구 기록만 표시해요.
        F&F를 포함한 어떤 실제 Scanner 종목도 모델이 검토했다는 뜻이 아닙니다.
      </p>
      <button type="button" onClick={() => void load()} disabled={loading}>
        {loading ? "로컬 연구 기록 확인 중…" : "기존 실제 모델 실험 결과 불러오기"}
      </button>
      {error && <p role="alert">{error}</p>}
      {data && <section aria-label="합성 모델 응답 기록" role="status">
        {!hasRecords
          ? <p><strong>이 PC의 연구 DB에는 실제 JEV 모델 호출 기록이 없어요.</strong>
              Mock 테스트 {data.mock_rows_excluded}건은 실제 모델 실적으로 계산하지 않았습니다.
              상태: {data.status}.</p>
          : <>
            <p>
              <strong>실제 공급자 호출로 기록된 실험 {data.actual_provider_attempts_recorded}건</strong>
              {" · "}응답 근거 확인 {data.actual_valid_receipts}건
              {" · "}합성 기대 판단 일치 {data.correct_against_synthetic_gold}건
              {" · "}불일치 {data.incorrect_against_synthetic_gold}건
            </p>
            {data.unverified_receipt_rows > 0 && (
              <p>형식 검증에 실패한 연구 기록 {data.unverified_receipt_rows}건은 결과에서 제외했습니다.</p>
            )}
            <table>
              <thead><tr>
                <th>합성 사례</th><th>기대</th><th>기록된 모델 판단</th><th>일치</th>
              </tr></thead>
              <tbody>{data.results.map((row, index) => (
                <tr key={row.case_id + "-" + index}>
                  <td>{row.case_title}</td>
                  <td>{labels[row.expected] ?? "미확인"}</td>
                  <td>{row.receipt_status === "JOURNAL_CONSISTENCY_CHECK_PASSED"
                    ? (labels[row.observed ?? ""] ?? "미확인") : "검증 불가"}</td>
                  <td>{row.matches_expected == null ? "미확인" : row.matches_expected ? "일치" : "불일치"}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        }
        <small>
          데이터 근거: 로컬 S6 연구 DB에 저장된 ACTUAL_PROVIDER 표시 기록.
          원본 공급자의 전자서명으로 진위를 독립적으로 검증한 것은 아닙니다.
          표시된 비용은 공개 표준 요금 추정치이며 실제 청구액이 아닙니다.
          저장된 데이터를 읽기만 하며 유료 API를 새로 호출하지 않습니다.
        </small>
        <p>
          실제 종목에서 JEV가 투자 성과를 개선하는지는 여전히 입증되지 않았습니다.
          유료 합성 실험을 추가하려면 별도의 기존 S6 CLI에서 모델·예산·명시적 동의를 확인해야 합니다.
        </p>
      </section>}
    </details>
  );
}
