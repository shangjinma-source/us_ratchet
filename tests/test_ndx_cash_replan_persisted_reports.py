"""All four explicitly bound recovery experiments must exist and pass audit."""
from pathlib import Path
import unittest

from ndx_cash_replan_persisted_audit import audit_replan


REPORT_ROOT = Path(__file__).resolve().parents[1] / 'data/cache/research/ndx_joint_weight_experiment_v2'
EXPECTED_REPORTS = {
    0: '0323c411c530b02d6967038b466d7ab59f9230460492407613fedc46ad9863fa',
    1: 'f29e52392faa56546fd687a4c4a8607fcf6e97a16279c30fa124bcc0e9d87aa9',
    2: '85bdf8fb8fc05751f37769b50dbc2d6a08e00b548de78069a0dc618348495a6e',
    3: 'ab2bc591745901df5052dffe934b8e20b42700feeea7cfff077d09b240483da4',
}


class CashReplanPersistedReportsTests(unittest.TestCase):
    def test_all_four_explicitly_bound_reports(self):
        self.assertEqual(set(EXPECTED_REPORTS), {0, 1, 2, 3})
        for case_index, digest in EXPECTED_REPORTS.items():
            with self.subTest(case_index=case_index):
                result = audit_replan(REPORT_ROOT / f'cash_replan_case{case_index}_20260911.json', digest)
                self.assertTrue(result['arithmetic_and_lineage_verified'])
                for role in ('candidate', 'incumbent'):
                    self.assertEqual(result['summary'][role]['daily_rows'], 378 if case_index == 3 else 357)


if __name__ == '__main__':
    unittest.main()
