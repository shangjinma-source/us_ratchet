from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction
import unittest
from backtest.paired_sell_execution import construct,paired_evaluate,terminal_values,BASELINE,PREMIUM


def bar(start,high='11',low='9',close='10'):
    t=datetime.fromisoformat(start)
    return dict(security_id='security',ticker='TEST',start=t.isoformat(),end=(t+timedelta(minutes=1)).isoformat(),open='10',high=high,low=low,close=close)


def fixture():
    t=datetime.fromisoformat('2026-10-15T10:00:00-04:00')
    return dict(trigger='MONTHLY_TARGET_REDUCTION',decision_id='decision',security_id='security',ticker='TEST',
        source_reference='synthetic-not-market-evidence',expected_revision='revision',held_shares=10,target_shares=6,sell_quantity=4,
        signal_at=t.isoformat(),accepted_at=t.isoformat(),session_open='2026-10-15T09:30:00-04:00',
        session_close='2026-10-15T10:02:00-04:00',session='2026-10-15',last_trade_at=t.isoformat(),
        last_price='10',last_price_kind='OBSERVED_TRADE',recent_minutes=[bar((t-timedelta(minutes=6-i)).isoformat()) for i in range(6)])


class PairedSellTests(unittest.TestCase):
    def evaluate(self,s,minutes,fees='1'):
        return paired_evaluate(signal=s,minutes=minutes,observed_through=s['session_close'],
                               evaluated_at=s['session_close'],fees=fees,available_cash='5',available_shares=10)

    def test_median_true_range_and_exact_rounding(self):
        s=fixture();s['last_price']='10.001';s['recent_minutes'][3]['high']='1000'
        p=construct(signal=s)
        self.assertEqual(Fraction(p['orders'][BASELINE]['limit_price']),Fraction('10.01'))
        self.assertEqual(Fraction(p['orders'][PREMIUM]['limit_price']),Fraction('11.01'))
        s['recent_minutes'][1].update(high='10',low='10')
        s['recent_minutes'][2].update(high='10',low='10')
        s['recent_minutes'][3].update(high='10',low='10')
        self.assertEqual(construct(signal=s)['orders'][BASELINE]['limit_price'],construct(signal=s)['orders'][PREMIUM]['limit_price'])

    def test_independent_fill_and_expiry_resources(self):
        s=fixture();r=self.evaluate(s,[bar(s['signal_at']),bar('2026-10-15T10:01:00-04:00')])
        self.assertEqual(r['status'],'PAIRED_CONDITIONAL_OUTCOMES')
        a,b=r['branches'][BASELINE],r['branches'][PREMIUM]
        self.assertEqual(a['fill']['status'],'SIMULATED_FILL')
        self.assertEqual(a['resulting_resources']['cash'],'44')
        self.assertEqual(a['resulting_resources']['shares'],6)
        self.assertEqual(b['fill']['status'],'EXPIRE') # exact high touch is not fill
        self.assertEqual(b['resulting_resources']['cash'],'5') # no proceeds or fee charged
        self.assertEqual(b['resulting_resources']['shares'],10)
        self.assertEqual(a['initial_resources'],b['initial_resources'])

    def test_gaps_unknown_not_expired_and_future_prices_do_not_change_signal(self):
        s=fixture();before=construct(signal=s)
        r=self.evaluate(s,[bar('2026-10-15T10:01:00-04:00',high='100')])
        self.assertEqual(r['status'],'UNKNOWN')
        self.assertTrue(all(b['resulting_resources'] is None for b in r['branches'].values()))
        self.assertEqual(before,construct(signal=s))

    def test_partial_acceptance_minute_excluded(self):
        s=fixture();s['accepted_at']='2026-10-15T10:00:30-04:00'
        r=self.evaluate(s,[bar(s['signal_at'],high='100'),bar('2026-10-15T10:01:00-04:00',high='10',low='10')])
        self.assertTrue(all(b['fill']['status']=='EXPIRE' for b in r['branches'].values()))

    def test_wrong_security_and_reserved_shares_refused(self):
        s=fixture();minutes=[bar(s['signal_at'],high='100')]
        minutes[0]['ticker']='OTHER'
        self.assertEqual(self.evaluate(s,minutes)['status'],'UNKNOWN')
        s['recent_minutes'][0]['security_id']='OTHER'
        self.assertEqual(self.evaluate(s,[])['status'],'UNKNOWN')
        s=fixture();minutes=[bar(s['signal_at'],high='100')]
        result=paired_evaluate(signal=s,minutes=minutes,observed_through=s['session_close'],
                              evaluated_at=s['session_close'],fees='0',available_cash='5',available_shares=3)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['branches'],{})
        # Even a complete noncrossing day cannot turn an invalid order into expiry.
        minutes=[bar(s['signal_at'],high='10',low='10'),bar('2026-10-15T10:01:00-04:00',high='10',low='10')]
        result=paired_evaluate(signal=s,minutes=minutes,observed_through=s['session_close'],
                              evaluated_at=s['session_close'],fees='0',available_cash='5',available_shares=3)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['branches'],{})

    def test_identity_isolation_input_immutability_and_unknown_boundaries(self):
        s=fixture();before=deepcopy(s);first=construct(signal=s)
        other=deepcopy(s);other['security_id']='second'
        for row in other['recent_minutes']:row['security_id']='second'
        self.assertNotEqual(first['orders'][BASELINE]['order_id'],construct(signal=other)['orders'][BASELINE]['order_id'])
        later=deepcopy(s)
        for key in ('session','signal_at','accepted_at','session_open','session_close','last_trade_at'):
            later[key]=later[key].replace('2026-10-15','2026-10-16')
        for row in later['recent_minutes']:
            for key in ('start','end'):row[key]=row[key].replace('2026-10-15','2026-10-16')
        self.assertNotEqual(first['orders'][BASELINE]['order_id'],construct(signal=later)['orders'][BASELINE]['order_id'])
        minutes=[bar(s['signal_at'],high='100')];saved=deepcopy(minutes)
        r=self.evaluate(s,minutes,fees='1000')
        self.assertEqual(r['status'],'UNKNOWN')
        self.assertEqual(s,before);self.assertEqual(minutes,saved)
        r=paired_evaluate(signal=s,minutes=minutes,observed_through=s['session_close'],
            evaluated_at=s['signal_at'],fees='0',available_cash='5',available_shares=10)
        self.assertEqual(r['status'],'UNKNOWN')

    def test_noncausal_history_or_unissued_reduction_refused(self):
        for change in ('future','gap','stale','urgent','quantity','missing'):
            s=fixture()
            if change=='future':s['recent_minutes'][-1]=bar(s['signal_at'])
            if change=='gap':s['recent_minutes'][0]=deepcopy(s['recent_minutes'][1])
            if change=='stale':s['last_trade_at']='2026-10-15T09:57:00-04:00'
            if change=='urgent':s['trigger']='URGENT_EXIT'
            if change=='quantity':s['sell_quantity']=5
            if change=='missing':del s['last_trade_at']
            with self.subTest(change=change):self.assertEqual(self.evaluate(s,[])['status'],'UNKNOWN')

    def test_terminal_mark_includes_unfilled_inventory_and_is_not_cash(self):
        s=fixture()
        close=bar('2026-10-15T10:01:00-04:00',low='8',close='8')
        close['source_reference']='synthetic-close'
        close['observed_at']=s['session_close']
        pair=self.evaluate(s,[bar(s['signal_at']),close])
        saved=deepcopy(pair)
        result=terminal_values(paired=pair,close_bar=close,evaluated_at=s['session_close'])
        self.assertEqual(result['status'],'PAIRED_TERMINAL_VALUES')
        self.assertEqual(result['branches'][BASELINE]['cash_plus_inventory'],'92')
        self.assertEqual(result['branches'][PREMIUM]['cash_plus_inventory'],'85')
        self.assertEqual(result['branches'][PREMIUM]['cash'],'5')
        self.assertEqual(result['premium_minus_baseline'],'-7')
        self.assertIsNone(result['economic_winner'])
        self.assertEqual(pair,saved)
        rising=deepcopy(close);rising['close']='10.5'
        rising_pair=self.evaluate(s,[bar(s['signal_at']),rising])
        rising_result=terminal_values(paired=rising_pair,close_bar=rising,evaluated_at=s['session_close'])
        self.assertEqual(rising_result['premium_minus_baseline'],'3')
        self.assertIsNone(rising_result['economic_winner'])

    def test_terminal_values_require_complete_pair_and_explicit_final_mark(self):
        s=fixture()
        pair=self.evaluate(s,[bar(s['signal_at']),bar('2026-10-15T10:01:00-04:00')])
        close=bar('2026-10-15T10:01:00-04:00');close['source_reference']='synthetic-close'
        close['observed_at']=s['session_close']
        for change in ('identity','time','source','ohlc','early','incomplete','late_capture'):
            p,b=deepcopy(pair),deepcopy(close);at=s['session_close']
            if change=='identity':b['ticker']='OTHER'
            if change=='time':b['end']=s['signal_at']
            if change=='source':b['source_reference']=''
            if change=='ohlc':b['close']='0'
            if change=='early':at=s['signal_at']
            if change=='incomplete':p['status']='UNKNOWN'
            if change=='late_capture':b['observed_at']='2026-10-15T10:03:00-04:00'
            with self.subTest(change=change):
                result=terminal_values(paired=p,close_bar=b,evaluated_at=at)
                self.assertEqual(result['status'],'UNKNOWN')
                self.assertEqual(result['branches'],{})

if __name__=='__main__':unittest.main()
