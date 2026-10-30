import { test, expect } from "@playwright/test";

/**
 * Real browser ↔ REAL, isolated FastAPI POST/GET ↔ real frozen Scanner.
 * No static Scanner API mocks. Auxiliary services are deliberately stubbed.
 * Uses a read-only operational MarketStore snapshot, ONLY in a Windows worker.
 */
test("P0-03 real local FastAPI Job and TEMP prospective capture", async ({page, request}) => {
  const seedResponse = await request.get("http://127.0.0.1:5280/__p003/seed");
  expect(seedResponse.status()).toBe(200);
  const seed = await seedResponse.json();
  expect(seed.offline_historical).toBe(true);
  expect(seed.prior.candidates?.length).toBeGreaterThan(0);
  const selected = [...seed.prior.candidates, ...(seed.prior.more_candidates || [])]
    .find(item => item.market === seed.selected_market && item.code === seed.selected_code);
  expect(selected).toBeTruthy();
  const key = seed.selected_market + "-" + seed.selected_code;
  const violations = [], observed = { created: null, completed: null };
  page.on("response", async response => {
    const url = new URL(response.url());
    if (url.pathname === "/api/backtest/scanner/jobs" && response.request().method() === "POST") {
      observed.created = {status: response.status(), data: await response.json()};
    }
    if (url.pathname.startsWith("/api/backtest/jobs/") && response.status() === 200) {
      const j = await response.json();
      if (j.status === "completed") observed.completed = j;
    }
  });
  page.on("pageerror", error => violations.push("PAGE_ERROR:" + error.name));

  // No cross-origin network. The Vite proxy to the dedicated local FastAPI
  // server is the only browser Scanner traffic. Unknown writes fail closed.
  await page.route("**/*", route => {
    const u = route.request().url();
    if (u.startsWith("http://127.0.0.1:5279/") || u.startsWith("data:"))
      return route.continue();
    violations.push("EXTERNAL_URL");
    return route.abort("blockedbyclient");
  });
  await page.route("**/api/**", route => {
    const req = route.request();
    const path = new URL(req.url()).pathname, method = req.method();
    if (method === "POST" && (path === "/api/backtest/scanner/jobs" ||
                                path === "/api/backtest/scanner/data-plan"))
      return route.continue();
    if (method === "GET" && path.startsWith("/api/backtest/jobs/"))
      return route.continue();
    function json(data) {
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(data)});
    }
    if (method === "GET" && path === "/api/health")
      return json({status:"ok"});
    if (method === "GET" && path === "/api/providers/status")
      return json({
        krx:{configured:false,role:"ISOLATED"},dart:{configured:false,role:"ISOLATED"},
        naver_news:{configured:false,provider_kind:"ISOLATED",role:"ISOLATED"},
        kis:{enabled:false,role:"ISOLATED"},real_trading:false,
      });
    if (method === "GET" && path === "/api/holdings/stocks") return json([]);
    if (method === "GET") return json({items:[],status:"DISABLED",available:false});
    violations.push("UNAPPROVED_API_WRITE:" + path);
    return route.fulfill({status:403,contentType:"application/json",
      body:JSON.stringify({detail:"P003_ISOLATED_DENIED"})});
  });

  await page.addInitScript((seedResult) => {
    const storageKey = "stockscope.scanner.session.v0.21.4-A.3";
    if (!window.sessionStorage.getItem(storageKey))
      window.sessionStorage.setItem(storageKey, JSON.stringify({
        schemaVersion:1,scope:seedResult.market_scope,
        result:seedResult.prior,completedAt:Date.now(),scrollY:0,
        showMore:false,expandedEvidenceIds:[],
        selectedCandidateKey:seedResult.selected_market+"-"+seedResult.selected_code,
      }));
    window.localStorage.setItem("stockscope-jev-review-enabled","off");
  }, seed);

  await page.goto("/scanner");
  const trigger = page.getByRole("button",{name:"이 후보 최신 확정 일봉으로 다시 판단"});
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect.poll(() => observed.completed?.status, {timeout:210000}).toBe("completed");
  const completed = observed.completed, data = completed.result;
  const check = data?.candidate_recheck, capture = data?.prospective_capture;
  expect(check?.market).toBe(seed.selected_market);
  expect(check?.code).toBe(seed.selected_code);
  expect(check?.source_job_id).toBe(completed.job_id);
  expect(check?.source_data_date).toBe(seed.previous_date);
  expect(check?.new_data_date).toBe(seed.new_date);
  expect(check?.new_eod_advanced).toBe(true);
  expect(check?.new_scanner_input_fingerprint_id).toBe(data.input_fingerprint.id);
  expect(check?.targeted_result_stored_in_capture).toBe(false);
  expect(capture?.status).toMatch(/^(COMPLETE|DUPLICATE)$/);
  const canonical = capture.canonical_capture_id || capture.capture_id;
  expect(check.baseline_scanner_capture_id).toBe(canonical);
  expect(check.status).toMatch(/^(MATCHED_RETURNED_CANDIDATE|TARGETED_EVALUATED_OUTSIDE_RANKING|TARGET_OUTSIDE_SCANNER_FILTER)$/);
  if (check.status === "TARGET_OUTSIDE_SCANNER_FILTER") {
    expect(check.filter_reason).toBeTruthy();
    await expect(page.getByText(/기본 필터 사유/)).toBeVisible({timeout:20000});
    await expect(page.getByText(/자동 선택하지 않았습니다/)).toBeVisible();
    await expect(page.locator(".scanner-selected-detail")).toHaveCount(0);
  } else if (check.status === "MATCHED_RETURNED_CANDIDATE") {
    await expect(page.locator(".scanner-selected-detail")).toContainText(selected.name);
  } else {
    await expect(page.locator(".scanner-selected-detail")).toHaveCount(0);
  }
  await expect(page.getByText(new RegExp(completed.job_id))).toBeVisible();
  await expect(page.getByText(new RegExp(canonical))).toBeVisible();

  await page.reload();
  if (check.status !== "MATCHED_RETURNED_CANDIDATE")
    await expect(page.locator(".scanner-selected-detail")).toHaveCount(0);

  expect(observed.created.status).toBe(202);
  expect(observed.created.data.job_id).toBe(completed.job_id);
  expect(violations).toEqual([]);
  const summary = {
    status:"BROWSER_REAL_API_VERIFIED", selected_market:seed.selected_market,
    selected_code:seed.selected_code, previous_date:seed.previous_date,
    new_date:seed.new_date, job_id:completed.job_id, job_status:completed.status,
    recheck_status:check.status,filter_reason:check.filter_reason ?? null,
    capture_id:canonical,capture_status:capture.status,
    api_post_status:observed.created.status,api_get_status:200,
    external_requests:0,latest_krx_eod_confirmed:false,
  };
  console.log("P003_LOOPBACK_RESULT " + JSON.stringify(summary));
});
