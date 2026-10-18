"""Independent six505 NAV/FX arithmetic and adjacent-return inspection; no producer calls."""
from copy import deepcopy
from datetime import date
from decimal import Decimal,Context,localcontext
from fractions import Fraction
import hashlib,json,math
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
INNER=('source_bytes_verified','historical_nav_currency_verified','historical_available_at_verified','point_in_time_verified','provider_binding_verified','benchmark_qualified','formal_admission_allowed','account_executed','returns_computed','drawdown_computed','mode_selected_using_results','fit_performed','execution_authorized','fx_is_close_price','fx_is_executable_price')
def check(v,m):
 if not v:raise ValueError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):check(enc(a)==enc(b),m)
def display(v):
 with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def inspect_target_inputs(*,alignment,target,alignment_reference,reference_calendar,nav_rows,fx_rows,nav_reference,fx_reference,fx_context):
 calendar=reference_calendar
 check(type(calendar) is list and calendar==sorted(set(calendar)) and all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in calendar),'Reference calendar')
 check(all(c in calendar and calendar.index(c)>=504 for c in CUTOFFS),'Six505 predecessors')
 days=calendar[calendar.index(CUTOFFS[0])-504:calendar.index(CUTOFFS[-1])+1]
 nav=nav_rows;fxrows=fx_rows;context=fx_context
 check(context['rate_direction']=='CNY_PER_USD' and context['historical_available_at_verified'] is False,'Conditional CNY/USD source direction')
 refs={'nav_csv':nav_reference,'fx_readback':fx_reference}
 fx={'source_references':fx_context['source_references']}
 check([r['date'] for r in nav]==sorted({r['date'] for r in nav}),'NAV order/uniqueness')
 check([r['date'] for r in fxrows]==sorted({r['date'] for r in fxrows}),'FX order/uniqueness')
 for i,r in enumerate(nav):
  check(r['available_at'] is None and type(r['nav_cny_decimal']) is str and Fraction(r['nav_cny_decimal'])>0,'NAV positive/unknown publication')
  exact(r['source_reference'],dict(nav_reference,row_index=i,csv_record_number=i+2),'NAV real CSV pointer')
 for i,r in enumerate(fxrows):
  check(r['historical_available_at'] is None,'FX unknown publication')
  ref=r['source_reference'];check(type(ref['table_row_index']) is int and ref['table_row_index']==i and type(ref['html_line']) is int and ref['html_line']>0,'FX original HTML pointer')
  exact({k:ref[k] for k in ('path','sha256')},fx_context['source_references']['china_history']['raw'],'FX actual source role')
  if r['status']=='REPORTED_RATE':check(Fraction(r['rate_decimal'])==Fraction(r['rate_literal'])>0,'Positive FX')
  else:check(r['status']=='NOT_AVAILABLE_ND' and r['rate_decimal'] is None and r['rate_literal']=='ND','FX ND literal')
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
 exact(alignment,aligned,"Independent complete alignment")
 contract=dict(decision_cutoffs=list(CUTOFFS),price_count=505,return_count=504,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13,target_modes=list(MODES),native_cny_role='SOURCE_CONTEXT_NOT_USD_RANKING_TARGET',missing_policy='KEEP_SLOTS_BLOCK_FULL13_NO_PARTIAL_POOL',mode_selection_using_results_allowed=False)
 expected_modes=[]
 for mode in MODES:
  conversions=[r['conversions'][mode] for r in rows]
  values=[None if c['nav_usd_exact'] is None else Fraction(c['nav_usd_exact']) for c in conversions]
  slots=[dict(session=day,conversion_preserved=c) for day,c in zip(days,conversions)]
  returns=[]
  for n in range(len(days)-1):
   a,b=values[n:n+2];v=None if a is None or b is None else b/a-1;f=None if v is None else float(v)
   check(f is None or math.isfinite(f) and f>-1,'Float boundary')
   returns.append(dict(previous_session=days[n],session=days[n+1],return_exact=None if v is None else str(v),return_float=f,status='BLOCKED_RETURN_SLOT' if v is None else 'CONDITIONAL_NUMERIC_RETURN'))
  decisions=[]
  for cutoff in CUTOFFS:
   end=days.index(cutoff);start=end-504;windows=[]
   for ordinal in range(13):
    left=start+21*ordinal;missing=[days[n] for n in range(left,left+253) if values[n] is None]
    windows.append(dict(window_index=ordinal,training_price_predecessor=days[left],training_freeze_close=days[left+126],evaluation_first_return_end=days[left+127],evaluation_last_return_end=days[left+252],training_return_index_start=left,training_return_index_stop=left+126,evaluation_return_index_start=left+126,evaluation_return_index_stop=left+252,missing_price_sessions=missing,status='BLOCKED_WINDOW' if missing else 'CONDITIONAL_NUMERIC_WINDOW'))
   complete=all(not w['missing_price_sessions'] for w in windows)
   decisions.append(dict(cutoff=cutoff,required_price_dates=days[start:end+1],required_return_count=504,windows=windows,window_count=13,complete_thirteen_window_numeric_supply=complete,status='CONDITIONAL_ALL13_TARGET_SUPPLY' if complete else 'BLOCKED_FULL13_TARGET_SUPPLY',scoring_allowed=False,partial_window_pooling_allowed=False))
  expected_modes.append(dict(mode=mode,price_slots=slots,return_slots=returns,decisions=decisions))
 expected=dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_V1',status='CONDITIONAL_INPUT_PREPARATION_NOT_SCORING',contract=contract,alignment_reference=alignment_reference,alignment_preserved=aligned,reference_calendar_preserved=calendar,session_dates=days,modes=expected_modes,source_bytes_authenticated=False,independent_alignment_verified=False,point_in_time_verified=False,benchmark_qualified=False,score_computed=False,fit_performed=False,account_executed=False,promotion_allowed=False,mode_selected_using_results=False,partial_window_pooling_allowed=False,missing_values_filled=False,returns_computed=True,historical_retrospective_only=True)
 expected['content_sha256']=sha(enc(expected));exact(target,expected,'All two-mode target rows/windows')
 return dict(schema='MULTIDECISION_TARGET_INPUTS_ARITHMETIC_INSPECTION_V1',status='PASS',session_count=len(days),nav_row_count=len(nav),fx_row_count=len(fxrows),mode_count=2,decision_count_per_mode=6,window_count_per_mode=78,mode_missing_counts=aligned['mode_missing_counts'],alignment_producer_called=False,target_producer_called=False,score_computed=False,fit_performed=False,account_executed=False,point_in_time_verified=False,benchmark_qualified=False,mode_selected_using_results=False)
