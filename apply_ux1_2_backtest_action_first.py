from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path('frontend/src/components/BacktestPanel.tsx')

OLD_HEADER = '''      <header className="multi-strategy-header">\n        <div>\n          <span>STRATEGY SELECTOR · v0.21.4-B.1.1</span>\n          <h1>10가지 투자 방법 자동 비교</h1>\n          <p>현재 가능한 전략을 먼저 찾고, 같은 과거 데이터의 성과는 그 다음 비교 근거로 사용합니다. 현재 판단과 과거 1위를 같은 의미로 섞지 않습니다.</p>\n        </div>\n        <div className="multi-strategy-flow" aria-label="전략 자동 검증 흐름">\n          <span>1 · 종목 선택</span><i>→</i><span>2 · 현재 가능 전략 확인</span><i>→</i><span>3 · 과거 성과 비교</span>\n        </div>\n      </header>\n\n      <nav className="backtest-subnav" aria-label="전략 검증 단계">\n        <button type="button" className={view === "setup" ? "active" : ""} onClick={() => { setView("setup"); scrollTop(); }}>1 · 설정</button>\n        <button type="button" className={view === "result" ? "active" : ""} disabled={!busy && !result && !error} onClick={() => { setView("result"); scrollTop(); }}>2 · 결과</button>\n      </nav>'''

NEW_HEADER = '''      <header className="multi-strategy-header">\n        <div>\n          <h1>종목 과거 성과</h1>\n          <p>같은 종목과 기간에서 10가지 전략의 과거 성과를 비교합니다.</p>\n        </div>\n      </header>\n\n      <nav className="backtest-subnav" aria-label="과거 성과 비교 화면">\n        <button type="button" className={view === "setup" ? "active" : ""} onClick={() => { setView("setup"); scrollTop(); }}>설정</button>\n        <button type="button" className={view === "result" ? "active" : ""} disabled={!busy && !result && !error} onClick={() => { setView("result"); scrollTop(); }}>결과</button>\n      </nav>'''

OLD_PURPOSE = '''          <section className="multi-strategy-purpose">\n            <div>\n              <span>이 기능으로 무엇을 해결하나요?</span>\n              <strong>“이 종목에서는 어떤 방법을 쓰는 게 맞지?”를 사용자가 직접 고르지 않게 합니다.</strong>\n              <p>과거에 잘 맞았는지, 지금 시장과 맞는지, 현재 진입 조건이 준비됐는지를 StockScope가 계산한 뒤 쉬운 행동 안내로 정리합니다.</p>\n            </div>\n            <div className="multi-strategy-chip-list">\n              {strategyGuides.map((guide) => (\n                <span key={guide.professional}>\n                  <b>{guide.easy}</b>\n                  <small>{guide.professional} 전략</small>\n                </span>\n              ))}\n            </div>\n          </section>\n\n'''

OLD_SECTION_TITLE = '<div className="backtest-section-title"><span>검증 설정</span><strong>10가지 방법은 StockScope가 자동으로 전부 비교합니다.</strong></div>'
NEW_SECTION_TITLE = '<div className="backtest-section-title"><span>검증 설정</span><strong>종목과 기간을 정하고 과거 성과를 비교합니다.</strong></div>'

OLD_HOLDING_TO_POLICY = '''            </div>\n\n            <details className="backtest-policy-details">\n              <summary><span>공정하게 비교하기 위해 어떤 조건을 같게 하나요?</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>'''

NEW_HOLDING_TO_POLICY = '''            </div>\n\n            <details className="backtest-policy-details">\n              <summary><span>비교할 전략 10개 보기</span><DetailToggleText closed="전략 보기 ▼" open="전략 숨기기 ▲" /></summary>\n              <div className="multi-strategy-chip-list">\n                {strategyGuides.map((guide) => (\n                  <span key={guide.professional}>\n                    <b>{guide.easy}</b>\n                    <small>{guide.professional} 전략</small>\n                  </span>\n                ))}\n              </div>\n            </details>\n\n            <details className="backtest-policy-details">\n              <summary><span>공정 비교 기준</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>'''

