"""Isolated full-domain source-content review for a saved frontier proposal.

The trusted review hash belongs to caller-owned research configuration, never
the same untrusted browser request. Constant units without corporate actions
only; source consistency is not independent vendor authenticity or live release.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, replay, require
from data.monthly_peak_raw_history import normalize_monthly_raw
from data.monthly_risk_epoch import initial_completed_risk_session, validate_monthly_epoch
from data.saved_frontier_policy_archive import read_saved_frontier_policy
from data.strategy_daily_session_capture import stamp


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
    require(review['schema'] == 'SAVED_FRONTIER_DAILY_REVIEW_V1'
            and review['target_id'] == target_id and review['proposal_id'] == proposal['proposal_id']
            and review['account_id'] == state['account_id'] and review['account_revision'] == state['revision']
            and review['risk_state_sha256'] == sha256(canonical(previous)).hexdigest(), 'FRONTIER_REVIEW_BINDING')
    require(review['normalization_reviewed'] is True and review['unresolved_units'] == []
            and review['pending_rights'] == []
            and review['review_scope'] == 'FULL_WINDOW_CONSTANT_UNITS_NO_ACTIONS', 'FRONTIER_REVIEW_SCOPE')
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
    sources, hashes = {}, {}
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
        require(unit['schema'] == 'SAVED_FRONTIER_CONSTANT_UNIT_REVIEW_V1'
                and unit['security_id'] == sid and unit['ticker'] == identity['ticker']
                and unit['target_id'] == target_id and unit['proposal_id'] == proposal['proposal_id']
                and unit['raw_sha256'] == hashes[sid] and unit['identity_sha256'] == pins[docs['identities']]
                and unit['currency'] == 'USD' and unit['basis_id'] == base['price_units'][sid]
                and unit['price_basis'] == binding['current_price_basis']
                and unit['unresolved_units'] == [] and unit['pending_rights'] == []
                and unit['corporate_actions'] == [], 'FRONTIER_UNIT_REVIEW_BINDING')
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
    normalized = normalize_monthly_raw(inputs=inputs, sources=sources, expected_hashes=hashes, identities=identities)
    require(normalized['inputs'] == inputs, 'FRONTIER_RAW_NORMALIZED_MISMATCH')
    result = dict(status='SAVED_FRONTIER_DAILY_EVIDENCE_READY', source_target_id=target_id,
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
