from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


KRX_SECTOR_MEMBERSHIP_PROBE_VERSION = (
    "VN_NEXT6C_S31_KRX_SECTOR_MEMBERSHIP_PROBE_V1"
)

_CODE_KEYS = (
    "ISU_SRT_CD",
    "종목코드",
    "ticker",
    "code",
)
_NAME_KEYS = (
    "ISU_ABBRV",
    "종목명",
    "name",
)
_KNOWN_AT_KEYS = (
    "available_at",
    "published_at",
    "publication_at",
    "announcement_at",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_code(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _load_json(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, Any] = {}
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        metadata = {
            key: item
            for key, item in value.items()
            if key not in {"output", "rows", "block1"}
        }
        rows = value.get("output") or value.get("rows") or value.get("block1")
    else:
        raise ValueError("JSON input must be an object or an array.")

    if not isinstance(rows, list):
        raise ValueError("JSON input does not contain a row array.")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Every membership row must be an object.")
    return [dict(row) for row in rows], metadata


def _load_csv(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "euc-kr", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)], {}
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("CSV encoding is not UTF-8/EUC-KR/CP949.") from last_error


def load_membership_export(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix in {".csv", ".txt"}:
        return _load_csv(path)
    raise ValueError("Only JSON or CSV membership exports are supported.")


def inspect_membership_export(
    *,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    query_date: str,
    benchmark_identity: str,
    source_label: str,
) -> dict[str, Any]:
    if len(query_date) != 8 or not query_date.isdigit():
        raise ValueError("query_date must be YYYYMMDD.")
    benchmark = str(benchmark_identity or "").strip()
    if not benchmark:
        raise ValueError("benchmark_identity is required.")
    source = str(source_label or "").strip()
    if not source:
        raise ValueError("source_label is required.")

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        code = _normalize_code(_first(row, _CODE_KEYS))
        if not code:
            raise ValueError(
                f"membership row {index} does not contain a stock code."
            )
        normalized.append(
            {
                "code": code,
                "name": str(_first(row, _NAME_KEYS) or "").strip() or None,
            }
        )

    normalized.sort(key=lambda item: (item["code"], item["name"] or ""))
    schema_fields = sorted(
        {
            str(key)
            for row in rows
            for key in row.keys()
        }
    )
    known_at_fields = sorted(
        key
        for key in _KNOWN_AT_KEYS
        if metadata.get(key) not in (None, "")
    )

    identity = {
        "probe_version": KRX_SECTOR_MEMBERSHIP_PROBE_VERSION,
        "source_label": source,
        "query_date": query_date,
        "benchmark_identity": benchmark,
        "constituents": normalized,
    }

    return {
        "probe_version": KRX_SECTOR_MEMBERSHIP_PROBE_VERSION,
        "source_label": source,
        "query_date": query_date,
        "benchmark_identity": benchmark,
        "row_count": len(normalized),
        "schema_fields": schema_fields,
        "schema_hash": _sha256(schema_fields),
        "constituents_hash": _sha256(normalized),
        "payload_hash": _sha256(identity),
        "constituent_identity_supported": bool(normalized),
        "historical_snapshot_supported": bool(normalized),
        "known_at_metadata_fields": known_at_fields,
        "known_at_proven": False,
        "pit_contract_compatible": False,
        "reason": (
            "SNAPSHOT_HAS_NO_VERIFIED_SOURCE_TIME_PROOF"
            if not known_at_fields
            else "SOURCE_TIME_METADATA_PRESENT_BUT_NOT_AUTHENTICATED_BY_OFFLINE_PROBE"
        ),
        "network_access": False,
        "limitations": [
            "OFFLINE_EXPORT_INSPECTION_ONLY",
            "QUERY_DATE_IS_NOT_KNOWN_AT",
            "FETCH_TIME_IS_NOT_KNOWN_AT",
            "NO_PRODUCTION_PROVIDER_AUTHORIZATION",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a manually exported or otherwise authorized KRX "
            "historical membership payload without making any network request."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--query-date", required=True)
    parser.add_argument("--benchmark-identity", required=True)
    parser.add_argument(
        "--source-label",
        default="KRX_DATA_MARKETPLACE_EXPORT",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows, metadata = load_membership_export(args.input)
    result = inspect_membership_export(
        rows=rows,
        metadata=metadata,
        query_date=args.query_date,
        benchmark_identity=args.benchmark_identity,
        source_label=args.source_label,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
