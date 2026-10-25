from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import unittest

from backtest import quantity_anchor_partition_completion as partition
from backtest import quantity_anchor_coupled_completion as coupled
from backtest import quantity_continuous_anchor_bound as continuous
from test_quantity_anchor_coupled_completion import fixture


def saved(value):
    raw = continuous.canonical(value)
    return raw, sha256(raw).hexdigest()


class PartitionCompletionTests(unittest.TestCase):
    def test_unsupported_geometries_close_at_independent_oracle(self):
        for options in [dict(symmetric=True), dict(cash='11/2')]:
            sources, optimum = fixture(**options, seed={})
            admission = coupled.build(**sources)
            self.assertEqual(admission['status'], 'UNRESOLVED_UNSUPPORTED_COUPLED_GEOMETRY')
            result = partition.build(**sources)
            self.assertTrue(result['objective_value_covered'])
            self.assertEqual(F(result['lower_product']), optimum)
            self.assertEqual(result['lower_product'], result['upper_product'])
            partition.verify(result, **sources)

    def test_single_node_segments_match_full_partition(self):
        sources, optimum = fixture(cash='11/2', seed={})
        full = partition.build(**sources)
        history, ledger = [], []
        for _ in range(99):
            result = partition.build(**sources, history=history, node_budget=1)
            partition.verify(result, **sources, history=history)
            ledger.extend(result['ledger'])
            history.append(saved(result))
            if result['objective_value_covered']:
                break
        self.assertTrue(result['objective_value_covered'])
        self.assertEqual(ledger, full['ledger'])
        self.assertEqual(F(result['lower_product']), optimum)
        self.assertEqual(len({row['id'] for row in ledger}), len(ledger))
        with self.assertRaisesRegex(ValueError, 'PARTITION_ALREADY_COMPLETE'):
            partition.build(**sources, history=history)

    def test_pending_bounds_and_partition_children_are_complete(self):
        sources, optimum = fixture(cash='11/2', seed={})
        result = partition.build(**sources, node_budget=1)
        self.assertFalse(result['objective_value_covered'])
        self.assertLessEqual(F(result['lower_product']), optimum)
        self.assertGreaterEqual(F(result['upper_product']), optimum)
        record = result['ledger'][0]
        self.assertEqual(record['terminal'], 'SPLIT')
        axis = record['axis']
        high, low = result['pending']
        self.assertEqual(low['box'][axis][0], record['box'][axis][0])
        self.assertEqual(low['box'][axis][1] + 1, high['box'][axis][0])
        self.assertEqual(high['box'][axis][1], record['box'][axis][1])

    def test_tampered_history_and_bad_budgets_rejected(self):
        sources, _ = fixture(cash='11/2', seed={})
        first = partition.build(**sources, node_budget=1)
        for key, value in [('pending', []), ('selected', {'A': 999}), ('parent_sha256', '0'*64),
                           ('objective_value_covered', True), ('segment_index', 2)]:
            bad = deepcopy(first)
            bad[key] = value
            with self.assertRaisesRegex(ValueError, 'PARTITION_SEGMENT_CHANGED'):
                partition.build(**sources, history=[saved(bad)])
        for budget in [0, True, 2001]:
            with self.assertRaisesRegex(ValueError, 'PARTITION_NODE_CAP_REQUIRED'):
                partition.build(**sources, node_budget=budget)
        bad = deepcopy(first)
        bad['upper_product'] = '0'
        with self.assertRaisesRegex(ValueError, 'PARTITION_CERTIFICATE_CHANGED'):
            partition.verify(bad, **sources)


if __name__ == '__main__':
    unittest.main()
