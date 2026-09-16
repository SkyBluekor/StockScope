declare const require: any;
declare const process: any;

const fs = require("fs");
const path = require("path");

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function resolveFrontendRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "src", "styles.css"))) return cwd;
  const nested = path.join(cwd, "frontend");
  if (fs.existsSync(path.join(nested, "src", "styles.css"))) return nested;
  throw new Error(`frontend root not found from ${cwd}`);
}

const frontendRoot = resolveFrontendRoot();
const css = fs.readFileSync(path.join(frontendRoot, "src", "styles.css"), "utf8");
const app = fs.readFileSync(path.join(frontendRoot, "src", "App.tsx"), "utf8");

assert(app.includes('className="strategy-detail-selected"'), "selected strategy detail markup missing");
assert(app.includes('<article className="strategy-row top">'), "selected detail no longer reuses strategy-row; review this regression test");

const hotfixStart = css.indexOf("v0.21.4-B.2.2.2a · Strategy tab layout hotfix");
assert(hotfixStart >= 0, "B.2.2.2a hotfix block missing");
const hotfix = css.slice(hotfixStart, hotfixStart + 5000);

assert(
  /\.strategy-detail-selected \.strategy-row\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(104px,\s*120px\)/.test(hotfix),
  "selected strategy detail must use a two-column body/score grid",
);
assert(
  /\.strategy-detail-selected \.strategy-score\s*\{[\s\S]*?grid-column:\s*auto/.test(hotfix),
  "legacy strategy-score grid-column placement is not neutralized",
);
assert(
  /\.strategy-detail-selected \.strategy-info\s*\{[\s\S]*?word-break:\s*keep-all/.test(hotfix),
  "Korean strategy copy must preserve word boundaries",
);
assert(!/\.strategy-detail-selected[^\{]*\{[^}]*word-break:\s*break-all/.test(hotfix), "break-all reintroduced in selected strategy detail");
assert(!/\.strategy-detail-selected[^\{]*\{[^}]*overflow-wrap:\s*anywhere/.test(hotfix), "overflow-wrap:anywhere reintroduced in selected strategy detail");
assert(
  /@media \(max-width:\s*700px\)[\s\S]*?\.strategy-detail-selected \.strategy-row\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/.test(hotfix),
  "narrow-width stack rule missing",
);

console.log("strategyLayoutRegression v0.21.4-B.2.2.2a: PASS (two-column detail, Korean wrapping, narrow stack)");
