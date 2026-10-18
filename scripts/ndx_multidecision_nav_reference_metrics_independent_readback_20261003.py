"""Independent saved NAV-window arithmetic and source readback; no producers run."""
from copy import deepcopy
from datetime import date
from decimal import Decimal,Context,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
from pathlib import Path
import hashlib,json,os,re,traceback,types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/multidecision_nav_reference_metrics_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_nav_reference_metrics_independent_readback_20261003_v1'
METRICS_SHA='2dc029413e03a8721c0c9baf6494115244f9d96b57640849090fb36be4d69a59'
PUBLICATION_SHA='eda71707860dc127c43e343d568b6cfdb781060576b2d649546e90797e8866db'
PRODUCER=ROOT/'scripts/ndx_multidecision_nav_reference_metrics_20261003.py'
PRODUCER_SHA='214baa13687f6ba603e1dd9a1471506c01cf4e4174551c7b9ff6ed6d9e11684f'
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND={
'alignment':('data/cache/research/nav_usd_observation_alignment_20261003_v1/alignment.json','ddd36e3bd3236d1494d9e42e08e66ce88e09d06c6c16f133c0214a951d54d90a'),
'alignment_publication':('data/cache/research/nav_usd_observation_alignment_20261003_v1/publication.json','f1c1e0c75fbdd1da09d590a3e534fb8bb39671f2cdd6d4c796c6ba9f86080878'),
'alignment_audit':('DYNAMIC_NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_20261003.json','53cba7de3d78cbf6b0fff8d00e77daf429ac497b75a021f0a8e2db7da1fe1ca9'),
'alignment_reader':('scripts/ndx_nav_usd_alignment_independent_review_20261003.py','8bf0f70985932f2413144c6135ec0b5df81c619172b5baa24ffd49d4e8449675'),
'account_inputs':('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json','c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
'account_publication':('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json','64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'),
'account_audit':('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json','8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'),
'account_reader':('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py','85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d')}
CODE={
'ndx_multidecision_reference_metrics_research':'0a1ef7ff8590538fdb29ce013027bd2ebd0ed17a816f405bc43bb0eef9489e62',
'ndx_same_window_nav_reference_metrics_research':'bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f',
'ndx_cash_fork_reference_window_research':'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'}
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX']
LANES=['RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE']
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_executed','account_metrics_calculated','subscription_redemption_modeled','fit_performed','selection_performed','point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','mode_selected_using_results','calendar_compressed','missing_values_filled','execution_authorized','promotion_allowed','automatic_retry_allowed','alignment_conversion_reaudited','future_independent_oos','untouched_holdout'),False)
INNER_FLAGS=dict.fromkeys(('point_in_time_verified','historical_available_at_verified','historical_currency_interval_verified','benchmark_qualified','formal_admission_allowed','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','account_executed','subscription_redemption_modeled','mode_selected_using_results','fit_performed','execution_authorized','promotion_allowed','future_independent_oos','untouched_holdout','missing_values_filled','calendar_compressed','raw_sources_reaudited'),False)
def require(v,m):
 if not v:raise ValueError(m)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def digest(x):return sha(enc(x))
def flags(x,keys):
 for k in keys:require(x[k] is False,'False authority '+k)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def merge(s,r):
 require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute external reference')
 require(r['path'] not in s or s[r['path']]==r['sha256'],'Conflicting source');s[r['path']]=r['sha256']
def decode(raw):
 def pairs(items):
  out={}
  for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def load(r,s,body=True):
 merge(s,r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent');raw=p.read_bytes();require(sha(raw)==r['sha256'],'Consumed bytes SHA');return decode(raw) if body else raw
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def dates(xs):
 require(type(xs)is list and xs==sorted(set(xs)) and 2<=len(xs)<=253,'Full ordered calendar')
 for x in xs:require(type(x)is str and date.fromisoformat(x).isoformat()==x,'Canonical date')
def rational(x):
 require(type(x)is str and 0<len(x)<=4096 and x.strip()==x,'Canonical rational text');v=Fraction(x);require(str(v)==x and v>0 and max(v.numerator.bit_length(),v.denominator.bit_length())<=16384,'Bounded positive rational');return v
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def independent_metrics(calendar,values):
 wealth=[v/values[0] for v in values]
 # All earlier/later pairs independently include the initial observation.
 dd=max(Fraction(0),max(1-wealth[j]/wealth[i] for j in range(len(wealth)) for i in range(j+1)))
 with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)) as ctx:
  terminal=Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator);annual=ctx.power(terminal,Decimal(252)/Decimal(len(calendar)-1))-1
 return dict(observation_count=len(calendar),interval_count=len(calendar)-1,cumulative_return=ratio(wealth[-1]-1),maximum_drawdown=ratio(dd),wealth=[dict(session=d,normalized_wealth=ratio(v)) for d,v in zip(calendar,wealth)],initial_one_in_drawdown=True,annualized_return_calculated=True,annualized_return_diagnostic_decimal=str(annual),annualization=dict(formula='terminal_normalized_wealth ** (252 / interval_count) - 1',sessions_per_year=252,interval_count=len(calendar)-1,decimal_precision=80,rounding='ROUND_HALF_EVEN',arithmetic='DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',annualization_is_historical_diagnostic=True,short_window_below_252_intervals=True,short_window_limitation='SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',formal_admission_allowed=False))
