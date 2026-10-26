import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.run_long_market_trend_probe_v1 import checkpoint_selection

class BranchCheckpointTests(unittest.TestCase):
    def case(self, alteration=None):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);reuse=base/'reuse';out=base/'out';reuse.mkdir();out.mkdir()
            args=dict(decision_date='2021-01-29',account_state=dict(cash='100'))
            expected=dict(arguments=args,signal={'risk_on':True},experiment_binding={'rule':'fixed10'},raw_selection={'value':1})
            if alteration:alteration(expected)
            (reuse/'2021-01-29.selection.json').write_text(json.dumps(expected))
            budget=dict(new=0,reused=0,maximum=36)
            with patch('scripts.run_long_market_trend_probe_v1.validate_selection_binding'):
                result=checkpoint_selection(arguments=args,signal={'risk_on':True},binding={'rule':'fixed10'},output=out,reuse=reuse,select=lambda **kw:self.fail('Unexpected optimizer'),budget=budget)
            self.assertEqual(budget,dict(new=0,reused=1,maximum=36))
            return result
    def test_exact_branch_reuse(self):self.assertEqual(self.case(),{'value':1})
    def test_wrong_account_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_BRANCH'):self.case(lambda c:c.update(arguments={'decision_date':'2021-01-29','account_state':{'cash':'999'}}))
    def test_baseline_without_signal_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_BRANCH'):self.case(lambda c:c.pop('signal'))
    def test_changed_signal_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_BRANCH'):self.case(lambda c:c.update(signal={'risk_on':False}))

if __name__=='__main__':unittest.main()
