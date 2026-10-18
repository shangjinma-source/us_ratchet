"""Explicit monthly observation in an isolated simulator; never installs a job.

Publication and source reviews remain explicit prerequisites. Registry/search and
quote evidence are stored only beneath the caller's isolated attempt directory.
An interrupted attempt is not retried automatically.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from backtest.current_quantity_v2_annual_clock import build_observation_clock
from backtest.current_quantity_v2_simulated_settlement import _rebuild, accept_orders
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_decision import QuantityV2MonthlyDecisionRegistry
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
from data.current_quantity_v2_monthly_sources import QuantityV2MonthlySources
from data.current_quantity_v2_monthly_training import build_monthly_training_package
from data.current_quantity_v2_monthly_training_reader import MonthlyMarketTrainingReader


def digest(value):
    return sha256(canonical(value)).hexdigest()


class _ReadOnlyChain:
    def __init__(self, chain): self.chain = deepcopy(chain)
    def read(self, account_id):
        require(account_id == self.chain['ledger']['account_id'], 'SIMULATION_ACCOUNT_MISMATCH')
        return deepcopy(self.chain)


def observe_monthly(*, simulation, root, configuration_path, configuration_sha256,
                    schedule_path, session, triggered_at, storage_directory,
                    paper_review_provider, review_reader, fetch, clock,
                    pullback_policy=None, pullback_cap_store=None):
    """Return a new simulation after one monthly observation, or same-month wait.

    triggered_at records the scheduler event within the scheduled 10:00 minute.
    All research/capture/acceptance use clock(), never that historical timestamp.
    Exact completed retries accept either the original or returned simulation.
    """
    simulation, _, last_at = _rebuild(simulation)
    trigger = stamp(triggered_at)
    local_trigger = trigger.astimezone(ZoneInfo('America/New_York'))
    require(local_trigger.date().isoformat() == session,
            'TRIGGER_SESSION_MISMATCH')
    require((local_trigger.hour, local_trigger.minute) == (10, 0), 'SIMULATION_TRIGGER_OUTSIDE_WINDOW')
    request = dict(simulation_id=simulation['simulation_id'], session=session,
        configuration_path=configuration_path, configuration_sha256=configuration_sha256,
        schedule_path=schedule_path, triggered_at=trigger.isoformat())
    directory = Path(storage_directory).resolve() / digest([simulation['simulation_id'], session])
    request_path = directory/'attempt.json'; result_path = directory/'result.json'
    if request_path.exists():
        previous = json.loads(request_path.read_bytes())
        require(previous['request'] == request, 'SIMULATION_ATTEMPT_CONFLICT')
        require(result_path.is_file(), 'SIMULATION_ATTEMPT_INCOMPLETE_NO_AUTOMATIC_RETRY')
        saved = json.loads(result_path.read_bytes())
        require(saved['sha256'] == digest(saved['result']), 'SIMULATION_RESULT_CHANGED')
        result = saved['result']; _rebuild(result['simulation'])
        require(digest(simulation) in (previous['simulation_sha256'], digest(result['simulation'])),
                'SIMULATION_ATTEMPT_STATE_CHANGED')
        return result
    state = simulation['chain']; ledger = state['ledger']
    old = active_proposal(ledger)
    old_month = old.get('target_month') or old['causal_inputs']['target_mandate']['target_month']
    require(old_month <= session[:7], 'SIMULATION_MONTH_REVERSED')
    if old_month == session[:7]:
        # This entry point owns monthly selection only. Daily continuation does
        # not require a fresh monthly configuration and is handled separately.
        return dict(status='SAME_MONTH_NO_RESELECTION', simulation=deepcopy(simulation),
            search_calls=0, accepted_at=None, simulation_only=True, real_account=False,
            forward_activated=False, source_authenticated=False,
            triggered_at=trigger.isoformat(), session=session)
    config = MonthlyFileConfiguration(root=root, path=configuration_path,
                                      sha256_value=configuration_sha256, clock=clock)
    supplied = config.market_reader(state)
    package = supplied['source_package']
    require(schedule_path in package['files'], 'SIMULATION_SCHEDULE_NOT_PINNED')
    schedule = json.loads(package['files'][schedule_path])
    require(schedule['schema'] == 'SCHEDULED_REGULAR_SESSIONS_V1', 'SIMULATION_SCHEDULE_SCHEMA')
    rows = [s for s in schedule['sessions'] if s['date'] == session]
    require(len(rows) == 1, 'SIMULATION_SESSION_NOT_SCHEDULED')
    # Publisher validates NY-local date boundaries; its V1 sessions need not
    # repeat timezone. Normalize that explicit contract for the clock helper.
    rows = [dict(rows[0], timezone=rows[0].get('timezone', 'America/New_York'))]
    observation = build_observation_clock(rows)[0]
    require(stamp(observation['observation_at']) <= trigger < stamp(observation['observation_at'])+timedelta(minutes=1),
            'SIMULATION_TRIGGER_OUTSIDE_WINDOW')
    last_clock = [max(trigger, last_at)]
    def actual_clock():
        now = stamp(clock())
        require(last_clock[0] <= now < stamp(observation['session_close']), 'SIMULATION_CLOCK_OUTSIDE_SESSION')
        last_clock[0] = now
        return now
    actual_clock()
    directory.mkdir(parents=True, exist_ok=False)
    with request_path.open('xb') as stream:
        stream.write(canonical(dict(request=request, simulation_sha256=digest(simulation))))
    try:
        result = dict(simulation=deepcopy(simulation), simulation_only=True, real_account=False,
            forward_activated=False, source_authenticated=False, triggered_at=trigger.isoformat(),
            scheduled_observation_at=observation['observation_at'], session=session)
        reader = MonthlyMarketTrainingReader(market_reader=config.market_reader,
            paper_review_provider=paper_review_provider, clock=actual_clock)
        training = build_monthly_training_package(state, **reader.capture(state), now=actual_clock())
        registry = QuantityV2MonthlyDecisionRegistry(storage_root=directory/'registry', clock=actual_clock)
        selected = registry.generate(state, training)
        require(selected['status'] == 'READY', 'MONTHLY_SIMULATION_SELECTION_UNAVAILABLE')
        registration = selected['registration_id']
        sources = QuantityV2MonthlySources(storage_root=directory/'captures',
            decision_reader=lambda current: registry.decision_package(registration, current),
            review_reader=review_reader, fetch=fetch, clock=actual_clock,
            pullback_policy=pullback_policy, pullback_cap_store=pullback_cap_store)
        capture = sources.capture(state)
        bridge = QuantityV2MonthlySourceBridge(store=_ReadOnlyChain(state),
            resolver=sources.resolve, clock=actual_clock)
        preview = bridge.preview(account_id=ledger['account_id'],
            decision_id=selected['capital_decision']['decision_id'], expected_revision=ledger['revision'])
        accepted_at = actual_clock().isoformat()
        proposal = bridge.monthly_resolver(state, preview['proposal_id'], accepted_at)
        accepted_at = actual_clock().isoformat()
        updated = accept_orders(simulation=simulation, proposal=proposal,
            acceptance_id='monthly-observation-'+session, accepted_at=accepted_at, kind='MONTHLY_RETARGET')
        result.update(status='SIMULATED_MONTHLY_ACCEPTED', simulation=updated,
            registration_id=registration, proposal_id=proposal['proposal_id'],
            accepted_at=accepted_at, search_calls=1, capture_receipt=capture['receipt'])
        terminal=dict(request_sha256=digest(request),base_revision=digest(simulation),
            registration_id=registration,proposal_id=proposal['proposal_id'],accepted_at=accepted_at,
            simulation_sha256=digest(updated),capture_receipt=capture['receipt'])
        terminal_raw=canonical(terminal)
        with (directory/'acceptance.json').open('xb') as stream: stream.write(terminal_raw)
        result['acceptance_receipt_sha256']=sha256(terminal_raw).hexdigest()
        with result_path.open('xb') as stream:
            stream.write(canonical(dict(result=result, sha256=digest(result))))
        return result
    except Exception as error:
        with (directory/'failed.json').open('xb') as stream:
            stream.write(canonical(dict(status='BLOCKED', error_type=type(error).__name__,
                automatic_retry=False, simulation_mutated=False)))
        raise


def monthly_operation_request(*, simulation_id, root, storage_directory, configuration_path,
                              configuration_sha256, schedule_path, session, triggered_at):
    return dict(kind='BOUND_MONTHLY_OBSERVATION_V1', root=str(Path(root).resolve()),
        storage_directory=str(Path(storage_directory).resolve()), monthly_request=dict(
            simulation_id=simulation_id, session=session, configuration_path=configuration_path,
            configuration_sha256=configuration_sha256, schedule_path=schedule_path,
            triggered_at=stamp(triggered_at).isoformat()))


def apply_monthly(*, store, simulation_id, expected_revision, operation_id, **arguments):
    """Bind the monthly attempt before invoking its existing idempotent workflow."""
    require('simulation' not in arguments, 'STORE_OWNS_SIMULATION_INPUT')
    request = monthly_operation_request(simulation_id=simulation_id, **{k:arguments[k] for k in
        ('root','storage_directory','configuration_path','configuration_sha256','schedule_path','session','triggered_at')})
    return store.apply(simulation_id=simulation_id, expected_revision=expected_revision,
        operation_id=operation_id, request=request,
        transform=lambda state: observe_monthly(simulation=state, **arguments)['simulation'])


def read_bound_monthly_result(request, simulation, expected_revision):
    """Read-only recovery proof: registered selection and saved capture reproduce acceptance."""
    require(set(request)=={'kind','root','storage_directory','monthly_request'}
            and request['kind']=='BOUND_MONTHLY_OBSERVATION_V1', 'MONTHLY_RECOVERY_REQUEST_REQUIRED')
    bound=request['monthly_request']
    require(set(bound)=={'simulation_id','session','configuration_path','configuration_sha256','schedule_path','triggered_at'}
            and bound['simulation_id']==simulation['simulation_id'] and digest(simulation)==expected_revision,
            'MONTHLY_RECOVERY_BASE_MISMATCH')
    directory=Path(request['storage_directory'])/digest([bound['simulation_id'],bound['session']])
    def read(name):
        path=directory/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=128*1024*1024,
                'MONTHLY_RECOVERY_EVIDENCE_UNAVAILABLE')
        return path.read_bytes()
    attempt_raw=read('attempt.json'); result_raw=read('result.json'); terminal_raw=read('acceptance.json')
    attempt=json.loads(attempt_raw); saved=json.loads(result_raw); result=saved['result']
    require(attempt==dict(request=bound,simulation_sha256=expected_revision), 'MONTHLY_RECOVERY_ATTEMPT_MISMATCH')
    require(saved['sha256']==digest(result), 'MONTHLY_RECOVERY_RESULT_CHANGED')
    terminal=json.loads(terminal_raw)
    require(result.get('acceptance_receipt_sha256')==sha256(terminal_raw).hexdigest()
            and terminal==dict(request_sha256=digest(bound),base_revision=expected_revision,
                registration_id=result['registration_id'],proposal_id=result['proposal_id'],
                accepted_at=result['accepted_at'],simulation_sha256=digest(result['simulation']),
                capture_receipt=result['capture_receipt']), 'MONTHLY_RECOVERY_TERMINAL_MISMATCH')
    require(result['status']=='SIMULATED_MONTHLY_ACCEPTED' and result['session']==bound['session']
            and result['triggered_at']==bound['triggered_at'], 'MONTHLY_RECOVERY_RESULT_BINDING')
    restored,_,_=_rebuild(result['simulation'])
    require(len(restored['batches'])==len(simulation['batches'])+1
            and restored['batches'][:-1]==simulation['batches'], 'MONTHLY_RECOVERY_HISTORY_MISMATCH')
    last=restored['batches'][-1]
    require(last.get('kind')=='ACCEPTANCE' and last['request']['kind']=='MONTHLY_RETARGET'
            and last['request']['acceptance_id']=='monthly-observation-'+bound['session']
            and last['request']['accepted_at']==result['accepted_at'], 'MONTHLY_RECOVERY_ACCEPTANCE_MISMATCH')
    proposal=last['request']['proposal']; state=simulation['chain']
    registry=QuantityV2MonthlyDecisionRegistry(storage_root=directory/'registry')
    selected=registry.read(result['registration_id'],state)
    require(selected['status']=='READY' and selected['capital_decision']==proposal['causal_inputs']['capital_decision']
            and result['proposal_id']==proposal['proposal_id'], 'MONTHLY_RECOVERY_REGISTRATION_MISMATCH')
    config=MonthlyFileConfiguration(root=request['root'],path=bound['configuration_path'],
        sha256_value=bound['configuration_sha256'],clock=lambda:stamp(result['accepted_at']))
    supplied=config.market_reader(state)
    require(all(proposal['causal_inputs']['source_hashes'].get(p)==h
                for p,h in supplied['source_package']['source_hashes'].items()), 'MONTHLY_RECOVERY_CONFIGURATION_MISMATCH')
    receipt=result['capture_receipt']
    require(Path(receipt['root']).resolve()==(directory/'captures').resolve(), 'MONTHLY_RECOVERY_CAPTURE_LOCATION')
    sources=QuantityV2MonthlySources(storage_root=directory/'captures',decision_reader=None,review_reader=None)
    package=sources._read_saved({'receipt':receipt})
    bridge=QuantityV2MonthlySourceBridge(store=_ReadOnlyChain(state),resolver=lambda *_:deepcopy(package),
        clock=lambda:stamp(proposal['causal_inputs']['now']))
    preview=bridge.preview(account_id=state['ledger']['account_id'],
        decision_id=selected['capital_decision']['decision_id'],expected_revision=state['ledger']['revision'])
    reproduced=bridge.monthly_resolver(state,preview['proposal_id'],result['accepted_at'])
    require(reproduced==proposal, 'MONTHLY_RECOVERY_PROPOSAL_MISMATCH')
    expected=accept_orders(simulation=simulation,proposal=proposal,acceptance_id=last['request']['acceptance_id'],
        accepted_at=result['accepted_at'],kind='MONTHLY_RETARGET')
    require(expected==restored, 'MONTHLY_RECOVERY_SIMULATION_MISMATCH')
    return restored,dict(kind='BOUND_MONTHLY_EXTERNAL_RESULT_V1',attempt_sha256=sha256(attempt_raw).hexdigest(),
        result_file_sha256=sha256(result_raw).hexdigest(),result_sha256=saved['sha256'],
        acceptance_receipt_sha256=sha256(terminal_raw).hexdigest(),
        original_request_sha256=digest(request),base_revision=expected_revision,
        registration_id=result['registration_id'],proposal_id=result['proposal_id'],capture_receipt=receipt)
