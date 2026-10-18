"""Pure independent raw-cross-moment identity; no IO or producer algorithms."""
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
import re
import sys
import time

MODEL = 'EXACT_SPLIT_RETURN_GRAM_DIAGONAL_SHRINK_REFERENCE_V1'
UNIT = 'INDEPENDENT_RAW_CROSS_MOMENT_PRIMITIVES_V1'
SCOPE = 'IDENTITY_PRIMITIVES_ONLY_EXCLUDES_PARSE_GCD_IO_GUARD_AND_PRODUCER_REPLAY'
PRODUCER_SCOPE = 'NUMERICAL_MOMENT_PRIMITIVES_ONLY_EXCLUDES_VALIDATION_IO_GCD_AND_INDEPENDENT_CERTIFICATE_RECHECK'
PERMISSIONS = {'source_authenticated', 'fit_performed', 'winner_selected', 'execution_authorized', 'formal_training_input_admitted'}
LIMITS = (14237, 14131)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _closed(value, keys, label):
    _require(type(value) is dict and set(value) == set(keys.split()), 'Closed ' + label)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def _bits(number):
    return [abs(number.numerator).bit_length(), number.denominator.bit_length()]


def _maximum(left, right):
    return [max(a, b) for a, b in zip(left, right)]


def _bit_pair(value, bounds, label):
    _require(type(value) is list and len(value) == 2
             and all(type(x) is int and 0 <= x <= limit for x, limit in zip(value, bounds)), label)


