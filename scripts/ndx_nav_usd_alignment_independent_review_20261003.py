"""Independent saved NAV/FX alignment arithmetic; no producer or HTML re-audit."""
from datetime import date
from decimal import Decimal,Context,localcontext
from fractions import Fraction
from pathlib import Path
import csv
import hashlib
import io
import json
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/nav_usd_observation_alignment_20261003_v1'
SHA='ddd36e3bd3236d1494d9e42e08e66ce88e09d06c6c16f133c0214a951d54d90a'
PUB='f1c1e0c75fbdd1da09d590a3e534fb8bb39671f2cdd6d4c796c6ba9f86080878'
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
OUTER=('http_performed','old_audit_repeated','account_executed','returns_computed','drawdown_computed','fit_performed','mode_selected_using_results','point_in_time_verified','promotion_allowed','execution_authorized','benchmark_qualified','legal_training_input_admitted','historical_nav_currency_verified','historical_available_at_verified','full_transitive_source_closure_reverified')
INNER=('source_bytes_verified','historical_nav_currency_verified','historical_available_at_verified','point_in_time_verified','provider_binding_verified','benchmark_qualified','formal_admission_allowed','account_executed','returns_computed','drawdown_computed','mode_selected_using_results','fit_performed','execution_authorized','fx_is_close_price','fx_is_executable_price')
def check(v,m):
 if not v:raise ValueError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(p,h):
 b=Path(p).read_bytes();check(sha(b)==h,'SHA '+str(p));return b
