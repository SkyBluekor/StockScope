from __future__ import annotations
from fractions import Fraction
import pytest
from app.macro.r4_contract import build_design_manifest, validate_model_use_dossier, validate_theorem_review, MODEL_USE_SCHEMA_ID, METHOD_ID
from app.macro.r4_lattice import median_set, midpoint_median, raw_mad, median_outer_interval, mad_outer_interval, POS_INF, NEG_INF


def test_design_manifest_is_deterministic():
    a=build_design_manifest(); b=build_design_manifest()
    assert a==b and len(a['design_hash'])==64
    assert a['domain']=={'contract_id':'R2A_CANDIDATE_DOMAIN_V1','kappa_num':1,'kappa_den':10}


def test_midpoint_median_matches_odd_even_and_ties():
    assert midpoint_median([Fraction(1),Fraction(2),Fraction(3)])==2
    assert midpoint_median([Fraction(1),Fraction(2),Fraction(3),Fraction(4)])==Fraction(5,2)
    assert median_set([Fraction(0),Fraction(0),Fraction(1),Fraction(1)])==(Fraction(0),Fraction(1))
    assert midpoint_median([Fraction(0),Fraction(0),Fraction(1),Fraction(1)])==Fraction(1,2)


def test_raw_mad_keeps_midpoint_center():
    assert raw_mad([Fraction(0),Fraction(0),Fraction(2),Fraction(2)])==1


def test_median_outer_interval_preserves_unobserved_tails():
    values=[Fraction(0),Fraction(1),Fraction(2),Fraction(3)]
    lo,hi=median_outer_interval(values,Fraction(1,2))
    assert lo==NEG_INF and hi==POS_INF


def test_mad_outer_interval_propagates_center_uncertainty():
    values=[Fraction(0),Fraction(0),Fraction(2),Fraction(2)]
    lo,hi=mad_outer_interval(values,Fraction(1,10))
    assert lo['num']>=0
    assert 'kind' in hi or hi['num']>=0


def test_missing_dossiers_fail_closed():
    d=build_design_manifest()
    ms, reasons, mh=validate_model_use_dossier(None,diagnostic_hash='a'*64,source_scope_hash='b'*64)
    ts, treasons, th=validate_theorem_review(None,design_hash=d['design_hash'])
    assert ms=='UNRESOLVED' and 'MODEL_USE_DOSSIER_MISSING' in reasons and mh is None
    assert ts=='BLOCKED' and 'THEOREM_REVIEW_DOSSIER_MISSING' in treasons and th is None


def test_closed_model_use_schema_rejects_unknown_field():
    d={
      'schema_id':MODEL_USE_SCHEMA_ID,'method_id':METHOD_ID,'diagnostic_hash':'a'*64,'source_scope_hash':'b'*64,
      'stationarity':{},'dependence':{},'finite_sample_proof_claim':False,'owner_identity':'o','reviewer_identity':'r',
      'authority_reference':'a','approval_reference':'p','approved_scope':'s','validity_rule':'v','revocation_rule':'x','status':'MODEL_USE_ACCEPTED','extra':1
    }
    with pytest.raises(Exception): validate_model_use_dossier(d,diagnostic_hash='a'*64,source_scope_hash='b'*64)


def test_model_use_requires_real_identity_and_nested_evidence():
    payload={
      'schema_id':MODEL_USE_SCHEMA_ID,'method_id':METHOD_ID,'diagnostic_hash':'a'*64,'source_scope_hash':'b'*64,
      'stationarity':{'class':'STRICT','rationale':'scoped working model','evidence_refs':['diag:1'],'contradictions':[],'dispositions':[],'decision':'ACCEPTED_FOR_MODEL_USE'},
      'dependence':{'class':'ALPHA_MIXING','rate':'exists a>15/2','rationale':'scoped working model','evidence_refs':['diag:2'],'contradictions':[],'dispositions':[],'nondegenerate_root_condition':'reviewed','quantile_continuity_review':'reviewed','decision':'ACCEPTED_FOR_MODEL_USE'},
      'finite_sample_proof_claim':False,'owner_identity':'','reviewer_identity':'','authority_reference':'','approval_reference':'',
      'approved_scope':'R4 DEV scope','validity_rule':'until revoked','revocation_rule':'on contradiction','status':'MODEL_USE_ACCEPTED'
    }
    status,reasons,_=validate_model_use_dossier(payload,diagnostic_hash='a'*64,source_scope_hash='b'*64)
    assert status=='UNRESOLVED'
    assert 'OWNER_IDENTITY_MISSING' in reasons
    assert 'REVIEWER_IDENTITY_MISSING' in reasons


def test_theorem_review_requires_named_reviewer_and_approval_reference():
    design=build_design_manifest()
    payload={
      'schema_id':'NEXT6E_S6A_R4_THEOREM_REVIEW_V1','method_id':METHOD_ID,'design_hash':design['design_hash'],
      'proof_units':{'D1':'APPROVED','D2':'APPROVED','D3':'APPROVED','D4':'APPROVED'},
      'reviewer_identity':'','approval_reference':'','unresolved_objections':[],'status':'APPROVED'
    }
    status,reasons,_=validate_theorem_review(payload,design_hash=design['design_hash'])
    assert status=='BLOCKED'
    assert 'THEOREM_REVIEWER_MISSING' in reasons
    assert 'THEOREM_APPROVAL_REFERENCE_MISSING' in reasons
