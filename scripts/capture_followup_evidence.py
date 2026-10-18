"""Explicit saved-journal follow-up capture; offline preflight by default."""
import argparse,json,os,re
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from data.current_quantity_v2_followup_provider import FollowupBundleProvider,canonical,safe_path,read_bytes,parse,STORAGE,MAX_TOTAL,MAX_FILES
from data.current_quantity_v2_followup_review import review_reference_followup,FORWARD_PATH,FORWARD_SHA
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources,fetch_daily_actions
from scripts.current_research_official_alert_capture import fetch_official_feed
from scripts.current_research_close_capture import capture_saved_close,default_fetch
CALENDAR='tmp/followup_capture_calendar_20261016_v1.json'
CALENDAR_SHA='fb9cce4e30f87864251fdd3e27608ff1c4fe1047dff0e0a0cc44cebdac5ed92b'
NY=ZoneInfo('America/New_York')
def now():return datetime.now(timezone.utc)
def require(ok,reason):
 if not ok:raise ValueError(reason)
def digest(raw):return sha256(raw).hexdigest()
def save(path,raw):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def reason(error):
 value=str(error)
 return value if type(error)is ValueError and re.fullmatch('[A-Z0-9_]{1,160}',value) else type(error).__name__
def guarded_replace(index,expected,new_raw):
 """Cross-process create-only reservation. Crashed reservations need explicit review."""
 lock=index.with_suffix('.lock');lock.parent.mkdir(parents=True,exist_ok=True)
 with lock.open('xb') as f:f.write(b'FOLLOWUP_INDEX_CAS');f.flush();os.fsync(f.fileno())
 temporary=index.with_suffix('.pending')
 try:
  current=parse(read_bytes(index,4096))['manifest_sha256'] if index.exists() else None
  require(current==expected,'INDEX_CAS_CONFLICT')
  save(temporary,new_raw);os.replace(temporary,index)
 finally:lock.unlink()
def preserve_progress(old,new):
 oldrows={(o['security_id'],h['sessions_after_reference']):h for o in old.get('orders',[]) for h in o['horizons']}
 newrows={(o['security_id'],h['sessions_after_reference']):h for o in new.get('orders',[]) for h in o['horizons']}
 for key,h in oldrows.items():
  if h['status']=='CONDITIONAL_PRICE_CHANGE':
   n=newrows.get(key)
   require(n is not None and n['status']=='CONDITIONAL_PRICE_CHANGE','COVERAGE_REGRESSION')
   require(all(n.get(k)==h.get(k) for k in ('target_session','closing_price','price_change_vs_reference')),'HISTORICAL_DATA_CONFLICT')
