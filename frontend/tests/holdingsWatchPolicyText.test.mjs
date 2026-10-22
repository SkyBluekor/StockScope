import assert from "node:assert/strict";
import test from "node:test";
import { holdingsWatchPolicyText as explain } from "../src/components/holdingsWatchPolicyText.ts";

test("known production Watch block reason has plain Korean explanation", () => {
  const result = explain({
    available: true, migration_required: false, policy_enabled: false,
    blocked_reason: "OPERATING_THRESHOLDS_UNAPPROVED",
  });
  assert.equal(result.title, "Watch 운영 정책 비활성");
  assert.match(result.explanation, /관측 횟수/);
  assert.match(result.explanation, /시세 유효시간/);
  assert.equal(result.runtimeConfirmed, false);
});
test("missing Watch API evidence is not interpreted as disabled or enabled", () => {
  for (const evidence of [undefined, null, {available:false, policy_enabled:false, migration_required:false, blocked_reason:null}]) {
    const result = explain(evidence);
    assert.match(result.title, /확인 불가/);
    assert.equal(result.approved, false);
    assert.equal(result.runtimeConfirmed, false);
  }
});
test("migration required takes precedence over activation flag", () => {
  const result = explain({policy_enabled:true,migration_required:true,blocked_reason:null});
  assert.match(result.title, /저장 구조/);
  assert.equal(result.approved,false);
});
test("unknown blocked reason cannot be misrepresented as approved thresholds", () => {
  const result = explain({policy_enabled:false,migration_required:false,blocked_reason:"OTHER"});
  assert.match(result.explanation,/운영 정책이 활성화되지 않았습니다/);
  assert.doesNotMatch(result.explanation,/유효시간이 아직 승인/);
});
test("enabled Watch policy does not prove monitoring heartbeat or broker protection", () => {
  const result = explain({policy_enabled:true,migration_required:false,blocked_reason:null});
  assert.equal(result.approved,true);
  assert.equal(result.runtimeConfirmed,false);
  assert.match(result.title,/별도 확인/);
  assert.match(result.explanation,/heartbeat/);
});
