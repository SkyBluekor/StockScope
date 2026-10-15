import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { scannerCandidateEvidence, scannerTieSummary } from "../src/components/scannerCandidateEvidence.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const panel = readFileSync(path.resolve(here, "../src/components/ScannerPanel.tsx"), "utf8");
const compare = readFileSync(path.resolve(here, "../src/components/ScannerRankComparison.tsx"), "utf8");

function candidate(code, distance, overrides = {}) {
  return {
    code, name: code, market: "KOSPI", action: "ENTRY_CANDIDATE",
    historical_fit: { status: "NOT_RUN" },
    risk: { status: "READY", warning: false },
    priority: {
      rank: Number(code), previous_rank: 3, rank_change: 2, tie_group: 1,
      tier: "READY", tie_size: 5, strict_rank: false,
      tie_breaker: "STRUCTURAL_TARGET_NEAREST_PROMOTE",
      historical_status: "DATA_UNAVAILABLE",
      structural_target_distance_pct: distance,
    },
    entry_risk_guide: {
      risk: {
        entry_reference_price: 100, invalidation_price: 95,
        target1_price: 105.25, rr1: 1.05,
        structural_target1_price: 100 + distance,
      },
    },
    ...overrides,
  };
}

test("S29 real-style five-way tie is not presented as a profitability leaderboard", () => {
  const rows = [candidate("001820", 4.0702), candidate("005830", 4.3173),
    candidate("010060", 6.6059), candidate("071090", 11.9822),
    candidate("093370", 7.0413)];
  assert.match(scannerTieSummary(rows), /5개 후보는 조건상 동률/);
  rows.forEach((row, i) => {
    const view = scannerCandidateEvidence(row, i);
    assert.match(view.orderLabel, /동률 5개/);
    assert.match(view.orderLabel, /표시/);
    assert.match(view.historicalLabel, /데이터 부족/);
    assert.equal(view.isForecastOrProvenProfit, false);
    assert.match(view.sameRunRankChangeLabel, /이번 분석 내 정렬 전/);
  });
  assert.match(scannerCandidateEvidence(rows[0], 0).tieExplanation, /종목코드/);
});

test("S29 1.05R Target1 and 2.38R structural estimate are never conflated", () => {
  const a = scannerCandidateEvidence(candidate("001820", 4.0702), 0);
  assert.equal(a.riskStatus, "CHECKED");
  assert.equal(a.target1R, 1.05);
  assert.equal(a.structuralR, 0.81);
  assert.match(a.riskLabel, /1.05R/);
  const high = candidate("071090", 11.9822, {
    entry_risk_guide: { risk: {
      entry_reference_price: 100, invalidation_price: 95,
      target1_price: 107.5, structural_target1_price: 111.9822, rr1: 1.5,
    } },
  });
  const b = scannerCandidateEvidence(high, 3);
  assert.equal(b.target1R, 1.5);
  assert.equal(b.structuralR, 2.4);
  assert.match(b.structuralLabel, /2.40R/);
});

test("S29 missing or invalid risk prices are NOT made up", () => {
  const missing = candidate("001820", 4, { entry_risk_guide: null });
  const unknown = scannerCandidateEvidence(missing, 0);
  assert.equal(unknown.riskStatus, "MISSING_REFERENCE");
  assert.equal(unknown.target1R, null);
  assert.match(unknown.riskLabel, /근거 부족/);

  const wrong = candidate("001820", 4, { entry_risk_guide: { risk: {
    entry_reference_price: 100, invalidation_price: 101,
    target1_price: 110, rr1: 1.3,
  } } });
  const bad = scannerCandidateEvidence(wrong, 0);
  assert.equal(bad.riskStatus, "INVALID_REFERENCE");
  assert.equal(bad.target1R, null);
});

test("S29 mismatched engine risk ratio surfaces review instead of a positive signal", () => {
  const wrong = candidate("001820", 4, { entry_risk_guide: { risk: {
    entry_reference_price: 100, invalidation_price: 95,
    target1_price: 107.5, structural_target1_price: 104, rr1: 12,
  } } });
  assert.equal(scannerCandidateEvidence(wrong, 0).riskStatus, "ENGINE_DISAGREEMENT");
  assert.match(scannerCandidateEvidence(wrong, 0).riskLabel, /재검토 필요/);
});

test("S29 legacy candidates without tie metadata are not invented strict winners", () => {
  const legacy = candidate("005930", 2, { priority: {
    tier: "READY", rank: 1, historical_status: "NOT_RUN",
  } });
  const label = scannerCandidateEvidence(legacy, 0).orderLabel;
  assert.match(label, /수익률 순위 아님/);
  assert.doesNotMatch(label, /동률 5개/);
  assert.match(scannerTieSummary([legacy]), /수익률 순위가 아니에요/);
});

test("S29 UI renders rank caution and distinct Target1-R on list and detail without changing engine", () => {
  assert.match(panel, /scannerCandidateEvidence\(candidate, rank - 1\)/);
  assert.match(panel, /scannerTieSummary\(\[\.\.\.result\.candidates, \.\.\.result\.more_candidates\]\)/);
  assert.match(panel, /scanner-s29-metric/);
  assert.match(panel, /s29\.structuralLabel/);
  assert.match(panel, /5·10·20거래일 성과는 별도 사전 기록/);
  assert.match(compare, /실제 수익률의 우열은 확인되지 않았어요/);
});
