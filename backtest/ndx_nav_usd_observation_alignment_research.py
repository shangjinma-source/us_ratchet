"""Saved-observation NAV/FX alignment, not returns or tradable valuations."""
from bisect import bisect_right
from copy import deepcopy
from datetime import date
from decimal import Decimal,Context,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
import hashlib
import json

SCHEMA='NAV_USD_OBSERVATION_ALIGNMENT_V1'
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
FLAGS=dict.fromkeys(('source_bytes_verified','historical_nav_currency_verified','historical_available_at_verified','point_in_time_verified','provider_binding_verified','benchmark_qualified','formal_admission_allowed','account_executed','returns_computed','drawdown_computed','mode_selected_using_results','fit_performed','execution_authorized','fx_is_close_price','fx_is_executable_price'),False)
LIMITATIONS=('CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','NO_AVAILABLE_AT','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX','HISTORICAL_NAV_CNY_IS_CONDITIONAL_ASSUMPTION')


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date required')
    return value


def dates(values):
    require(type(values) is list and 0<len(values)<=20000,'Bounded nonempty date list')
    for v in values:day(v)
    require(values==sorted(set(values)),'Dates must be unique and already ordered')


def number(value):
    require(type(value) is str and value and value==value.strip(),'Exact decimal string required, not float/bool')
    try:v=Decimal(value)
    except Exception:raise ValueError('Finite decimal required') from None
    require(v.is_finite() and v>0 and abs(v.adjusted())<=100 and len(v.as_tuple().digits)<=256,'Bounded positive decimal required')
    return Fraction(v)


