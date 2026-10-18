from copy import deepcopy
from fractions import Fraction
from decimal import localcontext,Inexact
import inspect,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_single_replacement_path_requests_research as m
from backtest import ndx_single_replacement_domain_research as domain
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from test_ndx_cash_neighbor_selected_path_requests_research import fixture as oldfixture

def fixture():
 oldcases=oldfixture()['cases'];original=[];olds=[]
 for i,c in enumerate(oldcases):
  old=c['old_paired_row'];r=old['input_row']
  for sid,s in r['securities'].items():s.update(issuer_id='issuer:'+sid,risk_chain='chain:'+sid)
  r.update(branch_role='MAIN_LANE',zero_buy_only=False,target_l1_applicable=True,fork_executable=False,target_weights_normalized=False,scenario_reference=dict(old['input_reference']),inventory_row_reference=dict(old['input_reference']),target_weights={'Z':'1'},allowed_buy_security_ids=['Z'],minimum_cash_buffer_usd='100',risk_parameters=dict(max_single_weight='1',min_single_weight='0.001',top_weight_cap='1',minimum_effective_n_ratio='0.001',risk_chain_top1_cap='1'),gaps=[{'reason':'CONDITIONAL_IDENTITY_ONLY'}])
  original.append(dict(input_row=r,input_reference=old['input_reference']));olds.append(old)
 refs={k:dict(path='E:/synthetic/'+k+'.json',sha256=chr(97+i)*64)for i,k in enumerate(('prepared','selection','selection_audit','old_paired'))}
 contract=dict(domain.SEMANTICS,expected_scenario_ids=[r['input_row']['scenario_id']for r in original],domain_core_reference=dict(path='E:/synthetic/domain.py',sha256='e'*64),action_contract_reference=dict(path='E:/synthetic/policy.json',sha256='f'*64))
 p=domain.prepare_single_replacement_domain(original,contract);rows=[]
 for i,c in enumerate(p['document']['cases']):
  task=domain.unrank(p,c['first_global_ordinal']);r=c['identity']['original_input_row'];fee=Fraction(3,25);cash=Fraction(r['starting_cash_usd'])+Fraction(r['cash_event']['amount_usd'])+100-20-fee
  evaluation=dict(status='FEASIBLE',feasible=True,gross_sell_usd='100',gross_buy_usd='20',total_fee_usd=str(fee),cash_after_usd=str(cash))
  record=dict(global_ordinal=task['global_ordinal'],task=task,evaluation=evaluation,source_reference={'preserved':'actual source locator comes from audited selection'},inspection_reference={'preserved':'actual per-task source pointer'})
  rows.append(dict(scenario_index=i,scenario_id=c['scenario_id'],scenario_identity_sha256=c['identity_sha256'],pair_count=c['pair_count'],integer_count=c['integer_count'],financial_integer_count_before_issuer=c['financial_integer_count_before_issuer'],structurally_excluded_integer_count=c['structurally_excluded_integer_count'],feasible_count=1,infeasible_count=c['integer_count']-1,status='SELECTED_REQUIRES_NEW_SIGNED_PATH',selected=record))
 d=p['document'];s=dict(schema='SINGLE_REPLACEMENT_COMPLETE_DOMAIN_SELECTION_V1',status='COMPLETE_WITHIN_FAMILY_SELECTION_NOT_ACCOUNT_OR_CROSS_FAMILY_WINNER',preparation_reference=refs['prepared'],prepared_content_sha256=p['content_sha256'],action_contract=deepcopy(contract),all_registered_points_consumed=True,rows=rows,feasible_count=40,infeasible_count=d['integer_count']-40,selected_case_count=40,no_feasible_case_count=0,**{k:d[k]for k in('scenario_count','pair_count','integer_count','financial_integer_count_before_issuer','structurally_excluded_integer_count')},**dict.fromkeys(('source_bytes_authenticated','point_in_time_verified','account_executed','fit_executed','future_returns_used','global_optimality_claimed'),False))
 return dict(prepared=p,selection=dict(document=s,content_sha256=m.digest(s)),old_paired_rows=olds,source_references=refs)
