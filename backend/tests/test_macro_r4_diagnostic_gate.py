from __future__ import annotations
import hashlib, json
from pathlib import Path
import pytest
from app.macro.r4_contract import build_design_manifest
from app.macro.r4_diagnostic import build_dev_diagnostic, validate_lineage, R4DiagnosticError
from app.macro.r4_gate import build_gate_assessment

DEV=Path('/mnt/data/DEV-7c3f6660b3aae03f.json')

@pytest.fixture(scope='module')
def dataset():
    if not DEV.is_file(): pytest.skip('exact frozen DEV fixture is only present in the authorized local execution context')
    return json.loads(DEV.read_text(encoding='utf-8'))

@pytest.fixture(scope='module')
def diagnostic(dataset):
    raw=DEV.read_bytes(); design=build_design_manifest()
    return build_dev_diagnostic(dataset,transport_digest=hashlib.sha256(raw).hexdigest(),design_hash=design['design_hash'],input_allowlist_id='ALLOW-EXPLICIT-DEV-ONLY',isolation_audit_id='ISO-SYNTHETIC-TEST',clean_isolation_certified=True)


def test_uncertified_context_fails_before_any_source_use():
    with pytest.raises(R4DiagnosticError) as e:
        build_dev_diagnostic({},transport_digest='x',design_hash=build_design_manifest()['design_hash'],input_allowlist_id='ALLOW-1',isolation_audit_id='ISO-1',clean_isolation_certified=False)
    assert e.value.code=='ISOLATION_NOT_CERTIFIED'


def test_lineage_wrong_dataset_id_fails_closed_without_lookup():
    with pytest.raises(R4DiagnosticError) as e:
        validate_lineage({'dataset_id':'OTHER','dataset_hash':'x'})
    assert e.value.code=='LINEAGE_MISMATCH'


def test_exact_dev_diagnostic_reproduces_structure_and_legacy_profile(diagnostic):
    diag=diagnostic
    assert diag['representation']['n']==1999
    assert diag['domain']['lower_bound']==200
    assert diag['diagnostics']['representation_checks']==['EXACT_COMPARISONS:5997']
    assert all(x['off_grid_count']==0 for x in diag['diagnostics']['lattice_counts'])
    legacy=diag['diagnostics']['legacy_r2_profile_audit']
    assert legacy['coordinate_m']==[1,5,21]
    assert legacy['lag_cutoff_L']==10
    assert legacy['bandwidth_b']==22
    assert legacy['effective_ell']==43
    assert legacy['canonical_reference_match'] is True
    assert legacy['historical_record_match'] is False
    assert legacy['historical_variant_reproduced'] is True
    assert legacy['selector_profile']['k_n']==5
    assert legacy['selector_profile']['lag_max']==50
    assert legacy['historical_natural_log_selector']['k_n']==8
    assert legacy['historical_natural_log_selector']['lag_max']==53
    assert legacy['historical_natural_log_selector']['coordinate_m']==[1,5,10]
    assert legacy['provenance_resolution']['classification']=='REFERENCE_SPEC_TRANSCRIPTION_ERROR_LOG_BASE'
    assert 'LEGACY_R2_CANONICAL_MISMATCH' not in diag['failure_codes']
    assert diag['diagnostics']['new_calibration_contract']['symbolic_contract_verified'] is True
    assert diag['diagnostics']['new_calibration_contract']['stochastic_computation_performed'] is False


def test_missing_approvals_leave_ga_blocked(diagnostic):
    design=build_design_manifest(); diag=diagnostic
    a=build_gate_assessment(design=design,diagnostic=diag,model_use=None,theorem_review=None)
    assert a['ga_status']=='BLOCKED'
    states={g['gate_id']:g['status'] for g in a['gates']}
    assert states['A10']=='PASS' and states['A5']=='UNRESOLVED' and states['A6']=='UNRESOLVED' and states['G1']=='BLOCKED'
    assert a['downstream_execution_authorized'] is False
