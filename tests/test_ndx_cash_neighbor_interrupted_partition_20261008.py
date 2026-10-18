import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/ndx_cash_neighbor_interrupted_partition_20261008.py'
spec = importlib.util.spec_from_file_location('partition', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PartitionTests(unittest.TestCase):
    def scan(self, statuses):
        return dict(tail=None, tasks=[dict(task_id=str(i), task_position=i, status=status) for i, status in enumerate(statuses)], undispatched_task_ids=[str(i) for i in range(len(statuses), 4)])

    def test_raw_saved_is_not_reclassified(self):
        result = m.classify(['0','1','2','3'], self.scan(['INFEASIBLE','RAW_SAVED_POSTCHECK_MISSING']))
        self.assertEqual(result['RAW_SAVED_POSTCHECK_MISSING'], ['1'])
        self.assertEqual(result['UNDISPATCHED'], ['2','3'])
        self.assertEqual(result['FEASIBLE'], [])

    def test_unknown_dispatch_is_not_retryable(self):
        result = m.classify(['0','1','2','3'], self.scan(['EXTERNALLY_REFERENCED','UNRESOLVED_DISPATCH']))
        self.assertEqual(result['UNRESOLVED_DISPATCH'], ['1'])
        self.assertNotIn('1', result['UNDISPATCHED'])

    def test_gap_wrong_order_and_partial_bytes_rejected(self):
        cases = []
        value = self.scan(['FEASIBLE']);value['undispatched_task_ids'] = ['2','3'];cases.append(value)
        value = self.scan(['FEASIBLE']);value['tasks'][0]['task_id'] = '1';cases.append(value)
        value = self.scan(['FEASIBLE']);value['tail'] = {'byte_count':1};cases.append(value)
        value = self.scan(['UNRESOLVED_DISPATCH','FEASIBLE']);cases.append(value)
        value = self.scan(['FEASIBLE']);value['tasks'][0]['task_position'] = False;cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.classify(['0','1','2','3'], value)

    def test_economic_failure_not_silently_swallowed(self):
        with self.assertRaises(ValueError):
            m.classify(['0','1','2','3'], self.scan(['VALIDATION_FAILURE']))

    def test_publication_requires_explicit_action_before_io(self):
        with patch.object(m, 'inspect', side_effect=AssertionError('Unexpected inspection')):
            with self.assertRaises(ValueError):
                m.publish()

if __name__ == '__main__':
    unittest.main()
