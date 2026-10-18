import unittest
from fractions import Fraction
from backtest.return_priority_limit_book_v3 import run_limit_book_v3
from backtest.return_priority_monthly_quantity_provider_v3 import build_monthly_quantity_provider_v3
D=['2025-07-16','2025-07-17','2025-07-18']
E=dict(event_id='mixed',old_sid='old',new_sid='new',effective_date=D[1],effective_time_confirmed=True,eligibility_confirmed=True,cash_per_share='199.91',new_shares_per_old_share='0.3399',source_references=['official'])
F={'mixed':dict(known_asof=D[1],fraction_reference_close=dict(date=D[0],price='100.01',source_references=['raw']),reference_is_previous_closing_session=True,fraction_cash_rounding='CEIL_CENT',source_references=['contract'])}
def bars(p):return {d:dict(open=p,high=p,low=p,close=p) for d in D}
class MixedBookTests(unittest.TestCase):
    def run_book(self,**kw):
        args=dict(session_dates=D,orders=[],ohlc={'new':bars('100')},initial_cash='50',initial_shares={'old':10,'new':2},cash_stock_merger_events=[E],fractional_settlements=F,price_source_references={'new':['raw']})
        args.update(kw);return run_limit_book_v3(**args)
    def test_split_limit_rounding_direction_reservation_and_cash(self):
        event=dict(date=D[1],security_id='old',type='split',new_shares=10,old_shares=1,source_references=['official'])
        for side,price,cash,hold,expected_cash in [('BUY','10','100.01',{},'0.01'),('SELL','10.01','0',{'old':1},'100.1')]:
            order=dict(id=side,security_id='old',decision_date=D[0],active_date=D[1],side=side,quantity=1,limit='100.01')
            r=run_limit_book_v3(session_dates=D[:2],orders=[order],ohlc={'old':bars(price)},initial_cash=cash,initial_shares=hold,events=[event])
            self.assertEqual(r['status'],'COMPLETE');self.assertEqual(Fraction(r['cash']),Fraction(expected_cash))
            audit=[x for x in r['order_log'] if x['event']=='SPLIT_LIMIT_ADJUSTED'][0]
            self.assertEqual(audit['raw_adjusted_limit'],'10001/1000');self.assertEqual(Fraction(audit['rounded_limit']),Fraction(price))
            self.assertEqual(audit['quantity_after'],10)
            self.assertIn('NOT_BROKER_RULE',r['split_limit_policy'])
        order=dict(id='zero',security_id='old',decision_date=D[0],active_date=D[1],side='BUY',quantity=1,limit='0.01')
        r=run_limit_book_v3(session_dates=D[:2],orders=[order],ohlc={},initial_cash='1',events=[event])
        self.assertEqual(r['reason'],'NONPOSITIVE_ROUNDED_SPLIT_LIMIT');self.assertEqual(r['cash'],'1');self.assertEqual(r['shares'],{})

    def test_same_day_successor_split_explicitly_blocked(self):
        action=dict(date=D[1],security_id='new',type='split',new_shares=2,old_shares=1,source_references=['split'])
        r=self.run_book(events=[action])
        self.assertEqual(r['status'],'BLOCKED')
        self.assertEqual(r['reason'],'ACTION_ON_PENDING_RIGHTS_OR_MIXED_SESSION_UNSUPPORTED')
        self.assertEqual(r['shares'],{'old':10,'new':2})
        self.assertEqual(r['merger_entitlements'],[])

    def test_existing_new_shares_remain_separate_and_no_old_bar_needed(self):
        r=self.run_book()
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['cash'],'50');self.assertEqual(r['shares'],{'old':0,'new':2})
        right=r['merger_entitlements'][0];self.assertEqual(right['pending_whole_shares'],3)
        self.assertEqual(r['rights_valuation']['fractional_cash_receivable'],'3991/100')
        self.assertEqual(Fraction(r['daily_ledger'][-1]['equity']),Fraction('2589.01'))
    def test_event_day_orders_cancelled_reserve_not_cash_credit(self):
        o=dict(id='buy',security_id='old',decision_date=D[0],active_date=D[1],side='BUY',quantity=1,limit='10')
        r=self.run_book(orders=[o],initial_shares={})
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['cash'],'50')
        self.assertFalse(any(x['event']=='ASSUMED_FILLED' for x in r['order_log']))
        self.assertEqual([x for x in r['order_log'] if x['event']=='CANCELLED_CONDITIONAL_MIXED_SESSION'][0]['released_reservation'],'10')
    def test_missing_fraction_reference_preserves_rights_and_blocks(self):
        r=self.run_book(fractional_settlements={});self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['shares']['old'],0);self.assertEqual(r['cash'],'50');self.assertEqual(len(r['merger_entitlements']),1)
    def test_provider_removes_old_target_without_reinvestment(self):
        calls=[]
        def decide(**kw):calls.append(1);return dict(investable_equity='100',target_quantities={'old':1})
        action=dict(date=D[1],security_id='old',type='cash_stock_merger',source_references=['official'])
        p=build_monthly_quantity_provider_v3(session_dates=D,monthly_inputs=[dict(decision_date=D[0],valuation_quotes=[dict(security_id='old',price='100')],search_arguments={'fee_bps':0},source_hashes={})],close_prices={'old':{D[0]:'100'}},actions=[action],decide=decide)
        p(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],cash='0',shares={'old':1}))
        r=p(decision_date=D[1],active_date=D[2],state=dict(asof=D[1],cash='0',shares={'old':0},merger_entitlements=[{'converted_old_shares':1}]))
        self.assertEqual(r['status'],'READY');self.assertEqual(r['target_shares'],{});self.assertEqual(r['orders'],[]);self.assertEqual(len(calls),1)
    def test_monthly_pending_rights_blocks_before_search(self):
        def poison(**kw):raise AssertionError('no search')
        p=build_monthly_quantity_provider_v3(session_dates=D,monthly_inputs=[dict(decision_date=D[0],valuation_quotes=[],search_arguments={'fee_bps':0},source_hashes={})],close_prices={},decide=poison)
        r=p(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],cash='100',shares={},merger_entitlements=[{'converted_old_shares':1}]))
        self.assertEqual(r['reason'],'MONTHLY_RESELECTION_WITH_PENDING_RIGHTS_UNSUPPORTED')

if __name__=='__main__':unittest.main()
