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

assert(panel.includes("STOCK SCANNER · v0.21.4-B.2.3"), "B.2.3 lineage UI version marker missing");
assert(panel.includes("function emptyCandidateMessage"), "user-facing empty-state guard missing");
assert(panel.includes("/\\bNO[_ -]?TRADE\\b/i.test(raw)"), "NO_TRADE leak guard missing");
assert(panel.includes("현재 조건에 맞는 후보가 없습니다."), "neutral no-candidate heading missing");
assert(panel.includes("후보가 없는 것도 정상적인 분석 결과입니다."), "no-candidate explanatory copy missing");
assert(panel.includes('role="status" aria-live="polite"'), "no-candidate status accessibility missing");
assert(panel.includes("setExpandedEvidenceIds([])"), "new Scanner run must collapse historical evidence");
assert(panel.includes("setSelectedCandidateKey(latest.result.candidates[0]"), "new Scanner run must select first candidate");
assert(session.includes("selectedCandidateKey?: string | null"), "selected candidate must remain session-persisted");
assert(session.includes('typeof parsed.selectedCandidateKey === "string"'), "selected candidate restore guard missing");

const b23Start = css.indexOf("v0.21.4-B.2.3 · Scanner Compact Decision Workspace");
const b231Start = css.indexOf("v0.21.4-B.2.3.1 · Scanner Compact Runtime Validation & Polish");
assert(b23Start >= 0 && b231Start > b23Start, "Scanner compact CSS version blocks missing");
const compactCss = css.slice(b23Start, b231Start);
const polishCss = css.slice(b231Start);
assert(compactCss.includes("@media (max-width: 1200px)"), "desktop/sidebar-aware compact breakpoint must start by 1200px");
assert(compactCss.includes("@media (max-width: 820px)"), "narrow candidate stacking breakpoint missing");
assert(compactCss.includes(".scanner-compare-metrics {\n    grid-template-columns: repeat(2, minmax(0, 1fr));"), "mid-width comparison metrics must be 2x2");
assert(compactCss.includes(".scanner-decision-price-band { grid-template-columns: repeat(3, minmax(0, 1fr)); }"), "mid-width detail prices must wrap 3+2");
assert(polishCss.includes(".scanner-workspace .scanner-no-candidate small"), "B.2.3.1 CSS must stay Scanner-scoped");
assert(!/font-size\s*:\s*(?:[0-9]|1[0-3](?:\.[0-9]+)?)px/i.test(polishCss), "B.2.3.1 reintroduced sub-14px text");

console.log("scannerCompactRuntimeRegression v0.21.4-B.2.3.1: PASS");
