"""Independent saved finite-preparation readback. Standard library only; no producer calls."""
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'data/cache/research/bulk_budgeted_search_prepare_20261003_v1'
RESULT_SHA='03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'
PUBLICATION_SHA='2471685a55d652a9e732b2a6cdf218232a192f07c3ed6e9e9824f95f5cb76212'
WRAPPER_SHA='35cbe7aef58362fc05d9ea06ed0e3104daeff6ef7d60e032a75d1344aac29125'
ORDER='BULK_ISSUER_COVER_STRATIFIED_RANK_V1'
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
PLAN_FALSE=('combination_enumeration_performed','task_inputs_materialized','fit_performed','old_fit_results_reused','old_plan_build_called','panel_audit_repeated','execution_authorized','point_in_time_verified','promotion_allowed','legal_training_input_admitted','full_transitive_source_closure_reverified','complete_ndx_eligible_pool_verified','continuous_weight_space_exhausted','winner_selected','dual_benchmark_evaluation_performed','oos_evaluation_performed')
OUTER_FALSE=('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','economic_comparison_performed','winner_selected','old_raw_reaudited')
MAT_FALSE=('fit_performed','wrapper_called','source_bytes_authenticated','source_bytes_reverified_at_call','identity_authenticated','point_in_time_verified','promotion_allowed','legal_training_input_admitted','execution_authorized','all_plan_tasks_completed','full_shard_completed','old_task_readback_repeated','old_weight_values_reaudited','anchor_alias_equivalence_verified')

def check(value,message):
 if not value:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def same(a,b,message):check(encode(a)==encode(b),message)
