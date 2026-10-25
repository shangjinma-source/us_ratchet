from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from backtest import quantity_anchor_coupled_completion as completion
from backtest import quantity_anchor_coupled_continuation as continuation
from backtest import quantity_continuous_anchor_bound as continuous
from test_quantity_anchor_coupled_completion import fixture


def setup():
    sources, optimum = fixture(seed={'B': 2})
    original = completion.build(**sources, node_budget=1)
    raw = continuous.canonical(original)
    return dict(origin_raw=raw, expected_origin_sha256=sha256(raw).hexdigest(), **sources), optimum


def saved(certificate):
    raw = continuous.canonical(certificate)
    return raw, sha256(raw).hexdigest()


class ContinuationTests(unittest.TestCase):
    def test_single_node_segments_match_uninterrupted_ledger_and_oracle(self):
        sources, optimum = setup()
        original = json.loads(sources['origin_raw'])
        base_sources = {key: value for key, value in sources.items() if key not in ('origin_raw', 'expected_origin_sha256')}
        uninterrupted = completion.build(**base_sources)['coupled']
        history = []
        records = deepcopy(original['coupled']['ledger'])
        point_count = len(original['coupled']['points'])
        for _ in range(20):
            before = deepcopy(sources)
            segment = continuation.build(**sources, history=history, node_budget=1, objective_budget=1)
            continuation.verify(segment, **sources, history=history)
            self.assertEqual(sources, before)
            self.assertLessEqual(segment['delta']['visited_nodes'], 1)
            for record in deepcopy(segment['delta']['ledger']):
                if 'point_index' in record:
                    record['point_index'] += point_count
                records.append(record)
            point_count += len(segment['delta']['points'])
            history.append(saved(segment))
            if segment['objective_value_covered']:
                break
        self.assertTrue(segment['objective_value_covered'])
        self.assertEqual(segment['lower_product'], str(optimum))
        self.assertEqual(records, uninterrupted['ledger'])
        self.assertEqual(segment['delta']['selected_candidate'], uninterrupted['selected_candidate'])
        self.assertEqual(len({tuple(row['prefix']) for row in records}), len(records))
        with self.assertRaisesRegex(ValueError, 'ALREADY_COMPLETE'):
            continuation.build(**sources, history=history)

    def test_new_search_does_not_evaluate_completed_parent_points(self):
        sources, _ = setup()
        # _advance is the new-search stage; public build additionally verifies prior work.
        origin = json.loads(sources['origin_raw'])
        problem = continuation.core.prepare(**json.loads(sources['base_raw'])['inputs'])
        state = origin['coupled']
        calls = []
        objective = continuation.core.objective
        def track(problem, quantities):
            calls.append(deepcopy(quantities))
            return objective(problem, quantities)
        with patch.object(continuation.core, 'objective', side_effect=track):
            while not state['domain_complete']:
                delta = continuation._advance(state, origin['loss'], problem, 1, 1)
                state = continuation._merge(state, delta)
        self.assertEqual(len(calls), len({tuple(sorted(point.items())) for point in calls}))
        self.assertGreater(len(calls), 0)

    def test_changed_history_binding_frontier_and_claim_rejected(self):
        sources, _ = setup()
        first = continuation.build(**sources, node_budget=1)
        raw, digest = saved(first)
        with self.assertRaisesRegex(ValueError, 'HISTORY_RAW_CHANGED'):
            continuation.build(**sources, history=[(raw, '0' * 64)])
        for key, value in [('parent_sha256', '0' * 64), ('segment_index', 9),
                           ('objective_value_covered', True), ('lower_product', '999')]:
            bad = deepcopy(first)
            bad[key] = value
            with self.assertRaisesRegex(ValueError, 'HISTORY_SEGMENT_CHANGED'):
                continuation.build(**sources, history=[saved(bad)])
        bad = deepcopy(first)
        bad['delta']['unsearched_frontier'] = []
        with self.assertRaisesRegex(ValueError, 'HISTORY_SEGMENT_CHANGED'):
            continuation.build(**sources, history=[saved(bad)])
        with self.assertRaises(ValueError):
            continuation.build(**sources, history=[(raw, digest), (raw, digest)])

    def test_budgets_sources_and_final_certificate_tamper(self):
        sources, _ = setup()
        for budgets in [dict(node_budget=0), dict(node_budget=True), dict(node_budget=5001),
                        dict(objective_budget=0), dict(objective_budget=501)]:
            with self.assertRaisesRegex(ValueError, 'POSITIVE_FIXED_SEGMENT_BUDGET_REQUIRED'):
                continuation.build(**sources, **budgets)
        with self.assertRaisesRegex(ValueError, 'ORIGIN_RAW_CHANGED'):
            continuation.build(**dict(sources, expected_origin_sha256='0' * 64))
        result = continuation.build(**sources)
        result['upper_product'] = '0'
        with self.assertRaisesRegex(ValueError, 'CONTINUATION_CHANGED'):
            continuation.verify(result, **sources)


if __name__ == '__main__':
    unittest.main()
