"""Risk-only monthly collection/review for exited positions; not production mounted.

Uses original capture transport and all first-window data checks. Risk state is
explicitly hash-bound, while actual account quantities remain unchanged.
"""
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical, require
from data.monthly_risk_epoch import validate_monthly_epoch
from data.strategy_monthly_supplement_capture import capture_supplement

def prepare_risk_supplement_request(*, root, state, target, identity_reference,
                               calendar_reference, unit_source_paths, source_pins,
                               security_ids, decision_date, now, risk_state):
    """Build a stable request from server records, never browser ticker/price input."""
    from zoneinfo import ZoneInfo
    from data.strategy_monthly_risk_security_domain_v1 import plan_risk_security_domain
    from data.strategy_daily_rolling_parent_v3 import pinned
    from data.strategy_daily_session_capture import stamp
    domain = plan_risk_security_domain(root=root, state=state, target=target, risk_state=risk_state,
        identity_reference=identity_reference, source_paths=unit_source_paths)
    wanted = set(security_ids)
    require(bool(wanted) and wanted <= set(domain['securities']), 'SUPPLEMENT_REQUEST_DOMAIN')
    calendar = json.loads(pinned(root, calendar_reference, maximum=8*1024*1024))
    require(calendar['schema'] == 'FIXED_EXCHANGE_SESSIONS_V1' and
        calendar['exchange'] == 'NASDAQ', 'SUPPLEMENT_CALENDAR_SCHEMA')
    sessions = calendar['sessions']; dates = [row['date'] for row in sessions]
    require(dates == sorted(set(dates)), 'SUPPLEMENT_CALENDAR_DATES')
    current = stamp(now); today = current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if today not in dates:
        return dict(status='WAIT_SUPPLEMENT_SESSION', request=None)
    index = dates.index(today); session = sessions[index]
    if not stamp(session['open']) <= current < stamp(session['close']):
        return dict(status='WAIT_SUPPLEMENT_SESSION', request=None)
    validate_monthly_epoch(decision_date=decision_date, target_month=target['payload']['target_month'], session_dates=dates)
    require(index >= 20 and decision_date in dates and dates.index(decision_date) < index, 'SUPPLEMENT_MONTHLY_WINDOW')
    unresolved = sorted(sid for sid in wanted if domain['securities'][sid]['unit_baseline'] is None)
    if unresolved:
        return dict(status='WAIT_UNIT_BASELINE', request=None, unresolved=unresolved)
    start = min(index-20, dates.index(decision_date))
    binding = dict(account_id=state['account_id'], account_revision=state['revision'],
        target_id=target['target_id'], session=today)
    request = dict(account_id=state['account_id'], state_revision=state['revision'],
        window_start=sessions[start]['open'], observed_floor=session['open'],
        securities={sid: {'ticker': domain['securities'][sid]['ticker']} for sid in sorted(wanted)},
        current_target_quantities={sid: target['payload']['target_quantities'].get(sid, 0)
                                   for sid in sorted(wanted)})
    configurations = {sid: dict(schema='SERVER_RISK_DAILY_WINDOW_V7', security_id=sid,
        risk_state_sha256=sha256(canonical(risk_state)).hexdigest(),
        monthly_decision_date=decision_date, identity=identity_reference, calendar=calendar_reference,
        unit_source_paths=unit_source_paths, source_pins=source_pins) for sid in sorted(wanted)}
    return dict(status='SUPPLEMENT_REQUEST_PREPARED', binding=binding, request=request,
        configurations=configurations, domain=domain, policy_approved=False)


