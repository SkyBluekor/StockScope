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

function hexLuminance(hex: string): number {
  let value = hex.slice(1);
  if (value.length === 3) value = value.split("").map((c: string) => c + c).join("");
  if (value.length !== 6) return 0;
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function walk(dir: string): string[] {
  const result: string[] = [];
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) result.push(...walk(full));
    else result.push(full);
  }
  return result;
}

const frontendRoot = resolveFrontendRoot();
const stylesPath = path.join(frontendRoot, "src", "styles.css");
const css = fs.readFileSync(stylesPath, "utf8");

const requiredTokens = [
  "--bg-page",
  "--bg-surface",
  "--bg-surface-raised",
  "--bg-surface-soft",
  "--bg-input",
  "--border-default",
  "--border-soft",
  "--text-primary",
  "--text-strong",
  "--text-secondary",
  "--text-muted",
  "--accent-primary",
  "--status-positive-bg",
  "--status-warning-bg",
  "--status-negative-bg",
];
for (const token of requiredTokens) {
  assert(css.includes(token), `missing theme token: ${token}`);
}
assert(/:root\s*\{[\s\S]*?color-scheme\s*:\s*dark\s*;/m.test(css), "dark-first :root color-scheme is missing");

const forbidden: string[] = [];
const declarationRegex = /(background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?)\s*:\s*([^;]+);/gi;
let match: RegExpExecArray | null;
while ((match = declarationRegex.exec(css))) {
  const property = match[1];
  const value = match[2];
  const hexes = value.match(/#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b/g) ?? [];
  const brightHex = hexes.find((hex: string) => hexLuminance(hex) > 0.72);
  const whiteRgba = /rgba?\(\s*255\s*,\s*255\s*,\s*255\b/i.test(value);
  const whiteFallback = /var\([^,]+,\s*#fff(?:fff)?\s*\)/i.test(value);
  if (brightHex || whiteRgba || whiteFallback) {
    const line = css.slice(0, match.index).split("\n").length;
    forbidden.push(`${line}: ${property}: ${value.trim()}`);
  }
}

const srcRoot = path.join(frontendRoot, "src");
for (const file of walk(srcRoot)) {
  if (!/\.(ts|tsx)$/.test(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  lines.forEach((line: string, index: number) => {
    if (/(background|backgroundColor|borderColor)\s*[:=][^\n]*(#fff(?:fff)?\b|#f8fafc\b|#f1f5f9\b|\bwhite\b)/i.test(line)) {
      forbidden.push(`${path.relative(frontendRoot, file)}:${index + 1}: inline bright surface`);
    }
  });
}

assert(forbidden.length === 0, `bright-surface regression detected:\n${forbidden.slice(0, 40).join("\n")}`);
assert(css.includes(".profit-protection-guide"), "B.2.2 profit-protection styles missing");
assert(/\.profit-protection-guide\s*\{[\s\S]*?background\s*:\s*var\(--surface-soft\)/m.test(css), "profit-protection guide must use theme surface token");

console.log(`darkThemeRegression v0.21.4-B.2.2.1: PASS (${requiredTokens.length} tokens, ${forbidden.length} bright surfaces)`);
