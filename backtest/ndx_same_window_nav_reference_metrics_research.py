"""Exact retrospective NAV reference metrics for the fixed 2026 evaluation window."""
from copy import deepcopy
from datetime import date
from decimal import Decimal,Context,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
import hashlib
import json

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
FLAGS=dict.fromkeys(('point_in_time_verified','historical_available_at_verified','historical_currency_interval_verified','benchmark_qualified','formal_admission_allowed','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','account_executed','subscription_redemption_modeled','mode_selected_using_results','fit_performed','execution_authorized','promotion_allowed','future_independent_oos','untouched_holdout','missing_values_filled','calendar_compressed','raw_sources_reaudited'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def reference(value):
    require(type(value) is dict and {'path','sha256'}<=set(value),'External reference required')
    require(type(value['path']) is str and bool(value['path']),'Reference path required')
    h=value['sha256'];require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Reference SHA required')
def dates(values):
    require(type(values) is list and len(values)<=253,'Bounded date list')
    for d in values:require(type(d) is str and date.fromisoformat(d).isoformat()==d,'Exact ISO day required')
    require(values==sorted(set(values)),'Dates ordered and unique')
def fraction(value):
    require(type(value) is str and 0<len(value)<=4096 and value==value.strip(),'Exact bounded rational string required')
    try:v=Fraction(value)
    except Exception:raise ValueError('Invalid rational string') from None
    require(str(v)==value and v>0,'Positive canonical rational required')
    require(v.numerator.bit_length()<=16384 and v.denominator.bit_length()<=16384,'Rational resource bound')
    return v
def display(value):
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
        return str(Decimal(value.numerator)/Decimal(value.denominator))
def metric(value):return dict(exact=str(value),decimal=display(value),unit='DIMENSIONLESS_RATIO_NOT_PERCENT')

def calculate_reference_metrics(*,alignment,alignment_reference,reference_calendar):
    """Use saved independently checked exact conversions, without redoing FX alignment."""
    reference(alignment_reference);reference(reference_calendar['source_reference'])
    require(alignment['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_V1' and alignment['status']=='CONDITIONAL_HISTORICAL_CONVERSION_ONLY','Saved observation alignment required')
    exact(alignment['modes'],list(MODES),'Both fixed modes required')
    require(alignment['conversion_formula']=='BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD' and alignment['fx_context_preserved']['rate_direction']=='CNY_PER_USD','Direction and session FX convention')
    for key in ('point_in_time_verified','historical_available_at_verified','benchmark_qualified','formal_admission_allowed','account_executed','mode_selected_using_results','fit_performed','execution_authorized'):require(alignment[key] is False,'Saved alignment has no authority')
    require(alignment['content_sha256']==digest({k:v for k,v in alignment.items() if k!='content_sha256'}),'Saved alignment content digest')
    all_dates=alignment['session_dates'];dates(all_dates);require(len(all_dates)==253 and all_dates[0]=='2025-09-18' and all_dates[126]=='2026-03-20' and all_dates[-1]=='2026-09-21','Fixed complete253 parent window')
    selected=reference_calendar['dates'];dates(selected);require(len(selected)==127,'127 prices for126 intervals');exact(selected,all_dates[126:],'Exact frozen initialClose plus126 evaluation rows')
    require(len(alignment['rows'])==253,'Full original alignment rows');exact([r['session'] for r in alignment['rows']],all_dates,'Original row order')
    modes={}
    for mode in MODES:
        observations=[];values=[]
        for original_index,row in enumerate(alignment['rows'][126:],126):
            conversion=row['conversions'][mode];require(conversion['denominator_basis']=='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX' and row['nav_date_fx_used_for_conversion'] is False,'Do not substitute NAV-date FX')
            if conversion['status']=='MISSING_ALIGNMENT_INPUT':
                require(type(conversion['reason']) is str and conversion['reason'] and conversion['nav_usd_exact'] is None and conversion['nav_usd_decimal'] is None,'Missing input remains explicit null');value=None
            else:
                require(conversion['status']=='CONDITIONAL_NAV_USD_OBSERVATION' and conversion['reason'] is None,'Known alignment state');value=fraction(conversion['nav_usd_exact'])
            values.append(value)
            observations.append(dict(session=row['session'],alignment_row_reference=dict(alignment_reference,json_pointer=f'/alignment/rows/{original_index}'),original_alignment_row=deepcopy(row),mode=mode,saved_value_exact=None if value is None else str(value),normalized_value_exact=None,normalized_value_decimal=None,drawdown_from_running_peak_exact=None))
        missing=[row['session'] for row,v in zip(observations,values) if v is None]
        if missing:
            intervals=[dict(previous_session=a,session=b,return_exact=None) for a,b in zip(selected,selected[1:])]
            metrics=None;status='BLOCKED_MISSING_REFERENCE_INPUT'
        else:
            normalized=[v/values[0] for v in values];peak=normalized[0];peak_index=0;maximum=Fraction(0);maximum_peak=maximum_trough=0
            for i,(row,v) in enumerate(zip(observations,normalized)):
                if v>peak:peak=v;peak_index=i
                drawdown=1-v/peak
                if drawdown>maximum:maximum=drawdown;maximum_peak=peak_index;maximum_trough=i
                row.update(normalized_value_exact=str(v),normalized_value_decimal=display(v),drawdown_from_running_peak_exact=str(drawdown))
            intervals=[dict(previous_session=selected[i],session=selected[i+1],return_exact=str(values[i+1]/values[i]-1)) for i in range(126)]
            ratio=values[-1]/values[0]
            metrics=dict(cumulative_return=metric(ratio-1),annualized_return=metric(ratio**2-1),maximum_drawdown=metric(maximum),annualization=dict(trading_days_per_year=252,return_interval_count=126,exponent_exact='2',formula='(LAST / FIRST) ** (252 / 126) - 1'),drawdown=dict(first_observation_included_as_peak=True,sign_convention='NONNEGATIVE_PEAK_TO_TROUGH_LOSS',peak_index=maximum_peak,trough_index=maximum_trough,peak_session=selected[maximum_peak],trough_session=selected[maximum_trough],equal_peak_policy='EARLIEST_UNTIL_STRICTLY_HIGHER_PEAK',equal_maximum_policy='FIRST_STRICT_MAXIMUM'))
            status='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED'
        modes[mode]=dict(mode=mode,status=status,observation_count=127,interval_count=126,missing_sessions=missing,observations=observations,interval_returns=intervals,metrics=metrics)
    both_complete=all(v['metrics'] is not None for v in modes.values())
    same=None if not both_complete else all(a['saved_value_exact']==b['saved_value_exact'] for a,b in zip(modes[MODES[0]]['observations'],modes[MODES[1]]['observations']))
    result=dict(schema='SAME_WINDOW_NAV_REFERENCE_METRICS_V1',status='HISTORICAL_EXTERNAL_REFERENCE_ONLY',reference_calendar=deepcopy(reference_calendar),alignment_reference=deepcopy(alignment_reference),mode_order=list(MODES),modes=modes,both_modes_complete=both_complete,mode_values_exactly_equal=same,modes_retained_separately=True,historical_normalization_base_exact='1',normalization_is_invested_capital_or_trade=False,evaluation_interval_previously_used_for_candidate_fitting=True,interpretation='EX_POST_NAV_USD_REFERENCE_NOT_FUND_SUBSCRIPTION_ACCOUNT_OR_COHORT',source_conversion_formula=alignment['conversion_formula'],original_alignment_limitations=deepcopy(alignment['limitations']),original_fx_context=deepcopy(alignment['fx_context_preserved']),decimal_display=dict(precision=80,rounding='ROUND_HALF_EVEN',exact_fraction_authoritative=True),**FLAGS)
    result['content_sha256']=digest(result)
    return result
