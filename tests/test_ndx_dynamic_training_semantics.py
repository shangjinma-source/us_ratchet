from copy import deepcopy
import unittest
from scripts.ndx_dynamic_training_context import load_context
from backtest.ndx_dynamic_training_semantics import training_semantics


class TrainingSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=load_context('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7')['inputs']

    def signature(self,inputs):
        return training_semantics(inputs=inputs,decision_data_end='2024-01-31',
            source_batch='ndx_cardinality_real_runner_p2_exact_v2',universe_track='strict_technology')['training_semantics_sha256']

    def test_column_order_not_economic_change(self):
        changed=deepcopy(self.inputs)
        changed['returns']=changed['returns'].iloc[:,::-1]
        self.assertEqual(self.signature(changed),self.signature(self.inputs))

    def test_fee_or_market_data_changes_signature(self):
        changed=deepcopy(self.inputs)
        changed['contract']['transaction_cost_bps']+=1
        self.assertNotEqual(self.signature(changed),self.signature(self.inputs))
        changed=deepcopy(self.inputs)
        changed['returns'].iloc[0,0]+=.01
        self.assertNotEqual(self.signature(changed),self.signature(self.inputs))

    def test_bad_calendar_and_boolean_rejected(self):
        changed=deepcopy(self.inputs)
        changed['returns']=changed['returns'].iloc[::-1]
        with self.assertRaises(ValueError): self.signature(changed)
        changed=deepcopy(self.inputs)
        changed['returns'][changed['returns'].columns[0]]=True
        with self.assertRaises(ValueError): self.signature(changed)


if __name__=='__main__':
    unittest.main()
