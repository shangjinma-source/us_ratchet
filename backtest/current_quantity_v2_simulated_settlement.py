"""Pure, isolated conditional simulator over already accepted paper orders.

No IO, scheduler, real fills or forward activation. Explicit supplied follow-up
proposals may be accepted through the existing paper-chain acceptance rules.
The envelope replays every modeled batch and rejects mixed manual events.
"""
from copy import deepcopy
from datetime import date
from zoneinfo import ZoneInfo
from data.current_quantity_v2_paper_chain import (
    review_chain, record_chain_event, accept_continuation, accept_monthly_retarget)
from data.current_quantity_v2_paper_ledger import digest
from backtest.current_quantity_v2_minute_day_fill import MODEL, evaluate, exact, stamp
from backtest.current_quantity_v2_daily_next_open import drawdown_summary

SCHEMA = 'ISOLATED_V2_SIMULATED_SETTLEMENT_V1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def create_simulation(*, chain, simulation_id, model):
    chain = review_chain(chain)
    require(model == MODEL, 'EXPLICIT_SUPPORTED_MODEL_REQUIRED')
    require(type(simulation_id) is str and simulation_id.strip(), 'SIMULATION_ID_REQUIRED')
    require(not chain['ledger']['events'] and not chain['operations'], 'PRISTINE_ACCEPTED_CHAIN_REQUIRED')
    return dict(schema=SCHEMA, simulation_id=simulation_id, model=model,
                origin=deepcopy(chain), chain=deepcopy(chain), batches=[],
                simulation_only=True, real_account=False, forward_activated=False,
                source_authenticated=False,
                same_time_rule='Fees beyond each SELL own proceeds use batch-start unreserved cash; insufficient aggregate funds reject all fills, not expiries.',
                late_evidence_rule='New batches cannot add outcomes at or before the last recorded event; no retrospective insertion.',
                scope='Accepted activation only; no automatic acceptance of subsequent orders or daily equity marks.')


def _references(chain):
    proposal = chain['ledger']['acceptance']['proposal']
    references = proposal.get('execution_references', proposal['causal_inputs'].get('execution_references'))
    for operation in reversed(chain['operations']):
        if operation['kind'] == 'ACCEPT':
            return operation['proposal']['binding']['execution_inputs']['execution_references']
        if operation['kind'] == 'MONTHLY_RETARGET':
            return operation['proposal']['causal_inputs']['execution_references']
    if proposal.get('target_scope') == 'NEW_CASH_CURRENT_QUOTE_ALLOCATION':
        # Cash genesis stores metadata beside the raw quote reference. Its
        # replay verifies every row and requires the current-cash BASIS in the
        # frozen unit review; normalize those verified fields for consumers.
        from data.current_quantity_v2_current_cash_plan import BASIS
        rows = {row['security_id']: row for row in proposal['rows']}
        references = {sid: dict(ref, security_id=sid, ticker=proposal['securities'][sid]['ticker'],
                                price_basis=BASIS, captured_at=rows[sid]['captured_at'],
                                source_hashes=deepcopy(rows[sid]['source_hashes']))
                      for sid, ref in references.items()}
    return references


