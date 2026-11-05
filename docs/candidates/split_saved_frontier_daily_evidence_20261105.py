# Complete isolated derivative; original source SHA256 17f9c6851e986cc70a6622a038e9db89f9f4cac2d0de5507a97c8e6b04ffab91
"""Isolated split-aware full-domain source-content review for a saved frontier proposal.

The trusted review hash belongs to caller-owned research configuration, never
the same untrusted browser request. Explicit reviewed split units are projected
through the existing normalizer; content consistency is not vendor authenticity
or a live release. Distinct distribution/quote clocks remain unimplemented.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_v1 import replay
from data.strategy_split_native_projection_v1 import project_native_split
from docs.candidates.split_monthly_raw_history_20261105 import normalize_monthly_raw
from data.monthly_risk_epoch import initial_completed_risk_session, validate_monthly_epoch
from data.saved_frontier_policy_archive import read_saved_frontier_policy
from data.strategy_daily_session_capture import stamp


def verify_transition_ancestry(*, state, transition, risk_before, target, proposal_id):
    """Authenticate the immutable preparation at a real prefix of this journal."""
    from core.strategy_account_ledger import create_account
    from core.strategy_account_split_v1 import apply_event
    cursor=create_account(state['account_id']);anchor=None;anchored=False
    for row in state['events']:
        if anchored:
            require(row['payload']['kind'] != 'SPLIT_CONFIRMED', 'SPLIT_NEW_ACTION_REQUIRES_PREPARATION')
        cursor,_=apply_event(cursor,row['payload'],expected_revision=cursor['revision'])
        if cursor['revision']==transition['payload']['account_revision']:
            anchor=deepcopy(cursor);anchored=True
    require(cursor==state and anchor is not None,'SPLIT_PREPARATION_ANCESTRY_MISMATCH')
    require(transition==project_native_split(account_after=anchor,
        action_id=transition['payload']['action_id'],risk_before=risk_before,target=target,
        expected_proposal_id=proposal_id),'RAW_NATIVE_TRANSITION_CHANGED')
    return anchor


def verify_saved_frontier_daily_evidence(*, research_root, target_id, state, risk_state,
        review_bytes, trusted_review_sha256, files, now, transition, risk_before, enabled=False):
    require(type(enabled) is bool, 'FRONTIER_ENABLED_BOOLEAN')
    if not enabled:
        return dict(status='SAVED_FRONTIER_DAILY_DISABLED', production_admitted=False)
    archived = read_saved_frontier_policy(research_root=research_root, target_id=target_id)
    target, proposal = archived['target'], archived['proposal']
    verify_transition_ancestry(state=state,transition=transition,risk_before=risk_before,target=target,proposal_id=proposal['proposal_id'])
    action = next(r['payload'] for r in state['events'] if r['payload'].get('action_id') == transition['payload']['action_id'])
    state, previous = deepcopy(state), deepcopy(risk_state)
    require(replay(state['account_id'], [row['payload'] for row in state['events']]) == state,
            'FRONTIER_ACCOUNT_REPLAY')
    require(state['account_id'] == target['payload']['account_id'], 'FRONTIER_ACCOUNT_BINDING')
    require(type(review_bytes) is bytes and len(review_bytes) <= 1024*1024
            and sha256(review_bytes).hexdigest() == trusted_review_sha256, 'FRONTIER_REVIEW_HASH')
    review = json.loads(review_bytes)
    if 'source_received_by_security' in review:
        received_map=review['source_received_by_security']
        require(set(received_map)==set(review['documents']['raw_by_security']) and
            max(map(stamp,received_map.values()))==stamp(review['source_received_at']), 'RAW_CAPTURE_RECEIPT_DOMAIN')
    clocks = review['action_clocks']
    require(clocks['distribution_at'] == clocks['quote_unit_effective_at'] == action['effective_at']
        and stamp(action['broker_confirmed_at']) <= stamp(now)
        and stamp(clocks['broker_tradable_at']) >= stamp(action['broker_confirmed_at'])
        and stamp(clocks['broker_tradable_at']) <= stamp(now), 'SPLIT_DISTINCT_CLOCKS_NOT_YET_SUPPORTED')
    require(review['schema'] == 'SPLIT_SAVED_FRONTIER_DAILY_REVIEW_V1'
            and review['transition_id'] == transition['transition_id']
            and review['target_id'] == target_id and review['proposal_id'] == proposal['proposal_id']
            and review['account_id'] == state['account_id'] and review['account_revision'] == state['revision']
            and review['risk_state_sha256'] == sha256(canonical(previous)).hexdigest(), 'FRONTIER_REVIEW_BINDING')
    require(review['normalization_reviewed'] is True and review['unresolved_units'] == []
            and review['pending_rights'] == []
            and review['review_scope'] == 'FULL_WINDOW_EXPLICIT_SPLIT_UNITS', 'FRONTIER_REVIEW_SCOPE')
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
    proposed = transition['payload']['risk_projection']['target_quantities']
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
        require(unit['schema'] == 'SPLIT_SAVED_FRONTIER_UNIT_REVIEW_V1'
                and unit['security_id'] == sid and unit['ticker'] == identity['ticker']
                and unit['target_id'] == target_id and unit['proposal_id'] == proposal['proposal_id']
                and unit['raw_sha256'] == hashes[sid] and unit['identity_sha256'] == pins[docs['identities']]
                and unit['currency'] == 'USD' and unit['basis_id'] == base['price_units'][sid]
                and unit['price_basis'] == binding['current_price_basis']
                and unit['unresolved_units'] == [] and unit['pending_rights'] == []
                and unit['transition_id'] == transition['transition_id'], 'FRONTIER_UNIT_REVIEW_BINDING')
        normalizations[sid] = unit['raw_normalization']
        nr = normalizations[sid]
        require(nr['current_unit_id'] == unit['basis_id'] and nr['captured_at'] == review.get('source_received_by_security', {}).get(sid, review['source_received_at']), 'RAW_UNIT_CAPTURE_BINDING')
        expected_schedule = []
        if sid == action['security_id']:
            expected_schedule = [dict(action_id=action['action_id'], security_id=sid, ratio=action['ratio'],
                old_unit_id=action['old_unit_id'], new_unit_id=action['new_unit_id'], quote_unit_effective_at=action['effective_at'])]
        require(nr['split_schedule'] == expected_schedule and unit['corporate_actions'] == expected_schedule, 'RAW_RECORDED_ACTION_CLOCK_BINDING')
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
    result = dict(status='SPLIT_SAVED_FRONTIER_DAILY_CONTENT_READY', transition_id=transition['transition_id'],
        transition=deepcopy(transition), observations=deepcopy(normalized['observations']), source_target_id=target_id,
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


def project_split_frontier_daily(*, research_root, risk_path, target_id, state,
        review_bytes, trusted_review_sha256, files, now, enabled=False):
    """Read a real prepared risk database and archive the actual derived signal.

    No authentication is granted by this isolated content pipeline. The database
    must come from prepare_split_risk; ordinary/live risk databases are rejected.
    """
    from contextlib import closing
    from pathlib import Path
    import sqlite3
    from data.saved_frontier_policy_archive import _research_root
    from data.strategy_daily_session_capture import reject_links
    from data.monthly_peak_exit_store import MonthlyPeakExitStore
    from data.strategy_daily_rebound_archive import archive_rebound_evidence
    if not enabled:
        return dict(status='SPLIT_FRONTIER_DISABLED', production_admitted=False)
    root = _research_root(research_root)
    path = Path(risk_path).resolve();reject_links(path)
    require(path.is_relative_to(root) and path.is_file() and path.stat().st_nlink == 1,
            'SPLIT_PREPARED_RISK_ISOLATION')
    require(not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal')),
            'SPLIT_RISK_NOT_QUIESCENT')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as connection:
        require(connection.execute('PRAGMA quick_check').fetchall()==[('ok',)], 'SPLIT_RISK_DATABASE_INTEGRITY')
        raw,digest=connection.execute('SELECT payload,digest FROM split_preparation WHERE singleton=1').fetchone()
    require(sha256(raw.encode()).hexdigest()==digest,'SPLIT_PREPARATION_CHANGED')
    preparation=json.loads(raw);transition=preparation['transition'];before=preparation['original_risk_state']
    store=MonthlyPeakExitStore(path);previous=store.read(state['account_id'])
    require(previous is not None,'SPLIT_PREPARED_RISK_REQUIRED')
    admitted=verify_saved_frontier_daily_evidence(research_root=root,target_id=target_id,state=state,
        risk_state=previous,review_bytes=review_bytes,trusted_review_sha256=trusted_review_sha256,
        files=files,now=now,transition=transition,risk_before=before,enabled=True)
    observations=admitted['observations'];baseline=admitted['inputs']['base_target']['quantities']
    result=store.advance(account_id=state['account_id'],expected_previous_session=previous['session_date'],
        observations=observations,baseline_targets=baseline,target_month=admitted['target_month'])
    require(set(previous['exited'])<=set(result['state']['exited']),'SPLIT_PRIOR_EXIT_LOST')
    extra={sid:0 for sid,q in state['shares'].items() if q==0 and sid not in baseline}
    effective=dict(result['effective_target_quantities'],**extra)
    proof=dict(admitted=admitted,risk_before=previous,risk_after=result['state'],transition=transition,
        original_risk_state=before,production_admitted=False)
    content=dict(files);content['split-frontier/projection.json']=canonical(proof)
    require('split-frontier/projection.json' not in files,'SPLIT_ARCHIVE_COLLISION')
    policy='SPLIT_SAVED_FRONTIER_CONTENT_ONLY_V1'
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',policy_id=policy,
        target_id=target_id,proposal_id=admitted['proposal_id'],account_id=state['account_id'],
        account_revision=state['revision'],source_sha256={k:sha256(v).hexdigest() for k,v in content.items()},
        valid_from=admitted['valid_from'],valid_until=admitted['valid_until'],source_authenticity_verified=False,
        production_admitted=False,transition_id=transition['transition_id'])
    archive=archive_rebound_evidence(root=root/'split-daily-evidence',receipt_bytes=canonical(receipt),files=content)
    signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target_id,
        proposal_id=admitted['proposal_id'],policy_id=policy,evidence_id=archive['receipt_sha256'],
        evidence_archive=archive,effective_target_quantities=effective,transition_id=transition['transition_id'],
        observed_at=admitted['observed_at'],available_at=admitted['available_at'],
        valid_from=admitted['valid_from'],valid_until=admitted['valid_until'])
    return dict(status='DAILY_SIGNAL_READY',signal=signal,evidence_archive=archive,
        transition=transition,original_risk_state=before,production_admitted=False)
