"""IO-free one-attempt batch lifecycle. Hooks are test seams, not authorization.

Only the source-bound worker may supply production hooks. This module never
imports an evaluator, touches a file, retries a hook, or projects an input task.
"""
from copy import deepcopy

OUTCOMES = {
    'FEASIBLE': 'inspected_feasible',
    'INFEASIBLE': 'inspected_infeasible',
    'EVALUATION_EXCEPTION': 'evaluation_exception',
    'NOT_EVALUATED_TECHNICAL_STOP': 'supplied_not_evaluated_technical',
    'NOT_EVALUATED_BUDGET': 'supplied_not_evaluated_budget',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def error_record(error):
    try:
        message = str(error)
    except BaseException as failure:
        message = 'ERROR_STRING_FAILED: ' + type(failure).__name__
    return {'type': type(error).__name__, 'message': message}


def checked_runs(descriptor, plans, value, inspection):
    """Map only an independently accepted full return to ordinal intervals."""
    require(inspection['status'] == 'PASS_SAVED_RESULT_EVIDENCE', 'Independent result acceptance')
    require(inspection['supplied_plan_count'] == descriptor['point_count'], 'Complete inspected batch')
    require(len(value['results']) == len(plans) == descriptor['point_count'], 'Complete saved rows')
    runs = []
    stopped = False
    for index, (plan, row) in enumerate(zip(plans, value['results'])):
        ordinal = descriptor['start'] + index
        require(type(plan['global_ordinal']) is int and plan['global_ordinal'] == ordinal, 'Original contiguous order')
        require(row['supplied_index'] == index and row['plan'] == plan, 'Saved original plan identity')
        status = OUTCOMES[row['status']]
        numeric = status in ('inspected_feasible', 'inspected_infeasible')
        require(not stopped or not numeric, 'No numeric rows after technical stop')
        stopped = stopped or not numeric
        if runs and runs[-1]['status'] == status:
            runs[-1]['stop'] = ordinal + 1
        else:
            runs.append(dict(start=ordinal, stop=ordinal + 1, status=status))
    return runs


def run_once(*, descriptor, plans, hooks):
    """RAW persistence precedes byte inspection and economic inspection.

    Hook order: before_dispatch -> start -> evaluate -> preserve -> decode ->
    inspect -> guard -> complete. Every hook is called at most once. Failed raw
    and exceptions are reported to the failure hook, never passed to evaluate.
    A source wrapper must authenticate hooks and retain all physical partials.
    """
    desc = deepcopy(descriptor)
    require(type(desc['start']) is int and type(desc['stop']) is int and
            0 <= desc['start'] < desc['stop'] and desc['stop'] - desc['start'] == desc['point_count'], 'Exact nonempty batch')
    require(type(plans) is list and len(plans) == desc['point_count'], 'Whole supplied batch')
    require([p['global_ordinal'] for p in plans] == list(range(desc['start'], desc['stop'])), 'Whole original ordinal range')
    state = dict(descriptor=desc, started=False, call_invoked=False, returned=False,
                 raw_preserved=False, independently_inspected=False,
                 references={}, point_runs=[], automatic_retry_allowed=False)
    stage = 'BEFORE_DISPATCH'
    try:
        hooks['before_dispatch']()
        stage = 'START'
        state['references']['started'] = hooks['start'](deepcopy(plans))
        state['started'] = True
        stage = 'EVALUATE'
        state['call_invoked'] = True
        value = hooks['evaluate'](deepcopy(plans))
        state['returned'] = True
        stage = 'PRESERVE_RAW'
        state['references']['raw_receipt'] = hooks['preserve'](value)
        state['raw_preserved'] = True
        del value
        stage = 'DECODE_SAVED_RAW'
        decoded = hooks['decode'](state['references']['raw_receipt'])
        stage = 'INDEPENDENT_INSPECTION'
        inspection, reference = hooks['inspect'](deepcopy(plans), decoded)
        state['references']['inspection'] = reference
        state['point_runs'] = checked_runs(desc, plans, decoded, inspection)
        del decoded
        stage = 'FINAL_SOURCE_GUARD'
        hooks['guard']()
        state['independently_inspected'] = True
        state['status'] = 'COMPLETE_SAVED_AND_INSPECTED' if all(
            r['status'] in ('inspected_feasible', 'inspected_infeasible') for r in state['point_runs']) else 'SAVED_TECHNICAL_STOP'
        stage = 'COMPLETE'
        state['references']['completion'] = hooks['complete'](deepcopy(state))
        return state
    except BaseException as error:
        state['failure_stage'] = stage
        state['error'] = error_record(error)
        state['independently_inspected'] = False
        if not state['call_invoked']:
            state['status'] = 'STOP_BEFORE_DISPATCH'
            state['point_runs'] = []
        else:
            status = 'validation_failure_returned' if state['raw_preserved'] else 'unresolved_dispatch_or_raw'
            state['status'] = 'VALIDATION_FAILURE' if state['raw_preserved'] else 'UNKNOWN_RETURN_OR_PARTIAL_RAW'
            state['point_runs'] = [dict(start=desc['start'], stop=desc['stop'], status=status)]
        # Physical failure save may itself fail. Propagate it, never retry or
        # invent a persisted completion. The already-written files remain.
        state['references']['failure'] = hooks['failure'](deepcopy(state))
        return state
