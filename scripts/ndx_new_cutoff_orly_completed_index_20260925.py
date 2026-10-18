"""Index saved independent results only; no runner, fitter or audit imports."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'new_cutoff_orly_completed_index_20260925_v1/index.json'
TASK_ROOT=BASE/'new_cutoff_orly_single_task_20260925_v1'
BOUND={
 'queue':('new_cutoff_orly_combination_materialization_20260925_v1/queue.json','cde70b4b1e38491997b7f8bec7ac6c9e8e5419d80bded20843f558638f6aadce'),
 'queue_audit':('new_cutoff_orly_combination_materialization_20260925_v1/independent_readback.json','da8afe3018b91db7bf66bb48b8835e7d79faa4e5e42374e3ee9dee11bfcc9936'),
 'rebinding':('new_cutoff_v5_completed_task_rebinding_20260925_v1/rebinding.json','c64888a62744c1ee8c6acb08c37d96350fe4e58546320d5a1957f90eedfb63b7'),
 'rebinding_audit':('new_cutoff_v5_completed_task_rebinding_20260925_v1/independent_readback.json','06a9b1b024bdc43e091bcadd6fa112fce34446a815a1cdf3f99f5a7f88612dbf'),
 'manifest':('new_cutoff_orly_completed_audit_references_20260925_v1/references.json','44eb259b5f7682117282846d9c11d8327b62d0503cd7d2b13312224ccb6c0986')}

PINS={str(ROOT/'scripts/ndx_new_cutoff_orly_single_task_20260925.py'):'e8f466b0cb83f90c73cbdf0d7414bf0692e0784107a2f3799daac5cd3f1308b2',
 str(ROOT/'scripts/ndx_new_cutoff_orly_single_task_independent_readback_20260925.py'):'1f70cb37e4bc7cd16616d8cf35f207d24981d15f7416571553113a561711ed34'}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),**PINS}
FALSE=('fit_performed','task_readback_repeated','materialization_repeated','all_plan_tasks_completed','full_shard_completed',
 'point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed')
RISK_NAMES={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}

def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def merge(sources,other):
    for path,digest in other.items():
        require(path not in sources or sources[path]==digest,'Conflicting source map');sources[path]=digest


def guard(sources):
    require(all(type(h) is str and len(h)==64 for h in PINS.values()),'Frozen runner/reader source SHA pending')
    expected=dict(sources);merge(expected,LOADED)
    for path,digest in expected.items():require(sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def load_bound(reference,sources):
    path=Path(reference['path']);raw=path.read_bytes();require(sha(raw)==reference['sha256'],'Consumed source bytes differ')
    merge(sources,{str(path):reference['sha256']})
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'Duplicate JSON key');value[key]=item
        return value
    def fail(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=fail)


def tasks_and_references(documents):
    queue=documents['queue'];manifest=documents['manifest'];audit=documents['queue_audit'];old=documents['rebinding'];old_audit=documents['rebinding_audit']
    require(queue['schema']=='NEW_CUTOFF_ORLY_COMBINATION_MATERIALIZATION_V1' and old['schema']=='NEW_CUTOFF_V5_COMPLETED_TASK_REBINDING_V1','Saved queue/rebinding schemas')
    require(type(queue['full_plan_task_denominator']) is int and queue['full_plan_task_denominator']==18868155 and
        type(old['externally_rebound_task_count']) is int and old['externally_rebound_task_count']==300,'Saved full denominator and old300')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('queue'),'Queue independent audit required')
    require(old_audit['status']=='PASSED' and old_audit['candidate_reference']==ref('rebinding') and old_audit['numerical_contracts_unchanged'] is True,'Old300 independent rebinding')
    old_ids=[row['numerical_task_id'] for row in old['rows']]
    require(len(old_ids)==len(set(old_ids))==300 and old_ids==old_audit['verified_numerical_task_ids'] and
        queue['reused_completed_reference']==dict(rebinding_reference=ref('rebinding'),independent_readback_reference=ref('rebinding_audit'),numerical_task_ids=old_ids),'Exact external300 references')
    tasks=[]
    for i,value in enumerate(queue['new_materializations']):
        for j,combo in enumerate(value['combinations']):
            for k,task in enumerate(combo['tasks']):tasks.append((task,dict(ref('queue'),json_pointer=f'/new_materializations/{i}/combinations/{j}/tasks/{k}')))
    ids=[t['numerical_task_id'] for t,p in tasks]
    require(len(ids)==len(set(ids))==102 and not set(ids)&set(old_ids),'Exact102 new IDs')
    require(set(manifest)=={'schema','queue_reference','task_audit_references','expected_count'} and manifest['schema']=='ORLY_COMPLETED_AUDIT_REFERENCES_V1' and
        manifest['queue_reference']==ref('queue') and type(manifest['expected_count']) is int and manifest['expected_count']==102,'Hard external reference manifest')
    refs=manifest['task_audit_references'];require([r['numerical_task_id'] for r in refs]==ids,'Exact102 manifest order/coverage')
    for r in refs:
        require(set(r)=={'numerical_task_id','path','sha256'} and r['path']==str(TASK_ROOT/r['numerical_task_id']/'independent_readback.json') and
            type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Canonical external task audit reference')
    return tasks,refs


def row_from_evidence(task,pointer,audit_reference,item):
    saved,started,raw,post=(item[k] for k in ('audit','started','raw','postcheck'));tid=task['numerical_task_id'];folder=TASK_ROOT/tid
    require(saved['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1' and saved['numerical_task_id']==tid and
        saved['independent_readback_performed'] is True and type(saved['completed_saved_task_readbacks']) is int and saved['completed_saved_task_readbacks']==1,'One saved independent readback')
    require(all(saved[k] is False for k in ('runner_called','fitter_called','optimization_repeated','promotion_allowed','execution_authorized','all_plan_tasks_completed')),'Saved authority changed')
    require(saved['input_references']['queue']==ref('queue') and saved['input_references']['audit']==ref('queue_audit') and saved['input_references']['rebinding']==ref('rebinding') and saved['input_references']['rebinding_audit']==ref('rebinding_audit'),'Saved lineage differs')
    require(all(saved['source_hashes'].get(p)==h and started['source_hashes'].get(p)==h for p,h in PINS.items() if 'single_task_20260925.py' in p),'Runner source closure differs')
    require(saved['source_hashes'].get(next(p for p in PINS if 'independent_readback' in p))==next(h for p,h in PINS.items() if 'independent_readback' in p),'Independent reader source differs')
    require(started['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_STARTED_V1' and canonical(started['task'])==canonical(task) and started['task_reference']==pointer,'Full started task/pointer mismatch')
    require(raw['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_RAW_V1' and raw['numerical_task_id']==tid and raw['source_hashes']==started['source_hashes'] and raw['runtime']==started['runtime'],'Raw source/runtime mismatch')
    require(raw['internal_optimizer_call_count'] is None,'Internal optimizer count remains unknown')
    require(all(saved['source_hashes'].get(p)==h for p,h in started['source_hashes'].items()),'Incomplete saved source closure')
    for name in ('started','raw'):
        r=saved[name+'_reference'];require(r['path']==str(folder/(name+'.json')) and saved['source_hashes'].get(r['path'])==r['sha256'],'Saved original reference differs')
    require(raw['started_reference']==saved['started_reference'] and post==saved['saved_postcheck'],'Raw/postcheck original binding differs')
    equal=task['numerical_identity']['weight_spec']=='equal_weight';counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0)
    require(canonical(raw['operation_counts'])==canonical(counts) and canonical(started['planned_operation_counts'])==canonical(counts),'Exactly one external attempt')
    status=saved['status'];detail=saved['detail'];require(saved['numerical_detail_status']==detail['status'],'Detail status differs')
    allowed=('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION_NO_RETURNED_FIT','VALIDATION_FAILURE_RECORDED')
    require(status in allowed,'Unknown saved result status')
    if raw['status']=='FIT_EXCEPTION':
        require(type(raw['returned_fit_count']) is int and raw['returned_fit_count']==0 and raw['fitted'] is None and type(raw['error']) is dict and detail['status']=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT','Exception cannot become returned fit')
        require(canonical(detail['error'])==canonical(raw['error']),'Saved numerical exception differs')
    else:
        require(raw['status']=='FIT_RETURNED' and type(raw['returned_fit_count']) is int and raw['returned_fit_count']==1 and raw['error'] is None and
            raw['fitted']['fit_data_sha256']==task['numerical_identity']['fit_data_sha256'],'Returned fit binding')
        checks=detail['checks'];require(type(checks) is dict and set(checks)==RISK_NAMES and all(type(v) is bool for v in checks.values()),'Exact five boolean risk results')
        require(len(raw['fitted']['source_hashes'])==25 and all(started['source_hashes'].get(p)==h for p,h in raw['fitted']['source_hashes'].items()),'Full numerical source closure')
        require(detail['status']==('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED'),'Risk failure cannot become pass')
    postref=None
    if post is not None:
        require(post['schema']=='NEW_CUTOFF_ORLY_SINGLE_TASK_POSTCHECK_V1' and post['numerical_task_id']==tid and post['started_reference']==saved['started_reference'] and post['raw_reference']==saved['raw_reference'],'Postcheck identity')
        path=str(folder/'postcheck.json');require(path in saved['source_hashes'],'Saved postcheck SHA missing');postref=dict(path=path,sha256=saved['source_hashes'][path])
    expected=detail['status']
    if post is not None and post['error'] is not None and not (detail['status']=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT' and canonical(post['error'])==canonical(detail['error'])):expected='VALIDATION_FAILURE_RECORDED'
    require(status==expected,'Validation failure cannot become completed pass')
    post_failed=post is not None and post['error'] is not None
    kind=('NUMERICAL_EXCEPTION_RECORDED' if expected=='NUMERICAL_EXCEPTION_NO_RETURNED_FIT' else 'VALIDATION_FAILURE_RECORDED') if post_failed else None
    require(saved['saved_postcheck_failure_preserved'] is post_failed and saved['saved_postcheck_failure_kind']==kind,'Exact saved failure classification')
    return dict(numerical_task_id=tid,full_task=deepcopy(task),task_reference=pointer,started_reference=deepcopy(saved['started_reference']),
        raw_reference=deepcopy(saved['raw_reference']),postcheck_reference=postref,independent_readback_reference=audit_reference,
        status=status,returned_fit_count=raw['returned_fit_count'],operation_counts=counts,targets=deepcopy(raw['fitted']['targets']) if raw['fitted'] is not None else None,
        fit_data_sha256=task['numerical_identity']['fit_data_sha256'])


def assemble(documents,evidence):
    tasks,refs=tasks_and_references(documents);require(set(evidence)=={t['numerical_task_id'] for t,p in tasks},'No omitted/extra task evidence')
    rows=[row_from_evidence(t,p,{k:r[k] for k in ('path','sha256')},evidence[t['numerical_task_id']]) for (t,p),r in zip(tasks,refs)]
    counts={status:sum(r['status']==status for r in rows) for status in ('FITTED_FIVE_RISKS_PASSED','FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION_NO_RETURNED_FIT','VALIDATION_FAILURE_RECORDED')}
    return dict(schema='NEW_CUTOFF_ORLY_COMPLETED_TASK_INDEX_V1',input_references={k:ref(k) for k in BOUND},new_tasks=rows,
        externally_completed_rebound_rows=deepcopy(documents['rebinding']['rows']),rebinding_reference=ref('rebinding'),rebinding_audit_reference=ref('rebinding_audit'),
        new_independently_read_task_count=102,new_status_counts=counts,new_returned_fit_count=sum(r['returned_fit_count'] for r in rows),
        external_completed_task_count=300,batch_saved_attempt_and_readback_count=402,batch_original_risk_pass_count=300+counts['FITTED_FIVE_RISKS_PASSED'],
        full_pool_planned_task_denominator=18868155,remaining_unattempted_plan_task_count=18867753,
        all_new_batch_independent_reports_present=True,all_new_batch_original_risks_passed=counts['FITTED_FIVE_RISKS_PASSED']==102,
        internal_optimizer_call_count=None,failure_is_global_infeasibility=False,**dict.fromkeys(FALSE,False))



def build():
    require(type(BOUND['manifest'][1]) is str and len(BOUND['manifest'][1])==64,'Actual102 external manifest SHA pending')
    sources=dict(LOADED);guard(sources);documents={role:load_bound(ref(role),sources) for role in BOUND}
    tasks,refs=tasks_and_references(documents);evidence={}
    for r in refs:
        tid=r['numerical_task_id'];saved=load_bound({k:r[k] for k in ('path','sha256')},sources);merge(sources,saved['source_hashes'])
        started=load_bound(saved['started_reference'],sources);raw=load_bound(saved['raw_reference'],sources);post=None
        if saved['saved_postcheck'] is not None:
            path=str(TASK_ROOT/tid/'postcheck.json');post=load_bound(dict(path=path,sha256=saved['source_hashes'][path]),sources)
        evidence[tid]=dict(audit=saved,started=started,raw=raw,postcheck=post)
    guard(sources);value=assemble(documents,evidence);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fresh immutable namespace required')
    value=build();guard(value['source_hashes']);blob=encode(value);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'index.json'},'Index output drift')
    return dict(path=str(OUTPUT),sha256=sha(blob))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))