def review_risk_supplement_packets(*, root, capture, request, binding, state, target,
                              configurations, risk_state, clock=None):
    """Produce native reviewed SID packets without policy approval or publication.

    Configurations are supplied by the server, including pinned identity/baseline
    closure and fixed calendar. Original capture receipts remain in each closure.
    """
    from data.strategy_daily_first_window_v7 import review_first_window
    require(capture['status']=='CAPTURED_REVIEW_REQUIRED' and capture['binding']==binding and
        capture['capture_id']==sha256(canonical(dict(binding=binding,request=request))).hexdigest(),
        'SUPPLEMENT_REVIEW_BINDING')
    require(state['account_id']==binding['account_id'] and state['revision']==binding['account_revision'] and
        target['target_id']==binding['target_id'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    files=capture['files'];pins=capture['source_hashes'];documents=capture['documents']
    require(set(files)==set(pins) and sum(map(len,files.values()))<=128*1024*1024,'SUPPLEMENT_SOURCE_BUDGET')
    for name,raw in files.items():require(sha256(raw).hexdigest()==pins[name],'SUPPLEMENT_SOURCE_CHANGED')
    require(set(configurations)==set(documents['action_receipts'])==set(request['securities']),
        'SUPPLEMENT_PACKET_DOMAIN')
    rss=files[documents['rss_raw']];rss_receipt=json.loads(files[documents['rss_receipt']])
    packets={}
    for sid,configuration in configurations.items():
        require(configuration['security_id']==sid,'SUPPLEMENT_PACKET_IDENTITY')
        original=json.loads(files[documents['action_receipts'][sid]])
        require(original['security_id']==sid and original['ticker']==request['securities'][sid]['ticker'] and
            original['http_status']==200 and original['body_truncated'] is False and original['transport_error'] is None,
            'SUPPLEMENT_PACKET_RECEIPT')
        daily=files[original['raw_path']]
        require(original['raw_sha256']==sha256(daily).hexdigest() and rss_receipt['raw_sha256']==sha256(rss).hexdigest(),
            'SUPPLEMENT_PACKET_HASH')
        # Derived receipt fields are an adapter view of the saved original;
        # never replace its real request/receipt timestamps with the review time.
        daily_receipt=dict(status='CAPTURED',attempts=1,http_status=original['http_status'],
            stored_bytes=len(daily),raw_sha256=original['raw_sha256'],url=original['url'],
            requested_from=original['requested_from'],started_at=original['requested_through'],received_at=original['received_at'])
        official_receipt=dict(status='CAPTURED',attempts=1,http_status=rss_receipt['http_status'],
            stored_bytes=rss_receipt['stored_bytes'],raw_sha256=rss_receipt['raw_sha256'],url=rss_receipt['url'],
            started_at=rss_receipt['started_at'],received_at=rss_receipt['received_at'])
        raw=canonical(configuration)
        reviewed=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
            capture_files={'daily.response.bin':daily,'daily.receipt.json':canonical(daily_receipt),
                'official.response.bin':rss,'official.receipt.json':canonical(official_receipt)},
            state=state,target=target,risk_state=risk_state,clock=clock)
        require(reviewed.get('receipt') is not None,'SUPPLEMENT_REVIEW_FAILED:'+str(reviewed.get('reason')))
        closure=reviewed['files']
        for name,body in files.items():
            name='supplement-original/'+capture['capture_id']+'/'+name
            require(name not in closure or closure[name]==body,'SUPPLEMENT_SOURCE_COLLISION');closure[name]=body
        closure['supplement-original/'+capture['capture_id']+'/binding.json']=canonical(dict(binding=binding,request=request))
        require(len(closure)<=2000 and sum(map(len,closure.values()))<=32*1024*1024,'SUPPLEMENT_PACKET_BUDGET')
        receipt=dict(reviewed['receipt'],source_sha256={name:sha256(body).hexdigest() for name,body in closure.items()})
        receipt_raw=canonical(receipt)
        packets[sid]=dict(receipt_bytes=receipt_raw,trusted_receipt_sha256=sha256(receipt_raw).hexdigest(),files=closure)
    return dict(status='SUPPLEMENT_PACKETS_REVIEWED_POLICY_UNRELEASED',packets=packets,
                account_writes=False,policy_approved=False)

