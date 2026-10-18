"""Independent reference-only 504-task rebinding audit, no production imports."""
import json,hashlib,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data/cache/research/bulk_completed_task_rebinding_20261003_v1'
SHA='e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d';PUB='377db67bbf5be163b96d2f4a2b22f7b808668c0a66bf82d437c41573d2e4d3ec'
def check(v,m):
 if not v:raise ValueError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def exact(a,b):return canonical(a)==canonical(b)
def raw(r):
 b=Path(r['path']).read_bytes();check(hashlib.sha256(b).hexdigest()==r['sha256'],'SHA '+r['path']);return b
def read(r):return json.loads(raw(r))
def ranking_tables(groups):
 n=len(groups);table=[[0]*(n+1) for _ in range(n+1)];table[n][0]=1
 for i in range(n-1,-1,-1):
  table[i][0]=1
  for k in range(1,n+1):table[i][k]=table[i+1][k]+len(groups[i]['security_ids'])*table[i+1][k-1]
 return table

def verify():
 reference={'path':str(D/'rebinding.json'),'sha256':SHA};result=read(reference);pub=read({'path':str(D/'publication.json'),'sha256':PUB});start=json.loads((D/'started.json').read_bytes());refs=result['input_references']
 check(pub['rebinding_reference']==reference and pub['status']=='PUBLISHED_REFERENCE_ONLY','receipt')
 check(result['source_hashes']==pub['source_hashes']==start['source_hashes'],'source maps')
 for path,h in result['source_hashes'].items():raw({'path':path,'sha256':h})
 docs={k:read(r) for k,r in refs.items()};plan=docs['plan']['plan'];ctx=plan['context'];panel=docs['panel']['panel'];saved=docs['completed_index'];oldplan=docs['old_plan']['plan']
 expected_sources={str(ROOT/'scripts/bulk_completed_task_rebinding_20261003.py'):'eb010c710bf7a18ab7b5815f2d730c982b697e8f64164bdae69d3ada71c89abd',**{r['path']:r['sha256'] for r in refs.values()},**plan['fitter_source_hashes'],str(ROOT/'DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md'):'8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879',str(ROOT/'scripts/ndx_bulk_conditional_panel_independent_review_20261003.py'):'5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b'}
 check(expected_sources==result['source_hashes'],'complete source closure')
 check(docs['plan_publication']['plan_reference']==refs['plan'] and docs['plan_publication']['source_hashes']==docs['plan']['source_hashes'],'plan publication')
 check(docs['panel_publication']['panel_reference']==refs['panel'] and docs['panel_publication']['source_hashes']==docs['panel']['source_hashes'],'panel publication')
 check(ctx['parameters']==oldplan['context']['parameters'] and ctx['weight_specs']==oldplan['context']['weight_specs'] and ctx['previous_target_weights'] is None and plan['fitter_source_hashes']==oldplan['fitter_source_hashes'] and len(plan['fitter_source_hashes'])==25,'old numerical environment')
 check(exact(result['complete_observed_provenance_and_missing'],panel['observed_provenance_and_missing']) and len(result['complete_observed_provenance_and_missing'])==101 and result['preserved_panel_evidence_reference']==refs['panel'],'101 evidence')
 check(result['panel_audit_reference']==ctx['panel_audit_reference'],'saved audit reference')
 groups=plan['canonical_groups'];table=ranking_tables(groups);positions={s:(i,j) for i,g in enumerate(groups) for j,s in enumerate(g['security_ids'])}
 universe={r[panel['universe']['columns'].index('security_id')]:dict(zip(panel['universe']['columns'],r)) for r in panel['universe']['data']};frame=panel['returns'];dates=[d[:10] for d in frame['index']]
 check(len(dates)==126 and all(d==d[:10]+'T00:00:00' for d in frame['index']),'126 exact timestamps')
 def independent_rank(sids):
  ordered=sorted(sids,key=lambda s:positions[s]);check(len({positions[s][0] for s in ordered})==len(sids),'single issuer')
  rank=0;first=0;remaining=len(ordered)
  for sid in ordered:
   gi,variant=positions[sid]
   # Sum every lexicographically smaller permissible next issuer/SID branch.
   rank+=sum(len(groups[j]['security_ids'])*table[j+1][remaining-1] for j in range(first,gi))
   rank+=variant*table[gi+1][remaining-1];first=gi+1;remaining-=1
  return rank
 partitions=[('new_tasks',102),('externally_completed_rebound_rows',402)];expected_original=[]
 for key,n in partitions:
  check(len(saved[key])==n,'partition '+key)
  expected_original.extend((key,i,r) for i,r in enumerate(saved[key]))
 check(len(result['rows'])==504,'full504')
 matrix_cache={};combos={};location_ids=set();numeric_ids=set();rank_changes=0;large=0
 for output,(key,i,original) in zip(result['rows'],expected_original):
  nested=key=='externally_completed_rebound_rows';old=original['old_completed_row'] if nested else original;task=old['full_task'];num=task['numerical_identity'];sidorder=tuple(sorted(num['selected']))
  check(exact(output['old_completed_row'],old) and exact(output['original_index_row'],original) and exact(output['prior_rebinding_row'],original if nested else None),'original full nested evidence')
  pointer='/'+key+'/'+str(i);check(output['original_index_row_reference']==dict(refs['completed_index'],json_pointer=pointer) and output['old_completed_row_reference']==dict(refs['completed_index'],json_pointer=pointer+('/old_completed_row' if nested else '')),'both origin pointers')
  check(digest(num)==task['numerical_task_id']==old['numerical_task_id']==output['numerical_task_id'] and digest(task['location_identity'])==task['location_id'],'old fulltask identity')
  for field in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):check(output['old_completed_row'][field]==old[field] and len(old[field]['sha256'])==64,'completion ref '+field)
  if nested:check(original['numerical_task_id']==old['numerical_task_id'] and digest(original['new_location_identity'])==original['new_location_id'] and original['verified_fit_data_sha256']==old['fit_data_sha256'],'nested identity')
  selected={sid:{k:universe[sid][k] for k in ('ticker','issuer_id','risk_chain')} for sid in sidorder}
  if sidorder not in matrix_cache:
   tickers=[selected[s]['ticker'] for s in sidorder];indexes=[frame['columns'].index(t) for t in tickers];values=[[r[j] for j in indexes] for r in frame['data']]
   check(all(type(v) is float and math.isfinite(v) and v>-1 for r in values for v in r),'matrix floatcells')
   matrix_cache[sidorder]=digest({'dates':dates,'tickers':tickers,'returns':values})
  matrix=matrix_cache[sidorder]
  expected_num={'schema':'ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1','cutoff':ctx['decision_cutoff'],'holding_count':len(sidorder),'selected':selected,'weight_spec':num['weight_spec'],'parameters':ctx['parameters'],'requested_previous_target_weights':None,'fit_data_sha256':matrix,'fitter_source_fingerprint':digest(plan['fitter_source_hashes'])}
  check(exact(num,expected_num) and old['fit_data_sha256']==matrix==output['verified_fit_data_sha256'] and task['expected_fitter_previous_target_weights']=={},'complete numeric contract')
  k=len(sidorder);rank=independent_rank(sidorder);card=plan['cardinalities'][k-1];size=ctx['shard_size'];shard_start=rank//size*size;stop=min(shard_start+size,card['combination_count']);spec_index=ctx['weight_specs'].index(num['weight_spec'])
  identity=dict(ctx,k=k,start=shard_start,stop=stop)
  location={'schema':'ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1','plan_reference':refs['plan'],'plan_id':plan['plan_id'],'shard_id':digest(identity),'order_version':ctx['order_version'],'group_fingerprint':ctx['group_fingerprint'],'k':k,'rank':rank,'spec_index':spec_index,'weight_spec':num['weight_spec']}
  check(exact(output['new_location_identity'],location) and output['new_location_id']==digest(location),'independent location/rank')
  offset=sum(c['planned_combination_count'] for c in plan['cardinalities'] if c['k']<k);position={'local_shard_ordinal':rank//size,'global_shard_ordinal':sum(c['planned_shard_count'] for c in plan['cardinalities'] if c['k']<k)+rank//size,'start':shard_start,'stop':stop,'global_task_ordinal':(offset+rank)*3+spec_index}
  check(exact(output['new_lazy_position'],position),'lazy biginteger position');large+=position['global_task_ordinal']>2**53
  priorloc=original['new_location_identity'] if nested else task['location_identity'];rank_changes+=priorloc['rank']!=rank
  check(output['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and type(output['new_wrapper_call_attempt_count']) is int and output['new_wrapper_call_attempt_count']==0,'no new attempt')
  numeric_ids.add(output['numerical_task_id']);location_ids.add(output['new_location_id']);combos.setdefault(sidorder,[]).append(spec_index)
 check(len(numeric_ids)==len(location_ids)==504 and len(combos)==len(matrix_cache)==168 and all(sorted(v)==[0,1,2] for v in combos.values()),'504 unique/168x3')
 total=plan['planned_canonical_task_count'];check(total==6222659648236112670 and result['full_plan_task_denominator']==total and result['remaining_uncompleted_task_count']==total-504==6222659648236112166 and result['externally_rebound_task_count']==504 and result['externally_rebound_combination_count']==168,'deduct exactly once')
 check(result['new_fit_count']==result['new_wrapper_call_attempt_count']==0,'newfit zero')
 for d in (result,pub):
  for key in ('fit_performed','task_readback_repeated','materialization_repeated','panel_audit_repeated','all_plan_tasks_completed','full_shard_completed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed'):check(d[key] is False,'authority '+key)
 check({f.name for f in D.iterdir()}=={'started.json','rebinding.json','publication.json'},'namespace')
 return {'status':'PASS','source_count':len(expected_sources),'tasks':504,'combinations':168,'direct_original_rows':102,'nested_original_rows':402,'independent_matrix_hashes':168,'rank_changed_task_rows':rank_changes,'global_task_ordinals_above_2_to_53':large,'remaining':total-504,'new_fit_count':0,'rebinding_sha256':SHA,'publication_sha256':PUB}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
