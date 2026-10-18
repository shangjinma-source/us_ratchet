from copy import deepcopy
import unittest
from scripts.ndx_dynamic_training_context import load_context
from backtest.ndx_dynamic_historical_gates import historical_gates


class HistoricalGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.restored=load_context('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7')

    def test_all_real_rows_recomputed(self):
        outputs=[historical_gates(result=row['result'],contract=self.restored['inputs']['contract'],
                                 holding_count=row['task']['holding_count']) for row in self.restored['records']]
        self.assertEqual(len(outputs),110)
        self.assertTrue(any(row['fractional_risk_passed'] and not row['historical_whole_lot_passed'] for row in outputs))
        self.assertTrue(all(row['technology_scope_passed'] is None for row in outputs))

    def test_saved_flag_and_threshold_tampering_rejected(self):
        for key,value in [('declared_max_single_passed',False),('declared_max_single_weight',.9)]:
            result=deepcopy(self.restored['records'][0]['result'])
            result[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                historical_gates(result=result,contract=self.restored['inputs']['contract'],holding_count=5)


if __name__=='__main__':
    unittest.main()
