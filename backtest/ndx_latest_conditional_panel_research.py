"""Pure latest-fit panel assembly; supplied evidence assertions are not authenticated."""
import copy
import hashlib
import json
import math
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
import pandas as pd

SCOPE='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY'
FALSE=('source_assertions_authenticated','formal_input_ready','legal_training_input_admitted',
       'point_in_time_verified','execution_authorized','promotion_allowed','historical_six_input_training_ready',
       'strict_loader_validation_passed','fit_performed','winner_selected')
CHANNEL_FALSE=('source_assertions_authenticated','security_identity_verified','volume_units_independently_certified',
               'complete_actions_verified','exchange_calendar_verified','dividend_cash_flows_included',
               'legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed')

def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def text(value):
    if type(value) is not str or not value or value!=value.strip():raise ValueError('Explicit canonical text required')
    return value

def number(value):
    if type(value) not in (int,float,str,Decimal):raise ValueError('Nonboolean finite number required')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite number required')
    return result

def finite_float(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Observation overflows float64 panel')
    return result

def exact_keys(value,keys):
    if type(value) is not dict or set(value)!=set(keys):raise ValueError('Exact evidence declaration schema required')

def refs(value):
    if type(value) is not list or not value:raise ValueError('Explicit dated evidence references required')
    for item in value:
        if set(item)!={'path','sha256'} or not text(item['path']):raise ValueError('Evidence reference schema differs')
        h=item['sha256']
        if type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('SHA256 required')

def dates(values):
    if type(values) is not list or not values or values!=sorted(set(values)):raise ValueError('Ordered unique calendar required')
    if any(type(d) is not str or date.fromisoformat(d).isoformat()!=d for d in values):raise ValueError('ISO calendar required')

def coordinate(value,observed,calendar):
    keys=('security_id','issuer_id','ticker','cusip','security_class')
    exact_keys(value,(*keys,'dated_fact','scope','latest_interval_verified','provider_binding_verified','assumed_window'))
    if value['scope']!=SCOPE or value['latest_interval_verified'] is not False or value['provider_binding_verified'] is not False:raise ValueError('Explicit unverified coordinate assumption required')
    if value['assumed_window']!={'first':calendar[0],'last':calendar[-1]}:raise ValueError('Exact conditional window required')
    fact=value['dated_fact'];exact_keys(fact,(*keys,'dated_as_of','source_references'));refs(fact['source_references'])
    if any(type(value[k]) is not str or not value[k] or value[k]!=fact[k] for k in keys):raise ValueError('Dated security/class fields differ')
    if value['ticker']!=observed['ticker'] or value['issuer_id']!=observed['issuer_id']:raise ValueError('Current observed issuer differs')
    cik=value['issuer_id'].removeprefix('issuer:')
    if len(cik)!=10 or not cik.isdecimal() or value['issuer_id']!='issuer:'+cik:raise ValueError('Explicit issuer CIK required')
    if len(value['cusip'])!=9 or not value['cusip'].isalnum() or value['security_id']!='security:'+cik+':'+value['cusip']:raise ValueError('Existing dated SID/CUSIP required')
    fact_day=fact['dated_as_of'];dates([fact_day])
    if fact_day>calendar[-1]:raise ValueError('Future dated fact cannot support this assumption')
    return {k:value[k] for k in keys}

def risk(value):
    exact_keys(value,('scope','latest_interval_verified','continued_historical_label_is_explicit_assumption','historical_labels','risk_chain','source_references','source_kind'))
    if value['scope']!=SCOPE or value['latest_interval_verified'] is not False or value['continued_historical_label_is_explicit_assumption'] is not True:raise ValueError('Historical risk persistence must be explicit unverified assumption')
    candidates=value['historical_labels']
    if type(candidates) is not list or not candidates: return None
    refs(value['source_references'])
    labels={text(v) for v in candidates}
    if len(labels)!=1 or labels & {'UNKNOWN','UNCLASSIFIED'}:return None
    if value['risk_chain']!=next(iter(labels)):raise ValueError('Risk chain differs from historical evidence')
    if value['source_kind'] not in ('INDEPENDENT_REVIEWED_DATED_BUSINESS','LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION'):raise ValueError('Explicit risk evidence category required')
    return value['risk_chain']

def channel_values(value,audit,ticker,calendar,cutoff):
    exact_keys(audit,('channel_sha256','passed','source_references'))
    if value['schema']!='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1' or value['ticker']!=ticker or value['cutoff']!=cutoff or value['calendar']!=calendar:raise ValueError('Exact channel/date schema required')
    if any(value.get(k) is not False for k in CHANNEL_FALSE):raise ValueError('Channel cannot upgrade evidence authentication')
    if audit['channel_sha256']!=canonical_sha(value) or audit['passed'] is not True:raise ValueError('Declared independent audit digest differs')
    refs(audit['source_references'])
    prices=value['price_rows'];returns=value['price_returns']
    if len(prices)!=127 or len(returns)!=126 or [r['session'] for r in prices]!=calendar:raise ValueError('Complete 127/126 panel required')
    closes=[number(r['nominal_close']) for r in prices]
    if any(v<=0 for v in closes):raise ValueError('Positive closes required')
    actual=[]
    with localcontext() as ctx:
        ctx.prec=50
        for i,row in enumerate(returns):
            if row['previous_session']!=calendar[i] or row['session']!=calendar[i+1]:raise ValueError('Exact adjacent predecessor required')
            if type(row['declared_share_ratio']) is not str:raise ValueError('Original declared share ratio must be a string')
            ratio=Fraction(row['declared_share_ratio'])
            if ratio<=0:raise ValueError('Positive declared share ratio required')
            expected=closes[i+1]*Decimal(ratio.numerator)/Decimal(ratio.denominator)/closes[i]-1
            v=number(row['price_return'])
            if v<=-1 or abs(v-expected)>Decimal('1e-12'):raise ValueError('Saved adjacent price return differs')
            actual.append(finite_float(v))
        liquid=value['liquidity']
        if liquid['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN':
            if any(liquid[k] is not None for k in ('rows','median_dollar_volume_usd','numerical_threshold_passed')):raise ValueError('Blocked volume cannot have liquid values')
            return actual,[finite_float(v) for v in closes],None,'BLOCKED_VOLUME_UNIT_UNKNOWN'
        if liquid['status']!='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE' or len(liquid['rows'])!=63:raise ValueError('Complete 63-row liquidity required')
        dollars=[];volumes=[]
        for day,close,row in zip(calendar[-63:],closes[-63:],liquid['rows']):
            volume=row['raw_volume']
            if row['session']!=day or type(volume) is not int or volume<=0:raise ValueError('Actual positive volume/date required')
            expected=close*volume
            if abs(number(row['dollar_volume'])-expected)>max(Decimal('1e-8'),abs(expected)*Decimal('1e-12')):raise ValueError('Nominal dollar-volume differs')
            dollars.append(expected);volumes.append(volume)
        median=sorted(dollars)[31]
        if value['minimum_median_dollar_volume_usd']!=50000000 or type(value['minimum_median_dollar_volume_usd']) is not int:raise ValueError('Original liquidity threshold required')
        if abs(number(liquid['median_dollar_volume_usd'])-median)>max(Decimal('1e-8'),abs(median)*Decimal('1e-12')) or liquid['numerical_threshold_passed'] is not (median>=50000000):raise ValueError('Median/threshold differs')
        if median<50000000:return actual,[finite_float(v) for v in closes],None,'BELOW_ORIGINAL_LIQUIDITY_THRESHOLD'
        return actual,[finite_float(v) for v in closes],dict(volumes=volumes,dollars=[finite_float(v) for v in dollars],median=finite_float(median)),None

def panel_digest(panel):
    """Mutation checksum only, never a source-authentication certificate."""
    payload={}
    for key,value in panel.items():
        if key=='panel_content_sha256':continue
        if isinstance(value,pd.DataFrame):
            payload[key]=dict(columns=list(value.columns),index=[str(v) for v in value.index],
                index_type=type(value.index).__name__,dtypes=[str(v) for v in value.dtypes],data=value.values.tolist())
        else:payload[key]=value
    return canonical_sha(payload)

def assemble_conditional_panel(*,observed_rows,calendar,cutoff,channels,channel_audits,coordinate_assumptions,risk_assumptions):
    """Caller must authenticate each supplied source; this pure API never does IO."""
    dates(calendar)
    if len(calendar)!=127 or calendar[-1]!=cutoff:raise ValueError('Latest fit needs 127 prices ending at explicit cutoff')
    if len(observed_rows)!=101 or len({r['ticker'] for r in observed_rows})!=101:raise ValueError('Complete 101-channel observation required')
    observed={r['ticker']:r for r in observed_rows}
    for ticker,row in observed.items():
        issuer=text(row['issuer_id']);cik=issuer.removeprefix('issuer:')
        if text(ticker)!=ticker.upper() or issuer!='issuer:'+cik or len(cik)!=10 or not cik.isascii() or not cik.isdecimal():raise ValueError('Explicit current observation requires canonical CIK')
    if len({r['issuer_id'] for r in observed_rows})!=100:raise ValueError('Complete 100 observed issuer denominator required')
    if any(set(mapping)-set(observed) for mapping in (channels,channel_audits,coordinate_assumptions,risk_assumptions)):raise ValueError('Unknown provider channel')
    if set(channel_audits)!=set(channels):raise ValueError('Every supplied numeric channel needs audit assertion')
    selected=[];missing=[];values={};seen=set()
    for ticker,row in observed.items():
        reasons=[];identity=None;chain=None;numeric=None
        if ticker not in channels:reasons.append('NO_COMPLETE_CONDITIONAL_CHANNEL')
        else:
            numeric=channel_values(channels[ticker],channel_audits[ticker],ticker,calendar,cutoff)
            if numeric[3]:reasons.append(numeric[3])
        if ticker not in coordinate_assumptions:reasons.append('NO_EXPLICIT_DATED_COORDINATE_ASSUMPTION')
        else:
            identity=coordinate(coordinate_assumptions[ticker],row,calendar)
            if identity['security_id'] in seen:raise ValueError('Duplicate security ID')
            seen.add(identity['security_id'])
        if ticker not in risk_assumptions:reasons.append('NO_EXPLICIT_RESEARCH_RISK_ASSUMPTION')
        else:
            chain=risk(risk_assumptions[ticker])
            if chain is None:reasons.append('UNKNOWN_OR_CONFLICTING_RISK_CHAIN')
        included=not reasons
        missing.append(dict(ticker=ticker,observed_issuer_id=row['issuer_id'],included_in_conditional_panel=included,blocking_reasons=reasons,
            coordinate_assumption=copy.deepcopy(coordinate_assumptions.get(ticker)),risk_assumption=copy.deepcopy(risk_assumptions.get(ticker)),
            channel_audit_assertion=copy.deepcopy(channel_audits.get(ticker)),source_assertions_authenticated=False,legal_training_input_admitted=False))
        if included:
            selected.append(dict(identity,risk_chain=chain,median_dollar_volume_usd=numeric[2]['median']));values[ticker]=numeric
    columns=sorted(values);index=pd.DatetimeIndex(calendar)
    frame=lambda part,idx:pd.DataFrame({t:values[t][part] for t in columns},index=idx,dtype='float64')
    panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=SCOPE,cutoff=cutoff,
        returns=frame(0,index[1:]),nominal_close=frame(1,index),
        raw_volume=pd.DataFrame({t:values[t][2]['volumes'] for t in columns},index=index[-63:],dtype='int64'),
        dollar_volume=pd.DataFrame({t:values[t][2]['dollars'] for t in columns},index=index[-63:],dtype='float64'),
        universe=pd.DataFrame(sorted(selected,key=lambda r:r['security_id']),columns=['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd']),
        observed_provenance_and_missing=missing,observed_security_count=101,observed_issuer_count=100,
        conditional_security_count=len(selected),conditional_issuer_count=len({r['issuer_id'] for r in selected}),
        candidate_cardinality_not_fixed=True,one_security_per_issuer_per_portfolio_required=True,
        historical_evaluation_505_rows_available=False,**dict.fromkeys(FALSE,False))
    panel['panel_content_sha256']=panel_digest(panel)
    return panel

def selected_mapping(panel,security_ids):
    """Explicit arbitrary k only; no optimization, ranking, or automatic choice."""
    if panel['schema']!='LATEST_CONDITIONAL_TYPED_PANEL_V1' or panel['scope']!=SCOPE or any(panel.get(k) is not False for k in FALSE):raise ValueError('Conditional panel scope differs')
    if panel.get('panel_content_sha256')!=panel_digest(panel):raise ValueError('Conditional panel changed after assembly')
    if type(security_ids) is not list or not security_ids or len(set(security_ids))!=len(security_ids):raise ValueError('Explicit unique SID subset required')
    rows=panel['universe'].to_dict('records');by_sid={r['security_id']:r for r in rows}
    if len(by_sid)!=len(rows) or any(s not in by_sid for s in security_ids):raise ValueError('Selected SID missing or duplicate')
    selected={s:{k:by_sid[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in security_ids}
    if len({r['issuer_id'] for r in selected.values()})!=len(selected):raise ValueError('Different share classes cannot duplicate an issuer in one portfolio')
    if any(r['ticker'] not in panel['returns'].columns for r in selected.values()):raise ValueError('Selected numeric column missing')
    return selected
