"""Independent compact-history linkage verification. No observation or old audit execution."""
import argparse
import hashlib
import json
import os
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT/'data/cache/research/prospective_observation_parent_history_independent_readback_20261003_v1'
PARENT = ROOT/'data/cache/research/prospective_observation_parent_history_20261003_v1'
BOUND = {'history': (str(PARENT/'history.json'), 'bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'), 'publication': (str(PARENT/'publication.json'), '648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'),
         'producer': (str(ROOT/'scripts/ndx_prospective_observation_parent_history_20261003.py'), '609ddb40d0f141b1cbe18b95e3eefa118cd2a2c19c877324c75a152a037c837b')}
CORE = (str(ROOT/'backtest/ndx_prospective_observation_parent_history_research.py'), '1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0')
GENESIS = {
 'reference': (str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/policy.json'), 'd04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'),
 'publication_reference': (str(ROOT/'data/cache/research/gap_monthly_policy_20261002_v1/publication.json'), '23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'),
 'readback_reference': (str(ROOT/'data/cache/research/gap_monthly_policy_history_input_readback_20261003_v1/independent_readback.json'), 'f11e5e1722b54724ffccaccb5a2c21ea945cbc9c9d96c458d064e11566833cd6'),
 'reader_reference': (str(ROOT/'scripts/ndx_gap_monthly_policy_history_input_readback_20261003.py'), '80ac03fb2dae11a96d4cd060ee1eb0c30731aab271fe793ece7fb52743d99b6e')}
BASELINES = {t: (str(ROOT/f'data/cache/research/observation_gap_classification_20261002_v1/{t}.csv'), h) for t,h in (
 ('QQQ','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 ('SPY','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'))}
OBSERVATION_BOUND = {'payload_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/observation_payload.json'),'06cf063ebc03f3808ff33d3a95f065cd6d789f30463ee46d26aef7fb69f9992a'), 'receipt_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/receipt.json'),'bde85f8e661ef1caba47ea69bb04f36e073ce5729f058959878571e5d228c248'), 'audit_reference':(str(ROOT/'data/cache/research/prospective_observation_receipt_20261003_v1/independent_readback.json'),'1c6f13cac2d33c776a61e51f320b58d96960d547cdd7d3b6e04e21a1022fe64a'), 'reader_reference':(str(ROOT/'scripts/ndx_prospective_observation_independent_readback_20261003.py'),'bc0d13435950ce5230551fca7daf7f4e43b6c33942ecf5cfc3dc28930d4b2e53')}
PREVIOUS_BOUND = None  # Later immutable versions must pin four references, including an explicit V2 reader.
POLICY = 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
PURE_FALSE = ('source_authenticity_verified','filesystem_attempt_inventory_authenticated','clock_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','seal_event_created','partial_recovery_performed','old_calendar_mutated')
WRAPPER_FALSE = PURE_FALSE + ('observation_created','network_capture_performed','old_audit_repeated','full_transitive_source_closure_reverified')

def require(ok, message):
 if not ok: raise ValueError(message)
