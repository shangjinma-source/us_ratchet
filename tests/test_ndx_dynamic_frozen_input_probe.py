"""Bounded real-capture contract tests; never run the economic replay."""
import unittest
from unittest.mock import patch

from scripts import ndx_dynamic_frozen_input_probe as probe


class DynamicInputTests(unittest.TestCase):
    def test_explicit_lane_required(self):
        for value in (None, '', ' x ', 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.prepare_lane(value)

    def test_loaded_source_drift_rejected(self):
        with patch.dict(probe._LOADED, {str(probe.SOURCE): '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                probe.prepare_lane('anything')

    def test_real_dynamic_calendar_and_scope(self):
        prepared = probe.prepare_lane(
            'ndx_cardinality_real_runner_p2_exact_v3/strict_technology/RETURN')
        summary = prepared['summary']
        self.assertEqual(summary['k_path'], [4,4,4,4,4,8,6,6,4,4,4,4,5,5])
        self.assertEqual(summary['session_count'], 294)
        self.assertEqual(summary['captured_lane_count'], 14)
        self.assertTrue(prepared['opens'].index.equals(prepared['closes'].index))
        for row in prepared['schedule']:
            calendar = prepared['closes'].index
            self.assertEqual(calendar.get_loc(row['execution_date']),
                             calendar.get_loc(row['decision_date']) + 1)
        self.assertFalse(summary['promotion_allowed'])
        self.assertFalse(summary['full_pit_universe_verified'])
        self.assertFalse(summary['economic_replay_performed'])
        self.assertFalse(summary['fixed_cardinality_claim'])
        self.assertTrue(summary['contains_bkr'])
        self.assertEqual(summary['aliases_by_security'], {})


if __name__ == '__main__':
    unittest.main()
