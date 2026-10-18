import copy
import unittest
from backtest import ndx_cash_neighbor_selection_research as m


def ref(n): return {'path':str(n),'sha256':('%064x'%n)}
def ratio(n): return {'numerator':n,'denominator':1}
def score(n): return {'distance':ratio(n),'fees_usd':ratio(1)}
def plan(q,i=0,feasible=True): return dict(supplied_plan_index=i,buy_shares={'A':q},proposed_holdings={'A':q},fees_usd='1',feasible=feasible)
def fixture():
    old=[plan(1),plan(2,1,False)]
    points=[dict(candidate_index=i,buy_shares=p['buy_shares'],saved_feasible=p['feasible'],reference=ref(i+10)) for i,p in enumerate(old)]
    c=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1',rule='R',scenario_id='s',original_input_row={'scenario_id':'s'},input_reference=ref(4),conditional_research_buy_ids=['A'],saved_buy_limits={'A':10},old_evaluated_points=points,original_selected_candidate_index=0)
    prepared=dict(contract=c,contract_sha256=m.digest(c))
    previous=dict(scenario_id='s',input_row=c['original_input_row'],input_reference=ref(4),evaluation={'branches':[{'branch_id':'s','evaluated_count':2,'evaluated_plans':old}],'unevaluated_supplied_plan_count':0},feasible_scores=[dict(candidate_index=0,**score(2))],selected_candidate_index=0)
    full={'reference':ref(500),'document':{'schema':'CASH_NEIGHBOR_FULL_BATCH_INDEPENDENT_READBACK_V1','status':'PASS','counts':dict(task_count=301657,new_arithmetic_checked_total_including_previously_audited_first=301656,external_original_single_task_count=1,ordered_shard_count=324,outcome_counts=dict(FEASIBLE=301656,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=1)),'shard_audit_references':[ref(i+1000) for i in range(324)]}}
    identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule='R',scenario_contract_sha256=prepared['contract_sha256'],buy_shares={'A':3})
    tid=m.digest(identity); checked=dict(task_id=tid,outcome='FEASIBLE',new_arithmetic_checked=True,original_target_stock_weight_l1=score(1))
    record=dict(task=dict(task_id=tid,identity=identity,scenario_id='s',scenario_candidate_ordinal=0),references={k:ref(i+30) for i,k in enumerate(('task','raw','postcheck'))},audit_task_index=0,shard_audit={'reference':ref(1000),'document':{'schema':'CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1','status':'PASS','detail':{'task_results':[checked]}}},raw=dict(error=None,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=1,result={'branches':[{'branch_id':'s','evaluated_plans':[plan(3)]}]}),postcheck=dict(outcome='FEASIBLE',evaluation_error=None,validation_error=None,original_target_stock_weight_l1=score(1)))
    return dict(prepared=prepared,previous_row=previous,new_records=[record],expected_new_count=1,old_selected_path=dict(reference=ref(5),scenario_id='s',buy_shares={'A':1},selected_candidate_index=0),full_audit=full,tie_policy=m.POLICY)

class Tests(unittest.TestCase):
    def test_new_best_original_tie_and_immutability(self):
        args=fixture(); before=copy.deepcopy(args); result=m.select_scenario(**args)
        self.assertEqual(result['status'],'NEW_PATH_REQUIRED');self.assertEqual(result['selected']['buy_shares'],{'A':3});self.assertEqual(args,before)
        for obj in (args['new_records'][0]['postcheck'],args['new_records'][0]['shard_audit']['document']['detail']['task_results'][0]): obj['original_target_stock_weight_l1']=score(2)
        result=m.select_scenario(**args);self.assertEqual(result['status'],'REUSE_EXISTING_PAIRED_PATH');self.assertEqual(result['reused_path_reference'],ref(5))
    def test_missing_reordered_bool_technical_and_fee_rejected(self):
        changes=[lambda a:a.update(new_records=[]),lambda a:a['new_records'][0]['task'].update(scenario_candidate_ordinal=1),lambda a:a['new_records'][0]['raw'].update(returned_evaluation_count=True),lambda a:a['new_records'][0]['postcheck'].update(validation_error='error'),lambda a:a['new_records'][0]['raw']['result']['branches'][0]['evaluated_plans'][0].update(fees_usd='2'),lambda a:a['full_audit'].update(reference=None)]
        for change in changes:
            a=fixture();change(a)
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):m.select_scenario(**a)
    def test_infeasible_preserved_and_no_feasible(self):
        a=fixture();r=a['new_records'][0];r['raw']['result']['branches'][0]['evaluated_plans'][0]['feasible']=False
        for obj in (r['postcheck'],r['shard_audit']['document']['detail']['task_results'][0]):obj.update(outcome='INFEASIBLE',original_target_stock_weight_l1=None)
        out=m.select_scenario(**a);self.assertEqual(out['total_candidate_count'],3);self.assertFalse(out['candidate_ledger'][-1]['feasible'])
        a['previous_row']['evaluation']['branches'][0]['evaluated_plans'][0]['feasible']=False;a['previous_row'].update(feasible_scores=[],selected_candidate_index=None)
        c=a['prepared']['contract'];c['old_evaluated_points'][0]['saved_feasible']=False;c['original_selected_candidate_index']=None;a['prepared']['contract_sha256']=m.digest(c)
        r['task']['identity']['scenario_contract_sha256']=a['prepared']['contract_sha256'];r['task']['task_id']=m.digest(r['task']['identity']);r['shard_audit']['document']['detail']['task_results'][0]['task_id']=r['task']['task_id'];a['old_selected_path']=None
        self.assertEqual(m.select_scenario(**a)['status'],'NO_FEASIBLE_IN_DECLARED_UNION')
    def test_duplicate_old_vector_and_audit_unlinked(self):
        a=fixture();a['new_records'][0]['shard_audit']['reference']=ref(9999)
        with self.assertRaises(ValueError):m.select_scenario(**a)
        a=fixture();r=a['new_records'][0];r['task']['identity']['buy_shares']={'A':1};r['task']['task_id']=m.digest(r['task']['identity']);r['shard_audit']['document']['detail']['task_results'][0]['task_id']=r['task']['task_id'];r['raw']['result']['branches'][0]['evaluated_plans'][0]['buy_shares']={'A':1}
        with self.assertRaises(ValueError):m.select_scenario(**a)

if __name__=='__main__':unittest.main()
