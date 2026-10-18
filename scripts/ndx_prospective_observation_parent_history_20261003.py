"""Publish compact history only after a supplied observation's independent readback.
No network, observations, seal attempts, recovery, or existing history mutation.
"""
import argparse,hashlib,json,os,types
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/prospective_observation_parent_history_20261003_v1'
CORE=(str(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py'),'1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0')
GENESIS_BOUND={
 'reference':(str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/policy.json'),'d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'),
 'publication_reference':(str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/publication.json'),'23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'),
 'readback_reference':(str(ROOT/'data/cache/research/gap_monthly_policy_history_input_readback_20261003_v1/independent_readback.json'),'f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'),
 'reader_reference':(str(ROOT/'scripts/ndx_gap_monthly_policy_history_input_readback_20261003.py'),'80ac03fb2dae11a96d4cd060ee1eb0c30731aab271fe793ece7fb52743d99b6e')}
BASELINE_BOUND={
 'QQQ':(str(ROOT/'data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv'),'a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'SPY':(str(ROOT/'data/cache/research/observation_gap_classification_20261002_v1/SPY.csv'),'dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf')}
OBSERVATION_BOUND={'payload_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/observation_payload.json'),'06cf063ebc03f3808ff33d3a95f065cd6d789f30463ee46d26aef7fb69f9992a'), 'receipt_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/receipt.json'),'bde85f8e661ef1caba47ea69bb04f36e073ce5729f058959878571e5d228c248'), 'audit_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/independent_readback.json'),'1c6f13cac2d33c776a61e51f320b58d96960d547cdd7d3b6e04e21a1022fe64a'), 'reader_reference':(str(ROOT/'scripts/ndx_prospective_observation_independent_readback_20261003.py'),'bc0d13435950ce5230551fca7daf7f4e43b6c33942ecf5cfc3dc28930d4b2e53')}
# Future immutable configuration, never a caller-supplied executable or mutable common.
# None = first observation. Later versions configure all four exact external refs;
# previous history independent readback and observation reader must both be V2.
PREVIOUS_BOUND=None
FLAGS=dict.fromkeys(('source_authenticity_verified','filesystem_attempt_inventory_authenticated','clock_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','seal_event_created','partial_recovery_performed','old_calendar_mutated','observation_created','network_capture_performed','old_audit_repeated','full_transitive_source_closure_reverified'),False)