def _execute(chain, registration, request):
    state = deepcopy(chain)
    prior_recorded = stamp(chain['ledger']['last_recorded_at'])
    now = stamp(request['evaluated_at'])
    observed = stamp(request['observed_through'])
    require(observed <= now, 'FUTURE_OBSERVATION')
    require(now >= stamp(state['ledger']['last_recorded_at']), 'EVALUATION_BEFORE_RECORDED_STATE')
    evidence = request['evidence']
    orders = state['ledger']['orders']
    references = _references(state)
    valued_closes = [stamp(row['session_close']) for row in registration.get('valuation', {}).get('records', [])
                     if row['status'] == 'COMPLETE']
    require(type(references) is dict, 'ACCEPTED_EXECUTION_IDENTITIES_REQUIRED')
    require(set(evidence) == set(orders), 'EXACT_ACCEPTED_ORDER_EVIDENCE_REQUIRED')
    candidates, results = [], {}
    for oid, order in sorted(orders.items()):
        item = evidence[oid]
        reference = references[order['security_id']]
        accepted, close = stamp(order['accepted_at']), stamp(order['session_close'])
        session = accepted.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        require(item['security_id'] == order['security_id'] and item['ticker'] == reference['ticker']
                and item['session'] == session == close.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                'ORDER_EVIDENCE_IDENTITY_MISMATCH')
        require(type(item['source_reference']) is str and item['source_reference'].strip(), 'SOURCE_REFERENCE_REQUIRED')
        fee = exact(item['fees'])
        require(fee >= 0, 'NONNEGATIVE_EXPLICIT_FEES_REQUIRED')
        require(accepted <= observed, 'OBSERVATION_BEFORE_ACCEPTANCE')
        for bar in item['minutes']:
            require(all(bar[key] == item[key] for key in ('security_id', 'ticker', 'session')),
                    'MINUTE_IDENTITY_MISMATCH')
            require(stamp(reference['session_open']) <= stamp(bar['start'])
                    < stamp(bar['end']) <= close and stamp(bar['end']) <= observed,
                    'MINUTE_OUTSIDE_OBSERVED_SESSION')
        if order['closed']:
            results[oid] = dict(status='ALREADY_CLOSED')
            continue
        require(order['filled_quantity'] == 0, 'PARTIAL_ORDER_UNSUPPORTED')
        event_id = 'simulation:' + digest([registration['simulation_id'], registration['model'], oid])
        args = dict(model=registration['model'], order=order, minutes=item['minutes'],
                    observed_through=request['observed_through'], evaluated_at=request['evaluated_at'],
                    fees=item['fees'], event_id=event_id, expected_revision=state['ledger']['revision'])
        # Discover chronological outcome only. No discovered fill is committed
        # until actual resources at that time pass the separate admission below.
        found = evaluate(**args, available_cash=str(order['quantity'] * exact(order['limit_price']) + fee),
                         available_shares=order['quantity'])
        results[oid] = found
        if found['event_proposal'] is not None:
            candidates.append((stamp(found['event_proposal']['recorded_at']), oid, args, found))
    candidates.sort(key=lambda row: (row[0], stamp(row[3]['event_proposal'].get(
        'executed_at', row[3]['event_proposal']['recorded_at'])), row[1]))
    times = sorted({row[0] for row in candidates})
    for at in times:
        group = [row for row in candidates if row[0] == at]
        ledger = state['ledger']
        free_cash = exact(ledger['cash']) - exact(ledger['reserved_cash'])
        # A sale pays its own fee; its net proceeds and expiry releases cannot
        # finance any other order's fees within this same-time batch.
        fee_shortfall = sum((max(exact('0'), exact(row[2]['fees']) -
                            (row[2]['order']['quantity'] * exact(row[2]['order']['limit_price'])
                             if row[2]['order']['side'] == 'SELL' else exact('0')))
                            for row in group if row[3]['status'] == 'SIMULATED_FILL'), exact('0'))
        if fee_shortfall > free_cash:
            for _, oid, _, _ in group:
                if results[oid]['status'] == 'SIMULATED_FILL':
                    results[oid] = dict(status='UNKNOWN', reason='SAME_TIME_FEES_EXCEED_UNRESERVED_CASH')
            # Expiry carries no fee and remains applicable, but its released
            # reservations never rescue a fill from this rejected time batch.
            group = [row for row in group if row[3]['status'] == 'EXPIRE']
        for _, oid, args, found in group:
            ledger = state['ledger']
            event = found['event_proposal']
            effective = stamp(event.get('executed_at', event['recorded_at']))
            if (stamp(event['recorded_at']) <= prior_recorded or
                    (valued_closes and stamp(event['recorded_at']) <= max(valued_closes)) or
                    stamp(event['recorded_at']) < stamp(ledger['last_recorded_at']) or
                    effective < stamp(ledger['last_effective_at'])):
                results[oid] = dict(status='UNKNOWN', reason='LATE_EVIDENCE_WOULD_REWRITE_HISTORY')
                continue
            order = ledger['orders'][oid]
            own_cash = order['quantity'] * exact(order['limit_price']) if order['side'] == 'BUY' else exact('0')
            own_shares = order['quantity'] if order['side'] == 'SELL' else 0
            sid = order['security_id']
            actual = evaluate(**dict(args, expected_revision=ledger['revision']),
                available_cash=str(exact(ledger['cash']) - exact(ledger['reserved_cash']) + own_cash),
                available_shares=ledger['shares'].get(sid, 0) - ledger['reserved_shares'].get(sid, 0) + own_shares)
            results[oid] = actual
            if actual['event_proposal'] is not None:
                state = record_chain_event(state, actual['event_proposal'], now=request['evaluated_at'])
    return state, results


