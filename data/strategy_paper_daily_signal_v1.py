"""Static paper replay wrapper over the versioned shared daily verifier.

No fake real events, market fetching, order acceptance, persistence or scheduler.
Trusted application/receipt hashes must be server-owned review inputs.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from core.strategy_account_difference import require, timestamp
from backtest.current_strategy_paper_slice_v1 import replay, project
from data.strategy_paper_continuous32_selection_v1 import (
    verify_paper_target, CODE_PATHS as SELECTION_CODE_PATHS)
from data.strategy_daily_signal_common_v1 import (
    _verify_daily_signal_core, CODE_PATHS as RULE_CODE_PATHS)

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'ISOLATED_CURRENT_STRATEGY_PAPER_DAILY_SIGNAL_ONLY'
CODE_PATHS = set(SELECTION_CODE_PATHS) | set(RULE_CODE_PATHS) | {
    'data/strategy_daily_signal_common_v1.py',
    'data/strategy_paper_daily_signal_v1.py',
    'core/strategy_account_difference.py',
}


def verify_paper_daily_signal(*, book, selection_result, selection_arguments,
        application_bytes, trusted_application_sha256, now, release_bytes,
        trusted_release_sha256, calendar_bytes, receipt_bytes=None,
        trusted_receipt_sha256=None, files=None):
    require(type(application_bytes) is bytes and
            sha256(application_bytes).hexdigest() == trusted_application_sha256,
            'PAPER_DAILY_APPLICATION_HASH')
    app = json.loads(application_bytes)
    require(app.get('schema') == 'PAPER_DAILY_SIGNAL_APPLICATION_V1' and
            app.get('scope') == SCOPE and app.get('authorized') is True and
            app.get('automatic_acceptance_allowed') is False, 'PAPER_DAILY_APPLICATION_SCOPE')
    current = timestamp(now)
    require(timestamp(app['approved_at']) <= timestamp(app['valid_from']) <= current <
            timestamp(app['valid_until']), 'PAPER_DAILY_APPLICATION_TIME')
    require(set(app['code_sha256']) == CODE_PATHS and all(
            sha256((ROOT/path).read_bytes()).hexdigest() == digest
            for path, digest in app['code_sha256'].items()), 'PAPER_DAILY_CODE_CHANGED')
    verified_book = replay(book)
    verified_selection = verify_paper_target(selection_result, **selection_arguments)
    require(verified_selection['target_quantities'] is not None, 'PAPER_MONTHLY_TARGET_NOT_READY')
    binding = selection_result['payload']['input_binding']
    selection_book = replay(selection_arguments['book'])
    historical_operations = selection_book['operations']
    require(selection_book['application'] == verified_book['application'] and
            selection_book['revision'] == binding['account_revision'] == verified_selection['account_revision'] and
            len(historical_operations) <= len(verified_book['operations']) and
            verified_book['operations'][:len(historical_operations)] == historical_operations,
            'PAPER_DAILY_SELECTION_NOT_ANCESTOR')
    genesis = sha256(canonical(verified_book['application'])).hexdigest()
    require(app['account_id'] == verified_book['application']['account_id'] == verified_selection['account_id']
            and app['account_genesis_sha256'] == genesis == binding['account_genesis_sha256']
            and app['target_id'] == verified_selection['target_id']
            and app['selection_application_sha256'] == binding['paper_application_sha256'],
            'PAPER_DAILY_ACCOUNT_TARGET_BINDING')
    require(timestamp(binding['valuation_at']) <= current and
            (verified_book['last_available_at'] is None or
             timestamp(verified_book['last_available_at']) <= current), 'PAPER_DAILY_STATE_NOT_AVAILABLE')
    require(type(calendar_bytes) is bytes and len(calendar_bytes) <= 4*1024*1024 and
            sha256(calendar_bytes).hexdigest() == app['calendar_sha256'] == binding['calendar_sha256'],
            'PAPER_DAILY_CALENDAR_BINDING')
    calendar = json.loads(calendar_bytes)
    sessions = {row['date']: row for row in calendar['sessions']}
    require(app['start_session'] in sessions and app['start_session'] <=
            current.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
            'PAPER_DAILY_BEFORE_REGISTERED_START')
    require(type(release_bytes) is bytes and sha256(release_bytes).hexdigest() ==
            trusted_release_sha256 == app['release_sha256'], 'PAPER_DAILY_RELEASE_BINDING')
    state = project(verified_book)
    state['orders'] = {row['order_id']: dict(row, status='OPEN') for row in state['pending_orders']}
    target = dict(target_id=verified_selection['target_id'], payload=dict(
        account_id=verified_selection['account_id'], target_month=verified_selection['target_month'],
        target_quantities=deepcopy(verified_selection['target_quantities'])))
    if receipt_bytes is not None:
        require(type(receipt_bytes) is bytes and sha256(receipt_bytes).hexdigest() == trusted_receipt_sha256,
                'RECEIPT_HASH_MISMATCH')
        receipt = json.loads(receipt_bytes)
        require(timestamp(receipt['available_at']) >= timestamp(binding['valuation_at']) and
                (verified_book['last_available_at'] is None or timestamp(receipt['available_at']) >=
                 timestamp(verified_book['last_available_at'])), 'PAPER_DAILY_RECEIPT_BEFORE_STATE')
    result = _verify_daily_signal_core(state=state, target=target, now=now,
        application_kind='PAPER', release_bytes=release_bytes, trusted_release_sha256=trusted_release_sha256,
        receipt_bytes=receipt_bytes, trusted_receipt_sha256=trusted_receipt_sha256,
        files=files, calendar_bytes=calendar_bytes)
    return dict(result, paper_application_sha256=trusted_application_sha256,
        paper_book_revision=verified_book['revision'], application_scope=SCOPE,
        automatic_acceptance_allowed=False, orders_created=False, account_mutated=False)
