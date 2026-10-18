"""First new-schema observation writer, pending future source anchors.

No current capture is silently upgraded to an observation. Later receipts and
seal-state events need a separate version; this namespace admits one attempt.
"""
import argparse,hashlib,json,os,platform,sys,types
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_prospective_observation_receipt_research.py';CORE_SHA='6a088c05321b9e9a407765190800acb9443f8f5de6f1c11d456d86f3e0415684'
OUTPUT=ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1'
BOUND={'parent':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/policy.json'),sha256='d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'), 'parent_publication':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/publication.json'),sha256='23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'), 'parent_readback':dict(path=str(ROOT/'data/cache/research/gap_monthly_policy_history_input_readback_20261003_v1/independent_readback.json'),sha256='f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'), 'capture':dict(path=str(ROOT/'data/cache/research/forward_source_capture_oct02_20261003_v1/capture.json'),sha256='a1a2b89c71ba651215cca153ccc6cea8e88a09a7a83949e523efdc5316c95882'), 'capture_publication':dict(path=str(ROOT/'data/cache/research/forward_source_capture_oct02_20261003_v1/publication.json'),sha256='4cea5fddd57b0b1371bf6941f2e7d855890e868a1bb8513fc3994886ab61a82e')}
PARENT_READBACK_SCHEMA='GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1'
SESSION='2026-10-02'
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','old_calendar_mutated','seal_status_event_created','network_capture_performed','production_generator_authorized','full_transitive_source_closure_reverified'),False)
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(encode(a)==encode(b),msg)
def now():return datetime.now(timezone.utc).isoformat()
def runtime():return dict(python=sys.version,executable=sys.executable,implementation=platform.python_implementation())
def ref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and r['path']==r['path'].strip() and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Exact external reference')
def load_json(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(sources):
    for p,h in {str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():require(p not in sources or sources[p]==h,'Loaded-source conflict')
    for p,h in {**sources,str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA}.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def consume(r,sources):
    ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source hash conflict');b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes');sources[r['path']]=r['sha256'];return b

def validate_documents(docs,refs):
    require(PARENT_READBACK_SCHEMA is not None,'Parent independent schema pending')
    p=docs['parent'];pub=docs['parent_publication'];audit=docs['parent_readback'];c=docs['capture'];cp=docs['capture_publication']
    require(p['schema']=='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and p['policy_id']=='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH','Explicit first-actual policy')
    require(pub['status']=='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','Published parent');exact(pub['policy_reference'],refs['parent'],'Parent receipt');exact(pub['source_hashes'],p['source_hashes'],'Parent source map')
    require(audit['schema']==PARENT_READBACK_SCHEMA and audit['status']=='PASS','Independent parent readback');exact(audit['policy_reference'],refs['parent'],'Parent audit anchor');exact(audit['publication_reference'],refs['parent_publication'],'Parent audit publication')
    require(c['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1' and cp['status']=='PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','Explicit sealed future capture');exact(cp['capture_reference'],refs['capture'],'Capture publication');exact(cp['source_hashes'],c['source_hashes'],'Capture sources')
    exact(c['input_references']['frontier'],p['frontier_reference'],'Same parent frontier')
    known=p['projection_inputs']['known_rows'];require(type(known) is list and len(known)==65 and type(p['projection_inputs']['new_prospective_observations']) is list and p['projection_inputs']['new_prospective_observations']==[] and type(p['new_observation_count']) is int and p['new_observation_count']==0,'First new-schema writer only, no skipped prior observation')
    require(all(r['kind'] in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION') for r in known),'No undocumented prospective ancestor')
    plan=c['plan']['capture_plan'];require(c['plan']['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1' and plan['schema']=='FORWARD_SOURCE_CAPTURE_PLANNING_V1','Capture metadata schema')
    exact(plan['accounted_prefix_dates'],[r['session'] for r in known],'Complete65 accounted dates');require(plan['revisions']==[],'Unresolved revision')
    require(plan['new_source_dates']==[SESSION],'Exactly selected new session, old no-new capture rejected')
    for obj in (p,pub,audit,c,cp):
        for key in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[key] is False,'No source authority upgrade')

def load_inputs():
    require(all(r is not None for r in BOUND.values()) and SESSION is not None and PARENT_READBACK_SCHEMA is not None,'Future capture/session/parent audit pins pending')
    refs=deepcopy(BOUND);sources={str(SOURCE):LOADED_SHA,str(CORE):CORE_SHA};guard(sources);docs={r:load_json(consume(v,sources)) for r,v in refs.items()};validate_documents(docs,refs)
    for role in ('parent','capture'):
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Failed parent namespace')
    c=docs['capture'];capture=dict(reference=refs['capture'],started_at_utc=c['capture_started_at_utc'],completed_at_utc=c['observed_at_utc'],sources={},baseline_sources={})
    for t in ('QQQ','SPY'):
        for role,r in [('sources',c['captured_artifacts'][t]),('baseline_sources',c['input_references']['baseline_'+t])]:capture[role][t]=dict(bytes=consume(r,sources),reference=deepcopy(r))
    tr=c['captured_artifacts']['tzif'];capture['tzif']=dict(bytes=consume(tr,sources),reference=deepcopy(tr))
    b=CORE.read_bytes();require(sha(b)==CORE_SHA,'Consumed core');core=types.ModuleType('_fresh_observation_payload');exec(compile(b,str(CORE),'exec'),core.__dict__);guard(sources)
    args=dict(parent_reference=refs['parent'],parent_readback_reference=refs['parent_readback'],known_typed_rows=deepcopy(docs['parent']['projection_inputs']['known_rows']),parent_attempt_inventory=[],capture=capture,session=SESSION)
    return args,refs,sources,core
def save(path,v):
    b=encode(v)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Durable bytes');return dict(path=str(path),sha256=sha(b))
def run(*,execute=False):
    require(type(execute) is bool and not OUTPUT.exists(),'One exclusive first-observation attempt; no retry')
    if not execute:return dict(status='NOT_EXECUTED')
    args,refs,sources,core=load_inputs();rt=runtime();OUTPUT.mkdir(parents=True,exist_ok=False);start=now()
    try:
        save(OUTPUT/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V1',writer_started_at_utc=start,input_references=refs,source_hashes=sources,runtime=rt,**FLAGS))
        preparation_end=now();payload=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=preparation_end)
        payload['writer_interval_role']='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION';payload['input_references']=refs;payload['source_hashes']=sources;payload['runtime']=rt
        out=save(OUTPUT/'observation_payload.json',payload);guard(sources);require(runtime()==rt,'Runtime drift')
        published_at=now();require(core.utc(published_at)>=core.utc(preparation_end),'Publication clock did not reverse')
        late=payload['timing_classification']=='LATE_OBSERVATION' or core.utc(published_at)>=core.utc(payload['conservative_deadline_utc'])
        receipt=save(OUTPUT/'receipt.json',dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=payload['observation_id'],payload_reference=out,publication_check_at_utc=published_at,publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification='LATE_OBSERVATION' if late else payload['timing_classification'],month_first_actual_observation=payload['month_first_actual_observation'],source_hashes=sources,runtime=rt,**FLAGS))
        guard(sources);require(runtime()==rt,'Final runtime drift')
        for r in (out,receipt):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final evidence bytes')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','observation_payload.json','receipt.json'},'Exact final namespace');return receipt
    except Exception as e:save(OUTPUT/'failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY',error=str(e),recorded_at_utc=now(),observation_payload_must_not_be_discarded=(OUTPUT/'observation_payload.json').exists(),**FLAGS));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
