"""Full monthly-window first-source review; no HTTP or policy approval.

Server configuration fixes identity, calendar and the target's unit-review source
mapping. An old mark is never used as today's price. A raw-price overlap with the
reviewed action source is required; missing continuity waits for new evidence.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.monthly_risk_epoch import validate_monthly_epoch
from data.saved_frontier_security_domain_v1 import plan_security_domain
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.strategy_daily_rolling_parent_v3 import pinned
from data.strategy_daily_session_capture import stamp
from data.current_quantity_v2_paper_action_sources import daily_url
from data.strategy_account_notice_review import review_notices
from scripts.current_research_official_alert_capture import parse_official_feed, URL

SOURCES = {
    'data/monthly_risk_epoch.py',
    'data/saved_frontier_first_window_v1.py',
    'data/saved_frontier_security_domain_v1.py',
    'core/saved_monthly_frontier_proposal.py',
    'data/strategy_daily_rolling_parent_v3.py',
    'data/strategy_daily_session_capture.py',
    'data/strategy_account_identity.py',
    'data/strategy_account_notice_review.py',
    'data/current_quantity_v2_paper_action_sources.py',
    'scripts/current_research_official_alert_capture.py',
    'data/strategy_daily_evidence_rebind.py',
    'data/strategy_daily_evidence_adapter.py',
    'core/strategy_account_ledger.py',
    'core/strategy_account_difference.py',
    'backtest/current_quantity_v2_risk_overlays.py',
}



# Exact independently reviewed notices only, not a category-wide exemption. Original bytes/times
# remain in closure and every issuer mention still goes through notice review.
VERIFIED_UNRELATED_FUTURE_NOTICES = {
    # Official full-body review: index data products only, no issuer corporate action.
    # Exact signature remains required; never an identifier/category-only bypass.
    'fpnews2026-74': (
        'Financial Products News',
        'fpnews2026-74 - Nasdaq Announces Launch of Six New Indexes Effective Wednesday, October 28th, 2026',
        'News Category Alert Markets What You Need To Know Financial Products News #2026-074'),
    # Full official notice reviewed in tmp/eta2026_61_review_20261028/review.json.
    # TRF schedule/clearing infrastructure only; original future RSS time retained.
    'ETA2026-61': (
        'Equity Trader Alert',
        'ETA2026-61 - UPDATED: FINRA/Nasdaq TRF Software Change Scheduled for November 2, 2026',
        'News Category Alert Markets What You Need To Know Equity Trader Alert #2026-061 Post - Trade'),
    'UTP2026-32': (
        'UTP Vendor Alert',
        'UTP2026-32 - 2027 Failover and Market Wide Circuit Breaker Testing Schedule',
        'News Category Alert Markets What You Need To Know UTP Vendor Alert #2026-032 UTP - SIP'),
    'ETP2026-175': (
        'Trader Alerts - New ETP Listings',
        'ETP2026-175 - Nasdaq Texas to Begin Dual Listing Twenty-Five VictoryShares ETFs on Tuesday, October 27, 2026',
        'News Category Alert Markets What You Need To Know Trader Alerts - New ETP Listings #2026-175 NTX'),
}

# Audit identity for the reviewed document, not a claim of a new HTTP body check.
# Runtime source pins bind this reviewed scope record; retain the official bytes
# and receipt in the release evidence archive for independent re-verification.
VERIFIED_UNRELATED_NOTICE_EVIDENCE = {
    'fpnews2026-74': dict(
        classification='REVIEWED_INDEX_DATA_DISSEMINATION_NO_ISSUER_ACTION',
        official_url='https://www.nasdaqtrader.com/TraderNews.aspx?id=fpnews2026-74',
        reviewed_body_sha256='c73d2260444a8b7360a78762a7432d003ab0cc54edb631f2833f4c0e06ecbacd',
        review_schema='OFFICIAL_NOTICE_SCOPE_REVIEW_V1',
        scope='Six TWD technology/semiconductor index data products on GIDS/GIW/GIFFD; no issuer shares, CUSIP, cash or entitlement change.',
        runtime_full_body_refetched=False),
}


def other_issuer_eca_scope(row, *, ticker, issuer_names):
    """Conditional scope classification, not review/approval of the other action.

    Two Nasdaq full notices independently confirmed the exact single-issuer
    reverse-split headline templates. Future variants are NOT body-authenticated.
    Unknown/multi-party titles are deliberately unsupported.
    """
    if row.get('news_category') != 'Equity Corporate Actions Alert' or row.get('description_truncated') is not False:
        return None
    match = re.fullmatch(r'(ECA(20[0-9]{2})-([1-9][0-9]*)) - Information Regarding the '
        r'(Reverse Stock Split and CUSIP Number Change|Reverse Stock Split, Par Value and CUSIP Number Change) '
        r"for ([A-Za-z0-9][A-Za-z0-9 .,'’-]{1,139}) \(([A-Z]{1,5})\)", row.get('title',''))
    if not match:
        return None
    identifier, year, number, action, issuer, symbol = match.groups()
    if row.get('link') != 'http://www.nasdaqtrader.com/TraderNews.aspx?id='+identifier:
        return None
    if row.get('description_summary') != ('News Category Alert Markets What You Need To Know '
        'Equity Corporate Actions Alert #'+year+'-'+number+' The Nasdaq Stock Market'):
        return None
    # No issuer lists, former/successor relationships, aliases or multiple ticker
    # syntax. A comma is accepted only before one trailing legal suffix.
    if re.search(r'\b(and|formerly|former|fka|successor|versus|including)\b',issuer,re.I):
        return None
    if ',' in issuer and not re.fullmatch(r"[A-Za-z0-9 .’'-]+, (?:Inc|Corp|Ltd)\.?",issuer):
        return None
    normalize = lambda value: re.sub(r'[^a-z0-9]','',value.lower())
    subject = normalize(issuer)
    names = {normalize(n) for n in issuer_names if isinstance(n,str) and normalize(n)}
    if not names:
        return None
    names |= {stem for n in tuple(names) if len(stem := re.sub(r'(incorporated|corporation|holdings|limited|inc|corp|ltd|plc)$','',n)) >= 3}
    if symbol.casefold() == ticker.casefold() or any(subject == n or subject in n or n in subject for n in names):
        return None
    return dict(identifier=identifier, issuer=issuer, ticker=symbol, action=action,
        classification='OTHER_SINGLE_ISSUER_ECA_REVERSE_SPLIT_TEMPLATE',
        full_body_reviewed_for_this_item=False,
        limitation='Conditional title/template scope only; not certification of this corporate action or absence of actions for the target.')


def reviewed_eca_776_scope(row, *, ticker, issuer_names):
    """One body-reviewed notice, limited to the two independently checked issuers."""
    expected = (
        'Equity Corporate Actions Alert',
        'ECA2026-776 - Information Regarding the Business Combination of Adial Pharmaceuticals, Inc. (ADIL) and Azora Therapeutics, Inc.',
        'News Category Alert Markets What You Need To Know Equity Corporate Actions Alert #2026-776 The Nasdaq Stock Market',
        'http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-776')
    if tuple(row.get(k) for k in ('news_category', 'title', 'description_summary', 'link')) != expected or row.get('description_truncated') is not False:
        return None
    verified_targets = {'MRNA': {'modernainc', 'moderna'}, 'SNDK': {'sandiskcorporation', 'sandisk'}}
    names = {re.sub(r'[^a-z0-9]', '', name.casefold()) for name in issuer_names if isinstance(name, str)}
    if ticker not in verified_targets or not names or not names <= verified_targets[ticker]:
        return None
    return dict(identifier='ECA2026-776', classification='BODY_REVIEWED_OTHER_ISSUERS_BUSINESS_COMBINATION',
        reviewed_body_sha256='ff54d7bf01f508daf178f24e1b81b539711f4039cab697faaf2ae3aa0bb485ec',
        official_url='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-776',
        old_issuer='Adial Pharmaceuticals, Inc.', old_ticker='ADIL', old_cusip='00688A304',
        new_issuer='Azora Therapeutics, Inc.', new_ticker='AZR', new_cusip='054800107',
        issue_type='Common Stock', expected_effective_date='2026-10-29',
        condition='Subject to shareholder vote on 2026-10-28; not certified effective by this scope review.',
        runtime_full_body_refetched=False,
        limitation='Only reviewed body version and these two target issuers; not a general merger exemption or proof of no other actions.')


def reviewed_eca_772_scope(row, *, ticker, issuer_names):
    """Exact reviewed two-security holding-company notice, not a general exemption."""
    expected = (
        'Equity Corporate Actions Alert',
        'ECA2026-772 - Information Regarding the Formation of a Holding Company for Navient Corporation (NAVI & JSM)',
        'News Category Alert Markets What You Need To Know Equity Corporate Actions Alert #2026-772 The Nasdaq Stock Market',
        'http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-772')
    if tuple(row.get(k) for k in ('news_category', 'title', 'description_summary', 'link')) != expected or row.get('description_truncated') is not False:
        return None
    verified_targets = {'MRNA': {'modernainc', 'moderna'}, 'SNDK': {'sandiskcorporation', 'sandisk'}}
    names = {re.sub(r'[^a-z0-9]', '', name.casefold()) for name in issuer_names if isinstance(name, str)}
    if ticker not in verified_targets or not names or not names <= verified_targets[ticker]:
        return None
    return dict(identifier='ECA2026-772', classification='BODY_REVIEWED_OTHER_ISSUERS_HOLDING_COMPANY_FORMATION',
        reviewed_body_sha256='613c43b72e1b3576d93b17a1a3f7f5e80838ab52b7c1651a26d4d91c6d2af37a',
        official_url='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-772',
        securities=[dict(ticker='NAVI', old_issuer='Navient Corporation', new_issuer='Navient Holdings, Inc.',
                         issue_type='Common Stock', old_cusip='63938C108', new_cusip='63943R108'),
                    dict(ticker='JSM', old_issuer='Navient Corporation', new_issuer='Navient LLC',
                         issue_type='6% Senior Notes due December 15, 2043', cusip='63938C405')],
        expected_reorganization_time='2026-10-28 23:59 America/New_York', marketplace_effective_date='2026-10-29',
        runtime_full_body_refetched=False,
        limitation='Only this reviewed body version and MRNA/SNDK issuer identities; not proof of completion or a general multi-security exemption.')


def reviewed_etp_177_scope(row, *, ticker, issuer_names):
    """Exact full-body-reviewed listing, not an ETP category exemption."""
    if (row.get('news_category'), row.get('title'), row.get('description_summary')) != (
        'Trader Alerts - New ETP Listings',
        'ETP2026-177 -  Nasdaq to Begin Listing Two Franklin Templeton ETFs on Thursday, October 29, 2026',
        'News Category Alert Markets What You Need To Know Trader Alerts - New ETP Listings #2026-177 The Nasdaq Stock Market'):
        return None
    if row.get('link') != 'http://www.nasdaqtrader.com/TraderNews.aspx?id=ETP2026-177' or row.get('description_truncated') is not False:
        return None
    normalize = lambda value: re.sub(r'[^a-z0-9]', '', value.casefold())
    allowed = {'MRNA': {'moderna', 'modernainc'}, 'SNDK': {'sandisk', 'sandiskcorporation'}}
    names = {normalize(name) for name in issuer_names if type(name) is str}
    if ticker not in allowed or not names or '' in names or not names <= allowed[ticker]:
        return None
    return dict(identifier='ETP2026-177', classification='EXACT_REVIEWED_TWO_OTHER_ETF_NEW_LISTING',
        official_url='https://www.nasdaqtrader.com/TraderNews.aspx?id=ETP2026-177',
        reviewed_body_sha256='b2280219ba6d4a45658ceb0432029b4d3848461ce7831234e53e0da318ab1646',
        listed_tickers=['FBEQ', 'FIBT'], issuer='Franklin Templeton', listing_date='2026-10-29',
        body_observed_at='2026-10-28T19:20:41.382420+00:00',
        scope='New ETF listing and valuation dissemination; no target-share consideration or distribution disclosed.',
        underlying_holdings_certified=False, runtime_full_body_refetched=False,
        publication_time_modified=False, historical_first_availability_certified=False)


def review_future_notice_scope(raw, *, feed, ticker, issuer_names):
    notices = review_notices(raw, ticker=ticker, issuer_names=issuer_names)
    require(feed['channel']['future_publication'] is False and
            not feed['channel'].get('publication_time_issue'), 'WAIT_KNOWN_ACTION_REVIEW')
    require(not notices['blocking'], 'WAIT_KNOWN_ACTION_REVIEW')
    ignored = []
    for row in feed['items']:
        require(row.get('publication_time_issue') is None and
                row.get('future_publication') in (True, False), 'WAIT_KNOWN_ACTION_REVIEW')
        if not row['future_publication']:
            continue
        # Conservative: even a title-only target mention exempted by the older
        # ETF grammar prevents using this unrelated-future exemption.
        require(not notices['matches'], 'WAIT_KNOWN_ACTION_REVIEW')
        matches = [identifier for identifier, signature in VERIFIED_UNRELATED_FUTURE_NOTICES.items()
                   if (row.get('news_category'), row.get('title'), row.get('description_summary')) == signature
                   and row.get('link') == 'http://www.nasdaqtrader.com/TraderNews.aspx?id='+identifier]
        eca_scope = (other_issuer_eca_scope(row, ticker=ticker, issuer_names=issuer_names) or
                     reviewed_eca_776_scope(row, ticker=ticker, issuer_names=issuer_names) or
                     reviewed_eca_772_scope(row, ticker=ticker, issuer_names=issuer_names) or
                     reviewed_etp_177_scope(row, ticker=ticker, issuer_names=issuer_names))
        require((len(matches) == 1 or eca_scope is not None) and row.get('description_truncated') is False,
                'WAIT_KNOWN_ACTION_REVIEW')
        ignored.append(dict(identifier=matches[0] if matches else eca_scope['identifier'],
            scope_classification=eca_scope or deepcopy(VERIFIED_UNRELATED_NOTICE_EVIDENCE.get(matches[0], dict(classification='EXACT_PREVIOUSLY_REVIEWED_NOTICE'))),
            index=row['index'], title=row['title'],
            news_category=row['news_category'], link=row['link'], guid=row.get('guid'),
            original_pubDate=row['pubDate'], published_at_utc=row['published_at_utc'],
            observed_at=feed['observed_at'], disposition='VERIFIED_UNRELATED_NOTICE_TIME_ANOMALY_RETAINED'))
    return dict(schema='ISSUER_SCOPED_FUTURE_NOTICE_REVIEW_V1', ticker=ticker,
        issuer_names=list(issuer_names), ignored_future_items=ignored,
        raw_sha256=sha256(raw).hexdigest(), issuer_notice_review=notices,
        original_times_modified=False, complete_action_coverage=False,
        limitation='Exact observed infrastructure/ETF notices and strictly parsed other-single-issuer ECA reverse-split templates excluded from this issuer gate; no point-in-time or no-action certification.')


def review_first_window(*, root, configuration_bytes, configuration_sha256,
                        capture_files, state, target, proposal, extra_security_ids=(), clock=None):
    """Return one SID's closed packet, to be aggregated before daily admission.

    capture_files are saved daily/official response and receipt bytes, not
    browser-provided prices. Publication and transport are separate server work.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    began = stamp(clock())
    try:
        return _review(root=Path(root), configuration_bytes=configuration_bytes,
                       configuration_sha256=configuration_sha256, capture_files=capture_files,
                       state=state, target=target, proposal=proposal, extra_security_ids=extra_security_ids, clock=clock, began=began)
    except (ValueError, KeyError, TypeError, IndexError, OSError, ArithmeticError) as error:
        return dict(status='WAIT_FIRST_WINDOW_REVIEW', reason=str(error),
                    receipt=None, files=None, policy_approved=False)


