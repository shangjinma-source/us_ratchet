import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts import run_simple253_cost as runner
import test_run_simple253_cost as author


class IndependentRunner(unittest.TestCase):
    def test_compare_direction_requires_both_scenarios_and_preserves_cost_fields(self):
        with TemporaryDirectory() as tmp,patch.object(runner,'ROOT',Path(tmp)):
            prepared=author.Simple253RunnerTests().setup_run(tmp)
            metrics=[dict(final_equity='21000',maximum_close_drawdown='1/10'),dict(final_equity='19000',maximum_close_drawdown='1/10')]
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate',return_value={'status':'COMPLETE'}) as call,patch.object(runner,'summarize',side_effect=metrics):
                runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
            saved=json.loads((Path(tmp)/runner.OUTPUT/'comparison.json').read_text())
            self.assertFalse(saved['both_scenarios_joint_improvement'])
            self.assertEqual(saved['comparison_direction'],'simple253_minus_saved_strategy')
            self.assertEqual(saved['comparisons']['slippage5']['continuous32']['final_equity_difference'],'1000')
            self.assertEqual(saved['comparisons']['fee1_slippage10']['continuous32_half']['final_equity_difference'],'-1000')
            self.assertEqual([c.kwargs['scenario'] for c in call.call_args_list],list(runner.SCENARIOS))

    def test_noncomplete_arm_stops_without_second_arm_or_retry(self):
        with TemporaryDirectory() as tmp,patch.object(runner,'ROOT',Path(tmp)):
            prepared=author.Simple253RunnerTests().setup_run(tmp)
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate',return_value={'status':'BLOCKED_MISSING_EVIDENCE'}) as call:
                with self.assertRaisesRegex(ValueError,'CANDIDATE_NOT_COMPLETE'):runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                out=Path(tmp)/runner.OUTPUT
                self.assertEqual(json.loads((out/'terminal.json').read_text())['status'],'FAILED')
                self.assertEqual(call.call_count,1)
                self.assertTrue((out/('slippage5__'+runner.ARM)/'outcome.json').exists())
                self.assertFalse((out/'comparison.json').exists())
                with self.assertRaises(FileExistsError):runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                self.assertEqual(call.call_count,1)

if __name__=='__main__':unittest.main()
