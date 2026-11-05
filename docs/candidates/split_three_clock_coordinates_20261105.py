"""Isolated three-clock coordinate preparation; unchanged distribution ledger.
All timing is content-reviewed and source-bound, not broker/source authorization.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from zoneinfo import ZoneInfo
from contextlib import closing
from pathlib import Path
import json,os,sqlite3,tempfile
from core.strategy_account_ledger import canonical,require,_revision
from core.strategy_account_split_v1 import moment
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.monthly_peak_exit import advance_monthly_exit
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_account_split_migration_v1 import checked_path


def review_timing(*, action, timing, now=None):
    proof=timing['review'];sources=timing['source_hex'];pins=timing['source_hashes']
    require(proof['schema']=='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2' and proof['action_id']==action['action_id']
        and proof['recorded_action_sha256']==sha256(canonical(action)).hexdigest(),'TIMING_ACTION_BINDING')
    require(set(sources)==set(pins) and 0<len(sources)<=8,'TIMING_SOURCE_DOMAIN')
    raw={name:bytes.fromhex(value) for name,value in sources.items()}
    require(sum(map(len,raw.values()))<=2*1024*1024 and all(sha256(raw[name]).hexdigest()==digest for name,digest in pins.items()),'TIMING_SOURCE_HASH')
    clocks=proof['clock_source_references']
    require(set(clocks)=={'distribution_at','quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at'}
        and all(type(refs)is list and refs and len(refs)==len(set(refs)) and set(refs)<=set(pins) for refs in clocks.values()),'TIMING_CLOCK_EVIDENCE_REQUIRED')
    distribution,quote,tradable,known=map(moment,(proof['distribution_at'],proof['quote_unit_effective_at'],proof['broker_tradable_at'],proof['tradable_evidence_received_at']))
    require(distribution==moment(action['effective_at']) and distribution<=quote and distribution<=tradable<=known,'TIMING_CLOCK_ORDER')
    require(proof['tradable_evidence_semantics']=='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE','TIMING_ACTUAL_TRADABILITY_REQUIRED')
    calendar=timing['calendar']
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ'
        and timing['calendar_sha256']==sha256(canonical(calendar)).hexdigest(),'TIMING_CALENDAR_BINDING')
    sessions=calendar['sessions'];dates=[r['date'] for r in sessions]
    require(dates==sorted(set(dates)) and bool(dates),'TIMING_CALENDAR_ORDER')
    bounds=[(moment(r['open']),moment(r['close'])) for r in sessions]
    require(all(a.astimezone(ZoneInfo('America/New_York')).date().isoformat()==r['date']==b.astimezone(ZoneInfo('America/New_York')).date().isoformat() for r,(a,b) in zip(sessions,bounds)),'TIMING_CALENDAR_SESSION_DATE')
    require(all(a<b for a,b in bounds) and all(bounds[i][1]<bounds[i+1][0] for i in range(len(bounds)-1)),'TIMING_CALENDAR_CLOCKS')
    require(not any(a<quote<b for a,b in bounds),'SPLIT_INTRADAY_UNIT_HISTORY_UNSUPPORTED')
    candidates=[r for r in sessions if moment(r['open'])>=quote]
    require(candidates and any(a<=quote for a,b in bounds),'TIMING_NEXT_FULL_SESSION_REQUIRED')
    boundary=candidates[0]['open']
    if now is not None:
        require(max(quote,tradable,known,moment(action['broker_confirmed_at']))<=moment(now),'TIMING_NOT_EXECUTABLE_YET')
    return dict(proof,quote_bar_boundary_at=boundary,timing_sha256=sha256(canonical(timing)).hexdigest())


def project_split_risk(*, account_after, action_id, risk_before, quantities_before, timing):
    require(account_after.get('revision') == _revision(account_after), 'SPLIT_ACCOUNT_INTEGRITY')
    events = [row for row in account_after['events']
              if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id]
    require(len(events) == 1, 'SPLIT_RECORDED_ACTION_REQUIRED')
    event = events[0]['payload']
    sid, ratio = event['security_id'], event['ratio']
    same_security_actions = [row['payload'] for row in account_after['events']
                             if row['payload']['kind'] == 'SPLIT_CONFIRMED'
                             and row['payload']['security_id'] == sid]
    require(same_security_actions[-1] == event, 'SPLIT_LATER_ACCOUNT_ACTION_REQUIRES_REVIEW')
    require(type(ratio) is int and ratio > 1, 'INTEGER_FORWARD_SPLIT_REQUIRED')
    require(risk_before['schema'] == 'MONTHLY_PEAK_EXIT_V1'
            and risk_before['account_id'] == account_after['account_id'], 'SPLIT_RISK_ACCOUNT_MISMATCH')
    require(sid in risk_before['peaks'] and sid in risk_before['last_closes'], 'SPLIT_RISK_DOMAIN_MISSING')
    require(risk_before['unit_ids'][sid] == event['old_unit_id'], 'SPLIT_RISK_OLD_UNIT_REQUIRED')
    clocks=review_timing(action=event,timing=timing)
    effective_day = moment(clocks['quote_bar_boundary_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(risk_before['session_date'] < effective_day, 'SPLIT_RISK_ALREADY_PAST_BOUNDARY')
    require(type(quantities_before) is dict and all(type(q) is int and q >= 0 for q in quantities_before.values()),
            'SPLIT_TARGET_QUANTITIES_INVALID')
    require(set(quantities_before) <= set(risk_before['peaks']), 'SPLIT_TARGET_RISK_DOMAIN')
    transformed = deepcopy(risk_before)
    for field in ('peaks', 'last_closes'):
        old = Fraction(risk_before[field][sid])
        require(old > 0, 'SPLIT_RISK_PRICE_INVALID')
        transformed[field][sid] = str(old / ratio)
    transformed['unit_ids'][sid] = event['new_unit_id']
    quantities = deepcopy(quantities_before)
    if sid in quantities:
        quantities[sid] *= ratio
    # Keeping exited and the decision epoch prevents a corporate action from
    # accidentally resetting the same-month exit rule.
    binding = dict(account_id=account_after['account_id'], account_revision=account_after['revision'],
                   action_sha256=sha256(canonical(event)).hexdigest(),
                   risk_before_sha256=sha256(canonical(risk_before)).hexdigest(),
                   quantities_before_sha256=sha256(canonical(quantities_before)).hexdigest())
    result = dict(schema='SPLIT_RISK_UNIT_PROJECTION_V1', binding=binding,
                  risk_state=transformed, target_quantities=quantities,
                  effective_at=event['effective_at'], quote_unit_effective_at=clocks['quote_unit_effective_at'],quote_bar_boundary_at=clocks['quote_bar_boundary_at'],timing_sha256=clocks['timing_sha256'], orders_created=False,
                  production_activated=False, requires_coordinated_publication=True)
    result['projection_sha256'] = sha256(canonical(result)).hexdigest()
    return result

def project_native_split(*, account_after, action_id, risk_before, target, expected_proposal_id, timing):
    proposal = build_frontier_proposal(target=target)
    require(proposal['proposal_id'] == expected_proposal_id, 'SPLIT_STALE_PROPOSAL')
    require(target['payload']['account_id'] == account_after['account_id'], 'SPLIT_TARGET_ACCOUNT_MISMATCH')
    require(risk_before.get('target_month') == target['payload']['target_month'],
            'SPLIT_RISK_TARGET_MONTH_MISMATCH')
    projected = project_split_risk(account_after=account_after, action_id=action_id,
        risk_before=risk_before, quantities_before=proposal['payload']['proposed_target_quantities'],timing=timing)
    action = next(row['payload'] for row in account_after['events']
                  if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id)
    clocks=review_timing(action=action,timing=timing)
    effective = moment(clocks['quote_bar_boundary_at'])
    require(moment(target['payload']['created_at']) < moment(action['effective_at']), 'SPLIT_TARGET_ALREADY_DISTRIBUTED')
    require(moment(target['payload']['created_at']) < effective, 'SPLIT_TARGET_ALREADY_POST_ACTION')
    require(target['payload']['target_month'] == effective.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'),
            'SPLIT_TARGET_MONTH_REQUIRES_REVIEW')
    original_quantities = dict(target['payload']['target_quantities'])
    if action['security_id'] in original_quantities:
        original_quantities[action['security_id']] *= action['ratio']
    payload = dict(schema='NATIVE_TARGET_SPLIT_TRANSITION_V1',
        timing_bundle=deepcopy(timing),account_revision=account_after['revision'], original_target_id=target['target_id'],
        original_proposal_id=proposal['proposal_id'], action_id=action_id,
        projected_original_quantities=original_quantities, risk_projection=projected,
        executable=False, orders_created=False, production_activated=False)
    return dict(transition_id=sha256(canonical(payload)).hexdigest(), payload=payload)

def project_history_units(*, observations, action, expected_sessions, timing):
    require(action.get('kind') == 'SPLIT_CONFIRMED', 'SPLIT_ACTION_REQUIRED')
    sid, ratio = action['security_id'], action['ratio']
    require(type(ratio) is int and ratio > 1, 'INTEGER_FORWARD_SPLIT_REQUIRED')
    require(action['old_unit_id'] != action['new_unit_id'], 'SPLIT_UNIT_CHANGE_REQUIRED')
    clocks=review_timing(action=action,timing=timing)
    effective_day = moment(clocks['quote_bar_boundary_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(type(expected_sessions) is list and bool(expected_sessions)
            and expected_sessions == sorted(set(expected_sessions)), 'SPLIT_EXPECTED_SESSIONS_REQUIRED')
    require([row['session_date'] for row in observations] == expected_sessions, 'SPLIT_FULL_HISTORY_REQUIRED')
    decisions = {row['decision_date'] for row in observations}
    require(len(decisions) == 1 and next(iter(decisions)) == expected_sessions[0]
            and expected_sessions[0] < effective_day, 'SPLIT_HISTORY_EPOCH_REQUIRED')
    normalized = []
    for original in observations:
        require(set(original) == {'decision_date','session_date','closes','unit_ids','evidence_sha256'},
                'SPLIT_HISTORY_ROW_FIELDS')
        digest = original['evidence_sha256']
        require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                'SPLIT_HISTORY_EVIDENCE_REQUIRED')
        require(set(original['closes']) == set(original['unit_ids']) and sid in original['closes'],
                'SPLIT_HISTORY_DOMAIN_REQUIRED')
        row = deepcopy(original)
        before = row['session_date'] < effective_day
        require(row['unit_ids'][sid] == (action['old_unit_id'] if before else action['new_unit_id']),
                'SPLIT_HISTORY_UNIT_MISMATCH')
        require(all(Fraction(value) > 0 for value in row['closes'].values()), 'SPLIT_HISTORY_PRICE_INVALID')
        if before:
            row['closes'][sid] = str(Fraction(row['closes'][sid]) / ratio)
            row['unit_ids'][sid] = action['new_unit_id']
        content = {key:value for key,value in row.items() if key != 'evidence_sha256'}
        # Matches monthly_exit_observations' content ID, not a source receipt.
        row['evidence_sha256'] = sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        normalized.append(row)
    payload = dict(schema='DERIVED_SPLIT_HISTORY_V1', action_sha256=sha256(canonical(action)).hexdigest(),
                   timing_sha256=clocks['timing_sha256'], original_observations=deepcopy(observations), normalized_observations=normalized,
                   source_authenticated=False, orders_created=False)
    return dict(history_projection_sha256=sha256(canonical(payload)).hexdigest(), payload=payload)

def prepare_split_risk(*, destination_path, account_after, action_id, risk_before,
                       target, expected_proposal_id, observations, expected_sessions, timing):
    destination = checked_path(destination_path)
    require(not destination.exists(), 'SPLIT_RISK_DESTINATION_EXISTS')
    require(destination.parent.is_dir(), 'SPLIT_RISK_PARENT_REQUIRED')
    transition = project_native_split(account_after=account_after, action_id=action_id,
        risk_before=risk_before, target=target, expected_proposal_id=expected_proposal_id,timing=timing)
    action = next(row['payload'] for row in account_after['events']
                  if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id)
    history = project_history_units(observations=observations, action=action, expected_sessions=expected_sessions,timing=timing)
    quantities = build_frontier_proposal(target=target)['payload']['proposed_target_quantities']
    prefix = [row for row in observations if row['session_date'] <= risk_before['session_date']]
    require(prefix and prefix[-1]['session_date'] == risk_before['session_date'], 'SPLIT_RISK_PREFIX_REQUIRED')
    replayed = None
    for row in prefix:
        replayed = advance_monthly_exit(state=replayed, account_id=account_after['account_id'],
            baseline_targets=quantities, **{key:value for key,value in row.items() if key != 'evidence_sha256'})['state']
    if 'target_month' in risk_before:
        replayed['target_month'] = risk_before['target_month']
    require(replayed == risk_before, 'SPLIT_RISK_PREFIX_STATE_MISMATCH')
    projection = transition['payload']['risk_projection']
    descriptor, name = tempfile.mkstemp(prefix='.split-risk-', suffix='.sqlite3', dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        store = MonthlyPeakExitStore(temporary)
        result = store.advance(account_id=account_after['account_id'], expected_previous_session=None,
            observations=history['payload']['normalized_observations'],
            baseline_targets=projection['target_quantities'], target_month=target['payload']['target_month'])
        envelope = dict(schema='SPLIT_RISK_PREPARATION_V1', transition=transition, history=history,
                        original_risk_state=risk_before, action=action,timing_bundle=deepcopy(timing),
                        result=result, production_activated=False, source_authenticated=False)
        raw = canonical(envelope).decode()
        require(len(raw.encode()) <= 32*1024*1024, 'SPLIT_RISK_PREPARATION_BUDGET')
        with closing(sqlite3.connect(temporary)) as connection:
            connection.execute('CREATE TABLE split_preparation (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL, digest TEXT NOT NULL)')
            connection.execute('INSERT INTO split_preparation VALUES(1,?,?)', (raw, sha256(raw.encode()).hexdigest()))
            connection.commit()
        require(MonthlyPeakExitStore(temporary).read(account_after['account_id']) == result['state'],
                'SPLIT_RISK_RESTART_MISMATCH')
        with closing(sqlite3.connect(temporary)) as connection:
            saved, digest = connection.execute('SELECT payload,digest FROM split_preparation').fetchone()
            require(saved == raw and sha256(saved.encode()).hexdigest() == digest, 'SPLIT_RISK_ARCHIVE_MISMATCH')
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        database_digest = sha256(temporary.read_bytes()).hexdigest()
        checked_path(destination)
        os.link(temporary, destination)
        return dict(status='SPLIT_RISK_PREPARED_NOT_ACTIVATED', destination_sha256=database_digest,
                    transition_id=transition['transition_id'], account_revision=account_after['revision'],
                    final_state=result['state'], requires_live_binding_recheck=True, source_authenticated=False)
    finally:
        temporary.unlink(missing_ok=True)
