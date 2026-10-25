import unittest
from copy import deepcopy
from data.strategy_followup_execution_binding_v1 import validate_execution_shape

class SubsetTests(unittest.TestCase):
    def case(self):
        b=dict(schema='DAILY_BUY_DATA_WAIT_SELL_EXECUTION_V1',projection_semantics='EXECUTION_SUBSET_NOT_STRATEGY_TARGET',effective_target_quantities={'A':6,'B':52},execution_quantities={'A':6,'B':0},waiting_buys={'B':52})
        r=dict(projection_semantics=b['projection_semantics'],effective_target_quantities=dict(b['effective_target_quantities']),execution_quantities=dict(b['execution_quantities']),daily_gate=dict(rows=[dict(security_id='A',held=14),dict(security_id='B',held=0)]),waiting_data=[dict(security_id='B',quantity=52,reason='WAIT_BUY_MINUTE_DATA')],new_orders=[dict(security_id='A',side='SELL',quantity=8)])
        return b,r
    def test_sell_subset_not_buy_target(self):
        b,r=self.case();before=deepcopy((b,r));validate_execution_shape(b,r);self.assertEqual((b,r),before)
    def test_buy_and_excess_sell_rejected(self):
        for side,quantity in [('BUY',8),('SELL',15)]:
            b,r=self.case();r['new_orders'][0].update(side=side,quantity=quantity)
            with self.assertRaisesRegex(ValueError,'ORDER_INVALID'):validate_execution_shape(b,r)
    def test_projection_and_wait_changes_rejected(self):
        b,r=self.case();r['execution_quantities']['B']=52
        with self.assertRaisesRegex(ValueError,'TARGET_CHANGED'):validate_execution_shape(b,r)
        b,r=self.case();r['waiting_data']=[]
        with self.assertRaisesRegex(ValueError,'WAITING_DATA_CHANGED'):validate_execution_shape(b,r)
    def test_unknown_schema_rejected(self):
        b,r=self.case();b['schema']='UNKNOWN'
        with self.assertRaisesRegex(ValueError,'BINDING_SCHEMA'):validate_execution_shape(b,r)
