"""Deterministic same-session rebinding of server-reviewed evidence.

Only account revision and monthly quantities change. Price history, units, raw
receipt time and policy approval remain unchanged. New securities/dates require
new evidence. Caller supplies the current real server clock, never browser time.
"""
from copy import deepcopy
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, replay
from core.strategy_account_difference import require, timestamp, quantities
from data.strategy_daily_evidence_adapter import SavedDailyEvidenceAdapter


class SameSessionDailyEvidenceProducer:
    """Server-only saved source reader; emits bytes in memory, never approvals."""
    def __init__(self, *, root, parent_receipt_path, trusted_parent_sha256, source_paths):
        self.reader = SavedDailyEvidenceAdapter(root=root)
        self.parent_path = parent_receipt_path
        self.parent_sha = trusted_parent_sha256
        self.source_paths = dict(source_paths)

    def prepare(self, state, target, now):
        require(len(self.source_paths) <= 2000, 'PARENT_SOURCE_DOMAIN_OR_BUDGET')
        files = {}
        total = 0
        for name, path in self.source_paths.items():
            raw = self.reader._read(path)
            total += len(raw)
            require(total <= 32 * 1024 * 1024, 'PARENT_SOURCE_DOMAIN_OR_BUDGET')
            files[name] = raw
        return rebind_reviewed_daily_evidence(
            receipt_bytes=self.reader._read(self.parent_path),
            trusted_receipt_sha256=self.parent_sha, files=files,
            state=state, target=target, now=now.isoformat())


