"""Durable, snapshot-bound full-window source capture; never approves a signal.

The server supplies reviewed identities and a fixed monthly window request.
Existing daily terminals are untouched. Publication still requires source review.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from data.monthly_risk_epoch import validate_monthly_epoch
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_daily_session_capture import reject_links


def prepare_supplement_request(*, root, state, target, identity_reference,
                               calendar_reference, unit_source_paths, source_pins,
                               security_ids, decision_date, now):
    """Build a stable request from server records, never browser ticker/price input."""
    from zoneinfo import ZoneInfo
    from data.strategy_daily_security_domain_v1 import plan_security_domain
    from data.strategy_daily_rolling_parent_v3 import pinned
    from data.strategy_daily_session_capture import stamp
    domain = plan_security_domain(root=root, state=state, target=target,
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
    configurations = {sid: dict(schema='SERVER_FIRST_DAILY_WINDOW_V6', security_id=sid,
        monthly_decision_date=decision_date, identity=identity_reference, calendar=calendar_reference,
        unit_source_paths=unit_source_paths, source_pins=source_pins) for sid in sorted(wanted)}
    return dict(status='SUPPLEMENT_REQUEST_PREPARED', binding=binding, request=request,
        configurations=configurations, domain=domain, policy_approved=False)


def capture_supplement(*, directory, request, binding, read_binding,
                       execute=False, fetch_daily=None, fetch_official=None, clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    require(set(binding)=={'account_id','account_revision','target_id','session'},'SUPPLEMENT_BINDING_FIELDS')
    require(request['account_id']==binding['account_id'] and
            request['state_revision']==binding['account_revision'],'SUPPLEMENT_ACCOUNT_BINDING')
    require(read_binding()==binding,'SUPPLEMENT_SNAPSHOT_CHANGED')
    intent=dict(binding=binding,request=request)
    identifier=sha256(canonical(intent)).hexdigest()
    base=Path(directory).resolve();reject_links(directory)
    folder=base/identifier;reject_links(folder)
    def save(name,raw):
        with (folder/name).open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
    def check():
        require(read_binding()==binding,'SUPPLEMENT_SNAPSHOT_CHANGED')
        observed=clock()
        from zoneinfo import ZoneInfo
        require(observed.tzinfo is not None and observed.astimezone(ZoneInfo('America/New_York')).date().isoformat()==binding['session'],
                'SUPPLEMENT_SESSION_CHANGED')
        return observed
    check()
    if folder.exists():
        if not (folder/'intent.json').exists():
            return dict(status='NEEDS_RECOVERY',capture_id=identifier,account_writes=False)
        require((folder/'intent.json').read_bytes()==canonical(intent),'SUPPLEMENT_INTENT_CHANGED')
        if not (folder/'complete.json').exists():
            return dict(status='NEEDS_RECOVERY',capture_id=identifier,account_writes=False)
        receipt=json.loads((folder/'complete.json').read_bytes())
        files={}
        for name,digest in receipt['source_hashes'].items():
            require(len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'SUPPLEMENT_HASH_INVALID')
            path=folder/(digest+'.bin');reject_links(path);raw=path.read_bytes()
            require(sha256(raw).hexdigest()==digest,'SUPPLEMENT_SOURCE_CHANGED');files[name]=raw
        check()
        return dict(receipt,files=files,reused=True)
    if not execute:return dict(status='DRY_RUN',capture_id=identifier,account_writes=False)
    base.mkdir(parents=True,exist_ok=True)
    try:folder.mkdir()
    except FileExistsError:return dict(status='NEEDS_RECOVERY',capture_id=identifier,account_writes=False)
    save('intent.json',canonical(intent));transport_count=0
    def transport(callback):
        def call(*args):
            nonlocal transport_count
            started=check();transport_count+=1
            response=callback(*args);received=clock();raw=response.get('body')
            # Preserve received bytes even when validation subsequently fails.
            if type(raw)is bytes:
                require(len(raw)<=8*1024*1024,'SUPPLEMENT_SOURCE_TOO_LARGE')
                save('transport-%03d.bin'%transport_count,raw)
                save('transport-%03d.json'%transport_count,canonical(dict(started_at=started.isoformat(),
                    received_at=received.isoformat(),status=response.get('status'),sha256=sha256(raw).hexdigest())))
            check();return response
        return call
    try:
        sources=PaperActionEvidenceSources(clock=clock)
        sources.fetch=transport(fetch_daily or sources.fetch)
        sources.rss_fetch=transport(fetch_official or sources.rss_fetch)
        captured=sources.capture(request);check()
        for name,raw in captured['files'].items():
            digest=captured['source_hashes'][name]
            require(sha256(raw).hexdigest()==digest,'SUPPLEMENT_SOURCE_CHANGED')
            if not (folder/(digest+'.bin')).exists():save(digest+'.bin',raw)
        receipt=dict(status='CAPTURED_REVIEW_REQUIRED',capture_id=identifier,binding=binding,
            source_hashes=captured['source_hashes'],documents=captured['documents'],
            finished_at=check().isoformat(),account_writes=False,policy_approved=False)
        save('complete.json',canonical(receipt))
        return dict(receipt,files=captured['files'],reused=False)
    except Exception as error:
        save('failed.json',canonical(dict(reason=str(error),at=clock().isoformat(),automatic_retry=False)))
        raise


def review_supplement_packets(*, root, capture, request, binding, state, target,
                              configurations, clock=None):
    """Produce native reviewed SID packets without policy approval or publication.

    Configurations are supplied by the server, including pinned identity/baseline
    closure and fixed calendar. Original capture receipts remain in each closure.
    """
    from data.strategy_daily_first_window_v6 import review_first_window
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
            state=state,target=target,clock=clock)
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


def merge_supplement_packets(*, existing, supplements, state, target, now):
    """Merge complete account evidence; no writes, policy release or partial signal."""
    from fractions import Fraction
    from data.strategy_daily_security_domain_v1 import aggregate_security_packets
    needed={sid for sid,q in target['payload']['target_quantities'].items() if q>0}
    needed.update(sid for sid,q in state['shares'].items() if q>0)
    needed.update(order['security_id'] for order in state['orders'].values()
        if order['status']=='OPEN' and order['remaining_quantity']>0)
    require(set(supplements)<=needed,'SUPPLEMENT_UNEXPECTED_SECURITY')
    def history(packet,sid):
        raw=packet['receipt_bytes'];require(sha256(raw).hexdigest()==packet['trusted_receipt_sha256'],'SUPPLEMENT_PARENT_HASH')
        receipt=json.loads(raw)
        require(set(receipt['source_sha256'])==set(packet['files']),'SUPPLEMENT_PARENT_DOMAIN')
        for name,digest in receipt['source_sha256'].items():
            require(sha256(packet['files'][name]).hexdigest()==digest,'SUPPLEMENT_PARENT_SOURCE_CHANGED')
        inputs=json.loads(packet['files'][receipt['normalized_inputs_path']])
        return receipt,inputs['histories'][sid]
    packets={sid:packet for sid,packet in existing.items() if sid in needed}
    for sid,packet in supplements.items():
        new_receipt,new=history(packet,sid)
        if sid in packets:
            old_receipt,old=history(packets[sid],sid)
            require(old_receipt['execution_session']==new_receipt['execution_session'],'SUPPLEMENT_SESSION_CONFLICT')
            require(old['units']['basis_id']==new['units']['basis_id'],'SUPPLEMENT_UNITS_CONFLICT')
            before={r['date']:r['close'] for r in old['closes']};after={r['date']:r['close'] for r in new['closes']}
            require(set(before)==set(after) and all(Fraction(before[d])==Fraction(after[d]) for d in before),
                'SUPPLEMENT_PRICE_CONFLICT')
        packets[sid]=packet
    domain=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],
        securities={sid:{} for sid in needed})
    result=aggregate_security_packets(domain=domain,packets=packets,state=state,target=target,now=now)
    if result.get('receipt') is None:return result
    monthly={}
    for sid,packet in packets.items():
        receipt=json.loads(packet['receipt_bytes']);name=receipt.get('monthly_history_inputs_path')
        if name:
            require(name in result['files'],'SUPPLEMENT_MONTHLY_HISTORY_LOST')
            monthly[sid]=dict(path=name,sha256=sha256(result['files'][name]).hexdigest())
    result['receipt']['monthly_history_inputs']=monthly
    result['policy_approved']=False
    return result


def restore_reviewed_monthly_history(*, receipt, files, decision_date):
    """Restore full monthly rows from a source-admitted receipt, never raw quotes.

    The caller authenticates the receipt and source-review authorization first.
    Hash, calendar, unit and overlapping-price checks remain mandatory here.
    """
    from copy import deepcopy
    from fractions import Fraction
    references=receipt.get('monthly_history_inputs',{})
    def read(path,digest=None):
        raw=files[path]
        require(sha256(raw).hexdigest()==receipt['source_sha256'][path] and
            (digest is None or sha256(raw).hexdigest()==digest),'SUPPLEMENT_MONTHLY_SOURCE_CHANGED')
        return json.loads(raw)
    inputs=deepcopy(read(receipt['normalized_inputs_path']))
    if receipt.get('full_domain_inputs_path'):
        domain=read(receipt['full_domain_inputs_path'])
        require(all(domain[key]==inputs[key] for key in
            ('signal_date','observed_at','session_dates','session_close_times')),
            'SUPPLEMENT_MONTHLY_CALENDAR_CHANGED')
        # Full-domain history predates account rebinding. Keep the freshly
        # verified target origin/quantities, while restoring held/order histories.
        for sid,history in inputs['histories'].items():
            require(domain['histories'].get(sid)==history,'SUPPLEMENT_MONTHLY_DOMAIN_CHANGED')
        inputs['histories']=deepcopy(domain['histories'])
        inputs['base_target']['price_units']={sid:history['units']['basis_id']
            for sid,history in inputs['histories'].items()}
    require(set(references)<=set(inputs['histories']),'SUPPLEMENT_MONTHLY_DOMAIN_CHANGED')
    for sid,reference in references.items():
        full=read(reference['path'],reference['sha256'])
        require(set(full['histories'])=={sid} and full['signal_date']==inputs['signal_date'] and
            full['session_dates']==inputs['session_dates'] and full['session_close_times']==inputs['session_close_times'] and
            full['base_target']['monthly_decision_date']==decision_date,'SUPPLEMENT_MONTHLY_CALENDAR_CHANGED')
        original=inputs['histories'][sid];extended=full['histories'][sid]
        require(original['units']==extended['units'],'SUPPLEMENT_MONTHLY_UNITS_CHANGED')
        before={row['date']:row for row in original['closes']};after={row['date']:row for row in extended['closes']}
        require(len(after)==len(extended['closes']) and set(before)<=set(after) and
            all(Fraction(before[d]['close'])==Fraction(after[d]['close']) and
                before[d]['completed_at']==after[d]['completed_at'] for d in before),
            'SUPPLEMENT_MONTHLY_PRICE_CHANGED')
        inputs['histories'][sid]=deepcopy(extended)
    return inputs


def review_supplement_policy(*, decision_date, **arguments):
    """Keep authenticated monthly references through complete-domain policy review.

    Server authorization and publication remain the caller's responsibility.
    Existing policy/source verification is performed before restoring any rows.
    """
    from data.strategy_daily_domain_policy_review_v1 import review_domain_policy
    from data.strategy_daily_signal_verifier import verify_daily_signal_bundle
    result = review_domain_policy(**arguments)
    if result.get('receipt') is None:
        return result
    references = {}
    for sid, packet in result['packets'].items():
        parent = json.loads(packet['receipt_bytes'])
        name = parent.get('monthly_history_inputs_path')
        if name is not None:
            require(name in result['files'] and
                result['receipt']['source_sha256'].get(name) == parent['source_sha256'].get(name),
                'SUPPLEMENT_MONTHLY_HISTORY_LOST')
            references[sid] = dict(path=name, sha256=parent['source_sha256'][name])
    result['receipt']['monthly_history_inputs'] = references
    restore_reviewed_monthly_history(receipt=result['receipt'], files=result['files'],
        decision_date=decision_date)
    raw = canonical(result['receipt'])
    verified = verify_daily_signal_bundle(
        state=arguments['state'], target=arguments['target'], now=arguments['now'],
        release_bytes=arguments['release_bytes'],
        trusted_release_sha256=arguments['trusted_release_sha256'],
        receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(),
        files=result['files'], calendar_bytes=arguments['calendar_bytes'])
    require(verified['status'] == 'DAILY_SIGNAL_READY', 'SUPPLEMENT_POLICY_VERIFICATION_REQUIRED')
    result['receipt_sha256'] = sha256(raw).hexdigest()
    return result
