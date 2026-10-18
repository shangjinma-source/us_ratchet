"""One immutable dated account attempt; original eight control runs only once."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_dynamic_frozen_execution_research as candidate
from backtest import ndx_dynamic_frozen_incumbent_control as incumbent

OUTPUT=ROOT/'data/cache/research/dated_account_execution_20261003_v1'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
INPUT_READER=ROOT/'scripts/ndx_dated_account_input_independent_readback_20261003.py'
INPUT_READER_SHA='688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'
ENGINE_PINS={
 'backtest/ndx_dynamic_frozen_execution_research.py':'69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b',
 'backtest/ndx_dynamic_frozen_incumbent_control.py':'537908ef0447b1e4e7104afdd2008d4d3d04b60f820bfaab33562dc7114f54e6',
 'backtest/ndx_dynamic_whole_lot_path.py':'3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
 'backtest/ndx_dynamic_whole_lot_repair_path.py':'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
 'backtest/ndx_whole_lot_repair_diagnostic.py':'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
 'backtest/ndx_split_accounting_research.py':'11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(pd.__file__).resolve(),Path(np.__file__).resolve())}
LOADED.update(candidate._LOADED_SOURCES);LOADED[str(Path(incumbent.__file__).resolve())]=incumbent._LOADED_SHA
FLAGS=dict.fromkeys(('fit_performed','winner_selected','economic_comparison_performed','independent_accounting_readback_performed','promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','historical_identity_verified','untouched_holdout','future_independent_oos','corporate_action_completeness_verified','dividend_cash_flows_modelled','total_return_modelled','runtime_binary_closure_verified','retry_allowed','full_transitive_source_closure_reverified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return sha(encode(value))
def exact(a,b,message):require(encode(a)==encode(b),message)
def canonical(value):require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Explicit SHA/ID')
def runtime():return dict(python=sys.version,implementation=platform.python_implementation(),executable=str(Path(sys.executable).resolve()),platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__)


def merge(sources,other):
    for path,h in other.items():
        canonical(h);require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h


def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)


def read(reference,sources):
    require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact external reference');canonical(reference['sha256'])
    blob=Path(reference['path']).read_bytes();require(sha(blob)==reference['sha256'],'Input byte drift');merge(sources,{reference['path']:reference['sha256']});return loads(blob)


def guard(sources):
    expected=dict(sources);merge(expected,LOADED)
    for relative,h in ENGINE_PINS.items():
        path=str((ROOT/relative).resolve());require(LOADED.get(path)==h,'Loaded frozen engine differs');merge(expected,{path:h})
    for path,h in expected.items():require(sha(Path(path).read_bytes())==h,'Source drift: '+path)


def destination(track,task_id):
    require(track in ('candidate','incumbent'),'Explicit track');canonical(task_id)
    return OUTPUT/'candidates'/task_id if track=='candidate' else OUTPUT/'incumbent'


def prepare(track,inputs_reference,input_readback_reference):
    require(track in ('candidate','incumbent'),'Explicit account track');canonical(INPUT_READER_SHA)
    sources=dict(LOADED);guard(sources);merge(sources,{str(INPUT_READER):INPUT_READER_SHA});guard(sources)
    audit=read(input_readback_reference,sources)
    require(audit['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['reader_sha256']==INPUT_READER_SHA,'New input audit required')
    require(audit['source_hashes'][str(INPUT_READER)]==INPUT_READER_SHA,'Readback source map reader binding')
    for key in ('producer_called','fit_performed','account_executed','old_raw_audit_repeated','point_in_time_verified','promotion_allowed'):require(audit[key] is False,'Readback authority boundary')
    exact(audit['inputs_reference'],inputs_reference,'Explicit audited input')
    document=read(inputs_reference,sources);publication=read(audit['publication_reference'],sources)
    require(document['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and publication['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and publication['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Input/publication schema')
    exact(publication['inputs_reference'],inputs_reference,'Publication payload');exact(publication['source_hashes'],document['source_hashes'],'Publication source closure')
    merge(sources,document['source_hashes'])
    inputs=document['inputs'];task=inputs['original_task'];task_id=task['numerical_task_id'];canonical(task_id)
    folder=INPUT_ROOT/task_id
    require(Path(inputs_reference['path'])==folder/'inputs.json' and Path(audit['publication_reference']['path'])==folder/'publication.json','Fixed audited input namespace')
    require(Path(input_readback_reference['path'])==folder/'independent_readback.json','Fixed colocated independent readback')
    require({p.name for p in folder.iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Failed/orphan input namespace')
    for obj in (document,inputs,publication):
        for key in ('fit_performed','point_in_time_verified','promotion_allowed','execution_authorized'):require(obj[key] is False,'No authority upgrade')
    identity=task['numerical_identity'];require(identity['cutoff']=='2026-03-20' and identity['requested_previous_target_weights'] is None and digest(identity)==task_id,'New task identity')
    account=inputs[track];calendar=inputs['calendar']
    require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[0]=='2026-03-20' and calendar[1]=='2026-03-23' and calendar[-1]=='2026-09-21','Single fixed calendar')
    require(account['initial_cash_usd']==25000 and account['minimum_cash_buffer_usd']==100 and account['transaction_cost_bps']==10 and account['external_cashflows']==[] and account['initial_holdings']=={},'Original cash/fee/no flows')
    require(account['valuation_end_date']==calendar[-1] and len(account['schedule'])==1 and account['schedule'][0]['decision_date']==calendar[0] and account['schedule'][0]['execution_date']==calendar[1],'Freeze then nextOpen')
    require(account['matrices']['open']['index']==account['matrices']['close']['index']==calendar,'Exact account calendar')
    weights=account['schedule'][0]['targets'];zeros=[s for s,t in weights.items() if t['target_weight']==0]
    require(all(type(t['target_weight']) in (int,float) and math.isfinite(t['target_weight']) and t['target_weight']>=0 for t in weights.values()),'Finite original targets')
    exact(account['engine_input_compatibility']['nonpositive_target_security_ids'],zeros,'Zero target evidence')
    require(account['engine_input_compatibility']['status']==('BLOCKED_NONPOSITIVE_TARGET' if zeros else 'REQUIRES_FROZEN_VALIDATION'),'Explicit compatibility state')
    shared=dict(account={k:deepcopy(inputs['incumbent'][k]) for k in ('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters')},original_control=inputs['original_incumbent_definition'],calendar=calendar)
    state=dict(track=track,numerical_task_id=task_id,task_reference=document['task_reference'],inputs_reference=deepcopy(inputs_reference),input_readback_reference=deepcopy(input_readback_reference),publication_reference=deepcopy(audit['publication_reference']),account=deepcopy(account),calendar=deepcopy(calendar),common_incumbent_identity=digest(shared),common_incumbent_definition=deepcopy(shared),candidate_normalization_evidence=deepcopy(inputs['candidate_engine_normalization_evidence']),original_task=deepcopy(task),engine_security_keys=deepcopy(inputs['engine_security_keys']),source_hashes=sources,runtime=runtime(),blocked_nonpositive=bool(zeros),**FLAGS)
    guard(sources);return state


def engine_arguments(account,track):
    kwargs={k:deepcopy(account[k]) for k in ('schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','valuation_end_date','transaction_cost_bps')}
    if track=='candidate':kwargs['identity_events']=deepcopy(account['identity_events'])
    for output,field in (('opens','open'),('closes','close')):
        matrix=account['matrices'][field];kwargs[output]=pd.DataFrame(matrix['data'],index=pd.to_datetime(matrix['index']),columns=matrix['columns'])
    kwargs.update(account['risk_parameters']);return kwargs


def execute_engine(state):
    fn=candidate.simulate_dynamic_frozen_execution_research if state['track']=='candidate' else incumbent.simulate_dynamic_frozen_incumbent_control
    return fn(**engine_arguments(state['account'],state['track']))


def save(path,value):
    blob=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Saved evidence drift');return dict(path=str(path),sha256=sha(blob))


def validate_returned(state,value):
    schema='ndx_dynamic_frozen_execution_research_v2' if state['track']=='candidate' else 'ndx_dynamic_frozen_incumbent_control_v1'
    require(value['schema']==schema and [r['session'] for r in value['daily']]==state['calendar'],'Returned account schema/fullcalendar')
    first=value['daily'][0];require(first['shares']=={} and first['cash_usd']==first['total_value_usd']==25000,'Original first cash point')
    require(value['point_in_time_verified'] is False and value['promotion_allowed'] is False and value['dividend_modelled'] is False,'Returned research limits')
    expected={str((ROOT/p).resolve()):h for p,h in ENGINE_PINS.items() if state['track']=='incumbent' or 'incumbent_control' not in p}
    exact(value['source_hashes'],expected,'Frozen account source closure')
    require(all(math.isfinite(r['cash_usd']) and math.isfinite(r['total_value_usd']) and all(type(q) is int and q>=0 for q in r['shares'].values()) for r in value['daily']),'Finite account/whole shares')


def run(track,inputs_reference,input_readback_reference,*,execute=False):
    require(type(execute) is bool and execute,'Explicit execute=True required')
    require(track in ('candidate','incumbent'),'Explicit track')
    if track=='incumbent':require(not (OUTPUT/'incumbent').exists(),'Original control already attempted; reuse only by external reference')
    # The fixed input directory names its numerical identity before any preparation.
    task_id=Path(inputs_reference['path']).parent.name;canonical(task_id);folder=destination(track,task_id)
    require(not folder.exists(),'Attempt evidence exists; no retry')
    state=prepare(track,inputs_reference,input_readback_reference);require(state['numerical_task_id']==task_id,'Input directory identity');guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed before start')
    folder.mkdir(parents=True,exist_ok=False)
    started_ref=save(folder/'started.json',dict(schema='DATED_ACCOUNT_STARTED_V1',state=state,planned_engine_call_count=0 if state['blocked_nonpositive'] else 1,**FLAGS))
    result=None;error=None;called=False
    if not state['blocked_nonpositive']:
        called=True
        try:result=execute_engine(state)
        except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
    raw_status='NOT_EXECUTED_NONPOSITIVE_TARGET' if state['blocked_nonpositive'] else ('ACCOUNT_EXCEPTION' if error else 'ACCOUNT_RETURNED')
    raw_ref=save(folder/'raw.json',dict(schema='DATED_ACCOUNT_RAW_V1',status=raw_status,started_reference=started_ref,account=result,error=error,engine_call_attempt_count=int(called),returned_account_count=int(result is not None),source_hashes=state['source_hashes'],runtime=state['runtime'],**FLAGS))
    post_error=error
    try:
        guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed after account')
        require({p.name for p in folder.iterdir()}=={'started.json','raw.json'},'Unexpected attempt evidence')
        for r in (started_ref,raw_ref):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Durable raw/started changed')
        if not state['blocked_nonpositive'] and error is None:
            require(type(result) is dict,'Engine returned no account mapping')
            validate_returned(state,result)
        guard(state['source_hashes']);require(runtime()==state['runtime'],'Runtime changed during postcheck')
    except Exception as exc:post_error=dict(type=type(exc).__name__,message=str(exc))
    status=('ACCOUNT_EXCEPTION_NO_RETURNED_RESULT' if error and post_error==error else 'VALIDATION_FAILURE_RECORDED') if post_error else ('NOT_EXECUTED_NONPOSITIVE_TARGET' if state['blocked_nonpositive'] else 'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING')
    # Display labels only, never mutate returned account ticker keys.
    display={s:state['account']['original_ticker_by_security'][s] for s in state['account']['original_security_order']}
    return save(folder/'postcheck.json',dict(schema='DATED_ACCOUNT_POSTCHECK_V1',track=track,numerical_task_id=task_id,status=status,started_reference=started_ref,raw_reference=raw_ref,error=post_error,common_incumbent_identity=state['common_incumbent_identity'],display_original_ticker_by_security=display,**FLAGS))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--track',choices=['candidate','incumbent'],required=True);parser.add_argument('--inputs-path',required=True);parser.add_argument('--inputs-sha256',required=True);parser.add_argument('--input-readback-path',required=True);parser.add_argument('--input-readback-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.track,dict(path=args.inputs_path,sha256=args.inputs_sha256),dict(path=args.input_readback_path,sha256=args.input_readback_sha256),execute=args.execute)))
