"""Independent counterexamples; no account, selection or old audit invocation."""
import ast,copy,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_cash_neighbor_selected_paths_independent_readback_20261003 as m
ROOT=Path(__file__).resolve().parents[1]
def fixture_module(name):
 s=importlib.util.spec_from_file_location('fixture_'+name,ROOT/'tests'/name);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
class IndependentReview(unittest.TestCase):
 def test_two_days_loss_fee_and_injection_not_return(self):
  a,r,t=fixture_module('test_ndx_cash_neighbor_selected_paths_independent_readback_20261003.py').fixture()
  # Second day price halves, cash remains unchanged. Flow must not enter TWR numerator.
  a['sessions'].append(dict(session='2023-05-02',open_prices={'A':'25','Z':'1'},close_prices={'A':'12.5','Z':'1'},cash_injection_usd='0',buy_shares={}))
  row=copy.deepcopy(r['rows'][0]);row.update(previous_close_session='2023-05-01',session='2023-05-02',previous_close_equity_usd='1274.9',pre_flow_open_equity_usd='1274.9',cash_injection_usd='0',post_flow_pre_fee_open_equity_usd='1274.9',post_trade_open_equity_usd='1274.9',close_equity_usd='1087.4',gross_buy_usd='0',fees_usd='0',holdings_before={'A':15,'Z':0},buy_shares={},overnight_pnl_usd='0',intraday_mark_pnl_before_fees_usd='-187.5',after_flow_pnl_net_fees_usd='-187.5',cash_flow_adjusted_pnl_usd='-187.5')
  q=lambda n,d:{'numerator':str(n),'denominator':str(d)}
  row.update(overnight_return=q(0,1),after_flow_return=q(-1875,12749),session_twr=q(-1875,12749),cumulative_twr=q(2437,3000))
  r['rows'].append(row);r.update(terminal_equity_usd='1087.4',net_dollar_pnl_excluding_injections_usd='-12.6',chained_twr=q(2437,3000))
  self.assertEqual(m.inspect_account(a,r,t)['chained_twr'],q(2437,3000))
  for field,value in [('chained_twr',q(4937,500)),('total_fees_usd','0')]:
   bad=copy.deepcopy(r);bad[field]=value
   with self.assertRaises(ValueError):m.inspect_account(a,bad,t)
  for value in (False,5.0,'5'):
   bad=copy.deepcopy(a);bad['sessions'][0]['buy_shares']['A']=value
   with self.assertRaises(ValueError):m.inspect_account(bad,r,t)
 def test_request_original_refs_reuse_and_wrong_scenario(self):
  f=fixture_module('test_ndx_cash_neighbor_selected_path_requests_research.py').fixture()['cases'][0]
  p,s,o=f['prepared'],f['selection'],f['old_paired_row'];inputs={'paired':{'path':'paired','sha256':'a'*64},'selection_audit':{'path':'audit','sha256':'a'*64}};sr={'path':'selection','sha256':'a'*64}
  s=copy.deepcopy(s);plan=o['selected_plan'];oldref=dict(inputs['paired'],json_pointer='/rows/0/paths/candidate')
  s.update(status='REUSE_EXISTING_PAIRED_PATH',selected=dict(origin='OLD',identity={'old_candidate_index':0},buy_shares=plan['buy_shares'],saved_plan=plan,feasible=True),reused_path_reference=oldref)
  keys=('source_bytes_authenticated','selection_reexecuted','risk_recomputed','fees_recomputed','account_executed','control_reexecuted','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','nav_fx_equivalence_verified')
  r=dict(schema='CASH_NEIGHBOR_SELECTED_PATH_REQUEST_V1',scenario_index=0,scenario_id=o['scenario_id'],status=s['status'],prepared_contract=p,old_paired_evidence=o,selection=s,input_references=dict(selection_reference=dict(sr,json_pointer='/selection'),selection_audit_reference=dict(inputs['selection_audit'],json_pointer='/cases/0'),old_paired_reference=dict(inputs['paired'],json_pointer='/rows/0')),control_path_reference=dict(inputs['paired'],json_pointer='/rows/0/paths/same_flow_zero_trade_control'),reused_candidate_path_reference=oldref,accounting_request=None,expected_first_trade={k:plan[k]for k in ('buy_shares','proposed_holdings','gross_buy_usd','fees_usd','cash_after_usd')},candidate_decision_time_executability_verified=False,nav_reference_diagnostics_allowed=True,**dict.fromkeys(keys,False))
  m.inspect_request(r,s,p,o,0,inputs,sr)
  for mode in ('scenario','control','reuse','dispatch'):
   rr,ss=copy.deepcopy(r),copy.deepcopy(s)
   if mode=='scenario':ss['scenario_id']='foreign';rr['selection']=ss
   elif mode=='control':rr['control_path_reference']['json_pointer']='/rows/1/paths/same_flow_zero_trade_control'
   elif mode=='reuse':rr['reused_candidate_path_reference']['sha256']='b'*64
   else:rr['accounting_request']={}
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_request(rr,ss,p,o,0,inputs,sr)
 def test_partition_no_invented_completion_and_pending_before_io(self):
  ids=[str(i)for i in range(40)]
  r=dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1',scenario_count=40,status='COMPLETE_PENDING_INDEPENDENT_READBACK',completed_rows=[dict(scenario_index=i,scenario_id=x,outcome='REUSE_EXISTING_PAIRED_PATH')for i,x in enumerate(ids)],attempted_scenario_ids=[],unresolved_scenario_ids=[],undispatched_scenario_ids=[],failure=None,**m.FLAGS)
  self.assertEqual(m.inspect_partition(r,ids)['attempted'],0)
  for mode in ('bool','missing','swapped','attempt'):
   b=copy.deepcopy(r)
   if mode=='bool':b['completed_rows'][0]['scenario_index']=False
   elif mode=='missing':b['completed_rows'].pop()
   elif mode=='swapped':b['completed_rows'][0],b['completed_rows'][1]=b['completed_rows'][1],b['completed_rows'][0]
   else:b['attempted_scenario_ids']=['0']
   with self.assertRaises(ValueError):m.inspect_partition(b,ids)
  with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'absent'),patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected input IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
  tree=ast.parse(Path(m.__file__).read_text());self.assertFalse(any(isinstance(v,ast.Call)and isinstance(v.func,ast.Attribute)and v.func.attr in ('account_path','prepare_selected_path_requests') for v in ast.walk(tree)))
if __name__=='__main__':unittest.main()
