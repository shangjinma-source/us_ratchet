import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.return_priority_original_weight_control_run import execute_control


class ControlExecutionTests(unittest.TestCase):
    def fixture(self, touched):
        days = ['2026-01-02', '2026-01-05', '2026-01-06']
        prices = ['10', '10' if touched else '12', '10' if touched else '12']
        ohlc = {'a': {d: dict.fromkeys(('open','high','low','close'), price)
                      for d, price in zip(days, prices)}}
        proposal = dict(session_dates=days, target_weights={'a':'1'}, ohlc=ohlc,
            proposed_account=dict(initial_cash='100', initial_shares={}, commission_bps='0',
                minimum_cash_buffer='0', monthly_decision_dates=[days[0]]))
        binding = dict(provider_arguments=dict(weights={'a':'1'}, session_dates=days, actions=[],
            close_prices={'a': dict(zip(days, prices))}, monthly_inputs=[dict(decision_date=days[0],
                valuation_quotes=[dict(security_id='a',price='10')],
                search_arguments=dict(fee_bps=0,minimum_cash_buffer=0),source_hashes={})]))
        return proposal, binding

    def test_real_kernel_complete_and_no_retry(self):
        proposal,binding = self.fixture(True)
        with TemporaryDirectory() as tmp:
            output=Path(tmp)/'run'
            result=execute_control(proposal=proposal,binding=binding,directory=output)
            self.assertEqual(result['metrics']['kernel_status'],'COMPLETE')
            outcome=json.loads((output/'outcome.json').read_text())
            self.assertEqual(outcome['shares'],{'a':10})
            self.assertEqual(outcome['cash'],'0')
            self.assertEqual(len(outcome['daily_ledger']),2)
            with self.assertRaises(FileExistsError):
                execute_control(proposal=proposal,binding=binding,directory=output)

    def test_untouched_day_limit_expires_without_fill(self):
        proposal,binding=self.fixture(False)
        with TemporaryDirectory() as tmp:
            output=Path(tmp)/'run'
            execute_control(proposal=proposal,binding=binding,directory=output)
            first=json.loads((output/'callback_2026-01-02.json').read_text())
            self.assertEqual(first['response']['orders'][0]['limit'],'10')
            outcome=json.loads((output/'outcome.json').read_text())
            self.assertEqual(outcome['daily_ledger'][0]['cash'],'100')
            self.assertFalse(any(outcome['daily_ledger'][0]['shares'].values()))

    def test_mismatched_prices_rejected_before_intent(self):
        proposal,binding=self.fixture(True)
        binding['provider_arguments']['close_prices']['a']['2026-01-02']='9'
        with TemporaryDirectory() as tmp:
            output=Path(tmp)/'run'
            with self.assertRaises(ValueError):
                execute_control(proposal=proposal,binding=binding,directory=output)
            self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
