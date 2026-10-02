from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any

CONTRACT_VERSION = "VN_NEXT6E_S6A_R3_ASSUMPTION_EVIDENCE_V1"
EXPECTED_DATASET_ID = "MACROCAL-DEV-7c3f6660b3aae03f"
EXPECTED_DATASET_HASH = "7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1"
DATASET_CONTRACT = "VN_NEXT6B_S2_CALIBRATION_DATASET_V1"
FEATURE_CONTRACT = "VN_NEXT6B_S1_MACRO_FEATURE_V1"
SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"
HORIZONS = (1, 5, 10)
FEATURE_IDS = {h: f"delta_bp_{h}obs" for h in HORIZONS}


class AssumptionEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _hash(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _d(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise AssumptionEvidenceError("R3_NONFINITE_VALUE", "Non-finite diagnostic input.")
    return result


def _dt(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _ft(value: float) -> str:
    return format(value, ".15g")


def _features(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {str(x["feature_id"]): dict(x) for x in row["features"]}
    expected = {"rate_level_pct", *FEATURE_IDS.values()}
    if set(result) != expected:
        raise AssumptionEvidenceError("R3_FEATURE_SET_MISMATCH", "Unexpected Development feature set.")
    return result


def _validate_lineage(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    expected_top = {
        "contract_version": DATASET_CONTRACT,
        "dataset_id": EXPECTED_DATASET_ID,
        "dataset_hash": EXPECTED_DATASET_HASH,
        "split_role": "DEVELOPMENT",
    }
    for key, expected in expected_top.items():
        if dataset.get(key) != expected:
            raise AssumptionEvidenceError("R3_DATASET_IDENTITY_MISMATCH", f"{key} mismatch.")

    manifest = dataset.get("manifest") or {}
    expected_manifest = {
        "contract_version": DATASET_CONTRACT,
        "feature_contract_version": FEATURE_CONTRACT,
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "series_id": SERIES_ID,
        "vintage_id": "2023-12-29",
        "observation_start": "2016-01-04",
        "observation_end": "2023-12-29",
        "analysis_row_count": 1999,
        "warmup_count": 10,
        "warmup_required": 10,
        "split_role": "DEVELOPMENT",
        "usage_scope": "REFERENCE_RESEARCH_ONLY",
        "historical_pit_eligible_count": 0,
        "production_decision_approved": False,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise AssumptionEvidenceError("R3_MANIFEST_IDENTITY_MISMATCH", f"manifest.{key} mismatch.")

    rows = list(dataset.get("rows") or [])
    if len(rows) != 1999:
        raise AssumptionEvidenceError("R3_ANALYSIS_ROW_COUNT_MISMATCH", "Expected 1999 Development rows.")

    row_hashes: list[str] = []
    for row in rows:
        feature_payload = {
            "contract_version": row["feature_contract_version"],
            "series_id": row["series_id"],
            "features": row["features"],
        }
        if _hash(feature_payload) != row["feature_set_hash"]:
            raise AssumptionEvidenceError("R3_FEATURE_HASH_MISMATCH", "Feature-set hash mismatch.")
        identity = {
            "split_role": row["split_role"],
            "series_id": row["series_id"],
            "vintage_id": row["vintage_id"],
            "observation_key": row["observation_key"],
            "observation_date": row["observation_date"],
            "normalized_hash": row["normalized_hash"],
            "feature_contract_version": row["feature_contract_version"],
            "feature_set_hash": row["feature_set_hash"],
        }
        row_hash = _hash(identity)
        if row_hash != row["row_hash"]:
            raise AssumptionEvidenceError("R3_ROW_HASH_MISMATCH", "Development row hash mismatch.")
        row_hashes.append(row_hash)
    if _hash({"manifest": manifest, "row_hashes": row_hashes}) != EXPECTED_DATASET_HASH:
        raise AssumptionEvidenceError("R3_DATASET_HASH_MISMATCH", "Canonical dataset hash mismatch.")
    return rows


def _put(target: dict[int, Any], pos: int, value: Any) -> None:
    if pos in target and target[pos] != value:
        raise AssumptionEvidenceError("R3_NATIVE_POSITION_CONFLICT", f"Native position conflict at {pos}.")
    target[pos] = value


def _reconstruct(rows: list[dict[str, Any]]) -> tuple[dict[int, str], dict[int, str], dict[int, Decimal]]:
    refs: dict[int, str] = {}
    dates: dict[int, str] = {}
    levels: dict[int, Decimal] = {}
    for i, row in enumerate(rows):
        fmap = _features(row)
        rate = fmap["rate_level_pct"]
        if rate["status"] != "AVAILABLE":
            raise AssumptionEvidenceError("R3_RATE_LEVEL_UNAVAILABLE", f"rate_level_pct unavailable at {i}.")
        ref, day, level = str(rate["current_observation_ref"]), str(rate["current_observation_date"]), _d(rate["value"])
        if ref != row["normalized_hash"] or day != row["observation_date"]:
            raise AssumptionEvidenceError("R3_CURRENT_IDENTITY_MISMATCH", f"Current feature identity mismatch at {i}.")
        _put(refs, i, ref); _put(dates, i, day); _put(levels, i, level)
        for h, fid in FEATURE_IDS.items():
            f = fmap[fid]
            if f["status"] != "AVAILABLE" or int(f["observation_distance"]) != h:
                raise AssumptionEvidenceError("R3_HORIZON_FEATURE_INVALID", f"{fid} invalid at {i}.")
            if f["current_observation_ref"] != ref or f["current_observation_date"] != day:
                raise AssumptionEvidenceError("R3_HORIZON_CURRENT_IDENTITY_MISMATCH", f"{fid} current identity mismatch.")
            p = i - h
            inferred = level - _d(f["value"]) / Decimal(100)
            _put(refs, p, str(f["baseline_observation_ref"]))
            _put(dates, p, str(f["baseline_observation_date"]))
            _put(levels, p, inferred)
    expected = list(range(-10, len(rows)))
    if sorted(refs) != expected or len(set(refs.values())) != len(refs):
        raise AssumptionEvidenceError("R3_NATIVE_POSITION_INCOMPLETE", "Native positions are incomplete or duplicated.")
    parsed = [date.fromisoformat(dates[p]) for p in expected]
    if any(a >= b for a, b in zip(parsed, parsed[1:])):
        raise AssumptionEvidenceError("R3_NATIVE_DATE_ORDER_INVALID", "Native dates are not strictly increasing.")
    return refs, dates, levels


def _validate_representation(rows: list[dict[str, Any]], levels: dict[int, Decimal]) -> int:
    comparisons = 0
    for i, row in enumerate(rows):
        fmap = _features(row)
        for h, fid in FEATURE_IDS.items():
            actual = _d(fmap[fid]["value"])
            direct = (levels[i] - levels[i - h]) * 100
            telescoped = sum((levels[p] - levels[p - 1]) * 100 for p in range(i - h + 1, i + 1))
            if actual != direct or actual != telescoped:
                raise Assump²È="25Q%M}]!%Q}=IIQ}UQ=5Q%ˆ°€‰­•É¹•°ˆè€‰AIi8ˆ°€‰É¥‘}Á½¥¹Ñ}½Õ¹Ðˆè€ÄÈÔ°€‰­}¸ˆè­}¸°€‰±…}µ…àˆè±…}µ…à°€‰É¡½}É¥Ðˆè}™Ð¡É¡½}É¥Ð¤°€‰½½É‘¥¹…Ñ•}´ˆè´°€‰±…}ÕÑ½™™}0ˆè0°€‰…µµ…}ÍÅÕ…É•ˆè}™Ð¡…µµ„È¤°€‰‘•±Ñ„ˆè}™Ð¡‘•±Ñ„¤°€‰•±±}½ÁÐˆè}™Ð¡•±°¤°€‰‰…¹‘Ý¥‘Ñ¡}ˆˆèˆ°€‰•™™•Ñ¥Ù•}•±°ˆè€È€¨ˆ€´€Ä°€‰É½Õ¹‘¥¹}µ½‘”ˆè€‰I=U9}Q=}9IMQ}Q%M}Q=}Y8ˆ°€‰µ…¹Õ…±}™…±±‰…­}ÕÍ•ˆè…±Í•ô(()‘•˜‰Õ¥±‘}ÈÍ}…ÍÍÕµÁÑ¥½¹}•Ù¥‘•¹”¡‘…Ñ…Í•Ðè‘¥ÑmÍÑÈ°¹åt°€¨°±•…¹}¥Í½±…Ñ¥½¹}•ÉÑ¥™¥•è‰½½°€ô…±Í”¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€É½ÝÌ€ô}Ù…±¥‘…Ñ•}±¥¹•…”¡‘…Ñ…Í•Ð¤ìÉ•™Ì°‘…Ñ•Ì°±•Ù•±Ì€ô}É•½¹ÍÑÉÕÐ¡É½ÝÌ¤ì½µÁ…É¥Í½¹Ì€ô}Ù…±¥‘…Ñ•}É•ÁÉ•Í•¹Ñ…Ñ¥½¸¡É½ÝÌ°±•Ù•±Ì¤(€€€Ù…±Õ•Ì€ô}Í•É¥•Ì¡É½ÝÌ¤ì¸€ô±•¸¡É½ÝÌ¤ì¹}µ¥¸€ô€¡¸€¬€ä¤€¼¼€ÄÀ(€€€Ñ¥”€ôíQUI}%Mm¡tè}Ñ¥•Ì¡Ù…±Õ•Ím¡t¤™½È ¥¸!=I%i=9Mô(€€€©½¥¹Ð€ô±¥ÍÐ¡é¥À ¨¡Ù…±Õ•Ím¡t™½È ¥¸!=I%i=9L¤¤¤ì©½¥¹Ñ}½Õ¹ÑÌ€ô½Õ¹Ñ•È¡©½¥¹Ð¤(€€€¥¹Ñ••É}É¥€ô…±°¡Ø€ôôØ¹Ñ½}¥¹Ñ•É…±}Ù…±Õ” ¤™½ÈÉ½Ü¥¸©½¥¹Ð™½ÈØ¥¸É½Ü¤(€€€ÅÕ…¹Ñ¥é…Ñ¥½¹}½¹™±¥Ð€ô¥¹Ñ••É}É¥…¹…¹ä¡ál‰Õ¹¥ÅÕ•}Ù…±Õ•}½Õ¹Ð‰t€ðál‰½Õ¹Ð‰t™½Èà¥¸Ñ¥”¹Ù…±Õ•Ì ¤¤(€€€É•Õ±…É¥Ñä€ô€‰MMU5AQ%=9}9=Q}AQˆ¥˜ÅÕ…¹Ñ¥é…Ñ¥½¹}½¹™±¥Ð•±Í”€‰U9IM=1Yˆ(€€€Í…±•Ì€ôíQUI}%Mm¡tè}ÁÉ•™¥á}Í…±•Ì¡Ù…±Õ•Ím¡t°¹}µ¥¸¤™½È ¥¸!=I%i=9Mô(€€€‰…¹‘Ý¥‘Ñ €ô}‰…¹‘Ý¥‘Ñ ¡mÙ…±Õ•Ím¡t™½È ¥¸!=I%i=9Mt¤(€€€‘¥…¹½ÍÑ¥Ì€ôì(€€€€€€€€‰Á}•Ù¥‘•¹•}±¥¹•…”ˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ°€‰‘…Ñ…Í•Ñ}¥ˆè‘…Ñ…Í•Ñl‰‘…Ñ…Í•Ñ}¥‰t°€‰‘…Ñ…Í•Ñ}¡…Í ˆè‘…Ñ…Í•Ñl‰‘…Ñ…Í•Ñ}¡…Í ‰t°€‰É½Ý}¡…Í¡}½Õ¹Ðˆè¹ô°(€€€€€€€€‰Å}¹…Ñ¥Ù•}Á½Í¥Ñ¥½¹}½µÁ±•Ñ•¹•ÍÌˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ°€‰¹…Ñ¥Ù•}Á½Í¥Ñ¥½¹}½Õ¹Ðˆè±•¸¡É•™Ì¤°€‰™¥ÉÍÑ}¹…Ñ¥Ù•}Á½Í¥Ñ¥½¸ˆè€´ÄÀ°€‰±…ÍÑ}¹…Ñ¥Ù•}Á½Í¥Ñ¥½¸ˆè¸€´€Ä°€‰ÍÑÉ¥Ñ}‘…Ñ•}½É‘•ÈˆèQÉÕ”°€‰™¥ÉÍÑ}¹…Ñ¥Ù•}‘…Ñ”ˆè‘…Ñ•Íl´ÄÁt°€‰±…ÍÑ}¹…Ñ¥Ù•}‘…Ñ”ˆè‘…Ñ•Ím¸€´€Åuô°(€€€€€€€€‰É}Ý}Ñ½}á}É•ÁÉ•Í•¹Ñ…Ñ¥½¹}¥‘•¹Ñ¥Ñäˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ°€‰½µÁ…É¥Í½¹}½Õ¹Ðˆè½µÁ…É¥Í½¹Ì°€‰•á…Ñ}‘•¥µ…±}•ÅÕ…±¥ÑäˆèQÉÕ•ô°(€€€€€€€€‰Í}©½¥¹Ñ}…±¥¹µ•¹Ðˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ°€‰©½¥¹Ñ}É½Ý}½Õ¹Ðˆè¸°€‰¡½É¥é½¹Ìˆè±¥ÍÐ¡!=I%i=9L¤°€‰…¹‘¥‘…Ñ•}‘½µ…¥¹}­…ÁÁ„ˆè€ˆÄ¼ÄÀˆ°€‰…¹‘¥‘…Ñ•}…¹¡½É}ÍÑ…ÉÐˆè¹}µ¥¸°€‰…¹‘¥‘…Ñ•}…¹¡½É}•¹ˆè¸€´€Ä°€‰Ñ¥µ•±¥¹•}½µÁÉ•ÍÍ•ˆè…±Í•ô°(€€€€€€€€‰Ñ}½¹Ñ¥¹Õ¥Ñå}…Ñ½µ}½µÁ…Ñ¥‰¥±¥Ñäˆèì‰ÍÑ…ÑÕÌˆèÉ•Õ±…É¥Ñä°€‰Ñ¡•½É•µ}É•ÅÕ¥É•µ•¹Ðˆè€‰=9Q%9U=UM})=%9Q}%MQI%	UQ%=8ˆ°€‰É•…Í½¸ˆè€‰I=i9}I=I}QUI}AI=MM}%M}MQI=91e}EU9Q%i}]%Q!}Q%Lˆ¥˜ÅÕ…¹Ñ¥é…Ñ¥½¹}½¹™±¥Ð•±Í”€‰9=}A=M%Q%Y}=9Q%9U%Qe}AQ9}IU1ˆ°€‰©½¥¹Ñ}Õ¹¥ÅÕ•}Ù…±Õ•}½Õ¹Ðˆè±•¸¡©½¥¹Ñ}½Õ¹ÑÌ¤°€‰©½¥¹Ñ}µ…á¥µÕµ}Ñ¥•}µÕ±Ñ¥Á±¥¥Ñäˆèµ…à¡©½¥¹Ñ}½Õ¹ÑÌ¹Ù…±Õ•Ì ¤¤°€‰…±±}½½É‘¥¹…Ñ•Í}½¹}¥¹Ñ••É}‰…Í¥Í}Á½¥¹Ñ}É¥ˆè¥¹Ñ••É}É¥°€‰µ…É¥¹…±ÌˆèÑ¥”°€‰©¥ÑÑ•É}ÕÍ•ˆè…±Í•ô°(€€€€€€€€‰Õ}ÍÑ…Ñ¥½¹…É¥Ñå}½µÁ…Ñ¥‰¥±¥Ñäˆèì‰ÍÑ…ÑÕÌˆè€‰U9IM=1Yˆ°€‰ÍÑÉ¥Ñ}ÍÑ…Ñ¥½¹…É¥Ñå}µ…Ñ¡•µ…Ñ¥…±±å}Ù•É¥™¥•ˆè…±Í”°€‰Á½ÍÑ}¡½}Í•µ•¹Ñ…Ñ¥½¹}ÕÍ•ˆè…±Í”°€‰™¥á•‘}…±•¹‘…É}å•…É}ÍÕµµ…ÉäˆèíQUI}%Mm¡tè}å•…É±ä¡É½ÝÌ°Ù…±Õ•Ím¡t¤™½È ¥¸!=I%i=9Mô°€‰É•…Í½¸ˆè€‰9=}AIAAI=Y}9U5I%}MQQ%=9I%Qe}AQ9}IU1‰ô°(€€€€€€€€‰Ù}ÍÑÉ½¹}µ¥á¥¹}µ½‘•±}ÕÍ”ˆèì‰ÍÑ…ÑÕÌˆè€‰U9IM=1Yˆ°€‰É•ÅÕ¥É•‘}É…Ñ”ˆè€‰…±Á¡…}h¡È¤õ<¡Éxµ„¤°„øÄÔ¼Èˆ°€‰µ¥á¥¹}É…Ñ•}µ…Ñ¡•µ…Ñ¥…±±å}Ù•É¥™¥•ˆè…±Í”°€‰±…}Í•±•Ñ½É}½½É‘¥¹…Ñ•}´ˆè‰…¹‘Ý¥‘Ñ¡l‰½½É‘¥¹…Ñ•}´‰t°€‰É•…Í½¸ˆè€‰%9%Q}M5A1}99=Q}YI%e}IEU%I}MQI=9}5%a%9}IQ‰ô°(€€€€€€€€‰Ý}µ•‘¥…¹}É•Õ±…É¥Ñäˆèì‰ÍÑ…ÑÕÌˆèÉ•Õ±…É¥Ñä°€‰Ñ¡•½É•µ}É•ÅÕ¥É•µ•¹Ðˆè€‰U9%EU}5%9}9}A=M%Q%Y}1=1}9M%Qdˆ°€‰µ…É¥¹…±ÌˆèÑ¥”°€‰Á½ÁÕ±…Ñ¥½¹}Õ¹¥ÅÕ•¹•ÍÍ}±…¥µ•ˆè…±Í”°€‰Á½Í¥Ñ¥Ù•}‘•¹Í¥Ñå}±…¥µ•ˆè…±Í•ô°(€€€€€€€€‰á}Á½Í¥Ñ¥Ù•}µ…‘}é•É½}Í…±”ˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ¥˜…±°¡ál‰é•É½}Í…±•}…¹¡½É}½Õ¹Ð‰t€ôô€À™½Èà¥¸Í…±•Ì¹Ù…±Õ•Ì ¤¤•±Í”€‰MMU5AQ%=9}9=Q}AQˆ°€‰…ÁÁÉ½Ù•‘}…¹‘¥‘…Ñ•}‘½µ…¥¹}½¹±äˆèQÉÕ”°€‰™•…ÑÕÉ•ÌˆèÍ…±•Ì°€‰•ÁÍ¥±½¹}É•ÍÕ•}ÕÍ•ˆè…±Í•ô°(€€€€€€€€‰å}µ…‘}±½…±}É•Õ±…É¥Ñäˆèì‰ÍÑ…ÑÕÌˆèÉ•Õ±…É¥Ñä°€‰Ñ¡•½É•µ}É•ÅÕ¥É•µ•¹Ðˆè€‰A=M%Q%Y}1=1}9M%Qe}Q}5}%9%9}A=%9QLˆ°€‰µ…É¥¹…±ÌˆèÑ¥”°€‰Á½Í¥Ñ¥Ù•}‘•¹Í¥Ñå}±…¥µ•ˆè…±Í•ô°(€€€€€€€€‰ÄÁ}µÕ±Ñ¥Á±¥•É}ÁÉ•ÁÉ½•ÍÍ½É}½µÁÕÑ…‰¥±¥Ñäˆèì‰ÍÑ…ÑÕÌˆè€‰5Q!5Q%11e}YI%%ˆ°€¨©‰…¹‘Ý¥‘Ñ °€‰‘•Ñ•Éµ¥¹¥ÍÑ¥}É•Á±…å}É•ÅÕ¥É•ˆèQÉÕ•ô°(€€€ô(€€€‰±½­•ÉÌ€ô€¡mt¥˜±•…¹}¥Í½±…Ñ¥½¹}•ÉÑ¥™¥••±Í”l‰19}%M=1Q%=9}9=Q}IQ%%‰t¤(€€€™½È­•ä°É•ÅÕ¥É•°½‘”¥¸€ (€€€€€€€€ ‰Ñ}½¹Ñ¥¹Õ¥Ñå}…Ñ½µ}½µÁ…Ñ¥‰¥±¥Ñäˆ°€‰MMU5AQ%=9}AQ}=I}5=1}UMˆ°€‰=9Q%9U%Qe}Q=5}=5AQ%	%1%Qe}9=Q}AQˆ¤°(€€€€€€€€ ‰Õ}ÍÑ…Ñ¥½¹…É¥Ñå}½µÁ…Ñ¥‰¥±¥Ñäˆ°€‰MMU5AQ%=9}AQ}=I}5=1}UMˆ°€‰MQQ%=9I%Qe}=5AQ%	%1%Qe}U9IM=1Yˆ¤°(€€€€€€€€ ‰Ù}ÍÑÉ½¹}µ¥á¥¹}µ½‘•±}ÕÍ”ˆ°€‰MMU5AQ%=9}AQ}=I}5=1}UMˆ°€‰MQI=9}5%a%9}5=1}UM}U9IM=1Yˆ¤°(€€€€€€€€ ‰Ý}µ•‘¥…¹}É•Õ±…É¥Ñäˆ°€‰MMU5AQ%=9}AQ}=I}5=1}UMˆ°€‰5%9}IU1I%Qe}9=Q}AQˆ¤°(€€€€€€€€ ‰á}Á½Í¥Ñ¥Ù•}µ…‘}é•É½}Í…±”ˆ°€‰5Q!5Q%11e}YI%%ˆ°€‰A=M%Q%Y}M1}9=Q}YI%%ˆ¤°(€€€€€€€€ ‰å}µ…‘}±½…±}É•Õ±…É¥Ñäˆ°€‰MMU5AQ%=9}AQ}=I}5=1}UMˆ°€‰5}1=1}IU1I%Qe}9=Q}AQˆ¤°(€€€€¤è(€€€€€€€¥˜‘¥…¹½ÍÑ¥Ím­•åul‰ÍÑ…ÑÕÌ‰t€„ôÉ•ÅÕ¥É•è‰±½­•ÉÌ¹…ÁÁ•¹¡½‘”¤(€€€‰…Í”€ôì(€€€€€€€€‰½¹ÑÉ…Ñ}Ù•ÉÍ¥½¸ˆè=9QIQ}YIM%=8°€‰ÍÑ…”ˆè€‰9aP´ÙµLÙµHÌˆ°€‰ÉÕ¹}­¥¹ˆè€‰19}IIU8ˆ°(€€€€€€€€‰Í½ÕÉ•}‘…Ñ…Í•Ñ}¥ˆè‘…Ñ…Í•Ñl‰‘…Ñ…Í•Ñ}¥‰t°€‰Í½ÕÉ•}‘…Ñ…Í•Ñ}¡…Í ˆè‘…Ñ…Í•Ñl‰‘…Ñ…Í•Ñ}¡…Í ‰t°(€€€€€€€€‰Í½ÕÉ•}ÕÍ…•}Í½Á”ˆè€‰Y1=A59Q}%9AUQ}MMU5AQ%=9}Y%9}=91dˆ°€‰µ•Ñ¡½‘}ÍÑ…Ñ”ˆè€‰5Q!=}AI=%1}I=i8ˆ°(€€€€€€€€‰…¹‘¥‘…Ñ•}‘½µ…¥¸ˆèì‰­…ÁÁ„ˆè€ˆÄ¼ÄÀˆ°€‰¸ˆè¸°€‰¹}µ¥¹}µ•Ñ¡½ˆè¹}µ¥¹ô°€‰‘¥…¹½ÍÑ¥Ìˆè‘¥…¹½ÍÑ¥Ì°(€€€€€€€€‰…ÍÍÕµÁÑ¥½¹}…•ÁÑ…¹”ˆè€‰9=Q}I9Qˆ¥˜‰±½­•ÉÌ•±Í”€‰I9Q}=I}5=1}UMˆ°€‰}„ˆè€‰	1=-ˆ¥˜‰±½­•ÉÌ•±Í”€‰AMLˆ°€‰‰±½­•ÉÌˆè‰±½­•ÉÌ°(€€€€€€€€‰Õ…Éˆèì‰•á•ÕÑ¥½¹}¥¹ÁÕÑ}Í½Á”ˆè€‰aA1%%Q}Y1=A59Q}IQ%Q}=91dˆ°€‰±•…¹}¥Í½±…Ñ¥½¹}•ÉÑ¥™¥•ˆè±•…¹}¥Í½±…Ñ¥½¹}•ÉÑ¥™¥•°€‰‘•Ù•±½Áµ•¹Ñ}…‘•ÅÕ…å}½ÕÑ½µ•}¥¹ÍÁ•Ñ•ˆè…±Í”°€‰Á…ÍÍ¥¹}¹}¥¹ÍÁ•Ñ•ˆè…±Í”°€‰É•½µµ•¹‘•‘}ÍÕÁÁ½ÉÑ}¥¹ÍÁ•Ñ•ˆè…±Í”°€‰¹•ÑÝ½É­}…•ÍÌˆè…±Í”°€‰‘…Ñ…‰…Í•}…•ÍÌˆè…±Í”°€‰ÉÕ¹Ñ¥µ•}ÝÉ¥Ñ•Ìˆè€Áô°(€€€€€€€€‰‘½Ý¹ÍÑÉ•…´ˆèì‰}ˆˆè€‰	1=-ˆ°€‰É•™•É•¹•}…‘•ÅÕ…äˆè€‰U9IM=1Yˆ°€‰µ¥¹¥µÕµ}ÁÉ¥½É}½‰Í•ÉÙ…Ñ¥½¹Ìˆè9½¹”°€‰É•½µµ•¹‘•‘}ÍÕÁÁ½ÉÐˆè9½¹”°€‰É…Ñ•}ÍÁ¥­”ˆè€‰U91%	IQˆ°€‰ØÍ}¡…¹•ˆè…±Í”°€‰ØÑ}É•…Ñ•ˆè…±Í”°€‰•Ù…±Õ…Ñ½É}¥µÁ±•µ•¹Ñ•ˆè…±Í”°€‰ÁÉ½‘ÕÑ¥½¹}¥µÁ…Ðˆè€‰9=9‰ô°(€€€€€€€€‰±¥µ¥Ñ…Ñ¥½¹Ìˆèl‰%9%Q}M5A1}=M}9=Q}AI=Y}MQI%Q}MQQ%=9I%Qdˆ°€‰%9%Q}M5A1}=M}9=Q}YI%e}MQI=9}5%a%9}IQˆ°€‰%9%Q}M5A1}=M}9=Q}MQ	1%M!}A=AU1Q%=9}9M%Qdˆ°€‰EU9Q%iQ%=9}Y%9}%M}UM}%1}1=M}]%Q!=UQ})%QQHˆ°€‰9=}A=MQ}!=}MQQ%=9I%Qe}Q!IM!=1}%9QI=U‰t°(€€€ô(€€€•Ù¥‘•¹•}¡…Í €ô}¡…Í ¡‰…Í”¤(€€€É•ÑÕÉ¸ì¨©‰…Í”°€‰•Ù¥‘•¹•}¥ˆè˜‰HÍMMU5µí•Ù¥‘•¹•}¡…Í¡lèÄÙuôˆ°€‰•Ù¥‘•¹•}¡…Í ˆè•Ù¥‘•¹•}¡…Í¡ô(()‘•˜É•¹‘•É}ÈÍ}…ÍÍÕµÁÑ¥½¹}•Ù¥‘•¹•}Ñ•áÐ¡•Ù¥‘•¹”è‘¥ÑmÍÑÈ°¹åt¤€´øÍÑÈè(€€€±¥¹•Ì€ôl‰9aP´ÙµLÙµHÌ18IIU8ˆ°€ˆôˆ€¨€ÜÈ°˜‰Ù¥‘•¹”€€€€€€€€€€€€€€èí•Ù¥‘•¹•l•Ù¥‘•¹•}¥uôˆ°˜‰…Ñ…Í•Ð€€€€€€€€€€€€€€€èí•Ù¥‘•¹•lÍ½ÕÉ•}‘…Ñ…Í•Ñ}¥uôˆ°˜‰…Ñ…Í•Ð¡…Í €€€€€€€€€€èí•Ù¥‘•¹•lÍ½ÕÉ•}‘…Ñ…Í•Ñ}¡…Í uôˆ°˜‰ÍÍÕµÁÑ¥½¸…•ÁÑ…¹”€èí•Ù¥‘•¹•l…ÍÍÕµÁÑ¥½¹}…•ÁÑ…¹”uôˆ°˜‰µ€€€€€€€€€€€€€€€€€€€èí•Ù¥‘•¹•l}„uôˆ°€ˆ‰t(€€€™½È­•ä°Ù…±Õ”¥¸•Ù¥‘•¹•l‰‘¥…¹½ÍÑ¥Ì‰t¹¥Ñ•µÌ ¤è±¥¹•Ì¹…ÁÁ•¹¡˜‰í­•ä¹ÍÁ±¥Ð |œ°€Ä¥lÁtèðÕôíÙ…±Õ•lÍÑ…ÑÕÌuôˆ¤(€€€±¥¹•Ì€¬ôlˆˆ°€‰	±½­•ÉÌˆ°€ˆ´´´´´´´´ˆ°€©m˜ˆ´íáôˆ™½Èà¥¸•Ù¥‘•¹•l‰‰±½­•ÉÌ‰ut°€ˆˆ°€‰É½é•¸‘½Ý¹ÍÑÉ•…´ÍÑ…Ñ”ˆ°€ˆ´´´´´´´´´´´´´´´´´´´´´´´ˆ°˜‰µ€€€€€€€€€€€€€€€€€€€èí•Ù¥‘•¹•l‘½Ý¹ÍÑÉ•…´ul}ˆuôˆ°˜‰I•™•É•¹”‘•ÅÕ…ä€€€€èí•Ù¥‘•¹•l‘½Ý¹ÍÑÉ•…´ulÉ•™•É•¹•}…‘•ÅÕ…äuôˆ°˜‰XÐÉ•…Ñ•€€€€€€€€€€€€èí•Ù¥‘•¹•l‘½Ý¹ÍÑÉ•…´ulØÑ}É•…Ñ•uôˆ°˜‰AÉ½‘ÕÑ¥½¸¥µÁ…Ð€€€€€èí•Ù¥‘•¹•l‘½Ý¹ÍÑÉ•…´ulÁÉ½‘ÕÑ¥½¹}¥µÁ…Ðuô‰t(€€€É•ÑÕÉ¸€‰q¸ˆ¹©½¥¸¡±¥¹•Ì¤(