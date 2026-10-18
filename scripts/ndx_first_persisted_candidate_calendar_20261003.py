"""First V1 persisted observation with explicit scoped-snapshot equivalence; never read live caches."""
import argparse,hashlib,json,os,shutil,types
from datetime import datetime,timezone
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/first_persisted_candidate_calendar_20261003_v1'
CORE=ROOT/'backtest/ndx_first_persisted_candidate_calendar_research.py'
CORE_SHA='74be1e9adfaf7ba11562b6d32fec124228a64c26df4a958b48e966843940c384'
ENVELOPE_ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBSERVATION_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
GENESIS_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_20261002_v1\\policy.json', 'd04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_20261002_v1\\publication.json', '23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\gap_monthly_policy_history_input_readback_20261003_v1\\independent_readback.json', 'f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_gap_monthly_policy_history_input_readback_20261003.py', '80ac03fb2dae11a96d4cd060ee1eb0c30731aab271fe793ece7fb52743d99b6e')}
HISTORY_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_20261003_v1\\history.json', 'bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_20261003_v1\\publication.json', '648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_parent_history_independent_readback_20261003_v1\\independent_readback.json', 'c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_prospective_observation_parent_history_independent_readback_20261003.py', '876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef')}
CAPTURE_BOUND={'reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_20261003_v1\\capture.json', 'a1a2b89c71ba651215cca153ccc6cea8e88a09a7a83949e523efdc5316c95882'), 'publication_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_20261003_v1\\publication.json', '4cea5fddd57b0b1371bf6941f2e7d855890e868a1bb8513fc3994886ab61a82e'), 'readback_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\forward_source_capture_oct02_independent_readback_20261003_v1\\independent_readback.json', '850601204fb50bb9cebbefcb4c9594a37b5bece71e5d2be26fb15f79e38881a8'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_forward_source_capture_oct02_independent_readback_20261003.py', 'b3e0377ea39c89b73c1cfdfdb3874ab68b151ec1c96c28f898df82164e7d218d')}
OBSERVATION_BOUND={'payload_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\observation_payload.json', '06cf063ebc03f3808ff33d3a95f065cd6d789f30463ee46d26aef7fb69f9992a'), 'receipt_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\receipt.json', 'bde85f8e661ef1caba47ea69bb04f36e073ce5729f058959878571e5d228c248'), 'audit_reference': ('E:\\Git\\us_ratchet\\data\\cache\\research\\prospective_observation_receipt_20261003_v1\\independent_readback.json', '1c6f13cac2d33c776a61e51f320b58d96960d547cdd7d3b6e04e21a1022fe64a'), 'reader_reference': ('E:\\Git\\us_ratchet\\scripts\\ndx_prospective_observation_independent_readback_20261003.py', 'bc0d13435950ce5230551fca7daf7f4e43b6c33942ecf5cfc3dc28930d4b2e53')}
FALSE=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_evidence_authenticated','observation_receipt_authenticated','clock_authenticity_verified','final_durable_completion_time_verified','seal_attempt_history_authenticated','production_lineage_ready','old_calendar_mutated','old_generator_called','observation_created','seal_event_created','future_independent_oos','exchange_holidays_verified','early_closes_verified','capture_called','observation_writer_called','history_append_called','old_audit_repeated','network_called')
MIN_FREE=5*1024**3

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(enc(a)==enc(b),message)
def reference(path,digest):
 require(type(path)is str and path and path.strip()==path and type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef'for c in digest),'Pending/invalid external source anchor');return dict(path=path,sha256=digest)
def configured(mapping,roles):
 exact(sorted(mapping),sorted(roles),'Exact external source roles');refs={}
 for k,v in mapping.items():require(type(v)is tuple and len(v)==2,'Pending external source anchor');refs[k]=reference(str(ROOT/v[0]),v[1])
 return refs
def merge(s,r):
 exact(sorted(r),['path','sha256'],'Exact reference fields');reference(r['path'],r['sha256']);require(r['path']not in s or s[r['path']]==r['sha256'],'Conflicting source hashes');s[r['path']]=r['sha256']
def no_live(s):
 require(all(not (Path(p).resolve().parent.as_posix().lower().endswith('/data/cache')and Path(p).suffix.lower()=='.csv')for p in s),'UNSUPPORTED_LIVE_CACHE_SOURCE_CLAIM outside explicit capture bridge')
def regular(p):require(p.is_file()and not p.is_symlink(),'Regular immutable source file')
def read(r,s):
 merge(s,r);no_live(s);p=Path(r['path']);regular(p);require(not (p.parent/'failure.json').exists(),'Failed source namespace');raw=p.read_bytes();require(sha(raw)==r['sha256'],'External source SHA mismatch');return raw
def decode(raw):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def guard(s):
 no_live(s);require(sha(SOURCE.read_bytes())==LOADED,'Loaded wrapper changed')
 for path,digest in s.items():
  p=Path(path);regular(p);require(not (p.parent/'failure.json').exists(),'Failed source namespace');require(sha(p.read_bytes())==digest,'Source drift')
def resource_gate(byte_count=0):
 require(type(byte_count)is int and byte_count>=0,'Exact byte count');require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE+byte_count,'RESOURCE_STOP_BEFORE_WRITE')
