"""Create-only registered V2 versus saved V1 comparison; no execution on import."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = 'scripts/return_priority_quantity_v2_comparison.py'
LOADED_RUNNER_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
METHODS = ('backtest/log_concave_integer_search.py', 'backtest/affordable_support_seeds.py',
           'backtest/quantity_training_upper_bound.py',
           'backtest/return_priority_fresh_cash_quantity_search_v2.py')


def absolute(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def digest(path):
    return hashlib.sha256(absolute(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(absolute(path).read_bytes())


def verified_load(path, expected):
    raw = absolute(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('LOADED_INPUT_PIN_CHANGED:' + str(path))
    return json.loads(raw)


def put_pin(pins, path, sha):
    if path in pins and pins[path] != sha:
        raise ValueError('CONFLICTING_PIN:' + str(path))
    pins[path] = sha


def verify(pins):
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError('PIN_CHANGED:' + path)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def register(*, draft_path, review_path, output):
    """Caller must read the independent review before invoking registration."""
    draft_sha, review_sha = digest(draft_path), digest(review_path)
    draft, review = verified_load(draft_path, draft_sha), verified_load(review_path, review_sha)
    if (review.get('status') not in ('PASS', 'CONDITIONAL_PASS')
            or review.get('independent_review') is not True
            or review.get('eligible_for_original94_single_conditional_research') is not True):
        raise ValueError('INDEPENDENT_REVIEW_NOT_PASSED')
    reviewed = review.get('reviewed_source_hashes', {})
    if not set(METHODS) <= draft['method_hashes'].keys():
        raise ValueError('MANDATORY_METHOD_CLOSURE_MISSING')
    if any(reviewed.get(p) != sha for p,sha in draft['method_hashes'].items()):
        raise ValueError('INDEPENDENT_REVIEW_METHOD_PINS_MISMATCH')
    if (draft['maximum_new_search_calls'] != 1 or draft['maximum_objective_evaluations'] != 8192
            or draft['baseline_search_calls'] != 0 or draft['book_calls'] != 0 or draft['automatic_retry']):
        raise ValueError('DRAFT_BUDGET_CHANGED')
    pins = dict(draft['source_pins'])
    for group in ('method_hashes', 'test_hashes', 'protected_before'):
        for path, sha in draft[group].items():
            if path in pins and pins[path] != sha:
                raise ValueError('CONFLICTING_DRAFT_PIN:' + path)
            pins[path] = sha
    for field in ('input', 'baseline_result', 'source_registration'):
        path,sha = draft[field+'_path'],draft[field+'_sha256']
        if path in pins and pins[path] != sha:
            raise ValueError('CONFLICTING_INPUT_PIN')
        pins[path] = sha
    verify(pins)
    for path in (RUNNER, 'api/server.py', 'web/index.html'):
        put_pin(pins, str(path), digest(path))
    put_pin(pins, str(draft_path), draft_sha)
    put_pin(pins, str(review_path), review_sha)
    if pins[RUNNER] != LOADED_RUNNER_SHA:
        raise ValueError('LOADED_RUNNER_CHANGED')
    args = verified_load(draft['input_path'], draft['input_sha256'])
    original = verified_load(draft['source_registration_path'], draft['source_registration_sha256'])
    if (original['inputs_sha256'] != draft['input_sha256'] or original['candidate_count'] != 94
            or original['issuer_count'] != 93 or original['maximum_objective_evaluations'] != 8192
            or original['decision_date'] != args['decision_date']):
        raise ValueError('ORIGINAL_REGISTRATION_SCOPE_MISMATCH')
    if args['max_objective_evaluations'] != 8192 or args['decision_date'] != draft['decision_date']:
        raise ValueError('INPUT_BUDGET_OR_DATE_CHANGED')
    if len(args['prices']) != 94 or len({m['issuer_id'] for m in args['metadata'].values()}) != 93:
        raise ValueError('SAME_INPUT_DOMAIN_CHANGED')
    verify(pins)
    directory = absolute(output)
    directory.mkdir()
    save(directory/'registration.json', dict(schema='V2_SINGLE_COMPARISON_REGISTRATION_V1',
        source_hashes=pins, input_path=draft['input_path'], baseline_path=draft['baseline_result_path'],
        independent_review_path=str(review_path), maximum_search_calls=1, baseline_search_calls=0,
        book_calls=0, automatic_retry=False, independent_oos=False, adoption_allowed=False,
        protected_paths=list(draft['protected_before']) + ['api/server.py', 'web/index.html']))
    return digest(directory/'registration.json')


def run(*, output, registration_sha256):
    directory = absolute(output)
    registration = verified_load(directory/'registration.json', registration_sha256)
    if {p.name for p in directory.iterdir()} != {'registration.json'}:
        raise ValueError('ALREADY_STARTED_NO_RETRY')
    verify(registration['source_hashes'])
    pins = registration['source_hashes']
    if pins.get(RUNNER) != LOADED_RUNNER_SHA or not set(METHODS) <= pins.keys():
        raise ValueError('RUNNER_OR_METHOD_CLOSURE_MISMATCH')
    if (registration.get('maximum_search_calls') != 1 or registration.get('baseline_search_calls') != 0
            or registration.get('book_calls') != 0 or registration.get('automatic_retry') is not False):
        raise ValueError('REGISTERED_BUDGET_MISMATCH')
    arguments = verified_load(registration['input_path'], pins[registration['input_path']])
    baseline = verified_load(registration['baseline_path'], pins[registration['baseline_path']])
    if (arguments['max_objective_evaluations'] != 8192 or arguments['decision_date'] != '2026-10-13'
            or len(arguments['prices']) != 94
            or len({m['issuer_id'] for m in arguments['metadata'].values()}) != 93):
        raise ValueError('REGISTERED_INPUT_SCOPE_MISMATCH')
    captured = {}
    for path in METHODS:
        name = path[:-3].replace('/', '.')
        if name in sys.modules:
            raise ValueError('FRESH_PROCESS_REQUIRED:' + name)
        raw = absolute(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pins[path]:
            raise ValueError('CAPTURED_METHOD_PIN_CHANGED:' + path)
        captured[name] = (path, compile(raw, str(absolute(path)), 'exec'))
    save(directory/'started.json', dict(registration_sha256=registration_sha256,
        maximum_new_search_calls=1, baseline_search_calls=0, automatic_retry=False))
    started = time.perf_counter()
    installed = []
    try:
        importlib.import_module('backtest')
        for name, (path, compiled) in captured.items():
            module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(name, absolute(path)))
            sys.modules[name] = module
            installed.append(name)
            exec(compiled, module.__dict__)
        core = sys.modules['backtest.return_priority_fresh_cash_quantity_search_v2']
        result = core.search_fresh_cash_quantities(**arguments)
        save(directory/'result.json', result)
        from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound
        from fractions import Fraction
        metrics = {}
        for name, item in [('saved_v1', baseline), ('new_v2', result)]:
            if item['decision_date'] != arguments['decision_date'] or Fraction(item['entered_cash']) != Fraction(arguments['entered_cash']):
                raise ValueError('RESULT_INPUT_BINDING_MISMATCH')
            if item['selected'] is None:
                metrics[name] = dict(status=item['status'], selected=None)
                continue
            bound = training_product_upper_bound(cash=Fraction(arguments['entered_cash']),
                fee=Fraction(arguments['fee_bps'])/10000, buffer=Fraction(arguments['minimum_cash_buffer']),
                prices=arguments['prices'], scenarios=arguments['training_scenarios'],
                quantities=item['selected']['quantities'])
            metrics[name] = dict(status=item['status'], selected=item['selected'],
                exact_training_product=str(bound['candidate_product']), bound=public_bound(bound),
                per_k=item['per_k'], objective_evaluations=item['objective_evaluations'])
        save(directory/'comparison.json', dict(methods=metrics, price_only=True,
            forecast_return=None, annualized_return=None, independent_oos=False, adoption_allowed=False))
        verify(registration['source_hashes'])
        save(directory/'terminal.json', dict(status='RETURNED_REQUIRES_INDEPENDENT_READBACK',
            elapsed_seconds=time.perf_counter()-started, actual_search_calls=1, baseline_search_calls=0,
            book_calls=0, result_sha256=digest(directory/'result.json')))
    except Exception as error:
        after = {}
        for path in registration.get('protected_paths', []):
            try:
                after[path] = digest(path)
            except OSError:
                after[path] = None
        save(directory/'failure.json', dict(type=type(error).__name__, message=str(error),
            elapsed_seconds=time.perf_counter()-started, automatic_retry=False, protected_after=after))
        raise
    finally:
        for name in reversed(installed):
            sys.modules.pop(name, None)