def _review(*, root, configuration_bytes, configuration_sha256, capture_files,
            state, target, proposal, extra_security_ids, clock, began):
    require(proposal == build_frontier_proposal(target=target), "FRONTIER_PROPOSAL_CHANGED")
    require(sha256(configuration_bytes).hexdigest() == configuration_sha256, 'FIRST_CONFIG_HASH')
    config = json.loads(configuration_bytes)
    require(config['schema'] == 'SAVED_FRONTIER_FIRST_WINDOW_V1', 'FIRST_CONFIG_SCHEMA')
    # A first source review does not create policy authority, even if a browser
    # or caller asks to attach an existing release.
    require(config.get('release_sha256') is None, 'FIRST_POLICY_MUST_REMAIN_UNRELEASED')
    files = {'first-window/configurations/'+configuration_sha256+'.json': configuration_bytes}
    def include(name, body):
        require(name not in files or files[name] == body, 'FIRST_SOURCE_COLLISION')
        files[name] = body
        require(len(files) <= 2000 and sum(map(len, files.values())) <= 32*1024*1024,
                'FIRST_SOURCE_BUDGET')
    require(SOURCES <= {r['path'] for r in config['source_pins']}, 'FIRST_CODE_PINS')
    for ref in config['source_pins']:
        body = pinned(root, ref, maximum=32*1024*1024)
        if ref['path'] in SOURCES:
            require(body == (Path(__file__).resolve().parents[1]/ref['path']).read_bytes(),
                    'FIRST_EXECUTING_SOURCE_CHANGED')
        include(ref['path'], body)
    for key in ('identity', 'calendar'):
        include(config[key]['path'], pinned(root, config[key], maximum=8*1024*1024))
    domain = plan_security_domain(root=root, state=state, target=target,
                                 identity_reference=config['identity'],
                                 source_paths=config['unit_source_paths'],
                                 monthly_quantities=proposal['payload']['proposed_target_quantities'],
                                 extra_security_ids=extra_security_ids)
    sid = config['security_id']; entry = domain['securities'][sid]
    # Preserve the complete pinned manifest, but include only this identity's
    # resolved source closure. Unrelated issuers are not evidence for this SID.
    for name,digest in entry['identity']['source_hashes'].items():
        include(name,pinned(root,dict(path=name,sha256=digest),maximum=8*1024*1024))
    baseline = entry['unit_baseline']
    require(baseline is not None, 'WAIT_UNIT_BASELINE')
    binding = target['payload']['decision']['payload']['input_binding']
    names = dict(baseline['source_hashes'])
    names[baseline['review_reference']['path']] = baseline['review_reference']['sha256']
    for name, digest in names.items():
        include(name, pinned(root, dict(path=config['unit_source_paths'][name], sha256=digest),
                             maximum=8*1024*1024))
    calendar = json.loads(files[config['calendar']['path']]); sessions = calendar['sessions']
    require(calendar['schema'] == 'FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange'] == 'NASDAQ',
            'FIRST_CALENDAR_SCHEMA')
    dates = [s['date'] for s in sessions]
    require(dates == sorted(set(dates)), 'FIRST_CALENDAR_DATES')
    for index, row in enumerate(sessions):
        require(stamp(row['open']) < stamp(row['close']) and
                stamp(row['open']).astimezone(ZoneInfo('America/New_York')).date().isoformat() ==
                row['date'] == stamp(row['close']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                and (index == 0 or stamp(sessions[index-1]['close']) < stamp(row['open'])),
                'FIRST_CALENDAR_SESSION')
    today = began.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(today in dates and dates.index(today) >= 20, 'FIRST_CALENDAR_COVERAGE')
    index = dates.index(today)
    epoch = config['monthly_decision_date']
    validate_monthly_epoch(decision_date=epoch, target_month=target['payload']['target_month'], session_dates=dates)
    require(epoch in dates and dates.index(epoch)<index,
            'FIRST_MONTHLY_EPOCH_REQUIRED')
    window_start = min(index-20, dates.index(epoch))
    window = sessions[window_start:index]; execution = sessions[index]
    require(began < stamp(execution['close']), 'WAIT_NEW_SESSION_EVIDENCE')
    require(stamp(baseline['reviewed_at']) <= began, 'FIRST_BASELINE_FUTURE')
    require(stamp(window[0]['open']) <= stamp(baseline['unit']['covered_through']) <= began,
        'WAIT_BASELINE_WINDOW_BRIDGE')
    require(set(capture_files) == {'daily.response.bin','daily.receipt.json',
                                  'official.response.bin','official.receipt.json'}, 'FIRST_CAPTURE_DOMAIN')
    prefix = 'first-window/'+sid.replace(':','_')+'/'+today+'/'
    received = []
    for name in ('daily', 'official'):
        body = capture_files[name+'.response.bin']; receipt = json.loads(capture_files[name+'.receipt.json'])
        start, end = stamp(receipt['started_at']), stamp(receipt['received_at'])
        require(receipt['status'] == 'CAPTURED' and receipt['attempts'] == 1
                and receipt['http_status'] == 200 and receipt['stored_bytes'] == len(body)
                and receipt['raw_sha256'] == sha256(body).hexdigest(), 'FIRST_CAPTURE_RECEIPT')
        require(stamp(window[-1]['close']) <= start <= end <= began and
                end.astimezone(ZoneInfo('America/New_York')).date().isoformat() == today,
                'FIRST_CAPTURE_CLOCK')
        if name == 'daily':
            requested_from=stamp(receipt['requested_from'])
            require(requested_from<=stamp(window[0]['open']) and
                    (stamp(window[0]['open'])-requested_from).total_seconds()<=8*86400,
                    'FIRST_REQUEST_WINDOW')
            expected=daily_url(entry['ticker'],requested_from,start)
        else: expected=URL
        require(receipt['url'] == expected, 'FIRST_CAPTURE_URL')
        received.append(end)
        include(prefix+name+'.response.bin', body); include(prefix+name+'.receipt.json', capture_files[name+'.receipt.json'])
    chart = json.loads(capture_files['daily.response.bin'])['chart']
    require(chart.get('error') is None and len(chart['result']) == 1, 'FIRST_SOURCE_SERIES')
    series = chart['result'][0]; meta = series['meta']
    require(meta['symbol'] == entry['ticker'] and meta['currency'] == 'USD'
            and meta['instrumentType'] == 'EQUITY', 'FIRST_SOURCE_IDENTITY')
    require(not any(series.get('events', {}).values()), 'WAIT_KNOWN_ACTION_REVIEW')
    timestamps = series['timestamp']; closes = series['indicators']['quote'][0]['close']
    adjusted = series['indicators']['adjclose'][0]['adjclose']
    require(len(timestamps) == len(closes) == len(adjusted), 'FIRST_SOURCE_LENGTH')
    prices = {}
    for timestamp, close, adj in zip(timestamps, closes, adjusted):
        require(datetime.fromtimestamp(timestamp, timezone.utc) <= received[0], 'FIRST_CURRENT_FUTURE_BAR')
        day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if day not in dates[window_start:index]: continue
        require(day not in prices and type(close) is not bool and close == adj and Fraction(str(close)) > 0,
                'WAIT_PRICE_OR_ADJUSTMENT_REVIEW')
        prices[day] = str(close)
    require(sorted(prices) == dates[window_start:index], 'FIRST_COMPLETE_MONTHLY_SESSIONS_REQUIRED')
    # Reuse raw action evidence, never the historical target's mark as a quote.
    overlaps = set(); prior_meta = []; excluded = []; receipt_bindings = []
    by_date = {row['date']: row for row in sessions}
    baseline_documents = {}
    for name in baseline['source_hashes']:
        try: baseline_documents[name] = json.loads(files[name])
        except (json.JSONDecodeError, UnicodeDecodeError): pass
    for name in baseline['source_hashes']:
        try: document = json.loads(files[name])
        except (json.JSONDecodeError, UnicodeDecodeError): continue
        if not isinstance(document, dict) or 'chart' not in document: continue
        matches = [(key, value) for key, value in baseline_documents.items()
                   if type(value) is dict and value.get('raw_path') == name
                   and value.get('raw_sha256') == sha256(files[name]).hexdigest()
                   and value.get('security_id') == sid and value.get('ticker') == entry['ticker']]
        require(len(matches) == 1, 'WAIT_BASELINE_RAW_RECEIPT')
        receipt_name, old_receipt = matches[0]
        old_received = stamp(old_receipt['received_at'])
        require(stamp(old_receipt['started_at']) <= old_received <= stamp(baseline['reviewed_at']) <= began
                and old_receipt['http_status'] == 200 and old_receipt['body_truncated'] is False
                and old_receipt['transport_error'] is None, 'FIRST_BASELINE_RECEIPT_TIME')
        expected_old_url = daily_url(entry['ticker'], stamp(old_receipt['requested_from']),
                                     stamp(old_receipt['requested_through']))
        require(old_receipt['url'] == expected_old_url == old_receipt['response_url']
                and old_receipt['interval'] == '1d'
                and stamp(old_receipt['requested_through']) <= old_received,
                'FIRST_BASELINE_RECEIPT_SOURCE')
        receipt_bindings.append(dict(raw_path=name, receipt_path=receipt_name, received_at=old_received.isoformat()))
        require(document['chart'].get('error') is None and len(document['chart']['result']) == 1, 'FIRST_BASELINE_SERIES')
        for old in document['chart']['result']:
            require(old['meta']['symbol'] == entry['ticker'] and old['meta']['currency'] == 'USD'
                    and old['meta']['instrumentType'] == 'EQUITY', 'FIRST_BASELINE_IDENTITY')
            prior_meta.append(old['meta'])
            require(old['meta'].get('exchangeName') == meta.get('exchangeName')
                    and bool(meta.get('exchangeName')), 'FIRST_EXCHANGE_CHANGED')
            require('timestamp' in old and 'indicators' in old, 'WAIT_BASELINE_RAW_PRICE_OVERLAP')
            old_closes = old['indicators']['quote'][0]['close']
            old_adjusted = old['indicators']['adjclose'][0]['adjclose']
            require(len(old['timestamp']) == len(old_closes) == len(old_adjusted), 'FIRST_BASELINE_LENGTH')
            seen_days = set()
            for ts, price, adjusted_price in zip(old['timestamp'], old_closes, old_adjusted):
                require(datetime.fromtimestamp(ts, timezone.utc) <= old_received, 'FIRST_BASELINE_FUTURE_BAR')
                day = datetime.fromtimestamp(ts, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                require(day not in seen_days, 'FIRST_BASELINE_DUPLICATE_DAY')
                seen_days.add(day)
                if day in prices:
                    require(day in by_date, 'FIRST_BASELINE_CALENDAR_GAP')
                    if stamp(by_date[day]['close']) > old_received:
                        excluded.append(dict(date=day, raw_path=name, receipt_path=receipt_name,
                            received_at=old_received.isoformat(), session_close=by_date[day]['close'],
                            reason='BAR_NOT_CLOSED_AT_ORIGINAL_RECEIPT'))
                        continue
                    require(type(price) is not bool and price == adjusted_price and Fraction(str(price)) > 0, 'WAIT_BASELINE_ADJUSTMENT_REVIEW')
                    require(Fraction(str(price)) == Fraction(prices[day]), 'WAIT_PRICE_CONTINUITY_REVIEW')
                    overlaps.add(day)
    require(overlaps, 'WAIT_BASELINE_RAW_PRICE_OVERLAP')
    feed = parse_official_feed(capture_files['official.response.bin'], observed_at=received[1])
    names = [meta[k] for k in ('longName','shortName') if isinstance(meta.get(k),str)]
    future_notice_scope = review_future_notice_scope(capture_files['official.response.bin'],
        feed=feed, ticker=entry['ticker'], issuer_names=names)
    units_name = prefix+'units.json'
    include(units_name, canonical(dict(status='CONDITIONAL_FIRST_WINDOW_REVIEWED',
        baseline_review=baseline['review_reference'], overlap_exact_dates=sorted(overlaps),
        baseline_overlap_semantics='ONLY_FIXED_CALENDAR_CLOSED_AT_ORIGINAL_RECEIPT',
        identity_closure_scope='CURRENT_SECURITY_REFERENCES_V1',
        future_notice_scope=future_notice_scope,
        identity_source_references=entry['identity']['source_references'],
        excluded_unclosed_baseline_bars=excluded, baseline_receipt_bindings=receipt_bindings,
        source_authenticated=False, coverage_complete=False, policy_approved=False,
        limitations='Finite public known-action checks may miss events.')))
    inputs = dict(signal_date=window[-1]['date'], observed_at=window[-1]['close'],
        session_dates=dates[:index], session_close_times=dict(review_reference=config['calendar']['path'],
            closes={s['date']:s['close'] for s in sessions[:index]}),
        base_target=dict(quantities={sid:proposal['payload']['proposed_target_quantities'].get(sid,0)},
            price_units={sid:baseline['unit']['current_price_basis']},
            origin_reference=proposal['proposal_id'],monthly_decision_date=epoch),
        histories={sid:dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            basis_id=baseline['unit']['current_price_basis'],currency='USD',unit_asof=window[-1]['date'],
            review_reference=units_name),source_reference=prefix+'daily.response.bin',
            closes=[dict(date=s['date'],close=prices[s['date']],completed_at=s['close']) for s in window])})
    monthly_name=prefix+'full-monthly-inputs.json';include(monthly_name,canonical(inputs))
    # Existing source aggregation consumes an exact 20-session view. Preserve
    # the complete reviewed window separately for the monthly peak policy.
    inputs=deepcopy(inputs)
    inputs['histories'][sid]['closes']=inputs['histories'][sid]['closes'][-20:]
    normalized_name=prefix+'normalized.json'; include(normalized_name,canonical(inputs))
    finished=stamp(clock())
    require(began<=finished<stamp(execution['close']),'FIRST_FINISH_CLOCK')
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',release_sha256=None,
        account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],
        normalization_reviewed=True,unresolved_units=[],pending_rights=[],
        normalized_inputs_path=normalized_name,monthly_history_inputs_path=monthly_name,market_asof=window[-1]['close'],
        research_observed_at_semantics='MARKET_ASOF_NOT_RECEIPT',source_received_at=max(received).isoformat(),
        available_at=finished.isoformat(),valid_from=max(finished,stamp(execution['open'])).isoformat(),
        valid_until=execution['close'],execution_session=execution,source_authenticated=False,coverage_complete=False,
        raw_source_paths=[prefix+n+'.response.bin' for n in ('daily','official')],
        source_sha256={name:sha256(body).hexdigest() for name,body in files.items()})
    return dict(status='FIRST_WINDOW_CONDITIONALLY_REVIEWED_POLICY_UNRELEASED',
                receipt=receipt,files=files,policy_approved=False,account_mutated=False)
