"""Independent forced-BKNG prefix queue readback, with frozen pure task validation."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research';sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_materialization_independent_readback_research as pure
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
PURE_SHA='cedc4a97ad4138662df6ba95982f7432690367e9ce119a8813ad772940d6dbd1'
CODEC_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
PRODUCER=ROOT/'scripts/ndx_new_cutoff_bkng_combination_materialize_20260925.py';PRODUCER_SHA='7684fd84738d646872f0f0bc04a4b47c6d950bfc4039013f6442aad140db7804'
CANDIDATE=BASE/'new_cutoff_bkng_combination_materialization_20260925_v1/queue.json';CANDIDATE_SHA='09347e88f02502bdc46f8b53585195b2beda0892df5e019f8e940803fb1b81cd'
OUTPUT=CANDIDATE.with_name('independent_readback.json')
BOUND={
 'plan':('new_cutoff_shard_prepare_20260925_v4/plan.json','761e3e9fe62efae84838e7f1c71bcf630856e1eb6e7c8a7b731ea8273ac4af74'),
 'panel':('new_cutoff_conditional_panel_20260925_v4/panel.json','c50856ad47fdc0c1eeebccf06f7d2a788cd68bfbde325296f8913242b2585c1d'),
 'audit':('new_cutoff_conditional_panel_20260925_v4/independent_increment_readback.json','ea44004b9475c9e284a2652a379dd6aabd89f8a23c1e52eec49e48d673b297a2'),
 'rebinding':('new_cutoff_v4_completed_task_rebinding_20260925_v1/rebinding.json','9917064d5a88baa9a764fc665449334c199b9816b9df8f2614d5a899d858fe57'),
 'rebinding_audit':('new_cutoff_v4_completed_task_rebinding_20260925_v1/independent_readback.json','ea616f698761f0b3988c1f79962821a4e0b8cab65b240d6770f5fffef224ad92')}
BKNG='security:0001075531:09857L108'
LOADED={**codec.LOADED,str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(Path(pure.__file__).resolve()):hashlib.sha256(Path(pure.__file__).read_bytes()).hexdigest()}
def require(ok,message):
 if not ok:raise ValueError(message)
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def merge(a,b):
 for p,h in b.items():require(p not in a or a[p]==h,'Source conflict');a[p]=h

def coefficient(sizes,degree):
 if degree<0:return 0
 values=[1]+[0]*degree
 for size in sizes:
  for power in range(degree,0,-1):values[power]+=size*values[power-1]
 return values[degree]

def forced_rank(groups,prefix,target):
 """Count preceding prefixes that include this exact SID; no production selection calls."""
 groups=pure.groups_contract(groups);lookup={s:(i,j) for i,(_,members) in enumerate(groups) for j,s in enumerate(members)}
 require(target in lookup and type(prefix) is list and target in prefix and len(prefix)==len(set(prefix)) and all(s in lookup for s in prefix),'Exact forced SID')
 coords=[lookup[s] for s in prefix];require(all(a[0]<b[0] for a,b in zip(coords,coords[1:])),'Issuer-prefix order')
 target_group,target_class=lookup[target];sizes=[len(g[1]) for g in groups]
 def tails(start,count,need):
  if not need:return coefficient(sizes[start:],count)
  if target_group<start:return 0
  return coefficient([sizes[i] for i in range(start,len(sizes)) if i!=target_group],count-1)
 rank=0;lower=0;needed=True
 for offset,(issuer,share_class) in enumerate(coords):
  left=len(coords)-offset-1
  for candidate in range(lower,issuer+1):
   class_stop=share_class if candidate==issuer else sizes[candidate]
   for klass in range(class_stop):
    if needed and candidate==target_group:
     if klass==target_class:rank+=tails(candidate+1,left,False)
    else:rank+=tails(candidate+1,left,needed)
  if issuer==target_group:
   require(share_class==target_class,'Target class substitution');needed=False
  lower=issuer+1
 require(not needed,'Forced target absent');return rank

def validate_materializations(*,materializations,selections,plan,panel,old_ids,target=BKNG):
 require(type(materializations) is list and type(selections) is list and len(materializations)==len(selections)==34,'Exactly34 singleton inputs')
 require(type(old_ids) is list and len(old_ids)==len(set(old_ids))==198,'Full198 external identities')
 groups=plan['canonical_groups'];independent_groups=pure.groups_contract(groups);lookup={s:r for r in panel['universe'] for s in [r['security_id']]}
 require(target in lookup and lookup[target]['ticker']=='BKNG','Forced exact BKNG coordinate')
 reports=[];ids=[];locations=[];selection_expected=[]
 for number,(value,selection) in enumerate(zip(materializations,selections)):
  k=4+number//2;local=number%2
  require(type(value['k']) is int and value['k']==k and type(value['start']) is int and type(value['stop']) is int and value['stop']==value['start']+1 and len(value['combinations'])==1,'Singleton full-rank interval')
  combo=value['combinations'][0];prefix=combo['prefix_security_ids'];require(len(prefix)==k and forced_rank(groups,prefix,target)==local,'First two constrained prefixes independently counted')
  rank=pure.independent_position(independent_groups,prefix);require(rank==value['start'],'Full rank is not forced-local rank')
  shards=[s for s in plan['shards'] if s['k']==k and s['start']<=rank<s['stop']];require(len(shards)==1,'Unique full-plan shard');shard=shards[0]
  expected=dict(k=k,forced_local_rank=local,prefix_security_ids=prefix,full_rank=rank,shard_id=shard['shard_id']);require(pure.exact(selection,expected),'Selection sidecar exact')
  reports.append(pure.verify_materialized(value=value,plan=plan,plan_reference=ref('plan'),shard_id=shard['shard_id'],panel=panel,start=rank,stop=rank+1,max_materialized_combinations=1,expected_fitter_source_hashes=plan['fitter_source_hashes']))
  selection_expected.append(deepcopy(expected))
  for task in combo['tasks']:ids.append(task['numerical_task_id']);locations.append(task['location_id'])
 require(len(ids)==len(set(ids))==len(locations)==len(set(locations))==102 and not set(ids)&set(old_ids),'102 new distinct tasks disjoint from198')
 require(selections[-2]['prefix_security_ids']!=selections[-1]['prefix_security_ids'],'Distinct k20 constrained prefixes')
 return dict(materialization_reports=reports,selections=selection_expected,numerical_task_ids=ids,location_ids=locations)

PRODUCER_FALSE=('fit_performed','old_plan_build_called','panel_audit_repeated','old_completed_tasks_rematerialized','old_task_readbacks_repeated','score_filtering_performed','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','full_shard_completed','all_plan_tasks_completed')
def project(documents):
 outer,candidate,audit,rebound,readback=(documents[k] for k in ('plan','panel','audit','rebinding','rebinding_audit'))
 require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V4' and outer['input_references']['panel']==ref('panel') and outer['input_references']['audit']==ref('audit'),'Plan lineage')
 require(audit['status']=='PASSED' and audit['candidate_reference']==ref('panel') and audit['panel_content_sha256']==candidate['panel']['panel_content_sha256'],'Hard panel audit')
 require(rebound['schema']=='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_V1' and rebound['input_references']['plan']==ref('plan') and readback['schema']=='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_INDEPENDENT_READBACK_V1' and readback['status']=='PASSED' and readback['candidate_reference']==ref('rebinding') and readback['numerical_contracts_unchanged'] is True,'Hard independently rebound198')
 ids=[r['numerical_task_id'] for r in rebound['rows']];require(len(ids)==len(set(ids))==198 and ids==readback['verified_numerical_task_ids'],'Complete old198 identity references')
 require(all(d[k] is False for d in documents.values() for k in ('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified')),'Parent authority')
 panel=codec.decode_frames(candidate['panel']);plan=outer['plan'];require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V4' and panel['conditional_security_count']==22 and panel['conditional_issuer_count']==21 and plan['context']['previous_target_weights'] is None,'22/21 conditional panel and None prior')
 require(all(panel[k] is False for k in codec.PANEL_FALSE),'Inner panel authority')
 projection=dict(panel_reference=ref('panel'),panel_content_sha256=panel['panel_content_sha256'],dates=[d.date().isoformat() for d in panel['returns'].index],columns=panel['returns'].columns.tolist(),returns=panel['returns'].values.tolist(),universe=[{k:r[k] for k in ('security_id','ticker','issuer_id','risk_chain')} for r in panel['universe'].to_dict('records')])
 pure.validate_plan_panel(plan,projection,plan['fitter_source_hashes'])
 forced=[r for r in projection['universe'] if r['security_id']==BKNG];require(len(forced)==1 and forced[0]['ticker']=='BKNG' and forced[0]['risk_chain']=='travel_hospitality','Exact BKNG risk coordinate')
 return plan,projection,ids

def producer_sources(documents):
 sources={str(PRODUCER):PRODUCER_SHA};merge(sources,codec.LOADED);merge(sources,pure.MATERIALIZER_SOURCES);merge(sources,documents['plan']['source_hashes']);merge(sources,documents['plan']['plan']['fitter_source_hashes']);merge(sources,{ref(k)['path']:ref(k)['sha256'] for k in BOUND});return sources

def verify_candidate(value,documents):
 plan,panel,old_ids=project(documents)
 groups=plan['canonical_groups'];forced_group=[g for g in groups if BKNG in g['security_ids']];require(len(forced_group)==1,'One forced issuer')
 sizes=[len(g['security_ids']) for g in groups if BKNG not in g['security_ids']]
 denominators=[dict(k=k,forced_combination_count=coefficient(sizes,k-1)) for k in range(4,21)]
 require(sum(r['forced_combination_count'] for r in denominators)==1572631 and type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==9431859,'Full-pool and forced denominators')
 for k in range(4,21):require(not plan['cardinalities'][k-1]['necessary_bound_certificates'],'Requested k still passes original necessary bounds')
 detail=validate_materializations(materializations=value['new_materializations'],selections=value['selections'],plan=plan,panel=panel,old_ids=old_ids)
 expected=dict(schema='NEW_CUTOFF_BKNG_COMBINATION_MATERIALIZATION_V1',input_references={k:ref(k) for k in BOUND},source_hashes=producer_sources(documents),selections=detail['selections'],new_materializations=value['new_materializations'],forced_sid=BKNG,forced_combination_counts=denominators,selection_rule='FIRST_TWO_FORCED_BKNG_PREFIX_COMBINATIONS_PER_K4_TO20_NO_SCORE_SELECTION',reused_completed_reference=dict(rebinding_reference=ref('rebinding'),independent_readback_reference=ref('rebinding_audit'),numerical_task_ids=old_ids),new_combination_count=34,new_task_count=102,new_completed_task_count=0,external_completed_task_count=198,full_plan_task_denominator=9431859,remaining_uncompleted_plan_task_count=9431661,complete_cardinalities=deepcopy(plan['cardinalities']),materializer_invocation_count=34,actual_fitter_invocation_count=0,complete_observed_provenance_and_missing=deepcopy(documents['plan']['complete_observed_provenance_and_missing']),preserved_sidecar_references=[deepcopy(documents['plan'][k]) for k in ('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference')],**dict.fromkeys(PRODUCER_FALSE,False))
 require(pure.exact(value,expected),'Full queue envelope/source/coverage/sidecars/permissions')
 return detail

def guard(sources):
 require(LOADED[str(Path(pure.__file__).resolve())]==PURE_SHA and LOADED[str(Path(codec.__file__).resolve())]==CODEC_SHA,'Frozen independent sources')
 expected=dict(sources);merge(expected,LOADED);merge(expected,codec.LOADED)
 for p,h in expected.items():require(codec.sha(Path(p).read_bytes())==h,'Source drift')

def build():
 require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None,'Actual anchors pending')
 sources=dict(LOADED);guard(sources);documents={}
 for k in BOUND:
  r=ref(k);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'Hard parent bytes differ');documents[k]=codec.loads(blob);sources[r['path']]=r['sha256']
 merge(sources,producer_sources(documents));guard(sources)
 blob=CANDIDATE.read_bytes();require(codec.sha(blob)==CANDIDATE_SHA,'Hard candidate bytes differ');sources[str(CANDIDATE)]=CANDIDATE_SHA
 detail=verify_candidate(codec.loads(blob),documents);guard(sources)
 return dict(schema='NEW_CUTOFF_BKNG_COMBINATION_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),input_references={k:ref(k) for k in BOUND},source_hashes=sources,independent_readback_count=1,actual_fitter_invocation_count=0,new_combination_count=34,new_task_count=102,new_completed_task_count=0,external_completed_task_count=198,forced_combination_denominator=1572631,full_plan_task_denominator=9431859,remaining_uncompleted_plan_task_count=9431661,first_two_forced_prefixes_independently_counted=True,complete_fullpool_ranks_independently_counted=True,verified_numerical_task_ids=detail['numerical_task_ids'],verified_location_ids=detail['location_ids'],pure_materialization_readbacks=detail['materialization_reports'],producer_called=False,production_index_called=False,production_selection_helper_called=False,old_task_readbacks_repeated=False,**{k:False for k in PRODUCER_FALSE if k!='old_task_readbacks_repeated'})

def publish():
 require(not OUTPUT.exists() and OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'queue.json'},'Exact producer-only namespace')
 value=build();guard(value['source_hashes']);blob=codec.pretty(value)
 with OUTPUT.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'queue.json',OUTPUT.name},'Readback publication bytes/namespace')
 return dict(path=str(OUTPUT),sha256=codec.sha(blob))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');a=p.parse_args();require(a.publish,'Explicit publish required');print(json.dumps(publish()))
