from copy import deepcopy
from fractions import Fraction as F
import unittest
from backtest.ma9_sma20_half import ma9_sma20_half_target
from backtest.continuous_guided_ma9_sma20_half_next_open import run_cost_ma9_sma20_half_next_open as run
from backtest.continuous_guided_cost_stress import prepare_arm
from test_current_quantity_v2_risk_overlays import fixture
import test_continuous_guided_cost_stress as cost
import test_monthly_latched_half_actions_integration as actions
from test_return_priority_limit_book_v4 import event

class IndependentDualMATests(unittest.TestCase):
 def test_each_exact_equality_suffix_and_noncompounding(self):
  for prices in ([1]*11+[10]*9,[F(200-18,11)]*11+[1]*8+[10]):
   args=fixture({'A':prices},quantities={'A':7});before=deepcopy(args)
   r=ma9_sma20_half_target(**args);self.assertEqual(r['target_quantities']['A'],3)
   d=r['diagnostics']['A'];self.assertEqual(F(d['sma9']),sum(map(F,prices[-9:]))/9)
   self.assertEqual(ma9_sma20_half_target(**args)['target_quantities']['A'],3);self.assertEqual(args,before)

 def test_bad_history_blocks_no_fill(self):
  for fault in ('duplicate','negative','boolean','incomplete','unit'):
   a,b,resolver=cost.CostStressTests().data()
   def bad(**kwargs):
    x=resolver(**kwargs);rows=x['histories']['A']['closes']
    if fault=='duplicate':rows[-2]['date']=rows[-1]['date']
    elif fault=='negative':rows[3]['close']='-1'
    elif fault=='boolean':rows[3]['close']=True
    elif fault=='incomplete':rows[-1]['completed_at']=kwargs['decision_date']+'T15:59:00-05:00'
    else:rows[-1]['close']='999'
    return x
   r=run(assembled=prepare_arm(a,'slippage5'),ohlc=b,initial_cash='1000',fee_bps='0',slippage_bps='5',history_resolver=bad)
   with self.subTest(fault=fault):
    self.assertEqual(r['status'],'BLOCKED');self.assertFalse(any(v['event']=='ASSUMED_NEXT_OPEN_FILLED' for v in r['order_log']))

 def test_future_open_not_in_prior_signal(self):
  a,b,resolver=cost.CostStressTests().data();base=run(assembled=prepare_arm(a,'slippage5'),ohlc=b,initial_cash='1000',fee_bps='0',slippage_bps='5',history_resolver=resolver)
  changed=deepcopy(b);changed['A'][a['session_dates'][1]].update(open='999',high='999')
  other=run(assembled=prepare_arm(a,'slippage5'),ohlc=changed,initial_cash='1000',fee_bps='0',slippage_bps='5',history_resolver=resolver)
  self.assertEqual(base['provider_audit'][0],other['provider_audit'][0])

 def test_real_afterclose_wait_and_split_recovery(self):
  for kind in ('split','afterclose'):
   a,b,resolver,calls=actions.MonthlyLatchedHalfActionsIntegrationTests().fixture();days=a['session_dates']
   if kind=='split':
    action=dict(date=days[2],security_id='A',new_security_id='B',type='split_identity',old_shares=1,new_shares=2,source_references=['official']);a['actions']=[action];a['provider_actions']=[deepcopy(action)]
   else:
    a['distribution_events']=[dict(event('AFTER_CLOSE'),effective_date=days[1],parent_sid='A',post_parent_sid='B',parent_ratio='2',child_ratio='1')]
    a['provider_actions']=[dict(date=days[1],security_id='A',post_parent_sid='B',parent_ratio='2',type='distribution',source_references=['official'])]
   r=run(assembled=a,ohlc=b,initial_cash='1000',fee_bps='0',slippage_bps='5',history_resolver=resolver)
   self.assertEqual(r['status'],'COMPLETE');audits=r['provider_audit'];full=audits[0]['monthly_ceiling']['A'];self.assertEqual(audits[0]['target_shares']['A'],full//2)
   for audit in audits[2:]:self.assertEqual(audit['monthly_ceiling'],{'B':full*2});self.assertEqual(audit['target_shares'],{'B':full*2})
   self.assertTrue(all(F(row['cash'])>=0 for row in r['daily_ledger']))
   if kind=='afterclose':
    self.assertEqual(audits[1]['action'],'WAIT_POST_ACTION_MARK');self.assertEqual(audits[1]['orders'],[]);self.assertNotIn(days[1],[x['decision_date'] for x in calls])

if __name__=='__main__':unittest.main()
