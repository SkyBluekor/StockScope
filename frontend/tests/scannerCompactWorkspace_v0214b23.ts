declare const require: any;
declare const process: any;

const fs = require("fs");
const path = require("path");

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function frontendRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "src", "components", "ScannerPanel.tsx"))) return cwd;
  const nested = path.join(cwd, "frontend");
  if (fs.existsSync(path.join(nested, "src", "components", "ScannerPanel.tsx"))) return nested;
  throw new Error(`frontend root not found from ${cwd}`);
}

const root = frontendRoot();
const panel = fs.readFileSync(path.join(root, "src", "components", "ScannerPanel.tsx"), "utf8");
const session = fs.readFileSync(path.join(root, "src", "components", "scannerSession.ts"), "utf8");
const css = fs.readFileSync(path.join(root, "src", "styles.css"), "utf8");

assert(panel.includes("function CandidateCompareRow"), "compact candidate comparison row missing");
assert(panel.includes("function CandidateDetail"), "single selected candidate detail renderer missing");
assert(panel.includes('className="scanner-compare-list"'), "candidate comparison list missing");
assert(panel.includes('className={`scanner-selected-detail tone-${tone}`}'), "selected candidate detail surface missing");
assert(panel.includes("selectedCandidateKey"), "selected candidate state missing");
assert(panel.includes("setSelectedCandidateKey(latest.result.candidates[0]"), "new analysis must reset selection to first candidate");
assert(session.includes("selectedCandidateKey?: string | null"), "selected candidate session persistence missing");
assert(!panel.includes("<CandidateCard"), "legacy full candidate cards are still rendered for every candidate");

const detailRenderCount = (panel.match(/<CandidateDetail/g) ?? []).length;
assert(detailRenderCount === 1, `expected one selected candidate detail render site, got ${detailRenderCount}`);

const b23Start = css.indexOf("v0.21.4-B.2.3 · Scanner Compact Decision Workspace");
assert(b23Start >= 0, "B.2.3 scanner compact CSS block missing");
const b23 = css.slice(b23Start);
assert(b23.includes(".scanner-compare-row"), "compact row CSS missing");
assert(b23.includes(".scanner-selected-detail"), "selected detail CSS missing");
assert(b23.includes("@media (max-width: 820px)"), "1024-to-mobile responsive transition missing");
assert(!/font-size\s*:\s*(?:[0-9]|1[0-3](?:\.[0-9]+)?)px/i.test(b23), "B.2.3 reintroduced hard-coded font below 14px");

console.log("scannerCompactWorkspace v0.21.4-B.2.3: PASS (compact comparison, one selected detail, session persistence, readable responsive CSS)");
