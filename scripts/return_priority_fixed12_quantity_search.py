"""Run one registered bounded search per prepared historical decision."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'backtest/return_priority_fresh_cash_quantity_search.py'
CORE_SHA = '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588'
OUTPUT = ROOT / 'tmp/fixed12_quantity_search_20261014_v1'
PROTECTED = ['data/state.json','data/broker_positions.json','config/config.yaml',
             'api/server.py','web/index.html','web/selected_stock_charts.js',
             'data/current_cash_portfolio_research.py', 'data/current_quantity_portfolio_research.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, payload):
    raw = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')
    with path.open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def guards():
    return {name:digest(ROOT/name) for name in PROTECTED}


def verify_sources(payload):
    require(bool(payload['source_hashes']), 'Explicit prepared source closure required')
    for name, expected in payload['source_hashes'].items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT/path
        require(digest(path)==expected, 'Input source changed: '+name)


def validate(payload):
    windows = payload['windows']
    require(len(windows)==12, 'All twelve registered historical decisions required')
    dates = [w['decision_cutoff'] for w in windows]
    require(dates==['2024-07-31','2024-08-30','2024-09-30','2024-10-31',
                   '2024-11-29','2024-12-31','2025-01-31','2025-02-28',
                   '2025-03-31','2025-04-30','2025-05-30','2025-06-30'],
            'Fixed twelve-month historical schedule differs')
    for window in windows:
        args = window['search_arguments']
        require(args['decision_date']==window['decision_cutoff'], 'Decision mismatch')
        require(Fraction(str(args['entered_cash']))==20000 and Fraction(str(args['fee_bps']))==0 and Fraction(str(args['minimum_cash_buffer']))==0, 'Cash/fee policy differs')
        require(args['max_objective_evaluations']==8192 and args['fixed_seed']=='fresh-quantity-20261014-v1', 'Search budget or seed differs')
        require(len(args['training_scenarios'])==len(args['scenario_dates'])==12 and max(args['scenario_dates'])<=args['decision_date'], 'Only mature training scenarios')
    require(all(w.get('status')=='READY_CONDITIONAL' for w in windows), 'Every full-domain input must pass explicit conditional readiness')
    require(all(not r.get('blockers') for w in windows for r in w['candidates']), 'Candidate blockers remain')
    verify_sources(payload)


def prepare(input_path):
    path = Path(input_path).resolve()
    require(not OUTPUT.exists(), 'Create-only output already exists')
    require((ROOT/'tmp').resolve() in path.parents, 'Prepared workspace input required')
    payload = json.loads(path.read_bytes())
    validate(payload)
    require(digest(CORE)==CORE_SHA, 'Reviewed core changed')
    registration = dict(input_path=str(path), input_sha256=digest(path), core_sha256=CORE_SHA,
                        runner_sha256=digest(Path(__file__)), protected_before=guards(),
                        decisions=[w['decision_cutoff'] for w in payload['windows']],
                        maximum_search_calls=12, objective_budget_per_call=8192,
                        book_calls=0, conditional_historical_research=True,
                        independent_oos=False, adoption_allowed=False)
    OUTPUT.mkdir()
    print(json.dumps({'registration_sha256':save(OUTPUT/'registration.json',registration)}),flush=True)


def run(registration_sha):
    registration_path = OUTPUT/'registration.json'
    require(digest(registration_path)==registration_sha, 'Reviewed registration differs')
    require({p.name for p in OUTPUT.iterdir()}=={'registration.json'}, 'Already started; inspect artifacts rather than rerun')
    registration = json.loads(registration_path.read_bytes())
    require(digest(Path(__file__))==registration['runner_sha256'] and digest(CORE)==CORE_SHA, 'Reviewed implementation changed')
    path = Path(registration['input_path'])
    require(digest(path)==registration['input_sha256'], 'Prepared input changed')
    payload = json.loads(path.read_bytes())
    validate(payload)
    require(guards()==registration['protected_before'], 'Protected files changed')
    module = types.ModuleType('registered_historical_quantity_core')
    exec(compile(CORE.read_bytes(),str(CORE),'exec'),module.__dict__)
    save(OUTPUT/'started.json',{'registration_sha256':registration_sha,'maximum_search_calls':12})
    summary = []
    try:
        for window in payload['windows']:
            decision = window['decision_cutoff']
            directory = OUTPUT/decision
            directory.mkdir()
            save(directory/'inputs.json',window)
            save(directory/'search_intent.json',{'maximum_calls':1,'objective_budget':8192})
            result = module.search_fresh_cash_quantities(**window['search_arguments'])
            save(directory/'search.json',result)
            require(result['selected'] is not None, 'Candidate unavailable; no silent fallback')
            selected = result['selected']
            summary.append(dict(decision_cutoff=decision,status=result['status'],selected=selected))
            print(json.dumps({'decision':decision,'status':result['status'],'k':selected['actual_k']}),flush=True)
        save(OUTPUT/'result.json',dict(status='COMPLETE_BOUNDED_HISTORICAL_SEARCHES_NOT_OUTCOME_VALIDATION',
             windows=summary,search_calls=12,book_calls=0,global_optimality_proven=False,
             historical_outcomes_evaluated=False,adoption_allowed=False,independent_oos=False))
    except Exception as error:
        save(OUTPUT/'failure.json',dict(type=type(error).__name__,message=str(error),completed_windows=len(summary),automatic_retry_allowed=False))
        raise
    finally:
        after = guards()
        save(OUTPUT/'protected_after.json',dict(hashes=after,unchanged=after==registration['protected_before']))
        require(after==registration['protected_before'], 'Protected files changed during search')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true')
    group.add_argument('--run',action='store_true')
    parser.add_argument('--input')
    parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        require(args.input is not None, 'Prepared input path required')
        prepare(args.input)
    else:
        require(args.registration_sha is not None, 'Reviewed registration SHA required')
        run(args.registration_sha)
