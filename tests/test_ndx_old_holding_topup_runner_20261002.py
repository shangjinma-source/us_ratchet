from copy import deepcopy
from fractions import Fraction
import unittest
from scripts import ndx_old_holding_topup_research_20261002 as module


def fixture():
    return dict(scenario_id='synthetic',lane='RETURN',branch_role='MAIN_LANE',zero_buy_only=False,
        target_l1_applicable=True,holdings={'A':8,'B':1,'C':8,'D':8},
        execution_prices=dict.fromkeys('ABCDE','10'),securities={sid:{'ticker':sid,'issuer_id':sid,'risk_chain':sid} for sid in 'ABCDE'},
        target_weights={'A':'.25','C':'.25','D':'.25','E':'.25'},allowed_buy_security_ids=list('ACDE'),
        starting_cash_usd='100',cash_event={'decision_date':'2023-04-28','execution_date':'2023-05-01','amount_usd':'100'},
        transaction_cost_bps='10',minimum_cash_buffer_usd='10',
        risk_parameters={'min_single_weight':'.05','max_single_weight':'.45','top_weight_cap':'.8','minimum_effective_n_ratio':'.7','risk_chain_top1_cap':'.55'},
        gaps=[{'reason':'UNRESOLVED_SYNTHETIC'}])


class TopupRunnerTests(unittest.TestCase):
    def test_complete_optional_supports_preserve_original_targets(self):
        row=fixture(); before=deepcopy(row); result=module.seed_domain(row)
        self.assertEqual(len(result['supports']),2)
        self.assertEqual(result['supports'][0]['support_security_ids'],list('ABCD'))
        self.assertEqual(result['supports'][1]['support_security_ids'],list('ABCDE'))
        self.assertEqual(result['conditional_research_buy_ids'],list('ABCDE'))
        self.assertEqual(result['seeds'][0]['seed_buy_shares'],dict.fromkeys('ABCDE',0))
        self.assertEqual(row,before)
        for support in result['supports']:
            seeds=[s for s in result['seeds'] if s['support_index']==support['support_index']]
            self.assertEqual(support['seed_count'],len(seeds))
            self.assertEqual(len(seeds),len({tuple(s['seed_buy_shares'].values()) for s in seeds}))
            for seed in seeds:
                self.assertEqual(seed['seed_buy_shares']['B'],0)
                self.assertEqual(seed['seed_buy_shares']['E']>0, support['support_index']==1)

    def test_shared_issuer_rejects_only_activated_class(self):
        row=fixture(); row['securities']['E']['issuer_id']='A'
        result=module.seed_domain(row)
        self.assertFalse(result['supports'][0]['structurally_excluded'])
        self.assertTrue(result['supports'][1]['structurally_excluded'])
        self.assertEqual(result['supports'][1]['seed_count'],0)
        self.assertTrue(all(seed['support_index']==0 for seed in result['seeds']))

    def test_actual_pure_closure_integration_full_old_l1_and_no_mutation(self):
        from backtest.ndx_min_weight_topup_closure_research import close_min_weight_topups
        from backtest.ndx_explicit_cash_plan_evaluation_research import evaluate_explicit_plans
        row=fixture(); before=deepcopy(row)
        result=module.research_row(row,close_min_weight_topups,evaluate_explicit_plans)
        self.assertEqual(row,before); self.assertEqual(result['input_row'],before)
        self.assertEqual(result['unprocessed_seed_count'],0)
        self.assertIsNotNone(result['selected_candidate_index'])
        plans=result['evaluation']['branches'][0]['evaluated_plans']
        for plan in plans:
            self.assertGreaterEqual(plan['proposed_holdings']['B'],2)
        expected=[]
        for plan in plans:
            if plan['feasible']:
                total=sum(plan['proposed_holdings'].values())
                distance=sum(abs(Fraction(plan['proposed_holdings'][sid],total)-Fraction(row['target_weights'].get(sid,'0'))) for sid in 'ABCDE')
                expected.append((distance,Fraction(plan['fees_usd']),plan['supplied_plan_index']))
        self.assertEqual(result['selected_candidate_index'],min(expected)[2])
        self.assertTrue(result['new_buy_domain_is_research_assumption'])
        self.assertFalse(result['formal_eligibility_verified'])


if __name__=='__main__':
    unittest.main()
