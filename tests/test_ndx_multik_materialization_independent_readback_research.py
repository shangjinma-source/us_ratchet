"""Synthetic twenty-security fixtures; generate only requested prefix positions."""
from copy import deepcopy
import importlib.util
from math import comb
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_multik_materialization_independent_readback_research as m
spec=importlib.util.spec_from_file_location('small_fixture',Path(__file__).with_name('test_ndx_issuer_materialization_independent_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def fixture():
 base=f.fixture();plan=base['plan'];ctx=plan['context'];groups=[dict(issuer_id='I%02d'%i,security_ids=(['S00A','S00B'] if i==0 else ['S%02d'%i])) for i in range(19)]
 ctx['group_fingerprint']=m.pure.digest(dict(order_version=m.pure.ORDER,groups=[(g['issuer_id'],g['security_ids']) for g in groups]));plan['canonical_groups']=groups;plan['plan_id']=m.pure.digest(ctx);plan['shards']=[]
 totals={k:comb(18,k) if k<=18 else 0 for k in range(4,20)}
 for k in totals:totals[k]+=2*comb(18,k-1)
 plan['planned_canonical_task_count']=plan['remaining_canonical_task_count']=sum(totals.values())*3
 for k in range(4,20):
  identity=dict(ctx,k=k,start=0,stop=2)
  plan['shards'].append(dict(identity,shard_id=m.pure.digest(identity),plan_id=plan['plan_id'],status='PLANNED_NOT_ENUMERATED',completed_canonical_task_count=0,remaining_canonical_task_count=6))
 panel=base['panel'];panel['universe']=[dict(security_id=s,ticker='T'+s,issuer_id=g['issuer_id'],risk_chain='C'+str(i%4)) for i,g in enumerate(groups) for s in g['security_ids']]
 panel['columns']=[r['ticker'] for r in panel['universe']];panel['returns']=[[float(i+1)/1000 for i in range(20)] for _ in range(126)]
 lookup={r['security_id']:r for r in panel['universe']}
 def materialize(k,start,stop):
  item=deepcopy(base['value']);shard=next(s for s in plan['shards'] if s['k']==k)
  item.update(plan_id=plan['plan_id'],shard_id=shard['shard_id'],group_fingerprint=ctx['group_fingerprint'],k=k,start=start,stop=stop,combination_count=stop-start,materialized_task_count=(stop-start)*3,remaining_unattempted_materialized_task_count=(stop-start)*3,max_materialized_combinations=stop-start,combinations=[])
  for rank in range(start,stop):
   prefix=[g['security_ids'][0] for g in groups[:k]]
   if rank==1:
    if k==19:prefix[0]='S00B'
    else:prefix[-1]=groups[k]['security_ids'][0]
   ordered=sorted(prefix);selected={s:{key:lookup[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in ordered};tickers=[selected[s]['ticker'] for s in ordered]
   matrix=dict(dates=panel['dates'],tickers=tickers,returns=[[row[panel['columns'].index(t)] for t in tickers] for row in panel['returns']]);h=m.pure.digest(matrix);tasks=[]
   for idx,weight in enumerate(m.pure.SPECS):
    num=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=k,selected=selected,weight_spec=weight,parameters=ctx['parameters'],requested_previous_target_weights=ctx['previous_target_weights'],fit_data_sha256=h,fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
    loc=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=base['plan_reference'],plan_id=plan['plan_id'],shard_id=shard['shard_id'],order_version=m.pure.ORDER,group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=idx,weight_spec=weight)
    tasks.append(dict(numerical_task_id=m.pure.digest(num),numerical_identity=num,location_id=m.pure.digest(loc),location_identity=loc,status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False,expected_fitter_previous_target_weights={},anchor_alias_equivalence_verified=False))
   item['combinations'].append(dict(k=k,rank=rank,prefix_security_ids=prefix,fitter_sorted_security_ids=ordered,fit_matrix=matrix,fit_data_sha256=h,tasks=tasks))
  return item
 old=materialize(4,0,1);new=[materialize(k,start,stop) for k,start,stop in m.REQUESTS]
 return dict(materializations=new,plan=plan,plan_reference=base['plan_reference'],panel=panel,expected_fitter_source_hashes=base['expected_fitter_source_hashes'],old_materialization=old,completed_task_ids=[t['numerical_task_id'] for t in old['combinations'][0]['tasks']])


class Tests(unittest.TestCase):
 def test_synthetic_batch31_new_plus_external1(self):
  args=fixture();r=m.verify_slices(**args)
  self.assertEqual((r['new_combination_count'],r['new_materialized_task_count'],r['batch_task_count_including_external']),(31,93,96))
  self.assertEqual(len(r['coverage']),16);self.assertFalse(r['all_plan_tasks_completed']);self.assertEqual(r['new_completed_task_count'],0)
 def test_old_rank0_never_sent_to_independent_materialization_reader(self):
  args=fixture();original=m.pure.verify_materialized;calls=[]
  def watch(**kwargs):calls.append((kwargs['value']['k'],kwargs['start'],kwargs['stop']));return original(**kwargs)
  with patch.object(m.pure,'verify_materialized',side_effect=watch):m.verify_slices(**args)
  self.assertEqual(calls,list(m.REQUESTS));self.assertNotIn((4,0,1),calls)
 def test_interval_order_missing_and_completed_reference(self):
  for attack in ('oldrank','missing','order','completed'):
   a=fixture()
   if attack=='oldrank':a['materializations'][0]=a['old_materialization']
   elif attack=='missing':a['materializations'].pop()
   elif attack=='order':a['materializations'].reverse()
   else:a['completed_task_ids'][0]='0'*64
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_slices(**a)
 def test_all_specs_matrix_and_fullpool_not_finished(self):
  for attack in ('spec','matrix','complete','fullpool'):
   a=fixture();item=a['materializations'][3]
   if attack=='spec':item['combinations'][0]['tasks'].pop()
   elif attack=='matrix':item['combinations'][0]['fit_matrix']['returns'][0][0]=.99
   elif attack=='complete':item['completed_task_count']=1
   else:a['plan']['planned_canonical_task_count']=a['plan']['remaining_canonical_task_count']=96
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_slices(**a)

if __name__=='__main__':unittest.main()
