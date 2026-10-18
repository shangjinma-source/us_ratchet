"""Saved-metadata requirements only: no price arithmetic, fitting, or source IO."""
from copy import deepcopy
from datetime import date
import hashlib
import json

SCHEMA='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1'
WINDOW={'first':'2026-03-20','last':'2026-09-21'}
CONTRACT=dict(decision_cutoff='2026-09-21',fit_return_rows=126,evaluation_return_rows=126,
              rolling_step_rows=21,price_window_lengths=[253,505])
FIELDS={'open','high','low','close','volume','adjclose'}
FLAGS=dict.fromkeys(('source_bytes_authenticated','reference_calendar_exchange_certified','prices_computed',
    'returns_computed','fit_performed','saved_final_cutoff_weights_reused_for_earlier_freeze',
    'identity_interval_verified','risk_interval_verified','complete_corporate_actions_verified',
    'provider_binding_verified','volume_unit_verified','point_in_time_verified','timely_availability_verified',
    'legal_training_input_admitted','historical_six_input_training_ready','formal_dual_benchmark_ready',
    'promotion_allowed','execution_authorized','future_independent_oos_recovered','benchmark_qualified','evaluation_executed'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def canonical_date(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date required')
    return value


def sha(value):
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Canonical SHA required')


def reference(value):
    require(type(value) is dict and {'path','sha256'}<=set(value)<= {'path','sha256','json_pointer'},'Explicit saved reference required')
    require(type(value['path']) is str and bool(value['path']) and value['path']==value['path'].strip(),'Explicit reference path')
    sha(value['sha256'])
    if 'json_pointer' in value:require(type(value['json_pointer']) is str and value['json_pointer'].startswith('/'),'Explicit JSON pointer')


def _dates(values):
    require(type(values) is list and bool(values) and len(values)<=10000,'Bounded nonempty date list')
    for value in values:canonical_date(value)
    require(values==sorted(set(values)),'Complete unique ascending dates; no implicit sort/dedup')


def _required_window(days,start,index):
    prices=days[start:start+253];training=prices[:127];evaluation=prices[126:]
    require(len(prices)==253,'Complete unsqueezed253-date window')
    return dict(window_index=index,start_price_index=start,required_price_dates=prices,
        training_price_dates=training,training_return_end_dates=training[1:],training_freeze_close_date=training[-1],
        evaluation_initial_close_date=evaluation[0],evaluation_price_dates=evaluation,
        evaluation_return_end_dates=evaluation[1:],
        training_return_predecessors=[dict(session=b,previous_session=a) for a,b in zip(training,training[1:])],
        evaluation_return_predecessors=[dict(session=b,previous_session=a) for a,b in zip(evaluation,evaluation[1:])],
        fit_return_count=126,evaluation_return_count=126,
        final_cutoff_fitted_targets_may_be_reused=False,historical_retrospective_only=True)


def _requirements(item,window):
    observations={row['session']:row for row in item['observation_rows']};days=window['required_price_dates']
    missing=[d for d in days if d not in observations]
    fields=[dict(session=d,missing_fields=deepcopy(observations[d]['missing_fields'])) for d in days
            if d in observations and observations[d]['missing_fields']]
    floor=item['event_policy_bridge']['regular_floor']
    forbidden=[d for d in days if floor is not None and d<floor]
    outside=[d for d in days if not WINDOW['first']<=d<=WINDOW['last']]
    close_missing=set(missing)|{row['session'] for row in fields if 'close' in row['missing_fields']}
    affected={}
    for role in ('training','evaluation'):
        pairs=window[role+'_return_predecessors']
        affected[role+'_return_pairs_with_missing_close']=[deepcopy(pair) for pair in pairs if pair['session'] in close_missing or pair['previous_session'] in close_missing]
        affected[role+'_return_pairs_crossing_or_before_partition']=[deepcopy(pair) for pair in pairs if floor is not None and pair['previous_session']<floor]
    return dict(window_index=window['window_index'],required_price_date_count=253,
        missing_price_dates=missing,saved_missing_field_rows=fields,regular_floor=floor,
        forbidden_pre_partition_price_dates=forbidden,identity_assumption_uncovered_price_dates=outside,
        risk_assumption_extension_required=bool(outside),identity_assumption_extension_required=bool(outside),
        saved_date_and_field_metadata_complete=not missing and not fields,
        saved_close_metadata_complete=not close_missing,partition_scope_complete=not forbidden,
        status='REQUIREMENT_GAPS_REMAIN' if missing or fields or forbidden or outside else 'METADATA_PRESENT_SEMANTICS_STILL_UNVERIFIED',
        action_policy_revalidation_for_window_required=True,dividend_and_cashflow_contract_required=True,
        same_window_incumbent_and_nav_bindings_required=True,historical_retrospective_only=True,
        **affected,**FLAGS)


def prepare_history_requirements(*,universe,observed_provenance_and_missing,reference_calendar,ticker_observations,window_contract):
    """Compare253/505 price requirements, preserving every SID and date gap.

    `reference_calendar` is {ticker:'AAPL', dates:list, source_reference:ref}.
    Each ticker record contains observation_rows [{session,missing_fields}],
    raw_reference, receipt_reference, decoded_sha256, bridge_reference,
    event_policy_bridge (regular_floor required), identity_assumed_window.
    Additional original record fields are preserved, not treated as authority.
    """
    require(type(window_contract) is dict and digest(window_contract)==digest(CONTRACT),'Exact original window lengths/cutoff; booleans forbidden')
    require(type(universe) is list and len(universe)==77,'Complete77 universe, no filtering')
    require(all(type(r) is dict and all(type(r.get(k)) is str and r[k] for k in ('security_id','issuer_id','ticker')) for r in universe),'Explicit SID/issuer/ticker')
    require(len({r['security_id'] for r in universe})==77 and len({r['ticker'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76,'Exact77SID/76issuer coordinates')
    require(type(observed_provenance_and_missing) is list and len(observed_provenance_and_missing)==101,'Complete101 provenance')
    require(all(type(r) is dict and type(r.get('ticker')) is str for r in observed_provenance_and_missing) and
        len({r['ticker'] for r in observed_provenance_and_missing})==101 and
        {r['ticker'] for r in universe}<={r['ticker'] for r in observed_provenance_and_missing},'Unique101 provenance must contain all77 tickers')
    require(type(reference_calendar) is dict and set(reference_calendar)=={'ticker','dates','source_reference'} and reference_calendar['ticker']=='AAPL','Explicit AAPL provider reference')
    reference(reference_calendar['source_reference']);dates=reference_calendar['dates'];_dates(dates)
    require(dates[-1]==window_contract['decision_cutoff'] and all(date.fromisoformat(d).weekday()<5 for d in dates),'Calendar must end exactly at cutoff with provider weekdays')
    require(type(ticker_observations) is dict and set(ticker_observations)=={r['ticker'] for r in universe},'Every and only77 ticker metadata rows')
    for ticker,item in ticker_observations.items():
        require(type(item) is dict and {'observation_rows','raw_reference','receipt_reference','decoded_sha256','bridge_reference','event_policy_bridge','identity_assumed_window'}<=set(item),'Explicit saved observation evidence')
        for key in ('raw_reference','receipt_reference','bridge_reference'):reference(item[key])
        sha(item['decoded_sha256']);require(digest(item['identity_assumed_window'])==digest(WINDOW),'Original identity assumption must not be extended silently')
        require(type(item['event_policy_bridge']) is dict and 'regular_floor' in item['event_policy_bridge'],'Saved partition policy required')
        floor=item['event_policy_bridge']['regular_floor']
        if floor is not None:canonical_date(floor)
        rows=item['observation_rows'];require(type(rows) is list and 0<len(rows)<=10000,'Bounded saved observations')
        for row in rows:
            require(type(row) is dict and {'session','missing_fields'}<=set(row),'Saved row metadata required')
            fields=row['missing_fields'];require(type(fields) is list and len(fields)==len(set(fields)) and all(type(f) is str and f in FIELDS for f in fields),'Explicit known missing fields, no bools')
        _dates([row['session'] for row in rows])
    require(dates==[row['session'] for row in ticker_observations['AAPL']['observation_rows'] if row['session']<=window_contract['decision_cutoff']],
        'Reference calendar must preserve complete saved AAPL date sequence, not filtered values')
    scenarios=[]
    for length in window_contract['price_window_lengths']:
        enough=len(dates)>=length;selected=dates[-length:] if enough else []
        windows=[_required_window(selected,start,i) for i,start in enumerate(range(0,length-252,21))] if enough else []
        rows=[]
        for security in universe:
            item=ticker_observations[security['ticker']]
            rows.append(dict(coordinate=deepcopy(security),requirements=[_requirements(item,w) for w in windows],
                status='REFERENCE_CALENDAR_TOO_SHORT' if not enough else 'WINDOW_REQUIREMENTS_RECORDED',
                reference_price_date_deficit=max(length-len(dates),0)))
        scenarios.append(dict(price_window_length=length,expected_adjacent_return_count=length-1,
            reference_calendar_complete=enough,required_reference_price_dates=selected,
            expected_rolling_window_count=1 if length==253 else 13,constructed_window_count=len(windows),
            rolling_step_return_rows=21,windows=windows,security_rows=rows,security_denominator=77,
            all_security_windows_retained=True,dates_intersected_or_compressed=False,
            desired_505_is_hard_admission_threshold=False,
            metadata_only=True,historical_retrospective_only=True,**FLAGS))
    result=dict(schema=SCHEMA,status='HISTORICAL_REQUIREMENTS_ONLY_NOT_TRAINING_ADMISSION',
        window_contract=deepcopy(window_contract),original_identity_assumed_window=deepcopy(WINDOW),
        universe=deepcopy(universe),observed_provenance_and_missing=deepcopy(observed_provenance_and_missing),
        reference_calendar=deepcopy(reference_calendar),ticker_observations_preserved=deepcopy(ticker_observations),
        scenarios=scenarios,security_denominator=77,issuer_denominator=76,observed_provenance_denominator=101,
        historical_retrospective_only=True,independent_future_oos=False,
        missing_timestamps_are_unknown_not_automatically_late=True,
        benchmark_objective_semantics='ORIGINAL_COMPONENTWISE_ABSOLUTE_DISTANCE_CONTRACT_NOT_REPLACED_BY_ONE_SIDED_GATE',
        benchmark_gaps=['NAV_AVAILABILITY_TIMESTAMPS','CURRENCY_AND_FX','SAME_CASHFLOW','EXECUTION_RULES','COMMON_OBSERVATION_CALENDAR'],
        source_metadata_are_caller_supplied_not_reauthenticated=True,
        next_required_contracts=['EXPLICIT_HISTORICAL_IDENTITY_AND_RISK_SCOPE','WINDOW_SPECIFIC_ACTION_AND_PRICE_UNITS',
            'INDEPENDENT_LONG_WINDOW_ARITHMETIC_READBACK','SAME_WINDOW_INCUMBENT_NAV_FLOWS_FEES_AND_AVAILABILITY'],**FLAGS)
    result['content_sha256']=digest(result)
    return result
