"""Extract full monthly closes from pinned Yahoo chart bytes.

This is a source-content check, not independent market authentication. The
caller supplies the reviewed security identity and constant-unit inputs from
source admission. It must establish action coverage for the FULL window.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from data.monthly_peak_exit_history import monthly_exit_observations


def normalize_monthly_raw(*, inputs, sources, expected_hashes, identities):
    result = deepcopy(inputs)
    domain = set(result['base_target']['quantities'])
    if not domain or any(set(mapping) != domain for mapping in
                         (sources, expected_hashes, identities, result['histories'])):
        raise ValueError('MONTHLY_RAW_DOMAIN_MISMATCH')
    dates = result['session_dates']
    decision = result['base_target']['monthly_decision_date']
    signal = result['signal_date']
    if decision not in dates or signal not in dates or decision > signal:
        raise ValueError('MONTHLY_RAW_CALENDAR_RANGE')
    window = dates[dates.index(decision):dates.index(signal)+1]
    for sid in sorted(domain):
        raw = sources[sid]
        if not isinstance(raw, bytes) or len(raw) > 8*1024*1024 or sha256(raw).hexdigest() != expected_hashes[sid]:
            raise ValueError('MONTHLY_RAW_SOURCE_CHANGED')
        chart = json.loads(raw)['chart']
        if chart.get('error') is not None or len(chart['result']) != 1:
            raise ValueError('MONTHLY_RAW_SERIES_REQUIRED')
        series = chart['result'][0]
        meta = series['meta']
        identity = identities[sid]
        if (meta.get('symbol') != identity['ticker'] or meta.get('currency') != 'USD'
                or meta.get('exchangeName') != identity['exchange']
                or meta.get('instrumentType') != 'EQUITY'):
            raise ValueError('MONTHLY_RAW_IDENTITY_MISMATCH')
        if any(series.get('events', {}).values()):
            raise ValueError('MONTHLY_RAW_ACTION_REVIEW_REQUIRED')
        times = series['timestamp']
        closes = series['indicators']['quote'][0]['close']
        adjusted = series['indicators']['adjclose'][0]['adjclose']
        if not len(times) == len(closes) == len(adjusted):
            raise ValueError('MONTHLY_RAW_LENGTH_MISMATCH')
        prices = {}
        for timestamp, close, adj in zip(times, closes, adjusted):
            day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(
                ZoneInfo('America/New_York')).date().isoformat()
            if day not in window:
                continue
            if day in prices or isinstance(close, bool) or close is None or adj is None:
                raise ValueError('MONTHLY_RAW_INVALID_PRICE')
            if Fraction(str(close)) <= 0 or Fraction(str(close)) != Fraction(str(adj)):
                raise ValueError('MONTHLY_RAW_ADJUSTMENT_REVIEW_REQUIRED')
            prices[day] = str(close)
        if set(prices) != set(window):
            raise ValueError('MONTHLY_RAW_COMPLETE_WINDOW_REQUIRED')
        history = result['histories'][sid]
        history['source_reference'] = 'sha256:' + expected_hashes[sid]
        history['closes'] = [dict(date=day, close=prices[day],
            completed_at=result['session_close_times']['closes'][day]) for day in window]
    observations = monthly_exit_observations(**result)
    return dict(inputs=result, observations=observations,
                source_sha256=dict(expected_hashes), source_authenticated=False)


def review_monthly_supplement(*, capture, request, binding, inputs, identities, now):
    """Review capture content against already admitted identity/unit history.

    The caller must authenticate those original inputs and the capture location.
    This conditional review never grants policy authority or complete action coverage.
    """
    from core.strategy_account_ledger import canonical, require
    from data.current_quantity_v2_paper_action_sources import daily_url, stamp
    from data.strategy_account_notice_review import review_notices
    from scripts.current_research_official_alert_capture import parse_official_feed, URL
    current=stamp(now)
    require(capture['status']=='CAPTURED_REVIEW_REQUIRED' and capture['binding']==binding and
        capture['capture_id']==sha256(canonical(dict(binding=binding,request=request))).hexdigest(),
        'SUPPLEMENT_REVIEW_BINDING')
    require(request['account_id']==binding['account_id'] and request['state_revision']==binding['account_revision'],
        'SUPPLEMENT_REVIEW_ACCOUNT')
    require(current.astimezone(ZoneInfo('America/New_York')).date().isoformat()==binding['session'] and
        stamp(capture['finished_at'])<=current,'SUPPLEMENT_REVIEW_TIME')
    files=capture['files'];pins=capture['source_hashes']
    require(set(files)==set(pins) and sum(map(len,files.values()))<=128*1024*1024,'SUPPLEMENT_REVIEW_FILES')
    for name,raw in files.items():require(sha256(raw).hexdigest()==pins[name],'SUPPLEMENT_REVIEW_HASH')
    documents=capture['documents'];sources={};hashes={};metas={}
    require(set(documents['action_receipts'])==set(identities)==set(inputs['histories']), 'SUPPLEMENT_REVIEW_DOMAIN')
    closes=inputs['session_close_times']['closes']
    for sid,path in documents['action_receipts'].items():
        receipt=json.loads(files[path]);ticker=identities[sid]['ticker']
        raw=files[receipt['raw_path']];received=stamp(receipt['received_at'])
        require(receipt['security_id']==sid and receipt['ticker']==ticker and receipt['http_status']==200 and
            receipt['body_truncated'] is False and receipt['transport_error'] is None and
            receipt['raw_sha256']==sha256(raw).hexdigest(),'SUPPLEMENT_REVIEW_RECEIPT')
        require(stamp(request['window_start'])<=stamp(closes[inputs['base_target']['monthly_decision_date']]) and
            stamp(receipt['requested_from'])<=stamp(request['window_start']) and
            stamp(closes[inputs['signal_date']])<=stamp(receipt['requested_through'])<=received<=stamp(capture['finished_at']),
            'SUPPLEMENT_REVIEW_WINDOW')
        require(receipt['url']==daily_url(ticker,stamp(receipt['requested_from']),stamp(receipt['requested_through'])) and
            receipt['interval']=='1d' and set(receipt['events_requested'])=={'dividends','splits'},'SUPPLEMENT_REVIEW_URL')
        series=json.loads(raw)['chart']['result'][0]
        require(all(datetime.fromtimestamp(t,timezone.utc)<=received for t in series['timestamp']), 'SUPPLEMENT_FUTURE_BAR')
        metas[sid]=series['meta'];sources[sid]=raw;hashes[sid]=sha256(raw).hexdigest()
    rss=files[documents['rss_raw']];rss_receipt=json.loads(files[documents['rss_receipt']])
    require(rss_receipt['url']==URL and rss_receipt['http_status']==200 and
        rss_receipt['raw_sha256']==sha256(rss).hexdigest() and rss_receipt['stored_bytes']==len(rss) and
        stamp(rss_receipt['started_at'])<=stamp(rss_receipt['received_at'])<=stamp(capture['finished_at']), 'SUPPLEMENT_RSS_RECEIPT')
    feed=parse_official_feed(rss,observed_at=stamp(rss_receipt['received_at']))
    require(feed['channel']['future_publication'] is False and feed['channel']['publication_time_issue'] is None and
        all(row['future_publication'] is False and row['publication_time_issue'] is None for row in feed['items']),
        'SUPPLEMENT_RSS_TIME')
    for sid,meta in metas.items():
        names=[meta[k] for k in ('longName','shortName') if isinstance(meta.get(k),str)]
        require(not review_notices(rss,ticker=identities[sid]['ticker'],issuer_names=names)['blocking'],
            'SUPPLEMENT_ACTION_REVIEW_REQUIRED')
    normalized=deepcopy(inputs);normalized['observed_at']=current.isoformat()
    result=normalize_monthly_raw(inputs=normalized,sources=sources,expected_hashes=hashes,identities=identities)
    for sid,history in inputs['histories'].items():
        old={row['date']:row['close'] for row in history['closes']}
        new={row['date']:row['close'] for row in result['inputs']['histories'][sid]['closes']}
        overlap=set(old)&set(new)
        require(bool(overlap) and all(Fraction(old[d])==Fraction(new[d]) for d in overlap),
            'SUPPLEMENT_PRICE_CONTINUITY')
    return dict(result,status='CONDITIONAL_MONTHLY_SOURCE_REVIEW',capture_id=capture['capture_id'],
        policy_approved=False,coverage_complete=False)
