"""GLOBAL-02-S2: offline-only UNSC change-notice evidence contract.

This module does NOT grant source rights. Parsing is limited to synthetic fixtures
or separately authorized, memory-only inputs. It is not registered as an approved
EventEvidence source and must never feed Scanner, JEV, trading, or storage.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from app.event_evidence.policy import EventEvidenceSourcePolicy
from app.event_evidence.time import (
    EvidenceTimeQuality,
    TemporalEvidence,
    conservative_available_at,
)

VERSION = "STOCKSCOPE_GLOBAL02_S2_UNSC_REFERENCE_V1"
SOURCE_KIND = "UNSC_SANCTIONS_UPDATE_CANDIDATE"
LIST_URL = "https://main.un.org/securitycouncil/en/content/list-updates-unsc-consolidated-list"
TERMS_URL = "https://www.un.org/en/about-us/terms-of-use"
ALLOWED_HOSTS = frozenset({"main.un.org", "press.un.org", "www.un.org", "un.org"})
MAX_HTML_BYTES = 1_000_000
MAX_ROWS = 40
MAX_REFS_PER_ROW = 40
NOTICE = re.compile(r"SC/\d{4,6}\Z")
REF = re.compile(r"[A-Z]{2}[IE]\.\d{3}\Z")
REGIME = re.compile(r"\d{4}\Z")
REF_SCAN = re.compile(r"(?<![A-Z0-9])([A-Za-z]{2}[iIeE]\.\d{3})(?![A-Z0-9])")
KIND = {
    "listing": "LISTING",
    "delisting": "DELISTING",
    "de-listing": "DELISTING",
    "de listing": "DELISTING",
    "amendment": "AMENDMENT",
}


class OfficialUpdateError(ValueError):
    """Public error carries a stable reason code, never untrusted source text."""


def candidate_policy() -> EventEvidenceSourcePolicy:
    """Research-only, deliberately not registered with policy_for_event_source."""
    return EventEvidenceSourcePolicy(
        policy_id="GLOBAL02-S2-UNSC-CANDIDATE-DENY-ALL",
        source_kind=SOURCE_KIND,
        policy_version=VERSION,
        display_allowed=False,
        normalization_allowed=False,
        raw_retention_allowed=False,
        derived_retention_allowed=False,
        ai_transform_allowed=False,
        historical_evaluation_allowed=False,
        prediction_input_allowed=False,
        attribution_required=True,
        policy_basis="UN_TERMS_PERSONAL_NONCOMMERCIAL_ONLY_NO_DERIVATIVES_OR_REDISTRIBUTION; "
                     "AUTOMATED_EXTRACTION_RIGHTS_UNVERIFIED",
    )


def _text(value: Any, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or len(value) > max_length:
        raise OfficialUpdateError("SEMANTICS_UNVERIFIED")
    return " ".join(value.split()).strip()


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise OfficialUpdateError("TIME_UNVERIFIED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise OfficialUpdateError("TIME_UNVERIFIED") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfficialUpdateError("TIME_UNVERIFIED")
    if parsed.utcoffset().total_seconds() != 0:
        raise OfficialUpdateError("TIME_UNVERIFIED")
    return parsed.astimezone(timezone.utc)


def official_url(value: str, *, base: str = LIST_URL) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    if value.startswith("//") or "\\" in value:
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    resolved = urljoin(base, value)
    try:
        parsed = urlsplit(resolved)
        allowed = (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and bool(parsed.path.strip("/"))
        )
    except ValueError:
        allowed = False
    if not allowed:
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    return resolved


class _TableReader(HTMLParser):
    """Tiny bounded HTML reader; no JS, external assets, or link traversal."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, Any]]]] = []
        self.depth = 0
        self.table: list[list[dict[str, Any]]] | None = None
        self.row: list[dict[str, Any]] | None = None
        self.cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = []
            return
        if self.depth != 1:
            return
        if tag == "tr":
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = {"text": "", "hrefs": []}
        elif tag == "a" and self.cell is not None:
            href = dict(attrs).get("href")
            if href is not None:
                self.cell["hrefs"].append(href)

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self.depth == 1 and self.table is not None:
                self.tables.append(self.table)
                self.table = None
                self.row = None
                self.cell = None
            self.depth = max(self.depth - 1, 0)
            return
        if self.depth != 1:
            return
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None


