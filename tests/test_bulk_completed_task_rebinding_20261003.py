import sys,itertools,math,tempfile
from datetime import date,timedelta
from unittest.mock import patch
from pathlib import Path
from copy import deepcopy
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import bulk_completed_task_rebinding_20261003 as m

def fixture():
 names=['s'+str(i).zfill(2) for i in range(77)];universe=[dict(security_id=s,issuer_id='i'+str(i if i!=1 else 0).zfill(2),ticker='T'+str(i),risk_chain='r'+str(i%4)) for i,s in enumerate(names)];groups={}
 for r in universe:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
 gs=[dict(issuer_id=k,security_ids=v) for k,v in sorted(groups.items())];specs=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'];sources={str(i):'a'*64 for i in range(25)}
 params=dict(fit_days=126,max_single_weight=.45,min_single_weight=.05,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55,shrinkage_intensity=.35,top_weight_cap=.8,turnover_anchor_strength=.25)
 ctx=dict(decision_cutoff='2026-09-21',parameters=params,previous_target_weights=None,weight_specs=specs,shard_size=1000,order_version='ISSUER_SID_PREFIX_LEX_V1',group_fingerprint=m.digest(dict(order_version='ISSUER_SID_PREFIX_LEX_V1',groups=[(g['issuer_id'],g['security_ids']) for g in gs])),fitter_source_fingerprint=m.digest(sources),panel_reference=m.ref('panel'),panel_audit_reference=m.AUDIT_REFERENCE)
 coeff=[1]+[0]*76
 for g in gs:
  for k in range(76,0,-1):coeff[k]+=len(g['security_ids'])*coeff[k-1]
 cards=[];offset=0
 for k in range(1,77):
  n=(coeff[k]+999)//1000 if 4<=k<=20 else 0;cards.append(dict(k=k,combination_count=coeff[k],planned_shard_count=n,first_global_shard_ordinal=offset,planned_combination_count=coeff[k] if n else 0,planned_canonical_task_count=3*coeff[k] if n else 0,first_global_planned_combination_ordinal=sum(c['planned_combination_count'] for c in cards)));offset+=n
 plan=dict(schema='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1',plan_id=m.digest(ctx),context=ctx,canonical_groups=gs,cardinalities=cards,fitter_source_hashes=sources,planned_canonical_task_count=3*sum(coeff[4:21]),completed_canonical_task_count=0)
 plan['content_sha256']=m.digest(plan)
 dates=[(date(2026,9,21)-timedelta(days=125-i)).isoformat()+'T00:00:00' for i in range(126)]
 panel=dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1',conditional_security_count=77,conditional_issuer_count=76,universe=dict(columns=list(universe[0]),data=[list(r.values()) for r in universe]),returns=dict(columns=[r['ticker'] for r in universe],dtypes=['float64']*77,index_kind='DatetimeIndex',index=dates,data=[[.01]*77 for _ in dates]),observed_provenance_and_missing=[dict(ticker=str(i)) for i in range(101)])
 flags=dict.fromkeys(('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified'),False)
 combos=list(itertools.combinations(names[2:11],4))+list(itertools.combinations(names[2:11],5))[:42];rows=[]
 for combo in combos:
  for si,spec in enumerate(specs):
   old=dict(selected={s:{} for s in combo},cutoff='2026-09-21');selected,matrix=m.matrix_and_selected(panel,old);num=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=len(combo),selected=selected,weight_spec=spec,parameters=deepcopy(params),requested_previous_target_weights=None,fit_data_sha256=matrix,fitter_source_fingerprint=m.digest(sources));loc={'old':len(rows)};task=dict(numerical_identity=num,numerical_task_id=m.digest(num),location_identity=loc,location_id=m.digest(loc),expected_fitter_previous_target_weights={});row=dict(numerical_task_id=task['numerical_task_id'],full_task=task,fit_data_sha256=matrix,status='FITTED_FIVE_RISKS_PASSED',targets={'preserved':'not rechecked'},**{k:dict(path=k,sha256='b'*64) for k in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference')});rows.append(row)
 nested=[dict(status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0,old_completed_row=r,numerical_task_id=r['numerical_task_id'],verified_fit_data_sha256=r['fit_data_sha256'],new_location_identity={'old':i},new_location_id=m.digest({'old':i}),earlier_wrapper={'must':'preserve'}) for i,r in enumerate(rows[102:])]
 sidecars={k:dict(m.ref('panel'),json_pointer='/'+k) for k in ('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')}
 return dict(plan=dict(schema='BULK_ALL_K_LAZY_PLAN_V1',source_hashes={},plan=plan,old_completed_tasks_deducted=0,complete_observed_provenance_and_missing=deepcopy(panel['observed_provenance_and_missing']),preserved_evidence_sidecar_references=sidecars,**flags),plan_publication=dict(schema='BULK_ALL_K_LAZY_PLAN_PUBLICATION_V1',status='PLANNED_NOT_ENUMERATED',plan_reference=m.ref('plan'),source_hashes={}),panel=dict(panel=panel,source_hashes={},**{k:[] for k in sidecars},original24_frame_exact_proof={str(i):dict(exact=True,original_sha256='a',projected_sha256='a') for i in range(5)},**flags),panel_publication=dict(panel_reference=m.ref('panel'),source_hashes={}),old_plan=dict(plan=dict(context=deepcopy(ctx),fitter_source_hashes=sources,canonical_groups=[dict(issuer_id=g['issuer_id'],security_ids=[s for s in g['security_ids'] if s in names[:24]]) for g in gs if any(s in names[:24] for s in g['security_ids'])])),completed_index=dict(schema='NEW_CUTOFF_CTAS_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_and_readback_count=504,new_tasks=rows[:102],externally_completed_rebound_rows=nested,**flags))

class Tests(unittest.TestCase):
 def test_full504_no_fit_and_nested_exact(self):
  docs=fixture();out=m.assemble(docs);self.assertEqual(len(out['rows']),504);self.assertEqual(out['externally_rebound_combination_count'],168);self.assertEqual(out['rows'][102]['original_index_row'],docs['completed_index']['externally_completed_rebound_rows'][0]);self.assertEqual(out['remaining_uncompleted_task_count'],docs['plan']['plan']['planned_canonical_task_count']-504)
 def test_rank_independent_small_enumeration(self):
  gs=[dict(issuer_id='a',security_ids=['a1','a2']),dict(issuer_id='b',security_ids=['b']),dict(issuer_id='c',security_ids=['c'])]
  expected=[['a1','b'],['a1','c'],['a2','b'],['a2','c'],['b','c']]
  for i,c in enumerate(expected):self.assertEqual(m.prefix_rank(gs,c),i)
  with self.assertRaises(ValueError):m.prefix_rank(gs,['a1','a2'])
 def test_numeric_source_matrix_prior_failclosed(self):
  for kind in ['matrix','source','prior','risk']:
   d=fixture()
   if kind=='matrix':d['panel']['panel']['returns']['data'][0][2]=.02
   elif kind=='source':d['plan']['plan']['fitter_source_hashes']=dict(d['plan']['plan']['fitter_source_hashes'],extra='c'*64)
   elif kind=='prior':d['plan']['plan']['context']['previous_target_weights']={}
   else:d['panel']['panel']['universe']['data'][2][-1]='changed'
   with self.assertRaises(ValueError):m.assemble(d)
 def test_namespace_pending_and_saved_nested_tamper(self):
  with patch.dict(m.BOUND,{'plan':('pending',None)}):
   with self.assertRaises(ValueError):m.read_inputs()
  with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'rebinding.json'),patch.object(m,'read_inputs') as read:
   with self.assertRaises(ValueError):m.publish()
   read.assert_not_called()
  d=fixture();d['completed_index']['externally_completed_rebound_rows'][0]['new_location_id']='forged'
  with self.assertRaises(ValueError):m.assemble(d)
 def test_large_rank_exact_integer(self):
  d=fixture();p=d['plan']['plan'];old=dict(holding_count=20,selected={'s'+str(i).zfill(2):{} for i in range(57,77)},weight_spec=p['context']['weight_specs'][2]);loc,pos=m.new_location(p,old,m.ref('plan'));self.assertIs(type(pos['global_task_ordinal']),int);self.assertGreater(loc['rank'],2**53)
if __name__=='__main__':unittest.main()
