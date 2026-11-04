import assert from "node:assert/strict";
import test from "node:test";
import { scannerPositionBoundary as check } from "../src/components/scannerPositionBoundary.ts";

const scanner = { code: "001820", market: "KOSPI", data_date: "2026-10-14", risk: { status: "READY" } };
const asof = { market_summary: [{ market: "KOSPI", data_date: "2026-10-14", regime: "RANGE" }] };
function stock(changes={}) {
  return {
    market: "KOSPI", ticker: "001820", watch_enabled: false,
    is_held: false, positions: [], ...changes,
  };
}
function position(changes={}) {
  return {
    position_id: "p1", status: "OPEN", provider: "MANUAL", account_name: "수동 보유 기록",
    ...changes,
  };
}

test("unknown holdings API must not be mistaken for absence of holdings", () => {
  const loading = check(scanner, asof, null, true, false);
  assert.equal(loading.state, "RECORDS_LOADING");
  const error = check(scanner, asof, null, false, false);
  assert.equal(error.state, "RECORDS_UNAVAILABLE");
  assert.equal(error.openPositionCount, null);
  assert.equal(error.brokerHoldingsVerified, false);
  assert.equal(error.activeStopOrWatchVerified, false);
});
test("missing from local list is not proof the broker has no position", () => {
  const result = check(scanner, asof, null, false, true);
  assert.equal(result.state, "NOT_IN_LOCAL_LIST");
  assert.match(result.explanation, /외부 증권계좌/);
  assert.equal(result.brokerHoldingsVerified, false);
});
test("registered OPEN positions are not conflated with Scanner's entry reference", () => {
  const result = check(scanner, asof, stock({
    is_held: true, positions: [position()],
  }), false, true);
  assert.equal(result.state, "LOCAL_POSITION_RECORDED");
  assert.equal(result.openPositionCount, 1);
  assert.deepEqual(result.positionAccounts, ["수동 보유 기록"]);
  assert.equal(result.scannerReferenceIsAppliedHoldingStop, false);
  assert.equal(result.activeStopOrWatchVerified, false);
  assert.equal(result.brokerHoldingsVerified, false);
  assert.match(result.nextAction, /Holdings/);
});
test("multiple positions are counted once, accounts are deduplicated", () => {
  const row = stock({ is_held: true, positions: [
    position({position_id: "p1", account_name: "계좌 A"}),
    position({position_id: "p2", account_name: "계좌 A"}),
    position({position_id: "p3", account_name: "계좌 B"}),
    position({position_id: "p4", status: "CLOSED", account_name: "종료 계좌"}),
  ]});
  const result = check(scanner, asof, row, false, true);
  assert.equal(result.openPositionCount, 3);
  assert.deepEqual(result.positionAccounts, ["계좌 A", "계좌 B"]);
});
test("WATCH only means no registered open position, not activated live Watch", () => {
  const result = check(scanner, asof, stock({watch_enabled: true}), false, true);
  assert.equal(result.state, "LOCAL_WATCH_ONLY");
  assert.equal(result.watchRegistered, true);
  assert.match(result.explanation, /실시간 감시/);
  assert.equal(result.activeStopOrWatchVerified, false);
});
test("registered record without open position cannot prove no broker holdings", () => {
  const result = check(scanner, asof, stock({
    positions: [position({status: "CLOSED"})],
  }), false, true);
  assert.equal(result.state, "LOCAL_RECORD_NO_OPEN_POSITION");
  assert.match(result.explanation, /외부 계좌/);
});
test("conflicting is_held and OPEN positions are held for review", () => {
  for (const item of [
    stock({is_held: true, positions: []}),
    stock({is_held: false, positions: [position()]}),
    stock({is_held: true, positions: undefined}),
  ]) {
    const result = check(scanner, asof, item, false, true);
    assert.equal(result.state, "LOCAL_RECORD_CONFLICT");
    assert.equal(result.brokerHoldingsVerified, false);
  }
});
test("wrong ticker or market cannot leak other account's positions", () => {
  for (const fields of [
    {ticker: "005830"}, {market: "KOSDAQ"},
  ]) {
    const result = check(scanner, asof, stock({
      is_held: true, positions: [position()], ...fields,
    }), false, true);
    assert.equal(result.state, "LOCAL_RECORD_CONFLICT");
    assert.equal(result.openPositionCount, null);
  }
});
test("matching signal-day market regime is historical only, never forward safe", () => {
  const result = check(scanner, asof, null, false, true);
  assert.equal(result.marketContext.state, "AS_OF_ONLY");
  assert.equal(result.marketContext.regime, "RANGE");
  assert.match(result.marketContext.caution, /이후 급락/);
});
test("dangerous signal-day market regime adds caution but not a new trading gate", () => {
  for (const regime of ["TREND_DOWN", "HIGH_VOLATILITY", "PANIC"]) {
    const result = check(scanner, {
      market_summary: [{market: "KOSPI", data_date: scanner.data_date, regime}],
    }, stock({is_held: true, positions: [position()]}), false, true);
    assert.equal(result.marketContext.state, "AS_OF_ONLY");
    assert.match(result.marketContext.caution, /위험 시장/);
    assert.equal(result.scannerReferenceIsAppliedHoldingStop, false);
  }
});
test("missing, duplicate or mismatched market summary never invents a safe regime", () => {
  for (const market_summary of [
    [], [{market: "KOSDAQ", data_date: scanner.data_date, regime: "RANGE"}],
    [asof.market_summary[0], asof.market_summary[0]],
  ]) {
    assert.equal(check(scanner, {market_summary}, null, false, true).marketContext.state,
      "UNAVAILABLE");
  }
  const result = check(scanner, {
    market_summary: [{market: "KOSPI", data_date: "2026-10-15", regime: "RANGE"}],
  }, null, false, true);
  assert.equal(result.marketContext.state, "DATE_MISMATCH");
  assert.equal(result.marketContext.regime, null);
});
test("pure evaluator never mutates existing candidate, holdings, or market snapshots", () => {
  const c = structuredClone(scanner), r = structuredClone(asof);
  const row = stock({is_held: true, positions: [position()]});
  const before = structuredClone(row);
  check(c, r, row, false, true);
  assert.deepEqual(c, scanner);
  assert.deepEqual(r, asof);
  assert.deepEqual(row, before);
});
