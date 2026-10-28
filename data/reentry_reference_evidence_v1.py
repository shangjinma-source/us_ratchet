"""Offline, server-pinned reference history reviewer. No capture or account writes.

Approved configuration is a server trust anchor, never a browser-supplied hash.
Public action coverage is conditional; source bytes are authenticated, not complete
proof of every historical issuer action. Unknown events or unit changes WAIT.
"""
from datetime import datetime,timezone,date
from fractions import Fraction as F
from hashlib import sha256
import json,re
from zoneinfo import ZoneInfo
from pathlib import Path
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_rolling_parent_v3 import pinned
from data.current_quantity_v2_paper_action_sources import daily_url,stamp
from data.strategy_account_identity import PinnedStrategyIdentity
from data import saved_frontier_first_window_v1 as notice_scope
from xml.etree.ElementTree import ParseError
from scripts.current_research_official_alert_capture import parse_official_feed,URL


def review_reference_interval(*,root,configuration_reference,lock,decision_session,as_of,capture_files=None):
 try:return _review(root=root,configuration_reference=configuration_reference,lock=lock,decision_session=decision_session,as_of=as_of,capture_files=capture_files)
 except (ValueError,KeyError,TypeError,IndexError,OSError,ArithmeticError,ParseError,UnicodeError) as error:
  return dict(status='WAIT_REFERENCE_SOURCE',reason=str(error),evidence=None,coverage_complete=False,orders_created=False)


