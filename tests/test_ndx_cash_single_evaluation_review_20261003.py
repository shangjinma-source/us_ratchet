"""Bounded synthetic review; no actual preparation/cache loading."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import ndx_cash_topup_neighbor_single_evaluation_20261003 as adapter
from test_ndx_cash_topup_neighbor_single_evaluation_20261003 import fixture


class Review(unittest.TestCase):
    def test_rehashed_cache_cannot_replace_sealed_preparation_before_reads(self):
        refs = {key: adapter.reference(path, h) for key, (path, h) in adapter.BOUND.items()}
        sources = adapter.source_map()
        sources.update({r['path']: r['sha256'] for r in refs.values()})
        common = dict(references=refs, preparation={'rows': []}, source_hashes=sources)
        common['metadata_sha256'] = adapter.digest(common)
        with patch.object(adapter, 'guard'), patch.object(adapter, 'load_reference') as read:
            with self.assertRaises(ValueError):
                adapter.load_task(common, 0, 0, 0, 'a' * 64)
            read.assert_not_called()

    def test_original_target_stock_l1_exact_and_one_explicit_plan(self):
        prepared, task = fixture()
        before = deepcopy((prepared, task))
        evaluate = adapter.fresh_evaluator()
        args = adapter.evaluation_arguments(prepared, task)
        result = evaluate(**args)
        plan = result['branches'][0]['evaluated_plans'][0]
        detail = adapter.inspect_return(prepared, task, result)
        values = [Fraction(10) * (10 + task['identity']['buy_shares'][s]) for s in 'ABCD']
        distance = sum(abs(v / sum(values) - Fraction(1, 4)) for v in values)
        score = detail['original_target_stock_weight_l1']['distance']
        self.assertEqual(Fraction(score['numerator'], score['denominator']), distance)
        self.assertEqual(plan['buy_shares'], task['identity']['buy_shares'])
        self.assertEqual(result['kernel_cartesian_search_evaluation_count'], 0)
        self.assertEqual((prepared, task), before)

    def test_bad_origin_bool_shares_and_returned_count_rejected(self):
        prepared, task = fixture()
        for mode in ('buy-bool', 'duplicate-move', 'seed-pointer'):
            altered = deepcopy(task)
            if mode == 'buy-bool':
                altered['identity']['buy_shares']['A'] = False
                altered['task_id'] = adapter.digest(altered['identity'])
            elif mode == 'duplicate-move':
                altered['first_origin']['moves'] *= 2
            else:
                altered['first_origin']['seed_reference']['json_pointer'] = '/rows/other'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                adapter.validate_task(prepared, altered, altered['task_id'])
        result = adapter.fresh_evaluator()(**adapter.evaluation_arguments(prepared, task))
        result['evaluated_count'] = True
        with self.assertRaises(ValueError):
            adapter.inspect_return(prepared, task, result)

    def test_unknown_return_raw_is_saved_once_and_never_retry(self):
        prepared, task = fixture()
        state = dict(prepared=prepared, task=task, contract_reference={'path':'c','sha256':'c'*64}, task_reference={'path':'s','sha256':'d'*64}, source_hashes={})
        numerical = Mock(return_value=None)
        with tempfile.TemporaryDirectory() as tmp, patch.object(adapter, 'OUTPUT', Path(tmp)), patch.object(adapter, 'load_task', return_value=state), patch.object(adapter, 'guard'), patch.object(adapter, 'fresh_evaluator', return_value=numerical):
            malicious = Mock(side_effect=AssertionError('Caller cannot replace numerical evaluator'))
            result = adapter.run(0, 0, 0, expected_task_id=task['task_id'], common={'references': {}, 'evaluator': malicious}, execute=True)
            post = adapter.decode(Path(result['path']).read_bytes())
            raw = adapter.decode((Path(result['path']).parent / 'raw.json').read_bytes())
            self.assertEqual(post['outcome'], 'VALIDATION_FAILURE')
            self.assertIsNone(raw['result'])
            self.assertEqual(raw['explicit_evaluator_call_attempt_count'], 1)
            numerical.assert_called_once()
            malicious.assert_not_called()
            with self.assertRaises(ValueError):
                adapter.run(0, 0, 0, expected_task_id=task['task_id'], common={}, execute=True)


if __name__ == '__main__':
    unittest.main()
