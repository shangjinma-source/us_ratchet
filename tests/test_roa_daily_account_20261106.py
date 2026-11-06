import unittest
from fractions import Fraction as F
from docs.candidates.roa_daily_account_20261106 import run_account


class AccountTests(unittest.TestCase):
    def run_case(self,days,closes,signals,dividends=(),actions=()):
        bars={'A':{d:dict(open='100',close=str(c)) for d,c in zip(days,closes)}}
        return run_account(session_dates=days,ohlc=bars,signals=signals,actions=actions,
            dividend_events=dividends,gate=lambda *args:{'admitted':True},initial_cash='10000')
    def test_next_open_integer_cash_slippage(self):
        days=['2026-01-02','2026-01-05']
        signal={days[0]:dict(decision_date=days[0],weights={'A':'1/10'},risk_on=True)}
        book=self.run_case(days,[100,100],signal)
        self.assertEqual(book['status'],'COMPLETE')
        fill=book['order_log'][0]
        self.assertEqual((fill['date'],fill['phase'],fill['quantity']),('2026-01-05','OPEN',9))
        self.assertEqual(F(fill['price']),F('100.05'))
        self.assertEqual(F(book['daily_ledger'][0]['cash']),F('9099.55'))
    def test_market_off_has_open_priority_over_pending(self):
        days=['2026-01-29','2026-01-30','2026-02-02']
        signals={days[0]:dict(decision_date=days[0],weights={'A':'1/10'},risk_on=True),
                 days[1]:dict(decision_date=days[1],weights={},risk_on=False)}
        book=self.run_case(days,[100,75,70],signals)
        self.assertEqual(book['status'],'COMPLETE')
        sell=book['order_log'][-1]
        self.assertEqual((sell['date'],sell['phase'],sell['side']),('2026-02-02','OPEN','SELL'))
        self.assertEqual(F(sell['price']),F(100)*F(1999,2000))
    def test_month_reduction_precedes_pending_close(self):
        days=['2026-01-29','2026-01-30','2026-02-02']
        signals={days[0]:dict(decision_date=days[0],weights={'A':'1/10'},risk_on=True),
                 days[1]:dict(decision_date=days[1],weights={'A':'1/20'},risk_on=True)}
        book=self.run_case(days,[100,75,70],signals)
        self.assertEqual(book['status'],'COMPLETE')
        sells=[f for f in book['order_log'] if f['side']=='SELL']
        self.assertEqual([(f['phase'],f['quantity']) for f in sells],[('OPEN',5),('CLOSE',4)])
    def test_split_off_on_keeps_successor_identity(self):
        days=['2026-01-02','2026-01-05','2026-01-06','2026-01-07','2026-01-08']
        signals={d:dict(decision_date=days[0],weights={'A':'1/10'},risk_on=(d!='2026-01-06')) for d in days[:-1]}
        bars={'A':{d:dict(open='100',close='100') for d in days[:2]},'B':{d:dict(open='50',close='50') for d in days[2:]}}
        action=dict(type='split_identity',date=days[2],security_id='A',new_security_id='B',old_shares='1',new_shares='2')
        book=run_account(session_dates=days,ohlc=bars,signals=signals,actions=[action],dividend_events=[],gate=lambda *args:{'admitted':True},initial_cash='10000')
        self.assertEqual(book['status'],'COMPLETE',book['reason'])
        self.assertEqual(book['daily_ledger'][1]['shares'],{'B':18})
        self.assertEqual([(f['side'],f['security_id']) for f in book['order_log']],[('BUY','A'),('SELL','B'),('BUY','B')])
    def test_dividend_receivable_then_paid_close(self):
        days=['2026-01-02','2026-01-05','2026-01-06','2026-01-07']
        signals={d:dict(decision_date=days[0],weights={'A':'1/10'},risk_on=True) for d in days[:-1]}
        event=dict(event_id='div',security_id='A',ex_date=days[2],payment_date=days[3],amount_per_share='2',withholding_rate='0',assumption='synthetic',currency='USD')
        book=self.run_case(days,[100]*4,signals,[event])
        self.assertEqual(book['status'],'COMPLETE')
        self.assertEqual(F(book['daily_ledger'][1]['dividend_receivable']),18)
        self.assertEqual(book['daily_ledger'][0]['cash'],book['daily_ledger'][1]['cash'])
        self.assertEqual(F(book['daily_ledger'][2]['cash'])-F(book['daily_ledger'][1]['cash']),18)
        self.assertEqual(len(book['order_log']),1)
        simultaneous=dict(type='split',date=days[2],security_id='A',old_shares='1',new_shares='2')
        blocked=self.run_case(days,[100]*4,signals,[event],[simultaneous])
        self.assertEqual(blocked['status'],'BLOCKED')
        self.assertEqual(blocked['reason']['error'],'SIMULTANEOUS_DIVIDEND_UNIT_REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
