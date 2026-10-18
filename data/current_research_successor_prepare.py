"""Assemble explicitly reviewed saved evidence; never fetch, search or activate."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from data.current_research_saved_quote import read_saved_quote
from data.current_research_successor_inputs import SuccessorInputLoader, REGISTRY_SCHEMA
from data.current_research_monthly_policy import route_monthly_research_policy
from data.current_research_successor_plan import _review_roll_state, _bind_monthly_session


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def prepare_successor_input(state, *, root, expected_revision, decision_date, active_date,
                            calendar_path, source_hashes, raw_sources, held_unit_continuity,
                            admission, search_arguments=None, policy_mode='BOUND_MONTHLY_POLICY'):
    """Read only. Unit declarations and admission must come from explicit review.

    Scheduled calendar evidence does not certify absence of emergency closures.
    Provider events are observations, not a complete corporate-action registry.
    """
    loader = SuccessorInputLoader(root=root)
    pins = deepcopy(source_hashes)
    _require(isinstance(pins, dict) and calendar_path in pins, 'CALENDAR_SOURCE_NOT_PINNED')
    for name, digest in pins.items():
        _require(hashlib.sha256(loader._path(name).read_bytes()).hexdigest() == digest, 'SOURCE_HASH_MISMATCH:' + name)
    def refs(values):
        _require(isinstance(values, list) and values and all(isinstance(v, str) and v in pins for v in values), 'UNPINNED_REVIEW_REFERENCE')
    artifact = json.loads(loader._path(calendar_path).read_bytes())
    _require(artifact.get('schema') == 'SCHEDULED_REGULAR_SESSIONS_V1', 'INVALID_SCHEDULE_SCHEMA')
    _require(all(pins.get(k) == v for k, v in artifact.get('source_hashes', {}).items()), 'CALENDAR_EVIDENCE_PIN_MISMATCH')
    calendar = artifact['calendar']
    _review_roll_state(state, expected_revision, decision_date, active_date, calendar)
    sessions = artifact['sessions']
    _require(len({s['date'] for s in sessions}) == len(sessions), 'DUPLICATE_SCHEDULE_SESSION')
    sessions = {s['date']:s for s in sessions}
    for day in (decision_date, active_date):
        _require(day in sessions, 'SCHEDULE_SESSION_MISSING')
        _bind_monthly_session({}, target_month=day[:7], market_session=sessions[day], active_date=day, source_hashes=pins)
    _require(isinstance(admission, dict) and admission.get('status') == 'ACCEPTED_CONDITIONAL_RESEARCH_INPUT', 'EXPLICIT_REVIEW_REQUIRED')
    _require(isinstance(admission.get('reviewer'), str) and admission['reviewer'].strip(), 'REVIEWER_REQUIRED')
    _require(datetime.fromisoformat(admission['reviewed_at']).tzinfo is not None, 'REVIEW_TIME_REQUIRES_ZONE')
    reviewed = datetime.fromisoformat(admission['reviewed_at'])
    _require(datetime.fromisoformat(sessions[decision_date]['close_at']) <= reviewed, 'REVIEW_BEFORE_DECISION_CLOSE')
    refs(admission.get('evidence_references'))
    _require(isinstance(admission.get('limitations'), list) and admission['limitations'] and all(isinstance(v, str) and v.strip() for v in admission['limitations']), 'REVIEW_LIMITATIONS_REQUIRED')
    plan = state['plan']; old = plan['causal_inputs']
    month = old['research_snapshot'].get('target_month')
    if policy_mode == 'ADOPT_INITIAL_FROZEN_MONTHLY_POLICY':
        _require(month is None and len(state['plans']) == 1 and plan['strategy_version'] == 'PAPER_FROZEN_QUANTITY_V1', 'INVALID_INITIAL_POLICY_ADOPTION')
        month = plan['active_date'][:7]
    else:
        _require(policy_mode == 'BOUND_MONTHLY_POLICY', 'INVALID_POLICY_MODE')
    route = route_monthly_research_policy(decision_date=decision_date, active_date=active_date, calendar=calendar, current_target_month=month)
    _require(route['action'] != 'RESELECT' or search_arguments is not None, 'RESELECT_SEARCH_ARGUMENTS_REQUIRED')
    exposed = {s for s,q in state['shares'].items() if q > 0}
    if route['action'] == 'ROLL':
        exposed |= {s for s,q in plan['target_quantities'].items() if q > 0}
    required = exposed | (set(search_arguments['prices']) if search_arguments is not None else set())
    _require(required <= set(raw_sources), 'MISSING_HELD_TARGET_OR_CANDIDATE_SOURCE')
    historical = {}
    for previous in state['plans']:
        for row in previous['causal_inputs']['research_snapshot']['stocks']:
            historical.setdefault(row['security_id'], set()).add(row['ticker'])
    quotes = []; observations = {}; dividends = []
    for sid, source in raw_sources.items():
        basis = source.get('price_basis')
        _require(isinstance(basis, str) and basis.strip(), 'EXPLICIT_PRICE_BASIS_REQUIRED')
        refs(source.get('source_references'))
        if sid in exposed:
            _require(historical.get(sid) == {source['ticker']}, 'HISTORICAL_TICKER_MISMATCH')
            _require(old['quotes'][sid]['price_basis'] == basis, 'HELD_OR_TARGET_BASIS_CHANGED')
            declaration = held_unit_continuity.get(sid)
            _require(isinstance(declaration, dict) and declaration.get('from_date') == old['decision_date'] and declaration.get('to_date') == decision_date
                and declaration.get('price_basis') == basis and declaration.get('status') == 'NO_UNPROCESSED_ACTIONS', 'EXPLICIT_UNIT_CONTINUITY_REQUIRED')
            refs(declaration.get('source_references'))
        if search_arguments is not None and sid in search_arguments['prices']:
            _require(search_arguments.get('price_basis') == basis and search_arguments['metadata'][sid]['ticker'] == source['ticker'], 'SEARCH_SOURCE_COORDINATE_MISMATCH')
        observation = read_saved_quote(root=root, ticker=source['ticker'], expected_security_type=source['expected_security_type'], entry=source['entry'],
            relative_directory=source['relative_directory'], decision_date=decision_date, decision_session_close_at=sessions[decision_date]['close_at'])
        _require(datetime.fromisoformat(observation['received_at']) <= reviewed, 'CAPTURE_AFTER_REVIEW')
        for name, digest in observation['source_hashes'].items():
            _require(name not in pins or pins[name] == digest, 'RAW_SOURCE_PIN_CONFLICT')
            pins[name] = digest
        for event in observation['event_details']:
            in_interval = old['decision_date'] < event['session'] <= decision_date
            _require(not (sid in exposed and in_interval and event['kind'] == 'splits'), 'RETURNED_SPLIT_REQUIRES_EXPLICIT_UNIT_PROCESSING')
            _require(not (sid in exposed and in_interval and event['kind'] not in ('splits', 'dividends')), 'UNKNOWN_EXPOSED_CORPORATE_ACTION')
            if event['kind'] == 'dividends':
                dividends.append(dict(security_id=sid, **event))
        quote = dict(price=observation['ohlc']['close'], as_of=decision_date, price_kind='RAW_PROVIDER_CLOSE_DECIMAL')
        quotes.append(dict(quote, security_id=sid, ticker=source['ticker'], price_basis=basis,
            source_references=list(dict.fromkeys(source['source_references'] + list(observation['source_hashes'])))))
        observations[sid] = observation
    bundle = dict(account_id=state['account_id'], revision=expected_revision, parent_plan_id=plan['plan_id'], decision_date=decision_date,
        active_date=active_date, calendar=calendar, decision_session=sessions[decision_date], market_session=sessions[active_date],
        source_hashes=pins, valuation_quotes=quotes, held_unit_continuity=deepcopy(held_unit_continuity), admission=deepcopy(admission),
        quote_reference_policy='EXACT_RAW_DECISION_CLOSE_NO_ROUNDING', policy_mode=policy_mode, preparation_route=route, saved_quote_observations=observations, returned_dividends=dividends,
        limitations=['DIVIDENDS_OBSERVED_NOT_CREDITED_TO_CASH', 'SCHEDULED_SESSIONS_NOT_EMERGENCY_CLOSURE_CERTIFICATION',
                     'SOURCE_HASHES_NOT_MARKET_TRUTH_OR_ACTION_COMPLETENESS_CERTIFICATION'], research_only=True, execution_blocked=True)
    if search_arguments is not None:
        from fractions import Fraction
        _require(search_arguments.get('decision_date') == decision_date and search_arguments.get('quote_as_of') == decision_date, 'SEARCH_DATE_MISMATCH')
        actual = {q['security_id']:q['price'] for q in quotes}
        _require(all(Fraction(value) == Fraction(actual[sid]) for sid,value in search_arguments['prices'].items()), 'SEARCH_PRICE_MISMATCH')
        bundle['search_arguments'] = deepcopy(search_arguments)
    raw = _bytes(bundle); input_id = hashlib.sha256(raw).hexdigest()
    entry = dict(bundle_path=input_id+'.json', sha256=input_id, **{k:bundle[k] for k in ('account_id','revision','parent_plan_id')})
    return dict(bundle=bundle, input_id=input_id, registry_entry=entry, registration_performed=False)


def save_prepared_input(prepared, *, root, relative_directory, registry_path):
    """Explicit create-only export. Never overwrite/merge a live registry."""
    loader = SuccessorInputLoader(root=root, registry_path=registry_path)
    directory = loader._path(relative_directory); registry = loader._path(registry_path)
    raw = _bytes(prepared['bundle']); input_id = hashlib.sha256(raw).hexdigest()
    _require(input_id == prepared['input_id'], 'PREPARED_CONTENT_CHANGED')
    bundle_path = directory / (input_id+'.json')
    _require(not registry.exists() and not bundle_path.exists(), 'CREATE_ONLY_TARGET_ALREADY_EXISTS')
    entry = dict(prepared['registry_entry'], bundle_path=bundle_path.relative_to(loader.root).as_posix())
    directory.mkdir(parents=True, exist_ok=True); registry.parent.mkdir(parents=True, exist_ok=True)
    with bundle_path.open('xb') as stream:stream.write(raw)
    with registry.open('xb') as stream:stream.write(_bytes(dict(schema=REGISTRY_SCHEMA, entries={input_id:entry})))
    return dict(input_id=input_id, bundle_path=entry['bundle_path'], registry_path=registry_path)
