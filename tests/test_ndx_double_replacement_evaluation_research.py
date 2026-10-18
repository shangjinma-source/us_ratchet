from copy import deepcopy
from decimal import Inexact, localcontext
from fractions import Fraction as F
from unittest.mock import patch
import unittest

from backtest import ndx_double_replacement_domain_research as domain
from backtest import ndx_double_replacement_evaluation_research as evaluator
from test_ndx_double_replacement_domain_research import fixture


def case(arguments=None):
    prepared = domain.prepare_double_replacement_domain(**(arguments or fixture()))
    return dict(prepared=prepared, registered_plans=[
        dict(global_ordinal=i, task=domain.unrank(prepared, i))
        for i in range(prepared['document']['integer_count'])
    ], max_evaluations=10000)


class Tests(unittest.TestCase):
    def test_caller_mutation_during_evaluation_cannot_rebind_prepared_identity(self):
        arguments = case()
        original_hash = arguments['prepared']['content_sha256']
        original = evaluator.evaluate_one
        def mutate_external(row, task):
            arguments['prepared']['content_sha256'] = 'f' * 64
            arguments['prepared']['document']['cases'][0]['identity']['original_input_row']['starting_cash_usd'] = '99999'
            return original(row, task)
        with patch.object(evaluator, 'evaluate_one', side_effect=mutate_external):
            result = evaluator.evaluate_explicit_double_replacement_plans(**arguments)
        self.assertEqual(result['prepared_content_sha256'], original_hash)
        self.assertEqual(F(result['results'][0]['evaluation']['cash_after_usd']), F('124.975'))

    def test_bilateral_two_sell_two_buy_hand_accounting_and_original_l1(self):
        arguments = case()
        before = deepcopy(arguments)
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = True
            result = evaluator.evaluate_explicit_double_replacement_plans(**arguments)
        self.assertEqual(arguments, before)
        first = result['results'][0]['evaluation']
        self.assertEqual(F(first['gross_sell_usd']), 50)
        self.assertEqual(F(first['gross_buy_usd']), 25)
        self.assertEqual(F(first['sell_fee_usd']), F('0.05'))
        self.assertEqual(F(first['buy_fee_usd']), F('0.025'))
        self.assertEqual(F(first['cash_after_usd']), F('124.975'))
        self.assertEqual(F(first['equity_after_usd']), F('149.975'))
        self.assertEqual(F(first['cash_flow_adjusted_pnl_usd']), F('-0.075'))
        self.assertEqual(first['risk']['weights'], {'C': '2/5', 'D': '3/5'})
        self.assertEqual(F(first['risk']['effective_n']), F(25, 13))
        self.assertEqual(F(first['original_target_stock_l1']), 0)
        self.assertEqual(result['full_integer_count'], 4)
        self.assertEqual(result['completed_evaluation_count'], 4)
        self.assertTrue(all(result[key] is False for key in evaluator.FLAGS))

    def test_validated_projection_isolated_no_repeated_preparation_hash(self):
        arguments = case()
        document = evaluator.validate_prepared(arguments['prepared'])
        for i, plan in enumerate(arguments['registered_plans']):
            self.assertEqual(evaluator.project_validated_task(document, i), plan['task'])
        arguments['prepared']['document']['cases'][0]['identity']['original_input_row']['holdings']['A'] = 900
        self.assertEqual(evaluator.project_validated_task(document, 0)['identity']['sell_quantities'], {'A': 2, 'B': 1})
        arguments = case()
        with patch.object(domain, 'unrank', side_effect=AssertionError('Repeated public hash')), patch.object(domain, 'checked', wraps=domain.checked) as checked:
            evaluator.evaluate_explicit_double_replacement_plans(**arguments)
        self.assertEqual(checked.call_count, 1)

    def test_full_suffix_validation_and_rehashed_domain_attack(self):
        for attack in ('bool', 'duplicate', 'second_sell', 'second_buy', 'zero', 'swapped_quantities', 'rehashed'):
            arguments = case()
            arguments['max_evaluations'] = 0
            final = arguments['registered_plans'][-1]
            if attack == 'bool':
                final['global_ordinal'] = True
            elif attack == 'duplicate':
                arguments['registered_plans'][-1] = deepcopy(arguments['registered_plans'][0])
            elif attack == 'second_sell':
                final['task']['signed_trade_quantities']['B'] = 0
            elif attack == 'second_buy':
                final['task']['signed_trade_quantities']['D'] = 0
            elif attack == 'zero':
                final['task']['proposed_holdings']['ZERO'] = 1
            elif attack == 'swapped_quantities':
                final['task']['identity']['buy_quantities'].reverse()
            else:
                document = arguments['prepared']['document']
                document['cases'][0]['pairs'][0]['financial_integer_count'] += 1
                arguments['prepared']['content_sha256'] = domain.digest(document)
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                evaluator.evaluate_explicit_double_replacement_plans(**arguments)

    def test_budget_and_hostile_exception_preserve_full_partition(self):
        arguments = case()
        arguments['max_evaluations'] = 1
        result = evaluator.evaluate_explicit_double_replacement_plans(**arguments)
        self.assertEqual(result['counts']['NOT_EVALUATED_BUDGET'], 3)
        class HostileError(BaseException):
            def __str__(self):
                raise RuntimeError('cannot stringify')
        original = evaluator.evaluate_one
        calls = []
        def evaluate(row, task):
            calls.append(task['task_id'])
            if len(calls) == 2:
                raise HostileError()
            return original(row, task)
        with patch.object(evaluator, 'evaluate_one', side_effect=evaluate):
            result = evaluator.evaluate_explicit_double_replacement_plans(**case())
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['counts']['NOT_EVALUATED_TECHNICAL_STOP'], 2)
        self.assertEqual(result['results'][1]['error'], dict(type='HostileError', message='ERROR_STRING_FAILED: RuntimeError'))
        self.assertEqual(sum(result['counts'].values()), 4)

    def test_original_five_risks_for_retained_stock_and_merged_new_chain(self):
        from backtest import ndx_conditional_new_cash_fork_research as frozen
        arguments = fixture()
        row = arguments['original_rows'][0]['input_row']
        row['holdings']['E'] = 1
        row['execution_prices']['E'] = '7'
        row['securities']['E'] = dict(ticker='E', issuer_id='issuer:E', risk_chain='shared')
        row['securities']['C']['risk_chain'] = 'shared'
        row['securities']['D']['risk_chain'] = 'shared'
        result = evaluator.evaluate_explicit_double_replacement_plans(**case(arguments))
        marks = {s: F(v) for s, v in row['execution_prices'].items()}
        parameters = {k: F(v) for k, v in row['risk_parameters'].items()}
        for item in result['results']:
            expected = frozen._risk(item['plan']['task']['proposed_holdings'], marks, row['securities'], parameters)
            actual = item['evaluation']['risk']
            for key in ('checks', 'all_passed', 'weights', 'effective_n', 'positive_holding_count'):
                self.assertEqual(actual[key], expected[key])

    def test_empty_domain_and_original_target_not_normalized(self):
        arguments = fixture()
        arguments['original_rows'][0]['input_row']['starting_cash_usd'] = '0'
        result = evaluator.evaluate_explicit_double_replacement_plans(**case(arguments))
        self.assertEqual(result['full_integer_count'], 0)
        self.assertEqual(result['completed_evaluation_count'], 0)
        arguments = fixture()
        arguments['original_rows'][0]['input_row']['target_weights'] = {'C': '0.2', 'D': '0.3'}
        result = evaluator.evaluate_explicit_double_replacement_plans(**case(arguments))
        self.assertEqual(F(result['results'][0]['evaluation']['original_target_stock_l1']), F('0.5'))


if __name__ == '__main__':
    unittest.main()
