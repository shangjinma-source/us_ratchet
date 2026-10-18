"""One new V2 continuous book; sealed V1/TOP1 results are never rerun.

The public V2 capital adapter owns its single core call. We persist adapter
attempts; an exception reports unknown actual core calls, never an invented 0.
Injected collaborators are for synthetic tests, not exposed by the CLI.
"""
import argparse
import hashlib
import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import return_priority_next12_monthly_comparison as sealed
absolute, digest, load, save, verify = sealed.absolute, sealed.digest, sealed.load, sealed.save, sealed.verify
VERSION = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
SELF = 'scripts/return_priority_next12_quantity_v2_run.py'
LOADED_ENTRY_HASHES = {path: digest(path) for path in (
    SELF, 'scripts/return_priority_next12_monthly_comparison.py')}
MODULES = list(dict.fromkeys(sealed.MODULES + [SELF,
    'data/current_research_capital_decision_v2.py',
    'backtest/return_priority_fresh_cash_quantity_search_v2.py',
    'backtest/affordable_support_seeds.py', 'backtest/log_concave_integer_search.py',
    'backtest/quantity_training_upper_bound.py']))
BASELINES = [
    'tmp/next12_monthly_comparison_20261015_v1',
    'tmp/next12_top1_pin_repair_20261015_v1']