def rows_from_html(page: str | bytes, *, max_rows: int = MAX_ROWS) -> list[dict[str, Any]]:
    """Read a bounded table into memory only. Does not imply scraping permission."""
    if isinstance(page, bytes):
        if len(page) > MAX_HTML_BYTES:
            raise OfficialUpdateError("SOURCE_SIZE_EXCEEDED")
        try:
            page = page.decode("utf-8")
        except UnicodeDecodeError:
            raise OfficialUpdateError("SOURCE_UNAVAILABLE") from None
    if not isinstance(page, str) or len(page.encode("utf-8")) > MAX_HTML_BYTES:
        raise OfficialUpdateError("SOURCE_SIZE_EXCEEDED")
    if not 1 <= max_rows <= MAX_ROWS:
        raise OfficialUpdateError("SOURCE_LIMIT_INVALID")
    reader = _TableReader()
    reader.feed(page)
    for table in reader.tables:
        for index, row in enumerate(table):
            header = " ".join(_text(cell["text"]).lower() for cell in row)
            if not all(token in header for token in (
                "date", "sanctions list", "permanent reference", "type of update",
                "notification",
            )):
                continue
            data: list[dict[str, Any]] = []
            for cells in table[index + 1:]:
                if len(cells) < 6:
                    continue
                fields = [_text(cell["text"], max_length=1024) for cell in cells[:6]]
                if not any(fields):
                    continue
                hrefs = cells[5]["hrefs"]
                data.append({
                    "change_date": fields[0],
                    "sanctions_regime_id": fields[1],
                    "permanent_reference_numbers": fields[2],
                    "change_type": fields[3],
                    "number_of_entries_affected": fields[4],
                    "official_notice_id": fields[5],
                    "official_reference_url": hrefs[0] if len(hrefs) == 1 else "",
                })
                if len(data) > max_rows:
                    raise OfficialUpdateError("SOURCE_LIMIT_EXCEEDED")
            if data:
                return data
    raise OfficialUpdateError("SOURCE_UNAVAILABLE")


def _refs(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, str) or len(raw) > 1024:
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    # Allow common comma, semicolon and fullwidth separators, but no prose.
    cleaned = raw.replace("，", ",").replace("；", ";").replace("\u00a0", " ")
    tokens = [t.strip().upper() for t in re.split(r"[,;\s]+", cleaned) if t.strip()]
    if not tokens or len(tokens) > MAX_REFS_PER_ROW:
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    if any(not REF.fullmatch(token) for token in tokens):
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    if len(set(tokens)) != len(tokens):
        raise OfficialUpdateError("IDENTITY_CONFLICT")
    return tuple(tokens)


