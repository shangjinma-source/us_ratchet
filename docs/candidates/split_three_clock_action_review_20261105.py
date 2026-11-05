"""Match captured split events to recorded actions; no source/broker authorization."""
import json
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_v1 import replay, moment
from data.current_quantity_v2_paper_action_sources import daily_url
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing


def review_recorded_splits(*, state, securities, action_package, now, timing):
    require(replay(state['account_id'], [row['payload'] for row in state['events']]) == state,
            'SPLIT_REVIEW_ACCOUNT_REPLAY')
    current = moment(now)
    files, pins = action_package['files'], action_package['source_hashes']
    require(set(files) == set(pins) and sum(map(len, files.values())) <= 128*1024*1024,
            'SPLIT_REVIEW_PACKAGE_DOMAIN')
    require(all(type(raw) is bytes and sha256(raw).hexdigest() == pins[name]
                for name, raw in files.items()), 'SPLIT_REVIEW_SOURCE_CHANGED')
    documents = action_package['documents']['action_receipts']
    require(set(documents) == set(securities), 'SPLIT_REVIEW_SECURITY_DOMAIN')
    recorded = [row['payload'] for row in state['events'] if row['payload']['kind'] == 'SPLIT_CONFIRMED']
    require(len(recorded)==1,'TIMING_ACTION_DOMAIN_REQUIRES_REVIEW')
    proof=review_timing(action=recorded[0],timing=timing,now=now)
    matches = []
    for sid, security in securities.items():
        receipt = json.loads(files[documents[sid]])
        begin, end, received = map(moment, (receipt['requested_from'], receipt['requested_through'], receipt['received_at']))
        require(receipt['security_id'] == sid and receipt['ticker'] == security['ticker']
                and receipt['http_status'] == 200 and receipt['body_truncated'] is False
                and receipt['transport_error'] is None and receipt['interval'] == '1d'
                and receipt['events_requested'] == ['dividends', 'splits']
                and begin <= end <= received <= current
                and receipt['request_period1'] == int(begin.timestamp())
                and receipt['request_period2'] == int(end.timestamp())+1
                and receipt['url'] == daily_url(security['ticker'], begin, end),
                'SPLIT_REVIEW_RECEIPT')
        raw = files[receipt['raw_path']]
        require(sha256(raw).hexdigest() == receipt['raw_sha256'], 'SPLIT_REVIEW_RAW_CHANGED')
        chart = json.loads(raw)['chart']
        require(chart.get('error') is None and len(chart['result']) == 1, 'SPLIT_REVIEW_CHART')
        entry = chart['result'][0]; meta = entry['meta']
        require(meta['symbol'] == security['ticker'] and meta['currency'] == 'USD'
                and meta['instrumentType'] == 'EQUITY', 'SPLIT_REVIEW_IDENTITY')
        events = entry.get('events', {})
        require(type(events) is dict and set(events) <= {'splits', 'dividends', 'capitalGains'}
                and all(type(value) is dict for value in events.values()), 'SPLIT_REVIEW_EVENTS')
        require(not events.get('dividends') and not events.get('capitalGains'), 'SPLIT_REVIEW_OTHER_RIGHTS')
        relevant = [action for action in recorded if action['security_id'] == sid]
        matched = set()
        for key, event in events.get('splits', {}).items():
            require(type(event.get('date')) is int and str(event['date']) == str(key), 'SPLIT_REVIEW_EVENT_DATE')
            at = datetime.fromtimestamp(event['date'], timezone.utc)
            day = at.astimezone(ZoneInfo('America/New_York')).date()
            require(all(type(event.get(field)) in (int, float) and event[field] > 0
                        for field in ('numerator', 'denominator')), 'SPLIT_REVIEW_RATIO_INVALID')
            ratio = Fraction(str(event['numerator'])) / Fraction(str(event['denominator']))
            require(begin <= at <= end and at <= current, 'SPLIT_REVIEW_EVENT_OUTSIDE_INTERVAL')
            require(Fraction(event['splitRatio'].replace(':', '/')) == ratio, 'SPLIT_REVIEW_RATIO_FIELDS')
            candidates = [action for action in relevant if
                moment(proof['quote_bar_boundary_at']).astimezone(ZoneInfo('America/New_York')).date() == day
                and Fraction(action['ratio']) == ratio]
            require(len(candidates) == 1, 'SPLIT_REVIEW_UNMATCHED_ACTION')
            action = candidates[0]
            require(action['action_id'] not in matched, 'SPLIT_REVIEW_DUPLICATE_ACTION')
            require(moment(action['broker_confirmed_at']) <= current, 'SPLIT_REVIEW_FUTURE_CONFIRMATION')
            matched.add(action['action_id'])
            matches.append(dict(action_id=action['action_id'], security_id=sid,
                recorded_action_sha256=sha256(canonical(action)).hexdigest(),
                provider_event_sha256=sha256(canonical(event)).hexdigest(), raw_sha256=receipt['raw_sha256']))
        require(all(action['action_id'] in matched for action in relevant), 'SPLIT_REVIEW_RECORDED_ACTION_MISSING')
    return dict(status='RECORDED_SPLITS_MATCH_CAPTURE_NOT_AUTHORIZED', account_revision=state['revision'],
        matches=matches,timing_sha256=proof['timing_sha256'], source_hashes=dict(pins), source_authenticated=False,
        broker_evidence_authenticated=False, coverage_complete=False, executable=False,
        account_mutated=False)
