from copy import deepcopy
from decimal import localcontext, Inexact
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import ndx_double_replacement_result_inspection_research as m
from backtest import ndx_double_replacement_evaluation_research as naive
from backtest import ndx_double_replacement_cached_evaluation_research as cached
from test_ndx_double_replacement_evaluation_research import case
from test_ndx_double_replacement_cached_evaluation_research import expanded
from test_ndx_double_replacement_domain_research import fixture


def samples(arguments=None):
    args=case()if arguments is None else arguments
    return args,[naive.evaluate_explicit_double_replacement_plans(**args),cached.evaluate_explicit_double_replacement_plans_cached(**args)]

class Tests(unittest.TestCase):
    def test_hand_values_both_schemas_and_forbidden_evaluators(self):
        args,saved=samples();before=deepcopy(args)
        row=args['prepared']['document']['cases'][0]['identity']['original_input_row'];task=args['registered_plans'][0]['task']
        expected=m.arithmetic(row,task)
        self.assertEqual(F(expected['gross_sell_usd']),50);self.assertEqual(F(expected['gross_buy_usd']),25)
        self.assertEqual(F(expected['total_fee_usd']),F(3,40));self.assertEqual(F(expected['cash_after_usd']),F(4999,40))
        self.assertEqual(F(expected['cash_flow_adjusted_pnl_usd']),-F(3,40))
        self.assertEqual(expected['risk']['weights'],{'C':'2/5','D':'3/5'})
        self.assertEqual(F(expected['risk']['effective_n']),F(25,13));self.assertEqual(expected['original_target_stock_l1'],'0')
        with patch.object(naive,'evaluate_one',side_effect=AssertionError('Forbidden naive')),patch.object(naive,'risk_snapshot',side_effect=AssertionError('Forbidden risk')),patch.object(cached,'evaluate_cached_point',side_effect=AssertionError('Forbidden cached')):
            with localcontext()as context:
                context.prec=1;context.traps[Inexact]=True
                for result in saved:
                    report=m.inspect_explicit_evaluations(**args,saved_result=result)
                    self.assertEqual(report['independently_checked_evaluation_count'],4)
                    self.assertIs(report['cache_runtime_counts_independently_verified'],False)
                    self.assertIs(report['source_bytes_authenticated'],False)
        self.assertEqual(args,before)

    def test_validated_snapshot_not_later_external_prepared_alias(self):
        for schema_index in (0,1):
            args,saved=samples();original=m.arithmetic
            def during(row,task):
                args['prepared']['content_sha256']='0'*64
                args['prepared']['document']['cases'][0]['identity']['original_input_row']['starting_cash_usd']='999999'
                return original(row,task)
            with patch.object(m,'arithmetic',side_effect=during):
                report=m.inspect_explicit_evaluations(**args,saved_result=saved[schema_index])
            self.assertEqual(report['independently_checked_evaluation_count'],4)

    def test_complete_multiholding_risks_and_resigned_field_attacks(self):
        args,saved=samples(case(expanded(4,'merged')))
        for result in saved:self.assertEqual(m.inspect_explicit_evaluations(**args,saved_result=result)['evaluation_status'],'ALL_SUPPLIED_EVALUATED')
        for attack in ('fee','cash','risk','chain','l1','weight','count','permission','extra'):
            result=deepcopy(saved[1]);value=result['results'][0]['evaluation']
            if attack=='fee':value['sell_fee_usd']='0'
            elif attack=='cash':value['cash_after_usd']='100'
            elif attack=='risk':value['risk']['checks']['RISK_CHAIN_TOP1_WEIGHT']=True
            elif attack=='chain':value['risk']['risk_chain_weights']['shared']='1/2'
            elif attack=='l1':value['original_target_stock_l1']='0'
            elif attack=='weight':value['risk']['weights']['C']='1/100'
            elif attack=='count':result['counts']['EVALUATION_EXCEPTION']=False
            elif attack=='permission':result['point_in_time_verified']=True
            else:result['risk_authenticated']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_explicit_evaluations(**args,saved_result=result)

    def test_budget_unsupplied_empty_and_all_plans_validated(self):
        for budget in (0,1,2,10):
            args=case();args['registered_plans']=[args['registered_plans'][3],args['registered_plans'][0]];args['max_evaluations']=budget
            for saved in samples(args)[1]:
                report=m.inspect_explicit_evaluations(**args,saved_result=saved)
                self.assertEqual(report['unsupplied_integer_count'],2)
                self.assertEqual(report['independently_checked_evaluation_count'],min(budget,2))
        a=fixture();a['original_rows'][0]['input_row']['starting_cash_usd']='0'
        args,saved=samples(case(a))
        for result in saved:self.assertEqual(m.inspect_explicit_evaluations(**args,saved_result=result)['full_integer_count'],0)
        args=case();args['max_evaluations']=0;result=samples(args)[1][0]
        for attack in ('bool','duplicate','second_sell','swap','zero','domain'):
            bad=deepcopy(args)
            if attack=='bool':bad['registered_plans'][-1]['global_ordinal']=True
            elif attack=='duplicate':bad['registered_plans'][-1]=deepcopy(bad['registered_plans'][0])
            elif attack=='second_sell':bad['registered_plans'][-1]['task']['signed_trade_quantities']['B']=0
            elif attack=='swap':bad['registered_plans'][-1]['task']['identity']['buy_quantities'].reverse()
            elif attack=='zero':bad['registered_plans'][-1]['task']['proposed_holdings']['ZERO']=1
            else:
                d=bad['prepared']['document'];d['cases'][0]['pairs'][0]['financial_integer_count']+=1;bad['prepared']['content_sha256']=m.digest(d)
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_explicit_evaluations(**bad,saved_result=result)

    def test_technical_stop_before_or_after_cache_insert_is_not_infeasible(self):
        args=case()
        for point in ('naive','cache_create','cache_point'):
            obj,name=(naive,'evaluate_one')if point=='naive'else(cached,'_prepare_pair_cache'if point=='cache_create'else'evaluate_cached_point')
            with patch.object(obj,name,side_effect=KeyboardInterrupt('original technical fact')):
                saved=(naive.evaluate_explicit_double_replacement_plans if point=='naive'else cached.evaluate_explicit_double_replacement_plans_cached)(**args)
            report=m.inspect_explicit_evaluations(**args,saved_result=saved)
            self.assertEqual(report['counts']['EVALUATION_EXCEPTION'],1)
            self.assertEqual(report['counts']['NOT_EVALUATED_TECHNICAL_STOP'],3)
            self.assertEqual(report['counts']['INFEASIBLE'],0)
            bad=deepcopy(saved);bad['results'][1]['status']='NOT_EVALUATED_BUDGET'
            with self.assertRaises(ValueError):m.inspect_explicit_evaluations(**args,saved_result=bad)
            if point!='naive':
                bad=deepcopy(saved);bad['pair_cache_count']=2
                with self.assertRaises(ValueError):m.inspect_explicit_evaluations(**args,saved_result=bad)
        original=cached.evaluate_cached_point;calls=[]
        def fail_second(*a):
            calls.append(1)
            if len(calls)==2:raise ValueError('Second point')
            return original(*a)
        with patch.object(cached,'evaluate_cached_point',side_effect=fail_second):saved=cached.evaluate_explicit_double_replacement_plans_cached(**args)
        report=m.inspect_explicit_evaluations(**args,saved_result=saved)
        self.assertEqual(report['independently_checked_evaluation_count'],1)
        self.assertEqual(saved['pair_cache_count'],1);self.assertEqual(saved['pair_cache_hit_count'],1)

if __name__=='__main__':unittest.main()