def inspect_reference(d,refs,saved):
 outer=d['alignment'];ap=d['alignment_publication'];aa=d['alignment_audit'];a=outer['alignment']
 require(outer['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1' and ap['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1' and ap['status']=='PUBLISHED_CONDITIONAL_CONVERSION_ONLY','Saved alignment role')
 exact(ap['alignment_reference'],refs['alignment'],'Alignment publication');exact(ap['source_hashes'],outer['source_hashes'],'Alignment closure')
 require(aa['schema']=='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1' and aa['status']=='PASS','Alignment audit')
 for field,role in [('alignment_sha256','alignment'),('publication_sha256','alignment_publication'),('reader_sha256','alignment_reader')]:require(aa[field]==refs[role]['sha256'],'Alignment audit binding')
 for obj in (outer,ap):flags(obj,('point_in_time_verified','benchmark_qualified','execution_authorized'))
 flags(aa,('point_in_time_verified','benchmark_qualified','account_executed'))
 doc=d['account_inputs'];pub=d['account_publication'];audit=d['account_audit'];inputs=doc['inputs']
 require(doc['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1' and pub['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Account source role')
 require(audit['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['scope']=='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION' and audit['reader_sha256']==refs['account_reader']['sha256'],'Account audit role')
 exact(pub['inputs_reference'],refs['account_inputs'],'Account publication');exact(audit['inputs_reference'],refs['account_inputs'],'Account audit inputs');exact(audit['publication_reference'],refs['account_publication'],'Account audit publication');exact(doc['source_hashes'],pub['source_hashes'],'Account source closure')
 for obj in (doc,pub):flags(obj,('account_simulation_performed','point_in_time_verified','execution_authorized','formal_benchmark_passed','promotion_allowed'))
 flags(audit,('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'))
 require(inputs['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' and inputs['content_sha256']==digest({k:v for k,v in inputs.items() if k!='content_sha256'}),'Account complete digest')
 for key,n in [('lane_count',8),('track_count',16),('coordinate_count',48)]:require(type(inputs[key])is int and inputs[key]==n and type(audit['inspection'][key])is int and audit['inspection'][key]==n,'Complete account domain')
 require(len(inputs['rows'])==8,'Full8 lanes');calendar=inputs['rows'][0]['tracks'][0]['stateful_input']['calendar'];dates(calendar);pointers=[]
 for i,row in enumerate(inputs['rows']):
  exact([row['fx_mode'],row['lane']],[MODES[i//4],LANES[i%4]],'Original lane order');require(len(row['tracks'])==2,'Two tracks')
  for j,t in enumerate(row['tracks']):
   require(t['track']==['CONTINUOUS','WHOLE_LOT'][j],'Track role');state=t['stateful_input'];exact(state['calendar'],calendar,'All16 calendar')
   for k in ('opens','closes'):exact(state[k]['index'],calendar,'No source calendar compression')
   pointers.append(f'/inputs/rows/{i}/tracks/{j}/stateful_input/calendar')
 require(len(calendar)==120 and calendar[0]=='2026-03-31' and calendar[-1]=='2026-09-21','120 points119 intervals')
 require(a['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_V1' and a['status']=='CONDITIONAL_HISTORICAL_CONVERSION_ONLY','Alignment object');exact(a['modes'],MODES,'Two FX modes');require(a['conversion_formula']=='BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD' and a['fx_context_preserved']['rate_direction']=='CNY_PER_USD','FX convention')
 flags(a,('point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','account_executed','mode_selected_using_results','fit_performed','execution_authorized'))
 require(a['content_sha256']==digest({k:v for k,v in a.items() if k!='content_sha256'}),'Alignment content digest');full=a['session_dates'];dates(full);require(len(full)==253 and calendar[0] in full,'Whole253 source');start=full.index(calendar[0]);exact(full[start:],calendar,'Contiguous full suffix');exact([r['session'] for r in a['rows']],full,'All original rows')
 modes={}
 for mode in MODES:
  observations=[];missing=[];values=[]
  for i in range(start,len(full)):
   row=a['rows'][i];conv=row['conversions'][mode];require(row['nav_date_fx_used_for_conversion'] is False and conv['denominator_basis']=='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX','No NAV date FX')
   if conv['status']=='MISSING_ALIGNMENT_INPUT':
    require(type(conv['reason'])is str and conv['reason'] and conv['nav_usd_exact'] is None and conv['nav_usd_decimal'] is None,'Missing slot preserved');value=None;missing.append(row['session'])
   else:require(conv['status']=='CONDITIONAL_NAV_USD_OBSERVATION' and conv['reason'] is None,'Known conversion');value=rational(conv['nav_usd_exact'])
   values.append(value);observations.append(dict(original_index=i,original_alignment_row=deepcopy(row),saved_value_exact=None if value is None else str(value)))
  modes[mode]=dict(mode=mode,missing_sessions=missing,observations=observations,status='BLOCKED_MISSING_REFERENCE_INPUT' if missing else 'HISTORICAL_METRICS_COMPUTED',metrics=None if missing else independent_metrics(calendar,values))
 expected=dict(schema='MULTIDECISION_CONTIGUOUS_NAV_REFERENCE_METRICS_V1',reference_calendar=dict(dates=calendar,source_reference=dict(refs['account_inputs'],json_pointer=pointers[0]),all_track_calendar_pointers=pointers,role='SAME_CALENDAR_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT'),alignment_reference=refs['alignment'],modes=modes,original_alignment_limitations=a['limitations'],original_fx_context=a['fx_context_preserved'],interpretation='EX_POST_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT_OR_COHORT',source_bytes_authenticated=False,alignment_conversion_reaudited=False,**INNER_FLAGS)
 exact(saved,expected,'Full independent NAV projection and arithmetic')
 return dict(mode_count=2,observation_count=120,interval_count=119,account_calendar_count=16,missing_by_mode={m:len(modes[m]['missing_sessions']) for m in MODES})
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s,inventories):
 require(hashfile(SOURCE)==LOADED,'Loaded reader drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift/failure')
 for path,names in inventories.items():require({p.name for p in Path(path).iterdir()}==set(names),'Exact parent inventory')
def load_inputs():
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for h in [METRICS_SHA,PUBLICATION_SHA,PRODUCER_SHA,*[h for _,h in BOUND.values()]]),'Future actual sources pending; no IO')
 refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};expected={str(LINEAGE):LINEAGE_SHA};d={}
 for k,r in refs.items():
  value=load(r,expected,not k.endswith('_reader'))
  if type(value)is dict:
   d[k]=value
   for p,h in value.get('source_hashes',{}).items():merge(expected,ref(p,h))
 for role in ('alignment_publication','account_publication'):
  if 'started_reference' in d[role]:load(d[role]['started_reference'],expected)
 for name,h in CODE.items():load(ref(ROOT/'backtest'/f'{name}.py',h),expected,False)
 load(ref(PRODUCER,PRODUCER_SHA),expected,False)
 sources=dict(expected);merge(sources,ref(SOURCE,LOADED));mr=ref(PARENT/'metrics.json',METRICS_SHA);pr=ref(PARENT/'publication.json',PUBLICATION_SHA)
 document=load(mr,sources);publication=load(pr,sources)
 require(publication['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_PUBLICATION_V1' and publication['status']=='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY_PENDING_READBACK','Successful exact NAV publication')
 exact(publication['metrics_reference'],mr,'Published metrics anchor')
 rawref=publication['raw_reference'];startref=publication['started_reference']
 for r,name in [(rawref,'raw_result.json'),(startref,'started.json')]:require(Path(r['path']).resolve()==PARENT/name,'Exact saved output locator')
 raw=load(rawref,sources);started=load(startref,sources)
 require(started['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_STARTED_V1','Started schema');require(raw['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_RAW_RETURN_V1','Raw schema')
 require(raw['returned'] is True and raw['call_invoked'] is True and type(raw['returned_call_count'])is int and raw['returned_call_count']==1 and raw['error'] is None and raw['original_return_is_json'] is True and raw['diagnostic_reference'] is None and raw['repr_error'] is None,'Only complete returned JSON')
 require(document['schema']=='MULTIDECISION_NAV_REFERENCE_METRICS_DOCUMENT_V1' and document['independent_readback_status']=='PENDING','Saved pending document');exact(document['raw_reference'],rawref,'Document raw binding');exact(raw['result'],document['metrics'],'Original raw result exact')
 for obj in (document,publication,raw,started):
  exact(obj['input_references'],refs,'Fixed8 source roles');exact(obj['source_hashes'],expected,'Independently reconstructed producer closure');flags(obj,FLAGS)
 for key in ('nav_manifest_preserved','nav_snapshot_preserved','fx_capture_manifest_preserved'):
  outputkey={'nav_manifest_preserved':'original_nav_manifest','nav_snapshot_preserved':'original_nav_snapshot','fx_capture_manifest_preserved':'original_fx_capture_manifest'}[key];exact(document[outputkey],d['alignment'][key],'Complete original capture metadata')
 inventories={str(PARENT):['started.json','raw_result.json','metrics.json','publication.json']}
 for role,name in [('alignment','alignment.json'),('account_inputs','inputs.json')]:inventories[str(Path(refs[role]['path']).parent)]=['started.json',name,'publication.json']
 # Older started files without an external receipt are only current-byte evidence.
 for path,names in list(inventories.items()):
  p=Path(path)/'started.json'
  if str(p) not in sources:
   b=p.read_bytes();merge(sources,ref(p,sha(b)))
 guard(sources,inventories)
 return dict(docs=d,refs=refs,document=document,sources=sources,inventories=inventories,metrics_reference=mr,publication_reference=pr)
def save(name,obj):
 raw=enc(obj);p=OUTPUT/name
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==raw,'Saved report drift');return ref(p,sha(raw))
def readback(*,execute=False):
 require(execute is True,'Explicit independent readback');require(not OUTPUT.exists(),'Create only no retry');c=load_inputs();OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_NAV_REFERENCE_INDEPENDENT_STARTED_V1',metrics_reference=c['metrics_reference'],publication_reference=c['publication_reference'],source_hashes=c['sources'])))
  counts=inspect_reference(c['docs'],c['refs'],c['document']['metrics']);guard(c['sources'],c['inventories'])
  rr=save('independent_readback.json',dict(schema='MULTIDECISION_NAV_REFERENCE_METRICS_INDEPENDENT_READBACK_V1',status='PASS',metrics_reference=c['metrics_reference'],publication_reference=c['publication_reference'],reader_sha256=LOADED,started_reference=written[0],source_hashes=c['sources'],inspection=counts,scope='SAVED_ALIGNMENT120_PROJECTION_AND_METRICS_NOT_FX_OR_ACCOUNT_REAUDIT',producer_called=False,old_metrics_called=False,original_started_dispatch_authority_verified=False,**FLAGS));written.append(rr)
  guard(c['sources'],c['inventories'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Own output drift')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact reader output');return rr
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**FLAGS))
  raise
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
