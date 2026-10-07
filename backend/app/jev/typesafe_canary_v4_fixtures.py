from __future__ import annotations

# Synthetic-only V4 Canary fixtures.
#
# Provider fixtures intentionally model residual semantic questions that are not
# currently proven to be production-reachable.  Production-reachable baseline
# rows remain local-only so the Canary cannot manufacture Jev utility.

FIXTURE_SPECS: list[dict] = [
    {
        "fixture_id": "v4-s01",
        "partition": "selection",
        "failure_mode": "DIRECT_CONTRADICTION",
        "semantic_scenario_id": "SEL_SUPPORT_DIRECT_LOSS",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": True,
        "strategy_intent": (
            "This continuation setup requires both directional structure and "
            "support integrity to remain materially intact."
        ),
        "definitions": {
            "directional_core": (
                "Directional structure means the broader directional condition "
                "required by the strategy remains intact."
            ),
            "support_floor": (
                "Support integrity means the strategy's required support "
                "structure has not been materially lost."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["directional_core", "support_floor"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["directional_core"],
                "stance": "SUPPORTS",
                "text": "the broader directional structure remains intact",
            },
            {
                "concept_refs": ["support_floor"],
                "stance": "UNRESOLVED",
                "text": "the supplied support meaning explicitly says the required support structure has been lost",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-s02",
        "partition": "selection",
        "failure_mode": "ALLOWED_EXCEPTION",
        "semantic_scenario_id": "SEL_ALLOWED_PULLBACK_SOFTNESS",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": False,
        "strategy_intent": (
            "A mild short-term pullback is allowed when the primary trend "
            "remains intact."
        ),
        "definitions": {
            "primary_trend": (
                "Primary trend means the broader trend condition that must "
                "remain intact for the exception to be allowed."
            ),
            "short_term_softness": (
                "Short-term softness means a temporary pullback that is not by "
                "itself a failure of the broader setup."
            ),
        },
        "relation": {
            "kind": "ALLOWS_IF",
            "members": ["short_term_softness"],
            "guards": ["primary_trend"],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["short_term_softness"],
                "stance": "UNRESOLVED",
                "text": "short-term momentum is mildly soft during an ordinary pullback",
            },
            {
                "concept_refs": ["primary_trend"],
                "stance": "SUPPORTS",
                "text": "the primary trend remains intact",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-s03",
        "partition": "selection",
        "failure_mode": "WEAK_SEMANTIC_PHRASING",
        "semantic_scenario_id": "SEL_STRUCTURE_DEGREE_WORDING",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": False,
        "expected_q1_gold": None,
        "strategy_intent": (
            "The setup requires structure quality to remain materially "
            "supportive rather than clearly deteriorated."
        ),
        "definitions": {
            "structure_quality": (
                "Structure quality means the supplied condition meanings still "
                "support the strategy's required structural context."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["structure_quality"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["structure_quality"],
                "stance": "UNRESOLVED",
                "text": "structure is somewhat weaker than before but remains partly supportive",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-s04",
        "partition": "selection",
        "failure_mode": "Q1_Q2_ISOLATION",
        "semantic_scenario_id": "SEL_Q1_Q2_ISOLATION_CONTINUATION",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": False,
        "strategy_intent": (
            "The continuation setup remains compatible with a brief pause when "
            "the continuation core is intact and participation remains adequate."
        ),
        "definitions": {
            "continuation_core": (
                "Continuation core means the directional continuation structure "
                "required by the strategy remains intact."
            ),
            "participation_support": (
                "Participation support means participation remains sufficient "
                "for the authored continuation relationship."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["continuation_core", "participation_support"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["continuation_core"],
                "stance": "SUPPORTS",
                "text": "the continuation structure remains intact during a brief pause",
            },
            {
                "concept_refs": ["participation_support"],
                "stance": "UNRESOLVED",
                "text": "participation is quieter than the prior session but remains adequate for continuation",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
        "isolation_family_id": "SEL-Q2",
    },
    {
        "fixture_id": "v4-s05",
        "partition": "selection",
        "failure_mode": "Q1_Q2_ISOLATION",
        "semantic_scenario_id": "SEL_Q1_Q2_ISOLATION_CONTINUATION",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": False,
        "strategy_intent": (
            "The continuation setup remains compatible with a brief pause when "
            "the continuation core is intact and participation remains adequate."
        ),
        "definitions": {
            "continuation_core": (
                "Continuation core means the directional continuation structure "
                "required by the strategy remains intact."
            ),
            "participation_support": (
                "Participation support means participation remains sufficient "
                "for the authored continuation relationship."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["continuation_core", "participation_support"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["continuation_core"],
                "stance": "SUPPORTS",
                "text": "the continuation structure remains intact during a brief pause",
            },
            {
                "concept_refs": ["participation_support"],
                "stance": "UNRESOLVED",
                "text": "participation is quieter than the prior session but remains adequate for continuation",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_B",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
        "isolation_family_id": "SEL-Q2",
    },
    {
        "fixture_id": "v4-s06",
        "partition": "selection",
        "failure_mode": "LOCAL_DETERMINISTIC_CONFLICT",
        "semantic_scenario_id": "SEL_LOCAL_SUPPORT_CONFLICT",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "Support integrity is a hard requirement.",
        "definitions": {
            "local_support": "Local support must remain intact.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_support"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_support"],
                "stance": "CONTRADICTS",
                "text": "the required support structure is explicitly broken",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "LOCAL_CONFLICT",
    },
    {
        "fixture_id": "v4-s07",
        "partition": "selection",
        "failure_mode": "LOCAL_MISSING",
        "semantic_scenario_id": "SEL_LOCAL_REQUIRED_BINDING_MISSING",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "Both local trend and local strength are required.",
        "definitions": {
            "local_strength": "Local relative strength must remain supportive.",
            "local_trend": "Local trend structure must remain supportive.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_trend", "local_strength"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_trend"],
                "stance": "SUPPORTS",
                "text": "local trend remains supportive",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "LOCAL_INCOMPLETE",
    },
    {
        "fixture_id": "v4-s08",
        "partition": "selection",
        "failure_mode": "LOCAL_AMBIGUOUS",
        "semantic_scenario_id": "SEL_LOCAL_SAME_CONCEPT_AMBIGUOUS",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "The local support concept must have one coherent meaning.",
        "definitions": {
            "local_support_state": "Local support state describes whether support remains intact.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_support_state"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_support_state"],
                "stance": "SUPPORTS",
                "text": "one authored condition says support remains intact",
            },
            {
                "concept_refs": ["local_support_state"],
                "stance": "CONTRADICTS",
                "text": "another authored condition says the same support has failed",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "LOCAL_AMBIGUOUS",
    },
    {
        "fixture_id": "v4-s09",
        "partition": "selection",
        "failure_mode": "PRODUCTION_PASS_BASELINE",
        "semantic_scenario_id": "SEL_PRODUCTION_BASELINE_MATCH",
        "reachability": "PRODUCTION_REACHABLE",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": (
            "The production-style baseline requires trend structure and "
            "relative strength to remain supportive."
        ),
        "definitions": {
            "relative_strength": "Relative strength remains supportive versus the comparison context.",
            "trend_structure": "Trend structure remains directionally intact.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["trend_structure", "relative_strength"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["trend_structure"],
                "stance": "SUPPORTS",
                "text": "trend structure remains intact",
            },
            {
                "concept_refs": ["relative_strength"],
                "stance": "SUPPORTS",
                "text": "relative strength remains supportive",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_A",
        "expected_local_status": "LOCAL_MATCH",
    },
    {
        "fixture_id": "v4-v01",
        "partition": "validation",
        "failure_mode": "REQUIRED_CONDITION_COLLAPSE",
        "semantic_scenario_id": "VAL_RECOVERY_SUPPORT_COLLAPSE",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": True,
        "strategy_intent": (
            "A recovery setup requires both recovery structure and its support "
            "base to remain intact."
        ),
        "definitions": {
            "recovery_base": (
                "Recovery base means the support structure needed for recovery "
                "has not materially failed."
            ),
            "recovery_structure": (
                "Recovery structure means stabilization and improvement after "
                "prior weakness."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["recovery_structure", "recovery_base"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["recovery_structure"],
                "stance": "SUPPORTS",
                "text": "recovery structure is still improving",
            },
            {
                "concept_refs": ["recovery_base"],
                "stance": "UNRESOLVED",
                "text": "the supplied support meaning says the recovery base has materially failed",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-v02",
        "partition": "validation",
        "failure_mode": "NEGATIVE_TRAP",
        "semantic_scenario_id": "VAL_RANGE_NO_BREAKOUT_TRAP",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": False,
        "strategy_intent": (
            "This range setup requires bounded range structure and does not "
            "require a directional breakout."
        ),
        "definitions": {
            "bounded_range": (
                "Bounded range means price behavior remains contained without "
                "requiring a directional breakout."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["bounded_range"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["bounded_range"],
                "stance": "UNRESOLVED",
                "text": "the market remains contained inside the range and no breakout has been confirmed",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-v03",
        "partition": "validation",
        "failure_mode": "NEAR_BOUNDARY_AMBIGUITY",
        "semantic_scenario_id": "VAL_MOMENTUM_BOUNDARY_WORDING",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": False,
        "expected_q1_gold": None,
        "strategy_intent": (
            "Momentum persistence must remain materially supportive, while "
            "minor fading can be tolerated."
        ),
        "definitions": {
            "momentum_persistence": (
                "Momentum persistence means directional continuation remains "
                "materially supportive rather than clearly exhausted."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["momentum_persistence"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["momentum_persistence"],
                "stance": "UNRESOLVED",
                "text": "momentum has faded to the edge of what could still be considered supportive",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
    },
    {
        "fixture_id": "v4-v04",
        "partition": "validation",
        "failure_mode": "COMPOSITIONAL_CONFLICT",
        "semantic_scenario_id": "VAL_TREND_PARTICIPATION_COMPOSITION",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": True,
        "strategy_intent": (
            "The setup requires both directional structure and participation "
            "support; neither requirement is optional."
        ),
        "definitions": {
            "participation_quality": (
                "Participation quality means participation remains supportive "
                "of the authored setup."
            ),
            "trend_quality": (
                "Trend quality means directional structure remains materially "
                "supportive."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["trend_quality", "participation_quality"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["trend_quality"],
                "stance": "WEAKENS",
                "text": "directional structure has weakened enough that its support is doubtful",
            },
            {
                "concept_refs": ["participation_quality"],
                "stance": "WEAKENS",
                "text": "participation is also fading rather than supporting continuation",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
        "isolation_family_id": "VAL-Q2",
    },
    {
        "fixture_id": "v4-v05",
        "partition": "validation",
        "failure_mode": "COMPOSITIONAL_CONFLICT",
        "semantic_scenario_id": "VAL_TREND_PARTICIPATION_COMPOSITION",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": True,
        "strategy_intent": (
            "The setup requires both directional structure and participation "
            "support; neither requirement is optional."
        ),
        "definitions": {
            "participation_quality": (
                "Participation quality means participation remains supportive "
                "of the authored setup."
            ),
            "trend_quality": (
                "Trend quality means directional structure remains materially "
                "supportive."
            ),
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["trend_quality", "participation_quality"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["trend_quality"],
                "stance": "WEAKENS",
                "text": "directional structure has weakened enough that its support is doubtful",
            },
            {
                "concept_refs": ["participation_quality"],
                "stance": "WEAKENS",
                "text": "participation is also fading rather than supporting continuation",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_D",
        "expected_local_status": "RESIDUAL_SEMANTIC_REVIEW",
        "isolation_family_id": "VAL-Q2",
    },
    {
        "fixture_id": "v4-v06",
        "partition": "validation",
        "failure_mode": "LOCAL_DETERMINISTIC_CONFLICT",
        "semantic_scenario_id": "VAL_LOCAL_COMPRESSION_CONFLICT",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "Compression is a hard local requirement.",
        "definitions": {
            "local_compression": "Local compression must remain present.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_compression"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_compression"],
                "stance": "CONTRADICTS",
                "text": "volatility is explicitly expanding instead of remaining compressed",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "LOCAL_CONFLICT",
    },
    {
        "fixture_id": "v4-v07",
        "partition": "validation",
        "failure_mode": "LOCAL_MISSING",
        "semantic_scenario_id": "VAL_LOCAL_RECOVERY_BINDING_MISSING",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "Both recovery and support bindings are required locally.",
        "definitions": {
            "local_recovery": "Local recovery structure must remain present.",
            "local_recovery_support": "Local recovery support must remain intact.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_recovery", "local_recovery_support"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_recovery"],
                "stance": "SUPPORTS",
                "text": "recovery structure is present",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "LOCAL_INCOMPLETE",
    },
    {
        "fixture_id": "v4-v08",
        "partition": "validation",
        "failure_mode": "LOCAL_AMBIGUOUS",
        "semantic_scenario_id": "VAL_LOCAL_PARTICIPATION_AMBIGUOUS",
        "reachability": "ROBUSTNESS_ONLY",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": "The local participation concept must be internally coherent.",
        "definitions": {
            "local_participation": "Local participation describes whether participation is supportive.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["local_participation"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["local_participation"],
                "stance": "SUPPORTS",
                "text": "one authored condition says participation is supportive",
            },
            {
                "concept_refs": ["local_participation"],
                "stance": "CONTRADICTS",
                "text": "another authored condition says participation has failed",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "LOCAL_AMBIGUOUS",
    },
    {
        "fixture_id": "v4-v09",
        "partition": "validation",
        "failure_mode": "PRODUCTION_PASS_BASELINE",
        "semantic_scenario_id": "VAL_PRODUCTION_BASELINE_MATCH",
        "reachability": "PRODUCTION_REACHABLE",
        "hard_expectation": True,
        "expected_q1_gold": None,
        "strategy_intent": (
            "The production-style compression baseline requires compression "
            "and directional structure to remain supportive."
        ),
        "definitions": {
            "compression": "Compression remains present and bounded.",
            "directional_structure": "Directional structure remains intact.",
        },
        "relation": {
            "kind": "REQUIRES_ALL",
            "members": ["compression", "directional_structure"],
            "guards": [],
            "materiality": "HARD",
        },
        "meanings": [
            {
                "concept_refs": ["compression"],
                "stance": "SUPPORTS",
                "text": "compression remains present",
            },
            {
                "concept_refs": ["directional_structure"],
                "stance": "SUPPORTS",
                "text": "directional structure remains intact",
            },
        ],
        "q2_variant": "ENTRY_REFERENCE_C",
        "expected_local_status": "LOCAL_MATCH",
    },
]
