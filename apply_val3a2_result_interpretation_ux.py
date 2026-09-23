from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

WORKSPACE = FRONTEND / "src" / "components" / "SimulationWorkspace.tsx"
CSS = FRONTEND / "src" / "simulation.css"
SERVICE = FRONTEND / "src" / "services" / "simulationApi.ts"
OUTCOME = BACKEND / "app" / "simulation" / "validation_outcome.py"
CATALOG = BACKEND / "app" / "simulation" / "validation_catalog.py"
API = BACKEND / "app" / "api" / "simulation.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
PACKAGE = FRONTEND / "package.json"

OLD_HELPERS = 'function pctText(value: number | null | undefined) {\n  if (value == null || !Number.isFinite(value)) return "-";\n  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;\n}\nfunction touchText(value: { touched_count: number; comparable_count: number; touched_pct: number | null }) {\n  if (value.comparable_count <= 0) return "비교 기준 없음";\n  const rate = value.touched_pct == null ? "-" : `${value.touched_pct.toFixed(1)}%`;\n  return `${value.touched_count} / ${value.comparable_count} · ${rate}`;\n}\n'
NEW_HELPERS = 'function pctText(value: number | null | undefined) {\n  if (value == null || !Number.isFinite(value)) return "-";\n  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;\n}\nfunction countText(value: number | null | undefined) {\n  return `${Number(value ?? 0).toLocaleString("ko-KR")}건`;\n}\nfunction touchText(value: { touched_count: number; comparable_count: number; touched_pct: number | null }) {\n  if (value.comparable_count <= 0) return "비교 기준 없음";\n  const rate = value.touched_pct == null ? "-" : `${value.touched_pct.toFixed(1)}%`;\n  return `${value.touched_count.toLocaleString("ko-KR")} / ${value.comparable_count.toLocaleString("ko-KR")}건 · ${rate}`;\n}\nfunction averageMedianNote(average: number | null | undefined, median: number | null | undefined) {\n  if (average == null || median == null || !Number.isFinite(average) || !Number.isFinite(median)) {\n    return "평균과 중앙값은 확인 가능한 표본만 사용합니다.";\n  }\n  const gap = average - median;\n  if (Math.abs(gap) < 0.005) {\n    return "평균과 중앙값이 거의 같습니다. 두 값 모두 결과 분포를 이해할 때 함께 확인합니다.";\n  }\n  return `평균은 중앙값보다 ${Math.abs(gap).toFixed(2)}%p ${gap > 0 ? "높습니다" : "낮습니다"}. 큰 상승·하락 사례가 평균에 영향을 줄 수 있으므로 두 값을 함께 확인합니다.`;\n}\n'
OLD_BLOCK = '            </div>\n\n            {selectedDraft.status === "COMPLETED" && <div className="sim-outcome-status">\n              <div className="sim-outcome-head">\n                <div>\n                  <span className="sim-section-kicker">후보 실제 결과</span>\n                  <h4>성과 평가</h4>\n                  <p>추천 당일은 제외하고 D+1~D+20 확정 일봉만 사용합니다. 실제 주문 체결을 의미하지 않습니다.</p>\n                </div>\n                <button className="sim-secondary" disabled={outcomeBusy} onClick={() => void calculateOutcomes(selectedDraft)}>\n                  {outcomeBusy ? "계산 중…" : outcomeSummary?.status === "READY" ? "성과 갱신" : "성과 계산"}\n                </button>\n              </div>\n\n              {outcomeBusy && !outcomeSummary ? <div className="sim-empty">성과 정보를 확인하는 중…</div> :\n              outcomeSummary?.status !== "READY" ? <div className="sim-outcome-summary">\n                <div><span>과거 판단 재현</span><strong>{selectedDraft.processed_day_count} / {selectedDraft.trading_day_count} 거래일</strong></div>\n                <div><span>저장된 후보</span><strong>{selectedDraft.candidate_count}</strong></div>\n                <div><span>성과 평가</span><strong>아직 계산하지 않음</strong></div>\n                <div><span>평가 구간</span><strong>D+1 ~ D+20</strong></div>\n              </div> : <>\n                <div className="sim-outcome-summary">\n                  <div><span>과거 판단 재현</span><strong>{outcomeSummary.replay.processed_trading_days} / {outcomeSummary.replay.target_trading_days} 거래일</strong><small>{outcomeSummary.replay.consistent === false ? "저장 건수 확인 필요" : "재현 완료"}</small></div>\n                  <div><span>전체 후보</span><strong>{outcomeSummary.total_candidates}</strong></div>\n                  <div><span>5D 평가 가능</span><strong>{outcomeSummary.horizons["5d"].sample_count}</strong></div>\n                  <div><span>20D 평가 가능</span><strong>{outcomeSummary.horizons["20d"].sample_count}</strong></div>\n                </div>\n                <div className="sim-outcome-returns">\n                  <div><span>5D 평균</span><strong>{pctText(outcomeSummary.horizons["5d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["5d"].sample_count}</small></div>\n                  <div><span>10D 평균</span><strong>{pctText(outcomeSummary.horizons["10d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["10d"].sample_count}</small></div>\n                  <div><span>20D 평균</span><strong>{pctText(outcomeSummary.horizons["20d"].average_pct)}</strong><small>표본 {outcomeSummary.horizons["20d"].sample_count}</small></div>\n                  <div><span>20D 중앙값</span><strong>{pctText(outcomeSummary.horizons["20d"].median_pct)}</strong><small>MFE 평균 {pctText(outcomeSummary.mfe_20d.average_pct)} · MAE 평균 {pctText(outcomeSummary.mae_20d.average_pct)}</small></div>\n                </div>\n                <table className="sim-outcome-touch">\n                  <thead><tr><th>가격 조건 관측</th><th>도달 / 비교 가능</th></tr></thead>\n                  <tbody>\n                    <tr><td>진입 가격 조건</td><td>{touchText(outcomeSummary.touches.entry)}</td></tr>\n                    <tr><td>손절 기준</td><td>{touchText(outcomeSummary.touches.stop)}</td></tr>\n                    <tr><td>1차 목표</td><td>{touchText(outcomeSummary.touches.target1)}</td></tr>\n                    <tr><td>2차 목표</td><td>{touchText(outcomeSummary.touches.target2)}</td></tr>\n                  </tbody>\n                </table>\n                <p className="sim-outcome-footnote">같은 일봉에서 손절·목표가 모두 닿으면 둘 다 기록하며 어떤 가격이 먼저 닿았는지는 추론하지 않습니다. 최근 후보의 10D·20D 데이터가 아직 없으면 해당 표본에서 제외됩니다.</p>\n              </>}\n            </div>}\n          </div>}\n\n          <div className="sim-saved-group sim-legacy-group">\n'
NEW_BLOCK = '            </div>\n\n            {selectedDraft.status === "COMPLETED" && <div className="sim-outcome-status">\n              <div className="sim-outcome-head">\n                <div>\n                  <span className="sim-section-kicker">후보 실제 결과</span>\n                  <h4>검증 결과</h4>\n                  <p>과거에 저장한 Scanner 후보가 이후 확정 일봉에서 어떻게 움직였는지 확인합니다.</p>\n                </div>\n                <div className="sim-outcome-refresh">\n                  <button className="sim-secondary" disabled={outcomeBusy} onClick={() => void calculateOutcomes(selectedDraft)}>\n                    {outcomeBusy ? "계산 중…" : outcomeSummary?.status === "READY" ? "성과 갱신" : "성과 계산"}\n                  </button>\n                  <small>새 거래일이 추가되면 최근 후보의 결과만 다시 계산합니다. Scanner 판단은 바뀌지 않습니다.</small>\n                </div>\n              </div>\n\n              {outcomeBusy && !outcomeSummary ? <div className="sim-empty">성과 정보를 확인하는 중…</div> :\n              outcomeSummary?.status !== "READY" ? <section className="sim-outcome-section">\n                <h5>아직 성과를 계산하지 않았습니다.</h5>\n                <p>\n                  과거 {selectedDraft.processed_day_count.toLocaleString("ko-KR")}거래일의 분석은 완료되었고,\n                  당시 포착한 후보는 {selectedDraft.candidate_count.toLocaleString("ko-KR")}건입니다.\n                  성과 계산을 누르면 각 후보의 다음 거래일부터 최대 20거래일까지 가격 변화를 확인합니다.\n                </p>\n                <p className="sim-outcome-note">실제 주문이나 체결을 가정하지 않고 Market Store의 확정 일봉만 사용합니다.</p>\n              </section> : <>\n                <section className="sim-outcome-section sim-outcome-overview">\n                  <span className="sim-section-kicker">한눈에 보기</span>\n                  <h5>검증 결과 요약</h5>\n                  <p>\n                    과거 {outcomeSummary.replay.processed_trading_days.toLocaleString("ko-KR")}거래일의 Scanner 판단을 다시 확인했고,\n                    당시 포착한 후보는 총 <strong>{countText(outcomeSummary.total_candidates)}</strong>입니다.\n                    그중 <strong>{countText(outcomeSummary.horizons["20d"].sample_count)}</strong>은\n                    20거래일 뒤까지 결과를 확인할 수 있습니다.\n                  </p>\n                  <p>\n                    20거래일 뒤 평균 가격 변화는 <strong>{pctText(outcomeSummary.horizons["20d"].average_pct)}</strong>,\n                    중앙값은 <strong>{pctText(outcomeSummary.horizons["20d"].median_pct)}</strong>입니다.\n                    {" "}{averageMedianNote(outcomeSummary.horizons["20d"].average_pct, outcomeSummary.horizons["20d"].median_pct)}\n                  </p>\n                  <p className="sim-outcome-note">\n                    이 수치는 실제 매매 수익률이 아니라 후보 포착 당일 종가를 기준으로 이후 확정 일봉의 가격 변화를 측정한 값입니다.\n                  </p>\n                </section>\n\n                <section className="sim-outcome-section">\n                  <h5>과거 분석 범위</h5>\n                  <dl className="sim-outcome-facts">\n                    <div><dt>과거 분석</dt><dd>{outcomeSummary.replay.processed_trading_days.toLocaleString("ko-KR")}거래일 모두 확인</dd></div>\n                    <div><dt>과거에 포착한 후보</dt><dd>{countText(outcomeSummary.total_candidates)}</dd></div>\n                    <div><dt>20거래일 뒤까지 확인</dt><dd>{countText(outcomeSummary.horizons["20d"].sample_count)} / {countText(outcomeSummary.total_candidates)}</dd></div>\n                  </dl>\n                  <p className="sim-outcome-note">\n                    같은 종목이 여러 거래일에 다시 포착된 경우 각각 한 건으로 계산합니다.\n                    최근에 포착된 후보는 아직 20거래일이 지나지 않아 장기 결과 표본에서 제외될 수 있습니다.\n                  </p>\n                </section>\n\n                <section className="sim-outcome-section">\n                  <h5>이후 가격 변화</h5>\n                  <table className="sim-outcome-table">\n                    <thead>\n                      <tr><th>확인 시점</th><th>평균 가격 변화</th><th>중앙값</th><th>확인 가능한 후보</th></tr>\n                    </thead>\n                    <tbody>\n                      <tr>\n                        <td>5거래일 뒤</td>\n                        <td>{pctText(outcomeSummary.horizons["5d"].average_pct)}</td>\n                        <td>{pctText(outcomeSummary.horizons["5d"].median_pct)}</td>\n                        <td>{countText(outcomeSummary.horizons["5d"].sample_count)}</td>\n                      </tr>\n                      <tr>\n                        <td>10거래일 뒤</td>\n                        <td>{pctText(outcomeSummary.horizons["10d"].average_pct)}</td>\n                        <td>{pctText(outcomeSummary.horizons["10d"].median_pct)}</td>\n                        <td>{countText(outcomeSummary.horizons["10d"].sample_count)}</td>\n                      </tr>\n                      <tr>\n                        <td>20거래일 뒤</td>\n                        <td>{pctText(outcomeSummary.horizons["20d"].average_pct)}</td>\n                        <td>{pctText(outcomeSummary.horizons["20d"].median_pct)}</td>\n                        <td>{countText(outcomeSummary.horizons["20d"].sample_count)}</td>\n                      </tr>\n                    </tbody>\n                  </table>\n                  <div className="sim-outcome-explain">\n                    <strong>평균과 중앙값은 왜 같이 보나요?</strong>\n                    <p>평균은 모든 후보의 값을 합쳐 계산해 큰 상승·하락 사례의 영향을 받을 수 있습니다. 중앙값은 결과를 순서대로 놓았을 때 가운데에 있는 값입니다.</p>\n                    <p>{averageMedianNote(outcomeSummary.horizons["20d"].average_pct, outcomeSummary.horizons["20d"].median_pct)}</p>\n                  </div>\n                </section>\n\n                <section className="sim-outcome-section">\n                  <h5>20거래일 동안의 가격 움직임</h5>\n                  <dl className="sim-outcome-movement">\n                    <div>\n                      <dt>평균 최고 상승폭</dt>\n                      <dd>{pctText(outcomeSummary.mfe_20d.average_pct)}</dd>\n                      <small>각 후보가 기준가보다 가장 많이 올랐던 순간을 평균한 값</small>\n                    </div>\n                    <div>\n                      <dt>평균 최대 하락폭</dt>\n                      <dd>{pctText(outcomeSummary.mae_20d.average_pct)}</dd>\n                      <small>각 후보가 기준가보다 가장 많이 내려갔던 순간을 평균한 값</small>\n                    </div>\n                  </dl>\n                </section>\n\n                <section className="sim-outcome-section">\n                  <h5>20거래일 안에 가격 기준에 닿은 경우</h5>\n                  <p className="sim-outcome-warning">\n                    이 수치는 성공률이나 손실률이 아닙니다. 해당 기간에 그 가격에 한 번이라도 닿았는지를 센 값입니다.\n                  </p>\n                  <table className="sim-outcome-table sim-outcome-touch">\n                    <thead><tr><th>가격 기준</th><th>도달한 후보 / 비교 가능한 후보</th></tr></thead>\n                    <tbody>\n                      <tr><td>진입 관찰 가격</td><td>{touchText(outcomeSummary.touches.entry)}</td></tr>\n                      <tr><td>손절 기준 가격</td><td>{touchText(outcomeSummary.touches.stop)}</td></tr>\n                      <tr><td>1차 목표 가격</td><td>{touchText(outcomeSummary.touches.target1)}</td></tr>\n                      <tr><td>2차 목표 가격</td><td>{touchText(outcomeSummary.touches.target2)}</td></tr>\n                    </tbody>\n                  </table>\n                  <div className="sim-outcome-explain">\n                    <strong>진입 관찰 가격은 무엇인가요?</strong>\n                    <p>Scanner가 당시 제시한 진입 가격 범위 또는 조건에 이후 20거래일 동안 실제 가격이 닿았는지를 뜻합니다. 실제 매수 체결을 의미하지 않습니다.</p>\n                  </div>\n                  <p className="sim-outcome-note">\n                    같은 후보가 손절 기준과 목표 가격에 모두 포함될 수 있습니다.\n                    같은 일봉에서 두 가격에 모두 닿았더라도 일봉 데이터만으로 어느 가격이 먼저였는지는 알 수 없으므로 순서를 추정하지 않습니다.\n                  </p>\n                </section>\n\n                <details className="sim-outcome-method">\n                  <summary>검증 방법 보기</summary>\n                  <dl>\n                    <div><dt>기준 가격</dt><dd>후보 포착 당일 종가</dd></div>\n                    <div><dt>결과 관찰 시작</dt><dd>다음 거래일 (D+1)</dd></div>\n                    <div><dt>관찰 기간</dt><dd>최대 20거래일</dd></div>\n                    <div><dt>가격 데이터</dt><dd>Market Store 확정 일봉</dd></div>\n                    <div><dt>실제 주문 가정</dt><dd>하지 않음</dd></div>\n                    <div><dt>같은 일봉의 손절·목표 순서</dt><dd>추정하지 않음</dd></div>\n                  </dl>\n                </details>\n              </>}\n            </div>}\n          </div>}\n\n          <div className="sim-saved-group sim-legacy-group">\n'
CSS_APPEND = '\n/* VAL.3-A2 — result interpretation UX */\n.sim-outcome-refresh {\n  display: flex;\n  max-width: 360px;\n  flex-direction: column;\n  align-items: flex-end;\n  gap: 6px;\n}\n.sim-outcome-refresh small {\n  color: var(--text-muted);\n  font-size: var(--font-badge);\n  line-height: 1.45;\n  text-align: right;\n}\n.sim-outcome-section {\n  margin-top: 18px;\n  padding-top: 17px;\n  border-top: 1px solid var(--border-default);\n}\n.sim-outcome-section h5 {\n  margin: 0 0 9px;\n  color: var(--text-primary);\n  font-size: var(--font-body);\n}\n.sim-outcome-section > p {\n  max-width: 960px;\n  margin: 6px 0 0;\n  color: var(--text-secondary);\n  font-size: var(--font-meta);\n  line-height: 1.65;\n}\n.sim-outcome-overview strong {\n  color: var(--text-primary);\n  font-weight: 850;\n}\n.sim-outcome-note {\n  color: var(--text-muted) !important;\n}\n.sim-outcome-warning {\n  padding-left: 10px;\n  border-left: 2px solid var(--status-warning);\n  color: var(--text-primary) !important;\n}\n.sim-outcome-facts,\n.sim-outcome-movement,\n.sim-outcome-method dl {\n  margin: 0;\n}\n.sim-outcome-facts > div {\n  display: grid;\n  grid-template-columns: minmax(180px, .75fr) 1fr;\n  gap: 18px;\n  padding: 8px 0;\n  border-bottom: 1px solid var(--border-subtle);\n}\n.sim-outcome-facts dt,\n.sim-outcome-method dt {\n  color: var(--text-muted);\n}\n.sim-outcome-facts dd,\n.sim-outcome-method dd {\n  margin: 0;\n  color: var(--text-primary);\n  font-weight: 800;\n}\n.sim-outcome-table {\n  width: 100%;\n  margin-top: 9px;\n  border-collapse: collapse;\n  font-size: var(--font-meta);\n}\n.sim-outcome-table th,\n.sim-outcome-table td {\n  padding: 9px 8px;\n  border-bottom: 1px solid var(--border-subtle);\n  text-align: right;\n}\n.sim-outcome-table th:first-child,\n.sim-outcome-table td:first-child {\n  text-align: left;\n}\n.sim-outcome-table th {\n  color: var(--text-muted);\n  font-weight: 800;\n}\n.sim-outcome-table td {\n  color: var(--text-primary);\n}\n.sim-outcome-explain {\n  margin-top: 12px;\n  padding-top: 10px;\n  border-top: 1px solid var(--border-subtle);\n}\n.sim-outcome-explain strong {\n  color: var(--text-primary);\n  font-size: var(--font-meta);\n}\n.sim-outcome-explain p {\n  max-width: 960px;\n  margin: 5px 0 0;\n  color: var(--text-secondary);\n  font-size: var(--font-meta);\n  line-height: 1.6;\n}\n.sim-outcome-movement {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(0, 1fr));\n  border-top: 1px solid var(--border-subtle);\n  border-bottom: 1px solid var(--border-subtle);\n}\n.sim-outcome-movement > div {\n  padding: 12px 14px 12px 0;\n}\n.sim-outcome-movement > div + div {\n  padding-left: 18px;\n  border-left: 1px solid var(--border-subtle);\n}\n.sim-outcome-movement dt {\n  color: var(--text-muted);\n  font-size: var(--font-meta);\n}\n.sim-outcome-movement dd {\n  margin: 4px 0 0;\n  color: var(--text-primary);\n  font-size: var(--font-body);\n  font-weight: 850;\n}\n.sim-outcome-movement small {\n  display: block;\n  margin-top: 4px;\n  color: var(--text-muted);\n  font-size: var(--font-badge);\n  line-height: 1.5;\n}\n.sim-outcome-method {\n  margin-top: 18px;\n  padding-top: 12px;\n  border-top: 1px solid var(--border-default);\n}\n.sim-outcome-method summary {\n  width: fit-content;\n  cursor: pointer;\n  color: var(--accent-primary);\n  font-size: var(--font-meta);\n  font-weight: 800;\n}\n.sim-outcome-method dl {\n  margin-top: 10px;\n}\n.sim-outcome-method dl > div {\n  display: grid;\n  grid-template-columns: minmax(170px, .7fr) 1fr;\n  gap: 18px;\n  padding: 7px 0;\n  border-bottom: 1px solid var(--border-subtle);\n  font-size: var(--font-meta);\n}\n@media(max-width:800px) {\n  .sim-outcome-refresh {\n    max-width: none;\n    align-items: flex-start;\n  }\n  .sim-outcome-refresh small {\n    text-align: left;\n  }\n  .sim-outcome-movement {\n    grid-template-columns: 1fr;\n  }\n  .sim-outcome-movement > div + div {\n    padding-left: 0;\n    border-left: 0;\n    border-top: 1px solid var(--border-subtle);\n  }\n  .sim-outcome-table {\n    display: block;\n    overflow-x: auto;\n  }\n}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    files = [path] if path.is_file() else sorted(
        p for p in path.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for item in files:
        hasher.update(str(item.relative_to(ROOT)).replace("\\", "/").encode())
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_workspace(source: str) -> str:
    if "VAL.3-A2" in source or "검증 결과 요약" in source:
        fail("SimulationWorkspace.tsx already appears to contain VAL.3-A2.")
    source = replace_once(source, OLD_HELPERS, NEW_HELPERS, "VAL.3-A1 helper functions")
    source = replace_once(source, OLD_BLOCK, NEW_BLOCK, "VAL.3-A1 outcome result block")
    return source


