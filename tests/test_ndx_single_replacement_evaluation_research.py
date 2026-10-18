import unittest
from copy import deepcopy
from decimal import localcontext,Inexact
from fractions import Fraction as F
from unittest.mock import patch
from test_ndx_single_replacement_domain_research import fixture
from backtest import ndx_single_replacement_domain_research as d
from backtest import ndx_single_replacement_evaluation_research as m

def case():
    a=fixture();p=d.prepare_single_replacement_domain(**a)
    plans=[dict(global_ordinal=i,task=d.unrank(p,i)) for i in range(p['document']['integer_count'])]
    return dict(prepared=p,registered_plans=plans,max_evaluations=10000)

class Tests(unittest.TestCase):
 def test_validated_projection_equals_frozen_domain_without_repeated_hash(self):
    a=case();validated=m.validate_prepared(a['prepared'])
    for i in range(a['prepared']['document']['integer_count']):
     self.assertEqual(m.project_validated_task(validated,i),d.unrank(a['prepared'],i))
    # Mutation of caller's prepared rows cannot alter the checked isolated state.
    a['prepared']['document']['cases'][0]['identity']['original_input_row']['holdings']['A']=999
    self.assertEqual(m.project_validated_task(validated,0)['identity']['sell_quantity'],2)
    a=case();original_checked=d.checked
    with patch.object(d,'unrank',side_effect=AssertionError('No repeated unrank/hash')),patch.object(d,'checked',wraps=original_checked) as checked:
     out=m.evaluate_explicit_single_replacement_plans(**a)
    self.assertEqual(checked.call_count,1)
    self.assertEqual(out['completed_evaluation_count'],len(a['registered_plans']))

 def test_hand_finance_l1_original_target_and_no_mutation(self):
    a=case();before=deepcopy(a)
    with localcontext() as c:
     c.prec=2;c.traps[Inexact]=True;o=m.evaluate_explicit_single_replacement_plans(**a)
    self.assertEqual(a,before);v=o['results'][0]['evaluation']
    # Sell A2 at10, buy C1 at5; B1 at20 stays. Cash110+20-5-.025.
    self.assertEqual(F(v['cash_after_usd']),F('124.975'))
    self.assertEqual(F(v['equity_after_usd']),F('149.975'))
    self.assertEqual(F(v['total_fee_usd']),F('0.025'))
    self.assertEqual(F(v['cash_flow_adjusted_pnl_usd']),F('-0.025'))
    self.assertEqual(v['risk']['weights'],{'B':'4/5','C':'1/5'})
    self.assertEqual(F(v['original_target_stock_l1']),F('1.6'))
    self.assertEqual(o['counts']['FEASIBLE']+o['counts']['INFEASIBLE'],o['supplied_plan_count'])
    self.assertTrue(all(o[k] is False for k in m.FLAGS))

 def test_all_suffix_validated_rehashed_preparation_not_trusted(self):
    for attack in ('rankbool','duplicate','sellpartial','retained','rehashed'):
     a=case();a['max_evaluations']=0
     if attack=='rankbool':a['registered_plans'][-1]['global_ordinal']=True
     elif attack=='duplicate':a['registered_plans'][-1]=deepcopy(a['registered_plans'][0])
     elif attack=='sellpartial':a['registered_plans'][-1]['task']['signed_trade_quantities']['B']=0
     elif attack=='retained':a['registered_plans'][-1]['task']['proposed_holdings']['ZERO']=1
     else:
      a['prepared']['document']['integer_count']+=1
      a['prepared']['content_sha256']=d.digest(a['prepared']['document'])
     with self.subTest(attack=attack),self.assertRaises(ValueError):m.evaluate_explicit_single_replacement_plans(**a)

 def test_budget_and_exception_preserve_complete_partition(self):
    a=case();a['max_evaluations']=1;o=m.evaluate_explicit_single_replacement_plans(**a)
    self.assertEqual(o['counts']['NOT_EVALUATED_BUDGET'],len(a['registered_plans'])-1)
    real=m.evaluate_one;calls=[]
    def flaky(row,task):
     calls.append(task['task_id'])
     if len(calls)==2:raise RuntimeError('original synthetic failure')
     return real(row,task)
    a=case()
    with patch.object(m,'evaluate_one',side_effect=flaky):o=m.evaluate_explicit_single_replacement_plans(**a)
    self.assertEqual(len(calls),2);self.assertEqual(o['status'],'TECHNICAL_STOP')
    self.assertEqual(o['results'][1]['error'],dict(type='RuntimeError',message='original synthetic failure'))
    self.assertEqual(o['results'][1]['plan'],a['registered_plans'][1])
    self.assertEqual(o['counts']['NOT_EVALUATED_TECHNICAL_STOP'],len(a['registered_plans'])-2)

 def test_frozen_risk_semantics_and_exact_tolerance_boundary(self):
    from backtest import ndx_conditional_new_cash_fork_research as old
    a=case();o=m.evaluate_explicit_single_replacement_plans(**a)
    row=a['prepared']['document']['cases'][0]['identity']['original_input_row']
    marks={s:F(v) for s,v in row['execution_prices'].items()};params={k:F(v) for k,v in row['risk_parameters'].items()}
    for r in o['results']:
     risk=old._risk(r['plan']['task']['proposed_holdings'],marks,row['securities'],params)
     for k in ('checks','all_passed','weights','effective_n','positive_holding_count'):self.assertEqual(r['evaluation']['risk'][k],risk[k])
    holdings={'A':1,'B':1};securities={s:dict(risk_chain=s) for s in holdings}
    p=dict(max_single_weight=F('0.5'),min_single_weight=F('0.1'),top_weight_cap=F(1),minimum_effective_n_ratio=F('0.5'),risk_chain_top1_cap=F(1))
    for extra,expected in [(F(1,10**9),True),(F(1001,10**12),False)]:
     w=F(1,2)+extra;r=m.risk_snapshot(holdings,{'A':w,'B':1-w},securities,p)
     self.assertIs(r['checks']['MAX_SINGLE_WEIGHT'],expected)

if __name__=='__main__':unittest.main()
