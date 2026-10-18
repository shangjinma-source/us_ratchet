import unittest
from backtest.return_priority_limit_book_v4 import run_limit_book_v4
D=['2026-01-01','2026-01-02','2026-01-05']
def bar(p):return dict(open=p,high=p,low=p,close=p)
def event(timing):return dict(event_id='spin',effective_date=D[1],timing=timing,parent_sid='P',post_parent_sid='P',child_sid='C',child_ratio='1/2',parent_ratio='1',eligibility_rule='ACTUAL_HOLDINGS_IMMEDIATELY_BEFORE_EVENT',eligibility_confirmed=True,ordered_steps_confirmed=True,parent_delivered_units_confirmed=True,source_references=['official'])
class DistributionBookTests(unittest.TestCase):
 def runbook(self,timing,**kw):
  args=dict(session_dates=D,orders=[],ohlc={'P':{D[1]:bar('100' if timing=='AFTER_CLOSE' else '90'),D[2]:bar('90')},'C':{D[1]:bar('20'),D[2]:bar('20')}},initial_cash='0',initial_shares={'P':2},distribution_events=[event(timing)],price_source_references={'P':['raw'],'C':['raw']})
  args.update(kw);return run_limit_book_v4(**args)
 def test_after_close_uses_pre_event_snapshot_next_day_rights(self):
  r=self.runbook('AFTER_CLOSE');self.assertEqual(r['status'],'COMPLETE')
  self.assertEqual([x['equity'] for x in r['daily_ledger']],['200','200'])
  self.assertEqual(r['daily_ledger'][0]['distribution_rights'],[])
  self.assertEqual(r['daily_ledger'][0]['valuation_phase'],'REGULAR_CLOSE_BEFORE_AFTER_HOURS_ACTION')
  self.assertIsNone(r['after_close_records'][0]['post_event_equity']);self.assertTrue(r['terminal_state_valuation_synchronized'])
 def test_terminal_after_close_not_post_event_wealth(self):
  r=self.runbook('AFTER_CLOSE',session_dates=D[:2]);self.assertFalse(r['terminal_state_valuation_synchronized'])
  self.assertEqual(r['final_wealth_basis'],'REGULAR_CLOSE_BEFORE_AFTER_HOURS_ACTION');self.assertEqual(r['daily_ledger'][-1]['equity'],'200');self.assertEqual(len(r['distribution_rights']),1)
 def test_before_open_and_cancel_reserved_order_no_cash_credit(self):
  order=dict(id='buy',security_id='P',decision_date=D[0],active_date=D[1],quantity=1,limit='100',side='BUY')
  r=self.runbook('BEFORE_OPEN',orders=[order],initial_cash='100')
  self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['cash'],'100');self.assertEqual(r['shares']['P'],2)
  self.assertEqual(r['daily_ledger'][0]['equity'],'300')
  self.assertTrue(any(x['event']=='CANCELLED_DISTRIBUTION_SESSION' for x in r['order_log']))
 def test_provider_waits_for_post_action_mark_without_search(self):
  from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
  calls=[]
  def decide(**kw):calls.append(1);return dict(investable_equity='200',target_quantities={'P':2})
  p=build_monthly_quantity_provider_v4(session_dates=D,monthly_inputs=[dict(decision_date=D[0],valuation_quotes=[dict(security_id='P',price='100')],search_arguments={'fee_bps':0},source_hashes={})],close_prices={'P':{D[0]:'100'}},actions=[dict(date=D[1],security_id='P',post_parent_sid='P',type='distribution',parent_ratio='1',source_references=['official'])],decide=decide)
  audit=[]
  def callback(**kw):
   r=p(**kw);audit.append(r);return r
  r=self.runbook('AFTER_CLOSE',orders=None,order_provider=callback)
  self.assertEqual(r['status'],'COMPLETE');self.assertEqual(len(calls),1)
  self.assertEqual(audit[1]['action'],'WAIT_POST_ACTION_MARK');self.assertEqual(audit[1]['orders'],[])

 def test_wrong_eligibility_and_missing_child_mark_block(self):
  r=self.runbook('BEFORE_OPEN',distribution_events=[dict(event('BEFORE_OPEN'),eligible_parent_quantity=3)]);self.assertEqual(r['reason'],'ELIGIBILITY_QUANTITY_MISMATCH')
  r=self.runbook('BEFORE_OPEN',ohlc={'P':{D[1]:bar('90')}});self.assertEqual(r['reason'],'DISTRIBUTION_VALUATION_BLOCKED');self.assertEqual(len(r['distribution_rights']),1)
  self.assertFalse(r['terminal_state_valuation_synchronized']);self.assertEqual(r['final_wealth_basis'],'NO_VALIDATED_CLOSE');self.assertIsNone(r['last_valued_date'])
 def test_failure_after_prior_close_does_not_claim_current_valuation(self):
  r=self.runbook('BEFORE_OPEN',ohlc={'P':{D[1]:bar('90'),D[2]:bar('90')},'C':{D[1]:bar('20')}})
  self.assertEqual(r['status'],'BLOCKED');self.assertFalse(r['terminal_state_valuation_synchronized'])
  self.assertEqual(r['last_valued_date'],D[1]);self.assertEqual(r['final_wealth_basis'],'LAST_VALIDATED_CLOSE_ONLY')
 def test_after_close_distribution_keeps_regular_session_trading(self):
  order=dict(id='buy',security_id='P',decision_date=D[0],active_date=D[1],quantity=1,limit='100',side='BUY')
  r=self.runbook('AFTER_CLOSE',session_dates=D[:2],orders=[order],initial_cash='100',initial_shares={'P':1})
  self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['cash'],'0');self.assertEqual(r['shares']['P'],2)
  self.assertEqual(r['distribution_rights'][0]['units'],'1')
  self.assertEqual(r['daily_ledger'][0]['equity'],'200')
  self.assertFalse(any(x['event']=='CANCELLED_DISTRIBUTION_SESSION' for x in r['order_log']))
if __name__=='__main__':unittest.main()
