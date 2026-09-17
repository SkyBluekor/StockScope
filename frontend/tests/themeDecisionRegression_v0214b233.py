from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
css=(ROOT/'src/styles.css').read_text(encoding='utf-8')
app=(ROOT/'src/App.tsx').read_text(encoding='utf-8')
scanner=(ROOT/'src/components/ScannerPanel.tsx').read_text(encoding='utf-8')
backtest=(ROOT/'src/components/BacktestPanel.tsx').read_text(encoding='utf-8')
api=(ROOT/'src/services/api.ts').read_text(encoding='utf-8')

assert 'html[data-theme="dark"]' in css
assert 'html[data-theme="light"]' in css
assert '--bg-page: #f3f6fa;' in css
assert '--bg-page: #10151d;' in css
assert 'stockscope-theme' in app and 'document.documentElement.dataset.theme = next' in app
assert 'stockscope-scanner-analysis-context' in scanner
assert 'stockscope-scanner-analysis-context' in backtest
assert '현재 조건 우선 전략' in backtest
assert '과거 비교 1위' in backtest
assert 'historical_best_strategy' in api
print('theme/decision regression: PASS')
