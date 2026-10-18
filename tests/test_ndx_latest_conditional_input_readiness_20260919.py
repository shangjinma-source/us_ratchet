from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import yaml
from scripts import ndx_latest_conditional_input_readiness_20260919 as m


class Tests(unittest.TestCase):
    def requirements(self):
        return m.requirements(*(yaml.safe_load((m.ROOT/m.SNAPSHOT_FILES[k]).read_bytes()) for k in ('scope','search','generator')))

    def test_exact_formal_lengths_and_505_not_admission(self):
        r=self.requirements()
        self.assertEqual(r['fit_adjacent_price_rows'],127)
        self.assertEqual(r['minimum_snapshot_adjusted_price_rows'],252)
        self.assertEqual(r['desired_training_price_rows'],505)
        self.assertFalse(r['desired_505_is_hard_admission_threshold'])
        self.assertFalse(r['original_track_filter_reused'])

    def test_missing_predecessor_not_hidden_by_126_quote_rows(self):
        reference=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(505)]
        r=m.assess_calendar(reference=reference,available=reference[-126:],requirements=self.requirements())
        self.assertEqual(r['fit_return_pairs_with_both_prices'],125)
        self.assertEqual(r['fit_return_date_pairs'][0]['missing_prices'],[reference[-127]])
        self.assertFalse(r['windows']['latest_fit_adjacent_prices']['date_coverage_complete'])

    def test_one_interior_missing_date_breaks_two_return_pairs(self):
        reference=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(505)]
        available=deepcopy(reference);available.remove(reference[-60])
        r=m.assess_calendar(reference=reference,available=available,requirements=self.requirements())
        self.assertEqual(r['fit_return_pairs_with_both_prices'],124)
        self.assertTrue(r['quote_covers_latest_cutoff'])

    def test_actual_readonly_snapshot_and_matrix_no_fit(self):
        with TemporaryDirectory() as folder:
            path,h=m.sealed_snapshot(Path(folder)/'observed_inputs');report=m.build(path,h)
            self.assertEqual(len(report['rows']),101)
            rows={r['ticker']:r for r in report['rows']}
            self.assertEqual(rows['HONA']['coverage']['fit_return_pairs_with_both_prices'],56)
            self.assertFalse(rows['HON']['legal_fit_input_ready'])
            self.assertEqual(rows['CMCSA']['conditional_available_row_count'],0)
            self.assertFalse(report['fit_performed'])
            nav=report['dual_benchmark_readiness']['target_012922']
            self.assertFalse(nav['publication_time_at_US_cutoff_verified'])
            self.assertEqual(nav['latest_nav_date_at_or_before_cutoff'],'2026-09-17')
            control=report['dual_benchmark_readiness']['original8']
            self.assertEqual(control['tsm_old_raw_reference']['latest_completed_raw_date'],'2026-09-10')
            self.assertTrue(control['tsm_cache_not_substituted_for_verified_nominal_or_adjusted_input'])


if __name__=='__main__':unittest.main()
