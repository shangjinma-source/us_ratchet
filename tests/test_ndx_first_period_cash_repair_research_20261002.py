from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest.ndx_cash_plan_repair_neighbors_research import generate_repair_neighbors
from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors
from backtest.ndx_explicit_cash_plan_evaluation_research import evaluate_explicit_plans
from scripts.ndx_first_period_cash_neighbor_research_20261002 import research_row
from scripts import ndx_first_period_cash_repair_research_20261002 as runner


def fixture():
    row=dict(scenario_id='synthetic',holdings={},starting_cash_usd='1000',injection_usd='0',
        cash_event={'decision_date':'2023-03-31','execution_date':'2023-04-03','amount_usd':'0'},
        execution_prices=dict.fromkeys('ABCD','10'),target_weights=dict.fromkeys('ABCD','.25'),
        securities={sid:{'issuer_id':sid,'risk_chain':sid} for sid in 'ABCD'},
        risk_parameters={'max_single_weight':'.45','min_single_weight':'.05','top_weight_cap':'.8','minimum_effective_n_ratio':'.7','risk_chain_top1_cap':'.55'},
        transaction_cost_bps='10',minimum_cash_buffer_usd='100')
    return row,research_row(row,generate_target_neighbors,evaluate_explicit_plans)


class RepairRunnerTests(unittest.TestCase):
    def test_evaluates_only_new_plans_and_retains_previous_best(self):
        row,old=fixture(); before=deepcopy((row,old)); calls=[]
        def evaluator(**kwargs):
            calls.append(deepcopy(kwargs['plans_by_branch']['synthetic']))
            return evaluate_explicit_plans(**kwargs)
        result=runner.process(row,old,generate_repair_neighbors,evaluator)
        self.assertEqual(len(calls),1)
        previous={runner.plan_key(p['buy_shares']) for p in old['evaluation']['branches'][0]['evaluated_plans']}
        self.assertFalse(previous & {runner.plan_key(p) for p in calls[0]})
        self.assertEqual(result['selected']['source'],'PREVIOUS_BATCH')
        self.assertEqual((row,old),before)
        self.assertFalse(result['previous_evaluation_repeated'])

    def test_coordinate_mismatch_and_duplicate_previous_rejected(self):
        row,old=fixture(); old['scenario_id']='other'
        with self.assertRaises(ValueError): runner.process(row,old,generate_repair_neighbors,evaluate_explicit_plans)
        row,old=fixture(); plans=old['evaluation']['branches'][0]['evaluated_plans']; plans[-1]=deepcopy(plans[0])
        with self.assertRaises(ValueError): runner.process(row,old,generate_repair_neighbors,evaluate_explicit_plans)

    def test_pending_pin_cannot_create_namespace(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(runner,'OUTPUT',Path(directory)/'new'),patch.object(runner,'PINS',{'x':('x',None)}):
            with self.assertRaises(ValueError): runner.run()
            self.assertFalse(runner.OUTPUT.exists())
