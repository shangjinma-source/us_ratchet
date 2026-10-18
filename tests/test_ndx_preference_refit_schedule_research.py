"""Adapter tests: real bound preference coordinate and no invented sessions."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import pandas as pd

from scripts import ndx_preference_refit_schedule_research as adapter


class PreferenceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(adapter._read(adapter.INVENTORY, adapter.INVENTORY_SHA))
        cls.descriptor = cls.inventory['reports'][-1]
        cls.report = json.loads(adapter._read(cls.descriptor['path'], cls.descriptor['sha256']))
        cls.prepared = adapter.equal_inputs.prepare_equal_base_date(**cls.descriptor['coordinate'])

    def test_real_latest_coordinate_and_original_parameters(self):
        period, audit = adapter._preference_decision(descriptor=self.descriptor,
                                                    report=self.report, prepared=self.prepared)
        self.assertEqual(period['decision_date'], '2024-05-31')
        self.assertEqual(period['execution_date'], '2024-06-03')
        self.assertEqual(period['cutoff'], period['decision_date'])
        self.assertEqual(set(item['ticker'] for item in period['selected'].values()), set(adapter.PREFERENCE))
        self.assertEqual(period['parameters'], {key: self.prepared['inputs']['contract'][key]
                                               for key in adapter.PARAMETERS})
        self.assertEqual(audit['reference']['technology_scope_passed'], None)
        self.assertEqual(period['returns'].index[-1], pd.Timestamp('2024-05-31'))

    def test_reference_replacement_and_duplicate_reference_rejected(self):
        changed = deepcopy(self.report)
        changed['analysis']['user_preference_references'][0]['job_id'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'job identity differs'):
            adapter._preference_decision(descriptor=self.descriptor, report=changed, prepared=self.prepared)
        changed = deepcopy(self.report)
        changed['analysis']['user_preference_references'] *= 2
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            adapter._preference_decision(descriptor=self.descriptor, report=changed, prepared=self.prepared)

    def test_restored_contract_drift_not_replaced_by_defaults(self):
        changed = deepcopy(self.prepared)
        changed['inputs']['contract']['max_single_weight'] = .99
        with self.assertRaisesRegex(ValueError, 'training semantics'):
            adapter._preference_decision(descriptor=self.descriptor, report=self.report, prepared=changed)

    def test_full_fifteen_date_denominator_and_duplicate_rejection(self):
        adapter._validate_inventory(self.inventory)
        for change in ('missing', 'duplicate'):
            inventory = deepcopy(self.inventory)
            if change == 'missing':
                inventory['reports'].pop()
                inventory['date_count'] -= 1
            else:
                inventory['reports'][-1] = deepcopy(inventory['reports'][-2])
            with self.subTest(change=change), self.assertRaises(ValueError):
                adapter._validate_inventory(inventory)

    def test_calendar_requires_observed_next_session_and_training_union(self):
        period = dict(decision_date='2024-03-28', cutoff='2024-03-28', execution_date='2024-04-01',
                      returns=pd.DataFrame({'A': [0.]}, index=pd.to_datetime(['2024-03-28'])))
        actual = {'QQQ': ['2024-03-28', '2024-04-01'], 'SPY': ['2024-03-28', '2024-04-01']}
        calendar, audit = adapter._build_calendar([period], actual)
        self.assertEqual(calendar, actual['QQQ'])
        self.assertEqual(audit['observed_tail_sessions'], ['2024-04-01'])
        fabricated = {key: ['2024-03-28', '2024-03-29', '2024-04-01'] for key in actual}
        with self.assertRaisesRegex(ValueError, 'not next observed'):
            adapter._build_calendar([period], fabricated)
        disagreement = dict(actual, SPY=['2024-03-28'])
        with self.assertRaisesRegex(ValueError, 'disagreement or missing boundary'):
            adapter._build_calendar([period], disagreement)
        missing = deepcopy(period)
        missing['returns'] = pd.DataFrame({'A': [0.]}, index=pd.to_datetime(['2024-03-27']))
        with self.assertRaisesRegex(ValueError, 'Training session union differs'):
            adapter._build_calendar([missing], actual)

    def test_frozen_observed_dates_cover_actual_final_execution(self):
        manifest = json.loads(adapter._read(adapter.CALENDAR_MANIFEST, adapter.CALENDAR_SHA))
        channels = {}
        for row in manifest['sources']:
            self.assertEqual(Path(row['frozen_path']).parent, adapter.CALENDAR_MANIFEST.parent)
            days = adapter._observed_dates(adapter._read(row['frozen_path'], row['frozen_sha256']))
            channels[row['ticker']] = [day for day in days if '2023-03-31' <= day <= '2024-06-03']
        self.assertEqual(channels['QQQ'], channels['SPY'])
        self.assertEqual(len(channels['QQQ']), 295)
        self.assertEqual(channels['QQQ'][-2:], ['2024-05-31', '2024-06-03'])
        with self.assertRaisesRegex(ValueError, 'Canonical observed'):
            adapter._observed_dates(b'Date,Date\n2024-01-01,2024-01-01\n')


if __name__ == '__main__':
    unittest.main()
