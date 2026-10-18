from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import ndx_double_replacement_cached_evaluation_research as m
from backtest import ndx_double_replacement_evaluation_research as naive
from backtest import ndx_double_replacement_domain_research as domain
from test_ndx_double_replacement_domain_research import fixture
from test_ndx_double_replacement_evaluation_research import case


def one(arguments):
    prepared=domain.prepare_double_replacement_domain(**arguments)
    task=domain.unrank(prepared,0)
    return dict(prepared=prepared,registered_plans=[dict(global_ordinal=0,task=task)],max_evaluations=1)


class Tests(unittest.TestCase):
    def test_exact_five_risk_tolerance_atoms_and_naive_full_fields(self):
        boundaries=[('max_single_weight','MAX_SINGLE_WEIGHT','0.499999999','0.4999999989',False),('min_single_weight','MIN_SINGLE_WEIGHT','0.500000001','0.5000000011',False),('top_weight_cap','SECURITY_TOP3_WEIGHT','0.999999999','0.9999999989',False),('risk_chain_top1_cap','RISK_CHAIN_TOP1_WEIGHT','0.499999999','0.4999999989',False),('minimum_effective_n_ratio','MINIMUM_EFFECTIVE_N','0.9000000005','0.9000000006',True)]
        for parameter,check,passing,failing,unequal in boundaries:
            for literal,expected in ((passing,True),(failing,False)):
                args=fixture();row=args['original_rows'][0]['input_row'];row['execution_prices']['C']='10';row['execution_prices']['D']='20'if unequal else'10';row['risk_parameters']={k:'1'for k in row['risk_parameters']};row['risk_parameters'].update(min_single_weight='0.001',minimum_effective_n_ratio='0.001');row['risk_parameters'][parameter]=literal
                inputs=one(args);old=naive.evaluate_explicit_double_replacement_plans(**inputs)
                with patch.object(naive,'evaluate_one',side_effect=AssertionError('No naive production call')):actual=m.evaluate_explicit_double_replacement_plans_cached(**inputs)
                with self.subTest(parameter=parameter,literal=literal):
                    self.assertEqual(actual['results'],old['results']);self.assertIs(actual['results'][0]['evaluation']['risk']['checks'][check],expected)

    def test_reconstructed_domain_and_full_suffix_before_cache_creation(self):
        for attack in ('pair','task_id','zero','scope','scenario_bool'):
            inputs=case();inputs['max_evaluations']=0
            if attack=='pair':
                d=inputs['prepared']['document'];d['cases'][0]['pairs'][0]['financial_bound']['joint_budget_usd']='999';inputs['prepared']['content_sha256']=domain.digest(d)
            elif attack=='scope':
                d=inputs['prepared']['document'];d['scope']='FOREIGN';inputs['prepared']['content_sha256']=domain.digest(d)
            elif attack=='task_id':inputs['registered_plans'][-1]['task']['task_id']='0'*64
            elif attack=='zero':inputs['registered_plans'][-1]['task']['signed_trade_quantities']['ZERO']=1
            else:inputs['registered_plans'][-1]['task']['scenario_index']=False
            with self.subTest(attack=attack),patch.object(m,'_prepare_pair_cache',side_effect=AssertionError('Invalid domain cannot create cache')),self.assertRaises(ValueError):m.evaluate_explicit_double_replacement_plans_cached(**inputs)

    def test_immutable_cache_and_flow_target_no_cross_scenario_reuse(self):
        args=fixture();other=deepcopy(args['original_rows'][0]);other['input_row']['scenario_id']='other';other['input_reference']['json_pointer']='/rows/1';other['input_row']['cash_event']['amount_usd']='6';other['input_row']['target_weights']={'C':'0.9','D':'0.9'};args['original_rows'].append(other);args['action_contract']['expected_scenario_ids'].append('other')
        inputs=case(args);before=deepcopy(inputs);result=m.evaluate_explicit_double_replacement_plans_cached(**inputs);oracle=naive.evaluate_explicit_double_replacement_plans(**inputs)
        self.assertEqual(result['results'],oracle['results']);self.assertEqual(inputs,before);self.assertEqual(result['pair_cache_count'],2)
        d=m.validate_prepared(inputs['prepared']);cache=m._prepare_pair_cache(d['cases'][0],d['cases'][0]['pairs'][0]);task=inputs['registered_plans'][0]['task'];expected=m.evaluate_cached_point(cache,task)
        d['cases'][0]['identity']['original_input_row']['target_weights']['C']='999'
        expected['risk']['weights'].clear()
        self.assertEqual(m.evaluate_cached_point(cache,task),oracle['results'][0]['evaluation'])
        with self.assertRaises(AttributeError):cache.flow=F(99)

    def test_error_suffix_preserves_every_identity_without_reentry(self):
        inputs=case();original=m.evaluate_cached_point;called=[]
        class Broken(BaseException):
            def __str__(self):raise RuntimeError('no string')
        def step(cache,task):
            called.append(task['task_id'])
            if len(called)==2:raise Broken()
            return original(cache,task)
        with patch.object(m,'evaluate_cached_point',step):out=m.evaluate_explicit_double_replacement_plans_cached(**inputs)
        self.assertEqual(len(called),2);self.assertEqual(out['counts']['NOT_EVALUATED_TECHNICAL_STOP'],2)
        self.assertEqual(out['results'][1]['error'],dict(type='Broken',message='ERROR_STRING_FAILED: RuntimeError'))
        self.assertEqual([r['plan']for r in out['results']],inputs['registered_plans'])

    def test_external_prepared_mutation_does_not_relabel_validated_result(self):
        inputs=case();expected=inputs['prepared']['content_sha256'];original=m.evaluate_cached_point
        def step(cache,task):
            inputs['prepared']['content_sha256']='0'*64
            inputs['prepared']['document']['scope']='FOREIGN_AFTER_VALIDATION'
            return original(cache,task)
        with patch.object(m,'evaluate_cached_point',step):out=m.evaluate_explicit_double_replacement_plans_cached(**inputs)
        self.assertEqual(out['prepared_content_sha256'],expected)
        self.assertEqual(out['action_contract']['scope'],domain.SCOPE)

if __name__=='__main__':unittest.main()