def _check_fees(evidence, fees):
    for oid, item in evidence.items():
        value = exact(item['fees'])
        require(oid not in fees or fees[oid] == value, 'REGISTERED_ORDER_FEES_CHANGED')
        fees[oid] = value


def _accept(chain, request):
    require(set(request) == {'kind', 'proposal', 'acceptance_id', 'accepted_at'}, 'INVALID_ACCEPTANCE_REQUEST')
    require(request['kind'] in ('CONTINUATION', 'MONTHLY_RETARGET'), 'UNSUPPORTED_ACCEPTANCE_KIND')
    function = accept_continuation if request['kind'] == 'CONTINUATION' else accept_monthly_retarget
    return function(chain, request['proposal'], acceptance_id=request['acceptance_id'], now=request['accepted_at'])


def _rebuild(simulation):
    require(simulation.get('schema') == SCHEMA, 'ISOLATED_SIMULATION_REQUIRED')
    rebuilt = create_simulation(chain=simulation['origin'], simulation_id=simulation['simulation_id'], model=simulation['model'])
    if 'valuation' in simulation:
        _configure_valuation(rebuilt, simulation['valuation']['registration'])
    fees = {}
    last_at = stamp(rebuilt['chain']['ledger']['last_recorded_at'])
    for batch in simulation['batches']:
        request = batch['request']
        if batch.get('kind') == 'CLOSE_VALUATION':
            require(set(batch) == {'kind', 'request', 'result'}, 'INVALID_VALUATION_BATCH')
            at = stamp(request['observed_at'])
            require(at >= last_at, 'SIMULATION_TIME_REVERSED')
            result = _record_close(rebuilt, request)
            require(result == batch['result'], 'VALUATION_REPLAY_MISMATCH')
            chain = rebuilt['chain']
        elif batch.get('kind') == 'ACCEPTANCE':
            require(set(batch) == {'kind', 'request'}, 'INVALID_SIMULATED_ACCEPTANCE')
            at = stamp(request['accepted_at'])
            require(at >= last_at, 'SIMULATION_TIME_REVERSED')
            chain = _accept(rebuilt['chain'], request)
            rebuilt['scope'] = _scope(rebuilt)
        else:
            require(set(batch) == {'request', 'results'}, 'INVALID_SIMULATED_BATCH')
            at = stamp(request['evaluated_at'])
            require(at >= last_at, 'SIMULATION_TIME_REVERSED')
            _check_fees(request['evidence'], fees)
            chain, results = _execute(rebuilt['chain'], rebuilt, request)
            require(results == batch['results'], 'SIMULATION_REPLAY_MISMATCH')
        rebuilt['chain'] = chain
        rebuilt['batches'].append(deepcopy(batch))
        last_at = at
    require(rebuilt == simulation, 'MIXED_OR_CHANGED_SIMULATION')
    return rebuilt, fees, last_at


def settle(*, simulation, evidence, observed_through, evaluated_at):
    rebuilt, fees, last_at = _rebuild(simulation)
    request = dict(evidence=deepcopy(evidence), observed_through=observed_through, evaluated_at=evaluated_at)
    if any(batch['request'] == request for batch in rebuilt['batches']):
        return rebuilt
    require(stamp(evaluated_at) >= last_at, 'SIMULATION_TIME_REVERSED')
    _check_fees(evidence, fees)
    chain, results = _execute(rebuilt['chain'], rebuilt, request)
    rebuilt['chain'] = chain
    rebuilt['batches'].append(dict(request=request, results=results))
    return rebuilt


