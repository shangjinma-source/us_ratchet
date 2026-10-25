"""Classify one just-closed empty candle; never authorize a price or drop a bar."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json

from core.strategy_account_ledger import require
from data.strategy_halt_aware_pullback_sources_v1 import (
    candidate_from_yahoo_bytes, instant, numeric, unique_object, reject_constant)
from data.strategy_halt_aware_pullback_entry_v1 import stamp
from data.strategy_execution_halt_evidence_v1 import verified_halt_intervals
from data.strategy_halt_aware_execution_limits_v1 import build_execution_limits as original_limits
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY


class RecentClosedMinuteUnavailable(ValueError):
    def __init__(self, evidence):
        super().__init__('UNEXPLAINED_NULL_MINUTE')
        self.evidence = deepcopy(evidence)


def classify_recent_null(*, raw, parameters):
    """Return evidence only. All input bytes remain intact and inadmissible."""
    p = parameters
    require(sha256(raw).hexdigest() == p['expected_sha256'], 'RAW_SHA256_MISMATCH')
    captured, checked, current = map(stamp, (p['captured_at'], p['checked_at'], p['now']))
    opening, closing = map(stamp, (p['session_open'], p['session_close']))
    require(opening <= captured <= checked <= current < closing, 'RETRY_SESSION_TIME')
    intervals = verified_halt_intervals(raw=p['halt_raw'], receipt=p['halt_receipt'],
        security_id=p['security_id'], ticker=p['ticker'], session=p['session'],
        session_open=p['session_open'], session_close=p['session_close'], now=p['now'])
    def halted(start):
        return any(stamp(x['halted_at']) <= start and start + timedelta(minutes=1) <= stamp(x['resumed_at']) for x in intervals)
    document = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_object, parse_constant=reject_constant)
    chart = document['chart']
    require(chart.get('error') is None and len(chart['result']) == 1, 'RETRY_CHART')
    result = chart['result'][0]; meta = result['meta']; times = result['timestamp']
    require(meta['symbol'] == p['ticker'] and meta['currency'] == 'USD'
        and meta['instrumentType'] == 'EQUITY' and meta['exchangeTimezoneName'] == 'America/New_York'
        and meta['dataGranularity'] == '1m', 'RETRY_IDENTITY')
    require(instant(meta['currentTradingPeriod']['regular']['start']) == opening
        and instant(meta['currentTradingPeriod']['regular']['end']) == closing, 'RETRY_CALENDAR')
    require(not any(value for key, value in result.get('events', {}).items() if key != 'dividends'), 'RETRY_UNIT_EVENT')
    quote = result['indicators']['quote']
    require(type(times) is list and 0 < len(times) <= 1440 and len(quote) == 1, 'RETRY_ARRAY')
    quote = quote[0]; fields = ('open','high','low','close','volume')
    require(all(type(quote.get(k)) is list and len(quote[k]) == len(times) for k in fields), 'RETRY_ARRAY')
    minute_end = captured.replace(second=0, microsecond=0)
    recent_start = minute_end - timedelta(minutes=1)
    require(0 <= (captured-minute_end).total_seconds() <= 2, 'RETRY_NOT_AT_BOUNDARY')
    last=instant(meta['regularMarketTime'])
    require(opening <= last <= checked and last <= captured+timedelta(seconds=1)
        and numeric(meta['regularMarketPrice'])>0 and current < last+timedelta(seconds=p['maximum_age_seconds']), 'RETRY_LAST_PRICE')
    for interval in intervals:
        require(stamp(interval['resumed_at'])<=stamp(interval['observed_at'])<=captured
            and last>=stamp(interval['resumed_at']), 'RETRY_HALT_TIME')
    post_resume=not intervals
    found=[]; complete={}; previous=None; prior_minute_snapshot=None
    for index, value in enumerate(times):
        start=instant(value)
        require(previous is None or previous < start, 'RETRY_TIME_ORDER');previous=start
        require(start <= checked and start <= captured+timedelta(seconds=1), 'RETRY_FUTURE')
        if start.second or start.microsecond or start > captured:
            values={k:numeric(quote[k][index]) for k in fields}
            require(index==len(times)-1 and start==instant(meta['regularMarketTime'])
                and opening <= start < closing and values['volume']==0 and values['open']>0
                and all(values[k]==values['open'] for k in ('high','low','close')), 'RETRY_SNAPSHOT')
            original_admissible=(start.replace(second=0,microsecond=0)==minute_end or captured < start <= captured+timedelta(seconds=1))
            if not original_admissible:
                # Explicit recapture eligibility ONLY: an old-minute last-trade
                # snapshot is never a candle or an admissible old quote. The
                # unchanged source adapter must accept the complete NEW capture.
                require(start.replace(second=0,microsecond=0)==recent_start
                    and 0 <= (captured-start).total_seconds() <= 3, 'RETRY_SNAPSHOT')
                prior_minute_snapshot=dict(at=start.isoformat(),seconds_before_capture=(captured-start).total_seconds(),
                    role='RECAPTURE_ELIGIBILITY_ONLY_NOT_BAR_OR_ACCEPTED_PRICE')
            continue
        if start < opening or start+timedelta(minutes=1)>closing:continue
        if start+timedelta(minutes=1)>captured:continue
        complete[start]=True
        values=[quote[k][index] for k in fields]
        if any(v is None for v in values):
            require(all(v is None for v in values), 'PARTIAL_NULL_MINUTE')
            if halted(start):continue
            require(start==recent_start, 'RETRY_OLDER_NULL')
            found.append(start.isoformat());continue
        o,h,l,c,v=map(numeric,values)
        require(min(o,h,l,c)>0 and v>0 and l<=min(o,c)<=max(o,c)<=h, 'RETRY_INVALID_BAR')
        require(not halted(start),'RETRY_HALT_BAR_OVERLAP')
        if intervals and start>=max(stamp(x['resumed_at']) for x in intervals):post_resume=True
    cursor=opening
    while cursor+timedelta(minutes=1)<=captured:
        require(cursor in complete, 'RETRY_MISSING_MINUTE');cursor+=timedelta(minutes=1)
    require(len(found)==1,'RETRY_RECENT_NULL_REQUIRED')
    require(post_resume,'RETRY_POST_RESUME_BAR_REQUIRED')
    return dict(security_id=p['security_id'],ticker=p['ticker'],raw_sha256=p['expected_sha256'],
        captured_at=p['captured_at'],null_minute=found[0],minute_end=minute_end.isoformat(),
        seconds_after_end=(captured-minute_end).total_seconds(),halt_raw_sha256=sha256(p['halt_raw']).hexdigest(),
        retry_only_prior_minute_snapshot=prior_minute_snapshot)


def retry_evidence(*, state, target_quantities, market_capture, now, policy=None, **unused):
    """Check every net-buy SID. An unrelated bad buy must not earn a retry."""
    require(type(target_quantities) is dict,'RETRY_TARGET_REQUIRED')
    policy=EXPERIMENTAL_POLICY if policy is None else policy
    require(policy==EXPERIMENTAL_POLICY,'RETRY_POLICY')
    package=market_capture;files=package['files'];pins=package['source_hashes']
    require(set(files)==set(pins) and len(files)<=2000 and sum(map(len,files.values()))<=128*1024*1024,'RETRY_SOURCE_BUDGET')
    require(all(sha256(raw).hexdigest()==pins[name] for name,raw in files.items()),'RETRY_SOURCE_CHANGED')
    require(package['account_id']==state['account_id'] and package['account_revision']==state['revision'],'RETRY_ACCOUNT')
    halt=package['halt_evidence'];halt_raw=files[halt['raw_path']];halt_receipt=json.loads(files[halt['receipt_path']])
    needed={sid for sid,q in target_quantities.items() if q}|{sid for sid,q in state['shares'].items() if q}
    require(needed <= set(package['marks']),'RETRY_DOMAIN')
    recent=[];all_buys=[]
    for sid in sorted(needed):
        gap=target_quantities.get(sid,0)-state['shares'].get(sid,0)
        for order in state['orders'].values():
            if order['status']=='OPEN' and order['security_id']==sid:gap+=order['remaining_quantity']*(-1 if order['side']=='BUY' else 1)
        if gap<=0:continue
        mark=package['marks'][sid];ticker=package['identities'][sid]['ticker']
        require(mark['ticker']==ticker and mark['security_id']==sid,'RETRY_SID_BINDING')
        refs=mark['source_references'];receipts=[name for name in refs if name.endswith('.receipt.json')]
        require(len(receipts)==1 and set(refs)==set(mark['source_hashes']) and all(mark['source_hashes'][x]==pins[x] for x in refs),'RETRY_MARK_CLOSURE')
        receipt=json.loads(files[receipts[0]]);raw=files[receipt['raw_path']]
        require(receipt['security_id']==sid and receipt['ticker']==ticker and receipt['raw_path'] in refs
            and receipt['raw_sha256']==sha256(raw).hexdigest() and receipt['captured_at']==mark['captured_at'],'RETRY_RECEIPT')
        doc=json.loads(raw)['chart']['result'][0];period=doc['meta']['currentTradingPeriod']['regular']
        p=dict(expected_sha256=receipt['raw_sha256'],security_id=sid,ticker=ticker,
            session=package['session'],session_open=instant(period['start']).isoformat(),session_close=instant(period['end']).isoformat(),
            captured_at=receipt['captured_at'],checked_at=receipt.get('checked_at',receipt['captured_at']),now=now,
            rebound_fraction=policy['rebound_fraction'],minimum_discount=policy['minimum_discount'],maximum_age_seconds=policy['maximum_age_seconds'],
            halt_raw=halt_raw,halt_receipt=halt_receipt)
        all_buys.append(sid)
        try:candidate_from_yahoo_bytes(raw=raw,previous_cap=None,**p)
        except ValueError as error:
            if str(error)!='UNEXPLAINED_NULL_MINUTE':raise
            recent.append(classify_recent_null(raw=raw,parameters=p))
    require(bool(recent),'RETRY_RECENT_NULL_REQUIRED')
    return dict(schema='RECENT_CLOSED_MINUTE_RECAPTURE_ELIGIBILITY_V1',account_revision=state['revision'],
        all_buy_security_ids=all_buys,recent_nulls=recent,source_hashes=dict(pins),price_authorized=False)


def build_execution_limits(**kwargs):
    try:return original_limits(**kwargs)
    except ValueError as error:
        if str(error)!='UNEXPLAINED_NULL_MINUTE':raise
        try:evidence=retry_evidence(**kwargs)
        except (ValueError,KeyError,TypeError,IndexError):raise error
        raise RecentClosedMinuteUnavailable(evidence) from error
