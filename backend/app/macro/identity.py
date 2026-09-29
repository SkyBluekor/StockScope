from __future__ import annotations

import hashlib
import json
from typing import Any

from app.macro.errors import MacroContractError


MACRO_IDENTITY_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_IDENTITY_V1"


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MacroContractError(
            "MACRO_CANONICAL_JSON_INVALID",
            "Macro payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
        ) from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def observation_key(
    *,
    series_id: str,
    native_observation_id: str,
    observation_date: str,
) -> str:
    return content_hash(
        {
            "contract_version": MACRO_IDENTITY_CONTRACT_VERSION,
            "series_id": series_id,
            "native_observation_id": native_observation_id,
            "observation_date": observation_date,
        }
    )
