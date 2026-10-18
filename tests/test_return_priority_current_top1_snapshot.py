import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import return_priority_current_top1_snapshot as runner

class CurrentTop1SnapshotTests(unittest.TestCase):
    def fixture(self,folder):
        evidence=folder/'evidence.json';runner.save(evidence,{'synthetic':True})
        args=dict(prices={'a':'300','b':'10'},metadata={'a':{'ticker':'A','issuer_id':'ia'},'b':{'ticker':'B','issuer_id':'ib'}},
            entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'a':'11/10','b':'1'}]*12,
            scenario_dates=[f'2025-{m:02d}-01' for m in range(1,13)],decision_date='2026-10-13',
            max_objective_evaluations=8192,fixed_seed='fresh-quantity-20261014-v1')
        source=folder/'input.json';runner.save(source,dict(status='READY_CONDITIONAL',blocked_tickers=[],search_arguments=args,
            source_hashes={runner.relative(evidence):runner.digest(evidence)},coordinate_semantics='SYNTHETIC'))
        return source,evidence

    def test_tiny_real_selector_io_once_and_no_core(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'tmp') as directory:
            folder=Path(directory);source,_=self.fixture(folder);out=folder/'run'
            receipt=runner.prepare(source,out)
            self.assertEqual({p.name for p in out.iterdir()},{'registration.json'})
            with patch('backtest.return_priority_fresh_cash_quantity_search.search_fresh_cash_quantities',side_effect=AssertionError('core prohibited')):
                result=runner.run(out,receipt['registration_sha256'])
            self.assertEqual(result['stocks'][0]['units'],66)
            self.assertEqual(result['cash'],'200');self.assertEqual(result['selector_calls'],1)
            self.assertEqual(result['quantity_core_calls'],0)
            self.assertEqual(runner.read(source)['search_arguments']['entered_cash'],'20000')
            with self.assertRaisesRegex(ValueError,'ALREADY_STARTED_NO_RETRY'):runner.run(out,receipt['registration_sha256'])

    def test_tamper_prevents_call_and_failed_attempt_cannot_retry(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'tmp') as directory:
            folder=Path(directory);source,evidence=self.fixture(folder);out=folder/'run'
            receipt=runner.prepare(source,out);original=evidence.read_bytes();evidence.write_text('changed')
            with patch.object(runner,'select_top1_quantities') as selector:
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):runner.run(out,receipt['registration_sha256'])
                selector.assert_not_called()
            self.assertFalse((out/'started.json').exists());evidence.write_bytes(original)
            with patch.object(runner,'select_top1_quantities',side_effect=ValueError('synthetic failure')) as selector:
                with self.assertRaisesRegex(ValueError,'synthetic failure'):runner.run(out,receipt['registration_sha256'])
                self.assertEqual(selector.call_count,1)
            self.assertTrue((out/'failure.json').exists())
            with self.assertRaisesRegex(ValueError,'ALREADY_STARTED_NO_RETRY'):runner.run(out,receipt['registration_sha256'])

if __name__=='__main__':unittest.main()
