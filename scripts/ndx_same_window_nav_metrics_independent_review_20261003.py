"""Exact external reference oracle from saved conversions, no production imports."""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal,Context,localcontext
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/same_window_nav_reference_metrics_20261003_v1'
SHA='2f2d072190115b38de2776b8ba33b50372a8546b2c858766751b79915c78dcfa'
PUB='338ae747c8d79ac70050742ce7b43e723c3d608f59776175186ab16d4fd08b5a'
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX']
def check(v,m):
 if not v:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(p,h):
 b=Path(p).read_bytes();check(sha(b)==h,'SHA '+str(p));return b
def display(v):
 with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def metric(v):return dict(exact=str(v),decimal=display(v),unit='DIMENSIONLESS_RATIO_NOT_PERCENT')
def verify():
 d=json.loads(read(BASE/'metrics.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes());refs=d['input_references'];docs={};sources={}
 check({p.name for p in BASE.iterdir()}=={'started.json','metrics.json','publication.json'},'Successful namespace')
 for role,r in refs.items():
  b=read(r['path'],r['sha256']);sources[r['path']]=r['sha256']
  if role!='alignment_audit_reader':docs[role]=json.loads(b)
 for rel,h in [('backtest/ndx_same_window_nav_reference_metrics_research.py','bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f'),('scripts/ndx_same_window_nav_reference_metrics_20261003.py','7d7c086dceb134dbd1e7f05e8a61b036cbc193b4adc3a46b65231e5b604cae73')]:read(ROOT/rel,h);sources[str(ROOT/rel)]=h
 check(len(sources)==9,'9 direct sources');exact(d['source_hashes'],sources,'Sources');exact(pub['source_hashes'],sources,'Publication sources');exact(started['source_hashes'],sources,'Started sources');exact(started['input_references'],refs,'Started parents')
 exact(pub['metrics_reference'],dict(path=str(BASE/'metrics.json'),sha256=SHA),'Output reference');check(pub['status']=='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY','Reference publication')
 outer=docs['alignment'];a=outer['alignment'];req=docs['requirements']['requirements'];report=docs['alignment_audit'];m=d['metrics']
 check(report['status']=='PASS' and report['alignment_sha256']==refs['alignment']['sha256'] and report['publication_sha256']==refs['alignment_publication']['sha256'] and report['reader_sha256']==refs['alignment_audit_reader']['sha256'],'Independent conversion binding only')
 exact(docs['alignment_publication']['alignment_reference'],refs['alignment'],'Alignment receipt');exact(docs['requirements_publication']['requirements_reference'],refs['requirements'],'Requirement receipt')
 exact(docs['alignment_publication']['source_hashes'],outer['source_hashes'],'Alignment map');exact(docs['requirements_publication']['source_hashes'],docs['requirements']['source_hashes'],'Requirement map')
 for k,source in [('original_nav_manifest','nav_manifest_preserved'),('original_nav_snapshot','nav_snapshot_preserved'),('original_fx_capture_manifest','fx_capture_manifest_preserved')]:exact(d[k],outer[source],'Full source sidecar')
 dates=[req['evaluation_initial_close_date']]+req['evaluation_return_end_dates'];exact(dates,a['session_dates'][126:],'Same127 dates');check(len(dates)==127 and dates[0]=='2026-03-20' and dates[-1]=='2026-09-21','Fixed calendar')
 exact(docs['panel']['panel']['returns']['index'],[x+'T00:00:00' for x in dates[1:]],'Already used126 interval');exact(m['mode_order'],MODES,'Separate modes')
 summaries=[]
 for mode in MODES:
  saved=m['modes'][mode];rows=a['rows'][126:];values=[None if x['conversions'][mode]['nav_usd_exact'] is None else Fraction(x['conversions'][mode]['nav_usd_exact']) for x in rows];missing=[x for x,v in zip(dates,values) if v is None]
  exact(saved['missing_sessions'],missing,'All missing slots');check(saved['observation_count']==127 and saved['interval_count']==126 and len(saved['observations'])==127 and len(saved['interval_returns'])==126,'No compression')
  peak=None;peak_index=0;loss=Fraction(0);pi=ti=0
  for i,(row,value) in enumerate(zip(rows,values)):
   item=dict(session=dates[i],alignment_row_reference=dict(refs['alignment'],json_pointer=f'/alignment/rows/{126+i}'),original_alignment_row=row,mode=mode,saved_value_exact=None if value is None else str(value),normalized_value_exact=None,normalized_value_decimal=None,drawdown_from_running_peak_exact=None)
   if not missing:
    normalized=value/values[0]
    if peak is None or normalized>peak:peak=normalized;peak_index=i
    dd=1-normalized/peak
    if dd>loss:loss=dd;pi=peak_index;ti=i
    item.update(normalized_value_exact=str(normalized),normalized_value_decimal=display(normalized),drawdown_from_running_peak_exact=str(dd))
   exact(saved['observations'][i],item,'Full saved conversion, normalization and provenance')
  expectedreturns=[dict(previous_session=dates[i],session=dates[i+1],return_exact=None if missing else str(values[i+1]/values[i]-1)) for i in range(126)];exact(saved['interval_returns'],expectedreturns,'126 interval returns')
  if missing:check(saved['metrics'] is None and saved['status']=='BLOCKED_MISSING_REFERENCE_INPUT','Missing mode blocked')
  else:
   # Independently verify running algorithm with every earlier/later pair.
   check(loss==max(1-values[j]/values[i] for j in range(127) for i in range(j+1)),'All-pairs drawdown oracle')
   ratio=values[-1]/values[0];expected=dict(cumulative_return=metric(ratio-1),annualized_return=metric(ratio*ratio-1),maximum_drawdown=metric(loss),annualization=dict(trading_days_per_year=252,return_interval_count=126,exponent_exact='2',formula='(LAST / FIRST) ** (252 / 126) - 1'),drawdown=dict(first_observation_included_as_peak=True,sign_convention='NONNEGATIVE_PEAK_TO_TROUGH_LOSS',peak_index=pi,trough_index=ti,peak_session=dates[pi],trough_session=dates[ti],equal_peak_policy='EARLIEST_UNTIL_STRICTLY_HIGHER_PEAK',equal_maximum_policy='FIRST_STRICT_MAXIMUM'))
   exact(saved['metrics'],expected,'All exact metrics');check(saved['status']=='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED','Complete mode')
  summaries.append(dict(mode=mode,missing_sessions=missing,metrics=saved['metrics']))
 complete=all(not x['missing_sessions'] for x in summaries);same=None if not complete else all(x['conversions'][MODES[0]]['nav_usd_exact']==x['conversions'][MODES[1]]['nav_usd_exact'] for x in a['rows'][126:]);check(m['both_modes_complete'] is complete and m['mode_values_exactly_equal'] is same and m['modes_retained_separately'] is True,'No mode selection')
 exact(m['original_alignment_limitations'],a['limitations'],'Availability limits');exact(m['original_fx_context'],a['fx_context_preserved'],'Current FX vintage')
 check(m['content_sha256']==sha(enc({k:v for k,v in m.items() if k!='content_sha256'})),'Metrics content checksum')
 for item in (d,m,pub,started):
  for key in ('point_in_time_verified','benchmark_qualified','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','account_executed','subscription_redemption_modeled','mode_selected_using_results','fit_performed','execution_authorized','promotion_allowed','future_independent_oos','untouched_holdout','raw_sources_reaudited'):check(item[key] is False,'No authority '+key)
 check(m['normalization_is_invested_capital_or_trade'] is False and m['evaluation_interval_previously_used_for_candidate_fitting'] is True,'Reference only')
 for path,h in sources.items():read(path,h)
 return dict(schema='SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_V1',status='PASS',metrics_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=9,mode_count=2,observation_slots=254,return_slots=252,both_modes_complete=complete,mode_values_exactly_equal=same,modes=summaries,benchmark_qualified=False,point_in_time_verified=False,formal_comparison_passed=False,account_executed=False,raw_sources_reaudited=False)
if __name__=='__main__':
 r=verify()
 with (ROOT/'DYNAMIC_SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_20261003.json').open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r,indent=2))
