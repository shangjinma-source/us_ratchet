"""Bounded saved-event follow-up dispatcher; no accounts or scheduler changes."""
import argparse,json,re
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from scripts.capture_followup_evidence import run as capture,reason
from data.current_quantity_v2_followup_provider import STORAGE,read_bytes,parse,safe_path
VERSION='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
def now():return datetime.now(timezone.utc)
def require(ok,code):
 if not ok:raise ValueError(code)
def run(*,root,max_scan=100,max_dispatch=10,after=None,execute=False,clock=now,single_event=capture):
 root=Path(root).resolve();journal=root/'data/quantity_v2_observations';events=journal/'events'
 require(type(max_scan)is int and 1<=max_scan<=10000 and type(max_dispatch)is int and 1<=max_dispatch<=100,'INVALID_BATCH_LIMIT')
 require(after is None or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}/[a-f0-9]{32}\.json',after),'INVALID_SCAN_CURSOR')
 observed=clock();require(observed.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
 counts=dict(scanned=0,malformed=0,non_ready=0,waiting=0,already_covered=0,prior_attempt_blocked=0,due=0,dispatched=0,failed=0)
 rows=[];due=[];last=after;partial=False
 # Filename cursor orders discovery; actual due work within this bounded page sorts by event time.
 if events.exists():
  require(not events.is_symlink() and events.resolve().is_relative_to(root),'EVENT_ROOT_ESCAPE')
  for day in sorted(events.iterdir(),key=lambda p:p.name):
   if not day.is_dir() or day.is_symlink() or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',day.name):continue
   for path in sorted(day.iterdir(),key=lambda p:p.name):
    if not path.is_file() or path.suffix!='.json':continue
    cursor=day.name+'/'+path.name
    if after is not None and cursor<=after:continue
    if counts['scanned']>=max_scan:partial=True;break
    counts['scanned']+=1;last=cursor
    try:
     require(re.fullmatch(r'[a-f0-9]{32}\.json',path.name) and not path.is_symlink(),'EVENT_PATH_INVALID')
     raw=read_bytes(safe_path(journal,'events/'+cursor),1024*1024);event=parse(raw)
     if event.get('status')!='READY':counts['non_ready']+=1;continue
     context=event['research_context'];binding=dict(decision_id=event['decision_id'],research_version=context['research_version'],available_cash_exact=context['available_cash_exact'])
     require(binding['research_version']==VERSION and context['research_id']==binding['decision_id'][:24],'EVENT_BINDING_INVALID')
     stamp=datetime.fromisoformat(event['observed_at']);require(stamp.tzinfo is not None and stamp<=observed,'EVENT_TIME_INVALID')
     args=dict(root=root,event_day=day.name,event_id=path.stem,event_sha256=sha256(raw).hexdigest(),**binding)
     pre=single_event(**args,execute=False,clock=clock)
     item=dict(event=cursor,event_sha256=args['event_sha256'],status=pre['status'])
     if pre['status']=='PREFLIGHT_ONLY':
      counts['due']+=1;due.append((stamp,cursor,args,item))
     elif pre['status'] in ('PRIOR_ATTEMPT_REQUIRES_REVIEW','NEEDS_RECOVERY'):
      counts['prior_attempt_blocked']+=1;item.update(status='NEEDS_RECOVERY',reason=pre.get('reason','PRIOR_ATTEMPT_REQUIRES_REVIEW'))
     elif pre['status']=='ALREADY_COVERED':counts['already_covered']+=1
     else:counts['waiting']+=1
     rows.append(item)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
     counts['malformed']+=1;rows.append(dict(event=cursor,status='SKIPPED_INVALID_EVENT_OR_SOURCE',reason=reason(error)))
   if partial:break
 due.sort(key=lambda v:(v[0],v[1]))
 for _,cursor,args,item in due[:max_dispatch]:
  if not execute:item['status']='DUE_READ_ONLY';continue
  try:
   result=single_event(**args,execute=True,clock=clock);item['status']=result['status'];counts['dispatched']+=1
  except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
   item.update(status='BLOCKED',reason=reason(error));counts['failed']+=1
 deferred=len(due)>max_dispatch
 return dict(status='PARTIAL_SCAN' if partial else 'PARTIAL_DISPATCH' if deferred else 'BATCH_CHECK_COMPLETE',execute=execute,counts=counts,events=rows,next_scan_cursor=after if deferred else last if partial else None,repeat_current_page=deferred,dispatch_deferred=deferred,scan_order='DATE_AND_FILENAME_CURSOR',dispatch_order='OLDEST_OBSERVED_FIRST_WITHIN_SCANNED_PAGE',scope='Pagination must continue before claiming complete journal coverage. Restarting only the first page may starve later pages.',account_writes=False,automatic_orders=False)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--max-scan',type=int,default=100);p.add_argument('--max-dispatch',type=int,default=10);p.add_argument('--after');p.add_argument('--execute',action='store_true')
 try:r=run(**vars(p.parse_args(argv)))
 except Exception as error:r=dict(status='BLOCKED',reason=reason(error),account_writes=False)
 print(json.dumps(r));return 2 if r['status']=='BLOCKED' or r.get('counts',{}).get('failed') else 0
if __name__=='__main__':raise SystemExit(main())
