"""One separately registered rebased99 V2 comparison. No execution on import."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from fractions import Fraction
from math import prod

ROOT = Path(__file__).resolve().parents[1]
RUNNER = 'scripts/return_priority_quantity_rebased99_comparison.py'
LOADED_RUNNER_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
METHODS = ('backtest/log_concave_integer_search.py', 'backtest/affordable_support_seeds.py',
           'backtest/quantity_training_upper_bound.py', 'backtest/return_priority_fresh_cash_quantity_search_v2.py')
PROTECTED = ('data/broker_positions.json', 'data/state.json', 'config/config.yaml',
             'data/research_paper/research_paper.sqlite3', 'backtest/return_priority_fresh_cash_quantity_search.py',
             'data/current_research_limit_plan.py', 'data/current_research_fill_ledger.py', 'api/server.py', 'web/index.html')
KWARGS = {'prices','metadata','entered_cash','fee_bps','minimum_cash_buffer','training_scenarios',
          'scenario_dates','decision_date','max_objective_evaluations','fixed_seed'}
SEED = 'fresh-quantity-20261014-v1'


def require(ok, reason):
    if not ok: raise ValueError(reason)


def absolute(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT/value


def digest(path):
    return hashlib.sha256(absolute(path).read_bytes()).hexdigest()


def verified_load(path, expected):
    raw = absolute(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'LOADED_PIN_CHANGED:'+str(path))
    return json.loads(raw)


def put(pins, path, value):
    require(path not in pins or pins[path] == value, 'CONFLICTING_PIN:'+str(path))
    pins[path] = value


def verify(pins):
    for path, value in pins.items(): require(digest(path) == value, 'PIN_CHANGED:'+path)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def scope(arguments, prepared):
    require(set(arguments) == KWARGS and arguments == prepared['search_arguments'], 'EXACT_PREPARED_KWARGS_REQUIRED')
    require(prepared['status'] == 'READY_CONDITIONAL' and prepared['coverage_denominator'] == 101
            and prepared['window']['member_count'] == 101, 'PREPARED_NOT_READY_OR_DENOMINATOR_CHANGED')
    domain = set(arguments['prices'])
    require(len(domain) == 99 and domain == set(arguments['metadata']), 'DOMAIN_99_REQUIRED')
    require(len({v['issuer_id'] for v in arguments['metadata'].values()}) == 98, 'ISSUERS_98_REQUIRED')
    require(arguments['decision_date'] == '2026-10-13' and arguments['max_objective_evaluations'] == 8192
            and arguments['fixed_seed'] == SEED, 'FIXED_DATE_BUDGET_SEED_REQUIRED')
    require(arguments['entered_cash'] == '20000' and arguments['fee_bps'] == '0'
            and arguments['minimum_cash_buffer'] == '0', 'FIXED_CASH_AND_FEES_REQUIRED')
    dates = prepared['window']['training_dates']
    require(len(dates) == 253 and dates == sorted(set(dates)) and dates[-1] == arguments['decision_date'], 'TRAINING_DATES_INVALID')
    require(arguments['scenario_dates'] == dates[21::21] and len(arguments['training_scenarios']) == 12
            and all(set(row) == domain for row in arguments['training_scenarios']), 'SCENARIO_DOMAIN_INVALID')


def saved_top1(arguments, prepared_path, prepared_sha, snapshot, registration, review, registration_sha, snapshot_sha):
    require(registration['input_path'] == prepared_path and registration['input_sha256'] == prepared_sha, 'TOP1_INPUT_BINDING_MISMATCH')
    require(snapshot['registration_sha256'] == registration_sha == review['registration_sha256']
            and review['result_sha256'] == snapshot_sha
            and review['status'] == 'PASS_INDEPENDENT_EXACT_TOP1_READBACK', 'TOP1_REVIEW_BINDING_MISMATCH')
    require(snapshot['metadata'] == arguments['metadata'], 'TOP1_METADATA_MISMATCH')
    result = snapshot['selector_result']
    require(result['decision_date'] == arguments['decision_date'] and result['entered_cash'] == arguments['entered_cash']
            and result['candidate_count'] == 99 and result['status'] == 'SELECTOR_COMPLETE', 'TOP1_SCOPE_MISMATCH')
    return result


def register(*, draft_path, review_path, runner_review_path, output):
    entry_paths = (draft_path, review_path, runner_review_path)
    entry_hashes = {str(path): digest(path) for path in entry_paths}
    draft, review, runner_review = [verified_load(path, entry_hashes[str(path)]) for path in entry_paths]
    require(review.get('status') in ('PASS','CONDITIONAL_PASS') and review.get('independent_review') is True
            and review.get('eligible_for_rebased99_single_conditional_research') is True, 'NEW_DOMAIN_REVIEW_REQUIRED')
    require(runner_review.get('status') == 'PASS' and runner_review.get('root_checked') is True
            and runner_review.get('reviewed_source_hashes',{}).get(RUNNER) == LOADED_RUNNER_SHA, 'ROOT_RUNNER_REVIEW_REQUIRED')
    require(set(draft['method_hashes']) == set(METHODS), 'METHOD_CLOSURE_REQUIRED')
    reviewed = review.get('reviewed_source_hashes',{})
    for path, value in dict(draft['method_hashes'], **{draft['input_path']:draft['input_sha256'],
            draft['prepared_path']:draft['prepared_sha256'], str(draft_path):entry_hashes[str(draft_path)]}).items():
        require(reviewed.get(path) == value, 'METHOD_AND_INPUT_REVIEW_PIN_MISMATCH:'+path)
    require(draft['maximum_new_search_calls'] == 1 and draft['maximum_objective_evaluations'] == 8192
            and draft['baseline_selector_calls'] == draft['baseline_search_calls'] == draft['book_calls'] == 0
            and draft['automatic_retry'] is False, 'DRAFT_BUDGET_MISMATCH')
    pins = dict(draft['source_pins'])
    for path,value in draft['method_hashes'].items(): put(pins,path,value)
    for key in ('input','prepared','baseline_result'): put(pins,draft[key+'_path'],draft[key+'_sha256'])
    for path,value in entry_hashes.items(): put(pins,path,value)
    put(pins,RUNNER,LOADED_RUNNER_SHA)
    for path in PROTECTED: put(pins,path,digest(path))
    verify(pins)
    arguments = verified_load(draft['input_path'], draft['input_sha256'])
    prepared = verified_load(draft['prepared_path'], draft['prepared_sha256'])
    scope(arguments,prepared)
    baseline_path = draft['baseline_result_path']
    top_registration = str(Path(baseline_path).with_name('registration.json')).replace('\\','/')
    top_review = str(Path(baseline_path).with_name('independent_readback.json')).replace('\\','/')
    require(top_registration in pins and top_review in pins, 'SEALED_TOP1_CLOSURE_REQUIRED')
    saved_top1(arguments,draft['prepared_path'],draft['prepared_sha256'], verified_load(baseline_path,pins[baseline_path]),
               verified_load(top_registration,pins[top_registration]),verified_load(top_review,pins[top_review]),pins[top_registration],pins[baseline_path])
    verify(pins)
    directory = absolute(output); directory.mkdir()
    save(directory/'registration.json',dict(schema='REB99_V2_SAVED_TOP1_SINGLE_COMPARISON_V1', source_hashes=pins,
        input_path=draft['input_path'],prepared_path=draft['prepared_path'],baseline_path=baseline_path,
        top1_registration_path=top_registration,top1_review_path=top_review,maximum_search_calls=1,
        baseline_selector_calls=0,baseline_search_calls=0,book_calls=0,automatic_retry=False,
        protected_paths=list(PROTECTED),independent_oos=False,adoption_allowed=False))
    return digest(directory/'registration.json')


def portfolio_metrics(arguments, result):
    selected=result['selected']; require(selected is not None,'SELECTED_REQUIRED')
    cash=Fraction(arguments['entered_cash']); prices={s:Fraction(v) for s,v in arguments['prices'].items()}
    q=selected['quantities']
    require(all(s in prices and type(n) is int and n>0 for s,n in q.items()), 'INVALID_QUANTITIES')
    require(len({arguments['metadata'][s]['issuer_id'] for s in q})==len(q), 'DUPLICATE_ISSUER')
    cost=sum((prices[s]*n for s,n in q.items()),Fraction(0)); fees=cost*Fraction(arguments['fee_bps'])/10000
    residual=cash-cost-fees
    require(residual>=Fraction(arguments['minimum_cash_buffer']) and selected['actual_k']==len(q)
            and Fraction(selected['notional'])==cost and Fraction(selected['fees'])==fees
            and Fraction(selected['residual_cash'])==residual,'SELECTED_BUDGET_MISMATCH')
    require(all(Fraction(selected['actual_weights'][s])==prices[s]*n/cash for s,n in q.items()),'WEIGHT_MISMATCH')
    product=prod((residual+sum((prices[s]*n*Fraction(row[s]) for s,n in q.items()),Fraction(0)))/cash
                 for row in arguments['training_scenarios'])
    return dict(quantities=q,notional=str(cost),fees=str(fees),residual_cash=str(residual),exact_portfolio_training_product=str(product))


def run(*, output, registration_sha256):
    directory=absolute(output); reg=verified_load(directory/'registration.json',registration_sha256)
    require({p.name for p in directory.iterdir()}=={'registration.json'}, 'ALREADY_STARTED_NO_RETRY')
    pins=reg['source_hashes']; verify(pins)
    require(pins.get(RUNNER)==LOADED_RUNNER_SHA and set(METHODS)<=pins.keys(), 'RUNNER_METHOD_PIN_MISMATCH')
    require(reg['maximum_search_calls']==1 and reg['baseline_selector_calls']==reg['baseline_search_calls']==reg['book_calls']==0
            and reg['automatic_retry'] is False and reg['protected_paths']==list(PROTECTED),'REGISTERED_BUDGET_OR_PROTECTION_MISMATCH')
    args=verified_load(reg['input_path'],pins[reg['input_path']]); prepared=verified_load(reg['prepared_path'],pins[reg['prepared_path']]); scope(args,prepared)
    baseline=saved_top1(args,reg['prepared_path'],pins[reg['prepared_path']],verified_load(reg['baseline_path'],pins[reg['baseline_path']]),
        verified_load(reg['top1_registration_path'],pins[reg['top1_registration_path']]),verified_load(reg['top1_review_path'],pins[reg['top1_review_path']]),pins[reg['top1_registration_path']],pins[reg['baseline_path']])
    baseline_metrics=portfolio_metrics(args,baseline)
    captured={}
    for path in METHODS:
        name=path[:-3].replace('/','.')
        require(name not in sys.modules,'FRESH_PROCESS_REQUIRED:'+name)
        raw=absolute(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==pins[path],'CAPTURED_METHOD_PIN_CHANGED:'+path)
        captured[name]=(path,compile(raw,str(absolute(path)),'exec'))
    save(directory/'started.json',dict(registration_sha256=registration_sha256,maximum_new_search_calls=1,baseline_selector_calls=0,book_calls=0))
    start=time.perf_counter();installed=[]
    try:
        importlib.import_module('backtest')
        for name,(path,compiled) in captured.items():
            module=importlib.util.module_from_spec(importlib.util.spec_from_file_location(name,absolute(path)))
            sys.modules[name]=module;installed.append(name);exec(compiled,module.__dict__)
        result=sys.modules['backtest.return_priority_fresh_cash_quantity_search_v2'].search_fresh_cash_quantities(**args)
        save(directory/'result.json',result)
        require(result['decision_date']==args['decision_date'] and Fraction(result['entered_cash'])==Fraction(args['entered_cash'])
                and 0<=result['objective_evaluations']<=8192,'RESULT_INPUT_OR_BUDGET_MISMATCH')
        metrics=portfolio_metrics(args,result)
        save(directory/'comparison.json',dict(saved_top1=baseline_metrics,new_v2=metrics,
            v2_to_top1_portfolio_product_ratio=str(Fraction(metrics['exact_portfolio_training_product'])/Fraction(baseline_metrics['exact_portfolio_training_product'])),
            top1_ranking_product_separate=baseline['training_gross_product'],price_only=True,annualized_return=None,
            forecast_return=None,independent_oos=False,adoption_allowed=False))
        verify(pins)
        save(directory/'terminal.json',dict(status='RETURNED_REQUIRES_INDEPENDENT_READBACK',actual_search_calls=1,
            baseline_selector_calls=0,baseline_search_calls=0,book_calls=0,result_sha256=digest(directory/'result.json'),elapsed_seconds=time.perf_counter()-start))
    except Exception as error:
        save(directory/'failure.json',dict(type=type(error).__name__,message=str(error),automatic_retry=False,elapsed_seconds=time.perf_counter()-start))
        raise
    finally:
        after={}
        for path in PROTECTED:
            try: after[path]=digest(path)
            except OSError: after[path]=None
        try:
            save(directory/'protected_after.json',dict(hashes=after,unchanged=all(after[p]==pins[p] for p in PROTECTED)))
        finally:
            for name in reversed(installed): sys.modules.pop(name,None)
