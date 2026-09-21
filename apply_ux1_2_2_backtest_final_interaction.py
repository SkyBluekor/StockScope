from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path('frontend/src/components/BacktestPanel.tsx')
STYLES = Path('frontend/src/styles.css')

STATE_ANCHOR = '  const [scannerContext, setScannerContext] = useState<ScannerAnalysisContext | null>(() => readScannerAnalysisContext(code));'
STATE_INSERT = '''  const [scannerContext, setScannerContext] = useState<ScannerAnalysisContext | null>(() => readScannerAnalysisContext(code));
  const [showStrategyGuides, setShowStrategyGuides] = useState(false);
  const [showComparisonCriteria, setShowComparisonCriteria] = useState(false);
  const [showAdvancedResearch, setShowAdvancedResearch] = useState(false);'''

STRATEGY_OLD = '''            <details className="backtest-policy-details">
              <summary><span>비교할 전략 10개 보기</span><DetailToggleText closed="전략 보기 ▼" open="전략 숨기기 ▲" /></summary>'''
STRATEGY_NEW = '''            <details className="backtest-policy-details" open={showStrategyGuides}>
              <summary onClick={(event) => { event.preventDefault(); setShowStrategyGuides((open) => !open); }}><span>비교할 전략 10개 보기</span><DetailToggleText closed="전략 보기 ▼" open="전략 숨기기 ▲" /></summary>'''

CRITERIA_OLD = '''            <details className="backtest-policy-details">
              <summary><span>공정 비교 기준</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>'''
CRITERIA_NEW = '''            <details className="backtest-policy-details" open={showComparisonCriteria}>
              <summary onClick={(event) => { event.preventDefault(); setShowComparisonCriteria((open) => !open); }}><span>공정 비교 기준</span><DetailToggleText closed="기준 보기 ▼" open="기준 숨기기 ▲" /></summary>'''

ADVANCED_OLD = '''          <details className="exit-validation-panel">
            <summary><span>고급 검증 · Exit 정책 연구</span><DetailToggleText closed="열기 ▼" open="닫기 ▲" /></summary>'''
ADVANCED_NEW = '''          <details className="exit-validation-panel" open={showAdvancedResearch}>
            <summary onClick={(event) => { event.preventDefault(); setShowAdvancedResearch((open) => !open); }}><span>고급 검증 · Exit 정책 연구</span><DetailToggleText closed="열기 ▼" open="닫기 ▲" /></summary>'''

CSS_START = '/* UX.1.2.2 BACKTEST FINAL INTERACTION START */'
CSS_END = '/* UX.1.2.2 BACKTEST FINAL INTERACTION END */'
CSS_BLOCK = r'''
/* UX.1.2.2 BACKTEST FINAL INTERACTION START */
/* Beat the legacy dark-theme !important active-button rule: these are tabs, not filled buttons. */
.backtest-workspace.multi-strategy-workspace > .backtest-subnav button,
html[data-theme="dark"] .backtest-workspace.multi-strategy-workspace > .backtest-subnav button {
  background: transparent !important;
  border: 0 !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  color: var(--text-subtle) !important;
}

.backtest-workspace.multi-strategy-workspace > .backtest-subnav button.active,
html[data-theme="dark"] .backtest-workspace.multi-strategy-workspace > .backtest-subnav button.active {
  background: transparent !important;
  border: 0 !important;
  border-bottom: 2px solid var(--primary) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  color: var(--text-strong) !important;
}

.backtest-workspace.multi-strategy-workspace > .backtest-subnav button:disabled,
html[data-theme="dark"] .backtest-workspace.multi-strategy-workspace > .backtest-subnav button:disabled {
  background: transparent !important;
  border-color: transparent !important;
  color: var(--text-subtle) !important;
}
/* UX.1.2.2 BACKTEST FINAL INTERACTION END */
'''.strip('\n') + '\n'

REQUIRED_BASELINE = [
    '<h1>종목 과거 성과</h1>',
    '<nav className="backtest-subnav" aria-label="과거 성과 비교 화면">',
    '<summary><span>비교할 전략 10개 보기</span>',
    '<summary><span>공정 비교 기준</span>',
    '<summary><span>고급 검증 · Exit 정책 연구</span>',
    'onClick={() => void runBacktest()}',
    'onClick={() => void runExitPolicyValidation(false)}',
]