def _review(*,root,configuration_reference,lock,decision_session,as_of,capture_files):
 pins={};bodies={};now=stamp(as_of)
 def read(ref,maximum=8*1024*1024):
  body=pinned(root,ref,maximum=maximum);name=ref['path'];require(name not in pins or pins[name]==ref['sha256'],'REFERENCE_SOURCE_COLLISION');pins[name]=ref['sha256'];bodies[name]=body
  if capture_files is not None and name in capture_files:require(capture_files[name]==body,'REFERENCE_CAPTURE_BYTES_CHANGED')
  require(sum(map(len,bodies.values()))<=64*1024*1024,'REFERENCE_SOURCE_BUDGET');return body
 config=json.loads(read(configuration_reference));require(config['reviewer_sha256']==sha256(Path(__file__).read_bytes()).hexdigest(),'REFERENCE_REVIEWER_VERSION');require(config['schema']=='SERVER_REFERENCE_INTERVAL_V1','REFERENCE_CONFIG_SCHEMA')
 require(config['origin_security_id']==lock['security_id'] and config['origin_unit_id']==lock['unit_id'] and config['exit_session']==lock['exit_session'] and config['decision_session']==decision_session,'REFERENCE_CONFIG_LOCK_BINDING')
 calendar=json.loads(read(config['calendar']));require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','REFERENCE_CALENDAR_SCHEMA')
 sessions=calendar['sessions'];dates=[r['date'] for r in sessions];require(dates==sorted(set(dates)) and lock['exit_session'] in dates and decision_session in dates,'REFERENCE_CALENDAR_RANGE')
 for row in sessions:
  opened,closed=stamp(row['open']),stamp(row['close']);require(opened<closed and opened.astimezone(ZoneInfo('America/New_York')).date().isoformat()==row['date']==closed.astimezone(ZoneInfo('America/New_York')).date().isoformat(),'REFERENCE_CALENDAR_CLOCK')
 window=dates[dates.index(lock['exit_session']):dates.index(decision_session)+1];require(len(window)>=2,'REFERENCE_EXIT_EXCLUSIVE_WINDOW')
 clocks={r['date']:r for r in sessions};require(stamp(clocks[decision_session]['close'])<=now,'REFERENCE_UNCOMPLETED_SESSION')
 approved=json.loads(read(config['approved_actions']));require(approved['schema']=='SERVER_APPROVED_REFERENCE_ACTIONS_V1','REFERENCE_APPROVED_ACTION_SCHEMA')
 facts=approved['facts'];require(isinstance(facts,list),'REFERENCE_FACTS_REQUIRED');used=set()
 def fact_for(event,sid):
  observed_hash=sha256(canonical(event)).hexdigest();matches=[f for f in facts if f.get('provider_security_id',f['security_id'])==sid and f['provider_event_sha256']==observed_hash]
  require(len(matches)==1,'REFERENCE_EVENT_NOT_EXACTLY_APPROVED');fact=matches[0]
  raw=read(fact['official_raw']);receipt=json.loads(read(fact['official_receipt']));require(receipt['http_status']==200 and receipt['body_truncated'] is False and receipt['transport_error'] is None and receipt['raw_sha256']==sha256(raw).hexdigest() and receipt['stored_bytes']==len(raw) and receipt['url']==fact['official_url'] and receipt['url'].startswith('https://') and stamp(receipt['started_at'])<=stamp(receipt['received_at'])<=now,'REFERENCE_OFFICIAL_SOURCE_RECEIPT')
  text=raw.decode('utf-8');quote=fact['quote'];require(isinstance(quote,str) and quote and quote in text and fact['issuer_name'] in text,'REFERENCE_OFFICIAL_QUOTE_IDENTITY')
  if event['kind']=='dividends':
   require(fact['kind']=='ORDINARY_CASH_DIVIDEND' and fact['currency']=='USD' and fact['unit_change'] is False,'REFERENCE_CASH_CLASSIFICATION')
   for field,phrase in [('record_date','record_quote'),('payment_date','payment_quote')]:
    d=date.fromisoformat(fact[field]);label=d.strftime('%B')+' '+str(d.day)+', '+str(d.year);require(fact[phrase] in text and label in fact[phrase],'REFERENCE_CASH_DATE_QUOTE')
   require(fact['event_session']<=fact['record_date']<=fact['payment_date'] and 'record' in fact['record_quote'].lower(),'REFERENCE_CASH_DATE_ORDER')
   match=re.search(r'cash dividend of \$([0-9]+(?:\.[0-9]+)?) per share',quote,re.I);require(match is not None and F(match.group(1))==F(fact['nominal_amount']),'REFERENCE_CASH_QUOTE_AMOUNT')
  elif event['kind']=='splits':
   require(fact['kind']=='INTEGER_SPLIT' and fact['timing']=='BEFORE_OPEN','REFERENCE_SPLIT_CLASSIFICATION')
   ratio=F(fact['ratio']);payload=event['payload'];require(ratio>0 and ratio.denominator==1 and F(payload['numerator'])/F(payload['denominator'])==ratio,'REFERENCE_SPLIT_RATIO')
   effective=fact['effective_quote'];require(effective in text,'REFERENCE_SPLIT_EFFECTIVE_QUOTE')
   timing=re.search(r'effective (?:at|before) (?:the )?(?:market open|opening of trading) on ([A-Z][a-z]+ [0-9]{1,2}, [0-9]{4})',effective,re.I);require(timing is not None and datetime.strptime(timing.group(1),'%B %d, %Y').date().isoformat()==fact['event_session'],'REFERENCE_SPLIT_EFFECTIVE_TIME')
   require(re.search(r'\b'+str(ratio.numerator)+r'[- ]for[- ]1\s+(?:forward\s+)?stock split\b',quote,re.I) is not None and fact['old_cusip'] in text and fact['new_cusip'] in text,'REFERENCE_SPLIT_QUOTE_IDENTITY')
  else:raise ValueError('REFERENCE_UNSUPPORTED_ACTION')
  used.add(observed_hash);return fact
 rows={};events=[];names={};identity_pins={};received_by_day={}
 for segment in config['segments']:
  identity=segment['identity'];lookup=PinnedStrategyIdentity(root,identity['path'],identity['sha256'])(segment['ticker']);require(lookup['security_id']==segment['security_id'],'REFERENCE_IDENTITY_SID')
  for name,h in lookup['source_hashes'].items():read(dict(path=name,sha256=h));identity_pins[name]=h
  raw=read(segment['raw']);receipt=json.loads(read(segment['receipt']));begin,end,received=map(stamp,(receipt['requested_from'],receipt['requested_through'],receipt['received_at']))
  require(receipt['http_status']==200 and receipt['body_truncated'] is False and receipt['transport_error'] is None and receipt['raw_sha256']==sha256(raw).hexdigest() and receipt['stored_bytes']==len(raw),'REFERENCE_DAILY_RECEIPT')
  require(receipt['security_id']==segment['security_id'] and receipt['ticker']==segment['ticker'] and receipt['interval']=='1d' and receipt['events_requested']==['dividends','splits'] and receipt['url']==daily_url(segment['ticker'],begin,end) and receipt['request_period1']==int(begin.timestamp()) and receipt['request_period2']==int(end.timestamp())+1,'REFERENCE_REQUEST_IDENTITY')
  require(segment['start_session'] in dates and segment['end_session'] in dates and segment['start_session']<=segment['end_session'] and begin<=stamp(clocks[segment['start_session']]['open']) and stamp(clocks[segment['end_session']]['close'])<=end<=received<=now,'REFERENCE_REQUEST_RANGE')
  chart=json.loads(raw)['chart'];require(chart.get('error') is None and len(chart['result'])==1,'REFERENCE_CHART_SCHEMA');series=chart['result'][0];meta=series['meta']
  require(meta['symbol']==segment['ticker'] and meta['currency']=='USD' and meta['instrumentType']=='EQUITY' and meta['exchangeName']==segment['exchange'],'REFERENCE_CHART_IDENTITY')
  names[segment['ticker']]=[meta[k] for k in ('longName','shortName') if isinstance(meta.get(k),str) and len(meta[k])>=2];require(names[segment['ticker']],'REFERENCE_ISSUER_NAMES_REQUIRED')
  action=series.get('events',{});require(type(action) is dict and set(action)<={'dividends','splits','capitalGains'} and all(type(v) is dict for v in action.values()),'REFERENCE_EVENT_SCHEMA')
  # All returned events are checked, including events outside selected bars;
  # later splits can change historical quote units and cannot be ignored.
  segment_facts=[]
  for kind,values in action.items():
   for key,payload in values.items():
    event={'kind':kind,'key':key,'payload':payload};fact=fact_for(event,segment['security_id']);segment_facts.append(fact)
    event_day=datetime.fromtimestamp(payload['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();require(event_day==fact['event_session'],'REFERENCE_ACTION_DATE')
    if kind=='splits':events.append(fact)
  require(segment['price_basis']=='ARCHIVED_SAME_UNIT_RAW_CLOSE','WAIT_NOMINAL_UNIT_CONTINUITY')
  # A split-bearing source cannot certify both sides of its changed unit.
  # Each segment must consist entirely of the declared pre/post unit, and a
  # separately approved split joins them. No reverse-adjustment guessing.
  for fact in segment_facts:
   if fact['kind']=='INTEGER_SPLIT':require(not(segment['start_session']<fact['event_session']<=segment['end_session']),'WAIT_SPLIT_SEGMENT_UNIT_PROOF')
  times=series['timestamp'];quotes=series['indicators']['quote'][0]['close'];adj=series['indicators']['adjclose'][0]['adjclose'];require(len(times)==len(quotes)==len(adj),'REFERENCE_BAR_LENGTH')
  expected=[d for d in window if segment['start_session']<=d<=segment['end_session']];found={}
  for t,value,adjusted in zip(times,quotes,adj):
   require(type(t) is int and datetime.fromtimestamp(t,timezone.utc)<=received,'REFERENCE_FUTURE_BAR')
   day=datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
   if day not in expected:continue
   require(day not in found and type(value) in (int,float) and F(str(value))>0,'REFERENCE_PRICE_INVALID')
   # Ordinary cash classification is not permission to guess adjusted price
   # units. Differing adjustedClose still needs a separate nominal proof.
   require(adjusted is not None and F(str(value))==F(str(adjusted)),'WAIT_NOMINAL_UNIT_CONTINUITY')
   require(stamp(clocks[day]['close'])<=received<=now,'REFERENCE_CLOSE_NOT_COMPLETED')
   found[day]=dict(session_date=day,completed=True,completed_at=clocks[day]['close'],security_id=segment['security_id'],unit_id=segment['unit_id'],close=str(value))
  require(set(found)==set(expected),'REFERENCE_MISSING_TRADING_SESSION')
  for day,row in found.items():require(day not in rows or rows[day]==row,'REFERENCE_SEGMENT_CONFLICT');rows[day]=row;received_by_day[day]=received
 require(set(rows)==set(window),'REFERENCE_FULL_INTERVAL_REQUIRED');anchor=rows[window[0]]
 require(anchor['security_id']==lock['security_id'] and anchor['unit_id']==lock['unit_id'] and F(anchor['close'])==F(lock['reference_price']),'WAIT_EXIT_ANCHOR_UNIT_CONTINUITY')
 current_sid=lock['security_id'];current_unit=lock['unit_id'];converted=[]
 for day in window[1:]:
  row=rows[day]
  if row['security_id']!=current_sid or row['unit_id']!=current_unit:
   matches=[f for f in events if f['event_session']==day and f['security_id']==current_sid and f['new_security_id']==row['security_id'] and f['old_unit_id']==current_unit and f['new_unit_id']==row['unit_id']]
   require(len(matches)==1,'WAIT_UNIT_TRANSITION_PROOF');f=matches[0];previous_day=window[window.index(day)-1];require(received_by_day[previous_day]<stamp(clocks[day]['open']),'WAIT_ARCHIVED_PRE_SPLIT_UNIT_SOURCE');row['conversion']=dict(kind='REVIEWED_INTEGER_SPLIT',timing='BEFORE_OPEN',old_security_id=current_sid,new_security_id=row['security_id'],old_unit_id=current_unit,new_unit_id=row['unit_id'],ratio=f['ratio'],evidence_sha256=sha256(canonical(f)).hexdigest());converted.append(f);current_sid=row['security_id'];current_unit=row['unit_id']
 require(len(events)==len(converted),'WAIT_SPLIT_EVENT_UNIT_CONTINUITY')
 rss=read(config['official_rss']['raw']);rr=json.loads(read(config['official_rss']['receipt']));require(rr['url']==URL and rr['http_status']==200 and rr['body_truncated'] is False and rr['transport_error'] is None and rr['raw_sha256']==sha256(rss).hexdigest() and rr['stored_bytes']==len(rss) and stamp(rr['started_at'])<=stamp(rr['received_at'])<=now and (now-stamp(rr['received_at'])).total_seconds()<=120,'REFERENCE_NOTICE_RECEIPT')
 scope_bytes=read(config['notice_scope_reviewer']);require(scope_bytes==Path(notice_scope.__file__).read_bytes(),'REFERENCE_NOTICE_SCOPE_CODE_CHANGED')
 feed=parse_official_feed(rss,observed_at=stamp(rr['received_at']));notice_reviews=[]
 for ticker,issuer_names in names.items():notice_reviews.append(notice_scope.review_future_notice_scope(rss,feed=feed,ticker=ticker,issuer_names=issuer_names))
 evidence=dict(status='AUTHENTICATED_COMPLETE_REFERENCE_INTERVAL',origin_security_id=lock['security_id'],origin_unit_id=lock['unit_id'],exit_session=lock['exit_session'],expected_sessions=window[1:],completed_through=decision_session,as_of=now.isoformat(),rows=[rows[d] for d in window[1:]],coverage_complete=False,coverage='CONDITIONAL_PROVIDER_AND_CURRENT_OFFICIAL_NOTICE_SCOPE',notice_scope_reviews=notice_reviews,source_hashes=pins)
 evidence['evidence_sha256']=sha256(canonical(evidence)).hexdigest()
 return dict(status='REFERENCE_SOURCE_REVIEWED_CONDITIONAL',evidence=evidence,identity_evidence_sha256=sha256(canonical(dict(configuration_sha256=configuration_reference['sha256'],lock=lock,decision_session=decision_session,complete_evidence_sha256=evidence['evidence_sha256'],identity_source_hashes=identity_pins))).hexdigest(),current_security_id=current_sid,coverage_complete=False,orders_created=False,limitations=['No immutable historical publication claim','Public provider and present official feed are not exhaustive historical action coverage','Split requires separately sourced same-unit segments; no guessed reverse adjustment'])
