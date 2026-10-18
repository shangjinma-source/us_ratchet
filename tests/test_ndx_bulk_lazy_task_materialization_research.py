from copy import deepcopy
import importlib.util
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backtest import ndx_bulk_lazy_task_materialization_research as m
spec=importlib.util.spec_from_file_location('rebind_fixture',Path(__file__).with_name('test_bulk_completed_task_rebinding_20261003.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture():
 docs=f.fixture();plan=docs['plan']['plan'];ref=f.m.ref('plan');ref['sha256']='a'*64
 # The synthetic rebinding is built from synthetic matrices only, not saved results.
 with patch.dict(f.m.BOUND,{'plan':('synthetic.json','a'*64)}):
  docs['plan_publication']['plan_reference']=f.m.ref('plan');saved=f.m.assemble(docs);ref=f.m.ref('plan')
 p=docs['panel']['panel'];u=p['universe'];panel=dict(panel_reference=plan['context']['panel_reference'],panel_content_sha256='c'*64,dates=[x[:10] for x in p['returns']['index']],columns=p['returns']['columns'],returns=p['returns']['data'],universe=[dict(zip(u['columns'],r)) for r in u['data']])
 index=m.scheduling.indexing.IssuerCombinationIndex([(g['issuer_id'],g['security_ids']) for g in plan['canonical_groups']])
 savedrow=saved['rows'][0];loc=savedrow['new_location_identity'];oldprefix=list(index.unrank(loc['k'],loc['rank']));fresh=list(index.unrank(4,0));assert fresh!=oldprefix
 positions=[dict(k=loc['k'],rank=loc['rank'],prefix_security_ids=oldprefix,selection_kind='SID_COVERAGE',proposal_index=0),dict(k=4,rank=0,prefix_security_ids=fresh,selection_kind='STRATIFIED_RANK',proposal_index=1)]
 kwargs=dict(lazy_plan=plan,plan_reference=ref,panel=panel,positions=positions,max_combinations=2,completed_rebinding={'reference':{'path':'saved.json','sha256':'d'*64},'document':saved})
 return kwargs,index

class Tests(unittest.TestCase):
 def run_case(self,kw,index):
  with patch.object(m,'SCHEDULE_SHA',m.LOADED[str(Path(m.scheduling.__file__).resolve())]),patch.object(m.scheduling,'validate_lazy_plan',return_value=index):return m.materialize_positions(**kw)
 def test_two_combos_three_specs_one_reuse(self):
  kw,ix=fixture();before=deepcopy(kw);r=self.run_case(kw,ix);self.assertEqual(kw,before);self.assertEqual((r['materialized_task_count'],r['selected_completed_intersection_count'],r['new_unattempted_task_count']),(6,3,3));self.assertEqual(r['complete_saved_completed_task_count'],504)
  task=r['combinations'][0]['tasks'][0];self.assertIsNone(task['numerical_identity']['requested_previous_target_weights']);self.assertEqual(task['expected_fitter_previous_target_weights'],{});self.assertEqual(task['complete_saved_rebinding_row'],kw['completed_rebinding']['document']['rows'][0]);self.assertFalse(r['fit_performed'])
 def test_invalid_last_request_before_any_unrank(self):
  for kind in ['budget','bool','rank','duplicate','matrix']:
   kw,ix=fixture()
   if kind=='budget':kw['max_combinations']=1
   elif kind=='bool':kw['positions'][-1]['k']=True
   elif kind=='rank':kw['positions'][-1]['rank']=2
   elif kind=='duplicate':kw['positions'][-1]=deepcopy(kw['positions'][0])
   else:kw['panel']['returns'][-1][-1]=float('nan')
   with patch.object(type(ix),'unrank',side_effect=AssertionError('unrank called')) as call:
    with self.assertRaises(ValueError):self.run_case(kw,ix)
    call.assert_not_called()
 def test_saved_digest_not_enough_to_change_identity(self):
  kw,ix=fixture();kw['completed_rebinding']['document']['rows'][0]['old_completed_row']['full_task']['numerical_identity']['parameters']['min_single_weight']=.01
  with self.assertRaises(ValueError):self.run_case(kw,ix)
 def test_complete_sources_and_specs_not_alias(self):
  kw,ix=fixture();r=self.run_case(kw,ix);tasks=r['combinations'][1]['tasks'];self.assertEqual(len({t['numerical_task_id'] for t in tasks}),3);self.assertEqual(r['fitter_source_hashes'],kw['lazy_plan']['fitter_source_hashes']);self.assertEqual(r['remaining_full_plan_uncompleted_count'],kw['lazy_plan']['planned_canonical_task_count']-504)
 def test_actual_lazy_validator_with_synthetic_full_contract(self):
  from scripts import bulk_all_k_plan_20261003 as planner
  kw,ix=fixture();ctx=kw['lazy_plan']['context'];sources={str(Path('synthetic_fitter_'+str(i)).resolve()):'a'*64 for i in range(25)}
  plan=planner.prepare_lazy_plan(groups=[(g['issuer_id'],g['security_ids']) for g in kw['lazy_plan']['canonical_groups']],panel_reference=ctx['panel_reference'],panel_audit_reference=ctx['panel_audit_reference'],decision_cutoff=ctx['decision_cutoff'],parameters=ctx['parameters'],fitter_source_hashes=sources,previous_target_weights=None)
  kw['lazy_plan']=plan;saved=kw['completed_rebinding']['document'];saved['full_plan_task_denominator']=plan['planned_canonical_task_count'];saved['remaining_uncompleted_task_count']=plan['planned_canonical_task_count']-504
  for row in saved['rows']:
   task=row['old_completed_row']['full_task'];num=task['numerical_identity'];num['fitter_source_fingerprint']=plan['context']['fitter_source_fingerprint'];tid=m.digest(num);task['numerical_task_id']=tid;row['numerical_task_id']=tid;row['old_completed_row']['numerical_task_id']=tid
   loc,unused=f.m.new_location(plan,num,kw['plan_reference']);row['new_location_identity']=loc;row['new_location_id']=m.digest(loc)
  with patch.object(m,'SCHEDULE_SHA',m.LOADED[str(Path(m.scheduling.__file__).resolve())]),patch.object(m.old,'materialize_slice',side_effect=AssertionError('eager materializer')),patch.object(m.scheduling.contracts,'prepare_issuer_shards',side_effect=AssertionError('eager plan')):
   result=m.materialize_positions(**kw)
  self.assertEqual(result['selected_completed_intersection_count'],3);self.assertEqual(result['risk_chain_exposures']['4']['security_occurrence_count'],8)
 def test_source_pin_pending(self):
  kw,ix=fixture()
  with patch.object(m,'SCHEDULE_SHA',None),self.assertRaises(ValueError):m.materialize_positions(**kw)
if __name__=='__main__':unittest.main()
