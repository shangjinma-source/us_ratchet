from copy import deepcopy
from fractions import Fraction as F
from decimal import localcontext,Inexact
from unittest.mock import patch
import unittest
from test_ndx_double_replacement_evaluation_research import case
from test_ndx_double_replacement_domain_research import fixture
from backtest import ndx_double_replacement_domain_research as domain
from backtest import ndx_double_replacement_evaluation_research as oracle
from backtest import ndx_double_replacement_cached_evaluation_research as cached

EXTRAS=('pair_cache_count','pair_cache_hit_count','cache_scope','risk_result_reused_across_points','intervals_skipped','naive_oracle_called','naive_oracle_source_sha256')
def normalized(result):
    out=deepcopy(result)
    for key in EXTRAS:out.pop(key)
    out['schema']=oracle.SCHEMA
    return out

def expanded(count,chain_mode):
    args=fixture();r=args['original_rows'][0]['input_row']
    r['target_weights']={'C':'0.2','D':'0.3'}
    for i in range(count):
        sid='R'+str(i);r['holdings'][sid]=1;r['execution_prices'][sid]=str(i+2)
        r['securities'][sid]=dict(ticker=sid,issuer_id='issuer:'+sid,risk_chain='shared'if chain_mode=='merged'else 'chain:'+sid)
    if chain_mode=='merged':
        r['securities']['C']['risk_chain']='shared';r['securities']['D']['risk_chain']='shared'
    elif chain_mode=='split' and count:
        r['securities']['C']['risk_chain']='chain:R0'
    return args

class Tests(unittest.TestCase):
 def test_full_small_domains_exact_every_field_against_naive(self):
    for count in (0,1,4):
      for mode in ('merged','split','separate'):
        with self.subTest(count=count,mode=mode):
          args=case(expanded(count,mode));before=deepcopy(args)
          expected=oracle.evaluate_explicit_double_replacement_plans(**args)
          with patch.object(oracle,'evaluate_one',side_effect=AssertionError('oracle forbidden')):
            with localcontext()as context:
              context.prec=1;context.traps[Inexact]=True
              actual=cached.evaluate_explicit_double_replacement_plans_cached(**args)
          self.assertEqual(normalized(actual),expected);self.assertEqual(args,before)
          self.assertFalse(actual['intervals_skipped']);self.assertEqual(actual['pair_cache_count']+actual['pair_cache_hit_count'],actual['completed_evaluation_count'])

 def test_two_flows_separate_caches_and_not_normalized_targets(self):
    a=expanded(1,'split');b=deepcopy(a['original_rows'][0]);b['input_row']['scenario_id']='case1';b['input_row']['cash_event']['amount_usd']='6';b['input_reference']['json_pointer']='/rows/1'
    a['original_rows'].append(b);a['action_contract']['expected_scenario_ids'].append('case1')
    args=case(a);self.assertEqual(normalized(cached.evaluate_explicit_double_replacement_plans_cached(**args)),oracle.evaluate_explicit_double_replacement_plans(**args))

 def test_cache_immutable_and_output_no_alias_single_validation(self):
    args=case();d=cached.validate_prepared(args['prepared']);c=cached._prepare_pair_cache(d['cases'][0],d['cases'][0]['pairs'][0]);t=deepcopy(args['registered_plans'][0]['task'])
    saved=cached.evaluate_cached_point(c,t);saved['risk']['weights']['C']='MUTATED';saved['risk']['checks'].clear()
    d['cases'][0]['identity']['original_input_row']['starting_cash_usd']='9999'
    self.assertEqual(cached.evaluate_cached_point(c,t),oracle.evaluate_one(args['prepared']['document']['cases'][0]['identity']['original_input_row'],t))
    with self.assertRaises(AttributeError):c.cash=F(0)
    with patch.object(domain,'checked',wraps=domain.checked)as checked,patch.object(domain,'unrank',side_effect=AssertionError('repeated public hash')):
      cached.evaluate_explicit_double_replacement_plans_cached(**args)
    self.assertEqual(checked.call_count,1)

 def test_entire_suffix_identity_and_technical_stop(self):
    args=case();args['max_evaluations']=0
    for kind in ('q','bool','duplicate','zero'):
      bad=deepcopy(args)
      if kind=='q':bad['registered_plans'][-1]['task']['identity']['buy_quantities'].reverse()
      elif kind=='bool':bad['registered_plans'][-1]['global_ordinal']=True
      elif kind=='duplicate':bad['registered_plans'][-1]=deepcopy(bad['registered_plans'][0])
      else:bad['registered_plans'][-1]['task']['proposed_holdings']['ZERO']=1
      with self.subTest(kind=kind),patch.object(cached,'evaluate_cached_point',side_effect=AssertionError('no evaluation')),self.assertRaises(ValueError):cached.evaluate_explicit_double_replacement_plans_cached(**bad)
    original=cached.evaluate_cached_point;calls=[]
    def step(cache,task):
      calls.append(task['task_id'])
      if len(calls)==2:raise KeyboardInterrupt('saved')
      return original(cache,task)
    with patch.object(cached,'evaluate_cached_point',side_effect=step):result=cached.evaluate_explicit_double_replacement_plans_cached(**case())
    self.assertEqual(len(calls),2);self.assertEqual(result['completed_evaluation_count'],1);self.assertEqual(result['counts']['NOT_EVALUATED_TECHNICAL_STOP'],2)

 def test_exact_budget_atom_and_empty_domain(self):
    for cash in ('95.1','95.099999999999999999999999999999','0'):
      a=fixture();a['original_rows'][0]['input_row']['starting_cash_usd']=cash;args=case(a)
      self.assertEqual(normalized(cached.evaluate_explicit_double_replacement_plans_cached(**args)),oracle.evaluate_explicit_double_replacement_plans(**args))

if __name__=='__main__':unittest.main()
