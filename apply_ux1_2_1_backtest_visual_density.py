from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path('frontend/src/components/BacktestPanel.tsx')
STYLES = Path('frontend/src/styles.css')

OLD_RUN = '''            <div className="backtest-run-row multi-strategy-run-row">\n              <div><strong>10가지 전략을 같은 조건으로 비교합니다.</strong></div>\n              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "과거 성과 비교 중..." : "과거 성과 비교"}</button>\n            </div>'''

NEW_RUN = '''            <div className="backtest-run-row multi-strategy-run-row">\n              <button type="button" disabled={busy || !code.trim() || stockSelectionDirty} onClick={() => void runBacktest()}>{busy ? "과거 성과 비교 중..." : "과거 성과 비교"}</button>\n            </div>'''

CSS_START = '/* UX.1.2.1 BACKTEST VISUAL DENSITY START */'
CSS_END = '/* UX.1.2.1 BACKTEST VISUAL DENSITY END */'
CSS_BLOCK = r'''
/* UX.1.2.1 BACKTEST VISUAL DENSITY START */
/* Page title is typography, not another card. */
.backtest-workspace.multi-strategy-workspace > .multi-strategy-header {
  display: block;
  margin: 0;
  padding: 8px 4px 14px;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace > .multi-strategy-header h1 {
  margin: 0;
}

.backtest-workspace.multi-strategy-workspace > .multi-strategy-header p {
  max-width: 760px;
  margin: 6px 0 0;
}

/* Real setup/result navigation: thin tabs instead of a second card. */
.backtest-workspace.multi-strategy-workspace > .backtest-subnav {
  display: flex;
  align-items: flex-end;
  gap: 28px;
  min-height: 0;
  margin: 0 0 16px;
  padding: 0 4px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, currentColor 18%, transparent);
  border-radius: 0;
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace > .backtest-subnav button {
  flex: 0 0 auto;
  width: auto;
  min-width: 0;
  margin: 0;
  padding: 10px 2px 9px;
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  box-shadow: none;
  opacity: 0.68;
}

.backtest-workspace.multi-strategy-workspace > .backtest-subnav button.active {
  background: transparent;
  border-bottom-color: var(--accent, #79a6ff);
  box-shadow: none;
  opacity: 1;
}

.backtest-workspace.multi-strategy-workspace > .backtest-subnav button:disabled {
  background: transparent;
  opacity: 0.38;
}

/* Keep one real settings surface, then flatten nested wrappers inside it. */
.backtest-workspace.multi-strategy-workspace .backtest-settings-card {
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace .backtest-stock-picker {
  margin-top: 10px;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace .holding-config {
  margin-top: 14px;
  padding: 14px;
  background: color-mix(in srgb, currentColor 2.5%, transparent);
  border-color: color-mix(in srgb, currentColor 16%, transparent);
  border-radius: 8px;
  box-shadow: none;
}

/* Optional information stays visually secondary and collapsed by default. */
.backtest-workspace.multi-strategy-workspace details.backtest-policy-details {
  margin: 0;
  padding: 0;
  background: transparent;
  border: 0;
  border-top: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 0;
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace details.backtest-policy-details > summary {
  padding: 12px 0;
}

.backtest-workspace.multi-strategy-workspace details.backtest-policy-details > .multi-strategy-chip-list,
.backtest-workspace.multi-strategy-workspace details.backtest-policy-details > .multi-strategy-method-brief {
  padding: 0 0 12px;
}

.backtest-workspace.multi-strategy-workspace details.backtest-policy-details .multi-strategy-chip-list > span {
  border-radius: 6px;
  box-shadow: none;
}

/* The CTA already explains the action; remove the duplicate sentence and align it directly. */
.backtest-workspace.multi-strategy-workspace .multi-strategy-run-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid color-mix(in srgb, currentColor 14%, transparent);
}

.backtest-workspace.multi-strategy-workspace .multi-strategy-run-row > button {
  margin-left: auto;
}

/* Advanced research remains available, but it no longer competes with the main flow. */
.backtest-workspace.multi-strategy-workspace details.exit-validation-panel {
  margin-top: 14px;
  background: transparent;
  border: 0;
  border-top: 1px solid color-mix(in srgb, currentColor 16%, transparent);
  border-radius: 0;
  box-shadow: none;
}

.backtest-workspace.multi-strategy-workspace details.exit-validation-panel > summary {
  padding: 14px 4px;
}

@media (max-width: 760px) {
  .backtest-workspace.multi-strategy-workspace > .multi-strategy-header {
    padding-left: 0;
    padding-right: 0;
  }

  .backtest-workspace.multi-strategy-workspace > .backtest-subnav {
    gap: 20px;
    padding-left: 0;
    padding-right: 0;
  }

  .backtest-workspace.multi-strategy-workspace .holding-config {
    padding: 12px;
  }

  .backtest-workspace.multi-strategy-workspace .multi-strategy-run-row > button {
    width: 100%;
  }
}
/* UX.1.2.1 BACKTEST VISUAL DENSITY END */
'''.strip('\n') + '\n'

REQUIRED_CURRENT_MARKERS = [
    '<h1>종목 과거 성과</h1>',
    '같은 종목과 기간에서 10가지 전략의 과거 성과를 비교합니다.',
    '<nav className="backtest-subnav" aria-label="과거 성과 비교 화면">',
    '<section className="backtest-settings-card">',
    '<div className="backtest-stock-picker">',
    '<div className="holding-config">',
    '<summary><span>비교할 전략 10개 보기</span>',
    '<summary><span>공정 비교 기준</span>',
    '<summary><span>고급 검증 · Exit 정책 연구</span>',
    'onClick={() => void runBacktest()}',
]

