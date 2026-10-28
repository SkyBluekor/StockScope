import assert from "node:assert/strict";
import test from "node:test";
import { scannerPolicyReadiness } from "../src/components/scannerPolicyReadiness.ts";

const legacy = { policy_source: "LEGACY_CURRENT_10_FALLBACK", fallback_used: true };
const active = { policy_source: "ACTIVE_SELECTION_POLICY", fallback_used: false };
const rollback = { policy_source: "ROLLBACK_FALLBACK", fallback_used: true };
const entry = (id = null, hash = null) => ({
  action: "ENTRY_CANDIDATE", strategy_version_id: id, strategy_definition_hash: hash,
});
const reference = { action: "WAIT", strategy_version_id: null, strategy_definition_hash: null };

test("real 9 legacy entry and 6 references never mislabel as locally validated", () => {
  const result = scannerPolicyReadiness(legacy, [
    ...Array.from({ length: 9 }, () => entry()),
    ...Array.from({ length: 6 }, () => reference),
  ], false);
  assert.equal(result.status, "LEGACY_IDENTITY_LIMITED");
  assert.equal(result.candidateEntryCount, 9);
  assert.equal(result.missingOriginalIdentityCount, 9);
  assert.match(result.message, /LEGACY_LIMITED/);
  assert.match(result.message, /자동으로 LOCAL_VALIDATED로 바꾸지 않습니다/);
});

test("active verified identity metadata is NOT falsely advertised as S7 PASS", () => {
  const result = scannerPolicyReadiness(active, [entry("policy-version-1", "hash1")], false);
  assert.equal(result.status, "PINNED_IDENTITY_PRESENT");
  assert.equal(result.missingOriginalIdentityCount, 0);
  assert.match(result.message, /S7 검증/);
  assert.match(result.message, /보장하지 않습니다/);
});

test("rollback still needs explicit S7 proof and cached result cannot claim original engine pass", () => {
  const result = scannerPolicyReadiness(rollback, [entry("version", "hash")], true);
  assert.equal(result.status, "PINNED_IDENTITY_PRESENT");
  assert.match(result.message, /캐시 결과/);
  assert.match(result.message, /보장할 수 없습니다/);
});

test("missing identity on active policy is NOT retroactively invented", () => {
  const result = scannerPolicyReadiness(active, [
    entry("version", null), entry(null, "hash"), reference,
  ], false);
  assert.equal(result.status, "PINNED_IDENTITY_INCOMPLETE");
  assert.equal(result.candidateEntryCount, 2);
  assert.equal(result.missingOriginalIdentityCount, 2);
  assert.match(result.message, /채워 넣지 않습니다/);
});

test("unavailable policy fails closed even if candidate fields appear", () => {
  const result = scannerPolicyReadiness(undefined, [entry("version", "hash")], false);
  assert.equal(result.status, "POLICY_UNKNOWN");
  assert.match(result.message, /확정할 수 없습니다/);
});
