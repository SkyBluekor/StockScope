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
const appPath = path.join(frontendRoot, "src", "App.tsx");
const app = fs.existsSync(appPath) ? fs.readFileSync(appPath, "utf8") : "";

const requiredTypographyTokens = [
  "--font-page-title",
  "--font-result-title",
  "--font-section-title",
  "--font-card-title",
  "--font-body",
  "--font-body-small",
  "--font-meta",
  "--font-badge",
  "--line-heading",
  "--line-body",
  "--line-compact",
  "--space-4",
  "--space-5",
  "--space-6",
];
for (const token of requiredTypographyTokens) {
  assert(css.includes(token), `missing readability token: ${token}`);
}

const tinyHardcoded: string[] = [];
const fontRegex = /font-size\s*:\s*([0-9.]+)px/gi;
let match: RegExpExecArray | null;
while ((match = fontRegex.exec(css))) {
  const value = Number(match[1]);
  if (value > 0 && value < 14) {
    const line = css.slice(0, match.index).split("\n").length;
    tinyHardcoded.push(`${line}: ${value}px`);
  }
}
assert(tinyHardcoded.length === 0, `hard-coded font below 14px detected:\n${tinyHardcoded.slice(0, 40).join("\n")}`);

assert(css.includes(".strategy-results.readability-compact"), "compact strategy layout styles missing");
assert(css.includes(".strategy-compact-list"), "compact strategy selector styles missing");
assert(css.includes(".strategy-detail-selected"), "selected strategy detail styles missing");
assert(app.includes("selectedStrategyIndex"), "strategy selection state missing");
assert(app.includes('className="strategy-compact-list"'), "strategy compact list markup missing");
assert(app.includes('className="strategy-detail-selected"'), "selected strategy detail markup missing");
assert(!app.includes('<details className="response-guide" open={index === 0}>'), "legacy ten-card response detail is still auto-open");

const selectedDetails = (app.match(/className="strategy-detail-selected"/g) ?? []).length;
assert(selectedDetails === 1, `expected one selected strategy detail renderer, got ${selectedDetails}`);

console.log(
  `readabilityRegression v0.21.4-B.2.2.2: PASS (${requiredTypographyTokens.length} tokens, ${tinyHardcoded.length} hard-coded fonts <14px, one selected strategy detail)`,
);
