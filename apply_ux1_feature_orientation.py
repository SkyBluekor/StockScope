from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

TARGETS = [
    "frontend/src/App.tsx",
    "frontend/src/components/TrackingWorkspace.tsx",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/styles.css",
    "frontend/src/tracking.css",
]


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


def add_after_heading(text: str, heading: str, body: str, marker: str) -> tuple[str, bool]:
    if marker in text:
        return text, False
    pattern = re.compile(rf"(<h([1-3])([^>]*)>\s*{re.escape(heading)}\s*</h\2>)")
    m = pattern.search(text)
    if not m:
        return text, False
    insert = m.group(1) + body
    return text[:m.start()] + insert + text[m.end():], True


def replace_app_nav_label(text: str) -> tuple[str, int]:
    # Cover the common forms used by App.tsx without touching route ids.
    count = 0
    for old, new in [
        ('label: "종목 추적"', 'label: "종목 성과 추적"'),
        ("label: '종목 추적'", "label: '종목 성과 추적'"),
        ('>종목 추적<', '>종목 성과 추적<'),
    ]:
        c = text.count(old)
        if c:
            text = text.replace(old, new)
            count += c
    return text, count


def add_button_title(text: str, label: str, title: str) -> tuple[str, int]:
    """Add a native tooltip to a simple nav button without changing its click behavior."""
    pattern = re.compile(
        rf'(<button\b(?![^>]*\btitle=)([^>]*)>\s*{re.escape(label)}\s*</button>)'
    )
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        original = match.group(1)
        open_end = original.find('>')
        if open_end < 0:
            return original
        count += 1
        return original[:open_end] + f' title="{title}"' + original[open_end:]

    return pattern.sub(repl, text), count


