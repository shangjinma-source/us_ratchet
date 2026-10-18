"""Explicit pinned observations for the current paper plan; no market refresh."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_plan_review import review_research_plan
from data.current_research_saved_quote import read_saved_quote


def review_plan_observations(state, *, root, observations, observed_through,
                             now, reviewed_observation_pins=None):
    """Caller authenticates admission and official close times/calendar.

    descriptors: security_id, ticker, expected_security_type, relative_directory,
    entry, observation_date, session_close_at. Older decision observations are
    validated but never substituted for the current order's active-date bar.
    Additional pins must come from a separately admitted observation registry;
    accepting this parameter does not itself establish that admission.
    """
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    review_paper_ledger(state)
    plan = state['plan']
    require(type(observed_through) is str and date.fromisoformat(observed_through).isoformat() == observed_through, 'INVALID_OBSERVATION_CUTOFF')
    require(isinstance(now, datetime) and now.tzinfo is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    require(observed_through <= now.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'FUTURE_OBSERVATION_CUTOFF')
    require(isinstance(observations, list), 'EXPLICIT_OBSERVATIONS_REQUIRED')
    pins = dict(plan['causal_inputs']['source_hashes'])
    require(reviewed_observation_pins is None or isinstance(reviewed_observation_pins, dict), 'INVALID_ADMITTED_PINS')
    for path, digest in (reviewed_observation_pins or {}).items():
        require(path not in pins or pins[path] == digest, 'CONFLICTING_OBSERVATION_PIN')
        pins[path] = digest
    securities = plan['causal_inputs']['securities']
    bars, audit, seen = [], [], set()
    for observation in observations:
        sid, day = observation['security_id'], observation['observation_date']
        require(sid in securities and observation['ticker'] == securities[sid], 'OBSERVATION_SECURITY_MISMATCH')
        require(type(day) is str and date.fromisoformat(day).isoformat() == day and day <= observed_through, 'OBSERVATION_AFTER_CUTOFF')
        require((sid,day) not in seen, 'DUPLICATE_SECURITY_OBSERVATION')
        seen.add((sid,day))
        close_at = datetime.fromisoformat(observation['session_close_at'])
        require(close_at.tzinfo is not None and close_at <= now, 'OBSERVATION_SESSION_NOT_COMPLETED')
        # Authenticate the three file pins against current plan or admitted source
        # before invoking any file read. Decoder then verifies the actual bytes.
        directory = Path(observation['relative_directory'])
        for suffix, key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
            path = (directory / (observation['ticker'] + suffix)).as_posix()
            require(path in pins and pins[path] == observation['entry'][key], 'OBSERVATION_SOURCE_NOT_ADMITTED')
        decoded = read_saved_quote(root=root,ticker=observation['ticker'],
            expected_security_type=observation['expected_security_type'],entry=observation['entry'],
            relative_directory=observation['relative_directory'],decision_date=day,
            decision_session_close_at=observation['session_close_at'])
        active = day == plan['active_date']
        if active:
            bars.append(dict(security_id=sid,session=day,source_references=list(decoded['source_hashes']),**decoded['ohlc']))
        audit.append(dict(security_id=sid,observation_date=day,used_for_active_session_range=active,
                          source_hashes=decoded['source_hashes'],completion_basis=decoded['completion_basis']))
    result = review_research_plan(state,observed_through=observed_through,market_bars=bars,source_hashes=pins)
    result['observation_scope'] = 'EXPLICIT_PINNED_CURRENT_PLAN_OBSERVATIONS_NO_MARKET_REFRESH'
    result['observation_audit'] = audit
    result['additional_observation_admission_verified_by_helper'] = False
    return result


def review_plan_bound_observations(state, *, root, now):
    """Default safe readback: verify saved source bytes, report no active bar.

    A plan's decision date is NOT proof of official session completion. This
    helper therefore never passes OHLC to the range reviewer or invents a close
    timestamp. It does not reuse selection_asof or require stocks.close fields.
    """
    import hashlib
    from data.current_research_saved_quote import _json
    review_paper_ledger(state)
    plan = state['plan']
    cutoff = plan['causal_inputs']['decision_date']
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('AWARE_SERVER_CLOCK_REQUIRED')
    if cutoff >= now.astimezone(ZoneInfo('America/New_York')).date().isoformat():
        raise ValueError('DEFAULT_OBSERVATION_REQUIRES_PRIOR_NY_DATE')
    if cutoff >= plan['active_date']:
        raise ValueError('PLAN_ACTIVE_DATE_NOT_AFTER_DECISION')
    result = review_plan_observations(state,root=root,observations=[],observed_through=cutoff,now=now)
    pins = plan['causal_inputs']['source_hashes']
    root = Path(root).resolve()
    audit = []
    def read(path):
        relative = Path(path)
        resolved = (root / relative).resolve()
        if relative.is_absolute() or relative.drive or '..' in relative.parts or not resolved.is_relative_to(root):
            raise ValueError('BOUND_SOURCE_OUTSIDE_ROOT')
        if resolved.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('BOUND_SOURCE_TOO_LARGE')
        raw = resolved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pins[path]:
            raise ValueError('BOUND_SOURCE_HASH_MISMATCH')
        return raw
    for order, row in zip(plan['orders'],result['orders']):
        quote = plan['causal_inputs']['quotes'][order['security_id']]
        candidates = [ref for ref in quote['source_references'] if Path(ref).name == order['ticker']+'.response.bin']
        if len(candidates) > 1:
            raise ValueError('AMBIGUOUS_BOUND_RAW_SOURCE')
        status = 'BOUND_RAW_REFERENCE_MISSING'
        paths = []
        if candidates:
            raw_path = candidates[0]
            parent = Path(raw_path).parent
            paths = [raw_path, (parent/(order['ticker']+'.receipt.json')).as_posix(), (parent/(order['ticker']+'.decoded.json')).as_posix()]
            status = 'BOUND_SOURCE_PIN_MISSING'
            if all(path in pins for path in paths):
                try:
                    raw, receipt_raw, observed_raw = [read(path) for path in paths]
                except FileNotFoundError:
                    status = 'BOUND_SOURCE_FILE_MISSING'
                else:
                    receipt, observation = _json(receipt_raw), _json(observed_raw)
                    if (receipt['http_status'] != 200 or receipt['ticker'] != order['ticker']
                        or receipt['raw_sha256'] != pins[raw_path]
                        or observation['ticker'] != order['ticker']
                        or observation['receipt_sha256'] != pins[paths[1]]):
                        raise ValueError('BOUND_SOURCE_IDENTITY_OR_RECEIPT_MISMATCH')
                    status = 'BOUND_SOURCE_BYTES_VERIFIED_NO_COMPLETED_ACTIVE_OBSERVATION'
        row['reason'] = status
        audit.append(dict(order_id=order['order_id'],status=status,source_paths=paths))
    result['observation_audit'] = audit
    result['observation_scope'] = 'CURRENT_PLAN_BOUND_SOURCE_BYTES_ONLY_NO_NEW_MARKET_OBSERVATION'
    result['completion_basis'] = 'NO_COMPLETED_ACTIVE_SESSION_OBSERVATION_SUPPLIED'
    return result
