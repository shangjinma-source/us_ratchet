"""Two explicitly chosen historical targets, with a surviving-SID strategic anchor.

No selection, execution, price identity certification or current-asof claim.
Preparation binds complete corrected queues; building is one-shot in memory.
"""
from copy import deepcopy
from pathlib import Path
from types import FunctionType, SimpleNamespace
from weakref import WeakKeyDictionary, WeakSet
import yaml

from backtest import ndx_corrected_cutoff_snapshot_research as snapshot
from backtest import ndx_dynamic_refit_schedule_research as schedule

adapter = snapshot.adapter
ROOT = adapter.ROOT
BASE = ROOT / 'data/cache/research/corrected_frontier_cutoff_archive_20260919_v1'
QUEUES = (
    (str(BASE / '20230403_queue.json'), '8958f310aca0263e4e88eb124a09cda70a312ac50345203d4c22c63605963f90'),
    (str(BASE / '20230501_queue.json'), '183b2aeafe7cf84b05945099b769f62ab4bacee68851a9ac4644501177bd64a8'),
)
SEED = dict(path=str(BASE / '20230403_first_non_equal_refit.json'),
            sha256='4d6846dfe7283716985ac663ff42a7409320c53c51e28b4b694af71e33231df0')
SOURCE = Path(__file__).resolve()
LOADED = {str(SOURCE): adapter.archive.drift.file_sha(SOURCE),
          str(snapshot.SOURCE): snapshot.LOADED, str(schedule._SOURCE): schedule._LOADED_SHA}
_STATES = WeakKeyDictionary()
_SEALS = WeakKeyDictionary()
_VERIFIERS = WeakKeyDictionary()
_CONSUMED = WeakSet()
CALENDAR_SOURCE = dict(path=str(ROOT / 'data/cache/research/dynamic_frozen_v2/preference_retrospective_accounting_20260912.json'),
    sha256='3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59')
OBJECTIVE = dict(path=str(ROOT / 'config/ndx_portfolio_objective_v2.yaml'),
    sha256='4f299d67a96204c9da605d3d326b723e3ab88d31926702128000c176ea316c7d')


class PreparedPath:
    __slots__ = ('__weakref__',)


def _read(reference):
    if type(reference) is not dict or set(reference) != {'path', 'sha256'}:
        raise ValueError('Explicit path and external SHA required')
    return snapshot.read(reference['path'], reference['sha256'])


def _calendar(envelope):
    if (type(envelope) is not dict or set(envelope) != {'schema','source','calendar'}
            or envelope['schema'] != 'EXPLICIT_OBSERVED_EXECUTION_CALENDAR_V1'
            or envelope['source'] != CALENDAR_SOURCE):
        raise ValueError('Hard observed daily-calendar lineage required')
    parent = _read(CALENDAR_SOURCE)
    calendar = envelope['calendar']
    if calendar != [r['session'] for r in parent['execution']['daily']]:
        raise ValueError('Entire observed parent calendar required without compression')
    if type(calendar) is not list or not calendar or [schedule._day(d) for d in calendar] != sorted(set(calendar)):
        raise ValueError('Explicit ordered calendar artifact required')
    return deepcopy(calendar)


def _payload_digest(state):
    payload = deepcopy({k:v for k,v in state.items() if k != 'periods'})
    payload['periods'] = [schedule._input_payload(p, state['calendar']) for p in state['periods']]
    return adapter.digest(payload)


def _register(state, verify):
    prepared = PreparedPath()
    _STATES[prepared] = state
    _SEALS[prepared] = _payload_digest(state)
    _VERIFIERS[prepared] = verify
    return prepared


def _verify_prepared(prepared, extra):
    state = _STATES[prepared]
    if _payload_digest(state) != _SEALS[prepared]:
        raise ValueError('Prepared path, seed, period matrix or source memory changed')
    return _VERIFIERS[prepared](extra)


