import unittest,tempfile,json,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock,patch
from test_bulk_budgeted_search_prepare_20261003 import module as m,panel_fixture

SIDE=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
def fixture():
 refs={k:{'path':'/'+k,'sha256':'a'*64} for k in ('plan','panel','rebinding')}
 panel=panel_fixture();panel['panel']['observed_provenance_and_missing']=[{} for _ in range(101)]
 for k in SIDE:panel[k]={}
 plan={'plan':{'context':{'panel_reference':refs['panel']},'planned_canonical_task_count':10000},'source_hashes':{},'complete_observed_provenance_and_missing':deepcopy(panel['panel']['observed_provenance_and_missing']),'preserved_evidence_sidecar_references':{k:dict(refs['panel'],json_pointer='/'+k) for k in SIDE},**m.FALSE}
 panel['source_hashes']={}
 rb={'source_hashes':{},'input_references':{'plan':refs['plan'],'panel':refs['panel']},'externally_rebound_task_count':504,'new_fit_count':0,'new_wrapper_call_attempt_count':0,'remaining_uncompleted_task_count':9496,'complete_observed_provenance_and_missing':deepcopy(plan['complete_observed_provenance_and_missing']),**m.FALSE}
 docs={'plan':plan,'panel':panel,'rebinding':rb,'contract':json.loads((m.ROOT/m.PINS['contract'][0]).read_bytes())}
 for role,field,status in [('plan','plan_reference','PLANNED_NOT_ENUMERATED'),('panel','panel_reference','PUBLISHED_CONDITIONAL_PANEL_ONLY'),('rebinding','rebinding_reference','PUBLISHED_REFERENCE_ONLY')]:docs[role+'_publication']={field:refs[role],'status':status,'source_hashes':{}}
 scheduler=Mock();scheduler.plan_budgeted_positions.return_value={'status':'PLANNED_NOT_ATTEMPTED','materialization_allowed':True,'positions':[{}]*544}
 mat=Mock();mat.materialize_positions.return_value={'combination_count':544,'materialized_task_count':1632,'complete_saved_completed_task_count':504,'selected_completed_intersection_count':0,'new_unattempted_task_count':1632,'remaining_full_plan_uncompleted_count':9496}
 return docs,refs,scheduler,mat
class IndependentWrapperReview(unittest.TestCase):
 def test_complete_sidecar_and_zero_count_guards_before_pure(self):
  for attack in ('sidecar-key','pointer','bool-fit','bool-attempt'):
   d,r,s,z=fixture()
   if attack=='sidecar-key':d['plan']['preserved_evidence_sidecar_references']['unknown']=d['plan']['preserved_evidence_sidecar_references'].pop(SIDE[-1])
   elif attack=='pointer':d['plan']['preserved_evidence_sidecar_references'][SIDE[-1]]['json_pointer']='/wrong'
   elif attack=='bool-fit':d['rebinding']['new_fit_count']=False
   else:d['rebinding']['new_wrapper_call_attempt_count']=False
   with self.assertRaises(ValueError):m.assemble(d,r,s,z)
   s.plan_budgeted_positions.assert_not_called();z.materialize_positions.assert_not_called()
 def test_only_true_materialization_permission_and_exact_forwarding(self):
  for permission in (False,1,None):
   d,r,s,z=fixture();s.plan_budgeted_positions.return_value['materialization_allowed']=permission
   with self.assertRaises(ValueError):m.assemble(d,r,s,z)
   z.materialize_positions.assert_not_called()
  d,r,s,z=fixture();out=m.assemble(d,r,s,z)
  self.assertEqual(out['remaining_uncompleted_task_count'],9496);self.assertEqual(z.materialize_positions.call_args.kwargs['completed_rebinding'],{'reference':r['rebinding'],'document':d['rebinding']})
 def test_loaded_source_guard_without_touching_real_source(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'wrapper.py';p.write_bytes(b'initial');h=m.sha(p.read_bytes())
   with patch.object(m,'SOURCE',p),patch.object(m,'LOADED_SHA',h):
    with self.assertRaises(ValueError):m.guard({str(p):'f'*64})
    p.write_bytes(b'changed')
    with self.assertRaises(ValueError):m.guard({})
 def test_parent_orphan_and_cached_import_rejected_before_import(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);pins={}
   for role in ('plan','panel','rebinding'):
    folder=root/role;folder.mkdir();raw=json.dumps({'plan':{'fitter_source_hashes':{}}}).encode();(folder/(role+'.json')).write_bytes(raw);(folder/'started.json').write_text('{}');(folder/'publication.json').write_text('{}');pins[role]=(role+'/'+role+'.json',m.sha(raw))
   with patch.object(m,'ROOT',root),patch.object(m,'PINS',pins),patch.object(m,'CODE_PINS',{'backtest/cached_review_core.py':'a'*64}),patch.object(m,'AUDIT_PINS',{}),patch.object(m,'guard'),patch.object(m.importlib,'import_module') as imp:
    (root/'panel'/'failure.json').write_text('{}')
    with self.assertRaisesRegex(ValueError,'namespace'):m.load_inputs()
    (root/'panel'/'failure.json').unlink()
    with patch.dict(sys.modules,{'backtest.cached_review_core':object()}):
     with self.assertRaisesRegex(ValueError,'Fresh'):m.load_inputs()
    imp.assert_not_called()
if __name__=='__main__':unittest.main()