def accept_orders(*, simulation, proposal, acceptance_id, accepted_at, kind='CONTINUATION'):
    """Accept explicit proposals, preserving prior modeled cash/shares/events.

    Matching acceptance IDs return the current replayed state without assigning
    a new time, matching native paper-chain idempotence. New accepts must follow
    the last observation, including observations that produced UNKNOWN.
    """
    rebuilt, _, last_at = _rebuild(simulation)
    request = dict(kind=kind, proposal=deepcopy(proposal), acceptance_id=acceptance_id, accepted_at=accepted_at)
    require(kind in ('CONTINUATION', 'MONTHLY_RETARGET'), 'UNSUPPORTED_ACCEPTANCE_KIND')
    for batch in rebuilt['batches']:
        if batch.get('kind') == 'ACCEPTANCE' and batch['request']['acceptance_id'] == acceptance_id:
            saved = batch['request']
            require(saved['kind'] == kind and saved['proposal'] == proposal, 'ACCEPTANCE_ID_CONFLICT')
            return rebuilt
    require(stamp(accepted_at) >= last_at, 'SIMULATION_TIME_REVERSED')
    rebuilt['chain'] = _accept(rebuilt['chain'], request)
    rebuilt['batches'].append(dict(kind='ACCEPTANCE', request=request))
    rebuilt['scope'] = _scope(rebuilt)
    return rebuilt


def _scope(simulation):
    return ('Explicit simulation accepts and conditional close valuations; no scheduler or authenticated performance.'
            if 'valuation' in simulation else
            'Explicit continuation and monthly acceptance; no scheduler or daily equity marks.')


def _value(chain, marks, as_of, observed_at, *, initial=False):
    ledger = chain['ledger']; references = _references(chain)
    held = {sid: q for sid, q in ledger['shares'].items() if q}
    require(type(marks) is dict and set(marks) <= set(held), 'EXACT_HELD_MARK_DOMAIN_REQUIRED')
    missing = sorted(set(held) - set(marks))
    total = exact(ledger['cash'])
    session = stamp(as_of).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    for sid, mark in marks.items():
        reference = references[sid]
        require(mark['security_id'] == sid and mark['ticker'] == reference['ticker'] and
                mark['session'] == session and mark['currency'] == 'USD' and
                mark['price_basis'] == reference['price_basis'], 'MARK_IDENTITY_OR_UNIT_MISMATCH')
        mark_at = stamp(mark['as_of'])
        require((mark_at <= stamp(as_of) if initial else mark_at == stamp(as_of)) and
                mark_at.astimezone(ZoneInfo('America/New_York')).date().isoformat() == session and
                mark_at <= stamp(mark['observed_at']) <= stamp(observed_at), 'MARK_TIME_MISMATCH')
        require(type(mark['source_references']) is list and mark['source_references'] and
                all(type(value) is str and value.strip() for value in mark['source_references']), 'MARK_SOURCE_REQUIRED')
        price = exact(mark['price']); require(price > 0, 'POSITIVE_MARK_REQUIRED')
        total += held[sid] * price
    return None if missing else str(total), missing


def _configure_valuation(simulation, registration):
    require(set(registration) == {'calendar', 'initial_marks', 'registered_at'}, 'INVALID_VALUATION_REGISTRATION')
    origin = simulation['origin']; accepted = origin['ledger']['acceptance']['accepted_at']
    # This version requires contemporaneous initial accounting, not retrospective registration.
    require(stamp(registration['registered_at']) == stamp(accepted), 'INITIAL_VALUATION_AT_ACCEPTANCE_REQUIRED')
    calendar = registration['calendar']; sessions = calendar['session_dates']
    require(sessions and sessions == sorted(set(sessions)) and set(sessions) == set(calendar['closes']), 'COMPLETE_DECLARED_CALENDAR_REQUIRED')
    require(type(calendar['source_references']) is list and calendar['source_references'] and
            all(type(v) is str and v.strip() for v in calendar['source_references']), 'CALENDAR_SOURCE_REQUIRED')
    start = stamp(accepted).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(sessions[0] == start, 'CALENDAR_START_MISMATCH')
    for session in sessions:
        require(date.fromisoformat(session).isoformat() == session and
                stamp(calendar['closes'][session]).astimezone(ZoneInfo('America/New_York')).date().isoformat() == session,
                'CALENDAR_CLOSE_DATE_MISMATCH')
    require(stamp(calendar['closes'][start]) > stamp(accepted), 'CALENDAR_CLOSE_BEFORE_ACCEPTANCE')
    require(all(stamp(order['session_close']) == stamp(calendar['closes'][start]) for order in origin['ledger']['orders'].values()), 'ACCEPTED_CALENDAR_CLOSE_MISMATCH')
    equity, missing = _value(origin, registration['initial_marks'], accepted, registration['registered_at'], initial=True)
    require(not missing and exact(equity) > 0, 'COMPLETE_POSITIVE_INITIAL_EQUITY_REQUIRED')
    simulation['valuation'] = dict(registration=deepcopy(registration), initial_equity=equity,
        records=[], performance=None, calendar_authenticated=False, source_authenticated=False,
        independent_oos=False, corrections_supported=False,
        limitations=['Declared calendar may omit sessions; metrics are conditional on its completeness.',
                    'No inferred distributions, corporate actions, cash flows, or share-unit adjustments.',
                    'Missing close attempts are retained; retrospective replacement is unsupported.'])
    simulation['scope'] = _scope(simulation)


