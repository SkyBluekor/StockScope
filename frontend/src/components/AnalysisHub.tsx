import type { StrategyAnalysis } from "../services/api";

export type AnalysisSection = "summary" | "strategy" | "fundamental" | "investor_style" | "risk" | "relative" | "event" | "indicators";

const strategyNames: Record<string, string> = {
  trend_following: "추세추종",
  pullback: "눌림목",
  breakout: "돌파",
  support_bounce: "지지선 반등",
  oversold_bounce: "과매도 반등",
  range_trading: "박스권 매매",
  momentum_continuation: "모멘텀 지속",
  volatility_squeeze: "변동성 압축",
  ma20_rebound: "20일선 반등",
  trend_recovery: "추세 회복",
  no_trade: "매매 보류",
};

function checkIcon(status: string) {
  if (status === "PASS") return "✓";
  if (status === "FAIL") return "✕";
  if (status === "WARN") return "!";
  return "?";
}

function formatActionPrice(value: number) {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

export function AnalysisHub({
  analysis,
  activeSection,
  onNavigate,
}: {
  analysis: StrategyAnalysis;
  activeSection: AnalysisSection;
  onNavigate: (section: AnalysisSection) => void;
}) {
  const summary = analysis.analysis_summary;
  const entry = summary.entry_timing;
  const action = summary.action_plan;
  const topStrategyName = summary.top_strategy.strategy
    ? strategyNames[summary.top_strategy.strategy] ?? summary.top_strategy.strategy
    : "뚜렷한 우선 전략 없음";
  const primaryNavigation = summary.navigation.slice(0, 7);
  const moreNavigation = summary.navigation.slice(7);
  const moreNavigationActive = moreNavigation.some((item) => item.key === activeSection);

  return (
    <section className={`analysis-hub action-first readability-v02122 verdict-${summary.verdict_code.toLowerCase()}`}>
      <div className="analysis-action-hero analysis-action-hero-v02122">
        <div className="analysis-action-copy">
          <span>STOCKSCOPE ACTION PLAN · v0.18.2</span>
          <div className="analysis-current-decision-label">현재 판단</div>
          <strong className="analysis-current-decision">{action.label}</strong>
          <h3>{action.headline}</h3>
          <p>{action.summary}</p>
          <div className="analysis-decision-meta" aria-label="현재 판단 요약">
            <span>내 상황 · {summary.perspective}</span>
            {entry.relevant && <span>진입 조건 · {entry.progress.label}</span>}
            <span>Risk · {summary.risk_level}</span>
          </div>
        </div>
        <div className="analysis-hub-verdict analysis-hub-verdict-compact">
          <span>종합 판단</span>
          <strong>{summary.verdict_label}</strong>
          <em>세부 점수보다 현재 행동을 먼저 봅니다.</em>
        </div>
      </div>

      <section className="analysis-priority-section analysis-priority-compact" aria-labelledby="priority-heading">
        <div className="analysis-priority-head">
          <div>
            <span>현재 결정에 가장 중요한 이유</span>
            <strong id="priority-heading">핵심 3개만 먼저 확인하세요.</strong>
          </div>
          <small>나머지 근거는 아래에서 필요할 때 펼쳐볼 수 있습니다.</small>
        </div>
        <div className="analysis-priority-list">
          {summary.priority_signals.map((signal, index) => (
            <article className={`analysis-priority-row ${signal.status.toLowerCase()}`} key={signal.key}>
              <span className="analysis-priority-index">{index + 1}</span>
              <div className="analysis-priority-name">
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </div>
              <p>{signal.action_hint}</p>
            </article>
          ))}
        </div>
      </section>

      {action.decision_scenarios.length > 0 && (
        <section className="analysis-decision-scenarios analysis-decision-scenarios-v02122" aria-labelledby="decision-change-heading">
          <div className="analysis-section-heading">
            <span>다음 분석에서 다시 볼 조건</span>
            <strong id="decision-change-heading">무엇이 바뀌면 판단이 달라지나요?</strong>
          </div>
          <div className="analysis-decision-table" role="list">
            {action.decision_scenarios.map((scenario) => (
              <article className={scenario.tone.toLowerCase()} key={`${scenario.condition}-${scenario.effect}`} role="listitem">
                <div>
                  <small>조건</small>
                  <span>{scenario.condition}</span>
                </div>
                <b aria-hidden="true">→</b>
                <div>
                  <small>판단 변화</small>
                  <strong>{scenario.effect}</strong>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {action.price_levels.length > 0 && (
        <section className="analysis-price-levels analysis-price-levels-v02122" aria-labelledby="price-level-heading">
          <div className="analysis-price-levels-head">
            <strong id="price-level-heading">앱이 자동으로 보는 핵심 가격</strong>
            <span>사용자가 차트에서 직접 계산할 필요가 없습니다.</span>
          </div>
          <div>
            {action.price_levels.map((level) => (
              <article key={level.key}>
                <span>{level.label}</span>
                <strong>{formatActionPrice(level.price)}</strong>
                <p>{level.meaning}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      <details className="analysis-supporting-details">
        <summary>
          <span>
            <strong>보조 분석 보기</strong>
            <small>기업 조건, 전략 점수, 진입 타이밍과 행동 근거</small>
          </span>
          <b>펼쳐보기</b>
        </summary>

        <div className={`analysis-strategy-separation ${entry.relevant ? "entry-timing-compact-grid" : ""}`}>
          <div>
            <span>기업 조건</span>
            <strong>{entry.style_context.label || "투자스타일 분석"}</strong>
            <b>{entry.style_context.fit_label || "판단 보류"}{entry.style_context.score == null ? "" : ` · ${Math.round(entry.style_context.score)} / 100`}</b>
            <small>기업 자체의 스타일 적합도입니다. 단기 가격 타이밍과는 별도로 판정합니다.</small>
          </div>
          <div>
            <span>전략 형태 적합도</span>
            <strong>{topStrategyName}</strong>
            <b>{summary.top_strategy.score == null ? "점수 없음" : `${summary.top_strategy.score} / 100`}</b>
            <small>이 점수는 해당 전략의 형태와 얼마나 맞는지이며 진입 신호가 아닙니다.</small>
          </div>
          {entry.relevant && (
            <div className="entry-timing-compact">
              <span>단기 진입 타이밍</span>
              <strong>{entry.action.primary}</strong>
              <b>{entry.label} · {entry.progress.label}</b>
              <small>{entry.most_missing.length > 0 ? `가장 부족: ${entry.most_missing.join(" · ")}` : "현재 핵심 조건 확인 완료"}</small>
              <button type="button" onClick={() => onNavigate("strategy")}>진입 타이밍 상세</button>
            </div>
          )}
        </div>

        <div className="analysis-action-grid">
          <article className="do-now">
            <span>지금 할 것</span>
            {action.do_now.length > 0 ? (
              <ul>{action.do_now.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : (
              <p>현재 자동 분석에서 별도의 즉시 확인 항목은 없습니다.</p>
            )}
          </article>
          <article className="avoid-now">
            <span>지금 피할 것</span>
            {action.avoid_now.length > 0 ? (
              <ul>{action.avoid_now.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : (
              <p>현재 별도의 금지 조건은 계산되지 않았습니다.</p>
            )}
          </article>
        </div>

        {action.conflict.show && (
          <div className="analysis-conflict-explainer">
            <strong>{action.conflict.headline}</strong>
            <p>{action.conflict.summary}</p>
            {action.conflict.blockers.length > 0 && (
              <div>{action.conflict.blockers.map((item) => <span key={item}>{item}</span>)}</div>
            )}
          </div>
        )}
      </details>

      {summary.other_signals.length > 0 && (
        <details className="analysis-other-signals">
          <summary>
            <span>
              <strong>나머지 분석 결과 {summary.other_signals.length}개</strong>
              <small>현재 행동에 영향이 적은 결과입니다.</small>
            </span>
            <b>펼쳐보기</b>
          </summary>
          <div className="analysis-signal-grid">
            {summary.other_signals.map((signal) => (
              <article className={`analysis-signal ${signal.status.toLowerCase()}`} key={signal.key}>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
                <p>{signal.action_hint}</p>
                <small>{signal.detail}</small>
              </article>
            ))}
          </div>
        </details>
      )}

      <details className="analysis-evidence-summary">
        <summary>
          <span>
            <strong>왜 이런 결론이 나왔는지 더 보기</strong>
            <small>핵심 근거와 추가 판단 변경 조건</small>
          </span>
          <b>펼쳐보기</b>
        </summary>
        <div className="analysis-hub-explain">
          <article>
            <strong>핵심 근거</strong>
            {summary.key_reasons.length > 0 ? (
              <ul>{summary.key_reasons.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : <p>현재 자동 분석에서 추가 근거가 충분하지 않습니다.</p>}
          </article>
          <article>
            <strong>추가 판단 변경 조건</strong>
            {summary.change_conditions.length > 0 ? (
              <ul>{summary.change_conditions.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : <p>현재 주요 변경 조건이 계산되지 않았습니다.</p>}
          </article>
        </div>
      </details>

      <div className="analysis-detail-navigation-block">
        <div className="analysis-detail-navigation-head">
          <div>
            <span>전문 분석</span>
            <strong>궁금한 영역만 선택해서 확인하세요.</strong>
          </div>
        </div>
        <nav className="analysis-hub-nav analysis-hub-nav-v02122" aria-label="분석 상세 탐색">
          {primaryNavigation.map((item) => (
            <button
              type="button"
              key={item.key}
              className={activeSection === item.key ? "active" : ""}
              onClick={() => onNavigate(item.key as AnalysisSection)}
              title={item.description}
            >
              <strong>{item.label}</strong>
            </button>
          ))}
          {moreNavigation.length > 0 && (
            <details className={`analysis-hub-nav-more ${moreNavigationActive ? "active" : ""}`}>
              <summary>더보기</summary>
              <div>
                {moreNavigation.map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    className={activeSection === item.key ? "active" : ""}
                    onClick={() => onNavigate(item.key as AnalysisSection)}
                    title={item.description}
                  >
                    <strong>{item.label}</strong>
                  </button>
                ))}
              </div>
            </details>
          )}
        </nav>
      </div>

      {activeSection === "summary" && (
        <div className="analysis-hub-collapsed-note">
          <strong>세부 분석은 기본적으로 접혀 있습니다.</strong>
          <span>전문 분석에서 궁금한 영역만 선택하면 해당 분석만 표시됩니다.</span>
        </div>
      )}
    </section>
  );
}

export function AnalysisDetailHeader({
  title,
  description,
  onClose,
}: {
  title: string;
  description: string;
  onClose: () => void;
}) {
  return (
    <div className="analysis-detail-head">
      <div>
        <span>DETAIL VIEW</span>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <button type="button" onClick={onClose}>종합으로 돌아가기</button>
    </div>
  );
}

export function PullbackConfirmationPanel({
  analysis,
}: {
  analysis: StrategyAnalysis;
}) {
  const result = analysis.pullback_confirmation;
  const detail = result.entry_timing;
  const entry = analysis.analysis_summary.entry_timing;
  const auto = result.auto_check;
  const levelRows: Array<{ key: string; label: string; value: number | null | undefined; note: string }> = [
    { key: "current", label: "현재가", value: entry.levels.current_price, note: "현재 분석에 사용한 가격" },
    { key: "ma20", label: "20일선", value: entry.levels.ma20, note: "단기 추세와 눌림 위치 기준" },
    { key: "support", label: "주요 지지", value: entry.levels.support, note: "현재 자동 지지 판정 기준" },
    { key: "invalidation", label: "전략 무효화", value: entry.levels.invalidation, note: "이탈 시 현재 전략 전제 재평가" },
    { key: "rebound", label: "반등 확인 후보", value: entry.levels.rebound_confirmation, note: "관측된 가격으로 계산 가능한 경우만 표시" },
  ];

  return (
    <section className={`pullback-confirmation entry-timing-detail state-${result.state.toLowerCase()}`}>
      <div className="pullback-confirmation-head">
        <div>
          <span>ENTRY TIMING ACTION ENGINE · v0.18.2</span>
          <h3>단기 진입 타이밍</h3>
          <p>{entry.summary}</p>
        </div>
        <div>
          <span>{entry.basis_label}</span>
          <strong>{entry.label}</strong>
          <em>{entry.progress.label}</em>
        </div>
      </div>

      <div className="entry-timing-action-card">
        <div>
          <span>현재 행동 · {entry.action.perspective}</span>
          <strong>{entry.action.primary}</strong>
          <p>{entry.action.next}</p>
        </div>
        <div>
          <span>지금 피할 것</span>
          <strong>{entry.action.avoid}</strong>
          <p>{entry.action.recheck_note}</p>
        </div>
      </div>

      <div className="entry-timing-progress-card">
        <div className="entry-timing-progress-head">
          <div>
            <span>앱 자동 확인</span>
            <strong>{entry.progress.label}</strong>
          </div>
          <b>{entry.progress.percent}%</b>
        </div>
        <div className="analysis-progress-track" aria-label={entry.progress.label}>
          <span style={{ width: `${Math.max(0, Math.min(100, entry.progress.percent))}%` }} />
        </div>
        <small>{entry.policy}</small>
      </div>

      <div className="entry-timing-check-columns">
        <article className="confirmed">
          <div className="entry-timing-column-head">
            <span>확인됨</span>
            <strong>{entry.confirmed_checks.length}개</strong>
          </div>
          {entry.confirmed_checks.length > 0 ? (
            <ul>
              {entry.confirmed_checks.map((check) => (
                <li key={`confirmed-${check.key}`}>
                  <span>{checkIcon(check.status)}</span>
                  <div><strong>{check.label}</strong><small>{check.value}</small></div>
                </li>
              ))}
            </ul>
          ) : <p>아직 확정된 조건이 없습니다.</p>}
        </article>

        <article className={entry.failed_checks.length > 0 ? "missing failed" : "missing"}>
          <div className="entry-timing-column-head">
            <span>{entry.failed_checks.length > 0 ? "실패 / 아직 부족" : "아직 부족"}</span>
            <strong>{entry.failed_checks.length + entry.pending_checks.length}개</strong>
          </div>
          {[...entry.failed_checks, ...entry.pending_checks].length > 0 ? (
            <ul>
              {[...entry.failed_checks, ...entry.pending_checks].map((check) => (
                <li key={`missing-${check.key}`}>
                  <span>{checkIcon(check.status)}</span>
                  <div><strong>{check.label}</strong><small>{check.explanation}</small></div>
                </li>
              ))}
            </ul>
          ) : <p>현재 핵심 조건이 모두 확인됐습니다.</p>}
        </article>
      </div>

      {levelRows.some((level) => level.value != null) && (
        <div className="entry-timing-levels">
          <div className="entry-timing-levels-head">
            <strong>앱이 계산한 가격 기준</strong>
            <span>없는 값은 임의로 만들지 않습니다.</span>
          </div>
          <div>
            {levelRows.filter((level) => level.value != null).map((level) => (
              <article key={level.key}>
                <span>{level.label}</span>
                <strong>{formatActionPrice(level.value as number)}</strong>
                <p>{level.note}</p>
              </article>
            ))}
          </div>
        </div>
      )}

      {entry.style_context.label && (
        <div className="entry-style-context">
          <span>투자스타일과 단기 타이밍은 별도 축</span>
          <strong>{entry.style_context.label} · {entry.style_context.fit_label}{entry.style_context.score == null ? "" : ` ${Math.round(entry.style_context.score)}/100`}</strong>
          <p>{entry.style_context.summary}</p>
        </div>
      )}

      <details className="entry-timing-rules">
        <summary>
          <span>
            <strong>반등 조건 계산 규칙</strong>
            <small>가격·RSI·거래량을 StockScope가 어떻게 자동 판정하는지</small>
          </span>
          <b>규칙 보기</b>
        </summary>
        <div>
          {detail.rules.price_rebound && <article><span>가격 반등</span><strong>{detail.rules.price_rebound}</strong></article>}
          {detail.rules.rsi_recovery && <article><span>RSI 회복</span><strong>{detail.rules.rsi_recovery}</strong></article>}
          {detail.rules.volume_recovery && <article><span>거래량 회복</span><strong>{detail.rules.volume_recovery}</strong></article>}
        </div>
      </details>

      {auto.input_hints.length > 0 && (
        <div className="pullback-input-hints">
          <div>
            <strong>장중 Preview 정확도를 더 높일 수 있는 선택 입력</strong>
            <span>입력하지 않아도 다음 KRX 확정 데이터에서 StockScope가 자동 재판정합니다.</span>
          </div>
          <div>
            {auto.input_hints.map((hint) => (
              <article key={hint.field}>
                <b>{hint.label}</b>
                <span>{hint.reason}</span>
              </article>
            ))}
          </div>
        </div>
      )}

      <details className="pullback-all-checks">
        <summary>
          <span>
            <strong>전체 자동 확인 근거</strong>
            <small>상승 추세·눌림·지지·가격 반등·RSI·거래량 7개 조건</small>
          </span>
          <b>자세히 보기</b>
        </summary>
        <div className="pullback-check-grid">
          {result.checks.map((check) => (
            <article className={`pullback-check ${check.status.toLowerCase()}`} key={check.key}>
              <span>{checkIcon(check.status)}</span>
              <div>
                <strong>{check.label}</strong>
                <b>{check.value}</b>
                <p>{check.explanation}</p>
              </div>
              <em>{check.source === "USER_INPUT" ? "현재 입력" : "KRX EOD"}</em>
            </article>
          ))}
        </div>
      </details>

      <div className="pullback-policy">{result.policy}</div>
    </section>
  );
}
