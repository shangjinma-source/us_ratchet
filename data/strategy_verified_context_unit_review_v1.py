"""Shared bounded interval action evidence for a verified account projection.

No fabricated intraday origin and no assertion of complete action coverage.
Any observed unit event or possible held cash entitlement stops the review.
"""
from hashlib import sha256
import html
import json
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_account_target_inputs import require, stamp
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import parse_official_feed, URL
from data.strategy_account_notice_review import review_notices


def review_verified_context_interval(*, state, exposure_times, exposed_security_ids, securities, marks, action_package, training_manifest_sha256,
                    historical_search_arguments_sha256, historical_price_basis,
                    training_closed_at, marks_sha256, now):
    current = stamp(now)
    closed = stamp(training_closed_at)
    require(closed <= current, 'TRAINING_NOT_CLOSED')
    require(set(securities) == set(marks) and bool(marks), 'UNIT_REVIEW_DOMAIN_MISMATCH')
    require(sha256(canonical(marks)).hexdigest() == marks_sha256, 'MARKS_BINDING_MISMATCH')
    floor = closed
    for value in exposure_times:
        floor = min(floor, stamp(value))
    files, pins = action_package['files'], action_package['source_hashes']
    require(set(files) == set(pins) and sum(map(len, files.values())) <= 128*1024*1024,
            'ACTION_PACKAGE_BUDGET')
    require(all(type(raw) is bytes and sha256(raw).hexdigest() == pins[path]
                for path, raw in files.items()), 'ACTION_SOURCE_CHANGED')
    documents = action_package['documents']
    require(set(documents['action_receipts']) == set(marks), 'ACTION_DOMAIN_MISMATCH')
    rss = files[documents['rss_raw']]
    receipt = json.loads(files[documents['rss_receipt']])
    received, started = stamp(receipt['received_at']), stamp(receipt['started_at'])
    require(receipt['url'] == URL and receipt['http_status'] == 200
            and receipt['raw_sha256'] == sha256(rss).hexdigest()
            and receipt['stored_bytes'] == len(rss) and started <= received <= current
            and (current-received).total_seconds() < 120, 'ACTION_RSS_RECEIPT_INVALID')
    feed = parse_official_feed(rss, observed_at=received)
    require(not feed['channel']['publication_time_issue'] and not feed['channel']['future_publication']
            and all(not item['publication_time_issue'] for item in feed['items']), 'ACTION_RSS_TIME_INVALID')
    # This is a live received feed, not historical PIT evidence. Scan every
    # received item, including future-dated announcements; no date filters may
    # hide a relevant notice. An unrelated scheduled item cannot veto all SIDs.
    units = {}
    for sid, mark in marks.items():
        ticker = securities[sid]['ticker']
        require(mark['security_id'] == sid and mark['currency'] == 'USD', 'MARK_IDENTITY_OR_CURRENCY')
        observed = stamp(mark['observed_at'])
        captured = stamp(mark['captured_at'])
        checked = stamp(mark.get('checked_at', mark['captured_at']))
        require(captured <= checked <= current and observed <= checked
                and (observed-captured).total_seconds() <= 1, 'MARK_CAPTURE_TIME_INVALID')
        covered = max(observed, captured)
        require(mark.get('ticker', ticker) == ticker, 'MARK_IDENTITY_OR_CURRENCY')
        path = documents['action_receipts'][sid]
        action = json.loads(files[path])
        begin, end, at = map(stamp, (action['requested_from'], action['requested_through'], action['received_at']))
        require(action['security_id'] == sid and action['ticker'] == ticker
                and action['http_status'] == 200 and action['body_truncated'] is False
                and action['transport_error'] is None and action['interval'] == '1d'
                and action['events_requested'] == ['dividends', 'splits']
                and begin <= floor <= observed and covered <= end <= at <= started
                and action['request_period1'] == int(begin.timestamp())
                and action['request_period2'] == int(end.timestamp())+1
                and action['url'] == daily_url(ticker, begin, end), 'ACTION_INTERVAL_NOT_COVERED')
        raw = files[action['raw_path']]
        require(sha256(raw).hexdigest() == action['raw_sha256'], 'ACTION_SOURCE_CHANGED')
        chart = json.loads(raw)['chart']
        require(chart.get('error') is None and len(chart['result']) == 1, 'ACTION_CHART_INVALID')
        entry = chart['result'][0]
        meta = entry['meta']
        require(meta['symbol'] == ticker and meta['currency'] == 'USD'
                and meta['instrumentType'] == 'EQUITY', 'ACTION_IDENTITY_MISMATCH')
        events = entry.get('events', {})
        require(type(events) is dict and set(events) <= {'dividends','splits','capitalGains'}
                and all(type(value) is dict for value in events.values()), 'ACTION_EVENTS_INVALID')
        require(not any(value for kind, value in events.items() if kind != 'dividends'),
                'KNOWN_UNIT_CHANGE_REQUIRES_REVIEW')
        # Keep possible entitlements unresolved instead of silently losing cash.
        exposed = state['shares'].get(sid, 0) > 0 or sid in exposed_security_ids
        require(not (exposed and events.get('dividends')), 'POSSIBLE_CASH_RIGHTS_REQUIRES_REVIEW')
        names = [meta[key].strip() for key in ('longName', 'shortName')
                 if isinstance(meta.get(key), str) and len(meta[key].strip()) >= 2]
        notice_review = review_notices(rss, ticker=ticker, issuer_names=names)
        require(not notice_review['blocking'], 'KNOWN_NOTICE_REQUIRES_REVIEW')
        units[sid] = dict(security_id=sid, current_price_basis=mark['price_basis'],
            current_mark_sha256=sha256(canonical(mark)).hexdigest(),
            historical_price_basis=historical_price_basis, training_manifest_sha256=training_manifest_sha256,
            historical_scenarios_usable_in_current_units=True, held_quantities_in_current_units=True,
            notice_match_audit=notice_review['matches'],
            covered_through=covered.isoformat(), limited_name_coverage=not bool(names),
            source_references=[path, action['raw_path'], documents['rss_raw'], documents['rss_receipt']])
    return dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1', status='CONDITIONAL_CURRENT_UNITS_REVIEWED',
        training_manifest_sha256=training_manifest_sha256,
        historical_search_arguments_sha256=historical_search_arguments_sha256,
        training_cutoff_date=closed.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
        training_closed_at=closed.isoformat(), marks_sha256=marks_sha256, account_revision=state['revision'],
        reviewed_at=current.isoformat(), securities=units, unresolved=[], pending_rights=[],
        source_references=sorted(pins), coverage_complete=False, source_authenticated=False,
        retention_unknown=True, limitations=['Public sources may omit actions; no match is not proof of no changes.',
            'Possible unit changes or cash rights require review before continuing.'])
