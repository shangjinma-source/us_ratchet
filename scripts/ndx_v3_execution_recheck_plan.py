"""Source-bound periodic execution preparation for four old whole-lot passes.

These are diagnostic priorities, not a new candidate universe or fixed k rule.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_joint_weight_runner as encoding
from backtest import ndx_joint_weight_runner_v3 as runner
from scripts.ndx_joint_weight_verify import _restore, _restore_input
from scripts.ndx_joint_weight_progress import RETURN_FIELDS, DRAWDOWN_FIELDS
from backtest.ndx_periodic_execution_clock import build_periodic_execution_schedule, PARAMETERS

CASES = (
 ('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7','546765779f412fee85c706e3b0c3d0cb2c2475522adbefa351706d3dee6a8d0d'),
 ('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7','88017843fdbca1712e0e9499dc4bc95e2f6180b8b19cd11133b37d15a1aa6d2c'),
 ('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7','bade8714491a6bd160147c2a0ea3ca02465e507d67e850bf7f95628e3ce368bc'),
 ('8f91495e11223c613246ae0a124e249f5a6d0659bc44112b40f58578833872e3','db5e4c2d6437c4f40cbada079d0e88f91b0b2e6b7a9a4ce4ed8d5120f638ef94'),
)
_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def prepare_case(context_sha256, job_id):
    if any(type(v) is not str or re.fullmatch('[0-9a-f]{64}',v) is None for v in (context_sha256,job_id)):
        raise ValueError('Explicit context and job digests required')
    if hashlib.sha256(_SOURCE.read_bytes()).hexdigest() != _LOADED_SHA or runner.source_hashes() != runner._LOADED_SOURCE_HASHES:
        raise ValueError('Loaded source drift')
    observed = {}
    def read(path):
        raw = path.read_bytes()
        value = json.loads(raw)
        if encoding._json_bytes(value) != raw:
            raise ValueError('Noncanonical captured JSON')
        observed[str(path)] = hashlib.sha256(raw).hexdigest()
        return value
    directory = runner.CHECKPOINT_ROOT/context_sha256
    context = read(directory/'context.json')
    if encoding._sha(context) != context_sha256 or context['numerical_sources'] != runner.source_hashes():
        raise ValueError('Context identity/source differs')
    tasks = context['tasks']
    if not isinstance(tasks,list) or len({t['job_id'] for t in tasks}) != len(tasks):
        raise ValueError('Invalid task denominator')
    selected = [t for t in tasks if t['job_id'] == job_id]
    if len(selected) != 1:
        raise ValueError('Task missing or ambiguous')
    task = selected[0]
    encoding._validate_task(task)
    checkpoint = read(directory/(job_id+'.json'))
    digest = checkpoint.pop('checkpoint_sha256',None)
    if (set(checkpoint) != {'context_sha256','task','status','result'} or encoding._sha(checkpoint) != digest
            or checkpoint['context_sha256'] != context_sha256 or checkpoint['status'] != 'EVALUATED'
            or encoding._json_bytes(checkpoint['task']) != encoding._json_bytes(task)):
        raise ValueError('Checkpoint identity differs')
    result = _restore(checkpoint['result'])
    if encoding._json_bytes(encoding._normalize(result)) != encoding._json_bytes(checkpoint['result']):
        raise ValueError('Result encoding differs')
    if (result.get('tickers') != task['tickers'] or result.get('weight_spec') != task['weight_spec']
            or type(result.get('holding_count')) is not int or result['holding_count'] != task['holding_count']):
        raise ValueError('Result portfolio identity differs')
    metrics = {f:result[f] for f in RETURN_FIELDS+DRAWDOWN_FIELDS}
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in metrics.values()):
        raise ValueError('Invalid saved economic metric')
    for key in ('declared_constraints_passed','whole_lot_executable_all_windows'):
        if type(result[key]) is not bool:
            raise ValueError('Invalid saved flag')
    inputs = {k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
    contract, returns = inputs['contract'], inputs['returns']
    starts = list(range(contract['fit_days'],len(returns)-contract['window_days']+1,contract['step_days']))
    if not starts:
        raise ValueError('No original evaluation windows')
    start = returns.index[starts[0]]
    end = returns.index[starts[-1]+contract['window_days']-1]
    names = sorted(task['tickers'].split(';'))
    labels = inputs['universe'].set_index('ticker').loc[names,'risk_chain'].to_dict()
    clock = build_periodic_execution_schedule(returns=returns,tickers=names,
        fit_days=contract['fit_days'],step_days=contract['step_days'],execution_end=end,
        weight_spec=task['weight_spec'],risk_chain_by_ticker=labels,
        projection_parameters={k:contract[k] for k in PARAMETERS})
    prices = inputs['nominal_prices'].loc[start:end,names]
    if not prices.index.equals(returns.loc[start:end].index) or clock['schedule'][0]['execution_date'] != str(start.date()):
        raise ValueError('Execution calendar/first decision differs')
    observed[str(_SOURCE)] = _LOADED_SHA
    for name,h in runner.source_hashes().items():
        observed[str(ROOT/name)] = h
    for name,h in clock['source_hashes'].items():
        path = Path(name) if Path(name).is_absolute() else ROOT/name
        observed[str(path)] = h
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p,h in observed.items()):
        raise ValueError('Sources changed during preparation')
    summary = dict(context_sha256=context_sha256,job_id=job_id,tickers=names,
        coordinate={key:task[key] for key in encoding.COORDINATE_FIELDS},
        weight_spec=task['weight_spec'],holding_count=task['holding_count'],
        saved_fractional_metrics=metrics,
        failed_components=[f for f in RETURN_FIELDS if metrics[f]<0]+[f for f in DRAWDOWN_FIELDS if metrics[f]>0],
        old_declared_constraints_passed=result['declared_constraints_passed'],
        old_whole_lot_executable=result['whole_lot_executable_all_windows'],
        projection_reconstruction_attempts=result['projection_reconstruction_audit']['attempt_count'],
        date_start=str(start.date()),date_end=str(end.date()),day_count=len(prices),
        legacy_decision_count=len(starts),periodic_decision_count=len(clock['schedule']),
        periodic_schedule_sha256=encoding._sha(clock['schedule']),
        candidate_source_contains_bkr='BKR' in names,source_hashes=observed,
        numerical_projector='V2_STRICT_NO_FAILED_PROPOSAL_RECOVERY_IN_THIS_PREPARATION',
        historical_source_scope='FROZEN_CONTEXT_NOT_CURRENT_ELIGIBILITY',
        portfolio_selection_precedes_execution=False,
        retrospective_fixed_portfolio_diagnostic=True,
        fresh_oos_consumed=False,promotion_allowed=False)
    return dict(summary=summary,task=task,inputs=inputs,prices=prices,clock=clock)


def run():
    cases = [prepare_case(c,j)['summary'] for c,j in CASES]
    if not all(r['old_declared_constraints_passed'] and r['old_whole_lot_executable'] for r in cases):
        raise ValueError('Explicit four-case selection differs from saved evidence')
    return dict(schema='ndx_v3_execution_recheck_plan_v1',cases=cases,
        scope='FOUR_DIAGNOSTIC_PRIORITY_CASES_NOT_RESTRICTED_OPTIMIZATION_UNIVERSE',
        real_execution_performed=False,promotion_allowed=False)


if __name__ == '__main__':
    print(json.dumps(run(),indent=2))
