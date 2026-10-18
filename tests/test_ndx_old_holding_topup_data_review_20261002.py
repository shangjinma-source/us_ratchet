import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import Mock,patch
from scripts import ndx_old_holding_topup_research_20261002 as m

def fixture():
    return {'scenario_id':'synthetic','branch_role':'MAIN_LANE','zero_buy_only':False,'target_l1_applicable':True,'holdings':{'GOOG':10,'OLD':10},'target_weights':{'GOOGL':'0.2','NEW':'0.8'},'allowed_buy_security_ids':['GOOGL','NEW'],
     'execution_prices':dict.fromkeys(('GOOG','OLD','GOOGL','NEW'),'10'),
     'securities':{'GOOG':{'issuer_id':'ALPH','risk_chain':'a'},'GOOGL':{'issuer_id':'ALPH','risk_chain':'a'},'OLD':{'issuer_id':'old','risk_chain':'b'},'NEW':{'issuer_id':'new','risk_chain':'c'}},
     'starting_cash_usd':'100','cash_event':{'amount_usd':'100','decision_date':'2023-04-28','execution_date':'2023-05-01'},'minimum_cash_buffer_usd':'0','transaction_cost_bps':'0',
     'risk_parameters':{'max_single_weight':'0.45','min_single_weight':'0.05','top_weight_cap':'0.8','minimum_effective_n_ratio':'0.7','risk_chain_top1_cap':'0.55'}}

class IndependentTests(unittest.TestCase):
    def test_all_supports_only_class_conflict_excluded(self):
        row=fixture();before=deepcopy(row);d=m.seed_domain(row)
        self.assertEqual(row,before);self.assertEqual(len(d['supports']),4)
        self.assertEqual([s['support_index'] for s in d['supports'] if s['structurally_excluded']],[1,3])
        self.assertTrue(all(set(s['support_security_ids']) >= {'GOOG','OLD'} for s in d['supports']))
        self.assertEqual(d['conditional_research_buy_ids'],['GOOG','GOOGL','NEW','OLD'])
        self.assertTrue(all(s['seed_buy_shares']['GOOGL']==0 for s in d['seeds']))
        self.assertTrue(any(all(q==0 for q in s['seed_buy_shares'].values()) for s in d['seeds']))
    def test_original_target_denominator_and_fraction_family(self):
        row=fixture();row['securities']['GOOGL']['issuer_id']='separate'
        d=m.seed_domain(row)
        self.assertEqual(d['normalized_original_targets']['GOOGL'],{'numerator':'1','denominator':'5'})
        self.assertEqual(d['normalized_original_targets']['NEW'],{'numerator':'4','denominator':'5'})
        self.assertEqual(len(d['supports']),4)
        fractions={Fraction(int(s['origin']['gross_budget_fraction']['numerator']),int(s['origin']['gross_budget_fraction']['denominator'])) for s in d['seeds'] if s['origin']['kind']=='ORIGINAL_TARGET_DIRECTION_FLOOR_CEIL'}
        self.assertEqual(fractions,set(m.FRACTIONS))
    def test_budget_prefix_counts_unknown_not_infeasibility(self):
        row=fixture();domain=m.seed_domain(row);seed=domain['seeds'][0];domain['seeds']=[deepcopy(seed) for _ in range(m.MAX_SEEDS+1)]
        close=Mock(return_value={'status':'UNKNOWN_ITERATION_BUDGET','buy_shares':None})
        evaluate=Mock(return_value={**dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','global_optimality_claimed'),False),'evaluated_count':0,'unevaluated_supplied_plan_count':0,'branches':[{'branch_id':'synthetic','evaluated_plans':[]}]})
        with patch.object(m,'seed_domain',return_value=domain):result=m.research_row(row,close,evaluate)
        self.assertEqual(close.call_count,m.MAX_SEEDS);self.assertEqual(result['unprocessed_seed_count'],1)
        self.assertIsNone(result['selected_candidate_index']);self.assertFalse(result['global_optimality_claimed'])
        self.assertEqual(evaluate.call_args.kwargs['plans_by_branch'],{'synthetic':[]})
        self.assertEqual(result['input_row'],row)

if __name__=='__main__':unittest.main()


