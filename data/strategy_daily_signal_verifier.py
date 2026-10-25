"""Server-only, isolated verifier for explicitly released SMA20-half evidence.

Trusted release/receipt hashes MUST come from server configuration and its reviewed
evidence store, never from the same request supplying bytes. The receipt attests
normalization/source review; hashes alone do not prove a vendor's data is true.
No default policy, fetching, production approval, account write or HTTP endpoint.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from backtest.partial_trend_exposure import partial_sma20_target
from core.strategy_account_ledger import replay
from core.strategy_account_difference import require, timestamp

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'SMA20_HALF_OFF_RESEARCH'
CODE_PATHS = {
    'backtest/partial_trend_exposure.py',
    'backtest/current_quantity_v2_risk_overlays.py',
}


def verify_daily_signal_bundle(*, state, target, now, release_bytes=None,
                               trusted_release_sha256=None, receipt_bytes=None,
                               trusted_receipt_sha256=None, files=None,
                               calendar_bytes=None):
    if release_bytes is None or trusted_release_sha256 is None:
        return dict(status='WAIT_POLICY_RELEASE', signal=None)
    require(type(release_bytes) is bytes and
            sha256(release_bytes).hexdigest() == trusted_release_sha256, 'RELEASE_HASH_MISMATCH')
    release = json.loads(release_bytes)
    require(release.get('schema') == 'SERVER_DAILY_POLICY_RELEASE_V1'
            and release.get('approved') is True and release.get('policy_id') == POLICY,
            'EXPLICIT_POLICY_RELEASE_REQUIRED')
    pins = release['code_sha256']
    require(type(pins) is dict and set(pins) == CODE_PATHS
            and all(sha256((ROOT / path).read_bytes()).hexdigest() == digest
                    for path, digest in pins.items()), 'DAILY_POLICY_CODE_CHANGED')
    current = timestamp(now)
    require(timestamp(release['approved_at']) <= current, 'FUTURE_POLICY_RELEASE')
    require(type(calendar_bytes) is bytes and len(calendar_bytes) <= 4 * 1024 * 1024
            and sha256(calendar_bytes).hexdigest() == release.get('calendar_sha256'),
            'FIXED_CALENDAR_HASH_MISMATCH')
    calendar = json.loads(calendar_bytes)
    require(calendar.get('schema') == 'FIXED_EXCHANGE_SESSIONS_V1'
            and calendar.get('exchange') == 'NASDAQ', 'FIXED_CALENDAR_REQUIRED')
    sessions = calendar['sessions']
    require(type(sessions) is list and bool(sessions), 'FIXED_CALENDAR_REQUIRED')
    dates = []
    previous_close = None
    for session in sessions:
        day = session['date']
        opened, closed = timestamp(session['open']), timestamp(session['close'])
        require(type(day) is str and date.fromisoformat(day).isoformat() == day
                and opened.astimezone(ZoneInfo('America/New_York')).date().isoformat() == day
                and closed.astimezone(ZoneInfo('America/New_York')).date().isoformat() == day
                and opened < closed and (previous_close is None or previous_close < opened),
                'INVALID_FIXED_CALENDAR_SESSION')
        dates.append(day)
        previous_close = closed
    require(dates == sorted(set(dates)), 'INVALID_FIXED_CALENDAR_DATES')
    if receipt_bytes is None or trusted_receipt_sha256 is None:
        return dict(status='WAIT_SIGNAL', signal=None)
    require(type(receipt_bytes) is bytes and
            sha256(receipt_bytes).hexdigest() == trusted_receipt_sha256, 'RECEIPT_HASH_MISMATCH')
    receipt = json.loads(receipt_bytes)
    require(receipt.get('schema') == 'SERVER_REVIEWED_DAILY_EVIDENCE_V1'
            and receipt.get('release_sha256') == trusted_release_sha256,
            'DAILY_RECEIPT_RELEASE_MISMATCH')
    require(replay(state['account_id'], [e['payload'] for e in state['events']]) == state,
            'ACCOUNT_REPLAY_MISMATCH')
    require(target['payload']['account_id'] == state['account_id'], 'TARGET_ACCOUNT_MISMATCH')
    for key, value in [('account_id', state['account_id']), ('account_revision', state['revision']),
                       ('target_id', target['target_id'])]:
        require(type(receipt.get(key)) is type(value) and receipt[key] == value,
                'DAILY_RECEIPT_BINDING_MISMATCH')
    require(target['payload']['target_month'] ==
            current.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'),
            'MONTHLY_TARGET_REQUIRED')
    source_pins = receipt['source_sha256']
    require(type(files) is dict and type(source_pins) is dict and
            set(files) == set(source_pins) and 0 < len(files) <= 2000,
            'DAILY_SOURCE_DOMAIN_MISMATCH')
    require(all(type(raw) is bytes for raw in files.values())
            and sum(map(len, files.values())) <= 32 * 1024 * 1024, 'DAILY_SOURCE_BUDGET')
    require(all(sha256(raw).hexdigest() == source_pins[path]
                for path, raw in files.items()), 'DAILY_SOURCE_HASH_MISMATCH')
    inputs = json.loads(files[receipt['normalized_inputs_path']])
    require(receipt.get('normalization_reviewed') is True
            and receipt.get('unresolved_units') == []
            and receipt.get('pending_rights') == [], 'DAILY_UNIT_REVIEW_REQUIRED')
    # These raw sources are independently reviewed by the trusted receipt author;
    # nonempty reference strings embedded in research inputs are not authority.
    raw_paths = receipt['raw_source_paths']
    require(type(raw_paths) is list and bool(raw_paths)
            and all(type(path) is str and path in files
                    and path != receipt['normalized_inputs_path'] for path in raw_paths),
            'REVIEWED_RAW_SOURCES_REQUIRED')
    require(inputs['base_target']['quantities'] == target['payload']['target_quantities'],
            'DAILY_MONTHLY_QUANTITIES_MISMATCH')
    market_asof = timestamp(inputs['observed_at'])
    received = timestamp(receipt['source_received_at'])
    available = timestamp(receipt['available_at'])
    valid_from = timestamp(receipt['valid_from'])
    valid_until = timestamp(receipt['valid_until'])
    require(timestamp(release['approved_at']) <= available and
            market_asof <= received <= available <= valid_from < valid_until, 'DAILY_EVIDENCE_CLOCK_INVALID')
    execution_session = receipt['execution_session']
    require(execution_session['date'] ==
            timestamp(execution_session['open']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            and timestamp(execution_session['close']) == valid_until,
            'REVIEWED_EXECUTION_SESSION_REQUIRED')
    require(inputs['signal_date'] in dates, 'SIGNAL_OUTSIDE_FIXED_CALENDAR')
    index = dates.index(inputs['signal_date'])
    require(index >= 19 and index + 1 < len(sessions), 'FIXED_CALENDAR_COVERAGE_REQUIRED')
    require(receipt.get('research_observed_at_semantics') == 'MARKET_ASOF_NOT_RECEIPT'
            and timestamp(receipt['market_asof']) == market_asof
            and market_asof == timestamp(sessions[index]['close']),
            'MARKET_ASOF_MUST_EQUAL_FIXED_CLOSE')
    next_session = sessions[index + 1]
    require(execution_session['date'] == next_session['date']
            and timestamp(execution_session['open']) == timestamp(next_session['open'])
            and valid_from == max(timestamp(next_session['open']), available)
            and valid_until == timestamp(next_session['close']),
            'NEXT_FIXED_SESSION_REQUIRED')
    require(inputs['session_dates'] == dates[:index + 1],
            'FIXED_CALENDAR_PREFIX_REQUIRED')
    source_closes = inputs['session_close_times']['closes']
    require(set(source_closes) == set(dates[:index + 1])
            and all(timestamp(source_closes[session['date']]) == timestamp(session['close'])
                    for session in sessions[:index + 1]), 'FIXED_CALENDAR_CLOSES_REQUIRED')
    require(all([row['date'] for row in history['closes']] == dates[index - 19:index + 1]
                for history in inputs['histories'].values()), 'FIXED_TWENTY_SESSION_WINDOW_REQUIRED')
    if not valid_from <= current < valid_until:
        return dict(status='WAIT_FRESH_SIGNAL', signal=None)
    result = partial_sma20_target(**inputs)
    domain = set(state['shares']) | set(target['payload']['target_quantities']) | {
        order['security_id'] for order in state['orders'].values() if order['status'] == 'OPEN'}
    effective = {sid: result['target_quantities'].get(sid, 0) for sid in domain}
    signal = dict(account_id=state['account_id'], account_revision=state['revision'],
                  target_id=target['target_id'], policy_id=POLICY,
                  evidence_id=trusted_receipt_sha256, observed_at=receipt['source_received_at'],
                  available_at=receipt['available_at'], valid_from=receipt['valid_from'],
                  valid_until=receipt['valid_until'], effective_target_quantities=effective)
    return dict(status='DAILY_SIGNAL_READY', signal=deepcopy(signal),
                policy_release_sha256=trusted_release_sha256,
                production_enabled=False, account_mutated=False,
                market_asof=receipt['market_asof'],
                source_truth='TRUSTED_SERVER_REVIEW_NOT_INDEPENDENT_VENDOR_ATTESTATION')
