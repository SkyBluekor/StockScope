from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SCANNER_REL = Path("frontend/src/components/ScannerPanel.tsx")
STYLES_REL = Path("frontend/src/styles.css")
CSS_MARKER = "UX.1.3 — Scanner Candidate Finder Action-First v1.0.4"

OLD_HEADER = '''      <section className="scanner-hero">\n        <div>\n          <span className="eyebrow">종목 후보 찾기 · v0.21.4-B.2.4</span>\n          <h1>오늘 어떤 종목을 먼저 볼까요?</h1>\n          <p>종목을 직접 고르기 전에 현재 조건을 먼저 보고, Risk·진입 기준까지의 거리·현재 전략 적합도로 우선순위를 정합니다. 같은 전략의 3년 과거 근거는 현재 판단과 분리해 참고로 보여줍니다.</p>\n        </div>\n        <div className="scanner-flow" aria-label="종목 찾기 흐름">\n          <span>1 · 시장 전체 빠른 검사</span><i>→</i><span>2 · 현재 전략·Risk 확인</span><i>→</i><span>3 · 우선순위 + 3년 참고 근거</span>\n        </div>\n      </section>'''

NEW_HEADER = '''      <section className="scanner-hero ux13-scanner-header">\n        <div>\n          <h1>종목 후보 찾기</h1>\n          <p>현재 시장 조건에 맞는 후보를 찾습니다.</p>\n        </div>\n      </section>'''

OLD_CONTROL_COPY = '''        <div>\n          <span>검색 시장</span>\n          <strong>일반 주식 중심으로 찾습니다.</strong>\n          <p>우선주·SPAC·ETF·ETN·거래정지·데이터 부족 종목은 기본 후보에서 제외합니다.</p>\n        </div>'''

NEW_CONTROL_COPY = '''        <div>\n          <strong>시장 선택</strong>\n          <p>일반 상장주 중심 · ETF·ETN·SPAC 등은 기본 후보에서 제외합니다.</p>\n        </div>'''

OLD_EMPTY = '''      {!result && !busy && !error && !freshnessFailure && (\n        <section className="scanner-empty-start">\n          <strong>전략을 먼저 고를 필요가 없습니다.</strong>\n          <p>버튼 한 번으로 시장 전체를 빠르게 거른 뒤, 조건이 좋은 종목만 10가지 전략과 Risk Engine으로 다시 확인합니다.</p>\n        </section>\n      )}'''

NEW_EMPTY = '''      {!result && !busy && !error && !freshnessFailure && (\n        <section className="scanner-empty-start ux13-scanner-empty">\n          <strong>후보 결과</strong>\n          <p>아직 후보가 없습니다.</p>\n        </section>\n      )}'''

SCOPED_CSS = r'''

/* UX.1.3 — Scanner Candidate Finder Action-First v1.0.4 */
.ux13-scanner-header{
  display:block !important;
  background:transparent !important;
  border:0 !important;
  border-radius:0 !important;
  box-shadow:none !important;
  padding:0 0 20px !important;
  min-height:0 !important;
}
.ux13-scanner-header h1{
  margin:0 0 6px !important;
}
.ux13-scanner-header p{
  margin:0 !important;
  max-width:760px;
}
.scanner-workspace .ux13-scanner-empty{
  background:transparent !important;
  border:0 !important;
  border-radius:0 !important;
  box-shadow:none !important;
  min-height:0 !important;
  padding:18px 0 4px !important;
}
.scanner-workspace .ux13-scanner-empty strong{
  display:block;
  margin-bottom:4px;
}
.scanner-workspace .ux13-scanner-empty p{
  margin:0 !important;
}
@media (max-width:760px){
  .ux13-scanner-header{padding-bottom:16px !important}
}
'''


