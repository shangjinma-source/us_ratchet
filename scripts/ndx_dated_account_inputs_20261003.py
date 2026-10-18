"""Immutable inputs for one explicit audited dated fit. No account/fit execution."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_account_input_research.py';CORE_SHA='319c80d23dad7e50eacb219206c5a5a3dd58bee41dc51b69e424a84f3c5b360e'
OUTPUT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
ATTEMPTS=ROOT/'data/cache/research/dated_single_task_20261003_v1'
BOUND={
 'normalizer':('backtest/ndx_dynamic_whole_lot_path.py','3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95'),
 'preparation':('data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json','ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'),
 'channels':('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json','0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'),
 'channels_publication':('data/cache/research/bulk_long_window_channels_20261003_v1/publication.json','b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'),
 'channels_audit':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json','3b7b35a3574757c9cdd12c74e701366979e490f5aadebcf0019da97349f4da65'),
 'control':('data/cache/research/original_eight_long_window_channels_20261003_v1/channels.json','67d433ae92acb0755a1ffdabf090e6c20706b4d1ba893637673e96a047acc372'),
 'control_publication':('data/cache/research/original_eight_long_window_channels_20261003_v1/publication.json','836622bff616370375539490c441fbb5b988d5dab8b661b202991288bcbf05e1'),
 'control_audit':('DYNAMIC_ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_20261003.json','182e901ad1554292444142c51ace220da2f1912b361d048d78b499d5aeaeb988'),
 'registry':('data/cache/research/standard_split_exact_gap_20260919_v1/registry_readback.json','61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'fit_reader':('scripts/ndx_dated_single_task_independent_readback_20261003.py','bd63ce1541c63d3f38e90a7313666d37abcbb9b51cc9d2291f702ee8fad43cea'),
}
FLAGS=dict.fromkeys(('account_executed','fit_performed','old_audit_repeated','raw_prices_decoded','point_in_time_verified','promotion_allowed','legal_training_input_admitted','execution_authorized','historical_identity_verified','provider_binding_verified','full_transitive_source_closure_reverified','split_evidence_reparsed','corporate_action_completeness_verified','dividend_cash_flows_modelled','untouched_holdout','future_independent_oos'),False)
_CACHE={}


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def ref(role):return dict(path=str(ROOT/BOUND[role][0]),sha256=BOUND[role][1])
def canonical(value):require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None,'Explicit SHA/ID required')

def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)


def merge(sources,path,h):
    canonical(h);require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h


def consume(reference,sources):
    require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact source reference');canonical(reference['sha256'])
    path=Path(reference['path']);blob=path.read_bytes();require(sha(blob)==reference['sha256'],'Source bytes differ');merge(sources,str(path),reference['sha256']);return blob


def guard(sources):
    expected=dict(sources);merge(expected,str(SOURCE),LOADED_SHA);merge(expected,str(CORE),CORE_SHA)
    for path,h in expected.items():require(sha(Path(path).read_bytes())==h,'Source drift: '+path)


def load_core():
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Current core differs');module=types.ModuleType('_dated_account_input_core');module.__file__=str(CORE)
    exec(compile(blob,str(CORE),'exec'),module.__dict__);require(Path(module.__file__).resolve()==CORE,'Loaded core path');return module


def validate_parents(docs):
    for role,schema in [('channels','BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1'),('control','ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1')]:
        d=docs[role];pub=docs[role+'_publication'];audit=docs[role+'_audit']
        require(d['schema']==schema and audit['status']=='PASS','Saved channel schemas/readback')
        exact(pub['channels_reference'],ref(role),'Successful parent publication payload');exact(pub['source_hashes'],d['source_hashes'],'Parent publication sources')
        require(pub['status'].startswith('PUBLISHED_') and audit['channels_sha256']==ref(role)['sha256'] and audit['publication_sha256']==ref(role+'_publication')['sha256'],'Channel audit binding')
        for obj in (d,pub):
            for key in ('point_in_time_verified','fit_performed','legal_training_input_admitted'):require(obj[key] is False,'No authority upgrade')
        audit_schema='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1' if role=='channels' else 'ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1'
        require(audit['schema']==audit_schema,'Role-specific independent schema')
        audit_false=('point_in_time_verified','fit_performed','account_simulation_performed','untouched_holdout')
        audit_false+=('legal_training_input_admitted','future_independent_oos') if role=='channels' else ('benchmark_qualified','reused_channels_recomputed')
        for key in audit_false:require(audit[key] is False,'Explicit role-specific readback authority')
    require(len(docs['channels']['rows'])==77 and len(docs['control']['rows'])==8,'77 and original8 denominator')
    require(len(docs['channels']['original_provenance_and_missing'])==101 and len(docs['channels']['preserved_evidence_sidecars'])==7,'Full evidence denominator')
    exact(docs['channels']['calendar253'],docs['control']['calendar253'],'Common253 source dates')
    require(docs['preparation']['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1','Dated task source')


def load_common():
    sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};guard(sources);docs={}
    for role in BOUND:
        blob=consume(ref(role),sources)
        if role not in ('fit_reader','normalizer'):docs[role]=loads(blob)
    validate_parents(docs)
    for role in ('channels','control'):
        folder=Path(ref(role)['path']).parent
        require(not (folder/'failure.json').exists() and (folder/'publication.json').is_file(),'Parent failed/unpublished')
    for index,ticker in ((2,'BKNG'),(12,'KLAC')):
        event=docs['registry']['events'][index];require(event['ticker']==ticker,'Fixed registry index')
        consume(dict(path=str(Path(event['raw_path'])),sha256=event['raw_sha256']),sources)
    tasks={}
    for i,combo in enumerate(docs['preparation']['materialized']['combinations']):
        for j,task in enumerate(combo['tasks']):
            tid=task['numerical_task_id'];canonical(tid);require(tid not in tasks,'Duplicate task');tasks[tid]=(task,dict(ref('preparation'),json_pointer=f'/materialized/combinations/{i}/tasks/{j}'))
    require(len(tasks)==1632,'Full dated task queue')
    handle={'ordered_task_ids':list(tasks)};_CACHE[id(handle)]=(handle,docs,tasks,sources,load_core());guard(sources);return handle


def split_bindings(sid,channel,registry,registry_reference):
    out=[];evidence=[]
    for policy in channel['event_policies']:
        if not '2026-03-20'<policy['session']<='2026-09-21':continue
        require(policy['kind']=='ORDINARY_SPLIT','Unsupported in-window action')
        matches=[r for r in channel['bridge_row_preserved']['event_policy_bridge']['events'] if r['session']==policy['session']]
        require(len(matches)==1 and matches[0]['status']=='SPECIFIC_POLICY_MATCH','Unique policy source')
        source=matches[0]['specific_event_reference'];i=source['event_index'];require(type(i) is int and i in (2,12),'Only explicit supported saved event indices')
        row=registry['events'][i]
        require(Path(source['parent']['path'])==Path(registry_reference['path']) and source['parent']['sha256']==registry_reference['sha256'],'Registry source binding')
        require(Path(source['original_raw_reference']['path'])==Path(row['raw_path']) and source['original_raw_reference']['sha256']==row['raw_sha256'],'Original event bytes reference')
        require(row['ticker']==channel['ticker'] and row['first_adjusted_trading_date']==policy['session'] and row['new_shares']==policy['numerator'] and row['old_shares']==policy['denominator'],'Saved split fact')
        require(row['specific_simple_share_split_event_supported'] is True and row['corporate_action_completeness_verified'] is False and row['point_in_time_verified'] is False,'Specific conditional fact only')
        event=dict(security_id=sid,session=policy['session'],new_shares=row['new_shares'],old_shares=row['old_shares'],source_url=row['source_url'],evidence_sha256=row['raw_sha256'])
        out.append(dict(event=event,policy_reference=dict(registry_reference,json_pointer=f'/events/{i}')))
        evidence.append(dict(registry_row=deepcopy(row),bridge_specific_reference=deepcopy(source)))
    return out,evidence


def project(core,task,task_reference,fit_result,fit_reference,docs):
    selected=task['numerical_identity']['selected'];by={r['coordinate']['security_id']:(i,r) for i,r in enumerate(docs['channels']['rows'])}
    require(len(by)==77 and set(selected)<=set(by),'Exact candidate universe')
    candidate={};control={};references={};events={};event_originals={}
    for sid in selected:
        i,row=by[sid]
        for key in ('ticker','issuer_id','risk_chain'):exact(row['coordinate'][key],selected[sid][key],'Selected saved coordinate')
        candidate[sid]=row['channel'];references[sid]=dict(ref('channels'),json_pointer=f'/rows/{i}/channel')
    securities=[]
    for i,row in enumerate(docs['control']['rows']):
        original=row['original_control_security'];sid=original['security_id'];require(sid not in control,'Original8 unique SID');securities.append(original);control[sid]=row['channel']
        if sid in candidate:exact(candidate[sid],control[sid],'Reused channel exact')
        else:references[sid]=dict(ref('control'),json_pointer=f'/rows/{i}/channel')
    for sid,channel in {**candidate,**control}.items():events[sid],event_originals[sid]=split_bindings(sid,channel,docs['registry'],ref('registry'))
    inputs=core.assemble_dated_account_inputs(task=task,fit_result=fit_result,task_reference={k:task_reference[k] for k in ('path','sha256')},fit_reference=fit_reference,candidate_channels_by_security=candidate,incumbent_securities=securities,incumbent_channels_by_security=control,channel_references=references,split_evidence_by_security=events)
    weights={s:float(t['target_weight']) for s,t in fit_result['targets'].items()};total=sum(weights[s] for s in task['numerical_identity']['selected'])
    compatible=all(v>0 and math.isfinite(v) for v in weights.values())
    inputs['candidate_engine_normalization_evidence']=dict(normalizer_source_reference=ref('normalizer'),original_weights=deepcopy({s:t['target_weight'] for s,t in fit_result['targets'].items()}),ordered_security_ids=list(task['numerical_identity']['selected']),float_total=total,effective_weights={s:weights[s]/total for s in task['numerical_identity']['selected']} if compatible else None,semantics='SAME_FLOAT_SUM_AND_DIVISION_AS_FROZEN_NORMALISE_TARGETS;NOT_AN_ENGINE_EXECUTION',blocked_nonpositive=not compatible,control_weights_normalized=False)
    return dict(schema='DATED_ACCOUNT_INPUT_DOCUMENT_V1',inputs=inputs,task_reference=deepcopy(task_reference),split_source_facts_preserved=event_originals,complete_original_control=deepcopy(docs['control']['original_control_preserved']),original_provenance_and_missing=deepcopy(docs['channels']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['channels']['preserved_evidence_sidecars']),input_references={k:ref(k) for k in BOUND},**FLAGS)


def save(path,value):
    blob=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Written bytes changed');return dict(path=str(path),sha256=sha(blob))


def run(task_id,readback_reference,*,execute=False,common=None):
    canonical(task_id);require(type(execute) is bool and execute,'Explicit execute=True required')
    destination=OUTPUT/task_id;require(not destination.exists(),'Input namespace exists; no overwrite/retry')
    if common is None:common=load_common()
    cached=_CACHE.get(id(common));require(cached is not None and cached[0] is common,'Only issued common handles')
    _,docs,tasks,base_sources,core=cached;require(common=={'ordered_task_ids':list(tasks)} and task_id in tasks,'Complete saved queue task')
    sources=dict(base_sources);guard(sources);task,task_reference=tasks[task_id];folder=ATTEMPTS/task_id
    require(Path(readback_reference['path'])==folder/'independent_readback.json','Explicit dated reader path')
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json','independent_readback.json'},'Only fully audited attempt evidence')
    report=loads(consume(readback_reference,sources));require(report['schema']=='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1' and report['status']=='PASSED' and report['numerical_task_id']==task_id and report['attempt_outcome'] in ('RISK_PASSED','RISK_FAILED'),'Returned independent dated fit required')
    exact(report['task_reference'],task_reference,'Report exact saved task pointer')
    require(report['source_hashes'][ref('fit_reader')['path']]==ref('fit_reader')['sha256'],'Audited reader binding')
    documents={}
    for key in ('started','raw','postcheck'):
        r=report[key+'_reference'];require(Path(r['path'])==folder/(key+'.json'),'Exact referenced task evidence path');documents[key]=loads(consume(r,sources))
    started=documents['started'];raw=documents['raw'];post=documents['postcheck']
    require(started['schema']=='DATED_SINGLE_TASK_STARTED_V1' and raw['schema']=='DATED_SINGLE_TASK_RAW_V1' and post['schema']=='DATED_SINGLE_TASK_POSTCHECK_V1','Dated evidence schemas')
    exact(started['task'],task,'Saved task identity');exact(started['task_reference'],task_reference,'Started pointer');exact(raw['started_reference'],report['started_reference'],'Raw started');exact(post['started_reference'],report['started_reference'],'Post started');exact(post['raw_reference'],report['raw_reference'],'Post raw')
    require(raw['status']=='FIT_RETURNED' and type(raw['returned_fit_count']) is int and raw['returned_fit_count']==1 and raw['error'] is None and post['error'] is None,'Returned no validation failure')
    expected='ORIGINAL_RISKS_'+('PASSED' if report['attempt_outcome']=='RISK_PASSED' else 'FAILED')+'_PENDING_INDEPENDENT_READBACK'
    require(post['status']==expected and raw['numerical_task_id']==post['numerical_task_id']==task_id,'Attempt outcome binding')
    guard(sources);destination.mkdir(parents=True,exist_ok=False)
    try:
        save(destination/'started.json',dict(schema='DATED_ACCOUNT_INPUT_STARTED_V1',task_reference=task_reference,independent_readback_reference=readback_reference,source_hashes=sources,**FLAGS))
        value=project(core,task,task_reference,raw['fitted'],report['raw_reference'],docs)
        value.update(independent_readback_reference=deepcopy(readback_reference),saved_attempt_outcome=report['attempt_outcome'],saved_readback=report,source_hashes=sources)
        guard(sources);output=save(destination/'inputs.json',value);guard(sources)
        receipt=save(destination/'publication.json',dict(schema='DATED_ACCOUNT_INPUT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED',inputs_reference=output,source_hashes=sources,**FLAGS))
        guard(sources)
        for r in (output,receipt):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Published readback drift')
        return output
    except Exception as error:
        save(destination/'failure.json',dict(schema='DATED_ACCOUNT_INPUT_FAILURE_V1',error_type=type(error).__name__,message=str(error),retry_allowed=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task-id',required=True);parser.add_argument('--readback-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.task_id,dict(path=str(ATTEMPTS/args.task_id/'independent_readback.json'),sha256=args.readback_sha256),execute=args.execute)))