def save(path,obj,*,failure=False):
 raw=enc(obj)
 if not failure:resource_gate(len(raw))
 with path.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Saved bytes');return reference(str(path),sha(raw))
def now():return datetime.now(timezone.utc).isoformat()
def load_inputs():
 refs=dict(genesis=configured(GENESIS_BOUND,ENVELOPE_ROLES),history=configured(HISTORY_BOUND,ENVELOPE_ROLES),observation=configured(OBSERVATION_BOUND,OBSERVATION_ROLES),capture=configured(CAPTURE_BOUND,ENVELOPE_ROLES));core_ref=reference(str(CORE),CORE_SHA) # Sixteen pending roles are checked before any IO.
 s={str(SOURCE):LOADED};merge(s,core_ref)
 for mapping in refs.values():
  for r in mapping.values():merge(s,r)
 no_live(s);docs={}
 for kind,mapping in refs.items():
  envelope=dict(mapping);roles=(('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit'))if kind=='observation'else(('reference','document'),('publication_reference','publication'),('readback_reference','readback'))
  for role,key in roles:
   obj=decode(read(mapping[role],s));require(type(obj)is dict and type(obj['source_hashes'])is dict,'Saved source envelope');envelope[key]=obj
   if kind!='capture' or key=='readback':
    for path,digest in obj['source_hashes'].items():merge(s,reference(path,digest))
  if kind=='genesis':envelope['baseline_references']=deepcopy(envelope['readback']['baseline_references'])
  read(mapping['reader_reference'],s);docs[kind]=envelope
 no_live(s)
 bridge=validate_snapshot_bridge(docs['capture'],s)
 tzref=docs['capture']['document']['captured_artifacts']['tzif'];tz=read(tzref,s);guard(s)
 blob=read(core_ref,s);require(sha(blob)==CORE_SHA,'Immediate private core bytes');module=types.ModuleType('_private_first_persisted_candidate_calendar');module.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),module.__dict__)
 exact(tuple(module.FALSE),FALSE[:18],'Frozen pure authority contract')
 exact(module.snapshot_bridge(docs['capture']),bridge,'Independent wrapper and pure bridge coordinates')
 return docs,refs,s,module,tz,core_ref

def validate_snapshot_bridge(capture,s):
 c,p,a=capture['document'],capture['publication'],capture['readback'];original=c['source_hashes'];exact(original,p['source_hashes'],'Capture original publication map');exact(a['capture_original_source_hashes_preserved'],original,'Audited original capture map')
 rows=[];excluded=set();folder=Path(capture['reference']['path']).parent
 for ticker in ('QQQ','SPY'):
  current=c['input_references']['current_'+ticker];snapshot=c['captured_artifacts'][ticker]
  merge({},current);merge({},snapshot)
  exact(current['path'],str(ROOT/'data/cache'/f'{ticker}.csv'),'Fixed original live path')
  exact(snapshot['path'],str(folder/f'{ticker}.csv'),'Fixed capture snapshot path')
  require(current['sha256']==snapshot['sha256']==original.get(current['path'])==a['source_hashes'].get(snapshot['path']),'Historical current/snapshot/audit SHA equivalence')
  excluded.add(current['path']);read(snapshot,s)
  rows.append(dict(ticker=ticker,original_current_reference=deepcopy(current),snapshot_reference=deepcopy(snapshot)))
 remaining={path:digest for path,digest in original.items()if path not in excluded};no_live(remaining)
 for path,digest in remaining.items():
  require(a['source_hashes'].get(path)==digest,'Audit covers every non-bridged capture source');merge(s,reference(path,digest))
 return dict(schema='FIRST_V1_SCOPED_SNAPSHOT_EQUIVALENCE_BRIDGE_V1',rows=rows,capture_reference=deepcopy(capture['reference']),publication_reference=deepcopy(capture['publication_reference']),readback_reference=deepcopy(capture['readback_reference']),current_live_cache_reopened=False,full_transitive_source_closure_reverified=False)

