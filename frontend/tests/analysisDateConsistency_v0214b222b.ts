declare const require: any;
declare const process: any;

const fs = require("fs");
const path = require("path");

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function resolveFrontendRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "src", "components", "ScannerPanel.tsx"))) return cwd;
  const nested = path.join(cwd, "frontend");
  if (fs.existsSync(path.join(nested, "src", "components", "ScannerPanel.tsx"))) return nested;
  throw new Error(`frontend root not found from ${cwd}`);
}

const root = resolveFrontendRoot();
const scanner = fs.readFileSync(path.join(root, "src", "components", "ScannerPanel.tsx"), "utf8");
const session = fs.readFileSync(path.join(root, "src", "components", "scannerSession.ts"), "utf8");
const app = fs.readFileSync(path.join(root, "src", "App.tsx"), "utf8");

assert(session.includes("resolveScannerDataDate"), "aligned Scanner date resolver missing");
assert(session.includes("unique.size !== 1"), "mixed market dates are not rejected");
assert(!session.includes("return values[values.length - 1]"), "legacy max-market-date selection still present");
assert(scanner.includes("fallback_allowed && freshnessFailure.available_data_date"), "fallback button is not guarded by backend permission");
assert(scanner.includes("current_date_valid ? \"새로운 확정 시세를 확인하지 못했습니다.\""), "valid-current-date warning state missing");
assert(scanner.includes("result?.requested_as_of ?? latestScannerDataDate(result)"), "claimed Scanner analysis date is not sent for backend validation");
assert(app.includes("시장 요약 기준"), "dashboard date is still presented as a global data basis");

console.log("analysisDateConsistency v0.21.4-B.2.2.2b: PASS");
