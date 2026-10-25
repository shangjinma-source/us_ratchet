"""Read-only profiled receipt wrapping fully replayed original data readiness."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import require
from data.strategy_account_ready_release import validate_ready_release as validate_original
from data.strategy_account_runtime_archive import _document
from data.strategy_profiled_runtime_archive import require_archived_configuration
from data.strategy_profiled_monthly_release import resolve_monthly_runtime
from scripts.register_quantity_v2_paper_protocol import safe_path

PROFILE_ADMISSION_SOURCES={'data/strategy_profiled_ready_release.py','data/strategy_profiled_release_activation.py'}

def validate_ready_release(*,root,receipt_path,receipt_sha256,account_state,clock=None):
    root=Path(root).resolve();clock=clock or (lambda:datetime.now(timezone.utc))
    def read(ref):
        require(type(ref)is dict and set(ref)=={'path','sha256'},'PROFILE_RECEIPT_REFERENCE')
        raw=safe_path(root,ref['path']).read_bytes()
        require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==ref['sha256'],'PROFILE_RECEIPT_CHANGED')
        return _document(raw)
    receipt=read(dict(path=receipt_path,sha256=receipt_sha256))
    require(set(receipt)=={'schema','status','base_ready','registry','archive','runtime'} and
            receipt['schema']=='PROFILED_READY_RELEASE_V1' and receipt['status']=='READY_FOR_REVIEW_NOT_ACTIVATED','PROFILE_READY_FIELDS')
    read(receipt['base_ready'])
    base=validate_original(root=root,receipt_path=receipt['base_ready']['path'],receipt_sha256=receipt['base_ready']['sha256'],account_state=account_state,clock=clock)
    registry=read(receipt['registry']);archive=read(receipt['archive']);runtime=read(receipt['runtime'])
    require(registry['original_registry']==dict(path=base['registry_path'],sha256=base['registry_sha256']),'PROFILE_BASE_READY_REGISTRY_MISMATCH')
    config=resolve_monthly_runtime(root=root,registry_path=receipt['registry']['path'],registry_sha256=receipt['registry']['sha256'],clock=clock,account_state=account_state)
    original=deepcopy(config);original['schema']='REAL_STRATEGY_RUNTIME_V1';original.pop('selector_profile')
    require(original==base['configuration'] and config==runtime,'PROFILE_READY_RUNTIME_MISMATCH')
    for name in PROFILE_ADMISSION_SOURCES:
        digest=config['runtime_pins'].get(name)
        require(digest and sha256(safe_path(root,name).read_bytes()).hexdigest()==digest and sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()==digest,'PROFILE_ADMISSION_SOURCE_CHANGED')
    require_archived_configuration(root=root,archive_path=receipt['archive']['path'],archive_sha256=receipt['archive']['sha256'],configuration=config)
    return dict(configuration=config,receipt=receipt,registry_path=receipt['registry']['path'],registry_sha256=receipt['registry']['sha256'],archive_path=receipt['archive']['path'],archive_sha256=receipt['archive']['sha256'],account_id=base['account_id'],account_revision=base['account_revision'])
