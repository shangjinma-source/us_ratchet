import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_two_period_conditional_execution_20260919 as m


class ConditionalExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target=json.loads((m.BASE/m.BOUND['target'][0]).read_bytes())['result']
        cls.prices=json.loads((m.BASE/m.BOUND['prices'][0]).read_bytes())
        cls.identities=m.identity.build()

    def test_real_seven_coordinate_preparation_does_not_execute(self):
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research',side_effect=AssertionError('No execution in preparation')):
            p=m.assemble(self.target,self.prices,self.identities)
        self.assertEqual(p['arguments']['opens'].shape,(21,7))
        self.assertEqual(p['arguments']['initial_cash_usd'],25000)
        self.assertEqual(p['arguments']['corporate_actions'],[])
        self.assertEqual(p['schedule'],self.target['schedule'])
        for row in p['arguments']['schedule']:
            self.assertTrue(all(v['ticker']==p['columns'][sid] for sid,v in row['targets'].items()))

    def test_wrong_identity_cash_clock_and_boolean_price_rejected(self):
        for defect in ('ticker','issuer','cash','clock','price','interval'):
            with self.subTest(defect=defect):
                t,p,i=copy.deepcopy((self.target,self.prices,self.identities));sid=next(iter(t['schedule'][0]['targets']))
                if defect=='ticker':t['schedule'][0]['targets'][sid]['ticker']='OTHER'
                if defect=='issuer':t['schedule'][0]['targets'][sid]['issuer_id']='issuer:0000000001'
                if defect=='cash':t['downstream_execution_capital_usd']=5000
                if defect=='clock':t['schedule'][0]['execution_date']='2023-04-04'
                if defect=='price':p['matrices']['open']['2023-03-31']['AMAT']=True
                if defect=='interval':i['continuous_identity_interval_verified']=True
                with self.assertRaises(ValueError):m.assemble(t,p,i)

    def test_default_preflight_and_interrupted_attempt_cannot_repeat(self):
        with tempfile.TemporaryDirectory(dir=m.BASE) as folder:
            output=str(Path(folder)/'account.json')
            with patch.object(m,'prepare',return_value=({}, {}, [])),patch.object(m,'verify_gaps'),patch.object(m.archive,'verify_expected_sources',return_value={}):
                with patch.object(m,'execute_prepared',side_effect=AssertionError('No implicit execution')):
                    self.assertFalse(m.run(identity_path='unused',identity_sha256='x',output=output)['execution_performed'])
                self.assertFalse(Path(output+'.started.json').exists())
                with patch.object(m,'execute_prepared',side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):m.run(identity_path='unused',identity_sha256='x',output=output,execute=True)
                self.assertTrue(Path(output+'.started.json').exists())
                self.assertFalse(Path(output).exists())
                with patch.object(m,'prepare',side_effect=AssertionError('Do not prepare again')):
                    with self.assertRaises(FileExistsError):m.run(identity_path='unused',identity_sha256='x',output=output,execute=True)


if __name__=='__main__':unittest.main()
