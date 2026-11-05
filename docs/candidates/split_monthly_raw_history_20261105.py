"""Conditional raw-close normalization into the existing monthly risk engine.

Caller-reviewed basis is evidence input, never inferred from adjclose. Dividend
events are checked and retained, not added to stock-price risk or account cash.
The caller still authenticates issuer identity, calendar, basis and action coverage.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import timestamp
from data.monthly_peak_exit_history import monthly_exit_observations


def _day(value):
    require(type(value) is int, 'RAW_ACTION_TIMESTAMP_REQUIRED')
    return datetime.fromtimestamp(value,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()


def _price(value):
    require(type(value) in (str,int,float), 'RAW_PRICE_REQUIRED')
    result=Fraction(str(value))
    require(result>0, 'RAW_POSITIVE_PRICE_REQUIRED')
    return result


def normalize_monthly_raw(*, inputs, sources, expected_hashes, identities, reviews):
    """All reviews bind exact raw bytes; no provider-basis auto-authentication.

split_schedule entries: action_id, security_id, ratio (integer forward split),
old_unit_id, new_unit_id, quote_unit_effective_at. reviewed_dividends entries
match provider date/amount exactly and do NOT certify broker cash entitlement.
"""
    result=deepcopy(inputs);domain=set(result['base_target']['quantities'])
    require(bool(domain) and all(set(item)==domain for item in
        (sources,expected_hashes,identities,reviews,result['histories'])), 'RAW_DOMAIN_MISMATCH')
    dates=result['session_dates'];decision=result['base_target']['monthly_decision_date'];signal=result['signal_date']
    require(dates==sorted(set(dates)) and decision in dates and signal in dates and decision<=signal,
            'RAW_CALENDAR_RANGE')
    window=dates[dates.index(decision):dates.index(signal)+1]
    retained={};projections={}
    for sid in sorted(domain):
        raw=sources[sid];review=reviews[sid]
        require(type(raw) is bytes and len(raw)<=8*1024*1024 and sha256(raw).hexdigest()==expected_hashes[sid], 'RAW_SOURCE_CHANGED')
        require(review.get('raw_sha256')==expected_hashes[sid] and review.get('security_id')==sid
                and isinstance(review.get('review_reference'),str) and bool(review['review_reference']), 'RAW_REVIEW_BINDING')
        basis=review.get('price_basis')
        require(basis in ('AS_TRADED','SPLIT_ADJUSTED_TO_CURRENT_UNIT'), 'EXPLICIT_RAW_PRICE_BASIS_REQUIRED')
        basis_asof=timestamp(review['basis_asof']);captured_at=timestamp(review['captured_at'])
        require(basis_asof<=captured_at,'RAW_BASIS_AFTER_CAPTURE')
        chart=json.loads(raw)['chart']
        require(chart.get('error') is None and len(chart['result'])==1, 'RAW_SERIES_REQUIRED')
        series=chart['result'][0];meta=series['meta'];identity=identities[sid]
        source_days={_day(value) for value in series['timestamp']}
        require(all(datetime.fromtimestamp(value,timezone.utc)<=captured_at for value in series['timestamp']), 'RAW_CAPTURE_BEFORE_BARS')
        require(meta.get('symbol')==identity['ticker'] and meta.get('exchangeName')==identity['exchange']
                and meta.get('currency')=='USD' and meta.get('instrumentType')=='EQUITY', 'RAW_IDENTITY_MISMATCH')
        events=series.get('events',{})
        require(type(events) is dict and not any(value for key,value in events.items() if key not in ('splits','dividends')), 'UNKNOWN_RAW_ACTION')
        schedule=review['split_schedule'];require(type(schedule) is list, 'SPLIT_SCHEDULE_REQUIRED')
        expected_splits=[];prior=None;ids=set()
        for split in schedule:
            require(split['security_id']==sid and type(split['ratio']) is int and split['ratio']>1,
                    'INTEGER_FORWARD_SPLIT_REQUIRED')
            effective=timestamp(split['quote_unit_effective_at'])
            day=effective.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            require(day in source_days and effective<=basis_asof, 'SPLIT_QUOTE_CLOCK_INVALID')
            if day in dates:
                require(effective<=timestamp(result['session_close_times']['closes'][day]), 'SPLIT_QUOTE_CLOCK_INVALID')
            require(split['action_id'] not in ids and split['old_unit_id']!=split['new_unit_id'], 'SPLIT_ID_OR_UNIT_INVALID')
            if prior is not None:
                require(prior[0]<day and prior[1]==split['old_unit_id'], 'SPLIT_CHAIN_INVALID')
            ids.add(split['action_id']);prior=(day,split['new_unit_id'])
            expected_splits.append((day,Fraction(split['ratio'])))
        raw_splits=[]
        for row in events.get('splits',{}).values():
            numerator=_price(row['numerator']);denominator=_price(row['denominator']);ratio=numerator/denominator
            if 'splitRatio' in row:
                parts=row['splitRatio'].split(':')
                require(len(parts)==2 and _price(parts[0])/_price(parts[1])==ratio,'RAW_SPLIT_RATIO_CONFLICT')
            raw_splits.append((_day(row['date']),ratio))
        require(sorted(raw_splits)==expected_splits, 'RAW_SPLIT_SCHEDULE_MISMATCH')
        dividends=[(_day(row['date']),_price(row['amount'])) for row in events.get('dividends',{}).values()]
        reviewed_dividends=[(row['date'],_price(row['provider_amount'])) for row in review['reviewed_dividends']]
        require(sorted(dividends)==sorted(reviewed_dividends) and len(set(dividends))==len(dividends), 'RAW_DIVIDEND_REVIEW_MISMATCH')
        current_unit=review['current_unit_id']
        require((prior is None or prior[1]==current_unit) and result['base_target']['price_units'][sid]==current_unit
                and result['histories'][sid]['units']['basis_id']==current_unit, 'RAW_CURRENT_UNIT_MISMATCH')
        times=series['timestamp'];closes=series['indicators']['quote'][0]['close']
        require(len(times)==len(closes),'RAW_LENGTH_MISMATCH')
        # adjclose may include dividend adjustments. Preserve bytes; never use
        # it as a stock-split ratio or stock-price-risk series.
        prices={}
        for epoch,close in zip(times,closes):
            day=_day(epoch)
            if day not in window:continue
            require(day not in prices, 'RAW_DUPLICATE_SESSION')
            value=_price(close)
            if basis=='AS_TRADED':
                for split_day,ratio in expected_splits:
                    if day<split_day:value/=ratio
            prices[day]=str(value)
        require(set(prices)==set(window),'RAW_COMPLETE_WINDOW_REQUIRED')
        history=result['histories'][sid]
        history['source_reference']='sha256:'+expected_hashes[sid]
        history['closes']=[dict(date=day,close=prices[day],completed_at=result['session_close_times']['closes'][day]) for day in window]
        retained[sid]=deepcopy(events)
        projections[sid]=dict(price_basis=basis,review=deepcopy(review),normalized_closes=deepcopy(prices))
    observations=monthly_exit_observations(**result)
    return dict(inputs=result,observations=observations,source_sha256=dict(expected_hashes),
        original_events=retained,projections=projections,review_sha256=sha256(canonical(reviews)).hexdigest(),
        source_authenticated=False,production_activated=False,dividends_in_price_risk=False,
        asof_available_at_signal=False,
        limitation='Conditional coordinate reconstruction; later-captured or later-unit history is retrospective, not historical source availability.')
