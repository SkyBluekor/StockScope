from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "src" / "styles.css"


def find_browser() -> str:
    env = os.environ.get("CHROME_BIN")
    if env and Path(env).exists():
        return env
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    raise RuntimeError("Chromium/Chrome/Edge executable not found. Set CHROME_BIN to run browser layout validation.")


def row(rank: int, name: str, strategy: str, judgement: str, current: str, interest: str, stop: str, target: str, selected: bool = False) -> str:
    selected_class = " selected" if selected else ""
    return f'''<button type="button" class="scanner-compare-row tone-watch{selected_class}">
      <span class="scanner-compare-rank">{rank}</span>
      <span class="scanner-compare-stock"><strong>{name}</strong><small>KOSPI · {strategy}</small></span>
      <span class="scanner-compare-judgement"><strong>{judgement}</strong><small>관심 후보 · 5/7 충족 · 부족 2개</small></span>
      <span class="scanner-compare-metrics">
        <span><small>현재가</small><strong>{current}</strong></span>
        <span><small>관심 가격</small><strong>{interest}</strong></span>
        <span><small>손절 참고</small><strong>{stop}</strong></span>
        <span><small>1차 목표</small><strong>{target}</strong></span>
      </span>
      <span class="scanner-compare-arrow">›</span>
    </button>'''


def fixture(css_uri: str) -> str:
    rows = "\n".join([
        row(1, "한화비전", "추세 추종", "관심 구간 확인", "58,700원", "56,900~59,800원", "54,100~54,900원", "63,800원", True),
        row(2, "코스맥스", "눌림목", "조건 확인", "280,500원", "271,000~286,000원", "258,500~263,000원", "304,000원"),
        row(3, "한화엔진", "돌파", "돌파 대기", "38,450원", "39,100원 이상", "35,700~36,200원", "43,600원"),
        row(4, "비에이치아이", "모멘텀 지속", "관찰", "63,200원", "61,500~64,300원", "58,100~59,000원", "69,400원"),
        row(5, "삼성SDI", "추세 회복", "조건 확인", "544,000원", "531,000~552,000원", "507,000~514,000원", "596,000원"),
    ])
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="{css_uri}">
<style>#runtime-report{{display:none!important}}</style></head>
<body><div class="app-shell"><div class="layout"><aside class="sidebar"></aside><main class="content">
<div class="scanner-workspace">
  <div class="scanner-decision-workspace">
    <section class="scanner-compare-panel">
      <header class="scanner-compare-head"><div><span>후보 빠른 비교</span><strong>핵심 가격과 현재 판단만 먼저 비교하세요.</strong></div><small>행을 선택하면 아래 상세 판단만 바뀝니다.</small></header>
      <div class="scanner-compare-labels"><span>순서</span><span>종목 / 전략</span><span>현재 판단</span><span>핵심 가격</span><span></span></div>
      <div class="scanner-compare-list">{rows}</div>
    </section>
    <article class="scanner-selected-detail tone-watch">
      <header class="scanner-selected-head"><div><span class="scanner-selected-kicker">선택한 후보 · 우선순위 1</span><div class="scanner-stock-line"><h3>한화비전</h3><span>KOSPI · 489790</span></div><div class="scanner-selected-tags"><span class="scanner-state-badge watch">관심 후보</span><span>추세 추종</span><span>최근 3년 · 14회 · 평균 +2.10%</span></div></div><div class="scanner-selected-price"><small>기준 종가</small><strong>58,700원</strong><span>2026.09.16 확정 일봉</span></div></header>
      <section class="scanner-detail-summary-grid"><div><small>현재 판단</small><strong>관심 구간 확인</strong><p>현재 가격이 관심 구간 안에 있어 다음 확정 일봉에서 조건 유지 여부를 확인합니다.</p></div><div><small>왜 후보인가</small><strong>현재 조건이 상대적으로 잘 맞습니다.</strong><p>추세와 거래량 조건이 함께 유지되고 있어 우선 확인 대상으로 분류했습니다.</p></div><div><small>판단이 바뀌는 조건</small><strong>5/7 충족 · 부족 2개</strong><p>최근 확정 저점 이탈 또는 거래량 약화가 확인되면 현재 판단을 다시 봅니다.</p></div></section>
      <section class="scanner-decision-price-band"><div><small>현재가</small><strong>58,700원</strong></div><div><small>관심 가격</small><strong>56,900~59,800원</strong></div><div class="stop"><small>손절 참고</small><strong>54,100~54,900원</strong></div><div class="target"><small>1차 목표</small><strong>63,800원</strong></div><div><small>2차 목표</small><strong>68,400원</strong></div></section>
      <section class="scanner-selected-strategy"><div><small>현재 가장 맞는 방법</small><strong>추세 추종</strong><span>전문 용어 · Trend Following</span></div><p>상승 흐름이 유지되는 동안 현재 추세가 이어지는지 확인하는 전략입니다. 설명이 길어져도 한 글자씩 세로로 깨지면 안 됩니다.</p></section>
      <section class="scanner-evidence-compact"><div class="scanner-evidence-compact-head"><div><small>같은 전략의 최근 3년 과거 근거</small><strong>과거 검증 완료</strong><span>최근 3년 · 14회 검증 · 평균 순수익 +2.10%</span></div><div class="scanner-evidence-compact-metrics"><span><small>유사 거래</small><b>14회</b></span><span><small>평균 순수익</small><b>+2.10%</b></span><span><small>최대 낙폭</small><b>-6.30%</b></span></div></div><details class="scanner-evidence-details"><summary>과거 근거 자세히 보기</summary><div>접힌 상세 정보</div></details></section>
      <footer class="scanner-selected-action"><div><small>지금 행동</small><strong>다음 확정 일봉을 확인하세요.</strong><p>현재 조건이 유지되는지 확인한 뒤 상세 분석으로 이동합니다.</p></div><button type="button" class="scanner-detail-button">이 종목 자세히 분석</button></footer>
    </article>
  </div>
  <section class="scanner-no-candidate" id="empty-state"><strong>현재는 관망이 정상 결과입니다.</strong><p>현재 확정 일봉 기준으로 10개 전략의 진입 조건을 충분히 만족한 종목이 없습니다.</p><small>후보가 없는 것도 정상적인 분석 결과입니다.</small></section>