def resign(a):a['selection']['content_sha256']=m.digest(a['selection']['document'])
class Tests(unittest.TestCase):
 def test_full_physical_json_compatibility_no_account_called(self):
  a=fixture()
  with tempfile.TemporaryDirectory()as t:
   path=Path(t)/'synthetic-source-objects.json';path.write_bytes(m.encode(a));a=json.loads(path.read_bytes())
  before=deepcopy(a)
  with patch.object(account,'account_path',side_effect=AssertionError('No accounting call')),localcontext()as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True;out=m.prepare_single_replacement_path_requests(**a)
  self.assertEqual(a,before);self.assertEqual(out['new_account_request_count'],40)
  request=out['rows'][0]['accounting_request'];self.assertEqual(request['sessions'][0]['trade_shares'],{'A':-10,'Z':1});self.assertTrue(all(x['trade_shares']=={}for x in request['sessions'][1:]));self.assertEqual(request['initial'],a['old_paired_rows'][0]['paths']['candidate']['accounting_inputs']['initial'])
  inspect.signature(account.account_path).bind(**request)
  self.assertEqual(Fraction(out['rows'][0]['expected_first_trade']['total_fee_usd']),Fraction(3,25));self.assertEqual(Fraction(out['rows'][0]['expected_first_trade']['cash_after_usd']),Fraction(51997,25))
  self.assertEqual(out['rows'][0]['selection_reference']['json_pointer'],'/selection/document/rows/0');self.assertIsNone(out['rows'][0]['reused_candidate_path_reference']);self.assertEqual(out['rows'][0]['original_gaps'],a['old_paired_rows'][0]['input_row']['gaps'])
 def test_missing_zero_quote_blocks_no_fill_and_no_feasible_no_cash(self):
  a=fixture();del a['old_paired_rows'][0]['paths']['candidate']['accounting_inputs']['sessions'][1]['open_prices']['Z']
  s=a['selection']['document'];r=s['rows'][1];r.update(status='NO_FEASIBLE',selected=None,feasible_count=0,infeasible_count=r['integer_count']);s.update(feasible_count=39,infeasible_count=s['integer_count']-39,selected_case_count=39,no_feasible_case_count=1);resign(a)
  out=m.prepare_single_replacement_path_requests(**a);self.assertEqual(out['status_counts'],{'NEW_SIGNED_PATH_REQUIRED':38,'NO_FEASIBLE':1,'BLOCKED_TEMPLATE_PRICE_GAP':1});self.assertIsNone(out['rows'][0]['accounting_request']);self.assertIsNone(out['rows'][1]['accounting_request'])
 def test_signed_trade_flow_date_identity_attacks(self):
  for kind in ('sell','zero','flow','firstopen','date','initial','order','bool'):
   a=fixture();s=a['selection']['document']['rows'][0]['selected'];old=a['old_paired_rows'][0];sessions=old['paths']['candidate']['accounting_inputs']['sessions']
   if kind=='sell':s['task']['signed_trade_quantities']['A']=-9
   elif kind=='zero':del s['task']['proposed_holdings']['A']
   elif kind=='flow':sessions[1]['cash_injection_usd']='1000'
   elif kind=='firstopen':sessions[0]['open_prices']['Z']='21'
   elif kind=='date':sessions[0]['session']='2023-05-02'
   elif kind=='initial':old['paths']['candidate']['accounting_inputs']['initial']['cash_usd']='999'
   elif kind=='order':a['old_paired_rows'].reverse()
   else:s['task']['scenario_index']=False
   resign(a)
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare_single_replacement_path_requests(**a)
 def test_partial_domain_and_source_conflict_rejected(self):
  a=fixture();a['old_paired_rows'].pop()
  with self.assertRaises(ValueError):m.prepare_single_replacement_path_requests(**a)
  a=fixture();a['source_references']['selection_audit']['path']=a['source_references']['selection']['path']
  with self.assertRaises(ValueError):m.prepare_single_replacement_path_requests(**a)
if __name__=='__main__':unittest.main()