def read_pinned(path, expected):
    raw = absolute(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected: raise ValueError('PIN_CHANGED:' + str(path))
    return json.loads(raw)

def require_fresh_runtime():
    # CLI prepare and run are separate invocations. Never use already imported
    # calculation functions whose bytes could predate the registered disk pins.
    for path in MODULES:
        if path.endswith('.py') and path not in (SELF, 'scripts/return_priority_next12_monthly_comparison.py'):
            if path[:-3].replace('/', '.') in sys.modules:
                raise ValueError('CALCULATION_MODULE_ALREADY_LOADED_USE_FRESH_CLI:' + path)

def guards():
    result = sealed.guards()
    for folder in BASELINES:
        if not absolute(folder).is_dir() or not (absolute(folder) / 'result.json').is_file():
            raise ValueError('SEALED_BASELINE_MISSING:' + folder)
        for path in sorted(absolute(folder).rglob('*')):
            if path.is_file(): result[str(path.relative_to(ROOT)).replace('\\','/')] = digest(path)
    return result

def prepare(input_path, input_sha, output):
    output = absolute(output)
    if output.exists(): raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    data = read_pinned(input_path, input_sha)
    assembled = sealed.validate(data)
    pins = dict(data['source_hashes'])
    for path in MODULES + [str(absolute(input_path))]:
        actual = digest(path)
        if path in pins and pins[path] != actual: raise ValueError('INPUT_CODE_PIN_CONFLICT:' + path)
        pins[path] = actual
    registration = dict(schema='NEXT12_QUANTITY_V2_SINGLE_BOOK_V1', method=VERSION,
        input_path=str(absolute(input_path)), input_sha256=input_sha, source_hashes=pins,
        protected_before=guards(), decision_dates=sealed.DECISIONS, session_dates=assembled['session_dates'],
        maximum_book_calls=1, maximum_capital_decision_attempts=12, maximum_core_calls=12,
        maximum_objective_evaluations_per_call=8192, initial_cash='20000', initial_shares={},
        monthly_cash_reset=False, automatic_retry=False, independent_oos=False, adoption_allowed=False,
        price_only=True, execution_policy='SEALED_PREVIOUS_CLOSE_DAY_NOT_LIVE_MINUTE_RULE',
        baseline_reruns=0, interpretation='New method experiment; not a rerun or relabeling of sealed V1.')
    output.mkdir(parents=True)
    save(output / 'registration.json', registration)
    return digest(output / 'registration.json')

def execute(prepared, assembled, directory, *, kernel=None, provider_factory=None, capital_decide=None):
    """One method; injected fakes are only for isolated synthetic tests."""
    from backtest.return_priority_limit_book_summary_v4 import summarize_limit_book_v4
    from backtest.return_priority_limit_book_v4 import run_limit_book_v4
    from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
    from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
    method = VERSION
    directory.mkdir()
    save(directory / 'book_intent.json', dict(method=method, maximum_calls=1, initial_cash='20000'))
    audit, decision_days, monthly_seen = [], [], set()
    book_calls = 0
    current_state = None
    windows = {w['decision_date']: w for w in assembled['monthly_inputs']}

    def decide(**kwargs):
        day = kwargs['decision_date']
        if day not in windows or day in decision_days or len(decision_days) >= 12:
            raise ValueError('CAPITAL_DECISION_BUDGET_OR_DATE')
        expected = windows[day]
        if kwargs['source_hashes'] != expected['source_hashes']:
            raise ValueError('MONTHLY_SOURCE_PINS_CHANGED')
        if kwargs['search_arguments'] != expected['search_arguments'] or kwargs['valuation_quotes'] != expected['valuation_quotes']:
            raise ValueError('REGISTERED_MONTHLY_ARGUMENT_CHANGED')
        account = kwargs['account_state']
        if Fraction(account['cash']) != Fraction(current_state['cash']) or account['shares'] != current_state['shares']:
            raise ValueError('ACTUAL_ACCOUNT_STATE_CHANGED')
        args = kwargs['search_arguments']
        if type(args['max_objective_evaluations']) is not int or args['max_objective_evaluations'] != 8192:
            raise ValueError('EVALUATION_BUDGET_CHANGED')
        save(directory / ('decision_intent_' + day + '.json'), dict(arguments=kwargs, prior_state=current_state))
        decision_days.append(day)  # An exception consumes this attempt; never retry.
        result = (capital_decide or decide_quantity_v2_for_account)(**kwargs)
        save(directory / ('decision_result_' + day + '.json'), result)
        if (result.get('method') != VERSION or result.get('binding', {}).get('selection_method') != VERSION
                or result.get('binding', {}).get('schema') != 'CAPITAL_DECISION_MECHANIC_V2'):
            raise ValueError('V2_METHOD_BINDING_MISMATCH')
        if result.get('core_calls') != 1:
            raise ValueError('V2_SINGLE_CORE_CALL_REQUIRED')
        if result.get('search_result', {}).get('method_version') != VERSION:
            raise ValueError('V2_SEARCH_RESULT_METHOD_MISMATCH')
        prices = {q['security_id']: Fraction(q['price']) for q in kwargs['valuation_quotes']}
        equity = Fraction(account['cash']) + sum((q * prices[sid] for sid,q in account['shares'].items() if q), Fraction(0))
        if Fraction(result['investable_equity']) != equity:
            raise ValueError('ACTUAL_EQUITY_MISMATCH')
        return result

    factory = provider_factory or build_monthly_quantity_provider_v4
    arguments = dict(session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
                     close_prices=assembled['close_prices'], actions=assembled['provider_actions'], decide=decide)
    provider = None

    def callback(*, decision_date, active_date, state):
        nonlocal current_state
        current_state = deepcopy(state)
        intent = dict(decision_date=decision_date, active_date=active_date, prior_state=current_state)
        # Saved before any selector/core entry. Duplicate callback fails before invocation.
        save(directory / ('callback_intent_' + decision_date + '.json'), intent)
        if decision_date in windows:
            if decision_date in monthly_seen or len(monthly_seen) >= 12:
                raise ValueError('MONTHLY_CALLBACK_BUDGET')
            monthly_seen.add(decision_date)
            save(directory / ('monthly_intent_' + decision_date + '.json'),
                 dict(method=method, prior_state=current_state, monthly_input=windows[decision_date]))
        response = provider(decision_date=decision_date, active_date=active_date, state=state)
        response = dict(response, method=VERSION)
        record = dict(intent, response=deepcopy(response))
        save(directory / ('callback_' + decision_date + '.json'), record)
        audit.append(record)
        return response

    try:
        provider = factory(**arguments)
        kwargs = dict(session_dates=assembled['session_dates'], ohlc=prepared['ohlc'], initial_cash='20000', initial_shares={},
            events=assembled['actions'], fee_bps='0', order_provider=callback,
            cash_stock_merger_events=assembled['cash_stock_merger_events'], fractional_settlements=assembled['fractional_settlements'],
            price_source_references=assembled['price_source_references'], distribution_events=assembled['distribution_events'],
            distribution_fractional_cash_values=assembled['distribution_fractional_cash_values'])
        if assembled.get('account_model') is not None:
            kwargs['account_model'] = assembled['account_model']
        book_calls = 1
        outcome = (kernel or run_limit_book_v4)(**kwargs)
    except Exception as error:
        save(directory / 'exception.json', dict(type=type(error).__name__, message=str(error),
             prior_state=current_state, preserved_callback_files=True))
        prior = current_state or {}
        outcome = dict(status='BLOCKED_EXCEPTION', reason=str(error),
            daily_ledger=deepcopy(prior.get('daily_ledger', [])), order_log=deepcopy(prior.get('order_log', [])),
            cash=prior.get('cash'), shares=deepcopy(prior.get('shares', {})), receivable=prior.get('receivable'),
            distribution_rights=deepcopy(prior.get('distribution_rights', [])),
            merger_entitlements=deepcopy(prior.get('merger_entitlements', [])),
            state_date=prior.get('asof'), terminal_state_valuation_synchronized=False,
            final_wealth_basis='LAST_VALIDATED_CLOSE_ONLY' if prior.get('daily_ledger') else 'NO_VALIDATED_CLOSE',
            exception_state_scope='LAST_CALLBACK_INPUT_ONLY; later intraday mutations unknown')
    save(directory / 'outcome.json', outcome)
    save(directory / 'provider_audit.json', audit)
    metrics = summarize_limit_book_v4(outcome, audit, '20000', assembled['session_dates'])
    completed_decisions = len(list(directory.glob('decision_result_*.json')))
    result = dict(method=VERSION, metrics=metrics, book_calls=book_calls,
        capital_decision_attempts=len(decision_days), completed_capital_decisions=completed_decisions,
        core_calls=(None if completed_decisions != len(decision_days) else completed_decisions),
        core_calls_upper_bound=len(decision_days), core_count_basis='PINNED_ADAPTER_AT_MOST_ONE_CORE_PER_ATTEMPT',
        selector_calls=0, denominator=1, independent_oos=False, adoption_allowed=False, price_only=True)
    save(directory / 'result.json', result)
    return result


def run(input_path, input_sha, output, registration_sha):
    output = absolute(output)
    reg = read_pinned(output / 'registration.json', registration_sha)
    if {p.name for p in output.iterdir()} != {'registration.json'}: raise ValueError('ALREADY_STARTED_NO_RETRY')
    require_fresh_runtime()
    if (reg['method'] != VERSION or reg['maximum_book_calls'] != 1 or reg['maximum_core_calls'] != 12
        or reg['maximum_capital_decision_attempts'] != 12 or reg['maximum_objective_evaluations_per_call'] != 8192):
        raise ValueError('REGISTERED_BUDGET_CHANGED')
    if reg['input_path'] != str(absolute(input_path)) or reg['input_sha256'] != input_sha:
        raise ValueError('EXPLICIT_INPUT_MISMATCH')
    if any(path not in reg['source_hashes'] for path in MODULES): raise ValueError('CODE_CLOSURE_MISSING')
    if any(reg['source_hashes'].get(path) != sha for path,sha in LOADED_ENTRY_HASHES.items()):
        raise ValueError('LOADED_ENTRY_PIN_CHANGED')
    verify(reg['source_hashes'])
    if guards() != reg['protected_before']: raise ValueError('PROTECTED_CHANGED')
    prepared = read_pinned(input_path, input_sha); assembled = sealed.validate(prepared)
    if assembled['session_dates'] != reg['session_dates'] or reg['decision_dates'] != sealed.DECISIONS:
        raise ValueError('REGISTERED_SCOPE_CHANGED')
    # Method pins accompany every monthly adapter call; no mutation of the sealed input.
    for window in assembled['monthly_inputs']:
        window['source_hashes'] = deepcopy(reg['source_hashes'])
    save(output / 'started.json', dict(registration_sha256=registration_sha, maximum_books=1, automatic_retry=False))
    try:
        result = execute(prepared, assembled, output / 'quantity_v2')
        save(output / 'result.json', dict(methods=[result], denominator=1, book_calls=result['book_calls'],
            complete_books=int(result['metrics']['complete_full_period']), baseline_reruns=0,
            independent_oos=False, adoption_allowed=False, price_only=True))
    finally:
        after = guards()
        save(output / 'protected_after.json', dict(hashes=after, unchanged=after == reg['protected_before']))
        if after != reg['protected_before']: raise ValueError('PROTECTED_CHANGED')
        verify(reg['source_hashes'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true'); modes.add_argument('--run', action='store_true')
    parser.add_argument('--input', required=True); parser.add_argument('--input-sha', required=True)
    parser.add_argument('--output', required=True); parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare: print(prepare(args.input, args.input_sha, args.output))
    elif args.registration_sha: run(args.input, args.input_sha, args.output, args.registration_sha)
    else: raise ValueError('EXPLICIT_REGISTRATION_SHA_REQUIRED')
