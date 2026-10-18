"""New candidate raw readback; prior original-eight audit reused by hard reference."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_split_accounting_readback_research.py'
CORE_SHA='6bebbaca5e57098ba950be96250c94b59381f93d7c5ace85f8684d96abbba65b'
RUNNER=ROOT/'scripts/ndx_dated_account_execution_20261003.py'
RUNNER_SHA='33752035971557f2ae1d273bd9424f293c9d4530938bee4bae44581cfab496cd'
INPUT_READER=ROOT/'scripts/ndx_dated_account_input_independent_readback_20261003.py'
INPUT_READER_SHA='688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'
CONTROL_AUDIT=ROOT/'DYNAMIC_DATED_FIRST_ACCOUNTS_INDEPENDENT_READBACK_20261003.json'
CONTROL_AUDIT_SHA='64c68233d31913422ef7d3f823602f3f1ecd85c2309184f7cf4cb2d623d4af7a'
ATTEMPTS=ROOT/'data/cache/research/dated_account_execution_20261003_v1/candidates'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
FIRST_TASK='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
ENGINE={
 'backtest/ndx_dynamic_frozen_execution_research.py':'69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b',
 'backtest/ndx_dynamic_whole_lot_path.py':'3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
 'backtest/ndx_dynamic_whole_lot_repair_path.py':'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
 'backtest/ndx_whole_lot_repair_diagnostic.py':'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
 'backtest/ndx_split_accounting_research.py':'11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c'}
FLAGS=dict.fromkeys(('account_reexecuted','fit_performed','old_audit_repeated','shared_incumbent_reaudited','point_in_time_verified','promotion_allowed','execution_authorized','future_independent_oos','untouched_holdout','formal_comparison_passed','full_transitive_source_closure_reverified'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message='Exact saved evidence differs'):require(enc(a)==enc(b),message)
def canonical(v):require(type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v),'Canonical SHA')
def merge(sources,p,h):
    canonical(h);require(p not in sources or sources[p]==h,'Conflicting source');sources[p]=h
def read(r,sources):
    require(type(r) is dict and set(r)=={'path','sha256'},'Exact external reference');canonical(r['sha256'])
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'External source bytes');merge(sources,r['path'],r['sha256'])
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(sources):
    allsources=dict(sources)
    for p,h in ((SOURCE,LOADED_SHA),(CORE,CORE_SHA),(RUNNER,RUNNER_SHA),(INPUT_READER,INPUT_READER_SHA),(CONTROL_AUDIT,CONTROL_AUDIT_SHA)):merge(allsources,str(p),h)
    for p,h in allsources.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)


def validate_evidence(task_id,post,raw,started,inputs,publication,input_audit,control_audit,refs):
    """Source-bound caller consumes all referenced bytes before this pure link check."""
    state=started['state'];require(state['track']=='candidate' and state['numerical_task_id']==task_id,'Candidate identity')
    require(started['schema']=='DATED_ACCOUNT_STARTED_V1' and raw['schema']=='DATED_ACCOUNT_RAW_V1' and post['schema']=='DATED_ACCOUNT_POSTCHECK_V1','Account envelope schemas')
    require(post['track']=='candidate' and post['numerical_task_id']==task_id,'Post identity')
    exact(raw['started_reference'],refs['started']);exact(post['started_reference'],refs['started']);exact(post['raw_reference'],refs['raw'])
    exact(raw['runtime'],state['runtime']);exact(raw['source_hashes'],state['source_hashes'])
    require(state['source_hashes'][str(RUNNER)]==RUNNER_SHA,'Saved runner source binding')
    require(inputs['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and publication['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and publication['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Input publication')
    exact(publication['inputs_reference'],refs['inputs']);exact(publication['source_hashes'],inputs['source_hashes'])
    require(input_audit['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and input_audit['status']=='PASS' and input_audit['reader_sha256']==INPUT_READER_SHA,'Input independent audit')
    exact(input_audit['inputs_reference'],refs['inputs']);exact(input_audit['publication_reference'],refs['publication'])
    require(input_audit['source_hashes'][str(INPUT_READER)]==INPUT_READER_SHA,'Input audit source map')
    for k,role in (('inputs_reference','inputs'),('publication_reference','publication'),('input_readback_reference','input_audit')):exact(state[k],refs[role])
    exact(state['account'],inputs['inputs']['candidate']);exact(state['original_task'],inputs['inputs']['original_task']);exact(state['task_reference'],inputs['task_reference']);exact(state['calendar'],inputs['inputs']['calendar'])
    task=state['original_task'];require(task['numerical_task_id']==task_id==sha(enc(task['numerical_identity'])) and task['numerical_identity']['cutoff']=='2026-03-20' and task['numerical_identity']['requested_previous_target_weights'] is None,'Dated numerical contract')
    exact(state['candidate_normalization_evidence'],inputs['inputs']['candidate_engine_normalization_evidence'])
    require(control_audit['schema']=='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1' and control_audit['status']=='PASS','Shared control external audit')
    rows=[r for r in control_audit['rows'] if r['track']=='incumbent'];require(len(rows)==1 and rows[0]['status']=='PASS','One shared control reference')
    shared=dict(account={k:inputs['inputs']['incumbent'][k] for k in ('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters')},original_control=inputs['inputs']['original_incumbent_definition'],calendar=inputs['inputs']['calendar'])
    exact(state['common_incumbent_definition'],shared);require(sha(enc(shared))==state['common_incumbent_identity']==post['common_incumbent_identity']==rows[0]['common_incumbent_identity'],'Same shared incumbent, no rerun')
    for obj in (inputs,publication,input_audit):
        for k in ('point_in_time_verified','promotion_allowed','account_executed'):require(obj[k] is False,'No input authority upgrade')
    for obj in (state,started,raw,post):
        for k in ('fit_performed','point_in_time_verified','promotion_allowed','execution_authorized','retry_allowed','independent_accounting_readback_performed'):require(obj[k] is False,'Original account permissions')
    require(type(state['blocked_nonpositive']) is bool,'Exact blocked state')
    for count in (started['planned_engine_call_count'],raw['engine_call_attempt_count'],raw['returned_account_count']):require(type(count) is int and count in (0,1),'Exact execution counts')
    zeros=[s for s,t in state['account']['schedule'][0]['targets'].items() if t['target_weight']==0]
    require(state['blocked_nonpositive'] is bool(zeros),'Nonpositive target boundary')
    if zeros:
        require(raw['status']=='NOT_EXECUTED_NONPOSITIVE_TARGET' and raw['account'] is None and raw['error'] is None and started['planned_engine_call_count']==raw['engine_call_attempt_count']==raw['returned_account_count']==0,'Blocked means no engine call')
        expected='NOT_EXECUTED_NONPOSITIVE_TARGET' if post['error'] is None else 'VALIDATION_FAILURE_RECORDED'
    else:
        require(started['planned_engine_call_count']==raw['engine_call_attempt_count']==1,'One call attempt')
        if raw['error'] is not None:
            require(raw['status']=='ACCOUNT_EXCEPTION' and raw['account'] is None and raw['returned_account_count']==0,'Original no-return exception')
            expected='ACCOUNT_EXCEPTION_NO_RETURNED_RESULT' if enc(post['error'])==enc(raw['error']) else 'VALIDATION_FAILURE_RECORDED'
        else:
            require(raw['status']=='ACCOUNT_RETURNED','Returned envelope')
            expected='VALIDATION_FAILURE_RECORDED' if post['error'] is not None else 'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING'
            if expected=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING':require(type(raw['account']) is dict and raw['returned_account_count']==1,'No false returned completion')
    require(post['status']==expected,'Post terminal classification')
    if expected=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING':exact(raw['account']['source_hashes'],{str(ROOT/k):h for k,h in ENGINE.items()})
    return expected,rows[0]


def readback(task_id,postcheck_reference,*,execute=False):
    canonical(task_id);require(type(execute) is bool and execute,'Explicit execute');require(task_id!=FIRST_TASK,'First candidate already independently read back; reuse its audit')
    folder=ATTEMPTS/task_id;require(Path(postcheck_reference['path'])==folder/'postcheck.json','Fixed candidate postcheck path')
    require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json'},'Unfinalized exact raw namespace only')
    sources={};guard(sources);post=read(postcheck_reference,sources)
    refs=dict(postcheck=postcheck_reference,started=post['started_reference'],raw=post['raw_reference'])
    for key in ('started','raw'):require(Path(refs[key]['path'])==folder/(key+'.json'),'Fixed raw evidence paths')
    started=read(refs['started'],sources);raw=read(refs['raw'],sources);state=started['state']
    for role,key,name in (('inputs','inputs_reference','inputs.json'),('publication','publication_reference','publication.json'),('input_audit','input_readback_reference','independent_readback.json')):
        refs[role]=state[key];require(Path(refs[role]['path'])==INPUT_ROOT/task_id/name,'Fixed audited input paths')
    inputfolder=INPUT_ROOT/task_id;require({p.name for p in inputfolder.iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Successful immutable inputs')
    inputs=read(refs['inputs'],sources);publication=read(refs['publication'],sources);audit=read(refs['input_audit'],sources)
    control_ref=dict(path=str(CONTROL_AUDIT),sha256=CONTROL_AUDIT_SHA);control=read(control_ref,sources)
    for p,h in state['source_hashes'].items():merge(sources,p,h)
    outcome,control_row=validate_evidence(task_id,post,raw,started,inputs,publication,audit,control,refs)
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Independent pure source');merge(sources,str(CORE),CORE_SHA);merge(sources,str(SOURCE),LOADED_SHA);guard(sources)
    accounting=None
    if outcome=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING':
        core=types.ModuleType('_independent_dated_accounting');exec(compile(blob,str(CORE),'exec'),core.__dict__)
        accounting=core.audit_account(execution=raw['account'],account_input=state['account'])
    report=dict(schema='DATED_ACCOUNT_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=task_id,attempt_outcome=outcome,accounting_verified=accounting is not None,accounting=accounting,postcheck_reference=postcheck_reference,raw_reference=refs['raw'],started_reference=refs['started'],inputs_reference=refs['inputs'],input_readback_reference=refs['input_audit'],shared_incumbent_audit_reference=dict(control_ref,json_pointer='/rows/1'),shared_incumbent_result_preserved=deepcopy(control_row),error_preserved=deepcopy(post['error']),source_hashes=sources,reader_sha256=LOADED_SHA,**FLAGS)
    guard(sources);require({p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json'},'No concurrent readback/residue')
    path=folder/'independent_accounting.json';b=enc(report)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    guard(sources);require(path.read_bytes()==b and {p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json','independent_accounting.json'},'Published independent evidence')
    return dict(path=str(path),sha256=sha(b))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task-id',required=True);parser.add_argument('--postcheck-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(readback(args.task_id,dict(path=str(ATTEMPTS/args.task_id/'postcheck.json'),sha256=args.postcheck_sha256),execute=args.execute)))
