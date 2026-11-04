import assert from "node:assert/strict";
import test from "node:test";
import { holdingProtectionSummary as review } from "../src/components/holdingProtectionSummary.ts";

function pos(id="p1") { return {position_id:id,status:"OPEN",quantity:"20",average_price:"9000"}; }
function stock() { return {stock_id:"stock-1",ticker:"012210",market:"KOSDAQ",is_held:true,positions:[pos()]}; }
function watch(overrides={}) {
  return {
    available:true, migration_required:false, policy_enabled:false,
    blocked_reason:"POLICY_RESEARCH", setting:null, rules:[], open_gaps:[],
    latest_notification:null, position_id:"p1", ...overrides,
  };
}
function management(active_plan=null, management_state="NO_PLAN") {
  return {position_id:"p1",active_plan,management_state};
}
function context({
  mgmt=management(), decision=null, w=watch(),
  mgmtStatus="AVAILABLE",decisionStatus="AVAILABLE",watchStatus="AVAILABLE",
  ledgerStatus="VALID", stockId="stock-1",
}={}) {
  return {
    stock:{stock_id:stockId,ticker:"012210",market:"KOSDAQ"},
    context_identity:{stock_id:stockId,market_confirmed_date:"2026-10-19"},
    source_status:{
      ledger:{status:ledgerStatus,reason_code:null},
      management:{status:mgmtStatus,reason_code:null},
      decision:{status:decisionStatus,reason_code:null},
      watch:{status:watchStatus,reason_code:null},
    },
    management:mgmtStatus==="AVAILABLE"?{positions:[mgmt]}:null,
    positions:[{position:pos(),management:mgmt,decision,watch:w}],
  };
}
function plan() {
  return {plan_id:"plan-1",position_id:"p1",status:"ACTIVE",version:1,
    stop_price:"8940",target1_price:"12540"};
}
function decision(overrides={}) {
  return {decision_id:"decision-1",position_id:"p1",status:"ACTIONABLE",
    effective_status:"ACTIONABLE",stale:false,...overrides};
}
test("unloaded or missing same-stock source fails closed, never guesses absence",()=>{
  assert.equal(review(stock(),null,true).state,"LOADING");
  assert.equal(review(stock(),null,false).state,"SOURCE_UNVERIFIED");
  assert.equal(review(stock(),context({stockId:"other"}),false).state,"SOURCE_UNVERIFIED");
  assert.equal(review(stock(),context({ledgerStatus:"UNAVAILABLE"}),false).state,"SOURCE_UNVERIFIED");
});
test("registered holdings without applied plan and decision highlights both and policy guard",()=>{
  const x=review(stock(),context(),false);
  assert.equal(x.state,"REVIEW_NEEDED");
  assert.equal(x.positionCount,1);
  assert.equal(x.plan.state,"NONE");
  assert.equal(x.decision.state,"NOT_CREATED");
  assert.equal(x.watch.state,"POLICY_UNVERIFIED");
  assert.match(x.headline,/관리 계획이 없어요/);
  assert.equal(x.hasBrokerBalanceProof,false);
  assert.equal(x.hasLiveWatchProof,false);
  assert.equal(x.hasExecutedStopProof,false);
});
test("missing management source is UNKNOWN not no applied plan",()=>{
  const x=review(stock(),context({mgmtStatus:"UNAVAILABLE"}),false);
  assert.equal(x.plan.state,"SOURCE_UNVERIFIED");
  assert.equal(x.state,"SOURCE_UNVERIFIED");
  assert.doesNotMatch(x.plan.label,/없음/);
});
test("decision migration is unverified rather than no decision",()=>{
  const x=review(stock(),context({decisionStatus:"MIGRATION_REQUIRED"}),false);
  assert.equal(x.decision.state,"SOURCE_UNVERIFIED");
});
test("applied plan evidence is not live watch/order proof",()=>{
  const x=review(stock(),context({
    mgmt:management(plan(),"WITHIN_PLAN"),
    decision:decision(),
    w:watch({policy_enabled:true,setting:{
      setting_id:"setting-1",plan_id:"plan-1",plan_version:1,status:"ACTIVE",policy_version:"v1",
    }}),
  }),false);
  assert.equal(x.plan.state,"APPLIED");
  assert.equal(x.decision.state,"SAVED");
  assert.equal(x.watch.state,"SETTING_PRESENT");
  assert.equal(x.state,"RECORDED_ONLY");
  assert.equal(x.hasLiveWatchProof,false);
  assert.equal(x.hasExecutedStopProof,false);
});
test("EOD stop breach flags manual review, not executed sell",()=>{
  const x=review(stock(),context({
    mgmt:management(plan(),"STOP_BREACHED"),decision:decision({primary_action:"STOP"}),
  }),false);
  assert.equal(x.plan.state,"REFERENCE_BREACHED");
  assert.equal(x.state,"REVIEW_NEEDED");
  assert.match(x.nextAction,/자동 손절이나 매도는 실행하지 않았습니다/);
});
test("stale, conflict and insufficient EOD decisions cannot appear current",()=>{
  for(const change of [{stale:true},{effective_status:"STALE"},{status:"CONFLICT"},{status:"INSUFFICIENT_DATA"}]){
    const x=review(stock(),context({mgmt:management(plan()),decision:decision(change)}),false);
    assert.equal(x.decision.state,"RECHECK");
  }
});
test("Watch gaps and missing status cannot count as active runtime",()=>{
  const g=review(stock(),context({w:watch({open_gaps:[{gap_id:"gap-1",reason_code:"WS_GAP"}]})}),false);
  assert.equal(g.watch.state,"GAP_REPORTED");
  const bad=review(stock(),context({watchStatus:"PARTIAL"}),false);
  assert.equal(bad.watch.state,"SOURCE_UNVERIFIED");
  assert.equal(bad.state,"SOURCE_UNVERIFIED");
});
test("Watch setting absent when policy enabled is not claimed as running",()=>{
  const x=review(stock(),context({w:watch({policy_enabled:true})}),false);
  assert.equal(x.watch.state,"SETTING_ABSENT");
});
test("one OPEN record cannot silently consume another position plan",()=>{
  const x=review(stock(),context({mgmt:management({...plan(),position_id:"p2"})}),false);
  assert.equal(x.plan.state,"SOURCE_UNVERIFIED");
  assert.equal(x.hasExecutedStopProof,false);
});
test("context position mismatch, duplicate, closed stock and wrong market block",()=>{
  const c=context();
  c.positions[0].position.position_id="p2";
  assert.equal(review(stock(),c,false).state,"SOURCE_UNVERIFIED");
  const duplicate=stock();duplicate.positions=[pos("p1"),pos("p1")];
  assert.equal(review(duplicate,context(),false).state,"SOURCE_UNVERIFIED");
  const closed=stock();closed.positions=[{...pos(),status:"CLOSED"}];closed.is_held=false;
  assert.equal(review(closed,context(),false).state,"SOURCE_UNVERIFIED");
  const wrong=stock();wrong.market="KOSPI";
  assert.equal(review(wrong,context(),false).state,"SOURCE_UNVERIFIED");
});
test("pure projection never mutates existing holdings/context input",()=>{
  const s=stock(), c=context();
  const sb=structuredClone(s),cb=structuredClone(c);
  review(s,c,false);
  assert.deepEqual(s,sb);
  assert.deepEqual(c,cb);
});
