import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { buildScannerDisplayLayout } from "../src/components/scannerDisplayGroups.ts";

function candidate(code, tieGroup = null, tieSize = null, rank = null) {
  return {
    code, name: code, market: "KOSPI",
    action: "ENTRY_CANDIDATE",
    priority: tieGroup == null ? { rank } : {
      rank, tier: "READY",
      tie_group: tieGroup, tie_size: tieSize, strict_rank: false,
      tie_breaker: "STRUCTURAL_TARGET_NEAREST_PROMOTE",
    },
  };
}
const flatten = (groups) => groups.flatMap(g => g.members.map(m => m.candidate.code));
function firstSix() {
  return Array.from({ length: 15 }, (_, i) =>
    candidate(String(i + 1).padStart(6, "0"),
      i < 6 ? 1 : i < 13 ? 2 : 3,
      i < 6 ? 6 : i < 13 ? 7 : 2, i + 1));
}

test("S30: original top 5 plus same-tie sixth stays visible, no candidate mutates", () => {
  const original = firstSix();
  const pristine = structuredClone(original);
  const layout = buildScannerDisplayLayout(original, 5);
  assert.equal(layout.originalFeaturedCount, 5);
  assert.equal(layout.visibleFeaturedCount, 6);
  assert.equal(layout.visibleOtherCount, 9);
  assert.equal(layout.originalOtherCount, 10);
  assert.equal(layout.expandedToKeepTieTogether, true);
  assert.equal(layout.featured[0].title, "동일 조건 후보 · 6종목");
  assert.equal(layout.featured[0].complete, true);
  assert.deepEqual(flatten(layout.featured), original.slice(0, 6).map(c => c.code));
  assert.deepEqual(flatten(layout.other), original.slice(6).map(c => c.code));
  assert.equal(layout.featured[0].members[5].fromOriginalMore, true);
  assert.equal(layout.featured[0].members[5].originalIndex, 5);
  assert.deepEqual(original, pristine);
});

test("S30: multiple contiguous tie groups are never split even when boundary crosses second group", () => {
  const rows = [
    candidate("000001", 1, 2, 1), candidate("000002", 1, 2, 2),
    candidate("000003", 2, 4, 3), candidate("000004", 2, 4, 4),
    candidate("000005", 2, 4, 5), candidate("000006", 2, 4, 6),
    candidate("000007", 3, 2, 7), candidate("000008", 3, 2, 8),
  ];
  const layout = buildScannerDisplayLayout(rows, 5);
  assert.equal(layout.visibleFeaturedCount, 6);
  assert.deepEqual(layout.featured.map(g => g.members.length), [2, 4]);
  assert.deepEqual(layout.other.map(g => g.members.length), [2]);
  assert.deepEqual([...flatten(layout.featured), ...flatten(layout.other)], rows.map(r => r.code));
});

test("S30: missing old tie metadata cannot fabricate a tie or reorder a candidate", () => {
  const rows = Array.from({ length: 8 }, (_, i) => candidate(String(i + 1)));
  const layout = buildScannerDisplayLayout(rows, 5);
  assert.equal(layout.expandedToKeepTieTogether, false);
  assert.equal(layout.featured.length, 5);
  assert.equal(layout.visibleOtherCount, 3);
  assert.ok(layout.featured.every(g => !g.tie && g.declaredSize === null));
});

test("S30: incomplete tie group is explicitly partial, not a trusted full cohort", () => {
  const rows = [
    candidate("000001", 1, 7, 1), candidate("000002", 1, 7, 2),
    candidate("000003", 1, 7, 3), candidate("000004", 1, 7, 4),
    candidate("000005", 1, 7, 5), candidate("000006", 1, 7, 6),
  ];
  const layout = buildScannerDisplayLayout(rows, 5);
  assert.equal(layout.featured.length, 1);
  assert.equal(layout.featured[0].complete, false);
  assert.equal(layout.featured[0].title, "동률 일부 확인 · 6/7종목");
  assert.match(layout.featured[0].explanation, /누락된 종목/);
  assert.equal(layout.expandedToKeepTieTogether, true);
});

