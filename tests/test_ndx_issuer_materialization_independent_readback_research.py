"""Hand-built synthetic tasks and tiny itertools reference order; no producer import."""
from copy import deepcopy
from datetime import date,timedelta
from itertools import combinations,product
from pathlib import Path
import unittest
from backtest import ndx_issuer_materialization_independent_readback_research as m


def fixture(prior=None):
 root=Path(__file__).resolve().parent
 groups=[dict(issuer_id='A',security_ids=['z1','z2']),dict(issuer_id='B',security_ids=['a']),dict(issuer_id='C',security_ids=['m']),dict(issuer_id='D',security_ids=['b'])]
 sources={str(root/('fitter_'+str(i)+'.py')):str(i%10)*64 for i in range(25)}
 panelref=dict(path=str(root/'panel.json'),sha256='a'*64);auditref=dict(path=str(root/'audit.json'),sha256='b'*64)
 params=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
 ctx=dict(plan_version='ISSUER_COUNTS_ONLY_SHARD_PREPARE_V1',order_version=m.ORDER,group_fingerprint=m.digest({'order_version':m.ORDER,'groups':[(r['issuer_id'],r['security_ids']) for r in groups]}),panel_reference=panelref,panel_audit_reference=auditref,decision_cutoff='2026-09-21',parameters=params,fitter_source_fingerprint=m.digest(sources),previous_target_weights=prior,weight_specs=m.SPECS,shard_size=2,mathematical_source_fingerprint='d'*64)
 pid=m.digest(ctx);ident=dict(ctx,k=4,start=0,stop=2);sid=m.digest(ident)
 shard=dict(ident,shard_id=sid,plan_id=pid,status='PLANNED_NOT_ENUMERATED',completed_canonical_task_count=0,remaining_canonical_task_count=6)
 plan=dict(schema=ctx['plan_version'],status='PLANNED_NOT_ENUMERATED',context=ctx,canonical_groups=groups,plan_id=pid,shards=[shard],fitter_source_hashes=sources,completed_canonical_task_count=0,remaining_canonical_task_count=6,planned_canonical_task_count=6,all_three_specs_planned_without_alias_deduplication=True)
 for flag in ('combination_enumeration_performed','risk_feasibility_proven','score_filtering_performed','task_identity_generated','runner_attached','external_source_bytes_verified','source_bytes_reverified_at_call','anchor_alias_equivalence_verified','identity_authenticated','fit_performed','promotion_allowed'):plan[flag]=False
 names=['z1','z2','a','m','b'];tickers=['Z1','Z2','A','M','B'];issuers=['A','A','B','C','D']
 panel=dict(panel_reference=panelref,panel_content_sha256='e'*64,dates=[(date(2026,9,21)-timedelta(days=i)).isoformat() for i in range(125,-1,-1)],columns=tickers,returns=[[.01,.02,.03,.04,.05] for _ in range(126)],universe=[dict(security_id=s,ticker=t,issuer_id=i,risk_chain='chain'+i) for s,t,i in zip(names,tickers,issuers)])
 planref=dict(path=str(root/'plan.json'),sha256='f'*64)
 selected={s:dict(ticker=t,issuer_id=i,risk_chain='chain'+i) for s,t,i in [('a','A','B'),('b','B','D'),('m','M','C'),('z1','Z1','A')]}
 matrix=dict(dates=panel['dates'],tickers=['A','B','M','Z1'],returns=[[.03,.05,.04,.01] for _ in range(126)])
 mh=m.digest(matrix);tasks=[]
 for i,spec in enumerate(m.SPECS):
  num=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-09-21',holding_count=4,selected=selected,weight_spec=spec,parameters=params,requested_previous_target_weights=prior,fit_data_sha256=mh,fitter_source_fingerprint=m.digest(sources))
  loc=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=planref,plan_id=pid,shard_id=sid,order_version=m.ORDER,group_fingerprint=ctx['group_fingerprint'],k=4,rank=0,spec_index=i,weight_spec=spec)
  tasks.append(dict(numerical_task_id=m.digest(num),numerical_identity=num,location_id=m.digest(loc),location_identity=loc,status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,expected_fitter_previous_target_weights={} if prior is None else prior,anchor_alias_equivalence_verified=False))
 combo=dict(k=4,rank=0,prefix_security_ids=['z1','a','m','b'],fitter_sorted_security_ids=['a','b','m','z1'],fit_matrix=matrix,fit_data_sha256=mh,tasks=tasks)
 value=dict(schema='ISSUER_BOUNDED_TASK_MATERIALIZATION_V1',status='MATERIALIZED_NOT_ATTEMPTED',plan_reference=planref,plan_id=pid,shard_id=sid,order_version=m.ORDER,group_fingerprint=ctx['group_fingerprint'],k=4,start=0,stop=1,panel_reference=panelref,panel_audit_reference=auditref,panel_content_sha256='e'*64,fitter_source_hashes=sources,materializer_loaded_source_hashes=m.MATERIALIZER_SOURCES,combination_count=1,materialized_task_count=3,completed_task_count=0,remaining_unattempted_materialized_task_count=3,max_materialized_combinations=1,combinations=[combo])
 for flag in ('source_bytes_authenticated','source_bytes_reverified_at_call','identity_authenticated','old_task_identity_reused','full_shard_completed','all_plan_tasks_completed','fit_performed','promotion_allowed'):value[flag]=False
 return dict(value=deepcopy(value),plan=deepcopy(plan),plan_reference=planref,shard_id=sid,panel=panel,start=0,stop=1,max_materialized_combinations=1,expected_fitter_source_hashes=deepcopy(sources))


