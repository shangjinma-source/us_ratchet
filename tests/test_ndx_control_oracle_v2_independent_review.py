import copy
import unittest
from test_ndx_fixed_control_accounting_independent_audit_research import fixture, CONTRACT
from backtest import ndx_fixed_control_accounting_independent_audit_v2_research as m


class ControlV2Review(unittest.TestCase):
    def test_empty_exception_requires_exact_boolean_false_and_zero_slots_are_nonempty(self):
        empty = {'all_passed':False,'checks':{'ALL_CASH':False}}
        for saved in ({'all_passed':0,'checks':{'ALL_CASH':False}},
                      {'all_passed':False,'checks':{'ALL_CASH':0}},
                      dict(empty,point_in_time_verified=True)):
            with self.assertRaises(ValueError): m.observed_risk(saved,{}, {},{},CONTRACT)
        with self.assertRaises(ValueError): m.observed_risk(empty,{'s':0},{'s':100},{'s':'chain'},CONTRACT)

    def test_private_binding_retains_cash_validation_and_does_not_mutate_prior(self):
        args = fixture()
        args['execution']['daily'][0]['risk'] = {'all_passed':False,'checks':{'ALL_CASH':False}}
        callback = m.prior._audit.__globals__['observed_risk']
        result = m.audit(**args)
        self.assertTrue(result['filled'])
        self.assertIs(m.prior._audit.__globals__['observed_risk'], callback)
        changed = copy.deepcopy(args)
        changed['execution']['daily'][0]['cash_usd'] = 24999
        with self.assertRaises(ValueError): m.audit(**changed)
        with self.assertRaises(ValueError): m.prior.audit(**args)


if __name__ == '__main__': unittest.main()
