"""Independent synthetic TWR boundary review; no saved accounts."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded, FloatOperation
from fractions import Fraction
import unittest
from backtest import ndx_cash_flow_return_accounting_research as m

def ratio(x):
    return Fraction(int(x['numerator']), int(x['denominator']))

def scenario():
    return dict(initial=dict(session='2023-04-28', cash_usd='0', holdings={'A':10}, close_prices={'A':'10'}),
      sessions=[dict(session='2023-05-01', open_prices={'A':'20','B':'40'}, close_prices={'A':'15','B':'50'}, cash_injection_usd='100', buy_shares={'B':2}),
                dict(session='2023-05-02', open_prices={'A':'12','B':'60'}, close_prices={'A':'20','B':'30'}, cash_injection_usd='42', buy_shares={'A':3})],
      transaction_cost_bps='250')

class Review(unittest.TestCase):
    def test_two_flows_fee_and_unbought_stock_exact_chain(self):
        value=scenario(); before=deepcopy(value); result=m.account_path(**value)
        self.assertEqual(value,before)
        self.assertEqual(result['terminal_equity_usd'],'343.1')
        self.assertEqual(result['total_fees_usd'],'2.9')
        self.assertEqual(result['net_dollar_pnl_excluding_injections_usd'],'101.1')
        expected=Fraction(200,100)*Fraction(268,300)*Fraction(258,268)*Fraction(3431,3000)-1
        self.assertEqual(ratio(result['chained_twr']),expected)
        self.assertEqual(result['rows'][1]['holdings_before'],{'A':10,'B':2})
        self.assertEqual(result['rows'][1]['overnight_pnl_usd'],'-10')
        for row in result['rows']:
            self.assertEqual(Fraction(row['cash_flow_adjusted_pnl_usd']),Fraction(row['overnight_pnl_usd'])+Fraction(row['after_flow_pnl_net_fees_usd']))

    def test_hostile_context_full_document_unchanged(self):
        inputs=scenario(); expected=m.account_path(**inputs)
        with localcontext() as ctx:
            ctx.prec=1
            for trap in (Inexact,Rounded,FloatOperation):ctx.traps[trap]=True
            self.assertEqual(m.account_path(**inputs),expected)
        self.assertFalse(expected['cash_buffer_and_risk_gates_evaluated'])
        self.assertFalse(expected['historical_experiment_executed'])
        self.assertFalse(expected['point_in_time_verified'])

    def test_missing_retained_stock_and_schema_price_attacks(self):
        for attack in ('missing_old_close','float','negative_flow','extra_price','repeated_date'):
            value=scenario()
            if attack=='missing_old_close':del value['sessions'][1]['close_prices']['B']
            elif attack=='float':value['sessions'][0]['cash_injection_usd']=100.0
            elif attack=='negative_flow':value['sessions'][1]['cash_injection_usd']='-1'
            elif attack=='extra_price':value['sessions'][1]['open_prices']['FAKE']='1'
            else:value['sessions'][1]['session']='2023-05-01'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.account_path(**value)

    def test_cash_fee_budget_and_zero_capital_boundaries(self):
        value=scenario()
        value['sessions'][0]['cash_injection_usd']='80'
        with self.assertRaisesRegex(ValueError,'Insufficient cash'):
            m.account_path(**value)  # Gross 80 fits; fee 2 does not.
        value=scenario()
        value['initial'].update(holdings={}, close_prices={})
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_ZERO_CAPITAL_INCEPTION'):
            m.account_path(**value)
        value=scenario()
        value['sessions'][0]['open_prices']['A']='0'
        with self.assertRaisesRegex(ValueError,'Prices must be positive'):
            m.account_path(**value)

    def test_no_buy_fee_zero_and_zero_flow_telescoping(self):
        value=scenario(); value['initial']['cash_usd']='1000'
        for row in value['sessions']:
            row['buy_shares']={};row['cash_injection_usd']='0'
            del row['open_prices']['B'];del row['close_prices']['B']
        result=m.account_path(**value)
        self.assertEqual(result['total_fees_usd'],'0')
        self.assertEqual(ratio(result['chained_twr']),Fraction(1200,1100)-1)

if __name__=='__main__':unittest.main()