</div>
</main></div></div><pre id="runtime-report"></pre>
<script>
function uniqueRows(selector) {{ return [...new Set([...document.querySelectorAll(selector)].map(el => Math.round(el.getBoundingClientRect().top)))].length; }}
function overflow(selector) {{ return [...document.querySelectorAll(selector)].filter(el => el.scrollWidth > el.clientWidth + 1).map(el => el.className || el.tagName); }}
const report = {{
  viewport: window.innerWidth,
  documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  contentWidth: Math.round(document.querySelector('.content').getBoundingClientRect().width),
  scannerWidth: Math.round(document.querySelector('.scanner-workspace').getBoundingClientRect().width),
  candidateRows: document.querySelectorAll('.scanner-compare-row').length,
  criticalOverflow: overflow('.scanner-compare-panel, .scanner-compare-row, .scanner-compare-metrics, .scanner-selected-detail, .scanner-decision-price-band, .scanner-selected-strategy, .scanner-evidence-compact'),
  textOverflow: overflow('.scanner-compare-stock strong, .scanner-compare-judgement strong, .scanner-compare-metrics strong, .scanner-decision-price-band strong'),
  metricRows: uniqueRows('.scanner-compare-row:first-child .scanner-compare-metrics > span'),
  priceRows: uniqueRows('.scanner-decision-price-band > div'),
  koreanWordBreak: getComputedStyle(document.querySelector('.scanner-compare-stock strong')).wordBreak,
  stockNameWidth: Math.round(document.querySelector('.scanner-compare-stock strong').getBoundingClientRect().width),
  stockNameHeight: Math.round(document.querySelector('.scanner-compare-stock strong').getBoundingClientRect().height),
  evidenceOpen: document.querySelector('.scanner-evidence-details').open,
  emptyContainsNoTrade: document.querySelector('#empty-state').textContent.includes('NO_TRADE')
}};
document.querySelector('#runtime-report').textContent = JSON.stringify(report);
</script></body></html>'''


def run_width(browser: str, width: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="stockscope-b231-") as td:
        page = Path(td) / "fixture.html"
        page.write_text(fixture(CSS_PATH.resolve().as_uri()), encoding="utf-8")
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--disable-dev-shm-usage",
            "--window-size=%d,1400" % width,
            "--virtual-time-budget=800",
            "--dump-dom",
        ]
        if os.name != "nt":
            cmd.append("--no-sandbox")
        cmd.append(page.resolve().as_uri())
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"browser failed at {width}px: {proc.stderr[-1200:]}")
        match = re.search(r'<pre id="runtime-report">(.*?)</pre>', proc.stdout, flags=re.S)
        if not match:
            raise RuntimeError(f"runtime report missing at {width}px")
        return json.loads(html.unescape(match.group(1)))


def assert_layout(width: int, report: dict) -> None:
    assert report["candidateRows"] == 5, f"{width}: expected 5 compact candidate rows"
    assert report["documentOverflow"] is False, f"{width}: horizontal document overflow detected"
    assert report["criticalOverflow"] == [], f"{width}: critical layout overflow: {report['criticalOverflow']}"
    assert report["textOverflow"] == [], f"{width}: price/name clipping: {report['textOverflow']}"
    assert report["koreanWordBreak"] == "keep-all", f"{width}: Korean keep-all lost"
    assert report["stockNameWidth"] >= 80, f"{width}: stock-name column too narrow ({report['stockNameWidth']}px)"
    assert report["stockNameHeight"] <= 48, f"{width}: Korean stock name appears vertically broken"
    assert report["evidenceOpen"] is False, f"{width}: historical evidence must be collapsed by default"
    assert report["emptyContainsNoTrade"] is False, f"{width}: internal NO_TRADE leaked to user-facing empty state"
    if width >= 1200:
        assert report["metricRows"] == 1, f"{width}: comparison metrics should be one row"
        assert report["priceRows"] == 1, f"{width}: detail price plan should be one row"
    elif width == 1024:
        assert report["metricRows"] == 2, f"{width}: comparison metrics must be 2x2"
        assert report["priceRows"] == 2, f"{width}: detail price plan must wrap 3+2"


def main() -> int:
    browser = find_browser()
    reports = {}
    for width in (1920, 1440, 1024):
        report = run_width(browser, width)
        assert_layout(width, report)
        reports[width] = report
        print(f"{width}px PASS · content {report['contentWidth']}px · scanner {report['scannerWidth']}px · metrics rows {report['metricRows']} · price rows {report['priceRows']}")
    print("scannerCompactRuntimeLayout v0.21.4-B.2.3.1: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"scannerCompactRuntimeLayout v0.21.4-B.2.3.1: FAIL: {exc}", file=sys.stderr)
        raise
