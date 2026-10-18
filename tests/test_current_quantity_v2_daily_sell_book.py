import unittest
from backtest.current_quantity_v2_daily_sell_book import run_daily_sell_book
from backtest.current_quantity_v2_next_open_book import run_next_open_book

class SellBookTests(unittest.TestCase):
    def args(self):
        dates=['2026-01-02','2026-01-05','2026-01-06','2026-01-07','2026-01-08','2026-01-09','2026-01-12']
        bars={d:dict(open='10',high='12',low='9',close='10') for d in dates}
        return dict(session_dates=dates,orders=[dict(id='sell',security_id='A',side='SELL',quantity=10,decision_mark='10',decision_date=dates[-2],active_date=dates[-1])],ohlc={'A':bars},initial_cash='0',initial_shares={'A':10},fee_bps='0',slippage_bps='0')
    def test_baseline_split_matches_old_book(self):
        a=self.args();day=a['session_dates'][-1];a['events']=[dict(date=day,security_id='A',type='split',new_shares=2,old_shares=1,source_references=['official'])];a['ohlc']['A'][day]=dict(open='5',high='6',low='4',close='5')
        old=run_next_open_book(**a);new=run_daily_sell_book(**a,mode='BASELINE_OPEN')
        self.assertEqual(new['status'],'COMPLETE')
        for key in ('cash','shares','fees','daily_ledger'):self.assertEqual(new[key],old[key])
        self.assertEqual(new['cash'],'100')
    def test_premium_execution_or_history_split_blocks(self):
        for index in (-1,-3):
            a=self.args();a['events']=[dict(date=a['session_dates'][index],security_id='A',type='split',new_shares=2,old_shares=1,source_references=['official'])]
            r=run_daily_sell_book(**a,mode='PREMIUM_DAY');self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['reason'],'PREMIUM_ACTION_WINDOW_UNIT_UNCERTAIN')
    def test_premium_causal_limit_and_no_current_high_funding(self):
        a=self.args();day=a['session_dates'][-1];a['ohlc']['B']={d:dict(open='10',high='10',low='10',close='10') for d in a['session_dates']};a['orders'].append(dict(id='buy',security_id='B',side='BUY',quantity=10,decision_mark='10',decision_date=a['session_dates'][-2],active_date=day))
        r=run_daily_sell_book(**a,mode='PREMIUM_DAY');self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['shares']['B'],0);self.assertEqual(r['cash'],'115')
        a['ohlc']['A'][day]['high']='100';s=run_daily_sell_book(**a,mode='PREMIUM_DAY')
        limits=lambda z:[x['limit'] for x in z['order_log'] if x['event']=='PREMIUM_LIMIT_FROZEN']
        self.assertEqual(limits(r),limits(s));self.assertEqual(limits(r),['23/2'])
    def test_missing_history_not_baseline_requirement(self):
        a=self.args();a['session_dates']=a['session_dates'][-2:]
        r=run_daily_sell_book(**a,mode='PREMIUM_DAY');self.assertEqual(r['reason'],'PREMIUM_SIX_COMPLETED_SESSIONS_REQUIRED')
        self.assertEqual(run_daily_sell_book(**a,mode='BASELINE_OPEN')['status'],'COMPLETE')

if __name__=='__main__':unittest.main()
