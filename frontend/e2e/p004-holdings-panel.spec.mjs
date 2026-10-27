import {test, expect} from "@playwright/test";

// All data is synthetic. Browser HTTP requests are intercepted before reaching
// a server backend. The only server running is the local Vite fixture server.
const host = "http://127.0.0.1:5281";

function activePlan(version=1, stop="90", target1="120", target2="130") {
  return {
    plan_id: "plan-p004-" + version,
    version,
    stop_price: stop,
    target1_price: target1,
    target2_price: target2,
    reference_price: "105",
  };
}

function createFixture(mode) {
  const initial = mode === "stale";
  let plan = activePlan();
  let applied = false;
  let proposalStop = "95";
  let proposalTarget1 = "125";
  let proposalTarget2 = "135";
  let decision = {
    decision_id: "decision-p004-old",
    position_id: "position-p004",
    decision_policy_version: "SYNTHETIC_V1",
    status: "ACTIONABLE",
    effective_status: initial ? "STALE" : "ACTIONABLE",
    primary_action: "HOLD",
    source_analysis_revision_id: initial ? "rev-p004-1" : "rev-p004-2",
    source_active_plan_id: plan.plan_id,
    source_active_plan_version: plan.version,
    source_position_status: "OPEN",
    source_position_quantity: "10",
    source_position_average_price: "100",
    valuation_market_date: "2026-10-21",
    valuation_price: "105",
    valuation_source: "CONFIRMED_EOD",
    horizon_intent: "SHORT",
    horizon_policy_version: "SYNTHETIC",
    input_fingerprint: "fingerprint-p004-1",
    evidence: {
      proposal_ready: true,
      new_plan_horizon_activatable: true,
      latest_analysis_differs_from_active_plan: !initial,
      proposal_conflict: null,
    },
    alternatives: [],
    limitations: [],
    created_at: "2026-10-21T17:00:00+09:00",
    stale: initial,
    stale_reasons: initial ? ["ACTIVE_PLAN_CHANGED"] : [],
    resolutions: [],
  };
  const state = {
    calls: [],
    violations: [],
    pageErrors: [],
    ledgerEventCount: 1,
    get plan() { return plan; },
    get decision() { return decision; },
    get applied() { return applied; },
    rotateProposal() {
      proposalStop = "96";
      proposalTarget1 = "126";
      proposalTarget2 = "136";
    },
    evaluate() {
      decision = {
        ...decision,
        decision_id: "decision-p004-refreshed",
        effective_status: "ACTIONABLE",
        source_analysis_revision_id: "rev-p004-1",
        source_active_plan_id: plan.plan_id,
        source_active_plan_version: plan.version,
        evidence: {
          ...decision.evidence,
          latest_analysis_differs_from_active_plan: false,
        },
        stale: false,
        stale_reasons: [],
      };
      return {decision};
    },
    apply() {
      if (applied) throw new Error("duplicate apply");
      applied = true;
      plan = activePlan(2, proposalStop, proposalTarget1, proposalTarget2);
      decision = {
        ...decision,
        stale: true,
        effective_status: "STALE",
        stale_reasons: ["ACTIVE_PLAN_CHANGED"],
      };
      return {decision, plan, plan_context: {
        context_version: "SYNTHETIC", source_decision_id: "decision-p004-old",
        selected_action: "HOLD",
      }};
    },
    decisionView() {
      return {
        stock_id: "stock-p004",
        market: "KOSPI", ticker: "000001",
        positions: [{position_id: "position-p004", decision}],
      };
    },
    managementView() {
      const same = initial || applied;
      return {
        stock_id: "stock-p004",
        market: "KOSPI", ticker: "000001",
        valuation: {available: true, market_date: "2026-10-21", price: "105"},
        positions: [{
          position_id: "position-p004",
          account_name: "합성 수동 계좌",
          provider: "MANUAL",
          management_state: "WITHIN_PLAN",
          active_plan: plan,
          proposal: {
            can_apply: !same,
            state: same ? "SAME_AS_ACTIVE" : "NEW_REVISION",
            reason: same ? "현재 활성 계획과 동일합니다." : null,
            analysis_revision_id: same ? "rev-p004-1" : "rev-p004-2",
            market_date: "2026-10-21",
            reference_price: "105", stop_price: proposalStop,
            target1_price: proposalTarget1, target2_price: proposalTarget2,
          },
        }],
      };
    },
  };
  return state;
}

