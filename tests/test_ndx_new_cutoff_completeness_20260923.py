"""Sealed JSON and in-memory counterexamples only; no raw auditor or publication."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_completeness_20260923 as m


class CompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {role: json.loads((m.BASE / relative).read_bytes()) for role, (relative, digest) in m.BOUND.items()}

    def test_sealed_numeric_coverage_does_not_admit_training(self):
        result = m.assemble(**self.docs)
        self.assertEqual(result['candidate_cutoff'], '2026-09-21')
        self.assertEqual(result['observed_reference_calendar_127'][0], '2026-03-20')
        self.assertEqual(result['observed_volume_calendar_63'][0], '2026-06-23')
        self.assertEqual(result['summary'], dict(ohlc_127_complete_channels=100, volume_63_complete_channels=102))
        rows = {row['ticker']: row for row in result['rows']}
        self.assertEqual(rows['SPCX']['ohlc_127']['complete_day_count'], 69)
        self.assertEqual(rows['HONA']['ohlc_127']['complete_day_count'], 68)
        self.assertEqual(len(result['rows']), 104)
        self.assertEqual(rows['QQQ']['status'], 'NOT_ATTEMPTED')
        self.assertTrue(all(result[key] is False for key in m.FLAGS))

    def test_aapl_null_cannot_compress_reference_dates(self):
        docs = deepcopy(self.docs)
        bar = next(row for row in docs['readback']['rows'] if row['ticker'] == 'AAPL')['observation']['rows'][-10]
        bar['raw_provider_fields']['close'] = None
        bar['missing_fields'].append('close')
        with self.assertRaisesRegex(ValueError, 'AAPL raw date sequence'):
            m.assemble(**docs)

    def test_other_channel_missing_date_and_volume_remain_separate(self):
        docs = deepcopy(self.docs)
        bars = docs['readback']['rows'][1]['observation']['rows']
        missing = bars.pop(-10)['new_york_date']
        bars[-8]['raw_provider_fields']['volume'] = None
        bars[-8]['missing_fields'].append('volume')
        result = m.assemble(**docs)['rows'][1]
        self.assertIn(missing, result['ohlc_127']['missing_dates'])
        self.assertEqual(result['ohlc_127']['complete_day_count'], 126)
        self.assertEqual(result['volume_63']['complete_day_count'], 61)
        self.assertEqual(result['return_126_use']['missing_pair_count'], 2)

    def test_bool_duplicate_scope_and_denominator_rejected(self):
        for attack in ('bool', 'duplicate', 'scope', 'denominator'):
            docs = deepcopy(self.docs)
            obs = docs['readback']['rows'][0]['observation']
            if attack == 'bool': obs['rows'][0]['raw_provider_fields']['volume'] = True
            elif attack == 'duplicate': obs['rows'].append(deepcopy(obs['rows'][-1]))
            elif attack == 'scope': obs['promotion_allowed'] = True
            else: docs['plan']['queue'].pop()
            with self.subTest(attack=attack), self.assertRaises(ValueError): m.assemble(**docs)

    def test_source_drift_and_fixed_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source'
            path.write_text('a')
            sources = {str(path): m.sha(path)}
            path.write_text('b')
            with self.assertRaisesRegex(ValueError, 'Bound source changed'): m.guard(sources)
            with self.assertRaisesRegex(ValueError, 'fixed namespace'): m.publish({}, Path(directory) / 'other.json')
            target = Path(directory) / 'attempt/manifest.json'
            target.parent.mkdir()
            with patch.object(m, 'OUTPUT', target), self.assertRaises(ValueError): m.publish({}, target)


if __name__ == '__main__':
    unittest.main()
