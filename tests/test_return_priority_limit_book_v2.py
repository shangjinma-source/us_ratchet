import unittest
from backtest.return_priority_limit_book_v2 import run_limit_book_v2, combine_split_identity_events
from backtest.return_priority_monthly_quantity_provider_v2 import build_monthly_quantity_provider_v2

D=['2024-09-30','2024-10-01','2024-10-02']
E=dict(date=D[1],security_id='old',new_security_id='new',type='split_identity',new_shares=10,old_shares=1,source_references=['official'])
def bar(p): return dict(open=p,high=p,low=p,close=p)
class IdentityTests(unittest.TestCase):
    def test_shares_and_active_order_once(self):
        order=dict(id='sell',security_id='old',decision_date=D[0],active_date=D[1],side='SELL',quantity=1,limit='100')
        r=run_limit_book_v2(session_dates=D,orders=[order],ohlc={'new':{d:bar('10') for d in D[1:]}},initial_cash='0',initial_shares={'old':2},events=[E])
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['shares'],{'old':0,'new':10});self.assertEqual(r['cash'],'100')
        fills=[x for x in r['order_log'] if x['event']=='ASSUMED_FILLED'];self.assertEqual(fills[0]['quantity'],10);self.assertEqual(fills[0]['security_id'],'new')
    def test_provider_target_wait_migrates_not_actual_twice(self):
        def decide(**kw):return dict(investable_equity='200',target_quantities={'old':2})
        p=build_monthly_quantity_provider_v2(session_dates=D,monthly_inputs=[dict(decision_date=D[0],search_arguments={'fee_bps':0},valuation_quotes=[dict(security_id='old',price='100')],source_hashes={})],close_prices={'old':{D[0]:'100'},'new':{D[1]:'10'}},actions=[E],decide=decide)
        audit=[]
        def cb(**kw):r=p(**kw);audit.append(r);return r
        r=run_limit_book_v2(session_dates=D,order_provider=cb,ohlc={'new':{d:bar('10') for d in D[1:]}},initial_cash='200',events=[E])
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['shares']['new'],20)
        self.assertEqual(audit[1]['target_shares'],{'new':20});self.assertEqual(audit[1]['orders'],[])
    def test_conflict_duplicate_fraction_and_mixed_fail_closed(self):
        base=dict(session_dates=D,orders=[],ohlc={},initial_cash='0',initial_shares={'old':1})
        self.assertEqual(run_limit_book_v2(**dict(base,initial_shares={'old':1,'new':1}),events=[E])['reason'],'SUCCESSOR_POSITION_OR_ORDER_CONFLICT')
        self.assertEqual(run_limit_book_v2(**base,events=[E,dict(E,type='split')])['reason'],'SIMULTANEOUS_EVENTS_REQUIRE_RESOLUTION')
        self.assertEqual(run_limit_book_v2(**base,events=[dict(E,new_shares=1,old_shares=2)])['reason'],'FRACTIONAL_SPLIT_HOLDING')
        self.assertEqual(run_limit_book_v2(**base,events=[dict(E,type='cash_stock_merger')])['reason'],'CASH_STOCK_ENTITLEMENT_ENGINE_NOT_CONNECTED')
    def test_old_security_cannot_reappear(self):
        o=dict(id='late',security_id='old',decision_date=D[1],active_date=D[2],side='BUY',quantity=1,limit='10')
        r=run_limit_book_v2(session_dates=D,orders=[o],ohlc={},initial_cash='100',events=[E])
        self.assertEqual(r['reason'],'TERMINATED_SECURITY_ORDER')
    def test_combine_deduplicates_economic_split_future_payload_not_read(self):
        split={k:v for k,v in E.items() if k not in ('type','new_security_id')}
        migration=dict(date=D[1],old_sid='old',new_sid='new',new_shares=10,old_shares=1,source_references=['identity'])
        r=combine_split_identity_events(split_events=[split,{'date':'2099-01-01'}],identity_migrations=[migration,{'date':'2099-01-01'}],start_date=D[0],end_date=D[-1])
        self.assertEqual(len(r),1);self.assertEqual(r[0]['type'],'split_identity')
        with self.assertRaisesRegex(ValueError,'RATIO_CONFLICT'):
            combine_split_identity_events(split_events=[split],identity_migrations=[dict(migration,new_shares=2)],start_date=D[0],end_date=D[-1])

if __name__=='__main__':unittest.main()
