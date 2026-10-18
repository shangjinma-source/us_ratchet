import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors
from backtest.ndx_explicit_cash_plan_evaluation_research import evaluate_explicit_plans
from scripts import ndx_first_period_cash_neighbor_research_20261002 as module


def fixture():
    return dict(scenario_id='synthetic',holdings={},starting_cash_usd='1000',injection_usd='0',
        cash_event={'decision_date':'2023-03-31','execution_date':'2023-04-03','amount_usd':'0'},
        execution_prices=dict.fromkeys('ABCD','10'),target_weights=dict.fromkeys('ABCD','0.25'),
        securities={sid:{'issuer_id':sid,'risk_chain':sid} for sid in 'ABCD'},
        risk_parameters={'max_single_weight':'.45','min_single_weight':'.05','top_weight_cap':'.8','minimum_effective_n_ratio':'.7','risk_chain_top1_cap':'.55'},
        transaction_cost_bps='10',minimum_cash_buffer_usd='100')


class ResearchTests(unittest.TestCase):
    def test_hand_computed_equal_target_selects_22_each(self):
        result=module.research_row(fixture(),generate_target_neighbors,evaluate_explicit_plans)
        self.assertEqual(result['evaluation']['evaluated_count'],17)
        selected=result['evaluation']['branches'][0]['evaluated_plans'][result['selected_supplied_plan_index']]
        self.assertEqual(selected['buy_shares'],dict.fromkeys('ABCD',22))
        self.assertEqual(selected['fees_usd'],'0.88')
        self.assertEqual(selected['cash_after_usd'],'119.12')
        self.assertFalse(result['economic_winner_selected'])

    def test_no_capital_above_buffer_does_not_invent_selection(self):
        row=fixture(); row['starting_cash_usd']='100'
        result=module.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
        self.assertIsNone(result['selected_supplied_plan_index'])
        self.assertEqual(result['evaluation']['evaluated_count'],1)

    def test_cash_mismatch_rejected_and_pending_anchor_writes_nothing(self):
        row=fixture(); row['injection_usd']='1'
        with self.assertRaises(ValueError): module.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)/'new'),patch.object(module,'PINS',{'pending':('pending',None)}):
            with self.assertRaises(ValueError): module.run()
            self.assertFalse(module.OUTPUT.exists())
