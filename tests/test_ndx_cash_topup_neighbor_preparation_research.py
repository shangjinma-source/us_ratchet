from copy import deepcopy
import itertools,unittest
from backtest import ndx_cash_topup_neighbor_preparation_research as m
def fixture():
    ref=dict(path='input.json',sha256='a'*64,json_pointer='/rows/0');oldref=dict(path='old.json',sha256='b'*64,json_pointer='/rows/0')
    row=dict(branch_role='MAIN_LANE',scenario_id='test',target_weights={'A':'0.5','B':'0.5'},holdings={'A':3},securities={'A':{'issuer_id':'I'},'B':{'issuer_id':'J'}},execution_prices={'A':'10','B':'20'},allowed_buy_security_ids=['B'],cash_event={'amount_usd':'1000'},gaps=['UNCHANGED'],**dict.fromkeys(('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'),False))
    plans=[dict(buy_shares={'A':1,'B':1},feasible=True),dict(buy_shares={'A':2,'B':1},feasible=True),dict(buy_shares={'A':0,'B':0},feasible=False)]
    old=dict(input_reference=ref,input_row=deepcopy(row),scenario_id='test',domain={'conditional_research_buy_ids':['A','B'],'buy_limits':{'A':3,'B':3}},evaluation={'branches':[dict(branch_id='test',evaluated_count=3,evaluated_plans=plans)]},original_allowed_buy_security_ids=['B'],selected_candidate_index=0,assumption='CONDITIONAL',new_buy_domain_is_research_assumption=True,target_weights_changed=False,cash_must_be_fully_invested=False,**dict.fromkeys(('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'),False))
    return dict(input_row=row,previous_row=old,input_reference=ref,previous_reference=oldref)
class Tests(unittest.TestCase):
    def test_full_grid_oracle_two_seeds_and_old_failed_excluded(self):
        a=fixture();before=deepcopy(a);p=m.prepare_scenario(**a);stats={};rows=list(m.iter_neighbors(p,stats))
        expected=set()
        for seed in [(1,1),(2,1)]:
            for v in itertools.product(range(4),repeat=2):
                dif=[abs(x-y) for x,y in zip(v,seed)]
                if max(dif)==1 and sum(x>0 for x in dif) in (1,2):expected.add(v)
        expected-={(1,1),(2,1),(0,0)}
        self.assertEqual({tuple(x['identity']['buy_shares'][s] for s in ('A','B')) for x in rows},expected)
        self.assertEqual(stats['raw_move_attempt_count'],16);self.assertEqual(stats['unprocessed_move_count'],0);self.assertEqual(a,before)
        self.assertTrue(all(x['evaluation_status']=='NOT_EVALUATED' for x in rows));self.assertEqual(len({x['task_id'] for x in rows}),len(rows))
    def test_identity_changes_for_source_or_cash_and_bool_reject(self):
        a=fixture();p=m.prepare_scenario(**a);a['input_row']['cash_event']['amount_usd']='10000';a['previous_row']['input_row']=deepcopy(a['input_row']);q=m.prepare_scenario(**a);self.assertNotEqual(p['contract_sha256'],q['contract_sha256'])
        a=fixture();a['previous_row']['evaluation']['branches'][0]['evaluated_plans'][0]['feasible']=1
        with self.assertRaises(ValueError):m.prepare_scenario(**a)
    def test_partial_iteration_is_not_complete_and_no_negative_new_buy(self):
        p=m.prepare_scenario(**fixture());stats={};it=m.iter_neighbors(p,stats);next(it);self.assertGreater(stats['unprocessed_move_count'],0)
        rows=list(it);self.assertTrue(all(v>=0 for x in rows for v in x['identity']['buy_shares'].values()));self.assertFalse(p['contract']['holdings_sold'])
    def test_changed_contract_or_missing_coordinate_reject(self):
        p=m.prepare_scenario(**fixture());p['contract']['saved_buy_limits']['A']=99
        with self.assertRaises(ValueError):list(m.iter_neighbors(p,{}))
        a=fixture();a['previous_row']['domain']['conditional_research_buy_ids']=['B']
        with self.assertRaises(ValueError):m.prepare_scenario(**a)
if __name__=='__main__':unittest.main()
