from copy import deepcopy
from decimal import Inexact, localcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors
from backtest.ndx_explicit_cash_plan_evaluation_research import evaluate_explicit_plans
from scripts import ndx_standard_cash_controls_research_20261002 as module


def fixture(cash=False):
    return dict(scenario_id='synthetic', lane='CASH_RETENTION_CONTROL' if cash else 'INCUMBENT_ADD_ONLY_CONTROL',
        branch_role='CASH_RETENTION_CONTROL' if cash else 'MIGRATION_CONTROL', zero_buy_only=cash,
        target_l1_applicable=not cash, allowed_buy_security_ids=[] if cash else list('ABCD'),
        holdings={sid: 1 for sid in 'ABCD'}, starting_cash_usd='1000',
        cash_event={'decision_date':'2023-03-31','execution_date':'2023-04-03','amount_usd':'1000'},
        execution_prices=dict.fromkeys('ABCD','10'), target_weights={} if cash else dict.fromkeys('ABCD','0.25'),
        securities={sid:{'issuer_id':sid,'risk_chain':sid} for sid in 'ABCD'},
        risk_parameters={'max_single_weight':'.45','min_single_weight':'.05','top_weight_cap':'.8','minimum_effective_n_ratio':'.7','risk_chain_top1_cap':'.55'},
        transaction_cost_bps='10', minimum_cash_buffer_usd='100', gaps=[{'reason':'SYNTHETIC_UNRESOLVED'}])


def document():
    rows=[]
    for cash in (True,False):
        for decision,execution in module.CLOCKS:
            for amount in ('1000','10000'):
                row=fixture(cash); row['cash_event']=dict(decision_date=decision,execution_date=execution,amount_usd=amount)
                row['scenario_id']=str(len(rows)); rows.append(row)
    for index in range(40):
        rows.append(dict(lane='RETURN', branch_role='MAIN_LANE', scenario_id='main'+str(index)))
    return dict(schema='REMAINING_STANDARD_CASH_INPUTS_V1',scenario_count=64, rows=rows, source_hashes={},
        original_execution_contract={'synthetic':True}, execution_contract_reference={'synthetic':True},
        **dict.fromkeys(('cash_fork_called','search_called','account_rerun','point_in_time_verified','promotion_allowed','orders_executed'),False))


class ControlsTests(unittest.TestCase):
    def test_cash_zero_buy_never_generator_or_l1_even_all_cash_risk_false(self):
        row=fixture(True); row['holdings']={}; row['execution_prices']={}; row['securities']={}
        generate=Mock(side_effect=AssertionError('Cash must not generate targets'))
        result=module.research_row(row,generate,evaluate_explicit_plans)
        self.assertEqual(result['evaluation']['evaluated_count'],1)
        plan=result['evaluation']['branches'][0]['evaluated_plans'][0]
        self.assertFalse(plan['feasible']); self.assertEqual(plan['buy_shares'],{})
        self.assertEqual(plan['cash_after_usd'],'2000'); self.assertEqual(plan['fees_usd'],'0')
        self.assertIsNone(result['selected_supplied_plan_index']); self.assertEqual(result['feasible_scores'],[])
        self.assertEqual(result['cash_control_plan_index'],0); generate.assert_not_called()

    def test_migration_preserves_old_holdings_and_scores_exactly(self):
        row=fixture(); before=deepcopy(row)
        result=module.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
        selected=result['evaluation']['branches'][0]['evaluated_plans'][result['selected_supplied_plan_index']]
        # Existing equal weights already have L1=0; lower fees select zero buys.
        self.assertEqual(selected['buy_shares'],dict.fromkeys('ABCD',0))
        self.assertEqual(selected['proposed_holdings'],dict.fromkeys('ABCD',1))
        self.assertEqual(selected['fees_usd'],'0')
        self.assertEqual(result['input_row'],before); self.assertEqual(row,before)
        self.assertFalse(result['time_series_return_evaluated'])

    def test_target_absent_old_sid_and_hostile_context(self):
        row=fixture(); row['holdings']['E']=5; row['execution_prices']['E']='10.000000000000002'
        row['securities']['E']={'issuer_id':'E','risk_chain':'E'}
        row['target_weights']['A']='0.25000000000000002'
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=module.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
        for plan in result['evaluation']['branches'][0]['evaluated_plans']:
            self.assertEqual(plan['proposed_holdings']['E'],5)
        self.assertEqual(result['generator']['normalized_target_weights']['E']['numerator'],'0')

    def test_exact24_selection_and_reject_coordinate_or_role_changes(self):
        doc=document(); selected=module.control_rows(doc)
        self.assertEqual(len(selected),24)
        self.assertEqual([index for index,_ in selected],list(range(24)))
        bad=deepcopy(doc); bad['rows'][1]['cash_event']=deepcopy(bad['rows'][0]['cash_event'])
        with self.assertRaises(ValueError): module.control_rows(bad)
        bad=fixture(True); bad['target_l1_applicable']=True
        with self.assertRaises(ValueError): module.research_row(bad,Mock(),Mock())

    def test_eight_target_bound_and_incomplete_generation_rejected(self):
        row=fixture(); row['holdings']={sid:1 for sid in 'ABCDEFGH'}
        row['execution_prices']=dict.fromkeys('ABCDEFGH','10')
        row['securities']={sid:{'issuer_id':sid,'risk_chain':sid} for sid in 'ABCDEFGH'}
        row['target_weights']=dict.fromkeys('ABCDEFGH','.125'); row['allowed_buy_security_ids']=list('ABCDEFGH')
        result=module.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
        self.assertLessEqual(result['evaluation']['evaluated_count'],257)
        self.assertEqual(result['evaluation']['unevaluated_supplied_plan_count'],0)
        with self.assertRaises(ValueError):
            module.research_row(row,Mock(return_value={'ungenerated_count':1,'plans':[]}),Mock())

    def test_publication_drift_failure_and_existing_namespace_early_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); parent=root/'parents'; parent.mkdir(); out=root/'output'
            source=root/'source.py'; source.write_text('synthetic')
            doc=document(); payload=module.encode(doc); (parent/'inputs.json').write_bytes(payload)
            ref={'path':str(parent/'inputs.json'),'sha256':module.sha(payload)}
            receipt=dict(schema='REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1',input_reference=ref,
                source_hashes={},status='INPUTS_ONLY_NOT_EXECUTED')
            (parent/'publication.json').write_bytes(module.encode(receipt))
            pins={role:(str(path),module.sha(path.read_bytes())) for role,path in
                  [('inputs',parent/'inputs.json'),('publication',parent/'publication.json')]}
            original_write=module.write_new
            def drifting_write(path,value):
                digest=original_write(path,value)
                if path.name=='publication.json': source.write_text('changed')
                return digest
            with patch.object(module,'SOURCE',source),patch.object(module,'LOADED_SHA',module.sha(source.read_bytes())),patch.object(module,'OUTPUT',out),patch.object(module,'PINS',pins),patch.object(module,'load_modules',return_value=(Mock(),Mock())),patch.object(module,'research_row',return_value={'synthetic':True}),patch.object(module,'write_new',side_effect=drifting_write):
                with self.assertRaisesRegex(ValueError,'Source drift'): module.run()
                self.assertTrue((out/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'namespace exists'): module.run()


if __name__=='__main__':
    unittest.main()
