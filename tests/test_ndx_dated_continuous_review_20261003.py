"""Independent exact buy-and-hold oracle, using only synthetic values."""
from fractions import Fraction as F
from decimal import localcontext, Inexact
import unittest
import test_ndx_dated_continuous_weight_diagnostic_research as owner

m = owner.m
def q(v): return F(int(v['numerator']), int(v['denominator']))


class Review(unittest.TestCase):
    def test_full_path_independent_fixed_quantity_and_all_pair_drawdown(self):
        a = owner.fixture()
        a['positions'][0]['target_weight'] = '0.60000000000000001'
        a['positions'][1]['target_weight'] = '0.4'
        for j, sid in enumerate(a['nominal_quotes']):
            for i, row in enumerate(a['nominal_quotes'][sid]):
                row['nominal_open_exact'] = str(13+j+i)
                row['nominal_close_exact'] = str(7+j+(i*7)%23)
        weights = [F('0.60000000000000001'), F('0.4')]
        expected = [F(1)] + [F(999,1000)*sum(weights[j]*F(a['nominal_quotes'][sid][i]['nominal_close_exact'])/F(a['nominal_quotes'][sid][1]['nominal_open_exact']) for j,sid in enumerate(a['nominal_quotes'])) for i in range(1,127)]
        with localcontext() as c:
            c.prec=2; c.traps[Inexact]=True
            r=m.diagnose_continuous_weights(**a)
        self.assertEqual([q(p['normalized_value']) for p in r['path']],expected)
        self.assertEqual(q(r['annualized_return_exact']),expected[-1]**2-1)
        self.assertEqual(q(r['max_drawdown_exact']),max(F(0),max((expected[i]-expected[j])/expected[i] for i in range(127) for j in range(i,127))))
        self.assertEqual(q(r['weight_sum_exact']),sum(weights))
        self.assertTrue(all(r[k] is False for k in m.FLAGS))

    def test_two_later_splits_and_entry_split_do_not_double_adjust(self):
        a=owner.fixture(); sid='sid:a'
        a['positions'][1]['target_weight']='0'
        a['positions'][0]['target_weight']='1'
        for i,row in enumerate(a['nominal_quotes'][sid]):
            price=F(12) if i<20 else F(6) if i<70 else F(2)
            row['nominal_open_exact']=str(price); row['nominal_close_exact']=str(price)
        a['split_events']=[dict(security_id=sid,effective_session=a['calendar'][i],numerator=str(n),denominator='1',source_reference={'path':str(i),'sha256':'a'*64}) for i,n in [(1,5),(20,2),(70,3)]]
        r=m.diagnose_continuous_weights(**a)
        self.assertEqual([q(p['normalized_value']) for p in r['path'][1:]],[F(999,1000)]*126)
        self.assertEqual(q(r['path'][-1]['security_rows'][0]['fractional_quantity']),F(1,2))
        self.assertEqual(q(r['max_drawdown_exact']),F(1,1000))

    def test_unspecified_quote_sid_and_calendar_shift_fail_closed(self):
        for kind in ('extra','missing','shift','fee_bool'):
            a=owner.fixture()
            if kind=='extra': a['nominal_quotes']['foreign']=a['nominal_quotes']['sid:a']
            elif kind=='missing': del a['nominal_quotes']['sid:b']
            elif kind=='shift': a['nominal_quotes']['sid:a'][126]['session']='2026-09-22'
            else: a['transaction_cost_bps']=True
            with self.assertRaises(ValueError):m.diagnose_continuous_weights(**a)


if __name__=='__main__':unittest.main()
