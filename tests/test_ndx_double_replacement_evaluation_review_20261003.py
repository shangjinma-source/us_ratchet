from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from test_ndx_double_replacement_evaluation_research import case
from test_ndx_double_replacement_domain_research import fixture
from backtest import ndx_double_replacement_evaluation_research as m

class Tests(unittest.TestCase):
 def test_all_small_points_independent_amounts_chain_and_literal_target(self):
  args=fixture();row=args['original_rows'][0]['input_row']
  row['holdings']['E']=2;row['execution_prices']['E']='7'
  row['securities']['E']=dict(ticker='E',issuer_id='IE',risk_chain='shared')
  row['securities']['C']['risk_chain']='shared';row['securities']['D']['risk_chain']='shared'
  row['target_weights']={'C':'0.2','D':'0.3'}
  inputs=case(args);snapshot=deepcopy(inputs);saved=m.evaluate_explicit_double_replacement_plans(**inputs)
  for item in saved['results']:
   task=item['plan']['task'];q=task['proposed_holdings'];prices={s:F(p) for s,p in row['execution_prices'].items()}
   amounts={s:qv*prices[s] for s,qv in q.items()if qv>0};S=sum(amounts.values(),F());w={s:a/S for s,a in amounts.items()}
   grossout=sum(row['holdings'][s]*prices[s]for s in task['identity']['outgoing_security_ids'])
   grossin=sum(prices[s]*q[s]for s in task['identity']['incoming_security_ids']);fee=(grossout+grossin)/1000
   r=item['evaluation'];self.assertEqual(F(r['cash_after_usd']),F(row['starting_cash_usd'])+F(row['cash_event']['amount_usd'])+grossout-grossin-fee)
   self.assertEqual(F(r['cash_flow_adjusted_pnl_usd']),-fee)
   self.assertEqual(F(r['risk']['effective_n']),S*S/sum(a*a for a in amounts.values()))
   l1=sum(abs(w.get(s,F())-F(row['target_weights'].get(s,'0')))for s in set(w)|set(row['target_weights']))
   self.assertEqual(F(r['original_target_stock_l1']),l1)
   self.assertEqual(r['risk']['positive_holding_count'],len(amounts));self.assertEqual(q['ZERO'],0)
  self.assertEqual(inputs,snapshot)

 def test_exact_joint_buffer_and_one_atom_exclusion(self):
  args=fixture();row=args['original_rows'][0]['input_row'];row['starting_cash_usd']='95.1'
  saved=m.evaluate_explicit_double_replacement_plans(**case(args))
  target=next(r for r in saved['results']if r['plan']['task']['identity']['buy_quantities']==[2,2])
  self.assertEqual(F(target['evaluation']['cash_after_usd']),100)
  self.assertIs(target['evaluation']['financial_checks']['CASH_BUFFER'],True)
  row['starting_cash_usd']='95.099999999999999999999999999999'
  self.assertEqual(case(args)['prepared']['document']['integer_count'],4)

 def test_each_risk_exact_tolerance_and_keyboard_stop_partition(self):
  holdings={'A':1,'B':1,'C':1,'ZERO':0};marks={s:F(1) for s in holdings}
  securities={s:dict(risk_chain='shared' if s in ('A','B') else 'other')for s in holdings}
  t=F(1,10**9);eps=F(1,10**30)
  params=dict(max_single_weight=F(1,3)-t,min_single_weight=F(1,3)+t,top_weight_cap=1-t,minimum_effective_n_ratio=1+t/3,risk_chain_top1_cap=F(2,3)-t)
  self.assertTrue(m.risk_snapshot(holdings,marks,securities,params)['all_passed'])
  fields=[('max_single_weight',-eps),('min_single_weight',eps),('top_weight_cap',-eps),('minimum_effective_n_ratio',eps),('risk_chain_top1_cap',-eps)]
  for field,delta in fields:
   bad=dict(params);bad[field]+=delta
   checks=m.risk_snapshot(holdings,marks,securities,bad)['checks']
   self.assertEqual(sum(v is False for v in checks.values()),1)
  args=case();original=m.evaluate_one;calls=[]
  def operation(row,task):
   calls.append(task['task_id'])
   if len(calls)==2:raise KeyboardInterrupt('stop once')
   return original(row,task)
  with patch.object(m,'evaluate_one',side_effect=operation):saved=m.evaluate_explicit_double_replacement_plans(**args)
  self.assertEqual(len(calls),2);self.assertEqual(saved['counts']['EVALUATION_EXCEPTION'],1)
  self.assertEqual(saved['counts']['NOT_EVALUATED_TECHNICAL_STOP'],2)
  self.assertEqual(saved['completed_evaluation_count'],1);self.assertEqual(saved['unsupplied_integer_count'],0)
  self.assertEqual([r['plan']for r in saved['results']],args['registered_plans'])

if __name__=='__main__':unittest.main()
