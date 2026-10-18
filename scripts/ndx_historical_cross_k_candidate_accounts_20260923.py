"""Bounded accounts for independently audited historical fits; never refits/control runs."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_historical_cross_k_account_arguments_research as binding
from scripts import ndx_historical_cross_k_prefix_independent_audit_20260923 as prefix
from scripts import ndx_historical_single_window_accounts_20260920 as single
archive=prefix.archive;publish=prefix.publish
INPUT=single.INPUT;PLAN=prefix.PLAN
BINDING_SHA='4df53abfe9e236a157fde6146a8b28036e41b8ee3b9e315354783ea99074db63'
PREFIX_SHA='833bd9064e9384f67896b7cf78a7cadcb04db9dfe8a650854a3b5592c70f9244'
FIRST_AUDIT=dict(path=str(PLAN['path']).replace('plan.json','completed_1_independent_audit.json'),sha256='2cd1f84ee70c193eb32e4ea84dcbd61daf096e34bcba0aa6629efb83bdd7c664')
EXTERNAL_ACCOUNT=dict(path=str(single.BASE/'candidate/account.json'),sha256='34b2b21b297e48a41e4568948644a5fcef4aeb7f3a3aca0d1849289181c0433d')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(binding.__file__).resolve(),Path(prefix.__file__).resolve(),Path(single.__file__).resolve())}
archive.merge(LOADED,single.LOADED);archive.merge(LOADED,prefix.LOADED)
FALSE=('fit_performed','result_imported','control_executed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','provider_identity_verified','corporate_action_completeness_verified')


def pack(v):return json.dumps(single.encode(v),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(pack(v)).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def full(sources):return archive.verify_expected_sources(sources,archive.load_contract())
def read(ref,sources):return prefix.read(ref,sources)


def authority(audit_reference):
    if LOADED[str(Path(binding.__file__).resolve())]!=BINDING_SHA or LOADED[str(Path(prefix.__file__).resolve())]!=PREFIX_SHA:raise ValueError('Sealed binding/prefix reader differs')
    sources=dict(LOADED);plan=read(PLAN,sources);inputs=read(INPUT,sources);audit=read(audit_reference,sources)
    prefix.verify(audit)
    if audit['plan_reference']!=PLAN or audit['schema']!='HISTORICAL_CROSS_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1':raise ValueError('Exact independently completed historical prefix required')
    for value in (plan,inputs,audit):archive.merge(sources,value['historical_expected_source_hashes'])
    index=read(audit['index_reference'],sources);details={d['task_id']:d for d in audit['details']};tasks={r['task_id']:r for r in plan['tasks']}
    if len(details)!=len(audit['details']) or [e['task_id'] for e in index['entries']]!=[d['task_id'] for d in audit['details']]:raise ValueError('Audited completed task denominator differs')
    queue=[]
    for entry in index['entries']:
        identifier=entry['task_id'];row=tasks[identifier]
        if row['status']!='PENDING_HISTORICAL_FIT' or identifier==prefix.plan_reader.target_reader.JOB:raise ValueError('Historical external result may not be queued for execution')
        queue.append(dict(task_id=identifier,task=dict(row['task'],task_id=identifier),fit_checkpoint_reference=entry['result_reference'],audited_detail=details[identifier]))
    value=dict(audit_reference=deepcopy(audit_reference),queue=queue,inputs=inputs,numerical=plan['numerical_source_hashes'],sources=sources,runtime=prefix.runtime())
    value['partition']=full(sources)
    return value


def bind_task(auth,row):
    temporary={};checkpoint=read(row['fit_checkpoint_reference'],temporary)
    if digest(checkpoint['task'])!=digest(row['task']) or checkpoint['plan_reference']!=PLAN or checkpoint['fit_performed'] is not True:raise ValueError('Fit checkpoint/task/source differs')
    for path,h in temporary.items():
        if auth['sources'].get(path)!=h:raise ValueError('Fit checkpoint not in independently audited source closure')
    return binding.prepare_candidate_arguments(inputs=auth['inputs'],task=row['task'],result=checkpoint['result'],numerical_sources=auth['numerical'],audited_detail=row['audited_detail'])


def external_reference(inputs,sources):
    saved=read(EXTERNAL_ACCOUNT,sources);target=read(single.TARGET,sources)
    single.target_reader.verify(read(dict(path=str(single.AUDIT_PATH),sha256=single.AUDIT_SHA),sources))
    for v in (saved,target):archive.merge(sources,v['historical_expected_source_hashes'])
    for key in ('started_reference','raw_execution_reference'):read(saved[key],sources)
    prepared=binding.prepare_candidate_arguments(inputs=inputs,task=target['task'],result=target['result'],numerical_sources=target['result']['source_hashes'],audited_detail=target['independent_matrix_and_risk_audit'])
    binding.existing_account_equivalence(prepared,saved,source_input_reference=INPUT)
    return deepcopy(EXTERNAL_ACCOUNT)


def marker_value(auth,row):return dict(schema='HISTORICAL_CROSS_K_ACCOUNT_ATTEMPT_V1',task_id=row['task_id'],plan_reference=PLAN,fit_prefix_audit_reference=auth['audit_reference'],fit_checkpoint_reference=row['fit_checkpoint_reference'],attempt_count=1,runtime=auth['runtime'])


def small(auth,sealed,prepared,sealed_prepared,marker=None):
    if digest(auth)!=sealed or digest(prepared)!=sealed_prepared or prefix.runtime()!=auth['runtime']:raise ValueError('Prepared RAM/runtime changed')
    for p,h in auth['sources'].items():
        if Path(p).suffix=='.py' and sha(p)!=h:raise ValueError('Loaded account source changed')
    if marker and sha(marker['path'])!=marker['sha256']:raise ValueError('Durable account attempt changed')


def restore(raw,prepared):
    account=prepared['account'];state=dict(account,track='candidate')
    return single.restore_and_audit(raw,state)


def result_value(auth,row,prepared,started,raw_ref,raw,sources):
    ready=prepared['status']=='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT'
    if ready:
        execution,audit=restore(raw,prepared);status='ACCOUNT_EXECUTED_AND_INDEPENDENTLY_AUDITED'
        account=prepared['account'];selected=account['selected']
        args=dict(calendar=account['calendar'],contract=account['contract'],schedule=selected['original_schedule'],effective_schedule=account['effective_schedule'],normalization_evidence=prepared['normalization_evidence'],internal_columns=selected['columns'])
    else:
        if raw_ref is not None or raw is not None:raise ValueError('Failed original risks cannot have an account execution')
        execution=None;audit=None;status='SKIPPED_RISK';args=None
    return dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_V1',task_id=row['task_id'],plan_reference=PLAN,fit_prefix_audit_reference=auth['audit_reference'],fit_checkpoint_reference=row['fit_checkpoint_reference'],
        started_reference=started,raw_reference=raw_ref,parameter_digest=digest(prepared),status=status,failed_original_risk_checks=prepared['failed_original_risk_checks'],
        arguments=args,execution=execution,independent_decimal_accounting=audit,execution_performed=ready,historical_expected_source_hashes=sources,
        # Full publication/index validation rechecks this complete source map.
        source_partition_verified_at_invocation_start=True,**dict.fromkeys(FALSE,False))


def index_value(auth,folder,entries,sources,external):
    return dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_INDEX_V1',plan_reference=PLAN,fit_prefix_audit_reference=auth['audit_reference'],folder=str(folder),
        audited_fit_task_count=len(auth['queue']),completed_account_task_count=len(entries),pending_account_task_count=len(auth['queue'])-len(entries),entries=entries,
        finalized_after_full_source_verification=True,external_completed_account_reference=external,external_account_imported=False,
        historical_expected_source_hashes=sources,archive_resolution=full(sources),**dict.fromkeys(FALSE,False))


def run(*,folder,audit_path=FIRST_AUDIT['path'],audit_sha256=FIRST_AUDIT['sha256'],max_new=0,index_path=None,index_sha256=None):
    if type(max_new) is not int or not 0<=max_new<=10:raise ValueError('Account budget must be integer 0..10')
    if (index_path is None)!=(index_sha256 is None):raise ValueError('External account index path/SHA pair required')
    audit_ref=dict(path=str(Path(audit_path).resolve()),sha256=audit_sha256);auth=authority(audit_ref);sealed=digest(auth);sources=dict(auth['sources'])
    external=external_reference(auth['inputs'],sources);external_required={p:h for p,h in sources.items() if p not in auth['sources']}
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);entries=[];authorities={digest(audit_ref):auth}
    if index_path:
        previous=read(dict(path=str(Path(index_path).resolve()),sha256=index_sha256),sources);entries=previous['entries']
        old_ref=previous['fit_prefix_audit_reference'];old=authority(old_ref) if digest(old_ref) not in authorities else authorities[digest(old_ref)];authorities[digest(old_ref)]=old
        previous_sources=previous['historical_expected_source_hashes'];full(previous_sources)
        if any(previous_sources.get(p)!=h for p,h in dict(old['sources'],**external_required).items()) or digest(previous)!=digest(index_value(old,folder,entries,previous_sources,external)):raise ValueError('Exact finalized account index/closure required')
        if [r['task_id'] for r in old['queue']]!=[r['task_id'] for r in auth['queue'][:len(old['queue'])]]:raise ValueError('New audited fit prefix must extend old prefix')
        archive.merge(sources,previous_sources)
    if [e['task_id'] for e in entries]!=[r['task_id'] for r in auth['queue'][:len(entries)]]:raise ValueError('Exact completed account prefix required')
    allowed={e['task_id'] for e in entries}
    for p in folder.iterdir():
        if p.is_dir() and p.name in allowed:continue
        if p.is_file() and p.name.startswith('index_') and p.suffix=='.json':continue
        raise ValueError('Unindexed attempt/raw/failure prevents replay')
    for entry in entries:
        directory=folder/entry['task_id'];saved=read(entry['result_reference'],sources);old_ref=saved['fit_prefix_audit_reference']
        if digest(old_ref) not in authorities:authorities[digest(old_ref)]=authority(old_ref)
        old=authorities[digest(old_ref)];row=next(r for r in old['queue'] if r['task_id']==entry['task_id']);prepared=bind_task(old,row)
        if set(entry)!={'task_id','started_reference','raw_reference','result_reference'}:raise ValueError('Exact account entry required')
        names={'started.json','result.json'}|({'raw.json'} if entry['raw_reference'] else set())
        if {p.name for p in directory.iterdir()}!=names:raise ValueError('Incomplete or failed account cannot replay')
        local=dict(old['sources']);raw=None
        for kind,name in [('started','started.json'),('result','result.json')]+([('raw','raw.json')] if entry['raw_reference'] else []):
            ref=entry[kind+'_reference']
            if ref['path']!=str(directory/name):raise ValueError('Saved account address differs')
            value=read(ref,sources)
            if kind=='started':
                if digest(value)!=digest(marker_value(old,row)):raise ValueError('Account marker differs')
                archive.merge(local,{ref['path']:ref['sha256']})
            if kind=='raw':
                expected=raw_value(old,row,prepared,entry['started_reference'],value['execution'])
                if digest(expected)!=digest(value):raise ValueError('Original raw account differs')
                raw=value['execution'];archive.merge(local,{ref['path']:ref['sha256']})
        if digest(saved)!=digest(result_value(old,row,prepared,entry['started_reference'],entry['raw_reference'],raw,local)):raise ValueError('Whole saved account/independent ledger/source differs')
        archive.merge(sources,local)
        if index_path:
            for key in ('started_reference','raw_reference','result_reference'):
                ref=entry[key]
                if ref and previous_sources.get(ref['path'])!=ref['sha256']:raise ValueError('Final account index omitted completed artifact')
    full(sources);processed=0
    try:
        for row in auth['queue'][len(entries):len(entries)+max_new]:
            prepared=bind_task(auth,row);sealed_prepared=digest(prepared);directory=folder/row['task_id'];small(auth,sealed,prepared,sealed_prepared)
            if directory.exists():raise ValueError('Existing account attempt must never replay')
            started=publish(directory/'started.json',marker_value(auth,row));local=dict(auth['sources']);archive.merge(local,{started['path']:started['sha256']});raw_ref=None;raw=None
            try:
                small(auth,sealed,prepared,sealed_prepared,started)
                if prepared['status']=='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT':
                    kwargs=deepcopy(prepared['account']['selected']['arguments']);before=digest(kwargs)
                    raw=single.candidate.simulate_dynamic_frozen_execution_research(**kwargs)
                    raw_ref=publish(directory/'raw.json',raw_value(auth,row,prepared,started,raw));archive.merge(local,{raw_ref['path']:raw_ref['sha256']})
                    if digest(kwargs)!=before:raise ValueError('Candidate engine mutated supplied arguments')
                small(auth,sealed,prepared,sealed_prepared,started)
                saved=publish(directory/'result.json',result_value(auth,row,prepared,started,raw_ref,raw,local));small(auth,sealed,prepared,sealed_prepared,started)
                for ref in (raw_ref,saved):
                    if ref and sha(ref['path'])!=ref['sha256']:raise ValueError('Published account bytes changed')
                entries.append(dict(task_id=row['task_id'],started_reference=started,raw_reference=raw_ref,result_reference=saved));processed+=1
                archive.merge(sources,local);archive.merge(sources,{saved['path']:saved['sha256']})
            except BaseException as error:
                publish(directory/'failure.json',dict(schema='HISTORICAL_CROSS_K_ACCOUNT_FAILURE_V1',task_id=row['task_id'],started_reference=started,raw_reference=raw_ref,error_type=type(error).__name__,automatic_retry_allowed=False,failure_is_economic_infeasibility=False));raise
        full(sources);value=index_value(auth,folder,entries,sources,external);path=folder/('index_'+digest(value)+'.json')
        if path.exists():
            if digest(json.loads(path.read_bytes()))!=digest(value):raise ValueError('Existing account index differs')
            saved=dict(path=str(path),sha256=sha(path))
        else:saved=publish(path,value)
        full(sources)
        if sha(saved['path'])!=saved['sha256']:raise ValueError('Finalized account index changed after publication')
        return dict(index_reference=saved,processed_this_invocation=processed,completed=len(entries),fit_performed=False,control_executed=False)
    finally:full(sources)


def raw_value(auth,row,prepared,started,raw):
    return dict(schema='HISTORICAL_CROSS_K_RAW_CANDIDATE_ACCOUNT_V1',task_id=row['task_id'],plan_reference=PLAN,fit_prefix_audit_reference=auth['audit_reference'],
        fit_checkpoint_reference=row['fit_checkpoint_reference'],started_reference=started,parameter_digest=digest(prepared),execution=raw,
        original_schedule=prepared['account']['selected']['original_schedule'],internal_columns=prepared['account']['selected']['columns'],
        calendar=prepared['account']['calendar'],contract=prepared['account']['contract'],independent_accounting_completed=False,execution_performed=True,**dict.fromkeys(FALSE,False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--audit-path',default=FIRST_AUDIT['path']);p.add_argument('--audit-sha256',default=FIRST_AUDIT['sha256']);p.add_argument('--max-new',type=int,default=0);p.add_argument('--index-path');p.add_argument('--index-sha256');print(json.dumps(run(**vars(p.parse_args()))))
