import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_combined_fractional_summary as summary
from test_ndx_combined_fractional_date import fixture


class SummaryTests(unittest.TestCase):
    def prepared(self):
        date = summary.combined._combine(**fixture(), policy_role='RETURN')
        for record in date['records']:
            for name in ('paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
                         'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
                         'return_p50_vs_012922','return_p10_vs_012922',
                         'max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922'):
                record['result'][name] = 0.
        source = Path(summary.encoding.__file__).resolve()
        date['source_hashes'] = dict(summary.combined._LOADED,
            **{str(source): hashlib.sha256(source.read_bytes()).hexdigest()})
        return date

    def test_unknown_scope_and_reference_not_admission(self):
        result = summary.summarize(self.prepared())
        self.assertEqual(len(result['roles']), 5)
        self.assertEqual(result['roles'][0]['status'], 'NO_ELIGIBLE_CANDIDATE')
        self.assertEqual(result['roles'][-1]['status'], 'SELECTED')
        self.assertFalse(result['promotion_allowed'])
        self.assertFalse(result['saved_weights_are_execution_targets'])

    def test_create_only_and_exact_readback(self):
        result = summary.summarize(self.prepared())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'summary.json'
            digest = summary.save_new(result, path)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                summary.save_new(result, path)

    def test_count_and_required_source_tampering_rejected(self):
        date = self.prepared()
        date['counts']['EQUAL_WEIGHT_BASE']['planned'] = 999
        with self.assertRaises(ValueError):
            summary.summarize(date)
        date = self.prepared()
        date['source_hashes'].pop(next(iter(summary.combined._LOADED)))
        with self.assertRaises(ValueError):
            summary.summarize(date)
        result = summary.summarize(self.prepared())
        result['counts']['DELTA']['observed'] = 0
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                summary.save_new(result, Path(directory) / 'bad.json')


if __name__ == '__main__':
    unittest.main()
