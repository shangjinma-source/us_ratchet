from copy import deepcopy
from unittest.mock import patch
import unittest
from backtest import ndx_cash_neighbor_stream_selection_research as m
from backtest import ndx_cash_neighbor_selection_research as old
from test_ndx_cash_neighbor_selection_research import fixture,score,ref

EXTRA=('ledger_emitted_row_count','ledger_storage_external','ledger_emitter_source_authenticated','emitted_prefix_valid_only_after_successful_return','parent_policy_source_sha256')
def compare(args):
    saved=deepcopy(args);expected=old.select_scenario(**deepcopy(args));emitted=[]
    args=dict(args);args['new_records']=iter(args['new_records'])
    result=m.select_scenario_stream(**args,emit_ledger_row=lambda row:emitted.append(row))
    actual={k:v for k,v in result.items() if k not in EXTRA};actual['schema']='CASH_NEIGHBOR_SCENARIO_SELECTION_V1';actual['candidate_ledger']=emitted
    assert actual==expected
    return result,emitted,saved

class Tests(unittest.TestCase):
    def test_stream_ledger_exact_old_version_and_input_unchanged(self):
        args=fixture();before=deepcopy(args);result,rows,_=compare(args)
        self.assertEqual(args,before);self.assertEqual(result['ledger_emitted_row_count'],3);self.assertEqual(len(rows),3);self.assertNotIn('candidate_ledger',result);self.assertEqual(result['status'],'NEW_PATH_REQUIRED')
        self.assertFalse(rows[1]['feasible']);self.assertTrue(result['ledger_storage_external'])
    def test_equal_score_old_first_and_new_first_ties(self):
        a=fixture()
        for d in (a['new_records'][0]['postcheck'],a['new_records'][0]['shard_audit']['document']['detail']['task_results'][0]):d['original_target_stock_weight_l1']=score(2)
        result,rows,_=compare(a);self.assertEqual(result['status'],'REUSE_EXISTING_PAIRED_PATH')
        a=fixture();r=deepcopy(a['new_records'][0]);r['task']['identity']['buy_shares']['A']=4;r['task']['task_id']=m.digest(r['task']['identity']);r['task']['scenario_candidate_ordinal']=1
        r['raw']['result']['branches'][0]['evaluated_plans'][0]['buy_shares']['A']=4;r['shard_audit']['document']['detail']['task_results'][0]['task_id']=r['task']['task_id'];a['new_records'].append(r);a['expected_new_count']=2
        result,rows,_=compare(a);self.assertEqual(result['selected']['buy_shares'],{'A':3});self.assertEqual(len(rows),4)
    def test_emitter_failures_return_values_and_mutation(self):
        def bad(row):raise RuntimeError('disk failure')
        def returned(row):return {'fake':'receipt'}
        def mutation(row):row['buy_shares']['A']=999
        for callback,error in ((None,ValueError),(bad,RuntimeError),(returned,ValueError),(mutation,ValueError)):
            a=fixture();before=deepcopy(a)
            with self.subTest(callback=callback),self.assertRaises(error):m.select_scenario_stream(**a,emit_ledger_row=callback)
            self.assertEqual(a,before)
    def test_truncated_extra_duplicate_bool_and_unlinked(self):
        for mode in ('missing','extra','duplicate','bool','audit','score'):
            a=fixture()
            if mode=='missing':a['new_records']=[]
            elif mode=='extra':a['new_records']*=2
            elif mode=='duplicate':
                r=a['new_records'][0];r['task']['identity']['buy_shares']={'A':1};r['task']['task_id']=m.digest(r['task']['identity']);r['raw']['result']['branches'][0]['evaluated_plans'][0]['buy_shares']={'A':1};r['shard_audit']['document']['detail']['task_results'][0]['task_id']=r['task']['task_id']
            elif mode=='bool':a['new_records'][0]['task']['scenario_candidate_ordinal']=False
            elif mode=='audit':a['new_records'][0]['shard_audit']['reference']=ref(9999)
            else:a['new_records'][0]['postcheck']['original_target_stock_weight_l1']['distance']['denominator']=True
            emitted=[]
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.select_scenario_stream(**a,emit_ledger_row=lambda r:emitted.append(r))
            # Earlier emitted rows remain diagnostics; no successful result is returned.
            self.assertLessEqual(len(emitted),3)
    def test_original_external_first_audit_exact_binding(self):
        a=fixture();r=a['new_records'][0];tid=r['task']['task_id'];single_ref=ref(600)
        checked=r['shard_audit']['document']['detail']['task_results'][0];checked.update(outcome='EXTERNALLY_REFERENCED',new_arithmetic_checked=False)
        single=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1',status='PASS',task_id=tid,returned_arithmetic_independently_verified=True,technical_failure_preserved=False,attempt_outcome='FEASIBLE',raw_reference=r['references']['raw'],postcheck_reference=r['references']['postcheck'],original_target_stock_weight_l1=score(1))
        r['single_audit']=dict(reference=single_ref,document=single);a['full_audit']['document']['source_hashes']={q['path']:q['sha256'] for q in (single_ref,r['references']['raw'],r['references']['postcheck'])}
        with patch.object(m,'FIRST_ID',tid),patch.object(old,'FIRST_ID',tid):
            result,rows,_=compare(a);self.assertEqual(result['new_candidate_count'],1);self.assertEqual(rows[-1]['references']['single_audit'],single_ref)
            a['full_audit']['document']['source_hashes'][single_ref['path']]='f'*64
            with self.assertRaises(ValueError):m.select_scenario_stream(**a,emit_ledger_row=lambda r:None)
    def test_no_feasible_remains_no_path_not_cash(self):
        a=fixture();r=a['new_records'][0];r['raw']['result']['branches'][0]['evaluated_plans'][0]['feasible']=False
        for d in (r['postcheck'],r['shard_audit']['document']['detail']['task_results'][0]):d.update(outcome='INFEASIBLE',original_target_stock_weight_l1=None)
        a['previous_row']['evaluation']['branches'][0]['evaluated_plans'][0]['feasible']=False;a['previous_row'].update(feasible_scores=[],selected_candidate_index=None)
        c=a['prepared']['contract'];c['old_evaluated_points'][0]['saved_feasible']=False;c['original_selected_candidate_index']=None;a['prepared']['contract_sha256']=m.digest(c)
        r['task']['identity']['scenario_contract_sha256']=a['prepared']['contract_sha256'];r['task']['task_id']=m.digest(r['task']['identity']);r['shard_audit']['document']['detail']['task_results'][0]['task_id']=r['task']['task_id'];a['old_selected_path']=None
        result,rows,_=compare(a);self.assertIsNone(result['selected']);self.assertEqual(result['status'],'NO_FEASIBLE_IN_DECLARED_UNION');self.assertEqual(len(rows),3)
if __name__=='__main__':unittest.main()
