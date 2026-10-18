"""Current sealed gap/calendar evidence adapter; no production observation writer."""
import argparse
import base64
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_gap_candidate_calendar_research.py';CORE_SHA='200e34dcc409c78220cdeddf88f25c1122c5b4992960e1d1e174f46ce9a95cb7'
OUTPUT=ROOT/'data/cache/research/gap_candidate_calendar_adapter_20261003_v1'
BOUND={
 'contract':('DYNAMIC_GAP_MONTHLY_CANDIDATE_LINEAGE_NEXT_CONTRACT_20261003.md','b4bd751f382d4c20850edbc5588bffadf4b0aa0db16e322b800afc544372b489'),
 'user_choice':('DYNAMIC_GAP_MONTHLY_POLICY_USER_DECISION_20261002.md','f661616a86dca8e80aa3e8bcea1b55c29b97760e993948049327fe1a38d84906'),
 'policy':('data/cache/research/gap_monthly_policy_20261002_v1/policy.json','d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'),
 'policy_publication':('data/cache/research/gap_monthly_policy_20261002_v1/publication.json','23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'),
 'frontier':('data/cache/research/observation_gap_frontier_20261002_v1/frontier.json','a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170'),
 'frontier_publication':('data/cache/research/observation_gap_frontier_20261002_v1/publication.json','36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44'),
 'ledger':('data/cache/research/observation_gap_ledger_20261002_v1/ledger.json','8c15643e8ccf0b4356f235b43bb29152d98be2c9e71c3f16310f6a1d7d12e67d'),
 'ledger_publication':('data/cache/research/observation_gap_ledger_20261002_v1/publication.json','6d36f4e420dd4fe959c1d88cb3b68b133ccce57ed6ad316b9d99ba1b7e411d7d'),
 'parent_sessions':('data/cache/research/observation_gap_ledger_20261002_v1/parent_sessions.csv','f78183b85d8e83b5037d3c4b77b2a8662af451def7a0411bbc26f82e1081f2e2'),
 'capture':('data/cache/research/forward_source_capture_scoped_20261002_v1/capture.json','25fa0d8664c51945384fb6a2e720b86d66965ddeff31ed005b0cd9a74d0dff1c'),
 'capture_publication':('data/cache/research/forward_source_capture_scoped_20261002_v1/publication.json','29e0423c6ef7241fd27fb60def7d7ef8bb67680505fd097660a499ea72678537'),
}
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','old_calendar_mutated','old_generator_called','new_observation_receipt_created','production_lineage_ready','network_capture_performed','old_audit_repeated','gap_ledger_validation_reexecuted','full_transitive_source_closure_reverified','fresh_observation'),False)
FIELDS=['Date','Open','High','Low','Close','Volume']
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def loads(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)

def scope_dates(blob,evidence,scope_start):
    """Verify byte/row projection only; never rerun old OHLC/capture audit."""
    require(sha(blob)==evidence['original_sha256'] and base64.b64decode(evidence['original_csv_bytes_base64'],validate=True)==blob,'Full original capture bytes')
    reader=csv.DictReader(io.StringIO(blob.decode('utf-8-sig'),newline=''));require(reader.fieldnames==FIELDS,'Original CSV header');rows=list(reader)
    require(type(evidence['original_row_count']) is int and evidence['original_row_count']==len(rows),'Original row count')
    exact([r['raw_csv_row'] for r in evidence['original_rows']],rows,'Exact original row evidence')
    included=[];excluded=[]
    for i,(r,ev) in enumerate(zip(rows,evidence['original_rows'])):
        keep=r['Date']>=scope_start
        require(type(ev['original_data_row_index']) is int and ev['original_data_row_index']==i and ev['session']==r['Date'] and ev['included_in_scoped_csv'] is keep,'Exact source index/scope')
        (included if keep else excluded).append(i)
    exact(evidence['included_original_row_indexes'],included,'Full scoped selection');exact(evidence['excluded_original_row_indexes'],excluded,'Full excluded dates')
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator='\n');writer.writeheader();writer.writerows(rows[i] for i in included);scoped=stream.getvalue().encode()
    require(scoped==evidence['scoped_csv_utf8'].encode() and sha(scoped)==evidence['scoped_sha256'],'Exact scoped derived bytes')
    return [rows[i]['Date'] for i in included]