def patch_css(source: str) -> str:
    if "VAL.3-A2" in source:
        fail("simulation.css already appears to contain VAL.3-A2.")
    return source.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("VAL.3-A2 — 전략 성과 검증 결과 해석 UX")
    print("Performance calculation changes: NO")
    print("DB changes: NO")
    print("Scanner rerun: NO")
    print("External network: NO")
    print("Theme support: LIGHT + DARK")

    for path in [WORKSPACE, CSS, SERVICE, OUTCOME, CATALOG, API, SCANNER, PACKAGE]:
        if not path.is_file():
            fail(f"Required file missing: {path}")

    originals = {
        WORKSPACE: WORKSPACE.read_text(encoding="utf-8-sig"),
        CSS: CSS.read_text(encoding="utf-8-sig"),
    }

    preflight = {
        "VAL.3-A1 result block": "후보 실제 결과" in originals[WORKSPACE],
        "VAL.3-A1 outcome state": "outcomeSummary?.status" in originals[WORKSPACE],
        "VAL.3-A1 refresh": "refreshValidationOutcomes" in originals[WORKSPACE],
        "VAL.3-A1 CSS": "VAL.3-A1" in originals[CSS],
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("VAL.3-A1 is not in the expected state.")

    protected = {
        "outcome": sha256(OUTCOME),
        "catalog": sha256(CATALOG),
        "api": sha256(API),
        "service": sha256(SERVICE),
        "scanner": sha256(SCANNER),
        "tracking": tree_hash(BACKEND / "app" / "tracking"),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "holdings": tree_hash(BACKEND / "app" / "holdings"),
    }

    try:
        WORKSPACE.write_text(patch_workspace(originals[WORKSPACE]), encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(originals[CSS]), encoding="utf-8", newline="\n")

        print()
        print("=== VAL.3-A2 STATIC CONTRACT ===")
        workspace = WORKSPACE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        package = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "result summary": "검증 결과 요약" in workspace,
            "candidate meaning": "같은 종목이 여러 거래일에 다시 포착된 경우 각각 한 건으로 계산합니다" in workspace,
            "full horizon wording": all(label in workspace for label in ("5거래일 뒤", "10거래일 뒤", "20거래일 뒤")),
            "average and median explanation": "평균과 중앙값은 왜 같이 보나요?" in workspace,
            "MFE label removed": "MFE 평균" not in workspace,
            "MAE label removed": "MAE 평균" not in workspace,
            "human movement labels": "평균 최고 상승폭" in workspace and "평균 최대 하락폭" in workspace,
            "touch is not win loss": "이 수치는 성공률이나 손실률이 아닙니다" in workspace,
            "entry touch explained": "진입 관찰 가격은 무엇인가요?" in workspace,
            "actual fill disclaimer": "실제 매수 체결을 의미하지 않습니다" in workspace,
            "same bar order disclaimer": "어느 가격이 먼저였는지는 알 수 없으므로 순서를 추정하지 않습니다" in workspace,
            "refresh does not rerun scanner": "Scanner 판단은 바뀌지 않습니다" in workspace,
            "method disclosure": "검증 방법 보기" in workspace,
            "source close explained": "후보 포착 당일 종가" in workspace,
            "maturity explained": "아직 20거래일이 지나지 않아 장기 결과 표본에서 제외될 수 있습니다" in workspace,
            "no win-rate label": "승률" not in workspace,
            "no theme fork": 'html[data-theme=' not in css and ":root" not in css,
            "theme tokens reused": "var(--text-primary)" in css and "var(--border-subtle)" in css,
            "no paid dependency": all(name not in package for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        # A2 is presentation-only. One focused A1 regression protects the numbers.
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            fail(f"Project venv python not found: {python}")
        test = ROOT / "backend" / "tests" / "test_validation_outcome_val3a1.py"
        if not test.is_file():
            fail("VAL.3-A1 regression test is missing.")
        run(
            [str(python), "-m", "pytest", "backend/tests/test_validation_outcome_val3a1.py", "-q"],
            ROOT,
            "VAL.3-A1 outcome regression",
        )

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        protected_after = {
            "outcome": sha256(OUTCOME),
            "catalog": sha256(CATALOG),
            "api": sha256(API),
            "service": sha256(SERVICE),
            "scanner": sha256(SCANNER),
            "tracking": tree_hash(BACKEND / "app" / "tracking"),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "holdings": tree_hash(BACKEND / "app" / "holdings"),
        }
        if protected_after != protected:
            fail("Protected backend/service source changed during a presentation-only task.")

        print()
        print("VAL.3-A2 IMPLEMENTATION READY")
        print("Modified:")
        print(" - frontend/src/components/SimulationWorkspace.tsx")
        print(" - frontend/src/simulation.css")
        print("Backend calculation changes: 0")
        print("DB changes: 0")
        print("Scanner rerun: 0")
        print("A1 outcome regression: PASS")
        print("Frontend build: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Open the existing completed validation.")
        print(" 2) Confirm the old A1 numbers are unchanged.")
        print(" 3) Read 검증 결과 요약 without opening any help.")
        print(" 4) Check 이후 가격 변화 / 가격 움직임 / 가격 기준 도달 wording.")
        print(" 5) Open 검증 방법 보기.")
        print(" 6) Capture one Dark screenshot.")
        return 0

    except Exception:
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8", newline="\n")
        print()
        print("FAILED — VAL.3-A2 frontend changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
