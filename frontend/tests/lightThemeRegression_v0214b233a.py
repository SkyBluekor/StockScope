"""Compatibility regression retained after B.2.3.3b.
B.2.3.3a established functional Light/Dark token separation; B.2.3.3b intentionally
rebalanced the exact Light colors. This test now protects the invariant rather than
freezing the superseded B.2.3.3a palette.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / 'src/styles.css').read_text(encoding='utf-8')
root = css[:css.index('html[data-theme="dark"]')]

for token in (
    '--bg-page','--bg-sidebar','--bg-surface','--bg-surface-raised','--bg-surface-soft','--bg-input',
    '--bg-selected','--bg-hover','--border-subtle','--border-default','--border-strong',
    '--text-primary','--text-secondary','--text-muted',
):
    assert re.search(rf'{re.escape(token)}\s*:\s*#[0-9a-f]{{6}};', root, re.I), token

# Light surfaces remain distinct and none is pure white.
def value(token: str) -> str:
    m = re.search(rf'{re.escape(token)}\s*:\s*(#[0-9a-f]{{6}});', root, re.I)
    assert m, token
    return m.group(1).lower()

surface_tokens = ('--bg-page','--bg-sidebar','--bg-surface','--bg-surface-raised','--bg-surface-soft','--bg-input')
values = [value(t) for t in surface_tokens]
assert len(set(values)) == len(values)
assert '#ffffff' not in values and '#fff' not in values
assert '--surface-muted: var(--bg-surface-soft);' in css
assert 'html[data-theme="light"] :where(input, select, textarea)' in css
assert 'html[data-theme="light"] .sidebar' in css
assert 'html[data-theme="dark"]' in css
print('light theme compatibility regression: PASS')