OLD_RUN = '''            <div className="backtest-run-row multi-strategy-run-row">\n              <div><strong>투자 방법을 직접 고를 필요가 없습니다.</strong><span>10가지 방법을 자동으로 비교하고 결과 화면에서 왜 이 방법이 맞는지와 지금 사용자가 해야 할 일을 보여줍니다.</span></div>\n              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "10가지 방법 분석 중..." : "10가지 방법 자동 비교 시작"}</button>\n            </div>'''

NEW_RUN = '''            <div className="backtest-run-row multi-strategy-run-row">\n              <div><strong>10가지 전략을 같은 조건으로 비교합니다.</strong></div>\n              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "과거 성과 비교 중..." : "과거 성과 비교"}</button>\n            </div>'''

OLD_EXIT = '<summary><span>연구용 · Exit 정책 검증</span><DetailToggleText closed="검증 열기 ▼" open="검증 닫기 ▲" /></summary>'
NEW_EXIT = '<summary><span>고급 검증 · Exit 정책 연구</span><DetailToggleText closed="열기 ▼" open="닫기 ▲" /></summary>'

PATCHES = [
    ('header + real step UI', OLD_HEADER, NEW_HEADER),
    ('purpose + strategy card wall', OLD_PURPOSE, ''),
    ('settings heading', OLD_SECTION_TITLE, NEW_SECTION_TITLE),
    ('strategy list moved below settings', OLD_HOLDING_TO_POLICY, NEW_HOLDING_TO_POLICY),
    ('run action', OLD_RUN, NEW_RUN),
    ('advanced validation label', OLD_EXIT, NEW_EXIT),
]

OLD_COPY_MARKERS = [
    'STRATEGY SELECTOR · v0.21.4-B.1.1',
    '10가지 투자 방법 자동 비교',
    '1 · 종목 선택',
    '2 · 현재 가능 전략 확인',
    '3 · 과거 성과 비교',
    '이 기능으로 무엇을 해결하나요?',
    '투자 방법을 직접 고를 필요가 없습니다.',
    '10가지 방법 자동 비교 시작',
    '공정하게 비교하기 위해 어떤 조건을 같게 하나요?',
    '연구용 · Exit 정책 검증',
]

NEW_REQUIRED = [
    '<h1>종목 과거 성과</h1>',
    '같은 종목과 기간에서 10가지 전략의 과거 성과를 비교합니다.',
    '>설정</button>',
    '>결과</button>',
    '비교할 전략 10개 보기',
    '공정 비교 기준',
    '과거 성과 비교 중...',
    '"과거 성과 비교"',
    '고급 검증 · Exit 정책 연구',
]

BEHAVIOR_ANCHORS = [
    'createMultiStrategyBacktestJob({',
    'createExitPolicyValidationJob({',
    'onClick={() => void runBacktest()}',
    'onClick={() => void runExitPolicyValidation(false)}',
    'strategyGuides.map((guide) => (',
    'setView("result")',
]


def normalize_newlines(raw: bytes) -> tuple[str, str]:
    decoded = raw.decode('utf-8')
    newline = '\r\n' if '\r\n' in decoded else '\n'
    return decoded.replace('\r\n', '\n'), newline


def apply_patch(text: str) -> str:
    if '<h1>종목 과거 성과</h1>' in text and 'multi-strategy-purpose' not in text:
        raise RuntimeError('UX.1.2 BacktestPanel patch appears to be already applied.')

    original_anchor_counts = {anchor: text.count(anchor) for anchor in BEHAVIOR_ANCHORS}

    for label, old, new in PATCHES:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f'{label}: expected exact current-source block once, found {count}. No write performed.')
        text = text.replace(old, new, 1)

    for marker in NEW_REQUIRED:
        if marker not in text:
            raise RuntimeError(f'post-patch acceptance marker missing: {marker}')

    for marker in ('multi-strategy-flow', 'multi-strategy-purpose', '10가지 방법 자동 비교 시작', '이 기능으로 무엇을 해결하나요?'):
        if marker in text:
            raise RuntimeError(f'post-patch obsolete UI remains: {marker}')

    if text.count('strategyGuides.map((guide) => (') != 1:
        raise RuntimeError('strategy guide rendering must remain exactly once after relocation.')

    for anchor, before_count in original_anchor_counts.items():
        after_count = text.count(anchor)
        if after_count != before_count:
            raise RuntimeError(f'behavior anchor changed unexpectedly: {anchor} ({before_count} -> {after_count})')

    return text


