"""Original-eight and NAV date/reference requirements, never price arithmetic."""
from bisect import bisect_right
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math

SCHEMA='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1'
TICKERS={'NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'}
FIELDS={'open','high','low','close','volume','adjclose'}
FLAGS=dict.fromkeys(('source_bytes_authenticated','historical_identity_verified','provider_binding_verified',
    'historical_currency_interval_verified','nav_publication_time_verified','fx_alignment_verified',
    'historical_risk_interval_verified','point_in_time_verified','benchmark_qualified','evaluation_executed',
    'prices_computed','returns_computed','account_executed','fx_computed','fit_performed','weights_reoptimized',
    'weights_normalized','holdings_converted','promotion_allowed','execution_authorized',
    'legal_training_input_admitted','future_independent_oos_recovered','same_cashflow_verified',
    'execution_rules_equivalent','fee_equivalence_verified','complete_corporate_actions_verified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date required')
    return value


def date_list(values):
    require(type(values) is list and 0<len(values)<=10000,'Bounded nonempty dates')
    for value in values:day(value)
    require(values==sorted(set(values)),'Dates must already be unique and ascending')


def prepare_benchmark_requirements(*,reference_calendar,original_control,stock_metadata,nav_metadata,fx_metadata):
    """253 dates; original eight ordered coordinates; saved NAV dates only.

    NAV row_index counts original CSV data rows from zero, excluding its header.
    Missing previous NAV remains None. Row-date linkage is not publication time.
    Input extras (including full original documents) are preserved unmodified.
    """
    source_hash_claims={}
    def reference(ref):
        require(type(ref) is dict and {'path','sha256'}<=set(ref)<={'path','sha256','json_pointer'},'Explicit source reference')
        path=ref['path'];sha=ref['sha256']
        require(type(path) is str and path and path==path.strip(),'Canonical source path')
        require(type(sha) is str and len(sha)==64 and all(c in '0123456789abcdef' for c in sha),'Canonical SHA')
        if 'json_pointer' in ref:require(type(ref['json_pointer']) is str and ref['json_pointer'].startswith('/'),'Explicit JSON pointer')
        require(path not in source_hash_claims or source_hash_claims[path]==sha,'Conflicting reference hashes')
        source_hash_claims[path]=sha
    require(type(reference_calendar) is dict and reference_calendar.get('ticker')=='AAPL','Explicit AAPL provider calendar')
    reference(reference_calendar['source_reference']);calendar=reference_calendar['dates'];date_list(calendar)
    require(len(calendar)==253 and all(date.fromisoformat(d).weekday()<5 for d in calendar),'Exactly253 provider weekday observations')
    require(type(original_control) is dict,'Original control mapping');reference(original_control['source_reference'])
    securities=original_control['securities'];require(type(securities) is list and len(securities)==8,'All eight original rows in original order')
    require(all(type(r) is dict and all(type(r.get(k)) is str and r[k] for k in ('ticker','security_id','issuer_id','risk_chain')) for r in securities),'Full original coordinates and risk')
    require({r['ticker'] for r in securities}==TICKERS and len({r['security_id'] for r in securities})==8 and len({r['issuer_id'] for r in securities})==8,'Eight unique original ticker/SID/issuer coordinates')
    total=Fraction(0)
    for security in securities:
        value=security['target_weight'];require(type(value) in (int,float,str),'Finite nonboolean original target')
        try:weight=Fraction(str(value))
        except (ValueError,ZeroDivisionError):raise ValueError('Finite original target required') from None
        require(weight>=0 and weight<=1,'Nonnegative unit original weight');total+=weight
    require(total>0,'Positive original target mass; no normalization')
    require(next(r for r in securities if r['ticker']=='TSM')['security_id']=='security:incumbent_overlay:TSM','Preserve original TSM overlay SID')
    require(type(stock_metadata) is dict and set(stock_metadata)==TICKERS,'All and only eight channel metadata records')
    stocks=[]
    for index,security in enumerate(securities):
        ticker=security['ticker'];item=stock_metadata[ticker]
        require(type(item) is dict and item['security_id']==security['security_id'],'Stock metadata SID mismatch')
        for key in ('raw_reference','receipt_reference','observation_reference'):reference(item[key])
        receipt=item['receipt_binding'];require(type(receipt) is dict and receipt.get('ticker')==ticker and digest(receipt['raw_reference'])==digest(item['raw_reference']),'Receipt/raw/ticker binding differs')
        rows=item['observation_rows'];require(type(rows) is list and 0<len(rows)<=10000,'Bounded saved observations')
        for row in rows:
            require(type(row) is dict and {'session','missing_fields'}<=set(row),'Saved observation metadata')
            fields=row['missing_fields'];require(type(fields) is list and all(type(f) is str and f in FIELDS for f in fields) and len(set(fields))==len(fields),'Explicit saved missing fields')
        date_list([row['session'] for row in rows]);by={row['session']:(i,row) for i,row in enumerate(rows)}
        for role in ('identity_evidence','risk_evidence'):
            require(type(item[role]) is list,'Explicit possibly empty evidence list')
            for ref in item[role]:reference(ref)
        requirements=[]
        for d in calendar:
            match=by.get(d);requirements.append(dict(session=d,observation_metadata_row_index=None if match is None else match[0],
                observation_reference=deepcopy(item['observation_reference']),observation_present=match is not None,
                saved_missing_fields=None if match is None else deepcopy(match[1]['missing_fields']),
                raw_reference=deepcopy(item['raw_reference']),receipt_reference=deepcopy(item['receipt_reference']),
                nominal_open_close_projection_required=True,nominal_prices_verified=False))
        stocks.append(dict(original_index=index,original_security=deepcopy(security),control_only=ticker=='TSM',
            tsm_not_added_to_candidate_pool=ticker=='TSM',all253_dates_retained=True,requirements=requirements,
            missing_observation_dates=[r['session'] for r in requirements if not r['observation_present']],
            saved_missing_field_dates=[r['session'] for r in requirements if r['saved_missing_fields']],
            missing_identity_evidence=not item['identity_evidence'],missing_risk_evidence=not item['risk_evidence'],
            identity_and_risk_window_extension_not_automatic=True,**FLAGS))
    require(type(nav_metadata) is dict and nav_metadata['publication_time_known'] is False and nav_metadata['selected_value_column']=='Close','Saved Close/UnitNav convention and unknown publication')
    for key in ('source_reference','manifest_reference','snapshot_reference'):reference(nav_metadata[key])
    navrows=nav_metadata['rows'];require(type(navrows) is list and 0<len(navrows)<=10000,'Full bounded saved NAV date rows')
    for index,row in enumerate(navrows):
        require(type(row) is dict and {'date','row_index','source_reference'}<=set(row),'Saved NAV row coordinates')
        require(type(row['row_index']) is int and row['row_index']==index,'Original contiguous NAV data row indexes, no header')
        reference(row['source_reference']);require(digest(row['source_reference'])==digest(nav_metadata['source_reference']),'NAV row must bind exact CSV source')
    navdates=[row['date'] for row in navrows];date_list(navdates)
    mapped=[]
    for d in calendar:
        index=bisect_right(navdates,d)-1
        if index<0:
            mapped.append(dict(session=d,status='NO_PRIOR_NAV_OBSERVATION',nav_date=None,mapped_row_reference=None,same_date=False,
                lag_calendar_days=None,available_at=None,publication_time_known=False,future_observation_used=False))
        else:
            navday=navdates[index];mapped.append(dict(session=d,status='SAVED_OBSERVATION_DATE_MAPPING_ONLY',nav_date=navday,
                mapped_row_reference=dict(deepcopy(nav_metadata['source_reference']),row_index=navrows[index]['row_index'],column='Close'),
                same_date=navday==d,lag_calendar_days=(date.fromisoformat(d)-date.fromisoformat(navday)).days,
                available_at=None,publication_time_known=False,future_observation_used=False))
    require(type(fx_metadata) is dict and fx_metadata.get('bound') is False and fx_metadata.get('source_reference') is None,'This requirements version requires explicitly unbound FX')
    result=dict(schema=SCHEMA,status='BENCHMARK_INPUT_REQUIREMENTS_ONLY_NOT_EVALUATED',historical_retrospective_only=True,
        reference_calendar=deepcopy(reference_calendar),original_control_preserved=deepcopy(original_control),stock_metadata_preserved=deepcopy(stock_metadata),
        nav_metadata_preserved=deepcopy(nav_metadata),fx_metadata_preserved=deepcopy(fx_metadata),
        original_target_weight_sum_exact=str(total),original_control_order=[r['ticker'] for r in securities],stock_requirements=stocks,
        stock_denominator=8,stock_date_requirement_count=8*253,nav_date_requirement_count=253,nav_date_mappings=mapped,
        nav_same_date_count=sum(r['same_date'] for r in mapped),nav_missing_same_date_sessions=[r['session'] for r in mapped if not r['same_date']],
        nav_without_prior_observation_sessions=[r['session'] for r in mapped if r['mapped_row_reference'] is None],
        training_return_end_dates=calendar[1:127],training_freeze_close_date=calendar[126],evaluation_initial_close_date=calendar[126],evaluation_return_end_dates=calendar[127:],
        nav_alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_OR_TRADE_AVAILABILITY',
        benchmark_objective_semantics='ORIGINAL_COMPONENTWISE_ABSOLUTE_DISTANCE_CONTRACT_NOT_REPLACED_BY_ONE_SIDED_GATE',
        outstanding_contracts=['NEW_WINDOW_NOMINAL_OHLC_PROJECTION_AND_INDEPENDENT_ARITHMETIC','HISTORICAL_IDENTITY_RISK_AND_ACTION_SCOPE',
            'NAV_PUBLICATION_AND_SUBSCRIPTION_TIMING','HISTORICAL_CURRENCY_AND_FX_DIRECTION_TIMESTAMP_AVAILABILITY',
            'EXPLICIT_INITIAL_CAPITAL_CASHFLOWS_EXECUTION_FEES_DIVIDENDS'],
        direct_reference_hash_claims=source_hash_claims,direct_claims_are_not_full_transitive_source_closure=True,**FLAGS)
    result['content_sha256']=digest(result)
    return result
