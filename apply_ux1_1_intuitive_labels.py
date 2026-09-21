from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def _python_has_module(python_exe: Path | str, module: str) -> bool:
    try:
        result = subprocess.run(
            [str(python_exe), "-c", f"import {module}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def resolve_project_python() -> str:
    """Prefer the project's virtualenv even when the shell did not activate it."""
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
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        existing.append(candidate)
        if _python_has_module(candidate, "pytest"):
            return str(candidate)

    # Fail before touching any source files. This is intentionally a preflight
    # error rather than a mid-apply rollback caused by using the wrong Python.
    inspected = ", ".join(str(p) for p in existing) or "none"
    raise RuntimeError(
        "pytest가 설치된 프로젝트 Python을 찾지 못했습니다. "
        f"확인한 Python: {inspected}. "
        "프로젝트 .venv가 있다면 .venv에 pytest가 설치되어 있는지 확인하세요."
    )


TARGETS = [
    "frontend/src/App.tsx",
    "frontend/src/components/ScannerPanel.tsx",
    "frontend/src/components/TrackingWorkspace.tsx",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/components/EmbeddedScanner.tsx",
    "frontend/src/styles.css",
    "frontend/src/tracking.css",
    "frontend/tests/test_tracking_track1_source.py",
]

OLD_GLOBAL_CSS = r'''/* UX.1 — compact feature orientation, intentionally non-card/editorial */
.feature-page-guide{margin:0 0 16px;padding:0 0 12px;border-bottom:1px solid var(--border-subtle,#30343b);display:grid;gap:3px;max-width:980px}
.feature-page-guide strong{color:var(--text-primary,#e6e8eb);font-size:16px;font-weight:750}
.feature-page-guide span{color:var(--text-secondary,#9aa1ab);font-size:14px;line-height:1.6}
.feature-page-guide small{color:var(--text-muted,#7f8792);font-size:12px;line-height:1.5}
.feature-orientation-copy{max-width:880px;margin:6px 0 0;color:var(--text-secondary,#9aa1ab);font-size:14px;line-height:1.65}
.feature-flow-line{margin:8px 0 18px;color:var(--text-muted,#7f8792);font-size:12px;letter-spacing:.01em}
.feature-section-help{margin:-5px 0 14px;color:var(--text-secondary,#9aa1ab);font-size:13px;line-height:1.6}
.feature-definition-line{display:flex;flex-wrap:wrap;gap:8px 22px;margin:-2px 0 10px;padding:0 0 10px;border-bottom:1px solid var(--border-subtle,#30343b);color:var(--text-muted,#7f8792);font-size:12px;line-height:1.55}
.feature-definition-line strong{color:var(--text-secondary,#9aa1ab);font-weight:700;margin-right:5px}
'''

OLD_TRACKING_CSS = r'''/* UX.1 — relationship between performance tracking and historical validation */
.tracking-mode-guide{margin:-12px 0 18px;color:var(--text-muted,#7f8792);font-size:12px;line-height:1.55}
'''


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    p = ROOT / rel
    if not p.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return p


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor, found {count}")
    return text.replace(old, new, 1)


def replace_at_least_once(text: str, old: str, new: str, label: str) -> tuple[str, int]:
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new), count


def unwrap_scanner_guide(text: str) -> str:
    # Undo the UX.1 standalone guide that was inserted around the ScannerPanel mount.
    pattern = re.compile(
        r'<>'
        r'\s*<div className="feature-page-guide" data-ux1="scanner">[\s\S]*?</div>'
        r'\s*(<ScannerPanel\b[\s\S]*?/>)'
        r'\s*</>',
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"App.tsx: expected exactly 1 UX.1 scanner guide wrapper, found {len(matches)}")
    m = matches[0]
    scanner = m.group(1)
    return text[:m.start()] + scanner + text[m.end():]


def patch_app(text: str) -> str:
    if 'data-ux1="scanner"' not in text:
        raise RuntimeError("App.tsx: UX.1 scanner guide marker not found; expected the currently applied UX.1 state")

    text = unwrap_scanner_guide(text)

    counts: list[str] = []
    for old, new, label in [
        ("빠른 조회", "종목 분석", "quick analysis label"),
        ("종목별 과거 근거", "종목 과거 성과", "single-stock historical label"),
        ("종목 찾기", "종목 후보 찾기", "scanner label"),
    ]:
        text, count = replace_at_least_once(text, old, new, f"App.tsx {label}")
        counts.append(f"{old}→{new}:{count}")

    # Remove the old marker left by UX.1 and leave a compact marker only.
    text = text.replace("\n/* UX.1 feature orientation: App navigation + scanner guide */\n", "\n")
    if "UX.1.1 intuitive information architecture" not in text:
        text = text.rstrip() + "\n\n/* UX.1.1 intuitive information architecture */\n"

    print("App labels: " + ", ".join(counts))
    return text


def patch_scanner_panel(text: str) -> str:
    # Keep the existing page hierarchy. Only replace the developer-facing eyebrow.
    text, count = replace_at_least_once(text, "STOCK SCANNER", "종목 후보 찾기", "ScannerPanel eyebrow")
    print(f"ScannerPanel eyebrow changes={count}")
    return text


def patch_tracking_workspace(text: str) -> str:
    text = replace_once(
        text,
        'aria-label="종목 성과 추적과 과거 전략 검증"',
        'aria-label="종목 성과 추적과 전략 성과 검증"',
        "TrackingWorkspace aria label",
    )
    text = replace_once(
        text,
        '>과거 전략 검증</button>',
        '>전략 성과 검증</button>',
        "TrackingWorkspace validation tab",
    )
    pattern = re.compile(
        r'\n\s*<p className="tracking-mode-guide">\{mode === "tracking"[\s\S]*?</p>'
    )
    text, count = pattern.subn("", text, count=1)
    if count != 1:
        raise RuntimeError(f"TrackingWorkspace mode guide: expected 1, found {count}")
    return text


def patch_recommendation_tracking(text: str) -> str:
    old_head = (
        '        <div><span>성과 데이터 축적</span><h1>종목 성과 추적</h1><p>이 화면에서 Scanner 종목 찾기를 직접 실행하거나 원하는 종목을 직접 추가해 이후 가격 움직임과 성과를 기록합니다. 쌓인 데이터는 Scanner가 어떤 조건에서 잘 작동했는지 분석하고 개선하는 데 사용됩니다.</p></div>'
    )
    new_head = (
        '        <div><span>종목 성과 기록</span><h1>종목 성과 추적</h1><p>Scanner 후보를 찾거나 원하는 종목을 직접 추가해 이후 성과를 기록하고 Scanner 개선에 활용합니다.</p></div>'
    )
    text = replace_once(text, old_head, new_head, "RecommendationTracking concise page head")

    text = replace_once(
        text,
        '      <p className="feature-flow-line">종목 추가 → 이후 움직임 기록 → 성과 축적 → Scanner 개선 자료</p>\n',
        '',
        "RecommendationTracking flow line removal",
    )
    text = replace_once(
        text,
        '        <p className="feature-section-help">Scanner 추천이 아니어도 관심 있는 종목을 직접 추가해 같은 기준으로 관찰할 수 있습니다.</p>\n',
        '',
        "RecommendationTracking manual help removal",
    )
    text = replace_once(
        text,
        '        <div className="feature-definition-line"><span><strong>추천</strong> Scanner가 찾은 종목</span><span><strong>직접</strong> 사용자가 추가한 종목</span><span><strong>추천 · 직접</strong> 같은 기준일·가격에서 두 조건이 모두 해당</span></div>\n',
        '',
        "RecommendationTracking source legend removal",
    )

    # Keep definitions where users actually act: on the source filters themselves.
    old_filters = '        <div className="tracking-list-filters"><div>{(["ALL", "SCANNER", "MANUAL"] as SourceFilter[]).map((value) => <button key={value} className={sourceFilter === value ? "active" : ""} onClick={() => setSourceFilter(value)}>{value === "ALL" ? "전체" : value === "SCANNER" ? "추천" : "직접"} <small>{sourceCounts[value]}</small></button>)}</div><div>{(["ALL", "ACTIVE", "CLOSED"] as StatusFilter[]).map((value) => <button key={value} className={statusFilter === value ? "active" : ""} onClick={() => setStatusFilter(value)}>{value === "ALL" ? "전체 상태" : value === "ACTIVE" ? "추적 중" : "종료"} <small>{statusCounts[value]}</small></button>)}</div></div>'
    new_filters = '        <div className="tracking-list-filters"><div>{(["ALL", "SCANNER", "MANUAL"] as SourceFilter[]).map((value) => <button key={value} title={value === "SCANNER" ? "Scanner가 찾은 종목" : value === "MANUAL" ? "직접 추가한 종목" : "모든 추적 종목"} className={sourceFilter === value ? "active" : ""} onClick={() => setSourceFilter(value)}>{value === "ALL" ? "전체" : value === "SCANNER" ? "추천" : "직접"} <small>{sourceCounts[value]}</small></button>)}</div><div>{(["ALL", "ACTIVE", "CLOSED"] as StatusFilter[]).map((value) => <button key={value} className={statusFilter === value ? "active" : ""} onClick={() => setStatusFilter(value)}>{value === "ALL" ? "전체 상태" : value === "ACTIVE" ? "추적 중" : "종료"} <small>{statusCounts[value]}</small></button>)}</div></div>'
    text = replace_once(text, old_filters, new_filters, "RecommendationTracking source filter tooltips")
    return text


def patch_simulation(text: str) -> str:
    old_head = '<div><span className="sim-eyebrow">Scanner 전략 연구</span><h1>과거 전략 검증</h1><p>현재 Scanner 전략을 과거 시장 전체에 다시 적용해 성능을 검증합니다. 개별 종목을 계속 관찰하는 성과 추적과 달리 Scanner 전략 자체를 평가하는 연구 기능입니다.</p></div>'
    new_head = '<div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>Scanner 전략을 과거 시장에 적용해 전체 성과를 검증합니다.</p></div>'
    text = replace_once(text, old_head, new_head, "SimulationWorkspace concise page head")
    text = replace_once(
        text,
        '      <p className="feature-flow-line">시장·기간 설정 → 과거 전략 검증 → 결과 비교 → Scanner 개선 근거</p>\n',
        '',
        "SimulationWorkspace flow line removal",
    )
    text, count = replace_at_least_once(text, "과거 전략 검증", "전략 성과 검증", "SimulationWorkspace terminology")
    print(f"Simulation terminology changes={count}")
    return text


def patch_embedded_scanner(text: str) -> str:
    # Make labels action-oriented, but keep internal job/error wording untouched.
    text = replace_once(text, '<span>종목 찾기</span>\n          <h2>이 화면에서 바로 추천 후보 찾기</h2>', '<span>추천 후보 찾기</span>\n          <h2>Scanner 후보를 바로 추가</h2>', "EmbeddedScanner section heading")
    text = replace_once(text, '{busy ? "후보 찾는 중…" : resultForScope ? "후보 다시 찾기" : "종목 찾기 실행"}', '{busy ? "후보 찾는 중…" : resultForScope ? "후보 다시 찾기" : "후보 찾기"}', "EmbeddedScanner run button")
    return text


def patch_tracking_source_test(text: str) -> str:
    """Update copy-only assertions to the intentional UX.1.1 labels.

    TRACK.1 behavior remains frozen; these two assertions only hard-coded old UI copy.
    Keeping the stale strings would force the product UI back to ambiguous wording.
    """
    text = replace_once(
        text,
        '    assert "이 화면에서 Scanner 종목 찾기를 직접 실행" in tracking',
        '    assert "Scanner 후보를 찾거나" in tracking',
        "tracking source test: page guidance copy",
    )
    text = replace_once(
        text,
        '    assert "종목 찾기 실행" in embedded',
        '    assert "후보 찾기" in embedded',
        "tracking source test: embedded scanner button copy",
    )
    return text


def remove_exact_css_block(text: str, block: str, label: str) -> str:
    candidates = ["\n" + block + "\n", block + "\n", "\n" + block, block]
    for candidate in candidates:
        if candidate in text:
            return text.replace(candidate, "\n", 1)
    raise RuntimeError(f"{label}: UX.1 CSS block not found")


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"LAUNCH PYTHON: {sys.executable}")

    # Resolve the correct project interpreter BEFORE modifying any file.
    project_python = resolve_project_python()
    print(f"PROJECT PYTHON: {project_python}")

    for rel in TARGETS:
        require(rel)
    require("frontend/package.json")
    require("backend/tools/verify_tracking_baseline.py")
    require("backend/tools/verify_scanner_production_baseline.py")

    frozen = require("docs/TRACKING_BASELINE.md").read_text(encoding="utf-8")
    if "CLOSED" not in frozen or "FROZEN" not in frozen:
        raise RuntimeError("TRACK.1 frozen baseline was not detected")

    # Require the exact current UX.1 state so this does not run against an older checkout.
    rec_current = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    for marker in (
        "성과 데이터 축적",
        "feature-flow-line",
        "feature-definition-line",
        "이 화면에서 Scanner 종목 찾기를 직접 실행",
    ):
        if marker not in rec_current:
            raise RuntimeError(f"UX.1 baseline marker missing from RecommendationTracking.tsx: {marker}")

    originals: dict[Path, bytes] = {}
    try:
        patches = {
            "frontend/src/App.tsx": patch_app,
            "frontend/src/components/ScannerPanel.tsx": patch_scanner_panel,
            "frontend/src/components/TrackingWorkspace.tsx": patch_tracking_workspace,
            "frontend/src/components/RecommendationTracking.tsx": patch_recommendation_tracking,
            "frontend/src/components/SimulationWorkspace.tsx": patch_simulation,
            "frontend/src/components/EmbeddedScanner.tsx": patch_embedded_scanner,
            "frontend/tests/test_tracking_track1_source.py": patch_tracking_source_test,
        }
        for rel, fn in patches.items():
            path = require(rel)
            originals[path] = path.read_bytes()
            current = path.read_text(encoding="utf-8")
            updated = fn(current)
            if updated == current:
                raise RuntimeError(f"No UX.1.1 change was produced for {rel}")
            path.write_text(updated, encoding="utf-8", newline="")
            print(f"UPDATE {rel}")

        styles = require("frontend/src/styles.css")
        originals[styles] = styles.read_bytes()
        styles_text = remove_exact_css_block(styles.read_text(encoding="utf-8"), OLD_GLOBAL_CSS, "styles.css")
        styles.write_text(styles_text, encoding="utf-8", newline="")
        print("UPDATE frontend/src/styles.css")

        tracking_css = require("frontend/src/tracking.css")
        originals[tracking_css] = tracking_css.read_bytes()
        tracking_text = remove_exact_css_block(tracking_css.read_text(encoding="utf-8"), OLD_TRACKING_CSS, "tracking.css")
        tracking_css.write_text(tracking_text, encoding="utf-8", newline="")
        print("UPDATE frontend/src/tracking.css")

        tests = [
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_usability_track110.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_tracking_same_baseline_merge_track1104.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
            "frontend/tests/test_embedded_scanner_track1101.py",
            "frontend/tests/test_scanner_panel_shared_track1101.py",
            "frontend/tests/test_tracking_lifecycle_track1102.py",
            "frontend/tests/test_manual_tracking_completion_track1103.py",
            "frontend/tests/test_same_baseline_merge_track1104.py",
        ]
        existing_tests = [p for p in tests if (ROOT / p).exists()]
        run([project_python, "-m", "pytest", *existing_tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm not found")
        run([npm, "--prefix", "frontend", "run", "build"])

        tracking_db = ROOT / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"
        if tracking_db.exists():
            print("\n[REQUIRED] TRACK.1 frozen runtime baseline")
            run([project_python, "backend/tools/verify_tracking_baseline.py"])
        else:
            print("\n[SKIP] TRACK.1 frozen runtime baseline")
            print(f"Tracking runtime DB is not present on this machine: {tracking_db}")
            print("UX.1.1 changes frontend copy/layout only, so a missing machine-local runtime DB is not an apply failure.")

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([project_python, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; UX.1.1 changes frontend wording/layout only.")

        print("\nUX.1.1 applied successfully.")
        print("- Removed the detached Scanner explanation block.")
        print("- Renamed main features to action/result-oriented Korean labels.")
        print("- Kept only short inline helper text inside each existing page hierarchy.")
        print("- Updated two copy-only regression assertions to match the intentional labels.")
        print("- No Backend, DB, Scanner algorithm, or TRACK.1 frozen behavior was changed.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK UX.1.1 frontend changes...")
        for path, data in reversed(list(originals.items())):
            try:
                path.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {path}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
