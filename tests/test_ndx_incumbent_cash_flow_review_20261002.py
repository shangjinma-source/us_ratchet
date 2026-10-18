from copy import deepcopy
from decimal import Inexact, localcontext
from fractions import Fraction as F
import unittest
from backtest import ndx_incumbent_cash_flow_research as m


def args(prices, weights, cash, holdings=None, flow='0', fee='0', buffer='0'):
    return dict(initial=dict(session='2023-01-02', cash_usd=cash, holdings=holdings or {}, close_prices=prices),
        sessions=[dict(session='2023-01-03',open_prices=deepcopy(prices),close_prices=deepcopy(prices),cash_injection_usd=flow)],
        fixed_weights=weights,schedule=[dict(decision_date='2023-01-02',execution_date='2023-01-03')],
        securities={s:dict(ticker=s,issuer_id=s,risk_chain=s) for s in prices},
        risk_parameters=dict(max_single_weight='.45',min_single_weight='.05',top_weight_cap='.8',minimum_effective_n_ratio='.7',risk_chain_top1_cap='.55'),
        transaction_cost_bps=fee,minimum_cash_buffer_usd=buffer)

def fraction(value):
    return F(int(value['numerator']),int(value['denominator']))

class IndependentReview(unittest.TestCase):
    def test_two_stages_restart_floor_and_risk_not_gate(self):
        a=args({'A':'100','B':'10'},{'A':'.5','B':'.5'},'210',fee='10000')
        r=m.simulate_incumbent_cash_flow(**a); d=r['decisions'][0]
        self.assertEqual(d['original_floor_shares'],{'A':1,'B':10})
        self.assertEqual(d['desired_shares'],{'A':0,'B':10})
        self.assertEqual([x['security_id'] for x in d['reductions']],['B']*9+['A'])
        self.assertEqual(d['reductions'][-1]['stage'],'CONTROL_FINANCIAL_PROJECTION_ALLOW_ZERO')
        self.assertEqual(r['executions'][0]['status'],'FILLED')
        self.assertEqual(r['terminal_equity_usd'],'110')
        self.assertFalse(d['risk']['all_passed'])
        a=args({'A':'100','B':'1'},{'A':'.5','B':'.5'},'200',fee='10')
        self.assertEqual(m.simulate_incumbent_cash_flow(**a)['decisions'][0]['desired_shares'],{'A':1,'B':99})

    def test_overnight_signed_fee_flow_exact_then_own_state_refreeze(self):
        a=args({'A':'10','B':'10'},{'B':'1'},'0',{'A':10},flow='100',fee='100')
        a['sessions'][0].update(open_prices={'A':'12','B':'10'},close_prices={'A':'12','B':'11'})
        a['sessions'].append(dict(session='2023-01-04',open_prices={'A':'12','B':'11'},close_prices={'A':'12','B':'11'},cash_injection_usd='0'))
        a['schedule'].append(dict(decision_date='2023-01-03',execution_date='2023-01-04'))
        original=deepcopy(a)
        with localcontext() as c:
            c.prec=2; c.traps[Inexact]=True
            r=m.simulate_incumbent_cash_flow(**a)
        self.assertEqual(a,original)
        self.assertEqual(r['decisions'][0]['desired_shares'],{'B':9})
        self.assertEqual(r['daily'][0]['cash_after_usd'],'127.9')
        self.assertEqual(r['daily'][0]['close_equity_usd'],'226.9')
        self.assertEqual(fraction(r['daily'][0]['session_twr']), F(6,5)*F(2269,2200)-1)
        self.assertEqual(r['decisions'][1]['cash_before_usd'],'127.9')
        self.assertEqual(r['decisions'][1]['shares_before'],{'B':9})
        self.assertEqual(r['decisions'][1]['desired_shares'],{'B':20})
        self.assertEqual(r['total_fees_usd'],'3.31')
        self.assertEqual(fraction(r['chained_twr']),F(6,5)*F(22569,22000)-1)

    def test_rejection_preserves_both_sides_and_flow_no_fee(self):
        a=args({'A':'10','B':'10'},{'B':'1'},'0',{'A':10},flow='1',fee='10')
        a['sessions'][0]['open_prices']={'A':'1','B':'100'}
        r=m.simulate_incumbent_cash_flow(**a); e=r['executions'][0]
        self.assertEqual(e['status'],'REJECTED'); self.assertEqual(e['shares_after'],{'A':10})
        self.assertEqual(e['cash_after_usd'],'1'); self.assertEqual(e['actual_fees_usd'],'0')
        self.assertEqual(r['trades'],[]); self.assertEqual(r['daily'][0]['signed_share_delta'],{})
        self.assertEqual(fraction(r['chained_twr']),F(1,10)*F(101,11)-1)
        self.assertFalse(r['open_replan_performed'])

    def test_no_normalization_full_domain_and_tolerance_boundaries(self):
        a=args({'A':'1'},{'A':'.99999999999999999'},'100')
        self.assertEqual(m.simulate_incumbent_cash_flow(**a)['decisions'][0]['desired_shares'],{'A':99})
        for price, status in [('1.000000005','FILLED'),('1.00000002','REJECTED')]:
            a=args({'A':'1'},{'A':'1'},'2',buffer='1')
            a['sessions'][0]['open_prices']={'A':price}
            self.assertEqual(m.simulate_incumbent_cash_flow(**a)['executions'][0]['status'],status)
        a=args({'A':'1','X':'2'},{'A':'1'},'1',{'X':1})
        del a['sessions'][0]['close_prices']['X']
        with self.assertRaises(ValueError): m.simulate_incumbent_cash_flow(**a)
        for key, value in [('cash_injection_usd',True),('cash_injection_usd',1.5)]:
            a=args({'A':'1'},{'A':'1'},'1'); a['sessions'][0][key]=value
            with self.assertRaises(ValueError): m.simulate_incumbent_cash_flow(**a)

if __name__=='__main__': unittest.main()