def project_inputs(docs,refs,artifacts):
    p=docs['policy'];front=docs['frontier'];capture=docs['capture'];scoped=capture['plan'];plan=scoped['capture_plan'];ledger=docs['ledger']
    for role,status,field in [('policy','PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','policy_reference'),('frontier','PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY','frontier_reference'),('capture','PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','capture_reference')]:
        receipt=docs[role+'_publication'];require(receipt['status']==status,'Successful source receipt');exact(receipt[field],refs[role],'Source receipt target');exact(receipt['source_hashes'],docs[role]['source_hashes'],'Source receipt source map')
        for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(receipt[k] is False and docs[role][k] is False,'No source permission upgrade')
    require(p['schema']=='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and p['policy_id']==POLICY,'Selected policy source');exact(p['user_choice_reference'],refs['user_choice'],'Explicit user policy record');exact(p['frontier_reference'],refs['frontier'],'Policy frontier')
    require(front['schema']=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1' and front['last_observed_session']=='2026-09-24' and front['last_accounted_session']=='2026-10-01','Frozen distinct cursors')
    exact(front['input_references']['ledger'],refs['ledger'],'Saved gap source');exact(front['input_references']['publication'],refs['ledger_publication'],'Saved gap receipt');exact(front['input_references']['parent_sessions'],refs['parent_sessions'],'Original session bytes')
    lr=docs['ledger_publication'];require(lr['status']=='PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY','Completed gap evidence receipt');exact(lr['artifacts']['ledger'],refs['ledger'],'Gap publication target')
    for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(lr[k] is False and ledger[k] is False,'Gap grants no observation authority')
    require(type(ledger['missed_observation_count']) is int and ledger['missed_observation_count']==5 and len(ledger['events'])==5,'Five sealed gap records only')
    known=p['projection_inputs']['known_rows'];require(len(known)==65 and p['projection_inputs']['new_prospective_observations']==[] and type(p['new_observation_count']) is int and p['new_observation_count']==0,'Current frozen prefix, no observations synthesized')
    exact(p['saved_frontier_rows'],front['known_accounted_rows'],'Complete original frontier');exact([r['input_row'] for r in p['projection']['rows']],known,'Policy full prefix projection')
    require(len(front['known_accounted_rows'])==65,'Complete65 frontier rows, no zip truncation')
    exact([{k:r[k] for k in ('session','kind')} for r in known],[{k:r[k] for k in ('session','kind')} for r in front['known_accounted_rows']],'Full typed coordinates match frontier')
    for i,(row,old) in enumerate(zip(known,front['known_accounted_rows'])):
        require(row['sequence']==i+1 and type(row['sequence']) is int and row['session']==old['session'] and row['kind']==old['kind'],'Exact saved typed coordinates');exact(row['evidence_reference'],dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),'Pointer content identity')
        require(row['seal_status']==('UNKNOWN' if i<60 else 'NOT_ATTEMPTED') and row['kind']==('SEALED_PARENT_OBSERVED_SESSION' if i<60 else 'MISSED_OBSERVATION'),'All60 UNKNOWN and5 MISSED preserved')
    require(capture['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1' and scoped['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1' and plan['schema']=='FORWARD_SOURCE_CAPTURE_PLANNING_V1','Independent capture schema, not observation receipt')
    exact(capture['input_references']['frontier'],refs['frontier'],'Capture frontier');exact(plan['accounted_prefix_dates'],[r['session'] for r in known],'Complete capture prefix')
    require(plan['capture_started_at_utc']==capture['capture_started_at_utc'] and plan['observed_at_utc']==capture['observed_at_utc'],'Saved capture interval')
    require(scoped['scope_start']==known[0]['session'] and scoped['full_original_bytes_preserved'] is True and scoped['fresh_observation'] is False and plan['fresh_observation'] is False,'Capture cannot become observed')
    source_dates={}
    for role in ('source','baseline'):
        for ticker in ('QQQ','SPY'):
            ev=scoped['csv_scope_evidence'][role][ticker];blob=artifacts[role+'_'+ticker];dates=scope_dates(blob,ev,scoped['scope_start'])
            require(scoped['original_'+role+'_sha256'][ticker]==sha(blob) and plan[('source' if role=='source' else 'baseline')+'_sha256'][ticker]==ev['scoped_sha256'],'Full/scoped hash roles not interchangeable')
            if role=='source':source_dates[ticker]=dates
    tzif=artifacts['tzif'];require(sha(tzif)==plan['tzif_sha256']==capture['captured_artifacts']['tzif']['sha256'],'Actual captured TZif bytes')
    return dict(policy_id=POLICY,known_typed_rows=deepcopy(known),new_observation_evidence=[],decision_session=None,capture_reference=deepcopy(refs['capture']),clock_evidence=dict(tzif_bytes=tzif,tzif_reference=deepcopy(capture['captured_artifacts']['tzif']),seal_evaluation_at_utc=None),source_references=dict(coverage_reference=dict(refs['capture'],json_pointer='/plan/csv_scope_evidence'),references=[deepcopy(v) for v in refs.values()],complete_source_session_dates=source_dates,revisions=deepcopy(plan['revisions'])))

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Source bytes drift '+path)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Pure source pin pending');docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    def read(ref):
        path=Path(ref['path']);h=ref['sha256'];require(str(path) not in sources or sources[str(path)]==h,'Source hash conflict');b=path.read_bytes();require(sha(b)==h,'Source byte pin');sources[str(path)]=h;return b
    for role,(relative,h) in BOUND.items():
        ref=dict(path=str(ROOT/relative),sha256=h);blob=read(ref);refs[role]=ref
        if role not in ('contract','user_choice','parent_sessions'):docs[role]=loads(blob)
    for role,filename in [('policy','policy.json'),('frontier','frontier.json')]:require({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'started.json',filename,'publication.json'},'Completed immutable source namespace')
    require({p.name for p in Path(refs['capture']['path']).parent.iterdir()}=={'started.json','capture.json','publication.json','QQQ.csv','SPY.csv','New_York.tzif'},'Completed current capture namespace')
    require(not (Path(refs['ledger']['path']).parent/'failure.json').exists(),'Failed gap publication cannot be used')
    capture=docs['capture'];artifacts={}
    for ticker in ('QQQ','SPY'):
        artifacts['source_'+ticker]=read(capture['captured_artifacts'][ticker]);artifacts['baseline_'+ticker]=read(capture['input_references']['baseline_'+ticker])
    artifacts['tzif']=read(capture['captured_artifacts']['tzif']);blob=read(dict(path=str(CORE),sha256=CORE_SHA));guard(sources)
    core=types.ModuleType('_fresh_gap_candidate_calendar');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,artifacts,core
def save(path,value):
    b=encoded(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Output bytes');return dict(path=str(path),sha256=sha(b))
def run(*,execute=False):
    require(type(execute) is bool,'Exact execute bool');require(not OUTPUT.exists(),'Immutable adapter namespace')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    docs,refs,sources,artifacts,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(input_references=refs,source_hashes=sources,retry_allowed=False,**FLAGS))
        args=project_inputs(docs,refs,artifacts);value=core.prepare_candidate_calendar_evidence(**args)
        require(value['schema']=='GAP_AWARE_CANDIDATE_CALENDAR_EVIDENCE_V1' and value['status']=='BLOCKED' and 'NO_NEW_OBSERVATION_EVIDENCE' in value['reasons'] and value['selected_row'] is None and value['calendar_prerequisites_conditionally_satisfied'] is False and value['new_observation_evidence_preserved']==[],'Current adapter cannot create observation or candidate')
        for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','production_lineage_ready'):require(value[k] is False,'Adapter result permission')
        exact(value['known_typed_rows_preserved'],args['known_typed_rows'],'Entire old prefix unchanged')
        document=dict(schema='SOURCE_BOUND_GAP_CANDIDATE_CALENDAR_EVIDENCE_V1',evidence=value,input_references=refs,source_hashes=sources,original_capture_plan_preserved=deepcopy(docs['capture']['plan']),current_capture_interval=dict(start=docs['capture']['capture_started_at_utc'],end=docs['capture']['observed_at_utc']),missing_production_contract='PERSISTED_OBSERVATION_RECEIPT_AND_SEAL_STATUS_EVENT_HISTORY_NOT_DEFINED',**FLAGS)
        guard(sources);out=save(OUTPUT/'evidence.json',document);guard(sources)
        pub=save(OUTPUT/'publication.json',dict(schema='GAP_CANDIDATE_CALENDAR_EVIDENCE_PUBLICATION_V1',status='PUBLISHED_BLOCKED_EVIDENCE_ONLY_NO_OBSERVATION',evidence_reference=out,source_hashes=sources,**FLAGS));guard(sources)
        require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(pub['path']).read_bytes())==pub['sha256'] and {p.name for p in OUTPUT.iterdir()}=={'started.json','evidence.json','publication.json'},'Final immutable readback');return out
    except Exception as exc:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