class Tests(unittest.TestCase):
 def test_manual_fixture_and_zero_fit(self):
  r=m.verify_materialized(**fixture());self.assertEqual(r['task_count'],3);self.assertFalse(r['fit_performed']);self.assertFalse(r['source_bytes_authenticated'])
 def test_independent_polynomial_rank_matches_tiny_reference(self):
  groups=[('A',['z1','z2']),('B',['a']),('C',['m']),('D',['b'])]
  for k in range(1,5):
   choices=[]
   for indexes in combinations(range(4),k):
    for sids in product(*(groups[i][1] for i in indexes)):choices.append(tuple((groups[i][0],s) for i,s in zip(indexes,sids)))
   choices.sort();self.assertEqual(m.suffix_count(groups,0,k),len(choices))
   for rank,selection in enumerate(choices):self.assertEqual(m.independent_position(groups,[s for i,s in selection]),rank)
 def test_exit_prior_and_none_distinct(self):
  args=fixture({'EXITED':.75,'a':.25});self.assertTrue(m.verify_materialized(**args)['full_prior_preserved'])
  args['value']['combinations'][0]['tasks'][0]['expected_fitter_previous_target_weights']={'a':1.}
  with self.assertRaises(ValueError):m.verify_materialized(**args)
 def test_rank_class_order_and_requested_range(self):
  for attack in ('class','duplicateissuer','order','stop'):
   a=fixture()
   if attack=='class':a['value']['combinations'][0]['prefix_security_ids'][0]='z2'
   elif attack=='duplicateissuer':a['value']['combinations'][0]['prefix_security_ids']=['z1','z2','m','b']
   elif attack=='order':a['value']['combinations'][0]['prefix_security_ids'].reverse()
   else:a['stop']=2
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**a)
 def test_full_matrix_including_unselected_and_contract_mutations(self):
  for attack in ('unselectedbool','date','matrix','parameter','source','spec','numericid','locationid','complete'):
   a=fixture();task=a['value']['combinations'][0]['tasks'][0]
   if attack=='unselectedbool':a['panel']['returns'][0][1]=True
   elif attack=='date':a['panel']['dates'][-1]='2026-09-22'
   elif attack=='matrix':a['value']['combinations'][0]['fit_matrix']['returns'][0][0]=.04
   elif attack=='parameter':task['numerical_identity']['parameters']['shrinkage_intensity']=.36
   elif attack=='source':a['value']['fitter_source_hashes'].pop(next(iter(a['value']['fitter_source_hashes'])))
   elif attack=='spec':a['value']['combinations'][0]['tasks'].pop()
   elif attack=='numericid':task['numerical_task_id']='0'*64
   elif attack=='locationid':task['location_id']='0'*64
   else:a['value']['full_shard_completed']=True
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**a)
 def test_nonboolean_pending_fields_and_prior_mass(self):
  for attack in ('attempt','start','prior'):
   a=fixture()
   if attack=='attempt':a['value']['combinations'][0]['tasks'][0]['wrapper_call_attempt_count']=False
   elif attack=='start':a['start']=False
   else:a=fixture({'EXIT':.5,'a':.50000000005})
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_materialized(**a)

if __name__=='__main__':unittest.main()
