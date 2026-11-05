import unittest
from fractions import Fraction as F
from docs.candidates.momentum_cash_merger_settlement_20261105 import Settlement, run_book
from backtest.historical_dividend_next_open_book_research import run_next_open_book


class SettlementIntegration(unittest.TestCase):
    days=['2023-12-13','2023-12-14','2023-12-15','2023-12-18','2023-12-19','2023-12-20','2023-12-21','2023-12-22']
    event=dict(event_id='SGEN_FIXTURE',type='merger',date='2023-12-14',security_id='A',share_cash='229',source_references=['official-fixture'])

    def test_three_delays_real_book_only_next_open_can_spend(self):
        for delay in (0,1,5):
            seen=[]
            def provider(*,decision_date,active_date,state):
                seen.append((active_date,F(state['cash'])))
                orders=[]
                if F(state['cash'])>=458:
                    orders=[dict(id='buy:'+active_date,security_id='B',side='BUY',quantity=2,
                                 decision_mark='229',decision_date=decision_date,active_date=active_date)]
                return dict(status='READY',orders=orders)
            bars={'B':{d:dict(open='229',high='229',low='229',close='229') for d in self.days}}
            book=run_book(settlement_delay=delay,session_dates=self.days,ohlc=bars,initial_cash='0',
                          initial_shares={'A':2},events=[self.event],order_provider=provider,fee_bps='0',slippage_bps='0')
            self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
            self.assertTrue(all(F(r['equity'])==458 for r in book['daily_ledger']))
            due=self.days[1+delay]
            row=next(r for r in book['daily_ledger'] if r['date']==due)
            self.assertEqual(F(row['cash']),458)
            self.assertEqual(F(row['receivable']),0)
            self.assertEqual(row['shares'].get('B',0),0)
            self.assertEqual(book['daily_ledger'][-1]['shares']['B'],2)
            available=[d for d,c in seen if c==458]
            self.assertEqual(available,[self.days[2+delay]])
            self.assertEqual(len(book['cash_merger_settlement']['releases']),1)

    def test_duplicate_and_wrong_date_release_rejected(self):
        store=Settlement(self.days,[self.event],0)
        store.accrue(self.event,2)
        with self.assertRaisesRegex(ValueError,'DATE_MISMATCH'):
            store.release('SGEN_FIXTURE','2023-12-15',F(0),F(458))
        self.assertEqual(store.release('SGEN_FIXTURE','2023-12-14',F(0),F(458)),(F(458),F(0)))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_SETTLEMENT'):
            store.release('SGEN_FIXTURE','2023-12-14',F(458),F(0))

    def test_non_cash_or_unentitled_release_rejected(self):
        store=Settlement(self.days,[self.event],0)
        with self.assertRaisesRegex(ValueError,'NO_ENTITLED'):
            store.release('SGEN_FIXTURE','2023-12-14',F(0),F(458))
        with self.assertRaisesRegex(ValueError,'POSITIVE_ENTITLED'):
            store.accrue(self.event,0)
        with self.assertRaisesRegex(ValueError,'BINDING_REQUIRED'):
            store.accrue(dict(self.event,type='split'),2)

    def test_no_merger_preserves_original_book_exactly(self):
        arguments = dict(session_dates=self.days, initial_cash='1000',
                         ohlc={'B': {d: dict(open='229', high='230', low='228', close='229')
                                     for d in self.days}}, fee_bps='0', slippage_bps='5',
                         orders=[dict(id='initial', security_id='B', side='BUY', quantity=2,
                                      decision_mark='229', decision_date=self.days[0],
                                      active_date=self.days[1])])
        original = run_next_open_book(**arguments)
        actual = run_book(settlement_delay=5, **arguments)
        self.assertEqual(actual.pop('cash_merger_settlement')['releases'], [])
        self.assertEqual(actual, original)

    def test_payment_beyond_window_remains_receivable(self):
        store = Settlement(self.days[:3], [self.event], 5)
        store.accrue(self.event, 2)
        for day in self.days[:3]:
            self.assertEqual(store.close(day, F(0), F(458)), (F(0), F(458)))
        self.assertEqual(store.log, [])
        with self.assertRaisesRegex(ValueError, 'FIXED_DELAY'):
            Settlement(self.days, [self.event], True)


if __name__=='__main__':unittest.main()