def encoded(v): return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b): require(encoded(a)==encoded(b),'Exact saved values/types')
def digest(b): return hashlib.sha256(b).hexdigest()
def reference(p,h):
 require(type(p)is str and p and p.strip()==p and type(h)is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Pending external anchor')
 return {'path':p,'sha256':h}
def configured(bound):
 require(type(bound)is dict,'Reference configuration')
 out={}
 for k,v in bound.items():
  require(type(v)is tuple and len(v)==2,'Pending external anchor');out[k]=reference(*v)
 return out
def merge(s,r):
 exact(set(r.keys())=={'path','sha256'},True);reference(r['path'],r['sha256'])
 require(r['path']not in s or s[r['path']]==r['sha256'],'Conflicting source');s[r['path']]=r['sha256']
def claims(s,obj):
 require(type(obj['source_hashes'])is dict,'Source map')
 for p,h in obj['source_hashes'].items():merge(s,reference(p,h))
def false(obj,keys):
 for k in keys:require(obj[k]is False,'False authority '+k)
def integer(v,n):require(type(v)is int and v==n,'Exact integer')
def loads(b):
 def pairs(items):
  out={}
  for k,v in items:require(k not in out,'Duplicate key');out[k]=v
  return out
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def rows(rows,s):
 require(type(rows)is list and 0<len(rows)<20000,'Bounded typed rows');months={};prior='';seen=set()
 for i,r in enumerate(rows):
  exact(sorted(r),sorted(('sequence','session','kind','evidence_reference','seal_status')));integer(r['sequence'],i+1)
  day=r['session'];require(type(day)is str and date.fromisoformat(day).isoformat()==day and date.fromisoformat(day).weekday()<5 and day>prior,'Ordered canonical weekday')
  require(r['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Kind')
  require(r['seal_status']in ('NOT_ATTEMPTED','FAILED','UNKNOWN','SEALED'),'Seal state')
  if r['kind']=='MISSED_OBSERVATION':exact(r['seal_status'],'NOT_ATTEMPTED')
  else:months.setdefault(day[:7],day)
  ref=r['evidence_reference'];exact(sorted(ref),['json_pointer','path','sha256']);merge(s,{k:ref[k] for k in ('path','sha256')})
  require(type(ref['json_pointer'])is str and ref['json_pointer'].startswith('/') and len(ref['json_pointer'])>1,'Pointer')
  key=encoded(ref);require(key not in seen,'Duplicate evidence');seen.add(key);prior=day
 return months
def envelope(e,s,genesis):
 for k in ('reference','publication_reference','readback_reference','reader_reference'):merge(s,e[k])
 d,p,a=e['document'],e['publication'],e['readback'];key='policy_reference'if genesis else 'history_reference'
 exact(p['schema'],'GAP_MONTHLY_POLICY_PUBLICATION_V1'if genesis else 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2')
 exact(p['status'],'PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL'if genesis else 'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL')
 exact(a['schema'],'GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1'if genesis else 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2');exact(a['status'],'PASS')
 exact(p[key],e['reference']);exact(a[key],e['reference']);exact(a['publication_reference'],e['publication_reference']);exact(a['reader_sha256'],e['reader_reference']['sha256'])
 exact(p['source_hashes'],d['source_hashes'])
 for role in ('reference','publication_reference','reader_reference'):require(a['source_hashes'].get(e[role]['path'])==e[role]['sha256'],'Parent audit source')
 for obj in (d,p,a):claims(s,obj)
 for obj in (p,a):false(obj,('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'))

def inspect(history,genesis,previous,observation):
 """Independent field reconstruction; existing parent reports are references, not rerun."""
 s={};envelope(genesis,s,True);g=genesis['document'];exact(g['schema'],'SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1');exact(g['policy_id'],POLICY);integer(g['new_observation_count'],0)
 exact(g['projection_inputs']['new_prospective_observations'],[]);false(g,('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'))
 original=g['projection_inputs']['known_rows'];integer(len(original),65);integer(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION' for r in original),60);integer(sum(r['kind']=='MISSED_OBSERVATION' for r in original),5);rows(original,s)
 baseline=genesis['baseline_references'];exact(sorted(baseline),['QQQ','SPY']);exact(baseline,genesis['readback']['baseline_references'])
 for r in baseline.values():merge(s,r);require(genesis['readback']['source_hashes'].get(r['path'])==r['sha256'],'Genesis baseline bound')
 known=deepcopy(original);oldentries=[];attempts=[];parent=genesis
 if previous is not None:
  envelope(previous,s,False);old=previous['document'];exact(old['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2');exact(old['policy_id'],POLICY);false(old,PURE_FALSE);exact(old['genesis_preserved'],genesis)
  known=old['known_typed_rows'];exact(known[:65],original);exact(old['first_actual_observed_session_by_month'],rows(known,s));exact(old['last_accounted_session'],known[-1]['session'])
  oldentries=old['observations'];attempts=old['parent_attempt_inventory'];integer(old['observation_count'],len(known)-65);integer(len(oldentries),old['observation_count']);integer(len(attempts),len(oldentries));require(bool(oldentries),'Nonempty prior history')
  baseline=old['baseline_references'];exact(baseline,oldentries[-1]['captured_baseline_references']);parent=previous
  for j,e in enumerate(oldentries):
   require(e['original_payload_embedded']is False,'Compact prior only');exact(e['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1');integer(e['sequence'],66+j);exact(e['observation_id'],digest(encoded(e['observation_identity'])))
   exact(known[65+j]['session'],e['session']);exact(known[65+j]['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(known[65+j]['evidence_reference'],dict(e['payload_reference'],json_pointer='/observation_identity'))
   exact(attempts[j],attempt(e))
   for k in ('payload_reference','receipt_reference','audit_reference','reader_reference'):merge(s,e[k])
   exact(sorted(e['original_source_hash_claims']),['audit','payload','receipt'])
   for c in e['original_source_hash_claims'].values():claims(s,{'source_hashes':c})
 for r in baseline.values():merge(s,r)
 p,r,a=observation['payload'],observation['receipt'],observation['audit']
 for key in ('payload_reference','receipt_reference','audit_reference','reader_reference'):merge(s,observation[key])
 for obj in (p,r,a):claims(s,obj);false(obj,('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed'))
 exact(p['source_hashes'],r['source_hashes'])
 for path,h in p['source_hashes'].items():require(a['source_hashes'].get(path)==h,'Observation audit source')
 exact(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1');exact(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1');exact(r['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
 exact(a['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'if previous is None else 'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2');exact(a['status'],'PASS');false(a,('writer_called','old_audit_repeated'))
 if previous is not None:exact(a['parent_history_reference'],parent['reference'])
 for key,n in [('new_observation_count',1),('parent_observed_count',len(known)-5),('parent_gap_count',5)]:integer(a['counts'][key],n)
 exact(r['payload_reference'],observation['payload_reference']);exact(a['payload_reference'],observation['payload_reference']);exact(a['receipt_reference'],observation['receipt_reference']);exact(a['reader_sha256'],observation['reader_reference']['sha256'])
 for key in ('payload_reference','receipt_reference','reader_reference'):require(a['source_hashes'].get(observation[key]['path'])==observation[key]['sha256'],'Audit immutable binding')
 exact(p['known_typed_rows_preserved'],known);exact(p['parent_attempt_inventory_preserved'],attempts);exact(p['parent_readback_reference'],parent['readback_reference'])
 identity={'parent_reference':parent['reference'],'capture_reference':p['observation_identity']['capture_reference'],'session':p['session']};exact(p['observation_identity'],identity);identifier=digest(encoded(identity));exact(p['observation_id'],identifier);exact(r['observation_id'],identifier);require(identifier not in {e['observation_id'] for e in oldentries},'Unique observation')
 integer(p['sequence'],len(known)+1);exact(p['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(p['initial_seal_status'],'NOT_ATTEMPTED');require(p['session']>known[-1]['session'],'Append only')
 captured={};required=[identity['capture_reference']]
 for ticker in ('QQQ','SPY'):
  v=p['full_original_sources_preserved'][ticker];exact(v['baseline_sources']['reference'],baseline[ticker]);captured[ticker]=v['sources']['reference'];required += [v['sources']['reference'],v['baseline_sources']['reference']]
 for ref in required:
  merge(s,ref)
  for obj in (p,a):require(obj['source_hashes'].get(ref['path'])==ref['sha256'],'Raw/capture reference source')
 months=rows(known,s);first=months.get(p['session'][:7],p['session']);exact(p['first_actual_observed_session_of_month'],first)
 for obj in (p,r):require(type(obj['month_first_actual_observation'])is bool and obj['month_first_actual_observation']==(first==p['session']),'Month first independent of late or seal');require(obj['timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),'Timing')
 require(p['timing_classification']!='LATE_OBSERVATION' or r['timing_classification']=='LATE_OBSERVATION','Late cannot improve')
 for key in ('month_first_actual_observation','timing_classification'):exact(a['counts'][key],r[key])
 entry={k:deepcopy(p[k])for k in ('observation_id','session','sequence','observation_identity','initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month')}
 entry.update(schema='COMPACT_OBSERVATION_REFERENCE_ENTRY_V1',original_payload_embedded=False,timing_classification=r['timing_classification'],payload_timing_classification=p['timing_classification'],captured_baseline_references=captured,previous_baseline_references=baseline,original_source_hash_claims={k:observation[k]['source_hashes']for k in ('payload','receipt','audit')})
 entry.update({k:observation[k]for k in ('payload_reference','receipt_reference','audit_reference','reader_reference')})
 for e in oldentries:exact(sorted(e),sorted(entry))
 newrows=known+[dict(sequence=p['sequence'],session=p['session'],kind=p['kind'],seal_status='NOT_ATTEMPTED',evidence_reference=dict(observation['payload_reference'],json_pointer='/observation_identity'))]
 expected=dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2',policy_id=POLICY,genesis_preserved=genesis,parent_history_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows=newrows,observations=oldentries+[entry],parent_attempt_inventory=attempts+[attempt(entry)],baseline_references=captured,observation_count=len(oldentries)+1,last_accounted_session=p['session'],first_actual_observed_session_by_month=rows(newrows,s),source_reference_claims=s,observation_storage='COMPACT_EXTERNAL_REFERENCES_NO_CSV_ROWS_OR_BASE64',authentication_role='CALLER_SUPPLIED_EXTERNALLY_AUTHENTICATED_EVIDENCE_NOT_AUTHENTICATED_BY_PURE')
 for key,value in expected.items():exact(history[key],value)
 false(history,PURE_FALSE)
 return {'typed_row_count':len(newrows),'observation_count':len(oldentries)+1,'new_observation_count':1,'source_claims':s,'first_actual_observed_session_by_month':expected['first_actual_observed_session_by_month']}

def attempt(e):return dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference'])
def read(r,s):
 merge(s,r);b=Path(r['path']).read_bytes();require(digest(b)==r['sha256'],'Source bytes');return b
def guard(s):
 require(digest(SOURCE.read_bytes())==LOADED,'Reader runtime drift')
 for p,h in s.items():require(digest(Path(p).read_bytes())==h,'Source drift')
def directory(folder,names):
 items=list(folder.iterdir());exact(sorted(x.name for x in items),sorted(names));require(all(x.is_file()and not x.is_symlink()for x in items),'Regular complete namespace')
def load_envelope(refs,s):
 out=deepcopy(refs)
 for name,key in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
  require(not (Path(refs[key]['path']).parent/'failure.json').exists(),'Failed parent');out[name]=loads(read(refs[key],s));claims(s,out[name])
 read(refs['reader_reference'],s);return out
def save(p,obj):
 b=encoded(obj)
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved report');return reference(str(p),digest(b))
def readback(*,execute=False):
 require(execute is True,'Explicit execute')
 # Gate every future artifact/reader before any filesystem access.
 bound=configured(BOUND);obsrefs=configured(OBSERVATION_BOUND);prevrefs=None if PREVIOUS_BOUND is None else configured(PREVIOUS_BOUND)
 grefs=configured(GENESIS);base=configured(BASELINES);core=reference(*CORE)
 require(not OUTPUT.exists(),'Create-only report; no retry');directory(PARENT,('started.json','history.json','publication.json'))
 s={str(SOURCE):LOADED};h=loads(read(bound['history'],s));pub=loads(read(bound['publication'],s));read(bound['producer'],s);read(core,s)
 started_bytes=(PARENT/'started.json').read_bytes();started=loads(started_bytes);started_ref=reference(str(PARENT/'started.json'),digest(started_bytes))
 # started is locally observed bytes, explicitly not externally pinned.
 merge(s,started_ref)
 g=load_envelope(grefs,s);g['baseline_references']=base
 for ref in base.values():read(ref,s)
 prev=None if prevrefs is None else load_envelope(prevrefs,s)
 if prevrefs is not None:directory(Path(prevrefs['reference']['path']).parent,('started.json','history.json','publication.json'))
 folder=Path(obsrefs['payload_reference']['path']).parent
 for key,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:exact(obsrefs[key]['path'],str(folder/name))
 directory(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'))
 o=deepcopy(obsrefs)
 for name,key in [('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')]:o[name]=loads(read(obsrefs[key],s));claims(s,o[name])
 read(obsrefs['reader_reference'],s)
 result=inspect(h,g,prev,o)
 inputs=dict(genesis=grefs,baseline=base,previous_history=prevrefs,observation=obsrefs,core=core)
 exact(h['input_references'],inputs);exact(started['input_references'],inputs);exact(started['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_STARTED_V2')
 producer_sources=dict(result['source_claims']);merge(producer_sources,bound['producer']);merge(producer_sources,core)
 exact(h['source_hashes'],producer_sources);exact(started['source_hashes'],producer_sources);exact(pub['source_hashes'],producer_sources);exact(h['source_reference_claims_preserved_from_pure'],result['source_claims'])
 exact(pub['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2');exact(pub['status'],'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL');exact(pub['history_reference'],bound['history']);integer(pub['observation_count'],result['observation_count']);exact(pub['new_observation_reference'],obsrefs['payload_reference']);exact(pub['previous_history_reference'],None if prevrefs is None else prevrefs['reference'])
 for obj in (h,pub,started):false(obj,WRAPPER_FALSE)
 for p,sha in producer_sources.items():merge(s,reference(p,sha))
 guard(s);OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',dict(history_reference=bound['history'],publication_reference=bound['publication'],source_hashes=s))
  report=dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',history_reference=bound['history'],publication_reference=bound['publication'],reader_sha256=LOADED,source_hashes=s,counts={k:v for k,v in result.items()if k!='source_claims'},started_reference_observed_not_external_anchor=started_ref,started_externally_authenticated=False,writer_called=False,producer_called=False,old_audit_repeated=False,price_values_recomputed=False,**dict.fromkeys(PURE_FALSE,False))
  ref=save(OUTPUT/'independent_readback.json',report);guard(s);directory(PARENT,('started.json','history.json','publication.json'));directory(folder,('started.json','observation_payload.json','receipt.json','independent_readback.json'));directory(OUTPUT,('started.json','independent_readback.json'));require(digest(Path(ref['path']).read_bytes())==ref['sha256'],'Final report bytes');return ref
 except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