def display(v):
 with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def verify():
 d=json.loads(read(BASE/'alignment.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes());refs=d['input_references'];sources=d['source_hashes']
 check({p.name for p in BASE.iterdir()}=={'started.json','alignment.json','publication.json'},'Exact namespace');check(len(refs)==7 and len(sources)==17,'Direct source counts')
 blobs={p:read(p,h) for p,h in sources.items()};docs={k:json.loads(blobs[r['path']]) for k,r in refs.items() if k!='nav_csv'}
 fx=docs['fx_readback'];req=docs['requirements'];navmanifest=docs['nav_manifest'];snapshot=docs['nav_snapshot'];capture=docs['fx_manifest']
 expected_sources={r['path']:r['sha256'] for r in refs.values()}
 expected_sources.update({str(ROOT/'backtest/ndx_nav_usd_observation_alignment_research.py'):'9c5c68453c3796f1f33656a2d8a0a16bd172ef00c2d8e02fc4f1b9ee69a2fb84',str(ROOT/'scripts/ndx_nav_usd_observation_alignment_20261003.py'):'a63352863192ca9f69d8fbb48c1132d41e95639f7aeb7bc276f29c32d0cb7e7e',str(ROOT/'scripts/ndx_official_fx_independent_review_20261003.py'):fx['reader_sha256'],str(ROOT/'scripts/ndx_official_fx_capture_20261003.py'):capture['source_sha256']})
 for source in fx['source_references'].values():
  for k in ('raw','receipt'):expected_sources[str((ROOT/source[k]['path']).resolve())]=source[k]['sha256']
 exact(sources,expected_sources,'All17 direct sources, no source silently omitted')
 exact(docs['requirements_publication']['requirements_reference'],refs['requirements'],'Requirements receipt')
 exact(docs['requirements_publication']['source_hashes'],req['source_hashes'],'Requirements source closure reference')
 exact(snapshot['immutable_copies']['nav.csv'],refs['nav_csv'],'NAV immutable CSV');exact(snapshot['immutable_copies']['original_manifest.json'],refs['nav_manifest'],'NAV immutable manifest')
 check(navmanifest['content_sha256']==refs['nav_csv']['sha256'] and navmanifest['publication_time_known'] is False and snapshot['nav_publication_time_verified'] is False,'NAV unknown publication')
 check(fx['manifest_sha256']==refs['fx_manifest']['sha256'] and fx['status']=='PASS','Saved FX readback identity');exact({r['name']:r for r in capture['sources']},fx['source_references'],'FX manifest pointers')
 for value in (fx,capture):check(value['historical_available_at_verified'] is False and value['point_in_time_verified'] is False and value['benchmark_qualified'] is False,'FX bounds')
 days=req['requirements']['reference_calendar']['dates'];check(len(days)==253 and days==sorted(set(days)),'253 date denominator')
 reader=csv.DictReader(io.StringIO(blobs[refs['nav_csv']['path']].decode('utf-8-sig')));check(reader.fieldnames==['Date','UnitNav','AccumNav','DailyPct','Close'],'CSV fields');navcsv=list(reader);check(len(navcsv)==1101,'All NAV rows')
 nav=[]
 for i,row in enumerate(navcsv):
  check(row['Close']==row['UnitNav'],'Close=UnitNav original string')
  exact(req['requirements']['nav_metadata_preserved']['rows'][i],dict(date=row['Date'],row_index=i,source_reference=refs['nav_csv']),'NAV metadata coordinate')
  nav.append(dict(date=row['Date'],nav_cny_decimal=row['Close'],available_at=None,source_reference=dict(refs['nav_csv'],row_index=i,csv_record_number=i+2),original_csv_row=row))
 fxrows=fx['table_rows'];check(len(fxrows)==6975,'All FX table rows');context={k:fx[k] for k in ('rate_direction','historical_available_at_verified','page_release_label','limitations','source_references','frequency','official_clauses','receipts')}
 check(context['rate_direction']=='CNY_PER_USD','CNY per USD denominator')
 for i,row in enumerate(fxrows):
  check(row['source_reference']['table_row_index']==i and row['historical_available_at'] is None,'FX original position/time')
  if row['status']=='REPORTED_RATE':check(Fraction(row['rate_decimal'])==Fraction(row['rate_literal'])>0,'FX precise decimal')
  else:check(row['status']=='NOT_AVAILABLE_ND' and row['rate_decimal'] is None and row['rate_literal']=='ND','ND unchanged')
 def fx_at(day):
  same=[(i,r) for i,r in enumerate(fxrows) if r['date']==day];valid=[(i,r) for i,r in enumerate(fxrows) if r['date']<=day and r['status']=='REPORTED_RATE'];s=same[0] if same else None;b=valid[-1] if valid else None
  def observation(pair):
   if pair is None:return None
   i,row=pair;return dict(date=row['date'],lag_calendar_days=(date.fromisoformat(day)-date.fromisoformat(row['date'])).days,original_row_index=i,original_row=row,rate_exact=None if row['rate_decimal'] is None else str(Fraction(row['rate_decimal'])),historical_available_at=None)
  lower='' if b is None else b[1]['date'];skipped=[dict(original_row_index=i,original_row=r) for i,r in enumerate(fxrows) if lower<r['date']<=day and r['status']=='NOT_AVAILABLE_ND']
  return dict(same_date=observation(s),backward_valid=observation(b),skipped_nd_rows=skipped),(s,b)
 rows=[];non_same_nav=[];strictmissing=[];backwardlag=[]
 for day in days:
  choices=[(i,r) for i,r in enumerate(nav) if r['date']<=day];chosen=choices[-1] if choices else None;ni=None if chosen is None else chosen[0];nr=None if chosen is None else chosen[1]
  nob=None if nr is None else dict(date=nr['date'],lag_calendar_days=(date.fromisoformat(day)-date.fromisoformat(nr['date'])).days,original_row_index=ni,original_row=nr,nav_cny_exact=str(Fraction(nr['nav_cny_decimal'])),available_at=None)
  aligned,pairs=fx_at(day);diagnostic=None if nr is None else fx_at(nr['date'])[0];conversions={}
  for mode,pair in zip(MODES,pairs):
   fi=None if pair is None else pair[0];fr=None if pair is None else pair[1];rate=None if fr is None or fr['rate_decimal'] is None else Fraction(fr['rate_decimal'])
   reason='NO_PRIOR_NAV_OBSERVATION' if nr is None else 'NO_SAME_SESSION_FX_ROW' if mode==MODES[0] and fr is None else 'SAME_SESSION_FX_ND' if mode==MODES[0] and rate is None else 'NO_PRIOR_VALID_FX_OBSERVATION' if rate is None else None
   value=None if reason else Fraction(nr['nav_cny_decimal'])/rate
   conversions[mode]=dict(status='MISSING_ALIGNMENT_INPUT' if reason else 'CONDITIONAL_NAV_USD_OBSERVATION',reason=reason,nav_usd_exact=None if value is None else str(value),nav_usd_decimal=None if value is None else display(value),nav_date=None if nr is None else nr['date'],fx_date=None if fr is None else fr['date'],fx_original_row_index=fi,nav_original_row_index=ni,denominator_basis='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX')
  rows.append(dict(session=day,nav_observation=nob,session_fx=aligned,nav_date_fx_diagnostic_only=diagnostic,nav_date_fx_used_for_conversion=False,conversions=conversions))
  if nr is not None and nr['date']!=day:non_same_nav.append(day)
  if conversions[MODES[0]]['nav_usd_exact'] is None:strictmissing.append(day)
  if aligned['backward_valid'] is not None and aligned['backward_valid']['date']!=day:backwardlag.append(dict(session=day,fx_date=aligned['backward_valid']['date'],lag=aligned['backward_valid']['lag_calendar_days']))
 claims={refs['nav_csv']['path']:refs['nav_csv']['sha256'],refs['fx_readback']['path']:refs['fx_readback']['sha256'],fx['source_references']['china_history']['raw']['path']:fx['source_references']['china_history']['raw']['sha256']}
 aligned=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_V1',status='CONDITIONAL_HISTORICAL_CONVERSION_ONLY',session_dates=days,rows=rows,modes=list(MODES),nav_rows_preserved=nav,fx_rows_preserved=fxrows,nav_reference=refs['nav_csv'],fx_reference=refs['fx_readback'],fx_context_preserved=context,direct_reference_hash_claims=claims,source_claims_not_full_transitive_verification=True,conversion_formula='BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD',historical_nav_currency_assumption='CNY_CONDITIONALLY_ASSUMED_NOT_INTERVAL_CERTIFIED',limitations=['CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','NO_AVAILABLE_AT','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX','HISTORICAL_NAV_CNY_IS_CONDITIONAL_ASSUMPTION'],decimal_display=dict(precision=80,rounding='ROUND_HALF_EVEN',exact_fraction_authoritative=True),mode_missing_counts={mode:sum(r['conversions'][mode]['nav_usd_exact'] is None for r in rows) for mode in MODES},**dict.fromkeys(INNER,False))
 aligned['content_sha256']=sha(enc(aligned))
 expected=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1',alignment=aligned,input_references=refs,source_hashes=sources,requirements_reference_preserved=refs['requirements'],original_requirements_source_hashes_preserved=req['source_hashes'],nav_manifest_preserved=navmanifest,nav_snapshot_preserved=snapshot,fx_capture_manifest_preserved=capture,prior_unbound_fx_requirement_not_overwritten=True,**dict.fromkeys(OUTER,False))
 exact(d,expected,'All253 two-mode values and complete outer/inner')
 exact(started,dict(source_hashes=sources,retry_allowed=False,**dict.fromkeys(OUTER,False)),'Started')
 exact(pub,dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_CONVERSION_ONLY',alignment_reference=dict(path=str(BASE/'alignment.json'),sha256=SHA),source_hashes=sources,**dict.fromkeys(OUTER,False)),'Publication')
 return dict(schema='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1',status='PASS',alignment_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_sources=17,nav_rows=1101,fx_rows=6975,session_count=253,mode_observations=506,mode_missing_counts=aligned['mode_missing_counts'],exact_nonnull_conversion_count=sum(r['conversions'][mode]['nav_usd_exact'] is not None for r in rows for mode in MODES),strict_missing_sessions=strictmissing,backward_fx_lag_rows=backwardlag,non_same_nav_date_count=len(non_same_nav),source_html_reparsed=False,old_fx_audit_repeated=False,returns_computed=False,account_executed=False,point_in_time_verified=False,benchmark_qualified=False)
if __name__=='__main__':
 result=verify();out=ROOT/'DYNAMIC_NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result,indent=2))
