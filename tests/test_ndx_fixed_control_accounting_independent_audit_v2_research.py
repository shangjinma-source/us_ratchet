import copy
import importlib.util
from pathlib import Path
import unittest
from backtest import ndx_fixed_control_accounting_independent_audit_v2_research as m

spec=importlib.util.spec_from_file_location('control_fixture',Path(__file__).with_name('test_ndx_fixed_control_accounting_independent_audit_research.py'))
fixture_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture_module)
EMPTY={'all_passed':False,'checks':{'ALL_CASH':False}}


class Tests(unittest.TestCase):
    def test_actual_empty_shape_then_nonempty_risk_failure_fill(self):
        args=fixture_module.fixture();args['execution']['daily'][0]['risk']=copy.deepcopy(EMPTY)
        original=m.prior.observed_risk
        with self.assertRaises(ValueError):m.prior.audit(**args)
        value=m.audit(**args)
        self.assertTrue(value['filled']);self.assertEqual(value['zero_share_security_ids'],['s7'])
        self.assertIs(m.prior.observed_risk,original)

    def test_rejected_account_remains_exact_ordinary_all_cash(self):
        args=fixture_module.fixture(True)
        for row in args['execution']['daily']:row['risk']=copy.deepcopy(EMPTY)
        value=m.audit(**args);self.assertTrue(value['rejected']);self.assertEqual(value['trade_count'],0)

    def test_no_expansion_to_zero_slots_partial_extensions_or_fake_risk(self):
        for shares,marks,saved in [({'s':0},{'s':1},EMPTY),({}, {},dict(EMPTY,risk_is_order_gate=False)),({}, {},{'all_passed':True,'checks':{'ALL_CASH':False}}),({}, {'s':1},EMPTY)]:
            with self.subTest(shares=shares,saved=saved),self.assertRaises(ValueError):m.observed_risk(saved,shares,marks,{},fixture_module.CONTRACT)
        args=fixture_module.fixture();args['execution']['daily'][1]['risk']=copy.deepcopy(EMPTY)
        with self.assertRaises(ValueError):m.audit(**args)


if __name__=='__main__':unittest.main()
