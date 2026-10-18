"""Source-bound fractional diagnostic. Never dispatches an integer account."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib,json,os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_continuous_weight_diagnostic_research.py'
CORE_SHA='bb9c6315548de809184c0b7fae7d7af7d7887b86f3f19abe4e37021d1c6a1a6a'
SEMANTICS=ROOT/'backtest/ndx_challenger_forward_evaluation.py'
SEMANTICS_SHA='e80be16c783fce0a28ee9792359bced6e0e9ee786bfe345745ea513af799438e'
OUTPUT=ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1'
# Both bytes and the independently published receipt contract must be supplied
# by root. A live completed directory is never searched for suitable results.
BOUND={
 'inputs':dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1/89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3/inputs.json'),sha256='ac0201e24925dff189d25e4fb5f0a8c741d567c31060f2aa48e3e2232fd90409'),
 'publication':dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1/89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3/publication.json'),sha256='c1f4ed8910725b5451c3cfa63f9545ded929f36d9abdba9586b3fe086386ff60'),
 'readback':dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1/89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3/independent_readback.json'),sha256='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3'),
}
READBACK_SCHEMA='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1'
FLAGS=dict.fromkeys(('account_executed','fit_performed','raw_prices_decoded','old_audit_repeated','point_in_time_verified','promotion_allowed','formal_cohort_verified','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified','integer_shares_computed','fund_account_computed'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def loads(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Explicit immutable reference')
def guard(sources):
    expected=dict(sources)
    for p,h in ((SOURCE,LOADED_SHA),(CORE,CORE_SHA),(SEMANTICS,SEMANTICS_SHA)):
        require(str(p) not in expected or expected[str(p)]==h,'Source conflict');expected[str(p)]=h
    for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)

def validate_receipts(docs,refs):
    require(READBACK_SCHEMA is not None,'Independent readback schema pending')
    d=docs['inputs'];p=docs['publication'];a=docs['readback']
    require(d['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and p['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and p['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Completed inputs publication')
    exact(p['inputs_reference'],refs['inputs'],'Published exact input bytes');exact(p['source_hashes'],d['source_hashes'],'Publication source map')
    require(a['schema']==READBACK_SCHEMA and a['status']=='PASS','External independent receipt')
    exact(a['inputs_reference'],refs['inputs'],'Audit input anchor');exact(a['publication_reference'],refs['publication'],'Audit publication anchor')
    for obj in (d,p,a):
        for k in ('point_in_time_verified','promotion_allowed','account_executed'):require(obj[k] is False,'No authority upgrade')

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

def assemble(docs,refs,core):
    validate_receipts(docs,refs);inp=docs['inputs']['inputs'];require(inp['valuation_point_count']==127 and inp['return_interval_count']==126,'Single evaluation window')
    results={role:core.diagnose_continuous_weights(**project_track(inp,role,refs['inputs'])) for role in ('candidate','incumbent')}
    return dict(schema='SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1',tracks=results,input_references=deepcopy(refs),original_task_preserved=deepcopy(inp['original_task']),original_input_limitations=deepcopy(inp['limitations']),original_provenance_and_missing=deepcopy(docs['inputs']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['inputs']['preserved_evidence_sidecars']),control_computation_scope='FIRST_EXPLICIT_DUAL_TRACK_ONLY;LATER_BATCH_REQUIRES_SEPARATE_IMMUTABLE_CONTROL_REFERENCE',evaluation_interval_previously_used_for_fitting=True,**FLAGS)

def load_inputs():
    require(all(v is not None for v in BOUND.values()) and READBACK_SCHEMA is not None,'Input/publication/audit pins pending');sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA,str(SEMANTICS):SEMANTICS_SHA};docs={};refs=deepcopy(BOUND);guard(sources)
    for role,r in refs.items():
        reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Parent bytes');require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Parent hash conflict');sources[r['path']]=r['sha256'];docs[role]=loads(b)
    folder=Path(refs['inputs']['path']).parent;require({p.name for p in folder.iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Successful sealed audited input namespace')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Consumed core bytes');core=types.ModuleType('_dated_continuous');exec(compile(blob,str(CORE),'exec'),core.__dict__);guard(sources);return docs,refs,sources,core
def save(path,v):
    b=encode(v)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Written bytes');return dict(path=str(path),sha256=sha(b))
def run(*,execute=False):
    require(type(execute) is bool and not OUTPUT.exists(),'Exact execute and new namespace')
    if not execute:return dict(status='NOT_EXECUTED')
    docs,refs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(input_references=refs,source_hashes=sources,**FLAGS));result=assemble(docs,refs,core);result['source_hashes']=sources;guard(sources);out=save(OUTPUT/'diagnostic.json',result);guard(sources)
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_CONTINUOUS_DIAGNOSTIC_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_FRACTIONAL_DIAGNOSTIC_NOT_ACCOUNT',diagnostic_reference=out,source_hashes=sources,**FLAGS));guard(sources)
        for r in (out,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output bytes')
        return out
    except Exception as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
