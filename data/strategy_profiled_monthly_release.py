"""Read-only profile assignment over independently validated monthly publication.

The caller must pin this wrapper document externally. No approval, activation or
selection occurs here. Original publication dates, identity and pins are checked
by the existing resolver; a profile assignment never changes their contents.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import require
from data.strategy_account_runtime_archive import _document
from data.strategy_account_monthly_release import resolve_monthly_runtime as resolve_original
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from scripts.register_quantity_v2_paper_protocol import safe_path

def resolve_monthly_runtime(*,root,registry_path,registry_sha256,clock,account_state=None):
    root=Path(root).resolve();raw=safe_path(root,registry_path).read_bytes()
    require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==registry_sha256,'PROFILE_REGISTRY_CHANGED')
    doc=_document(raw)
    if doc.get('schema')=='REAL_STRATEGY_MONTHLY_RELEASES_V1':
        return resolve_original(root=root,registry_path=registry_path,registry_sha256=registry_sha256,clock=clock,account_state=account_state)
    require(set(doc)=={'schema','original_registry','profiles'} and doc['schema']=='PROFILED_MONTHLY_RELEASES_V1','PROFILE_REGISTRY_FIELDS')
    ref=doc['original_registry'];require(set(ref)=={'path','sha256'},'PROFILE_BASE_REFERENCE')
    base=resolve_original(root=root,registry_path=ref['path'],registry_sha256=ref['sha256'],clock=clock,account_state=account_state)
    rows=doc['profiles'];require(type(rows)is list and len(rows)<=100 and all(type(r)is dict and set(r)=={'target_month','selector_profile'} for r in rows),'PROFILE_ASSIGNMENTS_INVALID')
    require(len({r['target_month'] for r in rows})==len(rows),'PROFILE_MONTH_DUPLICATE')
    matches=[r for r in rows if r['target_month']==base['target_month']]
    require(len(matches)==1 and matches[0]['selector_profile']==PROFILE_ID,'EXPLICIT_CURRENT_PROFILE_REQUIRED')
    require(RUNTIME_PATHS<=set(base['runtime_pins']),'PROFILE_RUNTIME_PINS_REQUIRED')
    for name in RUNTIME_PATHS:
        digest=base['runtime_pins'][name]
        require(sha256(safe_path(root,name).read_bytes()).hexdigest()==digest and sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()==digest,'PROFILE_SOURCE_CHANGED')
    return dict(deepcopy(base),schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID)
