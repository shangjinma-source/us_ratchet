"""Pure seal-attempt evidence state. No IO, dispatch, clock or source authentication."""
from copy import deepcopy
from datetime import datetime,timedelta,date
from hashlib import sha256
import json
FLAGS=dict.fromkeys(('source_bytes_authenticated','clock_authenticity_verified','filesystem_attempt_inventory_authenticated','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','production_generator_authorized','future_independent_oos','seal_executed','history_modified','automatic_retry_allowed','partial_recovery_performed'),False)
INVENTORY='OBSERVATION_SEAL_EVENT_INVENTORY_V1'
EVENT='OBSERVATION_SEAL_STATUS_EVENT_V1'
SCOPE='COMPLETE_CALLER_SUPPLIED_EVENT_SEQUENCE_NOT_FILESYSTEM_AUTHENTICATION'
REFS=('payload_reference','receipt_reference','audit_reference','reader_reference')
def require(ok,msg):
 if not ok:raise ValueError(msg)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha256(encoded(v)).hexdigest()
def exact(a,b):require(encoded(a)==encoded(b),'Exact value/type mismatch')
def utc(s):
 require(type(s)is str,'UTC string');v=datetime.fromisoformat(s);require(v.tzinfo is not None and v.utcoffset()==timedelta(0),'Aware UTC');return v
def integer(v,n):require(type(v)is int and v==n,'Exact count')
def reference(r,s):
 require(type(r)is dict and set(r)=={'path','sha256'},'Exact byte reference');p,h=r['path'],r['sha256'];require(type(p)is str and p and p.strip()==p and type(h)is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'Reference fields');require(p not in s or s[p]==h,'Conflicting source');s[p]=h
def claims(obj,s):
 require(type(obj['source_hashes'])is dict,'Complete source map')
 for p,h in obj['source_hashes'].items():reference(dict(path=p,sha256=h),s)
def associated(s,r):reference(r,{});exact(s.get(r['path']),r['sha256'])
def false(obj):
 for k in FLAGS:require(obj[k]is False,'Authority '+k)