def find_project_python(root: Path) -> Path:
    candidates = []
    if sys.platform.startswith('win'):
        candidates.extend([root / '.venv' / 'Scripts' / 'python.exe', root / 'venv' / 'Scripts' / 'python.exe'])
    else:
        candidates.extend([root / '.venv' / 'bin' / 'python', root / 'venv' / 'bin' / 'python'])
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def find_copy_coupled_tests(root: Path) -> list[Path]:
    tests_root = root / 'frontend' / 'tests'
    if not tests_root.exists():
        return []
    hits: list[Path] = []
    for path in tests_root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.py', '.ts', '.tsx', '.js', '.jsx'}:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except Exception:
            continue
        if 'BacktestPanel.tsx' in text and any(marker in text for marker in OLD_COPY_MARKERS):
            hits.append(path)
    return hits


def run(cmd: list[str], root: Path) -> None:
    print('RUN ', ' '.join(cmd))
    subprocess.run(cmd, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='StockScope UX.1.2 BacktestPanel action-first patch')
    parser.add_argument('--dry-run', action='store_true', help='validate exact current source and transformation without writing/building')
    args = parser.parse_args()

    root = Path.cwd().resolve()
    target = root / TARGET
    project_python = find_project_python(root)
    print(f'PROJECT ROOT: {root}')
    print(f'LAUNCH PYTHON: {Path(sys.executable).resolve()}')
    print(f'PROJECT PYTHON: {project_python}')
    print(f'TARGET: {target}')

    if not target.exists():
        raise RuntimeError(f'target file does not exist: {target}')

    raw = target.read_bytes()
    original, newline = normalize_newlines(raw)
    print(f'PREFLIGHT: exact BacktestPanel structure loaded ({len(original.splitlines())} lines)')

    patched = apply_patch(original)
    print('DRY-RUN PATCH: PASS')
    print('- exact current JSX blocks matched once each')
    print('- behavior anchors preserved')
    print('- strategyGuides renderer relocated, not duplicated/deleted')
    print('- step flow and purpose wall removed')

    copy_tests = find_copy_coupled_tests(root)
    if copy_tests:
        print('[NOTICE] Copy-coupled BacktestPanel source tests detected:')
        for path in copy_tests:
            print(f'  - {path.relative_to(root)}')
        print('These are not auto-edited in this narrow UI patch. Frontend production build is the required compile gate; visual UAT follows.')
    else:
        print('PREFLIGHT: no copy-coupled BacktestPanel tests detected')

    if args.dry_run:
        print('DRY-RUN COMPLETE: no files changed.')
        return 0

    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise RuntimeError('npm was not found. No write performed.')

    backup_dir = root / '.ux12_backtest_backup'
    backup = backup_dir / 'BacktestPanel.tsx'
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(raw)

    try:
        out = patched.replace('\n', newline).encode('utf-8')
        target.write_bytes(out)
        print(f'UPDATE {TARGET.as_posix()}')

        # Re-read the written source before build.
        written, _ = normalize_newlines(target.read_bytes())
        if written != patched:
            raise RuntimeError('written source does not match validated patch text')
        print('SOURCE ACCEPTANCE: PASS')

        run([npm, '--prefix', 'frontend', 'run', 'build'], root)
        print('FRONTEND BUILD: PASS')

        shutil.rmtree(backup_dir)
        print('\nUX.1.2 BacktestPanel action-first patch applied successfully.')
        print('- Removed the broken 1→2→3 step pill layout.')
        print('- Removed the detached purpose/strategy wall above the form.')
        print('- Moved the 10-strategy list below the actual settings as a collapsed detail.')
        print('- Shortened compare criteria, run action, and advanced research labels.')
        print('- No Backend, API, Scanner, Tracking, DB, or calculation logic changed.')
        print('- Next gate is visual UAT of the 종목 과거 성과 screen only.')
        return 0
    except Exception:
        target.write_bytes(backup.read_bytes())
        print('\nROLLBACK: restored original BacktestPanel.tsx')
        raise
    finally:
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'\nERROR: {exc}')
        raise SystemExit(1)
