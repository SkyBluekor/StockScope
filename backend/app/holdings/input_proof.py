from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.input_identity import ANALYSIS_PROOF_VERSION, PROOF_TABLE

from .analysis import (
    DEFAULT_MARKET_STORE_DB,
    INPUT_FINGERPRINT_CONTRACT_VERSION,
    analyze_single_stock,
)
from .catalog import HoldingsCatalog


class HoldingsInputProofError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AnalysisInputProofResult:
    revision_id: str
    market: str
    ticker: str
    market_date: str
    verification_result: str
    stored_fingerprint: str
    current_fingerprint: str
    generation: dict[str, object]
    verified_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision_id": self.revision_id,
            "market": self.market,
            "ticker": self.ticker,
            "market_date": self.market_date,
            "verification_result": self.verification_result,
            "stored_fingerprint": self.stored_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "generation": self.generation,
            "verified_at": self.verified_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_current_analysis_input(
    catalog: HoldingsCatalog,
    monitored_stock_id: str,
    *,
    market_store_db: Path | None = None,
    clock: Callable[[], str] | None = None,
) -> AnalysisInputProofResult:
    """Explicitly recompute one stored revision and persist only its proof.

    The immutable analysis revision is never updated. Provider/network access is
    forbidden by analyze_single_stock; this operation uses already stored EOD data.
    """
    with catalog.connection() as conn:
        proof_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (PROOF_TABLE,),
        ).fetchone()
        if proof_table is None:
            raise HoldingsInputProofError(
                "HOLD_INPUT_PROOF_MIGRATION_REQUIRED",
                "입력 증명 저장 구조가 없습니다. VN-P1-S1 migration을 먼저 실행해야 합니다.",
            )
        row = conn.execute(
            """
            SELECT s.market,s.ticker,d.id AS analysis_day_id,d.market_date,
                   d.current_revision_id,r.input_fingerprint,r.source_versions_json
            FROM monitored_stock s
            JOIN stock_analysis_day d ON d.monitored_stock_id=s.id
            JOIN stock_analysis_revision r ON r.id=d.current_revision_id
            WHERE s.id=? AND d.current_revision_id IS NOT NULL
            ORDER BY d.market_date DESC,d.id DESC
            LIMIT 1
            """,
            (monitored_stock_id,),
        ).fetchone()
    if row is None:
        raise HoldingsInputProofError(
            "HOLD_INPUT_PROOF_ANALYSIS_NOT_FOUND",
            "검증할 저장 분석 결과가 없습니다.",
        )

    market = str(row["market"])
    ticker = str(row["ticker"])
    market_date = str(row["market_date"])
    revision_id = str(row["current_revision_id"])
    stored_fingerprint = str(row["input_fingerprint"])
    try:
        source_versions = json.loads(str(row["source_versions_json"] or "{}"))
    except json.JSONDecodeError:
        source_versions = {}
    stored_contract = (
        str(source_versions.get("fingerprint_contract_version") or "")
        if isinstance(source_versions, dict)
        else ""
    )
    if stored_contract != INPUT_FINGERPRINT_CONTRACT_VERSION:
        raise HoldingsInputProofError(
            "HOLD_INPUT_PROOF_FINGERPRINT_VERSION_UNSUPPORTED",
            "이 분석 revision은 이전 fingerprint 계약으로 생성되어 현재 입력 증명과 직접 비교할 수 없습니다. 새 분석을 실행하세요.",
        )
    current = analyze_single_stock(
        market=market,
        ticker=ticker,
        market_date=market_date,
        market_store_db=Path(market_store_db or DEFAULT_MARKET_STORE_DB),
    )
    generation = current.source_versions.get("input_generation")
    if not isinstance(generation, dict):
        raise HoldingsInputProofError(
            "HOLD_INPUT_PROOF_GENERATION_UNAVAILABLE",
            "Market Store 입력 generation을 확인할 수 없습니다. migration 상태를 확인하세요.",
        )

    verification_result = (
        "MATCH" if current.input_fingerprint == stored_fingerprint else "MISMATCH"
    )
    verified_at = (clock or _now)()
    generation_json = json.dumps(
        generation,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    with catalog.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute(
            "SELECT current_revision_id FROM stock_analysis_day WHERE id=?",
            (str(row["analysis_day_id"]),),
        ).fetchone()
        if latest is None or str(latest["current_revision_id"] or "") != revision_id:
            raise HoldingsInputProofError(
                "HOLD_INPUT_PROOF_REVISION_CHANGED",
                "검증 중 현재 분석 revision이 변경되었습니다. 다시 시도하세요.",
            )
        conn.execute(
            f"""
            INSERT INTO {PROOF_TABLE}(
                revision_id,proof_version,input_fingerprint,generation_json,
                verification_result,current_fingerprint,verified_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(revision_id) DO UPDATE SET
                proof_version=excluded.proof_version,
                input_fingerprint=excluded.input_fingerprint,
                generation_json=excluded.generation_json,
                verification_result=excluded.verification_result,
                current_fingerprint=excluded.current_fingerprint,
                verified_at=excluded.verified_at
            """,
            (
                revision_id,
                ANALYSIS_PROOF_VERSION,
                stored_fingerprint,
                generation_json,
                verification_result,
                current.input_fingerprint,
                verified_at,
            ),
        )
        conn.commit()

    return AnalysisInputProofResult(
        revision_id=revision_id,
        market=market,
        ticker=ticker,
        market_date=market_date,
        verification_result=verification_result,
        stored_fingerprint=stored_fingerprint,
        current_fingerprint=current.input_fingerprint,
        generation=dict(generation),
        verified_at=verified_at,
    )