def prepare_explicit_path(*, path_path, path_sha256, calendar_path, calendar_sha256):
    path_ref = dict(path=str(Path(path_path).resolve()), sha256=path_sha256)
    calendar_ref = dict(path=str(Path(calendar_path).resolve()), sha256=calendar_sha256)
    path = _read(path_ref)
    calendar = _calendar(_read(calendar_ref))
    if (set(path) != {'schema', 'selection_policy', 'periods'}
            or path['schema'] != 'EXPLICIT_CORRECTED_TWO_PERIOD_PATH_V1'
            or type(path['selection_policy']) is not str or not path['selection_policy'].strip()
            or type(path['periods']) is not list or len(path['periods']) != 2):
        raise ValueError('Explicit two-period externally selected path required')
    sources = dict(LOADED)
    adapter.archive.merge(sources, {path_ref['path']:path_ref['sha256'], calendar_ref['path']:calendar_ref['sha256']})
    adapter.archive.merge(sources, {CALENDAR_SOURCE['path']:CALENDAR_SOURCE['sha256'], OBJECTIVE['path']:OBJECTIVE['sha256']})
    adapter.archive.strict({OBJECTIVE['path']:OBJECTIVE['sha256']})
    execution_contract = yaml.safe_load(Path(OBJECTIVE['path']).read_bytes())['execution_contract']
    periods, bindings, handles, gaps = [], [], [], []
    seed = None
    for index, (declaration, hard) in enumerate(zip(path['periods'], QUEUES)):
        if set(declaration) != {'queue', 'job_id', 'decision_date', 'execution_date', 'cutoff'}:
            raise ValueError('Exact explicit decision declaration required')
        if declaration['queue'] != dict(path=hard[0], sha256=hard[1]):
            raise ValueError('Only the two externally sealed original queues are supported')
        handle = snapshot.begin(queue_path=hard[0], queue_sha256=hard[1],
            **(dict(seed_path=SEED['path'], seed_sha256=SEED['sha256']) if index == 0 else {}))
        state = snapshot.state(handle)
        queue = state['queue']
        if (declaration['cutoff'] != queue['historical_cutoff'] or declaration['decision_date'] != queue['historical_cutoff']
                or declaration['execution_date'] != queue['coordinate']['selection_date']):
            raise ValueError('Original Close cutoff and next-Open selection coordinate required')
        entry = state['rows'].get(declaration['job_id'])
        if entry is None:
            raise ValueError('Explicit job absent from entire risk frontier/preference queue')
        if index == 0:
            seed = deepcopy(state['seed_value'])
            if entry['task']['job_id'] != seed['job_id'] or seed['result']['status'] != 'FITTED_FIVE_RISKS_PASSED':
                raise ValueError('First selected job must be the successful hard seed; never refit it')
        period = {k: declaration[k] for k in ('decision_date', 'execution_date', 'cutoff')}
        period.update(returns=deepcopy(state['changed']['returns']), selected=deepcopy(entry['selected']),
            weight_spec=entry['task']['weight_spec'], parameters=deepcopy(queue['fit_parameters']),
            source_hashes=deepcopy(state['sources']))
        periods.append(period)
        bindings.append(dict(queue=declaration['queue'], job_id=declaration['job_id'],
            full_candidate=deepcopy(entry), input_binding=deepcopy(queue['input_binding']),
            original_fourteen_parameter_contract=deepcopy(queue['original_fourteen_parameter_contract'])))
        adapter.archive.merge(sources, state['sources']);adapter.archive.merge(sources, state['additional'])
        gaps.extend(deepcopy(queue['historical_loader_gap_observations']))
        handles.append(handle)
    def verify(extra):
        merged = dict(sources);adapter.archive.merge(merged, extra)
        for handle in handles: snapshot.verify_all(snapshot.state(handle))
        adapter.audit.original.verify_gaps(gaps)
        return adapter.archive.verify_expected_sources(merged, adapter.archive.load_contract())
    verify({})
    # Reuse all original schedule input/clock/risk validation before allowing a fit.
    _run_targets(calendar, periods, seed['result']['refit'], verify, validate_only=True)
    return _register(dict(calendar=calendar, periods=periods, seed=seed, bindings=bindings,
        path=path, path_ref=path_ref, calendar_ref=calendar_ref, sources=sources,
        gaps=gaps, execution_contract=execution_contract), verify)


