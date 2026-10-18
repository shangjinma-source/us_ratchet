import unittest
from copy import deepcopy
from backtest.return_priority_ads_conversion import convert_dtc_ads, ACCOUNT_MODEL
from backtest.return_priority_limit_book_v4 import run_limit_book_v4
D=['2026-01-30','2026-02-02','2026-02-03']
def event():return dict(type='ads_conversion',date=D[1],event_id='azn',security_id='ads',new_security_id='ordinary',new_shares='1',old_shares='2',delivery_model=ACCOUNT_MODEL,source_references=['official','modelpolicy'])
def bar(p):return dict(open=p,high=p,low=p,close=p)
class ConversionTests(unittest.TestCase):
 def book(self,q,**kw):
  args=dict(session_dates=D,orders=[],initial_cash='100',initial_shares={'ads':q},ohlc={'ordinary':{D[1]:bar('200'),D[2]:bar('210')}},events=[event()],account_model=ACCOUNT_MODEL,price_source_references={'ordinary':['raw']})
  args.update(kw);return run_limit_book_v4(**args)
 def test_even_conserves_cash_and_cancels_old_day(self):
  order=dict(id='b',security_id='ads',decision_date=D[0],active_date=D[1],side='BUY',quantity=1,limit='100')
  r=self.book(4,orders=[order]);self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['shares'],{'ads':0,'ordinary':2});self.assertEqual(r['cash'],'100');self.assertEqual(r['daily_ledger'][0]['equity'],'500');self.assertTrue(any(x['event']=='CANCELLED_ADS_CONVERSION' for x in r['order_log']))
 def test_odd_keeps_fraction_and_blocks_valuation(self):
  r=self.book(3);self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['shares']['ordinary'],1);self.assertEqual(r['distribution_rights'][0]['units'],'1/2');self.assertEqual(r['cash'],'100');self.assertFalse(r['terminal_state_valuation_synchronized'])
 def test_model_required_and_duplicate_refused(self):
  r=self.book(2,account_model=None);self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['shares']['ads'],2)
  st=dict(cash='100',shares={'ads':2},distribution_rights=[])
  changed=convert_dtc_ads(state=st,event=event(),as_of=D[1],account_model=ACCOUNT_MODEL)
  with self.assertRaises(ValueError):convert_dtc_ads(state=changed,event=event(),as_of=D[1],account_model=ACCOUNT_MODEL)
  self.assertEqual(st['shares'],{'ads':2})
 def test_terminated_future_buy_and_future_payload(self):
  o=dict(id='old',security_id='ads',decision_date=D[1],active_date=D[2],side='BUY',quantity=1,limit='100')
  r=self.book(0,orders=[o]);self.assertEqual(r['reason'],'TERMINATED_SECURITY_ORDER')
  r=self.book(2,events=[event(),{'date':'2027-01-01'}]);self.assertEqual(r['status'],'COMPLETE')
 def test_same_day_successor_action_blocks_before_conversion(self):
  other=dict(date=D[1],security_id='ordinary',type='split',new_shares=2,old_shares=1,source_references=['other'])
  r=self.book(4,events=[event(),other])
  self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['reason'],'OVERLAPPING_ADS_SUCCESSOR_ACTION')
  self.assertEqual(r['shares'],{'ads':4});self.assertEqual(r['cash'],'100');self.assertEqual(r['distribution_rights'],[])
 def test_target_floor_not_asset_and_daily_no_search(self):
  from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
  calls=[]
  def decide(**kwargs):calls.append(1);return dict(investable_equity='500',target_quantities={'ads':3})
  p=build_monthly_quantity_provider_v4(session_dates=D,monthly_inputs=[dict(decision_date=D[0],valuation_quotes=[dict(security_id='ads',price='100')],search_arguments={'fee_bps':0},source_hashes={})],close_prices={'ads':{D[0]:'100'},'ordinary':{D[1]:'200'}},actions=[event()],decide=decide)
  a=p(decision_date=D[0],active_date=D[1],state=dict(asof=D[0],shares={'ads':4},cash='100'))
  b=p(decision_date=D[1],active_date=D[2],state=dict(asof=D[1],shares={'ads':0,'ordinary':2},cash='100'))
  self.assertEqual(a['status'],'READY');self.assertEqual(b['status'],'READY');self.assertEqual(b['target_shares']['ordinary'],1);self.assertEqual(len(calls),1);self.assertEqual(b['orders'][0]['side'],'SELL');self.assertEqual(b['orders'][0]['quantity'],1)
if __name__=='__main__':unittest.main()
