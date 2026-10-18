from copy import deepcopy
from itertools import combinations,product
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from scripts import ndx_new_cutoff_ctas_combination_independent_readback_20260925 as m

def batch():
 groups=[dict(issuer_id='I%02d'%i,security_ids=(['s00a','s00b'] if i==0 else [m.CTAS] if i==22 else ['s%02d'%i])) for i in range(23)]
 plan=dict(canonical_groups=groups,shards=[],fitter_source_hashes={});panel={'universe':[dict(security_id=s,ticker='CTAS' if s==m.CTAS else s) for g in groups for s in g['security_ids']]};values=[];selections=[]
 for k in range(4,21):
  shard=dict(k=k,start=0,stop=10**9,shard_id=m.pure.digest({'k':k}));plan['shards'].append(shard)
  for local in range(2):
   prefix=[g['security_ids'][0] for g in groups[:k-1]]+[m.CTAS]
   if local:
    if k==23:prefix[0]='s00b'
    else:prefix[-2]=groups[k-1]['security_ids'][0]
   rank=m.pure.independent_position(m.pure.groups_contract(groups),prefix)
   selections.append(dict(k=k,forced_local_rank=local,prefix_security_ids=prefix,full_rank=rank,shard_id=shard['shard_id']))
   tasks=[dict(numerical_task_id=m.pure.digest((k,local,spec)),location_id=m.pure.digest(('loc',k,local,spec))) for spec in range(3)]
   values.append(dict(k=k,start=rank,stop=rank+1,combinations=[dict(prefix_security_ids=prefix,tasks=tasks)]))
 return dict(materializations=values,selections=selections,plan=plan,panel=panel,old_ids=[m.pure.digest(('old',i)) for i in range(402)])