def bytes_at(reference):
 raw=Path(reference['path']).read_bytes();check(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Byte SHA: '+reference['path']);return raw
def read(reference):return json.loads(bytes_at(reference))
def merge(destination,source):
 for path,sha in source.items():
  check(path not in destination or destination[path]==sha,'Conflicting source');destination[path]=sha

class IndependentRanks:
 """Suffix polynomial coefficients, with explicit issuer/SID prefix branches."""
 def __init__(self,groups):
  self.groups=groups;self.n=len(groups);self.lookup={sid:(i,j) for i,g in enumerate(groups) for j,sid in enumerate(g['security_ids'])}
  self.suffix=[[0]*(self.n+1) for _ in range(self.n+1)];self.suffix[-1][0]=1
  for i in reversed(range(self.n)):
   self.suffix[i][0]=1
   for degree in range(1,self.n+1):self.suffix[i][degree]=self.suffix[i+1][degree]+len(groups[i]['security_ids'])*self.suffix[i+1][degree-1]
 def rank(self,prefix):
  check(prefix==sorted(prefix,key=self.lookup.__getitem__),'Canonical issuer/SID order')
  check(len({self.lookup[s][0] for s in prefix})==len(prefix),'Repeated issuer')
  first=0;rank=0;degree=len(prefix)
  for sid in prefix:
   issuer,variant=self.lookup[sid]
   rank+=sum(len(self.groups[i]['security_ids'])*self.suffix[i+1][degree-1] for i in range(first,issuer))
   rank+=variant*self.suffix[issuer+1][degree-1];first=issuer+1;degree-=1
  return rank
 def unrank(self,k,rank):
  check(type(rank) is int and 0<=rank<self.suffix[0][k],'Rank bounds')
  answer=[];first=0
  for degree in range(k,0,-1):
   found=False
   for i in range(first,self.n):
    block=self.suffix[i+1][degree-1]
    for sid in self.groups[i]['security_ids']:
     if rank<block:answer.append(sid);first=i+1;found=True;break
     rank-=block
    if found:break
   check(found,'Rank decoding')
  check(rank==0,'Residual rank');return answer

def verify_schedule(saved,plan,reference,oracle):
 seed=hashlib.sha256(b'NDX_BULK_CONDITIONAL_SEARCH_ROUND1_20261003').hexdigest()
 groups=oracle.groups;log=[];positions=[];strata=[];per_k={}
 def append(k,rank,kind,extra):
  duplicate=rank in selected;event={'proposal_index':len(log),'k':k,'rank':rank,'selection_kind':kind,'outcome':'DUPLICATE' if duplicate else 'ACCEPTED',**extra}
  log.append(event)
  if not duplicate:selected.add(rank);positions.append({'k':k,'rank':rank,'prefix_security_ids':oracle.unrank(k,rank),'selection_kind':kind,'proposal_index':event['proposal_index']})
 def sample(k,low,high,kind,stratum,attempt):
  width=high-low;bits=(width-1).bit_length();needed=max(1,(bits+7)//8)
  # Two SHA-256 rounds over canonical JSON are intentional frozen draw semantics.
  stream=b''.join(hashlib.sha256(hashlib.sha256(encode([ORDER,seed,plan['plan_id'],k,kind,stratum,attempt,block])).digest()).digest() for block in range((needed+31)//32))
  value=int.from_bytes(stream[:needed],'big') % (2**bits)
  extra={'interval_start':low,'interval_stop':high,'stratum_index':stratum,'draw_index':attempt}
  if value>=width:log.append({'proposal_index':len(log),'k':k,'rank':None,'selection_kind':kind,'outcome':'HASH_RANGE_REJECTED',**extra})
  else:append(k,low+value,kind,extra)
 for k in range(4,21):
  selected=set();permutation=sorted(range(76),key=lambda i:(digest([ORDER,seed,plan['plan_id'],k,groups[i]['issuer_id']]),groups[i]['issuer_id']))
  covers=[]
  for begin in range(0,76,k):covers.append([groups[i]['security_ids'][0] for i in sorted(permutation[(begin+j)%76] for j in range(k))])
  for group in groups:
   block=next(row for row in covers if group['security_ids'][0] in row)
   for alternate in group['security_ids'][1:]:covers.append([alternate if sid==group['security_ids'][0] else sid for sid in block])
  coverage_ranks=list(dict.fromkeys(oracle.rank(row) for row in covers))
  for rank in coverage_ranks:append(k,rank,'SID_COVERAGE',{})
  remainder=32-len(coverage_ranks);total=oracle.suffix[0][k]
  for j in range(remainder):
   low=j*total//remainder;high=(j+1)*total//remainder;strata.append({'k':k,'stratum_index':j,'start':low,'stop':high});attempt=0
   while sum(low<=r<high for r in selected)<high-low:
    before=len(selected);sample(k,low,high,'STRATIFIED_RANK',j,attempt);attempt+=1
    check(len(log)<=4096,'Exhausted proposal budget')
    if len(selected)>before:break
  attempt=0
  while len(selected)<32:sample(k,0,total,'STRATIFIED_REFILL',-1,attempt);attempt+=1;check(len(log)<=4096,'Refill budget')
  check(len(selected)==32,'Per-k exact32');per_k[str(k)]={'coverage_positions':len(coverage_ranks),'stratified_positions':remainder}
 coverage=[]
 for card in plan['cardinalities']:
  k=card['k'];rows=[r for r in positions if r['k']==k];exposures={sid:0 for sid in oracle.lookup}
  for row in rows:
   for sid in row['prefix_security_ids']:exposures[sid]+=1
  coverage.append({'k':k,'combination_count':card['combination_count'],'necessary_bound_certificates':card['necessary_bound_certificates'],'requested_position_count':32 if 4<=k<=20 else 0,'selected_position_count':len(rows),'unselected_planned_combination_count':card['planned_combination_count']-len(rows),'security_exposures':exposures,'all_security_ids_covered':all(exposures.values()),'issuer_exposures':{g['issuer_id']:sum(exposures[s] for s in g['security_ids']) for g in groups}})
  if rows:check(all(exposures.values()),'Every77SID covered per k');per_k[str(k)]['min_security_exposure']=min(exposures.values());per_k[str(k)]['max_security_exposure']=max(exposures.values())
 expected=dict(schema='BULK_BUDGETED_SEARCH_POSITIONS_V1',order_version=ORDER,status='PLANNED_NOT_ATTEMPTED',materialization_allowed=True,plan_content_sha256=plan['content_sha256'],plan_id=plan['plan_id'],seed_hex=seed,combinations_per_k={str(k):32 for k in range(4,21)},max_proposals=4096,proposal_budget_scope='GLOBAL_INCLUDING_HASH_REJECTION_AND_DUPLICATES',positions=positions,cardinality_coverage=coverage,strata=strata,proposal_log=log,proposal_count=len(log),requested_position_count=544,selected_position_count=544,all_k_combination_count=plan['all_k_combination_count'],planned_combination_count=plan['planned_combination_count'],planned_canonical_task_count=plan['planned_canonical_task_count'],unselected_planned_combination_count=plan['planned_combination_count']-544,existing_completed_reference=reference,existing_completion_used_to_change_selection=False,completed_task_count=0,source_bytes_authenticated=False,risk_feasibility_proven=False,uniform_combination_sampling_claimed=False,global_optimum_proven=False,**dict.fromkeys(PLAN_FALSE,False))
 expected.update(combination_enumeration_performed=True,full_domain_enumeration_performed=False,enumerated_position_count=544);expected['content_sha256']=digest(expected)
 same(saved,expected,'Complete independent schedule/hash stream/coverage/log')
 return positions,per_k,dict(Counter(r['outcome'] for r in log))

def verify():
 own_ref={'path':str(DIRECTORY/'preparation.json'),'sha256':RESULT_SHA};result=read(own_ref)
 publication=read({'path':str(DIRECTORY/'publication.json'),'sha256':PUBLICATION_SHA});started=json.loads((DIRECTORY/'started.json').read_bytes())
 check({p.name for p in DIRECTORY.iterdir()}=={'started.json','preparation.json','publication.json'},'Successful namespace')
 same(publication,dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1',status='PREPARED_NOT_ATTEMPTED',preparation_reference=own_ref,source_hashes=result['source_hashes'],**dict.fromkeys(OUTER_FALSE,False)),'Publication full envelope')
 same(started,dict(source_hashes=result['source_hashes'],retry_allowed=False,**dict.fromkeys(OUTER_FALSE,False)),'Started full envelope')
 wrapper=ROOT/'scripts/ndx_bulk_budgeted_search_prepare_20261003.py';raw=bytes_at({'path':str(wrapper),'sha256':WRAPPER_SHA})
 # Read only immutable literal source-binding manifests; never execute/import producer code.
 literals={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse(raw).body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'PINS','CODE_PINS','AUDIT_PINS'}}
 refs={role:{'path':str(ROOT/relative),'sha256':sha} for role,(relative,sha) in literals['PINS'].items()};same(result['input_references'],refs,'Exact7 bound inputs')
 docs={k:read(ref) for k,ref in refs.items()};plan=docs['plan']['plan'];context=plan['context'];panel=docs['panel']['panel'];saved=docs['rebinding'];mat=result['materialized']
 expected_sources={str(wrapper):WRAPPER_SHA};merge(expected_sources,{r['path']:r['sha256'] for r in refs.values()});merge(expected_sources,plan['fitter_source_hashes'])
 for manifest in ('CODE_PINS','AUDIT_PINS'):merge(expected_sources,{str(ROOT/p):h for p,h in literals[manifest].items()})
 same(expected_sources,result['source_hashes'],'Exact source closure')
 for path,sha in expected_sources.items():bytes_at({'path':path,'sha256':sha})
 same(mat['materializer_loaded_source_hashes'],{str(ROOT/p):h for p,h in literals['CODE_PINS'].items()},'Loaded mathematical source closure')
 for role,status in [('plan','PLANNED_NOT_ENUMERATED'),('panel','PUBLISHED_CONDITIONAL_PANEL_ONLY'),('rebinding','PUBLISHED_REFERENCE_ONLY')]:
  receipt=docs[role+'_publication'];check(receipt[role+'_reference']==refs[role] and receipt['status']==status,'Parent publication binding');same(receipt['source_hashes'],docs[role]['source_hashes'],'Parent source closure reference')
  check({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'started.json',role+'.json','publication.json'},'Successful parent')
 same(result['contract'],docs['contract'],'Contract unchanged')
 same(result['complete_observed_provenance_and_missing'],docs['plan']['complete_observed_provenance_and_missing'],'101 plan provenance');same(result['complete_observed_provenance_and_missing'],panel['observed_provenance_and_missing'],'101 panel provenance');same(result['complete_observed_provenance_and_missing'],saved['complete_observed_provenance_and_missing'],'101 saved provenance');check(len(result['complete_observed_provenance_and_missing'])==101,'101 denominator')
 expected_sidecars={key:dict(refs['panel'],json_pointer='/'+key) for key in SIDECARS};same(result['preserved_evidence_sidecar_references'],expected_sidecars,'Seven sidecar refs');same(docs['plan']['preserved_evidence_sidecar_references'],expected_sidecars,'Plan sidecar refs');check(all(k in docs['panel'] for k in SIDECARS),'Sidecar target exists')
 groups=plan['canonical_groups'];oracle=IndependentRanks(groups);check(len(groups)==76 and len(oracle.lookup)==77,'77/76 universe')
 check(context['previous_target_weights'] is None and len(plan['fitter_source_hashes'])==25 and context['fitter_source_fingerprint']==digest(plan['fitter_source_hashes']),'Full original numerical environment')
 positions,per_k,log_counts=verify_schedule(result['schedule'],plan,refs['rebinding'],oracle)
 frame=panel['returns'];universe={row[panel['universe']['columns'].index('security_id')]:dict(zip(panel['universe']['columns'],row)) for row in panel['universe']['data']};dates=[t[:10] for t in frame['index']]
 check(len(dates)==126 and dates==sorted(set(dates)) and dates[-1]==context['decision_cutoff'] and all(t==t[:10]+'T00:00:00' for t in frame['index']),'Full126 dates')
 check(len(frame['columns'])==77 and frame['dtypes']==['float64']*77 and all(len(row)==77 and all(type(v) is float and math.isfinite(v) and v>-1 for v in row) for row in frame['data']),'Entire matrix including unselected values')
 same([{'issuer_id':issuer,'security_ids':sorted(s for s,u in universe.items() if u['issuer_id']==issuer)} for issuer in sorted({u['issuer_id'] for u in universe.values()})],groups,'Full universe grouping')
 check(len(saved['rows'])==504,'Saved504 denominator');old={row['numerical_task_id']:(row,i) for i,row in enumerate(saved['rows'])};check(len(old)==504,'Unique504 IDs')
 # Saved weights/raw readback are trusted only by their existing bound index, never re-audited here.
 selected_ids=[];new_ids=[];all_numeric=set();all_locations=set();exposures={};matrix_cells=0;combinations=mat['combinations'];check(len(combinations)==544,'544 complete combinations')
 for position,combo in zip(positions,combinations):
  prefix=position['prefix_security_ids'];k=position['k'];rank=position['rank'];check(oracle.rank(prefix)==rank,'Independent reverse rank');order=sorted(prefix)
  selected={sid:{name:universe[sid][name] for name in ('ticker','issuer_id','risk_chain')} for sid in order};tickers=[selected[s]['ticker'] for s in order];columns=[frame['columns'].index(t) for t in tickers]
  matrix={'dates':dates,'tickers':tickers,'returns':[[row[i] for i in columns] for row in frame['data']]};matrix_sha=digest(matrix);matrix_cells+=126*k
  check(combo['k']==k and combo['rank']==rank,'Position pairing');same(combo['selection_position'],position,'Exact saved selection');same(combo['prefix_security_ids'],prefix,'Prefix');same(combo['fitter_sorted_security_ids'],order,'Fitter sortedSID');same(combo['fit_matrix'],matrix,'Full matrix values');check(combo['fit_data_sha256']==matrix_sha,'Matrix SHA')
  check(set(combo)=={'k','rank','prefix_security_ids','fitter_sorted_security_ids','selection_position','fit_matrix','fit_data_sha256','tasks'} and len(combo['tasks'])==3,'Exact combo shape/three specs')
  size=context['shard_size'];start=rank//size*size;stop=min(start+size,oracle.suffix[0][k]);shard=digest(dict(context,k=k,start=start,stop=stop))
  for spec_index,(spec,task) in enumerate(zip(context['weight_specs'],combo['tasks'])):
   numerical=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=context['decision_cutoff'],holding_count=k,selected=selected,weight_spec=spec,parameters=context['parameters'],requested_previous_target_weights=None,fit_data_sha256=matrix_sha,fitter_source_fingerprint=context['fitter_source_fingerprint'])
   location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=refs['plan'],plan_id=plan['plan_id'],shard_id=shard,order_version=context['order_version'],group_fingerprint=context['group_fingerprint'],k=k,rank=rank,spec_index=spec_index,weight_spec=spec)
   tid=digest(numerical);lid=digest(location);expected=dict(numerical_task_id=tid,numerical_identity=numerical,location_id=lid,location_identity=location,expected_fitter_previous_target_weights={},wrapper_call_attempt_count=0,fit_performed=False,anchor_alias_equivalence_verified=False)
   if tid in old:
    row,i=old[tid];same(row['old_completed_row']['full_task']['numerical_identity'],numerical,'Complete reused contract');same(row['new_location_identity'],location,'Reused location')
    expected.update(status='EXTERNALLY_COMPLETED_REFERENCE_ONLY',completed_reference=dict(refs['rebinding'],json_pointer='/rows/'+str(i)),complete_saved_rebinding_row=row);selected_ids.append(tid)
   else:expected.update(status='MATERIALIZED_NOT_ATTEMPTED',completed_reference=None,complete_saved_rebinding_row=None);new_ids.append(tid)
   same(task,expected,'Complete task envelope identity/reference/noattempt');check(tid not in all_numeric and lid not in all_locations,'Unique numerical/location');all_numeric.add(tid);all_locations.add(lid)
  entry=exposures.setdefault(str(k),dict(combination_count=0,security_occurrence_count=0,risk_chain_occurrence_counts={},security_occurrences=[]));entry['combination_count']+=1
  for sid,coordinate in selected.items():
   risk=coordinate['risk_chain'];entry['security_occurrence_count']+=1;entry['risk_chain_occurrence_counts'][risk]=entry['risk_chain_occurrence_counts'].get(risk,0)+1;entry['security_occurrences'].append(dict(rank=rank,security_id=sid,**coordinate))
 check(len(all_numeric)==len(all_locations)==1632 and set(selected_ids)==all_numeric.intersection(old) and not set(new_ids).intersection(old),'Exact504 intersection and uniqueness')
 total=plan['planned_canonical_task_count'];check(total==6222659648236112670,'Original full denominator')
 expected_mat=dict(schema='BULK_LAZY_TASK_MATERIALIZATION_V1',status='BOUNDED_INPUTS_MATERIALIZED_NO_EXECUTION',plan_reference=refs['plan'],plan_id=plan['plan_id'],panel_reference=refs['panel'],panel_audit_reference=context['panel_audit_reference'],panel_content_sha256=panel['panel_content_sha256'],fitter_source_hashes=plan['fitter_source_hashes'],completed_rebinding_reference=refs['rebinding'],complete_saved_completed_task_count=504,selected_completed_intersection_count=len(selected_ids),new_unattempted_task_count=len(new_ids),materialized_task_count=1632,combination_count=544,max_combinations=544,full_plan_task_denominator=total,remaining_full_plan_uncompleted_count=total-504,selected_completed_numerical_task_ids=selected_ids,new_unattempted_numerical_task_ids=new_ids,combinations=combinations,materializer_loaded_source_hashes=mat['materializer_loaded_source_hashes'],risk_chain_exposures=exposures,risk_chain_exposure_definition='SECURITY_OCCURRENCES_IN_COMBINATIONS_NOT_WEIGHT_OR_NEW_RISK_GATE',new_wrapper_call_attempt_count=0,new_fit_count=0,**dict.fromkeys(MAT_FALSE,False))
 same(mat,expected_mat,'Complete materialization envelope/exposures/zeroattempt')
 expected_outer=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_V1',status='PREPARED_NOT_ATTEMPTED',input_references=refs,contract=docs['contract'],schedule=result['schedule'],materialized=mat,complete_observed_provenance_and_missing=panel['observed_provenance_and_missing'],preserved_evidence_sidecar_references=expected_sidecars,original_completed_task_count=504,new_fit_count=0,new_wrapper_call_attempt_count=0,full_plan_task_denominator=total,remaining_uncompleted_task_count=total-504,source_hashes=expected_sources,**dict.fromkeys(OUTER_FALSE,False))
 same(result,expected_outer,'Complete outer authority/remaining/scope')
 return dict(status='PASS',preparation_sha256=RESULT_SHA,publication_sha256=PUBLICATION_SHA,reader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_count=len(expected_sources),combinations=544,tasks=1632,independent_matrix_cells=matrix_cells,cardinalities=list(range(4,21)),all77_securities_covered_per_cardinality=True,proposal_log_counts=log_counts,proposal_count=sum(log_counts.values()),strata_count=len(result['schedule']['strata']),per_cardinality=per_k,old_completed_reference_count=504,selected_completed_intersection_count=len(selected_ids),new_unattempted_tasks=len(new_ids),full_plan_task_denominator=total,remaining_uncompleted_task_count=total-504,unselected_planned_combinations=plan['planned_combination_count']-544,unmaterialized_planned_tasks=total-1632,new_fit_count=0,point_in_time_verified=False,full_search_completed=False,old_raw_readback_repeated=False)

if __name__=='__main__':print(json.dumps(verify(),indent=2))
