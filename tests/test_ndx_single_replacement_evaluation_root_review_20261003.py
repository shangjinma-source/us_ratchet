from fractions import Fraction
import unittest
from unittest.mock import patch

from backtest import ndx_single_replacement_domain_research as domain
from backtest import ndx_single_replacement_evaluation_research as evaluator
from test_ndx_single_replacement_domain_research import fixture


def four_stock_case():
    arguments = fixture()
    row = arguments['original_rows'][0]['input_row']
    row.update(holdings={s: 1 for s in 'ABCD'},
               target_weights={'B': '0.2', 'C': '0.2', 'D': '0.2', 'E': '0.4'},
               allowed_buy_security_ids=list('BCDE'),
               execution_prices={s: '100' for s in 'ABCDE'},
               securities={s: dict(ticker=s, issuer_id=s, risk_chain=s) for s in 'ABCDE'},
               risk_parameters=dict(max_single_weight='0.45', min_single_weight='0.05',
                                    top_weight_cap='0.8', minimum_effective_n_ratio='0.7',
                                    risk_chain_top1_cap='0.55'))
    row['cash_event']['amount_usd'] = '0.2'
    prepared = domain.prepare_single_replacement_domain(**arguments)
    return dict(prepared=prepared, max_evaluations=4,
                registered_plans=[dict(global_ordinal=i, task=domain.unrank(prepared, i)) for i in range(4)])


class Tests(unittest.TestCase):
    def test_feasible_basket_hand_equity_cash_target_distance(self):
        output = evaluator.evaluate_explicit_single_replacement_plans(**four_stock_case())
        self.assertEqual(output['counts']['FEASIBLE'], 4)
        first = output['results'][0]['evaluation']
        self.assertEqual(Fraction(first['cash_after_usd']), 100)
        self.assertEqual(Fraction(first['equity_after_usd']), 500)
        self.assertEqual(Fraction(first['total_fee_usd']), Fraction(1, 5))
        self.assertEqual(Fraction(first['cash_flow_adjusted_pnl_usd']), Fraction(-1, 5))
        self.assertEqual(Fraction(first['original_target_stock_l1']), Fraction(3, 10))
        self.assertEqual(first['risk']['weights'], dict.fromkeys('BCDE', '1/4'))
        self.assertEqual(first['risk']['effective_n'], '4')

    def test_interrupt_preserves_completed_prefix_and_stops(self):
        original = evaluator.evaluate_one
        calls = []
        def interrupted(row, task):
            calls.append(task['task_id'])
            if len(calls) == 2:
                raise KeyboardInterrupt('synthetic interruption')
            return original(row, task)
        with patch.object(evaluator, 'evaluate_one', side_effect=interrupted):
            output = evaluator.evaluate_explicit_single_replacement_plans(**four_stock_case())
        self.assertEqual(len(calls), 2)
        self.assertEqual(output['completed_evaluation_count'], 1)
        self.assertEqual(output['results'][1]['error']['type'], 'KeyboardInterrupt')
        self.assertEqual(output['counts']['NOT_EVALUATED_TECHNICAL_STOP'], 2)
        self.assertIs(output['economic_winner_selected'], False)


if __name__ == '__main__':
    unittest.main()
