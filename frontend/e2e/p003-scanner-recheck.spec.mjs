import { test, expect } from "@playwright/test";

const previousDate = "2026-10-20", nextDate = "2026-10-21";
const jobId = "fixture-p003-job", captureId = "fixture-p003-capture";
function candidate(market, code, date, name) {
  return {
    market, code, name, data_date: date, current_price: 12000,
    candidate_state: "WATCH", candidate_label: "관찰",
    strategy: "BREAKOUT", strategy_easy_name: "돌파 확인",
    strategy_name: "BREAKOUT", strategy_description: "테스트용",
    action: "WAIT", action_label: "관망", headline: "테스트용", reason: "테스트용",
    conditions: {passed:6,total:9,missing:3,top_missing:[]},
    risk: {status:"REVIEW",warning:false,warnings:[]},
    historical_fit: {status:"DATA_UNAVAILABLE",verified:false,label:"3년 검증 전",summary:"데이터 부족",trades:0},
    historical_evidence: null,
    priority: {tier:"WAIT",label:"관찰",reason:"검증용",strengths:[],facts:[],penalties:[],
      entry_gap_pct:null,entry_gap_basis:null,historical_status:"DATA_UNAVAILABLE",
      ranking_rule:"DISPLAY_ONLY",rank:1,previous_rank:1,rank_change:0,strict_rank:true},
    user_action: {title:null,detail:null,next_transition:null},
  };
}
const priorStock = candidate("KOSPI","145720",previousDate,"가상 이전 후보");
const otherStock = candidate("KOSDAQ","012345",nextDate,"가상 다른 후보");
function scanner(date, stocks, recheck) {
  return {
    version:"0.21.3.9",generated_at:date+"T15:30:00+09:00",
    requested_as_of:date,market_scope:"ALL",data_dates:{KOSPI:date,KOSDAQ:date},
    scanner_cache_hit:false,partial_data:false,
    input_fingerprint:{id:date===previousDate?"old-fp":"new-fp"},
    strategy_selection_policy:{policy_id:"LEGACY_CURRENT_10_FALLBACK",policy_hash:"same-policy",fallback_used:true},
    summary:{universe_total:2762,special_excluded:0,liquidity_filtered:1,quick_analyzed:320,data_insufficient:6,
      deep_analyzed:18,candidate_count:18,shown_count:stocks.length,excluded_after_analysis:0},
    market_summary:[{market:"KOSPI",data_date:date,regime:"RANGE"},{market:"KOSDAQ",data_date:date,regime:"RANGE"}],
    candidates:stocks,more_candidates:[],
    methodology:{meaning:"EOD_ONLY",pipeline:[],guardrail:"투자 권유 아님"},
    exclusion_policy:{default:[],liquidity:"거래대금 필터"},
    diagnostics:{market_store_reused_items:0,estimated_network_requests:0,network_requests:0,
      raw_cache_hits:0,retries:0,budget_used:0,budget_limit:0,budget_remaining:0},
    empty_message:null,prospective_capture:{status:"COMPLETE",capture_id:date===previousDate?"old-cap":captureId,
      canonical_capture_id:date===previousDate?"old-cap":captureId},
    ...(recheck?{candidate_recheck:recheck}:{}),
  };
}
function recheck(matched) {
  return {
    version:"SCANNER_CANDIDATE_RECHECK_V1",reference_kind:"USER_SELECTED_PRIOR_SCANNER_CANDIDATE",
    market:"KOSPI",code:"145720",name:"가상 이전 후보",
    source_data_date:previousDate,source_action:"WAIT",source_strategy:"BREAKOUT",
    source_input_fingerprint_id:"old-fp",
    new_data_date:nextDate,new_eod_advanced:true,new_scanner_input_fingerprint_id:"new-fp",
    policy_changed:false,source_job_id:jobId,
    status:matched?"MATCHED_RETURNED_CANDIDATE":"TARGET_OUTSIDE_SCANNER_FILTER",
    reason:matched?"새 반환 후보에 존재합니다.":"현재 유동성 필터를 통과하지 못했습니다.",
    filter_reason:matched?undefined:"LOW_LIQUIDITY",
    reported_action:matched?"WAIT":null,reported_strategy:matched?"BREAKOUT":null,
    no_trade_inferred:false,independently_evaluated_when_not_returned:false,
    baseline_scanner_capture_status:"COMPLETE",baseline_scanner_capture_id:captureId,
    targeted_result_stored_in_capture:false,prior_reference_stored_in_capture:false,
  };
}
function fulfill(route,data,status=200) {
  return route.fulfill({status,contentType:"application/json",
    headers:{"cache-control":"no-store"},body:JSON.stringify(data)});
}
async function setup(page,{matched=false}={}) {
  const calls=[],violations=[],pageErrors=[];
  page.on("pageerror",error=>pageErrors.push(String(error)));
  page.on("console",msg=>{if(msg.type()==="error")pageErrors.push("console: "+msg.text());});
  const oldResult=scanner(previousDate,[priorStock]);
  const newResult=scanner(nextDate,matched?[candidate("KOSPI","145720",nextDate,"가상 이전 후보"),otherStock]:[otherStock],recheck(matched));
  await page.route("**/*",route=>{
    const url=route.request().url();
    if(!url.startsWith("http://127.0.0.1:5279/")&&!url.startsWith("data:")){
      violations.push(url);return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  await page.route("**/api/**",route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    const entry={path,method:req.method(),body:req.postDataJSON?.()??null};
    calls.push(entry);
    if(path==="/api/backtest/scanner/data-plan"&&req.method()==="POST")
      return fulfill(route,{status:"AUTO_ALLOWED",provider_calls:0,db_writes:0,estimated_missing_krx_slots:0});
    if(path==="/api/backtest/scanner/jobs"&&req.method()==="POST")
      return fulfill(route,{job_id:jobId,status:"queued",stage:"queued",progress:{message:"대기 중",current:0,total:1,percent:0}},202);
    if(path==="/api/backtest/jobs/"+jobId&&req.method()==="GET")
      return fulfill(route,{job_id:jobId,status:"completed",stage:"complete",
        progress:{message:"완료",current:1,total:1,percent:100},result:newResult});
    if(req.method()==="GET"&&path==="/api/dart/stocks/145720/disclosures"){
      return fulfill(route,{
        provider:"OpenDART",stock_code:"145720",corp_code:"12345678",
        begin_date:"20261001",end_date:"20261030",
        count:1,total_count:1,total_page:1,pages_fetched:1,
        truncated:false,duplicate_receipt_count:0,
        rows:[{receipt_no:"20261022000001",corp_name:"가상 이전 후보",
          report_name:"검증용 공시",receipt_date:"20261022",remark:"",
          corp_code:"12345678",stock_code:"145720",
          viewer_url:"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261022000001",
          source_time_quality:"DATE_ONLY",source_published_at:null}],
        fetched_at:"2026-10-30T03:00:00+00:00",
        source_publication_time_verified:false,time_quality:"DATE_ONLY",
        event_evidence_storage:"NOT_PERSISTED_RIGHTS_UNVERIFIED",
        external_ai_transfer:"BLOCKED",db_writes:0,model_calls:0,
        p6f_ingest_preview:{contract_version:"JEV_P6F_DISCLOSURE_INGEST_CONTRACT_V1",
          validated_metadata_count:1,invalid_metadata_count:0,reason_counts:{},
          stock_code:"145720",market:"KOSPI",market_verified_by_source:false,
          storage_allowed:false,event_evidence_writes:0,ai_transmission_allowed:false,
          status:"PREVIEW_ONLY_NOT_PERSISTED"},
      });
    }
    if(req.method()==="GET"&&path==="/api/simulation/jev/event-data-audit"){
      const query=new URL(req.url()).searchParams;
      return fulfill(route,{
        version:"JEV_P6D_REAL_EVENT_INVENTORY_V1",read_only:true,
        capture_id:query.get("capture_id"),
        canonical_capture_id:query.get("capture_id"),entry_count:1,
        store:{status:"READY",schema_ready:true,
          stored_counts_not_asof:{source_refs:0,event_revisions:0,entities:0,
            entity_relevances:0,quality_assessments:0}},
        registry_status:"ABSENT_OR_EMPTY",cause_counts:{NO_INGESTED_EVENTS:1},
        rows:[{sample_index:0,ticker:"145720",market:"KOSPI",
          snapshot_hash:"authored-snapshot",reference_status:"NO_INDEPENDENT_EVIDENCE",
          assertion_status:"NO_INDEPENDENT_EVIDENCE",v5_route:"SKIPPED_NO_EVIDENCE",
          cause:"NO_INGESTED_EVENTS",reference_count:0,approved_assertions:0}],
        ready_for_live_jev:false,real_market_model_calls:0,mock_model_calls:0,db_writes:0,
      });
    }
    if(req.method()==="GET"&&path==="/api/simulation/jev/event-v5-routing"){
      const query=new URL(req.url()).searchParams;
      return fulfill(route,{
        version:"JEV_EVENT_REVIEW_STATE_V5",capture_id:query.get("capture_id"),
        sample_index:Number(query.get("sample_index")),
        snapshot_hash:"authored-snapshot",market:"KOSPI",ticker:"145720",
        event_reference_hash:null,assertion_identity_hash:"a".repeat(64),
        event_assessment_status:"NO_INDEPENDENT_EVIDENCE",
        routing:"SKIPPED_NO_EVIDENCE",semantic_review_candidate:false,
        external_model_call_allowed:false,transmission_status:"PROVIDER_HOLD",
        model_review_executed:false,model_result:null,
        reason_codes:[],actual_provider_calls:0,db_writes:0,
      });
    }
    if(req.method()==="GET"&&path==="/api/simulation/jev/independent-event-assessment"){
      const query=new URL(req.url()).searchParams;
      return fulfill(route,{
        version:"JEV_P6_INDEPENDENT_EVENT_ASSERTION_V1",read_only:true,
        capture_id:query.get("capture_id"),sample_index:Number(query.get("sample_index")),
        snapshot_hash:"authored-snapshot",market:"KOSPI",ticker:"145720",
        status:"NO_INDEPENDENT_EVIDENCE",
        reason_codes:["P6_NO_OBSERVED_REFERENCE_BY_CUTOFF"],
        decision_cutoff:"2026-10-20T00:00:00+00:00",reference_count:0,
        assertion_status:"NO_ASOF_REFERENCE",approved_assertion_count:0,
        reviewed_event_count:0,retrospective_assertion_count:0,
        local_review_required:false,independent_review_candidate:false,
        assessment_origin:"OPERATOR_AUTHORED_LOCAL_ONLY",
        ai_input_rights:"NOT_APPROVED",independent_conflict_proven:false,
        model_review_executed:false,external_model_call_allowed:false,
        actual_provider_calls:0,db_writes:0,
      });
    }
    if(req.method()==="GET"&&path==="/api/simulation/jev/independent-event-reference"){
      const query=new URL(req.url()).searchParams;
      return fulfill(route,{
        version:"JEV_LIVE_04R_P6_INDEPENDENT_EVENT_REFERENCE_V1",read_only:true,
        capture_id:query.get("capture_id"),sample_index:Number(query.get("sample_index")),
        snapshot_hash:"authored-snapshot",market:"KOSPI",ticker:"145720",
        status:"NO_INDEPENDENT_EVIDENCE",reason_codes:["P6_NO_OBSERVED_REFERENCE_BY_CUTOFF"],
        decision_cutoff:"2026-10-20T00:00:00+00:00",
        cutoff_source:"CAPTURE_CREATED_AT_NOT_MARKET_PUBLICATION",
        event_reference_status:"NO_VALIDATED_EVIDENCE",projection_hash:null,
        reference_count:0,source_kinds:[],ai_input_rights:"NOT_APPROVED",
        independent_conflict_proven:false,review_needed:false,
        model_review_executed:false,external_model_call_allowed:false,
        actual_provider_calls:0,db_writes:0,
      });
    }
    if(req.method()==="GET"&&path==="/api/simulation/jev/entry-routing"){
      const capture=new URL(req.url()).searchParams.get("capture_id");
      return fulfill(route,{
        version:"JEV_LIVE_04R_P5_ENTRY_ROUTING_V1",read_only:true,
        capture_id:capture,canonical_capture_id:capture,
        status:"COMPLETE",entry_count:1,
        counts:{LOCAL_MATCH:1,LOCAL_CONFLICT:0,LOCAL_INCOMPLETE:0,LOCAL_AMBIGUOUS:0,
          RESIDUAL_READY:0,RESIDUAL_BLOCKED:0,BLOCKED_EVIDENCE:0},
        rows:[{sample_index:0,market:"KOSPI",ticker:"145720",rank:1,
          snapshot_hash:"authored-snapshot",routing:"LOCAL_MATCH",semantic_status:"LOCAL_MATCH",
          local_v4_status:"SKIPPED_LOCAL",v4_state_hash:null,strategy_identity:"LEGACY_DERIVED",
          source_v2_valid:true,provider_decision:"HOLD",reason_codes:[]}],
        review_eligible_count:0,external_model_call_allowed:false,actual_provider_calls:0,db_writes:0,
      });
    }
    if(req.method()==="GET"&&path==="/api/health")return fulfill(route,{status:"ok"});
    if(req.method()==="GET"&&path==="/api/providers/status")return fulfill(route,{krx:{configured:false,role:"MOCK_BLOCKED"},dart:{configured:false,role:"MOCK_BLOCKED"},naver_news:{configured:false,provider_kind:"MOCK",role:"MOCK_BLOCKED"},kis:{enabled:false,role:"MOCK_BLOCKED"},real_trading:false});
    if(req.method()==="GET"&&path==="/api/holdings/stocks")return fulfill(route,[]);
    if(req.method()==="GET")return fulfill(route,{items:[],status:"DISABLED",available:false});
    violations.push(path);return fulfill(route,{detail:"Blocked by P0-03 E2E sandbox"},503);
  });
  await page.addInitScript((prior)=>{
    const key="stockscope.scanner.session.v0.21.4-A.3";
    if(!window.sessionStorage.getItem(key)){
      window.sessionStorage.setItem(key,JSON.stringify({
        schemaVersion:1,scope:"ALL",result:prior,completedAt:Date.now(),scrollY:0,
        showMore:false,expandedEvidenceIds:[],selectedCandidateKey:"KOSPI-145720",
      }));
    }
    window.localStorage.setItem("stockscope-jev-review-enabled","off");
  },oldResult);
  await page.goto("/scanner");
  await expect(page.getByRole("button",{name:"이 후보 최신 확정 일봉으로 다시 판단"})).toBeVisible();
  return {calls,violations,pageErrors};
}
test("button → job completion → LOW_LIQUIDITY → no unrelated auto-selected stock",async({page})=>{
  const {calls,violations}=await setup(page);
  await page.getByRole("button",{name:"이 후보 최신 확정 일봉으로 다시 판단"}).click();
  await expect(page.getByText("기본 필터 사유 ·")).toBeVisible();
  await expect(page.getByText(/기본 유동성 기준보다 낮습니다/)).toBeVisible();
  await expect(page.getByText(/실행 작업 · fixture-p003-job/)).toBeVisible();
  await expect(page.getByText(new RegExp(captureId))).toBeVisible();
  await expect(page.getByText(/자동 선택하지 않았습니다/)).toBeVisible();
  await expect(page.locator(".scanner-selected-detail")).toHaveCount(0);
  await expect(page.getByRole("button",{name:/가상 다른 후보 선택/})).toHaveAttribute("aria-pressed","false");
  const posted=calls.find(x=>x.path==="/api/backtest/scanner/jobs");
  expect(posted?.body?.recheck_candidate).toMatchObject({market:"KOSPI",code:"145720",source_data_date:previousDate});
  expect(posted?.body?.force_refresh).toBe(true);
  expect(posted?.body?.allow_large_sync).toBe(false);
  expect(violations).toEqual([]);
  await page.reload();
  await expect(page.locator(".scanner-selected-detail")).toHaveCount(0);
  await page.getByRole("button",{name:/가상 다른 후보 선택/}).click();
  await expect(page.locator(".scanner-selected-detail")).toContainText("가상 다른 후보");
});
test("matching target remains selected after a real browser Job",async({page})=>{
  const {calls,violations}=await setup(page,{matched:true});
  await page.getByRole("button",{name:"이 후보 최신 확정 일봉으로 다시 판단"}).click();
  await expect(page.getByText(/새 Scanner 후보 목록에서 확인/)).toBeVisible();
  await expect(page.locator(".scanner-selected-detail")).toContainText("가상 이전 후보");
  await expect(page.getByRole("button",{name:/가상 이전 후보 선택/})).toHaveAttribute("aria-pressed","true");
  expect(calls.find(x=>x.path==="/api/backtest/scanner/jobs")?.body?.recheck_candidate?.code).toBe("145720");
  expect(violations).toEqual([]);
});

test("G2-04 analysis/history tabs preserve current Scanner selection and rerun only on click",async({page})=>{
  const {calls,violations,pageErrors}=await setup(page,{matched:true});
  const analysis=page.getByRole("tab",{name:/이번 분석/});
  const history=page.getByRole("tab",{name:"저장 기록"});
  await expect(analysis).toHaveAttribute("aria-selected","true");
  await expect(page.getByRole("button",{name:/가상 이전 후보 선택/})).toHaveAttribute("aria-pressed","true");
  await history.click();
  await expect(history).toHaveAttribute("aria-selected","true");
  await expect(page.getByRole("region",{name:"저장 후보 날짜별 관찰"})).toBeVisible();
  await expect(page.getByRole("button",{name:/가상 이전 후보 선택/})).toBeHidden();
  expect(calls.filter(x=>x.method==="POST"&&x.path==="/api/backtest/scanner/jobs")).toHaveLength(0);
  await history.press("Home");
  await expect(analysis).toHaveAttribute("aria-selected","true");
  await expect(analysis).toBeFocused();
  await expect(page.getByRole("button",{name:/가상 이전 후보 선택/})).toHaveAttribute("aria-pressed","true");
  await expect(page.getByRole("button",{name:"후보 다시 찾기"})).toBeVisible();
  await page.getByRole("button",{name:"후보 다시 찾기"}).click();
  await expect.poll(()=>calls.filter(x=>x.method==="POST"&&x.path==="/api/backtest/scanner/jobs").length).toBe(1);
  const post=calls.find(x=>x.method==="POST"&&x.path==="/api/backtest/scanner/jobs");
  expect(post?.body?.force_refresh).toBe(false);
  expect(post?.body?.allow_large_sync).toBe(false);
  await expect(analysis).toHaveAttribute("aria-selected","true");
  expect(violations).toEqual([]);
  expect(pageErrors).toEqual([]);
});



test("P4 Horizon selector keeps the original Scanner control grid readable at desktop and mobile sizes",async({page})=>{
  const {calls,violations,pageErrors}=await setup(page,{matched:true});
  const card=page.locator(".scanner-control-card");
  const intro=card.locator(":scope > div:first-child p");
  const market=card.locator(".scanner-market-tabs");
  const actions=card.locator(".scanner-control-actions");
  const horizon=card.locator(".scanner-horizon-control");
  const choice=page.getByLabel("검토 기간");

  for (const {width,maxHeight,minIntroWidth} of [
    {width:1400,maxHeight:330,minIntroWidth:170},
    {width:900,maxHeight:450,minIntroWidth:150},
    {width:420,maxHeight:550,minIntroWidth:130},
  ]) {
    await page.setViewportSize({width,height:800});
    await expect(card).toBeVisible();
    await expect(choice).toBeVisible();
    const [cardBox,introBox,marketBox,actionsBox,horizonBox]=await Promise.all([
      card.boundingBox(),intro.boundingBox(),market.boundingBox(),
      actions.boundingBox(),horizon.boundingBox(),
    ]);
    expect(cardBox?.height, "Scanner control card must not become a towering grid at "+width).toBeLessThan(maxHeight);
    expect(introBox?.width, "Market description must not collapse into one-character lines at "+width).toBeGreaterThan(minIntroWidth);
    expect(horizonBox.y, "Horizon must sit below the first row at "+width).toBeGreaterThan(actionsBox.y);
    expect(horizonBox.y, "Horizon must sit below the market row at "+width).toBeGreaterThan(marketBox.y);
    expect(horizonBox.width, "Horizon must span the control card width at "+width).toBeGreaterThan(cardBox.width*0.75);
    const overflow=await card.evaluate(el=>el.scrollWidth-el.clientWidth);
    expect(overflow,"The controls must not overflow horizontally at "+width).toBeLessThanOrEqual(2);
  }

  await page.setViewportSize({width:1400,height:800});
  await choice.selectOption("SHORT");
  await expect(choice).toHaveValue("SHORT");
  await page.getByRole("button",{name:"후보 다시 찾기"}).click();
  await expect.poll(()=>calls.filter(c=>c.path==="/api/backtest/scanner/jobs"&&c.method==="POST").length).toBe(1);
  const request=calls.find(c=>c.path==="/api/backtest/scanner/jobs"&&c.method==="POST");
  expect(request.body).toMatchObject({
    horizon_intent:"SHORT",
    horizon_purpose:"LOCAL_REVIEW_ONLY",
  });
  await page.reload();
  await expect(page.getByLabel("검토 기간")).toHaveValue("SHORT");
  expect(violations).toEqual([]);
  expect(pageErrors).toEqual([]);
});


test("P5 selected candidate shows local-only batch verdict without any model POST or grid regression",async({page})=>{
  const {calls,violations,pageErrors}=await setup(page);
  await page.getByRole("tab",{name:"AI 검토"}).click();
  await page.locator('[data-jev-developer-details="true"] > summary').click();
  const summary=page.locator('[data-jev-entry-summary="p5"]');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("진입 후보:");
  await expect(summary).toContainText("의미 일치 1개");
  await expect(page.locator('[data-jev-entry-route="LOCAL_MATCH"]')).toContainText("JEV 추가 검토 불필요");
  await expect(page.locator('[data-jev-independent-event="p6a"]')).toContainText("확인된 독립 이벤트 근거 없음");
  await expect(page.locator('[data-jev-event-assessment="p6b"]')).toContainText("확인된 이벤트 근거 없음");
  await expect(page.locator('[data-jev-real-event-inventory="p6d"]')).toContainText("저장된 원천 이벤트 자료 0건");
  await expect(page.locator('[data-jev-event-v5="p6c"]')).toContainText("참고 이벤트 없음");
  await expect(page.locator('[data-jev-event-v5="p6c"]')).toContainText("모델 미실행");
  expect(calls.filter(x=>x.method==="POST"&&x.path.includes("/event-v5"))).toHaveLength(0);
  expect(calls.filter(x=>x.path==="/api/simulation/jev/independent-event-reference"&&x.method==="GET").length).toBeGreaterThan(0);
  await expect(page.getByRole("button",{name:"로컬 검토 완료 · JEV 호출 불필요"})).toBeDisabled();
  expect(calls.filter(x=>x.method==="POST"&&x.path.includes("/jev/reviews"))).toHaveLength(0);
  expect(calls.filter(x=>x.method==="POST"&&x.path==="/api/backtest/scanner/jobs")).toHaveLength(0);
  const card=page.locator(".scanner-control-card");
  expect((await card.boundingBox()).height).toBeLessThan(330);
  expect(violations).toEqual([]);
  expect(pageErrors).toEqual([]);
});


test("P6-E actual DART display requires explicit click; no evidence storage or model submission",async({page})=>{
  const {calls,violations,pageErrors}=await setup(page);
  await page.getByRole("tab",{name:"AI 검토"}).click();
  await page.locator('[data-jev-developer-details="true"] > summary').click();
  const disclosure=page.locator('[data-jev-live-dart="p6e"]');
  await expect(disclosure).toBeVisible();
  expect(calls.filter(x=>x.path.includes("/dart/stocks/"))).toHaveLength(0);
  await disclosure.locator("summary").click();
  await disclosure.getByRole("button",{name:"공시 새로 조회"}).click();
  await expect(disclosure.locator('[data-jev-live-dart-count="true"]')).toContainText("실제 조회 1건");
  await expect(disclosure.locator('[data-jev-p6f-ingest-preview="true"]')).toContainText("정규화 후보 1건");
  await expect(disclosure.locator('[data-jev-p6f-ingest-preview="true"]')).toContainText("실제 DB 저장 0건");
  await expect(disclosure.getByRole("link",{name:/검증용 공시/})).toHaveAttribute(
    "href","https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261022000001"
  );
  await expect(disclosure).toContainText("EventEvidence 영구 저장: 미승인·미실행");
  expect(calls.filter(x=>x.path==="/api/dart/stocks/145720/disclosures"&&x.method==="GET")).toHaveLength(1);
  expect(calls.filter(x=>x.method==="POST"&&x.path.includes("/jev/"))).toHaveLength(0);
  expect(violations).toEqual([]);
  expect(pageErrors).toEqual([]);
});


test("A: compact JEV status renders without hidden diagnostics or model calls; mobile layout fits",async({page})=>{
  const {calls,violations,pageErrors}=await setup(page);
  await page.getByRole("tab",{name:"AI 검토"}).click();
  const main=page.locator('[data-jev-a-summary="true"]');
  const compact=page.locator('[data-jev-primary-summary="true"]');
  const developer=page.locator('[data-jev-developer-details="true"]');
  await expect(compact).toBeVisible();
  await expect(compact).toContainText("가상 이전 후보 (145720)");
  await expect(compact).toContainText("Scanner 판단");
  await expect(compact).toContainText("관망");
  await expect(compact).toContainText("현재 서버에서 JEV 사용 불가");
  await expect(compact.getByRole("button",{name:"JEV 검토 실행 (사용 불가)"})).toBeDisabled();
  await expect(developer).not.toHaveAttribute("open","");
  await expect(page.locator('[data-jev-entry-summary="p5"]')).toHaveCount(0);
  await expect(page.locator('[data-jev-live-dart="p6e"]')).toHaveCount(0);
  await expect(page.locator('[data-jev-event-v5="p6c"]')).toHaveCount(0);
  expect(calls.filter(x=>[
    "/api/simulation/jev/entry-routing",
    "/api/simulation/jev/independent-event-reference",
    "/api/simulation/jev/independent-event-assessment",
    "/api/simulation/jev/event-v5-routing",
    "/api/simulation/jev/event-data-audit",
  ].includes(x.path))).toHaveLength(0);
  expect(calls.filter(x=>x.method==="POST"&&x.path.includes("/jev/"))).toHaveLength(0);
  for(const width of [1360,390]){
    await page.setViewportSize({width,height:800});
    await expect(compact).toBeVisible();
    const rect=await compact.boundingBox();
    expect(rect?.height).toBeLessThan(265);
    const overflow=await compact.evaluate(el=>el.scrollWidth-el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(2);
  }
  await developer.locator(":scope > summary").click();
  await expect(page.locator('[data-jev-entry-summary="p5"]')).toBeVisible();
  await expect(page.locator('[data-jev-live-dart="p6e"]')).toBeVisible();
  await expect(page.locator('[data-jev-event-v5="p6c"]')).toBeVisible();
  expect(calls.filter(x=>x.method==="POST"&&x.path.includes("/jev/"))).toHaveLength(0);
  await developer.locator(":scope > summary").click();
  await expect(page.locator('[data-jev-entry-summary="p5"]')).toHaveCount(0);
  await expect(compact).toBeVisible();
  expect(violations).toEqual([]);
  expect(pageErrors).toEqual([]);
});