def normalize_row(row: Mapping[str, Any], *, observed_at_utc: str) -> dict[str, Any]:
    """Normalize one *synthetic/authorized* row without storing or publishing it."""
    observed = _utc(observed_at_utc)
    if row.get("source_published_at_utc") is not None:
        # Official UTC publication proof is not established for this source.
        raise OfficialUpdateError("PUBLISHED_TIME_UNVERIFIED")
    notice = _text(row.get("official_notice_id"), max_length=30).upper()
    regime = _text(row.get("sanctions_regime_id"), max_length=32)
    if not NOTICE.fullmatch(notice) or not REGIME.fullmatch(regime):
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    raw_date = _text(row.get("change_date"), max_length=16)
    try:
        changed = (
            datetime.strptime(raw_date, "%d/%m/%Y").date()
            if "/" in raw_date else date.fromisoformat(raw_date)
        )
    except ValueError:
        raise OfficialUpdateError("SEMANTICS_UNVERIFIED") from None
    if changed > observed.date():
        raise OfficialUpdateError("FUTURE_EVENT_UNVERIFIED")
    kind = KIND.get(_text(row.get("change_type"), max_length=40).lower())
    if kind is None:
        raise OfficialUpdateError("SEMANTICS_UNVERIFIED")
    refs = _refs(row.get("permanent_reference_numbers"))
    count = _text(str(row.get("number_of_entries_affected", "")), max_length=5)
    if not count.isdecimal() or int(count) != len(refs):
        raise OfficialUpdateError("SEMANTICS_UNVERIFIED")
    official = official_url(row.get("official_reference_url"))
    # Enforce link/notice agreement, not merely an official-looking domain.
    if notice.replace("/", "").lower() not in official.lower().replace("/", ""):
        raise OfficialUpdateError("IDENTITY_UNVERIFIED")
    timestamp = observed.isoformat()
    temporal = TemporalEvidence(
        available_at=conservative_available_at(timestamp, timestamp),
        fetched_at=timestamp,
        first_seen_at=timestamp,
        event_time=changed.isoformat(),
        source_published_at=None,
        corrected_at=None,
        time_quality=EvidenceTimeQuality.DATE_ONLY,
    )
    return {
        "source_kind": SOURCE_KIND,
        "official_notice_id": notice,
        "sanctions_regime_id": regime,
        "permanent_reference_numbers": refs,
        "change_type": kind,
        "change_date": changed.isoformat(),
        "official_reference_url": official,
        "observed_at_utc": timestamp,
        "source_published_at_utc": None,
        "time_quality": temporal.time_quality.value,
        "temporal": temporal,
        "validation_status": "OFFLINE_IDENTITY_AND_SEMANTICS_ONLY",
        "rights_capabilities": candidate_policy().to_dict(),
    }


def blank_report(status: str = "RIGHTS_UNVERIFIED") -> dict[str, Any]:
    return {
        "version": VERSION,
        "source_kind": SOURCE_KIND,
        "source_status": status,
        "rights_status": "RIGHTS_UNVERIFIED",
        "official_list_url": LIST_URL,
        "terms_url": TERMS_URL,
        "identity_validated_count": 0,
        "notice_id_count": 0,
        "date_only_count": 0,
        "change_type_counts": {},
        "excluded_reasons": {},
        "duplicate_conflicts": 0,
        "exact_duplicates_ignored": 0,
        "correction_linkage_verified_count": 0,
        "historical_pit_verified_count": 0,
        "publication_rights_approved": False,
        "retention_approved": False,
        "ai_transfer_approved": False,
        "historical_decision_eligible": False,
        "production_decision_approved": False,
        "writes": 0,
        "ai_calls": 0,
        "production_inputs": 0,
    }


def inspect_rows(
    rows: list[Mapping[str, Any]], *, observed_at_utc: str,
    max_rows: int = MAX_ROWS,
) -> dict[str, Any]:
    """Aggregate only; never return names, permanent IDs, or raw rows."""
    if not 0 <= len(rows) <= max_rows <= MAX_ROWS:
        raise OfficialUpdateError("SOURCE_LIMIT_EXCEEDED")
    identities: dict[tuple[str, str, str, str], tuple[str, str]] = {}
    count_by_type: Counter[str] = Counter()
    notices: set[str] = set()
    duplicates = 0
    excluded: Counter[str] = Counter()
    for row in rows:
        try:
            item = normalize_row(row, observed_at_utc=observed_at_utc)
        except OfficialUpdateError as exc:
            excluded[str(exc)] += 1
            continue
        notices.add(item["official_notice_id"])
        for ref in item["permanent_reference_numbers"]:
            key = (
                item["official_notice_id"], item["sanctions_regime_id"],
                ref, item["change_type"],
            )
            detail = (item["change_date"], item["official_reference_url"])
            previous = identities.get(key)
            if previous is not None and previous != detail:
                raise OfficialUpdateError("IDENTITY_CONFLICT")
            if previous is not None:
                duplicates += 1
                continue
            identities[key] = detail
            count_by_type[item["change_type"]] += 1
    report = blank_report("OFFLINE_FIXTURE_VALIDATED_ONLY")
    report.update({
        "identity_validated_count": len(identities),
        "notice_id_count": len(notices),
        "date_only_count": len(identities),
        "change_type_counts": dict(sorted(count_by_type.items())),
        "excluded_reasons": dict(sorted(excluded.items())),
        "exact_duplicates_ignored": duplicates,
    })
    return report