FORBIDDEN_OLD_MARKERS = [
    'multi-strategy-flow',
    'multi-strategy-purpose',
    '1 · 종목 선택',
    '이 기능으로 무엇을 해결하나요?',
    '10가지 방법 자동 비교 시작',
]

BEHAVIOR_ANCHORS = [
    'createMultiStrategyBacktestJob({',
    'createExitPolicyValidationJob({',
    'onClick={() => void runBacktest()}',
    'onClick={() => void runExitPolicyValidation(false)}',
    'strategyGuides.map((guide) => (',
    'setView("result")',
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
    for marker in REQUIRED_CURRENT_MARKERS:
        if marker not in text:
            raise RuntimeError(f'BacktestPanel current UX.1.2 marker missing: {marker}')
    for marker in FORBIDDEN_OLD_MARKERS:
        if marker in text:
            raise RuntimeError(f'BacktestPanel is not on the expected UX.1.2 baseline; obsolete marker remains: {marker}')

    if text.count(OLD_RUN) != 1:
        raise RuntimeError(f'Backtest run row expected once, found {text.count(OLD_RUN)}. No write performed.')

    before = {anchor: text.count(anchor) for anchor in BEHAVIOR_ANCHORS}
    text = text.replace(OLD_RUN, NEW_RUN, 1)

    if '10가지 전략을 같은 조건으로 비교합니다.' in text:
        raise RuntimeError('duplicate run-row explanation still remains after patch')
    if text.count('strategyGuides.map((guide) => (') != 1:
        raise RuntimeError('strategy guide renderer must remain exactly once')
    if 'open' in ''.join(line for line in text.splitlines() if 'backtest-policy-details' in line):
        raise RuntimeError('backtest policy details must remain uncontrolled/collapsed by default')

    for anchor, count in before.items():
        if text.count(anchor) != count:
            raise RuntimeError(f'behavior anchor changed unexpectedly: {anchor} ({count} -> {text.count(anchor)})')
    return text


def patch_styles(text: str) -> str:
    if CSS_START in text or CSS_END in text:
        raise RuntimeError('UX.1.2.1 visual density CSS already exists in styles.css')
    suffix = '' if text.endswith('\n') else '\n'
    return text + suffix + '\n' + CSS_BLOCK


def run(cmd: list[str], root: Path) -> None:
    print('RUN ', ' '.join(cmd))
    subprocess.run(cmd, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='StockScope UX.1.2.1 BacktestPanel visual density polish')
    parser.add_argument('--dry-run', action='store_true', help='validate source/CSS patch without writing or building')
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

    print(f'PREFLIGHT: BacktestPanel UX.1.2 baseline loaded ({len(target_text.splitlines())} lines)')
    print(f'PREFLIGHT: styles.css loaded ({len(styles_text.splitlines())} lines)')

    patched_target = patch_backtest(target_text)
    patched_styles = patch_styles(styles_text)

    print('DRY-RUN PATCH: PASS')
    print('- UX.1.2 BacktestPanel action-first structure detected')
    print('- duplicate CTA explanation removed only; handlers preserved')
    print('- title/nav/stock picker/holding/details/advanced research receive scoped CSS overrides')
    print('- strategy and comparison <details> have no open attribute and remain collapsed on fresh mount')
    print('- no Backend/API/Scanner/Tracking/calculation source is touched')

    if args.dry_run:
        print('DRY-RUN COMPLETE: no files changed.')
        return 0

    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise RuntimeError('npm was not found. No write performed.')

    backup_dir = root / '.ux121_backtest_backup'
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    (backup_dir / TARGET.parent).mkdir(parents=True, exist_ok=True)
    (backup_dir / STYLES.parent).mkdir(parents=True, exist_ok=True)
    backup_target = backup_dir / TARGET
    backup_styles = backup_dir / STYLES
    backup_target.write_bytes(target_raw)
    backup_styles.write_bytes(styles_raw)

    try:
        target.write_bytes(patched_target.replace('\n', target_nl).encode('utf-8'))
        styles.write_bytes(patched_styles.replace('\n', styles_nl).encode('utf-8'))
        print(f'UPDATE {TARGET.as_posix()}')
        print(f'UPDATE {STYLES.as_posix()}')

        written_target, _ = normalize(target.read_bytes())
        written_styles, _ = normalize(styles.read_bytes())
        if written_target != patched_target or written_styles != patched_styles:
            raise RuntimeError('written files do not match validated patch output')
        if CSS_START not in written_styles or CSS_END not in written_styles:
            raise RuntimeError('scoped UX.1.2.1 CSS block missing after write')
        print('SOURCE ACCEPTANCE: PASS')

        run([npm, '--prefix', 'frontend', 'run', 'build'], root)
        print('FRONTEND BUILD: PASS')

        shutil.rmtree(backup_dir)
        print('\nUX.1.2.1 BacktestPanel visual density polish applied successfully.')
        print('- Flattened the title area and setup/result navigation with scoped CSS.')
        print('- Removed the nested stock-picker card treatment and softened holding/details surfaces.')
        print('- Removed the duplicate sentence beside the main compare CTA.')
        print('- Kept strategy/comparison details collapsed by default on a fresh mount.')
        print('- Reduced the visual priority of advanced Exit research.')
        print('- No behavior, calculation, API, Backend, Scanner, Tracking, or DB logic changed.')
        print('- Next gate: hard-refresh visual UAT of 종목 과거 성과 only.')
        return 0
    except Exception:
        target.write_bytes(backup_target.read_bytes())
        styles.write_bytes(backup_styles.read_bytes())
        print('\nROLLBACK: restored BacktestPanel.tsx and styles.css')
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
