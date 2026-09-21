from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()

TARGETS = [
    "frontend/src/components/ScannerPanel.tsx",
    "frontend/src/components/EmbeddedScanner.tsx",
    "frontend/src/components/RecommendationTracking.tsx",
    "frontend/src/components/SimulationWorkspace.tsx",
    "frontend/src/styles.css",
    "frontend/src/tracking.css",
]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("RUN ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def require(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"Required file missing: {rel}")
    return path


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
    inspected = ", ".join(str(p) for p in existing) or "none"
    raise RuntimeError(
        "pytest가 설치된 프로젝트 Python을 찾지 못했습니다. "
        f"확인한 Python: {inspected}"
    )


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


@dataclass(frozen=True)
class TagRange:
    tag: str
    start: int
    open_end: int
    close_start: int
    end: int


_TAG_RE = re.compile(r"<\s*(/?)\s*(div|section|aside|header|article|main|form|fieldset|nav|ul|ol)\b[^>]*>", re.IGNORECASE)


def tag_ranges(text: str) -> list[TagRange]:
    stack: list[tuple[str, int, int]] = []
    ranges: list[TagRange] = []
    for match in _TAG_RE.finditer(text):
        closing = bool(match.group(1))
        tag = match.group(2).lower()
        if not closing:
            stack.append((tag, match.start(), match.end()))
            continue
        # JSX is expected to be balanced, but tolerate unrelated oddities by
        # pairing with the nearest matching open tag.
        idx = None
        for i in range(len(stack) - 1, -1, -1):
            if stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            continue
        open_tag, start, open_end = stack[idx]
        del stack[idx:]
        ranges.append(TagRange(open_tag, start, open_end, match.start(), match.end()))
    return ranges


def smallest_container(text: str, phrases: list[str], label: str) -> TagRange:
    positions: list[int] = []
    for phrase in phrases:
        pos = text.find(phrase)
        if pos < 0:
            raise RuntimeError(f"{label}: phrase not found: {phrase}")
        positions.append(pos)
    candidates = [
        r for r in tag_ranges(text)
        if all(r.start <= pos < r.end for pos in positions)
    ]
    if not candidates:
        raise RuntimeError(f"{label}: no common JSX container found")
    return min(candidates, key=lambda r: r.end - r.start)


def remove_container(text: str, phrases: list[str], label: str) -> str:
    r = smallest_container(text, phrases, label)
    return text[:r.start] + text[r.end:]


def replace_tag_inner_containing(text: str, tag: str, phrase: str, new_inner: str, label: str) -> str:
    pattern = re.compile(rf"<{tag}\b([^>]*)>([\s\S]*?)</{tag}>", re.IGNORECASE)
    matches = [m for m in pattern.finditer(text) if phrase in m.group(2)]
    if len(matches) != 1:
        raise RuntimeError(f"{label}: expected exactly 1 <{tag}> containing '{phrase}', found {len(matches)}")
    m = matches[0]
    replacement = f"<{tag}{m.group(1)}>{new_inner}</{tag}>"
    return text[:m.start()] + replacement + text[m.end():]


def inner_of_range(text: str, r: TagRange) -> str:
    return text[r.open_end:r.close_start]


def discover_historical_source() -> Path:
    """Find the single-stock historical strategy screen without assuming App.tsx.

    UX.1.1/current branches may keep this screen in App.tsx or split it into a
    component.  Discovery uses several independent user-visible anchors, so a
    line break or nested span in the page title cannot break the apply script.
    """
    src_root = ROOT / "frontend" / "src"
    markers = {
        "현재 가능 전략 확인": 4,
        "10가지 방법 자동 비교 시작": 4,
        "이 기능으로 무엇을 해결하나요?": 3,
        "상승 흐름 따라가기": 2,
        "STRATEGY SELECTOR": 2,
        "공정하게 비교하기 위해 어떤 조건을 같게 하나요?": 2,
        "검증 설정": 1,
    }
    candidates: list[tuple[int, Path, list[str]]] = []
    for path in src_root.rglob("*.tsx"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = [marker for marker in markers if marker in text]
        score = sum(markers[m] for m in found)
        if score:
            candidates.append((score, path, found))

    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    if not candidates or candidates[0][0] < 6:
        detail = "; ".join(
            f"{p.relative_to(ROOT)} score={score} markers={found}"
            for score, p, found in candidates[:5]
        ) or "no candidates"
        raise RuntimeError(
            "종목 과거 성과 화면 소스를 찾지 못했습니다. "
            "App.tsx 고정 경로/제목 문자열에 의존하지 않고 탐색했지만 충분한 앵커가 없습니다. "
            f"후보: {detail}"
        )

    best_score, best_path, best_found = candidates[0]
    # A tie at a high score means the same view may have been duplicated; fail
    # before mutation rather than guessing which file is live.
    tied = [item for item in candidates if item[0] == best_score]
    if len(tied) > 1:
        detail = "; ".join(str(p.relative_to(ROOT)) for _, p, _ in tied)
        raise RuntimeError(f"종목 과거 성과 화면 후보가 여러 개입니다: {detail}")

    print(
        "HISTORICAL SOURCE:",
        best_path.relative_to(ROOT),
        f"score={best_score}",
        "markers=" + ", ".join(best_found),
    )
    return best_path


def semantic_tag_matches(text: str, tag: str, tokens: list[str]) -> list[re.Match[str]]:
    pattern = re.compile(rf"<{tag}\b([^>]*)>([\s\S]*?)</{tag}>", re.IGNORECASE)
    matches: list[re.Match[str]] = []
    for match in pattern.finditer(text):
        inner = match.group(2)
        plain = re.sub(r"<[^>]+>", " ", inner)
        plain = re.sub(r"[{}()\"'`]", " ", plain)
        plain = re.sub(r"\s+", " ", plain)
        if all(token in plain for token in tokens):
            matches.append(match)
    return matches


def replace_semantic_tag_inner(
    text: str,
    tag: str,
    tokens: list[str],
    new_inner: str,
    label: str,
    *,
    required: bool = False,
) -> tuple[str, int]:
    matches = semantic_tag_matches(text, tag, tokens)
    if not matches:
        if required:
            raise RuntimeError(f"{label}: semantic <{tag}> anchor not found: {tokens}")
        return text, 0
    if len(matches) != 1:
        raise RuntimeError(f"{label}: semantic <{tag}> anchor ambiguous ({len(matches)} matches): {tokens}")
    match = matches[0]
    replacement = f"<{tag}{match.group(1)}>{new_inner}</{tag}>"
    return text[:match.start()] + replacement + text[match.end():], 1


def preflight_markers(historical_path: Path) -> None:
    scanner = require("frontend/src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    scanner_required = (
        "오늘 어떤 종목을 먼저 볼까요?",
        "전략을 먼저 고를 필요가 없습니다.",
        "시장 전체 빠른 검사",
        "현재 전략·Risk 확인",
        "우선순위 + 3년 참고 근거",
    )
    missing = [marker for marker in scanner_required if marker not in scanner]
    if missing:
        raise RuntimeError(f"ScannerPanel UX.1.1 marker missing: {missing}")

    historical = historical_path.read_text(encoding="utf-8")
    # Deliberately do NOT require the rendered title as one contiguous source
    # string.  In current UI it may be split across JSX spans/components.
    historical_required = (
        "현재 가능 전략 확인",
        "이 기능으로 무엇을 해결하나요?",
        "상승 흐름 따라가기",
        "검증 설정",
    )
    missing = [marker for marker in historical_required if marker not in historical]
    if missing:
        raise RuntimeError(
            f"{historical_path.relative_to(ROOT)} historical UX marker missing: {missing}"
        )

    tracking = require("frontend/src/components/RecommendationTracking.tsx").read_text(encoding="utf-8")
    tracking_required = (
        "종목 성과 기록",
        "종목 성과 추적",
        "최근 추천 후보",
        "원하는 종목 직접 찾기",
        "추적 중인 종목과 기록",
    )
    missing = [marker for marker in tracking_required if marker not in tracking]
    if missing:
        raise RuntimeError(f"RecommendationTracking UX.1.1 marker missing: {missing}")

    sim = require("frontend/src/components/SimulationWorkspace.tsx").read_text(encoding="utf-8")
    sim_required = (
        "Scanner 전략 전체 검증",
        "전략 성과 검증",
        "무엇을, 어느 기간에 검증할지 저장합니다.",
        "설정을 먼저 보존합니다.",
        "실제 검증 실행은 다음 단계에서 연결합니다.",
    )
    missing = [marker for marker in sim_required if marker not in sim]
    if missing:
        raise RuntimeError(f"SimulationWorkspace UX.1.1 marker missing: {missing}")

def patch_scanner_panel(text: str) -> str:
    # 1) Remove the decorative 3-step rail entirely.
    text = remove_container(
        text,
        ["시장 전체 빠른 검사", "현재 전략·Risk 확인", "우선순위 + 3년 참고 근거"],
        "Scanner workflow rail",
    )

    # 2) Remove the explanation-only card under the actual controls.
    text = remove_container(text, ["전략을 먼저 고를 필요가 없습니다."], "Scanner explanation card")

    # 3) Make the page hierarchy action-first and concise.
    text = replace_tag_inner_containing(text, "h1", "오늘 어떤 종목을 먼저 볼까요?", "종목 후보 찾기", "Scanner h1")
    text = replace_tag_inner_containing(
        text,
        "p",
        "종목을 직접 고르기 전에",
        "현재 시장 조건에 맞는 후보를 찾습니다.",
        "Scanner intro",
    )

    eyebrow_pattern = re.compile(r"종목 후보 찾기\s*·\s*v[0-9A-Za-z.\-]+")
    text, count = eyebrow_pattern.subn("현재 시장 후보 탐색", text, count=1)
    if count != 1:
        raise RuntimeError(f"Scanner eyebrow/version: expected 1, found {count}")

    # Keep selection + primary action; remove prose that only explains exclusions.
    if "일반 주식 중심으로 찾습니다." in text:
        # Current Scanner uses <strong> here (older branches used a heading).
        if semantic_tag_matches(text, "strong", ["일반 주식 중심으로 찾습니다."]):
            text, _ = replace_semantic_tag_inner(text, "strong", ["일반 주식 중심으로 찾습니다."], "시장 선택", "Scanner control title", required=True)
        else:
            text = replace_tag_inner_containing(text, "h2", "일반 주식 중심으로 찾습니다.", "시장 선택", "Scanner control title")
    exclusion = "우선주·SPAC·ETF·ETN·거래정지·데이터 부족 종목은 기본 후보에서 제외합니다."
    if exclusion in text:
        # Remove the whole prose-only paragraph rather than leaving an empty line.
        matches = semantic_tag_matches(text, "p", ["우선주", "SPAC", "ETF", "ETN"])
        if len(matches) == 1:
            m = matches[0]
            text = text[:m.start()] + text[m.end():]
        else:
            text = text.replace(exclusion, "")

    text, _ = replace_at_least_once(text, "오늘의 후보 찾기", "후보 찾기", "Scanner primary button")
    return text


def build_collapsed_strategy_block(block: str) -> str:
    # Keep the complete strategy explanation available, but hide it from the
    # initial action path. This is deliberately safer than deleting nested JSX
    # whose wrapper may differ between local checkouts.
    ranges = tag_ranges(block)
    outer = None
    if ranges:
        # Pick the outermost element starting at/near the block beginning.
        outer = max(ranges, key=lambda r: r.end - r.start)
    content = inner_of_range(block, outer) if outer else block
    return (
        '<details className="ux12-strategy-list">'
        '<summary>비교할 전략 10개 보기</summary>'
        f'{content}'
        '</details>'
    )


def patch_app_historical(text: str) -> str:
    # Remove the awkward 3-step pills.  These labels are the stable structure;
    # the rendered H1 may be split across JSX and is therefore not a preflight anchor.
    text = remove_container(
        text,
        ["종목 선택", "현재 가능 전략 확인", "과거 성과 비교"],
        "Historical step rail",
    )

    # Rename title when we can identify it semantically, including nested spans.
    text, title_changes = replace_semantic_tag_inner(
        text,
        "h1",
        ["10가지", "자동", "비교"],
        "10가지 전략 과거 성과 비교",
        "Historical h1",
        required=False,
    )
    if title_changes == 0:
        print("Historical h1: source title is structurally split/non-literal; keep existing readable title")

    # Intro copy is secondary. Replace only when there is exactly one semantic match.
    intro_matches = semantic_tag_matches(text, "p", ["현재", "전략", "과거"])
    if len(intro_matches) == 1:
        m = intro_matches[0]
        replacement = f'<p{m.group(1)}>종목과 기간을 정하면 같은 조건에서 10가지 전략의 과거 성과를 비교합니다.</p>'
        text = text[:m.start()] + replacement + text[m.end():]

    eyebrow_pattern = re.compile(r"STRATEGY\s*SELECTOR\s*·?\s*v?[0-9A-Za-z.\-]*", re.IGNORECASE)
    text, eyebrow_count = eyebrow_pattern.subn("종목 과거 성과", text, count=1)
    if eyebrow_count == 0 and "STRATEGY SELECTOR" in text:
        text = text.replace("STRATEGY SELECTOR", "종목 과거 성과", 1)

    # Collapse only the actual 10-strategy list.  The previous v1.0.1
    # incorrectly assumed the intro copy ("이 기능으로 무엇을 해결하나요?")
    # lived inside the same JSX wrapper as the strategy cards.  In the current
    # BacktestPanel they are siblings, so that assumption is invalid.
    strategy_names = [
        "상승 흐름 따라가기",
        "쉬어간 뒤 다시 오를 때 노리기",
        "막힌 가격 돌파 노리기",
        "지지 가격에서 반등 노리기",
        "과도한 하락 뒤 반등 노리기",
        "일정 가격 범위에서 노리기",
        "강한 상승 이어가기",
        "큰 움직임 전 조용한 구간 찾기",
        "20일선 반등 노리기",
        "상승 흐름 회복 노리기",
    ]
    present_strategy_names = [name for name in strategy_names if name in text]
    if len(present_strategy_names) < 2:
        raise RuntimeError(
            "Historical strategy block: strategy labels are insufficient for safe discovery "
            f"({len(present_strategy_names)} found)"
        )

    # First + last visible strategy label should sit inside the shared strategy
    # grid/list wrapper even when the explanatory intro is a separate sibling.
    strategy_range = smallest_container(
        text,
        [present_strategy_names[0], present_strategy_names[-1]],
        "Historical strategy list",
    )
    strategy_block = text[strategy_range.start:strategy_range.end]
    if len(strategy_block) > 40000:
        raise RuntimeError(
            "Historical strategy list: discovered wrapper is too broad; refusing to move page-level JSX"
        )
    collapsed = build_collapsed_strategy_block(strategy_block)
    text = text[:strategy_range.start] + text[strategy_range.end:]

    # Remove the standalone explanation card only when it resolves to a small,
    # local JSX container.  If its wrapper is broad, keep the copy rather than
    # risk deleting unrelated controls.
    if "이 기능으로 무엇을 해결하나요?" in text:
        intro_range = smallest_container(text, ["이 기능으로 무엇을 해결하나요?"], "Historical intro block")
        intro_block = text[intro_range.start:intro_range.end]
        if len(intro_block) <= 5000 and "검증 설정" not in intro_block:
            text = text[:intro_range.start] + text[intro_range.end:]
        else:
            print("Historical intro block: wrapper too broad; keep it instead of unsafe removal")

    # The primary action may be text or nested markup. '검증 설정' plus either
    # button copy or the max-hold controls is enough to identify the settings block.
    action_phrase = "10가지 방법 자동 비교 시작"
    if action_phrase in text:
        setup_range = smallest_container(text, ["검증 설정", action_phrase], "Historical settings block")
    else:
        fallback_markers = [m for m in ("최대 보유기간", "초기 자본", "검증 종목") if m in text]
        if not fallback_markers:
            raise RuntimeError("Historical settings block: action/settings anchors not found")
        setup_range = smallest_container(text, ["검증 설정", fallback_markers[0]], "Historical settings block")
    text = text[:setup_range.end] + "\n" + collapsed + text[setup_range.end:]

    # Copy changes are optional/semantic; layout changes above are mandatory.
    if action_phrase in text:
        text = text.replace(action_phrase, "과거 성과 비교", 1)
    text = text.replace("연구용 · Exit 정책 검증", "고급 검증")
    text = text.replace("검증 열기", "Exit 정책 연구 보기")
    return text

def patch_embedded_scanner(text: str) -> str:
    text = replace_once(
        text,
        '<span>추천 후보 찾기</span>\n          <h2>Scanner 후보를 바로 추가</h2>',
        '<h2>Scanner 후보</h2>',
        "EmbeddedScanner heading",
    )
    text = replace_once(
        text,
        '<small>기존 종목 찾기와 같은 Scanner · 같은 결과 공유</small>',
        '<small>시장 선택 후 후보 찾기</small>',
        "EmbeddedScanner helper",
    )
    old_empty = (
        '        <div className="tracking-scanner-empty">\n'
        '          <strong>아직 종목 찾기 결과가 없습니다.</strong>\n'
        '          <span>시장 전체 또는 KOSPI·KOSDAQ을 선택하고 이 화면에서 바로 실행하세요.</span>\n'
        '        </div>'
    )
    new_empty = (
        '        <div className="tracking-scanner-empty">\n'
        '          <span>아직 후보가 없습니다. 위에서 시장을 선택하고 후보 찾기를 실행하세요.</span>\n'
        '        </div>'
    )
    text = replace_once(text, old_empty, new_empty, "EmbeddedScanner empty state")
    return text


def patch_recommendation_tracking(text: str) -> str:
    # Remove the redundant eyebrow and keep one short purpose sentence.
    if "<span>종목 성과 기록</span>" in text:
        text = text.replace("<span>종목 성과 기록</span>", "", 1)
    else:
        raise RuntimeError("Tracking page head: '종목 성과 기록' eyebrow not found")

    old_descriptions = (
        "Scanner 후보를 찾거나 원하는 종목을 직접 추가해 이후 성과를 기록하고 Scanner 개선에 활용합니다.",
        "이 화면에서 Scanner 종목 찾기를 직접 실행하거나 종목을 추가해 이후 성과를 기록하고 Scanner 개선에 활용합니다.",
        "이 화면에서 Scanner 종목 찾기를 직접 실행하거나 원하는 종목을 직접 추가해 이후 가격 움직임과 성과를 기록합니다. 쌓인 데이터는 Scanner가 어떤 조건에서 잘 작동했는지 분석하고 개선하는 데 사용됩니다.",
    )
    changed = 0
    for old in old_descriptions:
        if old in text:
            text = text.replace(old, "선택한 종목의 이후 성과를 기록하고 Scanner 개선 자료로 사용합니다.", 1)
            changed += 1
            break
    if changed == 0:
        # Fallback: limit the semantic search to the tracking header.
        header = smallest_container(text, ["종목 성과 추적", "최신 데이터 반영"], "Tracking page header")
        block = text[header.start:header.end]
        p_matches = semantic_tag_matches(block, "p", ["Scanner", "성과"])
        if len(p_matches) != 1:
            raise RuntimeError(f"Tracking page head description: expected 1 semantic paragraph, found {len(p_matches)}")
        m = p_matches[0]
        replacement = f'<p{m.group(1)}>선택한 종목의 이후 성과를 기록하고 Scanner 개선 자료로 사용합니다.</p>'
        block = block[:m.start()] + replacement + block[m.end():]
        text = text[:header.start] + block + text[header.end:]

    old_scanner_head = '<div className="tracking-section-head"><div><span>Scanner 결과</span><h2>최근 추천 후보</h2></div><small>{scannerSession ? `기준일 ${dateText(scannerDate)} · ${candidates.length}종목` : "최근 Scanner 결과 없음"}</small></div>'
    new_scanner_head = '<div className="tracking-section-head"><div><h2>후보 결과</h2></div><small>{scannerSession ? `기준일 ${dateText(scannerDate)} · ${candidates.length}종목` : "후보 없음"}</small></div>'
    text = replace_once(text, old_scanner_head, new_scanner_head, "Tracking candidate result head")

    old_candidate_empty = '<div className="tracking-empty tracking-empty-action"><strong>위 종목 찾기를 실행하면 추천 후보가 여기에 표시됩니다.</strong><span>메인 종목 찾기에서 실행한 결과도 같은 Scanner 상태를 사용합니다.</span></div>'
    new_candidate_empty = '<p className="tracking-empty">아직 후보가 없습니다.</p>'
    text = replace_once(text, old_candidate_empty, new_candidate_empty, "Tracking candidate empty")

    old_manual_head = '<div className="tracking-section-head"><div><span>직접 추가</span><h2>원하는 종목 직접 찾기</h2></div><small>종목명 또는 코드만 입력 · 기준일과 기준가는 자동</small></div>'
    new_manual_head = '<div className="tracking-section-head"><div><h2>직접 추가</h2></div><small>종목명 또는 코드 입력 · 기준일과 기준가는 자동</small></div>'
    text = replace_once(text, old_manual_head, new_manual_head, "Tracking manual head")

    old_list_head = '<div className="tracking-section-head"><div><span>저장된 기록</span><h2>추적 중인 종목과 기록</h2></div><small>종목 · 출처 · 시작 기준 · 현재 상태를 한 화면에서 확인</small></div>'
    new_list_head = '<div className="tracking-section-head"><div><h2>추적 기록</h2></div><small>종목 · 출처 · 시작 기준 · 현재 상태</small></div>'
    text = replace_once(text, old_list_head, new_list_head, "Tracking list head")

    old_empty = '<div className="tracking-empty tracking-empty-action"><strong>{rows.length === 0 ? "아직 추적 중인 종목이 없습니다." : "현재 필터에 맞는 추적 기록이 없습니다."}</strong><span>{rows.length === 0 ? "위 종목 찾기에서 추천 후보를 선택하거나 원하는 종목을 직접 추가해 추적을 시작할 수 있습니다." : "다른 출처 또는 상태 필터를 선택해보세요."}</span></div>'
    new_empty = '<div className="tracking-empty"><strong>{rows.length === 0 ? "아직 추적 중인 종목이 없습니다." : "현재 필터에 맞는 추적 기록이 없습니다."}</strong></div>'
    text = replace_once(text, old_empty, new_empty, "Tracking list empty")
    return text

def patch_simulation(text: str) -> str:
    old_head = '<div><span className="sim-eyebrow">Scanner 전략 전체 검증</span><h1>전략 성과 검증</h1><p>Scanner 전략을 과거 시장에 적용해 전체 성과를 검증합니다.</p></div>'
    new_head = '<div><h1>전략 성과 검증</h1><p>Scanner 전체 전략을 선택한 기간의 과거 시장에서 검증합니다.</p></div>'
    text = replace_once(text, old_head, new_head, "Simulation page head")

    old_section_head = '<div className="sim-section-head"><div><span className="sim-section-kicker">검증 설정</span><h2>무엇을, 어느 기간에 검증할지 저장합니다.</h2></div><small>최소 60 실제 거래일</small></div>'
    new_section_head = '<div className="sim-section-head"><div><h2>검증 설정</h2></div><small>최소 60 실제 거래일</small></div>'
    text = replace_once(text, old_section_head, new_section_head, "Simulation validation heading")

    overview = (
        '          <div className="sim-validation-overview">\n'
        '            <div><span>검증 대상</span><strong>Production Scanner</strong></div>\n'
        '            <div><span>Scanner 버전</span><strong>{PRODUCTION_SCANNER_VERSION}</strong></div>\n'
        '            <div><span>시장</span><strong>{marketLabel(marketScope)}</strong></div>\n'
        '            <div><span>상태</span><strong>설정 저장 전</strong></div>\n'
        '          </div>\n\n'
    )
    text = replace_once(text, overview, '', "Simulation overview removal")

    old_tail = (
        '          <p className="sim-validation-hint">{periodHint}</p>\n'
        '        </section>\n\n'
        '        <section className="sim-validation-block sim-draft-action">\n'
        '          <div><span className="sim-section-kicker">저장</span><h2>설정을 먼저 보존합니다.</h2><p>저장된 설정은 검증 대상·Scanner 버전·시장·실제 거래일 범위를 함께 남깁니다. 실행 엔진은 다음 단계에서 이 설정을 읽어 사용합니다.</p></div>\n'
        '          <button className="sim-primary" disabled={busy || !preview?.valid || !draftName.trim()} onClick={() => void saveDraft()}>{busy ? "처리 중…" : "설정 저장"}</button>\n'
        '        </section>\n\n'
        '        <section className="sim-validation-block sim-execution-pending">\n'
        '          <div><span className="sim-section-kicker">실행 정책</span><h2>실제 검증 실행은 다음 단계에서 연결합니다.</h2><p>D 신호 → D+1 체결, Gap·Slippage·수수료·Stop/Target 우선순위를 고정한 실행 정책이 완성되기 전에는 기존 수동 체결을 새 전략 검증처럼 실행하지 않습니다.</p></div>\n'
        '          <button className="sim-primary" disabled>검증 실행 · 준비 중</button>\n'
        '        </section>'
    )
    new_tail = (
        '          <p className="sim-validation-hint">{periodHint}</p>\n'
        '          <div className="sim-validation-meta">기준 Scanner {PRODUCTION_SCANNER_VERSION} · {marketLabel(marketScope)} · 최소 60 거래일</div>\n'
        '          <div className="sim-validation-savebar">\n'
        '            <button className="sim-primary" disabled={busy || !preview?.valid || !draftName.trim()} onClick={() => void saveDraft()}>{busy ? "처리 중…" : "설정 저장"}</button>\n'
        '          </div>\n'
        '        </section>\n'
        '        <p className="sim-validation-pending-note">검증 실행 기능은 준비 중입니다.</p>'
    )
    text = replace_once(text, old_tail, new_tail, "Simulation action consolidation")
    return text


GLOBAL_CSS = r'''

/* UX.1.2 — action-first hierarchy, no decorative guide cards */
.ux12-strategy-list{margin:18px 0 0;border-top:1px solid var(--border-subtle,#30343b);border-bottom:1px solid var(--border-subtle,#30343b);padding:0}
.ux12-strategy-list>summary{cursor:pointer;list-style:none;padding:14px 4px;color:var(--text-secondary,#9aa1ab);font-weight:700}
.ux12-strategy-list>summary::-webkit-details-marker{display:none}
.ux12-strategy-list>summary::after{content:"▾";float:right;color:var(--text-muted,#7f8792)}
.ux12-strategy-list[open]>summary::after{content:"▴"}
.ux12-strategy-list[open]{padding-bottom:14px}
'''

TRACKING_CSS = r'''

/* UX.1.2 — compact action-first tracking/validation layout */
.tracking-unified .tracking-head{padding-bottom:14px}
.tracking-unified .tracking-head h1{margin-top:0}
.tracking-unified .tracking-head p{max-width:760px;margin-top:6px}
.tracking-unified .tracking-meta-line{margin-top:0}
.tracking-unified .tracking-section-head{margin-bottom:10px}
.tracking-unified .tracking-section-head h2{margin:0}
.tracking-unified .tracking-empty{min-height:0;padding:12px 0}
.tracking-embedded-scanner .tracking-section-head{align-items:end}
.sim-validation-foundation .sim-page-head{align-items:end}
.sim-validation-foundation .sim-page-head p{max-width:760px}
.sim-validation-meta{margin-top:12px;padding-top:12px;border-top:1px solid var(--border-subtle,#30343b);color:var(--text-muted,#7f8792);font-size:13px}
.sim-validation-savebar{display:flex;justify-content:flex-end;margin-top:14px}
.sim-validation-pending-note{margin:8px 0 0;color:var(--text-muted,#7f8792);font-size:13px;text-align:right}
@media (max-width:760px){.sim-validation-savebar{justify-content:stretch}.sim-validation-savebar .sim-primary{width:100%}.sim-validation-pending-note{text-align:left}}
'''


def append_css(text: str, addition: str, marker: str) -> str:
    if marker in text:
        raise RuntimeError(f"CSS marker already present: {marker}")
    return text.rstrip() + "\n" + addition.strip() + "\n"


def patch_copy_assertions() -> list[str]:
    changed: list[str] = []
    tests_root = ROOT / "frontend" / "tests"
    if not tests_root.exists():
        return changed
    replacements = {
        '"오늘의 후보 찾기"': '"후보 찾기"',
        '"10가지 투자 방법 자동 비교"': '"10가지 전략 과거 성과 비교"',
        '"10가지 방법 자동 비교 시작"': '"과거 성과 비교"',
    }
    for path in tests_root.rglob("*.py"):
        original = path.read_text(encoding="utf-8")
        updated = original
        for old, new in replacements.items():
            # Only copy assertions should move with intentional UI wording.
            if old in updated:
                lines = []
                touched = False
                for line in updated.splitlines(keepends=True):
                    if old in line and "assert" in line:
                        line = line.replace(old, new)
                        touched = True
                    lines.append(line)
                if touched:
                    updated = "".join(lines)
        if updated != original:
            path.write_text(updated, encoding="utf-8", newline="")
            changed.append(str(path.relative_to(ROOT)))
    return changed


def main() -> int:
    print(f"PROJECT ROOT: {ROOT}")
    print(f"LAUNCH PYTHON: {sys.executable}")

    # Environment preflight happens before any source mutation.
    project_python = resolve_project_python()
    print(f"PROJECT PYTHON: {project_python}")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found")

    for rel in TARGETS:
        require(rel)
    historical_path = discover_historical_source()
    require("frontend/package.json")
    require("backend/tools/verify_scanner_production_baseline.py")
    if (ROOT / "docs" / "TRACKING_BASELINE.md").exists():
        frozen = (ROOT / "docs" / "TRACKING_BASELINE.md").read_text(encoding="utf-8")
        if "CLOSED" not in frozen or "FROZEN" not in frozen:
            raise RuntimeError("TRACK.1 frozen baseline marker is inconsistent")

    preflight_markers(historical_path)
    print("PREFLIGHT: UX.1.1 source markers detected")

    originals: dict[Path, bytes] = {}
    try:
        patchers: list[tuple[Path, object]] = [
            (historical_path, patch_app_historical),
            (require("frontend/src/components/ScannerPanel.tsx"), patch_scanner_panel),
            (require("frontend/src/components/EmbeddedScanner.tsx"), patch_embedded_scanner),
            (require("frontend/src/components/RecommendationTracking.tsx"), patch_recommendation_tracking),
            (require("frontend/src/components/SimulationWorkspace.tsx"), patch_simulation),
        ]

        # Validate every source transformation in memory before touching the
        # working tree.  This prevents a source-shape mismatch in one screen
        # from causing a write/rollback cycle across unrelated frontend files.
        planned: dict[Path, str] = {}
        for path, fn in patchers:
            rel = str(path.relative_to(ROOT))
            current = path.read_text(encoding="utf-8")
            updated = fn(current)
            if updated == current:
                raise RuntimeError(f"No UX.1.2 change produced for {rel}")
            planned[path] = updated
            print(f"DRY-RUN OK {rel}")

        styles = require("frontend/src/styles.css")
        planned[styles] = append_css(
            styles.read_text(encoding="utf-8"),
            GLOBAL_CSS,
            "UX.1.2 — action-first hierarchy",
        )
        print("DRY-RUN OK frontend/src/styles.css")

        tracking_css = require("frontend/src/tracking.css")
        planned[tracking_css] = append_css(
            tracking_css.read_text(encoding="utf-8"),
            TRACKING_CSS,
            "UX.1.2 — compact action-first",
        )
        print("DRY-RUN OK frontend/src/tracking.css")

        print("PATCH PLAN: all UX.1.2 source transformations validated before write")
        for path, updated in planned.items():
            originals[path] = path.read_bytes()
            path.write_text(updated, encoding="utf-8", newline="")
            print(f"UPDATE {path.relative_to(ROOT)}")

        # Update only stale copy assertions caused by intentional UI wording.
        test_paths_before = {p: p.read_bytes() for p in (ROOT / "frontend" / "tests").rglob("*.py")} if (ROOT / "frontend" / "tests").exists() else {}
        for p, data in test_paths_before.items():
            originals.setdefault(p, data)
        changed_tests = patch_copy_assertions()
        for rel in changed_tests:
            print(f"UPDATE {rel} (copy assertion only)")

        tests = [
            "backend/tests/test_recommendation_tracking_track1.py",
            "backend/tests/test_tracking_performance_track1.py",
            "backend/tests/test_tracking_integrity_track19.py",
            "backend/tests/test_tracking_usability_track110.py",
            "backend/tests/test_tracking_api_track1.py",
            "backend/tests/test_tracking_same_baseline_merge_track1104.py",
            "backend/tests/test_simulation_validation_period_simval0.py",
            "backend/tests/test_simulation_validation_catalog_simval01.py",
            "frontend/tests/test_tracking_track1_source.py",
            "frontend/tests/test_tracking_performance_source.py",
            "frontend/tests/test_scanner_session_reactive_track19.py",
            "frontend/tests/test_embedded_scanner_track1101.py",
            "frontend/tests/test_scanner_panel_shared_track1101.py",
            "frontend/tests/test_tracking_lifecycle_track1102.py",
            "frontend/tests/test_manual_tracking_completion_track1103.py",
            "frontend/tests/test_same_baseline_merge_track1104.py",
            "frontend/tests/test_simulation_ui1_source.py",
        ]
        existing_tests = [p for p in tests if (ROOT / p).exists()]
        run([project_python, "-m", "pytest", *existing_tests, "-q", "-p", "no:cacheprovider"])
        run([npm, "--prefix", "frontend", "run", "build"])

        tracking_verifier = ROOT / "backend" / "tools" / "verify_tracking_baseline.py"
        tracking_db = ROOT / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"
        if tracking_verifier.exists() and tracking_db.exists():
            print("\n[REQUIRED] TRACK.1 frozen runtime baseline")
            run([project_python, str(tracking_verifier.relative_to(ROOT))])
        else:
            print("\n[SKIP] TRACK.1 frozen runtime baseline")
            print(f"Tracking runtime DB not present on this machine: {tracking_db}")

        print("\n[REPORT ONLY] Scanner production baseline")
        baseline = run([project_python, "backend/tools/verify_scanner_production_baseline.py"], check=False)
        if baseline.returncode != 0:
            print("WARNING: pre-existing Scanner baseline mismatch remains; UX.1.2 is frontend-only.")

        print("\nUX.1.2 v1.0.2 applied successfully.")
        print("- Removed both awkward 3-step pill rails.")
        print("- Scanner is now title -> market selection -> primary action -> results.")
        print("- Historical single-stock validation puts settings before the 10-strategy explanation; strategies are collapsed.")
        print("- Tracking copy/empty states are compact and result-oriented.")
        print("- Strategy validation keeps settings and save action together; development-policy cards were removed.")
        print("- No Backend, DB, Scanner algorithm, Ranking, Risk, Entry/Stop/Target, or TRACK behavior was changed.")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("ROLLBACK UX.1.2 changes...")
        for path, data in reversed(list(originals.items())):
            try:
                path.write_bytes(data)
            except Exception as rollback_exc:
                print(f"ROLLBACK WARNING {path}: {rollback_exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
