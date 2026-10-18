"""Small exhaustive local-domain oracle; no saved research consumption."""
import itertools
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_cash_topup_neighbor_preparation_research as core
from scripts import ndx_cash_topup_neighbor_preparation_20261003 as wrapper
from test_ndx_cash_topup_neighbor_preparation_research import fixture


class Review(unittest.TestCase):
    def test_three_coordinate_exhaustive_domain_and_attempt_partition(self):
        args = fixture()
        row, old = args['input_row'], args['previous_row']
        row['target_weights']['C'] = '0'
        row['securities']['C'] = {'issuer_id': 'I'}  # No issuer filtering here.
        row['execution_prices']['C'] = '7'
        old['input_row'] = deepcopy(row)
        old['domain'] = {'conditional_research_buy_ids': ['A', 'B', 'C'], 'buy_limits': dict.fromkeys('ABC', 2)}
        vectors = [(1, 1, 1), (2, 1, 0), (0, 0, 0)]
        branch = old['evaluation']['branches'][0]
        branch['evaluated_plans'] = [dict(buy_shares=dict(zip('ABC', vector)), feasible=i < 2) for i, vector in enumerate(vectors)]
        before = deepcopy(args)
        prepared = core.prepare_scenario(**args)
        stats = {}
        actual = list(core.iter_neighbors(prepared, stats))
        expected = set()
        for seed in vectors[:2]:
            for point in itertools.product(range(3), repeat=3):
                differences = [abs(a-b) for a, b in zip(point, seed)]
                if max(differences) == 1 and 1 <= sum(d != 0 for d in differences) <= 2:
                    expected.add(point)
        expected.difference_update(vectors)
        self.assertEqual({tuple(t['identity']['buy_shares'][s] for s in 'ABC') for t in actual}, expected)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(stats['processed_move_count'], 36)
        self.assertEqual(sum(stats[k] for k in ('boundary_rejected_count', 'old_point_excluded_count', 'duplicate_new_point_count', 'new_candidate_count')), 36)
        self.assertEqual(args, before)
        self.assertTrue(all(t['issuer_eligibility_verified'] is False for t in actual))

    def test_no_feasible_seeds_empty_and_invalid_suffix_still_rejected(self):
        args = fixture()
        plans = args['previous_row']['evaluation']['branches'][0]['evaluated_plans']
        for p in plans:
            p['feasible'] = False
        stats = {}
        self.assertEqual(list(core.iter_neighbors(core.prepare_scenario(**args), stats)), [])
        self.assertEqual(stats['raw_move_attempt_count'], 0)
        plans[-1]['buy_shares']['A'] = True
        with self.assertRaises(ValueError):
            core.prepare_scenario(**args)

    def test_stream_hashes_offsets_and_fail_closed_without_source_reads(self):
        prepared = core.prepare_scenario(**fixture())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(wrapper, 'SHARD_SIZE', 3):
                result = wrapper.write_scenario(prepared, core, root / 'scenario')
            cursor = 0
            tasks = []
            for shard in result['shards']:
                blob = Path(shard['path']).read_bytes()
                saved = [json.loads(line) for line in blob.splitlines()]
                self.assertEqual(wrapper.sha(blob), shard['sha256'])
                self.assertEqual(shard['start'], cursor)
                cursor += len(saved)
                self.assertEqual(shard['stop'], cursor)
                tasks.extend(saved)
            self.assertEqual([t['scenario_candidate_ordinal'] for t in tasks], list(range(cursor)))
            with patch.object(wrapper, 'OUTPUT', root), patch.object(wrapper, 'load') as load:
                with self.assertRaises(ValueError):
                    wrapper.run(execute=True)
                load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
