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
    require(not feed['channel']['future_publication'] and not any(r['future_publication'] for r in feed['items'])
            and not review_notices(capture_files['official.response.bin'], ticker=entry['ticker'], issuer_names=names)['blocking'],
            'WAIT_KNOWN_ACTION_REVIEW')
    units_name = prefix+'units.json'
    include(units_name, canonical(dict(status='CONDITIONAL_FIRST_WINDOW_REVIEWED',
        baseline_review=baseline['review_reference'], overlap_exact_dates=sorted(overlaps),
        baseline_overlap_semantics='ONLY_FIXED_CALENDAR_CLOSED_AT_ORIGINAL_RECEIPT',
        identity_closure_scope='CURRENT_SECURITY_REFERENCES_V1',
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