def require(ok,msg):
 if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def valid(p,h):require(type(p)is str and p and p==p.strip() and type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Pending external source anchor');return dict(path=p,sha256=h)
def refs(bound,keys):
 require(type(bound)is dict and set(bound)==set(keys),'Complete fixed reference roles');out={}
 for k,v in bound.items():require(type(v)is tuple and len(v)==2,'Pending external source anchor');out[k]=valid(*v)
 return out
def loads(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def merge(s,r):
 valid(r['path'],r['sha256']);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def consume(r,s):
 merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Source bytes changed');return b
def guard(s):
 require(sha(SOURCE.read_bytes())==LOADED,'Loaded publisher changed')
 for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def add_claims(doc,s):
 require(type(doc['source_hashes'])is dict,'Source claims')
 for p,h in doc['source_hashes'].items():merge(s,valid(p,h))
def no_failure(r):require(not (Path(r['path']).parent/'failure.json').exists(),'Failed/partial parent namespace')
def observation_namespace(r):
 folder=Path(r['payload_reference']['path']).parent
 require(Path(r['payload_reference']['path'])==folder/'observation_payload.json' and Path(r['receipt_reference']['path'])==folder/'receipt.json' and Path(r['audit_reference']['path'])==folder/'independent_readback.json','Observed three artifacts in same namespace')
 require({x.name for x in folder.iterdir()}=={'started.json','observation_payload.json','receipt.json','independent_readback.json'},'Complete observed and independently read-back namespace')
 require(all(x.is_file()and not x.is_symlink()for x in folder.iterdir()),'Regular immutable observation files')
def load_envelope(r,s):
 e=deepcopy(r)
 for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:no_failure(r[role]);e[key]=loads(consume(r[role],s));add_claims(e[key],s)
 consume(r['reader_reference'],s);return e

def prepare(genesis,previous,observation,core):
 expected='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'if previous is None else 'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2'
 require(observation['audit']['schema']==expected,'V1 first-only; later observations require explicit V2 audit')
 if previous is not None:require(previous['readback']['schema']=='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2','Audited previous V2 history required')
 out=core.append_observation_history(genesis=genesis,previous_history=previous,observation=observation)
 require(out['schema']=='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2' and out['observation_storage']=='COMPACT_EXTERNAL_REFERENCES_NO_CSV_ROWS_OR_BASE64','Compact history schema')
 for f in core.FLAGS:require(out[f]is False,'No pure authority')
 count=1 if previous is None else previous['document']['observation_count']+1
 require(type(out['observation_count'])is int and out['observation_count']==count and len(out['observations'])==len(out['parent_attempt_inventory'])==count,'Exactly one compact append')
 for entry in out['observations']:
  exact(sorted(entry),sorted(core.COMPACT_KEYS),'Exact compact fields');require(entry['original_payload_embedded']is False,'No raw payload duplicated')
 return out

def save(p,v):
 b=enc(v)
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Durable bytes readback');return valid(str(p),sha(b))
def run(*,execute=False):
 require(execute is True,'Explicit execute')
 # All future roles and versions are configured before ANY filesystem operation.
 orefs=refs(OBSERVATION_BOUND,('payload_reference','receipt_reference','audit_reference','reader_reference'))
 prefs=None if PREVIOUS_BOUND is None else refs(PREVIOUS_BOUND,('reference','publication_reference','readback_reference','reader_reference'))
 grefs=refs(GENESIS_BOUND,('reference','publication_reference','readback_reference','reader_reference'));baselines=refs(BASELINE_BOUND,('QQQ','SPY'));cr=valid(*CORE)
 require(not OUTPUT.exists(),'Create-only; no retries')
 sources={str(SOURCE):LOADED};corebytes=consume(cr,sources);genesis=load_envelope(grefs,sources);genesis['baseline_references']=baselines
 for r in baselines.values():consume(r,sources)
 previous=None if prefs is None else load_envelope(prefs,sources)
 observation=deepcopy(orefs)
 observation_namespace(orefs)
 for key,role in [('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')]:observation[key]=loads(consume(orefs[role],sources));add_claims(observation[key],sources)
 consume(orefs['reader_reference'],sources);guard(sources)
 OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  references=dict(genesis=grefs,baseline=baselines,previous_history=prefs,observation=orefs,core=cr)
  save(OUTPUT/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_STARTED_V2',input_references=references,source_hashes=sources,**FLAGS))
  require(sha(corebytes)==cr['sha256'],'Consumed core hash');core=types.ModuleType('_pinned_history_core');exec(compile(corebytes,cr['path'],'exec'),core.__dict__)
  result=prepare(genesis,previous,observation,core)
  preserved=deepcopy(result['source_hashes'])
  for p,h in preserved.items():merge(sources,valid(p,h))
  result.update(source_reference_claims_preserved_from_pure=preserved,source_hashes=deepcopy(sources),input_references=references,**FLAGS)
  guard(sources);observation_namespace(orefs);hr=save(OUTPUT/'history.json',result)
  publication=save(OUTPUT/'publication.json',dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2',status='PUBLISHED_OBSERVATION_HISTORY_NO_SEAL',history_reference=hr,observation_count=result['observation_count'],new_observation_reference=orefs['payload_reference'],previous_history_reference=None if prefs is None else prefs['reference'],source_hashes=deepcopy(sources),**FLAGS))
  guard(sources);observation_namespace(orefs);require({p.name for p in OUTPUT.iterdir()}=={'started.json','history.json','publication.json'},'Exact successful output')
  require(sha(Path(hr['path']).read_bytes())==hr['sha256']and sha(Path(publication['path']).read_bytes())==publication['sha256'],'Final published bytes');return dict(history_reference=hr,publication_reference=publication)
 except BaseException as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False,**FLAGS));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
