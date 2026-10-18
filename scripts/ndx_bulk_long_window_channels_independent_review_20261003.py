"""Independent exact raw reconstruction oracle for the new77 long window only."""
from datetime import datetime
from decimal import Decimal,Context,localcontext
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/bulk_long_window_channels_20261003_v1'
SHA='0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'
PUB='b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'
NY=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
CONTRACT=dict(cutoff='2026-09-21',fit_return_count=126,evaluation_return_count=126,receipt_exclusion_date='2026-09-23')
INNER=('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','promotion_allowed','execution_authorized','fit_performed','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified')
OUTER=('http_performed','fit_performed','account_simulation_performed','old_127_producer_called','old_127_audit_repeated','old_outputs_spliced','identity_interval_extended','historical_identity_verified','historical_risk_verified','complete_corporate_actions_verified','volume_unit_certified','provider_binding_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','future_oos_evaluation_performed','formal_benchmark_evaluation_performed','full_transitive_source_closure_reverified')
def check(v,m):
 if not v:raise ValueError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(path,h):
 b=Path(path).read_bytes();check(sha(b)==h,'SHA '+str(path));return b
def unique(pairs):
 d={}
 for k,v in pairs:check(k not in d,'Duplicate raw key');d[k]=v
 return d
def bad(v):raise ValueError('Nonfinite raw '+v)
def saved(v):
 if type(v) is Decimal:return str(v)
 if type(v) is dict:return {k:saved(x) for k,x in v.items()}
 if type(v) is list:return [saved(x) for x in v]
 return v
def rational_tree(v):
 if type(v) in (int,float,Decimal):return str(Fraction(str(v)))
 if type(v) is dict:return {k:rational_tree(x) for k,x in v.items()}
 if type(v) is list:return [rational_tree(x) for x in v]
 return v
def fraction(v):
 check(type(v) in (int,Decimal),'Nonboolean raw number');return Fraction(v)
