"""Immutable persisted-observation candidate-calendar evidence; never seal/append."""
import argparse,hashlib,json,os,shutil,types
from datetime import datetime,timezone
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/persisted_candidate_calendar_20261003_v1'
CORE=ROOT/'backtest/ndx_persisted_candidate_calendar_research.py'
CORE_SHA='ec6243c2832538e27f2ee2a2cec1aac580be3ab6265944a6d931c2b1f7aaa500'
ENVELOPE_ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBSERVATION_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
HISTORY_BOUND=dict.fromkeys(ENVELOPE_ROLES)
CAPTURE_BOUND=dict.fromkeys(ENVELOPE_ROLES)
OBSERVATION_BOUND=dict.fromkeys(OBSERVATION_ROLES)
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
 forbidden={(ROOT/'data/cache'/f'{t}.csv').resolve()for t in ('QQQ','SPY')};require(all(Path(p).resolve()not in forbidden for p in s),'Live cache cannot be a permanent evidence source')
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
 refs=dict(history=configured(HISTORY_BOUND,ENVELOPE_ROLES),observation=configured(OBSERVATION_BOUND,OBSERVATION_ROLES),capture=configured(CAPTURE_BOUND,ENVELOPE_ROLES));core_ref=reference(str(CORE),CORE_SHA) # Twelve pending roles are checked before any IO.
 s={str(SOURCE):LOADED};merge(s,core_ref)
 for mapping in refs.values():
  for r in mapping.values():merge(s,r)
 no_live(s);docs={}
 for kind,mapping in refs.items():
  envelope=dict(mapping);roles=(('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit'))if kind=='observation'else(('reference','document'),('publication_reference','publication'),('readback_reference','readback'))
  for role,key in roles:
   obj=decode(read(mapping[role],s));require(type(obj)is dict and type(obj['source_hashes'])is dict,'Saved source envelope');envelope[key]=obj
   for path,digest in obj['source_hashes'].items():merge(s,reference(path,digest))
  read(mapping['reader_reference'],s);docs[kind]=envelope
 no_live(s)
 tzref=docs['capture']['document']['captured_artifacts']['tzif'];tz=read(tzref,s);guard(s)
 blob=read(core_ref,s);require(sha(blob)==CORE_SHA,'Immediate private core bytes');module=types.ModuleType('_private_persisted_candidate_calendar');module.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),module.__dict__)
 exact(tuple(module.FALSE),FALSE[:18],'Frozen pure authority contract')
 return docs,refs,s,module,tz,core_ref

def run(*,execute=False):
 require(execute is True,'Explicit execution');docs,refs,s,core,tz,core_ref=load_inputs();require(not OUTPUT.exists(),'Create-only no retry');resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  start=now();started=save(OUTPUT/'started.json',dict(schema='PERSISTED_CANDIDATE_CALENDAR_STARTED_V2',input_references=refs,core_reference=core_ref,source_hashes=deepcopy(s),started_at_utc=start,retry_allowed=False,**dict.fromkeys(FALSE,False)));guard(s)
  evaluation=now();evidence=core.prepare_persisted_candidate_evidence(history=docs['history'],observation=docs['observation'],capture=docs['capture'],tzif_bytes=tz,seal_evaluation_at_utc=evaluation)
  exact(evidence['schema'],'PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_EVIDENCE_V2','Frozen result version');require(evidence['status']in ('CONDITIONAL_CALENDAR_PREREQUISITES_ONLY','BLOCKED'),'Conditional outcome');require(type(evidence['calendar_prerequisites_conditionally_satisfied'])is bool,'Exact condition bool')
  for k in core.FALSE:require(evidence[k]is False,'Pure cannot grant authority')
  for path,digest in evidence['source_hash_claims'].items():require(s.get(path)==digest,'Pure source claim was actually byte checked')
  exact(evidence['input_references']['history'],refs['history'],'Same history refs');exact(evidence['input_references']['observation'],refs['observation'],'Same observation refs');exact(evidence['input_references']['capture'],refs['capture'],'Same capture refs');exact(evidence['timing']['seal_evaluation_at_utc'],evaluation,'Actual evaluation instant');guard(s)
  result=save(OUTPUT/'result.json',dict(schema='SOURCE_BOUND_PERSISTED_CANDIDATE_CALENDAR_V2',evidence=evidence,input_references=refs,core_reference=core_ref,source_hashes=deepcopy(s),started_reference=started,evaluation_at_utc=evaluation,evaluation_clock_read_by_runner=True,external_clock_attestation_verified=False,evaluation_time_role='BEFORE_CONDITIONAL_EVALUATION_NOT_ACTUAL_SEAL_OR_FINAL_DURABLE_COMPLETION',**dict.fromkeys(FALSE,False)))
  pub=save(OUTPUT/'publication.json',dict(schema='PERSISTED_CANDIDATE_CALENDAR_PUBLICATION_V2',status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=result,source_hashes=deepcopy(s),**dict.fromkeys(FALSE,False)));guard(s)
  for r in (started,result,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output bytes')
  items=list(OUTPUT.iterdir());exact(sorted(p.name for p in items),['publication.json','result.json','started.json'],'Exact successful namespace');require(all(p.is_file()and not p.is_symlink()for p in items),'Regular output files');return dict(result_reference=result,publication_reference=pub)
 except BaseException as error:
  save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False,**dict.fromkeys(FALSE,False)),failure=True);raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