BEHAVIOR_ANCHORS = [
    'createMultiStrategyBacktestJob({',
    'createExitPolicyValidationJob({',
    'onClick={() => void runBacktest()}',
    'onClick={() => void runExitPolicyValidation(false)}',
    'strategyGuides.map((guide) => (',
    'setView("result")',
    'setView("setup")',
]


def normalize(raw: bytes) -> tuple[str, str]:
    text = raw.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    return text.replace('\r\n', '\n'), newline


def find_project_python(root: Path) -> Path:
    candidates: list[Path] = []
    if sys.platform.startswith('win'):
        candidates.extend([root / '.venv' / 'Scripts' / 'python.exe', root / 'venv' / 'Scripts' / 'python.exe'])
    else:
        candidates.extend([root / '.venv' / 'bin' / 'python', root / 'venv' / 'bin' / 'python'])
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def patch_backtest(text: str) -> str:
    if 'showStrategyGuides' in text or 'showComparisonCriteria' in text or 'showAdvancedResearch' in text:
        raise RuntimeError('UX.1.2.2 controlled disclosure state already exists; patch appears applied.')

    for marker in REQUIRED_BASELINE:
        if marker not in text:
            raise RuntimeError(f'UX.1.2.1 baseline marker missing: {marker}')

    exact_blocks = [
        ('state anchor', STATE_ANCHOR, STATE_INSERT),
        ('strategy disclosure', STRATEGY_OLD, STRATEGY_NEW),
        ('comparison disclosure', CRITERIA_OLD, CRITERIA_NEW),
        ('advanced research disclosure', ADVANCED_OLD, ADVANCED_NEW),
    ]
    before = {anchor: text.count(anchor) for anchor in BEHAVIOR_ANCHORS}

    for label, old, new in exact_blocks:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f'{label}: expected exact current block once, found {count}. No write performed.')
        text = text.replace(old, new, 1)

    required_after = [
        'const [showStrategyGuides, setShowStrategyGuides] = useState(false);',
        'const [showComparisonCriteria, setShowComparisonCriteria] = useState(false);',
        'const [showAdvancedResearch, setShowAdvancedResearch] = useState(false);',
        'open={showStrategyGuides}',
        'setShowStrategyGuides((open) => !open)',
        'open={showComparisonCriteria}',
        'setShowComparisonCriteria((open) => !open)',
        'open={showAdvancedResearch}',
        'setShowAdvancedResearch((open) => !open)',
    ]
    for marker in required_after:
        if text.count(marker) != 1:
            raise RuntimeError(f'post-patch controlled disclosure marker count invalid: {marker} -> {text.count(marker)}')

    if text.count('strategyGuides.map((guide) => (') != 1:
        raise RuntimeError('strategy guide renderer must remain exactly once.')

    for anchor, count in before.items():
        if text.count(anchor) != count:
            raise RuntimeError(f'behavior anchor changed unexpectedly: {anchor} ({count} -> {text.count(anchor)})')

    return text


def patch_styles(text: str) -> str:
    visual_start = '/* UX.1.2.1 BACKTEST VISUAL DENSITY START */'
    visual_end = '/* UX.1.2.1 BACKTEST VISUAL DENSITY END */'
    if visual_start not in text or visual_end not in text:
        raise RuntimeError('UX.1.2.1 visual-density CSS baseline was not found. No write performed.')
    if CSS_START in text or CSS_END in text:
        raise RuntimeError('UX.1.2.2 final-interaction CSS already exists.')
    suffix = '' if text.endswith('\n') else '\n'
    return text + suffix + '\n' + CSS_BLOCK


def find_copy_coupled_tests(root: Path) -> list[Path]:
    tests_root = root / 'frontend' / 'tests'
    if not tests_root.exists():
        return []
    needles = ['비교할 전략 10개 보기', '공정 비교 기준', '고급 검증 · Exit 정책 연구', 'backtest-subnav']
    hits: list[Path] = []
    for path in tests_root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.py', '.ts', '.tsx', '.js', '.jsx'}:
            continue
        try:
            body = path.read_text(encoding='utf-8')
        except Exception:
            continue
        if 'BacktestPanel.tsx' in body and any(needle in body for needle in needles):
            hits.append(path)
    return hits


