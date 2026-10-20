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
const caseTitles: Record<string, string> = {
  "s5-consistent": "정상 전략",
  "s5-condition-contradiction": "전략 조건 충돌",
  "s5-risk-contradiction": "위험 판단 충돌",
  "s5-insufficient-evidence": "근거 부족",
  "s5-unresolved-ambiguity": "해결되지 않는 모순",
};

function validResponse(value: JevSyntheticActualReport): boolean {
  return value.scope === "SYNTHETIC_ONLY"
    && value.real_stock_models_reviewed === 0
    && value.scanner_uplift_proven === false
    && value.model_calls_on_request === 0
    && value.external_requests_on_request === 0
    && value.db_writes_on_request === 0
    && value.provider_provenance === "LOCAL_JOURNAL_ORIGIN_CLAIM_NOT_CRYPTOGRAPHICALLY_ATTESTED"
    && value.paired_baseline?.scope === "AUTHOR_CREATED_SYNTHETIC_CASES_ONLY"
    && value.paired_baseline.unique_authored_cases === 5
    && value.paired_baseline.real_market_cases === 0
    && value.paired_baseline.naive_baseline_is_actual_scanner_algorithm === false
    && value.paired_baseline.actual_stock_comparison_available === false
    && value.paired_baseline.jev_incremental_market_value_proven === false
    && value.paired_baseline.external_calls === 0
    && value.paired_baseline.db_writes === 0
    && value.paired_baseline.rows.length === 5
    && value.paired_baseline.rows.every(r => Object.prototype.hasOwnProperty.call(caseTitles, r.case_id))
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
            <div className="scanner-jev-paired">
              <strong>독립적인 합성 문제별 비교 (S31-T)</strong>
              <p>
                원래 진입 후보를 전부 통과시키는 단순 가상 대조군과 실제 기록된 모델 판단을
                동일한 문제별로 비교했어요. 이 대조군은 실제 StockScope Scanner 알고리즘이 아닙니다.
              </p>
              {data.paired_baseline.full_case_coverage
                ? <p>
                    <strong>서로 다른 합성 문제 {data.paired_baseline.pairable_unique_cases}종</strong>
                    {" · "}모델의 기대 답안 일치 {data.paired_baseline.model_correct_paired}종
                    {" · "}단순 대조군 일치 {data.paired_baseline.naive_baseline_correct_paired}종
                    {" · "}일치 개수 차이 {data.paired_baseline.paired_gold_label_difference > 0 ? "+" : ""}
                    {data.paired_baseline.paired_gold_label_difference}종
                  </p>
                : <p>
                    <strong>비교 불충분: 독립 문제 {data.paired_baseline.pairable_unique_cases}/5종만 비교 가능.</strong>
                    중복 응답 불일치, 모델 종류 혼합, 검증 불가 기록, 미실행 문제,
                    기록 조회 범위 제한이 있는 경우 전체 비교 점수를 만들지 않습니다.
                  </p>
              }
              <p>
                호출 기록 {data.paired_baseline.raw_actual_attempts}건 중
                반복된 문제 {data.paired_baseline.repeated_cases}종.
                같은 문제가 여러 번 나와도 독립 사례 수는 늘어나지 않습니다.
              </p>
              <table>
                <thead><tr>
                  <th>합성 문제</th><th>단순 대조군</th><th>모델 기록</th><th>기대 답안</th><th>반복</th>
                </tr></thead>
                <tbody>{data.paired_baseline.rows.map(row => (
                  <tr key={row.case_id}>
                    <td>{caseTitles[row.case_id] ?? "미확인"}</td>
                    <td>{labels[row.baseline_choice]}</td>
                    <td>{row.status === "PAIRABLE"
                      ? labels[row.model_decision ?? ""] ?? "검증 불가"
                      : "비교 제외 (" + row.status + ")"}</td>
                    <td>{labels[row.gold]}</td>
                    <td>{row.attempt_count}건{row.repeat_stability === "AGREED_REPEATS"
                      ? " · 일치" : ""}</td>
                  </tr>
                ))}</tbody>
              </table>
              <small>
                이 평가는 사전에 정답을 만들어 둔 합성 문제의 분류 차이만 보여줍니다.
                모델이 기존 Scanner보다 새로운 종목 위험을 발견했다는 증거나
                매매 성과 개선 증거는 아닙니다.
              </small>
            </div>
            <details>
              <summary>개별 호출 기록 {data.actual_provider_attempts_recorded}건 펼쳐보기</summary>
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
            </details>
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
