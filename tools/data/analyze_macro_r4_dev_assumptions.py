from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BACKEND=ROOT/'backend'
for p in (ROOT,BACKEND):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
from app.macro.r4_contract import build_design_manifest
from app.macro.r4_diagnostic import build_dev_diagnostic
from app.macro.r4_gate import build_gate_assessment

def load(path:Path):
    with path.open('r',encoding='utf-8') as f: return json.load(f)
def main()->int:
    p=argparse.ArgumentParser(description='NEXT-6E-S6A-R4 explicit Development-only diagnostic and gate assessment')
    p.add_argument('--development-artifact',required=True,type=Path)
    p.add_argument('--input-allowlist-id',required=True)
    p.add_argument('--isolation-audit-id',required=True)
    p.add_argument('--certify-clean-isolation',action='store_true')
    p.add_argument('--model-use-dossier',type=Path)
    p.add_argument('--theorem-review-dossier',type=Path)
    p.add_argument('--format',choices=('summary','json'),default='summary')
    a=p.parse_args(); raw=a.development_artifact.read_bytes(); dataset=json.loads(raw.decode('utf-8'))
    design=build_design_manifest(); diagnostic=build_dev_diagnostic(dataset,transport_digest=hashlib.sha256(raw).hexdigest(),design_hash=design['design_hash'],input_allowlist_id=a.input_allowlist_id,isolation_audit_id=a.isolation_audit_id,clean_isolation_certified=a.certify_clean_isolation)
    assessment=build_gate_assessment(design=design,diagnostic=diagnostic,model_use=load(a.model_use_dossier) if a.model_use_dossier else None,theorem_review=load(a.theorem_review_dossier) if a.theorem_review_dossier else None)
    if a.format=='json': print(json.dumps({'design':design,'diagnostic':diagnostic,'assessment':assessment},ensure_ascii=False,sort_keys=True))
    else:
        print('NEXT-6E-S6A-R4'); print('Diagnostic:',diagnostic['semantic_payload_hash']); print('G-A:',assessment['ga_status'])
        for g in assessment['gates']:
            print(f"{g['gate_id']}: {g['status']}" + (f" ({','.join(g['reason_codes'])})" if g['reason_codes'] else ''))
    return 0
if __name__=='__main__': raise SystemExit(main())
