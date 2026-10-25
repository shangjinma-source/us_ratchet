import json,tempfile,unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import test_review_simple253_cost as fixture
from scripts import review_saved_simple253_cost as saved

class IndependentSavedSimple(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.ReviewTests.setUpClass()
    def test_rehashed_false_optimizer_calls_rejected(self):
        bad=deepcopy(fixture.ReviewTests.outcome)
        bad['cost_stress_binding']['optimizer_calls']=False
        h=sha256(json.dumps(bad['cost_stress_binding'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        bad['cost_stress_binding_sha256']=h
        for row in bad['cost_stress_monthly_bindings']:row['arm_binding_sha256']=h
        with self.assertRaises(ValueError):fixture.ReviewTests().check(bad)
    def test_flag_type_and_top_selection_call_types(self):
        for name,value in [('automatic_promotion',0),('costs_are_research_assumptions',1)]:
            bad=deepcopy(fixture.ReviewTests.outcome);bad[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):fixture.ReviewTests().check(bad)
        for name,value in [('core_calls',False),('selector_calls',True)]:
            bad=deepcopy(fixture.ReviewTests.outcome);bad['provider_audit'][0]['selection'][name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):fixture.ReviewTests().check(bad)
    def test_blocked_terminal_rejected_before_prepare(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(saved,'ROOT',Path(tmp)),patch.object(saved,'REVIEWER_PATHS',[]):
            directory=Path(tmp)/saved.OUTPUT/('slippage5__'+saved.ARM);directory.mkdir(parents=True)
            (directory/'terminal.json').write_text(json.dumps({'status':'BLOCKED'}))
            with patch.object(saved,'prepare_run',side_effect=AssertionError('NO PREPARE FOR PARTIAL')):
                with self.assertRaisesRegex(ValueError,'COMPLETED_ARM_REQUIRED'):saved.run('slippage5')

if __name__=='__main__':unittest.main()
