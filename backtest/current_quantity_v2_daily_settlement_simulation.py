"""Explicit completed-session capture then isolated settlement; no scheduler.

Preparation is create-only. A partial/failed capture is retained and cannot be
silently fetched again. Store application only replays saved bytes, so a saved
preparation survives process restart without another network observation.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
from data.current_quantity_v2_late_unit_review import STATUS as LATE_STATUS, replay as replay_late_review

from backtest.current_quantity_v2_monthly_simulation import digest
from backtest.current_quantity_v2_simulated_settlement import _rebuild, _references, settle
from data.current_quantity_v2_completed_session_minutes import capture, decode, stamp, LIMIT
from data.current_quantity_v2_difference_plan import require
from backtest.current_quantity_v2_minute_day_fill import exact


def _write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)


def _read(path):
    require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents), 'INVALID_SETTLEMENT_SOURCE_PATH')
    with path.open('rb') as stream: raw = stream.read(LIMIT+1)
    require(len(raw) <= LIMIT, 'SETTLEMENT_SOURCE_TOO_LARGE')
    return raw


def _identities(simulation, session):
    rebuilt, _, last_at = _rebuild(simulation)
    refs = _references(rebuilt['chain']); identities = {}
    for oid, order in rebuilt['chain']['ledger']['orders'].items():
        ref = refs[order['security_id']]
        require(ref['session'] == session, 'ORDER_SESSION_MISMATCH')
        row = dict(security_id=order['security_id'], ticker=ref['ticker'], session=session,
                   session_open=stamp(ref['session_open']).isoformat(),
                   session_close=stamp(order['session_close']).isoformat())
        sid = row['security_id']
        require(sid not in identities or identities[sid] == row, 'ORDER_IDENTITY_CONFLICT')
        identities[sid] = row
    require(bool(identities), 'NO_ACCEPTED_ORDERS')
    return rebuilt, identities, last_at


def _read_capture(directory, identity, calendar_reference):
    receipt = json.loads(_read(directory/'receipt.json'))
    started = json.loads(_read(directory/'started.json'))
    for value in (receipt, started):
        require(all(value[k] == v for k, v in identity.items()), 'CAPTURE_IDENTITY_CHANGED')
        require(value['calendar_source_reference'] == calendar_reference, 'CAPTURE_CALENDAR_CHANGED')
    raw = _read(directory/'response.bin')
    require(sha256(raw).hexdigest() == receipt['raw_sha256'], 'CAPTURE_BYTES_CHANGED')
    require(stamp(receipt['captured_at']) >= stamp(started['started_at']), 'CLOCK_ROLLBACK')
    result = decode(raw, **identity, captured_at=receipt['captured_at'])
    result['source_reference'] = 'sha256:'+receipt['raw_sha256']
    require(result == json.loads(_read(directory/'minutes.json'))
            and receipt['status'] == result['status'], 'CAPTURE_DECODE_CHANGED')
    return result


def prepare_daily_settlement(*, store, simulation_id, expected_revision, session,
                             fees, calendar_source_reference, directory, fetch, clock):
    """Capture evidence once. Explicit fees apply to the exact accepted order set."""
    current = store.read(simulation_id)
    require(current['revision'] == expected_revision, 'STALE_SIMULATION_REVISION')
    simulation, identities, last_at = _identities(current['simulation'], session)
    orders = simulation['chain']['ledger']['orders']
    require(type(fees) is dict and set(fees) == set(orders), 'EXACT_EXPLICIT_ORDER_FEES_REQUIRED')
    require(all(exact(value) >= 0 for value in fees.values()), 'NONNEGATIVE_EXPLICIT_FEES_REQUIRED')
    require(type(calendar_source_reference) is str and calendar_source_reference.strip(), 'CALENDAR_REFERENCE_REQUIRED')
    request = dict(kind='COMPLETED_SESSION_SIMULATION_SETTLEMENT_V1', simulation_id=simulation_id,
                   expected_revision=expected_revision, session=session, fees=deepcopy(fees),
                   calendar_source_reference=calendar_source_reference, identities=identities)
    output = Path(directory).resolve()
    if output.exists():
        require(json.loads((output/'request.json').read_bytes()) == request, 'SETTLEMENT_PREPARATION_CONFLICT')
        _read_prepared(output, simulation, request)
        return dict(directory=str(output), request=request)
    now = stamp(clock().isoformat())
    require(now >= last_at and all(now >= stamp(row['session_close']) for row in identities.values()),
            'SETTLEMENT_CAPTURE_TOO_EARLY')
    output.mkdir(parents=True, exist_ok=False)
    _write(output/'request.json', request)
    last = [now]
    def actual_clock():
        value = stamp(clock().isoformat())
        require(value >= last[0], 'CLOCK_ROLLBACK')
        last[0] = value
        return value
    captures = {}
    for sid, identity in sorted(identities.items()):
        name = digest(sid)
        capture(directory=output/name, **identity, calendar_source_reference=calendar_source_reference,
                fetch=fetch, clock=actual_clock)
        captures[sid] = name
    _write(output/'ready.json', dict(request_sha256=digest(request), captures=captures,
                                   evaluated_at=actual_clock().isoformat()))
    _read_prepared(output, simulation, request)
    return dict(directory=str(output), request=request)


def _read_prepared(output, simulation, request):
    require(json.loads((output/'request.json').read_bytes()) == request, 'SETTLEMENT_PREPARATION_CONFLICT')
    require((output/'ready.json').is_file(), 'SETTLEMENT_CAPTURE_INCOMPLETE_NO_RETRY')
    ready = json.loads((output/'ready.json').read_bytes())
    rebuilt, identities, last_at = _identities(simulation, request['session'])
    require(identities == request['identities'] and ready['request_sha256'] == digest(request), 'SETTLEMENT_BINDING_CHANGED')
    require(ready['captures'] == {sid:digest(sid) for sid in identities}, 'CAPTURE_DOMAIN_CHANGED')
    evidence = {}; observed = []
    for sid, identity in identities.items():
        item = _read_capture(output/ready['captures'][sid], identity, request['calendar_source_reference'])
        observed.append(stamp(item['captured_at']))
        for oid, order in rebuilt['chain']['ledger']['orders'].items():
            if order['security_id'] == sid:
                evidence[oid] = dict(item, fees=request['fees'][oid])
    at = stamp(ready['evaluated_at'])
    require(at >= max(observed+[last_at]), 'SETTLEMENT_OBSERVATION_TIME_CHANGED')
    return dict(evidence=evidence, observed_through=max(observed).isoformat(), evaluated_at=at.isoformat())


def apply_daily_settlement(*, store, prepared, unit_reviews, source_hashes, evaluated_at):
    """Persist modeled outcomes; UNKNOWN remains explicit and does not expire orders."""
    request = deepcopy(prepared['request']); output = Path(prepared['directory']).resolve()
    bound = dict(request, directory=str(output), unit_reviews=deepcopy(unit_reviews), source_hashes=deepcopy(source_hashes), evaluated_at=evaluated_at)
    def transform(simulation):
        evidence = _read_prepared(output, simulation, request)
        refs = _references(simulation['chain'])
        require(set(unit_reviews) == set(request['identities']), 'SETTLEMENT_UNIT_REVIEW_REQUIRED')
        def pinned(name):
            require(type(name) is str and name in source_hashes and '\\' not in name and ':' not in name
                    and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                    'INVALID_SETTLEMENT_REVIEW_PATH')
            raw = _read(output/name)
            require(sha256(raw).hexdigest() == source_hashes[name], 'SETTLEMENT_REVIEW_SOURCE_CHANGED')
            return raw
        reviewed = []
        for sid, name in unit_reviews.items():
            review = json.loads(pinned(name)); ref = refs[sid]
            capture_item = next(item for item in evidence['evidence'].values() if item['security_id'] == sid)
            require(review.get('security_id') == sid and review.get('ticker') == ref['ticker']
                    and review.get('price_basis') == ref['price_basis']
                    and review.get('reference_sha256') == digest(ref)
                    and review.get('reference_source_hashes') == ref['source_hashes']
                    and review.get('capture_raw_sha256') == capture_item['source_reference'].removeprefix('sha256:')
                    and review.get('status') in ('NO_UNPROCESSED_ACTIONS', LATE_STATUS)
                    and stamp(review['covered_from']) <= stamp(ref['captured_at'])
                    and stamp(capture_item['captured_at']) <= stamp(review['covered_through']) <= stamp(review['reviewed_at'])
                    and type(review.get('source_references')) is list
                    and review['source_references'], 'SETTLEMENT_UNIT_REVIEW_REQUIRED')
            for path in review['source_references']: pinned(path)
            if review['status'] == LATE_STATUS:
                replay_late_review(review, reference=ref,
                    capture_raw_sha256=capture_item['source_reference'].removeprefix('sha256:'),
                    captured_at=capture_item['captured_at'], observed_at=evaluated_at, read=pinned)
            reviewed.append(stamp(review['reviewed_at']))
        require(stamp(evaluated_at) >= max([stamp(evidence['evaluated_at'])]+reviewed), 'SETTLEMENT_REVIEW_NOT_YET_OBSERVED')
        evidence['evaluated_at'] = stamp(evaluated_at).isoformat()
        return settle(simulation=simulation, **evidence)
    require(type(unit_reviews) is dict and set(unit_reviews) == set(request['identities']), 'SETTLEMENT_UNIT_REVIEW_REQUIRED')
    return store.apply(simulation_id=request['simulation_id'], expected_revision=request['expected_revision'],
        operation_id=request['simulation_id']+':daily-settlement:'+request['session'],
        request=bound, transform=transform)