def run(cmd: list[str], root: Path) -> None:
    print('RUN ', ' '.join(cmd))
    subprocess.run(cmd, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='StockScope UX.1.2.2 BacktestPanel final interaction polish')
    parser.add_argument('--dry-run', action='store_true', help='validate exact current source/CSS transformation without writing or building')
    args = parser.parse_args()

    root = Path.cwd().resolve()
    target = root / TARGET
    styles = root / STYLES
    project_python = find_project_python(root)

    print(f'PROJECT ROOT: {root}')
    print(f'LAUNCH PYTHON: {Path(sys.executable).resolve()}')
    print(f'PROJECT PYTHON: {project_python}')
    print(f'TARGET: {target}')
    print(f'STYLES: {styles}')

    if not target.exists():
        raise RuntimeError(f'target file missing: {target}')
    if not styles.exists():
        raise RuntimeError(f'styles file missing: {styles}')

    target_raw = target.read_bytes()
    styles_raw = styles.read_bytes()
    target_text, target_nl = normalize(target_raw)
    styles_text, styles_nl = normalize(styles_raw)

    print(f'PREFLIGHT: UX.1.2.1 BacktestPanel loaded ({len(target_text.splitlines())} lines)')
    print(f'PREFLIGHT: styles.css loaded ({len(styles_text.splitlines())} lines)')

    patched_target = patch_backtest(target_text)
    patched_styles = patch_styles(styles_text)

    copy_tests = find_copy_coupled_tests(root)
    if copy_tests:
        print('[NOTICE] BacktestPanel copy/source tests reference this UI:')
        for path in copy_tests:
            print(f'  - {path.relative_to(root)}')
    else:
        print('PREFLIGHT: no copy-coupled BacktestPanel interaction tests detected')

    print('DRY-RUN PATCH: PASS')
    print('- exact UX.1.2.1 disclosure blocks matched once each')
    print('- three disclosure states initialize false and are React-controlled')
    print('- native summary default toggle is prevented; user clicks update React state')
    print('- backtest/Exit handlers and strategy renderer preserved')
    print('- scoped CSS overrides the legacy dark-theme !important filled-tab rule')

    if args.dry_run:
        print('DRY-RUN COMPLETE: no files changed.')
        return 0

    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise RuntimeError('npm was not found. No write performed.')

    backup_dir = root / '.ux122_backtest_backup'
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    (backup_dir / TARGET.parent).mkdir(parents=True, exist_ok=True)
    (backup_dir / STYLES.parent).mkdir(parents=True, exist_ok=True)
    (backup_dir / TARGET).write_bytes(target_raw)
    (backup_dir / STYLES).write_bytes(styles_raw)

    try:
        target.write_text(patched_target.replace('\n', target_nl), encoding='utf-8', newline='')
        styles.write_text(patched_styles.replace('\n', styles_nl), encoding='utf-8', newline='')
        print(f'UPDATE {TARGET.as_posix()}')
        print(f'UPDATE {STYLES.as_posix()}')

        written_target = target.read_text(encoding='utf-8').replace('\r\n', '\n')
        written_styles = styles.read_text(encoding='utf-8').replace('\r\n', '\n')
        if written_target != patched_target:
            raise RuntimeError('BacktestPanel write verification mismatch')
        if written_styles != patched_styles:
            raise RuntimeError('styles.css write verification mismatch')
        # Re-run acceptance against the written source without attempting a second patch.
        for marker in (
            'open={showStrategyGuides}',
            'open={showComparisonCriteria}',
            'open={showAdvancedResearch}',
            'onClick={() => void runBacktest()}',
            'onClick={() => void runExitPolicyValidation(false)}',
        ):
            if written_target.count(marker) != 1:
                raise RuntimeError(f'SOURCE ACCEPTANCE marker count invalid: {marker} -> {written_target.count(marker)}')
        if CSS_START not in written_styles or CSS_END not in written_styles:
            raise RuntimeError('STYLE ACCEPTANCE: final interaction CSS markers missing')
        print('SOURCE ACCEPTANCE: PASS')

        run([npm, '--prefix', 'frontend', 'run', 'build'], root)
        print('FRONTEND BUILD: PASS')
    except Exception:
        print('ROLLBACK UX.1.2.2 BacktestPanel final interaction changes...')
        target.write_bytes((backup_dir / TARGET).read_bytes())
        styles.write_bytes((backup_dir / STYLES).read_bytes())
        raise
    finally:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

    print('\nUX.1.2.2 BacktestPanel final interaction polish applied successfully.')
    print('- Setup/result active tab is text + underline, including dark mode.')
    print('- Strategy list, comparison criteria, and advanced Exit research start closed on component mount.')
    print('- Each disclosure remains user-toggleable through React-controlled state.')
    print('- No Backend/API/Scanner/Tracking/DB/calculation logic changed.')
    print('- Next gate: hard-refresh visual UAT of 종목 과거 성과 only.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
