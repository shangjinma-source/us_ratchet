"""Read-only independent saved network V2 diagnostic verification; stdlib only."""
import argparse, csv, hashlib, io, json, os, re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
PARENT=ROOT/'data/cache/research/forward_network_day_receipt_20261003_v1'
SAVED=ROOT/'data/cache/research/forward_network_saved_diagnostic_20261003_v2'
OUTPUT=ROOT/'data/cache/research/forward_network_saved_diagnostic_independent_readback_20261003_v2'
PIN={
 'raw_QQQ':(PARENT/'QQQ.response.bin','6a7e79a370cae5ffc12eb28114c36b6ee1685d67dd6f9870bca6e0958ddb0bfd'),
 'raw_SPY':(PARENT/'SPY.response.bin','52ae32da20c44d6e99f024c978acb830c84e139fcd617122c8d5644c35495b4d'),
 'receipt_QQQ':(PARENT/'QQQ.receipt.json','a3d45e941845709f5982fad3f55d8b0d5be81b972af8279ad8f0b136d04982a9'),
 'receipt_SPY':(PARENT/'SPY.receipt.json','f14a43f2b60e1728ac1c0d70a98b446b9ae59c91187393e901f2f91e0d975c01'),
 'failure':(PARENT/'failure.json','ad49de29fe9e7c8976f745a62a1ef172fbf5c8f455b5a96b493a5f277a49739e'),
 'started':(PARENT/'started.json','3fe92ce0796928544123e77389edd76fbb904218efaa14df4165257d2974be34'),
 'baseline_QQQ':(ROOT/'data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'baseline_SPY':(ROOT/'data/cache/research/observation_gap_classification_20261002_v1/SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
 'old_core':(ROOT/'backtest/ndx_sina_saved_day_response_research.py','31417bc61f2471a8d92afede8eb85ff17cd92aadf71e439a9a72339987b80a36'),
 'old_producer':(ROOT/'scripts/ndx_forward_network_day_receipt_20261003.py','b1fb48b1e23e34b6bdb026f2382f0b421dab543890e12ccb85cd7cd97ac948f3'),
 'core':(ROOT/'backtest/ndx_sina_saved_day_response_v2_research.py','1e56dbd4967d466747331778b24eaa6bc814d8d4e2054a0fc6542d2ad0d328b7'),
 'producer':(ROOT/'scripts/ndx_forward_network_saved_diagnostic_20261003.py','df70c9ac08dc586b0eeb925c4f0a63649c3af77fbbe0dc13bed6121d6b8bcfd7'),
 'diagnostic':(SAVED/'diagnostic.json','be17caee922a4c59fd887d91a3f283263f51aa1cbe802d5555eb066f5fb70b50'),
 'publication':(SAVED/'publication.json','72799a45147cbad84f4085b8fee4cf90bf2df6f1d5df5a2cc81054ac59ce31c8'),
 'new_started':(SAVED/'started.json','7ec934f724e9f61ec82411d7e6d46dd70f17157d01a3d68b23b165feff0a404a')}
FLAGS=('observable_csv_derived','bridge_authorized','provider_basis_compatibility_verified','source_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','fresh_observation','point_in_time_verified','live_cache_written','old_capture_modified','oos_recovery_completed','clock_authenticity_verified')
NEWFLAGS=('network_request_performed','parent_failure_repaired','timeliness_evaluated')
FIELDS=('Open','High','Low','Close','Volume')

def require(ok,msg):
 if not ok: raise ValueError(msg)
def encoded(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def exact(a,b): require(encoded(a)==encoded(b),'Exact saved-value or source mismatch')
def pairs(values):
 out={}
 for k,v in values:
  require(k not in out,'Duplicate JSON key');out[k]=v
 return out
def load(b, tokens=False):
 kw=dict(object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
 if tokens: kw.update(parse_int=str,parse_float=str)
 return json.loads(b,**kw)
def utc(v):
 t=datetime.fromisoformat(v);require(t.utcoffset()==timedelta(0),'UTC receipt');return t
def day(v):
 d=date.fromisoformat(v);require(d.isoformat()==v and d.weekday()<5,'Canonical weekday');return v
def values(row):
 numbers={k:Decimal(row[k]) for k in FIELDS}
 require(all(n.is_finite() for n in numbers.values()),'Finite exact Decimal')
 normalized={}
 for k,n in numbers.items():
  s=format(n,'f');normalized[k]=('0' if n==0 else s.rstrip('0').rstrip('.') if '.' in s else s)
 valid=all(numbers[k]>0 for k in FIELDS[:4]) and numbers['Low']<=min(numbers['Open'],numbers['Close'])<=max(numbers['Open'],numbers['Close'])<=numbers['High']
 require(numbers['Volume']>=0 and numbers['Volume']==numbers['Volume'].to_integral_value(),'Integral volume')
 return normalized,valid

def inspect(ticker,raw,baseline,saved):
 banner=b"/*<script>location.href='//sina.com';</script>*/\n"
 require(raw.startswith(banner),'Observed exact banner')
 body=raw[len(banner):];match=re.fullmatch(r'var\s+_='+ticker+r'_day\((\[.*\])\);?',body.decode('utf-8-sig'),re.S)
 require(match is not None,'Only saved JSON array wrapper')
 rows=load(match.group(1),True);exact(rows,saved['raw_rows'])
 require(len(rows)==len(saved['normalized_rows']),'All provider rows')
 dates=[];normalized=[];outside=[]
 for i,r in enumerate(rows):
  d=day(r['d']);require(not dates or d>dates[-1],'Complete unique ascending dates');dates.append(d)
  val,valid=values({k:r[key] for k,key in zip(FIELDS,('o','h','l','c','v'))})
  require(d<'2026-07-01' or valid,'Required OHLC valid')
  if not valid: outside.append(dict(original_row_index=i,session=d,issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INVALID',original_row=r))
  normalized.append(dict(session=d,original_row_index=i,original_row=r,normalized=val,normalized_row_sha256=sha(encoded(dict(session=d,values=val)))))
 exact(normalized,saved['normalized_rows']);exact(outside,saved['outside_scope_ohlc_diagnostics'])
 reader=csv.DictReader(io.StringIO(baseline.decode('utf-8-sig'),newline=''));exact(reader.fieldnames,['Date',*FIELDS]);scope=[];prior=''
 for i,r in enumerate(reader):
  d=day(r['Date']);require(d>prior,'Full baseline order');prior=d
  if d>='2026-07-01':
   val,valid=values(r);require(valid,'Required baseline OHLC');scope.append(dict(session=d,original_data_row_index=i,original_row=r,normalized=val))
 exact(scope,saved['baseline_scope']);require(len(scope)==65,'65 accounted dates')
 lookup={r['session']:r for r in normalized};overlap=[];differences=[];missing=[]
 for b in scope:
  provider=lookup.get(b['session'])
  if provider is None: missing.append(b['session']);continue
  fields=[k for k in FIELDS if Decimal(b['original_row'][k])!=Decimal(provider['original_row'][dict(zip(FIELDS,('o','h','l','c','v')))[k]])]
  overlap.append(dict(session=b['session'],baseline_row=b,provider_row=provider,equal=not fields))
  if fields: differences.append(dict(session=b['session'],fields=fields,baseline=b['normalized'],provider=provider['normalized']))
 accounted=[r['session'] for r in scope];suffix=[d for d in dates if d>accounted[-1]]
 unexpected=[d for d in dates if accounted[0]<=d<=accounted[-1] and d not in accounted]
 for key,value in dict(ticker=ticker,scope_start='2026-07-01',target_session='2026-10-02',raw_sha256=sha(raw),baseline_sha256=sha(baseline),parsing_byte_offset=len(banner),parsing_bytes_sha256=sha(body),exact_banner_removed=True,ascii_only_response=raw.isascii(),overlap=overlap,overlap_differences=differences,missing_baseline_sessions=missing,unexpected_prefix_sessions=unexpected,new_provider_sessions=suffix,target_row=lookup.get('2026-10-02'),future_sessions=[d for d in suffix if d>'2026-10-02'],exact_single_new_target=suffix==['2026-10-02'],overlap_numeric_equal=not(missing or unexpected or differences)).items(): exact(saved[key],value)
 require(saved['schema']=='SINA_SAVED_DAY_OVERLAP_DIAGNOSTIC_V2' and saved['status']=='BLOCKED_PROVIDER_BASIS_COMPATIBILITY_NO_BRIDGE_AUTHORIZATION','Diagnostic only')
 for k in ('observable_csv_derived','provider_basis_compatibility_verified','source_authenticity_verified','historical_source_lineage_verified','candidate_seal_allowed','cohort_registration_allowed','fresh_observation','point_in_time_verified','live_mutation_allowed','oos_recovery_completed'): require(saved[k] is False,'No authority '+k)
 require(dates[-1]=='2026-10-01' and suffix==[] and not differences and not missing and not unexpected,'Actual observed no-new-date result')
 return dict(ticker=ticker,provider_rows=len(rows),first_date=dates[0],last_date=dates[-1],overlap_rows=len(overlap),decimal_field_comparisons=len(overlap)*5,overlap_differences=len(differences),new_sessions=suffix,target_row_present=False,outside_ohlc_diagnostics=len(outside))

def readback(*,execute=False):
 require(execute is True and not OUTPUT.exists(),'Explicit action/create-only')
 blobs={};refs={};sources={str(SOURCE):sha(SOURCE.read_bytes())}
 for role,(path,h) in PIN.items():
  b=path.read_bytes();require(sha(b)==h,'Pinned source drift '+role);blobs[role]=b;refs[role]=dict(path=str(path),sha256=h);sources[str(path)]=h
 require({p.name for p in PARENT.iterdir()}=={'started.json','failure.json','QQQ.response.bin','SPY.response.bin','QQQ.receipt.json','SPY.receipt.json'},'Frozen failed parent namespace')
 require({p.name for p in SAVED.iterdir()}=={'started.json','diagnostic.json','publication.json'},'Successful offline namespace')
 expected={refs[k]['path']:refs[k]['sha256'] for k in PIN if k not in ('diagnostic','publication','new_started')}
 bound={k:r for k,r in refs.items() if k not in ('core','producer','diagnostic','publication','new_started')}
 doc,pub,started,prior,fail=(load(blobs[k]) for k in ('diagnostic','publication','new_started','started','failure'))
 require(doc['schema']=='SAVED_NETWORK_DAY_DIAGNOSTIC_V2' and doc['status']=='BLOCKED_PROVIDER_BASIS_COMPATIBILITY_NO_BRIDGE_AUTHORIZATION','Output schema/status')
 require(pub['schema']=='SAVED_NETWORK_DAY_DIAGNOSTIC_PUBLICATION_V2' and pub['status']=='PUBLISHED_OFFLINE_DIAGNOSTIC_ONLY','Publication schema/status')
 require(started['schema']=='SAVED_NETWORK_DIAGNOSTIC_STARTED_V2','Started schema')
 exact(pub['diagnostic_reference'],refs['diagnostic'])
 for d in (doc,pub,started):
  exact(d['source_hashes'],expected)
  for k in (*FLAGS,*NEWFLAGS): require(d[k] is False,'Strict false '+k)
 exact(doc['input_references'],bound);exact(started['input_references'],bound)
 exact(doc['original_started'],prior);exact(doc['original_failure'],fail)
 require(prior['schema']=='FORWARD_NETWORK_DAY_RECEIPT_STARTED_V1' and fail['schema']=='FORWARD_NETWORK_DAY_RECEIPT_FAILURE_V1','Parent schema')
 require(fail['retry_allowed'] is False and fail['type']=='ValueError' and fail['message']=='Unsupported JSONP envelope; retain raw and block','Failed original preserved')
 for d in (prior,fail):
  for k in FLAGS: require(d[k] is False,'Parent flags')
 exact(prior['source_hashes'],{refs[k]['path']:refs[k]['sha256'] for k in ('old_core','old_producer','baseline_QQQ','baseline_SPY')})
 exact(prior['baseline_references'],{t:refs['baseline_'+t] for t in ('QQQ','SPY')})
 exact(prior['tickers'],['QQQ','SPY']);require(prior['target_session']=='2026-10-02','Target session')
 require(len(doc['rows'])==2,'Two source rows');previous=utc(prior['started_at_utc']);details=[]
 for t,entry in zip(('QQQ','SPY'),doc['rows']):
  require(entry['ticker']==t,'No source exchange');receipt=load(blobs['receipt_'+t]);exact(entry['original_receipt'],receipt)
  exact(entry['receipt_reference'],refs['receipt_'+t]);exact(entry['raw_reference'],refs['raw_'+t]);exact(receipt['raw_reference'],refs['raw_'+t])
  url='https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_='+t+'_day/US_MinKService.getDailyK?symbol='+t
  require(receipt['ticker']==t and receipt['request_url']==receipt['final_url']==url,'Exact provider/ticker')
  for k,n in [('network_attempt_count',1),('http_status',200),('saved_byte_count',len(blobs['raw_'+t]))]: require(type(receipt[k]) is int and receipt[k]==n,'Exact receipt count')
  require(receipt['response_complete'] is True and receipt['transport_error'] is None and receipt['retry_allowed'] is False and receipt['redirects_allowed'] is False,'Complete original receipt')
  require(previous<=utc(receipt['started_at_utc'])<=utc(receipt['completed_at_utc'])<=utc(fail['failed_at_utc']),'Saved UTC ordering');previous=utc(receipt['completed_at_utc'])
  details.append(inspect(t,blobs['raw_'+t],blobs['baseline_'+t],entry['diagnostic']))
 require(doc['new_session_sets_symmetric'] is True and doc['original_http_charset_preserved_not_used_to_guess_decoding'] is True,'No hidden source intersection')
 report=dict(schema='SAVED_NETWORK_DIAGNOSTIC_INDEPENDENT_READBACK_V2',status='PASS',diagnostic_reference=refs['diagnostic'],publication_reference=refs['publication'],reader_sha256=sources[str(SOURCE)],source_hashes=sources,producer_direct_source_count=len(expected),details=details,total_provider_rows=sum(d['provider_rows'] for d in details),decimal_field_comparisons=sum(d['decimal_field_comparisons'] for d in details),producer_called=False,core_called=False,network_performed=False,provider_basis_compatibility_verified=False,source_authenticity_verified=False,point_in_time_verified=False,timeliness_verified=False,observation_created=False,oos_recovery_completed=False,scope='SAVED_BYTES_OFFLINE_DIAGNOSTIC_ONLY_NOT_PROVIDER_OR_HISTORICAL_AVAILABILITY_AUTHENTICATION')
 for p,h in sources.items(): require(sha(Path(p).read_bytes())==h,'Final source drift')
 OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  b=encoded(report);path=OUTPUT/'independent_readback.json'
  with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
  for p,h in sources.items(): require(sha(Path(p).read_bytes())==h,'Postpublication source drift')
  require(path.read_bytes()==b and {p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Readback result bytes')
  return dict(path=str(path),sha256=sha(b),details=details)
 except Exception as error:
  with (OUTPUT/'failure.json').open('xb') as f:f.write(encoded(dict(status='FAILED',error=str(error),retry_allowed=False)));f.flush();os.fsync(f.fileno())
  raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
