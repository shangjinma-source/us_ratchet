import unittest
from test_ndx_two_period_benchmark_prefix_20260919 import fixture
from scripts import ndx_two_period_benchmark_prefix_20260919 as audit


class PrefixIndependentTests(unittest.TestCase):
    def test_frozen_delta_must_equal_actual_target_minus_held(self):
        docs,days,prices=fixture();e=docs['control']['execution'];sid=next(iter(e['decisions'][0]['delta']))
        e['decisions'][0]['delta'][sid]+=1;e['executions'][0]['frozen_delta'][sid]+=1
        with self.assertRaises(ValueError): audit.audit_control(docs['control'],docs['old'],days,prices)

    def test_decision_close_projected_cash_and_fees_independently_checked(self):
        for field in ('projected_cash_usd','projected_fees_usd'):
            with self.subTest(field=field):
                docs,days,prices=fixture();docs['control']['execution']['decisions'][0][field]+=1
                with self.assertRaises(ValueError): audit.audit_control(docs['control'],docs['old'],days,prices)

    def test_future_nav_mapping_and_float_trade_quantity_rejected(self):
        docs,days,prices=fixture();docs['control']['execution']['trades'][0]['share_delta']=float(docs['control']['execution']['trades'][0]['share_delta'])
        with self.assertRaises(ValueError): audit.audit_control(docs['control'],docs['old'],days,prices)
        nav=docs['nav'];path,=[p for p in nav['source_hashes'] if p.endswith('012922.csv')]
        nav['nav']['rows'][0]['nav_date']='2023-04-03'
        with self.assertRaises(ValueError): audit.audit_nav(nav,audit.Path(path).read_bytes(),days)


if __name__=='__main__': unittest.main()