class _ValidatedWithoutFit(Exception):
    pass


def _run_targets(calendar, periods, seed_refit, verify, *, validate_only=False):
    """Private binding only; frozen builder and fitter globals remain untouched."""
    count = 0
    def fit(**kwargs):
        nonlocal count
        if validate_only:
            raise _ValidatedWithoutFit()
        count += 1
        if count == 1:
            if kwargs['previous_target_weights'] is not None:
                raise ValueError('First decision cannot inject previous targets')
            result = deepcopy(seed_refit)
        else:
            result = adapter.fitter.refit_dynamic_cutoff_weights(**kwargs)
        names = [kwargs['selected'][sid]['ticker'] for sid in sorted(kwargs['selected'])]
        frame = kwargs['returns'].iloc[-kwargs['fit_days']:][names]
        payload = dict(dates=[d.date().isoformat() for d in frame.index], tickers=names,
                       returns=frame.to_numpy().tolist())
        if (result.get('schema') != 'ndx_dynamic_cutoff_refit_research_v2'
                or result['fit_data_sha256'] != adapter.digest(payload)):
            raise ValueError('Exact corrected cutoff fit matrix differs')
        adapter.audit.original.require_false(result, ('point_in_time_verified', 'source_authenticity_verified',
            'promotion_allowed', 'historical_task_evaluation_performed', 'order_generation_allowed'))
        return result
    facade = SimpleNamespace(**{k:getattr(adapter.fitter,k) for k in ('previous','_sources')},
                             refit_dynamic_cutoff_weights=fit)
    namespace = dict(schedule.build_refit_schedule_research.__globals__)
    namespace.update(fitter=facade, _verify=verify)
    private = FunctionType(schedule.build_refit_schedule_research.__code__, namespace)
    try:
        result = private(calendar=deepcopy(calendar), decisions=deepcopy(periods))
    except _ValidatedWithoutFit:
        if not validate_only: raise
        return None
    if validate_only: raise ValueError('Nonempty path validation did not reach first fit')
    return result


def build_path_targets(prepared):
    if type(prepared) is not PreparedPath or prepared not in _STATES:
        raise ValueError('Private prepared path required')
    state = _STATES[prepared]
    if prepared in _CONSUMED: raise ValueError('One-shot path already attempted; no automatic refit')
    _CONSUMED.add(prepared)
    verify = lambda extra: _verify_prepared(prepared, extra)
    verify({})
    try:
        result = _run_targets(state['calendar'], state['periods'], state['seed']['result']['refit'], verify)
    finally:
        verify({})
    result.pop('source_hashes')
    result.update(schema='CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1',
        explicit_path=state['path'], path_reference=state['path_ref'], calendar_reference=state['calendar_ref'],
        period_bindings=state['bindings'], original_first_seed_wrapper=state['seed'], first_seed_reference=SEED,
        first_seed_imported_without_refit=True, new_fit_count=len(state['periods'])-1,
        historical_expected_source_hashes=state['sources'], archive_resolution=verify({}),
        historical_loader_gap_observations=state['gaps'], historical_full_source_closure_verified=False,
        cutoff_scope='TWO_ARCHIVED_HISTORICAL_DECISIONS_NOT_CURRENT_LIVE_ASOF',
        external_expected_decision_denominator_verified=False,
        original_training_capital_preserved_in_period_bindings=True,
        downstream_execution_contract_reference=OBJECTIVE,
        downstream_execution_capital_usd=state['execution_contract']['starting_capital_usd'],
        downstream_execution_cash_buffer_usd=state['execution_contract']['minimum_cash_buffer_usd'],
        downstream_execution_transaction_cost_bps=state['execution_contract']['transaction_cost_bps'],
        downstream_execution_contract_applied=False, independently_selected_winner=False)
    return result
