import {test, expect} from "@playwright/test";

// An already-installed system Chrome is used. No screenshots, HAR or trace
// of a user's account, stock, holdings, prices, decision or Recovery notes.
test("real FastAPI GET handlers render saved Decision + Recovery without writing", async ({page}) => {
  let externalRequests = 0;
  let writeRequests = 0;
  const seen = new Set();
  page.on("request", request => {
    const address = request.url();
    const method = request.method();
    if (method !== "GET") writeRequests++;
    if (address.startsWith("http://127.0.0.1:5283/")) {
      if (address.includes("/api/holdings/") || address.includes("/__p004/")) {
        if (method === "GET") seen.add(new URL(address).pathname);
      }
    } else if (!address.startsWith("data:")) {
      externalRequests++;
    }
  });
  // Fail closed: block external loads or unexpected writes even if the UI
  // changes in a later revision. Do not echo private request URL strings.
  await page.route("**/*", route => {
    const address = route.request().url();
    if (!address.startsWith("http://127.0.0.1:5283/")
        && !address.startsWith("data:")) {
      return route.abort("blockedbyclient");
    }
    if (route.request().method() !== "GET") {
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  const response = await page.goto("/p004-loopback.html");
  expect(response?.status()).toBe(200);
  await expect(page.locator("#holdings-decision-panel")).toBeVisible();
  await expect(page.locator(".holding-recovery-panel")).toBeVisible();
  const seed = await page.request.get("/__p004/seed");
  expect(seed.ok()).toBeTruthy();
  const ids = await seed.json();
  const decPath = "/api/holdings/stocks/" + encodeURIComponent(ids.stock_id) + "/decision-support";
  const mgmtPath = "/api/holdings/stocks/" + encodeURIComponent(ids.stock_id) + "/management";
  const recPath = "/api/holdings/positions/" + encodeURIComponent(ids.position_id) + "/recovery";
  expect(seen.has(decPath)).toBe(true);
  expect(seen.has(mgmtPath)).toBe(true);
  expect(seen.has(recPath)).toBe(true);
  const [decision, management, recovery] = await Promise.all([
    page.request.get(decPath),
    page.request.get(mgmtPath),
    page.request.get(recPath),
  ]);
  expect(decision.status()).toBe(200);
  expect(management.status()).toBe(200);
  expect(recovery.status()).toBe(200);
  const record = (await decision.json()).positions.find(x => x.position_id === ids.position_id)?.decision;
  const plan = (await management.json()).positions.find(x => x.position_id === ids.position_id);
  const review = await recovery.json();
  expect(plan).toBeTruthy();
  if (record?.stale && record.stale_reasons?.length === 1
      && record.stale_reasons[0] === "ACTIVE_PLAN_CHANGED") {
    await expect(page.getByText(
      "이 판단이 참조한 활성 관리 계획이 현재 계획과 다릅니다. 기존 계획을 확인하고 판단만 다시 생성하세요.",
    )).toBeVisible();
  }
  if (plan.proposal.state === "SAME_AS_ACTIVE") {
    await expect(page.getByRole("button", {name: "새 분석 계획 비교"})).toHaveCount(0);
    await expect(page.getByRole("button", {name: "이 가격으로 관리 계획 적용"})).toHaveCount(0);
  }
  if (review.open_review) {
    await expect(page.locator(".holding-recovery-status")).toContainText("재검토 진행 중");
  } else {
    await expect(page.getByRole("button", {name: "손실 포지션 재검토"})).toBeVisible();
  }
  await page.reload();
  await expect(page.locator("#holdings-decision-panel")).toBeVisible();
  await expect(page.locator(".holding-recovery-panel")).toBeVisible();
  expect(writeRequests).toBe(0);
  expect(externalRequests).toBe(0);
  // Minimal privacy-safe machine-readable proof; no values or IDs.
  console.log("P004_READONLY_RESULT " + JSON.stringify({
    status: "READONLY_REAL_API_UI_VERIFIED",
    decision_get: seen.has(decPath),
    management_get: seen.has(mgmtPath),
    recovery_get: seen.has(recPath),
    external_requests: externalRequests,
    write_requests: writeRequests,
    decision_stale: record?.stale === true,
    active_plan_present: !!plan.active_plan,
    recovery_review_open: !!review.open_review,
  }));
});