def display(v):
 with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def verify():
 d=json.loads(read(BASE/'channels.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes())
 check({p.name for p in BASE.iterdir()}=={'started.json','channels.json','publication.json'},'Successful namespace')
 refs=d['input_references'];check(len(refs)==8,'Eight parents');sources={};parents={}
 for role,r in refs.items():
  b=read(r['path'],r['sha256']);sources[r['path']]=r['sha256']
  if role not in ('history_audit_report','history_audit_reader'):parents[role]=json.loads(b)
 for relative,h in [('backtest/ndx_bulk_long_window_channels_research.py','419c8c36b8720609211910347f4c088a9a1a6e3bd874cd3a72f62d8a9fecbd40'),('scripts/ndx_bulk_long_window_channels_20261003.py','5528d96b16d9c8daf3f57d252b7993e0f6fa93b922bf80441fbb9e54b4131b34')]:read(ROOT/relative,h);sources[str(ROOT/relative)]=h
 tz=read(NY,NY_SHA);sources[str(NY)]=NY_SHA;zone=ZoneInfo.from_file(BytesIO(tz),key='America/New_York')
 history=parents['history'];hr=history['requirements'];panel=parents['panel'];bridge=parents['bridge'];audit=parents['history_audit']
 exact(parents['history_publication']['requirements_reference'],refs['history'],'History receipt');check(audit['status']=='PASS' and audit['requirements_sha256']==refs['history']['sha256'],'History audit reference only')
 calendar=hr['scenarios'][0]['required_reference_price_dates'];check(len(calendar)==253 and calendar==sorted(set(calendar)),'253 reference dates')
 exact(panel['panel']['returns']['index'],[day+'T00:00:00' for day in calendar[127:]],'Previously fitted126 exact overlap')
 universe=[dict(zip(panel['panel']['universe']['columns'],row)) for row in panel['panel']['universe']['data']];exact(hr['universe'],universe,'Full77 universe')
 check(len(universe)==77 and len({x['issuer_id'] for x in universe})==76,'77/76')
 check(parents['prior_fit_batch']['status']=='BUDGETED_QUEUE_FINISHED' and parents['prior_fit_batch']['new_readback_count']==1630 and len(parents['prior_fit_batch']['initial_completed_rows'])==2,'Prior fitting context')
 brby={r['ticker']:(i,r) for i,r in enumerate(bridge['rows'])};check(len(brby)==101,'101 bridge')
 expectedrows=[];summaries=[];split_count=dividend_count=price_count=return_count=0
 for coord in universe:
  ticker=coord['ticker'];item=hr['ticker_observations_preserved'][ticker];bi,br=brby[ticker];exact(item['complete_bridge_row'],br,'Full bridge row');rawref=br['new_raw_reference'];receiptr=br['new_receipt_reference']
  raw=read(rawref['path'],rawref['sha256']);receipt=json.loads(read(receiptr['path'],receiptr['sha256']))
  for r in (rawref,receiptr):check(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source conflict');sources[r['path']]=r['sha256']
  check(receipt['ticker']==ticker and receipt['raw_path']==rawref['path'] and receipt['raw_sha256']==rawref['sha256'] and type(receipt['raw_bytes']) is int and receipt['raw_bytes']==len(raw),'Receipt binding')
  check(type(receipt['http_status']) is int and receipt['http_status']==200 and receipt['point_in_time_verified'] is False and receipt['promotion_allowed'] is False,'Receipt status')
  clock=datetime.fromisoformat(receipt['received_at_utc']);check(clock.tzinfo is not None and clock.utcoffset().total_seconds()==0 and clock.astimezone(zone).date().isoformat()=='2026-09-23','Receipt cutoff clock')
  decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;check(sha(decoded)==br['new_decoded_sha256'],'Decoded bytes')
  body=json.loads(decoded,parse_float=Decimal,object_pairs_hook=unique,parse_constant=bad);check(body['chart']['error'] is None and len(body['chart']['result'])==1,'Single raw channel');c=body['chart']['result'][0]
  for k,v in dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():check(c['meta'][k]==v,'Raw metadata '+k)
  timestamps=c['timestamp'];check(all(type(x) is int for x in timestamps) and timestamps==sorted(set(timestamps)),'Raw times');days=[datetime.fromtimestamp(x,zone).date().isoformat() for x in timestamps];check(days==sorted(set(days)),'NY dates')
  check([day for day in days if calendar[0]<=day<=calendar[-1]]==calendar,'Required fullcalendar without compression')
  pos={day:i for i,day in enumerate(days)};check(len(c['indicators']['quote'])==1,'One quote series');q=c['indicators']['quote'][0]
  check(all(len(q[k])==len(days) for k in ('open','high','low','close','volume')),'Quote dimensions')
  events=c.get('events',{});check(set(events)<= {'splits','dividends'},'Unreviewed event type');splits=events.get('splits',{});dividends=events.get('dividends',{});split_count+=len(splits);dividend_count+=len(dividends)
  exact(rational_tree(splits),rational_tree(br['new_returned_splits']),'All raw split values')
  mapping=br['event_policy_bridge'];policies=[];check(len(mapping['events'])==len(splits) and {x['provider_event_key'] for x in mapping['events']}==set(splits),'Full policy coverage')
  for m in mapping['events']:
   event=splits[m['provider_event_key']];stamp=event['date'];check(type(stamp) is int and str(stamp)==m['provider_event_key'],'Split key')
   day=datetime.fromtimestamp(stamp,zone).date().isoformat();ratio=fraction(event['numerator'])/fraction(event['denominator']);a,b=event['splitRatio'].split(':');check(Fraction(a)>0 and Fraction(b)>0 and Fraction(a)/Fraction(b)==ratio,'Raw ratio')
   p=m['policy'];check(m['status']=='SPECIFIC_POLICY_MATCH' and day==m['session']==p['session'] and type(p['numerator']) is int and type(p['denominator']) is int and Fraction(p['numerator'],p['denominator'])==ratio,'Specific policy match')
   check(p['kind'] in ('ORDINARY_SPLIT','BEFORE_PARTITION_UNMODELLED'),'Policy kind')
   if p['kind']=='ORDINARY_SPLIT':check(m['specific_event_reference'] is not None,'Event reference')
   else:check(mapping['regular_floor'] is not None and day<=mapping['regular_floor'],'Before-floor event')
   policies.append(dict(session=day,kind=p['kind'],numerator=ratio.numerator,denominator=ratio.denominator))
  policies.sort(key=lambda x:x['session']);check(len({p['session'] for p in policies})==len(policies),'Unique split dates')
  floor=mapping['regular_floor'];check(floor is None or floor<=calendar[0],'No required prepartition prices')
  quote=[];returns=[];previous=None;factors=[]
  for day in calendar:
   i=pos[day];v={k:fraction(q[k][i]) for k in ('open','high','low','close')};check(all(x>0 for x in v.values()) and v['low']<=min(v['open'],v['close'])<=max(v['open'],v['close'])<=v['high'],'OHLC sanity')
   factor=Fraction(1)
   for p in policies:
    if p['kind']=='ORDINARY_SPLIT' and p['session']>day:factor*=Fraction(p['numerator'],p['denominator'])
   factors.append(str(factor));nominal={k:v[k]*factor for k in ('open','close')}
   if q['volume'][i] is not None:check(fraction(q['volume'][i])>=0,'Volume sign')
   row=dict(session=day,raw_row_index=i,provider_timestamp=timestamps[i],split_factor_exact=str(factor),raw_volume=saved(q['volume'][i]))
   for k in ('open','close'):row.update({f'raw_{k}':saved(q[k][i]),f'nominal_{k}_exact':str(nominal[k]),f'nominal_{k}':display(nominal[k])})
   quote.append(row)
   if previous:
    # Reconstruct split-only gross from nominal marks and share-count conversion.
    gross=nominal['close']*previous['factor']/(previous['nominal_close']*factor);r=gross-1
    check(gross==v['close']/previous['raw_close'],'Split-only equivalent formulations');fv=float(r);check(math.isfinite(fv) and fv>-1,'Float boundary')
    returns.append(dict(previous_session=previous['day'],session=day,split_only_return_exact=str(r),split_only_return_float=fv,dividends_included=False))
   previous=dict(day=day,factor=factor,nominal_close=nominal['close'],raw_close=v['close'])
  price_count+=len(quote);return_count+=len(returns)
  channel=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1',ticker=ticker,status='CONDITIONAL_NUMERIC_RESULT',reasons=[],calendar=calendar,missing_price_dates=[],missing_price_fields=[],regular_floor=floor,raw_reference=rawref,receipt_reference=receiptr,receipt_preserved=receipt,decoded_sha256=sha(decoded),tzif_sha256=NY_SHA,provider_metadata=saved(c['meta']),returned_events=saved(events),returned_event_encoding='ALL_KEYS_PRESERVED_NONINTEGER_JSON_NUMBERS_AS_DECIMAL_STRINGS',bridge_row_preserved=br,event_policies=policies,provider_price_unit_assumption='SAVED_CHANNEL_SPLIT_ADJUSTED_PRICES_CONDITIONALLY_REVERSED_BY_ALL_LATER_ORDINARY_EVENTS_NOT_CERTIFIED',arithmetic='EXACT_FRACTION_FROM_RAW_DECIMAL;DISPLAY_DECIMAL_CONTEXT80;FLOAT_RETURNS_EXPLICIT_FITTER_BOUNDARY',conditional_reconstruction_performed=True,historical_retrospective_only=True,window_contract=CONTRACT,quote_rows=quote,return_rows=returns,training_returns=returns[:126],evaluation_returns=returns[126:],training_freeze_close_date=calendar[126],evaluation_initial_close_date=calendar[126],quote_rows_sha256=sha(enc(quote)),training_returns_sha256=sha(enc(returns[:126])),evaluation_returns_sha256=sha(enc(returns[126:])),**dict.fromkeys(INNER,False))
  expectedrows.append(dict(coordinate=coord,history_observation_reference=dict(refs['history'],json_pointer='/requirements/ticker_observations_preserved/'+ticker),original_identity_assumed_window=item['identity_assumed_window'],channel=channel))
  summaries.append(dict(ticker=ticker,raw_reference=rawref,receipt_reference=receiptr,raw_rows=len(days),required_rows=len(quote),split_count=len(splits),dividend_count=len(dividends),distinct_factors=sorted(set(factors)),quote_rows_sha256=channel['quote_rows_sha256'],training_returns_sha256=channel['training_returns_sha256'],evaluation_returns_sha256=channel['evaluation_returns_sha256']))
  print('verified '+ticker,flush=True)
 expected=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=expectedrows,input_references=refs,window_contract=CONTRACT,calendar253=calendar,training_return_count=126,evaluation_return_count=126,training_freeze_close_date=calendar[126],evaluation_first_return_date=calendar[127],security_count=77,issuer_count=76,observed_security_count=101,new_raw_channel_reconstruction_count=77,conditional_numeric_channel_count=77,blocked_price_channel_count=0,original_provenance_and_missing=panel['panel']['observed_provenance_and_missing'],preserved_evidence_sidecars={k:panel[k] for k in SIDECARS},preserved_sidecar_references={k:dict(refs['panel'],json_pointer='/'+k) for k in SIDECARS},history_requirement_reference=refs['history'],original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'),evaluation_interval_previously_used_for_fitting=True,future_independent_oos=False,untouched_holdout=False,evaluation_prior_fit_overlap_evidence=dict(panel_returns_reference=dict(refs['panel'],json_pointer='/panel/returns/index'),saved_batch_reference=refs['prior_fit_batch'],evaluation_dates=calendar[127:],evaluation_dates_sha256=sha(enc(calendar[127:])),exact_same_126_dates=True,prior_fit_task_count=1632,meaning='HISTORICAL_DIAGNOSTIC_NOT_UNTOUCHED_HOLDOUT'),new_independent_long_arithmetic_readback_completed=False,source_hashes=sources,**dict.fromkeys(OUTER,False))
 check(len(sources)==165,'165 direct sources');exact(d,expected,'Complete independent new253 arithmetic and envelope')
 exact(pub,dict(schema='BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK',channels_reference=dict(path=str(BASE/'channels.json'),sha256=SHA),source_hashes=sources,**dict.fromkeys(OUTER,False)),'Publication')
 exact(started,dict(source_hashes=sources,planned_raw_channel_count=77,retry_allowed=False,**dict.fromkeys(OUTER,False)),'Started')
 return dict(schema='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=len(sources),security_count=77,issuer_count=76,price_date_rows=price_count,nominal_open_close_values=price_count*2,split_factor_checks=price_count,return_rows=return_count,training_return_rows=77*126,evaluation_return_rows=77*126,returned_split_count=split_count,returned_dividend_count=dividend_count,per_channel=summaries,original_provenance_count=101,preserved_sidecar_count=7,evaluation_interval_previously_used_for_fitting=True,untouched_holdout=False,future_independent_oos=False,old_127_producer_called=False,old_127_audit_repeated=False,fit_performed=False,account_simulation_performed=False,point_in_time_verified=False,legal_training_input_admitted=False)
if __name__=='__main__':
 r=verify();out=ROOT/'DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in r.items() if k!='per_channel'},indent=2))
