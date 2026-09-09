import { useEffect, useMemo, useState } from "react";
import type { StrategyAnalysis } from "../services/api";
import { TermHelp } from "./BeginnerHelp";

type StyleCode = "BUFFETT" | "GRAHAM" | "LYNCH" | "CAN_SLIM";
type StyleChoice = "AUTO" | StyleCode;

const styleColors: Record<StyleCode, string> = {
  BUFFETT: "buffett",
  GRAHAM: "graham",
  LYNCH: "lynch",
  CAN_SLIM: "canslim",
};

function statusIcon(status: string) {
  if (status === "PASS") return "✓";
  if (status === "WARN") return "△";
  if (status === "FAIL") return "✕";
  return "?";
}

function fitClass(fit: string) {
  if (fit === "VERY_HIGH" || fit === "HIGH") return "positive";
  if (fit === "MEDIUM") return "caution";
  if (fit === "LOW" || fit === "VERY_LOW") return "negative";
  return "neutral";
}

function judgmentClass(status: string) {
  if (status === "GOOD" || status === "REVIEW") return "positive";
  if (status === "CAUTION" || status === "WAIT") return "caution";
  if (status === "WEAK" || status === "RISK_FIRST") return "negative";
  return "neutral";
}

export function InvestorStylePanel({ analysis }: { analysis: StrategyAnalysis }) {
  const data = analysis.investor_style;
  const [selected, setSelected] = useState<StyleChoice>("AUTO");
  const [quiz, setQuiz] = useState({ priority: "", monitoring: "", decline: "" });

  useEffect(() => setSelected("AUTO"), [analysis.code, analysis.data_date]);

  const styles = data.styles;
  const activeCode = selected === "AUTO" ? data.top_style?.code ?? styles[0]?.code : selected;
  const active = styles.find((style) => style.code === activeCode) ?? styles[0];

  const personalMatch = useMemo(() => {
    const scores: Record<StyleCode, number> = { BUFFETT: 0, GRAHAM: 0, LYNCH: 0, CAN_SLIM: 0 };
    const add = (code: StyleCode, points: number) => { scores[code] += points; };

    if (quiz.priority === "quality") { add("BUFFETT", 4); add("LYNCH", 1); }
    if (quiz.priority === "value") { add("GRAHAM", 4); add("BUFFETT", 1); }
    if (quiz.priority === "growth") { add("LYNCH", 4); add("CAN_SLIM", 2); }
    if (quiz.priority === "momentum") { add("CAN_SLIM", 4); add("LYNCH", 1); }

    if (quiz.monitoring === "low") { add("BUFFETT", 3); add("GRAHAM", 2); }
    if (quiz.monitoring === "medium") { add("LYNCH", 3); add("BUFFETT", 1); }
    if (quiz.monitoring === "high") { add("CAN_SLIM", 3); add("LYNCH", 1); }

    if (quiz.decline === "quality_opportunity") add("BUFFETT", 3);
    if (quiz.decline === "value_discount") add("GRAHAM", 3);
    if (quiz.decline === "growth_break") add("LYNCH", 3);
    if (quiz.decline === "momentum_break") add("CAN_SLIM", 3);

    const complete = Boolean(quiz.priority && quiz.monitoring && quiz.decline);
    const ranked = (Object.entries(scores) as Array<[StyleCode, number]>).sort((a, b) => b[1] - a[1]);
    return { complete, ranked };
  }, [quiz]);

  if (!data.available || !active) {
    return (
      <section className="investor-style-panel unavailable">
        <div className="investor-style-head">
          <div><span>INVESTOR STYLE ENGINE · v0.18.2.1</span><h3>투자 스타일 분석</h3></div>
        </div>
        <p>{data.message}</p>
      </section>
    );
  }

  const missing = active.action_plan.entry_judgment.missing ?? [];
  const missingLabel = missing.length > 0 ? missing.slice(0, 3).join(" · ") : "현재 핵심 조건 확인 완료";

  return (
    <section className="investor-style-panel style-ux-compressed">
      <div className="investor-style-head">
        <div>
          <span>INVESTOR STYLE ACTION ENGINE + ENTRY TIMING · v0.18.2.1</span>
          <h3>이 종목은 어떤 투자 방식과 잘 맞나?</h3>
          <p>기업 자체의 장기 적합성과 지금 진입하기 좋은 가격 타이밍을 분리해서 봅니다.</p>
        </div>
        <div className="investor-style-top">
          <span>현재 종목 최상위</span>
          <strong>{data.top_style?.label ?? "판단 보류"}</strong>
          <b>{data.top_style?.score == null ? "점수 없음" : `${Math.round(data.top_style.score)} / 100 · ${data.top_style.fit_label}`}</b>
          <small>스타일 적합도이며 상승확률이 아닙니다.</small>
        </div>
      </div>

      <div className="style-ranking-toolbar">
        <div>
          <strong>종목 적합도 순위</strong>
          <span>{selected === "AUTO" ? "StockScope가 최상위 스타일을 자동 선택 중" : `${active.short_label} 관점으로 직접 비교 중`}</span>
        </div>
        <button className={selected === "AUTO" ? "active" : ""} type="button" onClick={() => setSelected("AUTO")}>StockScope 자동</button>
      </div>

      <div className="style-ranking-strip">
        {data.comparison.map((item, index) => (
          <button
            type="button"
            key={item.code}
            className={`${fitClass(styles.find((style) => style.code === item.code)?.fit ?? "UNKNOWN")} ${activeCode === item.code ? "selected" : ""}`}
            onClick={() => setSelected(item.code)}
          >
            <span>{index + 1}위</span>
            <strong>{item.label}</strong>
            <b>{item.score == null ? "판단 보류" : `${Math.round(item.score)}점 · ${item.fit_label}`}</b>
          </button>
        ))}
      </div>

      <details className="style-comparison-details">
        <summary><span><strong>네 투자 방식의 차이 보기</strong><small>좋은 기업·가치·성장·시장 주도력 중 무엇을 우선하는지 비교합니다.</small></span><b>펼치기</b></summary>
        <div className="style-difference-grid">
          <article><b>Buffett</b><span>좋은 기업</span><p>기업의 질과 장기 현금창출력을 우선하고 가격이 과하지 않은지 봅니다.</p></article>
          <article><b>Graham</b><span>충분히 싼 가격</span><p>재무가 버틸 수 있는 기업을 안전마진이 있는 가격에 사는 데 초점을 둡니다.</p></article>
          <article><b>Lynch</b><span>성장과 가격의 균형</span><p>잘 성장하는 기업을 찾되 성장속도에 비해 가격 기대가 너무 높지 않은지 봅니다.</p></article>
          <article><b>CAN SLIM</b><span>실적 + 시장 주도력</span><p>최근 실적 성장과 강한 상대강도·거래량·시장 방향을 함께 확인합니다.</p></article>
        </div>
      </details>

      <section className={`style-playbook ${styleColors[active.code]}`}>
        <div className="style-playbook-title compact">
          <div>
            <span>{active.label.toUpperCase()} PLAYBOOK</span>
            <h4>{active.overview.core}</h4>
            <p>{active.overview.philosophy}</p>
          </div>
          <div className={fitClass(active.fit)}>
            <span>이 종목 적합도</span>
            <strong>{active.score == null ? "-" : Math.round(active.score)}</strong>
            <b>{active.fit_label}</b>
            <small>평가 커버리지 {active.coverage.percent}%</small>
          </div>
        </div>

        <section className={`style-primary-action ${judgmentClass(active.action_plan.entry_judgment.status)}`}>
          <div className="style-primary-action-head">
            <div>
              <span>{active.short_label.toUpperCase()} 관점 현재 행동</span>
              <strong>{active.action_plan.current_action}</strong>
            </div>
            {active.action_plan.blockers.length > 0
              ? <b className="style-blocker-badge warning">제한 요소 {active.action_plan.blockers.length}개</b>
              : <b className="style-blocker-badge clear">큰 제한 요소 없음</b>}
          </div>

          <div className="style-primary-metrics">
            <article className={judgmentClass(active.action_plan.company_judgment.status)}>
              <span>기업 조건</span>
              <strong>{active.action_plan.company_judgment.value}</strong>
              <small>{active.action_plan.company_judgment.summary}</small>
            </article>
            <article className={judgmentClass(active.action_plan.entry_judgment.status)}>
              <span>단기 타이밍</span>
              <strong>{active.action_plan.entry_judgment.value}</strong>
              <small>{active.action_plan.entry_judgment.progress_label ?? "자동 판정 중"}</small>
            </article>
            <article className={missing.length > 0 ? "caution" : "positive"}>
              <span>가장 부족</span>
              <strong>{missingLabel}</strong>
              <small>{missing.length > 3 ? `외 ${missing.length - 3}개 조건` : "다음 데이터에서 자동 재판정"}</small>
            </article>
          </div>

          {active.action_plan.entry_judgment.timing_note && (
            <p className="style-primary-timing-note">단기 타이밍 중요도 {active.action_plan.entry_judgment.timing_importance ?? "참고"} · {active.action_plan.entry_judgment.timing_note}</p>
          )}
        </section>

        <details className="style-auto-verdicts style-summary-details">
          <summary>
            <span><strong>기업 분석 결과 보기</strong><small>성장성·가격·재무 안정성·현금흐름은 앱이 이미 자동 판정했습니다.</small></span>
            <b>펼치기</b>
          </summary>
          <div className="style-auto-verdict-grid">
            {active.action_plan.judgments.map((item) => (
              <article className={judgmentClass(item.status)} key={item.key}>
                <span>{item.label}</span>
                <strong>{item.status_label}</strong>
                <p>{item.summary}</p>
              </article>
            ))}
          </div>
        </details>

        <details className="style-action-plan style-summary-details">
          <summary>
            <span><strong>현재 행동과 판단 변경 조건</strong><small>지금 할 일, 앱이 자동 재확인할 항목, 결론이 바뀌는 조건을 한곳에 모았습니다.</small></span>
            <b>펼치기</b>
          </summary>
          <div className="style-action-grid compressed-action-grid">
            <article>
              <b>지금 사용자 행동</b>
              <ul>{active.action_plan.do_now.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
            <article className="auto-monitor">
              <b>앱 자동 재확인</b>
              <ul>
                {active.action_plan.auto_monitor.map((item) => (
                  <li key={item.label}>
                    <strong>{item.label}</strong>
                    <span>{item.current}</span>
                    <small>{item.effect}</small>
                  </li>
                ))}
              </ul>
            </article>
            <article className="recheck">
              <b>판단이 바뀌는 조건</b>
              <ul>
                {active.action_plan.decision_scenarios.map((item) => (
                  <li key={`${item.condition}-${item.effect}`}>
                    <strong>{item.condition}</strong>
                    <span>→ {item.effect}</span>
                  </li>
                ))}
              </ul>
            </article>
          </div>
          <p className="style-automation-note">{active.action_plan.automation_note}</p>
        </details>

        {(active.action_plan.reasons.length > 0 || active.action_plan.blockers.length > 0) && (
          <details className="style-reason-details style-summary-details">
            <summary>
              <span><strong>왜 이렇게 판단했나?</strong><small>현재 결론의 핵심 근거와 행동 제한 요소를 확인합니다.</small></span>
              <b>근거 보기</b>
            </summary>
            <div className="style-decision-reasons">
              <article>
                <strong>판단 근거</strong>
                <ul>{active.action_plan.reasons.map((item) => <li key={item}>{item}</li>)}</ul>
              </article>
              <article className={active.action_plan.blockers.length ? "has-blockers" : "no-blockers"}>
                <strong>{active.action_plan.blockers.length ? "현재 행동을 제한하는 요소" : "큰 제한 요소 없음"}</strong>
                {active.action_plan.blockers.length
                  ? <ul>{active.action_plan.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
                  : <p>현재 자동판정에서 강한 제한 요소가 없습니다.</p>}
              </article>
            </div>
          </details>
        )}

        {active.company_type && (
          <div className="style-company-type"><span>Lynch 관점 기업 성격</span><strong>{active.company_type}</strong></div>
        )}

        <details className="style-company-fit style-company-fit-details">
          <summary><span><strong>스타일 적합도 판단 근거</strong><small>강점·약점은 앱이 이미 자동 분류했습니다.</small></span><b>근거 보기</b></summary>
          <div>
            <article>
              <b>잘 맞는 근거</b>
              {active.company_fit.strengths.length ? <ul>{active.company_fit.strengths.map((item) => <li key={item}>{item}</li>)}</ul> : <p>강하게 충족된 조건이 아직 부족합니다.</p>}
            </article>
            <article className="weakness">
              <b>부족한 부분</b>
              {active.company_fit.weaknesses.length ? <ul>{active.company_fit.weaknesses.map((item) => <li key={item}>{item}</li>)}</ul> : <p>현재 자동평가에서 뚜렷한 미충족 조건은 적습니다.</p>}
              {active.company_fit.unknowns.length > 0 && <small>평가 불가: {active.company_fit.unknowns.join(" · ")}</small>}
            </article>
          </div>
        </details>

        <details className="style-playbook-learning">
          <summary>
            <span><strong>이 투자 방식 자체를 이해하고 싶다면</strong><small>{active.overview.core}</small></span>
            <b>Playbook 보기</b>
          </summary>
          <div className="style-explainer-grid">
            <article>
              <strong>StockScope는 이 순서로 자동 분석</strong>
              <ol>{active.overview.process.map((item) => <li key={item}>{item}</li>)}</ol>
            </article>
            <article>
              <strong>이런 사용자에게 잘 맞음</strong>
              <ul>{active.overview.suited_for.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
            <article className="less-suited">
              <strong>이런 경우에는 덜 맞음</strong>
              <ul>{active.overview.less_suited_for.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
          </div>
        </details>

        <details className="style-condition-details">
          <summary><span><strong>평가 조건 자세히 보기</strong><small>UNKNOWN은 0점 벌점으로 처리하지 않습니다.</small></span><b>펼치기</b></summary>
          <div className="style-condition-grid">
            {active.conditions.map((condition) => (
              <article className={condition.status.toLowerCase()} key={condition.key}>
                <span>{statusIcon(condition.status)}</span>
                <div><strong>{condition.label}</strong><b>{condition.value}</b><p>{condition.explanation}</p><small>평가 가중치 {condition.weight}/100</small></div>
              </article>
            ))}
          </div>
        </details>
      </section>

      <details className="style-personal-fit">
        <summary><span><strong>나에게 맞는 투자방식도 알아보기</strong><small>세 질문으로 투자 성향의 방향만 간단히 비교합니다.</small></span><b>열기</b></summary>
        <div className="style-quiz-body">
          <fieldset>
            <legend>1. 투자할 때 가장 중요하게 보고 싶은 것은?</legend>
            {[
              ["quality", "좋은 기업을 오래 보유"], ["value", "충분히 싸게 사는 것"],
              ["growth", "잘 성장하는 기업"], ["momentum", "강하게 움직이는 시장 주도주"],
            ].map(([value, label]) => <button type="button" className={quiz.priority === value ? "active" : ""} key={value} onClick={() => setQuiz((q) => ({ ...q, priority: value }))}>{label}</button>)}
          </fieldset>
          <fieldset>
            <legend>2. 시장과 종목을 얼마나 자주 확인하고 싶은가?</legend>
            {[["low", "가끔 확인"], ["medium", "주기적으로 확인"], ["high", "시장 움직임을 자주 확인"]].map(([value, label]) => <button type="button" className={quiz.monitoring === value ? "active" : ""} key={value} onClick={() => setQuiz((q) => ({ ...q, monitoring: value }))}>{label}</button>)}
          </fieldset>
          <fieldset>
            <legend>3. 주가가 내려갈 때 가장 먼저 생각하는 것은?</legend>
            {[
              ["quality_opportunity", "좋은 기업이면 가격 기회인지 확인"], ["value_discount", "가치보다 충분히 싸졌는지 확인"],
              ["growth_break", "성장성이 훼손됐는지 확인"], ["momentum_break", "가격·시장 흐름이 꺾였는지 확인"],
            ].map(([value, label]) => <button type="button" className={quiz.decline === value ? "active" : ""} key={value} onClick={() => setQuiz((q) => ({ ...q, decline: value }))}>{label}</button>)}
          </fieldset>

          {personalMatch.complete ? (
            <div className="style-quiz-result">
              <span>선택한 성향과 가까운 방식</span>
              <strong>{styles.find((style) => style.code === personalMatch.ranked[0][0])?.label}</strong>
              <p>2순위: {styles.find((style) => style.code === personalMatch.ranked[1][0])?.label}</p>
              <small>이 결과는 투자성향을 단순화한 학습용 안내이며 수익 가능성이나 적합한 금융상품을 판단하는 설문이 아닙니다.</small>
            </div>
          ) : <p className="style-quiz-placeholder">세 질문을 모두 고르면 어떤 철학과 가까운지 보여줍니다.</p>}
        </div>
      </details>

      <details className="style-policy style-policy-details">
        <summary><strong className="term-inline">해석 원칙 <TermHelp term="investment_style_fit" /></strong><b>보기</b></summary>
        <p>{data.policy}</p>
      </details>
    </section>
  );
}