def run(cmd: list[str], *, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess:
    print("RUN ", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        input=input_text,
        text=True if input_text is not None else False,
    )


def require(rel: Path | str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


def python_has_module(exe: Path | str, module: str) -> bool:
    try:
        cp = subprocess.run(
            [str(exe), "-c", f"import {module}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return cp.returncode == 0
    except OSError:
        return False


def resolve_project_python() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        ROOT / "venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "bin" / "python",
        Path(sys.executable),
    ]
    seen: set[str] = set()
    existing: list[Path] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        existing.append(candidate)
        if python_has_module(candidate, "pytest"):
            return str(candidate)
    inspected = ", ".join(map(str, existing)) or "none"
    raise RuntimeError(f"pytest가 설치된 프로젝트 Python을 찾지 못했습니다. 확인한 Python: {inspected}")


def replace_exact_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exact block once, found {count}")
    return text.replace(old, new, 1)


def preflight_source(text: str) -> None:
    exact_blocks = {
        "Scanner header": OLD_HEADER,
        "Scanner control copy": OLD_CONTROL_COPY,
        "Scanner empty state": OLD_EMPTY,
    }
    for label, block in exact_blocks.items():
        count = text.count(block)
        if count != 1:
            raise RuntimeError(f"{label}: exact current JSX block expected once, found {count}")

    required = (
        'className="scanner-control-card"',
        'className="scanner-market-tabs"',
        'className="scanner-control-actions"',
        'className="scanner-progress-card progress-v24"',
        'className="scanner-result-summary"',
        'className="scanner-decision-workspace"',
        "useScannerSession",
        "createScannerJob",
        "fetchBacktestJob",
        "cancelBacktestJob",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"ScannerPanel behavior/layout anchors missing: {missing}")
    if "ux13-scanner-header" in text or "ux13-scanner-empty" in text:
        raise RuntimeError("UX.1.3 appears to be already applied to ScannerPanel")


def patch_scanner(text: str) -> tuple[str, int, dict[str, int]]:
    before_button_count = text.count("<button")
    anchors = {
        marker: text.count(marker)
        for marker in (
            "useScannerSession",
            "createScannerJob",
            "fetchBacktestJob",
            "cancelBacktestJob",
            "runScanner(",
            "setResult(",
            "writeScannerSession(",
            'className="scanner-progress-card progress-v24"',
            'className="scanner-result-summary"',
            'className="scanner-decision-workspace"',
        )
    }

    patched = replace_exact_once(text, OLD_HEADER, NEW_HEADER, "Scanner header")
    patched = replace_exact_once(patched, OLD_CONTROL_COPY, NEW_CONTROL_COPY, "Scanner control copy")
    patched = replace_exact_once(patched, OLD_EMPTY, NEW_EMPTY, "Scanner empty state")

    if patched.count('"오늘의 후보 찾기"') != 1:
        raise RuntimeError(f"Scanner CTA: expected old label once, found {patched.count(chr(34) + '오늘의 후보 찾기' + chr(34))}")
    patched = patched.replace('"오늘의 후보 찾기"', '"후보 찾기"', 1)

    if patched.count('<span>오늘 먼저 볼 후보</span>') != 1:
        raise RuntimeError("Scanner result label: expected current result section label once")
    patched = patched.replace('<span>오늘 먼저 볼 후보</span>', '<span>후보 결과</span>', 1)

    forbidden = (
        "오늘 어떤 종목을 먼저 볼까요?",
        "시장 전체 빠른 검사",
        "현재 전략·Risk 확인",
        "우선순위 + 3년 참고 근거",
        "전략을 먼저 고를 필요가 없습니다.",
        "오늘의 후보 찾기",
    )
    leftovers = [marker for marker in forbidden if marker in patched]
    if leftovers:
        raise RuntimeError(f"SOURCE ACCEPTANCE: stale UX markers remain: {leftovers}")

    for required in (
        "<h1>종목 후보 찾기</h1>",
        "현재 시장 조건에 맞는 후보를 찾습니다.",
        "<strong>시장 선택</strong>",
        '"후보 찾기"',
        '<strong>후보 결과</strong>',
        '<span>후보 결과</span>',
    ):
        if required not in patched:
            raise RuntimeError(f"SOURCE ACCEPTANCE: new marker missing: {required}")

    after_button_count = patched.count("<button")
    if after_button_count != before_button_count:
        raise RuntimeError(f"SOURCE ACCEPTANCE: button count changed {before_button_count} -> {after_button_count}")
    for marker, before in anchors.items():
        after = patched.count(marker)
        if after != before:
            raise RuntimeError(f"SOURCE ACCEPTANCE: behavior anchor changed: {marker} {before} -> {after}")

    return patched, before_button_count, anchors


def find_copy_coupled_tests() -> list[Path]:
    tests_dir = ROOT / "frontend" / "tests"
    if not tests_dir.exists():
        return []
    needles = (
        "오늘의 후보 찾기",
        "오늘 어떤 종목을 먼저 볼까요?",
        "시장 전체 빠른 검사",
        "전략을 먼저 고를 필요가 없습니다.",
        "오늘 먼저 볼 후보",
    )
    hits: list[Path] = []
    for path in tests_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "assert" in content and any(needle in content for needle in needles):
            hits.append(path)
    return hits


def patch_copy_only_tests(paths: list[Path]) -> dict[Path, str]:
    changed: dict[Path, str] = {}
    replacements = {
        'assert "오늘의 후보 찾기" in': 'assert "후보 찾기" in',
        'assert "오늘 어떤 종목을 먼저 볼까요?" in': 'assert "종목 후보 찾기" in',
        'assert "시장 전체 빠른 검사" in': 'assert "시장 선택" in',
        'assert "전략을 먼저 고를 필요가 없습니다." in': 'assert "아직 후보가 없습니다." in',
        'assert "오늘 먼저 볼 후보" in': 'assert "후보 결과" in',
    }
    for path in paths:
        original = path.read_text(encoding="utf-8")
        updated = original
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated == original:
            raise RuntimeError(f"Copy-coupled test detected but no safe exact assertion replacement matched: {path.relative_to(ROOT)}")
        changed[path] = updated
    return changed


def typescript_syntax_check(source: str, node: str, label: str) -> None:
    """Best-effort pre-write TSX parse check.

    This guard must never become a new environment dependency. The real
    authoritative check remains `npm --prefix frontend run build` after write,
    with rollback on failure.

    Exit codes from the Node helper:
      0 = parser available, syntax OK
      1 = parser available, actual TS/TSX syntax errors found (fatal)
      2 = TypeScript compiler API unavailable/incompatible (non-fatal skip)
    """
    frontend_dir = ROOT / "frontend"
    js = r'''
const fs = require('fs');
const path = require('path');

let raw;
try {
  const tsPath = require.resolve('typescript', {
    paths: [process.cwd(), path.resolve(process.cwd(), '..')],
  });
  raw = require(tsPath);
} catch (err) {
  process.stderr.write(`TypeScript compiler API resolution unavailable: ${err && err.message ? err.message : String(err)}\n`);
  process.exit(2);
}

const ts = raw && raw.default && typeof raw.default.transpileModule === 'function'
  ? raw.default
  : raw;

if (!ts || typeof ts.transpileModule !== 'function') {
  process.stderr.write('Resolved TypeScript package does not expose transpileModule; deferring to the normal frontend build.\n');
  process.exit(2);
}

const source = fs.readFileSync(0, 'utf8');
let result;
try {
  result = ts.transpileModule(source, {
    fileName: 'ScannerPanel.tsx',
    compilerOptions: {},
    reportDiagnostics: true,
  });
} catch (err) {
  process.stderr.write(`TypeScript compiler API parse unavailable: ${err && err.message ? err.message : String(err)}\n`);
  process.exit(2);
}

const diagnostics = Array.isArray(result && result.diagnostics) ? result.diagnostics : [];
const errors = diagnostics.filter(d => d && d.category === 1);
if (errors.length) {
  for (const d of errors) {
    let msg;
    if (ts && typeof ts.flattenDiagnosticMessageText === 'function') {
      msg = ts.flattenDiagnosticMessageText(d.messageText, '\n');
    } else {
      msg = String(d.messageText ?? 'TypeScript syntax error');
    }
    let where = '';
    if (d.file && typeof d.start === 'number' && typeof d.file.getLineAndCharacterOfPosition === 'function') {
      const pos = d.file.getLineAndCharacterOfPosition(d.start);
      where = `${pos.line + 1}:${pos.character + 1} `;
    }
    process.stderr.write(`${where}${msg}\n`);
  }
  process.exit(1);
}
'''
    cp = subprocess.run(
        [node, "-e", js],
        cwd=frontend_dir,
        input=source.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stderr = cp.stderr.decode("utf-8", errors="replace").strip()
    stdout = cp.stdout.decode("utf-8", errors="replace").strip()
    detail = stderr or stdout

    if cp.returncode == 0:
        print(f"{label}: PASS")
        return
    if cp.returncode == 1:
        raise RuntimeError(f"{label}: TypeScript parser found a real TSX syntax error:\n{detail or 'unknown syntax error'}")

    print(f"{label}: SKIP (compiler API unavailable/incompatible; frontend production build remains authoritative)")
    if detail:
        print(f"  parser note: {detail.splitlines()[0]}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"PROJECT ROOT: {ROOT}")
    print(f"LAUNCH PYTHON: {sys.executable}")
    project_python = resolve_project_python()
    print(f"PROJECT PYTHON: {project_python}")

    scanner_path = require(SCANNER_REL)
    styles_path = require(STYLES_REL)
    require("frontend/package.json")
    baseline_tool = require("backend/tools/verify_scanner_production_baseline.py")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    node = shutil.which("node.exe") or shutil.which("node")
    if not npm:
        raise RuntimeError("npm not found")
    if not node:
        raise RuntimeError("node not found")

    scanner = scanner_path.read_text(encoding="utf-8")
    styles = styles_path.read_text(encoding="utf-8")
    print(f"TARGET: {scanner_path}")
    print(f"PREFLIGHT: ScannerPanel loaded ({len(scanner.splitlines())} lines)")
    preflight_source(scanner)
    if CSS_MARKER in styles:
        raise RuntimeError("UX.1.3 v1.0.4 CSS marker already exists in styles.css")

    coupled_tests = find_copy_coupled_tests()
    if coupled_tests:
        print("PREFLIGHT: copy-coupled Scanner tests detected: " + ", ".join(str(p.relative_to(ROOT)) for p in coupled_tests))
    else:
        print("PREFLIGHT: no copy-coupled Scanner tests detected")

    patched, button_count, _ = patch_scanner(scanner)
    patched_styles = styles.rstrip() + SCOPED_CSS + "\n"
    planned_tests = patch_copy_only_tests(coupled_tests) if coupled_tests else {}

    # This gate specifically prevents the previous v1.0 failure where a JSX
    # inner element was removed but the surrounding {condition && (...)} was left dangling.
    typescript_syntax_check(patched, node, "PRE-WRITE TYPESCRIPT SYNTAX")

    print("DRY-RUN PATCH: PASS")
    print("- exact current ScannerPanel JSX blocks matched once each")
    print("- full conditional empty-state expression replaced; no dangling React wrapper")
    print("- decorative 1→2→3 workflow rail removed as part of the exact header block")
    print("- title/intro/market/CTA/result copy simplified")
    print("- Scanner behavior anchors and button count preserved")
    print(f"- preserved button count: {button_count}")

    if args.dry_run:
        print("DRY-RUN ONLY: no files changed")
        return 0

    originals: dict[Path, bytes] = {
        scanner_path: scanner_path.read_bytes(),
        styles_path: styles_path.read_bytes(),
    }
    for path in planned_tests:
        originals[path] = path.read_bytes()

    try:
        scanner_path.write_text(patched, encoding="utf-8", newline="")
        styles_path.write_text(patched_styles, encoding="utf-8", newline="")
        print(f"UPDATE {SCANNER_REL.as_posix()}")
        print(f"UPDATE {STYLES_REL.as_posix()}")
        for path, content in planned_tests.items():
            path.write_text(content, encoding="utf-8", newline="")
            print(f"UPDATE {path.relative_to(ROOT)} (copy assertion only)")

        accepted = scanner_path.read_text(encoding="utf-8")
        if accepted != patched:
            raise RuntimeError("SOURCE ACCEPTANCE: ScannerPanel written bytes differ from dry-run plan")
        if CSS_MARKER not in styles_path.read_text(encoding="utf-8"):
            raise RuntimeError("SOURCE ACCEPTANCE: scoped CSS marker missing")
        typescript_syntax_check(accepted, node, "POST-WRITE TYPESCRIPT SYNTAX")
        print("SOURCE ACCEPTANCE: PASS")

        key_tests = [
            "frontend/tests/test_scanner_panel_shared_track1101.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
        ]
        existing_tests = [p for p in key_tests if (ROOT / p).exists()]
        if existing_tests:
            run([project_python, "-m", "pytest", *existing_tests, "-q", "-p", "no:cacheprovider"])
        else:
            print("[SKIP] no key Scanner frontend pytest source tests found")

        run([npm, "--prefix", "frontend", "run", "build"])
        print("FRONTEND BUILD: PASS")

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([project_python, str(baseline_tool.relative_to(ROOT))], check=False)
        if baseline.returncode != 0:
            print("WARNING: Scanner production baseline mismatch is report-only for this frontend-only UX patch.")

        print("\nUX.1.3 Scanner Candidate Finder action-first patch applied successfully.")
        print("- Exact current ScannerPanel structure was used; no generic JSX-parent guessing remains.")
        print("- Removed the decorative workflow rail and the explanation-only empty-state copy.")
        print("- Kept a compact candidate-result empty state instead of a large strategy explanation card.")
        print("- Kept Scanner job/progress/result/session logic unchanged.")
        print("- No Backend, DB, Ranking, Risk, Entry/Stop/Target, Historical Evidence, or Tracking logic changed.")
        print("- Next gate: visual UAT of 종목 후보 찾기 only.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK UX.1.3 changes...")
        for path, data in originals.items():
            try:
                path.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {path}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