def display(value):
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def align_nav_usd_observations(*,session_dates,nav_rows,fx_rows,nav_reference,fx_reference,fx_context):
    """Both modes always returned, preserving all source rows and missing states.

    FX values are Chinese yuan per USD. Each mode divides the same backward NAV
    by session-aligned FX, never by a silently substituted NAV-date FX value.
    """
    dates(session_dates);claims={}
    def reference(r):
        require(type(r) is dict and {'path','sha256'}<=set(r),'Explicit reference required')
        p=r['path'];s=r['sha256'];require(type(p) is str and p and p==p.strip(),'Source path required')
        require(type(s) is str and len(s)==64 and all(c in '0123456789abcdef' for c in s),'SHA required')
        require(p not in claims or claims[p]==s,'Conflicting reference hashes');claims[p]=s
    reference(nav_reference);reference(fx_reference)
    require(type(nav_rows) is list and type(fx_rows) is list,'Saved row lists required')
    dates([r['date'] for r in nav_rows]);dates([r['date'] for r in fx_rows])
    nav_values=[]
    for row in nav_rows:
        require(type(row) is dict and row.get('available_at') is None,'NAV publication time must remain unknown')
        reference(row['source_reference'])
        require(row['source_reference']['path']==nav_reference['path'] and row['source_reference']['sha256']==nav_reference['sha256'],'NAV row/source differs')
        nav_values.append(number(row['nav_cny_decimal']))
    require(type(fx_context) is dict and fx_context.get('rate_direction')=='CNY_PER_USD' and fx_context.get('historical_available_at_verified') is False,'Explicit official direction and unknown availability')
    require(type(fx_context.get('limitations')) is list and {'CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX'}<=set(fx_context['limitations']),'Original FX timing/vintage restrictions required')
    require(type(fx_context.get('page_release_label')) is str and fx_context['page_release_label'],'Current vintage release label required')
    fx_raw_reference=fx_context['source_references']['china_history']['raw'];reference(fx_raw_reference)
    fx_values=[];valid_indexes=[]
    for i,row in enumerate(fx_rows):
        require(type(row) is dict and row.get('historical_available_at') is None,'FX available_at must remain unknown')
        reference(row['source_reference'])
        require(row['source_reference']['path']==fx_raw_reference['path'] and row['source_reference']['sha256']==fx_raw_reference['sha256'],'FX row/raw source differs')
        if row['status']=='REPORTED_RATE':
            value=number(row['rate_decimal']);require(number(row['rate_literal'])==value,'FX decimal/literal differs');valid_indexes.append(i)
        elif row['status']=='NOT_AVAILABLE_ND':
            require(row['rate_decimal'] is None and row['rate_literal']=='ND','ND must preserve null and literal');value=None
        else:raise ValueError('Unknown FX observation status')
        fx_values.append(value)
    navdates=[r['date'] for r in nav_rows];fxdates=[r['date'] for r in fx_rows];validdates=[fxdates[i] for i in valid_indexes];bydate={d:i for i,d in enumerate(fxdates)}
    def observation(index,session):
        if index is None:return None
        return dict(date=fxdates[index],lag_calendar_days=(date.fromisoformat(session)-date.fromisoformat(fxdates[index])).days,original_row_index=index,original_row=deepcopy(fx_rows[index]),rate_exact=None if fx_values[index] is None else str(fx_values[index]),historical_available_at=None)
    def aligned_fx(session):
        same=bydate.get(session);j=bisect_right(validdates,session)-1;back=valid_indexes[j] if j>=0 else None
        lower=fxdates[back] if back is not None else ''
        skipped=[dict(original_row_index=i,original_row=deepcopy(r)) for i,r in enumerate(fx_rows) if lower<r['date']<=session and r['status']=='NOT_AVAILABLE_ND']
        return dict(same_date=observation(same,session),backward_valid=observation(back,session),skipped_nd_rows=skipped),same,back
    rows=[]
    for session in session_dates:
        ni=bisect_right(navdates,session)-1;ni=None if ni<0 else ni
        nav=None if ni is None else dict(date=navdates[ni],lag_calendar_days=(date.fromisoformat(session)-date.fromisoformat(navdates[ni])).days,original_row_index=ni,original_row=deepcopy(nav_rows[ni]),nav_cny_exact=str(nav_values[ni]),available_at=None)
        fx,same,back=aligned_fx(session)
        nav_date_fx=None if ni is None else aligned_fx(navdates[ni])[0]
        conversions={}
        for mode,index in zip(MODES,(same,back)):
            rate=None if index is None else fx_values[index]
            reason='NO_PRIOR_NAV_OBSERVATION' if ni is None else ('NO_SAME_SESSION_FX_ROW' if mode==MODES[0] and index is None else 'SAME_SESSION_FX_ND' if mode==MODES[0] and rate is None else 'NO_PRIOR_VALID_FX_OBSERVATION' if rate is None else None)
            value=None if reason else nav_values[ni]/rate
            conversions[mode]=dict(status='MISSING_ALIGNMENT_INPUT' if reason else 'CONDITIONAL_NAV_USD_OBSERVATION',reason=reason,nav_usd_exact=None if value is None else str(value),nav_usd_decimal=None if value is None else display(value),nav_date=None if ni is None else navdates[ni],fx_date=None if index is None else fxdates[index],fx_original_row_index=index,nav_original_row_index=ni,denominator_basis='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX')
        rows.append(dict(session=session,nav_observation=nav,session_fx=fx,nav_date_fx_diagnostic_only=nav_date_fx,nav_date_fx_used_for_conversion=False,conversions=conversions))
    result=dict(schema=SCHEMA,status='CONDITIONAL_HISTORICAL_CONVERSION_ONLY',session_dates=deepcopy(session_dates),rows=rows,modes=list(MODES),nav_rows_preserved=deepcopy(nav_rows),fx_rows_preserved=deepcopy(fx_rows),nav_reference=deepcopy(nav_reference),fx_reference=deepcopy(fx_reference),fx_context_preserved=deepcopy(fx_context),direct_reference_hash_claims=claims,source_claims_not_full_transitive_verification=True,conversion_formula='BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD',historical_nav_currency_assumption='CNY_CONDITIONALLY_ASSUMED_NOT_INTERVAL_CERTIFIED',limitations=list(LIMITATIONS),decimal_display=dict(precision=80,rounding='ROUND_HALF_EVEN',exact_fraction_authoritative=True),mode_missing_counts={mode:sum(r['conversions'][mode]['nav_usd_exact'] is None for r in rows) for mode in MODES},**FLAGS)
    result['content_sha256']=digest(result)
    return result
