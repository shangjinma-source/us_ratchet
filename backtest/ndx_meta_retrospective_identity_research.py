"""Bounded META retrospective accounting: provider channel and daily ticker differ."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from backtest import ndx_dynamic_frozen_execution_research as engine
from backtest import ndx_identity_raw_fact_research as facts
from backtest import ndx_nominal_quote_reconstruction_research as nominal
from backtest import ndx_split_neutral_price_return_research as neutral

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = {str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
          for module in (engine, facts, nominal, neutral)}
LOADED[str(SOURCE)] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND = {
    'data/cache/research/meta_historical_price_source_probe_20260912_v1/manifest.json':
        'e1ec6f55875ce1033843ff14be57d1ad9a11e488f6074982ec7386eccb94b83a',
    'data/cache/research/identity_public_source_probe_20260912_v1/extracted_facts_20260912.json':
        'dfe62747ebce89e8545e6d89d1435803663b3cf8a153ba205be66ba8b513c4e5',
    'data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json':
        'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'}
SID = 'security:0001326801:30303M102'
ISSUER = 'issuer:0001326801'
INTERNAL = 'ACCOUNTING_META_30303M102'


def merge(sources, incoming):
    for path, digest in incoming.items():
        if path in sources and sources[path] != digest:
            raise ValueError('Conflicting META accounting source')
        sources[path] = digest


def build_bound_projection():
    sources = dict(LOADED)
    merge(sources, {str(ROOT / path): digest for path, digest in BOUND.items()})
    nominal.verify(sources)
    capture, fact_report, coverage = [json.loads((ROOT / path).read_bytes()) for path in BOUND]
    for report in (capture, fact_report, coverage):
        merge(sources, report['source_hashes'])
    nominal.verify(sources)
    notice, = [row for row in fact_report['probe_outcomes'] if row['name'] == 'nasdaq_meta_20220603_rename_notice']
    raw_notice = Path(notice['response_path']).read_bytes()
    if hashlib.sha256(raw_notice).hexdigest() != notice['response_sha256']:
        raise ValueError('Nasdaq notice changed')
    event = facts.extract_nasdaq_meta_notice(raw_notice)
    event['received_at_utc'] = notice['received_at_utc']
    if event != fact_report['nasdaq_meta_event']:
        raise ValueError('Bound notice facts differ from actual raw extraction')
    probe, = capture['probes']
    raw_path = Path(probe['response_path']).resolve()
    merge(sources, {str(raw_path): probe['response_sha256']})
    nominal.verify(sources)
    raw = raw_path.read_bytes()
    if len(raw) != probe['response_bytes'] or probe['http_status'] != 200 or probe['transport_success'] is not True:
        raise ValueError('Complete successful META raw price capture required')
    result, = json.loads(raw)['chart']['result']
    calendar = [datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in result['timestamp']]
    quote = nominal.reconstruct_nominal_quote_ticker(raw=raw,ticker='META',calendar=calendar,
        request=probe['request'],received_at_utc=probe['received_at_utc'],quote_field_basis=nominal.BASIS)
    if quote['provider_split_events']:
        raise ValueError('This dedicated META no-returned-split experiment requires separate new split adjudication')
    local_rows = [row for date in coverage['dates'] for row in date['candidates'] if row['cusip']=='30303M102']
    if not local_rows or any(row['security_id']!=SID or row['issuer_id']!=ISSUER or row['ticker']!='META' for row in local_rows):
        raise ValueError('Local stable META/CUSIP coordinate conflicts with scoped source')
    rows = []
    for row in quote['rows']:
        actual = 'FB' if row['session'] < event['fact_effective_date'] else 'META'
        rows.append(dict(session=row['session'],security_id=SID,issuer_id=ISSUER,ticker=actual,
            provider_request_symbol='META',internal_column=INTERNAL,
            open=row['nominal_open'],close=row['nominal_close'],declared_share_ratio=1,
            split_factor=row['split_factor']))
    return_payload=dict(schema='ndx_split_neutral_return_input_v1',basis='SPLIT_ONLY_ADJUSTED_CLOSE',
        event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS',dividend_adjustment_in_close=False,
        calendar=calendar,securities={SID:dict(issuer_id=ISSUER)},
        rows=[{key:row[key] for key in ('security_id','issuer_id','ticker','session','close')} for row in rows],
        daily_share_ratios=[dict(security_id=SID,session=day,new_shares=1,old_shares=1) for day in calendar])
    price_returns=neutral.calculate_split_neutral_price_returns(return_payload)
    received_day=datetime.fromisoformat(probe['received_at_utc'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    unfinalized=[day for day in calendar if day>=received_day]
    completed_returns=[row for row in price_returns['rows'] if row['session']<received_day]
    price_returns.update(raw_observed_numerics_include_unfinalized_bar=bool(unfinalized),
        unfinalized_sessions=unfinalized,completed_session_rule='STRICTLY_BEFORE_RECEIVED_NEW_YORK_DATE',
        completed_return_count=len(completed_returns),unfinalized_rows_training_use_allowed=False)
    return_by_date={row['session']:row for row in completed_returns}
    coverage_rows=[]
    training_inputs=[]
    for date in coverage['dates']:
        digest=date['old_context_sha256']
        path, = [Path(path) for path, value in coverage['source_hashes'].items() if value==digest and Path(path).name=='context.json']
        context=json.loads(path.read_bytes())
        days=[value['timestamp'][:10] for value in context['prepared_inputs']['returns']['payload']['mapping']['index']['items']]
        missing=sorted(set(days)-set(calendar))
        if days!=sorted(set(days)) or missing or any(day not in return_by_date for day in days):
            raise ValueError('META raw lacks original full training dates and prior close')
        previous_dates={day:calendar[calendar.index(day)-1] for day in days}
        selected_returns=[return_by_date[day] for day in days]
        for row in selected_returns:
            neutral.positive(row['previous_close'])
            neutral.positive(row['close'])
            if row['previous_session']!=previous_dates[row['session']]:
                raise ValueError('Return predecessor differs from adjacent observed provider session')
        research_input=dict(schema='ndx_meta_context_research_return_input_v1',coordinate=date['coordinate'],
            original_context_path=str(path),original_context_sha256=digest,security_id=SID,issuer_id=ISSUER,
            return_calendar=days,rows=selected_returns,original_context_rewritten=False,
            old_training_reuse_authorized=False,point_in_time_verified=False,promotion_allowed=False)
        serialized=json.dumps(research_input,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        training_inputs.append(dict(input=research_input,input_sha256=hashlib.sha256(serialized).hexdigest(),
            digest_encoding='UTF8_JSON_SORTED_COMPACT_DEFAULT_ASCII_NO_NAN'))
        coverage_rows.append(dict(coordinate=date['coordinate'],context_sha256=digest,
            full_training_return_date_count=len(days),missing_dates=missing,
            adjacent_observed_previous_close_count=len(previous_dates),previous_date_by_return_date=previous_dates,
            observed_calendar_exchange_completeness_independently_verified=False,
            earlier_close_available=True,pre_rename_FB_session_count=sum(day<event['fact_effective_date'] for day in days)))
    nominal.verify(sources)
    return dict(schema='ndx_meta_retrospective_projection_v1',scope='CONDITIONAL_RETROSPECTIVE_ACCOUNTING_ONLY',
        rows=rows,calendar=calendar,row_count=len(rows),security_id=SID,issuer_id=ISSUER,
        rename_event=event,full_training_date_coverage=coverage_rows,source_hashes=sources,
        split_neutral_return_input=return_payload,split_neutral_price_returns=price_returns,
        context_research_return_inputs=training_inputs,
        completed_session_price_returns=completed_returns,unfinalized_sessions=unfinalized,
        received_new_york_date=received_day,observed_row_count_is_not_completed_daily_bar_count=True,
        price_received_at_utc=probe['received_at_utc'],provider_request_symbol='META',
        issuer_coordinate_source='BOUND_LOCAL_COVERAGE_MAPPING_NOT_PRIMARY_CIK_ADJUDICATION',
        price_basis='CONDITIONAL_SPLIT_ONLY_QUOTE_OPEN_CLOSE_NOT_DIVIDEND_TOTAL_RETURN',
        strict_bridge_not_invoked_reason='Provider capture received in 2026 cannot truthfully meet first-use evidence cutoff in 2022.',
        provider_event_denominator='ALL_RETURNED_DAILY_SESSIONS_AND_RETURNED_EVENTS_THROUGH_REQUEST_RECEPTION_DATE',
        daily_ticker_projection_from_dated_notice=True, old_FB_cache_read_or_stitched=False,
        split_and_rename_are_separate=True,source_authenticity_adjudicated=False,
        historical_provider_binding_certified=False,primary_issuer_cik_adjudicated=False,
        continuous_identity_interval_certified=False,strategy_information_pit_verified=False,
        price_event_completeness_independently_certified=False,point_in_time_verified=False,promotion_allowed=False)


def simulate_bound_meta(*,projection,schedule,calendar):
    """Dedicated scoped adapter; rebuild prices/facts instead of trusting caller flags."""
    if projection != build_bound_projection():
        raise ValueError('META projection differs from independently rebuilt bound facts')
    sources=dict(projection['source_hashes'])
    by_date={row['session']:row for row in projection['rows']}
    if calendar!=sorted(set(calendar)) or not calendar or not set(calendar)<=set(by_date):
        raise ValueError('Explicit actual META session subset required')
    if set(calendar)&set(projection['unfinalized_sessions']):
        raise ValueError('Unfinalized provider bars cannot enter completed accounting sessions')
    expected=[day for day in projection['calendar'] if calendar[0]<=day<=calendar[-1]]
    if calendar!=expected:
        raise ValueError('Actual contiguous provider sessions cannot be dropped')
    translated=deepcopy(schedule)
    for row in translated:
        day=row['decision_date'];execution=row['execution_date']
        if (day not in calendar or execution not in calendar or calendar.index(execution)!=calendar.index(day)+1
                or set(row['targets'])!={SID}):
            raise ValueError('Complete one-security next-session accounting schedule required')
        target=row['targets'][SID]
        if target['issuer_id']!=ISSUER or target['ticker']!=by_date[day]['ticker']:
            raise ValueError('Decision SID/issuer/daily actual ticker conflicts with dated event')
        target['ticker']=INTERNAL
    index=pd.DatetimeIndex(calendar)
    arguments=dict(opens=pd.DataFrame({INTERNAL:[by_date[day]['open'] for day in calendar]},index=index),
        closes=pd.DataFrame({INTERNAL:[by_date[day]['close'] for day in calendar]},index=index),
        schedule=translated,risk_chains_by_decision={row['decision_date']:{SID:'platform_advertising'} for row in schedule},
        corporate_actions=[],identity_events=(),initial_cash_usd=25000.,minimum_cash_buffer_usd=100.,
        transaction_cost_bps=10.,valuation_end_date=calendar[-1],max_single_weight=1.,min_single_weight=.05,
        top_weight_cap=1.,minimum_effective_n_ratio=1.,risk_chain_top1_cap=1.)
    engine._check_sources()
    execution=engine.simulate_dynamic_frozen_execution_research(**arguments)
    merge(sources,execution['source_hashes'])
    numeric=deepcopy(execution)
    def labels(plan):
        if plan is None:return
        for sid,target in plan['targets'].items():
            target['internal_price_column']=target['ticker']
            target['ticker']=by_date[plan['decision_date']]['ticker']
    for row in execution['decisions']:labels(row)
    for row in execution['executions']:
        if 'plan' in row:labels(row['plan'])
        row['tickers_by_security']={sid:by_date[row['session']]['ticker'] for sid in row.get('prices',{})}
    for row in execution['trades']:
        row['internal_price_column']=row['ticker'];row['ticker']=by_date[row['session']]['ticker']
    for row in execution['daily']:
        row['internal_price_columns']=deepcopy(row['tickers'])
        row['tickers']={sid:by_date[row['session']]['ticker'] for sid in row['shares']}
    nominal.verify(sources)
    return dict(schema='ndx_meta_retrospective_accounting_v1',execution=execution,
        untranslated_numeric_execution=numeric,source_hashes=sources,
        rename_is_accounting_action=False,declared_corporate_action_count=0,
        scenario_risk_limits='ONE_SECURITY_ACCOUNTING_MECHANICS_ONLY_NOT_PORTFOLIO_OPTIMIZATION_CONTRACT',
        initial_cash_usd=25000.,minimum_cash_buffer_usd=100.,transaction_cost_bps=10.,
        fixed_schedule_changed=False,old_FB_cache_read_or_stitched=False,
        original_frozen_ticker_change_guard_retained=True,historical_provider_binding_certified=False,
        point_in_time_verified=False,promotion_allowed=False)