def observed(observation):
 require(type(observation)is dict and set(observation)==set(REFS)|{'payload','receipt','audit'},'Full externally referenced observation');s={}
 for k in REFS:reference(observation[k],s)
 p,r,a=(observation[k]for k in ('payload','receipt','audit'))
 exact(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1');exact(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1');exact(r['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
 require(a['schema']in ('PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1','PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2')and a['status']=='PASS','Explicit observation readback version')
 for obj in (r,a):exact(obj['payload_reference'],observation['payload_reference'])
 exact(a['receipt_reference'],observation['receipt_reference']);exact(a['reader_sha256'],observation['reader_reference']['sha256']);exact(p['source_hashes'],r['source_hashes'])
 for obj in (p,r,a):
  claims(obj,s)
  for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'):require(obj[k]is False,'Observation authority')
 for path,h in p['source_hashes'].items():associated(a['source_hashes'],dict(path=path,sha256=h))
 for k in ('payload_reference','receipt_reference','reader_reference'):associated(a['source_hashes'],observation[k])
 identity=p['observation_identity'];require(type(identity)is dict and set(identity)=={'parent_reference','capture_reference','session'},'Observation identity');reference(identity['parent_reference'],s);reference(identity['capture_reference'],s);associated(a['source_hashes'],identity['parent_reference']);associated(a['source_hashes'],identity['capture_reference'])
 exact(p['observation_id'],digest(identity));exact(r['observation_id'],p['observation_id']);exact(p['session'],identity['session']);d=date.fromisoformat(p['session']);require(d.isoformat()==p['session']and d.weekday()<5,'Canonical session')
 require(type(p['sequence'])is int and p['sequence']>0,'Observation sequence');exact(p['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(p['initial_seal_status'],'NOT_ATTEMPTED')
 first=p['first_actual_observed_session_of_month'];require(type(first)is str and date.fromisoformat(first).isoformat()==first and first[:7]==p['session'][:7]and first<=p['session'],'Original actual month coordinate');exact(p['month_first_actual_observation'],first==p['session']);exact(r['month_first_actual_observation'],p['month_first_actual_observation'])
 close,cs,ce,ws,we,check,deadline=map(utc,[p['conservative_close_utc'],p['capture_started_at_utc'],p['capture_completed_at_utc'],p['writer_started_at_utc'],p['writer_completed_at_utc'],r['publication_check_at_utc'],p['conservative_deadline_utc']]);require(close<=cs<=ce<=ws<=we<=check and close<deadline,'Observation time ordering')
 exact(p['timing_classification'],'LATE_OBSERVATION'if we>=deadline else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW');exact(r['timing_classification'],'LATE_OBSERVATION'if check>=deadline else p['timing_classification'])
 exact(r['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE');reference(p['tzif_reference'],s);associated(a['source_hashes'],p['tzif_reference'])
 counts=a['counts'];integer(counts['new_observation_count'],1);integer(counts['parent_gap_count'],5);integer(counts['parent_observed_count'],p['sequence']-6)
 if a['schema'].endswith('_V1'):integer(p['sequence'],66)
 else:
  require(p.get('writer_adapter_schema')=='VARIABLE_PREFIX_OBSERVATION_WRITER_V2' and r.get('writer_adapter_schema')=='VARIABLE_PREFIX_OBSERVATION_WRITER_V2','Explicit V2 observation writer adapter')
  require(p['sequence']>=67,'V2 follows persisted first observation');exact(a['parent_history_reference'],identity['parent_reference'])
 exact(counts['month_first_actual_observation'],p['month_first_actual_observation']);exact(counts['timing_classification'],r['timing_classification'])
 return p,r,s

def start_identity(p,obs,request,s):
 require(type(request['input_versions'])is dict and request['input_versions']and all(type(k)is str and k and type(v)is str and v for k,v in request['input_versions'].items()),'Explicit nonempty input versions')
 require(type(request['input_references'])is dict and request['input_references']and all(type(k)is str and k for k in request['input_references']),'Explicit input references')
 for r in request['input_references'].values():reference(r,s)
 reference(request['candidate_calendar_reference'],s)
 return dict(observation_id=p['observation_id'],observation_references={k:deepcopy(obs[k])for k in REFS},candidate_calendar_reference=deepcopy(request['candidate_calendar_reference']),input_versions=deepcopy(request['input_versions']),input_references=deepcopy(request['input_references']))
def eligibility(p,r,start,record):
 reasons=[]
 if not p['month_first_actual_observation']:reasons.append('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH')
 if r['timing_classification']=='LATE_OBSERVATION':reasons.append('OBSERVATION_RECEIPT_LATE')
 if start>=utc(p['conservative_deadline_utc'])or record>=utc(p['conservative_deadline_utc']):reasons.append('SEAL_START_OR_RECORD_OUTSIDE_CONSERVATIVE_WINDOW')
 return reasons

def success(proof,start,p,finished,s):
 require(type(proof)is dict and set(proof)=={'manifest','audit','manifest_reference','audit_reference','reader_reference'},'Complete versioned successful evidence')
 for k in ('manifest_reference','audit_reference','reader_reference'):reference(proof[k],s)
 m,a=proof['manifest'],proof['audit'];exact(m['schema'],'OBSERVATION_CANDIDATE_SEAL_MANIFEST_V1');exact(m['status'],'RESEARCH_SEAL_COMPLETED');exact(a['schema'],'OBSERVATION_CANDIDATE_SEAL_INDEPENDENT_READBACK_V1');exact(a['status'],'PASS')
 for obj in (m,a):
  exact(obj['observation_id'],p['observation_id']);exact(obj['attempt_id'],start['attempt_id']);false(obj);claims(obj,s)
 exact(a['manifest_reference'],proof['manifest_reference']);exact(a['reader_sha256'],proof['reader_reference']['sha256']);exact(m['attempt_started_at_utc'],start['attempt_started_at_utc']);exact(m['attempt_completed_at_utc'],finished)
 for k in ('candidate_calendar_reference','input_versions','input_references'):exact(m[k],start['attempt_identity'][k])
 for r in [start['attempt_identity']['candidate_calendar_reference'],*start['attempt_identity']['input_references'].values()]:associated(m['source_hashes'],r)
 for path,h in m['source_hashes'].items():associated(a['source_hashes'],dict(path=path,sha256=h))
 for k in ('manifest_reference','reader_reference'):associated(a['source_hashes'],proof[k])

def derive_seal_state(*,observation,inventory):
 p,r,s=observed(observation);require(type(inventory)is dict and set(inventory)=={'schema','observation_id','payload_reference','events','event_count','last_event_sha256','inventory_scope'},'Explicit complete inventory, never None');exact(inventory['schema'],INVENTORY);exact(inventory['inventory_scope'],SCOPE);exact(inventory['observation_id'],p['observation_id']);exact(inventory['payload_reference'],observation['payload_reference'])
 events=inventory['events'];require(type(events)is list and len(events)<=2,'Single complete attempt only');integer(inventory['event_count'],len(events));exact(inventory['last_event_sha256'],events[-1]['event_sha256']if events else None)
 previous=None;start=None;reasons=[];state='NOT_ATTEMPTED'
 common={'schema','sequence','previous_event_sha256','event_sha256','event_type','observation_id','attempt_id','recorded_at_utc'}
 for i,e in enumerate(events):
  require(type(e)is dict,'Event object');exact(e['schema'],EVENT);integer(e['sequence'],i+1);exact(e['previous_event_sha256'],previous);exact(e['observation_id'],p['observation_id']);exact(e['event_sha256'],digest({k:v for k,v in e.items()if k!='event_sha256'}));record=utc(e['recorded_at_utc'])
  if i==0:
   exact(e['event_type'],'SEAL_STARTED');exact(sorted(e),sorted(common|{'attempt_identity','attempt_started_at_utc'}));identity=e['attempt_identity'];exact(identity,start_identity(p,observation,identity,s));exact(e['attempt_id'],digest(identity));started=utc(e['attempt_started_at_utc']);require(utc(r['publication_check_at_utc'])<=started<=record,'Attempt cannot precede persisted observation');reasons=eligibility(p,r,started,record);start=e;state='UNKNOWN_UNRESOLVED'
  else:
   require(e['event_type']in ('SEALED','FAILED'),'Only one terminal following START');exact(e['attempt_id'],start['attempt_id']);end=utc(e['attempt_completed_at_utc']);require(utc(start['recorded_at_utc'])<=end<=record,'Terminal time ordering')
   extra={'attempt_completed_at_utc','success_evidence'}if e['event_type']=='SEALED'else {'attempt_completed_at_utc','error'};exact(sorted(e),sorted(common|extra))
   if e['event_type']=='SEALED':
    require(not reasons and record<utc(p['conservative_deadline_utc']),'Successful seal prerequisites or deadline failed');success(e['success_evidence'],start,p,e['attempt_completed_at_utc'],s);state='SEALED_RESEARCH_EVIDENCE_ONLY'
   else:
    error=e['error'];require(type(error)is dict and {'error_type','message','stage','traceback'}<=set(error),'Complete original failure evidence');require(all(type(error[k])is str and error[k].strip()for k in ('error_type','message','stage'))and(error['traceback']is None or type(error['traceback'])is str),'Original failure fields');state='FAILED'
  previous=e['event_sha256']
 return dict(schema='OBSERVATION_SEAL_EVENT_STATE_RESEARCH_V1',state=state,observation_id=p['observation_id'],observation_references={k:deepcopy(observation[k])for k in REFS},session=p['session'],first_actual_observed_session_of_month=p['first_actual_observed_session_of_month'],month_first_actual_observation=p['month_first_actual_observation'],inventory=deepcopy(inventory),attempt_id=None if start is None else start['attempt_id'],event_count=len(events),terminal_event_present=len(events)==2,conditional_start_eligible=None if start is None else not reasons,start_ineligibility_reasons=reasons,source_hash_claims=s,inventory_authentication_role=SCOPE,time_boundary_evidence=dict(payload_reference=deepcopy(observation['payload_reference']),tzif_reference=deepcopy(p['tzif_reference']),conservative_close_utc=p['conservative_close_utc'],conservative_deadline_utc=p['conservative_deadline_utc'],basis='DEPENDENT_ON_BOUND_OBSERVATION_READBACK_NOT_TZIF_OR_CLOCK_REAUTHENTICATION'),success_evidence_role='FUTURE_VERSIONED_RESEARCH_INTERFACE_NOT_PRODUCTION_SEAL_AUTHORITY',**FLAGS)

def append_seal_event(*,observation,inventory,event_request):
 prior=derive_seal_state(observation=observation,inventory=inventory);require(type(event_request)is dict,'Explicit event request');p,r,s=observed(observation);n=prior['event_count'];kind=event_request['event_type'];require(n<2,'Terminal attempt cannot retry')
 common={'event_type','recorded_at_utc'}
 if n==0:
  require(kind=='SEAL_STARTED','First event must be START');exact(sorted(event_request),sorted(common|{'attempt_started_at_utc','candidate_calendar_reference','input_versions','input_references'}));identity=start_identity(p,observation,event_request,s);extra=dict(attempt_identity=identity,attempt_started_at_utc=event_request['attempt_started_at_utc']);attempt_id=digest(identity)
 else:
  require(kind in ('SEALED','FAILED'),'No automatic repeated START');key='success_evidence'if kind=='SEALED'else'error';exact(sorted(event_request),sorted(common|{'attempt_id','attempt_completed_at_utc',key}));attempt_id=event_request['attempt_id'];extra=dict(attempt_completed_at_utc=event_request['attempt_completed_at_utc'],**{key:deepcopy(event_request[key])})
 event=dict(schema=EVENT,sequence=n+1,previous_event_sha256=inventory['last_event_sha256'],event_type=kind,observation_id=p['observation_id'],attempt_id=attempt_id,recorded_at_utc=event_request['recorded_at_utc'],**extra);event['event_sha256']=digest(event)
 updated=deepcopy(inventory);updated['events'].append(event);updated['event_count']=len(updated['events']);updated['last_event_sha256']=event['event_sha256'];return derive_seal_state(observation=observation,inventory=updated)
