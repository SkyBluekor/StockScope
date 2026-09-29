from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.macro.identity import content_hash
from app.macro.store import MACRO_META_EXPECTED, MACRO_STORE_TABLES


class LocalMacroReader:
    """Strict read-only Macro reader.

    It never creates a directory, database, schema, collection run, network
    request or backfill. Missing storage is returned as explicit unavailable
    state.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _table_names(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _schema_state(self) -> tuple[bool, str | None]:
        if not self.db_path.is_file():
            return False, "STORE_NOT_FOUND"
        try:
            with self._connect() as conn:
                tables = self._table_names(conn)
                if not set(MACRO_STORE_TABLES).issubset(tables):
                    return False, "SCHEMA_UNAVAILABLE"
                meta = {
                    str(row["key"]): str(row["value"])
                    for row in conn.execute(
                        "SELECT key,value FROM macro_schema_meta"
                    ).fetchall()
                }
                if any(meta.get(key) != value for key, value in MACRO_META_EXPECTED.items()):
                    return False, "SCHEMA_VERSION_MISMATCH"
        except sqlite3.Error:
            return False, "READ_FAILED"
        return True, None

    @staticmethod
    def _aware_utc(value: str, field: str) -> datetime:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field}은 timezone-aware ISO-8601 시각이어야 합니다.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{field}은 timezone-aware ISO-8601 시각이어야 합니다.")
        return parsed.astimezone(timezone.utc)

    def read_series_as_of(
        self,
        series_id: str,
        *,
        cutoff: str,
        historical_eligible_only: bool = True,
    ) -> dict[str, Any]:
        cutoff_utc = self._aware_utc(cutoff, "cutoff")
        ready, reason = self._schema_state()
        if not ready:
            return {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": reason,
                "observation": None,
            }
        quality_sql = (
            "AND time_quality IN ('EXACT','PROVIDER_TIME')"
            if historical_eligible_only
            else ""
        )
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM macro_observation_revision
                    WHERE series_id=?
                      AND published=1
                      {quality_sql}
                    """,
                    (series_id,),
                ).fetchall()
                eligible_rows = [
                    row
                    for row in rows
                    if self._aware_utc(str(row["available_at"]), "available_at")
                    <= cutoff_utc
                ]
                eligible_rows.sort(
                    key=lambda row: (
                        str(row["observation_date"]),
                        self._aware_utc(str(row["available_at"]), "available_at"),
                        int(row["revision_no"]),
                    ),
                    reverse=True,
                )
                row = eligible_rows[0] if eligible_rows else None
                if row is None:
                    any_row = conn.execute(
                        """
                        SELECT COUNT(*) FROM macro_observation_revision
                        WHERE series_id=? AND published=1
                        """,
                        (series_id,),
                    ).fetchone()
                    reason = (
                        "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"
                        if historical_eligible_only and int(any_row[0] or 0) > 0
                        else "DATA_ABSENT"
                    )
                    return {
                        "status": "UNAVAILABLE",
                        "series_id": series_id,
                        "reason": reason,
                        "observation": None,
                    }
                observation = {
                    key: row[key]
                    for key in (
                        "id",
                        "observation_key",
                        "revision_no",
                        "series_id",
                        "native_observation_id",
                        "observation_date",
                        "normalized_value",
                        "source_unit",
                        "realtime_start",
                        "realtime_end",
                        "vintage_id",
                        "available_at",
                        "fetched_at",
                        "time_quality",
                        "first_seen_at",
                        "source_published_at",
                        "provider_available_at",
                        "corrected_at",
                        "source_payload_hash",
                        "normalizer_version",
                        "normalized_hash",
                    )
                }
                return {
                    "status": "COMPLETE",
                    "series_id": series_id,
                    "reason": None,
                    "observation": observation,
                }
        except sqlite3.Error as exc:
            return {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": "READ_FAILED",
                "error": str(exc),
                "observation": None,
            }

    def read_series_window(
        self,
        series_id: str,
        *,
        cutoff: str,
        observation_limit: int,
        historical_eligible_only: bool = True,
    ) -> dict[str, Any]:
        if observation_limit < 1:
            raise ValueError("observation_limit must be >= 1.")
        cutoff_utc = self._aware_utc(cutoff, "cutoff")
        ready, reason = self._schema_state()
        if not ready:
            payload = {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": reason,
                "cutoff": cutoff,
                "historical_eligible_only": historical_eligible_only,
                "observations": [],
            }
            return {**payload, "window_hash": content_hash(payload)}

        quality_sql = (
            "AND time_quality IN ('EXACT','PROVIDER_TIME')"
            if historical_eligible_only
            else ""
        )
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM macro_observation_revision
                    WHERE series_id=?
                      AND published=1
                      {quality_sql}
                    """,
                    (series_id,),
                ).fetchall()

                available_rows = [
                    row
                    for row in rows
                    if self._aware_utc(str(row["available_at"]), "available_at")
                    <= cutoff_utc
                ]

                # Select the newest revision that was actually available by the
                # requested cutoff for each immutable observation identity.
                chosen: dict[str, sqlite3.Row] = {}
                for row in available_rows:
                    key = str(row["observation_key"])
                    previous = chosen.get(key)
                    if previous is None:
                        chosen[key] = row
                        continue
                    current_rank = (
                        self._aware_utc(str(row["available_at"]), "available_at"),
                        int(row["revision_no"]),
                    )
                    previous_rank = (
                        self._aware_utc(
                            str(previous["available_at"]),
                            "available_at",
                        ),
                        int(previous["revision_no"]),
                    )
                    if current_rank > previous_rank:
                        chosen[key] = row

                ordered = sorted(
                    chosen.values(),
                    key=lambda row: (
                        str(row["observation_date"]),
                        self._aware_utc(str(row["available_at"]), "available_at"),
                        int(row["revision_no"]),
                    ),
                    reverse=True,
                )
                selected = ordered[:observation_limit]

                observation_fields = (
                    "id",
                    "observation_key",
                    "revision_no",
                    "series_id",
                    "native_observation_id",
                    "observation_date",
                    "normalized_value",
                    "source_unit",
                    "realtime_start",
                    "realtime_end",
                    "vintage_id",
                    "available_at",
                    "fetched_at",
                    "time_quality",
                    "first_seen_at",
                    "source_published_at",
                    "provider_available_at",
                    "corrected_at",
                    "source_payload_hash",
                    "normalizer_version",
                    "normalized_hash",
                )
                observations = [
                    {key: row[key] for key in observation_fields}
                    for row in selected
                ]

                if observations:
                    status = "COMPLETE"
                    reason = None
                else:
                    published_count = int(
                        conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM macro_observation_revision
                            WHERE series_id=? AND published=1
                            """,
                            (series_id,),
                        ).fetchone()[0]
                    )
                    if rows:
                        # Matching quality rows exist, but none were available
                        # by the requested cutoff.
                        reason = "DATA_NOT_AVAILABLE_BY_CUTOFF"
                    elif historical_eligible_only and published_count > 0:
                        reason = "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"
                    else:
                        reason = "DATA_ABSENT"
                    status = "UNAVAILABLE"

                payload = {
                    "status": status,
                    "series_id": series_id,
                    "reason": reason,
                    "cutoff": cutoff,
                    "historical_eligible_only": historical_eligible_only,
                    "requested_limit": observation_limit,
                    "returned_count": len(observations),
                    "observations": observations,
                }
                return {**payload, "window_hash": content_hash(payload)}
        except sqlite3.Error as exc:
            payload = {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": "READ_FAILED",
                "cutoff": cutoff,
                "historical_eligible_only": historical_eligible_only,
                "requested_limit": observation_limit,
                "returned_count": 0,
                "observations": [],
                "error": str(exc),
            }
            return {**payload, "window_hash": content_hash(payload)}

    @staticmethod
    def _date_text(value: str, field: str) -> str:
        text = str(value or "").strip()
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be YYYY-MM-DD.") from exc
        return text

    @staticmethod
    def _observation_projection(row: sqlite3.Row) -> dict[str, Any]:
        return {
            key: row[key]
            for key in (
                "id",
                "observation_key",
                "revision_no",
                "series_id",
                "native_observation_id",
                "observation_date",
                "normalized_value",
                "source_unit",
                "realtime_start",
                "realtime_end",
                "vintage_id",
                "available_at",
                "fetched_at",
                "time_quality",
                "first_seen_at",
                "source_published_at",
                "provider_available_at",
                "corrected_at",
                "source_payload_hash",
                "normalizer_version",
                "normalized_hash",
            )
        }

    def inspect_reference_archive(
        self,
        series_id: str,
    ) -> dict[str, Any]:
        ready, reason = self._schema_state()
        if not ready:
            return {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": reason,
                "usage_scope": "REFERENCE_RESEARCH_ONLY",
                "vintages": [],
            }
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM macro_observation_revision
                    WHERE series_id=? AND published=1
                    ORDER BY observation_date ASC,revision_no ASC
                    """,
                    (series_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            return {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": "READ_FAILED",
                "error": str(exc),
                "usage_scope": "REFERENCE_RESEARCH_ONLY",
                "vintages": [],
            }

        by_vintage: dict[str, dict[str, sqlite3.Row]] = {}
        revision_counts: dict[str, int] = {}
        for row in rows:
            vintage = str(row["vintage_id"] or "").strip()
            if not vintage:
                continue
            revision_counts[vintage] = revision_counts.get(vintage, 0) + 1
            chosen = by_vintage.setdefault(vintage, {})
            key = str(row["observation_key"])
            previous = chosen.get(key)
            if previous is None or int(row["revision_no"]) > int(previous["revision_no"]):
                chosen[key] = row

        vintages: list[dict[str, Any]] = []
        for vintage in sorted(by_vintage):
            selected = list(by_vintage[vintage].values())
            selected.sort(key=lambda row: str(row["observation_date"]))
            quality_counts: dict[str, int] = {}
            pit_eligible = 0
            for row in selected:
                quality = str(row["time_quality"])
                quality_counts[quality] = quality_counts.get(quality, 0) + 1
                if quality in {"EXACT", "PROVIDER_TIME"}:
                    pit_eligible += 1
            vintages.append(
                {
                    "vintage_id": vintage,
                    "observation_start": (
                        str(selected[0]["observation_date"]) if selected else None
                    ),
                    "observation_end": (
                        str(selected[-1]["observation_date"]) if selected else None
                    ),
                    "observation_count": len(selected),
                    "stored_revision_count": revision_counts[vintage],
                    "time_quality_counts": dict(sorted(quality_counts.items())),
                    "historical_pit_eligible_count": pit_eligible,
                }
            )
        return {
            "status": "COMPLETE" if vintages else "UNAVAILABLE",
            "series_id": series_id,
            "reason": None if vintages else "VINTAGE_ARCHIVE_ABSENT",
            "usage_scope": "REFERENCE_RESEARCH_ONLY",
            "vintages": vintages,
        }

    def read_reference_archive_range(
        self,
        series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        vintage_id: str,
        warmup_observations: int = 0,
    ) -> dict[str, Any]:
        start = self._date_text(observation_start, "observation_start")
        end = self._date_text(observation_end, "observation_end")
        if start > end:
            raise ValueError("observation_start must be <= observation_end.")
        vintage = str(vintage_id or "").strip()
        if not vintage:
            raise ValueError("vintage_id is required.")
        if warmup_observations < 0:
            raise ValueError("warmup_observations must be >= 0.")

        ready, reason = self._schema_state()
        if not ready:
            payload = {
                "status": "NOT_PREPARED",
                "series_id": series_id,
                "reason": reason,
                "usage_scope": "REFERENCE_RESEARCH_ONLY",
                "vintage_id": vintage,
                "observation_start": start,
                "observation_end": end,
                "warmup_requested": warmup_observations,
                "warmup_observations": [],
                "analysis_observations": [],
            }
            return {**payload, "archive_hash": content_hash(payload)}

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM macro_observation_revision
                    WHERE series_id=?
                      AND published=1
                      AND vintage_id=?
                      AND observation_date<=?
                    ORDER BY observation_date ASC,revision_no ASC
                    """,
                    (series_id, vintage, end),
                ).fetchall()
        except sqlite3.Error as exc:
            payload = {
                "status": "NOT_PREPARED",
                "series_id": series_id,
                "reason": "READ_FAILED",
                "error": str(exc),
                "usage_scope": "REFERENCE_RESEARCH_ONLY",
                "vintage_id": vintage,
                "observation_start": start,
                "observation_end": end,
                "warmup_requested": warmup_observations,
                "warmup_observations": [],
                "analysis_observations": [],
            }
            return {**payload, "archive_hash": content_hash(payload)}

        # One dataset is pinned to one explicit vintage. Within that fixed
        # vintage, use the newest published revision currently present. A
        # later revision therefore creates a new dataset identity instead of
        # mutating an existing immutable artifact.
        chosen: dict[str, sqlite3.Row] = {}
        for row in rows:
            key = str(row["observation_key"])
            previous = chosen.get(key)
            if previous is None or int(row["revision_no"]) > int(previous["revision_no"]):
                chosen[key] = row

        selected = list(chosen.values())
        selected.sort(key=lambda row: str(row["observation_date"]))
        analysis_rows = [
            row
            for row in selected
            if start <= str(row["observation_date"]) <= end
        ]
        warmup_candidates = [
            row for row in selected if str(row["observation_date"]) < start
        ]
        warmup_rows = (
            warmup_candidates[-warmup_observations:]
            if warmup_observations
            else []
        )

        warmup = [self._observation_projection(row) for row in warmup_rows]
        analysis = [self._observation_projection(row) for row in analysis_rows]
        quality_counts: dict[str, int] = {}
        pit_eligible_count = 0
        for row in analysis:
            quality = str(row["time_quality"])
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
            if quality in {"EXACT", "PROVIDER_TIME"}:
                pit_eligible_count += 1

        status = "READY_REFERENCE_RESEARCH" if analysis else "NOT_PREPARED"
        reason = None if analysis else "VINTAGE_RANGE_NOT_PREPARED"
        if analysis and len(warmup) < warmup_observations:
            status = "PARTIAL_REFERENCE_RESEARCH"
            reason = "WARMUP_INSUFFICIENT"

        semantic_refs = [
            {
                "observation_key": row["observation_key"],
                "observation_date": row["observation_date"],
                "normalized_hash": row["normalized_hash"],
                "vintage_id": row["vintage_id"],
                "time_quality": row["time_quality"],
            }
            for row in (*warmup, *analysis)
        ]
        identity_payload = {
            "series_id": series_id,
            "usage_scope": "REFERENCE_RESEARCH_ONLY",
            "vintage_id": vintage,
            "observation_start": start,
            "observation_end": end,
            "warmup_requested": warmup_observations,
            "semantic_refs": semantic_refs,
            "revision_policy": "LATEST_PUBLISHED_REVISION_WITHIN_FIXED_VINTAGE",
        }
        archive_hash = content_hash(identity_payload)
        return {
            "status": status,
            "series_id": series_id,
            "reason": reason,
            "usage_scope": "REFERENCE_RESEARCH_ONLY",
            "historical_evaluation_eligible": False,
            "vintage_id": vintage,
            "observation_start": start,
            "observation_end": end,
            "warmup_requested": warmup_observations,
            "warmup_count": len(warmup),
            "analysis_count": len(analysis),
            "time_quality_counts": dict(sorted(quality_counts.items())),
            "historical_pit_eligible_analysis_count": pit_eligible_count,
            "revision_policy": "LATEST_PUBLISHED_REVISION_WITHIN_FIXED_VINTAGE",
            "warmup_observations": warmup,
            "analysis_observations": analysis,
            "archive_hash": archive_hash,
        }

    def read_snapshot(
        self,
        series_ids: list[str] | tuple[str, ...],
        *,
        cutoff: str,
        historical_eligible_only: bool = True,
    ) -> dict[str, Any]:
        unique = tuple(sorted({str(item).strip() for item in series_ids if str(item).strip()}))
        components = [
            self.read_series_as_of(
                series_id,
                cutoff=cutoff,
                historical_eligible_only=historical_eligible_only,
            )
            for series_id in unique
        ]
        complete = sum(item["status"] == "COMPLETE" for item in components)
        status = "COMPLETE" if complete == len(components) and components else (
            "PARTIAL" if complete > 0 else "UNAVAILABLE"
        )
        payload = {
            "status": status,
            "cutoff": cutoff,
            "historical_eligible_only": historical_eligible_only,
            "components": components,
        }
        return {
            **payload,
            "snapshot_hash": content_hash(payload),
        }

    def read_prepared_range(
        self,
        series_id: str,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        ready, reason = self._schema_state()
        if not ready:
            return {
                "status": "UNAVAILABLE",
                "series_id": series_id,
                "reason": reason,
                "manifest": None,
            }
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM macro_prepared_range
                WHERE series_id=? AND start_date=? AND end_date=?
                ORDER BY prepared_at DESC,id DESC
                LIMIT 1
                """,
                (series_id, start_date, end_date),
            ).fetchone()
            if row is None:
                return {
                    "status": "UNAVAILABLE",
                    "series_id": series_id,
                    "reason": "MANIFEST_ABSENT",
                    "manifest": None,
                }
            manifest = {key: row[key] for key in row.keys()}
            return {
                "status": str(row["status"]),
                "series_id": series_id,
                "reason": None,
                "manifest": manifest,
            }