test("S30: same group number with conflicting tier or size does not get merged", () => {
  const rows = [
    candidate("000001", 1, 2, 1), candidate("000002", 1, 2, 2),
    { ...candidate("000003", 1, 2, 3), priority: {
      ...candidate("000003", 1, 2, 3).priority, tier: "WAIT",
    } },
    candidate("000004", 1, 3, 4),
    candidate("000005", null, null, 5),
  ];
  const layout = buildScannerDisplayLayout(rows, 2);
  assert.equal(layout.featured.length, 1);
  assert.deepEqual(layout.other.map(g => g.members.length), [1, 1, 1]);
  assert.equal(layout.other[0].complete, false);
  assert.equal(layout.other[1].complete, false);
});

test("S30: selecting an originally-extra tie member has no duplicate pinned card", () => {
  const layout = buildScannerDisplayLayout(firstSix(), 5);
  const selectedSampleIndex = 5;
  const selectedIsExtra = selectedSampleIndex >= layout.visibleFeaturedCount;
  assert.equal(selectedIsExtra, false);
  const trulyExtra = 6 >= layout.visibleFeaturedCount;
  assert.equal(trulyExtra, true);
  assert.equal(layout.featured[0].members[5].originalIndex, selectedSampleIndex);
});

test("S30: read-only edge cases empty arrays and explicit zero-top do not add rows", () => {
  assert.deepEqual(buildScannerDisplayLayout([], 5).featured, []);
  const zero = buildScannerDisplayLayout([candidate("000001")], 0);
  assert.equal(zero.visibleFeaturedCount, 0);
  assert.equal(zero.visibleOtherCount, 1);
});

const root = path.dirname(fileURLToPath(import.meta.url));
const panel = readFileSync(path.resolve(root, "../src/components/ScannerPanel.tsx"), "utf8");
const summary = readFileSync(path.resolve(root, "../src/components/ScannerDecisionSummary.tsx"), "utf8");
const quote = readFileSync(path.resolve(root, "../src/components/scannerQuoteTruth.ts"), "utf8");
const style = readFileSync(path.resolve(root, "../src/components/scannerUX.css"), "utf8");

test("S30: UI uses merged display and stable original indices but does not change original backend arrays", () => {
  assert.match(panel, /buildScannerDisplayLayout\(allCandidates, result\?\.candidates\.length \?\? 0\)/);
  assert.match(panel, /displayLayout\.featured\.map/);
  assert.match(panel, /displayLayout\.other\.map/);
  assert.match(panel, /reviewFor\(candidate, member\.originalIndex\)/);
  assert.match(panel, /selectedSampleIndex >= displayLayout\.visibleFeaturedCount/);
  assert.match(panel, /member\.fromOriginalMore/);
  assert.match(panel, /선택 중인 추가 후보/);
  assert.match(panel, /분석일 · \{simpleConditionStatus\(candidate\)\}/);
  assert.match(panel, /현재 진입 판단 별도/);
  assert.doesNotMatch(panel, /rank_candidates\(/);
});

test("S30: explicit quote verification never impersonates present strategy or risk validation", () => {
  assert.match(summary, /현재 가격 미확인 · 지금 진입 판단 불가/);
  assert.match(summary, /새 시세 확인 실패 · 현재 진입 판단 보류/);
  assert.match(summary, /분석일 참고 범위 밖/);
  assert.match(summary, /현재 전략·위험 재검증 전/);
  assert.match(summary, /분석일 기준 · \{view\.headline\}/);
  assert.match(quote, /strategyRevalidated: false/);
  assert.match(style, /scanner-s30-group-heading/);
  assert.match(style, /scanner-s30-quote-hold/);
});
