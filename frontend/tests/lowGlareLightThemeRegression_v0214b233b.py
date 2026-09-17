from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
css = (ROOT / 'src/styles.css').read_text(encoding='utf-8')

EXPECTED = {
    '--bg-page': '#dce3ea',
    '--bg-sidebar': '#e5eaf0',
    '--bg-surface': '#e8edf3',
    '--bg-surface-raised': '#eff3f7',
    '--bg-surface-soft': '#dfe6ed',
    '--bg-input': '#e3e9ef',
    '--bg-selected': '#cfdef3',
    '--bg-hover': '#d8e1ea',
    '--border-subtle': '#c9d2dc',
    '--border-default': '#b9c5d1',
    '--border-strong': '#96a7b8',
    '--text-primary': '#172033',
    '--text-secondary': '#3f4d60',
    '--text-muted': '#566575',
}
for token, value in EXPECTED.items():
    assert f'{token}: {value};' in css, (token, value)

assert 'v0.21.4-B.2.3.3b · Low-Glare Light Theme Rebalance' in css
assert 'html[data-theme="light"] .topbar' in css
assert 'html[data-theme="light"] .sidebar' in css
assert 'box-shadow: none;' in css

# Luminance / contrast helpers.
def rgb(hex_color: str):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

def luminance(hex_color: str):
    values = []
    for c in rgb(hex_color):
        values.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126*values[0] + 0.7152*values[1] + 0.0722*values[2]

def contrast(a: str, b: str):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

# B.2.3.3a used page #eef2f6 and surface #f7f9fc. The new palette must be materially dimmer,
# not just "not pure white".
assert luminance(EXPECTED['--bg-page']) <= luminance('#eef2f6') - 0.10
assert luminance(EXPECTED['--bg-surface']) <= luminance('#f7f9fc') - 0.08
assert luminance(EXPECTED['--bg-surface-raised']) < 0.91

# Hierarchy: raised > main surface > input/soft > page, with all layers distinct.
assert luminance(EXPECTED['--bg-surface-raised']) > luminance(EXPECTED['--bg-surface'])
assert luminance(EXPECTED['--bg-surface']) > luminance(EXPECTED['--bg-input'])
assert luminance(EXPECTED['--bg-input']) > luminance(EXPECTED['--bg-surface-soft'])
assert luminance(EXPECTED['--bg-surface-soft']) > luminance(EXPECTED['--bg-page'])
assert len({EXPECTED[k] for k in ('--bg-page','--bg-sidebar','--bg-surface','--bg-surface-raised','--bg-surface-soft','--bg-input')}) == 6

# Normal surfaces must not drift back to F5+ near-white territory. Raised may be brighter by design.
for key in ('--bg-page','--bg-sidebar','--bg-surface','--bg-surface-soft','--bg-input'):
    assert int(EXPECTED[key][1:3], 16) < 0xF5, (key, EXPECTED[key])

# Readability on the darker light palette.
assert contrast('#172033', '#e8edf3') >= 4.5
assert contrast('#3f4d60', '#e8edf3') >= 4.5
assert contrast('#566575', '#dce3ea') >= 4.5
assert contrast('#256a3e', '#dceadf') >= 4.5
assert contrast('#795715', '#efe4c8') >= 4.5
assert contrast('#983640', '#efdcdd') >= 4.5
assert contrast('#2f619c', '#dce6f1') >= 4.5

# Pure white remains allowed for text on solid primary buttons, not for theme surface tokens.
root = css[:css.index('html[data-theme="dark"]')]
assert not re.search(r'--bg-(?:page|sidebar|surface|surface-raised|surface-soft|input)\s*:\s*#(?:fff|ffffff)\b', root, re.I)

# Dark canonical palette must remain intact.
dark_start = css.index('html[data-theme="dark"]')
dark_end = css.index('html[data-theme="light"]', dark_start)
dark = css[dark_start:dark_end]
for token, value in {
    '--bg-page':'#10151d', '--bg-sidebar':'#141b25', '--bg-surface':'#171e28',
    '--bg-surface-raised':'#1d2632', '--bg-surface-soft':'#202a37', '--bg-input':'#111924',
    '--bg-selected':'#203451', '--bg-hover':'#243142', '--border-default':'#344153',
    '--border-soft':'#293546', '--text-primary':'#e5ebf4', '--text-secondary':'#a8b4c5',
    '--text-muted':'#8391a4',
}.items():
    assert f'{token}: {value};' in dark, (token, value)

print('low-glare light theme regression: PASS')
