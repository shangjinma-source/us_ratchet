from copy import deepcopy
from unittest.mock import patch
import unittest
from test_ndx_double_replacement_result_inspection_research import samples,case,expanded
from backtest import ndx_double_replacement_result_inspection_research as m
from backtest import ndx_double_replacement_cached_evaluation_research as cache

class Tests(unittest.TestCase):
 def test_isolated_prepared_identity_during_inspection(self):
  for schema in (0,1):
   args,saved=samples();original=m.arithmetic
   def mutate(row,task):
    args['prepared']['content_sha256']='a'*64
    args['prepared']['document']['cases'][0]['identity']['original_input_row']['starting_cash_usd']='999999'
    return original(row,task)
   with self.subTest(schema=schema),patch.object(m,'arithmetic',side_effect=mutate):
    report=m.inspect_explicit_evaluations(**args,saved_result=saved[schema])
   self.assertEqual(report['independently_checked_evaluation_count'],4)

 def test_saved_technical_stop_does_not_certify_unobserved_runtime(self):
  args=case(expanded(1,'split'));fn=cache.evaluate_cached_point;seen=[]
  def stop(pair,task):
   seen.append(task['task_id'])
   if len(seen)==2:raise KeyboardInterrupt('declared')
   return fn(pair,task)
  with patch.object(cache,'evaluate_cached_point',side_effect=stop):saved=cache.evaluate_explicit_double_replacement_plans_cached(**args)
  report=m.inspect_explicit_evaluations(**args,saved_result=saved)
  self.assertFalse(report['all_supplied_plans_numerically_checked']);self.assertFalse(report['technical_exception_authenticity_verified'])
  self.assertFalse(report['cache_runtime_counts_independently_verified']);self.assertEqual(report['independently_checked_evaluation_count'],1)
  for attack in ('continued','emptyerror','cachebool','status'):
   bad=deepcopy(saved)
   if attack=='continued':bad['results'][2]['status']='INFEASIBLE'
   elif attack=='emptyerror':bad['results'][1]['error']={'type':'','message':''}
   elif attack=='cachebool':bad['pair_cache_count']=True
   else:bad['status']='ALL_SUPPLIED_EVALUATED'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_explicit_evaluations(**args,saved_result=bad)

 def test_literal_target_zero_keys_and_small_exact_mutation(self):
  args,saved=samples(case(expanded(4,'separate')))
  for source in saved:
   for field in ('total_fee_usd','cash_after_usd','original_target_stock_l1'):
    from fractions import Fraction
    bad=deepcopy(source);r=bad['results'][0]['evaluation'];r[field]=str(Fraction(r[field])+Fraction(1,10**90))
    with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_explicit_evaluations(**args,saved_result=bad)
  bad=deepcopy(args);bad['max_evaluations']=0;bad['registered_plans'][-1]['task']['proposed_holdings']['ZERO']=False
  with self.assertRaises(ValueError):m.inspect_explicit_evaluations(**bad,saved_result=saved[0])

if __name__=='__main__':unittest.main()
