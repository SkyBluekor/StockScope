import type { ScannerCandidate } from "../services/api";

// S30 is a rendering boundary only. The Scanner result's underlying arrays,
// engine ranks, eligibility, and saved sample indices remain byte-for-byte intact.
export type ScannerDisplayMember = {
  candidate: ScannerCandidate;
  originalIndex: number;
  fromOriginalMore: boolean;
};
export type ScannerDisplayGroup = {
  key: string;
  title: string;
  explanation: string;
  tie: boolean;
  declaredSize: number | null;
  complete: boolean;
  members: ScannerDisplayMember[];
};
export type ScannerDisplayLayout = {
  featured: ScannerDisplayGroup[];
  other: ScannerDisplayGroup[];
  originalFeaturedCount: number;
  visibleFeaturedCount: number;
  originalOtherCount: number;
  visibleOtherCount: number;
  expandedToKeepTieTogether: boolean;
};

function tieIdentity(candidate: ScannerCandidate): string | null {
  const priority = candidate.priority;
  if (!priority || priority.strict_rank !== false
    || !Number.isInteger(priority.tie_group) || !Number.isInteger(priority.tie_size)
    || typeof priority.tie_group !== "number" || typeof priority.tie_size !== "number"
    || priority.tie_group < 1 || priority.tie_size <= 1) return null;
  return [priority.tie_group, priority.tie_size, priority.tier].join("/");
}

function groupExplanation(tie: boolean, complete: boolean): string {
  if (!tie) return "표시 순서는 예상 수익률을 의미하지 않아요.";
  return complete
    ? "현재 조건상 동률입니다. 표시 순서는 우수 종목 순위가 아닙니다."
    : "동률 그룹의 일부만 이 결과에 포함됐습니다. 누락된 종목의 순서를 추측하지 않습니다.";
}

export function buildScannerDisplayLayout(
  candidates: ScannerCandidate[],
  originalFeaturedCount: number,
): ScannerDisplayLayout {
  const limit = Math.max(0, Math.min(
    candidates.length,
    Number.isInteger(originalFeaturedCount) ? originalFeaturedCount : 0,
  ));
  const groups: ScannerDisplayGroup[] = [];
  const seenTieKeys = new Set<string>();
  let i = 0;
  while (i < candidates.length) {
    const start = i;
    const identity = tieIdentity(candidates[i]);
    if (identity) {
      i++;
      while (i < candidates.length && tieIdentity(candidates[i]) === identity) i++;
    } else {
      i++;
    }
    const members = candidates.slice(start, i).map((candidate, offset) => ({
      candidate, originalIndex: start + offset,
      fromOriginalMore: start + offset >= limit,
    }));
    const declaredSize = identity ? candidates[start].priority!.tie_size! : null;
    // Matching metadata is never enough to claim completeness when a whole
    // group may be split by missing or inconsistent source rows.
    const repeated = identity !== null && seenTieKeys.has(identity);
    if (identity) seenTieKeys.add(identity);
    const complete = identity !== null
      && members.length === declaredSize && !repeated
      && members.every(member => tieIdentity(member.candidate) === identity);
    const tie = identity !== null;
    groups.push({
      key: (identity ?? "single") + ":" + start,
      title: tie
        ? complete
          ? `동일 조건 후보 · ${declaredSize}종목`
          : `동률 일부 확인 · ${members.length}/${declaredSize}종목`
        : "개별 검토 후보",
      explanation: groupExplanation(tie, complete),
      tie,
      declaredSize,
      complete,
      members,
    });
  }
  // Expand the visual top section to the *end* of any tie group crossing the
  // Scanner's original candidate_limit boundary, without rewriting that limit.
  let boundary = 0;
  for (const group of groups) {
    const end = boundary + group.members.length;
    boundary = end;
    if (end >= limit) break;
  }
  if (limit === 0) boundary = 0;
  const featured: ScannerDisplayGroup[] = [];
  const other: ScannerDisplayGroup[] = [];
  for (const group of groups) {
    (group.members[0].originalIndex < boundary ? featured : other).push(group);
  }
  return {
    featured, other,
    originalFeaturedCount: limit,
    visibleFeaturedCount: boundary,
    originalOtherCount: candidates.length - limit,
    visibleOtherCount: candidates.length - boundary,
    expandedToKeepTieTogether: boundary > limit,
  };
}
