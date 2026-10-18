"""Independent snapshot-only variable-prefix capture readback. No production calls."""
import argparse,csv,hashlib,io,json,os
from datetime import date,datetime,time,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/variable_prefix_source_capture_20261003_v1'
OUTPUT=ROOT/'data/cache/research/variable_prefix_capture_independent_readback_20261003_v1'
CAPTURE_SHA='435c1129792aaec3a52c7d156a39f34cf594838e1d406a833ddd55dc86ae878e'
PUBLICATION_SHA='16bd9eaf7da6e36eaa1b2d927e0749ea77c5f5885b5eddd28daa069f4171cadf'
PARENT_BOUND={
 'reference':('data/cache/research/prospective_observation_parent_history_20261003_v1/history.json','bd0eb3bb1ed5a4103af964e4c2016caf8e5abf45caf799ffbf786642bc7a4a33'),
 'publication_reference':('data/cache/research/prospective_observation_parent_history_20261003_v1/publication.json','648f6937e7ff876a824bab96a654461b411dccd6b4c7a6a19217d0bdd09fbcf6'),
 'readback_reference':('data/cache/research/prospective_observation_parent_history_independent_readback_20261003_v1/independent_readback.json','c6f9a113b1b5f00128befa74a415e6604012d47ac17eb7db2048dafa8a31a86a'),
 'reader_reference':('scripts/ndx_prospective_observation_parent_history_independent_readback_20261003.py','876094538679db3216f69cf3035101baf91498d5296512cbef4b2911486d7aef')}
