"""One new candidate fractional diagnostic; immutable original8 reference only."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib,json,os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_continuous_weight_diagnostic_research.py'
CORE_SHA='bb9c6315548de809184c0b7fae7d7af7d7887b86f3f19abe4e37021d1c6a1a6a'
SEMANTICS=ROOT/'backtest/ndx_challenger_forward_evaluation.py';SEMANTICS_SHA='e80be16c783fce0a28ee9792359bced6e0e9ee786bfe345745ea513af799438e'
OUTPUT=ROOT/'data/cache/research/dated_per_task_continuous_weight_diagnostic_20261003_v1'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
OLD_TASK='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
INPUT_READER=ROOT/'scripts/ndx_dated_account_input_independent_readback_20261003.py'
INPUT_READER_SHA='688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'
PREPARATION=ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'
PREPARATION_SHA='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'
BOUND={
 'control':dict(path=str(ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/diagnostic.json'),sha256='bb81bc97c9bb5564afeab9eed4a1421e40fe5274ae29807ce9994bd7b70b8c7f'),
 'control_publication':dict(path=str(ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/publication.json'),sha256='ad10068b3b2efa98ce13cdef62c52d096c085680343078a8c429daf5225144d8'),
 'control_readback':dict(path=str(ROOT/'DYNAMIC_DATED_CONTINUOUS_INDEPENDENT_READBACK_20261003.json'),sha256='3dca84ea418360f1c039c437614c0887966c665cdfbf4c5c0c99484659d42057'),
 'control_reader':dict(path=str(ROOT/'scripts/ndx_dated_continuous_independent_readback_20261003.py'),sha256='23e527a022ea02673db5367c4ff5c4f6771e54b28a74f1ada66336327fe09ebf')}
FLAGS=dict.fromkeys(('account_executed','fit_performed','raw_prices_decoded','old_audit_repeated','point_in_time_verified','promotion_allowed','formal_cohort_verified','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified','integer_shares_computed','fund_account_computed','control_diagnostic_recomputed','integer_rejection_overridden','weights_normalized'),False)
_CACHE={}


def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def canonical(value):require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Explicit numericID/SHA')
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Explicit immutable reference');canonical(r['sha256'])
def same_ref(a,b,message):
    reference(a);reference(b);require(Path(a['path'])==Path(b['path']) and a['sha256']==b['sha256'],message)
def merge(sources,path,h):require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h

def loads(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)

def guard(sources):
    expected=dict(sources)
    for p,h in ((SOURCE,LOADED_SHA),(CORE,CORE_SHA),(SEMANTICS,SEMANTICS_SHA),(INPUT_READER,INPUT_READER_SHA)):
        merge(expected,str(p),h)
    for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)

def read(r,sources):
    reference(r);blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'Bound input bytes');merge(sources,r['path'],r['sha256']);return loads(blob)


def validate_control(docs):
    d=docs['control'];p=docs['control_publication'];a=docs['control_readback']
    require(d['schema']=='SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1' and d['original_task_preserved']['numerical_task_id']==OLD_TASK,'Original first-task/control result')
    require(p['schema']=='DATED_CONTINUOUS_DIAGNOSTIC_PUBLICATION_V1' and p['status']=='PUBLISHED_CONDITIONAL_FRACTIONAL_DIAGNOSTIC_NOT_ACCOUNT','Original control publication')
    same_ref(p['diagnostic_reference'],BOUND['control'],'Original control bytes');exact(p['source_hashes'],d['source_hashes'],'Control sources')
    require(a['schema']=='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['reader_sha256']==BOUND['control_reader']['sha256'],'Original independent control audit')
    same_ref(a['diagnostic_reference'],BOUND['control'],'Control audit payload');same_ref(a['publication_reference'],BOUND['control_publication'],'Control receipt audit')
    for obj in (d,p,a):
        for k in ('account_executed','fit_performed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(obj[k] is False,'Reference has no account/PIT authority')
    control=d['tracks']['incumbent'];require(control['schema']=='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1' and len(control['path'])==127 and len(control['positions_preserved'])==8,'Complete sole original8 diagnostic')


def load_common():
    sources={};guard(sources);docs={}
    for role,r in BOUND.items():
        if role.endswith('_reader'):
            reference(r);require(sha(Path(r['path']).read_bytes())==r['sha256'],'Control reader source');merge(sources,r['path'],r['sha256'])
        else:docs[role]=read(r,sources)
    validate_control(docs)
    require({p.name for p in Path(BOUND['control']['path']).parent.iterdir()}=={'started.json','diagnostic.json','publication.json'},'Original immutable control namespace')
    for p,h in ((SOURCE,LOADED_SHA),(CORE,CORE_SHA),(SEMANTICS,SEMANTICS_SHA),(INPUT_READER,INPUT_READER_SHA)):merge(sources,str(p),h)
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Consumed frozen core bytes');core=types.ModuleType('_dated_per_task_fractional');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    handle=dict(immutable_control_reference=deepcopy(BOUND['control']));_CACHE[id(handle)]=(handle,docs,sources,core);guard(sources);return handle


def check_task(task_id):
    canonical(task_id);require(task_id!=OLD_TASK,'First candidate already completed; reference it instead of recomputing')
    require(not (OUTPUT/task_id).exists(),'Candidate diagnostic attempt exists; no retry')


def validate_inputs(task_id,docs,refs,control_doc):
    d=docs['inputs'];p=docs['publication'];a=docs['readback'];inp=d['inputs']
    require(d['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and p['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and p['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Published account inputs')
    same_ref(p['inputs_reference'],refs['inputs'],'Published input');exact(p['source_hashes'],d['source_hashes'],'Input source map')
    require(a['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['reader_sha256']==INPUT_READER_SHA and a['source_hashes'][str(INPUT_READER)]==INPUT_READER_SHA,'Independent input readback')
    same_ref(a['inputs_reference'],refs['inputs'],'Audited input');same_ref(a['publication_reference'],refs['publication'],'Audited publication')
    for obj in (d,p,a):
        for k in ('account_executed','fit_performed','point_in_time_verified','promotion_allowed'):require(obj[k] is False,'No source authority')
    task=inp['original_task'];require(task['numerical_task_id']==task_id and sha(encode(task['numerical_identity']))==task_id and task['numerical_identity']['cutoff']=='2026-03-20' and task['numerical_identity']['requested_previous_target_weights'] is None,'New dated task')
    source=d['task_reference'];require(Path(source['path'])==PREPARATION and source['sha256']==PREPARATION_SHA and source['json_pointer'].startswith('/materialized/combinations/'),'New dated preparation binding')
    require(type(inp['valuation_point_count']) is int and inp['valuation_point_count']==127 and type(inp['return_interval_count']) is int and inp['return_interval_count']==126,'Full diagnostic points')
    saved=control_doc['tracks']['incumbent'];exact(inp['calendar'],saved['calendar'],'Common control calendar')
    old=saved['source_references_preserved']['complete_original_track_preserved'];current=inp['incumbent']
    for key in ('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters','original_security_order','original_ticker_by_security'):
        exact(current[key],old[key],'Original control numerical contract unchanged: '+key)
    exact(inp['original_incumbent_definition'],[dict(security_id=s,**dict(ticker=current['original_ticker_by_security'][s],issuer_id=current['schedule'][0]['targets'][s]['issuer_id'],risk_chain=current['risk_chains_by_decision'][inp['calendar'][0]][s],target_weight=current['schedule'][0]['targets'][s]['target_weight'])) for s in current['original_security_order']],'Original8 definition/order')
    require(len(d['original_provenance_and_missing'])==101 and len(d['preserved_evidence_sidecars'])==7,'Full77-pool evidence denominator')

def project_track(inputs,role,input_reference):
    t=inputs[role];calendar=inputs['calendar'];order=t['original_security_order'];schedule=t['schedule']
    require(type(order) is list and len(order)==len(set(order)) and order,'Original unique complete SID order')
    require(len(schedule)==1 and schedule[0]['decision_date']==calendar[0] and schedule[0]['execution_date']==calendar[1],'Single frozen decision/nextOpen')
    targets=schedule[0]['targets'];require(set(targets)==set(order)==set(t['exact_quote_conversion_evidence'])==set(t['original_ticker_by_security']),'Complete targets and quote evidence')
    require(t['transaction_cost_bps']==10 and type(t['transaction_cost_bps']) is int and t['weights_normalized'] is False and t['nominal_prices_adjusted_again'] is False,'Original weight and nominal convention')
    require(t['initial_holdings']=={} and t['external_cashflows']==[] and t['identity_events']==[],'All-cash single entry without later funding')
    positions=[];quotes={};events=[]
    for sid in order:
        target=targets[sid];require(target['ticker']==t['engine_ticker_by_security'][sid],'Original SID-to-engine alias')
        positions.append(dict(security_id=sid,ticker=t['original_ticker_by_security'][sid],issuer_id=target['issuer_id'],target_weight=deepcopy(target['target_weight'])))
        rows=t['exact_quote_conversion_evidence'][sid];require([r['session'] for r in rows]==calendar,'All127 same dates')
        quotes[sid]=[]
        for row in rows:
            values={}
            for field in ('open','close'):
                evidence=row[field];require(type(evidence['exact']) is str,'Saved Fraction string only');n=Fraction(evidence['exact']);require(n>0,'Positive original nominal')
                require(type(evidence['value']) is float and float(n)==evidence['value'] and evidence['value'].hex()==evidence['float_hex'],'Saved float conversion crosslink')
                values['nominal_'+field+'_exact']=dict(numerator=str(n.numerator),denominator=str(n.denominator))
            quotes[sid].append(dict(session=row['session'],**values))
        bindings=t['split_evidence_preserved'][sid]
        for b in bindings:
            e=b['event'];require(e['security_id']==sid and e in t['corporate_actions'],'Every explicit action bound to correct SID')
            reference({k:b['policy_reference'][k] for k in ('path','sha256')})
            for key in ('new_shares','old_shares'):require(type(e[key]) is int and e[key]>0,'Split integer ratio')
            events.append(dict(security_id=sid,effective_session=e['session'],numerator=str(e['new_shares']),denominator=str(e['old_shares']),source_reference=deepcopy(b['policy_reference']),original_event_preserved=deepcopy(e)))
    exact([b['event'] for sid in order for b in t['split_evidence_preserved'][sid]],t['corporate_actions'],'No dropped or extra split actions')
    if role=='incumbent':
        require(len(order)==8,'Original8 complete');original=inputs['original_incumbent_definition'];exact([r['security_id'] for r in original],order,'Original8 order')
        exact([r['target_weight'] for r in original],[r['target_weight'] for r in positions],'Original8 weights unchanged')
    else:
        exact({r['security_id']:r['target_weight'] for r in positions},{sid:r['target_weight'] for sid,r in inputs['original_fit_result']['targets'].items()},'Raw saved candidate weights, not engine normalized')
    return dict(calendar=deepcopy(calendar),positions=positions,nominal_quotes=quotes,split_events=events,transaction_cost_bps=10,source_references=dict(inputs=dict(input_reference,json_pointer='/inputs/'+role),complete_original_track_preserved=deepcopy(t)))

def assemble(task_id,docs,refs,control_doc,core):
    validate_inputs(task_id,docs,refs,control_doc)
    inp=docs['inputs']['inputs']
    args=project_track(inp,'candidate',refs['inputs'])
    result=core.diagnose_continuous_weights(**args)
    require(result['schema']=='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1' and result['calendar']==inp['calendar'] and len(result['path'])==127 and result['weights_normalized'] is False,'Only complete candidate diagnostic')
    exact(result['positions_preserved'],args['positions'],'Original candidate weights preserved')
    return dict(schema='SOURCE_BOUND_DATED_PER_TASK_CONTINUOUS_DIAGNOSTIC_V1',numerical_task_id=task_id,candidate=result,immutable_control_reference=dict(BOUND['control'],json_pointer='/tracks/incumbent'),immutable_control_publication_reference=deepcopy(BOUND['control_publication']),immutable_control_readback_reference=deepcopy(BOUND['control_readback']),candidate_core_call_count=1,control_core_call_count=0,input_references=deepcopy(refs),original_task_preserved=deepcopy(inp['original_task']),original_input_limitations=deepcopy(inp['limitations']),original_provenance_and_missing=deepcopy(docs['inputs']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['inputs']['preserved_evidence_sidecars']),integer_account_status_consumed=False,integer_execution_or_rejection_inferred=False,evaluation_interval_previously_used_for_fitting=True,**FLAGS)


def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Durable evidence changed');return dict(path=str(path),sha256=sha(blob))


def run(task_id,inputs_reference,input_readback_reference,*,execute=False,common=None):
    require(type(execute) is bool and execute,'Explicit execute=True required');check_task(task_id)
    if common is None:common=load_common()
    stored=_CACHE.get(id(common));require(stored is not None and stored[0] is common,'Only issued common handles')
    _,control_docs,base_sources,core=stored;exact(common,dict(immutable_control_reference=BOUND['control']),'Unmodified common handle')
    sources=dict(base_sources);guard(sources)
    folder=INPUT_ROOT/task_id
    require(Path(inputs_reference['path'])==folder/'inputs.json' and Path(input_readback_reference['path'])==folder/'independent_readback.json','Explicit task namespace references')
    require({p.name for p in folder.iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Successful audited input namespace')
    audit=read(input_readback_reference,sources);refs=dict(inputs=deepcopy(inputs_reference),readback=deepcopy(input_readback_reference),publication=deepcopy(audit['publication_reference']))
    require(Path(refs['publication']['path'])==folder/'publication.json','Exact publication path')
    docs=dict(readback=audit,inputs=read(refs['inputs'],sources),publication=read(refs['publication'],sources))
    validate_inputs(task_id,docs,refs,control_docs['control']);guard(sources);check_task(task_id);output=OUTPUT/task_id;output.mkdir(parents=True,exist_ok=False)
    try:
        save(output/'started.json',dict(schema='DATED_PER_TASK_CONTINUOUS_STARTED_V1',task_id=task_id,input_references=refs,immutable_control_reference=BOUND['control'],planned_candidate_core_call_count=1,planned_control_core_call_count=0,source_hashes=sources,**FLAGS))
        result=assemble(task_id,docs,refs,control_docs['control'],core);result['source_hashes']=sources
        guard(sources);out=save(output/'diagnostic.json',result);guard(sources)
        require({p.name for p in output.iterdir()}=={'started.json','diagnostic.json'},'Unexpected pre-publication file')
        receipt=save(output/'publication.json',dict(schema='DATED_PER_TASK_CONTINUOUS_PUBLICATION_V1',status='PUBLISHED_CANDIDATE_DIAGNOSTIC_WITH_IMMUTABLE_CONTROL_REFERENCE',diagnostic_reference=out,source_hashes=sources,**FLAGS))
        guard(sources)
        require({p.name for p in output.iterdir()}=={'started.json','diagnostic.json','publication.json'},'Unexpected publication file')
        for r in (out,receipt):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final evidence changed')
        return out
    except Exception as e:save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task-id',required=True);p.add_argument('--inputs-sha256',required=True);p.add_argument('--input-readback-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.task_id,dict(path=str(INPUT_ROOT/a.task_id/'inputs.json'),sha256=a.inputs_sha256),dict(path=str(INPUT_ROOT/a.task_id/'independent_readback.json'),sha256=a.input_readback_sha256),execute=a.execute)))
