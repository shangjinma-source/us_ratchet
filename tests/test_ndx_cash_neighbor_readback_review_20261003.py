"""Independent bounded counterexamples for saved-neighborhood verification."""
import ast
import itertools
import unittest
from copy import deepcopy
from pathlib import Path
from scripts import ndx_cash_topup_neighbor_preparation_independent_readback_20261003 as reader
from test_ndx_cash_topup_neighbor_preparation_research import fixture
from test_ndx_cash_topup_neighbor_preparation_independent_readback_20261003 import shard_fixture


class Review(unittest.TestCase):
    def test_complete_three_sid_grid_includes_nonselected_seed_and_zero_target(self):
        args = fixture()
        row, old = args['input_row'], args['previous_row']
        row['target_weights']['C'] = '0'
        row['execution_prices']['C'] = '8'
        row['securities']['C'] = {'issuer_id': 'I'}
        old['input_row'] = deepcopy(row)
        old['domain'] = {'conditional_research_buy_ids': list('ABC'), 'buy_limits': dict.fromkeys('ABC', 2)}
        vectors = [(1, 1, 1), (2, 2, 2), (0, 0, 0)]
        old['evaluation']['branches'][0]['evaluated_plans'] = [dict(buy_shares=dict(zip('ABC', v)), feasible=i < 2) for i, v in enumerate(vectors)]
        prepared = reader.reconstruct_contract(row, old, args['input_reference'], args['previous_reference'])
        stats = {}
        saved = list(reader.expected_tasks(prepared, stats))
        expected = {v for v in itertools.product(range(3), repeat=3) if any(max(abs(a-b) for a,b in zip(v,s)) == 1 and 1 <= sum(a != b for a,b in zip(v,s)) <= 2 for s in vectors[:2])} - set(vectors)
        self.assertEqual({tuple(t['identity']['buy_shares'][s] for s in 'ABC') for t in saved}, expected)
        self.assertEqual(len(saved), len(expected))
        self.assertEqual(stats['raw_move_attempt_count'], 36)
        self.assertEqual(stats['unprocessed_move_count'], 0)

    def test_rehashed_wrong_origin_canonical_bytes_and_boolean_counts_rejected(self):
        prepared, row, raw, folder = shard_fixture()
        for mode in ('origin', 'noncanonical', 'false-count', 'true-authority'):
            lines = raw.splitlines()
            changed = deepcopy(row)
            if mode == 'origin':
                task = reader.decode(lines[0])
                task['first_origin']['seed_reference']['json_pointer'] = '/rows/999'
                lines[0] = reader.enc(task)
            elif mode == 'noncanonical':
                lines[0] = b' ' + lines[0]
            elif mode == 'false-count':
                changed['statistics']['unprocessed_move_count'] = False
            else:
                changed['risk_evaluated'] = True
            blob = b'\n'.join(lines) + b'\n'
            changed['shards'][0]['sha256'] = reader.sha(blob)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                reader.verify_shards(prepared, changed, lambda ref: blob, folder)

    def test_producer_not_imported_or_executed_and_original_rows_not_rewritten(self):
        tree = ast.parse(Path(reader.__file__).read_text())
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('exec', 'compile', '__import__') for n in ast.walk(tree)))
        args = fixture()
        before = deepcopy(args)
        result = reader.reconstruct_contract(args['input_row'], args['previous_row'], args['input_reference'], args['previous_reference'])
        self.assertEqual(args, before)
        result['contract']['original_input_row']['gaps'].append('tamper')
        self.assertEqual(args, before)
        self.assertEqual(result['contract']['all_feasible_seed_indexes'], [0, 1])


if __name__ == '__main__':
    unittest.main()
