"""Create-only registration and one-shot two-method conditional research run.

No execution on import. CLI requires explicit input and registration hashes.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACT = 'research_contracts/monthly_next12_comparison_20261014_v1.json'
DECISIONS = ['2025-07-31', '2025-08-29', '2025-09-30', '2025-10-31',
             '2025-11-28', '2025-12-31', '2026-01-30', '2026-02-27',
             '2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30']
MODULES = [
    'scripts/return_priority_next12_monthly_comparison.py',
    'backtest/return_priority_monthly_execution_inputs_v4.py',
    'backtest/return_priority_monthly_execution_inputs.py',
    'backtest/return_priority_limit_book_v4.py',
    'backtest/return_priority_limit_book_v2.py',
    'backtest/return_priority_monthly_quantity_provider_v4.py',
    'backtest/return_priority_monthly_top1_provider_v4.py',
    'backtest/return_priority_monthly_top1_selector.py',
    'backtest/return_priority_limit_book_summary_v4.py',
    'scripts/return_priority_fixed12_monthly_limit_run.py',
    'backtest/return_priority_distribution_entitlements.py',
    'backtest/return_priority_cash_stock_entitlements.py',
    'backtest/return_priority_ads_conversion.py',
    'backtest/return_priority_fresh_cash_quantity_search.py',
    'data/current_research_capital_decision.py', CONTRACT,
    'research_contracts/monthly_split_limit_rounding_20261014_v1.json',
    'research_contracts/next12_dtc_conversion_model_20261015_v1.json',
    'research_contracts/next12_conditional_source_policy_20261014_v1.json']
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js',
             'web/current_research_paper.js', 'data/current_quantity_portfolio_research.py',
             'data/current_cash_portfolio_research.py',
             'data/research_paper/research_paper.sqlite3',
             'data/research_paper/research_paper.sqlite3-wal',
             'data/research_paper/research_paper.sqlite3-shm',
             'backtest/return_priority_limit_book.py',
             'backtest/return_priority_limit_book_v3.py',
             'backtest/return_priority_monthly_quantity_provider_v3.py',
             'scripts/return_priority_monthly_actual_equity_run.py']


def absolute(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def digest(path):
    return hashlib.sha256(absolute(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(absolute(path).read_bytes())


def plain(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(plain(value), stream, ensure_ascii=False, indent=2, allow_nan=False)


def guards():
    return {p: digest(p) if absolute(p).is_file() else None for p in PROTECTED}


def verify(pins):
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError('PIN_CHANGED:' + path)


def validate(prepared):
    from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
    verify(prepared['source_hashes'])
    assembled = assemble_monthly_execution_inputs_v4(prepared)
    days = assembled['session_dates']
    windows = assembled['monthly_inputs']
    if len(days) != 251 or days[0] != '2025-07-31' or days[-1] != '2026-07-30':
        raise ValueError('CALENDAR_SCOPE_CHANGED')
    if [w['decision_date'] for w in windows] != DECISIONS:
        raise ValueError('MONTHLY_SCOPE_CHANGED')
    if len({w['active_date'][:7] for w in windows}) != 12:
        raise ValueError('TARGET_MONTHS_CHANGED')
    if (Fraction(prepared['initial_cash']) != 20000 or prepared['initial_shares']
            or Fraction(prepared['fee_bps']) or Fraction(prepared['minimum_cash_buffer'])):
        raise ValueError('INITIAL_CAPITAL_PROTOCOL_CHANGED')
    for window in windows:
        args = window['search_arguments']
        if (type(args['max_objective_evaluations']) is not int
                or args['max_objective_evaluations'] != 8192
                or args['fixed_seed'] != 'fresh-quantity-20261014-v1'
                or Fraction(args['entered_cash']) != 20000
                or Fraction(args['fee_bps']) or Fraction(args['minimum_cash_buffer'])
                or len(args['training_scenarios']) != 12
                or len(args['scenario_dates']) != 12
                or args['scenario_dates'] != sorted(set(args['scenario_dates']))
                or args['scenario_dates'][-1] != window['decision_date']):
            raise ValueError('SEARCH_PROTOCOL_CHANGED')
    # An unsupported conversion cannot disappear at the assembly boundary.
    if prepared.get('unsupported_conversions') and not assembled.get('unsupported_conversions'):
        raise ValueError('UNSUPPORTED_CONVERSION_GUARD_NOT_WIRED')
    if assembled.get('unsupported_conversions'):
        raise ValueError('UNSUPPORTED_CONVERSION_REQUIRES_EXPOSED_GUARD')
    if any(e.get('type') == 'ads_conversion' for e in assembled['actions']):
        if assembled.get('account_model') != 'DTC_BENEFICIAL_INTERESTS':
            raise ValueError('DTC_ACCOUNT_MODEL_REQUIRED')
    return assembled


def prepare(input_path, input_sha, output):
    output = absolute(output)
    if output.exists():
        raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    if digest(input_path) != input_sha:
        raise ValueError('INPUT_HASH_CHANGED')
    data = load(input_path)
    assembled = validate(data)
    pins = dict(data['source_hashes'])
    for path in MODULES + [str(absolute(input_path))]:
        actual = digest(path)
        if path in pins and pins[path] != actual:
            raise ValueError('INPUT_CODE_PIN_CONFLICT:' + path)
        pins[path] = actual
    registration = dict(schema='NEXT12_TWO_METHOD_RUN_V1', input_path=str(absolute(input_path)),
        input_sha256=input_sha, source_hashes=pins, protected_before=guards(),
        session_dates=assembled['session_dates'], decision_dates=DECISIONS,
        methods=['quantity', 'top1'], maximum_book_calls=2, maximum_quantity_core_calls=12,
        maximum_top1_capital_decision_attempts=12, initial_cash='20000', initial_shares={},
        monthly_cash_reset=False, automatic_retry=False, denominator=2,
        independent_oos=False, adoption_allowed=False, price_only=True,
        account_model=assembled.get('account_model'),
        interpretation=load(CONTRACT)['interpretation'])
    output.mkdir(parents=True)
    save(output / 'registration.json', registration)
    return digest(output / 'registration.json')


def execute_method(method, prepared, assembled, directory, *, kernel=None, provider_factory=None, core=None):
    """One method; injected fakes are only for isolated synthetic tests."""
    from backtest.return_priority_limit_book_summary_v4 import summarize_limit_book_v4
    from backtest.return_priority_limit_book_v4 import run_limit_book_v4
    from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
    from backtest.return_priority_monthly_top1_provider_v4 import build_monthly_top1_provider_v4
    from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
    from data.current_research_capital_decision import decide_quantity_for_account
    if method not in ('quantity', 'top1'):
        raise ValueError('UNREGISTERED_METHOD')
    directory.mkdir()
    save(directory / 'book_intent.json', dict(method=method, maximum_calls=1, initial_cash='20000'))
    audit, core_days, monthly_seen = [], [], set()
    attempts = 0
    callback_exception = False
    book_calls = 0
    current_state = None
    windows = {w['decision_date']: w for w in assembled['monthly_inputs']}

    def search(**kwargs):
        day = kwargs['decision_date']
        if day not in windows or day in core_days or len(core_days) >= 12:
            raise ValueError('CORE_CALL_BUDGET_OR_DATE')
        expected = deepcopy(windows[day]['search_arguments'])
        expected.pop('quote_as_of', None); expected.pop('price_basis', None)
        expected['entered_cash'] = kwargs['entered_cash']
        if kwargs != expected:
            raise ValueError('NONCASH_SEARCH_ARGUMENT_CHANGED')
        save(directory / ('core_intent_' + day + '.json'), dict(arguments=kwargs, prior_state=current_state))
        core_days.append(day)
        result = (core or search_fresh_cash_quantities)(**kwargs)
        save(directory / ('core_result_' + day + '.json'), result)
        return result

    def decide(**kwargs):
        return decide_quantity_for_account(search=search, **kwargs)

    factory = provider_factory or (build_monthly_quantity_provider_v4 if method == 'quantity' else build_monthly_top1_provider_v4)
    arguments = dict(session_dates=assembled['session_dates'], monthly_inputs=assembled['monthly_inputs'],
                     close_prices=assembled['close_prices'], actions=assembled['provider_actions'])
    if method == 'quantity':
        arguments['decide'] = decide
    provider = None

    def callback(*, decision_date, active_date, state):
        nonlocal current_state, attempts
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
        if method == 'top1':
            called = response['capital_decision_attempts']
            attempts += called
            if type(called) is not int or called not in (0, 1) or attempts > 12 or (called and decision_date not in windows):
                raise ValueError('SELECTOR_ATTEMPT_BUDGET')
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
        callback_exception = True
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
    result = dict(method=method, metrics=metrics, book_calls=book_calls, core_calls=len(core_days),
        capital_decision_attempts=(None if callback_exception else attempts) if method == 'top1' else len(core_days),
        selector_calls=(None if callback_exception or any(r['response'].get('selector_calls') is None for r in audit) else
                        sum(r['response'].get('selector_calls', 0) for r in audit)) if method == 'top1' else 0,
        denominator=1, independent_oos=False, adoption_allowed=False, price_only=True)
    save(directory / 'result.json', result)
    return result


def run(input_path, input_sha, output, registration_sha):
    output = absolute(output)
    if digest(output / 'registration.json') != registration_sha:
        raise ValueError('REGISTRATION_CHANGED')
    if {p.name for p in output.iterdir()} != {'registration.json'}:
        raise ValueError('ALREADY_STARTED_NO_RETRY')
    reg = load(output / 'registration.json')
    if reg['input_path'] != str(absolute(input_path)) or reg['input_sha256'] != input_sha or digest(input_path) != input_sha:
        raise ValueError('EXPLICIT_INPUT_MISMATCH')
    verify(reg['source_hashes'])
    if guards() != reg['protected_before']:
        raise ValueError('PROTECTED_CHANGED')
    data = load(input_path); assembled = validate(data)
    if assembled['session_dates'] != reg['session_dates'] or reg['methods'] != ['quantity', 'top1']:
        raise ValueError('REGISTERED_SCOPE_CHANGED')
    save(output / 'started.json', dict(registration_sha256=registration_sha, maximum_books=2, automatic_retry=False))
    try:
        results = []
        for method in reg['methods']:
            verify(reg['source_hashes'])
            if guards() != reg['protected_before']:
                raise ValueError('PROTECTED_CHANGED')
            results.append(execute_method(method, data, assembled, output / method))
        save(output / 'result.json', dict(methods=results, denominator=2,
            complete_books=sum(r['metrics']['complete_full_period'] for r in results),
            book_calls=sum(r['book_calls'] for r in results), independent_oos=False, adoption_allowed=False, price_only=True))
    finally:
        after = guards()
        save(output / 'protected_after.json', dict(hashes=after, unchanged=after == reg['protected_before']))
        if after != reg['protected_before']:
            raise ValueError('PROTECTED_CHANGED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true'); mode.add_argument('--run', action='store_true')
    parser.add_argument('--input', required=True); parser.add_argument('--input-sha', required=True)
    parser.add_argument('--output', required=True); parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        print(prepare(args.input, args.input_sha, args.output))
    elif args.registration_sha:
        run(args.input, args.input_sha, args.output, args.registration_sha)
    else:
        raise ValueError('EXPLICIT_REGISTRATION_SHA_REQUIRED')
