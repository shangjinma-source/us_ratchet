"""Isolated full-domain source-content review for a saved frontier proposal.

The trusted review hash belongs to caller-owned research configuration, never
the same untrusted browser request. Native monthly quantities are never multiplied
by the historical split again; source consistency is not vendor authentication.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_v1 import replay
from docs.candidates.split_monthly_raw_history_20261105 import normalize_monthly_raw
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing
from data.monthly_risk_epoch import initial_completed_risk_session, validate_monthly_epoch
from data.saved_frontier_policy_archive import read_saved_frontier_policy
from data.strategy_daily_session_capture import stamp


def verify_native_units(*,state,target,archived,review,now):
    """Bind native target units to its real journal prefix and pinned training review."""
    from pathlib import Path
    from core.strategy_account_ledger import create_account
    from core.strategy_account_split_v1 import apply_event
    from data.saved_frontier_policy_archive import _read
    binding=target['payload']['decision']['payload']['input_binding']
    cursor=create_account(state['account_id']);anchor=None
    for row in state['events']:
        cursor,_=apply_event(cursor,row['payload'],expected_revision=cursor['revision'])
        if cursor['revision']==binding['account_revision']:anchor=deepcopy(cursor)
    require(cursor==state and anchor is not None,'NATIVE_TARGET_PREFIX_REQUIRED')
    require(anchor['account_id']==binding['account_id'] and anchor['shares']==binding['strategy_shares']
        and anchor['holdings_revision']==binding['holdings_revision']
        and anchor['total_uninvested_cash']==binding['total_uninvested_cash'],'NATIVE_TARGET_PREFIX_CHANGED')
    actions=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
    expected={a['security_id']:dict(action_sha256=sha256(canonical(a)).hexdigest(),unit_id=a['new_unit_id']) for a in actions}
    require(bool(actions) and len(expected)==len(actions) and binding.get('recorded_split_bindings')==expected,'NATIVE_TARGET_SPLIT_BINDING')
    require([r['payload'] for r in anchor['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']==actions,'NATIVE_NEW_ACTION_REQUIRES_TARGET')
    digest=binding['source_hashes']['split-monthly-training-review.json']
    raw=_read(Path(archived['archive_path'])/'sources'/(digest+'.bin'))
    require(sha256(raw).hexdigest()==digest,'NATIVE_TRAINING_REVIEW_CHANGED')
    training=json.loads(raw)
    require(training['schema']=='SPLIT_MONTHLY_TRAINING_UNITS_CONTENT_V1','NATIVE_TRAINING_REVIEW_SCHEMA')
    bundles=review['timing_bundles'];require(set(bundles)==set(training['actions'])=={a['action_id'] for a in actions},'NATIVE_TIMING_DOMAIN')
    values={}
    for action in actions:
        aid=action['action_id'];sid=action['security_id'];timing=bundles[aid]
        clocks=review_timing(action=action,timing=timing,now=now)
        record=training['actions'][aid]
        require(record['recorded_action_sha256']==expected[sid]['action_sha256'] and record['timing_sha256']==clocks['timing_sha256'],'NATIVE_TRAINING_TIMING_CHANGED')
        floor=max(stamp(clocks[k]) for k in ('quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at'))
        require(stamp(binding['valuation_at'])>=max(floor,stamp(action['broker_confirmed_at'])),'NATIVE_TARGET_PREDATES_UNITS')
        for row in state['events']:
            event=row['payload']
            if event['kind'] in {'FILL','DIRECT_FILL'}:
                esid=event.get('security_id') or state['orders'][event['order_id']]['security_id']
                require(esid!=sid or not(stamp(action['effective_at'])<=stamp(event['executed_at'])<max(stamp(clocks['quote_unit_effective_at']),stamp(clocks['broker_tradable_at']))),'NATIVE_FILL_RECONCILIATION_REQUIRED')
        values[sid]=dict(action=deepcopy(action),clocks=clocks,timing=deepcopy(timing))
    result=dict(target_id=target['target_id'],target_account_revision=anchor['revision'],current_account_revision=state['revision'],training_review_sha256=digest,securities=values)
    result['proof_sha256']=sha256(canonical(result)).hexdigest()
    return result


def validate_raw_schedule(*,sid,raw,normalization,unit,native,epoch_open):
    schedule=[];item=native['securities'].get(sid)
    if item:
        action,clocks=item['action'],item['clocks']
        require(unit['basis_id']==action['new_unit_id'] and stamp(epoch_open)>=stamp(clocks['quote_bar_boundary_at']),'NATIVE_EPOCH_OR_UNIT_CHANGED')
        series=json.loads(raw)['chart']['result'][0]
        days={datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat() for t in series['timestamp']}
        boundary=stamp(clocks['quote_bar_boundary_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if boundary in days:
            schedule=[dict(action_id=action['action_id'],security_id=sid,ratio=action['ratio'],old_unit_id=action['old_unit_id'],new_unit_id=action['new_unit_id'],quote_unit_effective_at=clocks['quote_bar_boundary_at'])]
        else:
            require(all(day>boundary for day in days),'NATIVE_RAW_MISSING_ACTION_BOUNDARY')
    require(normalization['split_schedule']==schedule and unit['corporate_actions']==schedule,'NATIVE_RAW_ACTION_SCHEDULE')


def verify_saved_frontier_daily_evidence(*, research_root, target_id, state, risk_state,
        review_bytes, trusted_review_sha256, files, now, enabled=False):
    require(type(enabled) is bool, 'FRONTIER_ENABLED_BOOLEAN')
    if not enabled:
        return dict(status='SAVED_FRONTIER_DAILY_DISABLED', production_admitted=False)
    archived = read_saved_frontier_policy(research_root=research_root, target_id=target_id)
    target, proposal = archived['target'], archived['proposal']
    state, previous = deepcopy(state), deepcopy(risk_state)
    require(replay(state['account_id'], [row['payload'] for row in state['events']]) == state,
            'FRONTIER_ACCOUNT_REPLAY')
    require(state['account_id'] == target['payload']['account_id'], 'FRONTIER_ACCOUNT_BINDING')
    require(type(review_bytes) is bytes and len(review_bytes) <= 1024*1024
            and sha256(review_bytes).hexdigest() == trusted_review_sha256, 'FRONTIER_REVIEW_HASH')
    review = json.loads(review_bytes)
    native=verify_native_units(state=state,target=target,archived=archived,review=review,now=now)
    require(review['schema'] == 'SPLIT_NATIVE_MONTH_DAILY_REVIEW_V1'
            and review['target_id'] == target_id and review['proposal_id'] == proposal['proposal_id']
            and review['account_id'] == state['account_id'] and review['account_revision'] == state['revision']
            and review['risk_state_sha256'] == sha256(canonical(previous)).hexdigest(), 'FRONTIER_REVIEW_BINDING')
    require(review['normalization_reviewed'] is True and review['unresolved_units'] == []
            and review['pending_rights'] == []
            and review['review_scope'] == 'FULL_WINDOW_NATIVE_POST_SPLIT_UNITS', 'FRONTIER_REVIEW_SCOPE')
    require(type(files) is dict, 'FRONTIER_SOURCE_DOMAIN')
    files = files.copy()
    pins = review['source_sha256']
    require(set(files) == set(pins) and 0 < len(files) <= 2000
            and all(type(raw) is bytes and len(raw) <= 8*1024*1024 for raw in files.values())
            and sum(map(len, files.values())) <= 32*1024*1024, 'FRONTIER_SOURCE_DOMAIN')
    require(all(sha256(raw).hexdigest() == pins[name] for name, raw in files.items()), 'FRONTIER_SOURCE_HASH')
    docs = review['documents']
    def document(name):
        require(name in files, 'FRONTIER_DOCUMENT_SOURCE_MISSING')
        return json.loads(files[name])
    calendar = document(docs['calendar'])
    require(calendar['schema'] == 'FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange'] == 'NASDAQ',
            'FRONTIER_CALENDAR_SCHEMA')
    from docs.candidates.split_calendar_extension_20261105 import validate_calendar_extension
    for item in native['securities'].values():
        validate_calendar_extension(pinned=item['timing']['calendar'],current=calendar)
    sessions = calendar['sessions']
    require(type(sessions) is list and 1 < len(sessions) <= 1000, 'FRONTIER_CALENDAR_BUDGET')
    dates = [row['date'] for row in sessions]
    require(dates == sorted(set(dates)), 'FRONTIER_CALENDAR_ORDER')
    for index, row in enumerate(sessions):
        require(date.fromisoformat(row['date']).isoformat() == row['date']
                and stamp(row['open']) < stamp(row['close'])
                and stamp(row['open']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                    == row['date'] == stamp(row['close']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                and (index == 0 or stamp(sessions[index-1]['close']) < stamp(row['open'])), 'FRONTIER_CALENDAR_SESSION')
    current = stamp(now)
    require(stamp(target['payload']['created_at']) <= current, 'FRONTIER_TARGET_CREATION_TIME')
    day = current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(day in dates and dates.index(day) > 0 and day[:7] == target['payload']['target_month'],
            'FRONTIER_CURRENT_MONTH_SESSION')
    index = dates.index(day)
    execution, completed = sessions[index], sessions[index-1]
    received, reviewed = stamp(review['source_received_at']), stamp(review['reviewed_at'])
    require(stamp(completed['close']) <= received <= reviewed <= current
            and max(stamp(execution['open']), reviewed) <= current < stamp(execution['close']),
            'FRONTIER_SOURCE_TIME')
    inputs = document(docs['normalized_inputs'])
    require(inputs['signal_date'] == completed['date']
            and stamp(inputs['observed_at']) == reviewed and inputs['session_dates'] == dates[:index]
            and inputs['session_close_times']['closes'] == {row['date']: row['close'] for row in sessions[:index]}
            and inputs['session_close_times']['review_reference'] == docs['calendar'], 'FRONTIER_FIXED_CALENDAR_BINDING')
    same_month = previous is not None and previous['target_month'] == target['payload']['target_month']
    if previous is not None:
        require(previous['schema'] == 'MONTHLY_PEAK_EXIT_V1' and previous['account_id'] == state['account_id']
                and set(previous['peaks']) == set(previous['unit_ids']) == set(previous['last_closes'])
                and set(previous['exited']) <= set(previous['peaks']), 'FRONTIER_PRIOR_RISK_BINDING')
    epoch = review['monthly_decision_date']
    validate_monthly_epoch(decision_date=epoch, target_month=target['payload']['target_month'], session_dates=dates)
    expected_epoch = previous['decision_date'] if same_month else initial_completed_risk_session(
        inputs=dict(inputs, base_target=dict(inputs['base_target'], monthly_target_created_at=target['payload']['created_at'])),
        target=target, now=current)
    require(epoch == expected_epoch and epoch <= completed['date'], 'FRONTIER_EPOCH_BINDING')
    proposed = proposal['payload']['proposed_target_quantities']
    needed = {sid for sid, quantity in proposed.items() if quantity}
    needed.update(sid for sid, quantity in state['shares'].items() if quantity)
    needed.update(order['security_id'] for order in state['orders'].values()
                  if order['status'] == 'OPEN' and order['remaining_quantity'] > 0)
    if previous is not None:
        needed.update(previous['peaks'])
        needed.update(previous['exited'])
    require(0 < len(needed) <= 250 and set(inputs['histories']) == needed
            and set(docs['raw_by_security']) == needed and set(docs['unit_reviews']) == needed,
            'FRONTIER_COMPLETE_REQUIRED_DOMAIN')
    quantities = {sid: proposed.get(sid, 0) for sid in sorted(needed)}
    base = inputs['base_target']
    require(base['origin_reference'] == proposal['proposal_id'] and base['quantities'] == quantities
            and base['monthly_decision_date'] == epoch and set(base['price_units']) == needed,
            'FRONTIER_PROPOSAL_BASE_BINDING')
    identity_document = document(docs['identities'])
    identities = identity_document['securities']
    require(identity_document['schema'] == 'SAVED_FRONTIER_REVIEWED_IDENTITIES_V1'
            and set(identities) == needed, 'FRONTIER_IDENTITY_DOMAIN')
    binding = target['payload']['decision']['payload']['input_binding']
    sources, hashes, normalizations = {}, {}, {}
    window = dates[dates.index(epoch):index]
    for sid in sorted(needed):
        identity = identities[sid]
        require(identity['security_id'] == sid and identity['currency'] == 'USD'
                and type(identity['ticker']) is str and identity['ticker']
                and type(identity['exchange']) is str and identity['exchange']
                and identity['identity_reviewed'] is True, 'FRONTIER_IDENTITY_REVIEW')
        refs = identity['source_hashes']
        require(bool(refs) and all(name in files and pins[name] == digest for name, digest in refs.items()),
                'FRONTIER_IDENTITY_SOURCES')
        mark = binding['marks'].get(sid)
        if mark is not None:
            require(mark['ticker'] == identity['ticker'], 'FRONTIER_ORIGINAL_TICKER_CHANGED')
        metadata = binding['search_arguments']['metadata'].get(sid)
        if metadata is not None:
            require(metadata['ticker'] == identity['ticker'] and metadata['issuer_id'] == identity['issuer_id'],
                    'FRONTIER_CANDIDATE_ISSUER_CHANGED')
        ledger_identities = [row['payload']['identity_evidence'] for row in state['events']
                            if row['payload'].get('identity_evidence', {}).get('security_id') == sid]
        for ledger_identity in ledger_identities:
            require(all(name in pins and pins[name] == digest
                        for name, digest in ledger_identity['source_hashes'].items()),
                    'FRONTIER_LEDGER_IDENTITY_SOURCE_MISSING')
        recorded = {row['ticker'] for row in ledger_identities}
        require(not recorded or recorded == {identity['ticker']}, 'FRONTIER_RECORDED_TICKER_CHANGED')
        raw_path, unit_path = docs['raw_by_security'][sid], docs['unit_reviews'][sid]
        raw, unit = files[raw_path], document(unit_path)
        sources[sid], hashes[sid] = raw, pins[raw_path]
        history = inputs['histories'][sid]
        require(unit['schema'] == 'SPLIT_NATIVE_MONTH_UNIT_REVIEW_V1'
                and unit['security_id'] == sid and unit['ticker'] == identity['ticker']
                and unit['target_id'] == target_id and unit['proposal_id'] == proposal['proposal_id']
                and unit['raw_sha256'] == hashes[sid] and unit['identity_sha256'] == pins[docs['identities']]
                and unit['currency'] == 'USD' and unit['basis_id'] == base['price_units'][sid]
                and unit['price_basis'] == binding['current_price_basis']
                and unit['unresolved_units'] == [] and unit['pending_rights'] == []
                and unit['native_unit_proof_sha256'] == native['proof_sha256'], 'FRONTIER_UNIT_REVIEW_BINDING')
        nr=unit['raw_normalization'];normalizations[sid]=nr
        require(nr['current_unit_id']==unit['basis_id'] and nr['captured_at']==review['source_received_at'],'NATIVE_RAW_UNIT_CAPTURE')
        validate_raw_schedule(sid=sid,raw=raw,normalization=nr,unit=unit,native=native,epoch_open=sessions[dates.index(epoch)]['open'])
        require(stamp(unit['covered_from']) <= stamp(sessions[dates.index(epoch)]['open'])
                and stamp(completed['close']) <= stamp(unit['covered_through']) <= received
                and received <= stamp(unit['reviewed_at']) <= reviewed, 'FRONTIER_FULL_UNIT_WINDOW')
        if same_month and sid in previous['unit_ids']:
            require(unit['basis_id'] == previous['unit_ids'][sid], 'FRONTIER_UNIT_MIGRATION_REQUIRED')
        require(history['units'] == dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            unit_asof=completed['date'], currency='USD', basis_id=unit['basis_id'], review_reference=unit_path)
            and history['source_reference'] == 'sha256:' + hashes[sid], 'FRONTIER_NORMALIZED_UNIT_BINDING')
        series = json.loads(raw)['chart']['result'][0]
        require(all(type(value) is int and datetime.fromtimestamp(value, timezone.utc) <= received
                    for value in series['timestamp']), 'FRONTIER_FUTURE_RAW_BAR')
        require([row['date'] for row in history['closes']] == window, 'FRONTIER_FULL_NORMALIZED_WINDOW')
    normalized = normalize_monthly_raw(inputs=inputs, sources=sources, expected_hashes=hashes, identities=identities, reviews=normalizations)
    require(normalized['inputs'] == inputs, 'FRONTIER_RAW_NORMALIZED_MISMATCH')
    result = dict(status='SPLIT_NATIVE_MONTH_DAILY_CONTENT_READY', native_unit_proof=deepcopy(native), source_target_id=target_id,
        proposal_id=proposal['proposal_id'], account_id=state['account_id'], account_revision=state['revision'],
        target_month=target['payload']['target_month'], inputs=deepcopy(inputs),
        proposed_target_quantities=deepcopy(proposed),
        required_security_ids=sorted(needed), source_receipt_id=trusted_review_sha256,
        source_hashes=deepcopy(pins), risk_state_sha256=review['risk_state_sha256'],
        observed_at=reviewed.isoformat(), available_at=reviewed.isoformat(),
        source_received_at=received.isoformat(),
        valid_from=max(stamp(execution['open']), reviewed).isoformat(), valid_until=execution['close'],
        source_authenticity_verified=False, production_admitted=False, account_mutated=False,
        target_mutated=False)
    result['content_id'] = sha256(canonical(result)).hexdigest()
    return result


def project_native_month_daily(*,research_root,risk_path,target_id,state,review_bytes,trusted_review_sha256,files,now,enabled=False):
    """Advance original risk rules using a native new-month target, never old split quantities."""
    from pathlib import Path
    from contextlib import closing
    import sqlite3
    from data.saved_frontier_policy_archive import _research_root
    from data.strategy_daily_session_capture import reject_links
    from data.monthly_peak_exit_store import MonthlyPeakExitStore
    from data.saved_frontier_exit_packet_v1 import apply_frontier_exit_packet
    from data.strategy_daily_rebound_archive import archive_rebound_evidence
    if not enabled:return dict(status='NATIVE_MONTH_DAILY_DISABLED',production_admitted=False)
    root=_research_root(research_root);path=Path(risk_path).resolve();reject_links(path)
    require(path.is_relative_to(root) and path.is_file() and path.stat().st_nlink==1,'NATIVE_RISK_ISOLATION')
    require(not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')),'NATIVE_RISK_NOT_QUIESCENT')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
        require(con.execute('PRAGMA quick_check').fetchall()==[('ok',)],'NATIVE_RISK_INTEGRITY')
    store=MonthlyPeakExitStore(path);previous=store.read(state['account_id'])
    admitted=verify_saved_frontier_daily_evidence(research_root=root,target_id=target_id,state=state,risk_state=previous,review_bytes=review_bytes,trusted_review_sha256=trusted_review_sha256,files=files,now=now,enabled=True)
    archived=read_saved_frontier_policy(research_root=root,target_id=target_id)
    epoch=admitted['inputs']['base_target']['monthly_decision_date']
    reset=epoch if previous is not None and previous['target_month']!=admitted['target_month'] else None
    result=apply_frontier_exit_packet(target=archived['target'],proposal=archived['proposal'],inputs=admitted['inputs'],risk_store=store,account_id=state['account_id'],decision_date=epoch,expected_previous_session=previous['session_date'] if previous else None,authorized_monthly_reset=reset)
    content=dict(files);proofpath='native-month/projection.json'
    require(proofpath not in content,'NATIVE_ARCHIVE_COLLISION')
    content[proofpath]=canonical(dict(admitted=admitted,risk_before=previous,risk_after=result['state']))
    policy='SPLIT_NATIVE_MONTH_CONTENT_ONLY_V1'
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',policy_id=policy,target_id=target_id,proposal_id=admitted['proposal_id'],account_id=state['account_id'],account_revision=state['revision'],source_sha256={k:sha256(v).hexdigest() for k,v in content.items()},valid_from=admitted['valid_from'],valid_until=admitted['valid_until'],source_authenticity_verified=False,production_admitted=False)
    archive=archive_rebound_evidence(root=root/'native-daily-evidence',receipt_bytes=canonical(receipt),files=content)
    signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target_id,proposal_id=admitted['proposal_id'],policy_id=policy,evidence_id=archive['receipt_sha256'],evidence_archive=archive,effective_target_quantities=result['effective_target_quantities'],observed_at=admitted['observed_at'],available_at=admitted['available_at'],valid_from=admitted['valid_from'],valid_until=admitted['valid_until'])
    return dict(status='DAILY_SIGNAL_READY',signal=signal,evidence_archive=archive,native_unit_proof=admitted['native_unit_proof'],production_admitted=False)