async function setup(page, mode) {
  const state = createFixture(mode);
  page.on("pageerror", e => state.pageErrors.push(String(e)));
  page.on("console", m => {
    if (m.type() === "error") state.pageErrors.push(m.text());
  });
  await page.route("**/*", route => {
    const url = route.request().url();
    if (!url.startsWith(host + "/") && !url.startsWith("data:")) {
      state.violations.push(url);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  await page.route("**/api/**", route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const method = req.method();
    state.calls.push({path, method});
    const ok = (body, status=200) => route.fulfill({
      status, contentType: "application/json",
      headers: {"cache-control": "no-store"},
      body: JSON.stringify(body),
    });
    if (method === "GET" && path === "/api/holdings/stocks/stock-p004/decision-support")
      return ok(state.decisionView());
    if (method === "GET" && path === "/api/holdings/stocks/stock-p004/management")
      return ok(state.managementView());
    if (method === "POST" && path === "/api/holdings/positions/position-p004/decisions/evaluate")
      return ok(state.evaluate());
    if (method === "POST" && path === "/api/holdings/decisions/decision-p004-old/apply-plan") {
      if (mode !== "new-plan" || state.decision.stale || state.applied) {
        state.violations.push("blocked non-current apply");
        return ok({detail: "HOLD_DECISION_STALE"}, 409);
      }
      return ok(state.apply());
    }
    state.violations.push("unexpected: " + method + " " + path);
    return ok({detail: "Blocked by synthetic P0-04 UAT"}, 503);
  });
  await page.goto("/p004-test.html");
  await expect(page.locator("#holdings-decision-panel")).toBeVisible();
  return state;
}

function assertNoUnexpectedCalls(state) {
  expect(state.violations).toEqual([]);
  expect(state.pageErrors).toEqual([]);
  expect(state.ledgerEventCount).toBe(1);
}

test("STALE ACTIVE_PLAN_CHANGED -> fresh decision -> SAME_AS_ACTIVE; no redundant apply", async ({page}) => {
  const state = await setup(page, "stale");
  await expect(page.getByRole("button", {name: "최신 판단 다시 만들기"})).toBeVisible();
  await expect(page.getByText("이 판단이 참조한 활성 관리 계획이 현재 계획과 다릅니다. 기존 계획을 확인하고 판단만 다시 생성하세요.")).toBeVisible();
  await expect(page.getByRole("button", {name: "새 분석 계획 비교"})).toHaveCount(0);
  await page.getByRole("button", {name: "최신 판단 다시 만들기"}).click();
  await expect(page.getByText("현재 적용 계획을 유지할 수 있습니다.")).toBeVisible();
  await expect(page.getByRole("button", {name: "새 분석 계획 비교"})).toHaveCount(0);
  expect(state.calls.filter(x => x.method === "POST" && x.path.endsWith("/apply-plan"))).toHaveLength(0);
  expect(state.calls.filter(x => x.method === "POST" && x.path.endsWith("/decisions/evaluate"))).toHaveLength(1);
  expect(state.plan.version).toBe(1);
  await page.reload();
  await expect(page.getByText("현재 적용 계획을 유지할 수 있습니다.")).toBeVisible();
  assertNoUnexpectedCalls(state);
});

test("new analysis requires compare -> cancel -> compare -> explicit apply -> persisted reread", async ({page}) => {
  const state = await setup(page, "new-plan");
  await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toHaveCount(0);
  const compare = page.getByRole("button", {name: "새 분석 계획 비교"});
  await compare.click();
  await expect(page.getByRole("group", {name: "새 관리 계획 적용 확인"})).toContainText("90원 → 95원");
  await expect(page.getByRole("group", {name: "새 관리 계획 적용 확인"})).toContainText("120원 → 125원");
  await page.getByRole("button", {name: "취소"}).click();
  await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toHaveCount(0);
  expect(state.calls.filter(x => x.path.endsWith("/apply-plan"))).toHaveLength(0);
  await compare.click();
  await page.getByRole("button", {name: "이 가격으로 관리 계획 적용"}).click();
  await expect(page.getByText("새 분석의 관리 계획을 적용했습니다. 실제 매수·매도 거래는 발생하지 않았습니다.")).toBeVisible();
  expect(state.plan.version).toBe(2);
  expect(state.plan.stop_price).toBe("95");
  expect(state.applied).toBe(true);
  expect(state.calls.filter(x => x.path.endsWith("/apply-plan"))).toHaveLength(1);
  await expect(page.getByRole("button", {name: "새 분석 계획 비교"})).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", {name: "최신 판단 다시 만들기"})).toBeVisible();
  await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toHaveCount(0);
  assertNoUnexpectedCalls(state);
});

test("changed proposal invalidates previously confirmed prices before POST", async ({page}) => {
  const state = await setup(page, "new-plan");
  await page.getByRole("button", {name: "새 분석 계획 비교"}).click();
  await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toBeVisible();
  state.rotateProposal();
  await page.getByRole("button", {name: "테스트 데이터 재조회"}).click();
  await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toHaveCount(0);
  expect(state.calls.filter(x => x.path.endsWith("/apply-plan"))).toHaveLength(0);
  await page.getByRole("button", {name: "새 분석 계획 비교"}).click();
  await expect(page.getByRole("group", {name: "새 관리 계획 적용 확인"})).toContainText("90원 → 96원");
  assertNoUnexpectedCalls(state);
});
