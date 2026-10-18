"""New TSM raw oracle; seven other channels are checked only by saved references."""
from datetime import datetime
from decimal import Decimal, Context, localcontext
from fractions import Fraction
from pathlib import Path
from io import BytesIO
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/original_eight_long_window_channels_20261003_v1'
SHA='67d433ae92acb0755a1ffdabf090e6c20706b4d1ba893637673e96a047acc372'
PUB='836622bff616370375539490c441fbb5b988d5dab8b661b202991288bcbf05e1'
NY=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
FLAGS=('http_performed','fit_performed','account_simulation_performed','old_producer_called','old_audit_repeated','seven_reused_channels_recomputed','weights_normalized','weights_reoptimized','holdings_or_quotes_converted','identity_interval_extended','historical_identity_verified','historical_risk_verified','complete_corporate_actions_verified','provider_binding_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','formal_benchmark_evaluation_performed','full_transitive_source_closure_reverified','benchmark_qualified','fx_equivalence_verified','nav_publication_verified','future_independent_oos','untouched_holdout')
def check(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(p,h):
 b=Path(p).read_bytes();check(sha(b)==h,'SHA '+str(p));return b
def scalar(v):return str(v) if type(v) is Decimal else v
def tree(v):
 if isinstance(v,dict):return {k:tree(x) for k,x in v.items()}
 if isinstance(v,list):return [tree(x) for x in v]
 return scalar(v)
def rat(v):
 check(type(v) in (Decimal,int),'Raw finite nonboolean number');return Fraction(v)
def event_values(v):
 if isinstance(v,dict):return {k:event_values(x) for k,x in v.items()}
 if isinstance(v,list):return [event_values(x) for x in v]
 if type(v) in (str,int,float,Decimal):
  try:return str(Fraction(str(v)))
  except ValueError:pass
 return v
def display(v):
 with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def pairs(items):
 d={}
 for k,v in items:check(k not in d,'Duplicate raw key');d[k]=v
 return d
def fail(v):raise ValueError('Nonfinite '+v)

def verify():
 d=json.loads(read(BASE/'channels.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes())
 check({p.name for p in BASE.iterdir()}=={'channels.json','publication.json','started.json'},'Successful namespace')
 refs=d['input_references'];docs={};sources={}
 for role,r in refs.items():
  b=read(r['path'],r['sha256']);sources[r['path']]=r['sha256']
  if not role.endswith(('_reader','_report')):docs[role]=json.loads(b)
 check(len(refs)==10,'10 source parents')
 for relative,h in [('scripts/ndx_original_eight_long_window_channels_20261003.py','7ab83faa0d25839b5c061e1347a749ced24501723e9eed3e6079095cfab448ed'),('backtest/ndx_bulk_long_window_channels_research.py','419c8c36b8720609211910347f4c088a9a1a6e3bd874cd3a72f62d8a9fecbd40')]:
  read(ROOT/relative,h);sources[str(ROOT/relative)]=h
 tz=read(NY,NY_SHA);sources[str(NY)]=NY_SHA;zone=ZoneInfo.from_file(BytesIO(tz),key='America/New_York')
 parent=docs['channels'];req=docs['requirements']['requirements'];audit=docs['channels_audit'];calendar=req['reference_calendar']['dates']
 check(len(calendar)==253 and calendar[126]=='2026-03-20' and calendar[127]=='2026-03-23','126/126 shared predecessor')
 exact(d['calendar253'],calendar,'Full calendar');exact(calendar,parent['calendar253'],'Same candidate calendar')
 for role in ('channels','requirements'):
  p=docs[role+'_publication'];exact(p[role+'_reference'],refs[role],'Parent publication reference');exact(p['source_hashes'],docs[role]['source_hashes'],'Parent source map')
 check(audit['status']=='PASS' and audit['channels_sha256']==refs['channels']['sha256'] and audit['reader_sha256']==refs['channels_audit_reader']['sha256'],'Prior independent reference only')
 exact(d['complete_benchmark_requirements_preserved'],req,'Complete benchmark requirements')
 exact(d['original_control_preserved'],req['original_control_preserved'],'Original8 definition')
 securities=req['original_control_preserved']['securities'];order=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
 exact([s['ticker'] for s in securities],order,'Original order');exact(d['original_control_order'],order,'Output order')
 exact(d['original_target_weight_sum_exact'],req['original_target_weight_sum_exact'],'Unnormalized original weights')
 exact(d['original_candidate_provenance'],parent['original_provenance_and_missing'],'101 provenance');check(len(d['original_candidate_provenance'])==101,'101 count')
 exact(d['preserved_candidate_evidence_sidecars'],parent['preserved_evidence_sidecars'],'Seven sidecars');check(len(d['preserved_candidate_evidence_sidecars'])==7,'7 count')
 exact(d['evaluation_prior_fit_overlap_evidence'],parent['evaluation_prior_fit_overlap_evidence'],'Already consumed dates')
 check(d['evaluation_interval_previously_used_for_fitting'] is True and d['tsm_same_evaluation_calendar_not_claimed_prior_candidate_fit'] is True,'Not untouched evaluation')
 by={r['coordinate']['ticker']:(i,r) for i,r in enumerate(parent['rows'])};ab={r['ticker']:(i,r) for i,r in enumerate(audit['per_channel'])}
 reused=[]
 for i,row in enumerate(d['rows']):
  security=securities[i];ticker=security['ticker'];meta=req['stock_metadata_preserved'][ticker]
  exact(row['original_control_security'],security,'Original security');exact(row['original_control_security_reference'],dict(refs['requirements'],json_pointer=f'/requirements/original_control_preserved/securities/{i}'),'Security pointer')
  exact(row['complete_benchmark_metadata'],meta,'Full original metadata');exact(row['benchmark_metadata_reference'],dict(refs['requirements'],json_pointer='/requirements/stock_metadata_preserved/'+ticker),'Metadata pointer')
  if ticker=='TSM':continue
  j,old=by[ticker];ai,proof=ab[ticker]
  exact(row['complete_parent_row'],old,'Whole saved parent row');exact(row['channel'],old['channel'],'Whole saved channel exact')
  exact(row['channel_reference'],dict(refs['channels'],json_pointer=f'/rows/{j}/channel'),'Channel pointer');exact(row['independent_readback_reference'],dict(refs['channels_audit'],json_pointer=f'/per_channel/{ai}'),'Readback pointer')
  check(row['mode']=='EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC','Reuse mode')
  for field in ('quote_rows','training_returns','evaluation_returns'):check(sha(enc(row['channel'][field]))==proof[field+'_sha256'],'Saved payload digest')
  reused.append(ticker)
 row=d['rows'][4];meta=row['complete_benchmark_metadata'];ch=row['channel'];bridge=row['conditional_event_policy_bridge'];old=docs['old_tsm_basis']
 check(row['mode']=='ONE_NEW_TSM_RAW_RECONSTRUCTION' and all(row[k] is None for k in ('channel_reference','complete_parent_row','independent_readback_reference')),'New TSM separate')
 check(securities[4]['security_id']=='security:incumbent_overlay:TSM' and securities[4]['issuer_id']=='issuer:0001046179','Overlay unchanged')
 identity=meta['complete_identity_sidecar'];check(identity['cusip']=='874039100' and identity['security_class']=='American Depositary Shares' and type(identity['ordinary_shares_per_ads']) is int and identity['ordinary_shares_per_ads']==5,'ADS fact not conversion')
 check(old['reconstruction']['quote_field_basis']=='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS' and old['reconstruction']['basis_was_supplied_not_authenticated'] is True and old['reconstruction']['provider_split_events']==[],'Old conditional basis')
 check(old['all_returned_raw_events'].get('splits',{})=={} and meta['returned_events'].get('splits',{})=={},'Empty returned events not full actions')
 expectedbridge=dict(ticker='TSM',new_raw_reference=meta['raw_reference'],new_receipt_reference=meta['receipt_reference'],new_decoded_sha256=meta['decoded_sha256'],new_returned_splits={},event_policy_bridge=dict(events=[],regular_floor=None),basis_assumption='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS',old_basis_reference=dict(refs['old_tsm_basis'],json_pointer='/reconstruction/quote_field_basis'),old_returned_events_reference=dict(refs['old_tsm_basis'],json_pointer='/all_returned_raw_events'),new_returned_events_reference=dict(refs['requirements'],json_pointer='/requirements/stock_metadata_preserved/TSM/returned_events'),empty_returned_splits_is_not_action_completeness=True,complete_corporate_actions_verified=False,provider_price_unit_verified=False)
 exact(bridge,expectedbridge,'TSM conditional policy independently reconstructed');exact(ch['bridge_row_preserved'],expectedbridge,'Consumed policy')
 rawref=meta['raw_reference'];rr=meta['receipt_reference'];raw=read(rawref['path'],rawref['sha256']);receipt=json.loads(read(rr['path'],rr['sha256']))
 for r in (rawref,rr):sources[r['path']]=r['sha256']
 exact(receipt,meta['original_receipt'],'Saved receipt');exact(ch['receipt_preserved'],receipt,'Consumed receipt')
 check(receipt['raw_path']==rawref['path'] and receipt['raw_sha256']==rawref['sha256'] and receipt['raw_bytes']==len(raw) and receipt['http_status']==200 and receipt['ticker']=='TSM','Transport binding')
 clock=datetime.fromisoformat(receipt['received_at_utc']);check(clock.tzinfo is not None and clock.astimezone(zone).date().isoformat()=='2026-09-23','Receipt exclusion date')
 decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;check(sha(decoded)==meta['decoded_sha256']==ch['decoded_sha256'],'Decoded bytes')
 body=json.loads(decoded,parse_float=Decimal,object_pairs_hook=pairs,parse_constant=fail);check(body['chart']['error'] is None and len(body['chart']['result'])==1,'Single chart');c=body['chart']['result'][0]
 for key,value in dict(symbol='TSM',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d').items():check(c['meta'][key]==value,'Metadata '+key)
 exact(ch['provider_metadata'],tree(c['meta']),'All metadata');events=c.get('events',{});check(set(events)<= {'splits','dividends'} and events.get('splits',{})=={},'No returned splits');exact(ch['returned_events'],tree(events),'All events including dividends')
 exact(event_values(meta['returned_events']),event_values(events),'Metadata event values (saved float versus Decimal literal)');check(ch['event_policies']==[] and ch['regular_floor'] is None,'Conditional factor1 policy')
 timestamps=c['timestamp'];check(all(type(x) is int for x in timestamps) and timestamps==sorted(set(timestamps)),'Timestamps');days=[datetime.fromtimestamp(x,zone).date().isoformat() for x in timestamps];check(days==sorted(set(days)),'NY dates')
 exact([day for day in days if calendar[0]<=day<=calendar[-1]],calendar,'Uncompressed required days');pos={day:i for i,day in enumerate(days)};q=c['indicators']['quote'][0]
 check(len(c['indicators']['quote'])==1 and all(len(q[k])==len(days) for k in ('open','close','high','low','volume')),'Raw shape')
 quotes=[];returns=[];prev=None
 for day in calendar:
  i=pos[day];v={k:rat(q[k][i]) for k in ('open','close','high','low')};check(all(x>0 for x in v.values()) and v['low']<=min(v['open'],v['close'])<=max(v['open'],v['close'])<=v['high'],'OHLC')
  a=dict(session=day,raw_row_index=i,provider_timestamp=timestamps[i],split_factor_exact='1',raw_volume=scalar(q['volume'][i]))
  for k in ('open','close'):a.update({f'raw_{k}':scalar(q[k][i]),f'nominal_{k}_exact':str(v[k]),f'nominal_{k}':display(v[k])})
  quotes.append(a)
  if prev is not None:
   r=v['close']/prev[1]-1;returns.append(dict(previous_session=prev[0],session=day,split_only_return_exact=str(r),split_only_return_float=float(r),dividends_included=False))
  prev=(day,v['close'])
 for field,expected in [('quote_rows',quotes),('return_rows',returns),('training_returns',returns[:126]),('evaluation_returns',returns[126:])]:
  exact(ch[field],expected,'Independent TSM '+field)
  if field!='return_rows':check(ch[field+'_sha256']==sha(enc(expected)),'Independent payload digest')
 check(ch['status']=='CONDITIONAL_NUMERIC_RESULT' and ch['reasons']==[] and ch['missing_price_dates']==[] and ch['missing_price_fields']==[] and ch['tzif_sha256']==NY_SHA,'TSM complete conditional only')
 exact(ch['calendar'],calendar,'TSM calendar');check(ch['training_freeze_close_date']==calendar[126]==ch['evaluation_initial_close_date'],'TSM partition')
 for k in ('point_in_time_verified','provider_price_unit_verified','complete_corporate_actions_verified','dividend_cash_flows_included','identity_interval_verified','liquidity_qualified','benchmark_qualified','fit_performed'):check(ch[k] is False,'TSM authority '+k)
 for k in FLAGS:check(d[k] is False and pub[k] is False and started[k] is False,'Authority '+k)
 for k,v in dict(security_count=8,issuer_count=8,new_raw_channel_reconstruction_count=1,sealed_channel_reuse_count=7,conditional_numeric_channel_count=8,blocked_price_channel_count=0).items():check(type(d[k]) is int and d[k]==v,'Exact count '+k)
 exact(d['source_hashes'],sources,'Complete source map');check(len(sources)==15,'15 sources')
 exact(pub['source_hashes'],sources,'Publication sources');exact(started['source_hashes'],sources,'Started sources');exact(started['input_references'],refs,'Started refs')
 exact(pub['channels_reference'],dict(path=str(BASE/'channels.json'),sha256=SHA),'Publication payload');check(pub['status']=='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK','Publication status')
 for p,h in sources.items():read(p,h)
 return dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=15,reused_tickers=reused,reused_channels_recomputed=False,new_raw_ticker='TSM',raw_reference=rawref,receipt_reference=rr,price_rows=253,open_close_values=506,returns=252,training_returns=126,evaluation_returns=126,returned_splits=0,returned_dividends=len(events.get('dividends',{})),original_weight_sum_exact=d['original_target_weight_sum_exact'],original_provenance_count=101,preserved_sidecar_count=7,evaluation_interval_previously_used_for_fitting=True,untouched_holdout=False,point_in_time_verified=False,benchmark_qualified=False,fit_performed=False,account_simulation_performed=False)

if __name__=='__main__':
 result=verify();out=ROOT/'DYNAMIC_ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result,indent=2))