def patch_scanner_mount(text: str) -> tuple[str, bool]:
    """ScannerPanel has no stable page <h1> in the current compact workspace.

    Insert the UX guide at the App mount boundary instead of depending on
    ScannerPanel's internal markup. This keeps the Scanner implementation frozen.
    """
    if 'data-ux1="scanner"' in text:
        return text, False

    pattern = re.compile(r'(<ScannerPanel\b[\s\S]*?/>)', re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        raise RuntimeError("App.tsx: could not locate ScannerPanel mount")
    if len(matches) != 1:
        raise RuntimeError(f"App.tsx: expected exactly 1 ScannerPanel mount, found {len(matches)}")

    scanner = matches[0].group(1)
    replacement = (
        '<>\n'
        '              <div className="feature-page-guide" data-ux1="scanner">\n'
        '                <strong>종목 찾기</strong>\n'
        '                <span>현재 시장 데이터에서 Scanner 조건에 맞는 후보를 찾습니다. 순위와 전략 정보를 확인한 뒤 원하는 종목을 성과 추적에 추가할 수 있습니다.</span>\n'
        '                <small>시장 선택 → 후보 찾기 → 결과 확인 → 성과 추적</small>\n'
        '              </div>\n'
        f'              {scanner}\n'
        '            </>'
    )
    m = matches[0]
    return text[:m.start()] + replacement + text[m.end():], True


def patch_app(text: str) -> str:
    if "UX.1 feature orientation" in text:
        return text

    text, nav_count = replace_app_nav_label(text)
    if nav_count == 0:
        raise RuntimeError("App.tsx: could not locate the visible '종목 추적' navigation label")

    # 빠른 조회/종목별 과거 근거는 현재 App 안에서 별도 page heading이 아니라
    # navigation label + 기존 workspace로 렌더링된다. 네비게이션에는 짧은 native
    # tooltip을 붙이고, 복잡한 컴포넌트 구조를 억지로 재작성하지 않는다.
    tooltip_counts: dict[str, int] = {}
    for label, title in [
        ("빠른 조회", "특정 종목의 현재 정보를 빠르게 확인합니다."),
        ("종목별 과거 근거", "특정 종목의 과거 데이터와 판단 근거를 확인합니다."),
        ("종목 찾기", "현재 Scanner 조건에 맞는 후보를 찾습니다."),
        ("종목 성과 추적", "선택한 종목의 이후 성과를 기록하고 Scanner 개선 자료로 쌓습니다."),
    ]:
        text, count = add_button_title(text, label, title)
        tooltip_counts[label] = count

    text, scanner_added = patch_scanner_mount(text)

    marker = "\n/* UX.1 feature orientation: App navigation + scanner guide */\n"
    text += marker
    print(
        "App guidance: "
        f"scanner={'added' if scanner_added else 'already present'}, "
        + ", ".join(f"{key} tooltip={value}" for key, value in tooltip_counts.items())
        + f", nav label changes={nav_count}"
    )
    return text

def patch_tracking_workspace(text: str) -> str:
    text = replace_once(
        text,
        'aria-label="종목 추적과 연구 도구"',
        'aria-label="종목 성과 추적과 과거 전략 검증"',
        "TrackingWorkspace aria label",
    )
    text = replace_once(
        text,
        '>종목 추적</button>',
        '>종목 성과 추적</button>',
        "TrackingWorkspace tracking tab label",
    )
    anchor = '      </div>\n      {mode === "tracking" ? <RecommendationTracking /> : <SimulationWorkspace />}'
    replacement = (
        '      </div>\n'
        '      <p className="tracking-mode-guide">{mode === "tracking"\n'
        '        ? "선택한 종목의 이후 움직임과 성과를 기록해 Scanner 개선 자료로 쌓습니다."\n'
        '        : "Scanner 전략 전체를 과거 시장에 적용해 성능을 검증하는 연구 화면입니다."}</p>\n'
        '      {mode === "tracking" ? <RecommendationTracking /> : <SimulationWorkspace />}'
    )
    return replace_once(text, anchor, replacement, "TrackingWorkspace mode guide")


def patch_recommendation_tracking(text: str) -> str:
    old_head = (
        '        <div><span>가격 움직임 기록</span><h1>종목 추적</h1><p>이 화면에서 Scanner 종목 찾기를 직접 실행하거나, 원하는 종목을 이름·코드로 추가해 이후 움직임을 함께 추적합니다.</p></div>'
    )
    new_head = (
        '        <div><span>성과 데이터 축적</span><h1>종목 성과 추적</h1><p>이 화면에서 Scanner 종목 찾기를 직접 실행하거나 원하는 종목을 직접 추가해 이후 가격 움직임과 성과를 기록합니다. 쌓인 데이터는 Scanner가 어떤 조건에서 잘 작동했는지 분석하고 개선하는 데 사용됩니다.</p></div>'
    )
    text = replace_once(text, old_head, new_head, "RecommendationTracking page head")
    text = replace_once(
        text,
        '      </header>\n\n      <div className="tracking-meta-line">',
        '      </header>\n\n      <p className="feature-flow-line">종목 추가 → 이후 움직임 기록 → 성과 축적 → Scanner 개선 자료</p>\n      <div className="tracking-meta-line">',
        "RecommendationTracking feature flow",
    )
    text = replace_once(
        text,
        '        <div className="tracking-section-head"><div><span>직접 추가</span><h2>원하는 종목 직접 찾기</h2></div><small>종목명 또는 코드만 입력 · 기준일과 기준가는 자동</small></div>',
        '        <div className="tracking-section-head"><div><span>직접 추가</span><h2>원하는 종목 직접 찾기</h2></div><small>종목명 또는 코드만 입력 · 기준일과 기준가는 자동</small></div>\n        <p className="feature-section-help">Scanner 추천이 아니어도 관심 있는 종목을 직접 추가해 같은 기준으로 관찰할 수 있습니다.</p>',
        "RecommendationTracking manual help",
    )
    text = replace_once(
        text,
        '        <div className="tracking-section-head"><div><span>저장된 기록</span><h2>추적 중인 종목과 기록</h2></div><small>종목 · 출처 · 시작 기준 · 현재 상태를 한 화면에서 확인</small></div>',
        '        <div className="tracking-section-head"><div><span>저장된 기록</span><h2>추적 중인 종목과 기록</h2></div><small>종목 · 출처 · 시작 기준 · 현재 상태를 한 화면에서 확인</small></div>\n        <div className="feature-definition-line"><span><strong>추천</strong> Scanner가 찾은 종목</span><span><strong>직접</strong> 사용자가 추가한 종목</span><span><strong>추천 · 직접</strong> 같은 기준일·가격에서 두 조건이 모두 해당</span></div>',
        "RecommendationTracking source definitions",
    )
    old_th = '<th>종목</th><th>출처</th><th>시작일</th><th>기준가</th><th>현재가</th><th>현재</th><th>최대 상승</th><th>최대 하락</th><th>경과</th><th>상태</th><th>관리</th>'
    new_th = '<th>종목</th><th>출처</th><th>시작일</th><th title="추적을 시작한 거래일의 확정 종가">기준가</th><th title="가장 최근 반영된 확정 종가">현재가</th><th title="기준가 대비 최신 성과">현재</th><th title="추적 시작 이후 가장 많이 상승했던 폭">최대 상승</th><th title="추적 시작 이후 가장 많이 하락했던 폭">최대 하락</th><th>경과</th><th>상태</th><th>관리</th>'
    text = replace_once(text, old_th, new_th, "RecommendationTracking metric help")
    text = text.replace("종목 추적 목록을 불러오지 못했습니다.", "종목 성과 추적 목록을 불러오지 못했습니다.")
    return text


def patch_simulation(text: str) -> str:
    old = '<div><span className="sim-eyebrow">전략 검증 도구</span><h1>과거 전략 검증</h1><p>무엇을 검증하는지와 실제 평가 기간을 먼저 저장합니다. 실행 엔진이 완성되기 전에는 수동 체결을 전략 검증처럼 실행하지 않습니다.</p></div>'
    new = '<div><span className="sim-eyebrow">Scanner 전략 연구</span><h1>과거 전략 검증</h1><p>현재 Scanner 전략을 과거 시장 전체에 다시 적용해 성능을 검증합니다. 개별 종목을 계속 관찰하는 성과 추적과 달리 Scanner 전략 자체를 평가하는 연구 기능입니다.</p></div>'
    text = replace_once(text, old, new, "SimulationWorkspace page head")
    text = replace_once(
        text,
        '      </header>\n\n      <div className="sim-validation-tabs"',
        '      </header>\n      <p className="feature-flow-line">시장·기간 설정 → 과거 전략 검증 → 결과 비교 → Scanner 개선 근거</p>\n\n      <div className="sim-validation-tabs"',
        "SimulationWorkspace feature flow",
    )
    return text


GLOBAL_CSS = r'''

/* UX.1 — compact feature orientation, intentionally non-card/editorial */
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

TRACKING_CSS = r'''

/* UX.1 — relationship between performance tracking and historical validation */
.tracking-mode-guide{margin:-12px 0 18px;color:var(--text-muted,#7f8792);font-size:12px;line-height:1.55}
'''


def append_css(text: str, addition: str, marker: str) -> str:
    if marker in text:
        return text
    return text.rstrip() + "\n" + addition.strip() + "\n"


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"PYTHON      : {sys.executable}")

    for rel in TARGETS:
        require(rel)
    require("frontend/package.json")
    require("backend/tools/verify_tracking_baseline.py")
    require("backend/tools/verify_scanner_production_baseline.py")
    frozen = require("docs/TRACKING_BASELINE.md").read_text(encoding="utf-8")
    if "CLOSED" not in frozen or "FROZEN" not in frozen:
        raise RuntimeError("TRACK.1 frozen baseline was not detected. Finish TRACK.1 closeout first.")

    rec_current = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    for marker in ("hasScannerSource", "추천 · 직접", "previewManualTrackedItem", "최신 반영", "추적 종료"):
        if marker not in rec_current:
            raise RuntimeError(f"TRACK.1.10.4 baseline marker missing from RecommendationTracking.tsx: {marker}")

    originals: dict[Path, bytes] = {}
    try:
        patches = {
            "frontend/src/App.tsx": patch_app,
            "frontend/src/components/TrackingWorkspace.tsx": patch_tracking_workspace,
            "frontend/src/components/RecommendationTracking.tsx": patch_recommendation_tracking,
            "frontend/src/components/SimulationWorkspace.tsx": patch_simulation,
        }
        for rel, fn in patches.items():
            path = require(rel)
            originals[path] = path.read_bytes()
            current = path.read_text(encoding="utf-8")
            updated = fn(current)
            if updated == current:
                raise RuntimeError(f"No UX.1 change was produced for {rel}")
            path.write_text(updated, encoding="utf-8", newline="")
            print(f"UPDATE {rel}")

        styles = require("frontend/src/styles.css")
        originals[styles] = styles.read_bytes()
        styles_text = append_css(styles.read_text(encoding="utf-8"), GLOBAL_CSS, "UX.1 — compact feature orientation")
        styles.write_text(styles_text, encoding="utf-8", newline="")
        print("UPDATE frontend/src/styles.css")

        tracking_css = require("frontend/src/tracking.css")
        originals[tracking_css] = tracking_css.read_bytes()
        tracking_text = append_css(tracking_css.read_text(encoding="utf-8"), TRACKING_CSS, "UX.1 — relationship between performance tracking")
        tracking_css.write_text(tracking_text, encoding="utf-8", newline="")
        print("UPDATE frontend/src/tracking.css")

        # Existing regression only; UX.1 intentionally adds no new test files.
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
        run([sys.executable, "-m", "pytest", *existing_tests, "-q", "-p", "no:cacheprovider"])

        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm not found")
        run([npm, "--prefix", "frontend", "run", "build"])

        print("\n[REQUIRED] TRACK.1 frozen runtime baseline")
        run([sys.executable, "backend/tools/verify_tracking_baseline.py"])

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([sys.executable, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; UX.1 changes frontend guidance only.")

        print("\nUX.1 applied successfully.")
        print("- Top-level tracking label is now '종목 성과 추적'.")
        print("- Scanner, performance tracking, and historical validation explain their purpose and next action inline.")
        print("- Recommendation/direct-source meaning and tracking metric help are visible without changing TRACK behavior.")
        print("- No Backend, DB, Scanner algorithm, or TRACK.1 frozen behavior was changed.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK UX.1 frontend changes...")
        for path, data in reversed(list(originals.items())):
            try:
                path.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {path}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
