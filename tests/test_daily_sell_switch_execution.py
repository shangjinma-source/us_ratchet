import unittest
from copy import deepcopy
from fractions import Fraction as F
from backtest.daily_sell_switch_execution import execute_day

class ExecutionTests(unittest.TestCase):
    def args(self):
        return dict(orders=[dict(id='sell',security_id='A',side='SELL',quantity=10,limit='11'),dict(id='buy',security_id='B',side='BUY',quantity=10,limit='10')],ohlc={'A':dict(open='10',high='12',low='9',close='10'),'B':dict(open='10',high='11',low='9',close='10')},cash='0',shares={'A':10},fee_bps='0',slippage_bps='0',mode='PREMIUM_DAY')
    def test_intraday_sale_cannot_fund_open_buy_but_next_day_can(self):
        a=self.args();before=deepcopy(a);r=execute_day(**a)
        self.assertEqual(a,before);self.assertEqual(r['shares']['B'],0);self.assertEqual(r['cash'],'110')
        a.update(orders=[a['orders'][1]],cash=r['cash'],shares=r['shares']);s=execute_day(**a)
        self.assertEqual(s['shares']['B'],10);self.assertEqual(s['cash'],'10')
    def test_strict_touch_expiry_and_open_sale_funding(self):
        a=self.args();a['ohlc']['A'].update(high='11');r=execute_day(**a)
        self.assertEqual(r['cash'],'0');self.assertEqual(r['shares']['A'],10);self.assertEqual(r['log'][-1]['event'],'EXPIRED_UNSOLD')
        a['ohlc']['A'].update(open='12',high='13');r=execute_day(**a)
        self.assertEqual(r['shares']['B'],10);self.assertEqual(r['cash'],'20')
    def test_baseline_fees_and_cash_conservation(self):
        a=self.args();a.update(mode='BASELINE_OPEN',fee_bps='100');r=execute_day(**a)
        self.assertEqual(r['shares']['B'],9);self.assertEqual(F(r['cash']),F('8.1'));self.assertEqual(F(r['fees']),F('1.9'))
        cash=F(a['cash'])
        for x in r['log']:
            if x['event']=='FILLED':cash+=(1 if x['side']=='SELL' else -1)*x['quantity']*F(x['price'])-F(x['fee'])
        self.assertEqual(cash,F(r['cash']))
    def test_invalid_slippage_and_oversell_refuse(self):
        a=self.args();a['slippage_bps']='1'
        with self.assertRaisesRegex(ValueError,'SLIPPAGE'):execute_day(**a)
        a=self.args();a['orders'][0]['quantity']=11
        with self.assertRaisesRegex(ValueError,'HOLDINGS'):execute_day(**a)
    def test_open_equal_limit_not_open_fill(self):
        a=self.args();a['ohlc']['A']['open']='11';r=execute_day(**a)
        self.assertEqual(r['shares']['B'],0);self.assertEqual(r['log'][-1]['phase'],'INTRADAY_SELL')

if __name__=='__main__':unittest.main()
