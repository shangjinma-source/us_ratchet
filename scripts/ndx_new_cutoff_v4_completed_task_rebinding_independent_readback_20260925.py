"""Independent V4 completion-location readback; no fitter or production ranking imports."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research';sys.path.insert(0,str(ROOT))
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
CODEC_SHA='0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'
PRODUCER=ROOT/'scripts/ndx_new_cutoff_v4_completed_task_rebinding_20260925.py';PRODUCER_SHA='c4b2b37c7dfc0b106e168b76d9fd4a0927c321464f0aeb82a72021f636ba890b'
CANDIDATE=BASE/'new_cutoff_v4_completed_task_rebinding_20260925_v1/rebinding.json';CANDIDATE_SHA='9917064d5a88baa9a764fc665449334c199b9816b9df8f2614d5a899d858fe57'
OUTPUT=CANDIDATE.with_name('independent_readback.json')
BOUND={
 'plan':('new_cutoff_shard_prepare_20260925_v4/plan.json','761e3e9fe62efae84838e7f1c71bcf630856e1eb6e7c8a7b731ea8273ac4af74'),
 'panel':('new_cutoff_conditional_panel_20260925_v4/panel.json','c50856ad47fdc0c1eeebccf06f7d2a788cd68bfbde325296f8913242b2585c1d'),
 'audit':('new_cutoff_conditional_panel_20260925_v4/independent_increment_readback.json','ea44004b9475c9e284a2652a379dd6aabd89f8a23c1e52eec49e48d673b297a2'),
 'completed_index':('new_cutoff_cprt_completed_index_20260925_v1/index.json','8c690f7bd89c06d234e9495508d050046c76ea43a1581c7beddb31557c6797fd')}
LOADED={**codec.LOADED,str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
ORDER='ISSUER_SID_PREFIX_LEX_V1'
FALSE=('producer_called','production_index_called','prepare_called','materializer_called','fitter_called','old_weight_audit_repeated','fit_performed','promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','full_shard_completed','all_plan_tasks_completed','full_transitive_source_closure_reverified')
def require(ok,message):
 if not ok:raise ValueError(message)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b):return codec.canonical(a)==codec.canonical(b)
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])
def merge(a,b):
 for p,h in b.items():require(p not in a or a[p]==h,'Source conflict');a[p]=h

def suffix_count(sizes,start,degree):
 if degree<0:return 0
 coeff=[1]+[0]*degree
 for size in sizes[start:]:
  for d in range(degree,0,-1):coeff[d]+=size*coeff[d-1]
 return coeff[degree]

def independent_rank(groups,selected):
 require(type(groups) is list and groups and [g['issuer_id'] for g in groups]==sorted({g['issuer_id'] for g in groups}),'Canonical issuer order')
 lookup={};sizes=[]
 for i,g in enumerate(groups):
  members=g['security_ids'];require(type(members) is list and members and members==sorted(set(members)),'Canonical group members');sizes.append(len(members))
  for j,s in enumerate(members):require(s not in lookup,'Duplicate SID');lookup[s]=(i,j)
 require(type(selected) is list and selected and len(set(selected))==len(selected) and all(s in lookup for s in selected),'Known unique selected SIDs')
 coords=sorted(lookup[s] for s in selected);require(len({i for i,j in coords})==len(coords),'One security per issuer')
 rank=0;lower=0
 for n,(i,j) in enumerate(coords):
  left=len(coords)-n-1
  for skipped in range(lower,i):rank+=sizes[skipped]*suffix_count(sizes,skipped+1,left)
  rank+=j*suffix_count(sizes,i+1,left);lower=i+1
 return rank

def reconstruct_rows(documents):
 outer,paneldoc,audit,index=(documents[k] for k in ('plan','panel','audit','completed_index'));plan=outer['plan'];context=plan['context']
 require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V4' and outer['input_references']['panel']==ref('panel') and outer['input_references']['audit']==ref('audit'),'V4 plan lineage')
 require(index['schema']=='NEW_CUTOFF_CPRT_COMPLETED_TASK_INDEX_V1' and type(index['batch_saved_attempt_and_readback_count']) is int and index['batch_saved_attempt_and_readback_count']==198,'Full saved completion index')
 require(all(d[k] is False for d in (outer,paneldoc,audit,index) for k in ('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','full_transitive_source_closure_reverified')),'Parent permissions')
 require(audit['status']=='PASSED' and audit['candidate_reference']==ref('panel') and audit['original_twenty_one_five_frames_exact'] is True,'Independent V4 panel proof')
 require(outer['external_completed_index_reference']==ref('completed_index') and outer['completed_task_rebinding_verified'] is False and type(outer['external_completed_tasks_deducted']) is int and outer['external_completed_tasks_deducted']==0,'Undeducted plan completion metadata')
 require(context['panel_reference']==ref('panel') and context['panel_audit_reference']==ref('audit') and context['order_version']==ORDER and context['weight_specs']==SPECS and digest(context)==plan['plan_id'],'Full context and plan identity')
 require(type(plan['completed_canonical_task_count']) is int and plan['completed_canonical_task_count']==0 and type(plan['remaining_canonical_task_count']) is int and plan['remaining_canonical_task_count']==plan['planned_canonical_task_count'],'Original plan counters remain pending')
 numerical=plan['fitter_source_hashes'];require(len(numerical)==25 and digest(numerical)==context['fitter_source_fingerprint'],'Full25 source fingerprint')
 require(set(context['parameters'])=={'fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap'} and type(context['parameters']['fit_days']) is int and context['parameters']['fit_days']==126 and context['previous_target_weights'] is None,'All8 parameters and None request')
 panel=codec.decode_frames(paneldoc['panel']);frame=panel['returns'];require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V4' and panel['panel_content_sha256']==audit['panel_content_sha256'] and all(panel[k] is False for k in codec.PANEL_FALSE),'Conditional V4 panel')
 universe=panel['universe'].to_dict('records');by={r['security_id']:r for r in universe};require(len(by)==len(universe)==22 and panel['conditional_security_count']==22 and panel['conditional_issuer_count']==21 and frame.columns.is_unique and set(frame.columns)=={r['ticker'] for r in universe},'Complete22 unique universe/columns')
 grouped={}
 for r in universe:grouped.setdefault(r['issuer_id'],[]).append(r['security_id'])
 groups=[dict(issuer_id=k,security_ids=sorted(v)) for k,v in sorted(grouped.items())]
 require(groups==plan['canonical_groups'] and digest(dict(order_version=ORDER,groups=[(g['issuer_id'],g['security_ids']) for g in groups]))==context['group_fingerprint'],'Complete panel/group identity')
 require(len(frame)==126 and frame.index.is_unique and frame.index.is_monotonic_increasing and all(d.tzinfo is None and d==d.normalize() for d in frame.index),'126 canonical dates')
 dates=[d.date().isoformat() for d in frame.index];require(dates[-1]==context['decision_cutoff'],'Exact cutoff')
 for values in frame.values.tolist():
  for v in values:require(type(v) in (int,float) and math.isfinite(v) and v>-1,'All panel finite returns')
 require(len(index['new_tasks'])==102 and len(index['externally_completed_rebound_rows'])==96,'Complete102 plus nested96 scope')
 result=[];ids=set();locations=set();matrix_cache={}
 for section in ('new_tasks','externally_completed_rebound_rows'):
  for i,row in enumerate(index[section]):
   original=row if section=='new_tasks' else row['old_completed_row']
   if section!='new_tasks':
    require(row['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and type(row['new_wrapper_call_attempt_count']) is int and row['new_wrapper_call_attempt_count']==0 and row['numerical_task_id']==original['numerical_task_id'],'Saved nested rebinding contract')
   if section!='new_tasks':
    require(row['verified_fit_data_sha256']==original['fit_data_sha256'] and digest(row['new_location_identity'])==row['new_location_id'],'Prior rebinding matrix/location identity')
   for name in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
    evidence=original[name];require(type(evidence) is dict and set(evidence)=={'path','sha256'},'Complete original completion references')
   task=original['full_task'];ident=task['numerical_identity'];tid=row['numerical_task_id']
   require(original['status'] in ('FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'),'Saved independently completed pass')
   require(tid==task['numerical_task_id']==digest(ident) and digest(task['location_identity'])==task['location_id'] and tid not in ids,'Original unique task dualIDs');ids.add(tid)
   selected=ident['selected'];rebuilt={sid:{k:by[sid][k] for k in ('ticker','issuer_id','risk_chain')} for sid in sorted(selected)}
   require(exact(selected,rebuilt) and type(ident['holding_count']) is int and ident['holding_count']==len(selected),'Complete selected identity')
   require(exact(ident['parameters'],context['parameters']) and ident['requested_previous_target_weights'] is None and task['expected_fitter_previous_target_weights']=={} and ident['fitter_source_fingerprint']==context['fitter_source_fingerprint'] and ident['cutoff']==context['decision_cutoff'],'All unchanged numerical request fields')
   key=tuple(sorted(selected))
   if key not in matrix_cache:
    tickers=[rebuilt[s]['ticker'] for s in key];matrix_cache[key]=digest(dict(dates=dates,tickers=tickers,returns=frame[tickers].values.tolist()))
   require(matrix_cache[key]==ident['fit_data_sha256']==original['fit_data_sha256'],'New panel matrix unchanged')
   expected_identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=context['decision_cutoff'],holding_count=len(selected),selected=rebuilt,weight_spec=ident['weight_spec'],parameters=context['parameters'],requested_previous_target_weights=None,fit_data_sha256=matrix_cache[key],fitter_source_fingerprint=context['fitter_source_fingerprint'])
   require(exact(ident,expected_identity) and digest(expected_identity)==tid,'Full numerical identity unchanged')
   k=len(selected);rank=independent_rank(groups,list(selected));matches=[s for s in plan['shards'] if s['k']==k and s['start']<=rank<s['stop']];require(len(matches)==1,'One authorized new shard');shard=matches[0]
   require(all(type(shard[n]) is int for n in ('k','start','stop','completed_canonical_task_count','remaining_canonical_task_count')) and shard['completed_canonical_task_count']==0 and shard['remaining_canonical_task_count']==3*(shard['stop']-shard['start']) and shard['status']=='PLANNED_NOT_ENUMERATED','Exact pending shard')
   expected_shard=dict(context,k=k,start=shard['start'],stop=shard['stop']);require(shard['shard_id']==digest(expected_shard) and shard['plan_id']==plan['plan_id'],'Independent shard identity')
   spec=ident['weight_spec'];require(spec in SPECS,'Unmerged original spec')
   location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=ref('plan'),plan_id=plan['plan_id'],shard_id=shard['shard_id'],order_version=ORDER,group_fingerprint=context['group_fingerprint'],k=k,rank=rank,spec_index=SPECS.index(spec),weight_spec=spec)
   lid=digest(location);require(lid not in locations,'Unique rebound location');locations.add(lid)
   parent_reference=dict(ref('completed_index'),json_pointer='/'+section+'/'+str(i))
   row_reference=dict(parent_reference,json_pointer=parent_reference['json_pointer']+('/old_completed_row' if section!='new_tasks' else ''))
   result.append(dict(numerical_task_id=tid,old_completed_row=deepcopy(original),old_completed_row_reference=row_reference,new_location_identity=location,new_location_id=lid,verified_fit_data_sha256=matrix_cache[key],status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0,original_index_row=deepcopy(row),original_index_row_reference=parent_reference,prior_rebinding_row=deepcopy(row) if section!='new_tasks' else None))
 require(len(ids)==198 and len(matrix_cache)==66,'All198 identities/66 distinct matrices')
 for selected in matrix_cache:
  matching=[r for r in result if tuple(sorted(r['old_completed_row']['full_task']['numerical_identity']['selected']))==selected]
  require(len(matching)==3 and {r['new_location_identity']['weight_spec'] for r in matching}==set(SPECS),'All3 specs per old combination')
 return result

PRODUCER_FALSE=('fit_performed','task_readback_repeated','materialization_repeated','panel_audit_repeated','all_plan_tasks_completed','full_shard_completed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed')
INDEX_SOURCE=ROOT/'backtest/ndx_issuer_combination_index_research.py'
INDEX_SHA='bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b'
def producer_sources(documents):
 result={str(PRODUCER):PRODUCER_SHA,str(INDEX_SOURCE):INDEX_SHA}
 merge(result,codec.LOADED);merge(result,{ref(k)['path']:ref(k)['sha256'] for k in BOUND});merge(result,documents['plan']['plan']['fitter_source_hashes']);return result

def verify_candidate(value,documents):
 rows=reconstruct_rows(documents);plan=documents['plan']['plan']
 require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==9431859,'Complete new denominator')
 expected=dict(schema='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_V1',input_references={k:ref(k) for k in BOUND},rows=rows,externally_rebound_task_count=198,externally_rebound_combination_count=66,full_plan_task_denominator=9431859,remaining_uncompleted_task_count=9431661,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,**dict.fromkeys(PRODUCER_FALSE,False),source_hashes=producer_sources(documents))
 require(exact(value,expected),'Full rebound envelope/old references/new location/counters differ')
 return rows

def guard(sources):
 require(LOADED[str(Path(codec.__file__).resolve())]==CODEC_SHA,'Frozen codec mismatch')
 expected=dict(sources);merge(expected,LOADED);merge(expected,codec.LOADED)
 for p,h in expected.items():require(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Source drift')

def build():
 require(PRODUCER_SHA is not None and CANDIDATE_SHA is not None,'Actual producer/candidate pending')
 sources=dict(LOADED);guard(sources);documents={}
 for role in BOUND:
  r=ref(role);blob=Path(r['path']).read_bytes();require(codec.sha(blob)==r['sha256'],'Hard parent bytes');documents[role]=codec.loads(blob);merge(sources,{r['path']:r['sha256']})
 merge(sources,producer_sources(documents));guard(sources)
 blob=CANDIDATE.read_bytes();require(codec.sha(blob)==CANDIDATE_SHA,'Candidate external SHA');sources[str(CANDIDATE)]=CANDIDATE_SHA
 rows=verify_candidate(codec.loads(blob),documents);guard(sources)
 return dict(schema='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_INDEPENDENT_READBACK_V1',status='PASSED',candidate_reference=dict(path=str(CANDIDATE),sha256=CANDIDATE_SHA),producer_reference=dict(path=str(PRODUCER),sha256=PRODUCER_SHA),input_references={k:ref(k) for k in BOUND},source_hashes=sources,independent_readback_count=1,externally_rebound_task_count=198,externally_rebound_combination_count=66,full_plan_task_denominator=9431859,remaining_uncompleted_task_count=9431661,new_wrapper_call_attempt_count=0,new_fit_count=0,all_old_completed_rows_preserved_exact=True,new_locations_independently_counted=True,numerical_contracts_unchanged=True,verified_numerical_task_ids=[r['numerical_task_id'] for r in rows],**dict.fromkeys(FALSE,False))

def publish():
 require(not OUTPUT.exists() and OUTPUT.parent.is_dir() and {p.name for p in OUTPUT.parent.iterdir()}=={'rebinding.json'},'Exact unfinalized namespace')
 result=build();guard(result['source_hashes']);blob=codec.pretty(result)
 with OUTPUT.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 guard(result['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'rebinding.json',OUTPUT.name},'Publication bytes/namespace')
 return dict(path=str(OUTPUT),sha256=codec.sha(blob))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');args=p.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))
