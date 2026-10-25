"""Read-only cap advice archive, authorization and monthly replay verification."""
from pathlib import Path
from hashlib import sha256
import json
from core.strategy_account_ledger import require
from data.strategy_advice_followup_plan_v2 import resolve_policy_binding
from data.strategy_followup_authorization_v1 import review_authorization
from data.strategy_followup_cap_replay_v1 import review_projection
from data.strategy_followup_execution_binding_v1 import validate_execution_shape
from data.strategy_monthly_supplement_capture import restore_reviewed_monthly_history
from data.strategy_followup_price_basis_v1 import review_price_basis


def review_cap_event(*,root,event):
    root=Path(root).resolve();response=event['response'];budget=0
    def read(path):
        nonlocal budget
        path=Path(path)
        if not path.is_absolute():path=root/path
        require(path.resolve().is_relative_to(root/'data/strategy_account') and
                not any(p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&1024)
                        for p in (path,*path.parents)),'FOLLOWUP_CAP_SOURCE_PATH')
        require(path.stat().st_size<=32*1024*1024,'FOLLOWUP_CAP_SOURCE_SIZE')
        raw=path.read_bytes();budget+=len(raw)
        require(budget<=128*1024*1024,'FOLLOWUP_CAP_SOURCE_BUDGET')
        return raw
    def read_reference(path,digest):
        raw=read(path);require(sha256(raw).hexdigest()==digest,'FOLLOWUP_CAP_SOURCE_CHANGED')
        return json.loads(raw)
    def archive(reference):
        path=Path(reference['receipt_path']);receipt=read_reference(path,reference['receipt_sha256'])
        require(path.parent.name==reference['receipt_sha256'],'FOLLOWUP_CAP_ARCHIVE_LOCATION')
        manifest_raw=read(path.parent/'manifest.json');manifest=json.loads(manifest_raw)
        complete=json.loads(read(path.parent/'complete.json'))
        require(sha256(manifest_raw).hexdigest()==reference['manifest_sha256']==complete['manifest_sha256'] and
                manifest['receipt_sha256']==complete['receipt_sha256']==reference['receipt_sha256'] and
                manifest['source_sha256']==receipt['source_sha256'],'FOLLOWUP_CAP_ARCHIVE_INCOMPLETE')
        files={}
        require(0<len(receipt['source_sha256'])<=2000,'FOLLOWUP_CAP_SOURCE_COUNT')
        for name,pin in receipt['source_sha256'].items():
            require(type(pin)is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'FOLLOWUP_CAP_SOURCE_PIN')
            raw=read(path.parent/'sources'/(pin+'.bin'))
            require(sha256(raw).hexdigest()==pin,'FOLLOWUP_CAP_SOURCE_CHANGED');files[name]=raw
        require(receipt['account_id']==event['account_id'] and receipt['account_revision']==event['account_revision']
                and receipt['target_id']==event['target_id'],'FOLLOWUP_CAP_ARCHIVE_BINDING')
        return path,receipt,files
    policy,pin=resolve_policy_binding(event,root=root)
    reference=response['execution_binding'];binding=read_reference(reference['path'],reference['sha256'])
    validate_execution_shape(binding,response)
    require(binding['account_revision']==event['account_revision'] and
            binding['base_target_id']==event['target_id']==reference['base_target_id'] and
            binding['base_decision_id']==reference['base_decision_id'],'FOLLOWUP_CAP_EXECUTION_BINDING')
    require(binding['effective_target_quantities']==response['effective_target_quantities'] and
            binding['policy_id']==policy and binding['signal']['account_id']==event['account_id'],
            'FOLLOWUP_CAP_EXECUTION_SIGNAL')
    path,receipt,files=archive(response['evidence_archive'])
    require(binding['evidence_id']==reference['evidence_id']==response['evidence_archive']['receipt_sha256'] and
            binding['signal']['evidence_archive']==response['evidence_archive'],'FOLLOWUP_CAP_EXECUTION_ARCHIVE')
    proof=json.loads(files[receipt['cap_exit_projection_path']])
    require(sha256(files['cap-exit/release.json']).hexdigest()==pin==receipt['release_sha256']==proof['release_sha256'],
            'FOLLOWUP_CAP_RELEASE_BINDING')
    base_path,base_receipt,base_files=archive(proof['source_archive'])
    require(all(files.get(name)==raw for name,raw in base_files.items()),'FOLLOWUP_CAP_BASE_SOURCE_CHANGED')
    references=event['policy_references'];evidence=None
    for _ in range(8):
        if 'evidence_references' in references:
            evidence=references['evidence_references'];break
        references=references.get('base',{})
    require(evidence is not None,'FOLLOWUP_CAP_BASE_AUTHORIZATION_MISSING')
    review_authorization(root=root,event=event,evidence=evidence,receipt=base_receipt,
                         receipt_path=base_path,read_reference=read_reference)
    inputs=restore_reviewed_monthly_history(receipt=receipt,files=files,
        decision_date=proof['projection']['state']['decision_date'])
    require(inputs['base_target']['origin_reference']==event['target_id'],'FOLLOWUP_CAP_INPUT_TARGET')
    replay=review_projection(proof,inputs,account_id=event['account_id'],target_id=event['target_id'])
    require(replay['effective_target_quantities']==response['effective_target_quantities'],
            'FOLLOWUP_CAP_ADVICE_TARGET_CHANGED')
    price_basis=review_price_basis(json.loads(files[receipt['normalized_inputs_path']]),files)
    return dict(status='CAP_ARCHIVE_AUTHORIZATION_AND_REPLAY_CHECKED',policy_id=policy,
        policy_release_sha256=pin,price_basis=price_basis,replay=replay,
        capture_admitted=False,account_writes=False,network_calls=0)