PINS={
 'producer':('scripts/ndx_variable_prefix_source_capture_20261003.py','d945f34bb1d4f2affe9dc77b839ed3166cdaebbd1592f6340336bb883841a715'),
 'core':('backtest/ndx_variable_prefix_capture_research.py','9c76324fcbc8e5d57a1ef25566a59110acff32a58506c6d5b6947996e6c26039'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'tzif':('D:/python/Lib/site-packages/tzdata/zoneinfo/America/New_York','d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9')}
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
PURE_FALSE=('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified','timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','partial_recovery_performed','missed_events_created')
WRAPPER_FALSE=PURE_FALSE+('network_quote_refresh_performed','old_audit_repeated','full_transitive_source_closure_reverified')
FIELDS=['Date','Open','High','Low','Close','Volume']

def require(ok,message):
 if not ok:raise ValueError(message)
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(encode(a)==encode(b),'Exact content/types mismatch')
def sha(b):return hashlib.sha256(b).hexdigest()
def reference(path,digest):
 require(type(path)is str and path and path.strip()==path and type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef'for c in digest),'Pending/invalid external anchor');return dict(path=path,sha256=digest)
def ref(r):require(type(r)is dict and set(r)=={'path','sha256'},'Exact reference fields');return reference(r['path'],r['sha256'])
def merge(s,r):
 ref(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Conflicting source closure');s[r['path']]=r['sha256']
def count(v,n):require(type(v)is int and v==n,'Strict integer count')
def flags(v,names):
 for k in names:require(v[k]is False,'False authority required: '+k)
def utc(s):
 require(type(s)is str,'Clock string');v=datetime.fromisoformat(s.replace('Z','+00:00'));require(v.tzinfo is not None and v.utcoffset().total_seconds()==0,'UTC clock');return v

def inspect_parent(parent):
 h,p,a=parent['document'],parent['publication'],parent['readback'];claims={}
 for k in ('reference','publication_reference','readback_reference','reader_reference'):merge(claims,parent[k])
 exact(h['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2');exact(h['policy_id'],POLICY)
 exact(p['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2');exact(p['status'],'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL')
 exact(a['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2');exact(a['status'],'PASS')
 exact(p['history_reference'],parent['reference']);exact(a['history_reference'],parent['reference']);exact(a['publication_reference'],parent['publication_reference']);exact(a['reader_sha256'],parent['reader_reference']['sha256']);exact(h['source_hashes'],p['source_hashes'])
 for d in (h,p,a):
  flags(d,('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'))
  for path,digest in d['source_hashes'].items():merge(claims,reference(path,digest))
 for path,digest in h['source_hashes'].items():exact(a['source_hashes'][path],digest)
 for k in ('reference','publication_reference','reader_reference'):exact(a['source_hashes'][parent[k]['path']],parent[k]['sha256'])
 rows=h['known_typed_rows'];require(type(rows)is list and 66<=len(rows)<20000,'Complete variable history');days=[];months={}
 for i,r in enumerate(rows):
  count(r['sequence'],i+1);day=r['session'];require(type(day)is str and date.fromisoformat(day).isoformat()==day and date.fromisoformat(day).weekday()<5 and (not days or day>days[-1]),'Complete unique weekday order');days.append(day)
  require(r['kind']in ('SEALED_PARENT_OBSERVED_SESSION','MISSED_OBSERVATION','PROSPECTIVE_OBSERVED_SESSION'),'Typed kind');require(r['seal_status']in ('SEALED','NOT_ATTEMPTED','FAILED','UNKNOWN'),'Seal status')
  if r['kind']=='MISSED_OBSERVATION':exact(r['seal_status'],'NOT_ATTEMPTED')
  else:months.setdefault(day[:7],day)
 genesis=h['genesis_preserved']['document']['projection_inputs']['known_rows'];count(len(genesis),65);exact(rows[:65],genesis);count(sum(r['kind']=='MISSED_OBSERVATION'for r in genesis),5);count(sum(r['kind']=='SEALED_PARENT_OBSERVED_SESSION'for r in genesis),60)
 entries=h['observations'];inventory=h['parent_attempt_inventory'];count(len(entries),len(rows)-65);count(len(inventory),len(entries));count(h['observation_count'],len(entries));seen=set()
 for i,(entry,attempt)in enumerate(zip(entries,inventory)):
  exact(entry['schema'],'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1');require(entry['original_payload_embedded']is False and not any(k in entry for k in ('payload','receipt','audit','base64','original_csv_bytes_base64')),'Compact history only');count(entry['sequence'],66+i);exact(entry['session'],rows[65+i]['session']);exact(rows[65+i]['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(entry['observation_id'],sha(encode(entry['observation_identity'])));require(entry['observation_id']not in seen,'Unique observation IDs');seen.add(entry['observation_id'])
  for key in ('payload_reference','receipt_reference','audit_reference'):ref(entry[key])
  expected=dict(observation_id=entry['observation_id'],session=entry['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=entry['payload_reference'],receipt_reference=entry['receipt_reference'],independent_readback_reference=entry['audit_reference']);exact(attempt,expected);exact(rows[65+i]['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'))
 exact(h['last_accounted_session'],days[-1]);exact(h['first_actual_observed_session_by_month'],months)
 count(a['counts']['typed_row_count'],len(rows));count(a['counts']['observation_count'],len(entries));count(a['counts']['new_observation_count'],1);exact(a['counts']['first_actual_observed_session_by_month'],months)
 exact(sorted(h['baseline_references']),['QQQ','SPY']);exact(h['baseline_references'],entries[-1]['captured_baseline_references'])
 for r in h['baseline_references'].values():merge(claims,r);exact(a['source_hashes'][r['path']],r['sha256'])
 return days,months,claims

def csv_rows(raw,scope):
 require(type(raw)is bytes and 0<len(raw)<=8000000,'Bounded CSV');reader=csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''));exact(next(reader),FIELDS);rows=[];anomalies=[];previous=''
 for index,cells in enumerate(reader):
  if not cells:continue
  require(index<20000 and len(cells)==6 and all(type(v)is str and v and v.strip()==v for v in cells),'Full CSV record');r=dict(zip(FIELDS,cells));day=cells[0];d=date.fromisoformat(day);require(d.isoformat()==day and d.weekday()<5 and day>previous,'CSV unique weekday chronology');previous=day;values={}
  for field,value in zip(FIELDS[1:],cells[1:]):
   require(len(value)<=100,'Bounded numeric');n=Decimal(value);require(n.is_finite()and len(n.as_tuple().digits)<=50 and -50<=n.as_tuple().exponent<=50 and (n>=0 if field=='Volume'else n>0),'Finite positive OHLCV');values[field]=n
  issues=[]
  for left,right,reason in [('Low','Open','LOW_EXCEEDS_OPEN'),('Low','Close','LOW_EXCEEDS_CLOSE'),('Open','High','HIGH_BELOW_OPEN'),('Close','High','HIGH_BELOW_CLOSE'),('Low','High','LOW_EXCEEDS_HIGH')]:
   if values[left]>values[right]:issues.append(reason)
  require(day<scope or not issues,'Required OHLC invalid');rows.append(r)
  if issues:anomalies.append(dict(original_data_row_index=len(rows)-1,session=day,raw_csv_row=r,violations=issues,role='OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'))
 require(rows and any(r['Date']>=scope for r in rows),'Nonempty required scope');return rows,anomalies

def inspect_plan(*,plan,parent,source_bytes,source_references,baseline_bytes,tzif_bytes,tzif_reference,start,end):
 days,months,claims=inspect_parent(parent);begin,finish=utc(start),utc(end);require(begin<=finish,'Nonreversed acquisition interval');ref(tzif_reference);require(type(tzif_bytes)is bytes and 0<len(tzif_bytes)<=100000 and sha(tzif_bytes)==tzif_reference['sha256'],'Exact TZif snapshot');zone=ZoneInfo.from_file(io.BytesIO(tzif_bytes),key='America/New_York');merge(claims,tzif_reference)
 for v in (source_bytes,source_references,baseline_bytes):exact(sorted(v),['QQQ','SPY'])
 evidence={};diagnostics=[];newdates={}
 for ticker in ('QQQ','SPY'):
  current=source_references[ticker];baseline=parent['document']['baseline_references'][ticker]
  for raw,r in ((source_bytes[ticker],current),(baseline_bytes[ticker],baseline)):ref(r);require(sha(raw)==r['sha256'],'Raw snapshot SHA');merge(claims,r)
  old,oldissues=csv_rows(baseline_bytes[ticker],days[0]);new,newissues=csv_rows(source_bytes[ticker],days[0])
  if new[:len(old)]!=old:diagnostics.append(dict(ticker=ticker,reason='FULL_ORIGINAL_PREFIX_CHANGED'))
  oldscope=[r for r in old if r['Date']>=days[0]];newscope=[r for r in new if r['Date']>=days[0]];prior=[r for r in newscope if r['Date']<=days[-1]]
  if [r['Date']for r in oldscope]!=days:diagnostics.append(dict(ticker=ticker,reason='BASELINE_NOT_EXACT_ACCOUNTED_PREFIX'))
  if [r['Date']for r in prior]!=days:diagnostics.append(dict(ticker=ticker,reason='SOURCE_PARENT_PREFIX_MISSING_OR_EXTRA'))
  oldmap={r['Date']:r for r in oldscope};changed=[r['Date']for r in prior if r['Date']in oldmap and r!=oldmap[r['Date']]]
  if changed:diagnostics.append(dict(ticker=ticker,reason='PARENT_SOURCE_REVISION',sessions=changed))
  newdates[ticker]=[r['Date']for r in newscope if r['Date']>days[-1]]
  evidence[ticker]=dict(source_reference=current,baseline_reference=baseline,original_byte_count=len(source_bytes[ticker]),original_row_count=len(new),baseline_row_count=len(old),excluded_before_scope_ohlc_diagnostics=newissues,baseline_excluded_before_scope_ohlc_diagnostics=oldissues,new_session_dates=newdates[ticker])
 if newdates['QQQ']!=newdates['SPY']:diagnostics.append(dict(reason='SOURCE_NEW_DATES_DISAGREE'))
 if any(len(v)>1 for v in newdates.values()):diagnostics.append(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'))
 candidate=newdates['QQQ'][0]if not diagnostics and len(newdates['QQQ'])==1 else None
 if candidate and begin<datetime.combine(date.fromisoformat(candidate),time(16),zone).astimezone(timezone.utc):diagnostics.append(dict(reason='CAPTURE_NOT_ENTIRELY_AFTER_CONSERVATIVE_CLOSE'));candidate=None
 expected=dict(schema='COMPACT_HISTORY_VARIABLE_PREFIX_CAPTURE_PLAN_V1',status='BLOCKED_SOURCE_DIAGNOSTICS'if diagnostics else ('ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED'if candidate else 'NO_NEW_SESSION'),parent_history_reference=parent['reference'],parent_publication_reference=parent['publication_reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows_preserved=parent['document']['known_typed_rows'],parent_attempt_inventory_preserved=parent['document']['parent_attempt_inventory'],baseline_references=parent['document']['baseline_references'],source_evidence=evidence,source_reference_claims=claims,scope_start=days[0],last_accounted_session=days[-1],candidate_session=candidate,candidate_sequence=len(days)+1 if candidate else None,first_actual_observed_session_by_month_preserved=months,proposed_first_actual_session_of_month=months.get(candidate[:7],candidate)if candidate else None,capture_started_at=start,capture_completed_at=end,capture_completed_new_york=finish.astimezone(zone).isoformat(),capture_calendar_day_lag=(finish.astimezone(zone).date()-date.fromisoformat(candidate)).days if candidate else None,timing_role='AFTER_CONSERVATIVE_1600_CLOSE_ONLY_NOT_DEADLINE_OR_TIMELY_RECEIPT_CERTIFICATION',tzif_reference=tzif_reference,diagnostics=diagnostics,raw_bytes_embedded=False,authentication_role='CALLER_SUPPLIED_HISTORY_AUDIT_ASSERTIONS_NOT_FILE_AUTHENTICATION',**dict.fromkeys(PURE_FALSE,False))
 exact(plan,expected)
 return dict(status=expected['status'],parent_typed_row_count=len(days),parent_observed_count=len(days)-5,parent_gap_count=5,candidate_session=candidate,diagnostic_count=len(diagnostics),snapshot_counts={t:evidence[t]['original_row_count']for t in evidence})

def load_json(raw):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read(r,s):
 merge(s,r);p=Path(r['path']);require(p.is_file()and not p.is_symlink(),'Regular immutable source');raw=p.read_bytes();require(sha(raw)==r['sha256'],'Source SHA');return raw
def configured(bound):
 out={}
 for k,v in bound.items():require(type(v)is tuple and len(v)==2,'Pending configured parent');out[k]=reference(str(ROOT/v[0]),v[1])
 return out
def no_live(s):
 forbidden={str((ROOT/'data/cache'/f'{t}.csv').resolve())for t in ('QQQ','SPY')};require(all(str(Path(p).resolve())not in forbidden for p in s),'Live cache excluded from permanent readback')
def guard(s):
 no_live(s)
 for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift');require(not (Path(p).parent/'failure.json').exists(),'Failed immutable namespace')
def namespace(path,names):
 items=list(path.iterdir());exact(sorted(p.name for p in items),sorted(names));require(all(p.is_file()and not p.is_symlink()for p in items),'Exact regular namespace')
def save(path,obj):
 raw=encode(obj)
 with path.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Saved report bytes');return reference(str(path),sha(raw))

def readback(*,execute=False):
 require(execute is True,'Explicit readback');cr=reference(str(PARENT/'capture.json'),CAPTURE_SHA);pr=reference(str(PARENT/'publication.json'),PUBLICATION_SHA);parents=configured(PARENT_BOUND);pins=configured(PINS) # All pending checks precede IO.
 require(not OUTPUT.exists(),'Create-only no retry');s={str(SOURCE):LOADED};capture=load_json(read(cr,s));publication=load_json(read(pr,s));parent=dict(parents)
 for role,key in [('reference','document'),('publication_reference','publication'),('readback_reference','readback')]:parent[key]=load_json(read(parents[role],s))
 read(parents['reader_reference'],s);inputrefs={k:v for k,v in pins.items()if k!='producer'}
 exact(capture['schema'],'SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1');exact(publication['schema'],'VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1');exact(publication['status'],'PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION');exact(publication['capture_reference'],cr);exact(capture['parent_references'],parents);exact(capture['input_references'],inputrefs);flags(capture,WRAPPER_FALSE);flags(publication,WRAPPER_FALSE)
 require(capture['clock_captured_by_runner']is True and capture['external_clock_attestation_verified']is False,'Clock capture is not attestation');exact(capture['quote_source_type'],'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH');exact(capture['current_cache_verification_scope'],'CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE')
 _,_,parentclaims=inspect_parent(parent);base={}
 for r in pins.values():read(r,s);merge(base,r)
 for r in parents.values():merge(base,r)
 for obj in (parent['document'],parent['publication'],parent['readback']):
  for p,h in obj['source_hashes'].items():merge(base,reference(p,h))
 baseline={t:read(parent['document']['baseline_references'][t],s)for t in ('QQQ','SPY')}
 for r in parent['document']['baseline_references'].values():merge(base,r)
 no_live(base);sources=dict(base);artifacts=capture['captured_artifacts'];exact(sorted(artifacts),['QQQ','SPY','tzif']);snapshots={}
 for t in ('QQQ','SPY'):
  exact(artifacts[t]['path'],str(PARENT/f'{t}.csv'));snapshots[t]=read(artifacts[t],s);merge(sources,artifacts[t]);exact(capture['current_cache_references'][t],reference(str(ROOT/'data/cache'/f'{t}.csv'),artifacts[t]['sha256']))
 exact(sorted(capture['current_cache_references']),['QQQ','SPY']);exact(artifacts['tzif']['path'],str(PARENT/'New_York.tzif'));tz=read(artifacts['tzif'],s);exact(artifacts['tzif']['sha256'],pins['tzif']['sha256']);merge(sources,artifacts['tzif']);exact(capture['source_hashes'],sources);exact(publication['source_hashes'],sources)
 for path,digest in sources.items():merge(s,reference(path,digest))
 started_path=PARENT/'started.json';started_raw=started_path.read_bytes();started_ref=reference(str(started_path),sha(started_raw));merge(s,started_ref);started=load_json(started_raw);exact(started['schema'],'VARIABLE_PREFIX_CAPTURE_STARTED_V1');exact(started['parent_references'],parents);exact(started['input_references'],inputrefs);exact(started['source_hashes'],base);require(started['retry_allowed']is False,'No retry');flags(started,WRAPPER_FALSE)
 folder=Path(parents['reference']['path']).parent;exact(parents['reference']['path'],str(folder/'history.json'));exact(parents['publication_reference']['path'],str(folder/'publication.json'))
 def final_guard():
  namespace(PARENT,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'));namespace(folder,('started.json','history.json','publication.json'));guard(s)
 final_guard();OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',dict(schema='VARIABLE_PREFIX_CAPTURE_READBACK_STARTED_V1',capture_reference=cr,publication_reference=pr,reader_sha256=LOADED,**dict.fromkeys(WRAPPER_FALSE,False)))
  result=inspect_plan(plan=capture['plan'],parent=parent,source_bytes=snapshots,source_references={t:artifacts[t]for t in ('QQQ','SPY')},baseline_bytes=baseline,tzif_bytes=tz,tzif_reference=artifacts['tzif'],start=capture['capture_started_at'],end=capture['capture_completed_at']);final_guard()
  report=save(OUTPUT/'independent_readback.json',dict(schema='VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1',status='PASS',capture_reference=cr,publication_reference=pr,parent_references=parents,reader_sha256=LOADED,source_hashes=s,counts=result,started_reference_observed_not_external_anchor=started_ref,started_externally_authenticated=False,current_live_cache_read_or_reverified=False,producer_called=False,plan_history_capture_called=False,snapshot_bytes_verified=True,external_clock_attestation_verified=False,market_price_identity_verified=False,**dict.fromkeys(WRAPPER_FALSE,False)));final_guard();require(sha(Path(report['path']).read_bytes())==report['sha256'],'Final report SHA');namespace(OUTPUT,('started.json','independent_readback.json'));return report
 except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