def _literal(value, bounds, audit):
    _require(type(value) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?', value) is not None,
             'Canonical Fraction literal syntax')
    numerator, _, denominator = value.partition('/')
    denominator = denominator or '1'
    _require(value != '-0' and (not '/' in value or numerator not in ('0', '-0') and denominator != '1'),
             'Canonical Fraction literal representation')
    _require(len(numerator.lstrip('-')) <= (bounds[0] + 2) // 3
             and len(denominator) <= (bounds[1] + 2) // 3, 'Literal decimal premise')
    a, b = int(numerator), int(denominator)
    audit['integer_parses'] += 2
    _require(abs(a).bit_length() <= bounds[0] and b.bit_length() <= bounds[1], 'Literal bit premise')
    audit['gcd_checks'] += 1
    _require(math.gcd(abs(a), b) == 1, 'Canonical reduced Fraction literal')
    audit['fraction_constructions'] += 1
    return Fraction(a, b)


def _matrix(matrix, audit):
    _closed(matrix, 'model_id ordered_security_ids training_dates shape cells', 'matrix')
    _require(matrix['model_id'] == MODEL, 'Fixed model')
    ids, dates = matrix['ordered_security_ids'], matrix['training_dates']
    _require(type(ids) is list and 1 <= len(ids) <= 77 and all(type(x) is str and x for x in ids)
             and len(set(ids)) == len(ids), 'Unique ordered whole SIDs')
    _require(type(dates) is list and 2 <= len(dates) <= 126 and all(type(x) is str for x in dates)
             and dates == sorted(set(dates)), 'Ordered whole dates')
    _require(all(date.fromisoformat(x).isoformat() == x for x in dates), 'Canonical ISO dates')
    n, m = len(dates), len(ids)
    _require(type(matrix['shape']) is list and all(type(x) is int for x in matrix['shape'])
             and matrix['shape'] == [n, m], 'Exact typed matrix shape')
    rows = matrix['cells']
    _require(type(rows) is list and len(rows) == n and all(type(r) is list and len(r) == m for r in rows), 'Whole matrix cells')
    values, bits = [], [0, 0]
    for row in rows:
        parsed = []
        for text in row:
            number = _literal(text, (53, 56), audit)
            _require(number > -1, 'Return strictly greater than minus one')
            bits = _maximum(bits, _bits(number)); parsed.append(number)
        values.append(parsed)
    return n, m, values, bits, hashlib.sha256(_canonical(matrix)).hexdigest()


def _producer(result, n, m, digest, input_bits, audit):
    _closed(result, 'schema model_id input_binding matrix_sha256 status null_coordinates mean_tasks pair_tasks full_covariance arithmetic_ledger work certificate qualified_inventory current_account current_new_money plan_rows permissions', 'producer result')
    _require(result['schema'] == 'EXACT_TRAINING_MOMENTS_V1' and result['model_id'] == MODEL
             and result['input_binding'] == 'UNBOUND_PURE_INPUT_NOT_SOURCE_AUTHENTICATED'
             and result['matrix_sha256'] == digest and result['status'] == 'COMPLETE'
             and result['null_coordinates'] == [], 'Complete original pure matrix association')
    _require(result['qualified_inventory'] is None and result['current_account'] is None
             and result['current_new_money'] is None and result['plan_rows'] == [], 'No qualification/current cash/plans')
    _closed(result['permissions'], ' '.join(PERMISSIONS), 'producer permissions')
    _require(all(value is False for value in result['permissions'].values()), 'All permissions False')
    pairs_count = m * (m + 1) // 2
    full_cost = m * (n + 1) + pairs_count * (4 * n + 4)
    work = result['work']
    _closed(work, 'unit scope requested spent unused actual_primitive_counts mean_columns_completed pair_entries_completed required_tasks pending_tasks source_blocked_tasks matrix_validation_cells fraction_parses validation_is_outside_primitive_budget input_max_fraction_bits intermediate_max_fraction_bits output_max_fraction_bits source_io_calls guard_calls resume_replay_tasks independent_certificate_recheck_tasks gcd_internal_operations wall_elapsed_seconds', 'producer work')
    _require(work['unit'] == 'REGISTERED_RATIONAL_PRIMITIVES_V1' and work['scope'] == PRODUCER_SCOPE
             and work['validation_is_outside_primitive_budget'] is True and work['gcd_internal_operations'] is None,
             'Producer budget boundaries')
    _require(type(work['wall_elapsed_seconds']) in (int, float) and math.isfinite(work['wall_elapsed_seconds'])
             and work['wall_elapsed_seconds'] >= 0, 'Finite producer elapsed declaration')
    expected = dict(requested=full_cost, spent=full_cost, unused=0, mean_columns_completed=m,
                    pair_entries_completed=pairs_count, required_tasks=m+pairs_count, pending_tasks=0,
                    source_blocked_tasks=0, matrix_validation_cells=n*m, fraction_parses=n*m,
                    source_io_calls=0, guard_calls=0, resume_replay_tasks=0, independent_certificate_recheck_tasks=0)
    for key, value in expected.items():
        _require(type(work[key]) is int and work[key] == value, 'Typed producer work:' + key)
    counts = dict(mean_accumulations=n*m, mean_divisions=m, pair_center_subtractions=2*n*pairs_count,
                  pair_products=n*pairs_count, pair_accumulations=n*pairs_count, sample_divisions=pairs_count,
                  shrink_multiplications=2*pairs_count, shrink_additions=pairs_count)
    _require(_canonical(work['actual_primitive_counts']) == _canonical(counts), 'Exact typed producer primitive declarations')
    _bit_pair(work['input_max_fraction_bits'], (53, 56), 'Input bit summary')
    _require(work['input_max_fraction_bits'] == input_bits, 'Independently parsed input bits')
    _bit_pair(work['intermediate_max_fraction_bits'], (14245, 14138), 'Producer intermediate static bounds only')
    _bit_pair(work['output_max_fraction_bits'], (14245, 14138), 'Producer output bit bounds')
    means, pairs, covariance, ledger = (result[k] for k in ('mean_tasks', 'pair_tasks', 'full_covariance', 'arithmetic_ledger'))
    _require(type(means) is list and len(means) == m and type(pairs) is list and len(pairs) == pairs_count
             and type(ledger) is list and len(ledger) == m+pairs_count
             and type(covariance) is list and len(covariance) == m
             and all(type(row) is list and len(row) == m for row in covariance), 'Whole producer output shape')
    parsed_means, parsed_pairs, bits, characters, offset = [], [], [0, 0], 0, 0
    for i, task in enumerate(means):
        _closed(task, 'column status value', 'producer mean task')
        _require(type(task['column']) is int and task['column'] == i and task['status'] == 'COMPUTED', 'Canonical computed mean order')
        number = _literal(task['value'], (7116, 7063), audit)
        parsed_means.append(number); bits = _maximum(bits, _bits(number)); characters += len(task['value'])
        expected_ledger = dict(kind='MEAN', column=i, cost=n+1, start=offset, stop=offset+n+1)
        _require(_canonical(ledger[i]) == _canonical(expected_ledger), 'Typed original mean ledger')
        offset += n+1
    for ordinal, (i, j) in enumerate((i, j) for i in range(m) for j in range(i, m)):
        task = pairs[ordinal]
        _closed(task, 'i j status sample value', 'producer pair task')
        _require(type(task['i']) is int and type(task['j']) is int and task['i'] == i and task['j'] == j
                 and task['status'] == 'COMPUTED', 'Canonical computed pair order')
        sample = _literal(task['sample'], (14241, 14133), audit)
        entry = _literal(task['value'], (14245, 14138), audit)
        parsed_pairs.append((sample, entry)); bits = _maximum(bits, _maximum(_bits(sample), _bits(entry)))
        characters += len(task['sample']) + len(task['value'])
        for row, column in ((i, j),) if i == j else ((i, j), (j, i)):
            _require(type(covariance[row][column]) is str and covariance[row][column] == task['value'], 'Every full covariance coordinate association')
            characters += len(covariance[row][column])
        expected_ledger = dict(kind='PAIR', i=i, j=j, cost=4*n+4, start=offset, stop=offset+4*n+4)
        _require(_canonical(ledger[m+ordinal]) == _canonical(expected_ledger), 'Typed original pair ledger')
        offset += 4*n+4
    _require(bits == work['output_max_fraction_bits'], 'Independently parsed all producer output bits')
    _require(all(a >= b for a, b in zip(work['intermediate_max_fraction_bits'], bits)), 'Observed producer output is also intermediate')
    _require(characters <= 113304961, 'Signed numeric ASCII bound including all covariance copies')
    expected_certificate = dict(kind='COMPLETE_CENTERED_GRAM_PLUS_DIAGONAL', n=n, ddof=1, lambda_exact='7/20',
                                matrix_sha256=digest, independently_checked=False)
    _require(_canonical(result['certificate']) == _canonical(expected_certificate), 'Original Gram declaration remains False')
    return parsed_means, parsed_pairs, characters


def verify_raw_cross_moment_identity(*, matrix, numerical_result, work_budget, resume=None):
    """Independent, finite, atomic-prefix arithmetic. Pure caller input remains UNBOUND."""
    if resume is not None:
        raise NotImplementedError('Independent identity resume is not supported')
    _require(type(work_budget) is int and 0 <= work_budget <= 787556, 'Explicit finite work_budget nonbool in0..787556')
    _require(sys.get_int_max_str_digits() == 8192 and sys.flags.int_max_str_digits == 8192, 'Independent runtime get/flags must both be8192')
    started = time.perf_counter()
    validation = dict(integer_parses=0, gcd_checks=0, fraction_constructions=0)
    n, m, values, input_bits, digest = _matrix(matrix, validation)
    pair_count = m*(m+1)//2; required = m*(n+1)+pair_count*(2*n+7)
    _require(work_budget <= required, 'Budget exceeds registered dimensional complete cost')
    original_means, original_pairs, characters = _producer(numerical_result, n, m, digest, input_bits, validation)
    mean_tasks = [dict(column=i, status='PENDING_BUDGET', value=None) for i in range(m)]
    pair_tasks = [dict(i=i, j=j, status='PENDING_BUDGET', sample=None, value=None) for i in range(m) for j in range(i, m)]
    counts = dict.fromkeys(('mean_accumulations', 'mean_divisions', 'raw_cross_products', 'raw_cross_accumulations',
                            'mean_products', 'correction_multiplications', 'cross_correction_subtractions',
                            'sample_divisions', 'shrink_multiplications', 'shrink_additions'), 0)
    intermediate, output_bits, means, ledger = [0, 0], [0, 0], [], []
    spent = comparisons = 0

    def observe(number, output=False):
        nonlocal intermediate, output_bits
        bits = _bits(number)
        _require(all(x <= limit for x, limit in zip(bits, LIMITS)), 'Independent normalized Fraction bound')
        intermediate = _maximum(intermediate, bits)
        if output:
            output_bits = _maximum(output_bits, bits)
        return number

    def operate(kind, left, right):
        counts[kind] += 1
        if kind in ('mean_accumulations', 'raw_cross_accumulations', 'shrink_additions'):
            return observe(left + right)
        if kind == 'cross_correction_subtractions':
            return observe(left - right)
        if kind in ('mean_divisions', 'sample_divisions'):
            return observe(left / right)
        return observe(left * right)

    for i, task in enumerate(mean_tasks):
        if work_budget-spent < n+1:
            break
        acc = Fraction(0)
        for row in values:
            acc = operate('mean_accumulations', acc, row[i])
        mean = observe(operate('mean_divisions', acc, Fraction(n)), output=True)
        _require(mean == original_means[i] and str(mean) == numerical_result['mean_tasks'][i]['value'], 'Independent mean mismatch')
        means.append(mean); task.update(status='VERIFIED', value=str(mean))
        ledger.append(dict(kind='MEAN', column=i, cost=n+1, start=spent, stop=spent+n+1)); spent += n+1
    if len(means) == m:
        for ordinal, task in enumerate(pair_tasks):
            cost = 2*n+7
            if work_budget-spent < cost:
                break
            i, j = task['i'], task['j']; acc = Fraction(0)
            for row in values:
                acc = operate('raw_cross_accumulations', acc, operate('raw_cross_products', row[i], row[j]))
            product = operate('mean_products', means[i], means[j])
            correction = operate('correction_multiplications', Fraction(n), product)
            centered = operate('cross_correction_subtractions', acc, correction)
            sample = observe(operate('sample_divisions', centered, Fraction(n-1)), output=True)
            retained = operate('shrink_multiplications', Fraction(13, 20), sample)
            diagonal = operate('shrink_multiplications', Fraction(7, 20), sample if i == j else Fraction(0))
            entry = observe(operate('shrink_additions', retained, diagonal), output=True)
            _require((sample, entry) == original_pairs[ordinal]
                     and str(sample) == numerical_result['pair_tasks'][ordinal]['sample']
                     and str(entry) == numerical_result['pair_tasks'][ordinal]['value'], 'Independent sample/entry mismatch')
            for row, column in ((i, j),) if i == j else ((i, j), (j, i)):
                _require(numerical_result['full_covariance'][row][column] == str(entry), 'Independent full coordinate mismatch')
                comparisons += 1
            task.update(status='VERIFIED', sample=str(sample), value=str(entry))
            ledger.append(dict(kind='PAIR', i=i, j=j, cost=cost, start=spent, stop=spent+cost)); spent += cost
    _require(sum(counts.values()) == spent, 'Actual identity primitive accounting')
    completed_pairs = sum(t['status'] == 'VERIFIED' for t in pair_tasks)
    complete = len(means) == m and completed_pairs == pair_count
    return dict(schema='INDEPENDENT_RAW_CROSS_MOMENT_READBACK_V1', model_id=MODEL,
                status='PASS_INDEPENDENT_RAW_CROSS_MOMENT_IDENTITY_NOT_SOURCE_OR_ECONOMIC_ADMISSION' if complete else 'PARTIAL_PENDING_BUDGET',
                input_binding='UNBOUND_PURE_INPUT_NOT_SOURCE_AUTHENTICATED', matrix_sha256=digest,
                mean_tasks=mean_tasks, pair_tasks=pair_tasks, arithmetic_ledger=ledger,
                work=dict(unit=UNIT, scope=SCOPE, requested=work_budget, spent=spent, unused=work_budget-spent,
                          complete_cost=required, actual_primitive_counts=counts, means_verified=len(means), pairs_verified=completed_pairs,
                          pending_tasks=m+pair_count-len(means)-completed_pairs, full_coordinates_independently_compared=comparisons,
                          producer_full_coordinates_associated=m*m, input_max_fraction_bits=input_bits,
                          intermediate_max_fraction_bits=intermediate, output_max_fraction_bits=output_bits,
                          validation=validation, validation_outside_primitive_budget=True, original_numeric_ascii_all_copies=characters,
                          source_io_calls=0, guard_calls=0, producer_algorithm_calls=0, resume_replay_tasks=0,
                          gcd_internal_operations=None, elapsed_seconds=time.perf_counter()-started),
                producer_declarations=dict(ledger_and_count_schedule_checked=True, actual_execution_trace_independently_observed=False,
                                           intermediate_static_bounds_checked=True, intermediate_maxima_independently_replayed=False,
                                           output_maxima_independently_parsed=True, original_certificate_independently_checked=False),
                certificate=dict(kind='INDEPENDENT_RAW_CROSS_MOMENT_EQUALITY_WITH_SHRINK_GRAM_IDENTITY' if complete else 'INCOMPLETE_NO_FULL_EQUALITY_OR_PSD_CLAIM',
                                 n=n, ddof=1, lambda_exact='7/20', matrix_sha256=digest,
                                 independent_arithmetic_readback_complete=complete, original_certificate_modified=False,
                                 psd_conclusion_scope='EXACT_DESCRIPTIVE_GRAM_IDENTITY_ONLY' if complete else None),
                qualified_inventory=None, current_account=None, current_new_money=None, plan_rows=[],
                real_joint_objective='UNREGISTERED', causal_action_rule='UNREGISTERED', thirteen_cohort_prior_cash='SOURCE_BLOCKED',
                permissions={key: False for key in sorted(PERMISSIONS)})
