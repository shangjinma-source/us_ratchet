import unittest
from fractions import Fraction as F
from docs.candidates.roa_daily_account_20261106 import run_account

class IndependentAccountAudit(unittest.TestCase):
    days=['2026-01-02','2026-01-05','2026-01-06','2026-01-07']
    def run_book(self, risk, *, events=(), actions=(), negative=False):
        d=self.days
        bars={'A':{x:dict(open='-100' if negative and x==d[2] else '100',close='100') for x in d}}
        signals={x:dict(decision_date=d[0],weights={'A':'1/10'},risk_on=on) for x,on in zip(d[:-1],risk)}
        return run_account(session_dates=d,ohlc=bars,signals=signals,actions=list(actions),dividend_events=list(events),gate=lambda *a:{'admitted':True},initial_cash='10000',settlement_delay=1)
    def dividend(self,ex):
        return dict(event_id='div',security_id='A',ex_date=ex,payment_date=self.days[3],amount_per_share='2',withholding_rate='0',assumption='synthetic',currency='USD')
    def test_negative_open_rejected_without_negative_fill(self):
        book=self.run_book([True,False,False],negative=True)
        self.assertEqual(book['status'],'BLOCKED')
        self.assertTrue(all(F(x['price'])>0 for x in book['order_log']))
    def test_ex_date_buy_not_entitled(self):
        book=self.run_book([True,True,True],events=[self.dividend(self.days[1])])
        self.assertEqual(book['status'],'COMPLETE')
        self.assertEqual(book['dividend_ledger']['events']['div']['opening_quantity'],0)
        self.assertEqual(F(book['dividend_ledger']['paid_cash']),0)
    def test_ex_date_seller_keeps_entitlement(self):
        book=self.run_book([True,False,False],events=[self.dividend(self.days[2])])
        self.assertEqual(book['status'],'COMPLETE')
        self.assertEqual(book['dividend_ledger']['events']['div']['opening_quantity'],9)
        self.assertEqual(F(book['daily_ledger'][1]['dividend_receivable']),18)
        self.assertEqual(F(book['daily_ledger'][2]['cash'])-F(book['daily_ledger'][1]['cash']),18)
    def test_mixed_merger_cannot_silently_drop_stock_leg(self):
        event=dict(type='merger',date=self.days[2],security_id='A',new_security_id='B',share_cash='60',share_ratio='2.1243',event_id='mixed',source_references=['synthetic'])
        try:
            book=self.run_book([True,True,True],actions=[event])
        except ValueError:
            return
        self.assertEqual(book['status'],'BLOCKED')

    def test_cash_merger_pending_value_then_close_payment(self):
        event=dict(type='merger',date=self.days[2],security_id='A',share_cash='110',event_id='m',source_references=['synthetic'])
        book=self.run_book([True,True,True],actions=[event]);self.assertEqual(book['status'],'COMPLETE')
        self.assertEqual(book['daily_ledger'][1]['shares'],{})
        self.assertEqual(F(book['daily_ledger'][1]['merger_receivable']),990)
        self.assertEqual(book['daily_ledger'][1]['cash'],book['daily_ledger'][0]['cash'])
        self.assertEqual(F(book['daily_ledger'][2]['cash'])-F(book['daily_ledger'][1]['cash']),990)
        self.assertEqual(book['daily_ledger'][2]['equity'],book['daily_ledger'][1]['equity'])

if __name__=='__main__':unittest.main()