def run(*,execute=False):
 require(execute is True,'Explicit execution');docs,refs,s,core,tz,core_ref=load_inputs();require(not OUTPUT.exists(),'Create-only no retry');resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  start=now();started=save(OUTPUT/'started.json',dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_STARTED_V1',input_references=refs,core_reference=core_ref,source_hashes=deepcopy(s),started_at_utc=start,retry_allowed=False,**dict.fromkeys(FALSE,False)));guard(s)
  evaluation=now();evidence=core.prepare_first_persisted_candidate_evidence(genesis=docs['genesis'],history=docs['history'],observation=docs['observation'],capture=docs['capture'],tzif_bytes=tz,seal_evaluation_at_utc=evaluation)
  exact(evidence['schema'],'FIRST_PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_SNAPSHOT_EVIDENCE_V1','Frozen result version');require(evidence['status']in ('CONDITIONAL_CALENDAR_PREREQUISITES_ONLY','BLOCKED'),'Conditional outcome');require(type(evidence['calendar_prerequisites_conditionally_satisfied'])is bool,'Exact condition bool')
  for k in core.FALSE:require(evidence[k]is False,'Pure cannot grant authority')
  for path,digest in evidence['source_hash_claims'].items():require(s.get(path)==digest,'Pure source claim was actually byte checked')
  exact(evidence['input_references']['genesis'],refs['genesis'],'Same genesis refs');exact(evidence['input_references']['history'],refs['history'],'Same history refs');exact(evidence['input_references']['observation'],refs['observation'],'Same observation refs');exact(evidence['input_references']['capture'],refs['capture'],'Same capture refs');exact(evidence['timing']['seal_evaluation_at_utc'],evaluation,'Actual evaluation instant');guard(s)
  bridge=deepcopy(evidence['snapshot_equivalence_bridge']);original=deepcopy(evidence['original_source_claims_preserved'])
  result=save(OUTPUT/'result.json',dict(schema='SOURCE_BOUND_FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_V1',evidence=evidence,adapter_schema=core.BRIDGE_SCHEMA,original_source_claims_preserved=original,snapshot_equivalence_bridge=bridge,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,input_references=refs,core_reference=core_ref,source_hashes=deepcopy(s),started_reference=started,evaluation_at_utc=evaluation,evaluation_clock_read_by_runner=True,external_clock_attestation_verified=False,evaluation_time_role='BEFORE_CONDITIONAL_EVALUATION_NOT_ACTUAL_SEAL_OR_FINAL_DURABLE_COMPLETION',**dict.fromkeys(FALSE,False)))
  pub=save(OUTPUT/'publication.json',dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=result,adapter_schema=core.BRIDGE_SCHEMA,original_source_claims_preserved=original,snapshot_equivalence_bridge=bridge,current_live_cache_reopened=False,full_transitive_source_closure_reverified=False,source_hashes=deepcopy(s),**dict.fromkeys(FALSE,False)));guard(s)
  for r in (started,result,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output bytes')
  items=list(OUTPUT.iterdir());exact(sorted(p.name for p in items),['publication.json','result.json','started.json'],'Exact successful namespace');require(all(p.is_file()and not p.is_symlink()for p in items),'Regular output files');return dict(result_reference=result,publication_reference=pub)
 except BaseException as error:
  save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False,**dict.fromkeys(FALSE,False)),failure=True);raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
