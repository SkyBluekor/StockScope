from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

WORKSPACE = FRONTEND / "src" / "components" / "HoldingsWorkspace.tsx"
CSS = FRONTEND / "src" / "holdings.css"
SERVICE = FRONTEND / "src" / "services" / "holdingsApi.ts"
API = BACKEND / "app" / "api" / "holdings.py"
LIFECYCLE = BACKEND / "app" / "holdings" / "lifecycle.py"
CATALOG = BACKEND / "app" / "holdings" / "catalog.py"
SCANNER = BACKEND / "app" / "backtest" / "scanner.py"
PACKAGE = FRONTEND / "package.json"

CSS_APPEND = '/* HOLD.1-G.5 — holdings list + position action UX */\n.holdings-stock-table th:first-child,\n.holdings-stock-table td:first-child {\n  width: 46%;\n}\n.holdings-stock-table th:last-child,\n.holdings-stock-table td:last-child {\n  text-align: right;\n  white-space: nowrap;\n}\n.holdings-list-position-summary {\n  display: block;\n  margin-top: 5px;\n  color: var(--text-secondary);\n  font-size: var(--font-badge);\n  line-height: var(--line-body);\n  word-break: keep-all;\n}\n.holdings-list-action {\n  border: 0;\n  border-bottom: 1px solid var(--border-strong);\n  background: transparent;\n  color: var(--accent-primary);\n  padding: 2px 0 3px;\n  font: inherit;\n  font-size: var(--font-meta);\n  font-weight: 800;\n}\n.holdings-list-action:hover { border-bottom-color: var(--accent-primary); }\n.holdings-list-action.remove { color: var(--text-secondary); }\n.holdings-list-action.remove:hover {\n  color: var(--status-negative);\n  border-bottom-color: var(--status-negative);\n}\n.holdings-position-row {\n  grid-template-columns: minmax(170px, 1.35fr) minmax(90px, .55fr) minmax(120px, .75fr) minmax(215px, 1.1fr);\n  align-items: center;\n}\n.holdings-position-actions {\n  display: flex;\n  justify-content: flex-end;\n  flex-wrap: wrap;\n  gap: 6px;\n}\n.holdings-position-actions button {\n  border: 1px solid var(--border-strong);\n  background: transparent;\n  color: var(--text-primary);\n  padding: 7px 9px;\n  font: inherit;\n  font-size: var(--font-meta);\n  font-weight: 800;\n}\n.holdings-position-actions button:hover { background: var(--bg-hover); }\n.holdings-position-actions button.primary {\n  border-color: var(--accent-primary);\n  color: var(--accent-primary);\n}\n.holdings-position-broker-note {\n  display: block;\n  color: var(--text-muted);\n  font-size: var(--font-meta);\n  line-height: var(--line-body);\n  text-align: right;\n}\n.holdings-position-empty-actions {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  margin-top: 8px;\n}\n.holdings-manual-summary {\n  display: grid;\n  grid-template-columns: repeat(3, minmax(0, 1fr));\n  margin-bottom: 16px;\n  border-top: 1px solid var(--border-default);\n  border-bottom: 1px solid var(--border-default);\n}\n.holdings-manual-summary > div {\n  min-width: 0;\n  padding: 10px 12px;\n  border-right: 1px solid var(--border-subtle);\n}\n.holdings-manual-summary > div:last-child { border-right: 0; }\n.holdings-manual-summary span,\n.holdings-manual-summary strong { display: block; }\n.holdings-manual-summary span {\n  color: var(--text-muted);\n  font-size: var(--font-meta);\n}\n.holdings-manual-summary strong {\n  margin-top: 4px;\n  color: var(--text-primary);\n}\n.holdings-quantity-stepper {\n  display: grid;\n  grid-template-columns: 40px minmax(90px, 1fr) 40px;\n}\n.holdings-quantity-stepper button {\n  border: 1px solid var(--border-default);\n  background: transparent;\n  color: var(--text-primary);\n  font: inherit;\n  font-weight: 850;\n}\n.holdings-quantity-stepper button:hover:not(:disabled) { background: var(--bg-hover); }\n.holdings-quantity-stepper input {\n  border-left: 0;\n  border-right: 0;\n  text-align: center;\n}\n.holdings-form-preview {\n  display: flex;\n  justify-content: space-between;\n  gap: 16px;\n  grid-column: 1 / -1;\n  padding: 10px 0;\n  border-top: 1px solid var(--border-subtle);\n  border-bottom: 1px solid var(--border-subtle);\n}\n.holdings-form-preview span {\n  color: var(--text-muted);\n  font-size: var(--font-meta);\n}\n.holdings-form-preview strong { color: var(--text-primary); }\n.holdings-manual-account-fixed {\n  padding: 9px 10px;\n  border: 1px solid var(--border-default);\n  background: var(--bg-soft);\n  color: var(--text-secondary);\n  font-size: var(--font-body-small);\n}\n.holdings-dialog.manual .holdings-order-note { line-height: var(--line-body); }\n@media (max-width: 1180px) {\n  .holdings-position-row {\n    grid-template-columns: minmax(170px, 1.2fr) minmax(90px, .55fr) minmax(120px, .75fr);\n  }\n  .holdings-position-actions,\n  .holdings-position-broker-note {\n    grid-column: 1 / -1;\n    justify-content: flex-start;\n    text-align: left;\n  }\n}\n@media (max-width: 700px) {\n  .holdings-stock-table { min-width: 720px; }\n  .holdings-position-row { grid-template-columns: 1fr 1fr; }\n  .holdings-position-row > div:first-child,\n  .holdings-position-actions,\n  .holdings-position-broker-note { grid-column: 1 / -1; }\n  .holdings-manual-summary { grid-template-columns: 1fr; }\n  .holdings-manual-summary > div {\n    border-right: 0;\n    border-bottom: 1px solid var(--border-subtle);\n  }\n  .holdings-manual-summary > div:last-child { border-bottom: 0; }\n}\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


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


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def regex_replace_once(source: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    if count != 1:
        fail(f"{label}: expected one match, found {count}")
    return updated


def run(cmd: list[str], cwd: Path, label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def patch_workspace(source: str) -> str:
    if "HOLD_G5_POSITION_UX" in source:
        fail("HoldingsWorkspace.tsx already appears to contain HOLD.1-G.5.")

    helper_anchor = '''function quantity(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 6 }).format(parsed);
}
'''
    helper_add = helper_anchor + '''
const HOLD_G5_POSITION_UX = true;

function quantityNumber(value: string | null | undefined) {
  const parsed = Number(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function stockHoldingSummary(stock: HoldingStock) {
  const positions = stock.positions ?? [];
  if (positions.length === 0) return stock.watch_enabled ? "관심 종목" : "보유 기록 없음";
  if (positions.length === 1) {
    const position = positions[0];
    return `보유 ${quantity(position.quantity)}주 · 평균 ${money(position.average_price)}`;
  }
  const total = positions.reduce((sum, position) => sum + quantityNumber(position.quantity), 0);
  return `보유 ${positions.length}개 포지션 · 총 ${quantity(String(total))}주`;
}

function stockDecisionText(stock: HoldingStock) {
  if (!stock.current_analysis) return "분석 필요";
  return stock.decision_context?.entry.label
    ?? actionLabel[stock.current_analysis.action_state]
    ?? stock.current_analysis.action_state;
}
'''
    source = replace_once(source, helper_anchor, helper_add, "G.5 helpers")

    source = replace_once(
        source,
        '  const [removeOpen, setRemoveOpen] = useState(false);\n',
        '  const [removeTarget, setRemoveTarget] = useState<HoldingStock | null>(null);\n',
        "remove target state",
    )

    editable_anchor = '''  const editablePositions = useMemo(
    () => (detail?.positions ?? []).filter(
      (position) => position.account_kind === "MANUAL" || position.account_kind === "VIRTUAL",
    ),
    [detail],
  );
'''
    editable_new = editable_anchor + '''
  const manualPosition = useMemo(
    () => (detail?.positions ?? []).find((position) => position.position_id === manualPositionId) ?? null,
    [detail, manualPositionId],
  );

  const manualDialogTitle = manualMode === "buy"
    ? manualPosition ? "수량 추가" : "보유 등록"
    : manualMode === "sell"
      ? "수량 감소"
      : "정보 수정";

  const manualRemainingQuantity = manualMode === "sell" && manualPosition
    ? Math.max(0, quantityNumber(manualPosition.quantity) - quantityNumber(manualQuantity))
    : null;
'''
    source = replace_once(source, editable_anchor, editable_new, "manual position derived state")

    source = regex_replace_once(
        source,
        r'''  async function setSelectedWatch\(enabled: boolean, removedFromList = false\) \{.*?\n  \}\n\n  function requestWatchChange\(\) \{.*?\n  \}\n\n''',
        '''  async function changeWatch(stock: HoldingStock, enabled: boolean, removedFromList = false) {
    setError(null);
    setMessage(null);
    try {
      await setWatchEnabled(stock.stock_id, enabled);
      setRemoveTarget(null);
      const preferred = enabled || stock.is_held ? stock.stock_id : null;
      await reloadStocks(preferred);
      if (stock.is_held && stock.stock_id === selectedStockId) {
        await loadSelected(stock.stock_id);
      }
      setMessage(
        enabled
          ? `${stock.name}을(를) 관심 종목으로 등록했습니다.`
          : removedFromList
            ? `${stock.name}을(를) 내 종목 목록에서 제거했습니다. 저장된 분석 기록은 유지됩니다.`
            : `${stock.name}의 관심 등록을 해제했습니다. 보유 기록은 그대로 유지됩니다.`,
      );
    } catch (watchError) {
      setError(readableError(watchError, "관심 상태를 변경하지 못했습니다."));
    }
  }

  function requestListWatchChange(stock: HoldingStock) {
    if (!stock.watch_enabled) {
      void changeWatch(stock, true);
      return;
    }
    if (stock.is_held) {
      void changeWatch(stock, false);
      return;
    }
    setRemoveTarget(stock);
  }

''',
        "watch actions",
    )

    source = regex_replace_once(
        source,
        r'''  async function openManual\(mode: ManualMode\) \{.*?\n  \}\n\n  async function saveManual\(\) \{''',
        '''  async function openManual(mode: ManualMode, position?: HoldingPosition) {
    if (!detail) return;
    if (position?.account_kind === "BROKER") {
      setError("증권사 연동 보유는 잔고 동기화로만 변경할 수 있습니다.");
      return;
    }

    setManualMode(mode);
    setManualPositionId(position?.position_id ?? "");
    setManualAccountId(position?.account_id ?? "");
    setManualNote("");
    setManualAt(localDateTimeValue());
    setError(null);

    if (mode === "correction" && position) {
      setManualQuantity(position.quantity);
      setManualPrice(position.average_price ?? "");
    } else if (mode === "sell" && position) {
      setManualQuantity(quantityNumber(position.quantity) >= 1 ? "1" : position.quantity);
      setManualPrice("");
    } else {
      setManualQuantity("");
      setManualPrice("");
    }

    try {
      if (mode === "buy" && !position) {
        const rows = await listHoldingAccounts();
        setAccounts(rows);
        const manualAccounts = rows.filter(
          (account) => account.account_kind === "MANUAL" || account.account_kind === "VIRTUAL",
        );
        setManualAccountId(manualAccounts[0]?.id ?? "");
      } else {
        setAccounts([]);
      }
      setManualOpen(true);
    } catch (accountError) {
      setError(readableError(accountError, "보유 기록 계좌를 확인하지 못했습니다."));
    }
  }

  function adjustManualQuantity(delta: number) {
    const current = quantityNumber(manualQuantity);
    let next = Math.max(0, current + delta);
    if (manualMode === "sell" && manualPosition) {
      next = Math.min(next, quantityNumber(manualPosition.quantity));
    }
    setManualQuantity(String(next));
  }

  async function saveManual() {''',
        "manual open UX",
    )

    validation_anchor = '''    if (!manualQuantity.trim()) {
      setError("수량을 입력해주세요.");
      return;
    }
'''
    source = replace_once(
        source,
        validation_anchor,
        validation_anchor + '''    if (manualMode !== "correction" && quantityNumber(manualQuantity) <= 0) {
      setError("수량은 0보다 크게 입력해주세요.");
      return;
    }
    if (manualMode === "sell" && manualPosition && quantityNumber(manualQuantity) > quantityNumber(manualPosition.quantity)) {
      setError(`감소 수량은 현재 보유 ${quantity(manualPosition.quantity)}주를 넘을 수 없습니다.`);
      return;
    }
''',
        "manual quantity validation",
    )

    source = replace_once(
        source,
        '''      setMessage(
        manualMode === "buy"
          ? "보유 기록을 추가했습니다."
          : manualMode === "sell"
            ? "보유 기록을 감소시켰습니다."
            : "보유 정보를 수정했습니다.",
      );
''',
        '''      setMessage(
        manualMode === "buy"
          ? manualPosition
            ? `${manualQuantity}주를 추가했습니다. 보유 현황을 갱신했습니다.`
            : `${manualQuantity}주를 보유 종목으로 등록했습니다.`
          : manualMode === "sell"
            ? `${manualQuantity}주를 감소했습니다. 보유 현황을 갱신했습니다.`
            : "StockScope에 저장된 보유 정보를 수정했습니다.",
      );
''',
        "manual success message",
    )

    source = regex_replace_once(
        source,
        r'''              <table className="holdings-stock-table">.*?              </table>''',
        '''              <table className="holdings-stock-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th>현재 판단</th>
                    <th>분석일</th>
                    <th>관리</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleStocks.map((stock) => (
                    <tr
                      key={stock.stock_id}
                      className={selectedStockId === stock.stock_id ? "selected" : ""}
                      onClick={() => setSelectedStockId(stock.stock_id)}
                    >
                      <td>
                        <strong>{stock.name}</strong>
                        <small>{stock.ticker} · {stock.market}</small>
                        <span className="holdings-list-position-summary">{stockHoldingSummary(stock)}</span>
                      </td>
                      <td className="holdings-decision-cell">
                        <strong>{stockDecisionText(stock)}</strong>
                        {stock.decision_context && isPlanEvent(stock.decision_context) && (
                          <small>{stock.decision_context.previous_plan.label}</small>
                        )}
                      </td>
                      <td>{compactDate(stock.current_analysis?.market_date)}</td>
                      <td>
                        <button
                          type="button"
                          className={`holdings-list-action ${stock.watch_enabled && !stock.is_held ? "remove" : ""}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            requestListWatchChange(stock);
                          }}
                        >
                          {!stock.watch_enabled ? "관심 등록" : stock.is_held ? "관심 해제" : "제거"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>''',
        "stock table",
    )

    source = regex_replace_once(
        source,
        r'''                <div className="holdings-actions">.*?                </div>\n              </div>\n\n              <HoldingsPriceChart''',
        '''                <div className="holdings-actions">
                  <button className="holdings-primary" type="button" onClick={refreshSelected} disabled={refreshingAnalysis}>
                    {refreshingAnalysis ? "분석 확인 중" : "분석 새로고침"}
                  </button>
                  <button className="holdings-secondary" type="button" onClick={syncKis} disabled={syncingKis}>
                    {syncingKis ? "동기화 중" : "잔고 동기화"}
                  </button>
                </div>
              </div>

              <HoldingsPriceChart''',
        "detail header actions",
    )

    source = regex_replace_once(
        source,
        r'''              <section className="holdings-positions">.*?              </section>\n            </>''',
        '''              <section className="holdings-positions">
                <div className="holdings-block-title">
                  <div>
                    <h3>보유 현황</h3>
                    <span>계좌별 보유 수량과 평균단가를 확인하고, 수동 기록은 여기에서 바로 변경합니다.</span>
                  </div>
                </div>

                {detail.positions.length === 0 ? (
                  <div className="holdings-inline-empty">
                    <span>현재 열린 보유 기록이 없습니다.</span>
                    <div className="holdings-position-empty-actions">
                      <button className="holdings-primary small" type="button" onClick={() => void openManual("buy")}>
                        보유 등록
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="holdings-position-list">
                    {detail.positions.map((position) => (
                      <article key={position.position_id} className="holdings-position-row">
                        <div>
                          <strong>{position.account_name || (position.provider === "KIS" ? "한국투자증권" : "수동 기록")}</strong>
                          <small>{position.account_kind === "BROKER" ? "증권사 연동 보유" : "StockScope 내부 보유 기록"}</small>
                        </div>
                        <div><span>수량</span><strong>{quantity(position.quantity)}주</strong></div>
                        <div><span>평균단가</span><strong>{money(position.average_price)}</strong></div>
                        {position.account_kind === "BROKER" ? (
                          <span className="holdings-position-broker-note">잔고 동기화로 갱신됩니다.</span>
                        ) : (
                          <div className="holdings-position-actions">
                            <button className="primary" type="button" onClick={() => void openManual("buy", position)}>수량 추가</button>
                            <button type="button" onClick={() => void openManual("sell", position)}>수량 감소</button>
                            <button type="button" onClick={() => void openManual("correction", position)}>정보 수정</button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>''',
        "positions section",
    )

    source = regex_replace_once(
        source,
        r'''      \{removeOpen && detail && \(.*?      \)\}\n\n      \{addOpen && \(''',
        '''      {removeTarget && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setRemoveTarget(null)}>
          <div className="holdings-dialog holdings-remove-dialog" role="dialog" aria-modal="true" aria-label="목록에서 제거" onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>목록에서 제거</h2>
                <p>{removeTarget.name}을(를) 내 종목 목록에서 제거할까요?</p>
              </div>
              <button type="button" onClick={() => setRemoveTarget(null)} aria-label="닫기">×</button>
            </div>
            <div className="holdings-remove-copy">저장된 분석 기록과 과거 변화 기록은 삭제되지 않습니다.</div>
            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setRemoveTarget(null)}>취소</button>
              <button type="button" className="holdings-remove-confirm" onClick={() => void changeWatch(removeTarget, false, true)}>제거</button>
            </div>
          </div>
        </div>
      )}

      {addOpen && (''',
        "remove dialog",
    )

    source = regex_replace_once(
        source,
        r'''      \{manualOpen && detail && \(.*?      \)\}\n    </div>\n  \);\n\}''',
        '''      {manualOpen && detail && (
        <div className="holdings-dialog-backdrop" role="presentation" onMouseDown={() => setManualOpen(false)}>
          <div className="holdings-dialog manual" role="dialog" aria-modal="true" aria-label={manualDialogTitle} onMouseDown={(event) => event.stopPropagation()}>
            <div className="holdings-dialog-head">
              <div>
                <h2>{manualDialogTitle}</h2>
                <p>{detail.name} · 실제 증권사 주문이 아니라 StockScope 내부 보유 기록을 변경합니다.</p>
              </div>
              <button type="button" onClick={() => setManualOpen(false)} aria-label="닫기">×</button>
            </div>

            {manualPosition && (
              <div className="holdings-manual-summary">
                <div><span>대상</span><strong>{manualPosition.account_name || manualPosition.provider}</strong></div>
                <div><span>현재 수량</span><strong>{quantity(manualPosition.quantity)}주</strong></div>
                <div><span>현재 평균단가</span><strong>{money(manualPosition.average_price)}</strong></div>
              </div>
            )}

            <div className="holdings-form">
              {manualMode === "buy" && !manualPosition && (
                <label>
                  <span>기록 계좌</span>
                  <select value={manualAccountId} onChange={(event) => setManualAccountId(event.target.value)}>
                    <option value="">기본 수동 기록</option>
                    {accounts
                      .filter((account) => account.account_kind === "MANUAL" || account.account_kind === "VIRTUAL")
                      .map((account) => (
                        <option key={account.id} value={account.id}>{account.display_name || account.provider}</option>
                      ))}
                  </select>
                </label>
              )}

              {manualMode === "buy" && manualPosition && (
                <label>
                  <span>기록 계좌</span>
                  <div className="holdings-manual-account-fixed">{manualPosition.account_name || manualPosition.provider}</div>
                </label>
              )}

              <label>
                <span>
                  {manualMode === "buy"
                    ? manualPosition ? "추가 수량" : "보유 수량"
                    : manualMode === "sell"
                      ? "감소 수량"
                      : "보유 수량"}
                </span>
                {manualMode === "sell" ? (
                  <div className="holdings-quantity-stepper">
                    <button type="button" onClick={() => adjustManualQuantity(-1)} disabled={quantityNumber(manualQuantity) <= 0}>−</button>
                    <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" />
                    <button type="button" onClick={() => adjustManualQuantity(1)} disabled={!!manualPosition && quantityNumber(manualQuantity) >= quantityNumber(manualPosition.quantity)}>+</button>
                  </div>
                ) : (
                  <input value={manualQuantity} onChange={(event) => setManualQuantity(event.target.value)} inputMode="decimal" placeholder="예: 5" />
                )}
              </label>

              <label>
                <span>
                  {manualMode === "correction"
                    ? "평균단가"
                    : manualMode === "sell"
                      ? "감소 가격 (기록용)"
                      : manualPosition ? "추가 매수가" : "평균 매수가"}
                </span>
                <input value={manualPrice} onChange={(event) => setManualPrice(event.target.value)} inputMode="decimal" placeholder="예: 265000" />
              </label>

              {manualMode === "sell" && manualPosition && (
                <div className="holdings-form-preview">
                  <span>감소 후 보유 수량</span>
                  <strong>{quantity(String(manualRemainingQuantity ?? 0))}주</strong>
                </div>
              )}

              {manualMode === "buy" && manualPosition && manualQuantity.trim() && (
                <div className="holdings-form-preview">
                  <span>추가 후 보유 수량</span>
                  <strong>{quantity(String(quantityNumber(manualPosition.quantity) + quantityNumber(manualQuantity)))}주</strong>
                </div>
              )}

              <label>
                <span>기록 시각</span>
                <input type="datetime-local" value={manualAt} onChange={(event) => setManualAt(event.target.value)} />
              </label>
              <label className="full">
                <span>{manualMode === "correction" ? "수정 사유" : "메모 (선택)"}</span>
                <input value={manualNote} onChange={(event) => setManualNote(event.target.value)} placeholder={manualMode === "correction" ? "수정 이유를 입력하세요." : "선택 입력"} />
              </label>
            </div>

            <div className="holdings-order-note">
              {manualMode === "correction"
                ? "실제 주문 내역을 만드는 것이 아니라 StockScope에 저장된 보유 수량과 평균단가를 바로잡습니다."
                : manualMode === "sell"
                  ? "실제 매도 주문은 실행되지 않습니다. 선택한 내부 보유 기록의 수량만 감소시킵니다."
                  : "실제 매수 주문은 실행되지 않습니다. StockScope 내부 보유 기록만 추가합니다."}
            </div>

            <div className="holdings-dialog-actions">
              <button type="button" className="holdings-secondary" onClick={() => setManualOpen(false)}>취소</button>
              <button type="button" className="holdings-primary" onClick={() => void saveManual()} disabled={manualBusy}>
                {manualBusy
                  ? "저장 중"
                  : manualMode === "buy"
                    ? manualPosition ? "수량 추가" : "보유 등록"
                    : manualMode === "sell"
                      ? "감소 적용"
                      : "정보 수정"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}''',
        "manual dialog",
    )

    return source


def patch_css(source: str) -> str:
    if "HOLD.1-G.5 — holdings list + position action UX" in source:
        fail("holdings.css already appears to contain HOLD.1-G.5.")
    return source.rstrip() + "\n\n" + CSS_APPEND.strip() + "\n"


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("HOLD.1-G.5 — 내 종목 목록 · 보유 조작 UX 재설계")
    print("Backend API changes: NO")
    print("DB schema changes: NO")
    print("Scanner/Strategy/Risk changes: NO")
    print("BROKER manual mutation: FORBIDDEN")
    print("Theme support: LIGHT + DARK")

    for path in [WORKSPACE, CSS, SERVICE, API, LIFECYCLE, CATALOG, SCANNER, PACKAGE]:
        if not path.is_file():
            fail(f"Required file missing: {path}")

    workspace_before = WORKSPACE.read_text(encoding="utf-8-sig")
    css_before = CSS.read_text(encoding="utf-8-sig")
    service_before = SERVICE.read_text(encoding="utf-8-sig")

    preflight = {
        "G.4 decision context": "decision_context" in service_before and "isPlanEvent" in workspace_before,
        "G.4.1 explanation UX": "부족한 조건" in workspace_before and "이전 계획" in workspace_before,
        "manual buy API client": "recordManualBuy" in workspace_before,
        "manual sell API client": "recordManualSell" in workspace_before,
        "manual correction API client": "recordManualCorrection" in workspace_before,
        "existing inline remove UX": "holdings-remove-dialog" in workspace_before,
        "existing positions section": 'className="holdings-positions"' in workspace_before,
    }
    for name, ok in preflight.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if not all(preflight.values()):
        fail("Current HOLD workspace is not in the expected G.4.1 state.")
    if "HOLD_G5_POSITION_UX" in workspace_before:
        fail("HOLD.1-G.5 already appears to be applied.")

    protected = {
        "service": sha256(SERVICE),
        "api": sha256(API),
        "lifecycle": sha256(LIFECYCLE),
        "catalog": sha256(CATALOG),
        "scanner": sha256(SCANNER),
        "strategy": tree_hash(BACKEND / "app" / "strategy"),
        "risk": tree_hash(BACKEND / "app" / "risk"),
        "tracking": tree_hash(BACKEND / "app" / "tracking"),
        "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
    }

    try:
        WORKSPACE.write_text(patch_workspace(workspace_before), encoding="utf-8", newline="\n")
        CSS.write_text(patch_css(css_before), encoding="utf-8", newline="\n")

        print()
        print("=== HOLD.1-G.5 STATIC CONTRACT ===")
        workspace = WORKSPACE.read_text(encoding="utf-8")
        package = PACKAGE.read_text(encoding="utf-8").lower()

        checks = {
            "left list holding summary": "stockHoldingSummary(stock)" in workspace,
            "inline list remove/watch": "requestListWatchChange(stock)" in workspace,
            "remove stays watch-state only": "changeWatch(removeTarget, false, true)" in workspace,
            "right header manual button removed": '>수동 기록</button>' not in workspace,
            "right header list remove removed": "requestWatchChange" not in workspace,
            "hold registration": "보유 등록" in workspace and 'openManual("buy")' in workspace,
            "position add": ">수량 추가<" in workspace,
            "position decrease": ">수량 감소<" in workspace,
            "position correction": ">정보 수정<" in workspace,
            "sell remaining preview": "감소 후 보유 수량" in workspace,
            "broker sync only": "잔고 동기화로 갱신됩니다." in workspace,
            "broker mutation guard": 'position?.account_kind === "BROKER"' in workspace,
            "multi-position summary avoids avg merge": "보유 ${positions.length}개 포지션" in workspace,
            "correction explanation": "보유 수량과 평균단가를 바로잡습니다" in workspace,
            "no delete API": "DELETE" not in workspace,
            "theme tokens reused": "var(--text-primary)" in CSS_APPEND and "var(--border-subtle)" in CSS_APPEND,
            "no theme fork": 'html[data-theme=' not in CSS_APPEND and ":root" not in CSS_APPEND,
            "no paid dependency": all(name not in package for name in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly")),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"{name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            fail("Static contract failed: " + ", ".join(failed))

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            fail("npm was not found.")
        run([npm, "run", "build"], FRONTEND, "Frontend build")

        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            fail(f"Project venv python not found: {python}")
        run(
            [
                str(python), "-m", "pytest",
                "backend/tests/test_holdings_lifecycle_hold1c.py",
                "backend/tests/test_holdings_api_hold1f.py",
                "-q",
            ],
            ROOT,
            "Focused HOLD regression",
        )

        protected_after = {
            "service": sha256(SERVICE),
            "api": sha256(API),
            "lifecycle": sha256(LIFECYCLE),
            "catalog": sha256(CATALOG),
            "scanner": sha256(SCANNER),
            "strategy": tree_hash(BACKEND / "app" / "strategy"),
            "risk": tree_hash(BACKEND / "app" / "risk"),
            "tracking": tree_hash(BACKEND / "app" / "tracking"),
            "kis": tree_hash(BACKEND / "app" / "integrations" / "kis"),
        }
        if protected_after != protected:
            fail("Protected API/lifecycle/catalog/scanner/strategy/risk/tracking/KIS source changed.")

        print()
        print("HOLD.1-G.5 IMPLEMENTATION READY")
        print("Modified:")
        print(" - frontend/src/components/HoldingsWorkspace.tsx")
        print(" - frontend/src/holdings.css")
        print("Backend changes: 0")
        print("DB schema changes: 0")
        print("Left-list holding summary: PASS")
        print("Inline remove/watch action: PASS")
        print("Holding registration/add/decrease/correction UX: PASS")
        print("BROKER manual mutation exposed: NO")
        print("Physical stock delete: NO")
        print("Scanner/Strategy/Risk changes: 0")
        print("Frontend build: PASS")
        print("Focused HOLD regression: PASS")
        print()
        print("NEXT UAT:")
        print(" 1) Open 내 종목 분석 and select a manually-held stock.")
        print(" 2) Confirm left row shows quantity + average price.")
        print(" 3) Add 2 shares from 보유 현황 > 수량 추가.")
        print(" 4) Decrease 1 share and confirm 감소 후 보유 수량 preview.")
        print(" 5) Confirm a BROKER/KIS position has no manual mutation buttons.")
        print(" 6) Remove one watch-only stock from the left row.")
        print(" 7) Toggle 관심 해제 on a held+watched stock and confirm it remains in the list.")
        print(" 8) Capture one Dark screenshot.")
        return 0

    except Exception:
        WORKSPACE.write_text(workspace_before, encoding="utf-8", newline="\n")
        CSS.write_text(css_before, encoding="utf-8", newline="\n")
        print()
        print("FAILED — HOLD.1-G.5 frontend changes were rolled back.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