def register_valuation(*, simulation, calendar, initial_marks, registered_at):
    rebuilt, _, _ = _rebuild(simulation)
    registration = dict(calendar=deepcopy(calendar), initial_marks=deepcopy(initial_marks), registered_at=registered_at)
    if 'valuation' in rebuilt:
        require(rebuilt['valuation']['registration'] == registration, 'VALUATION_REGISTRATION_CHANGED')
        return rebuilt
    require(not rebuilt['batches'], 'REGISTER_BEFORE_SIMULATION_OUTCOMES')
    _configure_valuation(rebuilt, registration)
    return rebuilt


def _record_close(simulation, request):
    require('valuation' in simulation, 'VALUATION_REGISTRATION_REQUIRED')
    require(set(request) == {'session', 'marks', 'observed_at'}, 'INVALID_CLOSE_REQUEST')
    valuation = simulation['valuation']; calendar = valuation['registration']['calendar']
    index = len(valuation['records'])
    require(index < len(calendar['session_dates']) and request['session'] == calendar['session_dates'][index], 'NEXT_DECLARED_SESSION_REQUIRED')
    close = calendar['closes'][request['session']]
    require(stamp(request['observed_at']) >= stamp(close), 'CLOSE_NOT_OBSERVED')
    ledger = simulation['chain']['ledger']
    require(all(stamp(order['session_close']) == stamp(close) for order in ledger['orders'].values()
                if stamp(order['accepted_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat() == request['session']),
            'ACCEPTED_CALENDAR_CLOSE_MISMATCH')
    require(stamp(ledger['last_effective_at']) <= stamp(close), 'STATE_ALREADY_AFTER_REQUESTED_CLOSE')
    equity, missing = _value(simulation['chain'], request['marks'], close, request['observed_at'])
    unresolved = [oid for oid, order in ledger['orders'].items() if not order['closed']]
    if unresolved: equity = None
    row = dict(session=request['session'], date=request['session'], session_close=close,
        observed_at=request['observed_at'], revision=ledger['revision'], cash=ledger['cash'],
        shares=deepcopy(ledger['shares']), recorded_fees=ledger['recorded_fees'],
        equity=equity, missing_marks=missing, unresolved_orders=unresolved,
        status='COMPLETE' if equity is not None else 'BLOCKED')
    valuation['records'].append(row)
    complete = all(item['status'] == 'COMPLETE' for item in valuation['records'])
    performance = dict(status='COMPLETE_ON_DECLARED_SESSIONS' if complete else 'INCOMPLETE',
        initial_equity=valuation['initial_equity'], current_equity=equity,
        cumulative_return=None, drawdown=None, calendar_authenticated=False, independent_oos=False,
        drawdown_scope='OBSERVED_DECLARED_CLOSES_ONLY; UNOBSERVED_DAYS_AND_INTRADAY_LOSSES_NOT_COVERED')
    if complete:
        points = [dict(date='INITIAL_ACCEPTANCE', equity=valuation['initial_equity'])] + valuation['records']
        performance.update(cumulative_return=str(exact(equity)/exact(valuation['initial_equity'])-1),
                           drawdown=drawdown_summary(points))
    valuation['performance'] = performance
    return deepcopy(row)


def record_close(*, simulation, session, marks, observed_at):
    rebuilt, _, last_at = _rebuild(simulation)
    request = dict(session=session, marks=deepcopy(marks), observed_at=observed_at)
    for batch in rebuilt['batches']:
        if batch.get('kind') == 'CLOSE_VALUATION' and batch['request'] == request:
            return rebuilt
    require(stamp(observed_at) >= last_at, 'SIMULATION_TIME_REVERSED')
    result = _record_close(rebuilt, request)
    rebuilt['batches'].append(dict(kind='CLOSE_VALUATION', request=request, result=result))
    return rebuilt
