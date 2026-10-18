"""Pure conditional exact moments. No IO, fitting, source authority or cash actions."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import time

MODEL = 'EXACT_SPLIT_RETURN_GRAM_DIAGONAL_SHRINK_REFERENCE_V1'
UNIT = 'REGISTERED_RATIONAL_PRIMITIVES_V1'
SCOPE = 'NUMERICAL_MOMENT_PRIMITIVES_ONLY_EXCLUDES_VALIDATION_IO_GCD_AND_INDEPENDENT_CERTIFICATE_RECHECK'
MATRIX_KEYS = {'model_id', 'ordered_security_ids', 'training_dates', 'shape', 'cells'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _budget(value, resume):
    if resume is not None:
        raise NotImplementedError('Resume is not supported in the first version')
    _require(type(value) is int and value >= 0, 'work_budget must be a nonnegative integer, not bool')


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def _validate(matrix):
    _require(type(matrix) is dict and set(matrix) == MATRIX_KEYS, 'Closed matrix schema')
    _require(matrix['model_id'] == MODEL, 'Fixed exact model')
    ids, dates, shape, cells = (matrix[k] for k in ('ordered_security_ids', 'training_dates', 'shape', 'cells'))
    _require(type(ids) is list and ids and all(type(s) is str and s for s in ids) and len(set(ids)) == len(ids), 'Unique ordered SIDs')
    _require(type(dates) is list and len(dates) >= 2 and all(type(d) is str for d in dates)
             and dates == sorted(set(dates)), 'Strict ordered training dates')
    try:
        _require(all(date.fromisoformat(d).isoformat() == d for d in dates), 'Canonical ISO training dates')
    except ValueError as exc:
        raise ValueError('Canonical ISO training dates') from exc
    n, m = len(dates), len(ids)
    _require(type(shape) is list and all(type(x) is int for x in shape) and shape == [n, m], 'Matrix shape')
    _require(type(cells) is list and len(cells) == n and all(type(r) is list and len(r) == m for r in cells), 'Whole matrix rows')
    parsed, nulls, bits = [], [], [0, 0]
    for r, row in enumerate(cells):
        values = []
        for c, value in enumerate(row):
            if value is None:
                values.append(None)
                nulls.append([r, c])
                continue
            _require(type(value) is str, 'Exact cells must be canonical Fraction strings or null')
            try:
                number = Fraction(value)
            except (ValueError, ZeroDivisionError) as exc:
                raise ValueError('Invalid exact Fraction') from exc
            _require(str(number) == value and number > -1, 'Canonical finite return greater than -1')
            bits[0] = max(bits[0], abs(number.numerator).bit_length())
            bits[1] = max(bits[1], number.denominator.bit_length())
            values.append(number)
        parsed.append(values)
    return n, m, parsed, nulls, bits


def prepare_exact_training_moments(*, matrix, work_budget, resume_state=None):
    """Atomic canonical-prefix means/pairs; budget excludes explicitly reported validation."""
    _budget(work_budget, resume_state)
    started = time.perf_counter()
    n, m, values, nulls, input_bits = _validate(matrix)
    source_blocked = bool(nulls)
    task_status = 'SOURCE_BLOCKED' if source_blocked else 'PENDING_BUDGET'
    mean_tasks = [dict(column=c, status=task_status, value=None) for c in range(m)]
    pair_tasks = [dict(i=i, j=j, status=task_status, sample=None, value=None)
                  for i in range(m) for j in range(i, m)]
    counts = dict.fromkeys(('mean_accumulations', 'mean_divisions', 'pair_center_subtractions',
                           'pair_products', 'pair_accumulations', 'sample_divisions',
                           'shrink_multiplications', 'shrink_additions'), 0)
    intermediate_bits, output_bits = [0, 0], [0, 0]
    spent, means, ledger = 0, [], []

    def observe(number, output=False):
        intermediate_bits[0] = max(intermediate_bits[0], abs(number.numerator).bit_length())
        intermediate_bits[1] = max(intermediate_bits[1], number.denominator.bit_length())
        if output:
            output_bits[0] = max(output_bits[0], abs(number.numerator).bit_length())
            output_bits[1] = max(output_bits[1], number.denominator.bit_length())
        return number

    def operation(name, left, right):
        counts[name] += 1
        if name in ('mean_accumulations', 'pair_accumulations', 'shrink_additions'):
            return observe(left + right)
        if name == 'pair_center_subtractions':
            return observe(left - right)
        if name in ('pair_products', 'shrink_multiplications'):
            return observe(left * right)
        return observe(left / right)

    if not source_blocked:
        for c, task in enumerate(mean_tasks):
            cost = n + 1
            if work_budget - spent < cost:
                break
            acc = Fraction(0)
            for row in values:
                acc = operation('mean_accumulations', acc, row[c])
            mean = observe(operation('mean_divisions', acc, Fraction(n)), output=True)
            means.append(mean)
            task.update(status='COMPUTED', value=str(mean))
            ledger.append(dict(kind='MEAN', column=c, cost=cost, start=spent, stop=spent + cost))
            spent += cost
        if len(means) == m:
            for task in pair_tasks:
                cost = 4 * n + 4
                if work_budget - spent < cost:
                    break
                i, j = task['i'], task['j']
                acc = Fraction(0)
                for row in values:
                    left = operation('pair_center_subtractions', row[i], means[i])
                    right = operation('pair_center_subtractions', row[j], means[j])
                    product = operation('pair_products', left, right)
                    acc = operation('pair_accumulations', acc, product)
                sample = operation('sample_divisions', acc, Fraction(n - 1))
                retained = operation('shrink_multiplications', Fraction(13, 20), sample)
                diagonal = operation('shrink_multiplications', Fraction(7, 20), sample if i == j else Fraction(0))
                entry = observe(operation('shrink_additions', retained, diagonal), output=True)
                observe(sample, output=True)
                task.update(status='COMPUTED', sample=str(sample), value=str(entry))
                ledger.append(dict(kind='PAIR', i=i, j=j, cost=cost, start=spent, stop=spent + cost))
                spent += cost
    _require(sum(counts.values()) == spent, 'Actual primitive counts must match budget spent')
    completed_means = sum(t['status'] == 'COMPUTED' for t in mean_tasks)
    completed_pairs = sum(t['status'] == 'COMPUTED' for t in pair_tasks)
    complete = completed_means == m and completed_pairs == len(pair_tasks)
    covariance = None
    if complete:
        covariance = [[None] * m for _ in range(m)]
        for t in pair_tasks:
            covariance[t['i']][t['j']] = covariance[t['j']][t['i']] = t['value']
    total = len(mean_tasks) + len(pair_tasks)
    work = dict(unit=UNIT, scope=SCOPE, requested=work_budget, spent=spent, unused=work_budget - spent,
                actual_primitive_counts=counts, mean_columns_completed=completed_means,
                pair_entries_completed=completed_pairs, required_tasks=total,
                pending_tasks=0 if source_blocked else total - completed_means - completed_pairs,
                source_blocked_tasks=total if source_blocked else 0,
                matrix_validation_cells=n * m, fraction_parses=n * m - len(nulls),
                validation_is_outside_primitive_budget=True, input_max_fraction_bits=input_bits,
                intermediate_max_fraction_bits=intermediate_bits, output_max_fraction_bits=output_bits,
                source_io_calls=0, guard_calls=0, resume_replay_tasks=0,
                independent_certificate_recheck_tasks=0,
                gcd_internal_operations=None, wall_elapsed_seconds=time.perf_counter() - started)
    return dict(schema='EXACT_TRAINING_MOMENTS_V1', model_id=MODEL,
                input_binding='UNBOUND_PURE_INPUT_NOT_SOURCE_AUTHENTICATED',
                matrix_sha256=hashlib.sha256(_canonical(matrix)).hexdigest(),
                status='SOURCE_BLOCKED' if source_blocked else ('COMPLETE' if complete else 'PARTIAL_PENDING_BUDGET'),
                null_coordinates=nulls, mean_tasks=mean_tasks, pair_tasks=pair_tasks,
                full_covariance=covariance, arithmetic_ledger=ledger, work=work,
                certificate=dict(kind='COMPLETE_CENTERED_GRAM_PLUS_DIAGONAL' if complete else 'INCOMPLETE_NO_FULL_PSD_CLAIM',
                                 n=n, ddof=1, lambda_exact='7/20',
                                 matrix_sha256=hashlib.sha256(_canonical(matrix)).hexdigest(),
                                 independently_checked=False),
                qualified_inventory=None, current_account=None, current_new_money=None, plan_rows=[],
                permissions=dict(source_authenticated=False, fit_performed=False, winner_selected=False,
                                 execution_authorized=False, formal_training_input_admitted=False))


def check_exact_training_moment_certificate(*, matrix, result):
    """Independent requested replay, visibly separate from original preparation budget."""
    _require(type(result) is dict and type(result.get('work')) is dict, 'Result schema')
    budget = result['work'].get('requested')
    replay = prepare_exact_training_moments(matrix=matrix, work_budget=budget)
    left, right = deepcopy(result), deepcopy(replay)
    for obj in (left, right):
        obj['work'].pop('wall_elapsed_seconds', None)
    _require(left == right, 'Moment certificate/prefix/ledger differs from independent exact replay')
    return dict(status='PASS_EXACT_PREFIX_REPLAY_NOT_SOURCE_AUTHENTICATION',
                recheck_primitive_calls=replay['work']['spent'],
                recheck_validation_cells=replay['work']['matrix_validation_cells'],
                complete_psd_verified=replay['status'] == 'COMPLETE', source_authenticated=False)