def rebind_reviewed_daily_evidence(*, receipt_bytes, trusted_receipt_sha256,
                                  files, state, target, now):
    require(type(receipt_bytes) is bytes and sha256(receipt_bytes).hexdigest() ==
            trusted_receipt_sha256, 'PARENT_DAILY_RECEIPT_HASH_MISMATCH')
    parent = json.loads(receipt_bytes)
    require(parent.get('schema') == 'SERVER_REVIEWED_DAILY_EVIDENCE_V1'
            and parent.get('normalization_reviewed') is True
            and parent.get('unresolved_units') == [] and parent.get('pending_rights') == [],
            'REVIEWED_PARENT_EVIDENCE_REQUIRED')
    pins = parent['source_sha256']
    require(type(files) is dict and set(files) == set(pins) and len(files) <= 2000
            and all(type(raw) is bytes for raw in files.values())
            and sum(map(len, files.values())) <= 32 * 1024 * 1024,
            'PARENT_SOURCE_DOMAIN_OR_BUDGET')
    require(all(sha256(raw).hexdigest() == pins[name] for name, raw in files.items()),
            'PARENT_SOURCE_HASH_MISMATCH')
    current = timestamp(now)
    require(current >= timestamp(parent['available_at']), 'REBIND_CLOCK_BEFORE_PARENT_REVIEW')
    require(replay(state['account_id'], [e['payload'] for e in state['events']]) == state,
            'ACCOUNT_REPLAY_MISMATCH')
    require(state['account_id'] == parent['account_id'] ==
            target['payload']['account_id'], 'REBIND_ACCOUNT_MISMATCH')
    require(sha256(canonical(target['payload'])).hexdigest() == target['target_id'],
            'REBIND_TARGET_HASH_MISMATCH')
    decision = target['payload']['decision']
    require(sha256(canonical(decision['payload'])).hexdigest() == decision['decision_id']
            and decision['payload']['target_quantities'] == target['payload']['target_quantities'],
            'REBIND_TARGET_DECISION_MISMATCH')
    require(sha256(canonical(decision['payload']['input_binding'])).hexdigest() ==
            decision['payload'].get('input_id'), 'REBIND_TARGET_INPUT_MISMATCH')

    def waiting(reason):
        return dict(status=reason, receipt=None, files=None, account_mutated=False,
                    policy_approved=False)

    session = parent['execution_session']
    ny_date = current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if ny_date != session['date'] or current >= timestamp(session['close']):
        return waiting('WAIT_NEW_SESSION_EVIDENCE')
    if target['payload']['target_month'] != ny_date[:7]:
        return waiting('WAIT_MONTHLY_TARGET')
    inputs = json.loads(files[parent['normalized_inputs_path']])
    monthly = quantities(target['payload']['target_quantities'])
    needed = {sid for sid,q in monthly.items() if q} | {
        sid for sid,q in state['shares'].items() if q} | {
        order['security_id'] for order in state['orders'].values() if order['status'] == 'OPEN'}
    if not needed <= set(inputs['histories']):
        return waiting('WAIT_NEW_SECURITY_EVIDENCE')
    binding = decision['payload']['input_binding']
    monthly_date = binding['training_cutoff_date']
    require(monthly_date == binding['historical_search_arguments']['decision_date']
            and binding['search_arguments']['decision_date'] == binding['valuation_date'],
            'REBIND_TARGET_CUTOFF_MISMATCH')
    valuation_at = timestamp(binding['valuation_at'])
    created_at = timestamp(target['payload']['created_at'])
    require(valuation_at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            == binding['valuation_date'] and monthly_date <= binding['valuation_date'],
            'REBIND_TARGET_VALUATION_DATE_MISMATCH')
    require(valuation_at <= created_at <= current, 'REBIND_TARGET_TIME_FUTURE_OR_INVERTED')
    if monthly_date not in inputs['session_dates'] or monthly_date > inputs['signal_date']:
        return waiting('WAIT_TARGET_HISTORY_ALIGNMENT')
    # Explicit live extension: today's configuration may use the prior completed
    # session. The research helper's date is a historical training anchor only;
    # retain actual configuration/valuation times and never backdate availability.
    configuration = dict(monthly_decision_date_semantics=
        'HISTORICAL_TRAINING_ANCHOR_NOT_CONFIGURATION_TIME',
        training_cutoff=monthly_date, monthly_target_created_at=target['payload']['created_at'],
        valuation_at=binding['valuation_at'], valuation_date=binding['valuation_date'],
        execution_semantics='LIVE_APPLICATION_EXTENSION_NOT_NEXT_OPEN_BACKTEST_EQUIVALENCE')
    normalized = deepcopy(inputs)
    positive = {sid:q for sid,q in monthly.items() if q}
    normalized['histories'] = {sid:deepcopy(inputs['histories'][sid]) for sid in positive}
    normalized['base_target'] = dict(
        quantities=monthly,
        price_units={sid:inputs['histories'][sid]['units']['basis_id'] for sid in positive},
        origin_reference=target['target_id'], monthly_decision_date=monthly_date,
        **configuration)
    normalized_bytes = canonical(normalized)
    name = 'server-rebound/' + sha256(normalized_bytes).hexdigest() + '.json'
    parent_name = 'server-parent/' + trusted_receipt_sha256 + '.json'
    rebound_files = deepcopy(files)
    for path, raw in ((name, normalized_bytes), (parent_name, receipt_bytes)):
        require(path not in rebound_files or rebound_files[path] == raw, 'REBIND_PATH_CONFLICT')
        rebound_files[path] = raw
    require(len(rebound_files) <= 2000 and
            sum(map(len, rebound_files.values())) <= 32 * 1024 * 1024,
            'REBOUND_SOURCE_DOMAIN_OR_BUDGET')
    receipt = deepcopy(parent)
    receipt.update(account_revision=state['revision'], target_id=target['target_id'],
        normalized_inputs_path=name, available_at=current.isoformat(),
        available_at_semantics='ACTUAL_SERVER_REBIND_TIME_NOT_NEW_PRICE_CAPTURE',
        valid_from=max(current,timestamp(session['open'])).isoformat(),
        target_configuration=configuration,
        parent_review_sha256=trusted_receipt_sha256,
        source_sha256={path:sha256(raw).hexdigest() for path,raw in rebound_files.items()})
    return dict(status='REBOUND_EVIDENCE_READY_POLICY_UNCHANGED', receipt=receipt,
                files=rebound_files, account_mutated=False,
                release_sha256=parent.get('release_sha256'),
                source_received_at=parent['source_received_at'])
