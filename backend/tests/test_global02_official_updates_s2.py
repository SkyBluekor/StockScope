"""GLOBAL-02-S2: source identity, time, rights and no-side-effect regression."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.global02_official_updates import (
    MAX_HTML_BYTES, OfficialUpdateError, blank_report, candidate_policy,
    inspect_rows, normalize_row, official_url, rows_from_html, SOURCE_KIND,
)
from app.event_evidence.policy import EvidenceCapability, policy_for_event_source
from tools.data.inspect_global02_official_events import run, main

OBSERVED = "2026-11-03T01:00:00+00:00"


def _row(**changes):
    row = {
        "change_date": "2026-10-15",
        "sanctions_regime_id": "1267",
        "permanent_reference_numbers": "QDi.082, QDi.427, QDe.132",
        "change_type": "Amendment",
        "number_of_entries_affected": "3",
        "official_notice_id": "SC/16480",
        "official_reference_url": "https://press.un.org/en/2026/sc16480.doc.htm",
    }
    row.update(changes)
    return row


def _error(row, code):
    with pytest.raises(OfficialUpdateError, match=f"^{code}$"):
        normalize_row(row, observed_at_utc=OBSERVED)


def test_unsc_candidate_is_not_a_production_evidence_source():
    policy = candidate_policy()
    assert policy.source_kind == SOURCE_KIND
    for capability in EvidenceCapability:
        assert not policy.allows(capability)
        with pytest.raises(EventEvidenceContractError):
            policy.require(capability)
    with pytest.raises(EventEvidenceContractError) as unapproved:
        policy_for_event_source(SOURCE_KIND)
    assert unapproved.value.code == "EVENT_EVIDENCE_SOURCE_NOT_APPROVED"
    naver = policy_for_event_source("NAVER_NEWS", provider_kind="developer_center")
    assert not naver.ai_transform_allowed
    assert not naver.raw_retention_allowed


def test_normalizes_official_identity_and_date_only_without_backdating():
    row = normalize_row(_row(), observed_at_utc=OBSERVED)
    assert row["permanent_reference_numbers"] == ("QDI.082", "QDI.427", "QDE.132")
    assert row["change_type"] == "AMENDMENT"
    assert row["source_published_at_utc"] is None
    assert row["time_quality"] == "DATE_ONLY"
    assert row["temporal"].event_time == "2026-10-15"
    assert row["temporal"].available_at == "2026-11-03T01:00:00+00:00"
    assert row["temporal"].first_seen_at == row["temporal"].available_at
    assert not row["temporal"].historical_evaluation_eligible
    assert not row["temporal"].is_available_by("2026-10-15T23:59:59+00:00")
    assert row["rights_capabilities"]["ai_transform_allowed"] is False


@pytest.mark.parametrize("variant,wanted", [
    ({"official_notice_id": "SC/abc"}, "IDENTITY_UNVERIFIED"),
    ({"official_notice_id": ""}, "IDENTITY_UNVERIFIED"),
    ({"sanctions_regime_id": "Iran sanctions"}, "IDENTITY_UNVERIFIED"),
    ({"permanent_reference_numbers": "John Doe"}, "IDENTITY_UNVERIFIED"),
    ({"permanent_reference_numbers": "QDi.082, QDi.082",
      "number_of_entries_affected": "2"}, "IDENTITY_CONFLICT"),
    ({"permanent_reference_numbers": ""}, "IDENTITY_UNVERIFIED"),
    ({"change_type": "Re-listing"}, "SEMANTICS_UNVERIFIED"),
    ({"number_of_entries_affected": "2"}, "SEMANTICS_UNVERIFIED"),
    ({"change_date": "2026-02-30"}, "SEMANTICS_UNVERIFIED"),
    ({"change_date": "2030-01-01"}, "FUTURE_EVENT_UNVERIFIED"),
    ({"source_published_at_utc": "2026-10-15T00:00:00+00:00"},
     "PUBLISHED_TIME_UNVERIFIED"),
    ({"official_reference_url": "https://evil.example.org/sc16480"}, "IDENTITY_UNVERIFIED"),
    ({"official_reference_url": "https://press.un.org.evil.com/sc16480"}, "IDENTITY_UNVERIFIED"),
    ({"official_reference_url": "https://press.un.org/en/2026/sc12345.doc.htm"},
     "IDENTITY_UNVERIFIED"),
    ({"official_reference_url": "http://press.un.org/en/2026/sc16480.doc.htm"},
     "IDENTITY_UNVERIFIED"),
    ({"official_reference_url": "https://press.un.org@evil.com/sc16480"},
     "IDENTITY_UNVERIFIED"),
    ({"official_reference_url": "https://press.un.org/en/2026/sc16480.doc.htm?key=x"},
     "IDENTITY_UNVERIFIED"),
])
def test_untrusted_official_rows_fail_closed(variant, wanted):
    _error(_row(**variant), wanted)


@pytest.mark.parametrize("timestamp", [
    "2026-11-03", "2026-11-03T01:00:00", "2026-11-03T10:00:00+09:00",
    "invalid",
])
def test_observed_timestamp_requires_actual_utc(timestamp):
    with pytest.raises(OfficialUpdateError, match="TIME_UNVERIFIED"):
        normalize_row(_row(), observed_at_utc=timestamp)


def test_can_express_listing_delisting_amendment_as_separate_notice_revisions():
    amendment = _row()
    delisting = _row(
        official_notice_id="SC/16481",
        official_reference_url="https://press.un.org/en/2026/sc16481.doc.htm",
        permanent_reference_numbers="QDi.082",
        number_of_entries_affected="1",
        change_type="De-Listing",
        change_date="2026-10-16",
    )
    listing = _row(
        official_notice_id="SC/16482",
        official_reference_url="https://press.un.org/en/2026/sc16482.doc.htm",
        permanent_reference_numbers="QDi.082",
        number_of_entries_affected="1",
        change_type="Listing",
        change_date="2026-10-17",
    )
    report = inspect_rows([amendment, delisting, listing], observed_at_utc=OBSERVED)
    assert report["identity_validated_count"] == 5
    assert report["notice_id_count"] == 3
    assert report["change_type_counts"] == {"AMENDMENT": 3, "DELISTING": 1, "LISTING": 1}
    assert report["correction_linkage_verified_count"] == 0
    assert report["historical_pit_verified_count"] == 0


def test_exact_duplicate_dedup_and_conflicting_identity_rejected():
    row = _row()
    repeated = inspect_rows([row, deepcopy(row)], observed_at_utc=OBSERVED)
    assert repeated["identity_validated_count"] == 3
    assert repeated["exact_duplicates_ignored"] == 3
    conflict = _row(change_date="2026-10-14")
    with pytest.raises(OfficialUpdateError, match="IDENTITY_CONFLICT"):
        inspect_rows([row, conflict], observed_at_utc=OBSERVED)


def test_rejects_invalid_rows_without_echoing_source_text():
    report = inspect_rows([_row(), _row(
        change_type="THIS_IS_PRIVATE_UNTRUSTED_DATA",
        official_notice_id="SC/16483",
    )], observed_at_utc=OBSERVED)
    assert report["identity_validated_count"] == 3
    assert report["excluded_reasons"] == {"SEMANTICS_UNVERIFIED": 1}
    assert "PRIVATE" not in json.dumps(report)
    assert "QDI.082" not in json.dumps(report)
    assert "SC/16480" not in json.dumps(report)
    assert report["writes"] == report["ai_calls"] == report["production_inputs"] == 0


def test_bounded_html_table_parser_uses_only_single_official_notice_href():
    page = """
    <html><table><tr>
    <th>Date</th><th>Sanctions list</th><th>Permanent reference number</th>
    <th>Type of update</th><th>Number of entries affected</th>
    <th>Links to notification in English</th>
    </tr><tr><td>15/10/2026</td><td>1267</td><td>QDi.082, QDi.427, QDe.132</td>
    <td>Amendment</td><td>3</td>
    <td><a href="https://press.un.org/en/2026/sc16480.doc.htm">SC/16480</a></td></tr>
    </table></html>
    """
    rows = rows_from_html(page)
    assert len(rows) == 1
    norm = normalize_row(rows[0], observed_at_utc=OBSERVED)
    assert norm["change_date"] == "2026-10-15"
    assert norm["official_notice_id"] == "SC/16480"
    assert norm["source_published_at_utc"] is None


def test_html_bounded_and_untrusted_external_link_rejected():
    with pytest.raises(OfficialUpdateError, match="SOURCE_SIZE_EXCEEDED"):
        rows_from_html("x" * (MAX_HTML_BYTES + 1))
    with pytest.raises(OfficialUpdateError, match="SOURCE_UNAVAILABLE"):
        rows_from_html("<html><p>no update table</p></html>")
    with pytest.raises(OfficialUpdateError, match="SOURCE_LIMIT_EXCEEDED"):
        inspect_rows([_row()] * 41, observed_at_utc=OBSERVED)
    assert official_url("/securitycouncil/en/content/list-updates-unsc-consolidated-list").startswith(
        "https://main.un.org/"
    )
    with pytest.raises(OfficialUpdateError, match="IDENTITY_UNVERIFIED"):
        official_url("//outside.example/page")


def test_offline_cli_is_not_live_source_or_authorization(capsys):
    report = run(offline_fixture=True, observed_at_utc=OBSERVED)
    assert report["source_status"] == "OFFLINE_FIXTURE_VALIDATED_ONLY"
    assert report["data_origin"] == "SYNTHETIC_TEST_ROWS_NOT_REAL_UNSC_EVENTS"
    assert report["identity_validated_count"] == 4
    assert report["date_only_count"] == 4
    assert report["rights_status"] == "RIGHTS_UNVERIFIED"
    assert report["network_requests"] == 0
    assert report["writes"] == report["ai_calls"] == report["production_inputs"] == 0
    assert run()["source_status"] == "NOT_STARTED"
    assert main(["--offline-fixture"]) == 0
    output = capsys.readouterr().out
    assert "SC/99991" not in output
    assert "QDI.901" not in output


@pytest.mark.parametrize("confirmed", [False, True])
def test_live_even_with_user_opt_in_is_blocked_without_source_rights(confirmed):
    report = run(live=True, confirm_personal_research=confirmed)
    assert report["source_status"] == "RIGHTS_UNVERIFIED"
    assert report["network_requests"] == 0
    assert report["identity_validated_count"] == 0
    assert report["ai_transfer_approved"] is False
    assert report["retention_approved"] is False
    assert report["historical_decision_eligible"] is False
    assert report["production_decision_approved"] is False
    assert report["personal_research_confirmed"] is confirmed
