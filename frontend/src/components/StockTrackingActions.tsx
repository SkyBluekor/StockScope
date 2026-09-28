import { useEffect, useMemo, useState } from "react";
import NumericStepper, { parseFormattedNumber } from "./NumericStepper";
import {
  addWatchStock,
  listHoldingStocks,
  registerHeldStock,
  type HoldingStock,
} from "../services/holdingsApi";

type Props = {
  code: string;
  market: "KOSPI" | "KOSDAQ";
  name: string;
  referencePrice: number | null;
  onOpenHoldings: (target: { market: "KOSPI" | "KOSDAQ"; ticker: string; name: string }) => void;
};

function localDateTimeValue() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

function toIso(localValue: string) {
  const parsed = new Date(localValue);
  if (Number.isNaN(parsed.getTime())) return new Date().toISOString();
  return parsed.toISOString();
}

function totalQuantity(stock: HoldingStock | null) {
  if (!stock?.is_held) return 0;
  return stock.positions.reduce((sum, position) => {
    const quantity = Number(position.quantity);
    return sum + (Number.isFinite(quantity) ? quantity : 0);
  }, 0);
}

export default function StockTrackingActions({
  code,
  market,
  name,
  referencePrice,
  onOpenHoldings,
}: Props) {
  const [tracked, setTracked] = useState<HoldingStock | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"watch" | "held" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [heldOpen, setHeldOpen] = useState(false);
  const [quantity, setQuantity] = useState("1");
  const [averagePrice, setAveragePrice] = useState(
    referencePrice && referencePrice > 0 ? Math.round(referencePrice).toLocaleString("ko-KR") : "",
  );
  const [effectiveAt, setEffectiveAt] = useState(localDateTimeValue());

  useEffect(() => {
    let active = true;
    setLoading(true);
    setMessage(null);
    setError(null);
    void listHoldingStocks()
      .then((rows) => {
        if (!active) return;
        const match = rows.find(
          (row) => row.market === market && row.ticker.trim().toUpperCase() === code.trim().toUpperCase(),
        ) ?? null;
        setTracked(match);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setTracked(null);
        setError(reason instanceof Error ? reason.message : "내 종목 상태를 확인하지 못했습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [code, market]);

  useEffect(() => {
    setAveragePrice(referencePrice && referencePrice > 0 ? Math.round(referencePrice).toLocaleString("ko-KR") : "");
    setQuantity("1");
    setEffectiveAt(localDateTimeValue());
    setHeldOpen(false);
  }, [code, market, referencePrice]);

  const heldQuantity = useMemo(() => totalQuantity(tracked), [tracked]);

  async function addWatch() {
    setBusy("watch");
    setError(null);
    setMessage(null);
    try {
      const result = await addWatchStock({ market, ticker: code, name });
      setTracked(result.stock);
      setMessage(result.created ? "관심종목에 추가했습니다." : "관심 상태를 확인했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "관심종목을 추가하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function addHeld() {
    const parsedQuantity = parseFormattedNumber(quantity);
    const parsedPrice = parseFormattedNumber(averagePrice);
    if (parsedQuantity == null || parsedQuantity <= 0) {
      setError("보유 수량은 0보다 커야 합니다.");
      return;
    }
    if (parsedPrice == null || parsedPrice <= 0) {
      setError("실제 평균단가를 입력해주세요.");
      return;
    }

    setBusy("held");
    setError(null);
    setMessage(null);
    try {
      const result = await registerHeldStock({
        market,
        ticker: code,
        name,
        quantity: String(parsedQuantity),
        average_price: String(parsedPrice),
        effective_at: toIso(effectiveAt),
      });
      setTracked(result.stock);
      setHeldOpen(false);
      setMessage(`${name}을(를) ${parsedQuantity.toLocaleString("ko-KR")}주 기존 보유 상태로 등록했습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "보유종목을 등록하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const stateLabel = loading
    ? "내 종목 상태 확인 중..."
    : tracked?.is_held && tracked.watch_enabled
      ? `관심 · 보유 중${heldQuantity > 0 ? ` · ${heldQuantity.toLocaleString("ko-KR")}주` : ""}`
      : tracked?.is_held
        ? `보유 중${heldQuantity > 0 ? ` · ${heldQuantity.toLocaleString("ko-KR")}주` : ""}`
        : tracked?.watch_enabled
          ? "관심종목"
          : "내 종목에 등록되지 않음";

  return (
    <section className="stock-tracking-actions" aria-label="내 종목 상태">
      <div className="stock-tracking-copy">
        <span>내 종목 상태</span>
        <strong>{stateLabel}</strong>
        <small>등록 상태는 종목 분석의 Strategy·Scanner·Risk 계산을 변경하지 않습니다.</small>
      </div>

      <div className="stock-tracking-buttons">
        {!loading && !tracked?.watch_enabled && (
          <button type="button" className="stock-tracking-secondary" onClick={() => void addWatch()} disabled={busy != null}>
            {busy === "watch" ? "추가 중..." : "관심종목에 추가"}
          </button>
        )}
        {!loading && !tracked?.is_held && (
          <button type="button" className="stock-tracking-primary" onClick={() => setHeldOpen(true)} disabled={busy != null}>
            기존 보유 등록
          </button>
        )}
        {!loading && tracked && (tracked.watch_enabled || tracked.is_held) && (
          <button
            type="button"
            className="stock-tracking-secondary"
            onClick={() => onOpenHoldings({ market, ticker: code, name })}
          >
            내 종목 관리
          </button>
        )}
      </div>

      {(message || error) && (
        <div className={`stock-tracking-message ${error ? "error" : ""}`} role="status">
          {error ?? message}
        </div>
      )}

      {heldOpen && (
        <div className="stock-tracking-dialog-backdrop" role="presentation" onMouseDown={() => busy == null && setHeldOpen(false)}>
          <div
            className="stock-tracking-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="기존 보유 등록"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>기존 보유 등록</span>
                <h3>{name}</h3>
                <p>{code} · {market}</p>
              </div>
              <button type="button" onClick={() => setHeldOpen(false)} disabled={busy != null} aria-label="닫기">×</button>
            </header>

            <div className="stock-tracking-form">
              <label>
                <span>보유 수량</span>
                <NumericStepper
                  value={quantity}
                  onChange={setQuantity}
                  unit="주"
                  mode="quantity"
                  seedValue={1}
                  ariaLabel="보유 수량"
                />
              </label>

              <label>
                <span>평균단가</span>
                <NumericStepper
                  value={averagePrice}
                  onChange={setAveragePrice}
                  unit="원"
                  mode="price"
                  seedValue={referencePrice}
                  baseValue={referencePrice}
                  baseLabel="확정 종가"
                  quickPercentages={[-5, -1, 1, 5]}
                  ariaLabel="평균단가"
                />
                <small>
                  {referencePrice && referencePrice > 0
                    ? "최근 확정 종가를 기본값으로 사용합니다. 실제 평균단가와 다르면 수정하세요."
                    : "실제 보유 평균단가를 입력하세요."}
                </small>
              </label>

              <label>
                <span>기록 시각</span>
                <input
                  type="datetime-local"
                  value={effectiveAt}
                  onChange={(event) => setEffectiveAt(event.target.value)}
                />
              </label>
            </div>

            <p className="stock-tracking-dialog-note">
              기존에 보유 중이던 상태를 StockScope에 등록합니다. 신규 매수 주문이나 BUY 이벤트를 생성하는 기능이 아닙니다.
            </p>

            <div className="stock-tracking-dialog-actions">
              <button type="button" className="stock-tracking-secondary" onClick={() => setHeldOpen(false)} disabled={busy != null}>취소</button>
              <button type="button" className="stock-tracking-primary" onClick={() => void addHeld()} disabled={busy != null}>
                {busy === "held" ? "등록 중..." : "기존 보유 등록"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
