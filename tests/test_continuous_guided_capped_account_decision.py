from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import unittest
import test_continuous_guided_half_next_open as fixture
from backtest.continuous_guided_capped_account_decision import decide_capped_account
from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest import continuous_guided_account_decision as selector

class CappedAccountTests(unittest.TestCase):
 def test_real_second_month_search_uses_capped_branch_wealth(self):
  a,bars,_=fixture.GuidedHalfTests().data();day=a['session_dates'][2]
  second=deepcopy(a['monthly_inputs'][0]);second['decision_date']=day
  second['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'A':a['close_prices']['A'][day]})
  second['valuation_quotes'][0].update(as_of=day,price=a['close_prices']['A'][day]);a['monthly_inputs'].append(second)
  calls=[];audit=[]
  def decide(**kw):calls.append(deepcopy(kw));return decide_capped_account(**kw)
  provider=build_cost_monthly_quantity_provider(session_dates=a['session_dates'],monthly_inputs=a['monthly_inputs'],close_prices=a['close_prices'],actions=a['provider_actions'],decide=decide)
  def execute(**kw):
   r=provider(**kw)
   if r['status']!='READY':return r
   orders=[]
   for sid in sorted(set(r['target_shares'])|set(kw['state']['shares'])):
    q=r['target_shares'].get(sid,0)-kw['state']['shares'].get(sid,0)
    if q:orders.append(dict(id=kw['decision_date']+sid,security_id=sid,side='BUY' if q>0 else 'SELL',quantity=abs(q),decision_date=kw['decision_date'],active_date=kw['active_date'],decision_mark=a['close_prices'][sid][kw['decision_date']]))
   r.update(orders=orders,reserved_cash='0',unreserved_cash=kw['state']['cash']);audit.append(deepcopy(r));return r
  with patch.object(selector,'original_search',wraps=selector.original_search) as search:
   result=run_next_open_book(session_dates=a['session_dates'],ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5',order_provider=execute,events=a['actions'])
  self.assertEqual(result['status'],'COMPLETE');self.assertEqual(search.call_count,2)
  ledger=next(r for r in result['daily_ledger'] if r['date']==day);state=calls[1]['account_state']
  self.assertEqual((state['cash'],state['shares']),(ledger['cash'],ledger['shares']))
  equity=F(state['cash'])+sum(q*F(a['close_prices'][s][day]) for s,q in state['shares'].items())
  self.assertEqual(F(search.call_args_list[1].kwargs['entered_cash']),equity);self.assertNotEqual(equity,1000)
  for r in audit:
   selection=r.get('selection')
   if not selection:continue
   raw=selection['raw_selection'];self.assertNotEqual(selection['target_quantities'],raw['target_quantities'])
   for sid,q in selection['target_quantities'].items():
    self.assertLessEqual(q*F(a['close_prices'][sid][r['target_decision_date']]),F(selection['investable_equity'])/2)
  print('CAP_ACCOUNT: two real searches; second search budget='+str(equity)+'; own cash/holdings; original decision preserved')
