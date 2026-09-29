from __future__ import annotations

from app.event_evidence.time import (
    EvidenceTimeQuality,
    TemporalEvidence,
    TEMPORAL_EVIDENCE_CONTRACT_VERSION,
)
from app.macro.models import (
    MACRO_OBSERVATION_CONTRACT_VERSION,
    MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION,
    MACRO_SERIES_CONTRACT_VERSION,
    MacroObservation,
    MacroResearchProtocol,
    MacroSeriesContract,
    fred_dgs10_candidate_contract,
)


MACRO_TEMPORAL_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_TEMPORAL_V1"


__all__ = [
    "EvidenceTimeQuality",
    "TemporalEvidence",
    "TEMPORAL_EVIDENCE_CONTRACT_VERSION",
    "MACRO_TEMPORAL_CONTRACT_VERSION",
    "MACRO_OBSERVATION_CONTRACT_VERSION",
    "MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION",
    "MACRO_SERIES_CONTRACT_VERSION",
    "MacroObservation",
    "MacroResearchProtocol",
    "MacroSeriesContract",
    "fred_dgs10_candidate_contract",
]
