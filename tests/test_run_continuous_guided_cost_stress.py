from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import run_continuous_guided_cost_stress as runner
from backtest.continuous_guided_cost_stress import prepare_arm


class OnceOnlyCostTests(unittest.TestCase):
    def setup_run(self, directory):
        root = Path(directory)
        (root / 'source.txt').write_text('fixed', encoding='utf8')
        pins = {'source.txt': runner.hashlib.sha256((root / 'source.txt').read_bytes()).hexdigest()}
        assembled = dict(monthly_inputs=[dict(source_hashes={}, search_arguments={
            'max_objective_evaluations': 8192, 'fee_bps': '0'})], session_dates=['2026-01-01', '2026-01-02'])
        receipt = dict(source_hashes=pins, initial_cash='20000')
        return ({'ohlc': {}}, assembled, None, receipt)

    def test_monthly_pins_added_conflict_rejected_and_input_immutable(self):
        with TemporaryDirectory() as directory:
            _, assembled, _, receipt = self.setup_run(directory)
            original = deepcopy(assembled)
            result = prepare_arm(assembled, 'slippage5', receipt['source_hashes'])
            self.assertEqual(result['monthly_inputs'][0]['source_hashes'], receipt['source_hashes'])
            self.assertEqual(original, assembled)
            assembled['monthly_inputs'][0]['source_hashes']['source.txt'] = 'a' * 64
            with self.assertRaisesRegex(ValueError, 'PIN_CONFLICT'):
                prepare_arm(assembled, 'slippage5', receipt['source_hashes'])

    def test_preflight_no_directory_or_execution_and_wrong_hash_rejected(self):
        with TemporaryDirectory() as directory, patch.object(runner, 'ROOT', Path(directory)):
            prepared = self.setup_run(directory)
            with patch.object(runner, 'prepare_run', return_value=prepared), patch.object(runner, 'run_cost_stress_arm') as run:
                report = runner.run_once()
                self.assertEqual(report['status'], 'PREFLIGHT_ONLY_NO_SEARCH')
                with self.assertRaisesRegex(ValueError, 'REVIEWED_RECEIPT'):
                    runner.run_once(execute=True, expected_receipt_sha256='wrong')
                run.assert_not_called()
                self.assertFalse((Path(directory) / runner.OUTPUT).exists())

    def test_four_arms_separate_inputs_and_create_only(self):
        with TemporaryDirectory() as directory, patch.object(runner, 'ROOT', Path(directory)):
            prepared = self.setup_run(directory)
            seen = []
            def run(**kwargs):
                self.assertNotIn('mutated', kwargs['assembled'])
                kwargs['assembled']['mutated'] = True
                seen.append((kwargs['scenario'], kwargs['arm'], kwargs['initial_cash']))
                self.assertEqual(kwargs['reviewed_pins'], prepared[3]['source_hashes'])
                return dict(status='COMPLETE')
            with patch.object(runner, 'prepare_run', return_value=prepared), patch.object(runner, 'run_cost_stress_arm', side_effect=run), patch.object(runner, 'summarize', return_value=dict(final_equity='20001', maximum_close_drawdown='1/10')):
                report = runner.run_once(execute=True, expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                self.assertEqual(report['status'], 'COMPLETE_PENDING_INDEPENDENT_REVIEW')
                self.assertEqual(len(set(seen)), 4)
                self.assertTrue(all(row[2] == '20000' for row in seen))
                with self.assertRaises(FileExistsError):
                    runner.run_once(execute=True, expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                with self.assertRaisesRegex(ValueError, 'FIXED_ONCE_ONLY'):
                    runner.run_once(output_directory='tmp/another', execute=True)

    def test_failure_is_preserved_no_retry(self):
        with TemporaryDirectory() as directory, patch.object(runner, 'ROOT', Path(directory)):
            prepared = self.setup_run(directory)
            with patch.object(runner, 'prepare_run', return_value=prepared), patch.object(runner, 'run_cost_stress_arm', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    runner.run_once(execute=True, expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                terminal = json.loads((Path(directory) / runner.OUTPUT / 'terminal.json').read_text())
                self.assertFalse(terminal['automatic_retry_allowed'])
                with self.assertRaises(FileExistsError): runner.run_once(execute=True)

    def test_source_drift_after_arm_preserves_outcome_and_stops(self):
        with TemporaryDirectory() as directory, patch.object(runner, 'ROOT', Path(directory)):
            prepared = self.setup_run(directory)
            def run(**kwargs):
                (Path(directory) / 'source.txt').write_text('drift')
                return dict(status='COMPLETE')
            with patch.object(runner, 'prepare_run', return_value=prepared), patch.object(runner, 'run_cost_stress_arm', side_effect=run) as run_mock:
                with self.assertRaisesRegex(ValueError, 'SOURCE_DRIFT'):
                    runner.run_once(execute=True, expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                self.assertEqual(run_mock.call_count, 1)
                self.assertTrue((Path(directory) / runner.OUTPUT / 'slippage5__continuous32' / 'outcome.json').exists())


if __name__ == '__main__': unittest.main()