class Tests(unittest.TestCase):
 def test_all_five_saved_anchors_bytes_only_and_forced_denominator(self):
  for role in m.BOUND:
   reference=m.ref(role)
   if reference['sha256'] is not None:self.assertEqual(m.codec.sha(Path(reference['path']).read_bytes()),reference['sha256'],role)
  sizes=[1]*21+[2]
  self.assertEqual(sum(m.coefficient(sizes,k-1) for k in range(4,21)),6290694)
  self.assertEqual(m.coefficient(sizes,22),2)
 def test_constrained_rank_exhaustive_small_issuer_classes(self):
  groups=[dict(issuer_id='A',security_ids=['a','aa']),dict(issuer_id='B',security_ids=['b']),dict(issuer_id='C',security_ids=['c','cc']),dict(issuer_id='D',security_ids=['d'])]
  lookup={s:(i,j) for i,g in enumerate(groups) for j,s in enumerate(g['security_ids'])}
  for target in ('a','b','cc','d'):
   for k in range(1,5):
    values=[]
    for chosen in combinations(range(4),k):
     values.extend(list(v) for v in product(*(groups[i]['security_ids'] for i in chosen)) if target in v)
    values.sort(key=lambda p:[lookup[s] for s in p]);self.assertEqual([m.forced_rank(groups,p,target) for p in values],list(range(len(values))))
 def test_34_singletons102_disjoint_tasks_no_full_enumeration(self):
  a=batch()
  with patch.object(m.pure,'verify_materialized',return_value={'synthetic':True}) as check:
   result=m.validate_materializations(**a);self.assertEqual(len(result['numerical_task_ids']),102);self.assertEqual(check.call_count,34)
   self.assertTrue(all(c.kwargs['max_materialized_combinations']==1 for c in check.call_args_list))
  self.assertNotEqual(a['selections'][0]['full_rank'],0)
 def test_later_prefix_fullrank_duplicate_oldtask_and_missing(self):
  for attack in ('later','fullrank','old','count','spec','target'):
   a=batch()
   if attack=='later':a['materializations'][0]['combinations'][0]['prefix_security_ids'][-2]='s04'
   elif attack=='fullrank':a['materializations'][0]['start']=0;a['materializations'][0]['stop']=1
   elif attack=='old':a['old_ids'][0]=a['materializations'][0]['combinations'][0]['tasks'][0]['numerical_task_id']
   elif attack=='count':a['materializations'].pop()
   elif attack=='spec':a['materializations'][0]['combinations'][0]['tasks'].pop()
   else:a['materializations'][0]['combinations'][0]['prefix_security_ids'][-1]='s18'
   with self.subTest(attack=attack),patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**a)
 def test_full_envelope_counts_sidecars_oldrefs_and_permissions(self):
  a=batch();plan=a['plan'];plan['planned_canonical_task_count']=37740237;plan['cardinalities']=[dict(k=k,necessary_bound_certificates=[]) for k in range(1,21)]
  docs={'plan':dict(complete_observed_provenance_and_missing={'all101':'kept'},preserved_evidence_sidecar_reference={'old':'whole'},preserved_incremental_evidence_sidecar_reference={'v2':'whole'},preserved_v3_incremental_evidence_sidecar_reference={'v3':'whole'},preserved_v4_incremental_evidence_sidecar_reference={'v4':'whole'},preserved_v5_incremental_evidence_sidecar_reference={'v5':'whole'},preserved_v6_incremental_evidence_sidecar_reference={'v6':'whole'})}
  sizes=[len(g['security_ids']) for g in plan['canonical_groups'] if m.CTAS not in g['security_ids']];denominators=[dict(k=k,forced_combination_count=m.coefficient(sizes,k-1)) for k in range(4,21)]
  value=dict(schema='NEW_CUTOFF_CTAS_COMBINATION_MATERIALIZATION_V1',input_references={k:m.ref(k) for k in m.BOUND},source_hashes={},selections=a['selections'],new_materializations=a['materializations'],forced_sid=m.CTAS,forced_combination_counts=denominators,selection_rule='FIRST_TWO_FORCED_CTAS_PREFIX_COMBINATIONS_PER_K4_TO20_NO_SCORE_SELECTION',reused_completed_reference=dict(rebinding_reference=m.ref('rebinding'),independent_readback_reference=m.ref('rebinding_audit'),numerical_task_ids=a['old_ids']),new_combination_count=34,new_task_count=102,new_completed_task_count=0,external_completed_task_count=402,full_plan_task_denominator=37740237,remaining_uncompleted_plan_task_count=37739835,complete_cardinalities=plan['cardinalities'],materializer_invocation_count=34,actual_fitter_invocation_count=0,complete_observed_provenance_and_missing=docs['plan']['complete_observed_provenance_and_missing'],preserved_sidecar_references=[docs['plan'][k] for k in ('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference','preserved_v6_incremental_evidence_sidecar_reference')],**dict.fromkeys(m.PRODUCER_FALSE,False))
  with patch.object(m,'project',return_value=(plan,a['panel'],a['old_ids'])),patch.object(m,'producer_sources',return_value={}),patch.object(m.pure,'verify_materialized',return_value={}):
   self.assertEqual(len(m.verify_candidate(value,docs)['numerical_task_ids']),102)
   for key,changed in [('new_completed_task_count',False),('remaining_uncompleted_plan_task_count',4713768),('preserved_sidecar_references',[]),('forced_combination_counts',[]),('source_hashes',{'fake':'0'*64}),('all_plan_tasks_completed',True),('reused_completed_reference',{})]:
    v=deepcopy(value);v[key]=changed
    with self.subTest(key=key),self.assertRaises(ValueError):m.verify_candidate(v,docs)
 def test_existing_audit_and_pending_pin_refuse_work(self):
  with patch.object(m,'PRODUCER_SHA',None),patch.object(m,'guard') as guard:
   with self.assertRaises(ValueError):m.build()
   guard.assert_not_called()
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'independent_readback.json';out.write_text('{}')
   with patch.object(m,'OUTPUT',out),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.publish()
    build.assert_not_called()
 def test_same_issuer_and_target_shareclass_substitution(self):
  groups=[dict(issuer_id='A',security_ids=['a','aa']),dict(issuer_id='B',security_ids=['b'])]
  with self.assertRaises(ValueError):m.forced_rank(groups,['a','aa'],'a')
  with self.assertRaises(ValueError):m.forced_rank(groups,['aa','b'],'a')
if __name__=='__main__':unittest.main()
