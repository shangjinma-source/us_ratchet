"""New bounded moments regressions and one explicitly separate real bank snapshot."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_full_pool_training_moments_research as moments
from backtest import ndx_full_pool_training_matrix_binding_research as bank


def small(cells=None):
    cells = cells or [['0', '1/10'], ['1/5', '0'], ['1/10', '1/5']]
    return dict(model_id=moments.MODEL, ordered_security_ids=['A', 'B'],
                training_dates=['2026-01-01', '2026-01-02', '2026-01-03'], shape=[3, 2], cells=cells)


def oracle(matrix):
    # Independent summation identity, not the implementation's centered-product algorithm.
    rows = [[Fraction(x) for x in r] for r in matrix['cells']]
    n, m = matrix['shape']
    sums = [sum((r[c] for r in rows), Fraction()) for c in range(m)]
    means = [s / n for s in sums]
    sample = [[(sum((r[i] * r[j] for r in rows), Fraction()) - sums[i] * sums[j] / n) / (n - 1)
               for j in range(m)] for i in range(m)]
    cov = [[sample[i][j] * (1 if i == j else Fraction(13, 20)) for j in range(m)] for i in range(m)]
    return means, cov


class PureMomentUnits(unittest.TestCase):
    def test_complete_independent_fraction_oracle_and_certificate(self):
        matrix = small()
        result = moments.prepare_exact_training_moments(matrix=matrix, work_budget=56)
        means, cov = oracle(matrix)
        self.assertEqual(result['full_covariance'], [[str(x) for x in row] for row in cov])
        self.assertEqual([t['value'] for t in result['mean_tasks']], list(map(str, means)))
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['work']['spent'], 56)
        check = moments.check_exact_training_moment_certificate(matrix=matrix, result=result)
        self.assertTrue(check['complete_psd_verified'])
        self.assertFalse(check['source_authenticated'])

    def test_zero_and_every_atomic_boundary(self):
        for budget in (0, 1, 3, 4, 7, 8, 23, 24, 39, 40, 55, 56, 100):
            with self.subTest(budget=budget):
                out = moments.prepare_exact_training_moments(matrix=small(), work_budget=budget)
                expected = 0 if budget < 4 else 4 if budget < 8 else 8 + min(3, (budget - 8) // 16) * 16
                self.assertEqual(out['work']['spent'], expected)
                self.assertEqual(out['work']['unused'], budget - expected)
                self.assertEqual(sum(out['work']['actual_primitive_counts'].values()), expected)
                self.assertEqual(out['work']['pending_tasks'], 5 - len(out['arithmetic_ledger']))
                if budget < 56:
                    self.assertIsNone(out['full_covariance'])

    def test_actual_fraction_operations_match_report_including_offdiag_zero(self):
        actual = dict(add=0, sub=0, mul=0, div=0)
        originals = {name: getattr(Fraction, attr) for name, attr in
                     [('add', '__add__'), ('sub', '__sub__'), ('mul', '__mul__'), ('div', '__truediv__')]}
        def wrapped(name):
            def perform(left, right):
                actual[name] += 1
                return originals[name](left, right)
            return perform
        with patch.object(Fraction, '__add__', wrapped('add')), patch.object(Fraction, '__sub__', wrapped('sub')), \
             patch.object(Fraction, '__mul__', wrapped('mul')), patch.object(Fraction, '__truediv__', wrapped('div')):
            result = moments.prepare_exact_training_moments(matrix=small(), work_budget=56)
        self.assertEqual(actual, dict(add=18, sub=18, mul=15, div=5))
        self.assertEqual(sum(actual.values()), result['work']['spent'])

    def test_n126_registered_costs(self):
        from datetime import date, timedelta
        matrix = dict(model_id=moments.MODEL, ordered_security_ids=['A'], shape=[126, 1],
                      training_dates=[(date(2025,1,1) + timedelta(days=i)).isoformat() for i in range(126)],
                      cells=[['1/10'] for _ in range(126)])
        result = moments.prepare_exact_training_moments(matrix=matrix, work_budget=635)
        self.assertEqual([t['cost'] for t in result['arithmetic_ledger']], [127, 508])
        self.assertEqual(result['full_covariance'], [['0']])
        self.assertEqual(result['work']['actual_primitive_counts']['pair_products'], 126)

    def test_null_blocks_entire_matrix_without_arithmetic(self):
        matrix = small()
        matrix['cells'][1][0] = None
        result = moments.prepare_exact_training_moments(matrix=matrix, work_budget=999)
        self.assertEqual(result['status'], 'SOURCE_BLOCKED')
        self.assertEqual(result['work']['spent'], 0)
        self.assertEqual(result['work']['source_blocked_tasks'], 5)
        self.assertEqual(result['null_coordinates'], [[1, 0]])

    def test_constant_singular_psd_and_intermediate_bit_growth(self):
        for cells in ([['1/3','2/3']]*3, [['0','0'],['1/1000000007','1/1000000009'],['1/1000000033','1/1000000087']]):
            matrix = small(cells)
            result = moments.prepare_exact_training_moments(matrix=matrix, work_budget=56)
            self.assertEqual(result['full_covariance'], [[str(x) for x in row] for row in oracle(matrix)[1]])
            cov = [[Fraction(x) for x in row] for row in result['full_covariance']]
            self.assertGreaterEqual(cov[0][0] * cov[1][1] - cov[0][1] ** 2, 0)
            self.assertGreaterEqual(result['work']['intermediate_max_fraction_bits'][1], result['work']['output_max_fraction_bits'][1])
        self.assertGreater(result['work']['intermediate_max_fraction_bits'][1], result['work']['input_max_fraction_bits'][1])

    def test_closed_schema_and_invalid_numbers_dates_and_domain(self):
        changes = [lambda m: m.update(extra=True), lambda m: m['cells'][0].__setitem__(0, True),
                   lambda m: m['cells'][0].__setitem__(0, 0.1), lambda m: m['cells'][0].__setitem__(0, '1.0'),
                   lambda m: m['cells'][0].__setitem__(0, '-1'), lambda m: m['cells'][0].__setitem__(0, 'NaN'),
                   lambda m: m['cells'][0].__setitem__(0, '1/0'), lambda m: m['shape'].__setitem__(0, True),
                   lambda m: m['ordered_security_ids'].__setitem__(1, 'A'),
                   lambda m: m['training_dates'].__setitem__(0, 'not-a-date'),
                   lambda m: m['training_dates'].reverse(), lambda m: m.update(model_id='caller-selected')]
        for change in changes:
            matrix = small(); change(matrix)
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                moments.prepare_exact_training_moments(matrix=matrix, work_budget=100)

    def test_pure_no_io_permissions_and_detached_input(self):
        matrix = small(); before = deepcopy(matrix)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('IO')):
            result = moments.prepare_exact_training_moments(matrix=matrix, work_budget=56)
        self.assertEqual(matrix, before)
        self.assertTrue(all(v is False for v in result['permissions'].values()))
        self.assertIsNone(result['current_account'])
        self.assertEqual(result['plan_rows'], [])

    def test_resume_budget_validation_precedes_matrix(self):
        for budget in (None, True, -1, 2.5, '10'):
            with self.assertRaises(ValueError):
                moments.prepare_exact_training_moments(matrix=None, work_budget=budget)
        for state in ({}, False, {'rehashed': True}):
            with self.assertRaises(NotImplementedError):
                moments.prepare_exact_training_moments(matrix=None, work_budget=0, resume_state=state)

    def test_rehashed_result_matrix_and_ledger_tampering_rejected(self):
        matrix = small(); original = moments.prepare_exact_training_moments(matrix=matrix, work_budget=24)
        for change in (lambda r: r['pair_tasks'][0].update(value='99'),
                       lambda r: r['arithmetic_ledger'][0].update(cost=0),
                       lambda r: r['work'].update(spent=0),
                       lambda r: r['mean_tasks'].reverse(),
                       lambda r: r['certificate'].update(independently_checked=True)):
            result = deepcopy(original); change(result)
            with self.assertRaises(ValueError):
                moments.check_exact_training_moment_certificate(matrix=matrix, result=result)
        changed = small(); changed['cells'][0][0] = '1/10'
        original['matrix_sha256'] = hashlib.sha256(moments._canonical(changed)).hexdigest()
        with self.assertRaises(ValueError):
            moments.check_exact_training_moment_certificate(matrix=changed, result=original)

    def test_shared_budget_stops_prefix_across_matrices(self):
        items = [dict(matrix=small(), window_ordinals=[0, 1]), dict(matrix=small(), window_ordinals=[2])]
        remaining, spent, counts = bank._estimate_unique(items, 23, moments)
        self.assertEqual((remaining, spent), (15, 8))
        self.assertEqual(items[1]['moments']['work']['spent'], 0)
        self.assertEqual(sum(counts.values()), 8)
        self.assertEqual(items[0]['window_ordinals'], [0, 1])

    def test_full_matrix_principal_submatrix_equals_same_dates(self):
        matrix = small()
        full = moments.prepare_exact_training_moments(matrix=matrix, work_budget=56)
        sub = dict(model_id=moments.MODEL, ordered_security_ids=['B'], training_dates=matrix['training_dates'],
                   shape=[3,1], cells=[[r[1]] for r in matrix['cells']])
        out = moments.prepare_exact_training_moments(matrix=sub, work_budget=20)
        self.assertEqual(out['full_covariance'][0][0], full['full_covariance'][1][1])


class BankBoundaryUnits(unittest.TestCase):
    def test_invalid_host_options_fail_before_any_file_read(self):
        cases = [dict(include_covariance=True), dict(include_covariance=1),
                 dict(include_saved_dual_benchmarks=1), dict(work_budget=True), dict(work_budget=-1),
                 dict(work_budget=1), dict(include_covariance=True, work_budget=1.0),
                 dict(covariance_model='new-objective')]
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Read before parameter gate')):
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    bank.read_source_bound_training_bank(**kwargs)
            for state in ({}, False):
                with self.assertRaises(NotImplementedError):
                    bank.read_source_bound_training_bank(resume_state=state)
            with self.assertRaises(NotImplementedError):
                bank.read_source_bound_training_bank(include_covariance=True, work_budget=0, covariance_model=bank.LEGACY_MODEL)

    def test_fixed_source_pin_and_symlink_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'module.py'; p.write_text('raise AssertionError("executed")', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Fixed source bytes changed'):
                bank._load_fixed((p, '0'*64))
            link = Path(directory) / 'link.py'
            try:
                link.symlink_to(p)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, 'Reparse/symlink'):
                bank._read_regular(link)

    def test_cell_accessor_no_io_global_indices_and_detachment(self):
        column = dict(coordinate={'security_id':'A'}, original_channel=dict(
            return_rows=[dict(split_only_return_exact='0', split_only_return_float='0')] * 4,
            quote_rows=[dict(raw_row_index=None, reasons=['original'])] * 5),
            original_numeric_tokens={f'/return_rows/{i}/split_only_return_float':{'original_lexeme':'0'} for i in range(4)},
            raw_required_scope_numeric_tokens={}, source_reference={'path':'fixed'}, raw_reference={}, receipt_reference={})
        data = dict(windows=[dict(training_start=2)], source_columns=[column], shared_lineage_references={})
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('IO')):
            cell = bank.get_training_cell(data, window_ordinal=0, row=1, column=0)
        self.assertEqual(cell['global_return_index'], 3)
        self.assertEqual([q['pointer'] for q in cell['price_endpoints']], ['/quote_rows/3','/quote_rows/4'])
        cell['price_endpoints'][0]['original_quote']['reasons'].clear()
        self.assertEqual(column['original_channel']['quote_rows'][3]['reasons'], ['original'])
        for kwargs in (dict(window_ordinal=True,row=0,column=0), dict(window_ordinal=0,row=126,column=0),
                       dict(window_ordinal=0,row=0,column=-1)):
            with self.assertRaises(ValueError):
                bank.get_training_cell(data, **kwargs)


class RealWholeBankSnapshot(unittest.TestCase):
    def test_once_real_bank_full_756756_coordinate_comparison(self):
        destination = os.environ.get('FULL_POOL_BANK_SNAPSHOT_DIRECTORY')
        self.assertIsNotNone(destination, 'Explicit create-only evidence directory required')
        out = Path(destination)
        self.assertTrue(out.is_dir())
        # One fresh full77 source reader call. No true77 moments and no raw replay elsewhere.
        with patch.object(bank, '_load_fixed', wraps=bank._load_fixed) as loads:
            saved = bank.read_source_bound_training_bank()
        self.assertEqual(loads.call_count, 2)  # fixed reader and pure helper, not two reader runs
        facts = saved['facts']
        snapshot = json.dumps(facts, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',',':')).encode()
        with (out / 'facts.json').open('xb') as stream: stream.write(snapshot)
        self.assertEqual(facts['work']['source_reader_calls'], 1)
        self.assertEqual(facts['coverage']['unique_numeric_ready_matrices'], 12)
        self.assertEqual(facts['work']['spent'], 0)
        self.assertTrue(all(v is False for v in facts['permissions'].values()))
        self.assertEqual(len(facts['source_facts']['source_checks']), 10)
        self.assertIsNone(facts['qualified_inventory'])
        self.assertTrue(all(item['moments'] is None for item in facts['unique_training_matrices']))
        compared = tokens = accessor_checks = 0
        for ci, col in enumerate(facts['source_columns']):
            p = Path(col['source_reference']['path']); raw = p.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), col['source_reference']['sha256'])
            original = json.loads(raw, parse_float=Decimal)
            def faithful(value):
                if isinstance(value, Decimal): return str(value)
                if isinstance(value, list): return [faithful(x) for x in value]
                if isinstance(value, dict): return {k:faithful(v) for k,v in value.items()}
                return value
            self.assertEqual(col['original_channel'], faithful(original))
            for token in col['original_numeric_tokens'].values():
                self.assertEqual(raw[token['utf8_byte_start']:token['utf8_byte_stop']].decode('utf-8'), token['original_lexeme'])
                tokens += 1
            for wi, window in enumerate(facts['windows']):
                matrix = facts['unique_training_matrices'][window['unique_matrix_index']]['matrix']
                self.assertEqual(matrix['ordered_security_ids'][ci], col['coordinate']['security_id'])
                for ri in range(126):
                    g = window['training_start'] + ri
                    expected = original['return_rows'][g]
                    self.assertEqual(matrix['cells'][ri][ci], expected['split_only_return_exact'])
                    self.assertEqual(matrix['training_dates'][ri], expected['session'])
                    self.assertEqual(col['original_channel']['return_rows'][g], faithful(expected))
                    self.assertEqual(col['original_channel']['quote_rows'][g], faithful(original['quote_rows'][g]))
                    self.assertEqual(col['original_channel']['quote_rows'][g+1], faithful(original['quote_rows'][g+1]))
                    compared += 1
                for ri in (0,125):
                    cell = bank.get_training_cell(facts, window_ordinal=wi, row=ri, column=ci)
                    self.assertEqual(cell['global_return_index'], window['training_start']+ri)
                    self.assertEqual(cell['exact'], matrix['cells'][ri][ci])
                    accessor_checks += 1
        self.assertEqual(compared, 756756)
        guard = saved['final_guard']()
        # Mutation of detached facts must not mutate private guard baselines.
        original_permissions = deepcopy(facts['permissions'])
        facts['permissions'].clear()
        detached_guard = saved['final_guard']()
        facts['permissions'] = original_permissions
        evidence = dict(status='PASS_SINGLE_REAL_BANK_MATRIX_ONLY_NO_MOMENTS', snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
                        snapshot_bytes=len(snapshot), coordinate_comparisons=compared,
                        source_numeric_tokens_checked=tokens, detached_accessor_checks=accessor_checks,
                        source_reader_calls=1, true77_means_or_covariance_computed=False,
                        guard=guard, guard_after_detached_facts_mutation=detached_guard,
                        coverage=facts['coverage'], bank_work=facts['work'],
                        source_order=[dict(coordinate=c['coordinate'],reference=c['source_reference']) for c in facts['source_columns']],
                        excluded_from_snapshot='final_guard callable; saved only complete returned facts layer')
        with (out / 'real_bank_evidence.json').open('x', encoding='utf-8') as stream:
            json.dump(evidence, stream, ensure_ascii=True, indent=2)
