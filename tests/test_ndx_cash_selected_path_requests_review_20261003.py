from copy import deepcopy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from test_ndx_cash_neighbor_selected_path_requests_research import fixture
from backtest import ndx_cash_neighbor_selected_path_requests_research as m

class Review(unittest.TestCase):
 def test_all40_request_only_first_buy_changed_preserving_every_zero_and_evidence(self):
    a=fixture();before=deepcopy(a);out=m.prepare_selected_path_requests(**a);self.assertEqual(a,before);self.assertEqual(len(out['rows']),40)
    for c,r in zip(a['cases'],out['rows']):
      expected=deepcopy(c['old_paired_row']['paths']['candidate']['accounting_inputs']);expected['sessions'][0]['buy_shares']=deepcopy(c['selection']['selected']['saved_plan']['buy_shares']);self.assertEqual(r['accounting_request'],expected)
      self.assertEqual(r['old_paired_evidence'],c['old_paired_row']);self.assertEqual(r['prepared_contract'],c['prepared']);self.assertEqual(r['selection'],c['selection']);self.assertIn('Z',r['accounting_request']['sessions'][-1]['close_prices']);self.assertEqual(r['accounting_request']['initial']['holdings']['Z'],0)
      self.assertTrue(all(r[k] is False for k in m.FLAGS));self.assertTrue(r['control_path_reference']['json_pointer'].endswith('/paths/same_flow_zero_trade_control'))
    self.assertEqual(sum(out['status_counts'].values()),40)
 def test_known_old_feasible_forbids_claiming_empty_union(self):
    a=fixture();a['cases'][0]['selection'].update(selected=None,status='NO_FEASIBLE_IN_DECLARED_UNION',reused_path_reference=None)
    with self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)
 def test_old_infeasible_point_cannot_be_promoted_to_selected(self):
    a=fixture();c=a['cases'][0];contract=c['prepared']['contract'];plan=deepcopy(c['selection']['selected']['saved_plan']);contract['old_evaluated_points'].append(dict(candidate_index=1,buy_shares=deepcopy(plan['buy_shares']),saved_feasible=False,reference=dict(contract['previous_result_reference'],json_pointer='/failed/point')))
    c['prepared']['contract_sha256']=m.digest(contract);c['selection']['contract_sha256']=c['prepared']['contract_sha256'];c['selection']['selected']=dict(origin='OLD',identity={'old_candidate_index':1},buy_shares=deepcopy(plan['buy_shares']),saved_plan=plan,feasible=True)
    with self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)
 def test_reuse_requires_exact_plan_and_firstflow_or_latertrade_cannot_shift(self):
    for mode in ('reuse_fee','firstflow','latertrade','zerokey','wrongscenario'):
      a=fixture();c=a['cases'][0]
      if mode=='reuse_fee':
        plan=deepcopy(c['old_paired_row']['selected_plan']);plan['fees_usd']='999';s=c['selection'];s.update(status='REUSE_EXISTING_PAIRED_PATH',reused_path_reference=s['old_selected_path']['reference'],selected=dict(origin='OLD',identity={'old_candidate_index':0},buy_shares=deepcopy(plan['buy_shares']),saved_plan=plan,feasible=True))
      elif mode=='firstflow':c['old_paired_row']['paths']['candidate']['accounting_inputs']['sessions'][0]['cash_injection_usd']='0'
      elif mode=='latertrade':c['old_paired_row']['paths']['candidate']['accounting_inputs']['sessions'][-1]['buy_shares']={'A':0,'Z':1}
      elif mode=='zerokey':del c['old_paired_row']['paths']['candidate']['accounting_inputs']['sessions'][-1]['open_prices']['Z']
      else:a['expected_scenario_ids'][0],a['expected_scenario_ids'][1]=a['expected_scenario_ids'][1],a['expected_scenario_ids'][0]
      with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)
if __name__=='__main__':unittest.main()
