"""Read saved same-scope quote receipt chains; no HTTP, orders, or fills.

The server supplies the current tip. Local hashes verify bytes and chain order,
not external timestamps, identity or whether a later receipt exists elsewhere.
"""
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_execution import decode_intraday_reference

POLICY = 'FRESH_REGULAR_BUY_LOW_CAP_SELL_LAST_CEIL_V1'


def read_intraday_execution_reference(*, root, security_id, ticker, session, scope_id,
        receipt_paths, source_hashes, expected_tip_sha256, now, frozen_files=None):
    base = Path(root).resolve()
    now = _time(now)
    _require(all(isinstance(value, str) and value for value in (security_id, ticker, session, scope_id)), 'REFERENCE_IDENTITY_REQUIRED')
    _require(isinstance(receipt_paths, list) and 0 < len(receipt_paths) <= 1000
        and len(set(receipt_paths)) == len(receipt_paths), 'BOUNDED_UNIQUE_RECEIPT_CHAIN_REQUIRED')
    _require(isinstance(source_hashes, dict) and source_hashes, 'SOURCE_PINS_REQUIRED')
    _require(source_hashes.get(receipt_paths[-1]) == expected_tip_sha256, 'EXPECTED_TIP_MISMATCH')
    consumed = {}

    def read(name, expected):
        _require(isinstance(name, str) and name and '\\' not in name, 'INVALID_SOURCE_PATH')
        path = Path(name)
        _require(not path.is_absolute() and not path.drive and '..' not in path.parts, 'SOURCE_OUTSIDE_ROOT')
        if frozen_files is None:
            full = (base / path).resolve()
            _require(full.is_relative_to(base) and full.stat().st_size <= 4 * 1024 * 1024, 'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
            raw = full.read_bytes()
        else:
            _require(isinstance(frozen_files, dict), 'FROZEN_FILES_REQUIRED')
            raw = frozen_files[name]
            _require(isinstance(raw, bytes) and len(raw) <= 4 * 1024 * 1024, 'INVALID_FROZEN_SOURCE')
        _require(sha256(raw).hexdigest() == expected == source_hashes.get(name), 'SOURCE_HASH_MISMATCH')
        consumed[name] = expected
        return raw

    def unique(pairs):
        output = {}
        for key, value in pairs:
            _require(key not in output, 'DUPLICATE_JSON_FIELD')
            output[key] = value
        return output

    previous_hash, previous_time, cap = None, None, None
    for sequence, path in enumerate(receipt_paths, 1):
        digest = source_hashes[path]
        receipt = json.loads(read(path, digest), object_pairs_hook=unique)
        _require(set(receipt) == {'schema', 'scope_id', 'security_id', 'ticker', 'session', 'sequence',
            'previous_receipt_sha256', 'captured_at', 'raw_path', 'raw_sha256'}, 'RECEIPT_SCHEMA')
        _require(receipt['schema'] == 'INTRADAY_EXECUTION_QUOTE_RECEIPT_V1'
            and (receipt['scope_id'], receipt['security_id'], receipt['ticker'], receipt['session'])
            == (scope_id, security_id, ticker, session), 'RECEIPT_SCOPE_MISMATCH')
        _require(type(receipt['sequence']) is int and receipt['sequence'] == sequence
            and receipt['previous_receipt_sha256'] == previous_hash, 'RECEIPT_CHAIN_GAP')
        capture = _time(receipt['captured_at'])
        _require(capture <= now and (previous_time is None or previous_time <= capture), 'RECEIPT_TIME_ORDER_INVALID')
        raw = read(receipt['raw_path'], receipt['raw_sha256'])
        historical = decode_intraday_reference(raw, ticker=ticker, now=capture, captured_at=capture)
        _require(historical['session'] == session, 'QUOTE_SESSION_MISMATCH')
        prior_cap = cap
        observed_cap = Fraction(historical['observed_cap'])
        cap = observed_cap if cap is None else min(cap, observed_cap)
        previous_hash, previous_time = digest, capture
    current = decode_intraday_reference(raw, ticker=ticker, now=now, captured_at=capture)
    _require(now < _time(current['refresh_by']), 'REFERENCE_EXPIRED')
    last = Fraction(current['last_price'])
    # Ceil to a cent gives a minimum sell price at/above the observed last.
    cents = -(-(last * 100).numerator // (last * 100).denominator)
    sell = Fraction(cents, 100)
    return dict(policy=POLICY, security_id=security_id, ticker=ticker, session=session, scope_id=scope_id,
        session_open=current['session_open'], session_close=current['session_close'],
        last_price=current['last_price'], last_at=current['last_at'], minute_low=current['minute_low'],
        minute_start=current['minute_start'], minute_end=current['minute_end'], captured_at=capture.isoformat(),
        checked_at=now.isoformat(), valid_until=current['refresh_by'],
        buy_limit=str(cap), sell_limit=str(sell), prior_buy_cap=None if prior_cap is None else str(prior_cap),
        source_hashes=consumed, receipt_tip_sha256=previous_hash, receipt_count=len(receipt_paths),
        source_bytes_verified=True, source_authenticated=False, latest_tip_authenticated=False,
        research_only=True, execution_blocked=True, account_mutated=False,
        limitations=['BUY cap is nonincreasing in the complete supplied chain to the server-declared tip.',
            'SELL ceil(last) is an engineering limit reference, not bid/ask or a validated timing strategy.',
            'Reference expiry neither cancels nor changes an already accepted DAY order.'])