def run(*,root,event_day,event_id,event_sha256,decision_id,research_version,available_cash_exact,execute=False,clock=now,fetch=default_fetch,action_fetch=fetch_daily_actions,rss_fetch=fetch_official_feed):
 root=Path(root).resolve();observed=clock();require(observed.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
 require(re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',event_day) and re.fullmatch('[a-f0-9]{32}',event_id),'INVALID_EVENT_SELECTOR')
 binding=dict(decision_id=decision_id,research_version=research_version,available_cash_exact=available_cash_exact)
 event_path=f'events/{event_day}/{event_id}.json';journal=root/'data/quantity_v2_observations'
 event_raw=read_bytes(safe_path(journal,event_path),1024*1024);require(digest(event_raw)==event_sha256,'EVENT_CHANGED')
 event=parse(event_raw);started=datetime.fromisoformat(event['request_started_at']);original=datetime.fromisoformat(event['observed_at'])
 require(event['event_id']==event_id and started.tzinfo is not None and original.tzinfo is not None and started<=original<=observed and started.astimezone(NY).date().isoformat()==event_day,'EVENT_TIME_OR_ID')
 files={event_path:event_raw}
 for capture in event['captures']:
  name=capture['path'];require(name=='raw/'+capture['sha256']+'.bin','INVALID_CAPTURE_PATH')
  raw=read_bytes(safe_path(journal,name),32*1024*1024);require(digest(raw)==capture['sha256'],'ORIGINAL_CAPTURE_CHANGED');files[name]=raw
 def add_source(name,expected):
  raw=read_bytes(safe_path(root,name),32*1024*1024);require(digest(raw)==expected,'CALENDAR_SOURCE_CHANGED');files[name]=raw;return raw
 storage=root/STORAGE;index=storage/'index'/digest(canonical(binding))/(event_sha256+'.json')
 provider=FollowupBundleProvider(repository_root=root);old=provider.review(event_raw=event_raw,binding=binding,now=observed)
 require(old['status']!='BLOCKED_BUNDLE_VALIDATION','EXISTING_BUNDLE_INVALID')
 expected=parse(read_bytes(index,4096))['manifest_sha256'] if index.exists() else None
 require(old.get('bundle_sha256')==expected,'INDEX_CHANGED_DURING_PREFLIGHT')
 chain_sources={}
 if expected:
  bundle=safe_path(storage,'bundles/'+expected);manifest_raw=read_bytes(bundle/'manifest.json',4*1024*1024)
  require(digest(manifest_raw)==expected,'EXISTING_BUNDLE_CHANGED');saved_manifest=parse(manifest_raw)
  chain_sources=saved_manifest.get('trusted_chain_sources',{})
  for entry in chain_sources.values():
   name=entry['path'];content=read_bytes(safe_path(bundle/'sources',name),32*1024*1024)
   require(digest(content)==entry['sha256']==saved_manifest['source_hashes'][name],'EXISTING_CHAIN_CHANGED');files[name]=content
 records={row['reference']['pullback']['cap_record_hash'] for row in event.get('rows',[]) if row.get('reference',{}).get('pullback')}
 if not records.issubset(chain_sources):
  from data.current_quantity_v2_pullback_chain_source import read_pullback_chain_sources
  chain=read_pullback_chain_sources(repository_root=root,event_raws=[event_raw]);files.update(chain['files']);chain_sources.update(chain['record_paths'])
 calendar=parse(add_source(CALENDAR,CALENDAR_SHA));forward=parse(add_source(FORWARD_PATH,FORWARD_SHA))
 for document in (calendar,forward):
  for name,h in document['source_hashes'].items():add_source(name,h)
 require(len(files)<=MAX_FILES and sum(map(len,files.values()))<=MAX_TOTAL,'BUNDLE_SIZE_LIMIT')
 pins={p:digest(raw) for p,raw in files.items()}
 original_review=review_reference_followup(root=root,binding=binding,event_path=event_path,files=files,source_hashes=pins,trusted_chain_sources=chain_sources,daily_observations=[],now=observed)
 require(original_review['status']=='EVIDENCE_REVIEW_ONLY' and original_review['orders'],'ORIGINAL_REFERENCE_REQUIRED')
 days=calendar['calendar'];session=original.astimezone(NY).date().isoformat();require(session in days,'REFERENCE_CALENDAR_UNAVAILABLE');i=days.index(session)
 closed=[r['date'] for r in calendar['sessions'] if r['date']>session and datetime.fromisoformat(r['close_at'])<=observed]
 closed=[d for d in closed if d in days[i+1:i+21]]
 if not closed:return dict(status='WAITING_SESSION_CLOSE',http_calls=0,account_writes=False)
 target=closed[-1]
 matured=[h for h in (1,5,20) if i+h<len(days) and days[i+h]<=target]
 if not matured:return dict(status='WAITING_HORIZON_CLOSE',http_calls=0,account_writes=False)
 if expected and all(h['status']=='CONDITIONAL_PRICE_CHANGE' for o in old['orders'] for h in o['horizons'] if h['sessions_after_reference'] in matured):
  return dict(status='ALREADY_COVERED',manifest_sha256=expected,http_calls=0,account_writes=False)
 securities=[dict(security_id=o['security_id'],ticker=o['ticker'],security_type='EQUITY') for o in original_review['orders']]
 require(len({s['security_id'] for s in securities})==len(securities) and len({s['ticker'] for s in securities})==len(securities),'DUPLICATE_SECURITY')
 plan=dict(status='PREFLIGHT_ONLY',event_sha256=event_sha256,binding=binding,session=target,securities=securities,matured_horizons=matured,expected_manifest_sha256=expected,http_calls=0,account_writes=False)
 attempt=safe_path(storage,'attempts/'+event_sha256+'/'+target)
 if any(p.exists() or p.is_symlink() for p in (index.with_suffix('.pending'),index.with_suffix('.lock'))):
  return dict(plan,status='NEEDS_RECOVERY',reason='INDEX_PUBLICATION_RECOVERY_REQUIRED')
 if attempt.exists():
  if not execute:return dict(plan,status='NEEDS_RECOVERY',reason='INDEX_PUBLICATION_RECOVERY_REQUIRED' if index.with_suffix('.pending').exists() or index.with_suffix('.lock').exists() else 'PRIOR_CAPTURE_FAILED_REQUIRES_REVIEW' if (attempt/'failed.json').exists() else 'PARTIAL_CAPTURE_REQUIRES_REVIEW')
  raise ValueError('ATTEMPT_EXISTS_NO_RETRY')
 if not execute:return plan
 attempt.mkdir(parents=True)
 save(attempt/'started.json',canonical(plan))
 try:
  observations=[]
  # One source per original security; never expand into unrelated journal files.
  for ordinal,security in enumerate(securities):
   directory=(attempt/('daily-'+str(ordinal))).relative_to(root).as_posix()
   manifest=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session=target,history_start_date=session,calendar_path=CALENDAR,calendar_source_hashes={CALENDAR:CALENDAR_SHA,**calendar['source_hashes']},securities=[security],output_directory=directory)
   path=attempt/('capture-'+str(ordinal)+'.json');raw=canonical(manifest);save(path,raw)
   result=capture_saved_close(path.relative_to(root).as_posix(),digest(raw),root=root,capture=True,fetch=fetch,clock=clock)
   entry=result['entries'][0];require(entry['status']=='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED','DAILY_CAPTURE_FAILED')
   for suffix in ('.response.bin','.receipt.json','.decoded.json'):
    name='daily/'+str(ordinal)+'/'+security['ticker']+suffix;files[name]=read_bytes(root/directory/(security['ticker']+suffix),32*1024*1024)
   observations.extend(dict(security_id=security['security_id'],ticker=security['ticker'],date=d,relative_directory='daily/'+str(ordinal),entry=entry) for d in closed)
  transport_number=[0]
  def retained(kind,function,*args,**kwargs):
   number=transport_number[0];transport_number[0]+=1
   try:
    response=function(*args,**kwargs);body=response.get('body')
    if isinstance(body,bytes):save(attempt/f'{kind}-{number}.raw',body)
    save(attempt/f'{kind}-{number}.transport.json',canonical(dict(status=response.get('status'),received_at=clock().isoformat())))
    return response
   except Exception as error:
    save(attempt/f'{kind}-{number}.failed.json',canonical(dict(error_type=type(error).__name__,reason=reason(error),at=clock().isoformat())));raise
  action=PaperActionEvidenceSources(fetch=lambda *a,**k:retained('actions',action_fetch,*a,**k),rss_fetch=lambda:retained('rss',rss_fetch),clock=clock).capture(dict(account_id='followup:'+event_sha256,state_revision=event_sha256,window_start=original.isoformat(),observed_floor=original.isoformat(),securities={s['security_id']:{'ticker':s['ticker']} for s in securities},current_target_quantities={}))
  files.update(action['files']);documents=action['documents'];evidence={s['security_id']:dict(daily_receipt_path=documents['action_receipts'][s['security_id']],rss_raw_path=documents['rss_raw'],rss_receipt_path=documents['rss_receipt']) for s in securities}
  require(len(files)<=MAX_FILES and sum(map(len,files.values()))<=MAX_TOTAL,'BUNDLE_SIZE_LIMIT')
  pins={p:digest(raw) for p,raw in files.items()}
  manifest=dict(schema='V2_FOLLOWUP_BUNDLE_V1',binding=binding,event_path=event_path,event_sha256=event_sha256,source_hashes=pins,trusted_chain_sources=chain_sources,daily_observations=observations,action_evidence=evidence)
  raw=canonical(manifest);bundle_hash=digest(raw);directory=storage/'bundles'/bundle_hash
  require(not directory.exists(),'BUNDLE_ALREADY_EXISTS')
  save(directory/'manifest.json',raw)
  for name,content in files.items():save(safe_path(directory/'sources',name),content)
  reviewed=review_reference_followup(root=directory/'sources',binding=binding,event_path=event_path,files=files,source_hashes=pins,trusted_chain_sources=chain_sources,daily_observations=observations,action_evidence=evidence,now=clock())
  require(all(pins.get(p)==h for p,h in reviewed['source_hashes'].items()),'UNDECLARED_REVIEW_SOURCE')
  save(attempt/'review.json',canonical(reviewed))
  require(reviewed['status']=='EVIDENCE_REVIEW_ONLY','BUNDLE_REVIEW_FAILED')
  require(all(h['status']=='CONDITIONAL_PRICE_CHANGE' for o in reviewed['orders'] for h in o['horizons'] if h['sessions_after_reference'] in matured),'MATURED_HORIZON_UNRESOLVED')
  preserve_progress(old,reviewed)
  if expected:
   from data.current_research_saved_quote import read_saved_quote
   from fractions import Fraction
   old_directory=storage/'bundles'/expected;old_manifest=parse(read_bytes(old_directory/'manifest.json',4*1024*1024))
   new_by_key={(r['security_id'],r['date']):r for r in observations};closes={r['date']:r['close_at'] for r in calendar['sessions']}
   for prior in old_manifest['daily_observations']:
    key=(prior['security_id'],prior['date']);require(key in new_by_key,'DAILY_COVERAGE_REGRESSION');current=new_by_key[key]
    require(current['ticker']==prior['ticker'],'DAILY_IDENTITY_CONFLICT')
    def quote_at(base,item):
     return read_saved_quote(root=base,ticker=item['ticker'],expected_security_type='EQUITY',entry=item['entry'],relative_directory=item['relative_directory'],decision_date=item['date'],decision_session_close_at=closes[item['date']])['ohlc']
    left=quote_at(old_directory/'sources',prior);right=quote_at(directory/'sources',current)
    require(all(Fraction(left[k])==Fraction(right[k]) for k in ('open','high','low','close')),'HISTORICAL_DATA_CONFLICT')
  guarded_replace(index,expected,canonical(dict(manifest_sha256=bundle_hash)))
  answer=dict(status='FOLLOWUP_PUBLISHED',manifest_sha256=bundle_hash,previous_manifest_sha256=expected,session=target,matured_horizons=matured,account_writes=False,actual_fill_inferred=False)
  save(attempt/'complete.json',canonical(answer));return answer
 except Exception as error:
  save(attempt/'failed.json',canonical(dict(status='BLOCKED',reason=reason(error),at=clock().isoformat(),retry_allowed=False)));raise

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('root','event-day','event-id','event-sha256','decision-id','research-version','available-cash-exact'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--execute',action='store_true')
 try:answer=run(**vars(parser.parse_args(argv)))
 except Exception as error:answer=dict(status='BLOCKED',reason=reason(error),account_writes=False)
 print(json.dumps(answer));return 2 if answer['status']=='BLOCKED' else 0
if __name__=='__main__':raise SystemExit(main())
