import unittest
from backtest.current_quantity_v2_next_open_book import run_next_open_book as old
from backtest.historical_dividend_next_open_book_research import run_next_open_book as new

class Integration(unittest.TestCase):
    def args(self):
        days=['2020-03-02','2020-03-03','2020-03-04','2020-03-05']
        bars={s:{d:dict(open='10',high='10',low='10',close='10') for d in days} for s in ['A','B']}
        orders=[dict(id='sell',security_id='A',side='SELL',quantity=10,decision_mark='10',decision_date=days[0],active_date=days[1]),dict(id='buy',security_id='B',side='BUY',quantity=11,decision_mark='10',decision_date=days[0],active_date=days[1]),dict(id='reinvest',security_id='B',side='BUY',quantity=1,decision_mark='10',decision_date=days[2],active_date=days[3])]
        return dict(session_dates=days,orders=orders,ohlc=bars,initial_cash='0',initial_shares={'A':10},fee_bps='0',slippage_bps='0')
    def event(self):
        return dict(event_id='d',security_id='A',ex_date='2020-03-03',payment_date='2020-03-04',amount_per_share='1',withholding_rate='0',assumption='gross research',currency='USD')
    def test_zero_dividend_identical_nonempty(self):
        self.assertEqual(new(**self.args()),old(**self.args()))
    def test_cash_not_spent_until_paid_and_sold_entitlement(self):
        result=new(**self.args(),dividend_events=[self.event()])
        self.assertEqual(result['status'],'COMPLETE')
        rows=result['daily_ledger']
        self.assertEqual(rows[0]['shares']['B'],10)
        self.assertEqual(rows[0]['dividend_receivable'],'10')
        self.assertEqual(rows[1]['cash'],'10')
        self.assertEqual(rows[2]['shares']['B'],11)
        self.assertEqual(rows[2]['equity'],'110')
    def test_unknown_date_never_reinvests(self):
        event=self.event();event['payment_date']=None
        result=new(**self.args(),dividend_events=[event])
        self.assertEqual(result['shares']['B'],10)
        self.assertEqual(result['cash'],'0')
        self.assertEqual(result['daily_ledger'][-1]['equity'],'110')
    def test_split_no_dividend_path_identical(self):
        args=self.args();args['orders']=[]
        args['events']=[dict(date='2020-03-03',security_id='A',type='split',new_shares=2,old_shares=1,source_references=['fixture'])]
        self.assertEqual(new(**args),old(**args))
        self.assertEqual(new(**args)['shares']['A'],20)

    def test_invalid_or_outside_events_rejected(self):
        for changes in [dict(ex_date='not-a-date'),dict(payment_date='20200304'),dict(amount_per_share='-100'),dict(ex_date='2020-03-01'),dict(ex_date='2020-03-07')]:
            event=self.event();event.update(changes)
            with self.assertRaises(ValueError):
                new(**self.args(),dividend_events=[event])
        args=self.args();args['session_dates']=['2020-03-02','2020-03-05']
        args['orders']=[]
        with self.assertRaisesRegex(ValueError,'NOT_SESSION'):
            new(**args,dividend_events=[self.event()])

    def test_blocked_retains_accrued_state(self):
        args=self.args();del args['ohlc']['B']['2020-03-04']
        result=new(**args,dividend_events=[self.event()])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['dividend_ledger']['receivable'],'10')
        self.assertEqual(result['total_receivable'],'10')
        self.assertEqual(result['dividend_receivable'],'10')
        self.assertEqual(result['daily_ledger'][-1]['equity'],'110')

    def test_successor_action_overlap_rejected(self):
        args=self.args();args['orders']=[]
        args['events']=[dict(date='2020-03-03',security_id='B',new_security_id='A',type='split_identity',new_shares=1,old_shares=1,source_references=['fixture'])]
        result=new(**args,dividend_events=[self.event()])
        self.assertEqual(result['reason'],'DIVIDEND_SIMULTANEOUS_ACTION_UNSUPPORTED')
