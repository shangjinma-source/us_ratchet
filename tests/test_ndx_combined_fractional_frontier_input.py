"""Independent wrapper regressions; synthetic recovery never runs training."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_combined_fractional_frontier as wrapper
import test_ndx_combined_fractional_summary as summary_fixture


class FrontierInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.date = summary_fixture.SummaryTests().prepared()
        for path in (self.root / 'equal_base_20240201_20260911.json',
                     self.root / 'ndx_non_equal_base_fractional_v1' / 'synthetic' / 'context.json'):
            digest = self.write(path, {'fixture': 'SYNTHETIC'})
            self.date['source_hashes'][str(path)] = digest
        self.saved = wrapper.summaries.summarize(self.date)
        self.summary_path = self.root / 'summary.json'
        self.inventory_path = self.root / 'inventory.json'

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value, sort_keys=True).encode()
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def bind(self, duplicate=False):
        digest = self.write(self.summary_path, self.saved)
        row = dict(coordinate={key: self.saved['expected_date'][key] for key in wrapper.combined._KEYS},
                   path=str(self.summary_path), sha256=digest,
                   counts=deepcopy(self.saved['counts']), record_count=self.saved['record_count'])
        rows = [row, deepcopy(row)] if duplicate else [row]
        inventory = dict(schema='combined_summary_inventory_20260912', summaries=rows,
                         date_count=len(rows), record_count=sum(item['record_count'] for item in rows),
                         training_rerun=False, execution_performed=False,
                         point_in_time_verified=False, promotion_allowed=False)
        return self.write(self.inventory_path, inventory)

    def invoke(self, digest):
        return wrapper.run_date(inventory_path=self.inventory_path,
                                inventory_sha256=digest, selection_date='2024-02-01')

    def test_rebuilt_records_bound_and_unknown_scope_preserved(self):
        digest = self.bind()
        with patch.object(wrapper.combined, 'prepare_combined_date', return_value=self.date) as recover, \
                patch.object(wrapper.frontier, 'analyze_combined_date', return_value={'synthetic': True}) as analyze:
            result = self.invoke(digest)
        recover.assert_called_once()
        analyze.assert_called_once_with(self.date)
        self.assertEqual(result['records_sha256'], self.saved['records_sha256'])
        self.assertFalse(result['promotion_allowed'])
        self.assertTrue(all(row['eligibility']['technology_scope_passed'] is None
                            for row in self.date['records']))

    def test_correctly_rehashed_fake_record_digest_rejected(self):
        self.saved['records_sha256'] = '0' * 64
        digest = self.bind()
        with patch.object(wrapper.combined, 'prepare_combined_date', return_value=self.date), \
                patch.object(wrapper.frontier, 'analyze_combined_date') as analyze:
            with self.assertRaisesRegex(ValueError, 'Rebuilt complete records differ'):
                self.invoke(digest)
            analyze.assert_not_called()

    def test_consistently_inflated_summary_and_inventory_rejected(self):
        self.saved['counts']['EQUAL_WEIGHT_BASE'] = {
            key: value + 1 for key, value in self.saved['counts']['EQUAL_WEIGHT_BASE'].items()}
        self.saved['expected_date']['expected_task_count'] += 1
        self.saved['record_count'] += 1
        digest = self.bind()
        with patch.object(wrapper.combined, 'prepare_combined_date', return_value=self.date), \
                patch.object(wrapper.frontier, 'analyze_combined_date') as analyze:
            with self.assertRaisesRegex(ValueError, 'Rebuilt complete records differ'):
                self.invoke(digest)
            analyze.assert_not_called()

    def test_duplicate_coordinate_with_consistent_inventory_totals_rejected(self):
        digest = self.bind(duplicate=True)
        with patch.object(wrapper.combined, 'prepare_combined_date') as recover:
            with self.assertRaisesRegex(ValueError, 'Inventory denominator differs'):
                self.invoke(digest)
            recover.assert_not_called()

    def test_source_drift_during_analysis_rejected(self):
        digest = self.bind()

        def mutate_source(date):
            (self.root / 'equal_base_20240201_20260911.json').write_text('changed')
            return {'synthetic': True}

        with patch.object(wrapper.combined, 'prepare_combined_date', return_value=self.date), \
                patch.object(wrapper.frontier, 'analyze_combined_date', side_effect=mutate_source):
            with self.assertRaisesRegex(ValueError, 'Source closure differs'):
                self.invoke(digest)


if __name__ == '__main__':
    unittest.main()
